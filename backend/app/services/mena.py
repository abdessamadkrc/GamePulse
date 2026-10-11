"""MENA market comparison.

IMPORTANT: every number comes from the SYNTHETIC dataset. Country-level differences here are
parameters of the simulator, not statements about real markets. The value of this page is the
*framework*: one consistent scorecard, indexed to the regional average, that lets an operator
see where a market over/under-indexes and which lever (acquisition, retention, monetisation)
to pull.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from typing import Any

import pandas as pd

from ..cache import cached
from ..config import MENA_COUNTRIES
from ..db import query_df
from ..filters import Filters, data_bounds
from ..segment_rules import SEGMENT_ORDER
from . import metrics as m

SCORECARD = [
    # key, label, group, higher_is_better, unit
    ("d1", "D1 retention", "Retention", True, "pct"),
    ("d7", "D7 retention", "Retention", True, "pct"),
    ("d30", "D30 retention", "Retention", True, "pct"),
    ("early_churn_rate", "Early churn (days 8-14)", "Retention", False, "pct"),
    ("sessions_per_player", "Sessions / active player", "Engagement", True, "num"),
    ("matches_per_player", "Matches / active player", "Engagement", True, "num"),
    ("avg_session_minutes", "Avg session (min)", "Engagement", True, "min"),
    ("arpu", "ARPU", "Monetization", True, "usd"),
    ("arppu", "ARPPU", "Monetization", True, "usd"),
    ("conversion", "Payer conversion", "Monetization", True, "pct"),
]


MIN_WINDOW_DAYS = 90  # D30 needs cohorts 30+ days old, and small markets need sample size


def _mena_filters(f: Filters) -> Filters:
    chosen = [c for c in (f.countries or MENA_COUNTRIES) if c in MENA_COUNTRIES]
    lo, _ = data_bounds()
    date_from = max(lo, min(f.date_from, f.date_to - timedelta(days=MIN_WINDOW_DAYS - 1)))
    return replace(f, countries=tuple(chosen or MENA_COUNTRIES), date_from=date_from)


@cached
def comparison(f: Filters) -> dict[str, Any]:
    fm = _mena_filters(f)
    present = query_df("SELECT DISTINCT country FROM player_base WHERE country = ANY(:c)", {"c": MENA_COUNTRIES})["country"].tolist()
    if len(present) < 2:
        return {"available": False, "countries": [], "rows": [],
                "reason": "This comparison needs players from at least two of: " + ", ".join(MENA_COUNTRIES) + ". Your data has "
                          + (", ".join(present) if present else "none of them") + "."}
    by_country = m.breakdown(fm, "country").set_index("dim")
    region = m.breakdown(fm, "all").iloc[0]
    countries = [c for c in MENA_COUNTRIES if c in by_country.index]

    rows = []
    for c in countries:
        r = by_country.loc[c]
        metrics = {}
        for key, label, group, hib, unit in SCORECARD:
            v = r[key]
            base = region[key]
            idx = None if pd.isna(v) or pd.isna(base) or not base else float(v / base * 100)
            metrics[key] = {"value": None if pd.isna(v) else float(v), "index": idx}
        rows.append({
            "country": c,
            "new_players": int(r.new_players),
            "active_players": int(r.active_players),
            "revenue": float(r.revenue),
            "share_of_new": float(r.share_of_new),
            "metrics": metrics,
        })

    # best / worst per metric
    leaders = []
    for key, label, group, hib, unit in SCORECARD:
        vals = [(r["country"], r["metrics"][key]["value"]) for r in rows if r["metrics"][key]["value"] is not None]
        if len(vals) < 2:
            continue
        vals.sort(key=lambda x: x[1], reverse=hib)
        leaders.append({"key": key, "label": label, "group": group, "unit": unit,
                        "best": {"country": vals[0][0], "value": vals[0][1]},
                        "worst": {"country": vals[-1][0], "value": vals[-1][1]}})

    def composition(rows_dim: str, cols_dim: str, order: list[str] | None = None) -> list[dict[str, Any]]:
        ct = m.crosstab(fm, rows_dim, cols_dim)
        out = []
        for c in countries:
            g = ct[ct.row_key == c]
            tot = g.players.sum()
            row = {"country": c}
            keys = order or sorted(ct.col_key.unique())
            for k in keys:
                row[k] = float(g.loc[g.col_key == k, "players"].sum() / tot) if tot else 0.0
            out.append(row)
        return out

    seg = query_df(f"""
        WITH {fm.scope_cte()}
        SELECT b.country, b.segment, COUNT(*) AS players FROM scope b GROUP BY 1, 2
    """, fm.params())
    seg_rows = []
    for c in countries:
        g = seg[seg.country == c]
        tot = g.players.sum()
        row = {"country": c}
        for s in SEGMENT_ORDER:
            row[s] = float(g.loc[g.segment == s, "players"].sum() / tot) if tot else 0.0
        seg_rows.append(row)

    # weekly D7 over full history (not the date window) so the trend is readable
    weekly = query_df(f"""
        WITH {fm.scope_cte()}
        SELECT date_trunc('week', b.install_date)::date AS week, b.country,
               COUNT(b.d7) AS n, COALESCE(SUM(b.d7), 0) AS ret
        FROM scope b GROUP BY 1, 2 HAVING COUNT(b.d7) >= 30 ORDER BY 1
    """, fm.params())
    weekly["d7"] = weekly.ret / weekly.n
    trend = []
    for wk, g in weekly.groupby("week"):
        row = {"week": wk.isoformat()}
        row.update({r.country: float(r.d7) for r in g.itertuples()})
        trend.append(row)

    return {
        "window": {"from": fm.date_from.isoformat(), "to": fm.date_to.isoformat(),
                   "note": f"Comparison uses at least {MIN_WINDOW_DAYS} days so D30 is measurable and small markets have enough players."},
        "countries": countries,
        "region": {
            "new_players": int(region.new_players),
            **{k: (None if pd.isna(region[k]) else float(region[k])) for k, *_ in SCORECARD},
        },
        "scorecard_spec": [{"key": k, "label": l, "group": g, "higher_is_better": h, "unit": u}
                           for k, l, g, h, u in SCORECARD],
        "rows": rows,
        "leaders": leaders,
        "sources": composition("country", "source"),
        "platforms": composition("country", "platform"),
        "segments": seg_rows,
        "d7_trend": trend,
        "disclaimer": "All country differences are properties of the synthetic data generator. "
                      "They illustrate the analytical framework; they are not real-world market statistics.",
    }
