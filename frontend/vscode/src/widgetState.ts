import { hasVisualizationMetadata } from './cellMetadata.js';

export const WIDGET_MIME = 'application/vnd.jupyter.widget-view+json';
export const BRIDGE_MIME = 'application/vnd.sql-notebook-kit.bridge+json';

interface OutputItemLike {
  mime: string;
  data: Uint8Array;
}

interface CellLike {
  document: { uri: { toString(): string } };
  metadata: Record<string, unknown>;
  outputs: readonly {
    items: readonly OutputItemLike[];
    metadata?: Record<string, unknown>;
  }[];
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === 'object' && !Array.isArray(value);
}

function isLiveBridge(output: CellLike['outputs'][number]): boolean {
  if (!output.items.some(item => item.mime === BRIDGE_MIME)) return false;
  const transient = output.metadata?.transient;
  return isRecord(transient) && typeof transient.display_id === 'string';
}

function modelId(item: OutputItemLike): string | undefined {
  if (item.mime !== WIDGET_MIME) return undefined;
  try {
    const value = JSON.parse(new TextDecoder().decode(item.data)) as { model_id?: unknown };
    return typeof value.model_id === 'string' ? value.model_id : undefined;
  } catch {
    return undefined;
  }
}

export function managedWidgetCell(
  cells: readonly CellLike[], model: string
): { cellId: string; managed: boolean; live: boolean } | undefined {
  for (const cell of cells) {
    const items = cell.outputs.flatMap(output => [...output.items]);
    if (!items.some(item => modelId(item) === model)) continue;
    return {
      cellId: cell.document.uri.toString(),
      managed: hasVisualizationMetadata(cell.metadata) ||
        items.some(item => item.mime === BRIDGE_MIME),
      live: cell.outputs.some(isLiveBridge)
    };
  }
  return undefined;
}
