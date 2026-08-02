import type { BridgeMessage } from '@redshift-notebooks/protocol';

interface RendererContext {
  postMessage?(message: unknown): void;
}

interface OutputItem {
  json(): unknown;
}

export const activate = (context: RendererContext) => ({
  renderOutputItem(output: OutputItem, element: HTMLElement) {
    element.hidden = true;
    const message = output.json() as BridgeMessage;
    context.postMessage?.(message);
  }
});
