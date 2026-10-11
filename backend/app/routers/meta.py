import os

from fastapi import APIRouter

from ..cache import cached
from ..config import MENA_COUNTRIES, SYNTHETIC_NOTICE
from ..db import jsonable, query_df
from ..filters import data_bounds
from ..segment_rules import SEGMENT_ORDER
from ..services import importer as imp

router = APIRouter(prefix="/api")


@router.get("/health")
def health():
    query_df("SELECT 1")
    return {"status": "ok"}


@cached
def _options() -> dict:
    def col(sql: str) -> list[str]:
        return query_df(sql).iloc[:, 0].tolist()

    return {
        "countries": col("SELECT country FROM player_base GROUP BY 1 ORDER BY COUNT(*) DESC"),
        "platforms": col("SELECT platform FROM player_base GROUP BY 1 ORDER BY COUNT(*) DESC"),
        "sources": col("SELECT acquisition_source FROM player_base GROUP BY 1 ORDER BY COUNT(*) DESC"),
        "game_modes": col("SELECT game_mode FROM player_daily_mode GROUP BY 1 ORDER BY SUM(matches) DESC"),
        "segments": SEGMENT_ORDER,
    }


@router.get("/meta")
def meta():
    lo, hi = data_bounds()
    counts = query_df("""
        SELECT (SELECT COUNT(*) FROM players) AS players, (SELECT COUNT(*) FROM sessions) AS sessions,
               (SELECT COUNT(*) FROM matches) AS matches, (SELECT COUNT(*) FROM purchases) AS purchases,
               (SELECT COUNT(*) FROM events) AS events
    """).iloc[0].to_dict()
    kv = dict(query_df("SELECT key, value FROM meta_info").values.tolist())
    annotations = []
    if "surge_day" in kv:
        annotations.append({"date": kv["surge_day"], "label": "Scale-up + update"})
    return jsonable({
        "annotations": annotations,
        "notice": SYNTHETIC_NOTICE,
        "data_label": "SYNTHETIC PORTFOLIO DATA",
        "date_min": lo.isoformat(),
        "date_max": hi.isoformat(),
        "options": _options(),
        "mena_countries": MENA_COUNTRIES,
        "row_counts": counts,
        "dataset": imp.dataset_info(),
        "import_allowed": os.getenv("ALLOW_IMPORT", "1") == "1",
    })
