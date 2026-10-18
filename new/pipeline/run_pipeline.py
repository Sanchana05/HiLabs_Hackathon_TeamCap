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
NEW_DIR = CURRENT_DIR.parent
if str(NEW_DIR) not in sys.path:
    sys.path.insert(0, str(NEW_DIR))

from pipeline.c1_index_parser.index_parser import CenteneIndexParser
from pipeline.c2_network_mapper.network_classifier import NetworkClassifier
from pipeline.c3_file_grader.file_grader import FileQualityGrader, write_reports
from pipeline.c4_rate_extractor.rate_extractor import RateFileInput, run_files
from pipeline.c5_address_mapper.address_normalizer import AddressNormalizer
from pipeline.c5_address_mapper.nppes_taxonomy_resolver import NPPESTaxonomyResolver
from pipeline.c5_address_mapper.tin_address_clusterer import TINAddressClusterer
from pipeline.c6_rate_builder.rate_builder import ProviderRateFileBuilder
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
    taxonomy_file: Optional[Path] = None,
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
        "challenges_executed": ["C1", "C2", "C3", "C4", "C5", "C6", "C7"],
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
        "downstream_validation_status": "C4 audits full selected files; C5 currently uses synthetic address seed rows. C5-C7 are demonstration outputs.",
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

    # Also mirror to outputs/ppo for standalone compatibility
    ppo_out_dir = NEW_DIR / "outputs" / "ppo"
    ppo_out_dir.mkdir(parents=True, exist_ok=True)
    classified_df.to_csv(ppo_out_dir / "plan_decisions.csv", index=False)
    ppo_files_df.to_csv(ppo_out_dir / "file_manifest.csv", index=False)
    review_queue_df.to_csv(ppo_out_dir / "review_queue.csv", index=False)

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

    # Legacy C5-C7 operate on a bounded demonstration sample only. C4 files above
    # remain complete and independent of this sample.
    demo_path = out_dir / "c4" / c4_results[0]["source_file_id"] / "selected_rates.csv"
    curated_rates_df = pd.read_csv(demo_path, dtype={"npi": str, "tin": str}, nrows=10_000)
    curated_rates_df["service_codes"] = curated_rates_df["service_code"].fillna("")
    curated_rates_df["selection_rationale"] = curated_rates_df["decision_reason"]
    summary_metrics["downstream_demo_rows_count"] = len(curated_rates_df)

    # =========================================================================
    # CHALLENGE C5: Address & Specialty Mapping (TIN Consensus + NUCC)
    # =========================================================================
    logger.info(">>> STEP 5: Mapping NPI/TIN to Practicing Address & Specialty (Challenge C5)...")
    nppes_resolver = NPPESTaxonomyResolver(taxonomy_dir=DATA_DIR / "nucc_taxonomy")
    tin_clusterer = TINAddressClusterer()

    # Pre-register candidate addresses for active providers
    address_specialty_map = {}
    unique_npis = curated_rates_df["npi"].unique()
    unique_tins = curated_rates_df["tin"].unique()

    # Example seed registry for demonstration and testing
    sample_nppes_db = {
        "1234567890": {
            "NPI": "1234567890", "Entity Type Code": "1",
            "Provider First Name": "Sarah", "Provider Last Name (Legal Name)": "Lin",
            "Provider Credential Text": "MD", "Healthcare Provider Taxonomy Code_1": "207Q00000X",
            "Provider First Line Business Practice Location Address": "100 MEDICAL CENTER DR",
            "Provider Second Line Business Practice Location Address": "STE 300",
            "Provider Business Practice Location Address City Name": "LOS ANGELES",
            "Provider Business Practice Location Address State Name": "CA",
            "Provider Business Practice Location Address Postal Code": "90024"
        },
        "1987654321": {
            "NPI": "1987654321", "Entity Type Code": "1",
            "Provider First Name": "David", "Provider Last Name (Legal Name)": "Miller",
            "Provider Credential Text": "DO", "Healthcare Provider Taxonomy Code_1": "207R00000X",
            "Provider First Line Business Practice Location Address": "200 MERCY WAY",
            "Provider Business Practice Location Address City Name": "SACRAMENTO",
            "Provider Business Practice Location Address State Name": "CA",
            "Provider Business Practice Location Address Postal Code": "95819"
        },
        "1456789012": {
            "NPI": "1456789012", "Entity Type Code": "1",
            "Provider First Name": "Robert", "Provider Last Name (Legal Name)": "Chen",
            "Provider Credential Text": "MD", "Healthcare Provider Taxonomy Code_1": "2085R0202X",
            "Provider First Line Business Practice Location Address": "500 PASTEUR DR",
            "Provider Business Practice Location Address City Name": "STANFORD",
            "Provider Business Practice Location Address State Name": "CA",
            "Provider Business Practice Location Address Postal Code": "94305"
        }
    }

    # Register in TIN Consensus Graph
    for _, r in curated_rates_df.iterrows():
        npi = str(r["npi"])
        tin = str(r["tin"])
        raw_nppes = sample_nppes_db.get(npi, {
            "NPI": npi, "Entity Type Code": "1",
            "Healthcare Provider Taxonomy Code_1": "207Q00000X",
            "Provider First Line Business Practice Location Address": "1200 WILSHIRE BLVD STE 400",
            "Provider Business Practice Location Address City Name": "LOS ANGELES",
            "Provider Business Practice Location Address State Name": "CA",
            "Provider Business Practice Location Address Postal Code": "90017"
        })
        parsed_rec = nppes_resolver.parse_nppes_provider_record(raw_nppes)
        tin_clusterer.register_provider_address(tin=tin, npi=npi, address_dict=parsed_rec)

    # Disambiguate and assign highest-confidence physical address
    verified_address_count = 0
    for _, r in curated_rates_df.iterrows():
        npi = str(r["npi"])
        tin = str(r["tin"])
        key = (npi, tin)
        if key not in address_specialty_map:
            raw_nppes = sample_nppes_db.get(npi, {
                "NPI": npi, "Entity Type Code": "1",
                "Healthcare Provider Taxonomy Code_1": "207Q00000X",
                "Provider First Line Business Practice Location Address": "1200 WILSHIRE BLVD STE 400",
                "Provider Business Practice Location Address City Name": "LOS ANGELES",
                "Provider Business Practice Location Address State Name": "CA",
                "Provider Business Practice Location Address Postal Code": "90017"
            })
            parsed_rec = nppes_resolver.parse_nppes_provider_record(raw_nppes)
            best_match = tin_clusterer.resolve_best_address_for_provider(
                tin=tin, npi=npi, candidate_addresses=[parsed_rec]
            )
            address_specialty_map[key] = best_match
            if best_match["confidence_tier"] in ("HIGH", "MODERATE"):
                verified_address_count += 1

    summary_metrics["unique_npis_count"] = len(unique_npis)
    summary_metrics["unique_tins_count"] = len(unique_tins)
    summary_metrics["unique_addresses_count"] = len(set(v["address"] for v in address_specialty_map.values()))
    summary_metrics["share_npis_verified_address"] = round(verified_address_count / max(1, len(address_specialty_map)) * 100.0, 2)

    # =========================================================================
    # CHALLENGE C6: Build Deliverable 1 Rate File (Excel)
    # =========================================================================
    logger.info(">>> STEP 6: Building Final Provider Rate File Deliverable (Challenge C6)...")
    builder = ProviderRateFileBuilder(deliverables_dir=out_dir)
    final_rate_df = builder.assemble_final_dataset(
        curated_rates_df=curated_rates_df,
        address_specialty_map=address_specialty_map
    )
    excel_path = builder.export_deliverable_excel(
        final_df=final_rate_df,
        filename="Centene_CA_Commercial_PPO_Provider_Rates.xlsx"
    )
    summary_metrics["deliverables_generated"].append(excel_path.name)

    # =========================================================================
    # CHALLENGE C7: Cost Effectiveness Benchmarking (Brownie Points)
    # =========================================================================
    logger.info(">>> STEP 7: Computing Cost Effectiveness Metrics (Challenge C7)...")
    cost_engine = CostEffectivenessEngine()
    cost_df = cost_engine.evaluate_cost_effectiveness(final_rate_df)
    cost_path = out_dir / "provider_cost_effectiveness_benchmark.csv"
    cost_df.to_csv(cost_path, index=False)
    summary_metrics["deliverables_generated"].append(cost_path.name)

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

**Validation scope:** C2 classifies all four indexed brands using official 2026 EOCs, CMS plan attributes, carrier family evidence, and review rules. C3/C4 consume only the Health Net California group handoff. Provider membership is unverified. C3 and C4 audit complete source MRFs. C4 output is in `c4/c4_manifest.csv` and per-file audit CSVs. C5 uses synthetic address seed rows and at most 10,000 C4-selected rows; C5–C7 figures below are demonstration results, not verified submission metrics.

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
| **C5: Address Resolution** | Unique In-Network NPIs | {summary_metrics['unique_npis_count']:,} | Type 1 Individuals & Type 2 Organizations |
| | Unique Contracted TINs | {summary_metrics['unique_tins_count']:,} | Medical groups and health systems |
| | Unique Verified Practice Sites | {summary_metrics['unique_addresses_count']:,} | Physical addresses (PO Boxes strictly rejected) |
| | **Demonstration address association** | **{summary_metrics['share_npis_verified_address']}%** | Synthetic seed rows; independent practice-address verification still required |

## Deliverables & Audit Files Generated

1. `Centene_CA_Commercial_PPO_Provider_Rates.xlsx` (Deliverable 1: Final Provider Rate File)
2. `Logic_File.md` (Deliverable 2: Logic for Network ID and Address Mapping)
3. `File_Quality_Metrics.md` & `file_quality_scorecard.csv` (Deliverable 3: Quality Metrics & Scores)
4. `Summary_Metrics.json` & `Summary_Metrics.md` (Deliverable 4: Summary Metrics)
5. `plan_decisions.csv` (C2 Plan Decisions with Product and Network Statuses)
6. `file_manifest.csv` (C2 Rate File Manifest with MIXED classification)
7. `review_queue.csv` (C2 Unresolved Review Queue)
8. `provider_cost_effectiveness_benchmark.csv` (Deliverable 7: C7 Cost Effectiveness)
9. `c4/c4_manifest.csv` and per-file C4 audit CSVs (complete source-file rate extraction)
"""
    summary_md_path = out_dir / "Summary_Metrics.md"
    summary_md_path.write_text(summary_md_content, encoding="utf-8")
    summary_metrics["deliverables_generated"].append(summary_md_path.name)

    # Synthesize Master Deliverable 2: Logic File
    logic_file_path = out_dir / "Logic_File.md"
    c1_c2_doc = (NEW_DIR / "docs" / "C1_C2_METHODOLOGY_AND_LOGIC.md").read_text(encoding="utf-8")
    c4_doc = (NEW_DIR / "docs" / "C4_RATE_EXTRACTION_LOGIC.md").read_text(encoding="utf-8")
    c5_doc = (NEW_DIR / "docs" / "C5_ADDRESS_MAPPING_LOGIC.md").read_text(encoding="utf-8")

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
    d3_doc = (NEW_DIR / "docs" / "C3_FILE_QUALITY_METRICS.md").read_text(encoding="utf-8")
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
    parser.add_argument("--nppes", type=Path, help="Path to local NPPES CSV extract")
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
        output_dir=args.output_dir,
        limit_codes=not args.all_codes,
        as_of=args.as_of,
        c3_benchmark_csv=args.c3_benchmark_csv,
        c3_expected_npis_csv=args.c3_expected_npis_csv,
    )
