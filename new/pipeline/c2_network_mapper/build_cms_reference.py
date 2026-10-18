"""Rebuild the small, versioned CMS 2026 plan-attribute reference used by C2.

Download the 2026 Plan Attributes PUF ZIP from CMS first. This command reads the
supplied indexes and retains only matching HIOS product prefixes. It never
changes an index or a rate file.
"""
from __future__ import annotations

import argparse
import csv
import io
import zipfile
from pathlib import Path

from pipeline.c1_index_parser.index_parser import CenteneIndexParser
from pipeline.config import CONFIG_DIR, REPO_ROOT

SOURCE_URL = "https://download.cms.gov/marketplace-puf/2026/plan-attributes-puf.zip"
FIELDS = [
    "BusinessYear", "StateCode", "MarketCoverage", "StandardComponentId",
    "HIOSProductId", "PlanMarketingName", "PlanType", "NetworkId",
    "PlanEffectiveDate", "PlanExpirationDate",
]


def build(zip_path: Path, index_dir: Path, output: Path) -> int:
    parser = CenteneIndexParser()
    for path in sorted(index_dir.glob("*_index.json")):
        parser.parse_index_file(path)
    products = set(parser.build_deduplicated_plan_table().query("plan_id_type == 'hios'")["plan_id"])
    if not products:
        raise ValueError("No HIOS product IDs found in the supplied indexes")
    selected = []
    with zipfile.ZipFile(zip_path) as archive:
        with archive.open("plan-attributes-puf.csv") as source:
            for record in csv.DictReader(io.TextIOWrapper(source, encoding="utf-8-sig")):
                if record["BusinessYear"] == "2026" and record["HIOSProductId"] in products:
                    selected.append({key: record[key] for key in FIELDS})
    if not selected:
        raise ValueError("CMS reference did not match any supplied HIOS products")
    selected.sort(key=lambda row: tuple(row[key] for key in FIELDS))
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(selected)
    return len(selected)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zip", type=Path, default=REPO_ROOT / "data" / "reference" / "plan-attributes-puf.zip")
    parser.add_argument("--index-dir", type=Path, default=REPO_ROOT / "data" / "indexes")
    parser.add_argument("--output", type=Path, default=CONFIG_DIR / "cms_2026_plan_attributes.csv")
    args = parser.parse_args()
    print(f"Extracted {build(args.zip, args.index_dir, args.output)} CMS records from {SOURCE_URL}")


if __name__ == "__main__":
    main()
