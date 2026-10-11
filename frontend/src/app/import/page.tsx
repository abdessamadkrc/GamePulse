'use client';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { DragEvent, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useSWRConfig } from 'swr';
import { useFilters } from '@/lib/filters';
import {
  getImportState, getJob, InspectedFile, Job, runImport, Spec, startDemo, TableInfo, uploadFiles, UploadResponse, validateImport, Validation,
} from '@/lib/importApi';
import { Badge, Callout, Icon, PageHeader, Panel, Skeleton } from '@/components/ui';
import { fmtInt } from '@/lib/format';

type Step = 'choose' | 'check' | 'importing' | 'done';
const STEPS: { id: Step; label: string }[] = [
  { id: 'choose', label: 'Choose files' }, { id: 'check', label: 'Check' }, { id: 'importing', label: 'Import' }, { id: 'done', label: 'Results' },
];

// Friendly names for the columns we look for.
const LABEL: Record<string, string> = {
  player_id: 'Player ID', country: 'Country', platform: 'Platform (Android, iOS…)', device: 'Device model', install_date: 'Install date',
  acquisition_source: 'Where the player came from', session_start: 'Session start time', session_duration_minutes: 'Session length',
  match_date: 'Match time', game_mode: 'Game mode', kills: 'Kills', placement: 'Placement / rank', match_duration_minutes: 'Match length', result: 'Win or loss',
  purchase_date: 'Purchase time', amount: 'Amount paid', item_type: 'Item bought', event_name: 'Event name', event_date: 'Event time',
  experiment_id: 'Experiment name / id', variant: 'Group (control or test)', assignment_date: 'Assignment date', device_tier: 'Device quality (low/mid/high)',
  name: 'Name', description: 'Description', hypothesis: 'Hypothesis', primary_kpi: 'Main measure', control_label: 'Control label', test_label: 'Test label',
  start_date: 'Start date', end_date: 'End date',
};
const HIDDEN = new Set(['session_id', 'match_id', 'purchase_id', 'event_id']); // we generate these ourselves

const CAPS: { key: string; label: string; needs: string }[] = [
  { key: 'always', label: 'Overview, retention, engagement, player groups, “Who leaves, and when?”', needs: 'sessions' },
  { key: 'investigation', label: '“Why did it drop?” (needs roughly 3+ weeks of history)', needs: 'more history' },
  { key: 'purchases', label: 'Monetization (revenue, who pays)', needs: 'a purchases file' },
  { key: 'matches', label: 'Game-mode analysis and early-match signals', needs: 'a matches file' },
  { key: 'events', label: 'Tutorial and crash explanations', needs: 'an events file with tutorial_complete / crash' },
  { key: 'device_tiers', label: 'Device-quality analysis', needs: 'a devices file or device tiers' },
  { key: 'experiments', label: 'Reading and monitoring A/B tests', needs: 'experiment files' },
  { key: 'mena', label: 'MENA market comparison', needs: 'players in at least two MENA countries' },
];

function Stepper({ step }: { step: Step }) {
  const idx = STEPS.findIndex((s) => s.id === step);
  return (
    <ol className="mb-6 flex flex-wrap items-center gap-2 text-sm" aria-label="Progress">
      {STEPS.map((s, i) => (
        <li key={s.id} className="flex items-center gap-2">
          <span className={`flex items-center gap-2 rounded-full border px-3 py-1 ${i === idx ? 'border-accent bg-accent/10 text-ink' : i < idx ? 'border-good/40 text-good' : 'border-line text-ink3'}`}>
            <span className="num text-xs">{i < idx ? '✓' : i + 1}</span>{s.label}
          </span>
          {i < STEPS.length - 1 && <span className="text-ink3">→</span>}
        </li>
      ))}
    </ol>
  );
}

/* ------------------------------------------------------------------ step 1 */
function DropZone({ onFiles, busy }: { onFiles: (f: File[]) => void; busy: boolean }) {
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const drop = (e: DragEvent) => { e.preventDefault(); setOver(false); const f = Array.from(e.dataTransfer.files); if (f.length) onFiles(f); };
  return (
    <div onDragOver={(e) => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)} onDrop={drop}
      onClick={() => !busy && input.current?.click()} role="button" tabIndex={0} aria-label="Choose or drop CSV files"
      onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && input.current?.click()}
      className={`cursor-pointer rounded-xl border-2 border-dashed p-10 text-center transition-colors ${over ? 'border-accent bg-accent/10' : 'border-line bg-panel hover:border-accent/60'}`}>
      <input ref={input} type="file" multiple accept=".csv,.tsv,.txt,.zip,text/csv,application/zip" className="hidden"
        onChange={(e) => { const f = Array.from(e.target.files ?? []); if (f.length) onFiles(f); e.target.value = ''; }} />
      <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-accent/10 text-accent"><Icon name="upload" size={24} /></div>
      <p className="font-display text-xl font-semibold text-ink">{busy ? 'Reading your files…' : 'Drop your CSV files (or one .zip) here'}</p>
      <p className="mt-1 text-sm text-ink2">or click to choose them</p>
      <p className="mx-auto mt-4 max-w-xl text-xs text-ink3">
        Only a <b className="text-ink2">sessions</b> file is required: one row per play session with a player id and a start time. Add players, purchases, matches,
        events or experiments for deeper analysis. File and column names are matched automatically.
      </p>
    </div>
  );
}

/* ------------------------------------------------------------------ step 2 */
function FileCard({ f, tables, onTable, onMap }: { f: InspectedFile; tables: TableInfo[]; onTable: (t: string) => void; onMap: (target: string, src: string | null) => void }) {
  const info = tables.find((t) => t.value === f.table);
  const missing = info ? info.required.filter((r) => !f.mapping[r]) : [];
  const [open, setOpen] = useState(false);
  const show = open || missing.length > 0;
  const targets = info ? info.columns.filter((c) => !HIDDEN.has(c)) : [];
  const matched = targets.filter((c) => f.mapping[c]).length;
  const sample = (src: string | null) => { if (!src) return ''; const i = f.columns.indexOf(src); return i < 0 ? '' : f.preview.map((r) => r[i]).filter(Boolean).slice(0, 2).join(', '); };
  return (
    <section className="rounded-lg border border-line bg-panel p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="font-display text-base font-semibold text-ink">{f.filename}</div>
          <div className="text-xs text-ink3">{fmtInt(f.rows)} rows · {f.columns.length} columns</div>
        </div>
        <label className="flex items-center gap-2 text-sm text-ink2">
          This file contains
          <select value={f.table ?? 'ignore'} onChange={(e) => onTable(e.target.value)} className="rounded-md border border-line bg-panel px-2 py-1.5 text-sm text-ink">
            {tables.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
            <option value="ignore">Ignore this file</option>
          </select>
        </label>
      </div>
      {f.error && <p className="mt-2 text-sm text-bad">{f.error}</p>}
      {info && (
        <>
          <div className="mt-3 flex flex-wrap items-center gap-2 text-sm">
            {missing.length === 0 ? <Badge tone="good" icon="check">Required columns found</Badge> : <Badge tone="bad" icon="alert">Choose: {missing.map((m) => LABEL[m] ?? m).join(', ')}</Badge>}
            <span className="text-ink3">{matched} of {targets.length} columns matched automatically</span>
            {missing.length === 0 && <button onClick={() => setOpen((o) => !o)} className="text-accent hover:underline">{open ? 'Hide columns' : 'Check columns'}</button>}
          </div>
          {show && (
            <div className="mt-3 overflow-x-auto">
              <table className="data">
                <thead><tr><th>What we look for</th><th>Your column</th><th>Example values</th></tr></thead>
                <tbody>
                  {targets.map((t) => {
                    const req = info.required.includes(t);
                    return (
                      <tr key={t}>
                        <td>{LABEL[t] ?? t} {req && <span className="text-bad" title="required">*</span>}</td>
                        <td>
                          <select value={f.mapping[t] ?? ''} onChange={(e) => onMap(t, e.target.value || null)}
                            className={`rounded-md border bg-panel px-2 py-1 text-sm text-ink ${req && !f.mapping[t] ? 'border-bad' : 'border-line'}`} aria-label={`Column for ${LABEL[t] ?? t}`}>
                            <option value="">— not in my data —</option>
                            {f.columns.map((c) => <option key={c} value={c}>{c}</option>)}
                          </select>
                        </td>
                        <td className="num text-xs text-ink3">{sample(f.mapping[t] ?? null)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </section>
  );
}

function ValidationPanel({ v, busy }: { v: Validation | null; busy: boolean }) {
  if (busy && !v) return <Skeleton className="h-24 w-full" />;
  if (!v) return null;
  return (
    <div className="space-y-3">
      {v.errors.length > 0 && (
        <Callout tone="bad" icon="alert" title="Fix these before importing">
          <ul className="mt-1 list-disc space-y-1 pl-5">{v.errors.map((e, i) => <li key={i}>{e}</li>)}</ul>
        </Callout>
      )}
      {v.warnings.length > 0 && (
        <Callout tone="warn" icon="info" title="Things to know (the import will still work)">
          <ul className="mt-1 list-disc space-y-1 pl-5">{v.warnings.map((e, i) => <li key={i}>{e}</li>)}</ul>
        </Callout>
      )}
      {v.ok && v.stats?.rows && (
        <Callout tone="good" icon="check" title="Ready to import">
          {Object.entries(v.stats.rows as Record<string, number>).map(([k, n]) => `${fmtInt(n)} ${k}`).join(' · ')} · {v.stats.min_date} → {v.stats.max_date} ({v.stats.span_days + 1} days)
        </Callout>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ steps 3 + 4 */
function Progress({ job }: { job: Job | null }) {
  const pct = Math.round((job?.progress ?? 0) * 100);
  return (
    <Panel>
      <div className="py-6 text-center">
        <p className="font-display text-xl font-semibold text-ink">{job?.kind === 'demo' ? 'Generating the demo data' : 'Importing your data'}</p>
        <p className="mt-1 text-sm text-ink2">{job?.step ?? 'Starting…'}</p>
        <div className="mx-auto mt-5 h-2 max-w-md overflow-hidden rounded-full bg-panel2" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
          <div className="h-full rounded-full bg-accent transition-all" style={{ width: `${Math.max(pct, 4)}%` }} />
        </div>
        <p className="num mt-2 text-xs text-ink3">{pct}% · {job ? Math.round(job.seconds) : 0}s</p>
        <p className="mx-auto mt-4 max-w-md text-xs text-ink3">The rest of the site pauses for a few seconds while the data is replaced. Nothing changes if anything goes wrong.</p>
      </div>
    </Panel>
  );
}

function Results({ job, onAgain }: { job: Job; onAgain: () => void }) {
  const router = useRouter();
  const ds = job.summary?.dataset;
  const caps = ds?.capabilities ?? {};
  const findings: { severity: string; title: string; insight: string; link?: string }[] = job.summary?.findings ?? [];
  return (
    <div className="space-y-4">
      <Callout tone="good" icon="check" title={job.kind === 'demo' ? 'Demo data is ready' : 'Your data is loaded'}>
        {ds ? <>{fmtInt(ds.counts.players)} players · {fmtInt(ds.counts.sessions)} sessions · {ds.date_min} → {ds.date_max} ({ds.span_days + 1} days). Done in {Math.round(job.seconds)}s.</> : 'Done.'}
      </Callout>

      <div className="flex flex-wrap gap-2">
        <button onClick={() => router.push('/')} className="inline-flex items-center gap-1 rounded-md bg-accent px-4 py-2 text-sm font-medium text-white hover:opacity-90">Open the Overview <Icon name="arrow" size={14} /></button>
        {caps.investigation && <Link href="/investigation" className="inline-flex items-center gap-1 rounded-md border border-line px-4 py-2 text-sm text-accent hover:bg-panel2">Why did it drop? <Icon name="arrow" size={14} /></Link>}
        <Link href="/insights" className="inline-flex items-center gap-1 rounded-md border border-line px-4 py-2 text-sm text-accent hover:bg-panel2">All findings <Icon name="arrow" size={14} /></Link>
        <button onClick={onAgain} className="rounded-md px-3 py-2 text-sm text-ink3 hover:text-ink">Import something else</button>
      </div>

      {findings.length > 0 && (
        <Panel title="What the analysis found" sub="Generated automatically from your data">
          <ul className="space-y-3">
            {findings.map((f, i) => (
              <li key={i} className="rounded-md border border-line bg-panel2 p-3">
                <div className="mb-1 flex items-center gap-2"><Badge tone={f.severity === 'high' ? 'bad' : f.severity === 'medium' ? 'warn' : f.severity === 'positive' ? 'good' : 'neutral'}>{f.severity === 'high' ? 'Act soon' : f.severity === 'medium' ? 'Worth a look' : f.severity === 'positive' ? 'Good news' : 'For awareness'}</Badge><span className="font-medium text-ink">{f.title}</span></div>
                <p className="text-sm text-ink2">{f.insight}</p>
                {f.link && <Link href={f.link} className="mt-1 inline-block text-xs text-accent hover:underline">Open the analysis →</Link>}
              </li>
            ))}
          </ul>
        </Panel>
      )}

      <Panel title="What your data can show" sub="Based on the files you provided">
        <ul className="grid gap-2 md:grid-cols-2">
          {CAPS.map((c) => {
            const ok = c.key === 'always' ? true : Boolean(caps[c.key]);
            return (
              <li key={c.key} className="flex items-start gap-2 text-sm">
                <span className={`mt-0.5 ${ok ? 'text-good' : 'text-ink3'}`}><Icon name={ok ? 'check' : 'x'} size={14} /></span>
                <span className={ok ? 'text-ink' : 'text-ink3'}>{c.label}{!ok && <span className="block text-xs">Needs {c.needs}</span>}</span>
              </li>
            );
          })}
        </ul>
      </Panel>

      {job.warnings.length > 0 && (
        <Callout tone="warn" icon="info" title="Defaults that were used">
          <ul className="mt-1 list-disc space-y-1 pl-5">{job.warnings.map((w, i) => <li key={i}>{w}</li>)}</ul>
        </Callout>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ page */
export default function ImportPage() {
  const { meta } = useFilters();
  const { mutate } = useSWRConfig();
  const [step, setStep] = useState<Step>('choose');
  const [up, setUp] = useState<UploadResponse | null>(null);
  const [files, setFiles] = useState<InspectedFile[]>([]);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string>('');
  const [validation, setValidation] = useState<Validation | null>(null);
  const [validating, setValidating] = useState(false);
  const [seconds, setSeconds] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const secondsTouched = useRef(false);
  const [job, setJob] = useState<Job | null>(null);
  const [allowed, setAllowed] = useState(true);
  const poll = useRef<ReturnType<typeof setInterval> | null>(null);

  const specs: Spec[] = useMemo(() => files.filter((f) => f.table && f.table !== 'ignore').map((f) => ({ filename: f.filename, table: f.table as string, mapping: f.mapping })), [files]);

  // resume the progress view if the page is opened while a job is running
  useEffect(() => {
    getImportState().then((s) => {
      setAllowed(s.allowed);
      if (s.busy && s.job) { setJob(s.job); setStep('importing'); watch(s.job.id); }
    }).catch(() => undefined);
    return () => { if (poll.current) clearInterval(poll.current); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const watch = useCallback((id: string) => {
    if (poll.current) clearInterval(poll.current);
    poll.current = setInterval(async () => {
      try {
        const j = await getJob(id);
        setJob(j);
        if (j.state === 'done') {
          if (poll.current) clearInterval(poll.current);
          await mutate(() => true, undefined, { revalidate: true }); // every page re-reads the new data
          setStep('done');
        } else if (j.state === 'error') {
          if (poll.current) clearInterval(poll.current);
          setError(j.errors.join(' '));
          setStep('check');
        }
      } catch { /* the API may be briefly busy; keep polling */ }
    }, 800);
  }, [mutate]);

  const onFiles = async (picked: File[]) => {
    setError(''); setUploading(true);
    try {
      const r = await uploadFiles(picked);
      setUp(r); setFiles(r.files); setValidation(null); setConfirming(false); secondsTouched.current = false; setSeconds(false); setStep('check');
    } catch (e) { setError((e as Error).message); }
    finally { setUploading(false); }
  };

  // re-validate whenever the user changes a table type, a column, or the units
  useEffect(() => {
    if (step !== 'check' || !up) return;
    let live = true;
    setValidating(true);
    const t = setTimeout(() => {
      validateImport(up.session_id, specs, { durations_in_seconds: seconds })
        .then((v) => {
          if (!live) return;
          setValidation(v);
          if (v.stats?.durations_look_like_seconds && !secondsTouched.current) setSeconds(true);
        })
        .catch((e) => live && setValidation({ ok: false, errors: [(e as Error).message], warnings: [], stats: {} }))
        .finally(() => live && setValidating(false));
    }, 400);
    return () => { live = false; clearTimeout(t); };
  }, [step, up, specs, seconds]);

  const setTable = (name: string, table: string) =>
    setFiles((fs) => fs.map((f) => (f.filename === name ? { ...f, table: table === 'ignore' ? 'ignore' : table, mapping: table === 'ignore' ? {} : f.mappings[table] ?? {} } : f)));
  const setMap = (name: string, target: string, src: string | null) =>
    setFiles((fs) => fs.map((f) => (f.filename === name ? { ...f, mapping: { ...f.mapping, [target]: src } } : f)));

  const start = async () => {
    if (!up) return;
    setError(''); setStep('importing'); setJob(null);
    try {
      const { job_id } = await runImport(up.session_id, specs, { durations_in_seconds: seconds });
      watch(job_id);
    } catch (e) { setError((e as Error).message); setStep('check'); }
  };
  const demo = async (players: number) => {
    setError(''); setStep('importing'); setJob(null);
    try { const { job_id } = await startDemo(players); watch(job_id); } catch (e) { setError((e as Error).message); setStep('choose'); }
  };
  const again = () => { setUp(null); setFiles([]); setValidation(null); setJob(null); setError(''); setStep('choose'); };

  const ds = meta?.dataset;
  return (
    <>
      <PageHeader eyebrow="Your data" title="Import data"
        desc="Drop in your game's exports and GamePulse checks them, loads them and runs the analysis. No commands needed." />
      {!allowed && <Callout tone="warn" icon="alert" title="Importing is switched off on this server">The administrator has set ALLOW_IMPORT=0. You can still explore the data that is loaded.</Callout>}
      {allowed && <Stepper step={step} />}
      {error && <div className="mb-4"><Callout tone="bad" icon="alert" title="That did not work">{error}</Callout></div>}

      {allowed && step === 'choose' && (
        <div className="space-y-5">
          <DropZone onFiles={onFiles} busy={uploading} />
          <div className="grid gap-4 md:grid-cols-3">
            <Panel title="Not sure what to upload?">
              <p className="mb-3 text-sm text-ink2">Download example files in the expected format, then replace them with yours.</p>
              <a href="/api/import/sample.zip" className="inline-flex items-center gap-1 rounded-md border border-line px-3 py-1.5 text-sm text-accent hover:bg-panel2">Download sample CSVs (.zip)</a>
            </Panel>
            <Panel title="Just want to explore?">
              <p className="mb-3 text-sm text-ink2">Load a synthetic demo game. Takes about a minute and replaces the current data.</p>
              <div className="flex flex-wrap gap-2">
                <button onClick={() => demo(52000)} className="rounded-md border border-line px-3 py-1.5 text-sm text-accent hover:bg-panel2">Demo: 52,000 players</button>
                <button onClick={() => demo(5000)} className="rounded-md border border-line px-3 py-1.5 text-sm text-accent hover:bg-panel2">Small: 5,000</button>
              </div>
            </Panel>
            <Panel title="Currently loaded">
              {ds ? (
                <p className="text-sm text-ink2">
                  <Badge tone={ds.is_demo ? 'warn' : 'accent'}>{ds.is_demo ? 'Synthetic demo data' : 'Your data'}</Badge>
                  <span className="mt-2 block num">{fmtInt(ds.counts.players)} players · {fmtInt(ds.counts.sessions)} sessions</span>
                  <span className="block text-xs text-ink3">{ds.date_min} → {ds.date_max}</span>
                </p>
              ) : <Skeleton className="h-12 w-full" />}
              <p className="mt-2 text-xs text-ink3">Importing replaces this. Player ids are replaced by anonymous numbers.</p>
            </Panel>
          </div>
        </div>
      )}

      {allowed && step === 'check' && up && (
        <div className="space-y-4">
          {files.map((f) => (
            <FileCard key={f.filename} f={f} tables={up.tables} onTable={(t) => setTable(f.filename, t)} onMap={(t, s) => setMap(f.filename, t, s)} />
          ))}
          <label className="flex items-center gap-2 text-sm text-ink2">
            <input type="checkbox" checked={seconds} onChange={(e) => { secondsTouched.current = true; setSeconds(e.target.checked); }} className="accent-[var(--accent)]" />
            Session and match lengths in my files are in <b>seconds</b> (not minutes)
          </label>
          <ValidationPanel v={validation} busy={validating} />
          {confirming ? (
            <Callout tone="warn" icon="alert" title="Replace the current data?">
              <p>The {ds ? `${fmtInt(ds.counts.players)} players` : 'data'} currently loaded will be replaced by this dataset. If anything goes wrong, nothing is changed.</p>
              <div className="mt-3 flex flex-wrap gap-2">
                <button onClick={() => { setConfirming(false); start(); }} className="rounded-md bg-accent px-4 py-2 text-sm font-medium text-white hover:opacity-90">Yes, replace and import</button>
                <button onClick={() => setConfirming(false)} className="rounded-md border border-line px-4 py-2 text-sm text-ink2 hover:bg-panel2">Cancel</button>
              </div>
            </Callout>
          ) : (
            <div className="flex flex-wrap items-center gap-3 border-t border-line pt-4">
              <button onClick={again} className="rounded-md border border-line px-3 py-2 text-sm text-ink2 hover:bg-panel2">← Choose different files</button>
              {!validation?.ok && !validating && <span className="text-sm text-ink3">Fix the problems above to continue.</span>}
              <button disabled={!validation?.ok || validating} onClick={() => setConfirming(true)}
                className="ml-auto inline-flex items-center gap-1 rounded-md bg-accent px-5 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-40">
                {validating ? 'Checking…' : 'Import and analyse'} <Icon name="arrow" size={14} />
              </button>
            </div>
          )}
        </div>
      )}

      {allowed && step === 'importing' && <Progress job={job} />}
      {allowed && step === 'done' && job && <Results job={job} onAgain={again} />}
    </>
  );
}
