import type { ResolvedTheme, ThemeKind, ThemeTokens } from '@sql-notebook-kit/protocol';

const LIGHT: ThemeTokens = {
  background: '#ffffff', surface: '#ffffff', surface_muted: '#f6f8fa',
  surface_raised: '#ffffff', text: '#1f2328', text_muted: '#57606a',
  border: '#d0d7de', accent: '#0969da', accent_hover: '#0550ae',
  focus: '#0550ae', danger: '#cf222e', warning_bg: '#fff8c5',
  warning_text: '#4d2d00', selection_bg: '#ddf4ff', input_bg: '#f6f8fa'
};
const DARK: ThemeTokens = {
  background: '#1e1e1e', surface: '#252526', surface_muted: '#313131',
  surface_raised: '#2d2d30', text: '#f0f0f0', text_muted: '#c4c4c4',
  border: '#5a5a5a', accent: '#4daafc', accent_hover: '#75beff',
  focus: '#75beff', danger: '#f48771', warning_bg: '#3b2e00',
  warning_text: '#ffd866', selection_bg: '#063b49', input_bg: '#313131'
};

function composite(
  foreground: [number, number, number], alpha: number, backdrop: string
): string {
  const background = backdrop.slice(1).match(/.{2}/g)?.map(value => parseInt(value, 16));
  if (!background || background.length !== 3) return backdrop;
  const channels = foreground.map((value, index) =>
    Math.round(value * alpha + background[index] * (1 - alpha))
  );
  return `#${channels.map(value => value.toString(16).padStart(2, '0')).join('')}`;
}

function token(
  style: CSSStyleDeclaration,
  names: string | string[],
  fallback: string,
  backdrop = fallback
): string {
  const candidates = Array.isArray(names) ? names : [names];
  const value = candidates
    .map(name => style.getPropertyValue(name).trim())
    .find(candidate => candidate.length > 0);
  const probe = document.createElement('span');
  probe.style.color = value || fallback;
  probe.style.display = 'none';
  document.body.appendChild(probe);
  const resolved = getComputedStyle(probe).color;
  probe.remove();
  const match = resolved.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)(?:,\s*([\d.]+))?/);
  if (!match) return fallback;
  const foreground = match.slice(1, 4).map(Number) as [number, number, number];
  const alpha = match[4] === undefined ? 1 : Number(match[4]);
  return composite(foreground, alpha, backdrop);
}

function isDark(color: string): boolean {
  const channels = color.slice(1).match(/.{2}/g)?.map(value => parseInt(value, 16));
  return !!channels && channels[0] * 299 + channels[1] * 587 + channels[2] * 114 < 128_000;
}

function bodyTheme(forcedColors: boolean): ThemeKind | undefined {
  if (forcedColors || document.body.classList.contains('vscode-high-contrast') ||
      document.body.classList.contains('vscode-high-contrast-light')) {
    return 'high_contrast';
  }
  if (document.body.classList.contains('vscode-dark')) return 'dark';
  if (document.body.classList.contains('vscode-light')) return 'light';
  return undefined;
}

export function resolveVsCodeTheme(forcedColors: boolean): ResolvedTheme {
  const style = getComputedStyle(document.body);
  let kind = bodyTheme(forcedColors);
  let fallback = kind === 'dark' || kind === 'high_contrast' ? DARK : LIGHT;
  const background = token(style, [
    '--vscode-notebook-editorBackground', '--vscode-editor-background'
  ], fallback.background);
  if (!kind) {
    kind = isDark(background) ? 'dark' : 'light';
    fallback = kind === 'dark' ? DARK : LIGHT;
  }
  return {
    kind,
    tokens: {
      background,
      surface: token(style, '--vscode-sideBar-background', fallback.surface, background),
      surface_muted: token(style, '--vscode-input-background', fallback.surface_muted, background),
      surface_raised: token(
        style, '--vscode-editorWidget-background', fallback.surface_raised, background
      ),
      text: token(style, '--vscode-editor-foreground', fallback.text, background),
      text_muted: token(
        style, '--vscode-descriptionForeground', fallback.text_muted, background
      ),
      border: token(style, [
        '--vscode-panel-border', '--vscode-widget-border'
      ], fallback.border, background),
      accent: token(style, '--vscode-focusBorder', fallback.accent, background),
      accent_hover: token(
        style, '--vscode-button-hoverBackground', fallback.accent_hover, background
      ),
      focus: token(style, '--vscode-focusBorder', fallback.focus, background),
      danger: token(style, '--vscode-errorForeground', fallback.danger, background),
      warning_bg: token(
        style, '--vscode-inputValidation-warningBackground', fallback.warning_bg, background
      ),
      warning_text: token(
        style, '--vscode-editorWarning-foreground', fallback.warning_text, background
      ),
      selection_bg: token(style, [
        '--vscode-list-activeSelectionBackground', '--vscode-editor-selectionBackground'
      ], fallback.selection_bg, background),
      input_bg: token(style, '--vscode-input-background', fallback.input_bg, background)
    }
  };
}

export function applyWorkspaceTheme(root: HTMLElement, theme: ResolvedTheme): void {
  for (const kind of ['light', 'dark', 'high-contrast']) {
    root.classList.toggle(`snk-theme-${kind}`, kind === theme.kind.replace('_', '-'));
  }
  for (const [name, value] of Object.entries(theme.tokens)) {
    root.style.setProperty(`--snk-${name.replaceAll('_', '-')}`, value);
  }
  root.style.colorScheme = theme.kind === 'light' ? 'light' : 'dark';
}
