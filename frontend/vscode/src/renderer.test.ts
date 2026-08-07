// @vitest-environment jsdom

import { readFile } from 'node:fs/promises';
import { Buffer } from 'node:buffer';
import { resolve } from 'node:path';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { BridgeMessage } from '@sql-notebook-kit/protocol';
import { activate } from './renderer.js';

class MediaQuery {
  matches: boolean;
  readonly listeners = new Set<EventListenerOrEventListenerObject>();

  constructor(matches = false) {
    this.matches = matches;
  }

  addEventListener(_type: string, listener: EventListenerOrEventListenerObject): void {
    this.listeners.add(listener);
  }

  removeEventListener(_type: string, listener: EventListenerOrEventListenerObject): void {
    this.listeners.delete(listener);
  }

  change(matches: boolean): void {
    this.matches = matches;
    const event = new Event('change');
    for (const listener of this.listeners) {
      if (typeof listener === 'function') listener(event);
      else listener.handleEvent(event);
    }
  }
}

const request: BridgeMessage = {
  protocol_version: 1,
  request_id: 'request',
  session_id: 'session',
  cell_id: 'vscode-notebook-cell:/example#1',
  operation: 'capabilities',
  payload: {}
};

function output(id = 'output', live = true) {
  return {
    id,
    mime: 'application/vnd.sql-notebook-kit.bridge+json',
    json: () => request,
    metadata: live ? { transient: { display_id: 'bridge' } } : {}
  } as never;
}

function errorOutput(value: Record<string, unknown>) {
  return {
    id: 'error',
    mime: 'application/vnd.code.notebook.error',
    json: () => value
  } as never;
}

async function flushTheme(): Promise<void> {
  await Promise.resolve();
  await vi.advanceTimersByTimeAsync(50);
}

describe('VS Code bridge renderer', () => {
  let media: MediaQuery;

  beforeEach(() => {
    vi.useFakeTimers();
    document.body.className = '';
    document.body.removeAttribute('style');
    media = new MediaQuery();
    vi.stubGlobal('matchMedia', () => media);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  it('keeps activate exported from the built renderer module', async () => {
    const source = await readFile(resolve('dist/renderer.js'), 'utf8');
    const moduleUrl = `data:text/javascript;base64,${Buffer.from(source).toString('base64')}`;
    const built = await import(moduleUrl);
    expect(built.activate).toBeTypeOf('function');
  });

  it('posts capabilities immediately and uses dark fallbacks from the VS Code body class', async () => {
    document.body.className = 'vscode-dark';
    const messages: BridgeMessage[] = [];
    const renderer = activate({
      postMessage: (message: unknown) => messages.push(message as BridgeMessage)
    } as never);

    renderer.renderOutputItem(output(), document.createElement('div'), new AbortController().signal);
    expect(messages).toEqual([request]);
    await flushTheme();

    expect(messages[1].operation).toBe('theme_changed');
    expect(messages[1].payload).toMatchObject({
      kind: 'dark',
      tokens: { background: '#1e1e1e', text: '#f0f0f0', input_bg: '#313131' }
    });
    renderer.disposeOutputItem?.();
  });

  it('ignores a bridge output restored from notebook storage', async () => {
    const messages: BridgeMessage[] = [];
    const renderer = activate({
      postMessage: (message: unknown) => messages.push(message as BridgeMessage)
    } as never);
    const element = document.createElement('div');
    renderer.renderOutputItem(output('saved', false), element, new AbortController().signal);
    await flushTheme();
    expect(messages).toEqual([]);
    expect(element.hidden).toBe(true);
    renderer.disposeOutputItem?.();
  });

  it('prefers resolved VS Code tokens and reports high contrast from either host signal', async () => {
    document.body.className = 'vscode-light';
    document.body.style.setProperty('--vscode-editor-background', '#123456');
    document.body.style.setProperty('--vscode-editor-foreground', '#abcdef');
    media.matches = true;
    const messages: BridgeMessage[] = [];
    const renderer = activate({
      postMessage: (message: unknown) => messages.push(message as BridgeMessage)
    } as never);

    renderer.renderOutputItem(output(), document.createElement('div'), new AbortController().signal);
    await flushTheme();

    expect(messages[1].payload).toMatchObject({
      kind: 'high_contrast',
      tokens: { background: '#123456', text: '#abcdef' }
    });
    renderer.disposeOutputItem?.();
  });

  it('sends live theme changes and removes all listeners when every output is disposed', async () => {
    document.body.className = 'vscode-light';
    const messages: BridgeMessage[] = [];
    const renderer = activate({
      postMessage: (message: unknown) => messages.push(message as BridgeMessage)
    } as never);

    renderer.renderOutputItem(output(), document.createElement('div'), new AbortController().signal);
    await flushTheme();
    document.body.className = 'vscode-dark';
    await flushTheme();
    expect(messages.at(-1)?.payload.kind).toBe('dark');

    renderer.disposeOutputItem?.();
    const count = messages.length;
    document.body.className = 'vscode-light';
    media.change(true);
    await flushTheme();
    expect(messages).toHaveLength(count);
    expect(media.listeners).toHaveLength(0);
  });

  it('disposes only the requested output listener', async () => {
    const renderer = activate({ postMessage: vi.fn() } as never);
    renderer.renderOutputItem(output('one'), document.createElement('div'), new AbortController().signal);
    renderer.renderOutputItem(output('two'), document.createElement('div'), new AbortController().signal);
    expect(media.listeners).toHaveLength(2);

    renderer.disposeOutputItem?.('one');
    expect(media.listeners).toHaveLength(1);
    renderer.disposeOutputItem?.('two');
    expect(media.listeners).toHaveLength(0);
    renderer.disposeOutputItem?.();
  });

  it('renders managed SQL errors with collapsed technical details', () => {
    const renderer = activate({ postMessage: vi.fn() } as never);
    const element = document.createElement('div');
    renderer.renderOutputItem(errorOutput({
      name: 'SQLExecutionError',
      message: 'column missing (SQLSTATE 42703)',
      stack: 'sanitized traceback'
    }), element, new AbortController().signal);

    expect(element.querySelector('.snk-sql-error-summary')?.textContent)
      .toBe('column missing (SQLSTATE 42703)');
    expect(element.querySelector('details')?.hasAttribute('open')).toBe(false);
    expect(element.querySelector('pre')?.textContent).toBe('sanitized traceback');
    renderer.disposeOutputItem?.();
  });

  it('exports the visible Plotly chart at 2x through renderer messaging', async () => {
    vi.useRealTimers();
    const messages: unknown[] = [];
    const toImage = vi.fn().mockResolvedValue('data:image/png;base64,iVBORw0KGgo=');
    vi.stubGlobal('Plotly', { toImage });
    const renderer = activate({ postMessage: (message: unknown) => messages.push(message) } as never);
    renderer.renderOutputItem(output(), document.createElement('div'), new AbortController().signal);

    const root = document.createElement('div');
    root.className = 'snk-viz-workspace';
    root.innerHTML = `
      <button class="snk-export-button">Export PNG</button>
      <div class="snk-tabs"><button aria-pressed="true">Revenue / region</button></div>
      <div class="js-plotly-plot"></div>
      <div class="snk-export-status"></div>`;
    document.body.appendChild(root);
    (root.querySelector('.snk-export-button') as HTMLButtonElement).click();
    await new Promise(resolve => setTimeout(resolve, 0));

    expect(toImage).toHaveBeenCalledWith(expect.anything(), expect.objectContaining({ scale: 2 }));
    expect(messages.find(item => (item as { kind?: string }).kind === 'export_png'),
      root.querySelector('.snk-export-status')?.textContent ?? '').toMatchObject({
      kind: 'export_png', filename: 'Revenue - region.png', base64: 'iVBORw0KGgo='
    });
    renderer.disposeOutputItem?.();
  });

  it('routes prepared TSV through the VS Code host clipboard', async () => {
    vi.useRealTimers();
    const messages: unknown[] = [];
    let receive: ((message: unknown) => void) | undefined;
    const renderer = activate({
      postMessage: (message: unknown) => messages.push(message),
      onDidReceiveMessage: (listener: (message: unknown) => void) => {
        receive = listener;
        return { dispose: vi.fn() };
      }
    } as never);
    const root = document.createElement('div');
    root.className = 'snk-viz-workspace';
    root.innerHTML = `
      <button class="snk-copy-button">Copy data</button>
      <div class="snk-copy-status"></div>
      <textarea class="snk-copy-payload">Period\tRevenue\n2026-01\t3</textarea>`;
    document.body.appendChild(root);

    (root.querySelector('.snk-copy-button') as HTMLButtonElement).click();
    await Promise.resolve();
    const request = messages.find(item => (item as { kind?: string }).kind === 'copy_text') as {
      requestId: string; text: string;
    };
    expect(request.text).toBe('Period\tRevenue\n2026-01\t3');

    receive?.({ kind: 'copy_text_result', requestId: request.requestId, status: 'copied' });
    await Promise.resolve();
    expect(root.querySelector('.snk-copy-status')?.textContent).toBe('Copied visualization data.');
    renderer.disposeOutputItem?.();
  });
});
