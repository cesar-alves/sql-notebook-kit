import { describe, expect, it } from 'vitest';

import { activate } from './renderer.js';

describe('VS Code bridge renderer', () => {
  it('provides a notebook output renderer', () => {
    const renderer = activate({});
    expect(renderer.renderOutputItem).toBeTypeOf('function');
    expect(renderer.disposeOutputItem).toBeTypeOf('function');
  });
});
