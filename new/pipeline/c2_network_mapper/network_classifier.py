"""Challenge C2: Network Classifier & Disambiguation Engine
Integrates the 8-step classification plan with formal evidence hierarchy,
distinct product vs network statuses, anomaly queues, and mixed-file auditing.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

try:
    from pipeline.c2_network_mapper.verify_ppo_network import PPOVerificationEngine
    from pipeline.config import (
        STATUS_CONFIRMED_PPO,
        STATUS_EXCLUDED_NON_PPO,
        STATUS_PROVISIONAL_PPO,
        STATUS_UNRESOLVED,
    )
except ImportError:
    from .verify_ppo_network import PPOVerificationEngine
    from ..config import (
        STATUS_CONFIRMED_PPO,
        STATUS_EXCLUDED_NON_PPO,
        STATUS_PROVISIONAL_PPO,
        STATUS_UNRESOLVED,
    )

logger = logging.getLogger(__name__)


class NetworkClassifier:
    """Classifies health plans into product and network types pursuant to the classification plan."""

    def __init__(self, evidence_csv_path: Optional[Path] = None):
        self.engine = PPOVerificationEngine(evidence_csv_path=evidence_csv_path)
        self.classification_stats = {
            STATUS_CONFIRMED_PPO: 0,
            STATUS_PROVISIONAL_PPO: 0,
            STATUS_EXCLUDED_NON_PPO: 0,
            STATUS_UNRESOLVED: 0
        }

    def classify_dataset(self, df: pd.DataFrame) -> pd.DataFrame:
        """Classifies plan records and assigns both product_status and network_status."""
        dec_df, manifest_df, review_queue, summary = self.engine.verify_all_plans(df)
        self.classification_stats[STATUS_CONFIRMED_PPO] = summary["confirmed_ppo_count"]
        self.classification_stats[STATUS_PROVISIONAL_PPO] = summary["provisional_ppo_count"]
        self.classification_stats[STATUS_EXCLUDED_NON_PPO] = summary["excluded_non_ppo_count"]
        self.classification_stats[STATUS_UNRESOLVED] = summary["unresolved_count"]

        # Keep backward compatibility column
        dec_df["network_classification"] = dec_df["product_status"]
        dec_df["classification_rationale"] = dec_df["decision_reason"]
        dec_df["confidence_score"] = dec_df["product_status"].map({
            STATUS_CONFIRMED_PPO: 0.98,
            STATUS_PROVISIONAL_PPO: 0.85,
            STATUS_EXCLUDED_NON_PPO: 1.0,
            STATUS_UNRESOLVED: 0.50
        }).fillna(0.70)

        logger.info("Classification Breakdown: %s", self.classification_stats)
        return dec_df

    def extract_ppo_network_files(self, classified_df: pd.DataFrame) -> pd.DataFrame:
        """Isolates unique rate files that reference confirmed or provisional PPO plans,
        marking shared files with the MIXED classification flag.
        """
        _, manifest_df, _, _ = self.engine.verify_all_plans(classified_df)
        ppo_files = manifest_df[
            (manifest_df["confirmed_ppo_plans"] > 0) | (manifest_df["provisional_ppo_plans"] > 0)
        ].copy()

        return ppo_files
