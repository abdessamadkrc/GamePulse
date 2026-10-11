"""Dashboard filters -> reusable SQL fragments.

Every analytic endpoint builds two CTEs from the same Filters object:

  scope : the filtered set of players (country / platform / source / segment / game mode)
  act   : those players' daily activity inside [date_from, date_to]

Cohort metrics (retention, early engagement) use `scope` + install_date in range.
Activity metrics (DAU, revenue, sessions) use `act`. Keeping both definitions in one
place is what makes numbers on different pages reconcile.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date, timedelta
from functools import lru_cache
from typing import Any

from fastapi import Query

from .db import query_df

DIMENSIONS = {
    "country": "b.country",
    "platform": "b.platform",
    "source": "b.acquisition_source",
    "device": "b.device",
    "device_tier": "b.device_tier",
    "segment": "b.segment",
    "first_game_mode": "b.first_game_mode",
    "install_week": "date_trunc('week', b.install_date)::date",
    "install_date": "b.install_date",
    "tutorial": "CASE WHEN b.tutorial_completed = 1 THEN 'Finished tutorial' ELSE 'Did not finish tutorial' END",
    "all": "'All players'",
}


@lru_cache(maxsize=1)
def data_bounds() -> tuple[date, date]:
    df = query_df("SELECT key, value FROM meta_info WHERE key IN ('min_date','max_date')")
    kv = dict(zip(df["key"], df["value"]))
    return date.fromisoformat(kv["min_date"]), date.fromisoformat(kv["max_date"])


@dataclass(frozen=True)
class Filters:
    date_from: date
    date_to: date
    countries: tuple[str, ...] = ()
    platforms: tuple[str, ...] = ()
    sources: tuple[str, ...] = ()
    game_mode: str | None = None
    segment: str | None = None

    # ----- helpers -------------------------------------------------------------------
    @property
    def span_days(self) -> int:
        return (self.date_to - self.date_from).days + 1

    def previous(self) -> "Filters":
        """The immediately preceding window of identical length."""
        n = self.span_days
        return replace(self, date_from=self.date_from - timedelta(days=n), date_to=self.date_from - timedelta(days=1))

    def with_dates(self, date_from: date, date_to: date) -> "Filters":
        return replace(self, date_from=date_from, date_to=date_to)

    def without_dim(self, dim: str) -> "Filters":
        """Drop the filter that matches the dimension being broken down (keeps charts meaningful)."""
        mapping = {"country": "countries", "platform": "platforms", "source": "sources", "segment": "segment"}
        field_name = mapping.get(dim)
        if not field_name:
            return self
        return replace(self, **{field_name: () if field_name != "segment" else None})

    def key(self) -> tuple:
        return (self.date_from, self.date_to, self.countries, self.platforms, self.sources,
                self.game_mode, self.segment)

    # ----- SQL -----------------------------------------------------------------------
    def params(self) -> dict[str, Any]:
        _, max_date = data_bounds()
        p: dict[str, Any] = {
            "date_from": self.date_from,
            "date_to": self.date_to,
            "max_date": max_date,
            "mau_from": self.date_to - timedelta(days=29),
        }
        if self.countries:
            p["countries"] = list(self.countries)
        if self.platforms:
            p["platforms"] = list(self.platforms)
        if self.sources:
            p["sources"] = list(self.sources)
        if self.game_mode:
            p["game_mode"] = self.game_mode
        if self.segment:
            p["segment"] = self.segment
        return p

    def scope_cte(self, name: str = "scope") -> str:
        conds = ["TRUE"]
        if self.countries:
            conds.append("b.country = ANY(:countries)")
        if self.platforms:
            conds.append("b.platform = ANY(:platforms)")
        if self.sources:
            conds.append("b.acquisition_source = ANY(:sources)")
        if self.segment:
            conds.append("b.segment = :segment")
        if self.game_mode:
            conds.append("EXISTS (SELECT 1 FROM player_daily_mode m WHERE m.player_id = b.player_id "
                         "AND m.game_mode = :game_mode)")
        return f"{name} AS (SELECT b.* FROM player_base b WHERE {' AND '.join(conds)})"

    def act_cte(self, name: str = "act", scope: str = "scope",
                date_from: str = ":date_from", date_to: str = ":date_to") -> str:
        """Daily activity of in-scope players. With a game-mode filter, `matches` counts only that mode."""
        if self.game_mode:
            return (f"{name} AS (SELECT a.player_id, a.activity_date, a.sessions, a.minutes, "
                    f"COALESCE(m.matches, 0) AS matches, a.revenue, a.purchases "
                    f"FROM player_daily_activity a JOIN {scope} s ON s.player_id = a.player_id "
                    f"LEFT JOIN player_daily_mode m ON m.player_id = a.player_id "
                    f"AND m.activity_date = a.activity_date AND m.game_mode = :game_mode "
                    f"WHERE a.activity_date BETWEEN {date_from} AND {date_to})")
        return (f"{name} AS (SELECT a.player_id, a.activity_date, a.sessions, a.minutes, a.matches, "
                f"a.revenue, a.purchases FROM player_daily_activity a JOIN {scope} s "
                f"ON s.player_id = a.player_id WHERE a.activity_date BETWEEN {date_from} AND {date_to})")


def _csv(values: list[str] | None) -> tuple[str, ...]:
    out: list[str] = []
    for v in values or []:
        out.extend(x.strip() for x in v.split(",") if x.strip())
    return tuple(out)


def filters_dep(
    date_from: date | None = Query(None, description="Start of the analysis window"),
    date_to: date | None = Query(None, description="End of the analysis window"),
    country: list[str] | None = Query(None),
    platform: list[str] | None = Query(None),
    source: list[str] | None = Query(None),
    game_mode: str | None = Query(None),
    segment: str | None = Query(None),
) -> Filters:
    """FastAPI dependency. Defaults to the last 28 days of data."""
    lo, hi = data_bounds()
    date_to = min(date_to or hi, hi)
    date_from = max(date_from or (date_to - timedelta(days=27)), lo)
    if date_from > date_to:
        date_from = date_to
    return Filters(
        date_from=date_from,
        date_to=date_to,
        countries=_csv(country),
        platforms=_csv(platform),
        sources=_csv(source),
        game_mode=game_mode or None,
        segment=segment or None,
    )


def full_history(f: Filters) -> Filters:
    """Same population filters, but the entire data window (for trend charts)."""
    lo, hi = data_bounds()
    return f.with_dates(lo, hi)
