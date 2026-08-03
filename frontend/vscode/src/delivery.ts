import type { BridgeMessage } from '@redshift-notebooks/protocol';

export interface DeliveryKernel {
  readonly status: string;
  onDidChangeStatus(listener: (status: string) => void): { dispose(): void };
  execute(code: string, signal: AbortSignal): Promise<void>;
}

interface PendingDelivery {
  message: BridgeMessage;
  isCurrent: () => boolean;
  resolve: () => void;
  reject: (error: unknown) => void;
}

interface CoordinatorOptions {
  attempts?: number;
  timeoutMs?: number;
  onExhausted?: (message: BridgeMessage, error: unknown) => void;
}

const aborted = () => new DOMException('Delivery was cancelled.', 'AbortError');

export function kernelOutputError(output: unknown): Error | undefined {
  if (!output || typeof output !== 'object') return undefined;
  const items = (output as { items?: unknown }).items;
  if (!Array.isArray(items)) return undefined;
  const item = items.find(candidate =>
    !!candidate && typeof candidate === 'object' &&
    (candidate as { mime?: unknown }).mime === 'application/vnd.code.notebook.error'
  ) as { data?: unknown } | undefined;
  if (!item) return undefined;
  let detail = '';
  if (item.data instanceof Uint8Array) {
    const decoded = new TextDecoder().decode(item.data).trim();
    if (decoded) {
      try {
        const parsed = JSON.parse(decoded) as { message?: unknown; evalue?: unknown };
        detail = String(parsed.message ?? parsed.evalue ?? decoded);
      } catch {
        detail = decoded;
      }
    }
  }
  return new Error(`Kernel callback returned an error${detail ? `: ${detail}` : '.'}`);
}

function delay(timeoutMs: number, signal: AbortSignal): Promise<void> {
  if (signal.aborted) return Promise.reject(aborted());
  return new Promise((resolve, reject) => {
    const timer = setTimeout(done, timeoutMs);
    function done(): void {
      signal.removeEventListener('abort', cancel);
      resolve();
    }
    function cancel(): void {
      clearTimeout(timer);
      signal.removeEventListener('abort', cancel);
      reject(aborted());
    }
    signal.addEventListener('abort', cancel, { once: true });
  });
}

async function waitForKernelChange(
  kernel: DeliveryKernel,
  timeoutMs: number,
  signal: AbortSignal
): Promise<void> {
  if (signal.aborted) throw aborted();
  await new Promise<void>((resolve, reject) => {
    let subscription: { dispose(): void } | undefined;
    const timer = setTimeout(done, timeoutMs);
    function cleanup(): void {
      clearTimeout(timer);
      subscription?.dispose();
      signal.removeEventListener('abort', cancel);
    }
    function done(): void {
      cleanup();
      resolve();
    }
    function cancel(): void {
      cleanup();
      reject(aborted());
    }
    signal.addEventListener('abort', cancel, { once: true });
    subscription = kernel.onDidChangeStatus(done);
  });
}

export async function waitForReadyKernel(
  getKernel: () => Promise<DeliveryKernel | undefined>,
  signal: AbortSignal,
  timeoutMs = 15_000,
  pollMs = 250
): Promise<DeliveryKernel> {
  const deadline = Date.now() + timeoutMs;
  let lastStatus = 'missing';
  while (!signal.aborted && Date.now() < deadline) {
    const kernel = await getKernel();
    if (kernel?.status === 'idle') return kernel;
    lastStatus = kernel?.status ?? 'missing';
    const remaining = deadline - Date.now();
    if (remaining <= 0) break;
    if (kernel) await waitForKernelChange(kernel, Math.min(pollMs, remaining), signal);
    else await delay(Math.min(pollMs, remaining), signal);
  }
  if (signal.aborted) throw aborted();
  throw new Error(`Kernel did not become idle (last status: ${lastStatus}).`);
}

export async function executeWithTimeout(
  kernel: DeliveryKernel,
  code: string,
  signal: AbortSignal,
  timeoutMs = 10_000
): Promise<void> {
  if (signal.aborted) throw aborted();
  const controller = new AbortController();
  let timedOut = false;
  const cancel = () => controller.abort();
  signal.addEventListener('abort', cancel, { once: true });
  const timer = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, timeoutMs);
  try {
    await kernel.execute(code, controller.signal);
    if (timedOut) throw new Error('Kernel callback execution timed out.');
    if (signal.aborted) throw aborted();
  } finally {
    clearTimeout(timer);
    signal.removeEventListener('abort', cancel);
  }
}

export class DeliveryCoordinator {
  private readonly queue: PendingDelivery[] = [];
  private readonly attempts: number;
  private readonly timeoutMs: number;
  private readonly onExhausted?: (message: BridgeMessage, error: unknown) => void;
  private running = false;
  private closed = false;
  private activeController: AbortController | undefined;

  constructor(
    private readonly deliver: (message: BridgeMessage, signal: AbortSignal) => Promise<void>,
    options: CoordinatorOptions = {}
  ) {
    this.attempts = options.attempts ?? 2;
    this.timeoutMs = options.timeoutMs ?? 30_000;
    this.onExhausted = options.onExhausted;
  }

  enqueue(message: BridgeMessage, isCurrent: () => boolean): Promise<void> {
    if (this.closed) return Promise.resolve();
    return new Promise((resolve, reject) => {
      const pending = { message, isCurrent, resolve, reject };
      if (message.operation === 'theme_changed') {
        const index = this.queue.findIndex(item =>
          item.message.operation === 'theme_changed' &&
          item.message.session_id === message.session_id
        );
        if (index >= 0) {
          this.queue[index].resolve();
          this.queue[index] = pending;
        } else {
          this.queue.push(pending);
        }
      } else if (message.operation === 'capabilities_result') {
        const index = this.queue.findIndex(item => item.message.operation !== 'capabilities_result');
        this.queue.splice(index < 0 ? this.queue.length : index, 0, pending);
      } else {
        this.queue.push(pending);
      }
      void this.drain();
    });
  }

  close(): void {
    this.closed = true;
    this.activeController?.abort();
    for (const pending of this.queue.splice(0)) pending.resolve();
  }

  private async drain(): Promise<void> {
    if (this.running || this.closed) return;
    this.running = true;
    try {
      while (!this.closed) {
        const pending = this.queue.shift();
        if (!pending) break;
        if (!pending.isCurrent()) {
          pending.resolve();
          continue;
        }
        const controller = new AbortController();
        this.activeController = controller;
        const timer = setTimeout(() => controller.abort(), this.timeoutMs);
        let failure: unknown;
        try {
          for (let attempt = 0; attempt < this.attempts && !controller.signal.aborted; attempt++) {
            try {
              await this.deliver(pending.message, controller.signal);
              pending.resolve();
              failure = undefined;
              break;
            } catch (error) {
              failure = error;
            }
          }
          if (failure !== undefined && !this.closed) {
            this.onExhausted?.(pending.message, failure);
            pending.reject(failure);
          } else if (controller.signal.aborted) {
            pending.resolve();
          }
        } finally {
          clearTimeout(timer);
          this.activeController = undefined;
        }
      }
    } finally {
      this.running = false;
      if (!this.closed && this.queue.length) void this.drain();
    }
  }
}
