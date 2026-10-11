'use client';
import Link from 'next/link';
import { useState } from 'react';
import { useApi, Row } from '@/lib/api';
import { BarsH } from '@/components/charts';
import { BreakdownBars, CohortPanel, DauTrendPanel, RetentionTrendPanel, SegmentDistPanel, useBreakdown } from '@/components/panels';
import { FocusTabs } from '@/components/FocusTabs';
import { KpiGrid } from '@/components/kpis';
import { Callout, PageHeader, Panel, Pill } from '@/components/ui';
import { fmtNum, fmtPct, fmtPp } from '@/lib/format';
import { PLATFORM_COLOR, SOURCE_COLOR } from '@/lib/colors';

function IncidentBanner() {
  const { data } = useApi<{ current: Row; previous: Row | null }>('/api/kpis');
  const d = data?.current?.d7, p = data?.previous?.d7;
  if (d == null || p == null || d - p > -0.02) return null;
  return (
    <div className="mb-4">
      <Callout tone="bad" icon="alert" title={`D7 retention moved ${fmtPct(p)} → ${fmtPct(d)} (${fmtPp(d - p)})`}>
        This is bigger than normal week-to-week noise. <Link href="/investigation" className="font-medium text-accent underline underline-offset-2">Find out why</Link>, or read the <Link href="/insights" className="font-medium text-accent underline underline-offset-2">recommended next steps</Link>.
      </Callout>
    </div>
  );
}

function PlatformView() {
  const { data, error, isLoading, mutate } = useBreakdown('platform');
  const rows = data?.rows ?? [];
  const [m, setM] = useState('sessions_per_player');
  const opts = [
    { value: 'sessions_per_player', label: 'Sessions per player', d: 1 },
    { value: 'minutes_per_player', label: 'Minutes per player', d: 0 },
    { value: 'matches_per_player', label: 'Matches per player', d: 1 },
  ];
  const cur = opts.find((o) => o.value === m)!;
  return (
    <Panel title="Engagement by platform" sub="Per active player in the selected dates"
      right={<Pill label="Measure" value={m} onChange={setM} options={opts.map((o) => ({ value: o.value, label: o.label }))} />}
      loading={isLoading} error={error} onRetry={() => mutate()} empty={!rows.length}>
      <BarsH data={rows.map((r) => ({ name: r.dim, value: r[m], color: PLATFORM_COLOR[r.dim] }))} fmt={(v) => fmtNum(v, cur.d)} rowHeight={48} labelWidth={72} />
    </Panel>
  );
}

function CountryView() {
  const [m, setM] = useState('d7');
  const o = {
    d7: { label: 'D7 retention', unit: 'pct', digits: 1, min: 50 },
    revenue: { label: 'Revenue', unit: 'usd', digits: 0, min: 0 },
    new_players: { label: 'New players', unit: 'int', digits: 0, min: 0 },
  } as const;
  const c = o[m as keyof typeof o];
  return (
    <BreakdownBars key={m} title={`${c.label} by country`} dim="country" metric={m} unit={c.unit} digits={c.digits} minPlayers={c.min}
      right={<Pill label="Measure" value={m} onChange={setM} options={Object.entries(o).map(([value, v]) => ({ value, label: v.label }))} />} />
  );
}

export default function Overview() {
  return (
    <>
      <PageHeader eyebrow="Live game health" title="Overview"
        desc="A quick health check: are players showing up, coming back and spending? Pick one question below to look closer." />
      <IncidentBanner />
      <KpiGrid items={[
        { label: 'DAU', key: 'dau', fmt: 'int' },
        { label: 'MAU', key: 'mau', fmt: 'int' },
        { label: 'D7 retention', key: 'd7', fmt: 'pct', delta: 'pp' },
        { label: 'ARPU', key: 'arpu', fmt: 'usd' },
        { label: 'Conversion', key: 'conversion', fmt: 'pct', delta: 'pp' },
        { label: 'Revenue', key: 'revenue', fmt: 'compact$' },
      ]} />
      <p className="mt-3 text-xs text-ink3">
        Not sure where to start? <Link href="/investigation" className="text-accent hover:underline">Why did a number drop?</Link> ·{' '}
        <Link href="/explorer" className="text-accent hover:underline">Who leaves, and when?</Link> ·{' '}
        <Link href="/insights" className="text-accent hover:underline">What should I do next?</Link> ·{' '}
        <Link href="/experiments" className="text-accent hover:underline">Should we ship this change?</Link>
      </p>

      <div className="mt-6">
        <FocusTabs tabs={[
          { id: 'players', label: 'Daily players', question: 'How many people play each day?', render: () => <DauTrendPanel /> },
          { id: 'retention', label: 'Retention', question: 'Are new players coming back?', render: () => <RetentionTrendPanel /> },
          { id: 'cohorts', label: 'Weekly groups', question: 'How does each weekly group of new players fade over time?', render: () => <CohortPanel /> },
          { id: 'sources', label: 'Where from', question: 'Where do new players come from?', render: () => <BreakdownBars title="New players by source" sub="Installs in the selected dates" dim="source" metric="new_players" unit="int" colors={SOURCE_COLOR} /> },
          { id: 'countries', label: 'Countries', question: 'How do countries compare?', render: () => <CountryView /> },
          { id: 'platform', label: 'Platforms', question: 'Do Android and iOS players behave differently?', render: () => <PlatformView /> },
          { id: 'groups', label: 'Player groups', question: 'Who are our players today?', render: () => <SegmentDistPanel title="Players by group" /> },
        ]} />
      </div>
    </>
  );
}
