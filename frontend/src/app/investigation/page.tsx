'use client';
import { useEffect, useState } from 'react';
import Link from 'next/link';
import { useApi, Row } from '@/lib/api';
import { useFilters } from '@/lib/filters';
import { FocusTabs, FocusTab } from '@/components/FocusTabs';
import { Badge, Callout, DataTable, Grid, Icon, PageHeader, Panel, Pill, Skeleton } from '@/components/ui';
import { fmtDateLong, fmtDeltaUnit, fmtInt, fmtPct, fmtPpRaw, fmtUnit, isNil } from '@/lib/format';

const DIM_ORDER = ['country', 'platform', 'source', 'first_game_mode', 'device_tier'];
const DIM_STEP: Record<string, string> = {
  country: 'Retention by country',
  platform: 'Retention by platform',
  source: 'Retention by acquisition source',
  first_game_mode: 'Retention by game mode',
  device_tier: 'Retention by device tier',
};

function ContribBar({ v, max }: { v: number; max: number }) {
  const w = max ? Math.min(Math.abs(v) / max, 1) * 50 : 0;
  const neg = v < 0;
  return (
    <div className="flex items-center gap-2">
      <div className="relative h-3.5 w-28 shrink-0" aria-hidden>
        <div className="absolute left-1/2 top-0 h-full w-px bg-line" />
        <div className="absolute top-0.5 h-2.5 rounded-sm" style={{ width: `${w}%`, left: neg ? `${50 - w}%` : '50%', background: neg ? 'var(--bad)' : 'var(--good)' }} />
      </div>
      <span className={`num w-16 text-right ${neg ? 'text-bad' : 'text-good'}`}>{fmtPpRaw(v, 2)}</span>
    </div>
  );
}

const rateCell = (a: number | null, b: number | null) => (
  <span className="whitespace-nowrap">{fmtPct(a)} <span className="text-ink3">→</span> {fmtPct(b)}</span>
);

function DimensionTable({ rows, label }: { rows: Row[]; label: string }) {
  const max = Math.max(...rows.map((r) => Math.abs(r.contribution_pp)), 0.0001);
  return (
    <DataTable dense defaultSort={{ key: 'contribution_pp', desc: false }} rows={rows} columns={[
      { key: 'label', label, render: (r) => <span>{r.label}{r.low_sample && <span className="ml-1 text-[10px] text-ink3" title="Fewer than 40 players in the current window">low n</span>}</span> },
      { key: 'players', label: 'Players prev → cur', align: 'right', sortValue: (r) => r.players_cur, render: (r) => <span className="whitespace-nowrap">{fmtInt(r.players_prev)} → {fmtInt(r.players_cur)}</span> },
      { key: 'share', label: 'Install share', align: 'right', sortValue: (r) => r.share_cur, render: (r) => rateCell(r.share_prev, r.share_cur) },
      { key: 'rate', label: 'Retention', align: 'right', sortValue: (r) => r.rate_cur, render: (r) => rateCell(r.rate_prev, r.rate_cur) },
      { key: 'delta_pp', label: 'Δ rate', align: 'right', render: (r) => fmtPpRaw(r.delta_pp) },
      { key: 'rate_effect_pp', label: 'Rate effect', align: 'right', hint: 'Players in this segment behave differently', render: (r) => fmtPpRaw(r.rate_effect_pp, 2) },
      { key: 'mix_effect_pp', label: 'Mix effect', align: 'right', hint: 'A different share of installs now comes from this segment', render: (r) => fmtPpRaw(r.mix_effect_pp, 2) },
      { key: 'contribution_pp', label: 'Contribution to overall change', render: (r) => <ContribBar v={r.contribution_pp} max={max} /> },
    ]} />
  );
}

function Stat({ label, value, sub, tone, small }: { label: string; value: string; sub?: string; tone?: 'bad' | 'good'; small?: boolean }) {
  return (
    <div>
      <div className="eyebrow">{label}</div>
      <div className={`num ${small ? 'text-lg' : 'text-3xl'} font-medium ${tone === 'bad' ? 'text-bad' : tone === 'good' ? 'text-good' : 'text-ink'}`}>{value}</div>
      {sub && <div className="text-xs text-ink3">{sub}</div>}
    </div>
  );
}

const SIGNAL_TONE: Record<string, 'good' | 'warn' | 'neutral' | 'accent'> = { consistent: 'accent', weak: 'warn', none: 'neutral', insufficient: 'neutral' };

function HypothesisCard({ h }: { h: Row }) {
  return (
    <section className="rounded-lg border border-line bg-panel p-4">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <Badge tone="warn" icon="alert">{h.label}</Badge>
        <Badge tone={SIGNAL_TONE[h.signal.strength]}>{h.signal.text}</Badge>
      </div>
      <h3 className="font-display text-base font-semibold">{h.title}</h3>
      <p className="mt-1 text-sm text-ink2">{h.statement}</p>
      <table className="data mt-3" style={{ fontSize: 12 }}>
        <thead><tr><th>Evidence</th><th className="n">Previous</th><th className="n">Current</th></tr></thead>
        <tbody>
          {h.evidence.map((e: Row, i: number) => (
            <tr key={i}><td>{e.metric}</td><td className="n num">{fmtUnit(e.unit, e.previous, e.unit === 'num' ? 2 : 1)}</td><td className="n num">{fmtUnit(e.unit, e.current, e.unit === 'num' ? 2 : 1)}</td></tr>
          ))}
        </tbody>
      </table>
      <p className="mt-3 text-xs text-ink3"><span className="font-medium text-ink2">How to validate: </span>{h.validation}</p>
    </section>
  );
}

function H2({ children, id }: { children: React.ReactNode; id?: string }) {
  return <h2 id={id} className="mb-1 mt-8 scroll-mt-20 font-display text-lg font-semibold tracking-wide">{children}</h2>;
}

/** The whole investigation in four sentences, for someone who will not read the tables. */
function PlainSummary({ d }: { d: Row }) {
  const pr = d.problem, cul = d.culprit;
  const down = pr.delta_pp < 0;
  const share = cul.share_of_change;
  const causes: string[] = (d.hypotheses as Row[]).filter((h) => h.signal.strength === 'consistent').map((h) => h.title.toLowerCase());
  const ret = (cul.metrics as Row[]).find((m) => m.key === 'retention');
  return (
    <section aria-label="In plain words" className="mb-4 rounded-lg border border-accent/40 bg-accent/5 p-4">
      <div className="eyebrow mb-1 text-accent">In plain words</div>
      <p className="text-sm leading-relaxed text-ink">
        <b>{d.metric_label} {down ? 'fell' : 'rose'} from {fmtPct(pr.previous)} to {fmtPct(pr.current)}</b> ({Math.abs(pr.delta_pp).toFixed(1)} points).{' '}
        {pr.significant ? 'That is too big to be luck.' : 'That could still be luck.'}{' '}
        {share != null && cul.label !== 'All players' && (
          <>The biggest single source is <b>{cul.label}</b>, which accounts for about {Math.round(Math.abs(share) * 100)}% of the change{ret && ret.previous != null ? <> (their {d.metric_label} went from {fmtPct(ret.previous)} to {fmtPct(ret.current)})</> : null}.{' '}</>
        )}
        {causes.length ? <>We cannot prove why, but the data fits: {causes.join(' and ')}.</> : <>The data does not point to a clear cause yet.</>}{' '}
        A sensible next step is to test a fix on that group (last step).
      </p>
    </section>
  );
}

export default function InvestigationPage() {
  const { meta } = useFilters();
  const [metric, setMetric] = useState('d7');
  const [windowDays, setWindowDays] = useState('28');
  const [dim, setDim] = useState('country');
  const [ov, setOv] = useState<{ country: string; platform: string; source: string }>({ country: '', platform: '', source: '' });
  const cap = meta?.dataset?.capabilities;
  const maxWin: number = cap?.max_window ?? 42;
  const winOpts = Array.from(new Set([14, 28, 42, ...(cap?.suggested_window ? [cap.suggested_window] : [])].filter((w) => w <= maxWin))).sort((a, b) => a - b);
  useEffect(() => {
    if (cap?.suggested_window && Number(windowDays) > maxWin) setWindowDays(String(cap.suggested_window));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [maxWin, cap?.suggested_window]);
  const { data, error, isLoading, mutate } = useApi<Row>('/api/investigation', {
    filters: false, params: { metric, window: windowDays, country: ov.country, platform: ov.platform, source: ov.source },
  });
  const hasOverride = Boolean(ov.country || ov.platform || ov.source);
  const pr = data?.problem;
  const cul = data?.culprit;
  const dimRows: Row[] = data?.dimensions?.[dim]?.rows ?? [];
  const optionKey = { country: 'countries', platform: 'platforms', source: 'sources' } as const;
  const wait = isLoading || !data;

  const tabs: FocusTab[] = [
    {
      id: 'problem', label: 'What happened', question: 'What happened?',
      render: () => (
        <>
          {data && <PlainSummary d={data} />}
          <section className={`rounded-lg border bg-panel p-5 ${pr && pr.delta_pp >= 0 ? 'border-good/40' : 'border-bad/40'}`} aria-label="Problem statement">
            <div className="flex flex-wrap items-center gap-2">
              <Badge tone={pr && pr.delta_pp < 0 ? 'bad' : 'good'} icon="alert">{pr && pr.delta_pp < 0 ? 'Drop detected' : 'Rise detected'}</Badge>
              {pr && <Badge tone={pr.significant ? 'accent' : 'neutral'}>{pr.significant ? 'Too big to be luck' : 'Could be luck'} (p {pr.p_value < 0.0001 ? '< 0.0001' : `= ${pr.p_value.toFixed(3)}`})</Badge>}
            </div>
            {wait || !pr ? <Skeleton className="mt-3 h-12 w-96" /> : (
              <>
                <h3 className="mt-2 font-display text-3xl font-bold tracking-wide text-ink">{pr.statement}</h3>
                <div className="mt-3 grid grid-cols-2 gap-4 md:grid-cols-4">
                  <Stat label="Before" value={fmtPct(pr.previous)} sub={`${fmtInt(pr.players_prev)} new players`} />
                  <Stat label="Now" value={fmtPct(pr.current)} sub={`${fmtInt(pr.players_cur)} new players`} />
                  <Stat label="Difference" value={fmtPpRaw(pr.delta_pp)} tone={pr.delta_pp < 0 ? 'bad' : 'good'} sub={`${pr.relative_change > 0 ? '+' : '−'}${Math.abs(pr.relative_change * 100).toFixed(1)}% relative`} />
                  <Stat label="Periods compared" value={`${data!.window_days} days each`} sub={`${fmtDateLong(data!.periods.prev_from)} – ${fmtDateLong(data!.periods.prev_to)} vs ${fmtDateLong(data!.periods.cur_from)} – ${fmtDateLong(data!.periods.cur_to)}`} small />
                </div>
              </>
            )}
          </section>
        </>
      ),
    },
    {
      id: 'where', label: 'Where', question: 'Where did it move?',
      render: () => (
        <>
          <p className="mb-3 max-w-3xl text-sm text-ink3">Each row is one group of players. The last column shows how many points of the overall change that group accounts for, and the rows add up exactly to the total. A group that is growing and retains badly counts as a drag even if its own numbers barely moved.</p>
          <Panel title={DIM_STEP[dim]} sub="Biggest drag first"
            right={<Pill label="Look at" value={dim} onChange={setDim} options={DIM_ORDER.map((d) => ({ value: d, label: data?.dimensions?.[d]?.label ?? d }))} />}
            loading={wait} error={error} onRetry={() => mutate()} empty={!dimRows.length}>
            <DimensionTable rows={dimRows} label={data?.dimensions?.[dim]?.label ?? 'Value'} />
          </Panel>
        </>
      ),
    },
    {
      id: 'who', label: 'Which group', question: 'Which group of players is responsible?',
      render: () => (
        <>
          <p className="mb-3 max-w-3xl text-sm text-ink3">Every country × platform × source combination ({data?.segments?.searched ?? '…'} searched; at least {data?.segments?.min_players ?? 40} new players needed to be ranked). Click a row to look at that group in the next step.</p>
          <Panel title="Groups ranked by how much they explain" loading={wait} error={error} onRetry={() => mutate()} empty={!data?.segments?.rows?.length}>
            <DataTable dense rows={(data?.segments?.rows ?? []).filter((r: Row) => !r.low_sample)}
              onRowClick={(r) => setOv({ country: r.country, platform: r.platform, source: r.source })}
              columns={[
                { key: 'label', label: 'Group (country / platform / source)' },
                { key: 'players', label: 'Players before → now', align: 'right', render: (r) => <span className="whitespace-nowrap">{fmtInt(r.players_prev)} → {fmtInt(r.players_cur)}</span> },
                { key: 'share', label: 'Share of installs', align: 'right', render: (r) => rateCell(r.share_prev, r.share_cur) },
                { key: 'rate', label: 'Retention', align: 'right', render: (r) => rateCell(r.rate_prev, r.rate_cur) },
                { key: 'share_of_change', label: '% of total change', align: 'right', render: (r) => (r.share_of_change == null ? '–' : `${(r.share_of_change * 100).toFixed(0)}%`) },
                { key: 'contribution_pp', label: 'Contribution', render: (r) => <ContribBar v={r.contribution_pp} max={Math.max(...(data?.segments?.rows ?? []).map((x: Row) => Math.abs(x.contribution_pp)), 0.01)} /> },
              ]} />
          </Panel>
        </>
      ),
    },
    {
      id: 'profile', label: "What's different", question: cul ? `What is different about ${cul.label}?` : 'What is different about that group?',
      render: () => (
        <Panel loading={wait} error={error} onRetry={() => mutate()}>
          {cul && (
            <>
              <div className="mb-4 flex flex-wrap items-center gap-3">
                <div className="flex items-center gap-1.5 font-display text-xl font-semibold">
                  {[cul.filters.platform, cul.filters.source, cul.filters.country].filter(Boolean).map((p: string, i: number, a: string[]) => (
                    <span key={p} className="flex items-center gap-1.5"><span className="rounded border border-line bg-panel2 px-2 py-0.5">{p}</span>{i < a.length - 1 && <Icon name="arrow" size={14} className="text-ink3" />}</span>
                  ))}
                  {![cul.filters.platform, cul.filters.source, cul.filters.country].some(Boolean) && <span>All players</span>}
                </div>
                {cul.share_of_change != null && <Badge tone="bad">≈ {(cul.share_of_change * 100).toFixed(0)}% of the change ({fmtPpRaw(cul.contribution_pp, 2)})</Badge>}
                {!hasOverride && <Badge tone="accent">picked for you: the biggest drag</Badge>}
              </div>
              <div className="mb-4 flex flex-wrap items-center gap-2 text-xs text-ink2">
                <span className="eyebrow">Look at another group</span>
                {(['country', 'platform', 'source'] as const).map((k) => (
                  <select key={k} aria-label={k} value={ov[k]} onChange={(e) => setOv({ ...ov, [k]: e.target.value })}
                    className="rounded-md border border-line bg-panel px-2 py-1 text-xs text-ink">
                    <option value="">{k}: any</option>
                    {(meta?.options?.[optionKey[k]] ?? []).map((o: string) => <option key={o} value={o}>{o}</option>)}
                  </select>
                ))}
                {hasOverride && <button className="rounded px-2 py-1 text-accent hover:bg-panel2" onClick={() => setOv({ country: '', platform: '', source: '' })}>Back to the picked group</button>}
              </div>
              <DataTable dense rows={cul.metrics} columns={[
                { key: 'label', label: 'Measure' },
                { key: 'previous', label: 'Before', align: 'right', render: (r) => fmtUnit(r.unit, r.previous) },
                { key: 'current', label: 'Now', align: 'right', render: (r) => fmtUnit(r.unit, r.current) },
                { key: 'delta', label: 'Change', align: 'right', render: (r) => fmtDeltaUnit(r.unit, r.delta) },
                { key: 'delta_pct', label: 'Relative', align: 'right', render: (r) => (isNil(r.delta_pct) ? '–' : `${r.delta_pct >= 0 ? '+' : '−'}${Math.abs(r.delta_pct * 100).toFixed(0)}%`) },
                { key: 'worsened', label: 'Direction', render: (r) => (r.worsened == null ? '–' : r.worsened ? <Badge tone="bad" icon="down">worse</Badge> : <Badge tone="good" icon="up">better</Badge>) },
              ]} />
              <p className="mt-2 text-xs text-ink3">{fmtInt(cul.players_prev)} players before · {fmtInt(cul.players_cur)} now. Early-behaviour measures use players with their first 7 days fully observed; week-2 churn needs 14 days, so it covers fewer players.</p>
            </>
          )}
        </Panel>
      ),
    },
    {
      id: 'device', label: 'Device quality', question: 'Is it a phone-quality or crash problem?',
      render: () => (
        <Panel title={`Players on ${cul?.filters?.platform ?? 'all platforms'}, by device quality`} sub="All sources and countries on this platform: is a performance problem hitting everyone, or only this group?"
          loading={wait} error={error} onRetry={() => mutate()} empty={!data?.device_performance?.length}>
          <DataTable dense rows={data?.device_performance ?? []} columns={[
            { key: 'device_tier', label: 'Device quality', render: (r) => <span className="capitalize">{r.device_tier}-end</span> },
            { key: 'players', label: 'Players before → now', align: 'right', render: (r) => `${fmtInt(r.players_prev)} → ${fmtInt(r.players_cur)}` },
            { key: 'crash', label: 'Crashes per 100 sessions', align: 'right', hint: 'Per session, so players who quit early do not look safer', render: (r) => `${fmtUnit('num', r.crash100_prev, 1)} → ${fmtUnit('num', r.crash100_cur, 1)}` },
            { key: 'minutes', label: 'Avg session', align: 'right', render: (r) => `${fmtUnit('min', r.minutes_prev, 0)} → ${fmtUnit('min', r.minutes_cur, 0)}` },
            { key: 'rate', label: data?.metric_label ?? 'Retention', align: 'right', render: (r) => rateCell(r.rate_prev, r.rate_cur) },
          ]} />
        </Panel>
      ),
    },
    {
      id: 'why', label: 'Possible causes', question: 'What could be causing it? (not yet proven)',
      render: () => (
        <>
          <p className="mb-3 max-w-3xl text-sm text-ink3">These are candidate explanations. The signal says whether the data is <em>consistent</em> with each one, not that it is true. Every one needs a check before you act on it.</p>
          <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
            {wait && [0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-48" />)}
            {(data?.hypotheses ?? []).map((h: Row) => <HypothesisCard key={h.id} h={h} />)}
          </div>
        </>
      ),
    },
    {
      id: 'next', label: 'What next', question: 'What should we do next?',
      render: () => (
        <Panel title="Test a fix on the affected group" sub="Sample size at 80% power and 5% significance" loading={wait} error={error} onRetry={() => mutate()} empty={!data?.test_design}>
          {data?.test_design && (
            <>
              <p className="mb-3 text-sm text-ink2">This group's {data.metric_label} is <span className="num text-ink">{fmtPct(data.test_design.baseline)}</span> and about <span className="num text-ink">{data.test_design.daily_installs.toFixed(0)}</span> new players arrive per day. Compare the old onboarding with the improved one for this group only.</p>
              <DataTable dense rows={data.test_design.options} columns={[
                { key: 'mde_pp', label: 'Improvement to detect', render: (r) => `${r.mde_pp.toFixed(0)} points` },
                { key: 'n_per_arm', label: 'Players per group', align: 'right', render: (r) => fmtInt(r.n_per_arm) },
                { key: 'days_to_complete', label: 'Days to complete', align: 'right', render: (r) => (r.days_to_complete == null ? '–' : fmtInt(r.days_to_complete)) },
              ]} />
              <div className="mt-4 flex flex-wrap gap-2 text-sm">
                <Link href={`/experiments?tab=plan&kpi=${data.metric}&baseline=${data.test_design.baseline.toFixed(4)}&daily=${data.test_design.daily_installs.toFixed(0)}&lift=5&label=${encodeURIComponent(cul?.label ?? '')}`}
                  className="inline-flex items-center gap-1 rounded-md bg-accent px-3 py-1.5 font-medium text-white hover:opacity-90">Plan this test <Icon name="arrow" size={14} /></Link>
                <Link href="/experiments" className="inline-flex items-center gap-1 rounded-md border border-line px-3 py-1.5 text-accent hover:bg-panel2">See the existing onboarding test <Icon name="arrow" size={14} /></Link>
                <Link href="/insights" className="inline-flex items-center gap-1 rounded-md border border-line px-3 py-1.5 text-accent hover:bg-panel2">More recommendations <Icon name="arrow" size={14} /></Link>
              </div>
            </>
          )}
        </Panel>
      ),
    },
  ];

  return (
    <>
      <PageHeader eyebrow="Case file" title="Why did it drop?"
        desc="A number moved. This page finds which players are behind the change, how much each group explains, and what could be causing it. It never claims a cause it cannot prove."
        right={
          <div className="flex flex-wrap items-center gap-x-2 gap-y-2">
            <span className="eyebrow">Measure</span>
            <Pill label="Metric" value={metric} onChange={setMetric} options={[{ value: 'd1', label: 'D1' }, { value: 'd7', label: 'D7' }, { value: 'd30', label: 'D30' }]} />
            <span className="eyebrow ml-2">Compare periods of</span>
            <Pill label="Cohort window" value={windowDays} onChange={setWindowDays} options={winOpts.map((w) => ({ value: String(w), label: `${w}d` }))} />
          </div>
        } />
      {error ? <Callout tone="bad" icon="alert" title="Investigation unavailable">{String((error as Error).message)}</Callout> : <FocusTabs steps tabs={tabs} />}
    </>
  );
}
