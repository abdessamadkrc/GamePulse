from __future__ import annotations

import math
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text

from .config import DATABASE_URL

engine = create_engine(DATABASE_URL, pool_size=8, max_overflow=8, pool_pre_ping=True)


def query_df(sql: str, params: dict[str, Any] | None = None) -> pd.DataFrame:
    """Run a read-only SQL statement and return a DataFrame."""
    with engine.connect() as conn:
        return pd.read_sql(text(sql), conn, params=params or {})


def clean(value: Any) -> Any:
    """Make a value JSON-safe (NaN/inf -> None, numpy -> python, dates -> ISO)."""
    if value is None:
        return None
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        f = float(value)
        return None if (math.isnan(f) or math.isinf(f)) else f
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, pd.Timestamp) and pd.isna(value):
        return None
    if isinstance(value, datetime):  # includes pd.Timestamp
        return value.date().isoformat() if value.time() == datetime.min.time() else value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, (list, dict, tuple, np.ndarray)):
        return value
    return None if pd.isna(value) else value


def records(df: pd.DataFrame) -> list[dict[str, Any]]:
    """DataFrame -> list of JSON-safe dicts."""
    return [{k: clean(v) for k, v in row.items()} for row in df.to_dict("records")]


def jsonable(obj: Any) -> Any:
    """Recursively clean nested dict/list structures built from pandas/numpy values."""
    if isinstance(obj, dict):
        return {str(k): jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [jsonable(v) for v in obj]
    if isinstance(obj, pd.DataFrame):
        return records(obj)
    return clean(obj)
