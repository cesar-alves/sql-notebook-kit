export const PROTOCOL_VERSION = 1 as const;
export { installTableCopy, toTsv, type TableCopyOptions } from './tableCopy.js';
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
  session_id: string;
  cell_id: string;
  operation: Operation;
  payload: Record<string, unknown>;
}

const OPERATIONS = new Set<Operation>([
  'capabilities', 'capabilities_result', 'load', 'load_result', 'save',
  'save_result', 'theme_changed', 'error'
]);

function isRecord(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === 'object' && !Array.isArray(value);
}

function jsonLength(value: unknown): number | undefined {
  try { return JSON.stringify(value).length; } catch { return undefined; }
}

export function isCollection(value: unknown): value is Collection {
  if (!isRecord(value)) return false;
  const items = Array.isArray(value.items) ? value.items : [];
  const ids = items.map(item => isRecord(item) ? item.id : undefined);
  const length = jsonLength(value);
  return value.schema_version === 1 &&
    Number.isSafeInteger(value.revision) && Number(value.revision) >= 0 &&
    (value.active_id === null || typeof value.active_id === 'string') &&
    Array.isArray(value.items) && value.items.length <= 50 &&
    value.items.every(isRecord) && ids.every(id => typeof id === 'string') &&
    new Set(ids).size === ids.length &&
    (value.active_id === null || ids.includes(value.active_id)) &&
    length !== undefined && length <= 262_144;
}

export const emptyCollection = (): Collection => ({
  schema_version: 1,
  revision: 0,
  active_id: null,
  items: []
});

export function isBridgeMessage(value: unknown): value is BridgeMessage {
  if (!isRecord(value)) return false;
  const item = value as Partial<BridgeMessage>;
  return (
    item.protocol_version === PROTOCOL_VERSION &&
    typeof item.request_id === 'string' && item.request_id.length <= 80 &&
    typeof item.session_id === 'string' && item.session_id.length <= 80 &&
    typeof item.cell_id === 'string' && item.cell_id.length <= 4096 &&
    typeof item.operation === 'string' && OPERATIONS.has(item.operation as Operation) &&
    isRecord(item.payload) && (jsonLength(value) ?? Infinity) <= 300_000
  );
}

export function collectionFromMetadata(metadata: Record<string, unknown>): Collection {
  const namespace = metadata[METADATA_NAMESPACE] as Record<string, unknown> | undefined;
  const value = namespace?.visualizations;
  if (!value) return emptyCollection();
  if (!isCollection(value)) {
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
