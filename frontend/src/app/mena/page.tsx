'use client';
import { Fragment, useState } from 'react';
import { useApi, Row } from '@/lib/api';
import { BarsH, BarsV, LineChartX, ShareBars } from '@/components/charts';
import { FocusTabs } from '@/components/FocusTabs';
import { Callout, DataTable, PageHeader, Panel, Pill } from '@/components/ui';
import { fmtDate, fmtInt, fmtNum, fmtPct, fmtUnit, isNil } from '@/lib/format';
import { MENA_COLOR, PLATFORM_COLOR, SEGMENT_COLOR, SERIES, SOURCE_COLOR } from '@/lib/colors';

/** Index cell: 100 = MENA average. Colour is paired with the number and an arrow, never colour alone. */
function IndexCell({ v, hib }: { v: number | null; hib: boolean }) {
  if (isNil(v)) return <span className="text-ink3">–</span>;
  const diff = v - 100;
  const good = hib ? diff > 5 : diff < -5;
  const bad = hib ? diff < -5 : diff > 5;
  const mix = Math.min(Math.abs(diff) / 40, 1) * 55;
  const bg = good ? `color-mix(in srgb, var(--good) ${mix}%, transparent)` : bad ? `color-mix(in srgb, var(--bad) ${mix}%, transparent)` : 'transparent';
  return <span title="Index: 100 = MENA average" className="num inline-block min-w-[48px] rounded px-1.5 py-0.5 text-right" style={{ background: bg }}>{Math.round(v)}{good ? ' ▲' : bad ? ' ▼' : ''}</span>;
}

function useMena() {
  const { data: _d, error, isLoading, mutate } = useApi<Row>('/api/mena');
  const data: Row = _d ?? {};
  return { data, error, isLoading, mutate, rows: (data.rows ?? []) as Row[], countries: (data.countries ?? []) as string[] };
}

function Scorecard() {
  const { data, error, isLoading, mutate, rows, countries } = useMena();
  const spec: Row[] = data.scorecard_spec ?? [];
  return (
    <Panel
      loading={isLoading} error={error} onRetry={() => mutate()} empty={!rows.length}>
      <div className="overflow-x-auto">
        <table className="data">
          <thead><tr><th>Measure</th><th className="n">MENA</th>{countries.map((c) => <th key={c} className="n">{c}</th>)}</tr></thead>
          <tbody>
            {['Retention', 'Engagement', 'Monetization'].map((g) => (
              <Fragment key={g}>
                <tr><td colSpan={countries.length + 2} className="eyebrow !border-0 !pb-1 !pt-4">{g}</td></tr>
                {spec.filter((s) => s.group === g).map((s) => (
                  <tr key={s.key}>
                    <td>{s.label}</td>
                    <td className="n num text-ink2">{fmtUnit(s.unit, data.region[s.key])}</td>
                    {rows.map((r) => (
                      <td key={r.country} className="n">
                        <div className="num text-[13px]">{fmtUnit(s.unit, r.metrics[s.key].value)}</div>
                        <IndexCell v={r.metrics[s.key].index} hib={s.higher_is_better} />
                      </td>
                    ))}
                  </tr>
                ))}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>
    </Panel>
  );
}

function RetentionView() {
  const { data, error, isLoading, mutate, rows, countries } = useMena();
  const [v, setV] = useState('now');
  const merge = rows.map((r) => ({ country: r.country, D1: r.metrics.d1.value, D7: r.metrics.d7.value, D30: r.metrics.d30.value }));
  return (
    <Panel title={v === 'now' ? 'D1, D7 and D30 by market' : 'D7 by install week'}
      right={<Pill label="View" value={v} onChange={setV} options={[{ value: 'now', label: 'By market' }, { value: 'trend', label: 'Over time' }]} />}
      loading={isLoading} error={error} onRetry={() => mutate()} empty={!rows.length}>
      {v === 'now' ? (
        <BarsV data={merge} xKey="country" fmt={(x) => fmtPct(x, 0)} height={320}
          bars={[{ key: 'D1', name: 'D1', color: SERIES[0] }, { key: 'D7', name: 'D7', color: SERIES[1] }, { key: 'D30', name: 'D30', color: SERIES[2] }]} />
      ) : (
        <LineChartX data={data.d7_trend ?? []} xKey="week" xFmt={fmtDate} fmt={(x) => fmtPct(x, 0)} height={320} yDomain={[0, 'auto']}
          series={countries.map((c) => ({ key: c, name: c, color: MENA_COLOR[c], width: 2 }))} />
      )}
    </Panel>
  );
}

function EngagementMoney() {
  const { isLoading, error, mutate, rows } = useMena();
  const [m, setM] = useState('arpu');
  const opts: Record<string, { label: string; fmt: (v: number | null | undefined) => string }> = {
    arpu: { label: 'Revenue per player (ARPU)', fmt: (v) => `$${fmtNum(v, 2)}` },
    conversion: { label: 'Share who pay', fmt: (v) => fmtPct(v, 1) },
    sessions_per_player: { label: 'Sessions per player', fmt: (v) => fmtNum(v, 1) },
    avg_session_minutes: { label: 'Session length (min)', fmt: (v) => fmtNum(v, 1) },
  };
  return (
    <Panel title={opts[m].label} right={<Pill label="Measure" value={m} onChange={setM} options={Object.entries(opts).map(([value, o]) => ({ value, label: o.label.split(' (')[0] }))} />}
      loading={isLoading} error={error} onRetry={() => mutate()} empty={!rows.length}>
      <BarsH data={rows.map((r) => ({ name: r.country, value: r.metrics[m].value, color: MENA_COLOR[r.country] }))} fmt={opts[m].fmt} labelWidth={96} rowHeight={42} />
    </Panel>
  );
}

function MakeUp() {
  const { data, isLoading, error, mutate, rows } = useMena();
  const [v, setV] = useState('sources');
  const cfg: Record<string, { rows: Row[]; parts: { key: string; name: string; color: string }[] }> = {
    sources: { rows: data.sources ?? [], parts: Object.keys(SOURCE_COLOR).map((s) => ({ key: s, name: s, color: SOURCE_COLOR[s] })) },
    platforms: { rows: data.platforms ?? [], parts: Object.keys(PLATFORM_COLOR).map((s) => ({ key: s, name: s, color: PLATFORM_COLOR[s] })) },
    segments: { rows: data.segments ?? [], parts: Object.keys(SEGMENT_COLOR).map((s) => ({ key: s, name: s.replace(' Players', ''), color: SEGMENT_COLOR[s] })) },
  };
  return (
    <Panel title="What each market is made of" sub="Each bar sums to 100%"
      right={<Pill label="Break down by" value={v} onChange={setV} options={[{ value: 'sources', label: 'Sources' }, { value: 'platforms', label: 'Platforms' }, { value: 'segments', label: 'Player groups' }]} />}
      loading={isLoading} error={error} onRetry={() => mutate()} empty={!rows.length}>
      <ShareBars rows={cfg[v].rows} nameKey="country" parts={cfg[v].parts} height={360} />
    </Panel>
  );
}

function Leaders() {
  const { data, isLoading, error, mutate } = useMena();
  return (
    <Panel title="Best and weakest market for each measure" loading={isLoading} error={error} onRetry={() => mutate()} empty={!data.leaders?.length}>
      <DataTable dense rows={data.leaders ?? []} columns={[
        { key: 'label', label: 'Measure' },
        { key: 'best', label: 'Best market', render: (r) => <span>{r.best.country} <span className="num text-ink3">{fmtUnit(r.unit, r.best.value)}</span></span> },
        { key: 'worst', label: 'Weakest market', render: (r) => <span>{r.worst.country} <span className="num text-ink3">{fmtUnit(r.unit, r.worst.value)}</span></span> },
      ]} />
    </Panel>
  );
}

export default function MenaPage() {
  const { data } = useMena();
  return (
    <>
      <PageHeader eyebrow="Regional markets" title="MENA market comparison" />
      {data.window && <p className="text-xs text-ink3">Window {data.window.from} to {data.window.to}. {data.window.note}</p>}
      {data.available === false ? (
        <div className="mt-6"><Callout tone="neutral" icon="info" title="This comparison does not apply to the loaded data">{data.reason}</Callout></div>
      ) : (
      <div className="mt-6">
        <FocusTabs tabs={[
          { id: 'scorecard', label: 'Scorecard', question: 'How do the six markets compare overall?', render: () => <Scorecard /> },
          { id: 'retention', label: 'Retention', question: 'Which markets keep their players?', render: () => <RetentionView /> },
          { id: 'money', label: 'Engagement & money', question: 'Which markets play and pay the most?', render: () => <EngagementMoney /> },
          { id: 'makeup', label: 'Make-up', question: 'What is each market made of?', render: () => <MakeUp /> },
          { id: 'leaders', label: 'Best & weakest', question: 'Where is each market strongest and weakest?', render: () => <Leaders /> },
        ]} />
      </div>
      )}
    </>
  );
}
