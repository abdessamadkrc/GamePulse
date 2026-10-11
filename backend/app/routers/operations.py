"""Investigation, hypotheses, experiments, insights and MENA endpoints."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query

from ..db import jsonable
from ..filters import Filters, filters_dep
from ..services import experiment_hub as hub
from ..services import experiments as exp
from ..services import insights as ins
from ..services import investigation as inv
from ..services import mena as mena_svc

router = APIRouter(prefix="/api")


@router.get("/investigation")
def investigation(
    metric: Literal["d1", "d7", "d30"] = "d7",
    window: int = Query(28, ge=7, le=42, description="Length (days) of each install-cohort window"),
    country: str | None = None,
    platform: str | None = None,
    source: str | None = None,
):
    try:
        return jsonable(inv.investigate(metric, window, country or None, platform or None, source or None))
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/insights")
def insights():
    return jsonable({"cards": ins.generate()})


@router.get("/experiments")
def experiments():
    return jsonable({"experiments": exp.list_experiments()})


@router.get("/experiments/plan")
def experiment_plan(
    kpi: Literal["d1", "d7", "d30", "conversion_14d"] = "d7",
    baseline: float = Query(0.30, gt=0.005, lt=0.95, description="Current rate of the KPI, e.g. 0.30"),
    lift_pp: float = Query(3.0, ge=0.2, le=30, description="Smallest lift worth detecting, in percentage points"),
    power: float = Query(0.8, ge=0.6, le=0.99),
    alpha: float = Query(0.05, ge=0.001, le=0.2),
    daily: float = Query(300, gt=0, le=1_000_000, description="Eligible new players per day"),
    arms: int = Query(2, ge=2, le=5, description="Control plus variants"),
    test_share: float = Query(0.5, gt=0.05, lt=0.95, description="Share of traffic to the test arm (2 arms only)"),
):
    if baseline + lift_pp / 100 >= 0.999:
        raise HTTPException(422, "baseline + lift must stay below 100%")
    return jsonable(hub.plan(kpi, baseline, lift_pp, power, alpha, daily, arms, test_share))


@router.get("/experiments/{experiment_id}/timeline")
def experiment_timeline(experiment_id: str):
    res = hub.timeline(experiment_id)
    if res is None:
        raise HTTPException(404, "experiment not found")
    return jsonable(res)


@router.get("/experiments/{experiment_id}")
def experiment(experiment_id: str):
    res = exp.analyse(experiment_id)
    if res is None:
        raise HTTPException(404, "experiment not found")
    return jsonable(res)


@router.get("/mena")
def mena(f: Filters = Depends(filters_dep)):
    return jsonable(mena_svc.comparison(f))
