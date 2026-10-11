'use client';
import { useApi, Row } from '@/lib/api';
import { LineChartX } from '@/components/charts';
import { FocusTabs } from '@/components/FocusTabs';
import { KpiGrid } from '@/components/kpis';
import { DauTrendPanel, GroupByBars, useBreakdown } from '@/components/panels';
import { DataTable, PageHeader, Panel, Swatch } from '@/components/ui';
import { fmtInt, fmtMin, fmtNum, fmtPct } from '@/lib/format';
import { MODE_COLOR, PLATFORM_COLOR, SERIES, TIER_COLOR } from '@/lib/colors';

function TrendPanel({ title, sub, k, name, fmt, color = SERIES[0], pct }: { title: string; sub: string; k: string; name: string; fmt: (v: number | null | undefined) => string; color?: string; pct?: boolean }) {
  const { data, error, isLoading, mutate } = useApi<{ range: any; rows: Row[] }>('/api/trends/daily');
  return (
    <Panel title={title} sub={sub} loading={isLoading} error={error} onRetry={() => mutate()} empty={!data?.rows.length}>
      <LineChartX data={data?.rows ?? []} series={[{ key: k, name, color }]} fmt={fmt} height={300} yDomain={pct ? [0, 'auto'] : ['auto', 'auto']}
        shade={data ? { from: data.range.from, to: data.range.to } : undefined} />
    </Panel>
  );
}

function ModesPanel() {
  const { data, error, isLoading, mutate } = useApi<{ rows: Row[] }>('/api/engagement/modes');
  const rows = data?.rows ?? [];
  const total = rows.reduce((a, r) => a + r.matches, 0);
  return (
    <Panel title="Game modes" sub="Matches played in the selected dates" loading={isLoading} error={error} onRetry={() => mutate()} empty={!rows.length}>
      <DataTable dense rows={rows} columns={[
        { key: 'game_mode', label: 'Mode', render: (r) => <span><Swatch color={MODE_COLOR[r.game_mode]} />{r.game_mode}</span> },
        { key: 'players', label: 'Players', align: 'right', render: (r) => fmtInt(r.players) },
        { key: 'matches', label: 'Matches', align: 'right', render: (r) => fmtInt(r.matches) },
        { key: 'share', label: 'Share', align: 'right', sortValue: (r) => r.matches, render: (r) => fmtPct(r.matches / total) },
        { key: 'avg_match_minutes', label: 'Avg match', align: 'right', render: (r) => fmtMin(r.avg_match_minutes) },
        { key: 'win_rate', label: 'Win rate', align: 'right', hint: 'A win is finishing first', render: (r) => fmtPct(r.win_rate) },
        { key: 'kills_per_match', label: 'Kills / match', align: 'right', render: (r) => fmtNum(r.kills_per_match, 2) },
      ]} />
    </Panel>
  );
}

function DevicesPanel() {
  const p = useBreakdown('platform');
  const t = useBreakdown('device_tier');
  const rows: Row[] = [...(p.data?.rows ?? []), ...(t.data?.rows ?? []).map((r): Row => ({ ...r, dim: `${r.dim}-end devices` }))];
  return (
    <Panel title="Engagement by platform and device quality" sub="Per active player in the selected dates" loading={p.isLoading || t.isLoading} error={p.error || t.error}>
      <DataTable dense rows={rows} columns={[
        { key: 'dim', label: 'Group' },
        { key: 'active_players', label: 'Active', align: 'right', render: (r) => fmtInt(r.active_players) },
        { key: 'sessions_per_player', label: 'Sessions', align: 'right', render: (r) => fmtNum(r.sessions_per_player) },
        { key: 'matches_per_player', label: 'Matches', align: 'right', render: (r) => fmtNum(r.matches_per_player) },
        { key: 'avg_session_minutes', label: 'Avg session', align: 'right', render: (r) => fmtMin(r.avg_session_minutes) },
        { key: 'minutes_per_player', label: 'Minutes', align: 'right', render: (r) => fmtNum(r.minutes_per_player, 0) },
      ]} />
    </Panel>
  );
}

export default function EngagementPage() {
  return (
    <>
      <PageHeader eyebrow="How deeply do they play?" title="Engagement"
        desc="How often and for how long people play. DAU/MAU shows whether the game has become a daily habit." />
      <KpiGrid cols={4} items={[
        { label: 'DAU', key: 'dau', fmt: 'int' },
        { label: 'DAU / MAU', key: 'dau_mau', fmt: 'pct', delta: 'pp', hint: 'Share of monthly players who play on a typical day' },
        { label: 'Sessions / player', key: 'sessions_per_player', fmt: 'num' },
        { label: 'Avg session', key: 'avg_session_minutes', fmt: 'min' },
      ]} />
      <div className="mt-6">
        <FocusTabs tabs={[
          { id: 'daily', label: 'Daily players', question: 'How many people play each day?', render: () => <DauTrendPanel height={320} /> },
          { id: 'habit', label: 'Daily habit', question: 'Is the game becoming a daily habit?', render: () => <TrendPanel title="DAU / MAU" sub="Share of the last 30 days' players who play on a typical day (starts after 30 days of history)" k="dau_mau" name="DAU / MAU" fmt={(v) => fmtPct(v, 0)} color={SERIES[2]} pct /> },
          { id: 'length', label: 'Session length', question: 'How long does a typical session last?', render: () => <TrendPanel title="Average session length" sub="Minutes per session" k="avg_session_minutes" name="Avg session (min)" fmt={(v) => fmtNum(v, 0)} color={SERIES[3]} /> },
          { id: 'modes', label: 'Game modes', question: 'Which game modes do people play?', render: () => <ModesPanel /> },
          { id: 'devices', label: 'Platforms & devices', question: 'Do some players have a worse experience?', render: () => (
            <div className="space-y-4">
              <DevicesPanel />
              <GroupByBars title="Average session length" metric="avg_session_minutes" unit="min" dims={[
                { value: 'platform', label: 'Platform', colors: PLATFORM_COLOR }, { value: 'device_tier', label: 'Device quality', colors: TIER_COLOR }, { value: 'country', label: 'Country' }]} />
            </div>) },
        ]} />
      </div>
    </>
  );
}
