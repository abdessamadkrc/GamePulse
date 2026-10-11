'use client';
import useSWR from 'swr';
import { useFilters } from './filters';

export type Row = Record<string, any>;

export class ApiError extends Error {}

const fetcher = async (url: string) => {
  const r = await fetch(url);
  if (!r.ok) {
    let detail = '';
    try { detail = (await r.json()).detail ?? ''; } catch { /* ignore */ }
    throw new ApiError(`${r.status} ${r.statusText}${detail ? ` - ${detail}` : ''}`);
  }
  return r.json();
};

/** Fetch an endpoint, appending the global dashboard filters unless `filters: false`. */
export function useApi<T = any>(
  path: string,
  opts: { filters?: boolean; enabled?: boolean; params?: Record<string, string | number | undefined> } = {},
) {
  const { filters = true, enabled = true, params } = opts;
  const { qs, ready } = useFilters();
  const extra = new URLSearchParams();
  Object.entries(params ?? {}).forEach(([k, v]) => v !== undefined && v !== '' && extra.set(k, String(v)));
  const parts = [filters ? qs : '', extra.toString()].filter(Boolean).join('&');
  const key = !enabled || (filters && !ready) ? null : `${path}${parts ? (path.includes('?') ? '&' : '?') + parts : ''}`;
  return useSWR<T>(key, fetcher, { keepPreviousData: true, revalidateOnFocus: false, dedupingInterval: 30_000 });
}
