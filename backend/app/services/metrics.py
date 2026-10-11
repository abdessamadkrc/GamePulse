"""Core KPI computation.

Metric definitions (also documented in the README and the UI):

  Cohort metrics - players whose install_date is inside [date_from, date_to]
    D1/D7/D30 retention   = share of the cohort with a session exactly N days after install.
                            Only players old enough to have reached day N are counted
                            (their flag is NULL otherwise and AVG() ignores NULLs).
    Early churn           = share with NO session on days 8-14 after install.
    Sessions / matches per player (first 7 days), tutorial completion, 14-day LTV.

  Activity metrics - behaviour *inside* [date_from, date_to] by in-scope players
    DAU                   = average distinct players with >= 1 session per day.
    MAU                   = distinct players with >= 1 session in the 30 days ending date_to.
    ARPU                  = revenue / active players.     ARPPU = revenue / paying players.
    Conversion            = paying players / active players.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import numpy as np
import pandas as pd

from ..cache import cached
from ..db import query_df
from ..filters import DIMENSIONS, Filters, data_bounds, full_history
from ..segment_rules import CHURN_TIER_ENGAGED_DAYS, CHURN_TIER_HV_REVENUE

COHORT_DAY_COLUMNS = [1, 2, 3, 5, 7, 10, 14, 21, 30, 45, 60]


def _div(a, b):
    a = np.asarray(a, dtype="float64")
    b = np.asarray(b, dtype="float64")
    with np.errstate(divide="ignore", invalid="ignore"):
        out = np.where(b > 0, a / b, np.nan)
    return out


# --------------------------------------------------------------------------- cohort side
def _cohort_sql(f: Filters, dim_expr: str) -> str:
    return f"""
    WITH {f.scope_cte()}
    SELECT {dim_expr} AS dim,
           COUNT(*) AS new_players,
           COUNT(b.d1) AS d1_n, COALESCE(SUM(b.d1), 0) AS d1_ret,
           COUNT(b.d7) AS d7_n, COALESCE(SUM(b.d7), 0) AS d7_ret,
           COUNT(b.d30) AS d30_n, COALESCE(SUM(b.d30), 0) AS d30_ret,
           COUNT(b.early_churn) AS ec_n, COALESCE(SUM(b.early_churn), 0) AS ec_cnt,
           COUNT(*) FILTER (WHERE b.d7 IS NOT NULL) AS n7,
           COALESCE(SUM(b.sessions_7d) FILTER (WHERE b.d7 IS NOT NULL), 0) AS sessions_7d,
           COALESCE(SUM(b.minutes_7d) FILTER (WHERE b.d7 IS NOT NULL), 0) AS minutes_7d,
           COALESCE(SUM(b.matches_7d) FILTER (WHERE b.d7 IS NOT NULL), 0) AS matches_7d,
           COALESCE(SUM(b.tutorial_completed), 0) AS tutorial_done,
           COALESCE(SUM(b.crashed_7d) FILTER (WHERE b.d7 IS NOT NULL), 0) AS crashed_7d,
           COUNT(*) FILTER (WHERE b.days_since_install >= 13) AS n14,
           COALESCE(SUM(b.revenue_14d) FILTER (WHERE b.days_since_install >= 13), 0) AS rev14,
           COUNT(*) FILTER (WHERE b.days_since_install >= 13 AND b.revenue_14d > 0) AS payers14
    FROM scope b
    WHERE b.install_date BETWEEN :date_from AND :date_to
    GROUP BY 1
    """


def _activity_sql(f: Filters, dim_expr: str) -> str:
    return f"""
    WITH {f.scope_cte()}, {f.act_cte()}
    SELECT {dim_expr} AS dim,
           COUNT(DISTINCT a.player_id) FILTER (WHERE a.sessions > 0) AS active_players,
           COUNT(*) FILTER (WHERE a.sessions > 0) AS active_player_days,
           COALESCE(SUM(a.sessions), 0) AS sessions,
           COALESCE(SUM(a.minutes), 0) AS minutes,
           COALESCE(SUM(a.matches), 0) AS matches,
           COALESCE(SUM(a.revenue), 0) AS revenue,
           COUNT(DISTINCT a.player_id) FILTER (WHERE a.revenue > 0) AS payers,
           COALESCE(SUM(a.purchases), 0) AS purchases
    FROM act a JOIN scope b ON b.player_id = a.player_id
    GROUP BY 1
    """


def _totals_sql(f: Filters, dim_expr: str) -> str:
    return f"""
    WITH {f.scope_cte()}
    SELECT {dim_expr} AS dim, COUNT(*) AS players_total
    FROM scope b WHERE b.install_date <= :date_to GROUP BY 1
    """


def _finalise(df: pd.DataFrame, span_days: int) -> pd.DataFrame:
    d = df.copy()
    d["d1"] = _div(d.d1_ret, d.d1_n)
    d["d7"] = _div(d.d7_ret, d.d7_n)
    d["d30"] = _div(d.d30_ret, d.d30_n)
    d["early_churn_rate"] = _div(d.ec_cnt, d.ec_n)
    d["sessions_per_player_7d"] = _div(d.sessions_7d, d.n7)
    d["matches_per_player_7d"] = _div(d.matches_7d, d.n7)
    d["session_minutes_7d"] = _div(d.minutes_7d, d.sessions_7d)
    d["tutorial_rate"] = _div(d.tutorial_done, d.new_players)
    d["crash_rate_7d"] = _div(d.crashed_7d, d.n7)
    d["ltv14"] = _div(d.rev14, d.n14)
    d["payer_rate_14d"] = _div(d.payers14, d.n14)
    d["avg_dau"] = d.active_player_days / max(span_days, 1)
    d["sessions_per_player"] = _div(d.sessions, d.active_players)
    d["matches_per_player"] = _div(d.matches, d.active_players)
    d["avg_session_minutes"] = _div(d.minutes, d.sessions)
    d["minutes_per_player"] = _div(d.minutes, d.active_players)
    d["arpu"] = _div(d.revenue, d.active_players)
    d["arppu"] = _div(d.revenue, d.payers)
    d["conversion"] = _div(d.payers, d.active_players)
    return d


@cached
def breakdown(f: Filters, dim: str = "all") -> pd.DataFrame:
    """All headline metrics grouped by one dimension (country, platform, source, ...)."""
    expr = DIMENSIONS[dim]
    params = f.params()
    cohort = query_df(_cohort_sql(f, expr), params)
    activity = query_df(_activity_sql(f, expr), params)
    totals = query_df(_totals_sql(f, expr), params)
    df = totals.merge(cohort, on="dim", how="outer").merge(activity, on="dim", how="outer")
    num_cols = [c for c in df.columns if c != "dim"]
    df[num_cols] = df[num_cols].fillna(0)
    df = _finalise(df, f.span_days)
    total_new = df.new_players.sum()
    df["share_of_new"] = _div(df.new_players, total_new)
    total_rev = df.revenue.sum()
    df["share_of_revenue"] = _div(df.revenue, total_rev)
    return df


# --------------------------------------------------------------------------- KPI summary
@cached
def lifecycle_snapshot(f: Filters) -> dict[str, Any]:
    """Inactive / churned / returning players as of f.date_to (computed from raw daily activity)."""
    lo, _ = data_bounds()
    sql = f"""
    WITH {f.scope_cte()}, {f.act_cte('actall', date_from=':lo_date')},
    pl AS (
        SELECT s.player_id, s.install_date,
               MAX(a.activity_date) FILTER (WHERE a.sessions > 0) AS last_active,
               COUNT(*) FILTER (WHERE a.sessions > 0 AND a.activity_date >= :mau_from) AS cur,
               COUNT(*) FILTER (WHERE a.sessions > 0
                    AND a.activity_date BETWEEN CAST(:mau_from AS date) - 14
                                            AND CAST(:mau_from AS date) - 1) AS gap,
               COUNT(*) FILTER (WHERE a.sessions > 0
                    AND a.activity_date < CAST(:mau_from AS date) - 14) AS before
        FROM scope s LEFT JOIN actall a ON a.player_id = s.player_id
        WHERE s.install_date <= :date_to
        GROUP BY 1, 2
    )
    SELECT COUNT(*) AS total,
           COUNT(*) FILTER (WHERE last_active IS NULL OR last_active < CAST(:date_to AS date) - 13) AS inactive_14d,
           COUNT(*) FILTER (WHERE install_date <= CAST(:date_to AS date) - 29) AS churn_eligible,
           COUNT(*) FILTER (WHERE install_date <= CAST(:date_to AS date) - 29
                            AND (last_active IS NULL OR last_active < CAST(:date_to AS date) - 29)) AS churned_30d,
           COUNT(*) FILTER (WHERE cur > 0 AND gap = 0 AND before > 0) AS returning_players
    FROM pl
    """
    row = query_df(sql, {**f.params(), "lo_date": lo}).iloc[0]
    total = float(row.total)
    elig = float(row.churn_eligible)
    return {
        "total_players": int(row.total),
        "inactive_players": int(row.inactive_14d),
        "inactive_rate": float(row.inactive_14d / total) if total else None,
        "churned_players": int(row.churned_30d),
        "churn_rate": float(row.churned_30d / elig) if elig else None,
        "returning_players": int(row.returning_players),
    }


@cached
def period_metrics(f: Filters) -> dict[str, Any]:
    """Everything the KPI cards need for one window."""
    b = breakdown(f, "all").iloc[0] if len(breakdown(f, "all")) else None
    mau_sql = f"""
    WITH {f.scope_cte()}, {f.act_cte('act30', date_from=':mau_from')}
    SELECT COUNT(DISTINCT player_id) FILTER (WHERE sessions > 0) AS mau,
           COUNT(*) FILTER (WHERE sessions > 0) AS apd
    FROM act30
    """
    m = query_df(mau_sql, f.params()).iloc[0]
    mau = float(m.mau)
    dau30 = float(m.apd) / 30.0
    life = lifecycle_snapshot(f)
    if b is None:
        return {}
    g = lambda k: None if pd.isna(b[k]) else float(b[k])  # noqa: E731
    return {
        "new_players": g("new_players"),
        "total_players": g("players_total"),
        "active_players": g("active_players"),
        "dau": g("avg_dau"),
        "mau": mau,
        "dau_mau": (dau30 / mau) if mau else None,
        "d1": g("d1"), "d7": g("d7"), "d30": g("d30"),
        "sessions_per_player": g("sessions_per_player"),
        "matches_per_player": g("matches_per_player"),
        "avg_session_minutes": g("avg_session_minutes"),
        "revenue": g("revenue"),
        "arpu": g("arpu"), "arppu": g("arppu"),
        "payers": g("payers"), "conversion": g("conversion"),
        "early_churn_rate": g("early_churn_rate"),
        **{k: v for k, v in life.items()},
    }


# --------------------------------------------------------------------------- trends
@cached
def daily_trend(f: Filters) -> pd.DataFrame:
    """DAU, stickiness, revenue, new installs per calendar day over the filter's date window."""
    params = f.params()
    act = query_df(f"""
        WITH {f.scope_cte()}, {f.act_cte()}
        SELECT a.activity_date AS date,
               COUNT(*) FILTER (WHERE a.sessions > 0) AS dau,
               COALESCE(SUM(a.sessions), 0) AS sessions,
               COALESCE(SUM(a.minutes), 0) AS minutes,
               COALESCE(SUM(a.revenue), 0) AS revenue,
               COUNT(*) FILTER (WHERE a.revenue > 0) AS payers
        FROM act a GROUP BY 1 ORDER BY 1
    """, params)
    new = query_df(f"""
        WITH {f.scope_cte()}
        SELECT b.install_date AS date, COUNT(*) AS new_players
        FROM scope b WHERE b.install_date BETWEEN :date_from AND :date_to GROUP BY 1
    """, params)
    df = act.merge(new, on="date", how="outer").sort_values("date").fillna(0)
    df["date"] = pd.to_datetime(df["date"])

    # trailing-30-day MAU via a boolean player x day matrix (fast & exact)
    pairs = query_df(f"""
        WITH {f.scope_cte()}, {f.act_cte(date_from=':lo_date')}
        SELECT a.player_id, a.activity_date AS d FROM act a WHERE a.sessions > 0
    """, {**params, "lo_date": data_bounds()[0], "date_from": data_bounds()[0]})
    lo = pd.Timestamp(data_bounds()[0])
    ndays = (pd.Timestamp(f.date_to) - lo).days + 1
    mau_by_day: dict[pd.Timestamp, float] = {}
    if len(pairs):
        pid = pd.factorize(pairs.player_id)[0]
        di = (pd.to_datetime(pairs.d) - lo).dt.days.to_numpy()
        keep = di < ndays
        M = np.zeros((pid.max() + 1, ndays), dtype=np.int8)
        M[pid[keep], di[keep]] = 1
        c = np.concatenate([np.zeros((M.shape[0], 1), np.int32), np.cumsum(M, axis=1, dtype=np.int32)], axis=1)
        for i in range(29, ndays):
            mau_by_day[lo + pd.Timedelta(days=i)] = float(((c[:, i + 1] - c[:, i - 29]) > 0).sum())
    df["mau"] = df["date"].map(mau_by_day)
    df["dau_mau"] = df["dau"] / df["mau"]
    df["dau_7d"] = df["dau"].rolling(7, min_periods=1).mean()
    return df


@cached
def retention_trend(f: Filters) -> pd.DataFrame:
    """D1/D7/D30 per install day with a 7-day pooled rolling average (pooled = sum/sum, not mean of rates)."""
    df = query_df(f"""
        WITH {f.scope_cte()}
        SELECT b.install_date AS date, COUNT(*) AS installs,
               COUNT(b.d1) AS d1_n, COALESCE(SUM(b.d1),0) AS d1_ret,
               COUNT(b.d7) AS d7_n, COALESCE(SUM(b.d7),0) AS d7_ret,
               COUNT(b.d30) AS d30_n, COALESCE(SUM(b.d30),0) AS d30_ret
        FROM scope b WHERE b.install_date BETWEEN :date_from AND :date_to
        GROUP BY 1 ORDER BY 1
    """, f.params())
    df["date"] = pd.to_datetime(df["date"])
    for k in ("d1", "d7", "d30"):
        df[k] = _div(df[f"{k}_ret"], df[f"{k}_n"])
        r_ret = df[f"{k}_ret"].rolling(7, min_periods=3).sum()
        r_n = df[f"{k}_n"].rolling(7, min_periods=3).sum()
        df[f"{k}_7d"] = _div(r_ret, r_n)
    return df


@cached
def cohort_matrix(f: Filters) -> dict[str, Any]:
    """Weekly install cohorts x day-N retention (Dn = session exactly n days after install)."""
    cols = ",".join(f"({k})" for k in COHORT_DAY_COLUMNS)
    df = query_df(f"""
        WITH {f.scope_cte()}
        SELECT date_trunc('week', b.install_date)::date AS cohort, k.k AS day_n,
               COUNT(*) AS size,
               COUNT(*) FILTER (WHERE b.install_date + k.k <= :max_date) AS eligible,
               COUNT(a.player_id) AS retained
        FROM scope b
        CROSS JOIN (VALUES {cols}) AS k(k)
        LEFT JOIN player_daily_activity a
               ON a.player_id = b.player_id AND a.activity_date = b.install_date + k.k AND a.sessions > 0
        WHERE b.install_date BETWEEN :date_from AND :date_to
        GROUP BY 1, 2 ORDER BY 1, 2
    """, f.params())
    rows = []
    for cohort, g in df.groupby("cohort"):
        size = int(g["size"].iloc[0])
        cells = {}
        for r in g.itertuples():
            ok = r.eligible >= 0.6 * r.size and r.eligible > 0
            cells[int(r.day_n)] = float(r.retained / r.eligible) if ok else None
        rows.append({"cohort": cohort.isoformat(), "size": size, "cells": cells})
    return {"days": COHORT_DAY_COLUMNS, "rows": rows}


# --------------------------------------------------------------------------- churn
@cached
def churn_by_tier(f: Filters) -> pd.DataFrame:
    """Of players active in the prior 30 days, how many were gone in the latest 30 days?
    Tiers are assigned from prior-window behaviour (so churn can be attributed to who left)."""
    sql = f"""
    WITH {f.scope_cte()}, {f.act_cte('actw', date_from=':prior_from')},
    pl AS (
        SELECT a.player_id,
               COUNT(*) FILTER (WHERE a.sessions > 0 AND a.activity_date < :mau_from) AS prior_days,
               COALESCE(SUM(a.revenue) FILTER (WHERE a.activity_date < :mau_from), 0) AS prior_rev,
               COUNT(*) FILTER (WHERE a.sessions > 0 AND a.activity_date >= :mau_from) AS cur_days
        FROM actw a GROUP BY 1
    )
    SELECT CASE WHEN prior_rev >= {CHURN_TIER_HV_REVENUE} THEN 'High-Value'
                WHEN prior_days >= {CHURN_TIER_ENGAGED_DAYS} THEN 'Engaged'
                ELSE 'Casual' END AS tier,
           COUNT(*) AS active_prior,
           COUNT(*) FILTER (WHERE cur_days = 0) AS churned
    FROM pl WHERE prior_days > 0 GROUP BY 1
    """
    prior_from = f.date_to - timedelta(days=59)
    df = query_df(sql, {**f.params(), "prior_from": prior_from})
    df["churn_rate"] = _div(df.churned, df.active_prior)
    order = {"High-Value": 0, "Engaged": 1, "Casual": 2}
    return df.sort_values("tier", key=lambda s: s.map(order)).reset_index(drop=True)


@cached
def churn_by_dim(f: Filters, dim: str) -> pd.DataFrame:
    expr = DIMENSIONS[dim]
    prior_from = f.date_to - timedelta(days=59)
    df = query_df(f"""
    WITH {f.scope_cte()}, {f.act_cte('actw', date_from=':prior_from')},
    pl AS (
        SELECT a.player_id,
               COUNT(*) FILTER (WHERE a.sessions > 0 AND a.activity_date < :mau_from) AS prior_days,
               COUNT(*) FILTER (WHERE a.sessions > 0 AND a.activity_date >= :mau_from) AS cur_days
        FROM actw a GROUP BY 1
    )
    SELECT {expr} AS dim, COUNT(*) AS active_prior, COUNT(*) FILTER (WHERE pl.cur_days = 0) AS churned
    FROM pl JOIN scope b ON b.player_id = pl.player_id WHERE pl.prior_days > 0 GROUP BY 1
    """, {**f.params(), "prior_from": prior_from})
    df["churn_rate"] = _div(df.churned, df.active_prior)
    return df


# --------------------------------------------------------------------------- game modes & monetisation extras
@cached
def mode_stats(f: Filters) -> pd.DataFrame:
    return query_df(f"""
        WITH {f.scope_cte()}
        SELECT m.game_mode,
               COUNT(DISTINCT m.player_id) AS players,
               SUM(m.matches) AS matches,
               SUM(m.minutes) / NULLIF(SUM(m.matches), 0) AS avg_match_minutes,
               SUM(m.wins)::float8 / NULLIF(SUM(m.matches), 0) AS win_rate,
               SUM(m.kills)::float8 / NULLIF(SUM(m.matches), 0) AS kills_per_match
        FROM player_daily_mode m JOIN scope b ON b.player_id = m.player_id
        WHERE m.activity_date BETWEEN :date_from AND :date_to
        GROUP BY 1 ORDER BY matches DESC
    """, f.params())


@cached
def revenue_by_item(f: Filters) -> pd.DataFrame:
    return query_df(f"""
        WITH {f.scope_cte()}
        SELECT p.item_type, COUNT(*) AS purchases, SUM(p.amount)::float8 AS revenue,
               AVG(p.amount)::float8 AS avg_price, COUNT(DISTINCT p.player_id) AS buyers
        FROM purchases p JOIN scope b ON b.player_id = p.player_id
        WHERE p.purchase_date::date BETWEEN :date_from AND :date_to
        GROUP BY 1 ORDER BY revenue DESC
    """, f.params())


@cached
def spend_concentration(f: Filters) -> dict[str, Any]:
    """Pareto view of payer revenue + spend-bucket distribution."""
    df = query_df(f"""
        WITH {f.scope_cte()}, {f.act_cte()}
        SELECT a.player_id, SUM(a.revenue) AS rev FROM act a WHERE a.revenue > 0 GROUP BY 1 ORDER BY rev DESC
    """, f.params())
    if df.empty:
        return {"payers": 0, "top_shares": [], "buckets": []}
    rev = df.rev.to_numpy()
    total = rev.sum()
    shares = []
    for pct in (1, 5, 10, 20):
        k = max(1, int(np.ceil(len(rev) * pct / 100)))
        shares.append({"top_pct_of_payers": pct, "share_of_revenue": float(rev[:k].sum() / total)})
    bins = [0, 5, 20, 50, 100, np.inf]
    labels = ["<$5", "$5-20", "$20-50", "$50-100", "$100+"]
    cut = pd.cut(df.rev, bins=bins, labels=labels, right=False)
    buckets = [{"bucket": lbl, "payers": int((cut == lbl).sum()),
                "revenue": float(df.rev[cut == lbl].sum())} for lbl in labels]
    return {"payers": int(len(rev)), "top_shares": shares, "buckets": buckets}


def weekly(df: pd.DataFrame, value_cols: list[str], date_col: str = "date") -> pd.DataFrame:
    d = df.copy()
    d["week"] = d[date_col].dt.to_period("W-SUN").dt.start_time
    return d.groupby("week", as_index=False)[value_cols].sum()


def crosstab(f: Filters, rows: str, cols: str) -> pd.DataFrame:
    """Player counts (by install cohort in range) split by two dimensions."""
    return query_df(f"""
        WITH {f.scope_cte()}
        SELECT {DIMENSIONS[rows]} AS row_key, {DIMENSIONS[cols]} AS col_key, COUNT(*) AS players
        FROM scope b WHERE b.install_date BETWEEN :date_from AND :date_to GROUP BY 1, 2
    """, f.params())


def last_n_days(days: int) -> tuple[date, date]:
    _, hi = data_bounds()
    return hi - timedelta(days=days - 1), hi


__all__ = [
    "breakdown", "period_metrics", "daily_trend", "retention_trend", "cohort_matrix",
    "churn_by_tier", "churn_by_dim", "mode_stats", "revenue_by_item", "spend_concentration",
    "lifecycle_snapshot", "crosstab", "weekly", "full_history", "last_n_days",
]
