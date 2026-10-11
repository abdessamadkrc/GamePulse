"""Generate the synthetic dataset and load it into PostgreSQL.

Usage:
    python -m seed.generate            # no-op if the database is already seeded
    python -m seed.generate --force    # wipe and regenerate
    python -m seed.generate --players 80000 --seed 7

ALL DATA IS SYNTHETIC - not affiliated with Garena or Free Fire.
"""
from __future__ import annotations

import argparse
import io
import sys
import time
from pathlib import Path
from string import Template

import pandas as pd
from sqlalchemy import create_engine, text

from app.config import DATABASE_URL
from app.segment_rules import SQL_PARAMS
from seed.simulate import simulate

DB_DIR = next(p for p in [Path(__file__).resolve().parents[2] / "db", Path("/app/db")] if p.exists())
LOAD_ORDER = ["devices", "players", "sessions", "matches", "purchases", "events",
              "experiment_catalog", "experiments"]


def log(msg: str) -> None:
    print(f"[seed {time.strftime('%H:%M:%S')}] {msg}", flush=True)


def wait_for_db(engine, attempts: int = 60) -> None:
    for i in range(attempts):
        try:
            with engine.connect() as c:
                c.execute(text("SELECT 1"))
            return
        except Exception as exc:  # noqa: BLE001
            if i == attempts - 1:
                raise
            log(f"waiting for database ({exc.__class__.__name__})...")
            time.sleep(2)


def copy_df(raw, table: str, df: pd.DataFrame, chunk: int = 250_000) -> None:
    cols = ", ".join(df.columns)
    with raw.cursor() as cur:
        for i in range(0, len(df), chunk):
            buf = io.StringIO()
            df.iloc[i:i + chunk].to_csv(buf, index=False, header=False)
            buf.seek(0)
            cur.copy_expert(f"COPY {table} ({cols}) FROM STDIN WITH (FORMAT csv)", buf)
    raw.commit()


def build_derived(engine) -> None:
    log("building derived analytics tables (player_daily_activity, player_base)...")
    derived = Template((DB_DIR / "02_derived.sql").read_text()).substitute(SQL_PARAMS)
    with engine.begin() as c:
        c.exec_driver_sql(derived)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--derived-only", action="store_true",
                    help="rebuild only the derived tables (e.g. after editing segment_rules.py)")
    ap.add_argument("--players", type=int, default=52_000)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    engine = create_engine(DATABASE_URL)
    wait_for_db(engine)

    schema_sql = (DB_DIR / "01_schema.sql").read_text()
    with engine.begin() as c:
        c.exec_driver_sql(schema_sql)

    if args.derived_only:
        build_derived(engine)
        return 0

    with engine.connect() as c:
        seeded = c.execute(text("SELECT to_regclass('player_base') IS NOT NULL AND "
                                "(SELECT COUNT(*) FROM players) > 0")).scalar()
    if seeded and not args.force:
        log("database already seeded - nothing to do (use --force to regenerate)")
        return 0

    t0 = time.time()
    log(f"simulating {args.players:,} synthetic players (seed={args.seed})...")
    tables = simulate(args.players, args.seed)
    log("simulated: " + ", ".join(f"{k}={len(v):,}" for k, v in tables.items()))

    with engine.begin() as c:
        c.exec_driver_sql("TRUNCATE experiments, experiment_catalog, events, purchases, matches, "
                          "sessions, players, devices, meta_info RESTART IDENTITY CASCADE")

    raw = engine.raw_connection()
    try:
        for name in LOAD_ORDER:
            log(f"loading {name} ({len(tables[name]):,} rows)")
            copy_df(raw, name, tables[name])
        meta = tables["meta"]
        with raw.cursor() as cur:
            cur.executemany("INSERT INTO meta_info (key, value) VALUES (%s, %s)", meta.values.tolist())
        raw.commit()
    finally:
        raw.close()

    build_derived(engine)

    log(f"done in {time.time() - t0:.0f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
