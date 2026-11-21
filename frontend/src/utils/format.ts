const p2 = (n: number) => String(n).padStart(2, '0');

/** Локальная дата в формате YYYY-MM-DD (не UTC!). */
export function toISODate(d: Date): string {
  return `${d.getFullYear()}-${p2(d.getMonth() + 1)}-${p2(d.getDate())}`;
}

/** 21.11.2026 */
export function fmtDate(iso: string): string {
  const d = new Date(iso.length === 10 ? iso + 'T00:00:00' : iso);
  if (Number.isNaN(d.getTime())) return '—';
  return `${p2(d.getDate())}.${p2(d.getMonth() + 1)}.${d.getFullYear()}`;
}

/** 21.11.2026, 14:30 */
export function fmtDateTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  return `${fmtDate(iso)}, ${p2(d.getHours())}:${p2(d.getMinutes())}`;
}

export function addYears(d: Date, years: number): Date {
  const r = new Date(d);
  r.setFullYear(r.getFullYear() + years);
  return r;
}

export function clamp(v: number, a: number, b: number): number {
  return Math.max(a, Math.min(b, v));
}

/** «1 działka», «2 działki», «5 działek» */
export function dzialki(n: number): string {
  if (n === 1) return '1 działka';
  const few = n % 10 >= 2 && n % 10 <= 4 && (n % 100 < 10 || n % 100 >= 20);
  return `${n} ${few ? 'działki' : 'działek'}`;
}
