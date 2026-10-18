"""Extract official 2026 California Ambetter EOC links from a saved carrier page.

Download https://www.ambetterhealth.com/en/ca/health-plans/Plan_Materials/?group=ifp
as HTML, then run this script. Review the produced CSV before versioning it.
"""
from __future__ import annotations

import argparse
import csv
import re
from html.parser import HTMLParser
from pathlib import Path

from pipeline.config import CONFIG_DIR, REPO_ROOT


class LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.href = None
        self.label = ""
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.href = dict(attrs).get("href")
            self.label = ""

    def handle_data(self, data):
        if self.href is not None:
            self.label += data

    def handle_endtag(self, tag):
        if tag == "a" and self.href:
            self.links.append((self.label.strip(), self.href))
            self.href = None


def build(html_path: Path, output: Path) -> int:
    parser = LinkParser()
    parser.feed(html_path.read_text(encoding="utf-8"))
    records = []
    for label, href in parser.links:
        if "/eoc/2026/" not in href or not label.startswith("2026"):
            continue
        # The source page uses an en dash; tolerate a replacement character
        # when a saved copy was decoded by PowerShell before writing to disk.
        name = re.sub(r"^2026\s*[-–\ufffd]\s*", "", label)
        name = re.sub(r"\s*[-–\ufffd]\s*English \(PDF\)$", "", name).strip()
        if name == label or (" PPO" not in name and " HMO" not in name):
            raise ValueError(f"Unexpected Ambetter EOC label: {label}")
        plan_type = "PPO" if " PPO" in name else "HMO"
        records.append({
            "year": "2026", "state": "CA", "market": "individual",
            "plan_name": name, "plan_type": plan_type,
            "source_url": "https://www.ambetterhealth.com" + href,
        })
    if len(records) < 40:
        raise ValueError("Too few 2026 California Ambetter EOCs on saved carrier page")
    records.sort(key=lambda r: (r["plan_name"], r["source_url"]))
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(records[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(records)
    return len(records)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--html", type=Path, default=REPO_ROOT / "data" / "reference" / "ambetter_ca_plan_materials.html")
    parser.add_argument("--output", type=Path, default=CONFIG_DIR / "ambetter_ca_2026_eocs.csv")
    args = parser.parse_args()
    print(f"Extracted {build(args.html, args.output)} official 2026 EOC links")


if __name__ == "__main__":
    main()
