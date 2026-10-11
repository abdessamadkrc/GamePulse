export type Unit = 'pct' | 'num' | 'usd' | 'min' | 'int' | 'pp';

const nf = (d: number) => new Intl.NumberFormat('en-US', { minimumFractionDigits: d, maximumFractionDigits: d });

export const isNil = (v: unknown): v is null | undefined => v === null || v === undefined || (typeof v === 'number' && Number.isNaN(v));

export const fmtPct = (v: number | null | undefined, d = 1) => (isNil(v) ? '–' : `${nf(d).format(v * 100)}%`);
export const fmtNum = (v: number | null | undefined, d = 1) => (isNil(v) ? '–' : nf(d).format(v));
export const fmtInt = (v: number | null | undefined) => (isNil(v) ? '–' : nf(0).format(Math.round(v)));
export const fmtUsd = (v: number | null | undefined, d = 2) => (isNil(v) ? '–' : `$${nf(d).format(v)}`);
export const fmtMin = (v: number | null | undefined, d = 1) => (isNil(v) ? '–' : `${nf(d).format(v)}m`);
export const fmtCompact = (v: number | null | undefined) =>
  isNil(v) ? '–' : new Intl.NumberFormat('en-US', { notation: 'compact', maximumFractionDigits: 1 }).format(v);

/** percentage-point delta from a fraction difference, e.g. -0.062 = "−6.2 pp" */
export const fmtPp = (v: number | null | undefined, d = 1) =>
  isNil(v) ? '–' : `${v >= 0 ? '+' : '−'}${nf(d).format(Math.abs(v) * 100)} pp`;
/** delta already expressed in percentage points */
export const fmtPpRaw = (v: number | null | undefined, d = 1) =>
  isNil(v) ? '–' : `${v >= 0 ? '+' : '−'}${nf(d).format(Math.abs(v))} pp`;
export const fmtSignedPct = (v: number | null | undefined, d = 1) =>
  isNil(v) ? '–' : `${v >= 0 ? '+' : '−'}${nf(d).format(Math.abs(v) * 100)}%`;

export function fmtUnit(unit: Unit | string | undefined, v: number | null | undefined, d?: number) {
  switch (unit) {
    case 'pct': return fmtPct(v, d ?? 1);
    case 'usd': return fmtUsd(v, d ?? 2);
    case 'min': return fmtMin(v, d ?? 1);
    case 'int': return fmtInt(v);
    default: return fmtNum(v, d ?? 1);
  }
}

/** Format a before/after delta for a given unit (pct deltas shown in pp). */
export function fmtDeltaUnit(unit: string | undefined, delta: number | null | undefined) {
  if (isNil(delta)) return '–';
  if (unit === 'pct') return fmtPp(delta);
  const sign = delta >= 0 ? '+' : '−';
  const a = Math.abs(delta);
  if (unit === 'usd') return `${sign}$${nf(2).format(a)}`;
  if (unit === 'min') return `${sign}${nf(1).format(a)}m`;
  return `${sign}${nf(2).format(a)}`;
}

export const fmtDate = (iso: string) => new Date(iso + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
export const fmtDateLong = (iso: string) =>
  new Date(iso + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
