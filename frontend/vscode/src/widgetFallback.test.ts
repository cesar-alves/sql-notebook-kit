// @vitest-environment jsdom

import { afterEach, describe, expect, it, vi } from 'vitest';
import type { RendererApi } from 'vscode-notebook-renderer';

import { activate } from './widgetFallback.js';

function output(modelId = 'model') {
  return { id: 'output', mime: 'application/vnd.jupyter.widget-view+json', json: () => ({ model_id: modelId }) } as never;
}

function context(
  base: RendererApi, reply?: { managed: boolean; live: boolean }
) {
  const listeners = new Set<(message: unknown) => void>();
  return {
    getRenderer: vi.fn().mockResolvedValue(base),
    postMessage: vi.fn((message: { requestId: string }) => {
      if (reply) queueMicrotask(() => {
        for (const listener of listeners) listener({
          kind: 'widget_state_result', requestId: message.requestId, ...reply
        });
      });
    }),
    onDidReceiveMessage: (listener: (message: unknown) => void) => {
      listeners.add(listener);
      return { dispose: () => listeners.delete(listener) };
    },
    workspace: { isTrusted: true },
    getState: () => undefined,
    setState: () => {}
  } as never;
}

afterEach(() => vi.useRealTimers());

describe('saved visualization widget fallback', () => {
  it('shows a rerun placeholder for a managed stale widget', async () => {
    const original = vi.fn();
    const base: RendererApi = { renderOutputItem: original };
    await activate(context(base, { managed: true, live: false }));
    const element = document.createElement('div');
    await base.renderOutputItem(output(), element, new AbortController().signal);

    expect(original).not.toHaveBeenCalled();
    expect(element.querySelector('.rn-widget-placeholder')?.textContent)
      .toContain('Run this SQL cell');
  });

  it.each([
    { managed: true, live: true },
    { managed: false, live: false }
  ])('delegates live and unrelated widgets to Jupyter (%o)', async reply => {
    const original = vi.fn();
    const base: RendererApi = { renderOutputItem: original };
    await activate(context(base, reply));
    const item = output();
    const element = document.createElement('div');
    const signal = new AbortController().signal;
    await base.renderOutputItem(item, element, signal);
    expect(original).toHaveBeenCalledWith(item, element, signal);
  });

  it('fails open to Jupyter when host classification times out', async () => {
    vi.useFakeTimers();
    const original = vi.fn();
    const base: RendererApi = { renderOutputItem: original };
    await activate(context(base));
    const pending = base.renderOutputItem(
      output(), document.createElement('div'), new AbortController().signal
    );
    await vi.advanceTimersByTimeAsync(500);
    await pending;
    expect(original).toHaveBeenCalledOnce();
  });
});
