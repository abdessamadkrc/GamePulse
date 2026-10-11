'use client';
import { useApi, Row } from '@/lib/api';
import { BarsV, LineChartX } from './charts';
import { FocusTabs } from './FocusTabs';
import { Badge, Callout, Grid, KpiCard, Panel } from './ui';
import { fmtDate, fmtDateLong, fmtInt, fmtPct, fmtPpRaw, fmtUnit } from '@/lib/format';
import { SERIES } from '@/lib/colors';

const pStr = (p: number | null | undefined) => (p == null ? '–' : p < 0.0001 ? '< 0.0001' : p < 0.01 ? p.toFixed(4) : p.toFixed(3));
const fmtNum2 = (v: number) => v.toFixed(2);

/** Watch a test while it runs: cumulative lift, sample balance, peeking and novelty checks, one view at a time. */
export default function ExperimentMonitor({ id }: { id: string }) {
  const { data, error, isLoading, mutate } = useApi<Row>(`/api/experiments/${id}/timeline`, { filters: false });
  const isProp = data?.kind === 'proportion';
  const scale = isProp ? 100 : 1;
  const pts: Row[] = data?.points ?? [];
  const checked = pts.filter((p) => p.diff != null);
  const last = checked[checked.length - 1];
  const chartRows = pts.map((p) => ({
    date: p.date,
    diff: p.diff != null ? p.diff * scale : null,
    ci_low: p.ci_low != null ? p.ci_low * scale : null,
    ci_high: p.ci_high != null ? p.ci_high * scale : null,
  }));
  const unitFmt = (v: number | null | undefined) => (v == null ? '–' : isProp ? `${v.toFixed(1)} pp` : fmtUnit(data?.unit, v, 2));
  const lift: Row[] = (data?.lift_by_day ?? []).map((r: Row) => ({
    day: r.day, rel: r.rel_lift != null ? r.rel_lift * 100 : null,
    lo: r.rel_ci_low != null ? r.rel_ci_low * 100 : null, hi: r.rel_ci_high != null ? r.rel_ci_high * 100 : null,
  }));
  const pk = data?.peeking;
  const common = { loading: isLoading, error, onRetry: () => mutate() };

  if (error) return <Callout tone="bad" icon="alert" title="Timeline unavailable">{String((error as Error).message)}</Callout>;
  return (
    <>
      <Grid cols={4}>
        <KpiCard label={`Lift so far (${data?.kpi ?? '…'})`} loading={isLoading} value={last ? unitFmt(last.diff * scale) : '–'}
          sub={last ? `95% range ${unitFmt(last.ci_low * scale)} to ${unitFmt(last.ci_high * scale)}` : undefined} term="95% interval" />
        <KpiCard label="Is it a real difference?" loading={isLoading} value={last ? (last.significant ? 'Yes' : 'Not yet') : '–'} sub={last ? `p ${pStr(last.p_value)}` : undefined} term="Statistically significant" />
        <KpiCard label="Players enrolled" loading={isLoading} value={last ? fmtInt(last.n_control + last.n_test) : '–'} sub={last ? `${fmtInt(last.n_control)} control / ${fmtInt(last.n_test)} test` : undefined} />
        <KpiCard label="Groups the right size?" loading={isLoading} value={last ? (last.srm_p >= 0.001 ? 'Yes' : 'NO') : '–'} sub={last ? `p ${pStr(last.srm_p)} (a problem below 0.001)` : undefined} term="Sample-ratio mismatch (SRM)" />
      </Grid>
      <div className="mt-6">
        <FocusTabs syncHash={false} tabs={[
          { id: 'lift', label: 'Lift over time', question: 'How big is the difference, and how sure are we?', render: () => (
            <Panel sub="Test minus control, recalculated each enrolment day from everyone enrolled so far. A band that crosses 0 means the groups are not yet separable."
              empty={!checked.length} {...common}>
              <LineChartX data={chartRows} xKey="date" xFmt={fmtDate} fmt={(v) => (v == null ? '–' : isProp ? `${v.toFixed(0)} pp` : fmtNum2(v))} height={320} zero
                series={[
                  { key: 'diff', name: 'Lift (test − control)', color: SERIES[0], width: 2.5 },
                  { key: 'ci_high', name: 'Upper 95%', color: SERIES[0], dashed: true, width: 1.2, muted: true },
                  { key: 'ci_low', name: 'Lower 95%', color: SERIES[0], dashed: true, width: 1.2, muted: true },
                ]} />
            </Panel>) },
          { id: 'peek', label: 'Can I trust an early look?', question: 'Would stopping early have been safe?', render: () => (
            <Panel term="Peeking" {...common}>
              {pk && (
                <div className="space-y-3 text-sm">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge tone={pk.significance_flips ? 'warn' : 'neutral'} icon="alert">{pk.significance_flips ? `Flipped ${pk.significance_flips} time(s)` : 'Stable'}</Badge>
                    <span className="text-ink">{pk.text}</span>
                  </div>
                  {pk.first_significant_date && (
                    <p className="text-ink2">It first looked significant on <b className="text-ink">{fmtDateLong(pk.first_significant_date)}</b>, with only <b className="text-ink">{fmtPct(pk.enrolled_pct_at_first_significant, 0)}</b> of the players enrolled. Stopping there would have been a bet on early noise: decide only at the planned sample size.</p>
                  )}
                </div>
              )}
            </Panel>) },
          { id: 'balance', label: 'Group sizes', question: 'Are the two groups the same size every day?', render: () => (
            <Panel sub="Control and test should track each other. A persistent gap points to an assignment bug." empty={!data?.daily_enrolment?.length} {...common}>
              <BarsV data={data?.daily_enrolment ?? []} xKey="date" xFmt={fmtDate} stacked height={300} fmt={fmtInt}
                bars={[{ key: 'control', name: 'Control', color: SERIES[1] }, { key: 'test', name: 'Test', color: SERIES[0] }]} />
            </Panel>) },
          { id: 'fade', label: 'Does it fade?', question: 'Does the improvement fade as players get used to it?', render: () => (
            <Panel term="Novelty effect" sub="Retention of test ÷ control − 1 on each day after install. A true novelty effect shrinks over time. (The absolute gap always shrinks as retention decays, so it is not used.)"
              empty={!lift.length} {...common}>
              <LineChartX data={lift} xKey="day" xFmt={(v) => `D${v}`} fmt={(v) => (v == null ? '–' : `${v.toFixed(0)}%`)} height={300} zero
                series={[{ key: 'rel', name: 'Relative lift', color: SERIES[2], width: 2.5 },
                  { key: 'hi', name: 'Upper 95%', color: SERIES[2], dashed: true, width: 1.2, muted: true },
                  { key: 'lo', name: 'Lower 95%', color: SERIES[2], dashed: true, width: 1.2, muted: true }]} />
              {data?.fade && (
                <p className={`mt-3 text-sm ${data.fade.flag ? 'text-warn' : 'text-ink2'}`}>
                  <span className="num">{fmtPpRaw(data.fade.early_rel * 100, 0).replace(' pp', '%')}</span> early (days 1–3) vs <span className="num">{fmtPpRaw(data.fade.late_rel * 100, 0).replace(' pp', '%')}</span> late (days 10–14). {data.fade.text}
                </p>
              )}
            </Panel>) },
        ]} />
      </div>
    </>
  );
}
