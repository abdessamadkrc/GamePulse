'use client';
import { useState } from 'react';
import { useApi, Row } from '@/lib/api';
import { BarsV } from '@/components/charts';
import { FocusTabs } from '@/components/FocusTabs';
import { KpiGrid } from '@/components/kpis';
import { BreakdownBars, GroupByBars, useBreakdown } from '@/components/panels';
import { Callout, DataTable, PageHeader, Panel, Pill, Swatch } from '@/components/ui';
import { fmtDate, fmtInt, fmtPct, fmtUsd } from '@/lib/format';
import { PLATFORM_COLOR, SOURCE_COLOR } from '@/lib/colors';

function WeeklyInstalls() {
  const { data, error, isLoading, mutate } = useApi<{ rows: Row[]; sources: string[] }>('/api/acquisition/weekly');
  return (
    <Panel title="New players per week, by source" sub="Full history. Watch the mix shift, not only the total." loading={isLoading} error={error} onRetry={() => mutate()} empty={!data?.rows.length}>
      <BarsV data={data?.rows ?? []} xKey="week" stacked height={320} fmt={fmtInt} xFmt={fmtDate}
        bars={(data?.sources ?? []).map((s) => ({ key: s, name: s, color: SOURCE_COLOR[s] }))} />
    </Panel>
  );
}

function SourceQuality() {
  const [m, setM] = useState('d7');
  const o = {
    d7: { label: 'Come back after a week (D7)', unit: 'pct', sort: 'desc' as const },
    tutorial_rate: { label: 'Finish the tutorial', unit: 'pct', sort: 'desc' as const },
    early_churn_rate: { label: 'Gone in week 2 (lower is better)', unit: 'pct', sort: 'asc' as const },
  };
  const c = o[m as keyof typeof o];
  return (
    <BreakdownBars key={m} title="Share of new players who…" sub={c.label} dim="source" metric={m} unit={c.unit} colors={SOURCE_COLOR} sort={c.sort}
      right={<Pill label="Measure" value={m} onChange={setM} options={Object.entries(o).map(([value, v]) => ({ value, label: v.label.split(' (')[0] }))} />} />
  );
}

function SourceTable() {
  const { data, error, isLoading, mutate } = useBreakdown('source');
  const rows = data?.rows ?? [];
  const wd7 = rows.reduce((a, r) => a + (r.d7 ?? 0) * (r.new_players ?? 0), 0) / Math.max(rows.reduce((a, r) => a + (r.new_players ?? 0), 0), 1);
  return (
    <Panel title="Source scorecard" sub="Quality index = the source's D7 divided by the overall D7 (100 = average)" loading={isLoading} error={error} onRetry={() => mutate()} empty={!rows.length}>
      <DataTable dense defaultSort={{ key: 'new_players', desc: true }} rows={rows.map((r): Row => ({ ...r, quality: r.d7 != null && wd7 ? (r.d7 / wd7) * 100 : null }))} columns={[
        { key: 'dim', label: 'Source', render: (r) => <span><Swatch color={SOURCE_COLOR[r.dim]} />{r.dim}</span> },
        { key: 'new_players', label: 'New players', align: 'right', render: (r) => fmtInt(r.new_players) },
        { key: 'tutorial_rate', label: 'Finished tutorial', align: 'right', render: (r) => fmtPct(r.tutorial_rate) },
        { key: 'd1', label: 'D1', align: 'right', render: (r) => fmtPct(r.d1) },
        { key: 'd7', label: 'D7', align: 'right', render: (r) => fmtPct(r.d7) },
        { key: 'd30', label: 'D30', align: 'right', render: (r) => fmtPct(r.d30) },
        { key: 'payer_rate_14d', label: 'Paid in 14 days', align: 'right', render: (r) => fmtPct(r.payer_rate_14d) },
        { key: 'ltv14', label: '14-day revenue / player', align: 'right', render: (r) => fmtUsd(r.ltv14) },
        { key: 'quality', label: 'Quality index', align: 'right', render: (r) => (r.quality == null ? '–' : Math.round(r.quality)) },
      ]} />
    </Panel>
  );
}

export default function AcquisitionPage() {
  return (
    <>
      <PageHeader eyebrow="Where do players come from?" title="Acquisition"
        desc="Where new players come from, and whether each source brings players who stay, not just installs." />
      <KpiGrid cols={4} items={[
        { label: 'New players', key: 'new_players', fmt: 'int' },
        { label: 'D1 retention', key: 'd1', fmt: 'pct', delta: 'pp' },
        { label: 'D7 retention', key: 'd7', fmt: 'pct', delta: 'pp' },
        { label: 'Gone in week 2', key: 'early_churn_rate', fmt: 'pct', delta: 'pp', higherIsBetter: false },
      ]} />
      <div className="mt-6">
        <FocusTabs tabs={[
          { id: 'volume', label: 'Over time', question: 'How many new players arrive, and from where?', render: () => <WeeklyInstalls /> },
          { id: 'quality', label: 'Quality', question: 'Which sources bring players who stay?', render: () => <SourceQuality /> },
          { id: 'table', label: 'Scorecard', question: 'How does each source score overall?', render: () => <SourceTable /> },
          { id: 'mix', label: 'Mix', question: 'What do our new players look like?', render: () => (
            <GroupByBars title="New players" metric="new_players" unit="int" dims={[
              { value: 'country', label: 'Country' }, { value: 'platform', label: 'Platform', colors: PLATFORM_COLOR }, { value: 'source', label: 'Source', colors: SOURCE_COLOR }]} />) },
        ]} />
        <div className="mt-6">
          <Callout tone="warn" icon="info" title="There is no ad-spend data here">
            Cost per install and return on ad spend are deliberately not shown, because inventing cost numbers would be fabricating evidence. For a real game, join campaign spend and rank sources by cost per player who is still playing after a week.
          </Callout>
        </div>
      </div>
    </>
  );
}
