'use client';
import { ReactNode, useEffect, useState } from 'react';

export interface FocusTab {
  id: string;
  label: string;
  /** The plain question this view answers; shown as the heading of the view. */
  question: string;
  render: () => ReactNode;
}

/**
 * One question at a time. Only the active view is rendered (so only its data is fetched), the question is
 * the heading, and a "Next" link walks the reader through the rest. The view is kept in the URL hash so a
 * link or a refresh lands on the same view.
 */
export function FocusTabs({ tabs, syncHash = true, steps = false, aside }: {
  tabs: FocusTab[]; syncHash?: boolean; steps?: boolean; aside?: ReactNode;
}) {
  const [active, setActive] = useState(tabs[0].id);
  useEffect(() => {
    if (!syncHash) return;
    const h = window.location.hash.slice(1);
    if (h && tabs.some((t) => t.id === h)) setActive(h);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  const idx = Math.max(0, tabs.findIndex((t) => t.id === active));
  const tab = tabs[idx];
  const select = (id: string) => {
    setActive(id);
    if (syncHash) window.history.replaceState(null, '', `#${id}`);
  };
  const prev = tabs[idx - 1], next = tabs[idx + 1];

  return (
    <section>
      <div role="tablist" aria-label="Views" className="-mx-1 flex gap-1 overflow-x-auto border-b border-line px-1">
        {tabs.map((t, i) => {
          const on = t.id === tab.id;
          return (
            <button key={t.id} role="tab" aria-selected={on} onClick={() => select(t.id)}
              className={`relative shrink-0 whitespace-nowrap px-3 py-2.5 text-sm transition-colors ${on ? 'font-medium text-ink' : 'text-ink3 hover:text-ink'}`}>
              {steps && <span className={`num mr-1.5 inline-flex h-5 w-5 items-center justify-center rounded-full text-[11px] ${on ? 'bg-accent text-white' : 'border border-line text-ink3'}`}>{i + 1}</span>}
              {t.label}
              {on && <span className="absolute inset-x-2 -bottom-px h-0.5 rounded bg-accent" />}
            </button>
          );
        })}
      </div>

      <div className="mt-5 flex flex-wrap items-end justify-between gap-3">
        <h2 className="font-display text-xl font-semibold tracking-wide text-ink">{tab.question}</h2>
        {aside}
      </div>
      <div className="mt-4" key={tab.id}>{tab.render()}</div>

      {(prev || next) && (
        <div className="mt-6 flex items-center justify-between border-t border-line pt-4 text-sm">
          {prev ? <button onClick={() => select(prev.id)} className="text-ink3 hover:text-accent">← {prev.label}</button> : <span />}
          {next ? (
            <button onClick={() => select(next.id)} className="rounded-md border border-line px-3 py-1.5 text-accent hover:bg-panel2">
              {steps ? 'Next step' : 'Next view'}: {next.label} →
            </button>
          ) : <span />}
        </div>
      )}
    </section>
  );
}
