import type { BridgeMessage } from '@redshift-notebooks/protocol';

interface RendererContext { postMessage?(message: unknown): void; }
interface OutputItem { id: string; json(): unknown; }

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

function themeMessage(request: BridgeMessage): BridgeMessage {
  const style = getComputedStyle(document.body);
  const highContrast = matchMedia('(forced-colors: active)').matches;
  const background = token(style, '--vscode-editor-background', '#ffffff');
  const channels = background.slice(1).match(/.{2}/g)?.map(value => parseInt(value, 16)) ?? [255, 255, 255];
  const dark = !highContrast && channels[0] * 299 + channels[1] * 587 + channels[2] * 114 < 128_000;
  return {
    ...request,
    request_id: crypto.randomUUID(),
    operation: 'theme_changed',
    payload: {
      kind: highContrast ? 'high_contrast' : dark ? 'dark' : 'light',
      tokens: {
        background,
        surface: token(style, '--vscode-sideBar-background', background),
        surface_muted: token(style, '--vscode-input-background', background),
        surface_raised: token(style, '--vscode-editorWidget-background', background),
        text: token(style, '--vscode-editor-foreground', '#1f2328'),
        text_muted: token(style, '--vscode-descriptionForeground', '#57606a'),
        border: token(style, '--vscode-widget-border', '#d0d7de'),
        accent: token(style, '--vscode-focusBorder', '#0969da'),
        accent_hover: token(style, '--vscode-button-hoverBackground', '#0550ae'),
        focus: token(style, '--vscode-focusBorder', '#0969da'),
        danger: token(style, '--vscode-errorForeground', '#cf222e'),
        warning_bg: token(style, '--vscode-inputValidation-warningBackground', '#fff8c5'),
        warning_text: token(style, '--vscode-editorWarning-foreground', '#4d2d00'),
        selection_bg: token(style, '--vscode-editor-selectionBackground', '#ddf4ff'),
        input_bg: token(style, '--vscode-input-background', '#f6f8fa')
      }
    }
  };
}

export const activate = (context: RendererContext) => {
  const cleanups = new Map<string, () => void>();
  return {
    renderOutputItem(output: OutputItem, element: HTMLElement) {
      element.hidden = true;
      const request = output.json() as BridgeMessage;
      context.postMessage?.(request);
      if (request.operation !== 'capabilities') return;
      const media = matchMedia('(forced-colors: active)');
      let timer: number | undefined;
      const send = () => {
        window.clearTimeout(timer);
        timer = window.setTimeout(() => context.postMessage?.(themeMessage(request)), 50);
      };
      const observer = new MutationObserver(send);
      observer.observe(document.body, { attributes: true, attributeFilter: ['class', 'style'] });
      media.addEventListener('change', send);
      send();
      cleanups.set(output.id, () => {
        window.clearTimeout(timer);
        observer.disconnect();
        media.removeEventListener('change', send);
      });
    },
    disposeOutputItem(outputId?: string) {
      if (!outputId) return;
      cleanups.get(outputId)?.();
      cleanups.delete(outputId);
    }
  };
};
