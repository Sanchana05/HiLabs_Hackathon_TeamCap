"""Independently reconcile every candidate Excel row to C4 and C5 source outputs."""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path

from openpyxl import load_workbook

from pipeline.c5_address_mapper.resolve import selected_paths


HEADERS = ("NPI", "TIN", "Address", "Billing Code", "Specialty", "Rate")


def rows(path: Path):
    with path.open(newline="", encoding="utf-8-sig") as stream:
        yield from csv.DictReader(stream)


def audit(c4_paths: list[Path], c5_locations: Path, c5_evidence: Path,
          candidate_csv: Path, workbook_path: Path) -> dict:
    published = defaultdict(set)
    for path in c4_paths:
        for row in rows(path):
            published[(row["npi"], row["tin"], row["billing_code"])].add(Decimal(row["rate"]))
    observations = {r["id"]: r["source"] for r in rows(c5_evidence)}
    sites = defaultdict(list)
    for row in rows(c5_locations):
        sites[(row["npi"], row["tin"], row["address"])].append(row)
    candidates = list(rows(candidate_csv))
    workbook = load_workbook(workbook_path, read_only=True, data_only=True)
    try:
        sheet = workbook["Rate candidates"]
        iterator = sheet.values
        header = next(iterator)
        if tuple(header) != HEADERS:
            raise AssertionError(f"Unexpected workbook columns: {header}")
        excel_rows = list(iterator)
        if len(candidates) != len(excel_rows):
            raise AssertionError("Workbook/CSV row count mismatch")
        problems: Counter[str] = Counter()
        seen = set()
        for csv_row, excel_row in zip(candidates, excel_rows):
            npi, tin, address, code, specialty, rate = (csv_row[h] for h in HEADERS)
            key = (npi, tin, address, code)
            if key in seen:
                problems["duplicate_six_column_key"] += 1
            seen.add(key)
            if Decimal(rate) not in published[(npi, tin, code)]:
                problems["rate_not_in_c4"] += 1
            matching = sites[(npi, tin, address)]
            if len(matching) != 1 or matching[0]["practice_site_status"] != "corroborated":
                problems["site_not_corroborated"] += 1
            else:
                families = {observations.get(i, "") for i in matching[0]["source_ids"].split(";")}
                if not {"NPPES_PRIMARY", "NPPES_SECONDARY"} & families or "CMS_CLINICIAN" not in families:
                    problems["no_independent_nppes_cms_agreement"] += 1
            if not specialty:
                problems["missing_specialty"] += 1
            if (str(excel_row[0]), str(excel_row[1]), excel_row[2], str(excel_row[3]),
                excel_row[4], Decimal(str(excel_row[5]))) != (
                npi, tin, address, code, specialty, Decimal(rate)):
                problems["workbook_csv_mismatch"] += 1
        result = {"candidate_rows": len(candidates), "unique_six_column_keys": len(seen),
                  "workbook_sheets": workbook.sheetnames, "problems": dict(problems),
                  "passed": not problems}
        if problems:
            raise AssertionError(json.dumps(result, indent=2))
        return result
    finally:
        workbook.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--c4-manifest", type=Path)
    parser.add_argument("--selected-rates", type=Path, action="append", default=[])
    parser.add_argument("--c5-locations", type=Path, required=True)
    parser.add_argument("--c5-evidence", type=Path, required=True)
    parser.add_argument("--candidate-csv", type=Path, required=True)
    parser.add_argument("--workbook", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = audit(selected_paths(args.c4_manifest, args.selected_rates), args.c5_locations,
                   args.c5_evidence, args.candidate_csv, args.workbook)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
