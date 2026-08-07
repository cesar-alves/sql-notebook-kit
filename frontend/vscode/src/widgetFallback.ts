import type {
  ActivationFunction, OutputItem, RendererApi, RendererContext
} from 'vscode-notebook-renderer';

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
  const render = base.renderOutputItem.bind(base);
  base[INSTALLED] = true;
  base.renderOutputItem = async (
    output: OutputItem, element: HTMLElement, signal: AbortSignal
  ) => {
    const state = await classify(context, output, signal);
    if (signal.aborted) return;
    if (state?.managed && !state.live) {
      renderPlaceholder(element);
      return;
    }
    await render(output, element, signal);
  };
  return undefined;
}) satisfies ActivationFunction;

export type { RendererApi };
