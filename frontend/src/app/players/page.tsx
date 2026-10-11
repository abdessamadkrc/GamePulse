'use client';
import { useApi, Row } from '@/lib/api';
import { BarsH, LineChartX } from '@/components/charts';
import { FocusTabs } from '@/components/FocusTabs';
import { KpiGrid } from '@/components/kpis';
import { GroupByBars, SegmentDistPanel, useBreakdown } from '@/components/panels';
import { DataTable, PageHeader, Panel } from '@/components/ui';
import { fmtInt, fmtPct } from '@/lib/format';
import { PLATFORM_COLOR, SERIES, SOURCE_COLOR, TIER_COLOR } from '@/lib/colors';

function NewPlayersTrend() {
  const { data, error, isLoading, mutate } = useApi<{ range: any; rows: Row[] }>('/api/trends/daily');
  return (
    <Panel title="New players per day" sub="Installs by install date. Shaded area = selected dates." loading={isLoading} error={error} onRetry={() => mutate()} empty={!data?.rows.length}>
      <LineChartX data={data?.rows ?? []} series={[{ key: 'new_players', name: 'New players', color: SERIES[0] }]} fmt={fmtInt} height={300}
        shade={data ? { from: data.range.from, to: data.range.to } : undefined} />
    </Panel>
  );
}

function ChurnPanel() {
  const { data, error, isLoading, mutate } = useApi<{ by_tier: Row[] }>('/api/churn');
  const bars = (data?.by_tier ?? []).map((r) => ({ name: r.tier, value: r.churn_rate }));
  return (
    <Panel title="Share of players who left, by how engaged they were" sub="Players active in the previous 30 days who did not return in the latest 30."
      term="Churn" loading={isLoading} error={error} onRetry={() => mutate()} empty={!bars.length}>
      <BarsH data={bars} fmt={(v) => fmtPct(v, 1)} color="var(--s2)" labelWidth={90} rowHeight={44} />
      <p className="mt-3 text-xs text-ink3">High-Value = spent $5+ in the earlier 30 days; Engaged = played on 8+ days; Casual = everyone else.</p>
    </Panel>
  );
}

function CountryTable() {
  const { data, error, isLoading, mutate } = useBreakdown('country');
  return (
    <Panel title="Players by country" loading={isLoading} error={error} onRetry={() => mutate()} empty={!data?.rows.length}>
      <DataTable dense defaultSort={{ key: 'new_players', desc: true }} rows={data?.rows ?? []} columns={[
        { key: 'dim', label: 'Country' },
        { key: 'new_players', label: 'New players', align: 'right', render: (r) => fmtInt(r.new_players) },
        { key: 'share_of_new', label: 'Share', align: 'right', render: (r) => fmtPct(r.share_of_new) },
        { key: 'players_total', label: 'All-time players', align: 'right', render: (r) => fmtInt(r.players_total) },
        { key: 'active_players', label: 'Active', align: 'right', render: (r) => fmtInt(r.active_players) },
        { key: 'd1', label: 'D1', align: 'right', render: (r) => fmtPct(r.d1) },
        { key: 'd7', label: 'D7', align: 'right', render: (r) => fmtPct(r.d7) },
        { key: 'tutorial_rate', label: 'Finished tutorial', align: 'right', render: (r) => fmtPct(r.tutorial_rate) },
      ]} />
    </Panel>
  );
}

export default function PlayersPage() {
  return (
    <>
      <PageHeader eyebrow="Who is playing" title="Players" desc="How many players you have, who they are, and who has left or come back." />
      <KpiGrid cols={4} items={[
        { label: 'New players', key: 'new_players', fmt: 'int', hint: 'Installs inside the selected dates' },
        { label: 'Active players', key: 'active_players', fmt: 'int', hint: 'Different players with a session in the dates' },
        { label: 'Returning players', key: 'returning_players', fmt: 'int', hint: 'Back in the last 30 days after a break of 14+ days' },
        { label: 'Churn rate', key: 'churn_rate', fmt: 'pct', delta: 'pp', higherIsBetter: false, hint: 'Installed 30+ days ago and last played 30+ days ago' },
      ]} />
      <div className="mt-6">
        <FocusTabs tabs={[
          { id: 'new', label: 'New players', question: 'How many new players arrive each day?', render: () => <NewPlayersTrend /> },
          { id: 'who', label: 'Who they are', question: 'Who are our new players?', render: () => (
            <GroupByBars title="New players" sub="Installs in the selected dates" metric="new_players" unit="int" dims={[
              { value: 'country', label: 'Country' }, { value: 'platform', label: 'Platform', colors: PLATFORM_COLOR },
              { value: 'source', label: 'Source', colors: SOURCE_COLOR }, { value: 'device_tier', label: 'Device quality', colors: TIER_COLOR },
            ]} />) },
          { id: 'leaving', label: 'Who leaves', question: 'Which kind of player is most likely to leave?', render: () => <ChurnPanel /> },
          { id: 'groups', label: 'Player groups', question: 'How are players split into groups today?', render: () => <SegmentDistPanel title="Players by group" /> },
          { id: 'countries', label: 'Country table', question: 'How does each country look in detail?', render: () => <CountryTable /> },
        ]} />
      </div>
    </>
  );
}
