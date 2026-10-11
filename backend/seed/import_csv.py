"""Command-line twin of the browser's Import page (same pipeline: app/services/importer.py).

    python -m seed.import_csv --dir path/to/csvs --dry-run     # check only
    python -m seed.import_csv --dir path/to/csvs               # replace the data and rebuild analytics

Files are matched to tables by name or by their columns, and column names by synonym, exactly as in the browser.
Only sessions (player id + start time) are required. WARNING: importing REPLACES all existing data.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from app.services import importer as imp


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, help="folder containing CSV/TSV files")
    ap.add_argument("--dry-run", action="store_true", help="validate only, change nothing")
    ap.add_argument("--seconds", action="store_true", help="durations in the files are in seconds")
    args = ap.parse_args()

    folder = Path(args.dir)
    files = sorted(p for p in folder.iterdir() if p.suffix.lower() in (".csv", ".tsv", ".txt"))
    if not files:
        print(f"No CSV files found in {folder}")
        return 1

    sid, session = imp.new_session_dir()
    specs = []
    for p in files:
        (session / imp.safe_name(p.name)).write_bytes(p.read_bytes())
        info = imp.inspect_file(session / imp.safe_name(p.name))
        print(f"  {p.name:<28} -> {info['table'] or '??? (ignored)'}   ({info['rows']:,} rows)")
        if info["table"]:
            specs.append({"filename": info["filename"], "table": info["table"], "mapping": info["mapping"]})

    options = {"durations_in_seconds": args.seconds}
    res = imp.validate_specs(sid, specs, options)
    for w in res.warnings:
        print(f"  warning: {w}")
    if res.errors:
        for e in res.errors:
            print(f"  ERROR: {e}")
        print("\nValidation failed. Nothing was imported.")
        return 1
    print(f"Validation passed: {res.stats['rows']}  ({res.stats['min_date']} -> {res.stats['max_date']})")
    if args.dry_run:
        return 0

    job = imp.start_import(sid, specs, options)
    import time

    while imp.get_job(job.id).state in ("queued", "running"):
        time.sleep(1)
    j = imp.get_job(job.id)
    if j.state == "error":
        print("Import failed:", *j.errors, sep="\n  ")
        return 1
    print(f"Imported in {j.public()['seconds']}s. Restart the API (or just refresh the site) to see it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
