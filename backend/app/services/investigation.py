"""Game Operations investigation engine.

Question answered: "A headline KPI moved. *Where* did it move, *how much* of the move does each
segment explain, and what could be behind it?"

Method
------
1. Split install cohorts into two equal windows (previous / current). The current window ends
   at the last cohort old enough to have a measurable retention value.
2. Retention-change decomposition. For every segment s with cohort weight w (share of installs)
   and retention r, the overall change is
        sum_s ( w_c*r_c - w_p*r_p )                       (exact, no residual)
   (each term centred on the previous overall rate R_p, which cancels in the sum) and each
   segment's term is split into
        rate effect = avg(w) * (r_c - r_p)                (players behave differently)
        mix effect  = (w_c - w_p) * (avg(r) - R_p)        (a different kind of player arrives)
   This avoids the classic trap of blaming a segment that merely got bigger or smaller.
3. Rank segments by contribution, profile the top one against engagement / churn / device metrics.
4. Turn the evidence into hypotheses. A hypothesis is NEVER declared true: it is labelled
   "Hypothesis requiring validation" and carries the data signals that are consistent (or not)
   with it plus a concrete validation step.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from statsmodels.stats.power import NormalIndPower
from statsmodels.stats.proportion import proportion_effectsize, proportions_ztest

from ..cache import cached
from ..db import query_df
from ..filters import data_bounds
from .power import sample_size_control

ELIGIBILITY_DAYS = {"d1": 1, "d7": 7, "d30": 30}
METRIC_LABEL = {"d1": "D1 retention", "d7": "D7 retention", "d30": "D30 retention"}
MIN_SEGMENT_PLAYERS = 40
DIMENSIONS = {
    "country": "Country",
    "platform": "Platform",
    "source": "Acquisition source",
    "first_game_mode": "First game mode",
    "device_tier": "Device tier",
}


def _periods(metric: str, window: int) -> dict[str, pd.Timestamp]:
    _, max_date = data_bounds()
    last = pd.Timestamp(max_date) - pd.Timedelta(days=ELIGIBILITY_DAYS[metric])
    cur_from = last - pd.Timedelta(days=window - 1)
    prev_to = cur_from - pd.Timedelta(days=1)
    prev_from = prev_to - pd.Timedelta(days=window - 1)
    return {"prev_from": prev_from, "prev_to": prev_to, "cur_from": cur_from, "cur_to": last}


@cached
def _load(metric: str, window: int) -> tuple[pd.DataFrame, dict[str, pd.Timestamp]]:
    p = _periods(metric, window)
    df = query_df(
        """
        SELECT player_id, country, platform, acquisition_source AS source, device, device_tier,
               COALESCE(first_game_mode, 'No match played') AS first_game_mode, install_date,
               days_since_install, d1, d7, d30, early_churn, sessions_7d, minutes_7d, matches_7d,
               tutorial_completed, crashed_7d, crashes_7d, first5_win_rate, first5_avg_placement,
               first5_avg_kills, revenue_14d
        FROM player_base
        WHERE install_date BETWEEN :prev_from AND :cur_to
        """,
        {"prev_from": p["prev_from"].date(), "cur_to": p["cur_to"].date()},
    )
    df["install_date"] = pd.to_datetime(df["install_date"])
    df["period"] = np.where(df["install_date"] >= p["cur_from"], "current", "previous")
    return df, p


# --------------------------------------------------------------------------- decomposition
def decompose(df: pd.DataFrame, keys: list[str], metric: str) -> pd.DataFrame:
    d = df[df[metric].notna()]
    agg = d.groupby(keys + ["period"]).agg(n=(metric, "size"), ret=(metric, "sum")).reset_index()
    piv = agg.pivot_table(index=keys, columns="period", values=["n", "ret"], fill_value=0)
    piv.columns = [f"{a}_{b}" for a, b in piv.columns]
    for c in ("n_current", "n_previous", "ret_current", "ret_previous"):
        if c not in piv:
            piv[c] = 0
    N_c, N_p = piv.n_current.sum(), piv.n_previous.sum()
    out = piv.reset_index()
    out["w_cur"] = out.n_current / N_c
    out["w_prev"] = out.n_previous / N_p
    r_c = np.where(out.n_current > 0, out.ret_current / out.n_current.replace(0, np.nan), np.nan)
    r_p = np.where(out.n_previous > 0, out.ret_previous / out.n_previous.replace(0, np.nan), np.nan)
    out["rate_cur"], out["rate_prev"] = r_c, r_p
    r_c_f = np.where(np.isnan(r_c), r_p, r_c)
    r_p_f = np.where(np.isnan(r_p), r_c, r_p)
    # Contributions are centred on the previous overall rate R_p. Because the weights of each
    # period sum to 1 the centring term cancels in the total (sum stays exactly = overall change),
    # but it is what makes a *growing, below-average* segment show up as a drag instead of a gain.
    R_p = out.ret_previous.sum() / N_p
    rc0, rp0 = np.nan_to_num(r_c), np.nan_to_num(r_p)
    out["contribution"] = out.w_cur * (rc0 - R_p) - out.w_prev * (rp0 - R_p)
    out["rate_effect"] = (out.w_cur + out.w_prev) / 2 * (r_c_f - r_p_f)
    out["mix_effect"] = (out.w_cur - out.w_prev) * ((r_c_f + r_p_f) / 2 - R_p)
    out["delta"] = r_c - r_p
    return out


def _rows(dec: pd.DataFrame, keys: list[str], overall_delta: float) -> list[dict[str, Any]]:
    rows = []
    for r in dec.itertuples(index=False):
        rec = {k: getattr(r, k) for k in keys}
        rec.update({
            "label": " / ".join(str(getattr(r, k)) for k in keys),
            "players_prev": int(r.n_previous), "players_cur": int(r.n_current),
            "share_prev": float(r.w_prev), "share_cur": float(r.w_cur),
            "rate_prev": None if np.isnan(r.rate_prev) else float(r.rate_prev),
            "rate_cur": None if np.isnan(r.rate_cur) else float(r.rate_cur),
            "delta_pp": None if np.isnan(r.delta) else float(r.delta * 100),
            "contribution_pp": float(r.contribution * 100),
            "rate_effect_pp": float(r.rate_effect * 100),
            "mix_effect_pp": float(r.mix_effect * 100),
            "share_of_change": float(r.contribution / overall_delta) if overall_delta else None,
            "low_sample": bool(r.n_current < MIN_SEGMENT_PLAYERS),
        })
        rows.append(rec)
    return rows


# --------------------------------------------------------------------------- profiling
def _period_stats(d: pd.DataFrame, metric: str) -> dict[str, float | None]:
    def rate(col: str, frame: pd.DataFrame | None = None) -> float | None:
        x = (frame if frame is not None else d)[col].dropna()
        return float(x.mean()) if len(x) else None

    mature = d[d["days_since_install"] >= 7]   # full first-7-day window observed
    churn_ok = d[d["early_churn"].notna()]
    ltv_ok = d[d["days_since_install"] >= 13]
    sess = mature["sessions_7d"].sum()
    return {
        "players": int(len(d)),
        "retention": rate(metric),
        "d1": rate("d1"),
        "sessions_per_player": float(mature["sessions_7d"].mean()) if len(mature) else None,
        "session_minutes": float(mature["minutes_7d"].sum() / sess) if sess else None,
        "matches_per_player": float(mature["matches_7d"].mean()) if len(mature) else None,
        "early_churn": float(churn_ok["early_churn"].mean()) if len(churn_ok) else None,
        "tutorial_rate": rate("tutorial_completed"),
        "crash_rate": float(mature["crashed_7d"].mean()) if len(mature) else None,
        # crashes per 100 sessions normalises for exposure: churned players play less, so they crash less
        "crash_per_100": float(100 * mature["crashes_7d"].sum() / sess) if sess else None,
        "first5_win_rate": rate("first5_win_rate"),
        "first5_avg_placement": rate("first5_avg_placement"),
        "first5_avg_kills": rate("first5_avg_kills"),
        "low_end_share": float((d["device_tier"] == "low").mean()) if len(d) else None,
        "payer_rate_14d": float((ltv_ok["revenue_14d"] > 0).mean()) if len(ltv_ok) else None,
    }


# key, label, unit, higher_is_better
PROFILE_METRICS = [
    ("retention", "{metric}", "pct", True),
    ("d1", "D1 retention", "pct", True),
    ("sessions_per_player", "Sessions per player (first 7 days)", "num", True),
    ("session_minutes", "Avg session duration (min)", "min", True),
    ("matches_per_player", "Matches per player (first 7 days)", "num", True),
    ("early_churn", "Early churn (no session days 8-14)", "pct", False),
    ("tutorial_rate", "Tutorial completion", "pct", True),
    ("crash_per_100", "Crashes per 100 sessions (first 7 days)", "num", False),
    ("payer_rate_14d", "Payer conversion (first 14 days)", "pct", True),
]


def profile(df: pd.DataFrame, mask: pd.Series, metric: str) -> dict[str, Any]:
    seg = df[mask]
    prev = _period_stats(seg[seg.period == "previous"], metric)
    cur = _period_stats(seg[seg.period == "current"], metric)
    items = []
    for key, label, unit, hib in PROFILE_METRICS:
        a, b = prev[key], cur[key]
        delta = None if a is None or b is None else b - a
        items.append({
            "key": key,
            "label": label.format(metric=METRIC_LABEL[metric]),
            "unit": unit,
            "higher_is_better": hib,
            "previous": a,
            "current": b,
            "delta": delta,
            "delta_pct": None if delta is None or not a else delta / a,
            "worsened": None if delta is None else ((delta < 0) if hib else (delta > 0)),
        })
    return {"players_prev": prev["players"], "players_cur": cur["players"], "metrics": items,
            "_prev": prev, "_cur": cur}


# --------------------------------------------------------------------------- hypotheses
LABEL = "Hypothesis requiring validation"


def _signal(strength: str) -> dict[str, str]:
    text = {
        "consistent": "Data consistent with this hypothesis",
        "weak": "Weak signal",
        "none": "No supporting signal in available data",
        "insufficient": "Insufficient data",
    }[strength]
    return {"strength": strength, "text": text}


def build_hypotheses(df: pd.DataFrame, seg_mask: pd.Series, seg: dict[str, Any], metric: str,
                     seg_label: str, platform: str | None) -> list[dict[str, Any]]:
    P, C = seg["_prev"], seg["_cur"]
    rest = df[~seg_mask]
    rest_cur = _period_stats(rest[rest.period == "current"], metric)
    seg_all_prev = df[seg_mask & (df.period == "previous")]
    seg_all_cur = df[seg_mask & (df.period == "current")]
    n_prev_tot = (df.period == "previous").sum()
    n_cur_tot = (df.period == "current").sum()
    share_prev = len(seg_all_prev) / n_prev_tot if n_prev_tot else 0
    share_cur = len(seg_all_cur) / n_cur_tot if n_cur_tot else 0

    def ev(metric_name: str, prev: float | None, cur: float | None, unit: str) -> dict[str, Any]:
        return {"metric": metric_name, "previous": prev, "current": cur, "unit": unit}

    out: list[dict[str, Any]] = []

    # H1 acquisition quality ------------------------------------------------------------
    d1_gap = None if C["d1"] is None or rest_cur["d1"] is None else C["d1"] - rest_cur["d1"]
    mix_up = share_prev > 0 and share_cur >= 1.5 * share_prev or (share_cur - share_prev) >= 0.02
    low_q = d1_gap is not None and d1_gap <= -0.03
    strength = "consistent" if (mix_up and low_q) else "weak" if (mix_up or low_q) else "none"
    out.append({
        "id": "acquisition_quality",
        "title": "Lower-quality acquisition traffic",
        "statement": f"The share of installs from {seg_label} grew and these players are less engaged "
                     f"from day 1, which would point to targeting / creative / network quality rather "
                     f"than a product problem.",
        "signal": _signal(strength),
        "evidence": [
            ev("Share of all installs", share_prev, share_cur, "pct"),
            ev("D1 retention: segment vs rest of players (current)", rest_cur["d1"], C["d1"], "pct"),
        ],
        "validation": "Compare cost-per-install and 14-day LTV by campaign/creative; pause the lowest "
                      "quality campaigns for a week and watch blended D7. Requires marketing spend data "
                      "(not available in this synthetic dataset).",
    })

    # H2 onboarding ----------------------------------------------------------------------
    td = None if P["tutorial_rate"] is None or C["tutorial_rate"] is None else C["tutorial_rate"] - P["tutorial_rate"]
    strength = "insufficient" if td is None else "consistent" if td <= -0.05 else "weak" if td <= -0.02 else "none"
    out.append({
        "id": "onboarding",
        "title": "Poor onboarding experience",
        "statement": f"New players in {seg_label} struggle to get through the tutorial and reach their "
                     f"first match, so they never form a habit.",
        "signal": _signal(strength),
        "evidence": [
            ev("Tutorial completion", P["tutorial_rate"], C["tutorial_rate"], "pct"),
            ev("Matches per player (first 7 days)", P["matches_per_player"], C["matches_per_player"], "num"),
            ev("Avg session duration (min)", P["session_minutes"], C["session_minutes"], "min"),
        ],
        "validation": "Instrument the onboarding funnel step by step (tutorial start -> first match -> "
                      "second session) and run an onboarding A/B test limited to this segment.",
    })

    # H3 performance --------------------------------------------------------------------
    cd = None if P["crash_per_100"] is None or C["crash_per_100"] is None else C["crash_per_100"] - P["crash_per_100"]
    ratio = None if not P["crash_per_100"] or C["crash_per_100"] is None else C["crash_per_100"] / P["crash_per_100"]
    strength = ("insufficient" if cd is None or ratio is None else
                "consistent" if (ratio >= 1.6 and cd >= 0.8) else
                "weak" if (ratio >= 1.25 and cd >= 0.3) else "none")
    plat_txt = platform or "device"
    out.append({
        "id": "performance",
        "title": f"{plat_txt} performance problems" if platform else "App performance problems",
        "statement": f"Crashes / lag on lower-end devices degrade the first sessions of {seg_label}, "
                     f"cutting play time and return visits.",
        "signal": _signal(strength),
        "evidence": [
            ev("Crashes per 100 sessions (first 7 days)", P["crash_per_100"], C["crash_per_100"], "num"),
            ev("Low-end device share", P["low_end_share"], C["low_end_share"], "pct"),
            ev("Avg session duration (min)", P["session_minutes"], C["session_minutes"], "min"),
        ],
        "validation": "Break crash-free sessions down by app version x device model; check whether a "
                      "release shipped at the start of the drop; compare D7 for crashed vs non-crashed players.",
    })

    # H4 matchmaking --------------------------------------------------------------------
    wd = None if P["first5_win_rate"] is None or C["first5_win_rate"] is None else C["first5_win_rate"] - P["first5_win_rate"]
    pd_ = None if P["first5_avg_placement"] is None or C["first5_avg_placement"] is None else C["first5_avg_placement"] - P["first5_avg_placement"]
    strength = ("insufficient" if wd is None else
                "consistent" if (wd <= -0.03 or (pd_ is not None and pd_ >= 0.5)) else
                "weak" if wd <= -0.015 else "none")
    out.append({
        "id": "matchmaking",
        "title": "Matchmaking problems",
        "statement": f"Early matches for {seg_label} are lopsided or slow to start, which hurts the "
                     f"'first win' experience.",
        "signal": _signal(strength),
        "evidence": [
            ev("Win rate, first 5 matches", P["first5_win_rate"], C["first5_win_rate"], "pct"),
            ev("Avg placement, first 5 matches", P["first5_avg_placement"], C["first5_avg_placement"], "num"),
        ],
        "validation": "Queue time, bot-fill rate and skill-gap per lobby are not in this dataset - pull "
                      "them from matchmaking logs before concluding anything.",
    })

    # H5 difficulty ---------------------------------------------------------------------
    kd = None if P["first5_avg_kills"] is None or C["first5_avg_kills"] is None else C["first5_avg_kills"] - P["first5_avg_kills"]
    strength = ("insufficient" if kd is None or wd is None else
                "consistent" if (kd <= -0.3 and wd <= -0.02) else
                "weak" if (kd <= -0.15 or wd <= -0.02) else "none")
    out.append({
        "id": "difficulty",
        "title": "New-player difficulty is too high",
        "statement": f"{seg_label} players lose too often and too early, so they quit before reaching "
                     f"the content they would enjoy.",
        "signal": _signal(strength),
        "evidence": [
            ev("Kills per match, first 5 matches", P["first5_avg_kills"], C["first5_avg_kills"], "num"),
            ev("Win rate, first 5 matches", P["first5_win_rate"], C["first5_win_rate"], "pct"),
        ],
        "validation": "Run a difficulty / bot-fill A/B test for players in their first 10 matches and "
                      "measure D1 and D7.",
    })
    for h in out:
        h["label"] = LABEL
    order = {"consistent": 0, "weak": 1, "insufficient": 2, "none": 3}
    return sorted(out, key=lambda h: order[h["signal"]["strength"]])


# --------------------------------------------------------------------------- test design
def followup_test_design(seg_cur_n: int, window: int, baseline: float) -> dict[str, Any]:
    """Sample size for a follow-up A/B test on the affected segment (80% power, alpha 5%)."""
    daily = seg_cur_n / window
    options = []
    for mde in (0.03, 0.05):
        n = sample_size_control(baseline, mde * 100)
        options.append({
            "mde_pp": mde * 100,
            "n_per_arm": n,
            "days_to_complete": int(np.ceil(2 * n / daily)) if daily > 0 else None,
        })
    return {"baseline": baseline, "daily_installs": float(daily), "options": options}


# --------------------------------------------------------------------------- public API
@cached
def investigate(metric: str = "d7", window: int = 28, country: str | None = None,
                platform: str | None = None, source: str | None = None) -> dict[str, Any]:
    df, p = _load(metric, window)
    lo, hi = data_bounds()
    need = 2 * window + ELIGIBILITY_DAYS[metric]
    d = df[df[metric].notna()]
    prev = d[d.period == "previous"][metric]
    cur = d[d.period == "current"][metric]
    if p["prev_from"] < pd.Timestamp(lo) or len(prev) < 30 or len(cur) < 30:
        raise ValueError(
            f"Not enough history for this comparison: it needs about {need} days of installs but the data covers "
            f"{(hi - lo).days + 1}. Try a shorter comparison period or import more history.")
    r_p, r_c = float(prev.mean()), float(cur.mean())
    overall_delta = r_c - r_p
    z, pval = proportions_ztest([cur.sum(), prev.sum()], [len(cur), len(prev)])

    dims = {}
    for key, label in DIMENSIONS.items():
        dec = decompose(df, [key], metric).sort_values("contribution")
        dims[key] = {"label": label, "rows": _rows(dec, [key], overall_delta)}

    seg_dec = decompose(df, ["country", "platform", "source"], metric)
    seg_rows = _rows(seg_dec.sort_values("contribution"), ["country", "platform", "source"], overall_delta)
    candidates = [r for r in seg_rows if not r["low_sample"]]

    # which segment to profile: explicit override, else the biggest negative contributor
    if country or platform or source:
        chosen = {"country": country, "platform": platform, "source": source}
    else:
        top = candidates[0] if overall_delta < 0 else sorted(candidates, key=lambda r: -r["contribution_pp"])[0]
        chosen = {k: top[k] for k in ("country", "platform", "source")}
    mask = pd.Series(True, index=df.index)
    for k, v in chosen.items():
        if v:
            mask &= df[k] == v
    seg_label = " + ".join(v for v in (chosen["platform"], chosen["source"], chosen["country"]) if v) or "All players"
    prof = profile(df, mask, metric)
    seg_ret = df[mask & df[metric].notna()]
    sp, sc = seg_ret[seg_ret.period == "previous"][metric], seg_ret[seg_ret.period == "current"][metric]
    seg_p = None
    if len(sp) > 5 and len(sc) > 5 and sp.nunique() + sc.nunique() > 1:
        seg_p = float(proportions_ztest([sc.sum(), sp.sum()], [len(sc), len(sp)])[1])
    seg_contrib = float(seg_dec.merge(
        pd.DataFrame([chosen]).dropna(axis=1), how="inner")["contribution"].sum() * 100) if any(chosen.values()) else None

    # attribute the same segment against the whole population
    ov = profile(df, pd.Series(True, index=df.index), metric)

    # device performance view on the segment's platform (all players of that platform)
    plat_mask = (df["platform"] == chosen["platform"]) if chosen["platform"] else pd.Series(True, index=df.index)
    dev_rows = []
    for tier, g in df[plat_mask].groupby("device_tier"):
        gp, gc = g[g.period == "previous"], g[g.period == "current"]
        gp7, gc7 = gp[gp.days_since_install >= 7], gc[gc.days_since_install >= 7]
        s_p, s_c = gp7.sessions_7d.sum(), gc7.sessions_7d.sum()
        dev_rows.append({
            "device_tier": tier,
            "crash100_prev": float(100 * gp7.crashes_7d.sum() / s_p) if s_p else None,
            "crash100_cur": float(100 * gc7.crashes_7d.sum() / s_c) if s_c else None,
            "players_prev": int(len(gp)), "players_cur": int(len(gc)),
            "crash_prev": float(gp7.crashed_7d.mean()) if len(gp7) else None,
            "crash_cur": float(gc7.crashed_7d.mean()) if len(gc7) else None,
            "rate_prev": float(gp[metric].mean()) if gp[metric].notna().any() else None,
            "rate_cur": float(gc[metric].mean()) if gc[metric].notna().any() else None,
            "minutes_prev": float(gp7.minutes_7d.sum() / max(gp7.sessions_7d.sum(), 1)) if len(gp7) else None,
            "minutes_cur": float(gc7.minutes_7d.sum() / max(gc7.sessions_7d.sum(), 1)) if len(gc7) else None,
        })
    tier_order = {"low": 0, "mid": 1, "high": 2}
    dev_rows.sort(key=lambda r: tier_order[r["device_tier"]])

    hyps = build_hypotheses(df, mask, prof, metric, seg_label, chosen["platform"])
    baseline = prof["_cur"]["retention"] or r_c
    design = followup_test_design(prof["players_cur"], window, baseline) if prof["players_cur"] else None

    fmt = lambda x: f"{x * 100:.1f}%"  # noqa: E731
    verb = "dropped" if overall_delta < 0 else "rose"
    return {
        "metric": metric,
        "metric_label": METRIC_LABEL[metric],
        "window_days": window,
        "periods": {k: v.date().isoformat() for k, v in p.items()},
        "problem": {
            "statement": f"{METRIC_LABEL[metric]} {verb} from {fmt(r_p)} to {fmt(r_c)}.",
            "previous": r_p, "current": r_c,
            "delta_pp": overall_delta * 100,
            "relative_change": overall_delta / r_p if r_p else None,
            "players_prev": int(len(prev)), "players_cur": int(len(cur)),
            "p_value": float(pval),
            "significant": bool(pval < 0.05),
        },
        "dimensions": dims,
        "segments": {"rows": seg_rows[:15], "searched": len(seg_rows), "min_players": MIN_SEGMENT_PLAYERS},
        "culprit": {
            "label": seg_label,
            "filters": chosen,
            "is_override": bool(country or platform or source),
            "players_prev": prof["players_prev"], "players_cur": prof["players_cur"],
            "contribution_pp": seg_contrib,
            "share_of_change": (seg_contrib / (overall_delta * 100)) if seg_contrib is not None and overall_delta else None,
            "retention_p_value": seg_p,
            "metrics": prof["metrics"],
        },
        "overall_profile": ov["metrics"],
        "device_performance": dev_rows,
        "hypotheses": hyps,
        "test_design": design,
    }


def top_segment(metric: str = "d7", window: int = 28) -> dict[str, Any]:
    """Convenience wrapper used by the Insights generator."""
    return investigate(metric, window)
