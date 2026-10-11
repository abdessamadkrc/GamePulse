'use client';
import { createContext, useContext, useEffect, useMemo, useRef, useState, ReactNode } from 'react';
import useSWR from 'swr';

export type Preset = '28' | '56' | '90' | 'all' | 'custom';

export interface FilterState {
  preset: Preset;
  dateFrom: string;
  dateTo: string;
  countries: string[];
  platforms: string[];
  sources: string[];
  gameMode: string;
  segment: string;
}

interface Ctx {
  state: FilterState;
  set: (patch: Partial<FilterState>) => void;
  setPreset: (p: Preset) => void;
  reset: () => void;
  qs: string;
  ready: boolean;
  meta: Record<string, any> | undefined;
  activeCount: number;
}

const FilterCtx = createContext<Ctx | null>(null);

const addDays = (iso: string, n: number) => {
  const d = new Date(iso + 'T00:00:00Z');
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
};

export function FilterProvider({ children }: { children: ReactNode }) {
  const { data: meta } = useSWR('/api/meta', (u: string) => fetch(u).then((r) => r.json()), { revalidateOnFocus: false });
  const [state, setState] = useState<FilterState>({
    preset: '28', dateFrom: '', dateTo: '', countries: [], platforms: [], sources: [], gameMode: '', segment: '',
  });

  // a different dataset (e.g. after an import) means the old dates and filters no longer make sense
  const signature = meta?.date_max ? `${meta.date_min}|${meta.date_max}|${meta.dataset?.counts?.players ?? ''}|${meta.dataset?.data_label ?? ''}` : '';
  const lastSignature = useRef('');
  useEffect(() => {
    if (!signature) return;
    if (lastSignature.current && lastSignature.current !== signature) {
      setState({ preset: '28', dateTo: meta!.date_max, dateFrom: addDays(meta!.date_max, -27), countries: [], platforms: [], sources: [], gameMode: '', segment: '' });
    }
    lastSignature.current = signature;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [signature]);

  useEffect(() => {
    if (meta?.date_max && !state.dateTo) {
      setState((s) => ({ ...s, dateTo: meta.date_max, dateFrom: addDays(meta.date_max, -27) }));
    }
  }, [meta, state.dateTo]);

  const value = useMemo<Ctx>(() => {
    const ready = Boolean(state.dateFrom && state.dateTo);
    const p = new URLSearchParams();
    if (ready) { p.set('date_from', state.dateFrom); p.set('date_to', state.dateTo); }
    state.countries.forEach((c) => p.append('country', c));
    state.platforms.forEach((c) => p.append('platform', c));
    state.sources.forEach((c) => p.append('source', c));
    if (state.gameMode) p.set('game_mode', state.gameMode);
    if (state.segment) p.set('segment', state.segment);
    const max = meta?.date_max as string | undefined;
    const min = meta?.date_min as string | undefined;
    return {
      state,
      ready,
      meta,
      qs: p.toString(),
      activeCount:
        state.countries.length + state.platforms.length + state.sources.length + (state.gameMode ? 1 : 0) + (state.segment ? 1 : 0),
      set: (patch) => setState((s) => ({ ...s, ...patch })),
      setPreset: (preset) => {
        if (!max || !min) return;
        if (preset === 'all') setState((s) => ({ ...s, preset, dateFrom: min, dateTo: max }));
        else if (preset !== 'custom') setState((s) => ({ ...s, preset, dateTo: max, dateFrom: addDays(max, -(Number(preset) - 1)) }));
        else setState((s) => ({ ...s, preset }));
      },
      reset: () =>
        setState((s) => ({
          ...s, preset: '28', countries: [], platforms: [], sources: [], gameMode: '', segment: '',
          dateTo: max ?? s.dateTo, dateFrom: max ? addDays(max, -27) : s.dateFrom,
        })),
    };
  }, [state, meta]);

  return <FilterCtx.Provider value={value}>{children}</FilterCtx.Provider>;
}

export function useFilters() {
  const c = useContext(FilterCtx);
  if (!c) throw new Error('useFilters outside FilterProvider');
  return c;
}
