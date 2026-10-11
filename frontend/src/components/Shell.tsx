'use client';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import useSWR from 'swr';
import { ReactNode, useEffect, useState } from 'react';
import { FilterProvider, useFilters } from '@/lib/filters';
import FilterBar from './FilterBar';
import { GlossaryPanel } from './Info';
import { Icon } from './ui';

interface NavItem { href: string; label: string; icon: string; filters: boolean; group: string; tip: string }

// Grouped by what the person is trying to do, not by data type.
const NAV: NavItem[] = [
  { href: '/', label: 'Overview', icon: 'grid', filters: true, group: 'Start here', tip: 'Is the game healthy right now?' },
  { href: '/import', label: 'Import data', icon: 'upload', filters: false, group: 'Start here', tip: 'Load your own game data and analyse it automatically' },
  { href: '/players', label: 'Players', icon: 'users', filters: true, group: 'Check the game', tip: 'How many players, who they are, who left' },
  { href: '/retention', label: 'Retention', icon: 'repeat', filters: true, group: 'Check the game', tip: 'Do new players come back?' },
  { href: '/engagement', label: 'Engagement', icon: 'activity', filters: true, group: 'Check the game', tip: 'How often and how long people play' },
  { href: '/monetization', label: 'Monetization', icon: 'coins', filters: true, group: 'Check the game', tip: 'Revenue and who pays' },
  { href: '/acquisition', label: 'Acquisition', icon: 'funnel', filters: true, group: 'Check the game', tip: 'Where new players come from' },
  { href: '/segmentation', label: 'Player groups', icon: 'layers', filters: true, group: 'Check the game', tip: 'Casual, engaged, high-value, at-risk players' },
  { href: '/mena', label: 'MENA markets', icon: 'globe', filters: true, group: 'Check the game', tip: 'Compare six markets side by side' },
  { href: '/investigation', label: 'Why did it drop?', icon: 'search', filters: false, group: 'Find out why', tip: 'Find which players caused a KPI change' },
  { href: '/explorer', label: 'Who leaves, and when?', icon: 'heat', filters: true, group: 'Find out why', tip: 'Compare groups of players over time' },
  { href: '/insights', label: 'What to do next', icon: 'bulb', filters: false, group: 'Find out why', tip: 'Ready-made findings and recommended actions' },
  { href: '/experiments', label: 'Test an idea', icon: 'flask', filters: false, group: 'Decide', tip: 'Plan, monitor and read A/B tests' },
];

function ThemeToggle() {
  const [dark, setDark] = useState(true);
  useEffect(() => {
    const attr = document.documentElement.getAttribute('data-theme');
    setDark(attr ? attr === 'dark' : window.matchMedia('(prefers-color-scheme: dark)').matches);
  }, []);
  const toggle = () => {
    const next = dark ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', next);
    try { localStorage.setItem('gp-theme', next); } catch { /* storage unavailable */ }
    setDark(!dark);
  };
  return (
    <button onClick={toggle} aria-label={dark ? 'Switch to light theme' : 'Switch to dark theme'}
      className="flex h-8 w-8 items-center justify-center rounded-md border border-line text-ink2 hover:bg-panel2 hover:text-ink">
      <Icon name={dark ? 'sun' : 'moon'} size={15} />
    </button>
  );
}

function Nav({ onNavigate }: { onNavigate?: () => void }) {
  const path = usePathname();
  const groups = Array.from(new Set(NAV.map((n) => n.group)));
  return (
    <nav aria-label="Primary" className="flex flex-col gap-5">
      {groups.map((g) => (
        <div key={g}>
          <div className="eyebrow mb-1.5 px-3">{g}</div>
          <ul className="flex flex-col gap-0.5">
            {NAV.filter((n) => n.group === g).map((n) => {
              const active = n.href === '/' ? path === '/' : path.startsWith(n.href);
              return (
                <li key={n.href}>
                  <Link href={n.href} onClick={onNavigate} title={n.tip} aria-current={active ? 'page' : undefined}
                    className={`flex items-center gap-2.5 rounded-md border-l-2 px-3 py-2 text-[13px] ${active
                      ? 'border-accent bg-panel2 font-medium text-ink' : 'border-transparent text-ink2 hover:bg-panel2 hover:text-ink'}`}>
                    <Icon name={n.icon} size={16} className={active ? 'text-accent' : ''} />{n.label}
                  </Link>
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </nav>
  );
}

function Brand() {
  return (
    <Link href="/" className="flex items-center gap-2.5 px-3">
      <span className="flex h-8 w-8 items-center justify-center rounded-md bg-accent text-white">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"><path d="M2 12h4l3-8 5 16 3-8h5" /></svg>
      </span>
      <span>
        <span className="block font-display text-[17px] font-bold leading-none tracking-wide text-ink">GamePulse</span>
        <span className="block text-[10px] uppercase tracking-[0.14em] text-ink3">Game Ops Console</span>
      </span>
    </Link>
  );
}

function Inner({ children }: { children: ReactNode }) {
  const path = usePathname();
  const [open, setOpen] = useState(false);
  const [glossary, setGlossary] = useState(false);
  const { meta } = useFilters();
  const isDemo = meta?.dataset ? Boolean(meta.dataset.is_demo) : true;
  const { data: impState } = useSWR<{ busy: boolean }>('/api/import/state', (u: string) => fetch(u).then((r) => r.json()),
    { refreshInterval: (d) => (d?.busy ? 1500 : 20000), revalidateOnFocus: false });
  const item = NAV.find((n) => (n.href === '/' ? path === '/' : path.startsWith(n.href)));
  const showFilters = item?.filters ?? false;

  useEffect(() => setOpen(false), [path]);

  return (
    <div className="min-h-screen">
      {/* desktop sidebar */}
      <aside className="fixed inset-y-0 left-0 z-20 hidden w-60 flex-col gap-6 border-r border-line bg-panel py-5 lg:flex">
        <Brand />
        <div className="flex-1 overflow-y-auto px-2"><Nav /></div>
      </aside>

      {/* mobile drawer */}
      {open && (
        <div className="fixed inset-0 z-40 lg:hidden" role="dialog" aria-modal="true" aria-label="Navigation">
          <div className="absolute inset-0 bg-black/50" onClick={() => setOpen(false)} />
          <div className="absolute inset-y-0 left-0 w-64 overflow-y-auto bg-panel py-5">
            <div className="mb-5 flex items-center justify-between pr-3"><Brand />
              <button onClick={() => setOpen(false)} aria-label="Close navigation" className="text-ink2"><Icon name="x" /></button>
            </div>
            <div className="px-2"><Nav onNavigate={() => setOpen(false)} /></div>
          </div>
        </div>
      )}

      <GlossaryPanel open={glossary} onClose={() => setGlossary(false)} />

      <div className="lg:pl-60">
        <header className="sticky top-0 z-10 flex h-12 items-center gap-3 border-b border-line bg-bg/90 px-4 backdrop-blur lg:px-8">
          <button className="lg:hidden" onClick={() => setOpen(true)} aria-label="Open navigation"><Icon name="menu" size={20} /></button>
          <div className="eyebrow hidden sm:block">{item?.tip ?? 'Live-service mobile game'}</div>
          <div className="ml-auto flex items-center gap-3">
            {isDemo ? (
              <span className="hidden rounded border border-warn/50 bg-warn/10 px-2 py-0.5 text-[11px] font-semibold tracking-wide text-warn md:inline" title="All numbers are generated by a simulator">
                SYNTHETIC PORTFOLIO DATA
              </span>
            ) : (
              <span className="hidden rounded border border-accent/50 bg-accent/10 px-2 py-0.5 text-[11px] font-semibold tracking-wide text-accent md:inline" title="Data you imported">
                YOUR DATA
              </span>
            )}
            {meta?.row_counts && (
              <span className="num hidden text-[11px] text-ink3 xl:block">
                {Number(meta.row_counts.players).toLocaleString()} players · {Number(meta.row_counts.sessions).toLocaleString()} sessions
              </span>
            )}
            <button onClick={() => setGlossary(true)}
              className="flex h-8 items-center gap-1.5 rounded-md border border-line px-2.5 text-xs text-ink2 hover:bg-panel2 hover:text-ink" aria-label="Open glossary">
              <span className="flex h-4 w-4 items-center justify-center rounded-full border border-current text-[10px] font-semibold">?</span> Glossary
            </button>
            <ThemeToggle />
          </div>
        </header>
        {impState?.busy && path !== '/import' && (
          <div role="status" className="flex items-center justify-center gap-2 border-b border-accent/40 bg-accent/10 px-4 py-2 text-sm text-ink">
            <Icon name="upload" size={14} className="text-accent" /> A data import is running. Pages will refresh when it finishes.
            <Link href="/import" className="font-medium text-accent underline underline-offset-2">Watch progress</Link>
          </div>
        )}
        <main className="mx-auto max-w-[1600px] px-4 py-6 lg:px-8">
          {showFilters && <FilterBar segmentLocked={path.startsWith('/segmentation')} hideDates={path.startsWith('/explorer')} />}
          {children}
        </main>
      </div>
    </div>
  );
}

export default function Shell({ children }: { children: ReactNode }) {
  return (
    <FilterProvider>
      <Inner>{children}</Inner>
    </FilterProvider>
  );
}
