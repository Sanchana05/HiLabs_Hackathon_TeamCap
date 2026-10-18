"""C3 regression checks for full-file counting and honest unknowns."""
import csv
import gzip
import json
import tempfile
import unittest
from unittest.mock import patch
from datetime import date
from pathlib import Path

from pipeline.c3_file_grader.file_grader import FileQualityGrader, main, write_reports


class FileGraderTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=Path.cwd())
        self.root = Path(self.temporary.name)
        self.panel = self.root / "panel.csv"
        self.panel.write_text("billing_code,weight\n99213,2\n99214,1\n", encoding="utf-8")

    def tearDown(self):
        self.temporary.cleanup()

    def fixture(self, *, updated="2026-10-01", compressed=False):
        prices = [
            {"negotiated_type": "negotiated", "negotiated_rate": 100 + n,
             "billing_class": "professional", "service_code": ["11"],
             "expiration_date": "2026-12-31"}
            for n in range(30)
        ]
        prices.extend([
            {"negotiated_type": "negotiated", "negotiated_rate": 1000,
             "billing_class": "professional", "service_code": ["11"],
             "expiration_date": "2026-12-31"},
            {"negotiated_type": "negotiated", "negotiated_rate": 0,
             "billing_class": "professional", "service_code": ["11"],
             "expiration_date": "2026-12-31"},
        ])
        obj = {
            "version": "2.0.0", "provider_references": [
                {"provider_group_id": 7, "provider_groups": [
                    {"tin": {"type": "ein", "value": "123456789"}, "npi": ["1234567890"]}
                ]}
            ],
            "in_network": [{"billing_code_type": "CPT", "billing_code": "99213",
                            "negotiated_rates": [
                                {"provider_references": [7], "negotiated_prices": prices},
                                {"provider_references": [7], "negotiated_prices": [prices[0]]},
                                {"provider_references": [999], "negotiated_prices": [prices[1]]},
                            ]}]
        }
        if updated:
            obj["last_updated_on"] = updated
        path = self.root / ("rates.json.gz" if compressed else "rates.json")
        if compressed:
            with gzip.open(path, "wt", encoding="utf-8") as stream:
                json.dump(obj, stream)
        else:
            path.write_text(json.dumps(obj), encoding="utf-8")
        return path

    def test_raw_zero_missing_link_duplicate_and_outlier_are_counted(self):
        path = self.fixture(compressed=True)
        result = FileQualityGrader(self.panel).grade_file(
            path, as_of=date(2026, 10, 18), scratch_dir=self.root)
        counts = result["counts"]
        self.assertEqual(counts["published_prices"], 34)
        self.assertEqual(counts["zero_or_negative_prices"], 1)
        self.assertEqual(counts["unlinked_prices"], 1)
        self.assertEqual(counts["unresolved_reference_uses"], 1)
        self.assertEqual(counts["duplicate_provider_prices"], 1)
        self.assertEqual(counts["outlier_prices"], 1)
        self.assertEqual(result["unique_npis"], 1)
        self.assertEqual(result["dimension_scores"]["code_panel_coverage"], 66.67)
        self.assertIsNotNone(result["composite_fqs"])
        self.assertIsNone(result["external_provider_coverage_pct"])

    def test_missing_update_date_cannot_earn_freshness_points(self):
        path = self.fixture(updated="")
        result = FileQualityGrader(self.panel).grade_file(
            path, as_of=date(2026, 10, 18), scratch_dir=self.root)
        self.assertIsNone(result["dimension_scores"]["freshness"])
        self.assertIsNone(result["composite_fqs"])
        self.assertEqual(result["grade"], "NOT_GRADED")

    def test_each_file_has_a_separate_scorecard_row(self):
        grader = FileQualityGrader(self.panel)
        first = grader.grade_file(self.fixture(), as_of=date(2026, 10, 18), scratch_dir=self.root)
        second_path = self.root / "second.json"
        second_path.write_bytes((self.root / "rates.json").read_bytes())
        second = grader.grade_file(second_path, as_of=date(2026, 10, 18), scratch_dir=self.root)
        write_reports([first, second], self.root / "out")
        with (self.root / "out" / "file_quality_scorecard.csv").open(newline="", encoding="utf-8") as stream:
            rows = list(csv.DictReader(stream))
        self.assertEqual([row["file_name"] for row in rows], ["rates.json", "second.json"])

    def test_revenue_code_reuse_does_not_create_false_duplicates(self):
        common_price = {"negotiated_type": "negotiated", "negotiated_rate": 100,
                        "billing_class": "professional", "expiration_date": "2026-12-31"}
        obj = {"last_updated_on": "2026-10-01", "in_network": [
            {"billing_code_type": "RC", "billing_code": "636",
             "description": description, "negotiated_rates": [
                 {"provider_groups": [{"tin": {"type": "ein", "value": "123456789"},
                                       "npi": ["1234567890"]}],
                  "negotiated_prices": [common_price]}
             ]} for description in ("Drug A", "Drug B")
        ]}
        path = self.root / "revenue.json"
        path.write_text(json.dumps(obj), encoding="utf-8")
        result = FileQualityGrader(self.panel).grade_file(
            path, as_of=date(2026, 10, 18), scratch_dir=self.root)
        self.assertEqual(result["counts"].get("duplicate_provider_prices", 0), 0)
        self.assertEqual(result["benchmark_codes_present"], 0)

    def test_manifest_cli_grades_selected_file(self):
        path = self.fixture()
        manifest = self.root / "file_manifest.csv"
        manifest.write_text(
            "rate_file_name,rate_file_url,file_classification\n"
            f"{path.name},https://example.org/rates.json,MIXED\n", encoding="utf-8")
        argv = ["c3", "--manifest", str(manifest), "--rate-dir", str(self.root),
                "--output-dir", str(self.root / "out"), "--as-of", "2026-10-18",
                "--benchmark-csv", str(self.panel)]
        with patch("sys.argv", argv):
            main()
        details = json.loads((self.root / "out" / "file_quality_details.json").read_text())
        self.assertEqual(details[0]["source_url"], "https://example.org/rates.json")
        self.assertEqual(details[0]["file_classification"], "MIXED")

    def test_bad_roster_fails_and_removes_scratch_state(self):
        path = self.fixture()
        roster = self.root / "bad_roster.csv"
        roster.write_text("provider_id\n1234567890\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "npi column"):
            FileQualityGrader(self.panel, roster).grade_file(
                path, as_of=date(2026, 10, 18), scratch_dir=self.root)
        self.assertEqual(list(self.root.glob("c3_audit_*")), [])


if __name__ == "__main__":
    unittest.main()
