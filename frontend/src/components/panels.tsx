'use client';
import { ReactNode, useState } from 'react';
import { useApi, Row } from '@/lib/api';
import { BarDatum, BarsH, CohortHeatmap, LineChartX, LineSeries } from './charts';
import { Panel, Pill } from './ui';
import { fmtInt, fmtPct, fmtUnit, isNil } from '@/lib/format';
import { useFilters } from '@/lib/filters';
import { RET_COLOR, SEGMENT_COLOR, SERIES } from '@/lib/colors';

/** Mini hook: a breakdown by dimension under the current filters. */
export function useBreakdown(dim: string) {
  return useApi<{ rows: Row[] }>('/api/breakdown', { params: { dim } });
}

export function BreakdownBars({
  title, sub, dim, metric, unit = 'num', colors, sort = 'desc', limit, minPlayers = 0, highlight, right, rowHeight, labelWidth, digits,
}: {
  title: ReactNode; sub?: ReactNode; dim: string; metric: string; unit?: string; colors?: Record<string, string>;
  sort?: 'desc' | 'asc' | 'none'; limit?: number; minPlayers?: number; highlight?: string; right?: ReactNode; rowHeight?: number; labelWidth?: number; digits?: number;
}) {
  const { data, error, isLoading, mutate } = useBreakdown(dim);
  let rows = (data?.rows ?? []).filter((r) => !isNil(r[metric]) && (r.new_players ?? 0) + (r.active_players ?? 0) >= minPlayers);
  if (sort !== 'none') rows = [...rows].sort((a, b) => (sort === 'desc' ? b[metric] - a[metric] : a[metric] - b[metric]));
  if (limit) rows = rows.slice(0, limit);
  const bars: BarDatum[] = rows.map((r, i) => ({ name: String(r.dim), value: r[metric], color: colors?.[r.dim] ?? (colors ? SERIES[i % 8] : undefined) }));
  return (
    <Panel title={title} sub={sub} right={right} loading={isLoading} error={error} onRetry={() => mutate()} empty={!bars.length}>
      <BarsH data={bars} fmt={(v) => fmtUnit(unit, v, digits)} rowHeight={rowHeight} labelWidth={labelWidth} highlight={highlight} />
    </Panel>
  );
}

function useMark() {
  const { meta } = useFilters();
  const a = meta?.annotations?.[0];
  return a ? { x: a.date as string, label: a.label as string } : undefined;
}

export function DauTrendPanel({ height = 260 }: { height?: number }) {
  const mark = useMark();
  const { data, error, isLoading, mutate } = useApi<{ range: { from: string; to: string }; rows: Row[] }>('/api/trends/daily');
  const series: LineSeries[] = [
    { key: 'dau', name: 'DAU', color: SERIES[0], width: 1.5, muted: true },
    { key: 'dau_7d', name: 'DAU (7-day avg)', color: SERIES[0], width: 2.5 },
  ];
  return (
    <Panel title="Daily active users" sub="Distinct players with a session per day. Shaded area = selected date range." loading={isLoading} error={error} onRetry={() => mutate()} empty={!data?.rows.length}>
      <LineChartX data={data?.rows ?? []} series={series} fmt={fmtInt} height={height} shade={data ? { from: data.range.from, to: data.range.to } : undefined}
        refLine={mark} />
    </Panel>
  );
}

export function RetentionTrendPanel({ height = 260, keys = ['d1', 'd7', 'd30'] }: { height?: number; keys?: ('d1' | 'd7' | 'd30')[] }) {
  const { data, error, isLoading, mutate } = useApi<{ range: { from: string; to: string }; rows: Row[] }>('/api/trends/retention');
  const mark = useMark();
  const series: LineSeries[] = keys.map((k) => ({ key: `${k}_7d`, name: `${k.toUpperCase()} retention`, color: RET_COLOR[k] }));
  return (
    <Panel title="Retention trend" sub="By install date, 7-day pooled average. Shaded area = selected date range." loading={isLoading} error={error} onRetry={() => mutate()} empty={!data?.rows.length}>
      <LineChartX data={data?.rows ?? []} series={series} fmt={(v) => fmtPct(v, 0)} height={height}
        shade={data ? { from: data.range.from, to: data.range.to } : undefined} yDomain={[0, 'auto']}
        refLine={mark} />
    </Panel>
  );
}

export function CohortPanel() {
  const { data, error, isLoading, mutate } = useApi<{ days: number[]; rows: any[] }>('/api/retention/cohorts');
  return (
    <Panel title="Cohort retention heatmap" sub="Weekly install cohorts × days since install. Cohorts that have not had time to reach a day stay blank."
      loading={isLoading} error={error} onRetry={() => mutate()} empty={!data?.rows.length}>
      {data && <CohortHeatmap days={data.days} rows={data.rows} />}
    </Panel>
  );
}

export function SegmentDistPanel({ title = 'Player segment distribution' }: { title?: string }) {
  const { data, error, isLoading, mutate } = useApi<{ distribution: Row[]; as_of: string }>('/api/segments');
  const bars: BarDatum[] = (data?.distribution ?? []).map((d) => ({ name: d.segment.replace(' Players', ''), value: d.share, color: SEGMENT_COLOR[d.segment], players: d.players }));
  return (
    <Panel title={title} sub={`Rule-based lifecycle snapshot as of ${data?.as_of ?? 'last data day'} (date filter does not apply).`}
      loading={isLoading} error={error} onRetry={() => mutate()} empty={!bars.length}>
      <BarsH data={bars} fmt={(v) => fmtPct(v, 1)} labelWidth={84} rowHeight={34} />
    </Panel>
  );
}

export interface GroupDim { value: string; label: string; colors?: Record<string, string> }

/** One bar chart, with a small toggle to choose how to group it (country / platform / source...). */
export function GroupByBars({ dims, metric, unit = 'num', title, sub, minPlayers = 0, sort = 'desc', digits, labelWidth }: {
  dims: GroupDim[]; metric: string; unit?: string; title: ReactNode; sub?: ReactNode; minPlayers?: number;
  sort?: 'desc' | 'asc' | 'none'; digits?: number; labelWidth?: number;
}) {
  const [dim, setDim] = useState(dims[0].value);
  const d = dims.find((x) => x.value === dim) ?? dims[0];
  return (
    <BreakdownBars key={dim + metric} title={title} sub={sub} dim={d.value} metric={metric} unit={unit} colors={d.colors}
      minPlayers={minPlayers} sort={sort} digits={digits} labelWidth={labelWidth}
      right={dims.length > 1 ? <Pill label="Group by" value={dim} onChange={setDim} options={dims.map((x) => ({ value: x.value, label: x.label }))} /> : undefined} />
  );
}
