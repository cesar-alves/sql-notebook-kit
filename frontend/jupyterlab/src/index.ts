import type { JupyterFrontEnd, JupyterFrontEndPlugin } from '@jupyterlab/application';
import { IThemeManager } from '@jupyterlab/apputils';
import { INotebookTracker, type NotebookPanel } from '@jupyterlab/notebook';
import type { KernelMessage } from '@jupyterlab/services';
import {
  COMM_TARGET,
  PROTOCOL_VERSION,
  collectionFromMetadata,
  emptyCollection,
  isBridgeMessage,
  metadataWithCollection,
  type BridgeMessage,
  type Collection
} from '@redshift-notebooks/protocol';
import '../style/index.css';

const activeComms = new Map<any, string>();
let currentTheme: 'light' | 'dark' | 'high_contrast' = 'light';
let themeTimer: number | undefined;

function opaqueColor(value: string, fallback: string): string {
  const probe = document.createElement('span');
  probe.style.color = value || fallback;
  probe.style.display = 'none';
  document.body.appendChild(probe);
  const resolved = getComputedStyle(probe).color;
  probe.remove();
  const match = resolved.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)/);
  if (!match) return fallback;
  return `#${match.slice(1, 4).map(part => Number(part).toString(16).padStart(2, '0')).join('')}`;
}

function themePayload() {
  const style = getComputedStyle(document.body);
  const token = (name: string, fallback: string) =>
    opaqueColor(style.getPropertyValue(name).trim(), fallback);
  const dark = currentTheme !== 'light';
  return {
    kind: currentTheme,
    tokens: {
      background: token('--jp-layout-color0', dark ? '#1e1e1e' : '#ffffff'),
      surface: token('--jp-layout-color1', dark ? '#252526' : '#ffffff'),
      surface_muted: token('--jp-layout-color2', dark ? '#313131' : '#f6f8fa'),
      surface_raised: token('--jp-layout-color1', dark ? '#2d2d30' : '#ffffff'),
      text: token('--jp-ui-font-color1', dark ? '#f0f0f0' : '#1f2328'),
      text_muted: token('--jp-ui-font-color2', dark ? '#c4c4c4' : '#57606a'),
      border: token('--jp-border-color1', dark ? '#5a5a5a' : '#d0d7de'),
      accent: token('--jp-brand-color1', dark ? '#4daafc' : '#0969da'),
      accent_hover: token('--jp-brand-color2', dark ? '#75beff' : '#0550ae'),
      focus: token('--jp-brand-color1', dark ? '#75beff' : '#0550ae'),
      danger: token('--jp-error-color1', dark ? '#f48771' : '#cf222e'),
      warning_bg: token('--jp-warn-color3', dark ? '#3b2e00' : '#fff8c5'),
      warning_text: dark ? '#ffd866' : '#4d2d00',
      selection_bg: token('--jp-layout-color2', dark ? '#063b49' : '#ddf4ff'),
      input_bg: token('--jp-layout-color2', dark ? '#313131' : '#f6f8fa')
    }
  };
}

function sendTheme(comm: any, cellId: string): void {
  comm.send({
    protocol_version: PROTOCOL_VERSION,
    request_id: crypto.randomUUID(),
    cell_id: cellId,
    operation: 'theme_changed',
    payload: themePayload()
  });
}

function broadcastTheme(): void {
  window.clearTimeout(themeTimer);
  themeTimer = window.setTimeout(() => {
    activeComms.forEach((cellId, comm) => sendTheme(comm, cellId));
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
    activeComms.set(comm, request.cell_id);
    reply(comm, request, 'capabilities_result', { persistence: !panel.context.model.readOnly });
    sendTheme(comm, request.cell_id);
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
    const current = collectionFromMetadata(metadata);
    const expected = request.payload.expected_revision;
    if (expected !== current.revision) {
      reply(comm, request, 'save_result', { conflict: true, collection: current });
      return;
    }
    const next = request.payload.collection as Collection;
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
}

const plugin: JupyterFrontEndPlugin<void> = {
  id: '@redshift-notebooks/jupyterlab:plugin',
  autoStart: true,
  requires: [INotebookTracker, IThemeManager],
  activate: (_app: JupyterFrontEnd, tracker: INotebookTracker, themes: IThemeManager) => {
    const forcedColors = window.matchMedia('(forced-colors: active)');
    const updateTheme = () => {
      currentTheme = forcedColors.matches
        ? 'high_contrast'
        : themes.theme?.toLowerCase().includes('dark')
          ? 'dark'
          : 'light';
      document.querySelectorAll('.rn-viz-workspace').forEach(root => {
        root.classList.toggle('rn-theme-dark', currentTheme === 'dark');
        root.classList.toggle('rn-theme-light', currentTheme === 'light');
        root.classList.toggle('rn-theme-high-contrast', currentTheme === 'high_contrast');
      });
      broadcastTheme();
    };
    updateTheme();
    tracker.forEach(attach);
    tracker.widgetAdded.connect((_sender, panel) => attach(panel));
    themes.themeChanged.connect(updateTheme);
    forcedColors.addEventListener('change', updateTheme);
  }
};

export default plugin;
