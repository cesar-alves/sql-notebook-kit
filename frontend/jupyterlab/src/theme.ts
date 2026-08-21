import type { ResolvedTheme, ThemeKind } from '@sql-notebook-kit/protocol';

function opaqueColor(value: string, fallback: string): string {
  const probe = document.createElement('span');
  probe.style.color = value || fallback;
  probe.style.display = 'none';
  document.body.appendChild(probe);
  const resolved = getComputedStyle(probe).color;
  probe.remove();
  const match = resolved.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)/);
  if (!match) return fallback;
  return `#${match.slice(1, 4).map(part => Number(part).toString(16).padStart(2, '0')).join('')}`;
}

export function resolveJupyterTheme(kind: ThemeKind): ResolvedTheme {
  const style = getComputedStyle(document.body);
  const token = (name: string, fallback: string) =>
    opaqueColor(style.getPropertyValue(name).trim(), fallback);
  const dark = kind !== 'light';
  return {
    kind,
    tokens: {
      background: token('--jp-layout-color0', dark ? '#1e1e1e' : '#ffffff'),
      surface: token('--jp-layout-color1', dark ? '#252526' : '#ffffff'),
      surface_muted: token('--jp-layout-color2', dark ? '#313131' : '#f6f8fa'),
      surface_raised: token('--jp-layout-color1', dark ? '#2d2d30' : '#ffffff'),
      text: token('--jp-ui-font-color1', dark ? '#f0f0f0' : '#1f2328'),
      text_muted: token('--jp-ui-font-color2', dark ? '#c4c4c4' : '#57606a'),
      border: token('--jp-border-color1', dark ? '#5a5a5a' : '#d0d7de'),
      accent: token('--jp-brand-color1', dark ? '#4daafc' : '#0969da'),
      accent_hover: token('--jp-brand-color2', dark ? '#75beff' : '#0550ae'),
      focus: token('--jp-brand-color1', dark ? '#75beff' : '#0550ae'),
      danger: token('--jp-error-color1', dark ? '#f48771' : '#cf222e'),
      warning_bg: token('--jp-warn-color3', dark ? '#3b2e00' : '#fff8c5'),
      warning_text: dark ? '#ffd866' : '#4d2d00',
      selection_bg: token('--jp-layout-color2', dark ? '#063b49' : '#ddf4ff'),
      input_bg: token('--jp-layout-color2', dark ? '#313131' : '#f6f8fa')
    }
  };
}

export function applyJupyterTheme(root: HTMLElement, theme: ResolvedTheme): void {
  for (const kind of ['light', 'dark', 'high-contrast']) {
    root.classList.toggle(`snk-theme-${kind}`, kind === theme.kind.replace('_', '-'));
  }
  for (const [name, value] of Object.entries(theme.tokens)) {
    root.style.setProperty(`--snk-${name.replaceAll('_', '-')}`, value);
  }
  root.style.colorScheme = theme.kind === 'light' ? 'light' : 'dark';
}
