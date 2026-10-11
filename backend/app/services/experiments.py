"""A/B test analysis with statsmodels.

For each experiment we pull one row per assigned player (variant + outcomes measured over a
FIXED post-install window so both arms are compared like-for-like) and test:

  * proportion KPIs (D1, D7, conversion)      -> two-sample z-test (statsmodels.proportions_ztest)
                                                 + Newcombe CI for the difference
  * continuous KPIs (sessions, matches, rev.) -> Welch t-test (statsmodels.ttest_ind, unequal var)
                                                 + CI for the difference in means
  * sample-ratio mismatch (SRM)               -> chi-square on arm sizes vs the intended 50/50
  * secondary KPIs                            -> Holm correction, because testing 5 metrics at
                                                 alpha=5% inflates false positives
  * minimum detectable effect                 -> NormalIndPower at 80% power

The PRIMARY KPI drives the decision; secondary KPIs are guardrails / context.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from scipy import stats
from statsmodels.stats.multitest import multipletests
from statsmodels.stats.power import NormalIndPower
from statsmodels.stats.proportion import confint_proportions_2indep, proportion_effectsize, proportions_ztest
from statsmodels.stats.weightstats import CompareMeans, DescrStatsW

from ..cache import cached
from ..db import query_df
from .power import mde_pp, sample_size_control

ALPHA = 0.05

# key, label, kind, column, unit, higher_is_better
KPIS = [
    ("d1_retention", "D1 retention", "proportion", "d1", "pct", True),
    ("d7_retention", "D7 retention", "proportion", "d7", "pct", True),
    ("sessions_per_player", "Sessions per player (first 7 days)", "mean", "sessions_7d", "num", True),
    ("matches_per_player", "Matches per player (first 7 days)", "mean", "matches_7d", "num", True),
    ("conversion_14d", "Payer conversion (14 days)", "proportion", "paid_14d", "pct", True),
    ("revenue_per_player_14d", "Revenue per player (14 days, synthetic $)", "mean", "revenue_14d", "usd", True),
]
KPI_INDEX = {k[0]: k for k in KPIS}


def list_experiments() -> list[dict[str, Any]]:
    df = query_df("""
        SELECT c.*, COUNT(e.player_id) AS assigned
        FROM experiment_catalog c LEFT JOIN experiments e USING (experiment_id)
        GROUP BY c.experiment_id ORDER BY c.start_date DESC
    """)
    return df.to_dict("records")


def _load(experiment_id: str) -> pd.DataFrame:
    return query_df("""
        SELECT e.player_id, e.variant, e.assignment_date, b.platform, b.country, b.acquisition_source AS source,
               b.d1, b.d7, b.sessions_7d, b.matches_7d, b.revenue_14d,
               (b.revenue_14d > 0)::int AS paid_14d
        FROM experiments e JOIN player_base b USING (player_id)
        WHERE e.experiment_id = :eid AND b.days_since_install >= 13
    """, {"eid": experiment_id})


def _mde_pp(p0: float, n_control: int, n_test: int) -> float | None:
    """Smallest absolute lift detectable with 80% power (two-sided alpha 5%)."""
    return mde_pp(p0, n_control, n_test, power=0.8, alpha=ALPHA)


def _test_kpi(df: pd.DataFrame, key: str) -> dict[str, Any]:
    _, label, kind, col, unit, hib = KPI_INDEX[key]
    c = df.loc[df.variant == "control", col].dropna().astype(float)
    t = df.loc[df.variant == "test", col].dropna().astype(float)
    mc, mt = float(c.mean()), float(t.mean())
    if kind == "proportion":
        counts = np.array([t.sum(), c.sum()])
        nobs = np.array([len(t), len(c)])
        _, p = proportions_ztest(counts, nobs)
        ci = confint_proportions_2indep(counts[0], nobs[0], counts[1], nobs[1], method="newcomb")
        ci_lo, ci_hi = float(ci[0]), float(ci[1])
        method = "Two-proportion z-test (statsmodels)"
        mde = _mde_pp(mc, len(c), len(t))
    else:
        tt = stats.ttest_ind(t, c, equal_var=False)
        p = float(tt.pvalue)
        cm = CompareMeans(DescrStatsW(t), DescrStatsW(c))
        lo, hi = cm.tconfint_diff(alpha=ALPHA, usevar="unequal")
        ci_lo, ci_hi = float(lo), float(hi)
        method = "Welch t-test (statsmodels)"
        sd = float(np.sqrt((c.var(ddof=1) + t.var(ddof=1)) / 2))
        es = NormalIndPower().solve_power(nobs1=len(c), alpha=ALPHA, power=0.8, ratio=len(t) / len(c))
        mde = float(es * sd) if sd else None
    diff = mt - mc
    return {
        "key": key, "label": label, "kind": kind, "unit": unit, "higher_is_better": hib,
        "n_control": int(len(c)), "n_test": int(len(t)),
        "control": mc, "test": mt,
        "abs_diff": diff,
        "abs_diff_pp": diff * 100 if kind == "proportion" else None,
        "rel_diff": diff / mc if mc else None,
        "ci_low": ci_lo, "ci_high": ci_hi,
        "p_value": float(p),
        "method": method,
        "mde": mde,   # pp for proportions, raw units for means
    }


def _p(p: float) -> str:
    return "p < 0.0001" if p < 0.0001 else f"p = {p:.4f}" if p < 0.01 else f"p = {p:.3f}"


def _recommend(primary: dict[str, Any], guardrails: list[dict[str, Any]], srm_ok: bool, exp_name: str) -> dict[str, Any]:
    pk = primary
    sig = pk["p_value"] < ALPHA
    better = pk["abs_diff"] > 0
    worse_guard = [g for g in guardrails if g["significant_adj"] and (g["abs_diff"] < 0) == g["higher_is_better"]]

    def fmt_diff(k: dict[str, Any]) -> str:
        if k["kind"] == "proportion":
            return f"{abs(k['abs_diff']) * 100:.1f} percentage points"
        return f"{abs(k['abs_diff']):.2f}"

    if not srm_ok:
        return {
            "decision": "investigate",
            "headline": "Investigate before deciding: sample-ratio mismatch",
            "text": "The arm sizes deviate from the intended split more than chance allows. Randomisation or "
                    "logging may be broken, so results cannot be trusted until the assignment pipeline is checked.",
        }
    if sig and better and not worse_guard:
        ci = (f"{pk['ci_low'] * 100:.1f} to {pk['ci_high'] * 100:.1f} pp" if pk["kind"] == "proportion"
              else f"{pk['ci_low']:.2f} to {pk['ci_high']:.2f}")
        return {
            "decision": "ship",
            "headline": "Recommend a controlled rollout",
            "text": f"Test variant increased {pk['label']} by {fmt_diff(pk)} "
                    f"({pk['rel_diff'] * 100:+.1f}% relative; 95% CI {ci}). The difference is statistically "
                    f"significant ({_p(pk['p_value'])}). Recommend a controlled rollout (e.g. 25% -> 50% -> 100%) "
                    f"while monitoring monetization (conversion, revenue per player) and crash-related metrics.",
        }
    if sig and better and worse_guard:
        names = ", ".join(g["label"] for g in worse_guard)
        return {
            "decision": "hold",
            "headline": "Primary KPI improved, but a guardrail regressed",
            "text": f"{pk['label']} improved significantly, but {names} moved the wrong way. Review the trade-off "
                    f"before rolling out.",
        }
    if sig and not better:
        return {
            "decision": "stop",
            "headline": "Do not ship: primary KPI got worse",
            "text": f"Test variant decreased {pk['label']} by {fmt_diff(pk)} ({_p(pk['p_value'])}). "
                    f"Keep the control experience and revisit the design.",
        }
    mde = pk["mde"]
    mde_txt = (f"{mde:.1f} pp" if pk["kind"] == "proportion" and mde is not None else
               f"{mde:.2f}" if mde is not None else "n/a")
    return {
        "decision": "inconclusive",
        "headline": "No decision: the result is not statistically significant",
        "text": f"Observed difference in {pk['label']} is {pk['abs_diff'] * 100:+.2f} pp ({_p(pk['p_value'])}), "
                f"which is consistent with no effect. With this sample the test could only reliably detect a lift "
                f"of about {mde_txt}. Do not roll out on this evidence; either extend the test to a larger sample "
                f"or accept that any true effect is smaller than the business case requires."
        if pk["kind"] == "proportion" else
        f"Observed difference in {pk['label']} is not statistically significant ({_p(pk['p_value'])}).",
    }


@cached
def analyse(experiment_id: str) -> dict[str, Any] | None:
    cat = query_df("SELECT * FROM experiment_catalog WHERE experiment_id = :e", {"e": experiment_id})
    if cat.empty:
        return None
    meta = cat.iloc[0].to_dict()
    df = _load(experiment_id)
    n_c, n_t = int((df.variant == "control").sum()), int((df.variant == "test").sum())
    srm_p = float(stats.chisquare([n_c, n_t]).pvalue)
    srm_ok = srm_p >= 0.001

    results = [_test_kpi(df, k[0]) for k in KPIS]
    primary_key = meta["primary_kpi"] if meta["primary_kpi"] in KPI_INDEX else "d7_retention"
    secondary = [r for r in results if r["key"] != primary_key]
    adj = multipletests([r["p_value"] for r in secondary], alpha=ALPHA, method="holm")
    for r, padj, rej in zip(secondary, adj[1], adj[0]):
        r["p_adjusted"] = float(padj)
        r["significant_adj"] = bool(rej)
    primary = next(r for r in results if r["key"] == primary_key)
    primary["p_adjusted"] = primary["p_value"]
    primary["significant_adj"] = bool(primary["p_value"] < ALPHA)
    for r in results:
        r["significant"] = bool(r["p_value"] < ALPHA)
        r["is_primary"] = r["key"] == primary_key

    rec = _recommend(primary, secondary, srm_ok, meta["name"])

    subgroups = {dim: _subgroups(df, primary_key, dim) for dim in ("platform", "country", "source")}
    by_platform = [{k: r[k] for k in ("platform", "n_control", "n_test", "control", "test", "abs_diff", "p_value",
                                      "ci_low", "ci_high")} for r in subgroups["platform"]]

    return {
        "experiment": {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in meta.items()},
        "primary_kpi": primary_key,
        "alpha": ALPHA,
        "sample": {
            "control": n_c, "test": n_t, "total": n_c + n_t,
            "srm_p_value": srm_p, "srm_ok": srm_ok,
            "note": "Players assigned randomly 50/50 at install; outcomes measured over fixed post-install "
                    "windows (7 days for sessions/matches/retention, 14 days for monetisation).",
        },
        "results": results,
        "recommendation": rec,
        "by_platform": by_platform,
        "subgroups": subgroups,
    }


# --------------------------------------------------------------------------- subgroup effects
MIN_ARM_SUBGROUP = 60


def _subgroups(df: pd.DataFrame, primary_key: str, dim: str) -> list[dict[str, Any]]:
    """Primary-KPI effect inside each level of `dim`, Holm-corrected ACROSS the levels shown.
    Descriptive only: subgroups are underpowered, and the more you slice the more false positives you see."""
    rows = []
    for level, g in df.groupby(dim):
        if (g.variant == "control").sum() < MIN_ARM_SUBGROUP or (g.variant == "test").sum() < MIN_ARM_SUBGROUP:
            continue
        r = _test_kpi(g, primary_key)
        rows.append({dim: level, **{k: r[k] for k in ("n_control", "n_test", "control", "test", "abs_diff",
                                                      "rel_diff", "p_value", "ci_low", "ci_high")}})
    if rows:
        adj = multipletests([r["p_value"] for r in rows], alpha=ALPHA, method="holm")
        for r, p_adj, rej in zip(rows, adj[1], adj[0]):
            r["p_adjusted"], r["significant_adj"] = float(p_adj), bool(rej)
    return sorted(rows, key=lambda r: -(r["n_control"] + r["n_test"]))
