import csv
import json
from datetime import date
from pathlib import Path

from pipeline.c5_address_mapper.resolve import run_c5


def write_csv(path: Path, columns: list[str], rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def test_c5_keeps_multiple_sites_separates_ppo_and_tin_proof(tmp_path: Path) -> None:
    c4 = tmp_path / "selected_rates.csv"
    write_csv(c4, ["npi", "tin_type", "tin", "source_file_id", "billing_code", "rate"], [
        {"npi": "1234567890", "tin_type": "ein", "tin": "123456789", "source_file_id": "mixed-file", "billing_code": "99213", "rate": "100"},
        {"npi": "2234567890", "tin_type": "ein", "tin": "123456789", "source_file_id": "mixed-file", "billing_code": "99213", "rate": "110"},
        {"npi": "3234567890", "tin_type": "ein", "tin": "999999999", "source_file_id": "mixed-file", "billing_code": "99213", "rate": "120"},
    ])
    main = tmp_path / "npidata.csv"
    cols = ["NPI", "Entity Type Code", "Provider First Name", "Provider Last Name (Legal Name)",
            "Healthcare Provider Taxonomy Code_1", "Healthcare Provider Primary Taxonomy Switch_1",
            "Last Update Date", "NPI Deactivation Date", "NPI Reactivation Date",
            "Provider First Line Business Practice Location Address",
            "Provider Second Line Business Practice Location Address",
            "Provider Business Practice Location Address City Name",
            "Provider Business Practice Location Address State Name",
            "Provider Business Practice Location Address Postal Code"]
    def nppes(npi, line, unit=""):
        return {"NPI": npi, "Entity Type Code": "1", "Provider First Name": "Alex",
                "Provider Last Name (Legal Name)": npi, "Healthcare Provider Taxonomy Code_1": "207Q00000X",
                "Healthcare Provider Primary Taxonomy Switch_1": "Y", "Last Update Date": "2026-10-01",
                "Provider First Line Business Practice Location Address": line,
                "Provider Second Line Business Practice Location Address": unit,
                "Provider Business Practice Location Address City Name": "Los Angeles",
                "Provider Business Practice Location Address State Name": "CA",
                "Provider Business Practice Location Address Postal Code": "90024"}
    write_csv(main, cols, [nppes("1234567890", "100 Main Street", "Suite 100"),
                           nppes("2234567890", "200 Main Street"),
                           nppes("3234567890", "300 Main Street")])
    secondary = tmp_path / "pl.csv"
    write_csv(secondary, ["NPI", "Provider Secondary Practice Location Address- Address Line 1",
                          "Provider Secondary Practice Location Address-  Address Line 2",
                          "Provider Secondary Practice Location Address - City Name",
                          "Provider Secondary Practice Location Address - State Name",
                          "Provider Secondary Practice Location Address - Postal Code"], [
        {"NPI": "1234567890", "Provider Secondary Practice Location Address- Address Line 1": "400 Oak Road",
         "Provider Secondary Practice Location Address - City Name": "Los Angeles",
         "Provider Secondary Practice Location Address - State Name": "CA",
         "Provider Secondary Practice Location Address - Postal Code": "90024"}])
    external_cols = ["npi", "address_line1", "address_line2", "city", "state", "zip",
                     "source_date", "record_url", "plan_name", "plan_year", "tin_type", "tin"]
    payer = tmp_path / "payer.csv"
    write_csv(payer, external_cols, [
        {"npi": "1234567890", "address_line1": "100 Main St", "address_line2": "Ste 100", "city": "Los Angeles",
         "state": "CA", "zip": "90024", "source_date": "2026-10-01", "record_url": "payer:1",
         "plan_name": "Full Network PPO", "plan_year": "2026"},
        {"npi": "2234567890", "address_line1": "200 Main St", "city": "Los Angeles",
         "state": "CA", "zip": "90024", "source_date": "2026-10-01", "record_url": "payer:2",
         "plan_name": "Other HMO", "plan_year": "2026"}])
    roster = tmp_path / "roster.csv"
    write_csv(roster, external_cols, [
        {"npi": "1234567890", "address_line1": "100 Main St", "address_line2": "Ste 100", "city": "Los Angeles",
         "state": "CA", "zip": "90024", "source_date": "2026-10-01", "record_url": "roster:1",
         "tin_type": "ein", "tin": "123456789"}])
    cms = tmp_path / "cms.csv"
    write_csv(cms, ["NPI", "adr_ln_1", "adr_ln_2", "citytown", "state", "zip_code", "source_date"], [
        {"NPI": "2234567890", "adr_ln_1": "200 Main St", "citytown": "Los Angeles", "state": "CA", "zip_code": "90024", "source_date": "2026-09-10"}])
    out = tmp_path / "out"
    summary = run_c5(selected_rates=[c4], nppes_main=main, nppes_secondary=secondary,
                     output_dir=out, as_of=date(2026, 10, 18), monthly_through=date(2026, 10, 11),
                     payer_directory=payer, provider_roster=roster, cms=cms, ppo_plans=["Full Network PPO"])
    with (out / "c5_provider_locations.csv").open(newline="", encoding="utf-8") as stream:
        locations = list(csv.DictReader(stream))
    first = [r for r in locations if r["npi"] == "1234567890"]
    assert len(first) == 2
    assert {r["address"] for r in first} == {"100 MAIN ST STE 100, Los Angeles, CA 90024", "400 OAK RD, Los Angeles, CA 90024"}
    confirmed = next(r for r in first if "100 MAIN" in r["address"])
    assert (confirmed["practice_site_status"], confirmed["ppo_participation_status"], confirmed["tin_link_status"]) == ("corroborated", "confirmed", "proven")
    assert next(r for r in first if "400 OAK" in r["address"])["practice_site_status"] == "candidate"
    second = next(r for r in locations if r["npi"] == "2234567890")
    assert second["practice_site_status"] == "corroborated"
    assert second["ppo_participation_status"] == "unknown"
    assert second["tin_link_status"] == "unproven"
    assert summary["unique_npis_with_confirmed_ppo_site"] == 1
    assert summary["unique_npis_with_proven_tin_site"] == 1
    assert summary["unique_npis_with_fully_verified_link"] == 1
    assert (out / "c5_evidence.csv").is_file()
    assert (out / "c5_review_queue.csv").is_file()


def test_c5_no_valid_location_is_reviewed_not_fabricated(tmp_path: Path) -> None:
    c4 = tmp_path / "selected.csv"
    write_csv(c4, ["npi", "tin_type", "tin"], [{"npi": "1234567890", "tin_type": "ein", "tin": "123456789"}])
    main = tmp_path / "main.csv"
    write_csv(main, ["NPI", "Entity Type Code", "Provider First Line Business Practice Location Address",
                     "Provider Business Practice Location Address City Name",
                     "Provider Business Practice Location Address State Name",
                     "Provider Business Practice Location Address Postal Code"], [
        {"NPI": "1234567890", "Entity Type Code": "2", "Provider First Line Business Practice Location Address": "PO Box 44",
         "Provider Business Practice Location Address City Name": "Los Angeles", "Provider Business Practice Location Address State Name": "CA",
         "Provider Business Practice Location Address Postal Code": "90024"}])
    secondary = tmp_path / "secondary.csv"
    write_csv(secondary, ["NPI"], [])
    out = tmp_path / "out"
    run_c5(selected_rates=[c4], nppes_main=main, nppes_secondary=secondary,
           output_dir=out, as_of=date(2026, 10, 18), monthly_through=date(2026, 10, 11))
    assert len((out / "c5_provider_locations.csv").read_text().splitlines()) == 1
    with (out / "c5_review_queue.csv").open(newline="", encoding="utf-8") as stream:
        review = list(csv.DictReader(stream))
    assert review[0]["practice_site_status"] == "unresolved"
    assert review[0]["address"] == ""


def test_c5_newer_weekly_replaces_monthly_and_deactivation_blocks_site(tmp_path: Path) -> None:
    c4 = tmp_path / "selected.csv"
    write_csv(c4, ["npi", "tin_type", "tin"], [{"npi": "1234567890", "tin_type": "ein", "tin": "123456789"}])
    columns = ["NPI", "Entity Type Code", "NPI Deactivation Date",
               "Provider First Line Business Practice Location Address",
               "Provider Business Practice Location Address City Name",
               "Provider Business Practice Location Address State Name",
               "Provider Business Practice Location Address Postal Code"]
    def row(line, deactivated=""):
        return {"NPI": "1234567890", "Entity Type Code": "2", "NPI Deactivation Date": deactivated,
                "Provider First Line Business Practice Location Address": line,
                "Provider Business Practice Location Address City Name": "Los Angeles",
                "Provider Business Practice Location Address State Name": "CA",
                "Provider Business Practice Location Address Postal Code": "90024"}
    monthly = tmp_path / "monthly.csv"
    weekly = tmp_path / "weekly.csv"
    write_csv(monthly, columns, [row("100 Old Street")])
    write_csv(weekly, columns, [row("200 New Street", "10/16/2026")])
    secondary_cols = ["NPI", "Provider Secondary Practice Location Address- Address Line 1",
                      "Provider Secondary Practice Location Address-  Address Line 2",
                      "Provider Secondary Practice Location Address - City Name",
                      "Provider Secondary Practice Location Address - State Name",
                      "Provider Secondary Practice Location Address - Postal Code"]
    old_secondary = tmp_path / "old_pl.csv"
    new_secondary = tmp_path / "new_pl.csv"
    write_csv(old_secondary, secondary_cols, [{"NPI": "1234567890",
        "Provider Secondary Practice Location Address- Address Line 1": "300 Former Road",
        "Provider Secondary Practice Location Address - City Name": "Los Angeles",
        "Provider Secondary Practice Location Address - State Name": "CA",
        "Provider Secondary Practice Location Address - Postal Code": "90024"}])
    write_csv(new_secondary, secondary_cols, [])
    out = tmp_path / "out"
    run_c5(selected_rates=[c4], nppes_main=monthly, nppes_secondary=old_secondary,
           weekly_main=weekly, weekly_secondary=new_secondary,
           monthly_through=date(2026, 10, 11), weekly_through=date(2026, 10, 16),
           as_of=date(2026, 10, 18), output_dir=out)
    with (out / "c5_provider_locations.csv").open(newline="", encoding="utf-8") as stream:
        sites = list(csv.DictReader(stream))
    assert len(sites) == 1
    assert "200 NEW ST" in sites[0]["address"]
    assert sites[0]["practice_site_status"] == "unresolved"
    assert "100 OLD" not in (out / "c5_evidence.csv").read_text()


def test_cms_agreement_corroborates_exact_suite_despite_other_suite(tmp_path: Path) -> None:
    selected = tmp_path / "rates.csv"
    write_csv(selected, ["npi", "tin_type", "tin"],
              [{"npi": "1234567890", "tin_type": "ein", "tin": "123456789"}])
    main = tmp_path / "main.csv"
    write_csv(main, ["NPI", "Entity Type Code",
                     "Provider First Line Business Practice Location Address",
                     "Provider Second Line Business Practice Location Address",
                     "Provider Business Practice Location Address City Name",
                     "Provider Business Practice Location Address State Name",
                     "Provider Business Practice Location Address Postal Code"], [{
        "NPI": "1234567890", "Entity Type Code": "1",
        "Provider First Line Business Practice Location Address": "100 Main Street",
        "Provider Second Line Business Practice Location Address": "Suite 100",
        "Provider Business Practice Location Address City Name": "Los Angeles",
        "Provider Business Practice Location Address State Name": "CA",
        "Provider Business Practice Location Address Postal Code": "90024"}])
    secondary = tmp_path / "secondary.csv"
    write_csv(secondary, ["NPI", "Provider Secondary Practice Location Address- Address Line 1",
                          "Provider Secondary Practice Location Address-  Address Line 2",
                          "Provider Secondary Practice Location Address - City Name",
                          "Provider Secondary Practice Location Address - State Name",
                          "Provider Secondary Practice Location Address - Postal Code"], [{
        "NPI": "1234567890", "Provider Secondary Practice Location Address- Address Line 1": "100 Main St",
        "Provider Secondary Practice Location Address-  Address Line 2": "Ste 200",
        "Provider Secondary Practice Location Address - City Name": "Los Angeles",
        "Provider Secondary Practice Location Address - State Name": "CA",
        "Provider Secondary Practice Location Address - Postal Code": "90024"}])
    cms = tmp_path / "cms.csv"
    write_csv(cms, ["npi", "address_line1", "address_line2", "city", "state", "zip", "source_date"], [{
        "npi": "1234567890", "address_line1": "100 Main St", "address_line2": "Ste 100",
        "city": "Los Angeles", "state": "CA", "zip": "90024", "source_date": "2026-10-02"}])
    out = tmp_path / "out"
    run_c5(selected_rates=[selected], nppes_main=main, nppes_secondary=secondary,
           output_dir=out, as_of=date(2026, 10, 18), monthly_through=date(2026, 10, 11), cms=cms)
    sites = list(csv.DictReader((out / "c5_provider_locations.csv").open(newline="", encoding="utf-8")))
    assert next(r for r in sites if "STE 100" in r["address"])["practice_site_status"] == "corroborated"
    assert next(r for r in sites if "STE 200" in r["address"])["practice_site_status"] == "conflicted"
