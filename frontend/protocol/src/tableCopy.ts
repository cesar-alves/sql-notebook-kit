export interface TableCopyOptions {
  writeText(value: string): Promise<void>;
}

interface Coordinate {
  row: number;
  column: number;
}

interface Selection {
  anchor: Coordinate;
  focus: Coordinate;
}

const coordinate = (cell: Element): Coordinate => ({
  row: Number(cell.getAttribute('data-snk-row')),
  column: Number(cell.getAttribute('data-snk-column'))
});

function copyCell(target: EventTarget | null): HTMLElement | null {
  return target instanceof Element
    ? target.closest<HTMLElement>('[data-snk-row][data-snk-column]')
    : null;
}

function tableFor(cell: Element): HTMLElement | null {
  return cell.closest<HTMLElement>('.snk-copy-table');
}

function bounds(selection: Selection) {
  return {
    firstRow: Math.min(selection.anchor.row, selection.focus.row),
    lastRow: Math.max(selection.anchor.row, selection.focus.row),
    firstColumn: Math.min(selection.anchor.column, selection.focus.column),
    lastColumn: Math.max(selection.anchor.column, selection.focus.column)
  };
}

function cellValue(cell: Element): string {
  return cell.hasAttribute('data-snk-null') ? '' : cell.textContent ?? '';
}

function matrix(
  table: Element,
  selected?: Selection
): string[][] {
  const cells = Array.from(
    table.querySelectorAll<HTMLElement>('[data-snk-row][data-snk-column]')
  );
  if (!cells.length) return [];
  const range = selected ?? {
    anchor: { row: 0, column: 0 },
    focus: {
      row: Math.max(...cells.map(cell => coordinate(cell).row)),
      column: Math.max(...cells.map(cell => coordinate(cell).column))
    }
  };
  const { firstRow, lastRow, firstColumn, lastColumn } = bounds(range);
  const lookup = new Map(cells.map(cell => {
    const point = coordinate(cell);
    return [`${point.row}:${point.column}`, cellValue(cell)] as const;
  }));
  const result: string[][] = [];
  for (let row = firstRow; row <= lastRow; row += 1) {
    const values: string[] = [];
    for (let column = firstColumn; column <= lastColumn; column += 1) {
      values.push(lookup.get(`${row}:${column}`) ?? '');
    }
    result.push(values);
  }
  return result;
}

function quoteTsv(value: string): string {
  return /[\t\r\n"]/.test(value) ? `"${value.replaceAll('"', '""')}"` : value;
}

export function toTsv(rows: string[][]): string {
  return rows.map(row => row.map(quoteTsv).join('\t')).join('\n');
}

function status(root: Element, message: string, error = false): void {
  const target = root.querySelector<HTMLElement>('.snk-copy-status');
  if (!target) return;
  target.textContent = message;
  target.classList.toggle('snk-error', error);
}

function announce(root: Element, rows: string[][]): void {
  const dataRows = rows.length > 0 ? rows.length : 0;
  const columns = rows[0]?.length ?? 0;
  status(root, `Copied ${dataRows.toLocaleString()} row${dataRows === 1 ? '' : 's'} × ` +
    `${columns.toLocaleString()} column${columns === 1 ? '' : 's'}.`);
}

function renderSelection(table: HTMLElement, selection: Selection): void {
  const range = bounds(selection);
  for (const cell of table.querySelectorAll<HTMLElement>('[data-snk-row][data-snk-column]')) {
    const point = coordinate(cell);
    const selected = point.row >= range.firstRow && point.row <= range.lastRow &&
      point.column >= range.firstColumn && point.column <= range.lastColumn;
    const active = point.row === selection.focus.row && point.column === selection.focus.column;
    if (selected) cell.setAttribute('data-snk-selected', 'true');
    else cell.removeAttribute('data-snk-selected');
    cell.setAttribute('aria-selected', String(selected));
    if (active) cell.setAttribute('data-snk-active', 'true');
    else cell.removeAttribute('data-snk-active');
    cell.tabIndex = active ? 0 : -1;
    if (active) cell.focus({ preventScroll: true });
  }
}

function move(table: HTMLElement, current: Coordinate, key: string): Coordinate {
  const cells = Array.from(
    table.querySelectorAll<HTMLElement>('[data-snk-row][data-snk-column]')
  ).map(coordinate);
  const maxRow = Math.max(...cells.map(item => item.row));
  const maxColumn = Math.max(...cells.map(item => item.column));
  const delta = {
    ArrowUp: [-1, 0], ArrowDown: [1, 0], ArrowLeft: [0, -1], ArrowRight: [0, 1]
  }[key] ?? [0, 0];
  return {
    row: Math.max(0, Math.min(maxRow, current.row + delta[0])),
    column: Math.max(0, Math.min(maxColumn, current.column + delta[1]))
  };
}

export function installTableCopy(options: TableCopyOptions): () => void {
  const selections = new WeakMap<HTMLElement, Selection>();
  let dragging: HTMLElement | null = null;

  const select = (cell: HTMLElement, extend: boolean) => {
    const table = tableFor(cell);
    if (!table) return;
    const point = coordinate(cell);
    const existing = selections.get(table);
    const selection = extend && existing
      ? { anchor: existing.anchor, focus: point }
      : { anchor: point, focus: point };
    selections.set(table, selection);
    renderSelection(table, selection);
  };

  const pointerDown = (event: Event) => {
    const pointer = event as PointerEvent;
    if (typeof pointer.button === 'number' && pointer.button !== 0) return;
    const cell = copyCell(event.target);
    if (!cell) return;
    event.preventDefault();
    select(cell, pointer.shiftKey);
    dragging = tableFor(cell);
  };
  const pointerOver = (event: Event) => {
    const cell = copyCell(event.target);
    if (!cell || !dragging || tableFor(cell) !== dragging) return;
    select(cell, true);
  };
  const pointerUp = () => { dragging = null; };
  const keyDown = (event: KeyboardEvent) => {
    if (!['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight'].includes(event.key)) return;
    const cell = copyCell(event.target);
    const table = cell ? tableFor(cell) : null;
    if (!cell || !table) return;
    event.preventDefault();
    const existing = selections.get(table) ?? { anchor: coordinate(cell), focus: coordinate(cell) };
    const next = move(table, existing.focus, event.key);
    const selection = event.shiftKey
      ? { anchor: existing.anchor, focus: next }
      : { anchor: next, focus: next };
    selections.set(table, selection);
    renderSelection(table, selection);
  };
  const copy = (event: ClipboardEvent) => {
    const eventTable = copyCell(event.target)?.closest<HTMLElement>('.snk-copy-table');
    const activeTable = document.activeElement?.closest<HTMLElement>('.snk-copy-table');
    const table = eventTable ?? activeTable ?? null;
    const selection = table ? selections.get(table) : undefined;
    const root = table?.closest('.snk-viz-workspace');
    if (!table || !selection || !root || !event.clipboardData) return;
    const rows = matrix(table, selection);
    event.preventDefault();
    event.clipboardData.setData('text/plain', toTsv(rows));
    announce(root, rows);
  };
  const click = async (event: Event) => {
    const target = event.target instanceof Element ? event.target : null;
    const button = target?.closest('.snk-copy-button');
    const root = button?.closest('.snk-viz-workspace');
    if (!button || !root) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    const payload = root.querySelector<HTMLTextAreaElement>('.snk-copy-payload');
    const table = root.querySelector<HTMLElement>('.snk-copy-table');
    const rows = table ? matrix(table) : [];
    const value = payload?.value ?? toTsv(rows);
    status(root, 'Copying TSV…');
    try {
      await options.writeText(value);
      if (payload) {
        status(root, 'Copied visualization data.');
      } else {
        announce(root, rows);
      }
    } catch {
      status(root, 'Copy failed. Check clipboard permissions and try again.', true);
    }
  };

  document.addEventListener('pointerdown', pointerDown, true);
  document.addEventListener('pointerover', pointerOver, true);
  document.addEventListener('pointerup', pointerUp, true);
  document.addEventListener('keydown', keyDown, true);
  document.addEventListener('copy', copy, true);
  document.addEventListener('click', click, true);
  return () => {
    document.removeEventListener('pointerdown', pointerDown, true);
    document.removeEventListener('pointerover', pointerOver, true);
    document.removeEventListener('pointerup', pointerUp, true);
    document.removeEventListener('keydown', keyDown, true);
    document.removeEventListener('copy', copy, true);
    document.removeEventListener('click', click, true);
  };
}
