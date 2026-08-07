// @vitest-environment jsdom

import { afterEach, describe, expect, it, vi } from 'vitest';

import { installTableCopy, toTsv } from './tableCopy.js';

const disposers: Array<() => void> = [];

function install(writeText: (value: string) => Promise<void>): () => void {
  const dispose = installTableCopy({ writeText });
  disposers.push(dispose);
  return dispose;
}

function workspace(): HTMLElement {
  const root = document.createElement('div');
  root.className = 'rn-viz-workspace';
  root.innerHTML = `
    <button class="rn-copy-button">Copy table</button>
    <div class="rn-copy-status"></div>
    <div class="rn-copy-table" tabindex="0">
      <table>
        <thead><tr>
          <th tabindex="-1" data-rn-row="0" data-rn-column="0">First</th>
          <th tabindex="-1" data-rn-row="0" data-rn-column="1">Second</th>
        </tr></thead>
        <tbody>
          <tr><td tabindex="-1" data-rn-row="1" data-rn-column="0">a</td>
              <td tabindex="-1" data-rn-row="1" data-rn-column="1">b</td></tr>
          <tr><td tabindex="-1" data-rn-row="2" data-rn-column="0" data-rn-null="true">—</td>
              <td tabindex="-1" data-rn-row="2" data-rn-column="1">d</td></tr>
        </tbody>
      </table>
    </div>`;
  document.body.appendChild(root);
  return root;
}

function pointer(target: Element, type: string, options: MouseEventInit = {}): void {
  target.dispatchEvent(new MouseEvent(type, { bubbles: true, button: 0, ...options }));
}

function copy(target: Element): { prevented: boolean; text: string } {
  let text = '';
  const event = new Event('copy', { bubbles: true, cancelable: true });
  Object.defineProperty(event, 'clipboardData', {
    value: { setData: (type: string, value: string) => { if (type === 'text/plain') text = value; } }
  });
  target.dispatchEvent(event);
  return { prevented: event.defaultPrevented, text };
}

afterEach(() => {
  for (const dispose of disposers.splice(0)) dispose();
  document.body.replaceChildren();
});

describe('table copy controller', () => {
  it('serializes simple TSV and quotes only structurally special values', () => {
    expect(toTsv([['plain', 'a\tb'], ['line\nbreak', 'say "hello"']])).toBe(
      'plain\t"a\tb"\n"line\nbreak"\t"say ""hello"""'
    );
  });

  it('copies a dragged rectangle without adding unselected headers', () => {
    const root = workspace();
    const dispose = install(vi.fn());
    const start = root.querySelector('[data-rn-row="1"][data-rn-column="0"]') as HTMLElement;
    const end = root.querySelector('[data-rn-row="2"][data-rn-column="1"]') as HTMLElement;

    pointer(start, 'pointerdown');
    pointer(end, 'pointerover');
    pointer(end, 'pointerup');
    const result = copy(end);

    expect(result).toEqual({ prevented: true, text: 'a\tb\n\td' });
    expect(root.querySelectorAll('[data-rn-selected="true"]')).toHaveLength(4);
    expect(root.querySelector('.rn-copy-status')?.textContent).toBe('Copied 2 rows × 2 columns.');
    dispose();
  });

  it('expands a header selection with Shift+Arrow and includes selected headers', () => {
    const root = workspace();
    const dispose = install(vi.fn());
    const header = root.querySelector('[data-rn-row="0"][data-rn-column="0"]') as HTMLElement;
    pointer(header, 'pointerdown');
    header.dispatchEvent(new KeyboardEvent('keydown', {
      bubbles: true, key: 'ArrowRight', shiftKey: true
    }));

    const active = root.querySelector('[data-rn-active="true"]') as HTMLElement;
    expect(copy(active).text).toBe('First\tSecond');
    expect(active.textContent).toBe('Second');
    dispose();
  });

  it('copies the complete table from the button and reports host failures', async () => {
    const root = workspace();
    const writeText = vi.fn().mockResolvedValueOnce(undefined).mockRejectedValueOnce(new Error());
    const dispose = install(writeText);
    const button = root.querySelector('.rn-copy-button') as HTMLButtonElement;

    button.click();
    await Promise.resolve();
    expect(writeText).toHaveBeenCalledWith('First\tSecond\na\tb\n\td');
    expect(root.querySelector('.rn-copy-status')?.textContent).toBe('Copied 3 rows × 2 columns.');

    button.click();
    await Promise.resolve();
    await Promise.resolve();
    expect(root.querySelector('.rn-copy-status')?.textContent)
      .toBe('Copy failed. Check clipboard permissions and try again.');
    expect(root.querySelector('.rn-copy-status')?.classList.contains('rn-error')).toBe(true);
    dispose();
  });

  it('prefers a prepared visualization payload over a table', async () => {
    const root = workspace();
    const payload = document.createElement('textarea');
    payload.className = 'rn-copy-payload';
    payload.value = 'Period\tRevenue\n2026-01\t3';
    root.querySelector('.rn-copy-table')?.remove();
    root.appendChild(payload);
    const writeText = vi.fn().mockResolvedValue(undefined);
    const dispose = install(writeText);

    (root.querySelector('.rn-copy-button') as HTMLButtonElement).click();
    await Promise.resolve();

    expect(writeText).toHaveBeenCalledWith('Period\tRevenue\n2026-01\t3');
    expect(root.querySelector('.rn-copy-status')?.textContent).toBe('Copied visualization data.');
    dispose();
  });
});
