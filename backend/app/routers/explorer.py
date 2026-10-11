"""Cohort & Retention Explorer endpoints.

All accept the population filters (country, platform, source, game_mode, segment). The date window is
controlled by `window` (install cohorts from the last N days; 0 = all history) instead of date_from/date_to.
"""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query

from ..db import jsonable
from ..filters import Filters, filters_dep
from ..services import explorer as ex

router = APIRouter(prefix="/api/explorer")

Dim = Literal["install_week", "country", "platform", "source", "first_game_mode", "device_tier", "segment", "tutorial"]
CompareDim = Literal["country", "platform", "source", "first_game_mode", "device_tier", "segment", "tutorial", "all"]


@router.get("/cohorts")
def cohorts(dim: Dim = "install_week", window: int = Query(0, ge=0, le=120), f: Filters = Depends(filters_dep)):
    return jsonable(ex.cohort_matrix(ex.with_window(f, window), dim))


@router.get("/curves")
def curves(dim: Dim = "country", window: int = Query(0, ge=0, le=120), f: Filters = Depends(filters_dep)):
    return jsonable(ex.curves(ex.with_window(f, window), dim))


@router.get("/exit-timing")
def exit_timing(dim: Dim = "country", window: int = Query(0, ge=0, le=120), f: Filters = Depends(filters_dep)):
    return jsonable(ex.exit_timing(ex.with_window(f, window), dim))


@router.get("/compare")
def compare(
    dim: CompareDim = "country",
    metric: Literal["d1", "d7", "d30"] = "d7",
    window: int = Query(28, ge=7, le=42, description="Length (days) of each install-cohort window"),
    f: Filters = Depends(filters_dep),
):
    return jsonable(ex.compare(f, dim, metric, window))
