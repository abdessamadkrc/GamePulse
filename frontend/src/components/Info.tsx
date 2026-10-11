'use client';
import { useEffect, useRef, useState } from 'react';
import { findTerm, GLOSSARY } from '@/lib/glossary';

/** Small "?" button that explains a term in plain English. Works with mouse, touch and keyboard. */
export function Info({ term, className = '' }: { term: string; className?: string }) {
  const entry = findTerm(term);
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false); };
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false); };
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onKey);
    return () => { document.removeEventListener('mousedown', onDown); document.removeEventListener('keydown', onKey); };
  }, [open]);
  if (!entry) return null;
  return (
    <span ref={ref} className={`relative inline-flex ${className}`}>
      <button type="button" aria-label={`What is ${term}?`} aria-expanded={open} onClick={() => setOpen((o) => !o)}
        className="flex h-4 w-4 items-center justify-center rounded-full border border-line text-[10px] font-semibold text-ink3 hover:border-accent hover:text-accent">?</button>
      {open && (
        <span role="tooltip" className="absolute left-0 top-full z-40 mt-1.5 w-64 max-w-[80vw] rounded-md border border-line bg-panel p-3 text-left text-xs font-normal normal-case leading-relaxed tracking-normal text-ink2 shadow-xl">
          <b className="mb-1 block font-display text-[13px] text-ink">{entry.term}</b>
          {entry.plain}
          {entry.example && <span className="mt-1.5 block text-ink3">Example: {entry.example}</span>}
        </span>
      )}
    </span>
  );
}

/** Slide-in panel listing every term, with search. */
export function GlossaryPanel({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [q, setQ] = useState('');
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [open, onClose]);
  if (!open) return null;
  const items = GLOSSARY.filter((g) => (g.term + g.plain).toLowerCase().includes(q.toLowerCase()));
  return (
    <div className="fixed inset-0 z-50" role="dialog" aria-modal="true" aria-label="Glossary">
      <div className="absolute inset-0 bg-black/50" onClick={onClose} />
      <aside className="absolute inset-y-0 right-0 flex w-full max-w-md flex-col border-l border-line bg-panel shadow-2xl">
        <header className="flex items-center justify-between border-b border-line p-4">
          <div>
            <h2 className="font-display text-lg font-semibold">Glossary</h2>
            <p className="text-xs text-ink3">Plain-English meanings of the terms on this site.</p>
          </div>
          <button onClick={onClose} aria-label="Close glossary" className="text-ink2 hover:text-ink"><span aria-hidden className="text-lg leading-none">&times;</span></button>
        </header>
        <div className="border-b border-line p-3">
          <input autoFocus value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search a word, e.g. retention"
            className="w-full rounded-md border border-line bg-panel2 px-3 py-2 text-sm text-ink" aria-label="Search glossary" />
        </div>
        <div className="flex-1 space-y-4 overflow-y-auto p-4">
          {items.map((g) => (
            <div key={g.term}>
              <div className="font-display text-sm font-semibold text-ink">{g.term}</div>
              <p className="mt-0.5 text-sm text-ink2">{g.plain}</p>
              {g.example && <p className="mt-0.5 text-xs text-ink3">Example: {g.example}</p>}
            </div>
          ))}
          {!items.length && <p className="text-sm text-ink3">No matching term.</p>}
        </div>
      </aside>
    </div>
  );
}
