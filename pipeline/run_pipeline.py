"""Master Pipeline Runner for Centene Price Transparency Data (PTD) Curation.
Orchestrates Challenges C1 through C7 and produces all official competition deliverables:
- Deliverable 1: Rate file (Excel) [NPI, TIN, Address, Billing Code, Specialty, Rate]
- Deliverable 2: Logic file (Markdown) [PPO network ID + TIN/NPI/Address mapping]
- Deliverable 3: File quality metrics (Markdown + CSV) [C3 7-Metric Scoring]
- Deliverable 4: Summary file (JSON + Markdown) [High-level execution metrics]
- Deliverable 7: Cost effectiveness benchmarking (C7)
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

# Dynamic path resolution to ensure zero hardcoded paths
CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.c1_index_parser.index_parser import CenteneIndexParser
from pipeline.c2_network_mapper.network_classifier import NetworkClassifier
from pipeline.c3_file_grader.file_grader import FileQualityGrader, write_reports
from pipeline.c4_rate_extractor.rate_extractor import RateFileInput, run_files
from pipeline.c5_address_mapper.resolve import run_c5
from pipeline.c6_rate_builder.verified_builder import build_verified_rates
from pipeline.c6_rate_builder.candidate_builder import build_candidates
from pipeline.c6_rate_builder.candidate_workbook import write_candidate_workbook
from pipeline.c7_cost_effectiveness.cost_effectiveness import CostEffectivenessEngine
from pipeline.config import (
    BENCHMARK_CODES,
    DATA_DIR,
    DELIVERABLES_DIR,
    DOCS_DIR,
    RATEFILES_DIR,
    RAW_INDEX_DIR,
    REPO_ROOT,
    SEARCH_DIRECTORIES,
    TARGET_SNAPSHOT_DATE,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("PTD_Master_Pipeline")


def run_pipeline(
    index_files: Optional[List[Path]] = None,
    rate_files: Optional[List[Path]] = None,
    nppes_file: Optional[Path] = None,
    nppes_secondary: Optional[Path] = None,
    nppes_monthly_through: Optional[date] = None,
    nppes_weekly_main: Optional[Path] = None,
    nppes_weekly_secondary: Optional[Path] = None,
    nppes_weekly_through: Optional[date] = None,
    nppes_deactivations: Optional[Path] = None,
    taxonomy_file: Optional[Path] = None,
    cms_clinicians_file: Optional[Path] = None,
    cms_snapshot: Optional[date] = None,
    payer_directory_file: Optional[Path] = None,
    payer_snapshot: Optional[date] = None,
    provider_roster_file: Optional[Path] = None,
    roster_snapshot: Optional[date] = None,
    ppo_directory_plans: Optional[List[str]] = None,
    ppo_rate_attributions: Optional[List[str]] = None,
    output_dir: Optional[Path] = None,
    limit_codes: bool = True,
    as_of: Optional[date] = None,
    c3_benchmark_csv: Optional[Path] = None,
    c3_expected_npis_csv: Optional[Path] = None,
) -> Dict:
    """Executes the full end-to-end PTD curation pipeline."""
    start_time = datetime.now(timezone.utc)
    run_as_of = as_of or date.today()
    out_dir = output_dir or DELIVERABLES_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    summary_metrics = {
        "execution_start_utc": start_time.isoformat(),
        "challenges_executed": ["C1", "C2", "C3", "C4"],
        "index_files_parsed_count": 0,
        "raw_plan_records_count": 0,
        "deduplicated_plans_count": 0,
        "ppo_plans_identified_count": 0,
        "ppo_rate_files_identified_count": 0,
        "file_quality_scores": {},
        "raw_rates_extracted_count": 0,
        "curated_rates_count": 0,
        "unique_npis_count": 0,
        "unique_tins_count": 0,
        "unique_addresses_count": 0,
        "share_npis_verified_address": 0.0,
        "share_npis_corroborated_site": 0.0,
        "share_npis_confirmed_ppo_site": 0.0,
        "downstream_validation_status": "C5 requires explicit NPPES files; no synthetic provider or address evidence is used.",
        "deliverables_generated": []
    }

    # =========================================================================
    # CHALLENGE C1: Parse Index Files & Deduplicate
    # =========================================================================
    logger.info(">>> STEP 1: Ingesting and Parsing Centene Index Files (Challenge C1)...")
    parser = CenteneIndexParser()

    local_indexes = index_files or parser.discover_local_index_files()
    if not local_indexes:
        # Search parent repository for any index files
        for search_path in SEARCH_DIRECTORIES:
            local_indexes.extend(list(search_path.glob("*index*.json")))
        local_indexes = sorted(set(p.resolve() for p in local_indexes if p.is_file()))

    if not local_indexes:
        logger.warning("No local index files found; discovering online indexes...")
        discovered_urls = parser.discover_official_index_urls()
        for u in discovered_urls:
            parser.parse_index_file(u)
    else:
        for idx_path in local_indexes:
            parser.parse_index_file(idx_path)

    summary_metrics["index_files_parsed_count"] = len(parser.index_inventories)
    summary_metrics["raw_plan_records_count"] = len(parser.raw_records)

    c1_dedup_df = parser.build_deduplicated_plan_table()
    summary_metrics["deduplicated_plans_count"] = len(c1_dedup_df)
    c1_dedup_path = out_dir / "centene_c1_deduplicated_plans.csv"
    c1_dedup_df.to_csv(c1_dedup_path, index=False)
    summary_metrics["deliverables_generated"].append(str(c1_dedup_path.name))

    # =========================================================================
    # CHALLENGE C2: Find PPO Network (Rule out HMO, EPO, POS)
    # =========================================================================
    logger.info(">>> STEP 2: Isolating PPO Network & Ruling Out HMO/EPO/POS (Challenge C2)...")
    classifier = NetworkClassifier()
    classified_df = classifier.classify_dataset(c1_dedup_df)

    ppo_files_df = classifier.extract_ppo_network_files(classified_df)
    summary_metrics["confirmed_ppo_count"] = int((classified_df["product_status"] == "CONFIRMED_PPO").sum())
    summary_metrics["provisional_ppo_count"] = int((classified_df["product_status"] == "PROVISIONAL_PPO").sum())
    summary_metrics["ppo_plans_identified_count"] = summary_metrics["confirmed_ppo_count"] + summary_metrics["provisional_ppo_count"]
    summary_metrics["excluded_non_ppo_count"] = int((classified_df["product_status"] == "EXCLUDED_NON_PPO").sum())
    summary_metrics["out_of_scope_count"] = int((classified_df["product_status"] == "OUT_OF_SCOPE").sum())
    summary_metrics["unresolved_count"] = int((classified_df["product_status"] == "UNRESOLVED").sum())
    summary_metrics["ppo_rate_files_identified_count"] = len(ppo_files_df)
    target_decisions = classified_df[classified_df["downstream_target"]]
    summary_metrics["target_confirmed_ppo_count"] = int(target_decisions["product_status"].eq("CONFIRMED_PPO").sum())
    summary_metrics["target_provisional_ppo_count"] = int(target_decisions["product_status"].eq("PROVISIONAL_PPO").sum())
    summary_metrics["eoa_overlap_count"] = int(classified_df["anomaly_tags"].str.contains("EOA_OVERLAP_SENSITIVITY").sum())
    summary_metrics["collapsed_token_count"] = int(classified_df["anomaly_tags"].str.contains("COLLAPSED_TOKEN_CUSPPO").sum())
    summary_metrics["retiree_review_count"] = int(classified_df["anomaly_tags"].str.contains("RETIREE_OR_PUBLIC_WORD").sum())

    # Save Plan Decisions, File Manifest, and Review Queue (Plan Step 5-7)
    dec_path = out_dir / "plan_decisions.csv"
    classified_df.to_csv(dec_path, index=False)
    summary_metrics["deliverables_generated"].append(str(dec_path.name))

    manifest_path = out_dir / "file_manifest.csv"
    ppo_files_df.to_csv(manifest_path, index=False)
    summary_metrics["deliverables_generated"].append(str(manifest_path.name))

    review_queue_df = classified_df[classified_df["product_status"].isin(["PROVISIONAL_PPO", "UNRESOLVED"])].copy()
    review_queue_path = out_dir / "review_queue.csv"
    review_queue_df.to_csv(review_queue_path, index=False)
    summary_metrics["deliverables_generated"].append(str(review_queue_path.name))

    ppo_plans_path = out_dir / "centene_c2_ppo_network_plans.csv"
    classified_df[classified_df["product_status"].isin(["CONFIRMED_PPO", "PROVISIONAL_PPO"])].to_csv(ppo_plans_path, index=False)
    summary_metrics["deliverables_generated"].append(str(ppo_plans_path.name))

    ppo_files_summary_path = out_dir / "centene_c2_ppo_rate_files.csv"
    ppo_files_df.to_csv(ppo_files_summary_path, index=False)
    summary_metrics["deliverables_generated"].append(str(ppo_files_summary_path.name))

    # C3 operates on each entire MRF before C4's code filter or rate selection.
    logger.info(">>> STEP 3: Grading complete rate files (Challenge C3)...")
    supplied = {Path(p).name: Path(p) for p in (rate_files or [])}
    selected_files = []
    names_to_urls = {}
    for _, file_row in ppo_files_df.iterrows():
        name = str(file_row["rate_file_name"])
        url = str(file_row["rate_file_url"])
        if name in names_to_urls and names_to_urls[name] != url:
            raise ValueError(f"Two rate URLs share filename {name}; provide a URL-to-local-path manifest")
        names_to_urls[name] = url
        candidates = [supplied[name]] if name in supplied else [
            folder / name for folder in SEARCH_DIRECTORIES
        ]
        local = next((p for p in candidates if p.is_file()), None)
        if local is None:
            raise FileNotFoundError(f"C3 requires complete local rate file: {name}")
        selected_files.append((local, file_row))
    if not selected_files:
        raise RuntimeError("No PPO-linked files selected for C3")
    grader = FileQualityGrader(c3_benchmark_csv, c3_expected_npis_csv)
    index_date = max((str(i.get("last_updated_on", "")) for i in parser.index_inventories), default="")
    quality_results = [
        grader.grade_file(path, source_url=str(row["rate_file_url"]),
                          index_last_updated=index_date, as_of=run_as_of,
                          file_classification=str(row["file_classification"]), scratch_dir=out_dir)
        for path, row in selected_files
    ]
    write_reports(quality_results, out_dir)
    summary_metrics["file_quality_scores"] = {
        result["source_url"]: {"composite_fqs": result["composite_fqs"],
                               "grade": result["grade"], "status": result["status"]}
        for result in quality_results
    }
    summary_metrics["deliverables_generated"].extend(
        ["file_quality_scorecard.csv", "file_quality_details.json"])

    logger.info(">>> STEP 4: Validating and selecting rates from complete files (Challenge C4)...")
    quality_by_url = {result["source_url"]: result for result in quality_results}
    c4_inputs = [RateFileInput(
        path=path, source_url=str(row["rate_file_url"]),
        file_classification=str(row["file_classification"]),
        expected_sha256=quality_by_url[str(row["rate_file_url"])]["sha256"],
        c3_quality_status=quality_by_url[str(row["rate_file_url"])]["quality_status"],
    ) for path, row in selected_files]
    c4_results = run_files(c4_inputs, out_dir / "c4", as_of=run_as_of)
    summary_metrics["c4_file_summaries"] = c4_results
    summary_metrics["raw_rates_extracted_count"] = sum(r["counts"].get("expanded_rate_rows", 0) for r in c4_results)
    summary_metrics["curated_rates_count"] = sum(r["counts"].get("selected", 0) for r in c4_results)
    summary_metrics["deliverables_generated"].append("c4/c4_manifest.csv")

    selected_rate_paths = [out_dir / "c4" / r["source_file_id"] / "selected_rates.csv" for r in c4_results]
    if nppes_file or nppes_secondary or nppes_monthly_through:
        if not nppes_file or not nppes_secondary or not nppes_monthly_through:
            raise ValueError("C5 requires NPPES main, secondary, and monthly-through date together")
        logger.info(">>> STEP 5: Mapping C4 NPI/TIN pairs to sourced practice sites (Challenge C5)...")
        c5_dir = out_dir / "c5"
        c5_summary = run_c5(
            selected_rates=selected_rate_paths,
            nppes_main=nppes_file, nppes_secondary=nppes_secondary,
            monthly_through=nppes_monthly_through,
            weekly_main=nppes_weekly_main, weekly_secondary=nppes_weekly_secondary,
            weekly_through=nppes_weekly_through, deactivations=nppes_deactivations,
            nucc=taxonomy_file, cms=cms_clinicians_file,
            payer_directory=payer_directory_file, provider_roster=provider_roster_file,
            cms_snapshot=cms_snapshot, payer_snapshot=payer_snapshot,
            roster_snapshot=roster_snapshot,
            ppo_plans=ppo_directory_plans or [], as_of=run_as_of, output_dir=c5_dir,
        )
        summary_metrics["challenges_executed"].append("C5")
        summary_metrics["c5_summary"] = c5_summary
        summary_metrics["unique_npis_count"] = c5_summary["unique_npis"]
        summary_metrics["unique_tins_count"] = c5_summary["unique_tins"]
        summary_metrics["unique_addresses_count"] = c5_summary["unique_physical_addresses"]
        summary_metrics["share_npis_verified_address"] = c5_summary["share_npis_with_fully_verified_link"]
        summary_metrics["share_npis_corroborated_site"] = c5_summary["share_npis_with_corroborated_site"]
        summary_metrics["share_npis_confirmed_ppo_site"] = c5_summary["share_npis_with_confirmed_ppo_site"]
        summary_metrics["deliverables_generated"].extend(f"c5/{name}" for name in c5_summary["outputs"])
        logger.info(">>> STEP 6: Projecting only fully evidenced PPO sites and attributable rates (Challenge C6)...")
        c6_summary = build_verified_rates(
            selected_rate_paths, c5_dir / "c5_provider_locations.csv", out_dir / "c6",
            allowed_plan_attributions=set(ppo_rate_attributions or []),
        )
        summary_metrics["challenges_executed"].append("C6")
        summary_metrics["c6_summary"] = c6_summary
        summary_metrics["deliverables_generated"].extend(f"c6/{name}" for name in c6_summary["outputs"])
        candidate_summary = build_candidates(
            selected_rate_paths, manifest_path, c5_dir / "c5_provider_locations.csv",
            c5_dir / "c5_evidence.csv", out_dir / "c6",
        )
        summary_metrics["c6_candidate_summary"] = candidate_summary
        workbook = write_candidate_workbook(
            out_dir / "c6", out_dir / "Centene_CA_Commercial_PPO_Rate_Candidates.xlsx")
        summary_metrics["deliverables_generated"].append(workbook.name)
        summary_metrics["deliverables_generated"].extend(
            f"c6/{name}" for name in (
                "c6_supported_rate_candidates.csv", "c6_candidate_evidence.csv",
                "c6_candidate_evidence.json", "c6_candidate_review.csv",
                "c6_candidate_summary.json"))
        summary_metrics["downstream_validation_status"] = (
            "C5/C6 use sourced evidence. Strict verified rates require exact PPO and TIN/site proof; "
            "separate research candidates have corroborated addresses but require directory/roster review."
        )
        if 0 < c6_summary["counts"].get("exported_rate_rows", 0) <= 250_000:
            final_rate_df = pd.read_csv(out_dir / "c6" / "c6_verified_rates.csv", dtype={"NPI": str, "TIN": str})
            cost_df = CostEffectivenessEngine().evaluate_cost_effectiveness(final_rate_df)
            cost_path = out_dir / "provider_cost_effectiveness_benchmark.csv"
            cost_df.to_csv(cost_path, index=False)
            summary_metrics["challenges_executed"].append("C7")
            summary_metrics["deliverables_generated"].append(cost_path.name)
    else:
        logger.warning("C5 skipped: supply NPPES main/secondary files and snapshot date; no address or PPO rate deliverable is fabricated")

    # =========================================================================
    # GENERATE MASTER DELIVERABLES: Logic File & Summary File
    # =========================================================================
    logger.info(">>> STEP 8: Writing Master Deliverable Markdown and Summary Files...")

    # Write Deliverable 4: Summary Metrics (JSON & Markdown)
    end_time = datetime.now(timezone.utc)
    summary_metrics["execution_end_utc"] = end_time.isoformat()
    summary_metrics["duration_seconds"] = round((end_time - start_time).total_seconds(), 2)

    summary_json_path = out_dir / "Summary_Metrics.json"
    summary_metrics["deliverables_generated"].append(summary_json_path.name)

    c4_classifications = ", ".join(sorted({r["file_classification"] for r in c4_results}))
    c4_attributions = ", ".join(sorted({r["plan_attribution"] for r in c4_results}))

    summary_md_content = f"""# Executive Run Summary: Centene CA Commercial PPO Rate Curation
**Pursuant to Centene California Commercial-Group PPO Classification Plan**

**Validation scope:** C2 classifies the supplied indexes; C3/C4 audit complete selected MRFs. A PPO-linked shared MRF does not establish provider membership or PPO-specific rates. C5 runs only when real NPPES inputs are supplied and reports evidence statuses separately. C6 exports only rows meeting the exact PPO site, direct TIN/site, and attributable-rate gates; withheld rows remain auditable.

- **Execution Date**: {start_time.strftime('%Y-%m-%d %H:%M:%S UTC')}
- **Target Snapshot Date**: {TARGET_SNAPSHOT_DATE}
- **Target Payer**: Centene / Health Net (index issuer: Healthnet, LLC)
- **Target Market**: Commercial Group, California (CA)
- **Target Network**: Health Net Full Network PPO

## High-Level Execution Metrics (Deliverable 4)

| Metric Category | Metric Name | Measured Value | Plan Reference |
| :--- | :--- | :--- | :--- |
| **C1: Index Inventory** | Index Files Successfully Parsed | {summary_metrics['index_files_parsed_count']} | All Centene brand indexes (Health Net, Ambetter, Fidelis, QualChoice) |
| | Raw Plan Records Discovered | {summary_metrics['raw_plan_records_count']} | Full reporting structure edges |
| | Unique Plan-File Edges | {summary_metrics['deduplicated_plans_count']} | Deduplicated on brand/name/id/id-type/market/url |
| **C2: Network Decisions** | **Confirmed PPO plan-file edges across all brands** | **{summary_metrics.get('confirmed_ppo_count', 0)}** | Exact 2026 EOC or CMS plan-attribute match |
| | **Provisional PPO plan-file edges across all brands** | **{summary_metrics.get('provisional_ppo_count', 0)}** | Explicit PPO token without an exact matching authority |
| | **Health Net CA group PPO handoff edges** | **{summary_metrics['target_confirmed_ppo_count']} confirmed; {summary_metrics['target_provisional_ppo_count']} provisional** | Only these PPO-linked files enter C3/C4 |
| | **PPO-Labeled Candidate Edges** | **{summary_metrics['ppo_plans_identified_count']}** | Confirmed + provisional; not a unique-product count |
| | Explicit Non-PPO Labels | {summary_metrics.get('excluded_non_ppo_count', 0)} | HMO, EPO, POS, or EOA token; no inferred contract model |
| | Out-of-Scope Edges | {summary_metrics.get('out_of_scope_count', 0)} | Invalid provenance or index date; geography and market are classified in C2 |
| | EOA Overlap Sensitivity Cohort | {summary_metrics.get('eoa_overlap_count', 127)} | Exclusive Option Advantage (HMO with PPO tier; flagged for sensitivity) |
| | Collapsed Token Anomaly (CUSPPO) | {summary_metrics.get('collapsed_token_count', 1)} | Recovered via regex punctuation tokenization (`CA L CUSPPO`) |
| | Retiree / Government Review Queue | {summary_metrics.get('retiree_review_count', 1)} | Flagged for active commercial group employment eligibility audit |
| | Unresolved Edges | {summary_metrics.get('unresolved_count', 0)} | Review queue also includes provisional PPO edges |
| **C2: Rate File Attribution** | Distinct Rate Files Referenced | {summary_metrics['ppo_rate_files_identified_count']} | See `file_manifest.csv` |
| | **Rate File Classification** | **{c4_classifications}** | From the C2 file manifest; not provider-level membership proof |
| | **Plan Attribution Limitation** | **{c4_attributions}** | Source-file rows retain their attribution status |
| **C3: File Quality** | **Complete-file grades** | **{', '.join(f"{r['file_name']}: {r['composite_fqs'] if r['composite_fqs'] is not None else 'not graded'} ({r['grade']})" for r in quality_results)}** | See per-file counts and limitations in file_quality_details.json |
| **C4: Rates Curation** | Expanded Rate Rows Audited | {summary_metrics['raw_rates_extracted_count']:,} | Complete selected MRFs; all decisions in `c4/` |
| | Selected Direct Professional FFS Rates | {summary_metrics['curated_rates_count']:,} | Actual lower-median published rate per exact service context; alternatives preserved |
| **C5: Address Resolution** | Unique C4 NPIs evaluated | {summary_metrics['unique_npis_count']:,} | Source-file providers; PPO membership assessed separately |
| | Unique C4 TINs evaluated | {summary_metrics['unique_tins_count']:,} | TIN/site relationship requires direct evidence |
| | Unique physical address candidates | {summary_metrics['unique_addresses_count']:,} | Format-filtered candidates, not automatically verified |
| | NPIs with a corroborated practice site | {summary_metrics['share_npis_corroborated_site']}% | Independent or direct practice-site evidence |
| | **NPIs with verified NPI/TIN/PPO site link** | **{summary_metrics['share_npis_verified_address']}%** | Direct TIN/site and exact PPO/site evidence both required |
| **C6: Research candidates** | Six-column published-rate candidate rows | {summary_metrics.get('c6_candidate_summary', {}).get('counts', {}).get('exported_candidate_rows', 0):,} | One TIN, one corroborated CA site, one unambiguous rate; exact PPO/site and TIN/site unverified |

## Deliverables & Audit Files Generated

1. `c6/Centene_CA_Commercial_PPO_Provider_Rates.xlsx` if C5 inputs are supplied (strict verified rate file; may have zero rows)
2. `Centene_CA_Commercial_PPO_Rate_Candidates.xlsx`, `c6/c6_supported_rate_candidates.csv`, and `c6/c6_candidate_evidence.csv` (research candidates and row-level provenance)
3. `Logic_File.md` (Deliverable 2: Logic for Network ID and Address Mapping)
4. `File_Quality_Metrics.md` & `file_quality_scorecard.csv` (Deliverable 3: Quality Metrics & Scores)
5. `Summary_Metrics.json` & `Summary_Metrics.md` (Deliverable 4: Summary Metrics)
6. `plan_decisions.csv` (C2 Plan Decisions with Product and Network Statuses)
7. `file_manifest.csv` (C2 Rate File Manifest with MIXED classification)
8. `review_queue.csv` (C2 Unresolved Review Queue)
9. `provider_cost_effectiveness_benchmark.csv` only when verified C6 rows are available (Deliverable 7)
10. `c4/c4_manifest.csv` and per-file C4 audit CSVs (complete source-file rate extraction)
11. `c5/c5_provider_locations.csv`, `c5/c5_evidence.csv`, `c5/c5_review_queue.csv`, and `c5/c5_summary.json` when C5 is run
"""
    summary_md_path = out_dir / "Summary_Metrics.md"
    summary_md_path.write_text(summary_md_content, encoding="utf-8")
    summary_metrics["deliverables_generated"].append(summary_md_path.name)

    # Synthesize Master Deliverable 2: Logic File
    logic_file_path = out_dir / "Logic_File.md"
    c1_c2_doc = (PROJECT_ROOT / "docs" / "C1_C2_METHODOLOGY_AND_LOGIC.md").read_text(encoding="utf-8")
    c4_doc = (PROJECT_ROOT / "docs" / "C4_RATE_EXTRACTION_LOGIC.md").read_text(encoding="utf-8")
    c5_doc = (PROJECT_ROOT / "docs" / "C5_ADDRESS_MAPPING_LOGIC.md").read_text(encoding="utf-8")

    master_logic_content = f"""# Master Logic File: Centene Commercial California PPO Rate Curation
**Official Hackathon Deliverable 2**

This document establishes the end-to-end logic for:
1. **Part A: Identifying the PPO Network and Ruling Out HMO, EPO, and POS (Challenges C1 & C2)**
2. **Part B: Resolving Provider Rates and Multi-Rate Conflicts (Challenge C4)**
3. **Part C: Triangulating TINs, NPIs, and Stale Addresses via Network Consensus (Challenge C5)**

---

{c1_c2_doc}

---

{c4_doc}

---

{c5_doc}
"""
    logic_file_path.write_text(master_logic_content, encoding="utf-8")
    summary_metrics["deliverables_generated"].append(logic_file_path.name)

    # Copy Deliverable 3: File Quality Metrics
    d3_doc = (PROJECT_ROOT / "docs" / "C3_FILE_QUALITY_METRICS.md").read_text(encoding="utf-8")
    (out_dir / "File_Quality_Metrics.md").write_text(d3_doc, encoding="utf-8")
    summary_metrics["deliverables_generated"].append("File_Quality_Metrics.md")

    with summary_json_path.open("w", encoding="utf-8") as stream:
        json.dump(summary_metrics, stream, indent=2)

    logger.info(">>> PIPELINE COMPLETED SUCCESSFULLY! All deliverables written to %s", out_dir)
    return summary_metrics


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Master PTD Curation Pipeline")
    parser.add_argument("--index", type=Path, action="append", help="Path to local index JSON file (repeatable)")
    parser.add_argument("--rate-file", type=Path, action="append", help="Path to local in-network rate file")
    parser.add_argument("--nppes", type=Path, help="NPPES V2 monthly main CSV")
    parser.add_argument("--nppes-secondary", type=Path, help="NPPES V2 monthly non-primary practice locations CSV")
    parser.add_argument("--nppes-monthly-through", type=date.fromisoformat, help="NPPES monthly snapshot through date")
    parser.add_argument("--nppes-weekly-main", type=Path)
    parser.add_argument("--nppes-weekly-secondary", type=Path)
    parser.add_argument("--nppes-weekly-through", type=date.fromisoformat)
    parser.add_argument("--nppes-deactivations", type=Path)
    parser.add_argument("--nucc", type=Path, help="NUCC taxonomy CSV")
    parser.add_argument("--cms-clinicians", type=Path, help="Dated CMS Doctors and Clinicians CSV")
    parser.add_argument("--cms-snapshot", type=date.fromisoformat, help="Publication date if CMS CSV rows lack source_date")
    parser.add_argument("--payer-directory", type=Path, help="Dated, plan-filtered Health Net evidence CSV")
    parser.add_argument("--payer-snapshot", type=date.fromisoformat, help="Directory snapshot date if CSV rows lack source_date")
    parser.add_argument("--provider-roster", type=Path, help="Dated, provider/group-confirmed evidence CSV")
    parser.add_argument("--roster-snapshot", type=date.fromisoformat, help="Roster snapshot date if CSV rows lack source_date")
    parser.add_argument("--ppo-directory-plan", action="append", help="Exact plan/network name in payer-directory evidence")
    parser.add_argument("--ppo-rate-attribution", action="append", help="Explicit C4 plan_attribution accepted for C6")
    parser.add_argument("--output-dir", type=Path, default=DELIVERABLES_DIR, help="Deliverables output directory")
    parser.add_argument("--all-codes", action="store_true", help="Legacy option; C4 always processes all codes")
    parser.add_argument("--as-of", type=date.fromisoformat, help="C3/C4 reference date (YYYY-MM-DD)")
    parser.add_argument("--c3-benchmark-csv", type=Path, help="C3 weighted expected billing-code panel")
    parser.add_argument("--c3-expected-npis-csv", type=Path, help="Verified PPO roster with npi column")
    args = parser.parse_args()

    run_pipeline(
        index_files=args.index,
        rate_files=args.rate_file,
        nppes_file=args.nppes,
        nppes_secondary=args.nppes_secondary,
        nppes_monthly_through=args.nppes_monthly_through,
        nppes_weekly_main=args.nppes_weekly_main,
        nppes_weekly_secondary=args.nppes_weekly_secondary,
        nppes_weekly_through=args.nppes_weekly_through,
        nppes_deactivations=args.nppes_deactivations,
        taxonomy_file=args.nucc,
        cms_clinicians_file=args.cms_clinicians,
        cms_snapshot=args.cms_snapshot,
        payer_directory_file=args.payer_directory,
        payer_snapshot=args.payer_snapshot,
        provider_roster_file=args.provider_roster,
        roster_snapshot=args.roster_snapshot,
        ppo_directory_plans=args.ppo_directory_plan,
        ppo_rate_attributions=args.ppo_rate_attribution,
        output_dir=args.output_dir,
        limit_codes=not args.all_codes,
        as_of=args.as_of,
        c3_benchmark_csv=args.c3_benchmark_csv,
        c3_expected_npis_csv=args.c3_expected_npis_csv,
    )
