import type {
  ActivationFunction, OutputItem, RendererApi, RendererContext
} from 'vscode-notebook-renderer';
import { applyWorkspaceTheme, resolveVsCodeTheme } from './theme.js';

const BASE_RENDERER = 'jupyter-ipywidget-renderer';
const INSTALLED = 'redshiftNotebooksWidgetFallbackInstalled';

interface WidgetStateResult {
  kind: 'widget_state_result';
  requestId: string;
  managed: boolean;
  live: boolean;
}

function isResult(value: unknown): value is WidgetStateResult {
  if (!value || typeof value !== 'object') return false;
  const item = value as Partial<WidgetStateResult>;
  return item.kind === 'widget_state_result' && typeof item.requestId === 'string' &&
    typeof item.managed === 'boolean' && typeof item.live === 'boolean';
}

function modelId(output: OutputItem): string | undefined {
  try {
    const value = output.json() as { model_id?: unknown };
    return typeof value.model_id === 'string' ? value.model_id : undefined;
  } catch {
    return undefined;
  }
}

function renderPlaceholder(element: HTMLElement): void {
  element.replaceChildren();
  const root = document.createElement('div');
  root.className = 'snk-widget-placeholder';
  root.setAttribute('role', 'status');
  root.style.cssText = [
    'border-left: 3px solid var(--vscode-notebookInfoIcon-foreground, #3794ff)',
    'color: var(--vscode-editor-foreground)',
    'padding: 8px 12px'
  ].join(';');
  const title = document.createElement('strong');
  title.textContent = 'Visualization ready to restore';
  const detail = document.createElement('div');
  detail.textContent = 'Run this SQL cell to restore the interactive visualization from its saved settings.';
  detail.style.marginTop = '4px';
  root.append(title, detail);
  element.append(root);
}

async function classify(
  context: RendererContext<unknown>, output: OutputItem, signal: AbortSignal
): Promise<WidgetStateResult | undefined> {
  const id = modelId(output);
  if (!id || !context.postMessage || !context.onDidReceiveMessage || signal.aborted) {
    return undefined;
  }
  const requestId = crypto.randomUUID();
  return new Promise(resolve => {
    let settled = false;
    const finish = (value?: WidgetStateResult) => {
      if (settled) return;
      settled = true;
      window.clearTimeout(timer);
      subscription.dispose();
      signal.removeEventListener('abort', canceled);
      resolve(value);
    };
    const subscription = context.onDidReceiveMessage!((message: unknown) => {
      if (isResult(message) && message.requestId === requestId) finish(message);
    });
    const canceled = () => finish();
    signal.addEventListener('abort', canceled, { once: true });
    const timer = window.setTimeout(() => finish(), 500);
    context.postMessage!({ kind: 'widget_state', requestId, modelId: id });
  });
}

export const activate = (async (context: RendererContext<unknown>) => {
  const base = await context.getRenderer(BASE_RENDERER);
  if (!base || base[INSTALLED]) return undefined;
  const stylesheet = document.createElement('style');
  stylesheet.textContent = `
    .snk-managed-widget-output,
    .cell-output-ipywidget-background:has(.snk-viz-workspace) {
      background: transparent !important;
      border: 0 !important;
      outline: 0 !important;
      box-shadow: none !important;
    }
  `;
  document.head.appendChild(stylesheet);
  const render = base.renderOutputItem.bind(base);
  const dispose = base.disposeOutputItem?.bind(base);
  const forcedColors = matchMedia('(forced-colors: active)');
  const managed = new Map<string, { element: HTMLElement; observer: MutationObserver }>();

  const applyTheme = (element: HTMLElement) => {
    const theme = resolveVsCodeTheme(forcedColors.matches);
    element.classList.add('snk-managed-widget-output');
    // VS Code's built-in ipywidgets renderer forces this element to white with
    // an !important rule, including in dark themes.
    element.style.setProperty('background-color', 'transparent', 'important');
    element.style.setProperty('border', '0', 'important');
    element.style.setProperty('outline', '0', 'important');
    element.style.setProperty('box-shadow', 'none', 'important');
    element.style.color = theme.tokens.text;
    element.style.colorScheme = theme.kind === 'light' ? 'light' : 'dark';
    element.querySelectorAll<HTMLElement>('.snk-viz-workspace')
      .forEach(root => applyWorkspaceTheme(root, theme));
  };
  const refresh = () => managed.forEach(({ element }) => applyTheme(element));
  const themeObserver = new MutationObserver(refresh);
  themeObserver.observe(document.body, { attributes: true, attributeFilter: ['class', 'style'] });
  forcedColors.addEventListener('change', refresh);

  const unregister = (outputId: string) => {
    const entry = managed.get(outputId);
    entry?.observer.disconnect();
    if (entry) {
      entry.element.classList.remove('snk-managed-widget-output');
      entry.element.style.removeProperty('background-color');
      entry.element.style.removeProperty('border');
      entry.element.style.removeProperty('outline');
      entry.element.style.removeProperty('box-shadow');
      entry.element.style.removeProperty('color');
      entry.element.style.removeProperty('color-scheme');
    }
    managed.delete(outputId);
  };
  const register = (outputId: string, element: HTMLElement) => {
    unregister(outputId);
    applyTheme(element);
    const observer = new MutationObserver(() => applyTheme(element));
    observer.observe(element, { childList: true, subtree: true });
    managed.set(outputId, { element, observer });
  };

  base[INSTALLED] = true;
  base.renderOutputItem = async (
    output: OutputItem, element: HTMLElement, signal: AbortSignal
  ) => {
    const state = await classify(context, output, signal);
    if (signal.aborted) return;
    if (state?.managed && !state.live) {
      renderPlaceholder(element);
      register(output.id, element);
      return;
    }
    await render(output, element, signal);
    if (state?.managed || element.querySelector('.snk-viz-workspace')) {
      register(output.id, element);
    }
  };
  base.disposeOutputItem = (outputId?: string) => {
    if (outputId) unregister(outputId);
    else {
      for (const id of [...managed.keys()]) unregister(id);
      themeObserver.disconnect();
      forcedColors.removeEventListener('change', refresh);
      stylesheet.remove();
    }
    dispose?.(outputId);
  };
  return undefined;
}) satisfies ActivationFunction;

export type { RendererApi };
