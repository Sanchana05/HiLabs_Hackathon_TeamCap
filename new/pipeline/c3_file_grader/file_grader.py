"""Complete, bounded-memory audit of CMS in-network MRFs (before C4 filtering)."""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import math
import random
import sqlite3
import sys
import tempfile
from collections import Counter
from contextlib import ExitStack
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from statistics import quantiles

import ijson


WEIGHTS = {
    "code_panel_coverage": .25, "provider_linkage": .15,
    "usable_price_share": .15, "direct_dollar_share": .10,
    "outlier_control": .10, "freshness": .05, "duplicate_control": .20,
}
DIRECT_TYPES = {"negotiated", "fee schedule"}
KNOWN_TYPES = DIRECT_TYPES | {"percentage", "per diem", "derived"}
SAMPLE_SIZE = 128
MIN_STRATUM = 20
MAX_STRATA = 50000


def _open(path: Path):
    return gzip.open(path, "rb") if path.suffix.lower() == ".gz" else path.open("rb")


def _date(value):
    try:
        return date.fromisoformat(str(value)[:10])
    except (ValueError, TypeError):
        return None


def _amount(value):
    try:
        n = Decimal(str(value))
        return n if n.is_finite() else None
    except (InvalidOperation, ValueError, TypeError):
        return None


def _list(value):
    if value is None:
        return ()
    if not isinstance(value, list):
        value = [value]
    return tuple(sorted(str(x).strip() for x in value if str(x).strip()))


def _scope(item, price):
    return (str(item.get("billing_code_type", "")).upper().strip(),
            str(item.get("billing_code", "")).strip(),
            str(item.get("billing_code_type_version", "")).strip(),
            str(item.get("negotiation_arrangement", "")).strip(),
            str(item.get("name", "")).strip(),
            str(item.get("description", "")).strip(),
            str(price.get("billing_class", "")).lower().strip(),
            str(price.get("negotiated_type", "")).lower().strip(),
            _list(price.get("service_code")), _list(price.get("billing_code_modifier")))


def _metadata(path):
    result = {}
    with _open(path) as stream:
        for prefix, event, value in ijson.parse(stream):
            if "." not in prefix and event in {"string", "number", "boolean"}:
                result[prefix] = str(value)
    return result


def _sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _benchmark(path):
    if path is None:
        path = Path(__file__).resolve().parents[2] / "config" / "c3_benchmark_codes.csv"
    result = {}
    with Path(path).open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        if not {"billing_code", "weight"} <= set(reader.fieldnames or []):
            raise ValueError("Benchmark CSV must have billing_code and weight")
        for row in reader:
            code, weight = row["billing_code"].strip(), float(row["weight"])
            if not code or code in result or not math.isfinite(weight) or weight <= 0:
                raise ValueError(f"Invalid or duplicate benchmark code: {code!r}")
            result[code] = weight
    if not result:
        raise ValueError("Empty benchmark panel")
    resolved = Path(path).resolve()
    source = str(resolved.relative_to(Path.cwd().resolve())) if resolved.is_relative_to(Path.cwd().resolve()) else resolved.name
    return result, source


def _pairs(groups, counts):
    pairs = set()
    for group in groups:
        if not isinstance(group, dict):
            counts["invalid_provider_groups"] += 1
            continue
        tin = group.get("tin")
        value = str(tin.get("value", "")).strip() if isinstance(tin, dict) else ""
        tin_type = str(tin.get("type", "")).lower().strip() if isinstance(tin, dict) else ""
        npis = group.get("npi")
        if not value:
            counts["groups_without_tin"] += 1
        if not isinstance(npis, list) or not npis:
            counts["groups_without_npi"] += 1
            continue
        for npi in npis:
            npi = str(npi).strip()
            if len(npi) == 10 and npi.isdigit() and value:
                pairs.add((npi, tin_type, value))
            else:
                counts["incomplete_provider_links"] += 1
    return pairs


def _flush(db, fingerprints, npis, tins, counts):
    if not fingerprints:
        return
    db.executemany("INSERT OR IGNORE INTO npis VALUES (?)", ((npi,) for npi in npis))
    db.executemany("INSERT OR IGNORE INTO tins VALUES (?)", ((tin,) for tin in tins))
    before = db.total_changes
    db.executemany("INSERT OR IGNORE INTO seen VALUES (?)", ((value,) for value in fingerprints))
    counts["duplicate_provider_prices"] += len(fingerprints) - (db.total_changes - before)
    fingerprints.clear()
    npis.clear()
    tins.clear()


class FileQualityGrader:
    """Grades every published price; stores large distinct sets on disk."""

    def __init__(self, benchmark_csv=None, expected_npis_csv=None):
        self.benchmark, self.benchmark_source = _benchmark(benchmark_csv)
        self.expected_npis_csv = Path(expected_npis_csv) if expected_npis_csv else None

    def grade_file(self, path, *, source_url="", index_last_updated="",
                   as_of=None, file_classification="", sha256="", scratch_dir=None):
        path = Path(path).resolve()
        if not path.is_file():
            raise FileNotFoundError(path)
        as_of = as_of or date.today()
        counts, types = Counter(), Counter()
        codes, all_codes, samples, sample_seen = set(), set(), {}, Counter()
        rng = random.Random(0)
        meta = _metadata(path)
        updated = _date(meta.get("last_updated_on")) or _date(index_last_updated)
        update_source = "mrf" if _date(meta.get("last_updated_on")) else ("index" if updated else "missing")
        warnings = []
        if file_classification == "MIXED":
            warnings.append("Shared file: this audit does not establish PPO provider membership.")

        scratch = Path(scratch_dir or Path.cwd())
        scratch.mkdir(parents=True, exist_ok=True)
        with ExitStack() as stack:
            temp = stack.enter_context(tempfile.TemporaryDirectory(prefix="c3_audit_", dir=scratch))
            db = sqlite3.connect(str(Path(temp) / "state.sqlite"))
            stack.callback(db.close)
            db.execute("PRAGMA journal_mode=OFF")
            db.execute("PRAGMA synchronous=OFF")
            db.execute("PRAGMA cache_size=-131072")
            db.execute("CREATE TABLE refs (id TEXT PRIMARY KEY, groups_json TEXT)")
            db.execute("CREATE TABLE npis (npi TEXT PRIMARY KEY)")
            db.execute("CREATE TABLE tins (tin TEXT PRIMARY KEY)")
            db.execute("CREATE TABLE seen (fingerprint BLOB PRIMARY KEY) WITHOUT ROWID")
            db.execute("CREATE TABLE expected (npi TEXT PRIMARY KEY)")
            with _open(path) as stream:
                for ref in ijson.items(stream, "provider_references.item"):
                    counts["provider_reference_objects"] += 1
                    if not isinstance(ref, dict) or ref.get("provider_group_id") is None or not isinstance(ref.get("provider_groups"), list):
                        counts["invalid_provider_reference_objects"] += 1
                        continue
                    try:
                        db.execute("INSERT INTO refs VALUES (?,?)",
                                   (str(ref["provider_group_id"]), json.dumps(ref["provider_groups"], separators=(",", ":"))))
                    except sqlite3.IntegrityError:
                        counts["duplicate_provider_reference_ids"] += 1
            if self.expected_npis_csv:
                with self.expected_npis_csv.open(newline="", encoding="utf-8-sig") as stream:
                    reader = csv.DictReader(stream)
                    if "npi" not in (reader.fieldnames or []):
                        raise ValueError("Expected roster CSV needs an npi column")
                    db.executemany("INSERT OR IGNORE INTO expected VALUES (?)",
                                   ((row["npi"].strip(),) for row in reader if row["npi"].strip()))
            db.commit()

            fingerprints, npi_batch, tin_batch = [], set(), set()
            with _open(path) as stream:
                for item in ijson.items(stream, "in_network.item"):
                    counts["in_network_items"] += 1
                    if not isinstance(item, dict):
                        counts["invalid_in_network_items"] += 1
                        continue
                    code = str(item.get("billing_code", "")).strip()
                    if code:
                        all_codes.add(code)
                        if str(item.get("billing_code_type", "")).upper().strip() in {"CPT", "HCPCS"}:
                            codes.add(code)
                    else:
                        counts["items_without_code"] += 1
                    if not item.get("billing_code_type"):
                        counts["items_without_code_type"] += 1
                    rates = item.get("negotiated_rates")
                    if not isinstance(rates, list):
                        counts["items_without_rate_groups"] += 1
                        continue
                    for nr in rates:
                        counts["negotiated_rate_groups"] += 1
                        if not isinstance(nr, dict):
                            counts["invalid_rate_groups"] += 1
                            continue
                        groups = nr.get("provider_groups") or []
                        if not isinstance(groups, list):
                            counts["invalid_direct_group_lists"] += 1
                            groups = []
                        refs = nr.get("provider_references") or []
                        if not isinstance(refs, list):
                            counts["invalid_reference_lists"] += 1
                            refs = []
                        for ref_id in refs:
                            row = db.execute("SELECT groups_json FROM refs WHERE id=?", (str(ref_id),)).fetchone()
                            if row:
                                groups.extend(json.loads(row[0]))
                            else:
                                counts["unresolved_reference_uses"] += 1
                        pairs = _pairs(groups, counts)
                        prices = nr.get("negotiated_prices")
                        if not isinstance(prices, list):
                            counts["rate_groups_without_prices"] += 1
                            continue
                        for price in prices:
                            counts["published_prices"] += 1
                            if not isinstance(price, dict):
                                counts["invalid_price_objects"] += 1
                                continue
                            amount = _amount(price.get("negotiated_rate"))
                            kind = str(price.get("negotiated_type", "")).lower().strip()
                            types[kind or "(missing)"] += 1
                            if amount is None:
                                counts["non_numeric_prices"] += 1
                            elif amount <= 0:
                                counts["zero_or_negative_prices"] += 1
                            elif amount <= Decimal(".01"):
                                counts["penny_prices"] += 1
                            if amount is not None and amount >= 100000:
                                counts["high_price_flags"] += 1
                            expires = _date(price.get("expiration_date"))
                            if expires is None:
                                counts["missing_or_invalid_expiration"] += 1
                            elif expires.year >= 2100:
                                counts["far_future_expiration_flags"] += 1
                            elif expires < as_of:
                                counts["expired_prices"] += 1
                            if not kind:
                                counts["missing_rate_type"] += 1
                            elif kind not in KNOWN_TYPES:
                                counts["unknown_rate_type"] += 1
                            counts["linked_prices" if pairs else "unlinked_prices"] += 1
                            if amount is not None and amount > 0 and kind in DIRECT_TYPES:
                                key = _scope(item, price)
                                if key not in samples and len(samples) >= MAX_STRATA:
                                    counts["prices_outside_sample"] += 1
                                else:
                                    sample_seen[key] += 1
                                    sample = samples.setdefault(key, [])
                                    if len(sample) < SAMPLE_SIZE:
                                        sample.append(float(amount))
                                    else:
                                        pick = rng.randrange(sample_seen[key])
                                        if pick < SAMPLE_SIZE:
                                            sample[pick] = float(amount)
                            signature = (
                                _scope(item, price),
                                json.dumps(price, sort_keys=True, default=str, separators=(",", ":")),
                            )
                            for npi, tin_type, tin in pairs:
                                fingerprint = hashlib.sha256(repr((signature, npi, tin_type, tin)).encode()).digest()
                                fingerprints.append(fingerprint)
                                npi_batch.add(npi)
                                tin_batch.add(tin)
                                counts["expanded_provider_prices"] += 1
                                if len(fingerprints) >= 20000:
                                    _flush(db, fingerprints, npi_batch, tin_batch, counts)
                            if counts["published_prices"] % 250000 == 0:
                                print(f"C3 scanned {counts['published_prices']:,} published prices", file=sys.stderr, flush=True)
            _flush(db, fingerprints, npi_batch, tin_batch, counts)
            db.commit()
            unique_npis = db.execute("SELECT count(*) FROM npis").fetchone()[0]
            unique_tins = db.execute("SELECT count(*) FROM tins").fetchone()[0]
            expected = db.execute("SELECT count(*) FROM expected").fetchone()[0]
            matched = db.execute("SELECT count(*) FROM expected JOIN npis USING(npi)").fetchone()[0]

        bounds = {}
        for key, sample in samples.items():
            if sample_seen[key] < MIN_STRATUM:
                continue
            q1, _, q3 = quantiles(sample, n=4, method="inclusive")
            if q3 > q1:
                bounds[key] = (max(0., q1 - 3 * (q3 - q1)), q3 + 3 * (q3 - q1))
        if bounds:
            with _open(path) as stream:
                for item in ijson.items(stream, "in_network.item"):
                    if not isinstance(item, dict):
                        continue
                    for nr in item.get("negotiated_rates", []) or []:
                        if not isinstance(nr, dict):
                            continue
                        for price in nr.get("negotiated_prices", []) or []:
                            if not isinstance(price, dict):
                                continue
                            amount = _amount(price.get("negotiated_rate"))
                            if amount is None or amount <= 0:
                                continue
                            if str(price.get("negotiated_type", "")).lower().strip() not in DIRECT_TYPES:
                                continue
                            interval = bounds.get(_scope(item, price))
                            if interval:
                                counts["outlier_eligible_prices"] += 1
                                if not interval[0] <= float(amount) <= interval[1]:
                                    counts["outlier_prices"] += 1

        total = counts["published_prices"]
        scorable = total - counts["non_numeric_prices"] - counts["zero_or_negative_prices"]
        outlier_coverage = counts["outlier_eligible_prices"] / max(1, scorable)
        if not total:
            warnings.append("No published prices; no grade issued.")
        if updated is None:
            warnings.append("No valid update date; freshness unknown.")
        if outlier_coverage < .8:
            warnings.append("Insufficient comparable strata for filewide outlier score.")
        if not expected:
            warnings.append("External PPO provider coverage unknown; no reference roster supplied.")
        if counts["far_future_expiration_flags"]:
            warnings.append("Far-future expiration dates are not proof of an active contract.")
        weight_total = sum(self.benchmark.values())
        scores = {
            "code_panel_coverage": 100 * sum(w for code, w in self.benchmark.items() if code in codes) / weight_total,
            "provider_linkage": 100 * counts["linked_prices"] / total if total else None,
            "usable_price_share": 100 * (total - counts["non_numeric_prices"] - counts["zero_or_negative_prices"] - counts["penny_prices"]) / total if total else None,
            "direct_dollar_share": 100 * sum(n for kind, n in types.items() if kind in DIRECT_TYPES) / total if total else None,
            "outlier_control": 100 * (1 - counts["outlier_prices"] / counts["outlier_eligible_prices"]) if outlier_coverage >= .8 else None,
            "freshness": None,
            "duplicate_control": 100 * (1 - counts["duplicate_provider_prices"] / counts["expanded_provider_prices"]) if counts["expanded_provider_prices"] else None,
        }
        if updated is not None and total:
            days = (as_of - updated).days
            recency = 100 if days <= 31 else max(0, 100 - 2 * (days - 31))
            scores["freshness"] = recency
        scores = {k: round(v, 2) if v is not None else None for k, v in scores.items()}
        complete = total > 0 and all(v is not None for v in scores.values()) and not counts["invalid_in_network_items"]
        composite = round(sum(WEIGHTS[k] * v for k, v in scores.items()), 2) if complete else None
        grade = ("A" if composite >= 85 else "B" if composite >= 70 else "C" if composite >= 50 else "F") if composite is not None else "NOT_GRADED"
        review_flags = []
        if counts["expanded_provider_prices"] and counts["duplicate_provider_prices"] / counts["expanded_provider_prices"] > .20:
            review_flags.append("DUPLICATE_INFLATION_OVER_20_PERCENT")
        if scores["code_panel_coverage"] < 80:
            review_flags.append("BENCHMARK_PANEL_BELOW_80_PERCENT")
        if total and counts["far_future_expiration_flags"] / total > .50:
            review_flags.append("CONTRACT_EXPIRATION_NOT_VERIFIABLE")
        if not expected:
            review_flags.append("EXTERNAL_PPO_PROVIDER_COVERAGE_UNKNOWN")
        schema_errors = sum(counts[key] for key in (
            "invalid_provider_reference_objects", "duplicate_provider_reference_ids",
            "invalid_in_network_items", "items_without_code", "items_without_code_type",
            "items_without_rate_groups", "invalid_rate_groups", "rate_groups_without_prices",
            "invalid_direct_group_lists", "invalid_reference_lists",
            "invalid_price_objects", "missing_rate_type", "unknown_rate_type",
            "missing_or_invalid_expiration", "unresolved_reference_uses",
        ))
        if schema_errors:
            review_flags.append("SCHEMA_OR_REFERENCE_ERRORS")
        return {
            "file_name": path.name,
            "file_path": str(path.relative_to(Path.cwd().resolve())) if path.is_relative_to(Path.cwd().resolve()) else path.name,
            "source_url": source_url,
            "file_classification": file_classification, "size_bytes": path.stat().st_size,
            "sha256": sha256 or _sha256(path), "as_of": as_of.isoformat(),
            "mrf_last_updated_on": meta.get("last_updated_on"),
            "mrf_version": meta.get("version"),
            "index_last_updated_on": index_last_updated or None,
            "update_date_used": updated.isoformat() if updated else None,
            "update_date_source": update_source, "status": "COMPLETE" if total else "EMPTY",
            "composite_fqs": composite, "grade": grade, "dimension_scores": scores,
            "quality_status": "REVIEW_REQUIRED" if review_flags else "READY_FOR_ANALYST_REVIEW",
            "review_flags": review_flags, "schema_issue_count": schema_errors,
            "weights": WEIGHTS, "benchmark_source": self.benchmark_source,
            "benchmark_codes": len(self.benchmark),
            "benchmark_codes_present": sum(code in codes for code in self.benchmark),
            "distinct_billing_codes": len(all_codes), "unique_npis": unique_npis,
            "unique_tins": unique_tins, "expected_npis": expected or None,
            "matched_expected_npis": matched if expected else None,
            "external_provider_coverage_pct": round(100 * matched / expected, 2) if expected else None,
            "counts": dict(counts), "rate_types": dict(types), "outlier_strata_scored": len(bounds),
            "outlier_eligible_share": round(outlier_coverage, 4),
            "outlier_method": "seeded 128-price reservoir per code/type/version/description/class/setting/modifier; 3*IQR; >=20 prices",
            "warnings": warnings,
        }


def write_reports(results, output_dir):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "file_quality_details.json").write_text(
        json.dumps(results, indent=2, sort_keys=True), encoding="utf-8")
    columns = ["file_name", "source_url", "sha256", "size_bytes", "as_of", "status",
               "grade", "quality_status", "composite_fqs", "unique_npis", "unique_tins",
               "expected_npis", "external_provider_coverage_pct"] + list(WEIGHTS)
    with (output_dir / "file_quality_scorecard.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        for result in results:
            writer.writerow({**{k: result.get(k) for k in columns}, **result["dimension_scores"]})


def main():
    parser = argparse.ArgumentParser(description="Grade complete CMS in-network MRF files")
    parser.add_argument("--file", type=Path, action="append", help="Repeat for explicit files")
    parser.add_argument("--manifest", type=Path, help="C2 file_manifest.csv; grades each referenced file")
    parser.add_argument("--rate-dir", type=Path, action="append", help="Directory containing manifest files")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--as-of", type=date.fromisoformat, required=True)
    parser.add_argument("--index-last-updated", default="")
    parser.add_argument("--benchmark-csv", type=Path)
    parser.add_argument("--expected-npis-csv", type=Path)
    parser.add_argument("--scratch-dir", type=Path, help="Writable location for disk-backed audit state")
    args = parser.parse_args()
    if not args.file and not args.manifest:
        parser.error("Provide --file or --manifest")
    grader = FileQualityGrader(args.benchmark_csv, args.expected_npis_csv)
    inputs = [(p, "", "") for p in (args.file or [])]
    if args.manifest:
        names_to_urls = {}
        with args.manifest.open(newline="", encoding="utf-8-sig") as stream:
            for row in csv.DictReader(stream):
                name = row.get("rate_file_name") or row.get("filename")
                if not name:
                    raise ValueError("Manifest needs rate_file_name or filename")
                url = row.get("rate_file_url", "")
                if name in names_to_urls and names_to_urls[name] != url:
                    raise ValueError(f"Two rate URLs share filename {name}; use distinct local paths")
                names_to_urls[name] = url
                candidates = [directory / name for directory in (args.rate_dir or [args.manifest.parent])]
                path = next((candidate for candidate in candidates if candidate.is_file()), None)
                if path is None:
                    raise FileNotFoundError(f"Manifest rate file missing: {name}")
                inputs.append((path, row.get("rate_file_url", ""), row.get("file_classification", "")))
    results = [grader.grade_file(p, source_url=url, file_classification=classification,
                                 as_of=args.as_of, index_last_updated=args.index_last_updated,
                                 scratch_dir=args.scratch_dir or args.output_dir)
               for p, url, classification in inputs]
    write_reports(results, args.output_dir)
    print(json.dumps([{"file": r["file_name"], "grade": r["grade"],
                       "score": r["composite_fqs"]} for r in results], indent=2))


if __name__ == "__main__":
    main()
