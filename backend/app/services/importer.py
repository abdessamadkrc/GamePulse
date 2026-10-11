"""Browser-friendly data import.

Flow used by the Import page:   upload -> inspect (detect tables + map columns) -> validate -> load -> analyse

Design goals
  * Forgiving about format: auto-detects which file is which, matches column names by synonym, accepts string /
    UUID player ids (they are replaced by anonymous integers), parses dates and epoch timestamps, and can build the
    player table from sessions alone.
  * Honest about gaps: every default that is filled in is reported as a warning, and the result says which
    analyses the data can and cannot support.
  * Safe: the whole load (truncate + COPY + derived tables) runs in ONE transaction, so a failure leaves the
    existing data untouched. While it runs the API answers 503 on analysis endpoints (see main.py).

Everything that does not touch the database (detection, mapping, cleaning) is pure and unit-tested.
"""
from __future__ import annotations

import csv
import io
import re
import tempfile
import threading
import time
import uuid
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from string import Template
from typing import Any, Callable

import numpy as np
import pandas as pd

from ..cache import clear_all
from ..config import MENA_COUNTRIES
from ..db import engine, query_df
from ..filters import data_bounds
from ..segment_rules import SQL_PARAMS

# --------------------------------------------------------------------------- table specifications
COLUMNS: dict[str, list[str]] = {
    "devices": ["device", "platform", "device_tier"],
    "players": ["player_id", "country", "platform", "device", "install_date", "acquisition_source"],
    "sessions": ["session_id", "player_id", "session_start", "session_duration_minutes"],
    "matches": ["match_id", "player_id", "match_date", "game_mode", "kills", "placement", "match_duration_minutes", "result"],
    "purchases": ["purchase_id", "player_id", "purchase_date", "amount", "item_type"],
    "events": ["event_id", "player_id", "event_name", "event_date"],
    "experiment_catalog": ["experiment_id", "name", "description", "hypothesis", "primary_kpi", "control_label",
                           "test_label", "start_date", "end_date"],
    "experiments": ["experiment_id", "player_id", "variant", "assignment_date"],
}
REQUIRED: dict[str, list[str]] = {
    "players": ["player_id"],
    "sessions": ["player_id", "session_start"],
    "matches": ["player_id", "match_date"],
    "purchases": ["player_id", "purchase_date", "amount"],
    "events": ["player_id", "event_name", "event_date"],
    "experiments": ["experiment_id", "player_id", "variant"],
    "experiment_catalog": ["experiment_id"],
    "devices": ["device"],
}
TABLE_LABEL = {
    "players": "Players (one row per player)", "sessions": "Sessions (one row per play session)",
    "matches": "Matches", "purchases": "Purchases", "events": "Events",
    "experiments": "Experiment assignments", "experiment_catalog": "Experiment descriptions", "devices": "Device models",
}
LOAD_ORDER = ["devices", "players", "sessions", "matches", "purchases", "events", "experiment_catalog", "experiments"]

SYNONYMS: dict[str, list[str]] = {
    "player_id": ["player_id", "playerid", "user_id", "userid", "uid", "account_id", "accountid", "customer_id", "id", "player", "user", "device_id", "idfa", "uuid"],
    "country": ["country", "country_code", "countrycode", "country_name", "region", "market", "geo", "location"],
    "platform": ["platform", "os", "operating_system", "device_os", "os_name", "os_type"],
    "device": ["device", "device_model", "devicemodel", "model", "device_name", "handset", "phone_model"],
    "install_date": ["install_date", "installed_at", "install_time", "install_ts", "first_seen", "first_open", "registration_date",
                     "registered_at", "signup_date", "sign_up_date", "created_at", "install_dt", "installdate", "first_session"],
    "acquisition_source": ["acquisition_source", "source", "install_source", "channel", "media_source", "network", "campaign_source",
                           "utm_source", "traffic_source", "acquisition_channel", "attribution", "campaign"],
    "session_id": ["session_id", "sessionid", "session"],
    "session_start": ["session_start", "session_start_time", "start_time", "started_at", "session_time", "timestamp", "time",
                      "datetime", "date", "event_time", "login_time", "start", "ts", "session_date"],
    "session_duration_minutes": ["session_duration_minutes", "duration_minutes", "session_length_minutes", "duration_min", "minutes",
                                 "session_duration", "duration", "session_length", "playtime", "play_time", "length", "time_played",
                                 "session_duration_seconds", "duration_seconds", "duration_sec", "duration_secs", "duration_s", "session_duration_s",
                                 "duration_in_seconds", "seconds", "secs", "sec"],
    "match_id": ["match_id", "matchid", "game_id", "round_id", "match"],
    "match_date": ["match_date", "match_time", "match_start", "started_at", "timestamp", "date", "time", "datetime", "played_at", "start_time"],
    "game_mode": ["game_mode", "gamemode", "mode", "queue", "playlist", "match_type", "map", "game_type"],
    "kills": ["kills", "eliminations", "frags", "kill_count", "kos"],
    "placement": ["placement", "rank", "position", "place", "finish", "final_rank"],
    "match_duration_minutes": ["match_duration_minutes", "match_duration", "duration_minutes", "duration", "match_length", "length_minutes",
                               "duration_seconds", "duration_sec", "duration_s"],
    "result": ["result", "outcome", "win_loss", "won", "win", "victory", "match_result"],
    "purchase_id": ["purchase_id", "transaction_id", "order_id", "txn_id", "purchaseid", "receipt_id"],
    "purchase_date": ["purchase_date", "purchase_time", "transaction_time", "transaction_date", "timestamp", "date", "time", "datetime", "purchased_at", "paid_at"],
    "amount": ["amount", "revenue", "price", "value", "usd", "amount_usd", "price_usd", "gross", "net_revenue", "spend", "iap_revenue"],
    "item_type": ["item_type", "item", "product", "sku", "product_id", "category", "item_name", "product_name", "bundle"],
    "event_id": ["event_id", "eventid"],
    "event_name": ["event_name", "event", "name", "event_type", "action", "eventname", "type"],
    "event_date": ["event_date", "event_time", "timestamp", "time", "date", "datetime", "ts", "created_at"],
    "experiment_id": ["experiment_id", "experiment", "test_id", "ab_test", "exp_id", "experiment_name", "test_name"],
    "variant": ["variant", "group", "arm", "bucket", "treatment", "cohort", "experiment_group", "test_group", "variation"],
    "assignment_date": ["assignment_date", "assigned_at", "exposure_date", "enrolled_at", "date", "timestamp", "assignment_time"],
    "name": ["name", "title", "experiment_name"],
    "description": ["description", "desc", "summary"],
    "hypothesis": ["hypothesis"],
    "primary_kpi": ["primary_kpi", "primary_metric", "kpi", "metric"],
    "control_label": ["control_label", "control", "control_name"],
    "test_label": ["test_label", "test", "variant_name", "treatment_label"],
    "start_date": ["start_date", "start", "begin_date", "started_at"],
    "end_date": ["end_date", "end", "finish_date", "ended_at"],
    "device_tier": ["device_tier", "tier", "quality", "performance_tier", "device_class", "class"],
}
DIM_DEFAULT = "Unknown"
MAX_UPLOAD_BYTES = 400 * 1024 * 1024
UPLOAD_ROOT = Path(tempfile.gettempdir()) / "gamepulse_uploads"


def _db_dir() -> Path:
    here = Path(__file__).resolve()
    for p in (here.parents[3] / "db", here.parents[2] / "db"):
        if (p / "01_schema.sql").exists():
            return p
    raise FileNotFoundError("db/01_schema.sql not found")


# --------------------------------------------------------------------------- detection and mapping (pure)
def norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(name).strip().lower()).strip("_")


# If no exact synonym matches, a target may still be matched when exactly ONE unused column contains a telling word.
KEYWORDS: dict[str, list[str]] = {
    "player_id": ["user", "player", "account"], "country": ["country", "nation"], "platform": ["platform", "os"],
    "device": ["device", "model", "handset"], "install_date": ["install", "signup", "registered", "registration"],
    "acquisition_source": ["source", "channel", "network", "campaign"], "session_start": ["start", "login"],
    "session_duration_minutes": ["duration", "length", "playtime"], "match_date": ["match", "started", "played"],
    "game_mode": ["mode", "queue", "playlist"], "kills": ["kill", "elimin"], "placement": ["place", "rank", "position"],
    "match_duration_minutes": ["duration", "length"], "result": ["result", "outcome", "won"],
    "purchase_date": ["purchas", "transaction", "paid"], "amount": ["revenue", "amount", "price", "spend", "usd", "gross"],
    "item_type": ["item", "product", "sku"], "event_name": ["event"], "event_date": ["event", "time", "date"],
    "experiment_id": ["experiment", "test"], "variant": ["variant", "group", "arm", "bucket", "treatment"],
    "assignment_date": ["assign", "enrol", "expos"], "device_tier": ["tier", "quality", "class"],
}


def auto_mapping(table: str, columns: list[str]) -> dict[str, str | None]:
    """target column -> best matching source column (each source column used at most once)."""
    by_norm: dict[str, str] = {}
    for c in columns:
        by_norm.setdefault(norm(c), c)
    used: set[str] = set()
    out: dict[str, str | None] = {}
    for target in COLUMNS[table]:
        found = None
        for cand in SYNONYMS.get(target, [target]):
            src = by_norm.get(cand)
            if src and src not in used:
                found = src
                break
        if found:
            used.add(found)
        out[target] = found
    for target in COLUMNS[table]:  # second pass: keyword fallback for what is still unmatched
        if out[target]:
            continue
        kws = KEYWORDS.get(target, [])
        hits = [src for n, src in by_norm.items() if src not in used and any(k in n for k in kws)]
        if len(hits) == 1:
            out[target] = hits[0]
            used.add(hits[0])
    return out


_FILENAME_HINTS = [
    ("catalog", "experiment_catalog"), ("experiment", "experiments"), ("assignment", "experiments"), ("session", "sessions"),
    ("match", "matches"), ("purchase", "purchases"), ("transaction", "purchases"), ("iap", "purchases"), ("revenue", "purchases"),
    ("event", "events"), ("device", "devices"), ("player", "players"), ("user", "players"), ("install", "players"), ("account", "players"),
]
_SIGNATURE = {  # targets that strongly identify a table when the filename says nothing
    "sessions": ["session_start", "session_duration_minutes"], "matches": ["game_mode", "kills", "placement"],
    "purchases": ["amount", "purchase_date"], "events": ["event_name"], "experiments": ["variant"],
    "experiment_catalog": ["primary_kpi", "control_label"], "devices": ["device_tier"],
    "players": ["install_date", "country", "acquisition_source"],
}


_WEAK_TARGETS = {"country", "platform", "acquisition_source", "device", "game_mode"}
_GENERIC = {"timestamp", "time", "date", "datetime", "ts", "name", "id", "type", "start", "value", "user", "player", "session", "match", "event"}


def guess_table(filename: str, columns: list[str]) -> str | None:
    """Filename hints win; otherwise score each table by how distinctive its matched columns are
    (exact name 3, synonym 1, a generic column like 'timestamp' only 0.5)."""
    stem = norm(Path(filename).stem)
    for key, table in _FILENAME_HINTS:
        if key in stem:
            return table
    best, best_score = None, 0.0
    for table, sig in _SIGNATURE.items():
        mapping = auto_mapping(table, columns)
        score = 0.0
        for target in sig:
            src = mapping.get(target)
            if not src:
                continue
            n = norm(src)
            w = 3 if n == target else (0.5 if n in _GENERIC else 1)
            score += min(w, 0.5) if target in _WEAK_TARGETS else w
        if score > best_score:
            best, best_score = table, score
    return best


def detect_separator(sample: str) -> str:
    head = sample.splitlines()[0] if sample else ""
    counts = {sep: head.count(sep) for sep in (",", ";", "\t", "|")}
    sep = max(counts, key=counts.get)
    return sep if counts[sep] > 0 else ","


# --------------------------------------------------------------------------- cleaning helpers (pure)
def clean_id(s: pd.Series) -> pd.Series:
    out = s.astype("string").str.strip()
    out = out.str.replace(r"\.0+$", "", regex=True)
    return out.where(out.notna() & (out != "") & (out.str.lower() != "nan"))


def to_datetime(s: pd.Series) -> pd.Series:
    """Parse ISO strings, mixed formats, or epoch seconds/milliseconds into naive UTC timestamps."""
    st = s.astype("string")
    num = pd.to_numeric(st, errors="coerce")
    if len(st) and num.notna().mean() > 0.9:
        med = float(num.dropna().median())
        unit = "ms" if med > 1e11 else "s"
        return pd.to_datetime(num, unit=unit, errors="coerce")
    out = pd.to_datetime(st, errors="coerce", utc=True)
    if len(st) and out.isna().mean() > 0.05:
        out = pd.to_datetime(st, errors="coerce", utc=True, format="mixed")
    return out.dt.tz_convert(None)


def to_number(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s.astype("string").str.replace(",", ".", regex=False).str.replace(r"[^0-9eE+.\-]", "", regex=True), errors="coerce")


def norm_platform(s: pd.Series) -> pd.Series:
    t = s.astype("string").str.strip()
    low = t.str.lower()
    t = t.mask(low.isin(["android", "google", "play"]), "Android").mask(low.isin(["ios", "iphone", "ipad", "apple", "iphone os"]), "iOS")
    return t.fillna(DIM_DEFAULT).replace("", DIM_DEFAULT)


def norm_tier(s: pd.Series) -> pd.Series:
    low = s.astype("string").str.strip().str.lower().fillna("")
    out = pd.Series("mid", index=s.index, dtype="object")
    out[low.str.contains("low|budget|entry|basic")] = "low"
    out[low.str.contains("high|premium|flagship|top")] = "high"
    out[low.str.contains(r"^mid|medium|average")] = "mid"
    return out


def norm_variant(s: pd.Series) -> pd.Series:
    low = s.astype("string").str.strip().str.lower()
    ctrl = low.isin(["control", "c", "a", "0", "baseline", "holdout", "false", "old", "default"])
    test = low.isin(["test", "t", "b", "1", "treatment", "variant", "true", "new", "variation", "b_group", "variant_b"])
    return pd.Series(np.where(ctrl, "control", np.where(test, "test", None)), index=s.index, dtype="object")


# --------------------------------------------------------------------------- standardise + build (pure)
def standardise(df: pd.DataFrame, mapping: dict[str, str | None]) -> pd.DataFrame:
    """Rename mapped source columns to their target names; unmapped targets are simply absent."""
    cols = {src: tgt for tgt, src in mapping.items() if src and src in df.columns}
    return df[list(cols)].rename(columns=cols)


@dataclass
class BuildResult:
    tables: dict[str, pd.DataFrame] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)


def build_tables(raw: dict[str, pd.DataFrame], options: dict[str, Any] | None = None) -> BuildResult:
    """raw[table] has TARGET column names (strings). Returns cleaned tables ready for COPY."""
    opt = options or {}
    res = BuildResult()
    err, warn = res.errors, res.warnings
    seconds = bool(opt.get("durations_in_seconds"))
    looks_like_seconds = False

    if "sessions" not in raw or raw["sessions"].empty:
        err.append("A sessions file is required: one row per play session with a player id and a start time.")
        return res
    for table, df in raw.items():
        for req in REQUIRED.get(table, []):
            if req not in df.columns:
                err.append(f"{TABLE_LABEL.get(table, table)}: the column “{req}” is required but was not matched to any column.")
    if err:
        return res

    # ---- sessions
    s = raw["sessions"].copy()
    s["pkey"] = clean_id(s["player_id"])
    s["session_start"] = to_datetime(s["session_start"])
    n0 = len(s)
    bad = s["pkey"].isna() | s["session_start"].isna()
    if bad.mean() > 0.2:
        err.append(f"{bad.sum():,} of {n0:,} session rows have no readable player id or start time. Check the column mapping for the sessions file.")
        return res
    if bad.any():
        warn.append(f"Dropped {bad.sum():,} session rows with a missing player id or unreadable date.")
    s = s[~bad]
    if "session_duration_minutes" in s.columns:
        d = to_number(s["session_duration_minutes"])
        if seconds:
            d = d / 60.0
        elif d.dropna().median() > 300:
            looks_like_seconds = True
            warn.append("Session durations look like seconds (median above 300). If so, tick “durations are in seconds” and re-check.")
        fill = float(d[d > 0].median()) if (d > 0).any() else 10.0
        d = d.where(d > 0).fillna(fill).clip(0.1, 1440)
    else:
        d = pd.Series(10.0, index=s.index)
        warn.append("No session-length column was found, so every session is treated as 10 minutes. Session-length metrics will not be meaningful.")
    s["dur"] = d.round(1)
    first_session = s.groupby("pkey")["session_start"].min()

    # ---- players (authoritative list of player ids)
    if "players" in raw and not raw["players"].empty:
        p = raw["players"].copy()
        p["pkey"] = clean_id(p["player_id"])
        p = p[p["pkey"].notna()]
        dups = int(p.duplicated("pkey").sum())
        if dups:
            warn.append(f"{dups:,} duplicate player ids in the players file; the first row of each was kept.")
            p = p.drop_duplicates("pkey")
        known = set(p["pkey"])
        orphan = ~s["pkey"].isin(known)
        if orphan.mean() > 0.5:
            err.append("More than half of the sessions belong to player ids that are not in the players file. The id columns probably do not match between files.")
            return res
        if orphan.any():
            warn.append(f"Dropped {orphan.sum():,} sessions whose player id is not in the players file.")
            s = s[~orphan]
    else:
        p = pd.DataFrame({"pkey": first_session.index.astype(str)})
        warn.append("No players file: players were built from the sessions file and install date = first session. Country, platform, device and source are 'Unknown'.")

    pid = pd.Series(np.arange(1, len(p) + 1), index=p["pkey"].values)
    p = p.reset_index(drop=True)
    p["player_id"] = pid.loc[p["pkey"]].values
    fs = first_session.reindex(p["pkey"]).values
    p["_first"] = pd.to_datetime(fs)
    if "install_date" in p.columns:
        inst = to_datetime(p["install_date"])
        if inst.isna().mean() > 0.3:
            warn.append("Most install dates could not be read, so install date = first session date was used instead.")
            inst = p["_first"]
        else:
            inst = inst.fillna(p["_first"])
    else:
        inst = p["_first"]
        if "players" in raw:
            warn.append("No install-date column was matched: install date = date of each player's first session (retention is measured from it).")
    inst = inst.fillna(p["_first"])
    adj = int((inst.dt.normalize() > p["_first"].dt.normalize()).sum())
    if adj:
        warn.append(f"{adj:,} players had sessions before their install date; their install date was moved back to the first session.")
    inst = pd.concat([inst, p["_first"]], axis=1).min(axis=1)
    p["install_date"] = inst.dt.date
    for tgt in ("country", "device", "acquisition_source"):
        p[tgt] = (p[tgt].astype("string").str.strip().replace("", pd.NA).fillna(DIM_DEFAULT) if tgt in p.columns else DIM_DEFAULT)
    p["platform"] = norm_platform(p["platform"]) if "platform" in p.columns else DIM_DEFAULT
    for tgt, label in (("country", "country"), ("platform", "platform"), ("acquisition_source", "acquisition source")):
        if (p[tgt] == DIM_DEFAULT).all():
            warn.append(f"No {label} information was found, so breakdowns by {label} will show a single 'Unknown' group.")
    if len(p) < 50:
        warn.append(f"Only {len(p):,} players: statistics will be very noisy.")
    players = p[COLUMNS["players"]].copy()
    key_to_id = pid

    # ---- devices
    dev_rows = players[["device", "platform"]].drop_duplicates("device")
    if "devices" in raw and "device" in raw["devices"].columns:
        dv = raw["devices"].copy()
        dv["device"] = dv["device"].astype("string").str.strip()
        dv = dv.drop_duplicates("device")
        dv["device_tier"] = norm_tier(dv["device_tier"]) if "device_tier" in dv.columns else "mid"
        dv["platform"] = norm_platform(dv["platform"]) if "platform" in dv.columns else DIM_DEFAULT
        devices = dv[["device", "platform", "device_tier"]]
        missing = dev_rows[~dev_rows["device"].isin(devices["device"])].assign(device_tier="mid")
        devices = pd.concat([devices, missing[["device", "platform", "device_tier"]]], ignore_index=True)
    else:
        devices = dev_rows.assign(device_tier="mid")[["device", "platform", "device_tier"]]
        if len(dev_rows) > 1:
            warn.append("No device-quality information: every device is treated as 'mid' tier, so device-quality analysis will be flat.")
    devices["platform"] = devices["platform"].fillna(DIM_DEFAULT)

    # ---- final sessions
    s = s.reset_index(drop=True)
    sessions = pd.DataFrame({
        "session_id": np.arange(1, len(s) + 1),
        "player_id": key_to_id.loc[s["pkey"]].values,
        "session_start": s["session_start"].values,
        "session_duration_minutes": s["dur"].values,
    })

    def link(df: pd.DataFrame, label: str) -> pd.DataFrame:
        k = clean_id(df["player_id"])
        ok = k.isin(key_to_id.index)
        if (~ok).any():
            warn.append(f"Dropped {int((~ok).sum()):,} {label} rows whose player id is not in the players/sessions data.")
        out = df[ok].copy()
        out["player_id"] = key_to_id.loc[k[ok]].values
        return out

    tables: dict[str, pd.DataFrame] = {"devices": devices, "players": players, "sessions": sessions}

    # ---- matches
    if "matches" in raw and not raw["matches"].empty:
        m = link(raw["matches"], "match")
        m["match_date"] = to_datetime(m["match_date"])
        m = m[m["match_date"].notna()].drop(columns=["match_id"], errors="ignore").reset_index(drop=True)
        m["game_mode"] = m["game_mode"].astype("string").str.strip().fillna(DIM_DEFAULT) if "game_mode" in m.columns else DIM_DEFAULT
        m["kills"] = to_number(m["kills"]).fillna(0).clip(0, 500).astype(int) if "kills" in m.columns else 0
        m["placement"] = to_number(m["placement"]).fillna(0).clip(0, 10000).astype(int) if "placement" in m.columns else 0
        md = to_number(m["match_duration_minutes"]) if "match_duration_minutes" in m.columns else pd.Series(10.0, index=m.index)
        if seconds:
            md = md / 60.0
        m["match_duration_minutes"] = md.where(md > 0).fillna(10.0).clip(0.1, 600).round(1)
        if "result" in m.columns:
            low = m["result"].astype("string").str.strip().str.lower()
            m["result"] = np.where(low.isin(["win", "won", "victory", "1", "true", "w", "winner"]), "win", "loss")
        else:
            m["result"] = np.where(m["placement"] == 1, "win", "loss")
        m.insert(0, "match_id", np.arange(1, len(m) + 1))
        tables["matches"] = m[COLUMNS["matches"]]
    # ---- purchases
    if "purchases" in raw and not raw["purchases"].empty:
        pu = link(raw["purchases"], "purchase")
        pu["purchase_date"] = to_datetime(pu["purchase_date"])
        pu["amount"] = to_number(pu["amount"])
        pu = pu[pu["purchase_date"].notna() & (pu["amount"] > 0)].drop(columns=["purchase_id"], errors="ignore").reset_index(drop=True)
        pu["item_type"] = pu["item_type"].astype("string").str.strip().fillna("unknown") if "item_type" in pu.columns else "unknown"
        pu["amount"] = pu["amount"].round(2).clip(upper=1e6)
        pu.insert(0, "purchase_id", np.arange(1, len(pu) + 1))
        tables["purchases"] = pu[COLUMNS["purchases"]]
        if "matches" not in tables:
            pass
    # ---- events
    if "events" in raw and not raw["events"].empty:
        ev = link(raw["events"], "event")
        ev["event_date"] = to_datetime(ev["event_date"])
        ev = ev[ev["event_date"].notna()].drop(columns=["event_id"], errors="ignore").reset_index(drop=True)
        ev["event_name"] = ev["event_name"].astype("string").str.strip().str.lower().str.replace(r"\s+", "_", regex=True)
        ev.insert(0, "event_id", np.arange(1, len(ev) + 1))
        tables["events"] = ev[COLUMNS["events"]]
        names = set(ev["event_name"].dropna())
        for wanted in ("tutorial_complete", "crash"):
            if wanted not in names:
                warn.append(f"The events file has no “{wanted}” event, so the related hypothesis will show 'insufficient data'.")
    # ---- experiments
    if "experiments" in raw and not raw["experiments"].empty:
        ex = link(raw["experiments"], "experiment")
        ex["variant"] = norm_variant(ex["variant"])
        badv = ex["variant"].isna()
        if badv.any():
            if badv.mean() > 0.5:
                err.append("Could not tell which experiment rows are control and which are test. Use values like control/test (or A/B, 0/1).")
                return res
            warn.append(f"Dropped {int(badv.sum()):,} experiment rows with an unrecognised variant.")
            ex = ex[~badv]
        ex["experiment_id"] = ex["experiment_id"].astype("string").str.strip()
        inst_by_id = players.set_index("player_id")["install_date"]
        if "assignment_date" in ex.columns:
            ad = to_datetime(ex["assignment_date"]).dt.date
            ex["assignment_date"] = ad.where(pd.Series(ad).notna().values, ex["player_id"].map(inst_by_id))
        else:
            ex["assignment_date"] = ex["player_id"].map(inst_by_id)
            warn.append("No assignment date for experiments: each player's install date was used.")
        ex = ex.dropna(subset=["assignment_date"]).drop_duplicates(["experiment_id", "player_id"])
        tables["experiments"] = ex[COLUMNS["experiments"]]
        if "experiment_catalog" in raw and not raw["experiment_catalog"].empty:
            cat = raw["experiment_catalog"].copy()
            cat["experiment_id"] = cat["experiment_id"].astype("string").str.strip()
        else:
            cat = pd.DataFrame({"experiment_id": sorted(ex["experiment_id"].unique())})
            warn.append("No experiment descriptions file: experiments were named after their ids (primary KPI D7 retention).")
        rng = ex.groupby("experiment_id")["assignment_date"].agg(["min", "max"])
        for c, default in (("name", None), ("description", "Imported experiment"), ("hypothesis", "Not provided"),
                           ("primary_kpi", "d7_retention"), ("control_label", "Control"), ("test_label", "Test")):
            if c not in cat.columns:
                cat[c] = cat["experiment_id"] if default is None else default
            cat[c] = cat[c].astype("string").fillna(cat["experiment_id"] if default is None else default)
        kp = {"d7": "d7_retention", "d1": "d1_retention", "d30": "d30_retention", "conversion": "conversion_14d"}
        cat["primary_kpi"] = cat["primary_kpi"].str.lower().map(lambda v: kp.get(v, v))
        cat.loc[~cat["primary_kpi"].isin(["d1_retention", "d7_retention", "d30_retention", "conversion_14d"]), "primary_kpi"] = "d7_retention"
        for c, how in (("start_date", "min"), ("end_date", "max")):
            auto = cat["experiment_id"].map(rng[how])
            cat[c] = (to_datetime(cat[c]).dt.date.where(pd.to_datetime(cat[c], errors="coerce").notna(), auto) if c in cat.columns else auto)
        tables["experiment_catalog"] = cat[COLUMNS["experiment_catalog"]].drop_duplicates("experiment_id")

    # ---- window + stats
    stamps = [sessions["session_start"].max()]
    for t, c in (("matches", "match_date"), ("purchases", "purchase_date"), ("events", "event_date")):
        if t in tables and len(tables[t]):
            stamps.append(tables[t][c].max())
    max_date = pd.Timestamp(max(stamps)).date()
    min_date = min(players["install_date"])
    span = (max_date - min_date).days
    if span < 8:
        err.append(f"The data covers only {span + 1} day(s). At least 8 days are needed to measure retention.")
    elif span < 30:
        warn.append(f"The data covers {span + 1} days: D30 retention needs 37+ days and the 'Why did it drop?' analysis needs about 21+ days.")
    elif span < 63:
        warn.append(f"The data covers {span + 1} days: the 'Why did it drop?' analysis will use shorter comparison periods.")
    res.tables = tables
    res.stats = {"rows": {k: int(len(v)) for k, v in tables.items()}, "min_date": str(min_date), "max_date": str(max_date), "span_days": span,
                 "durations_look_like_seconds": looks_like_seconds}
    return res


# --------------------------------------------------------------------------- file inspection (IO, no DB)
def new_session_dir() -> tuple[str, Path]:
    UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
    cutoff = time.time() - 3600  # prune old uploads
    for d in UPLOAD_ROOT.iterdir():
        try:
            if d.is_dir() and d.stat().st_mtime < cutoff:
                for f in d.iterdir():
                    f.unlink(missing_ok=True)
                d.rmdir()
        except OSError:
            pass
    sid = uuid.uuid4().hex[:16]
    path = UPLOAD_ROOT / sid
    path.mkdir()
    return sid, path


def session_dir(sid: str) -> Path:
    if not re.fullmatch(r"[0-9a-f]{16}", sid):
        raise ValueError("invalid upload session")
    p = UPLOAD_ROOT / sid
    if not p.is_dir():
        raise ValueError("The upload expired. Please choose your files again.")
    return p


def safe_name(name: str) -> str:
    base = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(name).name)[:120] or "file.csv"
    return base


def extract_zip(archive: Path, folder: Path) -> list[str]:
    """Unpack the CSV/TSV/TXT files of a .zip into the upload folder (flat, sanitised names, size-capped)."""
    names: list[str] = []
    with zipfile.ZipFile(archive) as z:
        members = [i for i in z.infolist() if not i.is_dir() and i.filename.lower().endswith((".csv", ".tsv", ".txt"))
                   and "__MACOSX" not in i.filename and not Path(i.filename).name.startswith(".")]
        if not members:
            raise ValueError("the zip contains no .csv, .tsv or .txt files.")
        if sum(i.file_size for i in members) > MAX_UPLOAD_BYTES:
            raise ValueError("the unpacked files are larger than the upload limit.")
        for i in members:
            name = safe_name(i.filename)
            if (folder / name).exists():
                name = f"{len(names)}_{name}"
            with z.open(i) as src, open(folder / name, "wb") as dst:
                while chunk := src.read(1 << 20):
                    dst.write(chunk)
            names.append(name)
    return names


def read_head(path: Path, nrows: int = 200) -> tuple[pd.DataFrame, str, int]:
    with open(path, "r", encoding="utf-8-sig", errors="replace") as fh:
        sample = fh.read(8192)
    sep = detect_separator(sample)
    df = pd.read_csv(path, sep=sep, dtype=str, nrows=nrows, encoding="utf-8-sig", encoding_errors="replace", on_bad_lines="skip")
    with open(path, "rb") as fh:
        total = sum(chunk.count(b"\n") for chunk in iter(lambda: fh.read(1 << 20), b""))
    return df, sep, max(total - 1, 0)


def inspect_file(path: Path) -> dict[str, Any]:
    df, sep, rows = read_head(path)
    cols = [str(c) for c in df.columns]
    table = guess_table(path.name, cols)
    return {
        "filename": path.name, "separator": sep, "rows": rows, "columns": cols,
        "table": table,
        "mapping": auto_mapping(table, cols) if table else {},
        "mappings": {t: auto_mapping(t, cols) for t in COLUMNS},
        "preview": [[str(v)[:40] if pd.notna(v) else "" for v in row] for row in df.head(5).itertuples(index=False)],
    }


def load_raw(sid: str, specs: list[dict[str, Any]]) -> dict[str, pd.DataFrame]:
    """Read the uploaded files fully, apply each file's column mapping, and concatenate files of the same table."""
    d = session_dir(sid)
    parts: dict[str, list[pd.DataFrame]] = {}
    for sp in specs:
        table = sp.get("table")
        if not table or table == "ignore":
            continue
        if table not in COLUMNS:
            raise ValueError(f"Unknown table type “{table}”.")
        path = d / safe_name(sp["filename"])
        if not path.exists():
            raise ValueError(f"File {sp['filename']} is missing from the upload.")
        with open(path, "r", encoding="utf-8-sig", errors="replace") as fh:
            sep = detect_separator(fh.read(8192))
        df = pd.read_csv(path, sep=sep, dtype=str, encoding="utf-8-sig", encoding_errors="replace", on_bad_lines="skip")
        df.columns = [str(c) for c in df.columns]
        parts.setdefault(table, []).append(standardise(df, sp.get("mapping") or {}))
    return {t: pd.concat(v, ignore_index=True) for t, v in parts.items()}


def validate_specs(sid: str, specs: list[dict[str, Any]], options: dict[str, Any]) -> BuildResult:
    tables = [sp.get("table") for sp in specs if sp.get("table") and sp.get("table") != "ignore"]
    res_pre = BuildResult()
    if not tables:
        res_pre.errors.append("No file is assigned to a table yet. Choose what each file contains.")
        return res_pre
    raw = load_raw(sid, specs)
    return build_tables(raw, options)


# --------------------------------------------------------------------------- loading (DB)
def _copy(cur, table: str, df: pd.DataFrame, chunk: int = 250_000) -> None:
    cols = ", ".join(df.columns)
    for i in range(0, len(df), chunk):
        buf = io.StringIO()
        df.iloc[i:i + chunk].to_csv(buf, index=False, header=False)
        buf.seek(0)
        cur.copy_expert(f"COPY {table} ({cols}) FROM STDIN WITH (FORMAT csv)", buf)


def load_tables(tables: dict[str, pd.DataFrame], meta: dict[str, str], on_step: Callable[[str, float], None] | None = None) -> None:
    """Replace ALL data in ONE transaction: if anything fails nothing changes."""
    step = on_step or (lambda *_: None)
    schema = (_db_dir() / "01_schema.sql").read_text()
    derived = Template((_db_dir() / "02_derived.sql").read_text()).substitute(SQL_PARAMS)
    with engine.begin() as conn:
        conn.exec_driver_sql(schema)
        conn.exec_driver_sql("ALTER TABLE players DROP CONSTRAINT IF EXISTS players_platform_check")
        conn.exec_driver_sql("ALTER TABLE devices DROP CONSTRAINT IF EXISTS devices_platform_check")
        conn.exec_driver_sql("TRUNCATE experiments, experiment_catalog, events, purchases, matches, sessions, players, devices, meta_info")
        cur = conn.connection.cursor()
        n = len(LOAD_ORDER)
        for i, name in enumerate(LOAD_ORDER):
            if name in tables and len(tables[name]):
                step(f"Saving {name} ({len(tables[name]):,} rows)", 0.30 + 0.35 * i / n)
                _copy(cur, name, tables[name])
        cur.executemany("INSERT INTO meta_info (key, value) VALUES (%s, %s)", list(meta.items()))
        step("Building analytics tables", 0.70)
        conn.exec_driver_sql(derived)
    clear_all()
    data_bounds.cache_clear()


# --------------------------------------------------------------------------- dataset info + analysis summary
def dataset_info() -> dict[str, Any]:
    c = query_df("""SELECT (SELECT COUNT(*) FROM players) players, (SELECT COUNT(*) FROM sessions) sessions,
        (SELECT COUNT(*) FROM matches) matches, (SELECT COUNT(*) FROM purchases) purchases,
        (SELECT COUNT(*) FROM events) events, (SELECT COUNT(*) FROM experiments) experiments,
        (SELECT COUNT(DISTINCT device_tier) FROM devices) tiers,
        (SELECT COUNT(DISTINCT country) FROM players WHERE country = ANY(:mena)) mena""", {"mena": MENA_COUNTRIES}).iloc[0]
    kv = dict(query_df("SELECT key, value FROM meta_info").values.tolist())
    lo, hi = data_bounds()
    span = (hi - lo).days
    max_window = max(0, min(42, (span - 7) // 2))
    label = kv.get("data_label", "")
    return {
        "counts": {k: int(c[k]) for k in ("players", "sessions", "matches", "purchases", "events", "experiments")},
        "date_min": lo.isoformat(), "date_max": hi.isoformat(), "span_days": span,
        "data_label": label, "is_demo": "SYNTHETIC" in label.upper(),
        "capabilities": {
            "investigation": max_window >= 7, "max_window": max_window, "suggested_window": min(28, max_window) if max_window >= 7 else None,
            "d30": span >= 37, "matches": int(c["matches"]) > 0, "purchases": int(c["purchases"]) > 0,
            "events": int(c["events"]) > 0, "experiments": int(c["experiments"]) > 0,
            "device_tiers": int(c["tiers"]) > 1, "mena": int(c["mena"]) >= 2,
        },
    }


def analysis_summary() -> dict[str, Any]:
    """Warm the expensive analyses and return the headline findings for the post-import screen."""
    from . import insights as ins  # local import: avoids a cycle at module load
    out: dict[str, Any] = {"findings": [], "notes": []}
    try:
        cards = ins.generate()
        out["findings"] = [{"severity": c["severity"], "title": c["title"], "insight": c["insight"], "link": c.get("link")}
                           for c in cards[:4]]
    except Exception as exc:  # noqa: BLE001
        out["notes"].append(f"Automatic findings could not be generated: {exc}")
    return out


# --------------------------------------------------------------------------- background jobs
@dataclass
class Job:
    id: str
    kind: str
    state: str = "queued"          # queued | running | done | error
    step: str = "Starting"
    progress: float = 0.0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)
    started: float = field(default_factory=time.time)
    finished: float | None = None

    def public(self) -> dict[str, Any]:
        return {"id": self.id, "kind": self.kind, "state": self.state, "step": self.step, "progress": round(self.progress, 3),
                "errors": self.errors, "warnings": self.warnings, "summary": self.summary,
                "seconds": round((self.finished or time.time()) - self.started, 1)}


_JOBS: dict[str, Job] = {}
_LOCK = threading.Lock()
_CURRENT: str | None = None


def busy() -> bool:
    with _LOCK:
        j = _JOBS.get(_CURRENT or "")
        return bool(j and j.state in ("queued", "running"))


def current_job() -> dict[str, Any] | None:
    with _LOCK:
        j = _JOBS.get(_CURRENT or "")
        return j.public() if j else None


def get_job(job_id: str) -> Job | None:
    return _JOBS.get(job_id)


def _start(kind: str, worker: Callable[[Job], None]) -> Job:
    global _CURRENT
    with _LOCK:
        cur = _JOBS.get(_CURRENT or "")
        if cur and cur.state in ("queued", "running"):
            raise RuntimeError("An import is already running. Please wait for it to finish.")
        job = Job(id=uuid.uuid4().hex[:12], kind=kind)
        _JOBS[job.id] = job
        _CURRENT = job.id

    def run() -> None:
        job.state = "running"
        try:
            worker(job)
            job.state = "done"
            job.progress = 1.0
            job.step = "Done"
        except Exception as exc:  # noqa: BLE001
            job.state = "error"
            job.errors.append(str(exc))
        finally:
            job.finished = time.time()

    threading.Thread(target=run, daemon=True).start()
    return job


def start_import(sid: str, specs: list[dict[str, Any]], options: dict[str, Any]) -> Job:
    def work(job: Job) -> None:
        job.step, job.progress = "Reading your files", 0.05
        raw = load_raw(sid, specs)
        job.step, job.progress = "Checking and cleaning the data", 0.15
        res = build_tables(raw, options)
        job.warnings = res.warnings
        if res.errors:
            job.errors = res.errors
            raise ValueError("The data did not pass the checks, so nothing was changed.")
        meta = {"min_date": res.stats["min_date"], "max_date": res.stats["max_date"], "data_label": "Imported dataset (your data)"}

        def on_step(msg: str, p: float) -> None:
            job.step, job.progress = msg, p

        load_tables(res.tables, meta, on_step)
        job.step, job.progress = "Running the analysis", 0.9
        info = dataset_info()
        job.summary = {"dataset": info, "rows": res.stats["rows"], **analysis_summary()}
        shutil_cleanup(sid)

    return _start("import", work)


def start_demo(players: int, seed: int = 42) -> Job:
    def work(job: Job) -> None:
        from seed.simulate import simulate  # the simulator ships in the same image

        job.step, job.progress = f"Generating {players:,} synthetic players", 0.05
        tables = simulate(players, seed)
        meta = {r.key: r.value for r in tables.pop("meta").itertuples()}

        def on_step(msg: str, p: float) -> None:
            job.step, job.progress = msg, p

        load_tables(tables, meta, on_step)
        job.step, job.progress = "Running the analysis", 0.9
        job.summary = {"dataset": dataset_info(), "rows": {k: int(len(v)) for k, v in tables.items()}, **analysis_summary()}

    return _start("demo", work)


def shutil_cleanup(sid: str) -> None:
    try:
        d = session_dir(sid)
        for f in d.iterdir():
            f.unlink(missing_ok=True)
        d.rmdir()
    except (ValueError, OSError):
        pass


# --------------------------------------------------------------------------- sample files
def sample_zip(players: int = 2000, seed: int = 11) -> bytes:
    from seed.simulate import simulate

    tables = simulate(players, seed)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name in LOAD_ORDER:
            z.writestr(f"{name}.csv", tables[name].to_csv(index=False))
        z.writestr("README.txt", "Synthetic sample files in the GamePulse import format. Only players.csv and sessions.csv are required; "
                                 "column names are matched automatically, so your own exports usually work as they are.\n")
    return buf.getvalue()
