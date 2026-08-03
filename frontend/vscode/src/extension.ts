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

interface JupyterKernel {
  readonly status: string;
  readonly onDidChangeStatus: vscode.Event<string>;
  executeCode(code: string, token: vscode.CancellationToken): AsyncIterable<unknown>;
}

interface JupyterApi {
  kernels: { getKernel(uri: vscode.Uri): Thenable<JupyterKernel | undefined> };
}

const sessions = new Map<string, string>();
const keyFor = (notebook: vscode.NotebookDocument, cellId: string) =>
  `${notebook.uri.toString()}\n${cellId}`;

async function activeKernel(notebook: vscode.NotebookDocument): Promise<JupyterKernel | undefined> {
  const extension = vscode.extensions.getExtension<JupyterApi>('ms-toolsai.jupyter');
  if (!extension) return undefined;
  const api = extension.isActive ? extension.exports : await extension.activate();
  return api?.kernels.getKernel(notebook.uri);
}

async function waitUntilIdle(kernel: JupyterKernel, timeoutMs = 10_000): Promise<boolean> {
  if (kernel.status === 'idle') return true;
  return new Promise(resolve => {
    const timer = setTimeout(() => { subscription.dispose(); resolve(false); }, timeoutMs);
    const subscription = kernel.onDidChangeStatus(status => {
      if (status === 'idle') {
        clearTimeout(timer);
        subscription.dispose();
        resolve(true);
      }
    });
  });
}

async function deliver(kernel: JupyterKernel, message: BridgeMessage): Promise<void> {
  if (!(await waitUntilIdle(kernel))) return;
  const encoded = Buffer.from(JSON.stringify(message), 'utf8').toString('base64');
  const code =
    `from redshift_notebooks.visualize.protocol import _deliver_vscode_response as _rn_d;` +
    `_rn_d(${JSON.stringify(encoded)})`;
  const cancellation = new vscode.CancellationTokenSource();
  const timer = setTimeout(() => cancellation.cancel(), 10_000);
  try {
    for await (const _output of kernel.executeCode(code, cancellation.token)) { /* consume */ }
  } finally {
    clearTimeout(timer);
    cancellation.dispose();
  }
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
  const kernel = await activeKernel(notebook);
  if (!cell || !kernel) return;

  const sessionKey = keyFor(notebook, request.cell_id);
  if (request.operation === 'capabilities') {
    sessions.set(sessionKey, request.session_id);
    const writable = vscode.workspace.fs.isWritableFileSystem(notebook.uri.scheme) !== false;
    await deliver(kernel, response(request, 'capabilities_result', {
      persistence: writable,
      reason: writable ? undefined : 'The notebook file system is read-only.'
    }));
    return;
  }
  if (sessions.get(sessionKey) !== request.session_id) return;
  if (request.operation === 'theme_changed') {
    await deliver(kernel, request);
    return;
  }
  try {
    const current = collectionFromMetadata(cell.metadata);
    if (request.operation === 'load') {
      await deliver(kernel, response(request, 'load_result', { collection: current }));
      return;
    }
    const expected = request.payload.expected_revision;
    const next = request.payload.collection;
    if (!Number.isSafeInteger(expected) || !isCollection(next) || next.revision !== current.revision + 1) {
      await deliver(kernel, response(request, 'error', {
        message: 'The visualization save request is invalid.'
      }));
      return;
    }
    if (expected !== current.revision) {
      await deliver(kernel, response(request, 'save_result', {
        conflict: true, collection: current
      }));
      return;
    }
    const edit = new vscode.WorkspaceEdit();
    edit.set(notebook.uri, [vscode.NotebookEdit.updateCellMetadata(
      cell.index, metadataWithCollection(cell.metadata, next as Collection)
    )]);
    const applied = await vscode.workspace.applyEdit(edit);
    await deliver(kernel, response(request, applied ? 'save_result' : 'error',
      applied ? { revision: next.revision } : { message: 'The notebook is read-only.' }));
  } catch (error) {
    await deliver(kernel, response(request, 'error', {
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
  context.subscriptions.push(vscode.workspace.onDidCloseNotebookDocument(notebook => {
    const prefix = `${notebook.uri.toString()}\n`;
    for (const key of sessions.keys()) if (key.startsWith(prefix)) sessions.delete(key);
  }));
}

export function deactivate(): void {
  sessions.clear();
}
