'use client';
import { useState } from 'react';
import Link from 'next/link';
import { useApi, Row } from '@/lib/api';
import { GroupHeatmap, LineChartX, ShareHeatTable } from '@/components/charts';
import { FocusTabs } from '@/components/FocusTabs';
import { Badge, Callout, DataTable, DeltaChip, Grid, KpiCard, PageHeader, Panel, Pill, makeDelta } from '@/components/ui';
import { fmtDate, fmtInt, fmtPct, fmtPpRaw, isNil } from '@/lib/format';
import { MODE_COLOR, PLATFORM_COLOR, SEGMENT_COLOR, SERIES, SOURCE_COLOR, TIER_COLOR } from '@/lib/colors';

const DIMS = [
  { value: 'install_week', label: 'Install week' },
  { value: 'country', label: 'Country' },
  { value: 'platform', label: 'Platform' },
  { value: 'source', label: 'Source' },
  { value: 'first_game_mode', label: 'First game mode' },
  { value: 'device_tier', label: 'Device quality' },
  { value: 'tutorial', label: 'Tutorial' },
  { value: 'segment', label: 'Player group' },
];
const COMPARE_DIMS = DIMS.filter((d) => d.value !== 'install_week');
const WINDOWS = [{ value: '0', label: 'All time' }, { value: '90', label: 'Last 90 days' }, { value: '56', label: 'Last 56 days' }];

const COLOR_MAPS: Record<string, Record<string, string>> = {
  source: SOURCE_COLOR, platform: PLATFORM_COLOR, first_game_mode: MODE_COLOR, segment: SEGMENT_COLOR,
  device_tier: { low: TIER_COLOR.low, mid: TIER_COLOR.mid, high: TIER_COLOR.high },
};
const colorFor = (dim: string, label: string, i: number) => COLOR_MAPS[dim]?.[label] ?? SERIES[i % 8];
const labelFmt = (dim: string) => (dim === 'install_week' ? (s: string) => (/^\d{4}-\d{2}-\d{2}$/.test(s) ? `Week of ${fmtDate(s)}` : s) : undefined);
const dimLabel = (v: string) => DIMS.find((d) => d.value === v)?.label ?? v;
const pStr = (p: number | null) => (p == null ? '–' : p < 0.0001 ? '< 0.0001' : p.toFixed(p < 0.01 ? 4 : 3));

/** The two controls every view shares: how to group players, and which install dates to include. */
function Controls({ dim, setDim, win, setWin, dims = DIMS }: { dim: string; setDim: (v: string) => void; win?: string; setWin?: (v: string) => void; dims?: typeof DIMS }) {
  return (
    <div className="mb-3 flex flex-wrap items-center gap-x-3 gap-y-2 text-xs text-ink2">
      <span className="eyebrow">Group players by</span>
      <Pill label="Group by" value={dim} onChange={setDim} options={dims} />
      {win !== undefined && setWin && (<><span className="eyebrow ml-2">Installed</span><Pill label="Install dates" value={win} onChange={setWin} options={WINDOWS} /></>)}
    </div>
  );
}

function HeatmapView() {
  const [dim, setDim] = useState('install_week');
  const [win, setWin] = useState('0');
  const { data, error, isLoading, mutate } = useApi<Row>('/api/explorer/cohorts', { params: { dim, window: win } });
  return (
    <>
      <Controls dim={dim} setDim={setDim} win={win} setWin={setWin} />
      <Panel title={`Retention by ${dimLabel(dim).toLowerCase()}`} sub="Each cell: the % of that group who played exactly N days after installing. Darker is better. Blank = group too new."
        loading={isLoading} error={error} onRetry={() => mutate()} empty={!data?.rows?.length}>
        {data && <GroupHeatmap days={data.days} rowHeader={dimLabel(dim)} labelFmt={labelFmt(dim)} rows={[data.overall, ...data.rows]} />}
        {dim === 'segment' && <p className="mt-3 text-xs text-warn">Player groups describe players today and are partly defined by recent activity, so “Churned” will always look worst. To compare groups fairly, use things known at install: country, platform, source, device or tutorial.</p>}
      </Panel>
    </>
  );
}

function CurvesView() {
  const [dim, setDim] = useState('source');
  const [win, setWin] = useState('0');
  const [show, setShow] = useState('chart');
  const { data, error, isLoading, mutate } = useApi<Row>('/api/explorer/curves', { params: { dim, window: win } });
  const groups: Row[] = data?.groups ?? [];
  const rows: Row[] = [];
  for (let d = 0; d <= 30; d++) {
    const r: Row = { day: d };
    groups.forEach((g) => { r[g.label] = g.points.find((p: Row) => p.day === d)?.rate ?? null; });
    r.__all = data?.overall?.points?.find((p: Row) => p.day === d)?.rate ?? null;
    rows.push(r);
  }
  const series = [
    ...groups.slice(0, 6).map((g, i) => ({ key: g.label, name: g.label, color: colorFor(dim, g.label, i) })),
    { key: '__all', name: 'All players', color: 'var(--ink-3)', dashed: true, width: 1.5 },
  ];
  return (
    <>
      <Controls dim={dim} setDim={setDim} win={win} setWin={setWin} />
      <Panel title={`Retention curve by ${dimLabel(dim).toLowerCase()}`}
        sub={data && data.total_groups > 6 ? `Showing the ${Math.min(6, groups.length)} largest of ${data.total_groups} groups` : 'Share of new players still playing, day by day'}
        right={<Pill label="Show" value={show} onChange={setShow} options={[{ value: 'chart', label: 'Chart' }, { value: 'numbers', label: 'Numbers' }]} />}
        loading={isLoading} error={error} onRetry={() => mutate()} empty={!groups.length}>
        {show === 'chart' ? (
          <LineChartX data={rows} xKey="day" xFmt={(v) => `D${v}`} series={series} fmt={(v) => fmtPct(v, 0)} height={340} yDomain={[0, 1]} />
        ) : (
          <DataTable dense rows={groups} defaultSort={{ key: 'd7', desc: true }} columns={[
            { key: 'label', label: dimLabel(dim), render: (r) => labelFmt(dim)?.(r.label) ?? r.label },
            { key: 'size', label: 'Players', align: 'right', render: (r) => fmtInt(r.size) },
            { key: 'day1_loss', label: 'Gone after day 0', align: 'right', hint: 'Share of installs who never play the next day', render: (r) => fmtPct(r.day1_loss) },
            { key: 'd7', label: 'D7', align: 'right', render: (r) => fmtPct(r.d7) },
            { key: 'd14', label: 'D14', align: 'right', render: (r) => fmtPct(r.d14) },
            { key: 'd30', label: 'D30', align: 'right', render: (r) => fmtPct(r.d30) },
            { key: 'steepest_day', label: 'Steepest fall after D1', align: 'right', hint: 'Day (2-14) with the biggest day-over-day loss',
              render: (r) => (r.steepest_day ? `D${r.steepest_day} (−${(r.steepest_loss * 100).toFixed(0)}%)` : '–') },
          ]} />
        )}
      </Panel>
    </>
  );
}

function LeaveView() {
  const [dim, setDim] = useState('source');
  const [win, setWin] = useState('0');
  const { data, error, isLoading, mutate } = useApi<Row>('/api/explorer/exit-timing', { params: { dim, window: win } });
  return (
    <>
      <Controls dim={dim} setDim={setDim} win={win} setWin={setWin} />
      <Panel title={`When each ${dimLabel(dim).toLowerCase()} group first takes a 7-day break`} sub="Each row adds up to 100%. Early columns are players you lose almost straight away."
        loading={isLoading} error={error} onRetry={() => mutate()} empty={!data?.rows?.length}>
        {data && <ShareHeatTable columns={data.buckets} rowHeader={dimLabel(dim)} labelFmt={labelFmt(dim)} rows={[data.overall, ...data.rows]} />}
        <p className="mt-2 text-xs text-ink3">{data?.note}</p>
      </Panel>
    </>
  );
}

function ChangedView() {
  const [dim, setDim] = useState('country');
  const [metric, setMetric] = useState('d7');
  const [win, setWin] = useState('28');
  const { data, error, isLoading, mutate } = useApi<Row>('/api/explorer/compare', { params: { dim, metric, window: win } });
  const rows: Row[] = data?.rows ?? [];
  const maxC = Math.max(...rows.map((r) => Math.abs(r.contribution_pp ?? 0)), 0.01);
  const bm = data?.by_metric;
  return (
    <>
      <div className="mb-4"><Grid cols={3}>
        {(['d1', 'd7', 'd30'] as const).map((m) => {
          const x = bm?.[m];
          return (
            <KpiCard key={m} label={`${m.toUpperCase()} retention`} loading={isLoading && !bm} value={fmtPct(x?.rate_cur)} term={`${m.toUpperCase()} retention`}
              delta={x ? makeDelta(x.rate_cur, x.rate_prev, 'pp') : null}
              deltaLabel={x ? `vs ${fmtPct(x.rate_prev)} before · ${x.significant ? 'a real change' : 'within noise'}` : ''} />
          );
        })}
      </Grid></div>
      <div className="mb-3 flex flex-wrap items-center gap-x-3 gap-y-2 text-xs text-ink2">
        <span className="eyebrow">Measure</span>
        <Pill label="Metric" value={metric} onChange={setMetric} options={[{ value: 'd1', label: 'D1' }, { value: 'd7', label: 'D7' }, { value: 'd30', label: 'D30' }]} />
        <span className="eyebrow ml-2">Compare periods of</span>
        <Pill label="Window" value={win} onChange={setWin} options={[{ value: '14', label: '14 days' }, { value: '28', label: '28 days' }, { value: '42', label: '42 days' }]} />
        <span className="eyebrow ml-2">Group by</span>
        <select aria-label="Group by" value={dim} onChange={(e) => setDim(e.target.value)} className="rounded-md border border-line bg-panel px-2 py-1 text-xs text-ink">
          {COMPARE_DIMS.map((d) => <option key={d.value} value={d.value}>{d.label}</option>)}
        </select>
      </div>
      <Panel title={`${metric.toUpperCase()} retention by ${dimLabel(dim).toLowerCase()}`}
        sub={data ? `New players ${fmtDate(data.periods.prev_from)}–${fmtDate(data.periods.prev_to)} (before) vs ${fmtDate(data.periods.cur_from)}–${fmtDate(data.periods.cur_to)} (now)` : undefined}
        loading={isLoading} error={error} onRetry={() => mutate()} empty={!rows.length}>
        {data && (
          <>
            <div className="mb-3 flex flex-wrap items-center gap-3 text-sm">
              <span className="text-ink2">Overall</span>
              <span className="num text-lg text-ink">{fmtPct(data.overall.rate_prev)} → {fmtPct(data.overall.rate_cur)}</span>
              <DeltaChip delta={makeDelta(data.overall.rate_cur, data.overall.rate_prev, 'pp')} />
              <Badge tone={data.overall.significant ? 'accent' : 'neutral'}>{data.overall.significant ? 'a real change' : 'within noise'} · p {pStr(data.overall.p_value)}</Badge>
            </div>
            <DataTable dense defaultSort={{ key: 'contribution_pp', desc: false }} rows={rows} columns={[
              { key: 'label', label: dimLabel(dim), render: (r) => <span>{r.label}{r.low_sample && <span className="ml-1 text-[10px] text-ink3" title="Fewer than 30 players in a period">few players</span>}</span> },
              { key: 'players', label: 'Players before → now', align: 'right', sortValue: (r) => r.players_cur, render: (r) => `${fmtInt(r.players_prev)} → ${fmtInt(r.players_cur)}` },
              { key: 'rate', label: 'Retention', align: 'right', sortValue: (r) => r.rate_cur, render: (r) => `${fmtPct(r.rate_prev)} → ${fmtPct(r.rate_cur)}` },
              { key: 'delta_pp', label: 'Change', align: 'right', render: (r) => fmtPpRaw(r.delta_pp) },
              { key: 'p_value', label: 'Real change?', render: (r) => (r.p_value == null ? '–' : r.significant ? <Badge tone={r.delta_pp < 0 ? 'bad' : 'good'} icon={r.delta_pp < 0 ? 'down' : 'up'}>yes</Badge> : <Badge tone="neutral">no</Badge>) },
              { key: 'contribution_pp', label: 'Share of overall change', sortValue: (r) => r.contribution_pp, render: (r) => {
                const v = r.contribution_pp as number; const w = Math.min(Math.abs(v) / maxC, 1) * 50; const neg = v < 0;
                return (
                  <div className="flex items-center gap-2">
                    <div className="relative h-3.5 w-24 shrink-0" aria-hidden>
                      <div className="absolute left-1/2 top-0 h-full w-px bg-line" />
                      <div className="absolute top-0.5 h-2.5 rounded-sm" style={{ width: `${w}%`, left: neg ? `${50 - w}%` : '50%', background: neg ? 'var(--bad)' : 'var(--good)' }} />
                    </div>
                    <span className={`num w-16 text-right ${neg ? 'text-bad' : 'text-good'}`}>{fmtPpRaw(v, 2)}</span>
                  </div>
                );
              } },
            ]} />
            <p className="mt-3 text-xs text-ink3">“Change” is the group's own movement. “Share of overall change” also counts how much of the new players it now makes up, so a growing weak group drags the total down even if its own rate is steady. With many groups, a few “yes” answers can be luck.</p>
          </>
        )}
      </Panel>
      <div className="mt-4">
        <Callout tone="neutral" icon="info" title="Found a group that moved?">
          Take it to <Link href="/investigation" className="font-medium text-accent underline underline-offset-2">Why did it drop?</Link>, which profiles the group and lists possible causes.
        </Callout>
      </div>
    </>
  );
}

export default function ExplorerPage() {
  return (
    <>
      <PageHeader eyebrow="Which players are leaving, and when?" title="Who leaves, and when?"
        desc="Compare groups of players over time: how fast each group stops playing, the day they first take a break, and which group changed versus the previous period." />
      <FocusTabs tabs={[
        { id: 'heatmap', label: 'Fade over time', question: 'How does each group fade over time?', render: () => <HeatmapView /> },
        { id: 'curves', label: 'Curves', question: 'How quickly does each group stop playing?', render: () => <CurvesView /> },
        { id: 'leave', label: 'When they leave', question: 'On which day do players first stop playing?', render: () => <LeaveView /> },
        { id: 'changed', label: 'What changed', question: 'Which group changed since the previous period?', render: () => <ChangedView /> },
      ]} />
    </>
  );
}
