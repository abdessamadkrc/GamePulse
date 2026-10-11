// Plain-English definitions used by the "?" explainers and the Glossary panel.
// Rule: say what it means for a player or a decision, not how it is calculated.

export interface GlossaryEntry { term: string; plain: string; example?: string }

export const GLOSSARY: GlossaryEntry[] = [
  { term: 'Retention', plain: 'Out of every 100 new players, how many come back to the game. The most important health signal for a live game.' },
  { term: 'D1 retention', plain: 'Out of 100 players who installed, how many opened the game again exactly 1 day later. Higher is better.', example: '50% = half of new players return the next day.' },
  { term: 'D7 retention', plain: 'Out of 100 players who installed, how many played exactly 7 days later. Our headline retention number.', example: '30% = 30 of 100 new players are still playing a week in.' },
  { term: 'D30 retention', plain: 'Out of 100 players who installed, how many played exactly 30 days later. Measures long-term habit.' },
  { term: 'DAU', plain: 'Daily active users: how many different players played on a typical day.' },
  { term: 'MAU', plain: 'Monthly active users: how many different players played at least once in the last 30 days.' },
  { term: 'DAU/MAU', plain: 'Of everyone who played this month, the share who play on a typical day. Higher means players have made the game a habit.', example: '12% = a typical day has about 1 in 8 monthly players.' },
  { term: 'ARPU', plain: 'Average revenue per user: total revenue divided by all active players (payers and non-payers).' },
  { term: 'ARPPU', plain: 'Average revenue per paying user: total revenue divided by only the players who paid.' },
  { term: 'Conversion', plain: 'The share of active players who paid at least once in the period.' },
  { term: 'Churn', plain: 'Players who stopped playing. Here: installed 30+ days ago and no session for the last 30 days.' },
  { term: 'Early churn', plain: 'New players who disappear in their second week (no session on days 8 to 14 after install).' },
  { term: 'Cohort', plain: 'A group of players who installed in the same period, for example the same week. We follow each group over time to compare them fairly.' },
  { term: 'Segment', plain: 'A group of players defined by a rule, such as "Engaged" or "At-Risk". Segments describe players today; they are not a cause of anything.' },
  { term: 'Percentage points (pp)', plain: 'The plain difference between two percentages. 31% to 25% is a 6 pp drop (not "6%", which would be a different number).' },
  { term: 'Statistically significant', plain: 'Unlikely to be just luck. A p-value below 0.05 means that, if nothing had really changed, you would see a gap this big less than 5% of the time.' },
  { term: '95% interval', plain: 'The range the true value probably sits in. If it includes zero, we cannot say there is a real difference.' },
  { term: 'Hypothesis', plain: 'A possible explanation that has not been proven. GamePulse always labels these "requiring validation".' },
  { term: 'Contribution', plain: 'How many points of the overall change come from one group. All groups add up exactly to the total change.' },
  { term: 'Rate effect', plain: 'Players in this group behave differently than before (for example, they now quit sooner).' },
  { term: 'Mix effect', plain: 'A different kind of player now makes up more of the installs (for example, more low-quality traffic), even if each group behaves as before.' },
  { term: 'A/B test', plain: 'Show half of new players the current version (control) and half the new one (test), then compare the results. The only way to know a change caused an improvement.' },
  { term: 'Guardrail', plain: 'A number that must not get worse while you try to improve another, such as revenue or crashes during a retention test.' },
  { term: 'Sample-ratio mismatch (SRM)', plain: 'A warning that the two groups are not the size they should be. It usually means the test is set up wrongly, so do not trust its result.' },
  { term: 'Power / detectable lift', plain: 'How small a real improvement your test can reliably notice. A smaller sample can only detect big improvements.' },
  { term: 'Peeking', plain: 'Checking results early and stopping when they look good. It produces false wins, so decide only at the planned sample size.' },
  { term: 'Novelty effect', plain: 'An improvement that fades because players were just curious about something new.' },
  { term: 'Holm correction', plain: 'An adjustment for looking at many results at once, so a few lucky ones are not mistaken for real findings.' },
];

/** KPI keys (as used by /api/kpis) -> glossary term */
export const TERM_BY_KEY: Record<string, string> = {
  d1: 'D1 retention', d7: 'D7 retention', d30: 'D30 retention', dau: 'DAU', mau: 'MAU', dau_mau: 'DAU/MAU',
  arpu: 'ARPU', arppu: 'ARPPU', conversion: 'Conversion', churn_rate: 'Churn', early_churn_rate: 'Early churn',
};

export const findTerm = (t: string) => GLOSSARY.find((g) => g.term === t);
