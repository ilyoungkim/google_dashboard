export function formatNumber(n: number): string {
  return new Intl.NumberFormat('ko-KR').format(Math.round(n));
}

export function formatPercent(n: number): string {
  return (n * 100).toFixed(1) + '%';
}

export function formatPosition(n: number): string {
  return n.toFixed(1);
}

export function formatDate(dateStr: string): string {
  const d = new Date(dateStr);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

export function daysAgo(days: number): string {
  const d = new Date();
  d.setDate(d.getDate() - days);
  return d.toISOString().slice(0, 10);
}

export function todayStr(): string {
  return new Date().toISOString().slice(0, 10);
}
