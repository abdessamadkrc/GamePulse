'use client';
import { ReactNode, useEffect, useState } from 'react';
import { useApi, Row } from '@/lib/api';
import { LineChartX } from './charts';
import { Badge, Callout, DataTable, Grid, KpiCard, Panel, Skeleton } from './ui';
import { FocusTabs } from './FocusTabs';
import { fmtInt, fmtPct } from '@/lib/format';
import { SERIES } from '@/lib/colors';

export interface PlanInitial { kpi?: string; baseline?: number; daily?: number; lift?: number; label?: string }

const KPIS = [
  { value: 'd1', label: 'D1 retention' },
  { value: 'd7', label: 'D7 retention' },
  { value: 'd30', label: 'D30 retention' },
  { value: 'conversion_14d', label: 'Payer conversion (14 days)' },
];
const KPI_FROM_KPIS: Record<string, string> = { d1: 'd1', d7: 'd7', d30: 'd30', conversion_14d: 'conversion' };

function useDebounced<T>(value: T, ms = 400) {
  const [v, setV] = useState(value);
  useEffect(() => { const t = setTimeout(() => setV(value), ms); return () => clearTimeout(t); }, [value, ms]);
  return v;
}

function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <label className="block text-xs">
      <span className="eyebrow mb-1 block">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-[11px] text-ink3">{hint}</span>}
    </label>
  );
}
const inputCls = 'num w-full rounded-md border border-line bg-panel px-2.5 py-1.5 text-sm text-ink';

function planAsText(p: Row): string {
  const i = p.inputs, r = p.result, m = p.measurement_plan;
  return [
    `A/B TEST PLAN: ${i.kpi_label}`,
    `Baseline ${(i.baseline * 100).toFixed(1)}%, detect +${i.lift_pp} pp (target ${(r.target_rate * 100).toFixed(1)}%), power ${(i.power * 100).toFixed(0)}%, alpha ${i.alpha}`,
    `Sample: ${r.n_control.toLocaleString()} control + ${r.n_per_variant.toLocaleString()} per variant = ${r.total.toLocaleString()} players`,
    `Duration: ${r.enrol_days} days to enrol, readout on day ${r.readout_day} (at ${i.daily} eligible players/day, ${i.arms} arms)`,
    '', `PRIMARY KPI: ${m.primary_kpi}`, '', 'GUARDRAILS:', ...m.guardrails.map((g: string) => `- ${g}`),
    '', 'CHECKPOINTS:', ...m.checkpoints.map((c: Row) => `- Day ${c.day}: ${c.what}`),
    '', 'STOP RULES:', ...m.stop_rules.map((s: string) => `- ${s}`), '', `SHIP RULE: ${m.ship_rule}`,
  ].join('\n');
}

export default function PlanTest({ initial }: { initial: PlanInitial }) {
  const kpis = useApi<{ current: Row }>('/api/kpis', { filters: false });
  const [kpi, setKpi] = useState(initial.kpi && KPIS.some((k) => k.value === initial.kpi) ? initial.kpi : 'd7');
  const [baseline, setBaseline] = useState(initial.baseline != null ? String(+(initial.baseline * 100).toFixed(1)) : '');
  const [lift, setLift] = useState(String(initial.lift ?? 3));
  const [daily, setDaily] = useState(String(initial.daily != null ? Math.round(initial.daily) : 300));
  const [power, setPower] = useState('0.8');
  const [alpha, setAlpha] = useState('0.05');
  const [arms, setArms] = useState('2');
  const [share, setShare] = useState('50');
  const [copied, setCopied] = useState(false);

  // default the baseline to the platform's current rate until the user types one
  useEffect(() => {
    if (baseline === '' && kpis.data?.current) {
      const v = kpis.data.current[KPI_FROM_KPIS[kpi]];
      if (typeof v === 'number') setBaseline(String(+(v * 100).toFixed(1)));
    }
  }, [kpis.data, kpi, baseline]);

  const q = useDebounced({ kpi, baseline, lift, daily, power, alpha, arms, share });
  const b = parseFloat(q.baseline) / 100, l = parseFloat(q.lift), d = parseFloat(q.daily);
  const valid = b > 0.005 && b < 0.95 && l >= 0.2 && l <= 30 && d > 0 && b + l / 100 < 0.999;
  const { data, error, isLoading, mutate } = useApi<Row>('/api/experiments/plan', {
    filters: false, enabled: valid,
    params: { kpi: q.kpi, baseline: b, lift_pp: l, daily: d, power: q.power, alpha: q.alpha, arms: q.arms, test_share: parseFloat(q.share) / 100 },
  });
  const res = valid ? data?.result : undefined;

  return (
    <>
      {initial.label && (
        <div className="mb-4"><Callout tone="accent" icon="info" title={`Planning a test for: ${initial.label}`}>
          Baseline and daily traffic were prefilled from the Investigation. Check them against your own numbers.
        </Callout></div>
      )}
      <Panel title="Test design" sub="Change any input; the plan updates as you type.">
        <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
          <Field label="KPI">
            <select className={inputCls} value={kpi} onChange={(e) => { setKpi(e.target.value); setBaseline(''); }}>
              {KPIS.map((k) => <option key={k.value} value={k.value}>{k.label}</option>)}
            </select>
          </Field>
          <Field label="Baseline rate (%)" hint="Current value of the KPI for the players you will test">
            <input className={inputCls} inputMode="decimal" value={baseline} onChange={(e) => setBaseline(e.target.value)} />
          </Field>
          <Field label="Smallest lift worth detecting (pp)" hint="Percentage points over baseline">
            <input className={inputCls} inputMode="decimal" value={lift} onChange={(e) => setLift(e.target.value)} />
          </Field>
          <Field label="Eligible new players per day" hint="Who would enter the test">
            <input className={inputCls} inputMode="numeric" value={daily} onChange={(e) => setDaily(e.target.value)} />
          </Field>
          <Field label="Power">
            <select className={inputCls} value={power} onChange={(e) => setPower(e.target.value)}>
              <option value="0.8">80% (standard)</option><option value="0.9">90% (stricter)</option>
            </select>
          </Field>
          <Field label="Significance level (alpha)">
            <select className={inputCls} value={alpha} onChange={(e) => setAlpha(e.target.value)}>
              <option value="0.05">5% (standard)</option><option value="0.01">1% (stricter)</option>
            </select>
          </Field>
          <Field label="Arms (control + variants)">
            <select className={inputCls} value={arms} onChange={(e) => setArms(e.target.value)}>
              <option value="2">2: control + 1 test</option><option value="3">3: control + 2 tests</option><option value="4">4: control + 3 tests</option>
            </select>
          </Field>
          <Field label="Traffic to the test arm (%)" hint={arms === '2' ? 'Only for 2 arms' : 'Equal split with 3+ arms'}>
            <input className={inputCls} inputMode="numeric" disabled={arms !== '2'} value={arms === '2' ? share : String(Math.round(100 / Number(arms)))} onChange={(e) => setShare(e.target.value)} />
          </Field>
        </div>
        {!valid && baseline !== '' && <p className="mt-3 text-sm text-warn">Check the inputs: baseline 0.5–95%, lift 0.2–30 pp, and baseline + lift below 100%.</p>}
      </Panel>

      {error ? <div className="mt-4"><Callout tone="bad" icon="alert" title="Could not compute the plan">{String((error as Error).message)}</Callout></div> : (
        <>
          <div className="mt-4"><Grid cols={4}>
            <KpiCard label="Players per arm" loading={isLoading && !res} value={res ? fmtInt(res.n_control) : '–'} sub={res && data ? `${fmtInt(res.total)} in total` : undefined} />
            <KpiCard label="Days to enrol" loading={isLoading && !res} value={res ? fmtInt(res.enrol_days) : '–'} sub={res ? `at ${fmtInt(Number(daily))} players per day` : undefined} />
            <KpiCard label="Readout on day" loading={isLoading && !res} value={res ? fmtInt(res.readout_day) : '–'} sub={res ? 'enrolment + time for the KPI to mature' : undefined} hint="The last enrolee needs the KPI's full window before you can read it" />
            <KpiCard label="Detectable in 28 days" loading={isLoading && !res} value={res?.mde_28d_pp != null ? `${res.mde_28d_pp.toFixed(1)} pp` : '–'} sub="smallest lift a 4-week test could see" />
          </Grid></div>

          {(data?.warnings ?? []).map((w: string, i: number) => (
            <div className="mt-3" key={i}><Callout tone="warn" icon="alert">{w}</Callout></div>
          ))}

          <div className="mt-6">
            <FocusTabs syncHash={false} tabs={[
              { id: 'plan', label: 'The plan', question: 'What should we agree before launch?', render: () => (
                data?.measurement_plan ? (
                  <Panel sub="Agree this before launch, so nobody can choose the rules after seeing the result."
                    right={<button className="rounded-md border border-line px-2.5 py-1 text-xs text-accent hover:bg-panel2"
                      onClick={() => { navigator.clipboard?.writeText(planAsText(data)).then(() => { setCopied(true); setTimeout(() => setCopied(false), 1800); }).catch(() => undefined); }}>
                      {copied ? 'Copied' : 'Copy as text'}</button>}>
                    <div className="grid gap-5 md:grid-cols-2">
                      <div>
                        <div className="eyebrow mb-1">Main measure</div>
                        <p className="text-sm text-ink">{data.measurement_plan.primary_kpi}</p>
                        <div className="eyebrow mb-1 mt-4">Must not get worse</div>
                        <ul className="space-y-1 text-sm text-ink2">{data.measurement_plan.guardrails.map((g: string) => <li key={g}>• {g}</li>)}</ul>
                        <div className="eyebrow mb-1 mt-4">When to ship</div>
                        <p className="text-sm text-ink2">{data.measurement_plan.ship_rule}</p>
                      </div>
                      <div>
                        <div className="eyebrow mb-1">Checkpoints</div>
                        <ol className="space-y-2 text-sm">
                          {data.measurement_plan.checkpoints.map((c: Row) => (
                            <li key={c.day + c.what} className="flex gap-2"><Badge tone="accent">Day {c.day}</Badge><span className="text-ink2">{c.what}</span></li>
                          ))}
                        </ol>
                        <div className="eyebrow mb-1 mt-4">When to stop</div>
                        <ul className="space-y-1 text-sm text-ink2">{data.measurement_plan.stop_rules.map((s: string) => <li key={s}>• {s}</li>)}</ul>
                      </div>
                    </div>
                    <p className="mt-4 text-xs text-ink3">Target: {fmtPct(data.inputs.baseline)} → {fmtPct(res?.target_rate)} · {data.note}</p>
                  </Panel>
                ) : <Skeleton className="h-40 w-full" />) },
              { id: 'curve', label: 'Size vs. lift', question: 'How many players does a smaller improvement need?', render: () => (
                <Panel sub="Halving the improvement you want to detect roughly quadruples the players you need" loading={isLoading && !data} empty={!data?.curve?.length}>
                  <LineChartX data={data?.curve ?? []} xKey="lift" xFmt={(v) => `+${v} pp`} fmt={fmtInt} height={300}
                    series={[{ key: 'n_control', name: 'Players per group', color: SERIES[0] }]} />
                </Panel>) },
              { id: 'sens', label: 'Options', question: 'What if we aim for a different improvement?', render: () => (
                <Panel loading={isLoading && !data} empty={!data?.sensitivity?.length}>
                  <DataTable dense rows={data?.sensitivity ?? []} columns={[
                    { key: 'lift_pp', label: 'Improvement to detect', render: (r) => `+${r.lift_pp} pp` },
                    { key: 'n_control', label: 'Players per group', align: 'right', render: (r) => fmtInt(r.n_control) },
                    { key: 'total', label: 'Total players', align: 'right', render: (r) => fmtInt(r.total) },
                    { key: 'days', label: 'Days to enrol', align: 'right', render: (r) => fmtInt(r.days) },
                  ]} />
                </Panel>) },
            ]} />
          </div>
          <button className="sr-only" onClick={() => mutate()}>Refresh plan</button>
        </>
      )}
    </>
  );
}
