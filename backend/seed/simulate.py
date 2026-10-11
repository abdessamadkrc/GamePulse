"""Synthetic player-behaviour simulator for GamePulse.

ALL DATA PRODUCED HERE IS SYNTHETIC. It is not real telemetry and is not affiliated
with Garena, Free Fire or any other publisher.

The simulator is deliberately *causal*: every player has a latent "stickiness" (a logit)
built from country, platform, acquisition source, device tier, noise and a handful of
planted effects. Retention, session length, spend and crash exposure are all derived
from that latent value, so the analytics layer finds structure that really is in the data
instead of statistical accident.

Planted effects (documented in the README, discoverable through the Investigation page):

  1. TikTok campaign surge   - from install day SURGE_DAY a large share of installs is
     low-quality TikTok traffic on Android, concentrated in Morocco.
  2. Android performance regression - from SURGE_DAY crash rates jump on low-end Android.
  3. Onboarding experiment   - exp_onboarding_v2 (installs in days 30-56): the improved
     onboarding lifts stickiness, so D7 retention is genuinely higher in the test arm.
  4. Store-bundle experiment - exp_store_bundle_v1 (installs in days 0-29): a tiny
     conversion nudge that is NOT detectable at this sample size (a true "no decision").
  5. Live-ops event          - an anniversary event on days 60-66 lifts DAU.
"""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd
from scipy.special import expit, ndtr

START = date(2025, 1, 1)
DAYS = 120
END = START + timedelta(days=DAYS - 1)
SURGE_DAY = 85           # first install day affected by the TikTok surge / Android regression
SURGE_SHARE = 0.20       # share of post-surge installs that are surge traffic
LIVEOPS_DAYS = (60, 66)  # anniversary event window (absolute days)
ONB_WINDOW = (30, 56)    # install-day window of the onboarding experiment
STORE_WINDOW = (0, 29)   # install-day window of the store experiment
ONB_LIFT = 0.30          # logit lift of the improved onboarding
STORE_LIFT = 0.06        # logit lift of the store bundle on payer propensity
BASE_LOGIT = -0.06

COUNTRIES = ["Morocco", "Saudi Arabia", "UAE", "Egypt", "Algeria", "Tunisia",
             "Turkey", "Brazil", "Indonesia", "France"]
COUNTRY_SHARE = np.array([14, 12, 7, 14, 9, 5, 10, 12, 11, 6], float)
COUNTRY_SHARE /= COUNTRY_SHARE.sum()
ANDROID_SHARE = np.array([0.85, 0.60, 0.55, 0.87, 0.88, 0.84, 0.75, 0.82, 0.90, 0.50])
COUNTRY_LOGIT = np.array([0.00, 0.12, 0.16, -0.06, -0.10, 0.05, 0.05, -0.05, 0.00, 0.10])
COUNTRY_PAY = np.array([-0.15, 0.45, 0.50, -0.25, -0.30, -0.20, 0.05, -0.05, -0.10, 0.20])
# low / mid / high device-tier mix for Android players, per country
ANDROID_TIERS = np.array([
    [0.45, 0.42, 0.13], [0.15, 0.40, 0.45], [0.12, 0.38, 0.50], [0.47, 0.41, 0.12],
    [0.48, 0.40, 0.12], [0.44, 0.43, 0.13], [0.30, 0.45, 0.25], [0.38, 0.45, 0.17],
    [0.42, 0.43, 0.15], [0.22, 0.43, 0.35],
])

SOURCES = ["Organic", "Facebook Ads", "TikTok Ads", "Google UAC", "Influencer", "Referral", "AppLovin"]
SOURCE_SHARE = np.array([0.26, 0.20, 0.12, 0.18, 0.10, 0.06, 0.08])
SOURCE_LOGIT = np.array([0.20, -0.05, -0.22, 0.00, 0.05, 0.35, -0.30])
TIKTOK = SOURCES.index("TikTok Ads")
SURGE_COUNTRY_SHARE = np.array([0.46, 0.05, 0.02, 0.17, 0.15, 0.06, 0.03, 0.02, 0.03, 0.01])
SURGE_COUNTRY_SHARE /= SURGE_COUNTRY_SHARE.sum()

DEVICES = {
    "Android": {
        "low": ["Galaxy A03", "Redmi 9A", "Infinix Hot 10", "Tecno Spark 7", "Itel A48"],
        "mid": ["Galaxy A32", "Redmi Note 10", "Realme 8", "Oppo A54"],
        "high": ["Galaxy S21", "Galaxy S23", "Xiaomi 12", "Pixel 7"],
    },
    "iOS": {
        "mid": ["iPhone 8", "iPhone SE", "iPhone 11"],
        "high": ["iPhone 12", "iPhone 13", "iPhone 14"],
    },
}
TIER_LOGIT = {"low": -0.15, "mid": 0.0, "high": 0.10}
CRASH_RATE = {  # per-session probability
    ("Android", "low"): 0.022, ("Android", "mid"): 0.010, ("Android", "high"): 0.005,
    ("iOS", "mid"): 0.003, ("iOS", "high"): 0.002,
}

GAME_MODES = ["Battle Royale", "Clash Squad", "Ranked", "Quick Rush"]
MODE_ALPHA = [3.0, 2.2, 1.6, 2.0]
MODE_MINUTES = np.array([14.0, 9.0, 16.0, 5.0])
MODE_KILLS = np.array([1.3, 1.8, 1.5, 2.2])
MODE_TEAMS = np.array([12, 2, 12, 2])

HOUR_P = np.array([0, 0, 0, 0, 0, 0, .01, .02, .03, .04, .04, .05, .06, .06, .06, .07,
                   .07, .08, .09, .10, .10, .08, .04, 0], float)
HOUR_P /= HOUR_P.sum()

ITEMS = {
    "starter_pack": ([1.99, 2.99, 4.99], [0.5, 0.3, 0.2]),
    "gems_pack": ([0.99, 1.99, 4.99, 9.99, 19.99, 49.99, 99.99], None),
    "battle_pass": ([9.99], [1.0]),
    "skin_bundle": ([4.99, 9.99, 19.99], [0.4, 0.4, 0.2]),
    "weapon_crate": ([0.99, 2.99, 4.99], [0.5, 0.3, 0.2]),
}
GEM_WEIGHTS = {  # by spend tier
    "minnow": [0.35, 0.30, 0.25, 0.09, 0.01, 0.0, 0.0],
    "dolphin": [0.10, 0.15, 0.30, 0.30, 0.13, 0.02, 0.0],
    "whale": [0.0, 0.02, 0.10, 0.25, 0.33, 0.22, 0.08],
}

EXPERIMENT_CATALOG = [
    {
        "experiment_id": "exp_onboarding_v2",
        "name": "New Player Onboarding",
        "description": "Improved first-session onboarding: shorter tutorial, guided first match, "
                       "clearer reward preview.",
        "hypothesis": "A guided first match and shorter tutorial will help new players reach "
                      "their 'aha' moment faster and increase D7 retention.",
        "primary_kpi": "d7_retention",
        "control_label": "Old onboarding",
        "test_label": "Improved onboarding",
        "start_date": START + timedelta(days=ONB_WINDOW[0]),
        "end_date": START + timedelta(days=ONB_WINDOW[1]),
    },
    {
        "experiment_id": "exp_store_bundle_v1",
        "name": "Personalised Starter Bundle",
        "description": "Store shows a personalised starter bundle on day 1 instead of the "
                       "generic offer.",
        "hypothesis": "A personalised starter bundle will increase 14-day payer conversion.",
        "primary_kpi": "conversion_14d",
        "control_label": "Generic starter offer",
        "test_label": "Personalised bundle",
        "start_date": START + timedelta(days=STORE_WINDOW[0]),
        "end_date": START + timedelta(days=STORE_WINDOW[1]),
    },
]


def _build_devices() -> pd.DataFrame:
    rows = [(d, plat, tier) for plat, tiers in DEVICES.items() for tier, ds in tiers.items() for d in ds]
    return pd.DataFrame(rows, columns=["device", "platform", "device_tier"])


def simulate(n_players: int = 52_000, seed: int = 42) -> dict[str, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    n = n_players

    # ------------------------------------------------------------------ installs
    day = np.arange(DAYS)
    dow = (START.weekday() + day) % 7
    w = (1 + 0.0035 * day) * np.where(dow >= 5, 1.2, 1.0)
    w[SURGE_DAY:] *= 1.18
    install_day = np.sort(rng.choice(DAYS, size=n, p=w / w.sum()))

    surge = (install_day >= SURGE_DAY) & (rng.random(n) < SURGE_SHARE)
    country_idx = rng.choice(len(COUNTRIES), size=n, p=COUNTRY_SHARE)
    source_idx = rng.choice(len(SOURCES), size=n, p=SOURCE_SHARE)
    country_idx[surge] = rng.choice(len(COUNTRIES), size=surge.sum(), p=SURGE_COUNTRY_SHARE)
    source_idx[surge] = TIKTOK
    is_android = rng.random(n) < ANDROID_SHARE[country_idx]
    is_android[surge] = rng.random(surge.sum()) < 0.93

    tier_idx = np.zeros(n, int)  # 0 low 1 mid 2 high
    a_idx = np.where(is_android)[0]
    u = rng.random(len(a_idx))
    cum = np.cumsum(ANDROID_TIERS[country_idx[a_idx]], axis=1)
    tier_idx[a_idx] = (u[:, None] > cum).sum(axis=1).clip(0, 2)
    i_idx = np.where(~is_android)[0]
    tier_idx[i_idx] = np.where(rng.random(len(i_idx)) < 0.55, 2, 1)

    devices_df = _build_devices()
    tier_names = np.array(["low", "mid", "high"])
    device_name = np.empty(n, object)
    for plat_name, mask in (("Android", is_android), ("iOS", ~is_android)):
        for t, tname in enumerate(tier_names):
            m = mask & (tier_idx == t)
            options = DEVICES[plat_name].get(tname)
            if m.any() and options:
                device_name[m] = rng.choice(options, size=m.sum())

    platform = np.where(is_android, "Android", "iOS")
    country = np.array(COUNTRIES)[country_idx]
    source = np.array(SOURCES)[source_idx]

    # ------------------------------------------------------------------ experiments
    onb_mask = (install_day >= ONB_WINDOW[0]) & (install_day <= ONB_WINDOW[1])
    store_mask = (install_day >= STORE_WINDOW[0]) & (install_day <= STORE_WINDOW[1]) & (rng.random(n) < 0.6)
    onb_test = onb_mask & (rng.random(n) < 0.5)
    store_test = store_mask & (rng.random(n) < 0.5)

    # ------------------------------------------------------------------ latent stickiness
    post = install_day >= SURGE_DAY
    tiktok_android_post = post & (source_idx == TIKTOK) & is_android
    low_android_post = post & is_android & (tier_idx == 0)
    logit = (
        BASE_LOGIT
        + COUNTRY_LOGIT[country_idx]
        + np.where(is_android, 0.0, 0.15)
        + SOURCE_LOGIT[source_idx]
        + np.array([TIER_LOGIT["low"], TIER_LOGIT["mid"], TIER_LOGIT["high"]])[tier_idx]
        + rng.normal(0, 0.85, n)
    )
    logit = logit - 0.95 * tiktok_android_post - 0.35 * (tiktok_android_post & (country == "Morocco"))
    logit = logit - 0.35 * low_android_post
    logit = logit + ONB_LIFT * onb_test
    s = expit(logit)

    # ------------------------------------------------------------------ daily activity matrix
    j = np.arange(DAYS)
    h = np.where(j == 0, 1.0, np.maximum(j, 1) ** -0.20 * np.exp(-(np.maximum(j, 1) - 1) / 45.0))
    abs_day = install_day[:, None] + j[None, :]
    absc = np.clip(abs_day, 0, DAYS - 1)
    boost = np.where((absc >= LIVEOPS_DAYS[0]) & (absc <= LIVEOPS_DAYS[1]), 1.30, 1.0)
    boost = boost * np.where(((START.weekday() + absc) % 7) >= 5, 1.08, 1.0)
    p = np.clip(s[:, None] * h[None, :] * boost, 0, 0.97)
    A = rng.random((n, DAYS)) < p
    A[:, 0] = True
    A &= abs_day < DAYS
    pi, ji = np.nonzero(A)
    n_ad = len(pi)
    ad_abs = install_day[pi] + ji

    # ------------------------------------------------------------------ sessions
    lam = 0.25 + 1.45 * s
    k = 1 + np.where(ji == 0, rng.poisson(0.9, n_ad), rng.poisson(lam[pi]))
    ses_ad = np.repeat(np.arange(n_ad), k)
    ses_p = pi[ses_ad]
    ses_j = ji[ses_ad]
    ses_abs = ad_abs[ses_ad]
    n_ses = len(ses_p)
    start_epoch = int(pd.Timestamp(START).timestamp())
    sec = rng.choice(24, size=n_ses, p=HOUR_P) * 3600 + rng.integers(0, 3600, n_ses)
    ses_ts = start_epoch + ses_abs.astype(np.int64) * 86400 + sec

    dur_mult = np.ones(n)
    dur_mult[tiktok_android_post] *= 0.80
    dur_mult[low_android_post] *= 0.90
    mu = (8 + 24 * s) * dur_mult
    sigma = 0.55
    dur = mu[ses_p] * np.exp(rng.normal(0, sigma, n_ses) - sigma ** 2 / 2)
    dur = np.round(np.clip(dur, 1, 150), 1)

    sessions = pd.DataFrame({
        "session_id": np.arange(1, n_ses + 1),
        "player_id": ses_p + 1,
        "session_start": pd.to_datetime(ses_ts, unit="s"),
        "session_duration_minutes": dur,
    })

    # ------------------------------------------------------------------ matches
    skill = rng.normal(0, 1, n)
    mode_pref = rng.dirichlet(MODE_ALPHA, n)
    m_per = rng.poisson(0.55 * dur / 10.0)
    n_m = int(m_per.sum())
    m_ses = np.repeat(np.arange(n_ses), m_per)
    m_p = ses_p[m_ses]
    cumpref = np.cumsum(mode_pref, axis=1)
    mode = (rng.random(n_m)[:, None] > cumpref[m_p]).sum(axis=1).clip(0, 3)
    m_dur = np.clip(MODE_MINUTES[mode] * (1 + rng.normal(0, 0.2, n_m)), 2, 30)
    slack = np.maximum(dur[m_ses] - m_dur, 0)
    day_start = start_epoch + ses_abs[m_ses].astype(np.int64) * 86400
    m_ts = np.minimum(ses_ts[m_ses] + (rng.random(n_m) * slack * 60).astype(np.int64), day_start + 86399)
    kills = rng.poisson(MODE_KILLS[mode] * np.exp(0.35 * skill[m_p]))
    uu = ndtr(0.7 * skill[m_p] + rng.normal(0, 1, n_m))
    placement = 1 + np.minimum(((1 - uu) * MODE_TEAMS[mode]).astype(int), MODE_TEAMS[mode] - 1)
    order = np.argsort(m_ts, kind="stable")
    matches = pd.DataFrame({
        "match_id": np.arange(1, n_m + 1),
        "player_id": (m_p + 1)[order],
        "match_date": pd.to_datetime(m_ts[order], unit="s"),
        "game_mode": np.array(GAME_MODES)[mode][order],
        "kills": kills[order].astype(np.int16),
        "placement": placement[order].astype(np.int16),
        "match_duration_minutes": np.round(m_dur[order], 1),
        "result": np.where(placement[order] == 1, "win", "loss"),
    })

    # ------------------------------------------------------------------ purchases
    is_ios = ~is_android
    pay_logit = (-3.05 + 2.2 * (s - 0.5) + COUNTRY_PAY[country_idx] + 0.35 * is_ios
                 + STORE_LIFT * store_test)
    payer = rng.random(n) < expit(pay_logit)
    tier_u = rng.random(n)
    gulf = np.isin(country, ["Saudi Arabia", "UAE"])
    whale_p = np.where(gulf, 0.045, 0.028)
    spend_tier = np.where(tier_u < whale_p, "whale", np.where(tier_u < whale_p + 0.22, "dolphin", "minnow"))

    ad_start = np.searchsorted(pi, np.arange(n))
    ad_end = np.searchsorted(pi, np.arange(n), side="right")
    p_rows = []
    item_names = list(ITEMS)
    for pid in np.where(payer)[0]:
        tier = spend_tier[pid]
        cnt = {"whale": 8 + rng.poisson(8), "dolphin": 2 + rng.poisson(2), "minnow": 1 + rng.poisson(0.5)}[tier]
        offs = ji[ad_start[pid]:ad_end[pid]]
        wts = np.exp(-offs / 12.0)
        picks = rng.choice(len(offs), size=cnt, p=wts / wts.sum())
        picks.sort()
        for idx_, pick in enumerate(picks):
            if idx_ == 0 and rng.random() < 0.45:
                item = "starter_pack"
            else:
                item = rng.choice(["gems_pack", "battle_pass", "skin_bundle", "weapon_crate"],
                                  p=[0.58, 0.14, 0.18, 0.10])
            prices, probs = ITEMS[item]
            if item == "gems_pack":
                probs = GEM_WEIGHTS[tier]
            amount = float(rng.choice(prices, p=np.array(probs) / np.sum(probs)))
            absd = install_day[pid] + int(offs[pick])
            t = start_epoch + absd * 86400 + int(rng.choice(24, p=HOUR_P)) * 3600 + int(rng.integers(0, 3600))
            p_rows.append((pid + 1, t, amount, item))
    purchases = pd.DataFrame(p_rows, columns=["player_id", "ts", "amount", "item_type"]).sort_values("ts")
    purchases.insert(0, "purchase_id", np.arange(1, len(purchases) + 1))
    purchases["purchase_date"] = pd.to_datetime(purchases.pop("ts"), unit="s")
    purchases = purchases[["purchase_id", "player_id", "purchase_date", "amount", "item_type"]]

    # ------------------------------------------------------------------ events
    ev_parts = []

    def add(name: str, pid_idx: np.ndarray, ts: np.ndarray) -> None:
        ev_parts.append(pd.DataFrame({"player_id": pid_idx + 1, "event_name": name, "ts": ts}))

    big = np.iinfo(np.int64).max
    day_first = np.full(n_ad, big, np.int64)
    np.minimum.at(day_first, ses_ad, ses_ts)
    first_ts = np.full(n, big, np.int64)
    d0 = ji == 0
    first_ts[pi[d0]] = day_first[d0]

    pids = np.arange(n)
    add("first_open", pids, first_ts)
    add("tutorial_begin", pids, first_ts + 20)
    tut_logit = (0.4 + 1.6 * (s - 0.5) + 0.7 * onb_test - 0.6 * tiktok_android_post
                 - 0.3 * low_android_post)
    done = rng.random(n) < expit(tut_logit)
    add("tutorial_complete", pids[done], first_ts[done] + rng.integers(240, 720, done.sum()))

    later = ji > 0
    add("daily_login", pi[later], day_first[later])
    for name, prob in (("level_up", 0.45), ("store_view", 0.12), ("ad_watched", 0.22), ("friend_invite", 0.02)):
        m = rng.random(n_ad) < prob
        add(name, pi[m], day_first[m] + rng.integers(300, 2400, m.sum()))
    in_live = (ad_abs >= LIVEOPS_DAYS[0]) & (ad_abs <= LIVEOPS_DAYS[1])
    weekend_evt = ((START.weekday() + ad_abs) % 7) == 5
    m = (in_live & (rng.random(n_ad) < 0.45)) | (weekend_evt & (rng.random(n_ad) < 0.10))
    add("liveops_event_join", pi[m], day_first[m] + rng.integers(600, 3000, m.sum()))

    base_crash = np.array([[CRASH_RATE.get(("Android" if a else "iOS", t), 0.003)
                            for t in ("low", "mid", "high")] for a in (True, False)])
    crash_p = base_crash[(~is_android).astype(int), tier_idx]
    crash_p = np.where(low_android_post, 0.055, crash_p)
    crash_p = np.where(post & is_android & (tier_idx == 1), crash_p * 1.4, crash_p)
    crash_s = rng.random(n_ses) < crash_p[ses_p]
    add("crash", ses_p[crash_s], ses_ts[crash_s] + (rng.random(crash_s.sum()) * dur[crash_s] * 60).astype(np.int64))

    events = pd.concat(ev_parts, ignore_index=True).sort_values("ts", kind="stable").reset_index(drop=True)
    events.insert(0, "event_id", np.arange(1, len(events) + 1))
    events["event_date"] = pd.to_datetime(events.pop("ts"), unit="s")
    events = events[["event_id", "player_id", "event_name", "event_date"]]

    # ------------------------------------------------------------------ assemble
    install_dates = pd.to_datetime(START) + pd.to_timedelta(install_day, unit="D")
    players = pd.DataFrame({
        "player_id": np.arange(1, n + 1),
        "country": country,
        "platform": platform,
        "device": device_name,
        "install_date": install_dates.date,
        "acquisition_source": source,
    })

    exp_rows = []
    for exp_id, mask, test in (("exp_onboarding_v2", onb_mask, onb_test),
                               ("exp_store_bundle_v1", store_mask, store_test)):
        idx = np.where(mask)[0]
        exp_rows.append(pd.DataFrame({
            "experiment_id": exp_id,
            "player_id": idx + 1,
            "variant": np.where(test[idx], "test", "control"),
            "assignment_date": install_dates[idx].date,
        }))
    experiments = pd.concat(exp_rows, ignore_index=True)

    return {
        "devices": devices_df,
        "players": players,
        "sessions": sessions,
        "matches": matches,
        "purchases": purchases,
        "events": events,
        "experiment_catalog": pd.DataFrame(EXPERIMENT_CATALOG),
        "experiments": experiments,
        "meta": pd.DataFrame({
            "key": ["min_date", "max_date", "data_label", "seed", "surge_day"],
            "value": [START.isoformat(), END.isoformat(),
                      "SYNTHETIC portfolio data - not affiliated with Garena or Free Fire",
                      str(seed), (START + timedelta(days=SURGE_DAY)).isoformat()],
        }),
    }


if __name__ == "__main__":  # quick calibration printout
    import sys
    t = simulate(int(sys.argv[1]) if len(sys.argv) > 1 else 52_000)
    pl, se = t["players"], t["sessions"]
    print({k: len(v) for k, v in t.items()})
    se["d"] = se.session_start.dt.date
    act = se.groupby(["player_id", "d"]).size().reset_index()[["player_id", "d"]]
    act = act.merge(pl[["player_id", "install_date", "country", "platform", "acquisition_source"]], on="player_id")
    act["off"] = (pd.to_datetime(act.d) - pd.to_datetime(act.install_date)).dt.days
    pl["inst"] = pd.to_datetime(pl.install_date)
    pl["day"] = (pl.inst - pd.Timestamp(START)).dt.days
    for N in (1, 7, 30):
        ret = set(act.loc[act.off == N, "player_id"])
        pl[f"d{N}"] = pl.player_id.isin(ret).astype(float).where(pl.day + N <= DAYS - 1)
    print(pl[["d1", "d7", "d30"]].mean())
    cur = pl[(pl.day >= 85) & (pl.day <= 112)]
    prv = pl[(pl.day >= 57) & (pl.day <= 84)]
    print("D7 prev", prv.d7.mean(), "cur", cur.d7.mean(), "n", len(prv), len(cur))
    print("revenue", t["purchases"].amount.sum(), "payers", t["purchases"].player_id.nunique())
