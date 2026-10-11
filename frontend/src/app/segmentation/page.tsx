'use client';
import { useState } from 'react';
import { useApi, Row } from '@/lib/api';
import { ClusterScatter, LineChartX, ShareBars } from '@/components/charts';
import { FocusTabs } from '@/components/FocusTabs';
import { SegmentDistPanel } from '@/components/panels';
import { Callout, DataTable, PageHeader, Panel, Pill, Swatch } from '@/components/ui';
import { fmtInt, fmtNum, fmtPct, fmtUsd } from '@/lib/format';
import { SEGMENT_COLOR, SERIES } from '@/lib/colors';

const SEGMENTS = ['New Players', 'Casual Players', 'Engaged Players', 'High-Value Players', 'At-Risk Players', 'Churned Players'];
type Seg = { definitions: Row[]; distribution: Row[]; by_country: Row[]; by_platform: Row[]; by_source: Row[] };

function useSegments() { return useApi<Seg>('/api/segments'); }

function Rules() {
  const { data, error, isLoading, mutate } = useSegments();
  return (
    <Panel title="Rules for each group" sub="The first rule that matches wins. Thresholds live in backend/app/segment_rules.py." loading={isLoading} error={error} onRetry={() => mutate()}>
      <DataTable dense rows={data?.definitions ?? []} columns={[
        { key: 'priority', label: '#', hint: 'Rules are checked top to bottom' },
        { key: 'segment', label: 'Group', render: (r) => <span><Swatch color={SEGMENT_COLOR[r.segment]} />{r.segment}</span> },
        { key: 'rule', label: 'Rule' },
        { key: 'intent', label: 'What it is for' },
      ]} />
    </Panel>
  );
}

function Behaviour() {
  const { data, error, isLoading, mutate } = useSegments();
  return (
    <Panel title="Behaviour of each group" sub="Last 30 days and lifetime spend, as of the last day of data" loading={isLoading} error={error} onRetry={() => mutate()} empty={!data?.distribution?.length}>
      <DataTable dense rows={data?.distribution ?? []} columns={[
        { key: 'segment', label: 'Group', render: (r) => <span><Swatch color={SEGMENT_COLOR[r.segment]} />{r.segment}</span> },
        { key: 'players', label: 'Players', align: 'right', render: (r) => fmtInt(r.players) },
        { key: 'share', label: 'Share', align: 'right', render: (r) => fmtPct(r.share) },
        { key: 'sessions_30d', label: 'Sessions', align: 'right', render: (r) => fmtNum(r.sessions_30d) },
        { key: 'minutes_30d', label: 'Minutes', align: 'right', render: (r) => fmtNum(r.minutes_30d, 0) },
        { key: 'days_since_last', label: 'Days since last play', align: 'right', render: (r) => fmtNum(r.days_since_last) },
        { key: 'avg_spend', label: 'Avg lifetime spend', align: 'right', render: (r) => fmtUsd(r.avg_spend) },
        { key: 'revenue_share', label: 'Share of revenue', align: 'right', render: (r) => fmtPct(r.revenue_share) },
      ]} />
    </Panel>
  );
}

function Mix() {
  const { data, error, isLoading, mutate } = useSegments();
  const [by, setBy] = useState('country');
  const parts = SEGMENTS.map((s) => ({ key: s, name: s.replace(' Players', ''), color: SEGMENT_COLOR[s] }));
  const rows = by === 'country' ? data?.by_country : by === 'platform' ? data?.by_platform : data?.by_source;
  return (
    <Panel title="Share of each group" sub="Each bar sums to 100%"
      right={<Pill label="Group by" value={by} onChange={setBy} options={[{ value: 'country', label: 'Country' }, { value: 'platform', label: 'Platform' }, { value: 'source', label: 'Source' }]} />}
      loading={isLoading} error={error} onRetry={() => mutate()} empty={!rows?.length}>
      <ShareBars rows={rows ?? []} nameKey={by} parts={parts} />
    </Panel>
  );
}

function Leaving() {
  const { data, error, isLoading, mutate } = useApi<{ by_tier: Row[] }>('/api/churn');
  return (
    <Panel title="Who leaves?" sub="Players active in the earlier 30 days who were gone in the latest 30, by how engaged they were" term="Churn"
      loading={isLoading} error={error} onRetry={() => mutate()} empty={!data?.by_tier?.length}>
      <DataTable dense rows={data?.by_tier ?? []} columns={[
        { key: 'tier', label: 'Earlier engagement' },
        { key: 'active_prior', label: 'Active in earlier 30 days', align: 'right', render: (r) => fmtInt(r.active_prior) },
        { key: 'churned', label: 'Gone in latest 30', align: 'right', render: (r) => fmtInt(r.churned) },
        { key: 'churn_rate', label: 'Left', align: 'right', render: (r) => fmtPct(r.churn_rate) },
      ]} />
    </Panel>
  );
}

const KVIEWS = [
  { value: 'profiles', label: 'Cluster profiles' }, { value: 'map', label: 'Map' },
  { value: 'overlap', label: 'Compare with rules' }, { value: 'k', label: 'How many clusters?' },
];

function KMeans() {
  const [k, setK] = useState('5');
  const [view, setView] = useState('profiles');
  const { data, error, isLoading, mutate } = useApi<Row>('/api/segments/kmeans', { filters: false, params: { k } });
  const names: string[] = (data?.clusters ?? []).map((c: Row) => c.name);
  const colors: Record<string, string> = {};
  names.forEach((n, i) => (colors[n] = SERIES[i % 8]));
  const feats: string[] = data?.features ?? [];
  const common = { loading: isLoading, error, onRetry: () => mutate() };
  return (
    <div className="space-y-3">
      <Callout tone="neutral" icon="info">K-Means finds groups from behaviour alone, without our rules. Use it to check whether the rules miss a natural grouping. {data?.note}</Callout>
      <div className="flex flex-wrap items-center gap-3 text-xs text-ink2">
        <span className="eyebrow">View</span><Pill label="K-Means view" value={view} onChange={setView} options={KVIEWS} />
        <span className="eyebrow ml-2">Clusters</span><Pill label="Number of clusters" value={k} onChange={setK} options={[4, 5, 6, 7].map((n) => ({ value: String(n), label: String(n) }))} />
        {data && <span>Separation score <span className="num text-ink">{fmtNum(data.silhouette, 2)}</span> (higher = cleaner groups)</span>}
      </div>
      {view === 'profiles' && (
        <Panel title="Average behaviour per cluster" empty={!data?.clusters?.length} {...common}>
          <DataTable dense rows={data?.clusters ?? []} columns={[
            { key: 'name', label: 'Cluster', render: (r) => <span><Swatch color={colors[r.name]} />{r.name}</span> },
            { key: 'players', label: 'Players', align: 'right', render: (r) => `${fmtInt(r.players)} (${fmtPct(r.share, 0)})` },
            ...feats.map((f) => ({ key: f, label: f, align: 'right' as const, sortValue: (r: Row) => r.profile[f], render: (r: Row) => fmtNum(r.profile[f], f.startsWith('Lifetime') ? 2 : 1) })),
          ]} />
        </Panel>
      )}
      {view === 'map' && (
        <Panel title="Behaviour map" sub="1,500 sampled players flattened to two dimensions" empty={!data?.scatter?.length} {...common}>
          <ClusterScatter points={data?.scatter ?? []} colors={colors} />
        </Panel>
      )}
      {view === 'overlap' && (
        <Panel title="How clusters map to the rule-based groups" sub="Each row sums to 100%" empty={!data?.overlap_with_rules?.length} {...common}>
          <DataTable dense rows={data?.overlap_with_rules ?? []} columns={[
            { key: 'segment', label: 'Rule-based group' },
            ...names.map((n) => ({ key: n, label: n, align: 'right' as const, render: (r: Row) => fmtPct(r[n], 0) })),
          ]} />
        </Panel>
      )}
      {view === 'k' && (
        <Panel title="Choosing the number of clusters" sub="Look for the bend where extra clusters stop paying off" empty={!data?.elbow?.length} {...common}>
          <LineChartX data={data?.elbow ?? []} xKey="k" xFmt={(v) => String(v)} series={[{ key: 'inertia', name: 'Spread inside clusters', color: SERIES[0] }]} fmt={(v) => fmtNum(v, 0)} height={280} />
        </Panel>
      )}
    </div>
  );
}

export default function SegmentationPage() {
  return (
    <>
      <PageHeader eyebrow="Who are our players?" title="Player groups"
        desc="Players sorted by simple rules into new, casual, engaged, high-value, at-risk and churned. The rules are listed, so you can see exactly who is in each group." />
      <FocusTabs tabs={[
        { id: 'size', label: 'How many', question: 'How many players are in each group?', render: () => <SegmentDistPanel title="Players by group" /> },
        { id: 'rules', label: 'The rules', question: 'Who is in each group?', render: () => <Rules /> },
        { id: 'behaviour', label: 'Behaviour', question: 'How does each group behave and spend?', render: () => <Behaviour /> },
        { id: 'mix', label: 'By market', question: 'How do the groups differ by country, platform or source?', render: () => <Mix /> },
        { id: 'leaving', label: 'Who leaves', question: 'Which kind of player leaves?', render: () => <Leaving /> },
        { id: 'kmeans', label: 'Advanced: clustering', question: 'Does an algorithm find groups our rules miss?', render: () => <KMeans /> },
      ]} />
    </>
  );
}
