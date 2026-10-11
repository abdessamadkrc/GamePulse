"""Experiment Hub: plan a test, monitor it while it runs, and read it without fooling yourself.

  plan()      sample size, duration and a written measurement plan for a proposed test
  timeline()  cumulative lift by enrolment day, sample balance over time, peeking and novelty checks

The final readout (statistics, recommendation) stays in services/experiments.py.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from scipy import stats

from ..cache import cached
from ..db import query_df
from .experiments import ALPHA, KPI_INDEX, _load
from .power import mde_pp, sample_size_control

KPI_PLAN = {
    "d1": {"label": "D1 retention", "maturity_days": 1},
    "d7": {"label": "D7 retention", "maturity_days": 7},
    "d30": {"label": "D30 retention", "maturity_days": 30},
    "conversion_14d": {"label": "Payer conversion (14 days)", "maturity_days": 14},
}
GUARDRAILS = {
    "d1": ["Payer conversion (14d)", "Crashes per 100 sessions", "Sessions per player (first 7 days)"],
    "d7": ["Payer conversion (14d)", "Revenue per player (14d)", "Crashes per 100 sessions"],
    "d30": ["Payer conversion (14d)", "Revenue per player (14d)", "D1 retention"],
    "conversion_14d": ["D1 retention", "D7 retention", "Revenue per player (14d)", "Crashes per 100 sessions"],
}


# --------------------------------------------------------------------------- planner
def plan(kpi: str, baseline: float, lift_pp: float, power: float, alpha: float, daily: float,
         arms: int, test_share: float) -> dict[str, Any]:
    """Sample size, duration and a written measurement plan for a proposed A/B test on a proportion KPI."""
    meta = KPI_PLAN[kpi]
    a_adj = alpha / (arms - 1) if arms > 2 else alpha          # Bonferroni vs control when several variants
    share = test_share if arms == 2 else 1.0 / arms
    ratio = share / (1 - share) if arms == 2 else 1.0

    def size(lift: float) -> tuple[int, int, int]:
        n_c = sample_size_control(baseline, lift, power, a_adj, ratio)
        n_t = int(np.ceil(n_c * ratio))
        return n_c, n_t, n_c + n_t * (arms - 1)

    n_c, n_t, total = size(lift_pp)
    days = int(np.ceil(total / daily))
    readout = days + meta["maturity_days"]

    sens = []
    for lift in (1, 2, 3, 5, 8, 10):
        if baseline + lift / 100 < 0.999:
            c, _, tot = size(lift)
            sens.append({"lift_pp": lift, "n_control": c, "total": tot, "days": int(np.ceil(tot / daily))})
    curve = []
    for lift in range(1, 13):
        if baseline + lift / 100 < 0.999:
            curve.append({"lift": float(lift), "n_control": size(float(lift))[0]})

    n28 = daily * 28
    nc28 = int(n28 * (1 - share)) if arms == 2 else int(n28 / arms)
    nt28 = int(n28 * share) if arms == 2 else int(n28 / arms)
    mde28 = mde_pp(baseline, nc28, nt28, power, a_adj) if min(nc28, nt28) > 1 else None

    warnings: list[str] = []
    if days > 60:
        warnings.append(f"At {daily:.0f} eligible players per day this test needs {days} days to enrol. Consider a larger "
                        f"target lift, a higher-traffic segment, or a more sensitive KPI.")
    if mde28 is not None and mde28 > lift_pp * 1.5:
        warnings.append(f"In 28 days you could only detect about {mde28:.1f} pp, well above your {lift_pp:.1f} pp target.")
    if arms > 2:
        warnings.append(f"With {arms} arms the significance level is split ({alpha:.3f} to {a_adj:.4f} per comparison) "
                        f"so the family-wise error stays at {alpha:.0%}.")

    return {
        "inputs": {"kpi": kpi, "kpi_label": meta["label"], "baseline": baseline, "lift_pp": lift_pp, "power": power,
                   "alpha": alpha, "alpha_per_comparison": a_adj, "daily": daily, "arms": arms, "test_share": share},
        "result": {"n_control": n_c, "n_per_variant": n_t, "total": total, "enrol_days": days,
                   "readout_day": readout, "mde_28d_pp": mde28, "target_rate": baseline + lift_pp / 100},
        "sensitivity": sens,
        "curve": curve,
        "warnings": warnings,
        "measurement_plan": {
            "primary_kpi": f"{meta['label']}: at least +{lift_pp:g} pp over a {baseline * 100:.1f}% baseline",
            "guardrails": [f"{g}: no significant drop (Holm-adjusted p < 0.05); do not ship if the 95% CI lower bound "
                           f"is below -0.5 pp" for g in GUARDRAILS[kpi]],
            "checkpoints": [
                {"day": int(np.ceil(days / 2)), "what": f"About 50% enrolled. Check sample balance (SRM) and guardrails only. "
                                                       f"Do NOT read {meta['label']} yet."},
                {"day": days, "what": "Enrolment complete. Stop assigning players."},
                {"day": readout, "what": f"{meta['label']} is mature for the last enrolee. Run the single planned analysis."},
            ],
            "stop_rules": [
                "Sample-ratio mismatch (p < 0.001): stop and fix assignment before reading any result.",
                "A guardrail is significantly worse: pause and investigate.",
                "Never stop early because a daily number looks significant (peeking inflates false positives).",
            ],
            "ship_rule": f"Ship (staged 25% -> 50% -> 100%) only if {meta['label']} is significantly higher, the 95% CI "
                         f"excludes 0, and no guardrail regresses.",
        },
        "note": "Two-sided test on a proportion using Cohen's h (statsmodels NormalIndPower).",
    }


# --------------------------------------------------------------------------- monitor
def _lift_by_day(experiment_id: str) -> list[dict[str, Any]]:
    """Retention difference (test - control) on each day since assignment: does the lift fade as exposure ages?"""
    df = query_df("""
        SELECT e.variant, k.k AS day_n, COUNT(*) AS n, COUNT(a.player_id) AS ret
        FROM experiments e
        CROSS JOIN generate_series(1, 14) AS k(k)
        LEFT JOIN player_daily_activity a ON a.player_id = e.player_id
             AND a.activity_date = e.assignment_date + k.k AND a.sessions > 0
        WHERE e.experiment_id = :eid
          AND e.assignment_date + k.k <= (SELECT value::date FROM meta_info WHERE key = 'max_date')
        GROUP BY 1, 2 ORDER BY 2, 1
    """, {"eid": experiment_id})
    out = []
    for d, g in df.groupby("day_n"):
        c, t = g[g.variant == "control"], g[g.variant == "test"]
        if c.empty or t.empty:
            continue
        nc, rc, nt, rt = int(c.n.iloc[0]), int(c.ret.iloc[0]), int(t.n.iloc[0]), int(t.ret.iloc[0])
        pc, pt = rc / nc, rt / nt
        se = float(np.sqrt(pc * (1 - pc) / nc + pt * (1 - pt) / nt))
        row = {"day": int(d), "n_control": nc, "ret_control": rc, "n_test": nt, "ret_test": rt,
               "control": pc, "test": pt, "diff": pt - pc,
               "ci_low": pt - pc - 1.96 * se, "ci_high": pt - pc + 1.96 * se,
               "rel_lift": None, "rel_ci_low": None, "rel_ci_high": None}
        if pc > 0 and pt > 0 and rc > 0 and rt > 0:
            # relative lift (test / control - 1) with a log-ratio interval: robust to baseline decay
            se_log = float(np.sqrt((1 - pc) / (nc * pc) + (1 - pt) / (nt * pt)))
            lr = float(np.log(pt / pc))
            row.update({"rel_lift": float(np.exp(lr) - 1), "rel_ci_low": float(np.exp(lr - 1.96 * se_log) - 1),
                        "rel_ci_high": float(np.exp(lr + 1.96 * se_log) - 1)})
        out.append(row)
    return out


def _pooled_rel(rows: list[dict[str, Any]]) -> tuple[float, float, float] | None:
    """Relative lift (test / control - 1) pooled over several days, with a log-ratio interval."""
    nc, rc = sum(r["n_control"] for r in rows), sum(r["ret_control"] for r in rows)
    nt, rt = sum(r["n_test"] for r in rows), sum(r["ret_test"] for r in rows)
    if min(rc, rt) == 0:
        return None
    pc, pt = rc / nc, rt / nt
    se = float(np.sqrt((1 - pc) / (nc * pc) + (1 - pt) / (nt * pt)))
    lr = float(np.log(pt / pc))
    return float(np.exp(lr) - 1), float(np.exp(lr - 1.96 * se) - 1), float(np.exp(lr + 1.96 * se) - 1)


def _fade(lift: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Novelty check on RELATIVE lift, pooled over days 1-3 (early) vs days 10-14 (late).
    Absolute lift always shrinks as retention itself decays, so it would flag every test; a real novelty
    effect shows the relative lift shrinking. Pooling avoids calling it from one noisy day."""
    early = _pooled_rel([p for p in lift if 1 <= p["day"] <= 3])
    late = _pooled_rel([p for p in lift if 10 <= p["day"] <= 14])
    if early is None or late is None:
        return None
    ratio = late[0] / early[0] if early[0] else None
    early_real = early[1] > 0 or early[2] < 0
    flag = bool(early_real and ratio is not None and ratio < 0.5)
    return {"early_rel": early[0], "late_rel": late[0], "early_ci": [early[1], early[2]], "late_ci": [late[1], late[2]],
            "ratio": ratio, "flag": flag,
            "text": ("The relative lift in days 10-14 is less than half of days 1-3: a possible novelty effect. "
                     "Plan the readout for later cohorts, not the first days." if flag else
                     "The relative lift holds between days 1-3 and days 10-14: no sign of a fading novelty effect. "
                     "(The absolute gap narrows only because retention itself decays.)")}


@cached
def timeline(experiment_id: str) -> dict[str, Any] | None:
    cat = query_df("SELECT primary_kpi FROM experiment_catalog WHERE experiment_id = :e", {"e": experiment_id})
    if cat.empty:
        return None
    key = cat.primary_kpi.iloc[0] if cat.primary_kpi.iloc[0] in KPI_INDEX else "d7_retention"
    _, label, kind, col, unit, _hib = KPI_INDEX[key]
    df = _load(experiment_id)
    df["assignment_date"] = pd.to_datetime(df["assignment_date"])
    df["y"] = df[col].astype(float)
    df["y2"] = df["y"] ** 2

    days = pd.date_range(df.assignment_date.min(), df.assignment_date.max())
    agg = (df.groupby(["assignment_date", "variant"]).agg(n=("y", "size"), s=("y", "sum"), s2=("y2", "sum"))
             .unstack("variant").reindex(days).fillna(0))
    cum = agg.cumsum()
    nc, nt = cum[("n", "control")].to_numpy(), cum[("n", "test")].to_numpy()
    sc, st = cum[("s", "control")].to_numpy(), cum[("s", "test")].to_numpy()
    qc, qt = cum[("s2", "control")].to_numpy(), cum[("s2", "test")].to_numpy()
    with np.errstate(divide="ignore", invalid="ignore"):
        mc, mt = sc / nc, st / nt
        vc = np.maximum((qc - sc ** 2 / nc) / (nc - 1), 0)
        vt = np.maximum((qt - st ** 2 / nt) / (nt - 1), 0)
        se = np.sqrt(vc / nc + vt / nt)
        diff = mt - mc
        z = diff / se
    pval = 2 * stats.norm.sf(np.abs(z))
    srm = stats.chi2.sf((nc - nt) ** 2 / np.maximum(nc + nt, 1), 1)
    valid = (nc >= 100) & (nt >= 100) & np.isfinite(se) & (se > 0)

    total = float(nc[-1] + nt[-1])
    points = []
    for i, d in enumerate(days):
        pt: dict[str, Any] = {"date": d.date().isoformat(), "n_control": int(nc[i]), "n_test": int(nt[i]),
                              "enrolled_pct": float((nc[i] + nt[i]) / total),
                              "srm_p": float(srm[i]) if nc[i] + nt[i] else None}
        if valid[i]:
            pt.update({"control": float(mc[i]), "test": float(mt[i]), "diff": float(diff[i]),
                       "ci_low": float(diff[i] - 1.96 * se[i]), "ci_high": float(diff[i] + 1.96 * se[i]),
                       "p_value": float(pval[i]), "significant": bool(pval[i] < ALPHA)})
        points.append(pt)

    checked = [p for p in points if p.get("significant") is not None]
    flips = sum(1 for a, b in zip(checked, checked[1:]) if a["significant"] != b["significant"])
    first = next((p for p in checked if p["significant"]), None)
    final_sig = bool(checked and checked[-1]["significant"])
    if flips:
        text = (f"The result flipped between significant and not significant {flips} time(s) while data accumulated. "
                f"Decide only at the planned sample size.")
    elif final_sig:
        text = "Significant from the first checkable day and stayed that way, so early looks agreed with the final result."
    else:
        text = "Never significant at any look: the interval keeps containing 0, so the test cannot separate the arms."
    lift = _lift_by_day(experiment_id)
    return {
        "experiment_id": experiment_id, "kpi": label, "unit": unit, "kind": kind, "points": points,
        "daily_enrolment": [{"date": d.date().isoformat(), "control": int(agg[("n", "control")].iloc[i]),
                             "test": int(agg[("n", "test")].iloc[i])} for i, d in enumerate(days)],
        "peeking": {"significance_flips": flips,
                    "first_significant_date": first["date"] if first else None,
                    "enrolled_pct_at_first_significant": first["enrolled_pct"] if first else None,
                    "final_significant": final_sig, "text": text},
        "lift_by_day": lift, "fade": _fade(lift), "min_n_for_ci": 100,
    }
