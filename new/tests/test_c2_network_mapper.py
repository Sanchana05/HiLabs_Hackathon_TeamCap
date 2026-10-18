"""C2 evidence, scope, provenance, and C3/C4 manifest contract checks."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

NEW_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = NEW_DIR.parent
sys.path.insert(0, str(NEW_DIR))

from pipeline.c1_index_parser.index_parser import CenteneIndexParser
from pipeline.c2_network_mapper.network_classifier import NetworkClassifier
from pipeline.c2_network_mapper.verify_ppo_network import PPOVerificationEngine

SOURCE = "2026-09-30_healthnet_index.json"
URL = "https://www.centene.com/content/dam/centene/Centene%20Corporate/json/DOCUMENT/2026-09-30_centene-management-company-llc_healthnet-ca_in-network.json"


def row(name: str, **updates) -> dict:
    record = {
        "brand": "healthnet", "plan_name": name, "plan_id": "67138CA073",
        "plan_id_type": "ein", "market_type": "group", "issuer_name": "Healthnet, LLC",
        "source_index": SOURCE, "last_updated_on": "2026-09-30",
        "rate_file_url": URL,
    }
    record.update(updates)
    return record


class C2EvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = PPOVerificationEngine()

    def test_exact_2026_eoc_confirms_name_but_flags_anomalous_ein(self):
        result = self.engine.classify_and_verify_plan(row("Gold PPO 500/20"))
        self.assertEqual(result["product_status"], "CONFIRMED_PPO")
        self.assertEqual(result["network_name"], "Full Network PPO")
        self.assertEqual(result["evidence_ids"], "HN2026PPO015")
        self.assertIn("INVALID_EIN_FORMAT", result["anomaly_tags"])
        self.assertIn("INDEX_EIN_NOT_PRODUCT_ID", result["evidence_match_basis"])

    def test_different_benefit_variant_is_only_provisional(self):
        result = self.engine.classify_and_verify_plan(row("Gold HDHP PPO 1800/20%"))
        self.assertEqual(result["product_status"], "PROVISIONAL_PPO")
        self.assertEqual(result["network_status"], "UNKNOWN_NETWORK")
        self.assertFalse(result["evidence_ids"])

    def test_conflict_retiree_and_unlabeled_are_reviewed(self):
        names = [
            "CA L CUS PPO IRONWORKERS EPO$15",
            "CA L CUS PPO HN Retiree",
            "CA L SAL Mex 5/0/1500",
        ]
        for name in names:
            with self.subTest(name=name):
                self.assertEqual(self.engine.classify_and_verify_plan(row(name))["product_status"], "UNRESOLVED")

    def test_explicit_non_ppo_and_scope_are_separate(self):
        self.assertEqual(self.engine.classify_and_verify_plan(row("CA L EOA 20"))["product_status"], "EXCLUDED_NON_PPO")
        outside = self.engine.classify_and_verify_plan(row("Gold PPO 500/20", rate_file_url=URL.replace("healthnet-ca", "healthnet-ny")))
        self.assertEqual(outside["product_status"], "OUT_OF_SCOPE")
        self.assertFalse(outside["evidence_ids"])

    def test_hios_id_requires_evidence_id_match(self):
        candidate = self.engine.classify_and_verify_plan(row("Gold PPO 500/20", plan_id="12345CA001", plan_id_type="hios"))
        self.assertEqual(candidate["product_status"], "PROVISIONAL_PPO")

    def test_evidence_file_is_required_and_duplicates_fail_closed(self):
        with self.assertRaises(FileNotFoundError):
            PPOVerificationEngine(Path("does-not-exist.csv"))
        with tempfile.TemporaryDirectory(dir=NEW_DIR / "cache") as tmp:
            path = Path(tmp) / "evidence.csv"
            source = pd.read_csv(NEW_DIR / "config" / "ppo_evidence_sources.csv", dtype=str).head(1)
            pd.concat([source, source]).to_csv(path, index=False)
            with self.assertRaises(ValueError):
                PPOVerificationEngine(path)

    def test_manifest_remains_compatible_and_never_claims_provider_membership(self):
        records = pd.DataFrame([
            row("Gold PPO 500/20"),
            row("CA L HMO 30"),
            row("CA L PPO 30/1000/5000/20%"),
        ])
        decisions, manifest, review, summary = self.engine.verify_all_plans(records)
        selected = NetworkClassifier().extract_ppo_network_files(decisions)
        self.assertEqual(manifest.iloc[0]["file_classification"], "MIXED")
        self.assertEqual(selected.iloc[0]["plan_attribution_limitation"], "SHARED_FILE_UNRESOLVED")
        self.assertEqual(summary["review_queue_count"], 1)
        self.assertEqual(review.iloc[0]["product_status"], "PROVISIONAL_PPO")

    def test_provisional_only_file_is_not_marked_ppo_only(self):
        decisions, manifest, _, _ = self.engine.verify_all_plans(pd.DataFrame([
            row("CA L PPO 30/1000/5000/20%")
        ]))
        self.assertEqual(decisions.iloc[0]["product_status"], "PROVISIONAL_PPO")
        self.assertEqual(manifest.iloc[0]["file_classification"], "UNKNOWN")


class SuppliedIndexesIntegrationTests(unittest.TestCase):
    def test_all_supplied_indexes_and_c2_decisions(self):
        files = sorted((REPO_ROOT / "data" / "indexes").glob("*_index.json"))
        self.assertEqual(len(files), 11)
        parser = CenteneIndexParser()
        for path in files:
            parser.parse_index_file(path)
        plans = parser.build_deduplicated_plan_table()
        self.assertEqual(len(plans), 3270)
        self.assertIn("plan_id_type", plans.columns)
        self.assertIn("source_indexes", plans.columns)
        self.assertIn("last_updated_on", plans.columns)
        self.assertEqual(plans.duplicated([
            "brand", "plan_name", "plan_id", "plan_id_type", "market_type", "rate_file_url"
        ]).sum(), 0)
        decisions, manifest, review, summary = PPOVerificationEngine().verify_all_plans(plans)
        self.assertEqual(summary["confirmed_ppo_count"], 30)
        self.assertEqual(summary["provisional_ppo_count"], 422)
        self.assertEqual(summary["out_of_scope_count"], 1958)
        self.assertEqual(summary["review_queue_count"], 430)
        self.assertEqual(summary["mixed_rate_files_count"], 1)
        self.assertEqual(len(manifest[manifest.confirmed_ppo_plans > 0]), 1)
        self.assertTrue((decisions[decisions.product_status == "CONFIRMED_PPO"]["evidence_ids"] != "").all())


if __name__ == "__main__":
    unittest.main()
