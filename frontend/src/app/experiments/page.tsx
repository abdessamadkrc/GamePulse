'use client';
import { Suspense, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import { useApi, Row } from '@/lib/api';
import { CiBar } from '@/components/charts';
import ExperimentMonitor from '@/components/ExperimentMonitor';
import { FocusTabs } from '@/components/FocusTabs';
import PlanTest from '@/components/PlanTest';
import { Badge, Callout, DataTable, Grid, PageHeader, Panel, Pill, Skeleton } from '@/components/ui';
import { fmtDateLong, fmtInt, fmtUnit, isNil } from '@/lib/format';

const pStr = (p: number) => (p < 0.0001 ? 'p < 0.0001' : `p = ${p < 0.01 ? p.toFixed(4) : p.toFixed(3)}`);
const diffStr = (r: Row) => (r.kind === 'proportion' ? `${r.abs_diff >= 0 ? '+' : '−'}${Math.abs(r.abs_diff * 100).toFixed(2)} pp` : `${r.abs_diff >= 0 ? '+' : '−'}${fmtUnit(r.unit, Math.abs(r.abs_diff), 2)}`);
const ciStr = (r: Row) => (r.kind === 'proportion' ? `${(r.ci_low * 100).toFixed(1)} to ${(r.ci_high * 100).toFixed(1)} pp` : `${fmtUnit(r.unit, r.ci_low, 2)} to ${fmtUnit(r.unit, r.ci_high, 2)}`);

const DECISION: Record<string, { tone: 'good' | 'warn' | 'bad' | 'neutral'; icon: string }> = {
  ship: { tone: 'good', icon: 'check' }, hold: { tone: 'warn', icon: 'alert' }, stop: { tone: 'bad', icon: 'alert' },
  inconclusive: { tone: 'neutral', icon: 'info' }, investigate: { tone: 'warn', icon: 'alert' },
};

function Big({ label, value, sub, tone }: { label: string; value: string; sub?: string; tone?: 'good' | 'bad' }) {
  return (
    <div className="rounded-lg border border-line bg-panel p-4">
      <div className="eyebrow">{label}</div>
      <div className={`num mt-1 text-2xl font-medium ${tone === 'good' ? 'text-good' : tone === 'bad' ? 'text-bad' : 'text-ink'}`}>{value}</div>
      {sub && <div className="mt-1 text-xs text-ink3">{sub}</div>}
    </div>
  );
}

function DecideTab({ id }: { id: string }) {
  const { data: _d, error, isLoading } = useApi<Row>(`/api/experiments/${id}`, { filters: false });
  const data: Row = _d ?? {};
  const [subDim, setSubDim] = useState('platform');
  if (error) return <Callout tone="bad" icon="alert" title="Experiment unavailable">{String((error as Error).message)}</Callout>;
  if (isLoading || !data.results) return <Skeleton className="h-96 w-full" />;
  const ex = data.experiment;
  const primary = (data.results as Row[]).find((r) => r.is_primary);
  const rec = data.recommendation;
  const dec = DECISION[rec?.decision ?? 'inconclusive'];

  return (
    <FocusTabs syncHash={false} tabs={[
      { id: 'verdict', label: 'The verdict', question: 'Did it work, and should we ship it?', render: () => (
        <div className="space-y-4">
          <Panel>
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div className="max-w-2xl">
                <h3 className="font-display text-xl font-semibold">{ex.name}</h3>
                <p className="mt-1 text-sm text-ink2">{ex.description}</p>
                <p className="mt-2 text-sm"><span className="eyebrow mr-2">Idea being tested</span><span className="text-ink2">{ex.hypothesis}</span></p>
              </div>
              <div className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm">
                <div><div className="eyebrow">Control (current)</div>{ex.control_label}</div>
                <div><div className="eyebrow">Test (new)</div>{ex.test_label}</div>
                <div><div className="eyebrow">Players joined</div>{fmtDateLong(ex.start_date)} – {fmtDateLong(ex.end_date)}</div>
                <div><div className="eyebrow">Main measure</div>{primary?.label}</div>
              </div>
            </div>
          </Panel>
          <Callout tone={dec.tone} icon={dec.icon} title={rec.headline}>{rec.text}</Callout>
          {primary && (
            <Grid cols={4}>
              <Big label="Control" value={fmtUnit(primary.unit, primary.control, primary.kind === 'proportion' ? 1 : 2)} sub={`n = ${fmtInt(primary.n_control)}`} />
              <Big label="Test" value={fmtUnit(primary.unit, primary.test, primary.kind === 'proportion' ? 1 : 2)} sub={`n = ${fmtInt(primary.n_test)}`} />
              <Big label="Difference" value={diffStr(primary)} sub={`${primary.rel_diff >= 0 ? '+' : '−'}${Math.abs(primary.rel_diff * 100).toFixed(1)}% relative · 95% range ${ciStr(primary)}`} tone={primary.significant ? (primary.abs_diff > 0 ? 'good' : 'bad') : undefined} />
              <Big label="Real difference?" value={primary.significant ? 'Yes' : 'Not shown'} sub={`${pStr(primary.p_value)} · threshold ${data.alpha}`} tone={primary.significant ? 'good' : undefined} />
            </Grid>
          )}
        </div>) },
      { id: 'kpis', label: 'Every number', question: 'How did every number move?', render: () => (
        <Panel sub="The main measure decides. The others are safety checks and context; their p-values are adjusted for looking at several at once.">
          <DataTable dense rows={data.results} columns={[
            { key: 'label', label: 'Measure', render: (r) => <span>{r.label}{r.is_primary && <span className="ml-2"><Badge tone="accent">main</Badge></span>}</span> },
            { key: 'control', label: 'Control', align: 'right', render: (r) => fmtUnit(r.unit, r.control, r.kind === 'proportion' ? 1 : 2) },
            { key: 'test', label: 'Test', align: 'right', render: (r) => fmtUnit(r.unit, r.test, r.kind === 'proportion' ? 1 : 2) },
            { key: 'abs_diff', label: 'Difference', align: 'right', render: (r) => <span className="whitespace-nowrap">{diffStr(r)}</span> },
            { key: 'rel_diff', label: 'Relative', align: 'right', render: (r) => (isNil(r.rel_diff) ? '–' : `${r.rel_diff >= 0 ? '+' : '−'}${Math.abs(r.rel_diff * 100).toFixed(1)}%`) },
            { key: 'ci', label: '95% range', sortValue: (r) => r.abs_diff, render: (r) => {
              const scale = Math.max(Math.abs(r.ci_low), Math.abs(r.ci_high)) * 1.25 || 1;
              return <div><CiBar low={r.ci_low} high={r.ci_high} value={r.abs_diff} scale={scale} /><div className="num text-[11px] text-ink3">{ciStr(r)}</div></div>;
            } },
            { key: 'p_adjusted', label: 'Real difference?', render: (r) => (
              <span className="whitespace-nowrap"><Badge tone={r.significant_adj ? (r.abs_diff * (r.higher_is_better ? 1 : -1) > 0 ? 'good' : 'bad') : 'neutral'} icon={r.significant_adj ? 'check' : undefined}>{r.significant_adj ? 'yes' : 'no'}</Badge> <span className="num text-[11px] text-ink3">{pStr(r.p_adjusted)}</span></span>
            ) },
          ]} />
        </Panel>) },
      { id: 'subgroups', label: 'Every kind of player', question: 'Does it hold for every kind of player?', render: () => (
        <Panel sub="For context only: small groups are noisy, and the more you slice the more false positives appear. P-values are adjusted across the groups shown."
          right={<Pill label="Split by" value={subDim} onChange={setSubDim} options={[{ value: 'platform', label: 'Platform' }, { value: 'country', label: 'Country' }, { value: 'source', label: 'Source' }]} />}>
          <DataTable dense rows={data.subgroups?.[subDim] ?? []} defaultSort={{ key: 'n', desc: true }} columns={[
            { key: subDim, label: subDim.charAt(0).toUpperCase() + subDim.slice(1) },
            { key: 'n', label: 'Players (control / test)', align: 'right', sortValue: (r) => r.n_control + r.n_test, render: (r) => `${fmtInt(r.n_control)} / ${fmtInt(r.n_test)}` },
            { key: 'control', label: 'Control', align: 'right', render: (r) => fmtUnit(primary?.unit, r.control, primary?.kind === 'proportion' ? 1 : 2) },
            { key: 'test', label: 'Test', align: 'right', render: (r) => fmtUnit(primary?.unit, r.test, primary?.kind === 'proportion' ? 1 : 2) },
            { key: 'abs_diff', label: 'Difference', align: 'right', render: (r) => <span className="whitespace-nowrap">{diffStr({ ...r, kind: primary?.kind, unit: primary?.unit })}</span> },
            { key: 'p_adjusted', label: 'Adjusted p', align: 'right', render: (r) => <span className="whitespace-nowrap">{r.significant_adj ? <Badge tone="good" icon="check">{pStr(r.p_adjusted).replace('p ', '')}</Badge> : pStr(r.p_adjusted).replace('p ', '')}</span> },
          ]} />
        </Panel>) },
      { id: 'trust', label: 'Can we trust it?', question: 'Can we trust this result?', render: () => (
        <Panel sub="Things that can quietly invalidate an A/B test">
          <ul className="space-y-4 text-sm text-ink2">
            <li className="flex items-start gap-2"><Badge tone={data.sample.srm_ok ? 'good' : 'bad'} icon={data.sample.srm_ok ? 'check' : 'alert'}>{data.sample.srm_ok ? 'passed' : 'failed'}</Badge>
              <span><b className="text-ink">Are the groups the right size?</b> {fmtInt(data.sample.control)} control vs {fmtInt(data.sample.test)} test, against an even split (p = {data.sample.srm_p_value.toFixed(3)}; a problem below 0.001).</span></li>
            <li className="flex items-start gap-2"><Badge tone="neutral" icon="info">size</Badge>
              <span><b className="text-ink">Could it detect a small improvement?</b> With this many players the main measure can reliably detect about {primary?.kind === 'proportion' ? `${primary.mde.toFixed(1)} points` : fmtUnit(primary?.unit, primary?.mde, 2)}. “Not shown” below that size means <i>unknown</i>, not <i>no effect</i>.</span></li>
            <li className="flex items-start gap-2"><Badge tone="neutral" icon="info">timing</Badge><span><b className="text-ink">Fair time windows.</b> {data.sample.note}</span></li>
          </ul>
        </Panel>) },
    ]} />
  );
}

const TABS = [
  { value: 'decide', label: 'Read results' },
  { value: 'monitor', label: 'Monitor' },
  { value: 'plan', label: 'Plan a test' },
];

function Hub() {
  const sp = useSearchParams();
  const list = useApi<{ experiments: Row[] }>('/api/experiments', { filters: false });
  const [tab, setTab] = useState(TABS.some((t) => t.value === sp.get('tab')) ? (sp.get('tab') as string) : 'decide');
  const [sel, setSel] = useState('');
  const id = sel || list.data?.experiments?.[0]?.experiment_id;
  const num = (k: string) => (sp.get(k) != null && !Number.isNaN(Number(sp.get(k))) ? Number(sp.get(k)) : undefined);

  return (
    <>
      <PageHeader eyebrow="Measure before you ship" title="Test an idea"
        desc="Before you ship a change, try it on part of your players. Plan a test, watch it while it runs, then read the result without fooling yourself."
        right={<Pill label="What do you want to do?" value={tab} onChange={setTab} options={TABS} />} />
      <p className="mb-4 text-sm text-ink2">
        {tab === 'plan' && <><b className="text-ink">Before launch:</b> how many players and how long? What rules should everyone agree on in advance?</>}
        {tab === 'monitor' && <><b className="text-ink">While a test runs:</b> is it healthy, and can you trust an early result?</>}
        {tab === 'decide' && <><b className="text-ink">After a test ends:</b> did it work, how sure are we, and should we ship?</>}
      </p>
      {tab !== 'plan' && list.data && (
        <div className="mb-4 flex flex-wrap items-center gap-2">
          <span className="eyebrow">Test</span>
          <Pill label="Experiment" value={id ?? ''} onChange={setSel} options={list.data.experiments.map((e) => ({ value: e.experiment_id, label: e.name }))} />
        </div>
      )}
      {tab !== 'plan' && list.data && list.data.experiments.length === 0 && (
        <Callout tone="neutral" icon="info" title="This dataset has no experiments yet">
          To read or monitor an A/B test, import an experiments file (player id, experiment name, control/test) on the <a href="/import" className="font-medium text-accent underline underline-offset-2">Import data</a> page.
          You can still <button className="font-medium text-accent underline underline-offset-2" onClick={() => setTab('plan')}>plan a new test</button>.
        </Callout>
      )}
      {tab === 'decide' && id && <DecideTab key={id} id={id} />}
      {tab === 'monitor' && id && <ExperimentMonitor key={id} id={id} />}
      {tab === 'plan' && <PlanTest initial={{ kpi: sp.get('kpi') ?? undefined, baseline: num('baseline'), daily: num('daily'), lift: num('lift'), label: sp.get('label') ?? undefined }} />}
    </>
  );
}

export default function ExperimentsPage() {
  return (
    <Suspense fallback={<Skeleton className="h-96 w-full" />}>
      <Hub />
    </Suspense>
  );
}
