import { describe, expect, it } from 'vitest';
import {
  collectionFromMetadata,
  emptyCollection,
  isBridgeMessage,
  metadataWithCollection
} from './index.js';

describe('shared visualization protocol', () => {
  it('uses an empty revision-zero collection for absent metadata', () => {
    expect(collectionFromMetadata({})).toEqual(emptyCollection());
  });

  it('round-trips namespaced metadata without replacing adjacent keys', () => {
    const metadata = metadataWithCollection({ sql_notebook_kit: { keep: true } }, emptyCollection());
    expect(collectionFromMetadata(metadata)).toEqual(emptyCollection());
    expect((metadata.sql_notebook_kit as Record<string, unknown>).keep).toBe(true);
  });

  it('reads legacy metadata and migrates only its visualization collection', () => {
    const legacy = {
      redshift_notebooks: { visualizations: { ...emptyCollection(), revision: 3 }, keep: true },
      adjacent: true
    };
    expect(collectionFromMetadata(legacy).revision).toBe(3);
    const migrated = metadataWithCollection(legacy, { ...emptyCollection(), revision: 4 });
    expect(migrated).toEqual({
      redshift_notebooks: { keep: true },
      sql_notebook_kit: { visualizations: { ...emptyCollection(), revision: 4 } },
      adjacent: true
    });
  });

  it('prefers canonical metadata over a stale legacy collection', () => {
    expect(collectionFromMetadata({
      sql_notebook_kit: { visualizations: { ...emptyCollection(), revision: 5 } },
      redshift_notebooks: { visualizations: { ...emptyCollection(), revision: 2 } }
    }).revision).toBe(5);
  });

  it('rejects an incompatible protocol message', () => {
    expect(isBridgeMessage({ protocol_version: 2 })).toBe(false);
  });

  it('rejects unknown operations and malformed collections', () => {
    expect(isBridgeMessage({
      protocol_version: 1, request_id: 'r', session_id: 's', cell_id: 'c',
      operation: 'execute', payload: {}
    })).toBe(false);
    expect(() => collectionFromMetadata({
      sql_notebook_kit: { visualizations: { schema_version: 1, revision: -1, items: [] } }
    })).toThrow(/newer compatible extension/);
  });
});
