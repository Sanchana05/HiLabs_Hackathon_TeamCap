"""C4 contract tests for source fidelity and exact-context selection."""
import csv
import gzip
import hashlib
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from pipeline.c4_rate_extractor.rate_extractor import RateExtractor, RateFileInput, _inputs, run_files


class RateExtractorTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=Path.cwd())
        self.root = Path(self.temporary.name)
        self.price = {"negotiated_type": "negotiated", "negotiated_rate": 100,
                      "expiration_date": "9999-12-31", "billing_class": "professional",
                      "setting": "outpatient", "service_code": ["11"]}

    def tearDown(self):
        self.temporary.cleanup()

    def fixture(self, *, gzip_file=False):
        prices = [self.price, dict(self.price), dict(self.price, negotiated_rate=200),
                  dict(self.price, negotiated_rate=90, billing_code_modifier=["26"]),
                  dict(self.price, negotiated_rate=80, service_code=["22"]),
                  dict(self.price, negotiated_type="percentage", negotiated_rate=40),
                  dict(self.price, negotiated_rate=70, expiration_date="2020-01-01"),
                  dict(self.price, negotiated_rate=0)]
        data = {"provider_references": [{"provider_group_id": 1, "provider_groups": [
            {"tin": {"type": "ein", "value": "12-3456789"}, "npi": ["1234567890"]}]}],
            "in_network": [{"negotiation_arrangement": "ffs", "name": "Office visit",
                            "billing_code_type": "CPT", "billing_code_type_version": "2026",
                            "billing_code": "99213", "description": "Office visit",
                            "negotiated_rates": [
                                {"provider_references": [1], "negotiated_prices": prices},
                                {"provider_references": [999], "negotiated_prices": [self.price]},
                                {"provider_groups": [{"tin": {"type": "ein", "value": "123456789"},
                                                      "npi": [0]}], "negotiated_prices": [self.price]},
                            ]}]}
        path = self.root / ("rates.json.gz" if gzip_file else "rates.json")
        if gzip_file:
            with gzip.open(path, "wt", encoding="utf-8") as stream:
                json.dump(data, stream)
        else:
            path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def test_complete_audit_keeps_actual_rate_and_separate_contexts(self):
        path = self.fixture(gzip_file=True)
        result = RateExtractor(as_of=date(2026, 10, 18)).run_file(
            RateFileInput(path, file_classification="MIXED"), self.root / "out")
        with (self.root / "out" / "rate_decisions.csv").open(newline="", encoding="utf-8") as stream:
            decisions = list(csv.DictReader(stream))
        with (self.root / "out" / "selected_rates.csv").open(newline="", encoding="utf-8") as stream:
            selected = list(csv.DictReader(stream))
        self.assertEqual(result["counts"]["published_prices"], 10)
        self.assertEqual(len(decisions), 10)
        self.assertEqual(len(selected), 3)
        self.assertEqual({row["rate"] for row in selected}, {"100", "90", "80"})
        self.assertEqual({row["service_code"] for row in selected}, {"11", "22"})
        self.assertTrue(all(row["tin"] == "123456789" and row["tin_raw"] == "12-3456789" for row in selected))
        self.assertEqual({row["decision"] for row in decisions},
                         {"SELECTED", "ALTERNATE", "DUPLICATE", "INVALID", "VALID_NON_BENCHMARK"})
        self.assertTrue(all(row["plan_attribution"] == "SHARED_FILE_UNRESOLVED" for row in decisions))
        self.assertTrue(any("UNRESOLVED_PROVIDER_REFERENCE" in row["decision_reason"] for row in decisions))
        self.assertTrue(any("INVALID_OR_UNKNOWN_NPI" in row["decision_reason"] for row in decisions))
        self.assertTrue(any("EXPIRED_AS_OF" in row["decision_reason"] for row in decisions))
        self.assertEqual(list((self.root / "out").glob("c4_state_*")), [])

    def test_c3_hash_binding_and_manifest_input(self):
        path = self.fixture()
        manifest = self.root / "manifest.csv"
        manifest.write_text("rate_file_name,rate_file_url,file_classification\n"
                            "rates.json,https://example.org/rates.json,MIXED\n", encoding="utf-8")
        details = self.root / "c3.json"
        details.write_text(json.dumps([{"file_name": path.name,
                                       "source_url": "https://example.org/rates.json",
                                       "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                                       "quality_status": "REVIEW_REQUIRED"}]), encoding="utf-8")
        inputs = _inputs([], manifest, [self.root], details)
        results = run_files(inputs, self.root / "out", as_of=date(2026, 10, 18))
        self.assertEqual(results[0]["c3_quality_status"], "REVIEW_REQUIRED")
        self.assertTrue((self.root / "out" / "c4_manifest.csv").is_file())
        with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
            RateExtractor(as_of=date(2026, 10, 18)).run_file(
                RateFileInput(path, expected_sha256="0" * 64), self.root / "bad")

    def test_multiple_file_port_keeps_sources_separate(self):
        first = self.fixture()
        second = self.root / "other.json"
        second.write_bytes(first.read_bytes())
        results = run_files([
            RateFileInput(first, "https://example.org/a", "MIXED"),
            RateFileInput(second, "https://example.org/b", "UNKNOWN"),
        ], self.root / "multi", as_of=date(2026, 10, 18))
        self.assertEqual(len(results), 2)
        self.assertNotEqual(results[0]["source_file_id"], results[1]["source_file_id"])
        self.assertEqual(results[0]["plan_attribution"], "SHARED_FILE_UNRESOLVED")
        self.assertEqual(results[1]["plan_attribution"], "UNVERIFIED_NETWORK_MEMBERSHIP")
        with (self.root / "multi" / "c4_manifest.csv").open(newline="", encoding="utf-8") as stream:
            rows = list(csv.DictReader(stream))
        self.assertEqual(len(rows), 2)

    def test_references_after_in_network_are_resolved(self):
        path = self.fixture()
        original = json.loads(path.read_text(encoding="utf-8"))
        path.write_text(json.dumps({"in_network": original["in_network"],
                                    "provider_references": original["provider_references"]}), encoding="utf-8")
        result = RateExtractor(as_of=date(2026, 10, 18)).run_file(
            RateFileInput(path), self.root / "later_references")
        self.assertEqual(result["counts"]["selected"], 3)
        self.assertEqual(result["counts"]["invalid"], 4)

    def test_unrepresentable_rate_is_audited_without_crashing(self):
        path = self.fixture()
        data = json.loads(path.read_text(encoding="utf-8"))
        data["in_network"][0]["negotiated_rates"][0]["negotiated_prices"][0]["negotiated_rate"] = "1e9999"
        path.write_text(json.dumps(data), encoding="utf-8")
        result = RateExtractor(as_of=date(2026, 10, 18)).run_file(
            RateFileInput(path), self.root / "huge")
        self.assertEqual(result["counts"]["invalid"], 5)
        with (self.root / "huge" / "rate_decisions.csv").open(newline="", encoding="utf-8") as stream:
            rows = list(csv.DictReader(stream))
        self.assertIn("RATE_OUTSIDE_SORTABLE_RANGE", rows[0]["decision_reason"])


if __name__ == "__main__":
    unittest.main()
