// @vitest-environment jsdom

import { afterEach, describe, expect, it, vi } from 'vitest';

import { isManagedSql, safeFilename, writeClipboardText } from './helpers.js';
import { applyJupyterTheme, resolveJupyterTheme } from './theme.js';

afterEach(() => {
  vi.unstubAllGlobals();
  document.body.replaceChildren();
});

describe('Redshift notebook editor helpers', () => {
  it('resolves and applies complete host theme tokens to a workspace', () => {
    document.body.style.setProperty('--jp-layout-color0', '#101112');
    document.body.style.setProperty('--jp-border-color1', '#343536');
    const root = document.createElement('div');
    root.className = 'snk-viz-workspace snk-theme-light';

    const theme = resolveJupyterTheme('dark');
    applyJupyterTheme(root, theme);

    expect(theme.tokens.background).toBe('#101112');
    expect(root.classList.contains('snk-theme-dark')).toBe(true);
    expect(root.classList.contains('snk-theme-light')).toBe(false);
    expect(root.style.getPropertyValue('--snk-border')).toBe('#343536');
    expect(root.style.colorScheme).toBe('dark');
  });
  it('recognizes supported SQL magic forms without swallowing later Python', () => {
    expect(isManagedSql('%%sql\nselect 1')).toBe(true);
    expect(isManagedSql('%sql\nselect 1')).toBe(true);
    expect(isManagedSql('%sql select 1')).toBe(true);
    expect(isManagedSql('%sql select 1\nvalue = 2')).toBe(false);
    expect(isManagedSql('print("%%sql")')).toBe(false);
  });

  it('creates a bounded filesystem-safe PNG filename', () => {
    expect(safeFilename(' Revenue / region:*? ')).toBe('Revenue - region---.png');
    expect(safeFilename('   ')).toBe('visualization.png');
    expect(safeFilename('x'.repeat(120))).toBe(`${'x'.repeat(100)}.png`);
  });

  it('uses the browser text clipboard when it is available', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText } });

    await writeClipboardText('a\tb');

    expect(writeText).toHaveBeenCalledWith('a\tb');
  });

  it('falls back to a temporary selected textarea', async () => {
    Object.defineProperty(navigator, 'clipboard', { configurable: true, value: undefined });
    const execCommand = vi.fn().mockReturnValue(true);
    Object.defineProperty(document, 'execCommand', { configurable: true, value: execCommand });

    await writeClipboardText('fallback');

    expect(execCommand).toHaveBeenCalledWith('copy');
    expect(document.querySelector('textarea')).toBeNull();
  });
});
