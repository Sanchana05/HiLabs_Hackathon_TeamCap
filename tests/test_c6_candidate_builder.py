import csv
from pathlib import Path

from pipeline.c6_rate_builder.candidate_builder import build_candidates


def write_csv(path: Path, fields: list[str], rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def test_shared_ppo_file_corrob_site_yields_labeled_candidate_only(tmp_path: Path) -> None:
    c2 = tmp_path / "c2.csv"
    write_csv(c2, ["rate_file_url", "target_confirmed_ppo_plans"],
              [{"rate_file_url": "https://payer/mrf.json", "target_confirmed_ppo_plans": "2"}])
    c4 = tmp_path / "c4.csv"
    base = {"source_file_id": "file1", "source_url": "https://payer/mrf.json",
            "file_classification": "MIXED", "npi": "1234567890", "tin_type": "ein",
            "tin": "123456789", "billing_code_type": "CPT", "billing_code": "99213"}
    write_csv(c4, list(base) + ["rate", "source_locator"], [
        {**base, "rate": "100.00", "source_locator": "item/1"},
        {**base, "rate": "100.00", "source_locator": "item/2"},
        {**base, "billing_code": "99214", "rate": "120.00", "source_locator": "item/3"},
        {**base, "billing_code": "99214", "rate": "130.00", "source_locator": "item/4"},
        {**base, "billing_code": "99215", "rate": "150.00", "source_locator": "item/5"},
        {**base, "billing_code": "99215", "billing_code_type": "HCPCS",
         "rate": "150.00", "source_locator": "item/6"},
    ])
    c5 = tmp_path / "sites.csv"
    write_csv(c5, ["npi", "tin_type", "tin", "address", "specialty", "source_ids",
                   "practice_site_status", "tin_link_status", "ppo_participation_status"], [
        {"npi": "1234567890", "tin_type": "ein", "tin": "123456789",
         "address": "100 MAIN ST, Los Angeles, CA 90024", "specialty": "Family Medicine",
         "source_ids": "1;2", "practice_site_status": "corroborated",
         "tin_link_status": "unproven", "ppo_participation_status": "unknown"},
    ])
    evidence = tmp_path / "evidence.csv"
    write_csv(evidence, ["id", "source", "source_date", "source_ref"], [
        {"id": "1", "source": "NPPES_PRIMARY", "source_date": "2026-10-01", "source_ref": "nppes:1"},
        {"id": "2", "source": "CMS_CLINICIAN", "source_date": "2026-10-02", "source_ref": "cms:2"},
    ])
    summary = build_candidates([c4], c2, c5, evidence, tmp_path / "out")
    with (tmp_path / "out/c6_supported_rate_candidates.csv").open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 1
    assert rows[0]["Rate"] == "100.00"
    assert summary["counts"]["MULTIPLE_RATES_FOR_SIX_COLUMN_KEY"] == 1
    assert summary["counts"]["MULTIPLE_CODE_TYPES_FOR_SIX_COLUMN_KEY"] == 1
    with (tmp_path / "out/c6_candidate_evidence.csv").open(newline="", encoding="utf-8") as stream:
        details = list(csv.DictReader(stream))
    assert details[0]["Decision"] == "RESEARCH_CANDIDATE_NOT_DIRECTORY_VERIFIED"
    assert "CMS_CLINICIAN" in details[0]["Address Evidence"]
