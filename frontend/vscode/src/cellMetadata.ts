import {
  LEGACY_METADATA_NAMESPACE,
  METADATA_NAMESPACE,
  collectionFromMetadata,
  metadataWithCollection,
  type Collection
} from '@sql-notebook-kit/protocol';

function isRecord(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === 'object' && !Array.isArray(value);
}

function hasCollection(metadata: Record<string, unknown>): boolean {
  const current = metadata[METADATA_NAMESPACE];
  const legacy = metadata[LEGACY_METADATA_NAMESPACE];
  return (isRecord(current) && Object.hasOwn(current, 'visualizations')) ||
    (isRecord(legacy) && Object.hasOwn(legacy, 'visualizations'));
}

export function jupyterCellMetadata(
  cellMetadata: Record<string, unknown>
): Record<string, unknown> {
  return isRecord(cellMetadata.metadata) ? cellMetadata.metadata : {};
}

export function hasVisualizationMetadata(cellMetadata: Record<string, unknown>): boolean {
  return hasCollection(jupyterCellMetadata(cellMetadata)) || hasCollection(cellMetadata);
}

export function collectionFromCellMetadata(
  cellMetadata: Record<string, unknown>
): Collection {
  const nested = jupyterCellMetadata(cellMetadata);
  return hasCollection(nested)
    ? collectionFromMetadata(nested)
    : collectionFromMetadata(cellMetadata);
}

export function cellMetadataWithCollection(
  cellMetadata: Record<string, unknown>,
  collection: Collection
): Record<string, unknown> {
  const nested = metadataWithCollection(jupyterCellMetadata(cellMetadata), collection);
  const result: Record<string, unknown> = { ...cellMetadata, metadata: nested };
  const legacyNamespace = result[LEGACY_METADATA_NAMESPACE];
  if (!isRecord(legacyNamespace) || !Object.hasOwn(legacyNamespace, 'visualizations')) {
    return result;
  }
  const { visualizations: _visualizations, ...remaining } = legacyNamespace;
  if (Object.keys(remaining).length) result[LEGACY_METADATA_NAMESPACE] = remaining;
  else delete result[LEGACY_METADATA_NAMESPACE];
  return result;
}
