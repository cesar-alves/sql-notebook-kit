import { describe, expect, it } from 'vitest';

import { BRIDGE_MIME, WIDGET_MIME, managedWidgetCell } from './widgetState.js';

const bytes = (value: unknown) => new TextEncoder().encode(JSON.stringify(value));
const cell = (
  metadata: Record<string, unknown>, mimes: Array<{ mime: string; value?: unknown }>
) => ({
  document: { uri: { toString: () => 'vscode-notebook-cell:/example#1' } },
  metadata,
  outputs: [{
    items: mimes.map(item => ({ mime: item.mime, data: bytes(item.value ?? {}) }))
  }]
});

describe('saved widget ownership', () => {
  it('recognizes current and legacy visualization metadata', () => {
    const collection = {
      schema_version: 1, revision: 1, active_id: null, items: []
    };
    const widget = { mime: WIDGET_MIME, value: { model_id: 'owned' } };
    expect(managedWidgetCell([cell({
      metadata: { sql_notebook_kit: { visualizations: collection } }
    }, [widget])], 'owned')?.managed).toBe(true);
    expect(managedWidgetCell([cell({
      sql_notebook_kit: { visualizations: collection }
    }, [widget])], 'owned')?.managed).toBe(true);
  });

  it('uses the bridge output to recognize an unsaved visualization workspace', () => {
    const match = managedWidgetCell([cell({}, [
      { mime: WIDGET_MIME, value: { model_id: 'owned' } },
      { mime: BRIDGE_MIME }
    ])], 'owned');
    expect(match).toEqual({
      cellId: 'vscode-notebook-cell:/example#1', managed: true
    });
  });

  it('does not claim unrelated or malformed widgets', () => {
    expect(managedWidgetCell([cell({}, [
      { mime: WIDGET_MIME, value: { model_id: 'other' } }
    ])], 'other')?.managed).toBe(false);
    expect(managedWidgetCell([cell({}, [
      { mime: WIDGET_MIME, value: { wrong: true } }
    ])], 'other')).toBeUndefined();
  });
});
