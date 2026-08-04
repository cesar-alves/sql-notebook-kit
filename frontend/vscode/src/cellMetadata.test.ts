import { describe, expect, it } from 'vitest';

import {
  cellMetadataWithCollection,
  collectionFromCellMetadata,
  hasVisualizationMetadata
} from './cellMetadata.js';

const saved = {
  schema_version: 1 as const,
  revision: 4,
  active_id: null,
  items: []
};

describe('VS Code Jupyter cell metadata', () => {
  it('reads the nested metadata sent to execute requests', () => {
    const cell = { metadata: { redshift_notebooks: { visualizations: saved }, keep: true } };
    expect(collectionFromCellMetadata(cell)).toEqual(saved);
    expect(hasVisualizationMetadata(cell)).toBe(true);
  });

  it('reads legacy top-level metadata and migrates it on write', () => {
    const legacy = {
      metadata: { keep: true },
      redshift_notebooks: { visualizations: saved, legacyKeep: true },
      vscodeKeep: true
    };
    expect(collectionFromCellMetadata(legacy)).toEqual(saved);

    const next = { ...saved, revision: 5 };
    const migrated = cellMetadataWithCollection(legacy, next);
    expect(migrated).toEqual({
      metadata: {
        keep: true,
        redshift_notebooks: { visualizations: next }
      },
      redshift_notebooks: { legacyKeep: true },
      vscodeKeep: true
    });
  });

  it('prefers canonical nested metadata over a stale legacy copy', () => {
    const nested = { ...saved, revision: 7 };
    expect(collectionFromCellMetadata({
      metadata: { redshift_notebooks: { visualizations: nested } },
      redshift_notebooks: { visualizations: saved }
    })).toEqual(nested);
  });
});
