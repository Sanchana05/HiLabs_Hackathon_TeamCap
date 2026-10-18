"""Re-evaluate C5 site decisions from an already ingested, unchanged work DB.

Use after decision-rule changes when source observations and as-of date are the
same. For any source or date change, rerun the full C5 ingestion instead.
"""
from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from pipeline.c5_address_mapper.resolve import C5Resolver


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--c5-dir", required=True, type=Path)
    parser.add_argument("--as-of", required=True, type=date.fromisoformat)
    parser.add_argument("--ppo-plan", action="append", default=[])
    args = parser.parse_args()
    previous_path = args.c5_dir / "c5_summary.json"
    work_db = args.c5_dir / "c5_work.sqlite"
    if not previous_path.is_file() or not work_db.is_file():
        raise FileNotFoundError("C5 summary and work DB are both required")
    previous = json.loads(previous_path.read_text(encoding="utf-8"))
    if previous.get("as_of") != args.as_of.isoformat():
        raise ValueError("As-of date changed; rerun full C5 ingestion")
    resolver = C5Resolver(work_db, as_of=args.as_of, ppo_plans=args.ppo_plan)
    try:
        summary = resolver.write_outputs(args.c5_dir)
    finally:
        resolver.close()
    summary["inputs"] = previous.get("inputs", [])
    summary["re_evaluated_from_existing_work_db"] = True
    previous_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
