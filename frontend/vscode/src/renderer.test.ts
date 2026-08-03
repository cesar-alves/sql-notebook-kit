// @vitest-environment jsdom

import { readFile } from 'node:fs/promises';
import { Buffer } from 'node:buffer';
import { resolve } from 'node:path';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { BridgeMessage } from '@redshift-notebooks/protocol';
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

function output(id = 'output') {
  return { id, json: () => request } as never;
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
  });
});
