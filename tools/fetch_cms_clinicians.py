"""Stream the current CMS clinician file and retain only C4 provider NPIs.

The full CMS file is large. This command never loads it into memory and writes
the source publication date and dataset URL beside each retained observation.
CMS practice sites corroborate addresses, not commercial network membership.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import urllib.request
from collections import Counter
from datetime import date
from pathlib import Path


DATASET_ID = "mj5m-pzi6"
METADATA_URL = f"https://data.cms.gov/provider-data/api/1/metastore/schemas/dataset/items/{DATASET_ID}"
DATASET_URL = f"https://data.cms.gov/provider-data/dataset/{DATASET_ID}"
FIELDS = ("npi", "address_line1", "address_line2", "city", "state", "zip",
          "source_date", "record_id", "record_url", "specialty", "provider_name")


def target_npis(paths: list[Path]) -> set[str]:
    result: set[str] = set()
    for path in paths:
        with path.open(newline="", encoding="utf-8-sig") as stream:
            result.update(row["npi"].strip() for row in csv.DictReader(stream) if row.get("npi"))
    if not result:
        raise ValueError("No target NPIs in C4 selected-rate files")
    return result


def fetch(paths: list[Path], output: Path, *, as_of: date | None = None) -> dict:
    wanted = target_npis(paths)
    with urllib.request.urlopen(METADATA_URL, timeout=60) as response:
        metadata = json.load(response)
    modified = metadata.get("modified", "")
    distribution = metadata.get("distribution") or []
    source_url = next((d.get("downloadURL", "") for d in distribution
                       if d.get("mediaType") == "text/csv"), "")
    if not modified or not source_url:
        raise ValueError("CMS metadata has no publication date or CSV distribution")
    if as_of and date.fromisoformat(modified[:10]) > as_of:
        raise ValueError(f"CMS source {modified} is newer than analysis date {as_of}")
    output.parent.mkdir(parents=True, exist_ok=True)
    partial = output.with_suffix(output.suffix + ".part")
    counts: Counter[str] = Counter()
    matched: set[str] = set()
    request = urllib.request.Request(source_url, headers={"User-Agent": "HiLabs-provider-address-research/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=120) as response, \
             partial.open("w", newline="", encoding="utf-8") as destination:
            reader = csv.DictReader(io.TextIOWrapper(response, encoding="utf-8-sig", newline=""))
            writer = csv.DictWriter(destination, fieldnames=FIELDS)
            writer.writeheader()
            for row in reader:
                counts["source_rows"] += 1
                if counts["source_rows"] % 500_000 == 0:
                    print(f"Scanned {counts['source_rows']:,} CMS rows", flush=True)
                npi = (row.get("NPI") or "").strip()
                if npi not in wanted:
                    continue
                if (row.get("State") or "").strip().upper() != "CA":
                    continue
                line = (row.get("adr_ln_1") or "").strip()
                if not line:
                    continue
                writer.writerow({
                    "npi": npi,
                    "address_line1": line,
                    "address_line2": row.get("adr_ln_2", ""),
                    "city": row.get("City/Town", ""),
                    "state": row.get("State", ""),
                    "zip": row.get("ZIP Code", ""),
                    "source_date": modified,
                    "record_id": f"{row.get('Ind_enrl_ID', '')}:{row.get('adrs_id', '')}",
                    "record_url": DATASET_URL,
                    "specialty": row.get("pri_spec", ""),
                    "provider_name": " ".join(filter(None, (
                        row.get("Provider First Name", ""), row.get("Provider Last Name", "")))),
                })
                counts["matched_rows"] += 1
                matched.add(npi)
        partial.replace(output)
    finally:
        if partial.exists():
            partial.unlink()
    summary = {"dataset": DATASET_ID, "source_url": source_url,
               "dataset_url": DATASET_URL, "modified": modified,
               "target_npis": len(wanted), "matched_npis": len(matched),
               "counts": dict(counts), "output": output.name}
    output.with_suffix(".json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selected-rates", action="append", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--as-of", type=date.fromisoformat)
    args = parser.parse_args()
    print(json.dumps(fetch(args.selected_rates, args.output, as_of=args.as_of), indent=2))


if __name__ == "__main__":
    main()
