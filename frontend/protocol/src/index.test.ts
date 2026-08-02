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
    const metadata = metadataWithCollection({ redshift_notebooks: { keep: true } }, emptyCollection());
    expect(collectionFromMetadata(metadata)).toEqual(emptyCollection());
    expect((metadata.redshift_notebooks as Record<string, unknown>).keep).toBe(true);
  });

  it('rejects an incompatible protocol message', () => {
    expect(isBridgeMessage({ protocol_version: 2 })).toBe(false);
  });
});
