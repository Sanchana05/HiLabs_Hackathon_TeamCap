"""Deterministic Verification of Centene California Commercial Group PPO Network.
Standalone command specified in Centene California commercial-group PPO classification plan.
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import unquote, urlsplit

import pandas as pd

# Add repo root to sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# Use the robust verification engine from new.pipeline
from new.pipeline.c2_network_mapper.verify_ppo_network import PPOVerificationEngine

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")


def main():
    ap = argparse.ArgumentParser(description="Deterministic Centene PPO Network Verifier")
    ap.add_argument("--plans", type=Path, required=True, help="Path to C1 deduplicated plan CSV")
    ap.add_argument("--evidence", type=Path, default=Path("config/ppo_evidence_sources.csv"), help="Path to ppo_evidence_sources.csv")
    ap.add_argument("--output", type=Path, default=Path("outputs/ppo"), help="Output directory for PPO decisions")
    args = ap.parse_args()

    args.output.mkdir(parents=True, exist_ok=True)
    engine = PPOVerificationEngine(evidence_csv_path=args.evidence)

    plans_df = pd.read_csv(args.plans, dtype=str).fillna("")
    dec_df, manifest_df, review_queue, summary = engine.verify_all_plans(plans_df)

    dec_df.to_csv(args.output / "plan_decisions.csv", index=False)
    manifest_df.to_csv(args.output / "file_manifest.csv", index=False)
    review_queue.to_csv(args.output / "review_queue.csv", index=False)

    with open(args.output / "summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print("=" * 60)
    print("PPO NETWORK VERIFICATION SUMMARY")
    print("=" * 60)
    print(json.dumps(summary, indent=2))
    print(f"Decisions saved to: {args.output / 'plan_decisions.csv'}")
    print(f"File manifest saved to: {args.output / 'file_manifest.csv'}")
    print(f"Review queue saved to: {args.output / 'review_queue.csv'}")


if __name__ == "__main__":
    main()
