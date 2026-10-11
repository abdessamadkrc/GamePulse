'use client';
import { useState } from 'react';
import { FocusTabs } from '@/components/FocusTabs';
import { KpiGrid } from '@/components/kpis';
import { CohortPanel, GroupByBars, RetentionTrendPanel, useBreakdown } from '@/components/panels';
import { DataTable, PageHeader, Panel, Pill } from '@/components/ui';
import { fmtInt, fmtPct } from '@/lib/format';
import { MODE_COLOR, PLATFORM_COLOR, SOURCE_COLOR } from '@/lib/colors';

const DIMS = [
  { value: 'country', label: 'Country' },
  { value: 'platform', label: 'Platform' },
  { value: 'source', label: 'Source' },
  { value: 'first_game_mode', label: 'First game mode' },
];

function RetentionTable() {
  const [dim, setDim] = useState('country');
  const { data, error, isLoading, mutate } = useBreakdown(dim);
  const label = DIMS.find((d) => d.value === dim)!.label;
  return (
    <Panel title={`Exact numbers by ${label.toLowerCase()}`} sub="Only players old enough for each day are counted"
      right={<Pill label="Group by" value={dim} onChange={setDim} options={DIMS} />}
      loading={isLoading} error={error} onRetry={() => mutate()} empty={!data?.rows.length}>
      <DataTable dense defaultSort={{ key: 'd7', desc: true }} rows={data?.rows ?? []} columns={[
        { key: 'dim', label },
        { key: 'new_players', label: 'New players', align: 'right', render: (r) => fmtInt(r.new_players) },
        { key: 'd1', label: 'D1', align: 'right', render: (r) => fmtPct(r.d1) },
        { key: 'd7', label: 'D7', align: 'right', render: (r) => fmtPct(r.d7) },
        { key: 'd30', label: 'D30', align: 'right', render: (r) => fmtPct(r.d30) },
        { key: 'early_churn_rate', label: 'Gone in week 2', align: 'right', hint: 'No session on days 8-14 after install', render: (r) => fmtPct(r.early_churn_rate) },
      ]} />
    </Panel>
  );
}

export default function RetentionPage() {
  const [m, setM] = useState<'d1' | 'd7' | 'd30'>('d7');
  const label = m.toUpperCase();
  const toggle = <Pill label="Retention measure" value={m} onChange={(v) => setM(v as 'd1' | 'd7' | 'd30')}
    options={[{ value: 'd1', label: 'D1 (next day)' }, { value: 'd7', label: 'D7 (one week)' }, { value: 'd30', label: 'D30 (one month)' }]} />;
  return (
    <>
      <PageHeader eyebrow="Do players come back?" title="Retention"
        desc="Do new players come back? Retention is the share of a group of new players who play again after 1, 7 or 30 days: the best early sign of a healthy game." />
      <KpiGrid cols={4} items={[
        { label: 'D1 retention', key: 'd1', fmt: 'pct', delta: 'pp' },
        { label: 'D7 retention', key: 'd7', fmt: 'pct', delta: 'pp' },
        { label: 'D30 retention', key: 'd30', fmt: 'pct', delta: 'pp', hint: 'Needs 30 days of elapsed time; blank for very recent dates' },
        { label: 'Gone in week 2', key: 'early_churn_rate', fmt: 'pct', delta: 'pp', higherIsBetter: false, hint: 'New players with no session on days 8-14' },
      ]} />
      <div className="mt-6">
        <FocusTabs aside={undefined} tabs={[
          { id: 'trend', label: 'Over time', question: 'Is retention getting better or worse?', render: () => <RetentionTrendPanel height={320} /> },
          { id: 'weekly', label: 'Weekly groups', question: 'How does each weekly group of new players fade over time?', render: () => <CohortPanel /> },
          { id: 'groups', label: 'Which groups', question: `Which kinds of players have the best ${label} retention?`, render: () => (
            <div className="space-y-3">
              <div className="flex items-center gap-2 text-xs text-ink2"><span className="eyebrow">Measure</span>{toggle}</div>
              <GroupByBars key={m} title={`${label} retention`} metric={m} unit="pct" minPlayers={50} dims={[
                { value: 'country', label: 'Country' }, { value: 'platform', label: 'Platform', colors: PLATFORM_COLOR },
                { value: 'source', label: 'Source', colors: SOURCE_COLOR }, { value: 'first_game_mode', label: 'First game mode', colors: MODE_COLOR },
              ]} />
            </div>) },
          { id: 'numbers', label: 'Exact numbers', question: 'What are the exact numbers?', render: () => <RetentionTable /> },
        ]} />
      </div>
    </>
  );
}
