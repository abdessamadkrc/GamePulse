"""Single source of truth for the rule-based player segmentation.

The thresholds are injected into db/02_derived.sql by the seeder AND served to the UI,
so the documentation a visitor reads is exactly the logic that was executed.
Tune the numbers here, re-run the seeder (`docker compose run --rm seed --force`),
and every dashboard follows.
"""

NEW_DAYS = 7                 # installed within the last 7 days (day 0..7)
CHURN_DAYS = 30              # no session for 30+ days
RISK_DAYS = 8                # no session for 8-29 days (lapsing)
HV_REVENUE = 10.0            # lifetime spend (synthetic USD)
ENGAGED_ACTIVE_DAYS_14D = 4  # active on 4+ of the last 14 days

SQL_PARAMS = {
    "NEW_DAYS": NEW_DAYS,
    "CHURN_DAYS": CHURN_DAYS,
    "RISK_DAYS": RISK_DAYS,
    "HV_REVENUE": HV_REVENUE,
    "ENGAGED_ACTIVE_DAYS_14D": ENGAGED_ACTIVE_DAYS_14D,
}

SEGMENT_ORDER = [
    "New Players",
    "Casual Players",
    "Engaged Players",
    "High-Value Players",
    "At-Risk Players",
    "Churned Players",
]

# Evaluated top-to-bottom: the first matching rule wins.
SEGMENT_DEFINITIONS = [
    {
        "segment": "New Players",
        "priority": 1,
        "rule": f"Installed {NEW_DAYS} days ago or less",
        "intent": "Onboarding cohort - judged on early retention, not lifetime behaviour.",
    },
    {
        "segment": "Churned Players",
        "priority": 2,
        "rule": f"No session for {CHURN_DAYS}+ days",
        "intent": "Lost players. Candidates for win-back campaigns, not for in-game tuning.",
    },
    {
        "segment": "At-Risk Players",
        "priority": 3,
        "rule": f"No session for {RISK_DAYS}-{CHURN_DAYS - 1} days",
        "intent": "Lapsing players - the last window where a re-engagement push is cheap.",
    },
    {
        "segment": "High-Value Players",
        "priority": 4,
        "rule": f"Active in the last {RISK_DAYS - 1} days AND lifetime spend >= ${HV_REVENUE:.0f}",
        "intent": "Revenue core. Protect their experience first.",
    },
    {
        "segment": "Engaged Players",
        "priority": 5,
        "rule": f"Active in the last {RISK_DAYS - 1} days AND active on {ENGAGED_ACTIVE_DAYS_14D}+ of the last 14 days",
        "intent": "Habit-formed players: the healthy base that drives DAU and social loops.",
    },
    {
        "segment": "Casual Players",
        "priority": 6,
        "rule": "Everyone else who is still active",
        "intent": "Occasional players with room to grow into Engaged.",
    },
]

# Churn-risk tiers used on the Churn views: assigned from behaviour in the *prior* 30-day
# window, so we can say "which kind of player left" rather than "who is gone now".
CHURN_TIER_HV_REVENUE = 5.0     # spent >= $5 in the prior 30 days
CHURN_TIER_ENGAGED_DAYS = 8     # active on 8+ of the prior 30 days
