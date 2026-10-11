// Categorical slots come from the validated palette (CSS vars switch per theme).
export const SERIES = ['var(--s1)', 'var(--s2)', 'var(--s3)', 'var(--s4)', 'var(--s5)', 'var(--s6)', 'var(--s7)', 'var(--s8)'];

// Colour follows the ENTITY, never its rank: a filter must not repaint surviving series.
export const SOURCE_COLOR: Record<string, string> = {
  Organic: SERIES[0], 'Facebook Ads': SERIES[1], 'TikTok Ads': SERIES[2], 'Google UAC': SERIES[3],
  Influencer: SERIES[4], Referral: SERIES[5], AppLovin: SERIES[6],
};
export const PLATFORM_COLOR: Record<string, string> = { Android: SERIES[0], iOS: SERIES[1] };
export const SEGMENT_COLOR: Record<string, string> = {
  'New Players': SERIES[0], 'Casual Players': SERIES[1], 'Engaged Players': SERIES[2],
  'High-Value Players': SERIES[3], 'At-Risk Players': SERIES[4], 'Churned Players': SERIES[5],
};
export const MENA_COLOR: Record<string, string> = {
  Morocco: SERIES[0], 'Saudi Arabia': SERIES[1], UAE: SERIES[2], Egypt: SERIES[3], Algeria: SERIES[4], Tunisia: SERIES[6],
};
export const MODE_COLOR: Record<string, string> = {
  'Battle Royale': SERIES[0], 'Clash Squad': SERIES[1], Ranked: SERIES[2], 'Quick Rush': SERIES[3],
};
export const TIER_COLOR: Record<string, string> = { low: SERIES[1], mid: SERIES[0], high: SERIES[2] };
export const RET_COLOR = { d1: SERIES[0], d7: SERIES[1], d30: SERIES[2] };

export const ACCENT = 'var(--accent)';
