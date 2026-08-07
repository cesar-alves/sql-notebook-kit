import { afterEach, describe, expect, it, vi } from 'vitest';

import type { BridgeMessage, Operation } from '@sql-notebook-kit/protocol';
import {
  DeliveryCoordinator,
  executeWithTimeout,
  kernelOutputError,
  waitForReadyKernel,
  type DeliveryKernel
} from './delivery.js';

function message(operation: Operation, requestId: string, sessionId = 'session'): BridgeMessage {
  return {
    protocol_version: 1,
    request_id: requestId,
    session_id: sessionId,
    cell_id: 'vscode-notebook-cell:/example#1',
    operation,
    payload: {}
  };
}

function deferred(): { promise: Promise<void>; resolve: () => void } {
  let resolve!: () => void;
  return { promise: new Promise(done => { resolve = done; }), resolve };
}

class Kernel implements DeliveryKernel {
  readonly listeners = new Set<(status: string) => void>();
  readonly executions: string[] = [];
  executeImpl: (code: string, signal: AbortSignal) => Promise<void> = async () => {};

  constructor(public status: string) {}

  onDidChangeStatus(listener: (status: string) => void): { dispose(): void } {
    this.listeners.add(listener);
    return { dispose: () => this.listeners.delete(listener) };
  }

  setStatus(status: string): void {
    this.status = status;
    for (const listener of this.listeners) listener(status);
  }

  async execute(code: string, signal: AbortSignal): Promise<void> {
    this.executions.push(code);
    await this.executeImpl(code, signal);
  }
}

afterEach(() => {
  vi.useRealTimers();
});

describe('DeliveryCoordinator', () => {
  it('serializes deliveries and continues after a rejected attempt', async () => {
    const first = deferred();
    let active = 0;
    let maximum = 0;
    const calls: string[] = [];
    const attempts = new Map<string, number>();
    const coordinator = new DeliveryCoordinator(async item => {
      active += 1;
      maximum = Math.max(maximum, active);
      calls.push(item.request_id);
      attempts.set(item.request_id, (attempts.get(item.request_id) ?? 0) + 1);
      try {
        if (item.request_id === 'first') await first.promise;
        if (item.request_id === 'retry' && attempts.get(item.request_id) === 1) {
          throw new Error('temporary failure');
        }
      } finally {
        active -= 1;
      }
    });

    const pending = [
      coordinator.enqueue(message('save_result', 'first'), () => true),
      coordinator.enqueue(message('save_result', 'retry'), () => true),
      coordinator.enqueue(message('save_result', 'last'), () => true)
    ];
    await Promise.resolve();
    expect(calls).toEqual(['first']);
    first.resolve();
    await Promise.all(pending);

    expect(maximum).toBe(1);
    expect(calls).toEqual(['first', 'retry', 'retry', 'last']);
  });

  it('prioritizes capabilities and coalesces queued themes', async () => {
    const blocker = deferred();
    const calls: string[] = [];
    const coordinator = new DeliveryCoordinator(async item => {
      calls.push(item.request_id);
      if (item.request_id === 'blocker') await blocker.promise;
    });

    const pending = [
      coordinator.enqueue(message('save_result', 'blocker'), () => true),
      coordinator.enqueue(message('theme_changed', 'theme-old'), () => true),
      coordinator.enqueue(message('theme_changed', 'theme-new'), () => true),
      coordinator.enqueue(message('save_result', 'save'), () => true),
      coordinator.enqueue(message('capabilities_result', 'capability'), () => true)
    ];
    await Promise.resolve();
    blocker.resolve();
    await Promise.all(pending);

    expect(calls).toEqual(['blocker', 'capability', 'theme-new', 'save']);
  });

  it('drops stale and closed deliveries without poisoning the queue', async () => {
    const calls: string[] = [];
    const coordinator = new DeliveryCoordinator(async item => { calls.push(item.request_id); });
    await coordinator.enqueue(message('save_result', 'stale'), () => false);
    coordinator.close();
    await coordinator.enqueue(message('save_result', 'closed'), () => true);
    expect(calls).toEqual([]);
  });

  it('aborts the active delivery and discards pending work when closed', async () => {
    const calls: string[] = [];
    const coordinator = new DeliveryCoordinator((item, signal) => new Promise((_, reject) => {
      calls.push(item.request_id);
      signal.addEventListener('abort', () => reject(new Error('cancelled')), { once: true });
    }));
    const active = coordinator.enqueue(message('save_result', 'active'), () => true);
    const pending = coordinator.enqueue(message('save_result', 'pending'), () => true);
    await Promise.resolve();
    coordinator.close();
    await Promise.all([active, pending]);
    expect(calls).toEqual(['active']);
  });
});

describe('kernel delivery recovery', () => {
  it('polls through a missing and busy kernel and uses its replacement', async () => {
    vi.useFakeTimers();
    const busy = new Kernel('busy');
    const replacement = new Kernel('idle');
    let calls = 0;
    const ready = waitForReadyKernel(async () => {
      calls += 1;
      if (calls === 1) return undefined;
      if (calls === 2) return busy;
      return replacement;
    }, new AbortController().signal, 1_000, 100);

    await vi.advanceTimersByTimeAsync(200);
    await expect(ready).resolves.toBe(replacement);
    expect(busy.listeners).toHaveLength(0);
  });

  it('wakes immediately when a busy kernel becomes idle', async () => {
    vi.useFakeTimers();
    const kernel = new Kernel('busy');
    const ready = waitForReadyKernel(async () => kernel, new AbortController().signal);
    await Promise.resolve();
    kernel.setStatus('idle');
    await expect(ready).resolves.toBe(kernel);
    expect(kernel.listeners).toHaveLength(0);
  });

  it('cancels callback execution and reports its timeout', async () => {
    vi.useFakeTimers();
    const kernel = new Kernel('idle');
    kernel.executeImpl = (_code, signal) => new Promise(resolve => {
      signal.addEventListener('abort', () => resolve(), { once: true });
    });
    const execution = executeWithTimeout(
      kernel, 'callback()', new AbortController().signal, 100
    );
    const rejected = expect(execution).rejects.toThrow('timed out');
    await vi.advanceTimersByTimeAsync(100);
    await rejected;
  });

  it('recognizes a Jupyter callback error output', () => {
    const output = {
      items: [{
        mime: 'application/vnd.code.notebook.error',
        data: new TextEncoder().encode(JSON.stringify({ evalue: 'bridge import failed' }))
      }]
    };
    expect(kernelOutputError(output)?.message).toContain('bridge import failed');
    expect(kernelOutputError({ items: [] })).toBeUndefined();
  });
});
