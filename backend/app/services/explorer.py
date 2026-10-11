"""Cohort & Retention Explorer.

Four questions, four functions:

  cohort_matrix : how does retention at day N differ across cohorts?        (heatmap)
  curves        : what does the retention curve look like, and where is the steepest drop?
  exit_timing   : on which day did players play for the LAST time?            (when do they leave)
  compare       : which cohort changed versus the previous period, and is it real?

Every function can group by any of EXPLORER_DIMS and respects the dashboard population
filters (country / platform / source / game mode / segment). The explorer ignores the global
date window and uses its own `window` (install cohorts from the last N days; 0 = all history)
so that D30 stays measurable.

Caveat shown in the UI: 'segment' is a snapshot at the last data day and is partly defined by
recent activity, so retention-by-segment is descriptive, not a cohort cause. Use install-time
attributes (country, platform, source, device, tutorial) to compare cohorts.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Any

import numpy as np
import pandas as pd
from statsmodels.stats.proportion import proportions_ztest

from ..cache import cached
from ..db import query_df
from ..filters import DIMENSIONS, Filters, data_bounds
from .metrics import COHORT_DAY_COLUMNS

EXPLORER_DIMS = ["install_week", "country", "platform", "source", "first_game_mode", "device_tier", "segment", "tutorial"]
ELIGIBILITY_DAYS = {"d1": 1, "d7": 7, "d30": 30}
MIN_GROUP = 100        # smallest group shown in matrices/curves
MAX_GROUPS = 12
CURVE_DAYS = 30
EXIT_LABELS = ["Break after day 0", "After day 1", "After days 2-3", "After days 4-7", "After days 8-14",
               "After days 15-29", "After day 30+", "Never took a 7-day break"]


def with_window(f: Filters, window: int) -> Filters:
    lo, hi = data_bounds()
    start = lo if window <= 0 else max(lo, hi - timedelta(days=window - 1))
    return f.with_dates(start, hi)


def _grp(dim: str) -> str:
    return f"COALESCE(({DIMENSIONS[dim]})::text, 'Unknown')"


def _order(labels: list[str], sizes: dict[str, int], dim: str) -> list[str]:
    if dim == "install_week":
        return sorted(labels)
    kept = [lb for lb in labels if sizes[lb] >= MIN_GROUP]
    return sorted(kept, key=lambda lb: -sizes[lb])[:MAX_GROUPS]


# --------------------------------------------------------------------------- heatmap
@cached
def cohort_matrix(f: Filters, dim: str) -> dict[str, Any]:
    cols = ",".join(f"({k})" for k in COHORT_DAY_COLUMNS)
    df = query_df(f"""
        WITH {f.scope_cte()}
        SELECT {_grp(dim)} AS grp, k.k AS day_n, COUNT(*) AS size,
               COUNT(*) FILTER (WHERE b.install_date + k.k <= :max_date) AS eligible,
               COUNT(a.player_id) AS retained
        FROM scope b
        CROSS JOIN (VALUES {cols}) AS k(k)
        LEFT JOIN player_daily_activity a
               ON a.player_id = b.player_id AND a.activity_date = b.install_date + k.k AND a.sessions > 0
        WHERE b.install_date BETWEEN :date_from AND :date_to
        GROUP BY 1, 2
    """, f.params())

    def cells(g: pd.DataFrame) -> dict[int, float | None]:
        out: dict[int, float | None] = {}
        for r in g.itertuples():
            ok = r.eligible > 0 and r.eligible >= 0.6 * r.size
            out[int(r.day_n)] = float(r.retained / r.eligible) if ok else None
        return out

    sizes = df.groupby("grp")["size"].first().to_dict()
    rows = [{"label": lb, "size": int(sizes[lb]), "cells": cells(df[df.grp == lb])} for lb in _order(list(sizes), sizes, dim)]
    tot = df.groupby("day_n")[["size", "eligible", "retained"]].sum().reset_index()
    overall = {"label": "All players", "size": int(tot["size"].iloc[0]) if len(tot) else 0, "cells": cells(tot)}
    return {"dim": dim, "days": COHORT_DAY_COLUMNS, "rows": rows, "overall": overall}


# --------------------------------------------------------------------------- curves
def _curve_points(g: pd.DataFrame, size: int) -> list[dict[str, float | None]]:
    pts: list[dict[str, float | None]] = [{"day": 0, "rate": 1.0}]
    for r in g.sort_values("day_n").itertuples():
        ok = r.eligible >= max(30, 0.6 * size)
        pts.append({"day": int(r.day_n), "rate": float(r.retained / r.eligible) if ok else None})
    return pts


def _drop_stats(pts: list[dict[str, float | None]]) -> dict[str, Any]:
    rate = {p["day"]: p["rate"] for p in pts}
    day1_loss = None if rate.get(1) is None else 1 - rate[1]
    best_day, best = None, 0.0
    for d in range(2, 15):  # steepest relative day-over-day loss after the day-1 cliff
        a, b = rate.get(d - 1), rate.get(d)
        if a and b is not None and (a - b) / a > best:
            best, best_day = (a - b) / a, d
    return {"day1_loss": day1_loss, "steepest_day": best_day, "steepest_loss": best if best_day else None,
            "d7": rate.get(7), "d14": rate.get(14), "d30": rate.get(30)}


@cached
def curves(f: Filters, dim: str) -> dict[str, Any]:
    df = query_df(f"""
        WITH {f.scope_cte()}
        SELECT {_grp(dim)} AS grp, k.k AS day_n, COUNT(*) AS size,
               COUNT(*) FILTER (WHERE b.install_date + k.k <= :max_date) AS eligible,
               COUNT(a.player_id) AS retained
        FROM scope b
        CROSS JOIN generate_series(1, {CURVE_DAYS}) AS k(k)
        LEFT JOIN player_daily_activity a
               ON a.player_id = b.player_id AND a.activity_date = b.install_date + k.k AND a.sessions > 0
        WHERE b.install_date BETWEEN :date_from AND :date_to
        GROUP BY 1, 2
    """, f.params())
    sizes = df.groupby("grp")["size"].first().to_dict()
    groups = []
    labels = _order(list(sizes), sizes, dim)
    if dim == "install_week":  # too many weekly lines are unreadable: keep the 8 most recent
        labels = labels[-8:]
    for lb in labels:
        pts = _curve_points(df[df.grp == lb], int(sizes[lb]))
        groups.append({"label": lb, "size": int(sizes[lb]), "points": pts, **_drop_stats(pts)})
    tot = df.groupby("day_n")[["size", "eligible", "retained"]].sum().reset_index()
    size_all = int(tot["size"].iloc[0]) if len(tot) else 0
    pts = _curve_points(tot, size_all)
    return {"dim": dim, "days": CURVE_DAYS, "groups": groups,
            "overall": {"label": "All players", "size": size_all, "points": pts, **_drop_stats(pts)},
            "total_groups": len(sizes)}


# --------------------------------------------------------------------------- exit timing
@cached
def exit_timing(f: Filters, dim: str) -> dict[str, Any]:
    """Day of each player's FIRST break of 7+ days without a session ("first lapse").

    'Last session ever' is a poor exit signal: sporadic returners push it late for almost everyone.
    The first 7-day break captures when a player first disengages, even if they drift back later.
    A break at the tail counts only if the 7 quiet days have already elapsed by the last data day."""
    df = query_df(f"""
        WITH {f.scope_cte()},
        days AS (
            SELECT a.player_id, a.activity_date - b.install_date AS d,
                   CASE WHEN LEAD(a.activity_date) OVER w IS NULL
                        THEN CAST(:max_date AS date) - a.activity_date + 1
                        ELSE LEAD(a.activity_date) OVER w - a.activity_date END AS gap
            FROM player_daily_activity a JOIN scope b ON b.player_id = a.player_id
            WHERE a.sessions > 0
              AND b.install_date BETWEEN :date_from AND :date_to
              AND b.install_date <= CAST(:max_date AS date) - 30
            WINDOW w AS (PARTITION BY a.player_id ORDER BY a.activity_date)
        ),
        lapse AS (SELECT player_id, MIN(d) FILTER (WHERE gap >= 8) AS lapse_day FROM days GROUP BY player_id)
        SELECT {_grp(dim)} AS grp,
               CASE WHEN l.lapse_day IS NULL THEN 7
                    WHEN l.lapse_day = 0 THEN 0 WHEN l.lapse_day = 1 THEN 1
                    WHEN l.lapse_day <= 3 THEN 2 WHEN l.lapse_day <= 7 THEN 3
                    WHEN l.lapse_day <= 14 THEN 4 WHEN l.lapse_day <= 29 THEN 5 ELSE 6 END AS bucket,
               COUNT(*) AS n
        FROM lapse l JOIN scope b ON b.player_id = l.player_id
        GROUP BY 1, 2
    """, f.params())

    def shares(g: pd.DataFrame) -> list[float]:
        tot = g.n.sum()
        return [float(g.loc[g.bucket == i, "n"].sum() / tot) if tot else 0.0 for i in range(len(EXIT_LABELS))]

    sizes = df.groupby("grp")["n"].sum().to_dict()
    rows = [{"label": lb, "size": int(sizes[lb]), "shares": shares(df[df.grp == lb])} for lb in _order(list(sizes), sizes, dim)]
    return {"dim": dim, "buckets": EXIT_LABELS, "rows": rows,
            "overall": {"label": "All players", "size": int(df.n.sum()), "shares": shares(df)},
            "note": "Players installed 30+ days before the last data day. Each player is placed in the bucket of the day "
                    "their first 7-day break began (the last day they played before it)."}


# --------------------------------------------------------------------------- period comparison
def contributions(agg: pd.DataFrame) -> pd.DataFrame:
    """agg needs columns n_prev, ret_prev, n_cur, ret_cur. Adds rates, weights and a contribution that
    is centred on the previous overall rate, so contributions sum EXACTLY to the overall change."""
    a = agg.copy()
    N_p, N_c = a.n_prev.sum(), a.n_cur.sum()
    R_p = a.ret_prev.sum() / N_p if N_p else 0.0
    a["w_prev"] = a.n_prev / N_p if N_p else 0.0
    a["w_cur"] = a.n_cur / N_c if N_c else 0.0
    a["rate_prev"] = np.where(a.n_prev > 0, a.ret_prev / a.n_prev.replace(0, np.nan), np.nan)
    a["rate_cur"] = np.where(a.n_cur > 0, a.ret_cur / a.n_cur.replace(0, np.nan), np.nan)
    a["contribution"] = a.w_cur * (np.nan_to_num(a.rate_cur) - R_p) - a.w_prev * (np.nan_to_num(a.rate_prev) - R_p)
    return a


def _significance(n_p: int, r_p: int, n_c: int, r_c: int) -> tuple[float | None, float | None, float | None]:
    if n_p < 30 or n_c < 30:
        return None, None, None
    p_p, p_c = r_p / n_p, r_c / n_c
    diff = p_c - p_p
    se = float(np.sqrt(p_p * (1 - p_p) / n_p + p_c * (1 - p_c) / n_c))
    try:
        pval = float(proportions_ztest([r_c, r_p], [n_c, n_p])[1])
    except Exception:  # degenerate (all 0 / all 1)
        pval = None
    return diff - 1.96 * se, diff + 1.96 * se, pval


def _period_counts(f: Filters, expr: str, metric: str, window: int) -> tuple[pd.DataFrame, dict[str, str]]:
    _, hi = data_bounds()
    cur_to = hi - timedelta(days=ELIGIBILITY_DAYS[metric])
    cur_from = cur_to - timedelta(days=window - 1)
    prev_to = cur_from - timedelta(days=1)
    prev_from = prev_to - timedelta(days=window - 1)
    df = query_df(f"""
        WITH {f.scope_cte()}
        SELECT {expr} AS grp,
               CASE WHEN b.install_date >= :cur_from THEN 'cur' ELSE 'prev' END AS period,
               COUNT(b.{metric}) AS n, COALESCE(SUM(b.{metric}), 0) AS ret
        FROM scope b
        WHERE b.install_date BETWEEN :prev_from AND :cur_to AND b.{metric} IS NOT NULL
        GROUP BY 1, 2
    """, {**f.params(), "prev_from": prev_from, "cur_from": cur_from, "cur_to": cur_to})
    piv = df.pivot_table(index="grp", columns="period", values=["n", "ret"], fill_value=0)
    piv.columns = [f"{a}_{b}" for a, b in piv.columns]
    for c in ("n_prev", "ret_prev", "n_cur", "ret_cur"):
        if c not in piv:
            piv[c] = 0
    periods = {"prev_from": prev_from.isoformat(), "prev_to": prev_to.isoformat(),
               "cur_from": cur_from.isoformat(), "cur_to": cur_to.isoformat()}
    return piv.reset_index(), periods


@cached
def compare(f: Filters, dim: str, metric: str, window: int) -> dict[str, Any]:
    agg, periods = _period_counts(f, _grp(dim) if dim != "all" else "'All players'", metric, window)
    full = contributions(agg)
    tot = {"n_prev": int(agg.n_prev.sum()), "ret_prev": int(agg.ret_prev.sum()),
           "n_cur": int(agg.n_cur.sum()), "ret_cur": int(agg.ret_cur.sum())}

    def row(r: pd.Series, label: str, contribution: float | None) -> dict[str, Any]:
        n_p, r_p, n_c, r_c = int(r.n_prev), int(r.ret_prev), int(r.n_cur), int(r.ret_cur)
        rate_p = r_p / n_p if n_p else None
        rate_c = r_c / n_c if n_c else None
        lo, hi, pv = _significance(n_p, r_p, n_c, r_c)
        return {
            "label": label, "players_prev": n_p, "players_cur": n_c,
            "share_prev": float(r.get("w_prev", 1.0)), "share_cur": float(r.get("w_cur", 1.0)),
            "rate_prev": rate_p, "rate_cur": rate_c,
            "delta_pp": None if rate_p is None or rate_c is None else (rate_c - rate_p) * 100,
            "ci_low_pp": None if lo is None else lo * 100, "ci_high_pp": None if hi is None else hi * 100,
            "p_value": pv, "significant": bool(pv is not None and pv < 0.05),
            "low_sample": bool(n_p < 30 or n_c < 30),
            "contribution_pp": None if contribution is None else contribution * 100,
        }

    rows = [row(r, str(r.grp), float(r.contribution)) for _, r in full.iterrows()]
    overall = row(pd.Series(tot), "All players", None)
    overall["contribution_pp"] = overall["delta_pp"]
    if dim == "install_week":
        rows.sort(key=lambda r: r["label"])
    else:
        rows.sort(key=lambda r: (r["contribution_pp"] is None, r["contribution_pp"]))

    by_metric = {}
    for m in ELIGIBILITY_DAYS:
        a, per = _period_counts(f, "'All players'", m, window)
        o = row(pd.Series({"n_prev": a.n_prev.sum(), "ret_prev": a.ret_prev.sum(),
                           "n_cur": a.n_cur.sum(), "ret_cur": a.ret_cur.sum()}), "All players", None)
        by_metric[m] = {**{k: o[k] for k in ("rate_prev", "rate_cur", "delta_pp", "p_value", "significant")}, "periods": per}
    return {"dim": dim, "metric": metric, "window": window, "periods": periods,
            "overall": overall, "rows": rows, "by_metric": by_metric}
