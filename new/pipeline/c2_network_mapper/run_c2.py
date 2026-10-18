"""Run C1 and C2 only, producing C3/C4-ready PPO file_manifest.csv."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

from pipeline.c1_index_parser.index_parser import CenteneIndexParser
from pipeline.c2_network_mapper.verify_ppo_network import PPOVerificationEngine
from pipeline.config import DELIVERABLES_DIR, RAW_INDEX_DIR, REPO_ROOT


def run(index_paths: list[Path], output_dir: Path, evidence_path: Path | None = None) -> dict:
    paths = sorted({Path(path).resolve() for path in index_paths})
    if not paths:
        raise ValueError("No index files supplied; use --index-dir or --index")
    for path in paths:
        if not path.is_file():
            raise FileNotFoundError(f"Index file not found: {path}")
    parser = CenteneIndexParser()
    inventory = []
    first_source_by_hash = {}
    for path in paths:
        records = parser.parse_index_file(path)
        if not records:
            raise ValueError(f"Index produced no plan-file edges: {path}; {parser.warnings}")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        inventory.append({
            **parser.index_inventories[-1],
            "sha256": digest,
            "duplicate_content_of": first_source_by_hash.get(digest, ""),
            "raw_plan_file_edges": len(records),
        })
        first_source_by_hash.setdefault(digest, path.name)
    plans = parser.build_deduplicated_plan_table()
    engine = PPOVerificationEngine(evidence_path)
    decisions, all_files, review, summary = engine.verify_all_plans(plans)
    selected_files = engine.select_ppo_files(all_files)
    if selected_files.empty:
        raise ValueError("No California group PPO-linked rate file found; inspect scope and inputs")

    output_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(inventory).to_csv(output_dir / "index_inventory.csv", index=False)
    pd.DataFrame(parser.raw_records).to_csv(output_dir / "raw_plan_file_edges.csv", index=False)
    plans.to_csv(output_dir / "centene_c1_deduplicated_plans.csv", index=False)
    decisions.to_csv(output_dir / "plan_decisions.csv", index=False)
    decisions[decisions["product_status"].isin(
        ["CONFIRMED_PPO", "PROVISIONAL_PPO"]
    )].to_csv(output_dir / "centene_c2_ppo_network_plans.csv", index=False)
    selected_files.to_csv(output_dir / "file_manifest.csv", index=False)
    all_files.to_csv(output_dir / "all_file_inventory.csv", index=False)
    review.to_csv(output_dir / "review_queue.csv", index=False)
    summary.update({
        "source_index_count": len(paths),
        "distinct_index_content_count": len(first_source_by_hash),
        "raw_plan_file_edges": len(parser.raw_records),
        "deduplicated_plan_file_edges": len(plans),
        "selected_ppo_rate_files": len(selected_files),
        "index_sha256": {row["source"]: row["sha256"] for row in inventory},
    })
    (output_dir / "c2_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Repeatable C1/C2 run from local CMS TiC index files")
    parser.add_argument("--index-dir", type=Path, help="Folder of *_index.json files")
    parser.add_argument("--index", type=Path, action="append", help="Explicit index file; repeatable")
    parser.add_argument("--evidence", type=Path, help="Versioned 2026 official EOC register")
    parser.add_argument("--output-dir", type=Path, default=DELIVERABLES_DIR)
    args = parser.parse_args()
    if args.index:
        paths = args.index
    else:
        index_dir = args.index_dir or (REPO_ROOT / "data" / "indexes")
        if not index_dir.is_dir() and not args.index_dir:
            index_dir = RAW_INDEX_DIR
        paths = list(index_dir.glob("*_index.json"))
    print(json.dumps(run(paths, args.output_dir, args.evidence), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
