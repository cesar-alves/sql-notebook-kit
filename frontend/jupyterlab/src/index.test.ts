// @vitest-environment jsdom

import { describe, expect, it } from 'vitest';

import { isManagedSql, safeFilename } from './helpers.js';

describe('Redshift notebook editor helpers', () => {
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
});
