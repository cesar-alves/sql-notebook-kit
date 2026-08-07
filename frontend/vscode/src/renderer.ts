import { installTableCopy, type BridgeMessage } from '@redshift-notebooks/protocol';
import type {
  ActivationFunction, OutputItem, RendererApi, RendererContext
} from 'vscode-notebook-renderer';

type ThemeKind = 'light' | 'dark' | 'high_contrast';
const BRIDGE_MIME = 'application/vnd.redshift-notebooks.bridge+json';
const ERROR_MIME = 'application/vnd.code.notebook.error';

function isRecord(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === 'object' && !Array.isArray(value);
}

function isLiveDisplay(output: OutputItem): boolean {
  if (!isRecord(output.metadata)) return false;
  const transient = output.metadata.transient;
  return isRecord(transient) && typeof transient.display_id === 'string';
}

interface PlotlyElement extends HTMLElement {
  _fullLayout?: { width?: number; height?: number };
}

interface PlotlyApi {
  toImage(element: PlotlyElement, options: Record<string, unknown>): Promise<string>;
}

interface ExportRequest {
  kind: 'export_png';
  requestId: string;
  filename: string;
  base64: string;
}

interface ExportResult {
  kind: 'export_png_result';
  requestId: string;
  status: 'saved' | 'canceled' | 'failed';
  filename: string;
}

interface CopyTextRequest {
  kind: 'copy_text';
  requestId: string;
  text: string;
}

interface CopyTextResult {
  kind: 'copy_text_result';
  requestId: string;
  status: 'copied' | 'failed';
}

const LIGHT = {
  background: '#ffffff', surface: '#ffffff', surface_muted: '#f6f8fa',
  surface_raised: '#ffffff', text: '#1f2328', text_muted: '#57606a',
  border: '#d0d7de', accent: '#0969da', accent_hover: '#0550ae',
  focus: '#0550ae', danger: '#cf222e', warning_bg: '#fff8c5',
  warning_text: '#4d2d00', selection_bg: '#ddf4ff', input_bg: '#f6f8fa'
};
const DARK = {
  background: '#1e1e1e', surface: '#252526', surface_muted: '#313131',
  surface_raised: '#2d2d30', text: '#f0f0f0', text_muted: '#c4c4c4',
  border: '#5a5a5a', accent: '#4daafc', accent_hover: '#75beff',
  focus: '#75beff', danger: '#f48771', warning_bg: '#3b2e00',
  warning_text: '#ffd866', selection_bg: '#063b49', input_bg: '#313131'
};

function token(style: CSSStyleDeclaration, name: string, fallback: string): string {
  const probe = document.createElement('span');
  probe.style.color = style.getPropertyValue(name).trim() || fallback;
  probe.style.display = 'none';
  document.body.appendChild(probe);
  const resolved = getComputedStyle(probe).color;
  probe.remove();
  const match = resolved.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)/);
  return match
    ? `#${match.slice(1, 4).map(value => Number(value).toString(16).padStart(2, '0')).join('')}`
    : fallback;
}

function isDark(color: string): boolean {
  const channels = color.slice(1).match(/.{2}/g)?.map(value => parseInt(value, 16));
  return !!channels && channels[0] * 299 + channels[1] * 587 + channels[2] * 114 < 128_000;
}

function bodyTheme(forcedColors: boolean): ThemeKind | undefined {
  if (forcedColors || document.body.classList.contains('vscode-high-contrast')) {
    return 'high_contrast';
  }
  if (document.body.classList.contains('vscode-dark')) return 'dark';
  if (document.body.classList.contains('vscode-light')) return 'light';
  return undefined;
}

function themeMessage(request: BridgeMessage, forcedColors: boolean): BridgeMessage {
  const style = getComputedStyle(document.body);
  let kind = bodyTheme(forcedColors);
  let fallback = kind === 'dark' || kind === 'high_contrast' ? DARK : LIGHT;
  const background = token(style, '--vscode-editor-background', fallback.background);
  if (!kind) {
    kind = isDark(background) ? 'dark' : 'light';
    fallback = kind === 'dark' ? DARK : LIGHT;
  }
  return {
    ...request,
    request_id: crypto.randomUUID(),
    operation: 'theme_changed',
    payload: {
      kind,
      tokens: {
        background,
        surface: token(style, '--vscode-sideBar-background', fallback.surface),
        surface_muted: token(style, '--vscode-input-background', fallback.surface_muted),
        surface_raised: token(style, '--vscode-editorWidget-background', fallback.surface_raised),
        text: token(style, '--vscode-editor-foreground', fallback.text),
        text_muted: token(style, '--vscode-descriptionForeground', fallback.text_muted),
        border: token(style, '--vscode-widget-border', fallback.border),
        accent: token(style, '--vscode-focusBorder', fallback.accent),
        accent_hover: token(style, '--vscode-button-hoverBackground', fallback.accent_hover),
        focus: token(style, '--vscode-focusBorder', fallback.focus),
        danger: token(style, '--vscode-errorForeground', fallback.danger),
        warning_bg: token(style, '--vscode-inputValidation-warningBackground', fallback.warning_bg),
        warning_text: token(style, '--vscode-editorWarning-foreground', fallback.warning_text),
        selection_bg: token(style, '--vscode-editor-selectionBackground', fallback.selection_bg),
        input_bg: token(style, '--vscode-input-background', fallback.input_bg)
      }
    }
  };
}

function sqlErrorPayload(output: OutputItem): {
  name: string; message: string; traceback: string;
} | null {
  const payload = output.json() as {
    name?: string; ename?: string; message?: string; evalue?: string; stack?: string; traceback?: string[];
  };
  const name = payload.name ?? payload.ename ?? 'Error';
  const message = payload.message ?? payload.evalue ?? '';
  const traceback = Array.isArray(payload.traceback) ? payload.traceback.join('\n') : payload.stack;
  return name === 'SQLExecutionError' ? { name, message, traceback: traceback ?? '' } : null;
}

function renderError(
  payload: { name: string; message: string; traceback: string }, element: HTMLElement
): void {
  const { name, message, traceback } = payload;
  element.replaceChildren();
  element.className = 'rn-sql-error';
  const summary = document.createElement('div');
  summary.className = 'rn-sql-error-summary';
  summary.setAttribute('role', 'alert');
  summary.textContent = message || 'The SQL statement could not be executed.';
  const details = document.createElement('details');
  const label = document.createElement('summary');
  label.textContent = 'Technical details';
  const pre = document.createElement('pre');
  pre.textContent = traceback || `${name}: ${message}`;
  details.append(label, pre);
  element.append(summary, details);
}

function safeFilename(value: string): string {
  const stem = value.trim().replace(/[\\/:*?"<>|\u0000-\u001f]/g, '-').replace(/\s+/g, ' ');
  return `${(stem || 'visualization').slice(0, 100)}.png`;
}

function status(root: Element, message: string, error = false): void {
  const target = root.querySelector<HTMLElement>('.rn-export-status');
  if (!target) return;
  target.textContent = message;
  target.classList.toggle('rn-error', error);
}

function base64FromDataUrl(value: string): string {
  const marker = ';base64,';
  const index = value.indexOf(marker);
  if (index < 0) throw new Error('Plotly returned an invalid PNG.');
  return value.slice(index + marker.length);
}

export const activate = ((context: RendererContext<unknown>): RendererApi => {
  const stylesheet = document.createElement('style');
  stylesheet.textContent = `
    .rn-sql-error {
      color: var(--vscode-editor-foreground); background: var(--vscode-editor-background);
      border-left: 3px solid var(--vscode-errorForeground); padding: 8px 12px;
    }
    .rn-sql-error-summary { color: var(--vscode-errorForeground); font-weight: 600; }
    .rn-sql-error details { margin-top: 6px; }
    .rn-sql-error summary { cursor: pointer; color: var(--vscode-editor-foreground); }
    .rn-sql-error pre {
      color: var(--vscode-editor-foreground); background: var(--vscode-textCodeBlock-background);
      border: 1px solid var(--vscode-widget-border); margin: 8px 0 0;
      max-height: 24rem; overflow: auto; padding: 8px; white-space: pre-wrap;
    }
  `;
  document.head.appendChild(stylesheet);
  const builtinRenderer = context.getRenderer?.('vscode.builtin-renderer');
  const cleanups = new Map<string, () => void>();
  const exports = new Map<string, { root: Element; filename: string }>();
  const copies = new Map<string, {
    resolve(): void; reject(): void; timer: number;
  }>();
  const disposeTableCopy = installTableCopy({
    writeText(text: string): Promise<void> {
      return new Promise((resolve, reject) => {
        if (!context.postMessage) {
          reject();
          return;
        }
        const requestId = crypto.randomUUID();
        const timer = window.setTimeout(() => {
          copies.delete(requestId);
          reject();
        }, 10_000);
        copies.set(requestId, { resolve, reject, timer });
        const request: CopyTextRequest = { kind: 'copy_text', requestId, text };
        context.postMessage(request);
      });
    }
  });
  const exportListener = async (event: Event) => {
    const target = event.target instanceof Element ? event.target : null;
    const button = target?.closest('.rn-export-button');
    const root = button?.closest('.rn-viz-workspace');
    if (!button || !root) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    const plot = root.querySelector<PlotlyElement>('.js-plotly-plot');
    const plotly = (window as unknown as { Plotly?: PlotlyApi }).Plotly;
    const cached = root.querySelector<HTMLImageElement>('img.plot-img[src^="data:image/png"]')?.src;
    if (!plot && !cached) {
      status(root, 'The rendered visualization is not ready to export.', true);
      return;
    }
    if (plot && !plotly?.toImage && !cached) {
      const modebar = root.querySelector<HTMLElement>(
        '.modebar-btn[data-title*="Download plot"], .modebar-btn[data-title*="png"]'
      );
      if (modebar) {
        modebar.click();
        status(root, 'Downloaded PNG using Plotly.');
      } else {
        status(root, 'This frontend cannot export the rendered visualization.', true);
      }
      return;
    }
    const selected = root.querySelector<HTMLElement>('.rn-tabs button[aria-pressed="true"]');
    const filename = safeFilename(selected?.textContent ?? 'visualization');
    const requestId = crypto.randomUUID();
    try {
      const width = Math.max(1, plot?._fullLayout?.width ?? plot?.clientWidth ?? 1);
      const height = Math.max(1, plot?._fullLayout?.height ?? plot?.clientHeight ?? 1);
      const dataUrl = plot && plotly?.toImage
        ? await plotly.toImage(plot, { format: 'png', width, height, scale: 2 })
        : cached as string;
      const request: ExportRequest = {
        kind: 'export_png', requestId, filename, base64: base64FromDataUrl(dataUrl)
      };
      exports.set(requestId, { root, filename });
      context.postMessage?.(request);
      status(root, 'Choose where to save the PNG…');
    } catch {
      status(root, 'PNG export failed.', true);
    }
  };
  document.addEventListener('click', exportListener, true);
  const messageDisposable = context.onDidReceiveMessage?.((message: unknown) => {
    const copyResult = message as Partial<CopyTextResult>;
    if (copyResult.kind === 'copy_text_result' && typeof copyResult.requestId === 'string') {
      const pending = copies.get(copyResult.requestId);
      if (!pending) return;
      copies.delete(copyResult.requestId);
      window.clearTimeout(pending.timer);
      if (copyResult.status === 'copied') pending.resolve();
      else pending.reject();
      return;
    }
    const result = message as Partial<ExportResult>;
    if (result.kind !== 'export_png_result' || typeof result.requestId !== 'string') return;
    const pending = exports.get(result.requestId);
    if (!pending) return;
    exports.delete(result.requestId);
    if (result.status === 'saved') status(pending.root, `Saved ${pending.filename}.`);
    else if (result.status === 'canceled') status(pending.root, 'PNG export canceled.');
    else status(pending.root, 'PNG export failed.', true);
  });
  return {
    async renderOutputItem(output: OutputItem, element: HTMLElement, signal: AbortSignal) {
      if (output.mime === ERROR_MIME) {
        const payload = sqlErrorPayload(output);
        if (payload) renderError(payload, element);
        else (await builtinRenderer)?.renderOutputItem(output, element, signal);
        return;
      }
      if (output.mime !== BRIDGE_MIME) return;
      element.hidden = true;
      if (!isLiveDisplay(output)) return;
      const request = output.json() as BridgeMessage;
      context.postMessage?.(request);
      if (request.operation !== 'capabilities') return;
      const media = matchMedia('(forced-colors: active)');
      let timer: number | undefined;
      const send = () => {
        window.clearTimeout(timer);
        timer = window.setTimeout(
          () => context.postMessage?.(themeMessage(request, media.matches)), 50
        );
      };
      const observer = new MutationObserver(send);
      observer.observe(document.body, { attributes: true, attributeFilter: ['class', 'style'] });
      media.addEventListener('change', send);
      send();
      cleanups.get(output.id)?.();
      cleanups.set(output.id, () => {
        window.clearTimeout(timer);
        observer.disconnect();
        media.removeEventListener('change', send);
      });
    },
    disposeOutputItem(outputId?: string) {
      if (!outputId) {
        for (const cleanup of cleanups.values()) cleanup();
        cleanups.clear();
        document.removeEventListener('click', exportListener, true);
        messageDisposable?.dispose();
        disposeTableCopy();
        for (const pending of copies.values()) {
          window.clearTimeout(pending.timer);
          pending.reject();
        }
        copies.clear();
        exports.clear();
        stylesheet.remove();
        return;
      }
      cleanups.get(outputId)?.();
      cleanups.delete(outputId);
    }
  };
}) satisfies ActivationFunction;
