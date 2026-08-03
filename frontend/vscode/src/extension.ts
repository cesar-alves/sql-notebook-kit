import * as vscode from 'vscode';
import { Buffer } from 'node:buffer';
import {
  collectionFromMetadata,
  isBridgeMessage,
  isCollection,
  metadataWithCollection,
  type BridgeMessage,
  type Collection
} from '@redshift-notebooks/protocol';
import {
  DeliveryCoordinator,
  executeWithTimeout,
  kernelOutputError,
  waitForReadyKernel,
  type DeliveryKernel
} from './delivery.js';

interface JupyterKernel {
  readonly status: string;
  readonly onDidChangeStatus: vscode.Event<string>;
  executeCode(code: string, token: vscode.CancellationToken): AsyncIterable<unknown>;
}

interface JupyterApi {
  kernels: { getKernel(uri: vscode.Uri): Thenable<JupyterKernel | undefined> };
}

const sessions = new Map<string, string>();
const coordinators = new Map<string, DeliveryCoordinator>();
const keyFor = (notebook: vscode.NotebookDocument, cellId: string) =>
  `${notebook.uri.toString()}\n${cellId}`;

async function activeKernel(notebook: vscode.NotebookDocument): Promise<JupyterKernel | undefined> {
  const extension = vscode.extensions.getExtension<JupyterApi>('ms-toolsai.jupyter');
  if (!extension) return undefined;
  const api = extension.isActive ? extension.exports : await extension.activate();
  return api?.kernels.getKernel(notebook.uri);
}

function adaptKernel(kernel: JupyterKernel): DeliveryKernel {
  return {
    get status() { return kernel.status; },
    onDidChangeStatus: listener => kernel.onDidChangeStatus(listener),
    async execute(code: string, signal: AbortSignal): Promise<void> {
      const cancellation = new vscode.CancellationTokenSource();
      const cancel = () => cancellation.cancel();
      signal.addEventListener('abort', cancel, { once: true });
      try {
        for await (const output of kernel.executeCode(code, cancellation.token)) {
          const error = kernelOutputError(output);
          if (error) throw error;
        }
      } finally {
        signal.removeEventListener('abort', cancel);
        cancellation.dispose();
      }
    }
  };
}

async function deliveryKernel(notebook: vscode.NotebookDocument): Promise<DeliveryKernel | undefined> {
  const kernel = await activeKernel(notebook);
  return kernel ? adaptKernel(kernel) : undefined;
}

async function deliver(
  notebook: vscode.NotebookDocument,
  message: BridgeMessage,
  signal: AbortSignal
): Promise<void> {
  const kernel = await waitForReadyKernel(() => deliveryKernel(notebook), signal);
  const encoded = Buffer.from(JSON.stringify(message), 'utf8').toString('base64');
  const code = `from redshift_notebooks.visualize.protocol import ` +
    `_deliver_vscode_response as _rn_d;_rn_d(${JSON.stringify(encoded)})`;
  await executeWithTimeout(kernel, code, signal);
}

function coordinatorFor(notebook: vscode.NotebookDocument): DeliveryCoordinator {
  const notebookKey = notebook.uri.toString();
  const existing = coordinators.get(notebookKey);
  if (existing) return existing;
  const coordinator = new DeliveryCoordinator(
    (message, signal) => deliver(notebook, message, signal),
    {
      onExhausted(message, error) {
        void activeKernel(notebook).then(kernel => {
          console.error('Redshift Notebooks bridge delivery exhausted.', {
            notebook: notebookKey,
            cell: message.cell_id,
            operation: message.operation,
            kernelStatus: kernel?.status ?? 'missing',
            error
          });
        });
      }
    }
  );
  coordinators.set(notebookKey, coordinator);
  return coordinator;
}

function queueDelivery(notebook: vscode.NotebookDocument, message: BridgeMessage): void {
  const sessionKey = keyFor(notebook, message.cell_id);
  void coordinatorFor(notebook).enqueue(
    message,
    () => sessions.get(sessionKey) === message.session_id
  ).catch(() => { /* exhaustion is logged by the coordinator */ });
}

function closeNotebook(notebook: vscode.NotebookDocument): void {
  const notebookKey = notebook.uri.toString();
  coordinators.get(notebookKey)?.close();
  coordinators.delete(notebookKey);
  const prefix = `${notebookKey}\n`;
  for (const key of sessions.keys()) if (key.startsWith(prefix)) sessions.delete(key);
}

function closeAll(): void {
  for (const coordinator of coordinators.values()) coordinator.close();
  coordinators.clear();
  sessions.clear();
}

function response(
  request: BridgeMessage,
  operation: BridgeMessage['operation'],
  payload: Record<string, unknown>
): BridgeMessage {
  return { ...request, operation, payload };
}

async function handleMessage(event: {
  editor: vscode.NotebookEditor;
  message: unknown;
}): Promise<void> {
  if (!isBridgeMessage(event.message)) return;
  const request = event.message;
  if (!['capabilities', 'load', 'save', 'theme_changed'].includes(request.operation)) return;
  const notebook = event.editor.notebook;
  const cell = notebook.getCells().find(item => item.document.uri.toString() === request.cell_id);
  if (!cell) return;

  const sessionKey = keyFor(notebook, request.cell_id);
  if (request.operation === 'capabilities') {
    sessions.set(sessionKey, request.session_id);
    const writable = vscode.workspace.fs.isWritableFileSystem(notebook.uri.scheme) !== false;
    queueDelivery(notebook, response(request, 'capabilities_result', {
      persistence: writable,
      reason: writable ? undefined : 'The notebook file system is read-only.'
    }));
    return;
  }
  if (sessions.get(sessionKey) !== request.session_id) return;
  if (request.operation === 'theme_changed') {
    queueDelivery(notebook, request);
    return;
  }
  try {
    const current = collectionFromMetadata(cell.metadata);
    if (request.operation === 'load') {
      queueDelivery(notebook, response(request, 'load_result', { collection: current }));
      return;
    }
    const expected = request.payload.expected_revision;
    const next = request.payload.collection;
    if (!Number.isSafeInteger(expected) || !isCollection(next) || next.revision !== current.revision + 1) {
      queueDelivery(notebook, response(request, 'error', {
        message: 'The visualization save request is invalid.'
      }));
      return;
    }
    if (expected !== current.revision) {
      queueDelivery(notebook, response(request, 'save_result', {
        conflict: true, collection: current
      }));
      return;
    }
    const edit = new vscode.WorkspaceEdit();
    edit.set(notebook.uri, [vscode.NotebookEdit.updateCellMetadata(
      cell.index, metadataWithCollection(cell.metadata, next as Collection)
    )]);
    const applied = await vscode.workspace.applyEdit(edit);
    queueDelivery(notebook, response(request, applied ? 'save_result' : 'error',
      applied ? { revision: next.revision } : { message: 'The notebook is read-only.' }));
  } catch (error) {
    queueDelivery(notebook, response(request, 'error', {
      message: error instanceof Error ? error.message : 'Visualization persistence failed.'
    }));
  }
}

export function activate(context: vscode.ExtensionContext): void {
  const channel = vscode.notebooks.createRendererMessaging('redshift-notebooks-bridge');
  context.subscriptions.push(channel.onDidReceiveMessage(event => {
    void handleMessage(event).catch(error => {
      console.error('Redshift Notebooks bridge request failed.', error);
    });
  }));
  context.subscriptions.push(vscode.workspace.onDidCloseNotebookDocument(closeNotebook));
}

export function deactivate(): void {
  closeAll();
}
