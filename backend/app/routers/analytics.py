"""Dashboard analytics endpoints (all accept the shared filter query params)."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException

from ..db import jsonable, query_df, records
from ..filters import DIMENSIONS, Filters, data_bounds, filters_dep, full_history
from ..segment_rules import SEGMENT_ORDER
from ..services import metrics as m
from ..services import segmentation as seg

router = APIRouter(prefix="/api")

Dim = Literal["country", "platform", "source", "device", "device_tier", "segment", "first_game_mode", "all"]


def _range(f: Filters) -> dict:
    return {"from": f.date_from.isoformat(), "to": f.date_to.isoformat(), "days": f.span_days}


@router.get("/kpis")
def kpis(f: Filters = Depends(filters_dep)):
    prev = f.previous()
    lo, _ = data_bounds()
    has_prev = prev.date_from >= lo
    return jsonable({
        "range": _range(f),
        "previous_range": _range(prev) if has_prev else None,
        "current": m.period_metrics(f),
        "previous": m.period_metrics(prev) if has_prev else None,
    })


@router.get("/trends/daily")
def trend_daily(f: Filters = Depends(filters_dep)):
    """Full-history daily series (population filters applied, date window returned for shading)."""
    df = m.daily_trend(full_history(f))
    out = df.copy()
    out["date"] = out["date"].dt.date.astype(str)
    out["avg_session_minutes"] = out.minutes / out.sessions.where(out.sessions > 0)
    out["sessions_per_dau"] = out.sessions / out.dau.where(out.dau > 0)
    out["arpdau"] = out.revenue / out.dau.where(out.dau > 0)
    return jsonable({"range": _range(f), "rows": records(out)})


@router.get("/trends/retention")
def trend_retention(f: Filters = Depends(filters_dep)):
    df = m.retention_trend(full_history(f)).copy()
    df["date"] = df["date"].dt.date.astype(str)
    return jsonable({"range": _range(f), "rows": records(df[["date", "installs", "d1", "d7", "d30", "d1_7d", "d7_7d", "d30_7d"]])})


@router.get("/retention/cohorts")
def cohorts(f: Filters = Depends(filters_dep)):
    return jsonable(m.cohort_matrix(full_history(f)))


@router.get("/breakdown")
def breakdown(dim: Dim = "country", f: Filters = Depends(filters_dep)):
    if dim not in DIMENSIONS:
        raise HTTPException(400, f"unknown dimension {dim}")
    df = m.breakdown(f, dim)
    if dim == "segment":
        order = {s: i for i, s in enumerate(SEGMENT_ORDER)}
        df = df.sort_values("dim", key=lambda s: s.map(order))
    else:
        df = df.sort_values("new_players", ascending=False)
    return jsonable({"dim": dim, "range": _range(f), "rows": records(df)})


@router.get("/engagement/modes")
def engagement_modes(f: Filters = Depends(filters_dep)):
    return jsonable({"rows": records(m.mode_stats(f))})


@router.get("/monetization/summary")
def monetization(f: Filters = Depends(filters_dep)):
    return jsonable({
        "items": records(m.revenue_by_item(f)),
        "concentration": m.spend_concentration(f),
    })


@router.get("/acquisition/weekly")
def acquisition_weekly(f: Filters = Depends(filters_dep)):
    ff = full_history(f)
    df = query_df(f"""
        WITH {ff.scope_cte()}
        SELECT date_trunc('week', b.install_date)::date AS week, b.acquisition_source AS source, COUNT(*) AS installs
        FROM scope b GROUP BY 1, 2 ORDER BY 1
    """, ff.params())
    rows: dict[str, dict] = {}
    for r in df.itertuples():
        rows.setdefault(r.week.isoformat(), {"week": r.week.isoformat()})[r.source] = int(r.installs)
    return jsonable({"rows": list(rows.values()), "sources": sorted(df.source.unique().tolist())})


@router.get("/players/summary")
def players_summary(f: Filters = Depends(filters_dep)):
    life = m.lifecycle_snapshot(f)
    cur = m.period_metrics(f)
    return jsonable({"lifecycle": life, "period": cur})


@router.get("/churn")
def churn(f: Filters = Depends(filters_dep)):
    return jsonable({
        "snapshot": m.lifecycle_snapshot(f),
        "by_tier": records(m.churn_by_tier(f)),
        "by_country": records(m.churn_by_dim(f, "country").sort_values("churn_rate", ascending=False)),
        "by_platform": records(m.churn_by_dim(f, "platform")),
        "by_source": records(m.churn_by_dim(f, "source").sort_values("churn_rate", ascending=False)),
        "definition": "Churn = player active in the 30 days before the window ending at the end date "
                      "but with no session in the latest 30 days.",
    })


@router.get("/segments")
def segments(f: Filters = Depends(filters_dep)):
    return jsonable({
        "definitions": seg.definitions(),
        "distribution": seg.distribution(f),
        "by_country": seg.segment_by_dimension(f, DIMENSIONS["country"], "country"),
        "by_platform": seg.segment_by_dimension(f, DIMENSIONS["platform"], "platform"),
        "by_source": seg.segment_by_dimension(f, DIMENSIONS["source"], "source"),
        "as_of": data_bounds()[1].isoformat(),
    })


@router.get("/segments/kmeans")
def segments_kmeans(k: int = 5):
    if not 4 <= k <= 8:
        raise HTTPException(400, "k must be between 4 and 8")
    return jsonable(seg.kmeans(k))
