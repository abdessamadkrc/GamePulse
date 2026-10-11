'use client';
import { useEffect, useRef, useState } from 'react';
import { useFilters, Preset } from '@/lib/filters';
import { Icon } from './ui';
import { fmtDate } from '@/lib/format';

function MultiSelect({ label, options, value, onChange }: { label: string; options: string[]; value: string[]; onChange: (v: string[]) => void }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const h = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false); };
    document.addEventListener('mousedown', h);
    return () => document.removeEventListener('mousedown', h);
  }, []);
  const active = value.length > 0;
  return (
    <div ref={ref} className="relative">
      <button onClick={() => setOpen((o) => !o)} aria-expanded={open} aria-haspopup="listbox"
        className={`flex items-center gap-1.5 rounded-md border px-2.5 py-1.5 text-xs ${active ? 'border-accent/60 bg-accent/10 text-ink' : 'border-line bg-panel text-ink2 hover:text-ink'}`}>
        {label}{active && <span className="num rounded bg-accent px-1 text-[10px] text-white">{value.length}</span>}
        <Icon name="chevron" size={12} />
      </button>
      {open && (
        <div role="listbox" aria-multiselectable className="absolute left-0 top-full z-30 mt-1 max-h-72 w-56 overflow-auto rounded-md border border-line bg-panel p-1 shadow-xl">
          {options.map((o) => {
            const on = value.includes(o);
            return (
              <label key={o} className="flex cursor-pointer items-center gap-2 rounded px-2 py-1.5 text-xs text-ink hover:bg-panel2">
                <input type="checkbox" checked={on} className="accent-[var(--accent)]"
                  onChange={() => onChange(on ? value.filter((v) => v !== o) : [...value, o])} />
                {o}
              </label>
            );
          })}
          {active && <button onClick={() => onChange([])} className="mt-1 w-full rounded px-2 py-1 text-left text-xs text-accent hover:bg-panel2">Clear</button>}
        </div>
      )}
    </div>
  );
}

function SingleSelect({ label, options, value, onChange }: { label: string; options: string[]; value: string; onChange: (v: string) => void }) {
  return (
    <label className={`flex items-center gap-1 rounded-md border px-2 py-1 text-xs ${value ? 'border-accent/60 bg-accent/10' : 'border-line bg-panel'}`}>
      <span className="sr-only">{label}</span>
      <select value={value} onChange={(e) => onChange(e.target.value)} className="bg-transparent py-0.5 text-xs text-ink2 outline-none">
        <option value="">{label}: all</option>
        {options.map((o) => <option key={o} value={o} className="bg-panel text-ink">{o}</option>)}
      </select>
    </label>
  );
}

const PRESETS: { id: Preset; label: string }[] = [
  { id: '28', label: 'Last 28 days' }, { id: '56', label: '56 days' }, { id: '90', label: '90 days' }, { id: 'all', label: 'All time' },
];

function list(values: string[], noun: string) {
  if (!values.length) return `All ${noun}`;
  return values.length <= 2 ? values.join(', ') : `${values.length} ${noun}`;
}

/** One line by default ("what am I looking at?"); expands to the full controls on demand. */
export default function FilterBar({ segmentLocked, hideDates }: { segmentLocked?: boolean; hideDates?: boolean }) {
  const { state, set, setPreset, reset, meta, activeCount } = useFilters();
  const [open, setOpen] = useState(false);
  const o = meta?.options;
  const preset = PRESETS.find((p) => p.id === state.preset);
  const dateText = hideDates ? 'Install cohorts: set on this page'
    : state.dateFrom ? `${preset?.id === 'all' ? 'All time' : preset?.id === 'custom' ? 'Custom dates' : preset?.label} · ${fmtDate(state.dateFrom)} – ${fmtDate(state.dateTo)}` : 'Loading…';
  const changed = activeCount > 0 || (!hideDates && state.preset !== '28');

  return (
    <div className="mb-5 rounded-lg border border-line bg-panel/90 backdrop-blur">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 px-3 py-2">
        <span className="eyebrow flex items-center gap-1"><Icon name="filter" size={12} /> Showing</span>
        <span className="text-sm text-ink">{dateText}</span>
        <span className="text-ink3">·</span>
        <span className={`text-sm ${state.countries.length ? 'text-ink' : 'text-ink2'}`}>{list(state.countries, 'countries')}</span>
        <span className="text-ink3">·</span>
        <span className={`text-sm ${state.platforms.length ? 'text-ink' : 'text-ink2'}`}>{list(state.platforms, 'platforms')}</span>
        <span className="text-ink3">·</span>
        <span className={`text-sm ${state.sources.length ? 'text-ink' : 'text-ink2'}`}>{list(state.sources, 'sources')}</span>
        {(state.gameMode || state.segment) && <><span className="text-ink3">·</span><span className="text-sm text-ink">{[state.gameMode, state.segment].filter(Boolean).join(', ')}</span></>}
        <div className="ml-auto flex items-center gap-2">
          {changed && <button onClick={reset} className="rounded-md px-2 py-1 text-xs text-accent hover:bg-panel2">Reset</button>}
          <button onClick={() => setOpen((v) => !v)} aria-expanded={open}
            className="flex items-center gap-1 rounded-md border border-line px-2.5 py-1 text-xs text-ink2 hover:bg-panel2 hover:text-ink">
            {open ? 'Hide filters' : 'Change filters'}<Icon name="chevron" size={12} className={open ? 'rotate-180' : ''} />
          </button>
        </div>
      </div>

      {open && (
        <div className="border-t border-line p-3">
          <div className="flex flex-wrap items-center gap-2">
            {!hideDates && (
              <>
                <div className="inline-flex rounded-md border border-line bg-panel2 p-0.5" role="group" aria-label="Date range">
                  {PRESETS.map((p) => (
                    <button key={p.id} onClick={() => setPreset(p.id)} aria-pressed={state.preset === p.id}
                      className={`rounded px-2 py-1 text-xs font-medium ${state.preset === p.id ? 'bg-panel text-ink shadow-sm' : 'text-ink3 hover:text-ink'}`}>
                      {p.label}
                    </button>
                  ))}
                </div>
                <div className="flex items-center gap-1 text-xs text-ink2">
                  <input type="date" aria-label="From date" value={state.dateFrom} min={meta?.date_min} max={state.dateTo || meta?.date_max}
                    onChange={(e) => set({ dateFrom: e.target.value, preset: 'custom' })}
                    className="num rounded-md border border-line bg-panel px-1.5 py-1 text-xs text-ink" />
                  <span>→</span>
                  <input type="date" aria-label="To date" value={state.dateTo} min={state.dateFrom} max={meta?.date_max}
                    onChange={(e) => set({ dateTo: e.target.value, preset: 'custom' })}
                    className="num rounded-md border border-line bg-panel px-1.5 py-1 text-xs text-ink" />
                </div>
                <span className="mx-1 hidden h-5 w-px bg-line md:block" />
              </>
            )}
            <MultiSelect label="Country" options={o?.countries ?? []} value={state.countries} onChange={(countries) => set({ countries })} />
            <MultiSelect label="Platform" options={o?.platforms ?? []} value={state.platforms} onChange={(platforms) => set({ platforms })} />
            <MultiSelect label="Source" options={o?.sources ?? []} value={state.sources} onChange={(sources) => set({ sources })} />
            <SingleSelect label="Game mode" options={o?.game_modes ?? []} value={state.gameMode} onChange={(gameMode) => set({ gameMode })} />
            <SingleSelect label="Player group" options={o?.segments ?? []} value={state.segment} onChange={(segment) => set({ segment })} />
          </div>
          <p className="mt-2 text-[11px] text-ink3">
            {hideDates
              ? 'This page sets its own install-cohort window; the other filters still apply.'
              : 'Retention counts players who installed inside the dates; activity and revenue count what happened inside them.'}
            {segmentLocked ? ' Player groups are a snapshot at the last day of data.' : ''}
          </p>
        </div>
      )}
    </div>
  );
}
