"""Refresh master summary after a C5 decision re-evaluation and C6 rerun."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def sync(output_dir: Path) -> None:
    summary_path = output_dir / "Summary_Metrics.json"
    c5 = json.loads((output_dir / "c5/c5_summary.json").read_text(encoding="utf-8"))
    c6 = json.loads((output_dir / "c6/c6_summary.json").read_text(encoding="utf-8"))
    candidate = json.loads((output_dir / "c6/c6_candidate_summary.json").read_text(encoding="utf-8"))
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["c5_summary"] = c5
    summary["c6_summary"] = c6
    summary["c6_candidate_summary"] = candidate
    summary["unique_npis_count"] = c5["unique_npis"]
    summary["unique_tins_count"] = c5["unique_tins"]
    summary["unique_addresses_count"] = c5["unique_physical_addresses"]
    summary["share_npis_verified_address"] = c5["share_npis_with_fully_verified_link"]
    summary["share_npis_corroborated_site"] = c5["share_npis_with_corroborated_site"]
    summary["share_npis_confirmed_ppo_site"] = c5["share_npis_with_confirmed_ppo_site"]
    generated = summary.get("deliverables_generated", [])
    for name in ("Centene_CA_Commercial_PPO_Rate_Candidates.xlsx", "c6/c6_workbook_validation.json"):
        if (output_dir / name).is_file() and name not in generated:
            generated.append(name)
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    md_path = output_dir / "Summary_Metrics.md"
    lines = md_path.read_text(encoding="utf-8").splitlines()
    has_candidate_row = any("**C6: Research candidates**" in line for line in lines)
    updated = []
    for line in lines:
        if "NPIs with a corroborated practice site" in line:
            line = ("| | NPIs with a corroborated practice site | "
                    f"{c5['share_npis_with_corroborated_site']}% "
                    "| Independent or direct practice-site evidence |")
        updated.append(line)
        if "NPIs with verified NPI/TIN/PPO site link" in line and not has_candidate_row:
            updated.append(
                "| **C6: Research candidates** | Six-column candidate rows | "
                f"{candidate['counts'].get('exported_candidate_rows', 0):,} "
                "| Independently corroborated address; exact PPO/site and TIN/site unverified |")
    md_path.write_text("\n".join(updated) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    sync(args.output_dir)


if __name__ == "__main__":
    main()
