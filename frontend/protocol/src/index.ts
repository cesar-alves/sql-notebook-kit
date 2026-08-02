export const PROTOCOL_VERSION = 1 as const;
export const COMM_TARGET = 'redshift_notebooks.visualizations.v1';
export const METADATA_NAMESPACE = 'redshift_notebooks';

export type ThemeKind = 'light' | 'dark' | 'high_contrast';
export type Operation =
  | 'capabilities'
  | 'capabilities_result'
  | 'load'
  | 'load_result'
  | 'save'
  | 'save_result'
  | 'theme_changed'
  | 'error';

export interface Collection {
  schema_version: 1;
  revision: number;
  active_id: string | null;
  items: unknown[];
}

export interface BridgeMessage {
  protocol_version: number;
  request_id: string;
  cell_id: string;
  operation: Operation;
  payload: Record<string, unknown>;
}

export const emptyCollection = (): Collection => ({
  schema_version: 1,
  revision: 0,
  active_id: null,
  items: []
});

export function isBridgeMessage(value: unknown): value is BridgeMessage {
  if (!value || typeof value !== 'object') return false;
  const item = value as Partial<BridgeMessage>;
  return (
    item.protocol_version === PROTOCOL_VERSION &&
    typeof item.request_id === 'string' &&
    typeof item.cell_id === 'string' &&
    typeof item.operation === 'string' &&
    !!item.payload &&
    typeof item.payload === 'object'
  );
}

export function collectionFromMetadata(metadata: Record<string, unknown>): Collection {
  const namespace = metadata[METADATA_NAMESPACE] as Record<string, unknown> | undefined;
  const value = namespace?.visualizations;
  if (!value) return emptyCollection();
  if (typeof value !== 'object' || (value as Collection).schema_version !== 1) {
    throw new Error('Visualization metadata requires a newer compatible extension.');
  }
  return value as Collection;
}

export function metadataWithCollection(
  metadata: Record<string, unknown>,
  collection: Collection
): Record<string, unknown> {
  const namespace = (metadata[METADATA_NAMESPACE] as Record<string, unknown> | undefined) ?? {};
  return {
    ...metadata,
    [METADATA_NAMESPACE]: { ...namespace, visualizations: collection }
  };
}
