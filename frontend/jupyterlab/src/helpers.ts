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
