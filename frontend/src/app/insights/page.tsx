'use client';
import Link from 'next/link';
import { useState } from 'react';
import { useApi, Row } from '@/lib/api';
import { Badge, Callout, Icon, PageHeader, Skeleton } from '@/components/ui';

const SEV: Record<string, { tone: 'bad' | 'warn' | 'good' | 'neutral'; label: string }> = {
  high: { tone: 'bad', label: 'Act soon' }, medium: { tone: 'warn', label: 'Worth a look' }, positive: { tone: 'good', label: 'Good news' }, info: { tone: 'neutral', label: 'For awareness' },
};
const SIG_TONE: Record<string, 'accent' | 'warn' | 'neutral'> = { consistent: 'accent', weak: 'warn', none: 'neutral', insufficient: 'neutral' };

function Block({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="mt-4">
      <div className="eyebrow mb-1.5">{label}</div>
      {children}
    </div>
  );
}

function Detail({ c }: { c: Row }) {
  return (
    <div className="border-t border-line px-5 pb-5 pt-1">
      <Block label="What the data says"><p className="text-sm text-ink">{c.insight}</p></Block>
      <Block label="Evidence">
        <ul className="space-y-1 text-sm text-ink2">
          {c.evidence.map((e: string, i: number) => <li key={i} className="flex gap-2"><span className="mt-2 h-1 w-1 shrink-0 rounded-full bg-ink3" /><span className="num text-[13px]">{e}</span></li>)}
        </ul>
      </Block>
      <Block label="Possible explanations (not proven)">
        <ul className="space-y-1.5">
          {c.hypotheses.map((h: Row, i: number) => (
            <li key={i} className="flex flex-wrap items-center gap-2 text-sm">
              <Badge tone={c.category === 'Experimentation' ? 'good' : 'warn'}>{h.label}</Badge>
              <span className="text-ink">{h.title}</span>
              <Badge tone={SIG_TONE[h.signal] ?? 'neutral'}>{h.signal_text}</Badge>
            </li>
          ))}
        </ul>
        {c.hypothesis_note && <p className="mt-2 text-xs text-ink3">{c.hypothesis_note}</p>}
      </Block>
      <div className="mt-5 grid gap-3 md:grid-cols-2">
        <div className="rounded-md border border-accent/40 bg-accent/5 p-3">
          <div className="eyebrow mb-1 text-accent">What to do next</div>
          <p className="text-sm text-ink">{c.next_step}</p>
        </div>
        <div className="rounded-md border border-line bg-panel2 p-3">
          <div className="eyebrow mb-1">Number to keep watching</div>
          <p className="text-sm text-ink">{c.kpi_to_monitor}</p>
          {c.link && <Link href={c.link} className="mt-2 inline-flex items-center gap-1 text-xs text-accent hover:underline">Open the analysis <Icon name="arrow" size={12} /></Link>}
        </div>
      </div>
    </div>
  );
}

export default function InsightsPage() {
  const { data, error, isLoading, mutate } = useApi<{ cards: Row[] }>('/api/insights', { filters: false });
  const [open, setOpen] = useState<string>('');
  const cards = data?.cards ?? [];
  const current = open || cards[0]?.id;

  return (
    <>
      <PageHeader eyebrow="Strategy & operations" title="What to do next"
        desc="Ready-made findings from the data, most urgent first. Open one at a time: what changed, the evidence, what might explain it, and the one thing to do next." />
      {error ? (
        <Callout tone="bad" icon="alert" title="Findings unavailable"><button className="underline" onClick={() => mutate()}>Retry</button> · {String((error as Error).message)}</Callout>
      ) : (
        <ul className="space-y-2" aria-label="Findings">
          {isLoading && [0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-16" />)}
          {cards.map((c) => {
            const sev = SEV[c.severity] ?? SEV.info;
            const on = c.id === current;
            return (
              <li key={c.id} className={`overflow-hidden rounded-lg border bg-panel ${on ? 'border-accent/50' : 'border-line'}`}>
                <button onClick={() => setOpen(on ? '__none' : c.id)} aria-expanded={on}
                  className="flex w-full items-start gap-3 p-4 text-left hover:bg-panel2">
                  <div className="min-w-0 flex-1">
                    <div className="mb-1 flex flex-wrap items-center gap-2"><Badge tone={sev.tone}>{sev.label}</Badge><span className="eyebrow">{c.category}</span></div>
                    <h2 className="font-display text-lg font-semibold leading-snug tracking-wide text-ink">{c.title}</h2>
                    {!on && <p className="mt-1 line-clamp-1 text-sm text-ink3">{c.insight}</p>}
                  </div>
                  <Icon name="chevron" size={16} className={`mt-2 shrink-0 text-ink3 transition-transform ${on ? 'rotate-180' : ''}`} />
                </button>
                {on && <Detail c={c} />}
              </li>
            );
          })}
        </ul>
      )}
    </>
  );
}
