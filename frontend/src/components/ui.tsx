'use client';
import { ReactNode, useMemo, useState } from 'react';
import { isNil } from '@/lib/format';
import { Info } from './Info';

/* ------------------------------------------------------------------ icons */
const ICONS: Record<string, string> = {
  grid: 'M4 4h6v6H4zM14 4h6v6h-6zM4 14h6v6H4zM14 14h6v6h-6z',
  users: 'M9 11a3 3 0 100-6 3 3 0 000 6zM3 20v-1a5 5 0 015-5h2a5 5 0 015 5v1M16 5.2a3 3 0 010 5.6M18 14.5a5 5 0 013 4.5v1',
  repeat: 'M17 2l3 3-3 3M4 11V9a4 4 0 014-4h12M7 22l-3-3 3-3M20 13v2a4 4 0 01-4 4H4',
  activity: 'M3 12h4l3 8 4-16 3 8h4',
  coins: 'M12 6c4.4 0 8-1 8-2.5S16.4 1 12 1 4 2 4 3.5 7.6 6 12 6zM4 3.5v5C4 10 7.6 11 12 11s8-1 8-2.5v-5M4 8.5v5C4 15 7.6 16 12 16s8-1 8-2.5v-5M4 13.5v5C4 20 7.6 21 12 21s8-1 8-2.5v-5',
  funnel: 'M3 4h18l-7 8.5V20l-4-2v-5.5z',
  layers: 'M12 3l9 5-9 5-9-5zM3 13l9 5 9-5M3 17.5l9 5 9-5',
  flask: 'M9 3h6M10 3v6L4.5 19a1.5 1.5 0 001.3 2.2h12.4a1.5 1.5 0 001.3-2.2L14 9V3M7.5 15h9',
  bulb: 'M9 18h6M10 21h4M12 3a6 6 0 00-3.5 10.9c.6.5 1 1.2 1 2V16h5v-.1c0-.8.4-1.5 1-2A6 6 0 0012 3z',
  heat: 'M3 3h7v7H3zM14 3h7v7h-7zM3 14h7v7H3zM14 14h3.5v3.5H14zM20.5 14H21v.5M14 20.5v.5h.5M18 18h3v3h-3z',
  upload: 'M12 16V4M7 9l5-5 5 5M4 20h16',
  search: 'M11 18a7 7 0 100-14 7 7 0 000 14zM21 21l-4.5-4.5',
  globe: 'M12 21a9 9 0 100-18 9 9 0 000 18zM3 12h18M12 3c2.5 2.7 3.8 5.7 3.8 9s-1.3 6.3-3.8 9c-2.5-2.7-3.8-5.7-3.8-9S9.5 5.7 12 3z',
  sun: 'M12 16a4 4 0 100-8 4 4 0 000 8zM12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4',
  moon: 'M21 13.5A8.5 8.5 0 1110.5 3a6.7 6.7 0 0010.5 10.5z',
  menu: 'M4 6h16M4 12h16M4 18h16',
  x: 'M6 6l12 12M18 6L6 18',
  up: 'M12 19V5M5 12l7-7 7 7',
  down: 'M12 5v14M19 12l-7 7-7-7',
  alert: 'M12 9v4M12 17h.01M10.3 3.9L2.4 18a2 2 0 001.7 3h15.8a2 2 0 001.7-3L13.7 3.9a2 2 0 00-3.4 0z',
  check: 'M5 12.5l4.5 4.5L19 7.5',
  info: 'M12 22a10 10 0 100-20 10 10 0 000 20zM12 11v5M12 8h.01',
  filter: 'M3 5h18l-7 8v6l-4-2v-4z',
  chevron: 'M6 9l6 6 6-6',
  arrow: 'M5 12h14M13 6l6 6-6 6',
};

export function Icon({ name, size = 16, className = '' }: { name: keyof typeof ICONS | string; size?: number; className?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.7}
      strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden>
      <path d={ICONS[name] ?? ICONS.info} />
    </svg>
  );
}

/* ------------------------------------------------------------------ states */
export function Skeleton({ className = '' }: { className?: string }) {
  return <div className={`skeleton ${className}`} />;
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  return (
    <div role="alert" className="flex flex-col items-start gap-2 rounded-md border border-bad/40 bg-bad/5 p-4 text-sm">
      <div className="flex items-center gap-2 font-medium text-bad"><Icon name="alert" /> Could not load this data</div>
      <div className="text-ink2">{String((error as Error)?.message ?? error)}. Check that the API is running at /api/health.</div>
      {onRetry && <button onClick={onRetry} className="rounded border border-line px-2 py-1 text-xs hover:bg-panel2">Retry</button>}
    </div>
  );
}

export function EmptyState({ children = 'No data for the selected filters.' }: { children?: ReactNode }) {
  return <div className="flex h-full min-h-[120px] items-center justify-center text-sm text-ink3">{children}</div>;
}

interface PanelProps {
  term?: string;
  title?: ReactNode;
  sub?: ReactNode;
  right?: ReactNode;
  loading?: boolean;
  error?: unknown;
  onRetry?: () => void;
  empty?: boolean;
  minH?: number;
  className?: string;
  children?: ReactNode;
}

export function Panel({ term, title, sub, right, loading, error, onRetry, empty, minH = 0, className = '', children }: PanelProps) {
  return (
    <section className={`rounded-lg border border-line bg-panel p-4 shadow-[var(--shadow)] ${className}`}>
      {(title || right) && (
        <header className="mb-3 flex items-start justify-between gap-3">
          <div className="min-w-0">
            {title && <h3 className="flex items-center gap-1.5 font-display text-[15px] font-semibold tracking-wide text-ink">{title}{term && <Info term={term} />}</h3>}
            {sub && <p className="mt-0.5 text-xs text-ink3">{sub}</p>}
          </div>
          {right}
        </header>
      )}
      <div style={{ minHeight: minH || undefined }}>
        {error ? <ErrorState error={error} onRetry={onRetry} /> : loading ? <Skeleton className="h-full w-full" /> : empty ? <EmptyState /> : children}
      </div>
    </section>
  );
}

/* ------------------------------------------------------------------ badges / callouts */
type Tone = 'neutral' | 'good' | 'bad' | 'warn' | 'accent';
const TONE: Record<Tone, string> = {
  neutral: 'border-line text-ink2 bg-panel2',
  good: 'border-good/40 text-good bg-good/10',
  bad: 'border-bad/40 text-bad bg-bad/10',
  warn: 'border-warn/50 text-warn bg-warn/10',
  accent: 'border-accent/40 text-accent bg-accent/10',
};
export function Badge({ tone = 'neutral', children, icon }: { tone?: Tone; children: ReactNode; icon?: string }) {
  return (
    <span className={`inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-[11px] font-medium ${TONE[tone]}`}>
      {icon && <Icon name={icon} size={11} />}{children}
    </span>
  );
}

export function Callout({ tone = 'accent', title, children, icon = 'info' }: { tone?: Tone; title?: ReactNode; children: ReactNode; icon?: string }) {
  const border = { neutral: 'border-line', good: 'border-good/50', bad: 'border-bad/50', warn: 'border-warn/50', accent: 'border-accent/50' }[tone];
  const text = { neutral: 'text-ink2', good: 'text-good', bad: 'text-bad', warn: 'text-warn', accent: 'text-accent' }[tone];
  return (
    <div className={`flex gap-3 rounded-lg border ${border} bg-panel p-4`}>
      <Icon name={icon} size={18} className={`mt-0.5 shrink-0 ${text}`} />
      <div className="min-w-0 text-sm">
        {title && <div className={`font-display text-[15px] font-semibold ${text}`}>{title}</div>}
        <div className="text-ink2">{children}</div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ KPI */
export interface DeltaInfo { text: string; good: boolean | null; dir: 'up' | 'down' | 'flat' }

/** Build a delta from current/previous values. `kind` decides how the change is expressed. */
export function makeDelta(cur: number | null | undefined, prev: number | null | undefined, kind: 'pp' | 'rel', higherIsBetter = true): DeltaInfo | null {
  if (isNil(cur) || isNil(prev)) return null;
  const diff = cur - prev;
  const flat = Math.abs(kind === 'pp' ? diff * 100 : prev ? diff / prev : 0) < (kind === 'pp' ? 0.05 : 0.0005);
  const dir = flat ? 'flat' : diff > 0 ? 'up' : 'down';
  const text = kind === 'pp'
    ? `${diff >= 0 ? '+' : '−'}${Math.abs(diff * 100).toFixed(1)} pp`
    : prev ? `${diff >= 0 ? '+' : '−'}${Math.abs((diff / prev) * 100).toFixed(1)}%` : '–';
  return { text, dir, good: flat ? null : (diff > 0) === higherIsBetter };
}

export function DeltaChip({ delta, label }: { delta: DeltaInfo | null; label?: string }) {
  if (!delta) return <span className="text-xs text-ink3">no prior period</span>;
  const color = delta.good === null ? 'text-ink3' : delta.good ? 'text-good' : 'text-bad';
  return (
    <span className={`inline-flex items-center gap-1 text-xs font-medium ${color}`}>
      {delta.dir !== 'flat' && <Icon name={delta.dir === 'up' ? 'up' : 'down'} size={12} />}
      <span className="num">{delta.text}</span>
      {label && <span className="font-normal text-ink3">{label}</span>}
    </span>
  );
}

export function KpiCard({ label, value, delta, deltaLabel = 'vs prev', hint, loading, sub, term }: {
  term?: string; label: string; value: ReactNode; delta?: DeltaInfo | null; deltaLabel?: string; hint?: string; loading?: boolean; sub?: ReactNode;
}) {
  return (
    <div className="rounded-lg border border-line bg-panel p-4" title={hint}>
      <div className="eyebrow flex items-center gap-1.5">{label}{term && <Info term={term} />}</div>
      {loading ? (
        <Skeleton className="mt-3 h-8 w-24" />
      ) : (
        <div className="num mt-1.5 text-[26px] font-medium leading-none text-ink">{value}</div>
      )}
      <div className="mt-2 min-h-[16px]">
        {loading ? <Skeleton className="h-3 w-20" /> : delta !== undefined ? <DeltaChip delta={delta} label={deltaLabel} /> : sub ? <span className="text-xs text-ink3">{sub}</span> : null}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ headings */
export function PageHeader({ title, desc, right, eyebrow }: { title: string; desc?: ReactNode; right?: ReactNode; eyebrow?: string }) {
  return (
    <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
      <div>
        {eyebrow && <div className="eyebrow mb-1">{eyebrow}</div>}
        <h1 className="font-display text-2xl font-bold tracking-wide text-ink">{title}</h1>
        {desc && <p className="mt-1 max-w-3xl text-sm text-ink2">{desc}</p>}
      </div>
      {right}
    </div>
  );
}

export function SectionTitle({ children, sub }: { children: ReactNode; sub?: ReactNode }) {
  return (
    <div className="mb-3 mt-8">
      <h2 className="font-display text-lg font-semibold tracking-wide text-ink">{children}</h2>
      {sub && <p className="text-sm text-ink3">{sub}</p>}
    </div>
  );
}

export function Grid({ cols = 2, children, className = '' }: { cols?: 1 | 2 | 3 | 4 | 6; children: ReactNode; className?: string }) {
  const c = {
    1: 'grid-cols-1',
    2: 'grid-cols-1 xl:grid-cols-2',
    3: 'grid-cols-1 md:grid-cols-2 xl:grid-cols-3',
    4: 'grid-cols-2 xl:grid-cols-4',
    6: 'grid-cols-2 md:grid-cols-3 xl:grid-cols-6',
  }[cols];
  return <div className={`grid gap-4 ${c} ${className}`}>{children}</div>;
}

/* ------------------------------------------------------------------ table */
export interface Column<T> {
  key: string;
  label: string;
  align?: 'left' | 'right';
  render?: (row: T) => ReactNode;
  sortValue?: (row: T) => number | string | null | undefined;
  hint?: string;
}

export function DataTable<T extends Record<string, any>>({ columns, rows, defaultSort, onRowClick, dense, maxHeight }: {
  columns: Column<T>[]; rows: T[]; defaultSort?: { key: string; desc?: boolean }; onRowClick?: (row: T) => void; dense?: boolean; maxHeight?: number;
}) {
  const [sort, setSort] = useState(defaultSort ?? null);
  const sorted = useMemo(() => {
    if (!sort) return rows;
    const col = columns.find((c) => c.key === sort.key);
    const val = (r: T) => (col?.sortValue ? col.sortValue(r) : r[sort.key]);
    return [...rows].sort((a, b) => {
      const x = val(a), y = val(b);
      if (isNil(x) && isNil(y)) return 0;
      if (isNil(x)) return 1;
      if (isNil(y)) return -1;
      const r = typeof x === 'number' && typeof y === 'number' ? x - y : String(x).localeCompare(String(y));
      return sort.desc ? -r : r;
    });
  }, [rows, sort, columns]);

  return (
    <div className="overflow-auto" style={{ maxHeight }}>
      <table className="data" style={dense ? { fontSize: 13 } : undefined}>
        <thead>
          <tr>
            {columns.map((c) => (
              <th key={c.key} title={c.hint} className={`${c.align === 'right' ? 'n' : ''} sortable`}
                onClick={() => setSort((s) => (s?.key === c.key ? { key: c.key, desc: !s.desc } : { key: c.key, desc: true }))}
                aria-sort={sort?.key === c.key ? (sort.desc ? 'descending' : 'ascending') : 'none'}>
                {c.label}{sort?.key === c.key ? (sort.desc ? ' ↓' : ' ↑') : ''}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sorted.map((r, i) => (
            <tr key={i} onClick={onRowClick ? () => onRowClick(r) : undefined} className={onRowClick ? 'cursor-pointer' : ''}>
              {columns.map((c) => (
                <td key={c.key} className={c.align === 'right' ? 'n num' : ''}>{c.render ? c.render(r) : r[c.key]}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function Swatch({ color }: { color: string }) {
  return <span className="mr-2 inline-block h-2.5 w-2.5 rounded-sm align-middle" style={{ background: color }} />;
}

export function Pill({ options, value, onChange, label }: { options: { value: string; label: string }[]; value: string; onChange: (v: string) => void; label?: string }) {
  return (
    <div role="tablist" aria-label={label} className="inline-flex rounded-md border border-line bg-panel2 p-0.5">
      {options.map((o) => (
        <button key={o.value} role="tab" aria-selected={o.value === value} onClick={() => onChange(o.value)}
          className={`rounded px-2.5 py-1 text-xs font-medium transition-colors ${o.value === value ? 'bg-panel text-ink shadow-sm' : 'text-ink3 hover:text-ink'}`}>
          {o.label}
        </button>
      ))}
    </div>
  );
}
