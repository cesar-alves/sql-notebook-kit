import { hasVisualizationMetadata } from './cellMetadata.js';

export const WIDGET_MIME = 'application/vnd.jupyter.widget-view+json';
export const BRIDGE_MIME = 'application/vnd.redshift-notebooks.bridge+json';

interface OutputItemLike {
  mime: string;
  data: Uint8Array;
}

interface CellLike {
  document: { uri: { toString(): string } };
  metadata: Record<string, unknown>;
  outputs: readonly { items: readonly OutputItemLike[] }[];
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
): { cellId: string; managed: boolean } | undefined {
  for (const cell of cells) {
    const items = cell.outputs.flatMap(output => [...output.items]);
    if (!items.some(item => modelId(item) === model)) continue;
    return {
      cellId: cell.document.uri.toString(),
      managed: hasVisualizationMetadata(cell.metadata) ||
        items.some(item => item.mime === BRIDGE_MIME)
    };
  }
  return undefined;
}
