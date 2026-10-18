"""Build evidence-backed submission documents from completed stage summaries.

Run after the stage commands. Missing downstream summaries stay unknown rather
than inheriting figures from the old synthetic demonstration.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


def percent(numerator: int | None, denominator: int | None) -> float | None:
    if numerator is None or denominator is None or denominator == 0:
        return None
    return round(100 * numerator / denominator, 2)


def show(value, suffix="") -> str:
    return "Unknown" if value is None else f"{value:,}{suffix}" if isinstance(value, int) else f"{value}{suffix}"


def nested_section(path: Path) -> str:
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    if lines and lines[0].startswith("# "):
        lines = lines[1:]
    inside_fence = False
    result = []
    for line in lines:
        if line.startswith("```"):
            inside_fence = not inside_fence
        if not inside_fence and line.startswith("## "):
            line = "#" + line
        elif not inside_fence and line.startswith("### "):
            line = "#" + line
        result.append(line)
    return "\n".join(result).strip()


def build(source: Path, output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    c2 = read_json(source / "deliverables" / "c2_summary.json")
    c3_all = read_json(source / "deliverables" / "file_quality_details.json")
    manifest_path = source / "outputs" / "c4" / "c4_manifest.csv"
    c4_files = sorted((source / "outputs" / "c4").glob("*/c4_summary.json"))
    c4 = read_json(c4_files[0]) if len(c4_files) == 1 else None
    c5 = read_json(source / "outputs" / "c5" / "c5_summary.json")
    c6 = read_json(source / "outputs" / "c6" / "c6_summary.json")
    c3 = c3_all[0] if isinstance(c3_all, list) and len(c3_all) == 1 else None
    if c2 is None or c3 is None:
        raise FileNotFoundError("C2 summary and one complete C3 file audit are required")
    if c4 is not None and c4.get("sha256") != c3.get("sha256"):
        raise ValueError("C3 and C4 source hashes differ")
    if c4 is not None and not manifest_path.is_file():
        raise FileNotFoundError("C4 summary has no manifest")
    if c4 is not None and c5 is not None:
        selected_path = source / "outputs" / "c4" / c4["source_file_id"] / "selected_rates.csv"
        selected_hash = hashlib.sha256(selected_path.read_bytes()).hexdigest()
        c5_hashes = {item.get("sha256") for item in c5.get("inputs", [])}
        if selected_hash not in c5_hashes:
            raise ValueError("C5 did not use the current C4 selected-rate file")
    if c4 is not None and c6 is not None and c6["counts"].get("selected_c4_rows") != c4["counts"]["selected"]:
        raise ValueError("C6 selected-row count does not match the current C4 run")

    # The official logic and metric deliverables are assembled from the
    # reviewed stage methodology. They can be rebuilt after documentation edits.
    docs = source / "docs"
    sections = [
        ("C1–C2: PPO network identification", "C1_C2_METHODOLOGY_AND_LOGIC.md"),
        ("C4: rate selection", "C4_RATE_EXTRACTION_LOGIC.md"),
        ("C5–C6: provider, TIN, address, and rate evidence", "C5_ADDRESS_MAPPING_LOGIC.md"),
    ]
    logic = [
        "# Logic file — Centene California commercial group PPO",
        "",
        "**Deliverable 2.** The sections below state the implemented decision rules and their evidence limits. "
        "The selected Health Net rate file is shared with non-PPO plans. A file link alone does not verify PPO-specific rates or provider membership.",
    ]
    for title, filename in sections:
        logic += ["", "---", "", f"## {title}", "", nested_section(docs / filename)]
    (output / "Logic_File.md").write_text("\n".join(logic) + "\n", encoding="utf-8")
    shutil.copyfile(docs / "C3_FILE_QUALITY_METRICS.md", output / "File_Quality_Metrics.md")

    # Target counts come from the current manifest, not a historical report.
    import csv
    with (source / "deliverables" / "file_manifest.csv").open(newline="", encoding="utf-8") as stream:
        target_rows = list(csv.DictReader(stream))
    if len(target_rows) != 1:
        raise ValueError("Expected one current Health Net CA handoff file; review the manifest")
    target = target_rows[0]
    target_confirmed = int(target["target_confirmed_ppo_plans"])
    target_provisional = int(target["target_provisional_ppo_plans"])
    mixed = target["file_classification"] == "MIXED"
    c4_selected = c4["counts"]["selected"] if c4 else None
    unique_npis = c5.get("unique_npis") if c5 else None
    physical_npis = c5.get("unique_npis_with_physical_candidate") if c5 else None
    verified_npis = c5.get("unique_npis_with_fully_verified_link") if c5 else None
    exported = c6["counts"].get("exported_rate_rows", 0) if c6 else None
    metrics = {
        "as_of": c3["as_of"],
        "target": "Centene / Health Net California commercial group PPO",
        "source_status": "CURRENT_STAGE_OUTPUTS_WITH_UNVERIFIED_DOWNSTREAM_LINKAGE",
        "challenges_executed": ["C1", "C2", "C3"] + (["C4"] if c4 else []) + (["C5"] if c5 else []) + (["C6"] if c6 else []),
        "confirmed_ppo_count": c2["confirmed_ppo_count"],
        "provisional_ppo_count": c2["provisional_ppo_count"],
        "excluded_non_ppo_count": c2["excluded_non_ppo_count"],
        "unresolved_count": c2["unresolved_count"],
        "c4_file_summaries": [c4] if c4 else [],
        "c1_c2": {
            "index_files": c2["source_index_count"],
            "raw_plan_file_edges": c2["raw_plan_file_edges"],
            "deduplicated_plan_file_edges": c2["deduplicated_plan_file_edges"],
            "all_brand_confirmed_ppo_edges": c2["confirmed_ppo_count"],
            "all_brand_provisional_ppo_edges": c2["provisional_ppo_count"],
            "target_confirmed_ppo_edges": target_confirmed,
            "target_provisional_ppo_edges": target_provisional,
            "selected_rate_files": c2["selected_ppo_rate_files"],
            "file_classification": target["file_classification"],
        },
        "c3": {
            "source_sha256": c3["sha256"],
            "published_prices": c3["counts"]["published_prices"],
            "quality_score": c3["composite_fqs"],
            "grade": c3["grade"],
            "quality_status": c3["quality_status"],
            "review_flags": c3["review_flags"],
            "external_ppo_provider_coverage_pct": c3["external_provider_coverage_pct"],
        },
        "c4": None if c4 is None else {
            "expanded_rate_rows": c4["counts"]["expanded_rate_rows"],
            "selected_rate_contexts": c4_selected,
            "plan_attribution": c4["plan_attribution"],
        },
        "c5": None if c5 is None else {
            "unique_npis": unique_npis,
            "unique_tins": c5["unique_tins"],
            "npi_tin_pairs": c5["npi_tin_pairs"],
            "npis_with_physical_candidate": physical_npis,
            "candidate_npi_coverage_pct": percent(physical_npis, unique_npis),
            "npis_with_fully_verified_link": verified_npis,
            "verified_npi_coverage_pct": percent(verified_npis, unique_npis),
        },
        "c6": None if c6 is None else {
            "verified_ppo_rate_rows": exported,
            "withheld_unattributed_rate_rows": c6["counts"].get("withheld_unattributed_rate_rows"),
        },
        "validation": {
            "rate_sample_correctness_pct": None,
            "clean_rerun_success": None,
            "note": "Neither source-row sample comparison nor clean-clone rerun is recorded in the stage summaries.",
        },
    }
    (output / "Summary_Metrics.json").write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")

    verified_pct = percent(verified_npis, unique_npis)
    lines = [
        "# Current run summary — Centene California commercial group PPO",
        "",
        f"**Deliverable 4 · as of {c3['as_of']}**. Counts below come from the current C2–C6 stage summaries, not the earlier synthetic demonstration. C3 grades the complete shared file; it does not prove PPO rate attribution.",
        "",
        "| Stage | Measure | Result | Interpretation |",
        "| --- | --- | ---: | --- |",
        f"| C1 | Index files / deduplicated plan-file edges | {c2['source_index_count']} / {c2['deduplicated_plan_file_edges']:,} | {c2['raw_plan_file_edges']:,} raw edges |",
        f"| C2 | Target PPO edges | {target_confirmed} confirmed; {target_provisional} provisional | One selected file; classification {target['file_classification']} |",
        f"| C3 | Published prices / file quality | {c3['counts']['published_prices']:,} / {c3['composite_fqs']}/100 | Grade {c3['grade']}; {c3['quality_status']} |",
        f"| C4 | Expanded rows / selected contexts | {show(c4['counts']['expanded_rate_rows'] if c4 else None)} / {show(c4_selected)} | {c4['plan_attribution'] if c4 else 'Not run'} |",
        f"| C5 | Unique NPIs / TINs / NPI–TIN pairs | {show(unique_npis)} / {show(c5['unique_tins'] if c5 else None)} / {show(c5['npi_tin_pairs'] if c5 else None)} | Source-file providers; PPO membership unresolved |",
        f"| C5 | NPIs with physical site candidate | {show(physical_npis)} ({show(percent(physical_npis, unique_npis), '%')}) | Candidate is not verified |",
        f"| C5 | NPIs with fully verified link | {show(verified_npis)} ({show(verified_pct, '%')}) | Requires site, TIN/site, and exact PPO/site proof |",
        f"| C6 | Verified PPO-specific rate rows | {show(exported)} | {show(c6['counts'].get('withheld_unattributed_rate_rows') if c6 else None)} C4 rows withheld for unattributed rates |",
        "",
        "## Source and review notes",
        "",
        f"- C3 source SHA-256: `{c3['sha256']}`. Benchmark-panel coverage: {c3['dimension_scores']['code_panel_coverage']}%; duplicate control: {c3['dimension_scores']['duplicate_control']}%. External PPO provider coverage is unknown without a verified roster.",
        f"- C3 review flags: {', '.join(c3['review_flags'])}.",
        "- C5 used NPPES/NUCC evidence without a dated exact-plan directory or direct TIN/site roster in the recorded run. NPPES-only sites remain candidates.",
        "- Rate sample correctness and clean-clone reproducibility are not recorded in these stage summaries; neither is assigned a passing value.",
        "- The earlier root-level and historical workbook/summary figures are not submission evidence. The current C6 workbook has headers and zero verified PPO rows.",
        "",
        "See `Project_Evaluation_Scorecard.md` for the cross-stage measures and release gate.",
    ]
    (output / "Summary_Metrics.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    project = [
        "# Project evaluation scorecard",
        "",
        "This measures end-to-end evidence and submission readiness. It is separate from C3 file quality and optional C7 provider price comparisons. Unknown measures are never treated as zero or as passing.",
        "",
        "| Measure | Formula | Current result | Decision use |",
        "| --- | --- | ---: | --- |",
        f"| Target plan evidence maturity | Confirmed target PPO plan-file edges ÷ confirmed + provisional target PPO edges | {percent(target_confirmed, target_confirmed + target_provisional)}% ({target_confirmed}/{target_confirmed + target_provisional}) | Prioritize plan review; not a network accuracy estimate |",
        f"| File attribution | Selected target files known PPO-only ÷ selected target files | {0 if mixed else 100}% ({0 if mixed else 1}/1) | Blocks PPO-specific rate claim for shared files |",
        f"| Candidate address reach | Unique C4 NPIs with physical candidate ÷ unique C4 NPIs | {show(percent(physical_npis, unique_npis), '%')} | Shows matching reach, not verification |",
        f"| Fully verified provider link | Unique C4 NPIs with corroborated site, direct TIN/site proof, and exact PPO/site proof ÷ unique C4 NPIs | {show(verified_pct, '%')} | Core C5 outcome |",
        f"| Verified rate yield | C6 verified PPO-specific rows ÷ C4 selected rate contexts | {show(percent(exported, c4_selected), '%')} | Final rate-file evidence gate; zero while attribution is unresolved |",
        "| Rate sample correctness | Sampled exported rows matching source rate and selection decision ÷ sampled exported rows | Unknown | Requires a recorded source-row audit or answer key |",
        "| Clean rerun | Successful fresh-environment runs ÷ attempted fresh-environment runs | Unknown | Requires a recorded clean run with input hashes |",
        "",
        "**Release gate:** publish a populated PPO rate file only when a PPO-only rate attribution is documented, its NPI/TIN/site links are verified, sampled rows reconcile to the source, and the README rerun succeeds. The current release gate is **not met**.",
        "",
        "The C3 score is reported separately: " + str(c3["composite_fqs"]) + "/100, grade " + str(c3["grade"]) + ", " + str(c3["quality_status"]) + ". It grades the published file's fitness for direct-dollar benchmarking, not the completed project.",
    ]
    (output / "Project_Evaluation_Scorecard.md").write_text("\n".join(project) + "\n", encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--output-dir", type=Path, default=PROJECT_ROOT / "deliverables")
    args = parser.parse_args()
    build(args.source, args.output_dir)
