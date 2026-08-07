export function isManagedSql(source: string): boolean {
  const lines = source.split(/\r?\n/);
  const first = lines[0] ?? '';
  return /^\s*%%sql(?:\s.*)?$/.test(first) ||
    /^\s*%sql\s*$/.test(first) ||
    (lines.length === 1 && /^\s*%sql\s+/.test(first));
}

export function safeFilename(value: string): string {
  const stem = value.trim().replace(/[\\/:*?"<>|\u0000-\u001f]/g, '-').replace(/\s+/g, ' ');
  return `${(stem || 'visualization').slice(0, 100)}.png`;
}

export async function writeClipboardText(value: string): Promise<void> {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(value);
    return;
  }
  const fallback = document.createElement('textarea');
  fallback.value = value;
  fallback.style.position = 'fixed';
  fallback.style.opacity = '0';
  document.body.appendChild(fallback);
  fallback.select();
  const copied = document.execCommand('copy');
  fallback.remove();
  if (!copied) throw new Error('Clipboard access is unavailable.');
}
