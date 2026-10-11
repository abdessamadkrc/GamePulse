"""Write a SYNTHETIC sample dataset as CSV files, in the exact format import_csv.py expects.

    python -m seed.export_csv --out sample_data --players 5000 --seed 11

Use the output as a template: replace each file with your own data (same column names).
"""
from __future__ import annotations

import argparse
from pathlib import Path

from seed.simulate import simulate

FILES = ["devices", "players", "sessions", "matches", "purchases", "events", "experiment_catalog", "experiments"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="sample_data")
    ap.add_argument("--players", type=int, default=5000)
    ap.add_argument("--seed", type=int, default=11)
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    tables = simulate(args.players, args.seed)
    for name in FILES:
        tables[name].to_csv(out / f"{name}.csv", index=False)
        print(f"wrote {out / (name + '.csv')}  ({len(tables[name]):,} rows)")


if __name__ == "__main__":
    main()
