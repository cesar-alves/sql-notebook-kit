import * as vscode from 'vscode';
import {
  collectionFromMetadata,
  metadataWithCollection,
  type BridgeMessage,
  type Collection
} from '@redshift-notebooks/protocol';

export function activate(context: vscode.ExtensionContext): void {
  const channel = vscode.notebooks.createRendererMessaging('redshift-notebooks-bridge');
  context.subscriptions.push(channel.onDidReceiveMessage(async event => {
    const request = event.message as BridgeMessage;
    const notebook = event.editor.notebook;
    const cell = notebook.getCells().find(item => item.metadata.id === request.cell_id);
    if (!cell) return;
    const current = collectionFromMetadata(cell.metadata);
    if (request.operation === 'load') {
      await channel.postMessage({ ...request, operation: 'load_result', payload: { collection: current } }, event.editor);
      return;
    }
    if (request.operation === 'save') {
      if (request.payload.expected_revision !== current.revision) {
        await channel.postMessage({ ...request, operation: 'save_result', payload: { conflict: true, collection: current } }, event.editor);
        return;
      }
      const next = request.payload.collection as Collection;
      const edit = new vscode.WorkspaceEdit();
      edit.set(notebook.uri, [
        vscode.NotebookEdit.updateCellMetadata(
          cell.index,
          metadataWithCollection(cell.metadata, next)
        )
      ]);
      const applied = await vscode.workspace.applyEdit(edit);
      await channel.postMessage({
        ...request,
        operation: applied ? 'save_result' : 'error',
        payload: applied ? { revision: next.revision } : { message: 'The notebook is read-only.' }
      }, event.editor);
    }
  }));
}

export function deactivate(): void {}
