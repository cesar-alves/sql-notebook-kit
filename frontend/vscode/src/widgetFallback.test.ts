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

class MediaQuery {
  matches = false;
  readonly listeners = new Set<EventListenerOrEventListenerObject>();

  addEventListener(_type: string, listener: EventListenerOrEventListenerObject): void {
    this.listeners.add(listener);
  }

  removeEventListener(_type: string, listener: EventListenerOrEventListenerObject): void {
    this.listeners.delete(listener);
  }
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
  document.body.className = '';
  document.body.removeAttribute('style');
});

function stubMedia(): MediaQuery {
  const media = new MediaQuery();
  vi.stubGlobal('matchMedia', () => media);
  return media;
}

describe('saved visualization widget fallback', () => {
  it('shows a rerun placeholder for a managed stale widget', async () => {
    stubMedia();
    const original = vi.fn();
    const base: RendererApi = { renderOutputItem: original };
    await activate(context(base, { managed: true, live: false }));
    const element = document.createElement('div');
    await base.renderOutputItem(output(), element, new AbortController().signal);

    expect(original).not.toHaveBeenCalled();
    expect(element.querySelector('.snk-widget-placeholder')?.textContent)
      .toContain('Run this SQL cell');
    expect(element.classList.contains('snk-managed-widget-output')).toBe(true);
    base.disposeOutputItem?.();
  });

  it.each([
    { managed: true, live: true },
    { managed: false, live: false }
  ])('delegates live and unrelated widgets to Jupyter (%o)', async reply => {
    stubMedia();
    const original = vi.fn();
    const base: RendererApi = { renderOutputItem: original };
    await activate(context(base, reply));
    const item = output();
    const element = document.createElement('div');
    const signal = new AbortController().signal;
    await base.renderOutputItem(item, element, signal);
    expect(original).toHaveBeenCalledWith(item, element, signal);
    expect(element.classList.contains('snk-managed-widget-output')).toBe(reply.managed);
    base.disposeOutputItem?.();
  });

  it('fails open to Jupyter when host classification times out', async () => {
    stubMedia();
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
    base.disposeOutputItem?.();
  });

  it('themes only managed output padding and workspace roots, then cleans up', async () => {
    const media = stubMedia();
    document.body.className = 'vscode-dark';
    document.body.style.setProperty('--vscode-editor-background', '#101112');
    document.body.style.setProperty('--vscode-editor-foreground', '#f1f2f3');
    document.body.style.setProperty('--vscode-panel-border', '#343536');
    const original = vi.fn(async (_output, element: HTMLElement) => {
      const root = document.createElement('div');
      root.className = 'snk-viz-workspace snk-theme-light';
      element.append(root);
    });
    const dispose = vi.fn();
    const base: RendererApi = { renderOutputItem: original, disposeOutputItem: dispose };
    await activate(context(base, { managed: true, live: true }));
    const element = document.createElement('div');

    await base.renderOutputItem(output(), element, new AbortController().signal);

    const root = element.querySelector<HTMLElement>('.snk-viz-workspace')!;
    expect(element.style.backgroundColor).toBe('transparent');
    expect(element.style.getPropertyPriority('background-color')).toBe('important');
    expect(element.style.border).toBe('0px');
    expect(element.style.outline).toBe('0');
    expect(element.style.boxShadow).toBe('none');
    expect(root.classList.contains('snk-theme-dark')).toBe(true);
    expect(root.style.getPropertyValue('--snk-border')).toBe('#343536');
    base.disposeOutputItem?.('output');
    expect(element.classList.contains('snk-managed-widget-output')).toBe(false);
    expect(element.style.backgroundColor).toBe('');
    expect(dispose).toHaveBeenCalledWith('output');
    base.disposeOutputItem?.();
    expect(media.listeners).toHaveLength(0);
  });

  it('recognizes a rendered workspace even when the output has no persistence bridge', async () => {
    stubMedia();
    document.body.className = 'vscode-dark';
    const original = vi.fn(async (_output, element: HTMLElement) => {
      const root = document.createElement('div');
      root.className = 'snk-viz-workspace snk-theme-light';
      element.append(root);
    });
    const base: RendererApi = { renderOutputItem: original };
    await activate(context(base, { managed: false, live: false }));
    const element = document.createElement('div');

    await base.renderOutputItem(output(), element, new AbortController().signal);

    expect(element.classList.contains('snk-managed-widget-output')).toBe(true);
    expect(element.style.backgroundColor).toBe('transparent');
    expect(element.querySelector('.snk-viz-workspace')?.classList.contains('snk-theme-dark'))
      .toBe(true);
    base.disposeOutputItem?.();
  });

  it('overrides the built-in white widget wrapper around managed workspaces', async () => {
    stubMedia();
    const original = vi.fn(async (_output, element: HTMLElement) => {
      const root = document.createElement('div');
      root.className = 'snk-viz-workspace';
      element.append(root);
    });
    const base: RendererApi = { renderOutputItem: original };
    await activate(context(base, { managed: true, live: true }));
    const wrapper = document.createElement('div');
    wrapper.className = 'cell-output-ipywidget-background';
    wrapper.style.setProperty('background', '#fff', 'important');
    const element = document.createElement('div');
    wrapper.append(element);
    document.body.append(wrapper);

    await base.renderOutputItem(output(), element, new AbortController().signal);

    const scopedRule = [...document.styleSheets]
      .flatMap(sheet => [...sheet.cssRules])
      .find(rule => rule.cssText.includes(':has(.snk-viz-workspace)'));
    expect(scopedRule?.cssText).toContain('background: transparent !important');
    expect(scopedRule?.cssText).toContain('border: 0 !important');
    expect(scopedRule?.cssText).toContain('box-shadow: none !important');
    base.disposeOutputItem?.();
    wrapper.remove();
  });

  it('composites translucent host colors instead of making them opaque white', async () => {
    stubMedia();
    document.body.className = 'vscode-dark';
    document.body.style.setProperty('--vscode-editor-background', '#202020');
    document.body.style.setProperty(
      '--vscode-list-activeSelectionBackground', 'rgba(255, 255, 255, 0.1)'
    );
    document.body.style.setProperty('--vscode-notebook-outputContainerBorderColor', '#ffffff');
    const original = vi.fn(async (_output, element: HTMLElement) => {
      const root = document.createElement('div');
      root.className = 'snk-viz-workspace';
      element.append(root);
    });
    const base: RendererApi = { renderOutputItem: original };
    await activate(context(base, { managed: true, live: true }));
    const element = document.createElement('div');

    await base.renderOutputItem(output(), element, new AbortController().signal);

    const root = element.querySelector<HTMLElement>('.snk-viz-workspace')!;
    expect(root.style.getPropertyValue('--snk-selection-bg')).toBe('#363636');
    expect(root.style.getPropertyValue('--snk-border')).toBe('#5a5a5a');
    base.disposeOutputItem?.();
  });
});
