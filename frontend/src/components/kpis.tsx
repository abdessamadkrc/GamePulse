'use client';
import { useApi, Row } from '@/lib/api';
import { Callout, Grid, KpiCard, makeDelta } from './ui';
import { TERM_BY_KEY } from '@/lib/glossary';
import { fmtCompact, fmtInt, fmtNum, fmtPct, fmtUsd, fmtMin } from '@/lib/format';

export interface KpiSpec {
  label: string;
  key: string;
  fmt: 'int' | 'pct' | 'usd' | 'usd0' | 'num' | 'compact$' | 'min' | 'compact';
  delta?: 'pp' | 'rel' | 'none';
  higherIsBetter?: boolean;
  hint?: string;
  term?: string;
}

const FMT: Record<KpiSpec['fmt'], (v: number | null | undefined) => string> = {
  int: fmtInt, pct: fmtPct, usd: fmtUsd, usd0: (v) => fmtUsd(v, 0), num: (v) => fmtNum(v, 1),
  'compact$': (v) => `$${fmtCompact(v)}`, min: fmtMin, compact: fmtCompact,
};

export function KpiGrid({ items, cols = 6 }: { items: KpiSpec[]; cols?: 3 | 4 | 6 }) {
  const { data, isLoading, error } = useApi<{ current: Row; previous: Row | null }>('/api/kpis');
  if (error) return <Callout tone="bad" icon="alert" title="KPIs unavailable">{String((error as Error).message)}</Callout>;
  const c = data?.current, p = data?.previous;
  return (
    <Grid cols={cols === 3 ? 3 : cols === 4 ? 4 : 6}>
      {items.map((k) => (
        <KpiCard key={k.key + k.label} label={k.label} loading={isLoading} hint={k.hint} term={k.term ?? TERM_BY_KEY[k.key]}
          value={FMT[k.fmt](c?.[k.key])}
          delta={k.delta === 'none' ? undefined : makeDelta(c?.[k.key], p?.[k.key], k.delta ?? 'rel', k.higherIsBetter ?? true)}
          deltaLabel="vs prev" />
      ))}
    </Grid>
  );
}
