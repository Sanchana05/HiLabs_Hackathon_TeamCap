"""Build a reviewable six-column rate candidate file from corroborated CA sites.

The public MRF is linked to confirmed PPO plans but also non-PPO plans. CMS
permits shared files when negotiated data is common to the linked plans. These
rows are published PPO-linked candidates, not directory-verified PPO/site/TIN
contracts. The separately gated verified builder remains the strict export.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path

from pipeline.c5_address_mapper.resolve import selected_paths


RATE_COLUMNS = ("NPI", "TIN", "Address", "Billing Code", "Specialty", "Rate")
EVIDENCE_COLUMNS = RATE_COLUMNS + (
    "TIN Type", "Address Status", "TIN/Site Status", "PPO/Site Status",
    "Rate File Classification", "Rate Source URL", "Rate Source Locators",
    "Address Evidence", "Decision",
)
CA_ADDRESS = re.compile(r",\s*CA\s+\d{5}(?:-?\d{4})?\s*$", re.IGNORECASE)


def _rows(path: Path):
    with path.open(newline="", encoding="utf-8-sig") as stream:
        yield from csv.DictReader(stream)


def _write(path: Path, fields: tuple[str, ...], rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _ppo_linked_files(c2_manifest: Path, c4_paths: list[Path]) -> set[str]:
    """Require the same URL in the C2 PPO handoff and the C4 rate rows."""
    linked_urls = {r["rate_file_url"] for r in _rows(c2_manifest)
                   if int(r.get("target_confirmed_ppo_plans") or 0) > 0}
    if not linked_urls:
        raise ValueError("C2 has no confirmed California PPO plan/file link")
    selected: set[str] = set()
    for path in c4_paths:
        first = next(_rows(path), None)
        if first and first.get("source_url") in linked_urls:
            selected.add(first.get("source_file_id", ""))
    if not selected or "" in selected:
        raise ValueError("C4 selected rates do not match C2 confirmed PPO file URLs")
    return selected


def build_candidates(c4_paths: list[Path], c2_manifest: Path, c5_locations: Path,
                     c5_evidence: Path, output_dir: Path) -> dict:
    for path in (*c4_paths, c2_manifest, c5_locations, c5_evidence):
        if not path.is_file():
            raise FileNotFoundError(path)
    output_dir.mkdir(parents=True, exist_ok=True)
    linked_ids = _ppo_linked_files(c2_manifest, c4_paths)
    counts: Counter[str] = Counter()
    site_rows: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    all_sites: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    for site in _rows(c5_locations):
        key = (site["npi"], site["tin_type"], site["tin"])
        all_sites[key].append(site)
        if site["practice_site_status"] == "corroborated" and CA_ADDRESS.search(site["address"]):
            site_rows[key].append(site)
    observations = {row["id"]: row for row in _rows(c5_evidence)}
    npi_tins: dict[str, set[tuple[str, str]]] = defaultdict(set)
    grouped: dict[tuple[str, str, str, str], list[dict]] = defaultdict(list)
    for path in c4_paths:
        for rate in _rows(path):
            counts["selected_c4_rows"] += 1
            if rate.get("source_file_id") not in linked_ids:
                counts["not_c2_confirmed_ppo_linked"] += 1
                continue
            key = (rate["npi"], rate["tin_type"], rate["tin"])
            npi_tins[rate["npi"]].add(key[1:])
            grouped[key + (rate["billing_code"],)].append(rate)
    output_rows: list[dict] = []
    evidence_rows: list[dict] = []
    review_rows: list[dict] = []
    counts["six_column_code_groups"] = len(grouped)
    for key, rates in grouped.items():
        npi, kind, tin, code = key
        pair = key[:3]
        sites = site_rows.get(pair, [])
        reason = ""
        if len(npi_tins[npi]) != 1:
            reason = "MULTIPLE_TINS_FOR_NPI"
        elif len(sites) != 1:
            reason = "NO_SINGLE_CORROBORATED_CA_SITE" if not sites else "MULTIPLE_CORROBORATED_CA_SITES"
        elif len(all_sites.get(pair, [])) > 1:
            # Other NPPES-only sites remain plausible; the published rate has no POS address.
            reason = "ADDITIONAL_UNRESOLVED_SITE_CANDIDATES"
        elif len({r.get("billing_code_type", "") for r in rates}) != 1:
            reason = "MULTIPLE_CODE_TYPES_FOR_SIX_COLUMN_KEY"
        else:
            try:
                amounts = {Decimal(r["rate"]) for r in rates}
            except (InvalidOperation, KeyError):
                reason = "INVALID_RATE"
            else:
                if len(amounts) != 1:
                    reason = "MULTIPLE_RATES_FOR_SIX_COLUMN_KEY"
        if reason:
            counts[reason] += 1
            review_rows.append({"npi": npi, "tin_type": kind, "tin": tin,
                                "billing_code_type": ";".join(sorted({r.get("billing_code_type", "") for r in rates})),
                                "billing_code": code,
                                "c4_context_rows": len(rates), "reason": reason})
            continue
        site = sites[0]
        if not site["specialty"]:
            counts["MISSING_SPECIALTY"] += 1
            review_rows.append({"npi": npi, "tin_type": kind, "tin": tin,
                                "billing_code_type": rates[0].get("billing_code_type", ""),
                                "billing_code": code, "c4_context_rows": len(rates),
                                "reason": "MISSING_SPECIALTY"})
            continue
        amount = str(next(iter(amounts)))
        result = dict(zip(RATE_COLUMNS, (npi, tin, site["address"], code, site["specialty"], amount)))
        source_ids = site["source_ids"].split(";")
        sources = sorted({f"{observations[i]['source']} ({observations[i]['source_date']}): "
                          f"{observations[i]['source_ref']}" for i in source_ids if i in observations})
        detail = {
            **result, "TIN Type": kind, "Address Status": site["practice_site_status"],
            "TIN/Site Status": site["tin_link_status"],
            "PPO/Site Status": site["ppo_participation_status"],
            "Rate File Classification": rates[0].get("file_classification", ""),
            "Rate Source URL": rates[0].get("source_url", ""),
            "Rate Source Locators": "; ".join(sorted({r.get("source_locator", "") for r in rates})),
            "Address Evidence": "; ".join(sources),
            "Decision": "RESEARCH_CANDIDATE_NOT_DIRECTORY_VERIFIED",
        }
        output_rows.append(result)
        evidence_rows.append(detail)
        counts["exported_candidate_rows"] += 1
    output_rows.sort(key=lambda r: (r["NPI"], r["TIN"], r["Address"], r["Billing Code"]))
    evidence_rows.sort(key=lambda r: (r["NPI"], r["TIN"], r["Address"], r["Billing Code"]))
    _write(output_dir / "c6_supported_rate_candidates.csv", RATE_COLUMNS, output_rows)
    _write(output_dir / "c6_candidate_evidence.csv", EVIDENCE_COLUMNS, evidence_rows)
    (output_dir / "c6_candidate_evidence.json").write_text(
        json.dumps(evidence_rows, ensure_ascii=False), encoding="utf-8")
    _write(output_dir / "c6_candidate_review.csv",
           ("npi", "tin_type", "tin", "billing_code_type", "billing_code", "c4_context_rows", "reason"),
           review_rows)
    summary = {"counts": dict(counts), "c2_linked_source_file_ids": sorted(linked_ids),
               "status": "research_candidates; address independently corroborated, TIN/site and exact PPO/site unverified",
               "rule": "One TIN, one corroborated CA site and no alternate site for the NPI; one published rate per six-column key. Shared MRF linkage supports PPO rate candidacy, not a direct directory or TIN/site assertion."}
    (output_dir / "c6_candidate_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--c4-manifest", type=Path)
    parser.add_argument("--selected-rates", type=Path, action="append", default=[])
    parser.add_argument("--c2-manifest", type=Path, required=True)
    parser.add_argument("--c5-locations", type=Path, required=True)
    parser.add_argument("--c5-evidence", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build_candidates(selected_paths(args.c4_manifest, args.selected_rates),
                                      args.c2_manifest, args.c5_locations, args.c5_evidence,
                                      args.output_dir), indent=2))


if __name__ == "__main__":
    main()
