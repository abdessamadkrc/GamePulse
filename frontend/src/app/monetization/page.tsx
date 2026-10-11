'use client';
import { useMemo } from 'react';
import { useApi, Row } from '@/lib/api';
import { BarsH, BarsV, LineChartX } from '@/components/charts';
import { FocusTabs } from '@/components/FocusTabs';
import { KpiGrid } from '@/components/kpis';
import { GroupByBars } from '@/components/panels';
import { DataTable, PageHeader, Panel } from '@/components/ui';
import { fmtInt, fmtPct, fmtUsd } from '@/lib/format';
import { SERIES, SOURCE_COLOR } from '@/lib/colors';

type Summary = { items: Row[]; concentration: { payers: number; top_shares: Row[]; buckets: Row[] } };

function RevenueTrend() {
  const { data, error, isLoading, mutate } = useApi<{ range: any; rows: Row[] }>('/api/trends/daily');
  const rows = useMemo(() => {
    const r = data?.rows ?? [];
    return r.map((d, i) => {
      const w = r.slice(Math.max(0, i - 6), i + 1);
      return { ...d, revenue_7d: w.reduce((a, x) => a + x.revenue, 0) / w.length };
    });
  }, [data]);
  return (
    <Panel title="Daily revenue" sub="Revenue per day. Shaded area = selected dates." loading={isLoading} error={error} onRetry={() => mutate()} empty={!rows.length}>
      <LineChartX data={rows} height={300} fmt={(v) => fmtUsd(v, 0)}
        series={[{ key: 'revenue', name: 'Revenue', color: SERIES[2], width: 1.5, muted: true }, { key: 'revenue_7d', name: 'Revenue (7-day average)', color: SERIES[2], width: 2.5 }]}
        shade={data ? { from: data.range.from, to: data.range.to } : undefined} />
    </Panel>
  );
}

function ItemsPanel() {
  const { data, error, isLoading, mutate } = useApi<Summary>('/api/monetization/summary');
  const items = (data?.items ?? []).map((r, i) => ({ name: String(r.item_type).replace('_', ' '), value: r.revenue, color: SERIES[i % 8] }));
  return (
    <Panel title="Revenue by item type" loading={isLoading} error={error} onRetry={() => mutate()} empty={!items.length}>
      <BarsH data={items} fmt={(v) => fmtUsd(v, 0)} labelWidth={110} rowHeight={38} />
    </Panel>
  );
}

function ConcentrationPanel() {
  const { data, error, isLoading, mutate } = useApi<Summary>('/api/monetization/summary');
  const conc = (data?.concentration.top_shares ?? []).map((r) => ({ name: `Top ${r.top_pct_of_payers}% of payers`, value: r.share_of_revenue }));
  return (
    <Panel title="Share of revenue from the biggest spenders" sub={`${fmtInt(data?.concentration.payers)} paying players in the selected dates`}
      loading={isLoading} error={error} onRetry={() => mutate()} empty={!conc.length}>
      <BarsH data={conc} fmt={(v) => fmtPct(v, 0)} labelWidth={140} rowHeight={40} color="var(--s4)" />
      <p className="mt-2 text-xs text-ink3">When a few players carry the revenue, protect them before optimising the average.</p>
    </Panel>
  );
}

function BucketsPanel() {
  const { data, error, isLoading, mutate } = useApi<Summary>('/api/monetization/summary');
  const buckets = data?.concentration.buckets ?? [];
  return (
    <Panel title="Paying players by total spend" loading={isLoading} error={error} onRetry={() => mutate()} empty={!buckets.length}>
      <BarsV data={buckets} xKey="bucket" height={260} fmt={fmtInt} bars={[{ key: 'payers', name: 'Paying players', color: SERIES[0] }]} />
    </Panel>
  );
}

function CountryTable() {
  const { data, error, isLoading, mutate } = useApi<{ rows: Row[] }>('/api/breakdown', { params: { dim: 'country' } });
  return (
    <Panel title="Money by country" loading={isLoading} error={error} onRetry={() => mutate()} empty={!data?.rows.length}>
      <DataTable dense defaultSort={{ key: 'revenue', desc: true }} rows={data?.rows ?? []} columns={[
        { key: 'dim', label: 'Country' },
        { key: 'active_players', label: 'Active', align: 'right', render: (r) => fmtInt(r.active_players) },
        { key: 'payers', label: 'Payers', align: 'right', render: (r) => fmtInt(r.payers) },
        { key: 'conversion', label: 'Conversion', align: 'right', render: (r) => fmtPct(r.conversion) },
        { key: 'revenue', label: 'Revenue', align: 'right', render: (r) => fmtUsd(r.revenue, 0) },
        { key: 'arpu', label: 'ARPU', align: 'right', render: (r) => fmtUsd(r.arpu) },
        { key: 'arppu', label: 'ARPPU', align: 'right', render: (r) => fmtUsd(r.arppu) },
      ]} />
    </Panel>
  );
}

export default function MonetizationPage() {
  return (
    <>
      <PageHeader eyebrow="Does the game earn?" title="Monetization" desc="How much money the game makes and who pays." />
      <KpiGrid cols={4} items={[
        { label: 'Revenue', key: 'revenue', fmt: 'compact$' },
        { label: 'ARPU', key: 'arpu', fmt: 'usd', hint: 'Revenue divided by all active players' },
        { label: 'Paying players', key: 'payers', fmt: 'int' },
        { label: 'Conversion', key: 'conversion', fmt: 'pct', delta: 'pp', hint: 'Share of active players who paid' },
      ]} />
      <div className="mt-6">
        <FocusTabs tabs={[
          { id: 'time', label: 'Over time', question: 'Is revenue growing?', render: () => <RevenueTrend /> },
          { id: 'buy', label: 'What they buy', question: 'What do players spend money on?', render: () => <ItemsPanel /> },
          { id: 'who', label: 'Who pays', question: 'How much of the revenue comes from a few players?', render: () => <ConcentrationPanel /> },
          { id: 'spend', label: 'Spend per payer', question: 'How much does a typical paying player spend?', render: () => <BucketsPanel /> },
          { id: 'where', label: 'Where from', question: 'Where does the revenue come from?', render: () => (
            <GroupByBars title="Revenue" metric="revenue" unit="usd" digits={0} dims={[
              { value: 'country', label: 'Country' }, { value: 'source', label: 'Source', colors: SOURCE_COLOR }, { value: 'platform', label: 'Platform' }]} />) },
          { id: 'table', label: 'Country table', question: 'How does each country compare in detail?', render: () => <CountryTable /> },
        ]} />
      </div>
    </>
  );
}
