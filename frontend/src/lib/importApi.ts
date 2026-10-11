// Thin client for /api/import/* (the browser never talks to the database directly).

export interface InspectedFile {
  filename: string;
  rows: number;
  columns: string[];
  separator?: string;
  table: string | null;
  mapping: Record<string, string | null>;
  mappings: Record<string, Record<string, string | null>>; // target-column mapping for EVERY table type
  preview: string[][];
  error?: string;
}
export interface TableInfo { value: string; label: string; required: string[]; columns: string[] }
export interface UploadResponse { session_id: string; files: InspectedFile[]; tables: TableInfo[] }
export interface Spec { filename: string; table: string; mapping: Record<string, string | null> }
export interface Validation { ok: boolean; errors: string[]; warnings: string[]; stats: Record<string, any> }
export interface Job {
  id: string; kind: 'import' | 'demo'; state: 'queued' | 'running' | 'done' | 'error'; step: string; progress: number;
  errors: string[]; warnings: string[]; summary: Record<string, any>; seconds: number;
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(path, init);
  if (!r.ok) {
    let detail = '';
    try { detail = (await r.json()).detail ?? ''; } catch { /* not json */ }
    throw new Error(detail || `${r.status} ${r.statusText}`);
  }
  return r.json();
}
const json = (body: unknown): RequestInit => ({ method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });

export const getImportState = () => call<{ allowed: boolean; busy: boolean; job: Job | null }>('/api/import/state');

export function uploadFiles(files: File[]) {
  const fd = new FormData();
  files.forEach((f) => fd.append('files', f, f.name));
  return call<UploadResponse>('/api/import/upload', { method: 'POST', body: fd });
}
export const validateImport = (session_id: string, files: Spec[], options: Record<string, unknown>) =>
  call<Validation>('/api/import/validate', json({ session_id, files, options }));
export const runImport = (session_id: string, files: Spec[], options: Record<string, unknown>) =>
  call<{ job_id: string }>('/api/import/run', json({ session_id, files, options }));
export const startDemo = (players: number) => call<{ job_id: string }>('/api/import/demo', json({ players }));
export const getJob = (id: string) => call<Job>(`/api/import/status/${id}`);
