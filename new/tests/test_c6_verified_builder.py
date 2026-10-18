import csv
from pathlib import Path

from pipeline.c6_rate_builder.verified_builder import build_verified_rates


def write_csv(path: Path, fields: list[str], rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def test_c6_gates_mixed_files_and_ambiguous_contexts(tmp_path: Path) -> None:
    sites = tmp_path / "sites.csv"
    write_csv(sites, ["npi", "tin_type", "tin", "address_key", "address", "specialty",
                      "source_ids", "practice_site_status", "tin_link_status", "ppo_participation_status"], [
        {"npi": "1234567890", "tin_type": "ein", "tin": "123456789", "address_key": "a1",
         "address": "100 MAIN ST, Los Angeles, CA 90024", "specialty": "Family Medicine", "source_ids": "1;2",
         "practice_site_status": "corroborated", "tin_link_status": "proven", "ppo_participation_status": "confirmed"},
        {"npi": "2234567890", "tin_type": "ein", "tin": "123456789", "address_key": "a2",
         "address": "200 MAIN ST, Los Angeles, CA 90024", "specialty": "Family Medicine", "source_ids": "3",
         "practice_site_status": "candidate", "tin_link_status": "unproven", "ppo_participation_status": "unknown"},
    ])
    rates = tmp_path / "rates.csv"
    fields = ["npi", "tin_type", "tin", "billing_code", "rate", "source_file_id",
              "source_locator", "plan_attribution", "file_classification", "setting"]
    base = {"npi": "1234567890", "tin_type": "ein", "tin": "123456789",
            "source_file_id": "f1", "plan_attribution": "PPO_ONLY", "file_classification": "PPO_ONLY"}
    write_csv(rates, fields, [
        {**base, "billing_code": "99213", "rate": "100", "setting": "outpatient"},
        {**base, "billing_code": "99214", "rate": "130", "setting": "outpatient"},
        {**base, "billing_code": "99214", "rate": "140", "setting": "both"},
        {**base, "billing_code": "99215", "rate": "150", "plan_attribution": "SHARED_FILE_UNRESOLVED", "file_classification": "MIXED"},
        {**base, "npi": "2234567890", "billing_code": "99213", "rate": "90"},
    ])
    out = tmp_path / "out"
    summary = build_verified_rates([rates], sites, out,
                                   allowed_plan_attributions={"PPO_ONLY", "SHARED_FILE_UNRESOLVED"})
    with (out / "c6_verified_rates.csv").open(newline="", encoding="utf-8") as stream:
        exported = list(csv.DictReader(stream))
    assert len(exported) == 1
    assert exported[0]["Billing Code"] == "99213"
    assert summary["counts"]["withheld_unattributed_rate_rows"] == 1
    assert summary["counts"]["withheld_no_verified_site_rows"] == 1
    assert summary["counts"]["ambiguous_context_rows"] == 2
    assert (out / "Centene_CA_Commercial_PPO_Provider_Rates.xlsx").is_file()
