import type { JupyterFrontEnd, JupyterFrontEndPlugin } from '@jupyterlab/application';
import { IThemeManager } from '@jupyterlab/apputils';
import { IEditorLanguageRegistry, type IEditorLanguage } from '@jupyterlab/codemirror';
import { INotebookTracker, type NotebookPanel } from '@jupyterlab/notebook';
import { IRenderMimeRegistry, RenderedError } from '@jupyterlab/rendermime';
import type { IRenderMime } from '@jupyterlab/rendermime-interfaces';
import type { KernelMessage } from '@jupyterlab/services';
import { StandardSQL, sql } from '@codemirror/lang-sql';
import { Widget } from '@lumino/widgets';
import { isManagedSql, safeFilename, writeClipboardText } from './helpers.js';
import { applyJupyterTheme, resolveJupyterTheme } from './theme.js';
import {
  COMM_TARGET,
  PROTOCOL_VERSION,
  collectionFromMetadata,
  emptyCollection,
  isCollection,
  isBridgeMessage,
  metadataWithCollection,
  installTableCopy,
  type BridgeMessage,
  type Collection
} from '@sql-notebook-kit/protocol';
import '../style/index.css';

const activeComms = new Map<any, { cellId: string; sessionId: string }>();
let currentTheme: 'light' | 'dark' | 'high_contrast' = 'light';
let themeTimer: number | undefined;
const SQL_MIME = 'text/x-sql-notebook-kit';

interface PlotlyElement extends HTMLElement {
  _fullLayout?: { width?: number; height?: number };
}

interface PlotlyApi {
  toImage(element: PlotlyElement, options: Record<string, unknown>): Promise<string>;
}

interface SaveFileHandle {
  createWritable(): Promise<{ write(data: Blob): Promise<void>; close(): Promise<void> }>;
}

type SavePicker = (options: Record<string, unknown>) => Promise<SaveFileHandle>;

function attachSqlHighlighting(panel: NotebookPanel): void {
  const observed = new WeakSet<object>();
  const update = (cell: any) => {
    if (!cell?.model?.sharedModel) return;
    const apply = () => {
      const source = cell.model.sharedModel.getSource() as string;
      cell.model.mimeType = isManagedSql(source) ? SQL_MIME : panel.content.codeMimetype;
    };
    apply();
    if (!observed.has(cell.model.sharedModel)) {
      observed.add(cell.model.sharedModel);
      cell.model.sharedModel.changed.connect(apply);
    }
  };
  const updateAll = () => panel.content.widgets.forEach(update);
  updateAll();
  (panel.content.model?.cells as any)?.changed?.connect(updateAll);
}

function exportStatus(root: Element, message: string, error = false): void {
  const target = root.querySelector<HTMLElement>('.snk-export-status');
  if (!target) return;
  target.textContent = message;
  target.classList.toggle('snk-error', error);
}

function dataUrlBlob(value: string): Promise<Blob> {
  return fetch(value).then(response => response.blob());
}

function downloadBlob(blob: Blob, filename: string): void {
  const anchor = document.createElement('a');
  anchor.href = URL.createObjectURL(blob);
  anchor.download = filename;
  anchor.click();
  window.setTimeout(() => URL.revokeObjectURL(anchor.href), 0);
}

async function exportPlot(root: Element): Promise<void> {
  const plot = root.querySelector<PlotlyElement>('.js-plotly-plot');
  const plotly = (window as unknown as { Plotly?: PlotlyApi }).Plotly;
  const cached = root.querySelector<HTMLImageElement>('img.plot-img[src^="data:image/png"]')?.src;
  if (!plot && !cached) {
    exportStatus(root, 'The rendered visualization is not ready to export.', true);
    return;
  }
  if (plot && !plotly?.toImage && !cached) {
    const modebar = root.querySelector<HTMLElement>(
      '.modebar-btn[data-title*="Download plot"], .modebar-btn[data-title*="png"]'
    );
    if (modebar) {
      modebar.click();
      exportStatus(root, 'Downloaded PNG using Plotly.');
    } else {
      exportStatus(root, 'This frontend cannot export the rendered visualization.', true);
    }
    return;
  }
  const selected = root.querySelector<HTMLElement>('.snk-tabs button[aria-pressed="true"]');
  const filename = safeFilename(selected?.textContent ?? 'visualization');
  const width = Math.max(1, plot?._fullLayout?.width ?? plot?.clientWidth ?? 1);
  const height = Math.max(1, plot?._fullLayout?.height ?? plot?.clientHeight ?? 1);
  const png = plot && plotly?.toImage
    ? plotly.toImage(plot, { format: 'png', width, height, scale: 2 })
    : Promise.resolve(cached as string);
  const picker = (window as unknown as { showSaveFilePicker?: SavePicker }).showSaveFilePicker;
  try {
    if (picker) {
      const handle = await picker({
        suggestedName: filename,
        types: [{ description: 'PNG image', accept: { 'image/png': ['.png'] } }]
      });
      const writable = await handle.createWritable();
      await writable.write(await dataUrlBlob(await png));
      await writable.close();
      exportStatus(root, `Saved ${filename}.`);
      return;
    }
    const blob = png.then(dataUrlBlob);
    const Clipboard = (window as unknown as { ClipboardItem?: typeof ClipboardItem }).ClipboardItem;
    if (navigator.clipboard?.write && Clipboard) {
      await navigator.clipboard.write([new Clipboard({ 'image/png': blob })]);
      exportStatus(root, 'Copied PNG to the clipboard.');
      return;
    }
    downloadBlob(await blob, filename);
    exportStatus(root, `Downloaded ${filename}.`);
  } catch (error) {
    if ((error as DOMException).name === 'AbortError') {
      exportStatus(root, 'PNG export canceled.');
      return;
    }
    try {
      downloadBlob(await dataUrlBlob(await png), filename);
      exportStatus(root, `Downloaded ${filename}.`);
    } catch {
      exportStatus(root, 'PNG export failed.', true);
    }
  }
}

function installExportHandler(): void {
  document.addEventListener('click', event => {
    const target = event.target instanceof Element ? event.target : null;
    const button = target?.closest('.snk-export-button');
    const root = button?.closest('.snk-viz-workspace');
    if (!button || !root) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    void exportPlot(root);
  }, true);
}

class SQLExecutionErrorRenderer extends Widget implements IRenderMime.IRenderer {
  private readonly fallback: RenderedError;

  constructor(options: IRenderMime.IRendererOptions) {
    super();
    this.fallback = new RenderedError(options);
  }

  async renderModel(model: IRenderMime.IMimeModel): Promise<void> {
    const payload = model.data['application/vnd.jupyter.error'] as any;
    const traceback = Array.isArray(payload?.traceback) ? payload.traceback.join('\n') : '';
    this.node.replaceChildren();
    if (payload?.ename === 'SQLExecutionError') {
      this.addClass('snk-sql-error');
      const summary = document.createElement('div');
      summary.className = 'snk-sql-error-summary';
      summary.setAttribute('role', 'alert');
      summary.textContent = payload.evalue || 'The SQL statement could not be executed.';
      const details = document.createElement('details');
      const label = document.createElement('summary');
      label.textContent = 'Technical details';
      const pre = document.createElement('pre');
      pre.textContent = traceback || `${payload.ename}: ${payload.evalue}`;
      details.append(label, pre);
      this.node.append(summary, details);
      return;
    }
    await this.fallback.renderModel(model);
    this.node.appendChild(this.fallback.node);
  }

  dispose(): void {
    this.fallback.dispose();
    super.dispose();
  }
}

function themePayload() {
  return resolveJupyterTheme(currentTheme);
}

function sendTheme(comm: any, cellId: string, sessionId: string): void {
  comm.send({
    protocol_version: PROTOCOL_VERSION,
    request_id: crypto.randomUUID(),
    session_id: sessionId,
    cell_id: cellId,
    operation: 'theme_changed',
    payload: themePayload()
  });
}

function broadcastTheme(): void {
  window.clearTimeout(themeTimer);
  themeTimer = window.setTimeout(() => {
    activeComms.forEach(({ cellId, sessionId }, comm) => sendTheme(comm, cellId, sessionId));
  }, 100);
}

function findCell(panel: NotebookPanel, cellId: string) {
  return panel.content.widgets.find(cell => cell.model.id === cellId);
}

function reply(comm: any, request: BridgeMessage, operation: BridgeMessage['operation'], payload: Record<string, unknown>) {
  comm.send({
    protocol_version: PROTOCOL_VERSION,
    request_id: request.request_id,
    cell_id: request.cell_id,
    operation,
    payload
  });
}

function handle(panel: NotebookPanel, comm: any, value: unknown): void {
  if (!isBridgeMessage(value)) return;
  const request = value;
  const cell = findCell(panel, request.cell_id);
  if (!cell) {
    reply(comm, request, 'error', { message: 'The originating notebook cell was not found.' });
    return;
  }
  if (request.operation === 'capabilities') {
    activeComms.set(comm, { cellId: request.cell_id, sessionId: request.session_id });
    reply(comm, request, 'capabilities_result', {
      persistence: !panel.context.model.readOnly,
      png_export: true
    });
    sendTheme(comm, request.cell_id, request.session_id);
    return;
  }
  const metadata = cell.model.sharedModel.getMetadata() as Record<string, unknown>;
  if (request.operation === 'load') {
    try {
      reply(comm, request, 'load_result', { collection: collectionFromMetadata(metadata) });
    } catch (error) {
      reply(comm, request, 'error', { message: (error as Error).message });
    }
    return;
  }
  if (request.operation === 'save') {
    if (panel.context.model.readOnly) {
      reply(comm, request, 'error', { message: 'The notebook is read-only.' });
      return;
    }
    let current: Collection;
    try {
      current = collectionFromMetadata(metadata);
    } catch (error) {
      reply(comm, request, 'error', { message: (error as Error).message });
      return;
    }
    const expected = request.payload.expected_revision;
    if (expected !== current.revision) {
      reply(comm, request, 'save_result', { conflict: true, collection: current });
      return;
    }
    const next = request.payload.collection as Collection;
    if (!isCollection(next) || next.revision !== current.revision + 1) {
      reply(comm, request, 'error', { message: 'The visualization collection is invalid.' });
      return;
    }
    cell.model.sharedModel.setMetadata(metadataWithCollection(metadata, next) as any);
    panel.context.model.dirty = true;
    reply(comm, request, 'save_result', { revision: next.revision });
  }
}

function attach(panel: NotebookPanel): void {
  const register = () => {
    const kernel = panel.sessionContext.session?.kernel;
    if (!kernel) return;
    kernel.registerCommTarget(COMM_TARGET, (comm: any, message: KernelMessage.ICommOpenMsg) => {
      comm.onMsg = (message: KernelMessage.ICommMsgMsg) =>
        handle(panel, comm, message.content.data);
      handle(panel, comm, message.content.data);
    });
  };
  register();
  panel.sessionContext.kernelChanged.connect(register);
  attachSqlHighlighting(panel);
}

const plugin: JupyterFrontEndPlugin<void> = {
  id: '@sql-notebook-kit/jupyterlab:plugin',
  autoStart: true,
  requires: [INotebookTracker, IThemeManager, IEditorLanguageRegistry, IRenderMimeRegistry],
  activate: (
    _app: JupyterFrontEnd,
    tracker: INotebookTracker,
    themes: IThemeManager,
    languages: IEditorLanguageRegistry,
    rendermime: IRenderMimeRegistry
  ) => {
    const language: IEditorLanguage = {
      name: 'SQL Notebook Kit',
      alias: ['sql-notebook-kit', 'notebook-sql'],
      mime: SQL_MIME,
      extensions: ['sql'],
      support: sql({ dialect: StandardSQL }) as unknown as IEditorLanguage['support']
    };
    languages.addLanguage(language);
    rendermime.addFactory({
      safe: true,
      mimeTypes: ['application/vnd.jupyter.error'],
      defaultRank: 105,
      createRenderer: options => new SQLExecutionErrorRenderer(options)
    }, 105);
    installExportHandler();
    installTableCopy({ writeText: writeClipboardText });
    const forcedColors = window.matchMedia('(forced-colors: active)');
    const updateTheme = () => {
      currentTheme = forcedColors.matches
        ? 'high_contrast'
        : themes.theme?.toLowerCase().includes('dark')
          ? 'dark'
          : 'light';
      const theme = themePayload();
      document.querySelectorAll<HTMLElement>('.snk-viz-workspace')
        .forEach(root => applyJupyterTheme(root, theme));
      broadcastTheme();
    };
    updateTheme();
    tracker.forEach(attach);
    tracker.widgetAdded.connect((_sender, panel) => attach(panel));
    themes.themeChanged.connect(updateTheme);
    forcedColors.addEventListener('change', updateTheme);
    const workspaceObserver = new MutationObserver(records => {
      const theme = themePayload();
      for (const record of records) {
        for (const node of record.addedNodes) {
          if (!(node instanceof HTMLElement)) continue;
          if (node.matches('.snk-viz-workspace')) applyJupyterTheme(node, theme);
          node.querySelectorAll<HTMLElement>('.snk-viz-workspace')
            .forEach(root => applyJupyterTheme(root, theme));
        }
      }
    });
    workspaceObserver.observe(document.body, { childList: true, subtree: true });
  }
};

export default plugin;
