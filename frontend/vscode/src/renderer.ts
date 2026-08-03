import type { BridgeMessage } from '@redshift-notebooks/protocol';
import type {
  ActivationFunction, OutputItem, RendererApi, RendererContext
} from 'vscode-notebook-renderer';

type ThemeKind = 'light' | 'dark' | 'high_contrast';

const LIGHT = {
  background: '#ffffff', surface: '#ffffff', surface_muted: '#f6f8fa',
  surface_raised: '#ffffff', text: '#1f2328', text_muted: '#57606a',
  border: '#d0d7de', accent: '#0969da', accent_hover: '#0550ae',
  focus: '#0550ae', danger: '#cf222e', warning_bg: '#fff8c5',
  warning_text: '#4d2d00', selection_bg: '#ddf4ff', input_bg: '#f6f8fa'
};
const DARK = {
  background: '#1e1e1e', surface: '#252526', surface_muted: '#313131',
  surface_raised: '#2d2d30', text: '#f0f0f0', text_muted: '#c4c4c4',
  border: '#5a5a5a', accent: '#4daafc', accent_hover: '#75beff',
  focus: '#75beff', danger: '#f48771', warning_bg: '#3b2e00',
  warning_text: '#ffd866', selection_bg: '#063b49', input_bg: '#313131'
};

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

function isDark(color: string): boolean {
  const channels = color.slice(1).match(/.{2}/g)?.map(value => parseInt(value, 16));
  return !!channels && channels[0] * 299 + channels[1] * 587 + channels[2] * 114 < 128_000;
}

function bodyTheme(forcedColors: boolean): ThemeKind | undefined {
  if (forcedColors || document.body.classList.contains('vscode-high-contrast')) {
    return 'high_contrast';
  }
  if (document.body.classList.contains('vscode-dark')) return 'dark';
  if (document.body.classList.contains('vscode-light')) return 'light';
  return undefined;
}

function themeMessage(request: BridgeMessage, forcedColors: boolean): BridgeMessage {
  const style = getComputedStyle(document.body);
  let kind = bodyTheme(forcedColors);
  let fallback = kind === 'dark' || kind === 'high_contrast' ? DARK : LIGHT;
  const background = token(style, '--vscode-editor-background', fallback.background);
  if (!kind) {
    kind = isDark(background) ? 'dark' : 'light';
    fallback = kind === 'dark' ? DARK : LIGHT;
  }
  return {
    ...request,
    request_id: crypto.randomUUID(),
    operation: 'theme_changed',
    payload: {
      kind,
      tokens: {
        background,
        surface: token(style, '--vscode-sideBar-background', fallback.surface),
        surface_muted: token(style, '--vscode-input-background', fallback.surface_muted),
        surface_raised: token(style, '--vscode-editorWidget-background', fallback.surface_raised),
        text: token(style, '--vscode-editor-foreground', fallback.text),
        text_muted: token(style, '--vscode-descriptionForeground', fallback.text_muted),
        border: token(style, '--vscode-widget-border', fallback.border),
        accent: token(style, '--vscode-focusBorder', fallback.accent),
        accent_hover: token(style, '--vscode-button-hoverBackground', fallback.accent_hover),
        focus: token(style, '--vscode-focusBorder', fallback.focus),
        danger: token(style, '--vscode-errorForeground', fallback.danger),
        warning_bg: token(style, '--vscode-inputValidation-warningBackground', fallback.warning_bg),
        warning_text: token(style, '--vscode-editorWarning-foreground', fallback.warning_text),
        selection_bg: token(style, '--vscode-editor-selectionBackground', fallback.selection_bg),
        input_bg: token(style, '--vscode-input-background', fallback.input_bg)
      }
    }
  };
}

export const activate = ((context: RendererContext<unknown>): RendererApi => {
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
        timer = window.setTimeout(
          () => context.postMessage?.(themeMessage(request, media.matches)), 50
        );
      };
      const observer = new MutationObserver(send);
      observer.observe(document.body, { attributes: true, attributeFilter: ['class', 'style'] });
      media.addEventListener('change', send);
      send();
      cleanups.get(output.id)?.();
      cleanups.set(output.id, () => {
        window.clearTimeout(timer);
        observer.disconnect();
        media.removeEventListener('change', send);
      });
    },
    disposeOutputItem(outputId?: string) {
      if (!outputId) {
        for (const cleanup of cleanups.values()) cleanup();
        cleanups.clear();
        return;
      }
      cleanups.get(outputId)?.();
      cleanups.delete(outputId);
    }
  };
}) satisfies ActivationFunction;
