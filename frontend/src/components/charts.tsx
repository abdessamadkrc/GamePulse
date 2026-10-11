'use client';
import {
  Bar, BarChart, CartesianGrid, Cell, LabelList, Legend, Line, LineChart, ReferenceArea, ReferenceLine,
  ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis, ZAxis,
} from 'recharts';
import { fmtDate, fmtNum, fmtPct, isNil } from '@/lib/format';
import { SERIES } from '@/lib/colors';

type Fmt = (v: number | null | undefined) => string;
const axisLine = { stroke: 'var(--grid)' };

/* ------------------------------------------------------------------ tooltip */
function ChartTip({ active, payload, label, fmt, labelFmt }: any) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-md border border-line bg-panel px-3 py-2 text-xs shadow-lg">
      {label !== undefined && <div className="mb-1 font-medium text-ink">{labelFmt ? labelFmt(label) : String(label)}</div>}
      {payload.filter((p: any) => !isNil(p.value)).map((p: any, i: number) => (
        <div key={i} className="flex items-center justify-between gap-4 py-0.5">
          <span className="flex items-center gap-1.5 text-ink2">
            <span className="inline-block h-2 w-2 rounded-sm" style={{ background: p.color || p.fill || p.stroke }} />
            {p.name ?? p.dataKey}
          </span>
          <span className="num text-ink">{(p.payload?.__fmt?.[p.dataKey] ?? fmt ?? fmtNum)(p.value)}</span>
        </div>
      ))}
    </div>
  );
}

/* ------------------------------------------------------------------ line chart */
export interface LineSeries { key: string; name: string; color: string; dashed?: boolean; width?: number; muted?: boolean }

export function LineChartX({ data, xKey = 'date', series, fmt = fmtNum, height = 260, shade, yDomain, xFmt = fmtDate, legend, refLine, zero }: {
  data: any[]; xKey?: string; series: LineSeries[]; fmt?: Fmt; height?: number; shade?: { from: string; to: string };
  yDomain?: [number | 'auto' | 'dataMin', number | 'auto' | 'dataMax']; xFmt?: (s: string) => string; legend?: boolean;
  refLine?: { x: string; label: string }; zero?: boolean;
}) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
        <CartesianGrid vertical={false} stroke="var(--grid)" />
        {shade && <ReferenceArea x1={shade.from} x2={shade.to} fill="var(--accent)" fillOpacity={0.08} stroke="none" ifOverflow="hidden" />}
        {refLine && <ReferenceLine x={refLine.x} stroke="var(--ink-3)" strokeDasharray="3 3" label={{ value: refLine.label, fill: 'var(--ink-3)', fontSize: 11, position: 'insideTopLeft' }} />}
        {zero && <ReferenceLine y={0} stroke="var(--ink-3)" />}
        <XAxis dataKey={xKey} tickFormatter={xFmt} axisLine={axisLine} tickLine={false} minTickGap={36} />
        <YAxis tickFormatter={(v) => fmt(v)} axisLine={false} tickLine={false} width={52} domain={yDomain ?? ['auto', 'auto']} />
        <Tooltip content={<ChartTip fmt={fmt} labelFmt={xFmt} />} />
        {(legend ?? series.length > 1) && <Legend iconType="plainline" wrapperStyle={{ paddingTop: 6 }} />}
        {series.map((s) => (
          <Line key={s.key} type="monotone" dataKey={s.key} name={s.name} stroke={s.color} strokeWidth={s.width ?? 2}
            strokeDasharray={s.dashed ? '4 3' : undefined} strokeOpacity={s.muted ? 0.45 : 1} dot={false}
            activeDot={{ r: 4, stroke: 'var(--panel)', strokeWidth: 2 }} connectNulls />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}

/* ------------------------------------------------------------------ horizontal bars */
export interface BarDatum { name: string; value: number | null; color?: string; [k: string]: any }

export function BarsH({ data, fmt = fmtNum, color = 'var(--accent)', rowHeight = 30, labelWidth = 118, signed, highlight }: {
  data: BarDatum[]; fmt?: Fmt; color?: string; rowHeight?: number; labelWidth?: number; signed?: boolean; highlight?: string;
}) {
  const height = data.length * rowHeight + 16;
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} layout="vertical" margin={{ top: 0, right: 56, left: 0, bottom: 0 }} barCategoryGap={6}>
        <XAxis type="number" hide domain={signed ? ['dataMin', 'dataMax'] : [0, 'dataMax']} />
        <YAxis type="category" dataKey="name" width={labelWidth} axisLine={false} tickLine={false}
          tick={{ fill: 'var(--ink-2)', fontSize: 12 }} interval={0} />
        <Tooltip cursor={{ fill: 'var(--panel-2)' }} content={<ChartTip fmt={fmt} />} />
        {signed && <ReferenceLine x={0} stroke="var(--ink-3)" />}
        <Bar dataKey="value" name="Value" radius={[0, 4, 4, 0]} stroke="var(--panel)" strokeWidth={2}>
          {data.map((d, i) => (
            <Cell key={i} fill={d.color ?? color} fillOpacity={highlight && d.name !== highlight ? 0.45 : 1} />
          ))}
          <LabelList dataKey="value" position="right" formatter={(v: any) => fmt(v)} fill="var(--ink-2)" fontSize={11}
            className="num" />
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

/* ------------------------------------------------------------------ vertical (grouped / stacked) bars */
export interface BarSeries { key: string; name: string; color: string }

export function BarsV({ data, xKey, bars, fmt = fmtNum, height = 260, stacked, xFmt, legend = true, yDomain }: {
  data: any[]; xKey: string; bars: BarSeries[]; fmt?: Fmt; height?: number; stacked?: boolean; xFmt?: (s: string) => string; legend?: boolean;
  yDomain?: [number | 'auto', number | 'auto'];
}) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }} barCategoryGap={stacked ? '18%' : '24%'}>
        <CartesianGrid vertical={false} stroke="var(--grid)" />
        <XAxis dataKey={xKey} tickFormatter={xFmt} axisLine={axisLine} tickLine={false} interval={0}
          tick={{ fontSize: 11 }} minTickGap={8} />
        <YAxis tickFormatter={(v) => fmt(v)} axisLine={false} tickLine={false} width={50} domain={yDomain ?? [0, 'auto']} />
        <Tooltip cursor={{ fill: 'var(--panel-2)' }} content={<ChartTip fmt={fmt} labelFmt={xFmt} />} />
        {legend && bars.length > 1 && <Legend iconType="square" wrapperStyle={{ paddingTop: 6 }} />}
        {bars.map((b, i) => (
          <Bar key={b.key} dataKey={b.key} name={b.name} fill={b.color} stackId={stacked ? 's' : undefined}
            stroke="var(--panel)" strokeWidth={stacked ? 2 : 0}
            radius={stacked ? (i === bars.length - 1 ? [3, 3, 0, 0] : 0) : [3, 3, 0, 0]} />
        ))}
      </BarChart>
    </ResponsiveContainer>
  );
}

/** 100% stacked horizontal bars: one row per entity (e.g. country), segments = shares. */
export function ShareBars({ rows, nameKey, parts, height }: {
  rows: any[]; nameKey: string; parts: { key: string; name: string; color: string }[]; height?: number;
}) {
  return (
    <ResponsiveContainer width="100%" height={height ?? rows.length * 34 + 52}>
      <BarChart data={rows} layout="vertical" margin={{ top: 0, right: 12, left: 0, bottom: 0 }} barCategoryGap={8}>
        <XAxis type="number" domain={[0, 1]} tickFormatter={(v) => fmtPct(v, 0)} axisLine={false} tickLine={false} />
        <YAxis type="category" dataKey={nameKey} width={96} axisLine={false} tickLine={false} tick={{ fill: 'var(--ink-2)', fontSize: 12 }} interval={0} />
        <Tooltip cursor={{ fill: 'var(--panel-2)' }} content={<ChartTip fmt={(v: any) => fmtPct(v, 1)} />} />
        <Legend iconType="square" wrapperStyle={{ paddingTop: 4 }} />
        {parts.map((p) => (
          <Bar key={p.key} dataKey={p.key} name={p.name} stackId="s" fill={p.color} stroke="var(--panel)" strokeWidth={2} />
        ))}
      </BarChart>
    </ResponsiveContainer>
  );
}

/* ------------------------------------------------------------------ cohort heatmap */
export function CohortHeatmap({ days, rows }: { days: number[]; rows: { cohort: string; size: number; cells: Record<string, number | null> }[] }) {
  const max = 0.55;
  const style = (v: number | null | undefined) => {
    if (isNil(v)) return { background: 'transparent', color: 'var(--ink-3)' };
    const t = Math.min(v / max, 1);
    const pctMix = Math.round(8 + t * 82);
    return { background: `color-mix(in srgb, var(--seq-550) ${pctMix}%, var(--panel))`, color: pctMix > 52 ? '#fff' : 'var(--ink)' };
  };
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[640px] border-separate text-xs" style={{ borderSpacing: 2 }}>
        <thead>
          <tr>
            <th className="eyebrow p-1 text-left">Install week</th>
            <th className="eyebrow p-1 text-right">Players</th>
            {days.map((d) => <th key={d} className="eyebrow p-1 text-center">D{d}</th>)}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.cohort}>
              <td className="num whitespace-nowrap p-1 text-ink2">{fmtDate(r.cohort)}</td>
              <td className="num p-1 text-right text-ink3">{r.size.toLocaleString()}</td>
              {days.map((d) => {
                const v = r.cells[String(d)];
                return (
                  <td key={d} className="num rounded-sm p-1 text-center" style={style(v)}
                    title={isNil(v) ? 'Not enough elapsed time' : `Week of ${r.cohort}: D${d} retention ${fmtPct(v)}`}>
                    {isNil(v) ? '' : (v * 100).toFixed(0)}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
      <div className="mt-2 flex items-center gap-2 text-[11px] text-ink3">
        <span>Retention % of cohort active exactly N days after install</span>
        <span className="ml-auto inline-flex items-center gap-1">0%
          <span className="inline-block h-2 w-24 rounded" style={{ background: 'linear-gradient(90deg, color-mix(in srgb, var(--seq-550) 8%, var(--panel)), var(--seq-550))' }} />
          {Math.round(max * 100)}%+
        </span>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ scatter */
export function ClusterScatter({ points, colors }: { points: { x: number; y: number; cluster: string }[]; colors: Record<string, string> }) {
  const groups = Array.from(new Set(points.map((p) => p.cluster)));
  return (
    <ResponsiveContainer width="100%" height={300}>
      <ScatterChart margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
        <CartesianGrid stroke="var(--grid)" />
        <XAxis type="number" dataKey="x" name="PC1" axisLine={axisLine} tickLine={false} tickFormatter={(v) => fmtNum(v, 0)} />
        <YAxis type="number" dataKey="y" name="PC2" axisLine={false} tickLine={false} width={36} tickFormatter={(v) => fmtNum(v, 0)} />
        <ZAxis range={[28, 28]} />
        <Tooltip cursor={{ strokeDasharray: '3 3' }} content={<ChartTip fmt={(v: any) => fmtNum(v, 2)} />} />
        <Legend iconType="circle" />
        {groups.map((g, i) => (
          <Scatter key={g} name={g} data={points.filter((p) => p.cluster === g)} fill={colors[g] ?? SERIES[i % 8]} fillOpacity={0.65} />
        ))}
      </ScatterChart>
    </ResponsiveContainer>
  );
}

/** Horizontal CI whisker for experiment lifts (difference with 95% CI). */
export function CiBar({ low, high, value, scale }: { low: number; high: number; value: number; scale: number }) {
  const toPct = (v: number) => 50 + (v / scale) * 50;
  const l = Math.max(0, toPct(low)), h = Math.min(100, toPct(high)), m = Math.max(0, Math.min(100, toPct(value)));
  const good = low > 0, bad = high < 0;
  const color = good ? 'var(--good)' : bad ? 'var(--bad)' : 'var(--ink-3)';
  return (
    <div className="relative h-5 w-full min-w-[140px]" aria-label={`difference ${value}, interval ${low} to ${high}`}>
      <div className="absolute left-1/2 top-0 h-5 w-px bg-line" />
      <div className="absolute top-1/2 h-0.5 -translate-y-1/2 rounded" style={{ left: `${l}%`, width: `${Math.max(h - l, 1)}%`, background: color }} />
      <div className="absolute top-1/2 h-3 w-3 -translate-x-1/2 -translate-y-1/2 rounded-full border-2" style={{ left: `${m}%`, background: color, borderColor: 'var(--panel)' }} />
    </div>
  );
}


/* ------------------------------------------------------------------ generic heatmaps (Retention Explorer) */
const heatStyle = (v: number | null | undefined, max: number) => {
  if (isNil(v)) return { background: 'transparent', color: 'var(--ink-3)' };
  const t = Math.min(Math.max(v, 0) / max, 1);
  const mix = Math.round(8 + t * 82);
  return { background: `color-mix(in srgb, var(--seq-550) ${mix}%, var(--panel))`, color: mix > 52 ? '#fff' : 'var(--ink)' };
};

/** Rows = any cohort group, columns = day N. Same encoding as CohortHeatmap, label is free text. */
export function GroupHeatmap({ days, rows, rowHeader, labelFmt, max = 0.55, onlyFirstN }: {
  days: number[]; rows: { label: string; size: number; cells: Record<string, number | null> }[];
  rowHeader: string; labelFmt?: (s: string) => string; max?: number; onlyFirstN?: number;
}) {
  const shown = onlyFirstN ? rows.slice(0, onlyFirstN) : rows;
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[640px] border-separate text-xs" style={{ borderSpacing: 2 }}>
        <thead>
          <tr>
            <th className="eyebrow p-1 text-left">{rowHeader}</th>
            <th className="eyebrow p-1 text-right">Players</th>
            {days.map((d) => <th key={d} className="eyebrow p-1 text-center">D{d}</th>)}
          </tr>
        </thead>
        <tbody>
          {shown.map((r) => (
            <tr key={r.label}>
              <td className="whitespace-nowrap p-1 text-ink2">{labelFmt ? labelFmt(r.label) : r.label}</td>
              <td className="num p-1 text-right text-ink3">{r.size.toLocaleString()}</td>
              {days.map((d) => {
                const v = r.cells[String(d)];
                return (
                  <td key={d} className="num rounded-sm p-1 text-center" style={heatStyle(v, max)}
                    title={isNil(v) ? 'Not enough elapsed time' : `${r.label}: D${d} retention ${fmtPct(v)}`}>
                    {isNil(v) ? '' : (v * 100).toFixed(0)}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
      <div className="mt-2 flex items-center gap-2 text-[11px] text-ink3">
        <span>% of the group active exactly N days after install. Blank = group too young for that day.</span>
        <span className="ml-auto inline-flex items-center gap-1">0%
          <span className="inline-block h-2 w-24 rounded" style={{ background: 'linear-gradient(90deg, color-mix(in srgb, var(--seq-550) 8%, var(--panel)), var(--seq-550))' }} />
          {Math.round(max * 100)}%+
        </span>
      </div>
    </div>
  );
}

/** Rows = groups, columns = buckets, values are shares (each row sums to 100%). */
export function ShareHeatTable({ columns, rows, rowHeader, max = 0.4, labelFmt }: {
  columns: string[]; rows: { label: string; size: number; shares: number[] }[]; rowHeader: string; max?: number; labelFmt?: (s: string) => string;
}) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[640px] border-separate text-xs" style={{ borderSpacing: 2 }}>
        <thead>
          <tr>
            <th className="eyebrow p-1 text-left">{rowHeader}</th>
            <th className="eyebrow p-1 text-right">Players</th>
            {columns.map((c) => <th key={c} className="eyebrow p-1 text-center leading-tight">{c}</th>)}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.label}>
              <td className="whitespace-nowrap p-1 text-ink2">{labelFmt ? labelFmt(r.label) : r.label}</td>
              <td className="num p-1 text-right text-ink3">{r.size.toLocaleString()}</td>
              {r.shares.map((v, i) => (
                <td key={i} className="num rounded-sm p-1.5 text-center" style={heatStyle(v, max)} title={`${r.label}: ${fmtPct(v)} ${columns[i]}`}>
                  {(v * 100).toFixed(0)}%
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
