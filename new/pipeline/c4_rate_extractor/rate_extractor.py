"""Complete, disk-backed extraction of CMS TiC in-network rates.

The output is a rate *file* audit. It never asserts that a provider belongs to
a PPO network merely because the file was linked by a PPO plan.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import logging
import math
import os
import re
import sqlite3
import tempfile
from collections import Counter
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterable

import ijson

LOG = logging.getLogger(__name__)
RATE_TYPES = {"negotiated", "derived", "fee schedule", "percentage", "per diem"}
CLASSES = {"professional", "institutional", "both"}
SETTINGS = {"inpatient", "outpatient", "both"}
ARRANGEMENTS = {"ffs", "bundle", "capitation"}
FIELDS = [
    "source_file_id", "source_file_name", "source_url", "source_locator",
    "file_classification", "plan_attribution", "npi", "tin_type", "tin", "tin_raw",
    "billing_code_type", "billing_code_type_version", "billing_code", "name",
    "description", "negotiation_arrangement", "negotiated_type", "rate",
    "rate_unit", "billing_class", "setting", "service_code",
    "billing_code_modifiers", "expiration_date", "contract_status",
    "provider_reference_id", "additional_information", "bundled_codes",
    "covered_services", "quality_flags", "decision", "decision_reason",
    "selected_source_locator", "rates_considered_count",
]


@dataclass(frozen=True)
class RateFileInput:
    path: Path
    source_url: str = ""
    file_classification: str = "UNKNOWN"
    expected_sha256: str = ""
    c3_quality_status: str = "NOT_PROVIDED"


def _open(path: Path):
    return gzip.open(path, "rb") if path.name.endswith(".gz") else path.open("rb")


def _iter_provider_references(path: Path):
    """Find references in either legal top-level JSON property order."""
    with _open(path) as stream:
        builder = None
        for prefix, event, value in ijson.parse(stream):
            if prefix == "provider_references" and event == "end_array":
                break
            if prefix == "provider_references.item" and event == "start_map":
                builder = ijson.common.ObjectBuilder()
            if builder is not None:
                builder.event(event, value)
                if prefix == "provider_references.item" and event == "end_map":
                    yield builder.value
                    builder = None


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _json(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _number(value):
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return number if number.is_finite() else None


def _date(value):
    try:
        return date.fromisoformat(str(value))
    except (ValueError, TypeError):
        return None


def _providers(groups, ref_label):
    """Yield each TIN/NPI association; keep invalid associations for audit."""
    for group_index, group in enumerate(groups):
        if not isinstance(group, dict):
            yield "", "", "", "", ref_label, f"group{group_index}", "INVALID_PROVIDER_GROUP"
            continue
        tin = group.get("tin") if isinstance(group.get("tin"), dict) else {}
        tin_type = str(tin.get("type") or "").strip().lower()
        tin_raw = str(tin.get("value") or "").strip()
        tin_value = tin_raw.replace("-", "") if tin_type == "ein" else tin_raw
        npis = group.get("npi")
        if not isinstance(npis, list) or not npis:
            npis = [""]
        for npi_index, raw_npi in enumerate(npis):
            npi = str(raw_npi).strip()
            problems = []
            if not npi.isdigit() or len(npi) != 10 or npi == "0000000000":
                problems.append("INVALID_OR_UNKNOWN_NPI")
            if tin_type == "ein":
                if not re.fullmatch(r"\d{2}-?\d{7}", tin_raw) or tin_value == "000000000":
                    problems.append("INVALID_EIN")
            elif tin_type == "npi":
                if not tin_value.isdigit() or len(tin_value) != 10 or tin_value == "0000000000":
                    problems.append("INVALID_TIN_NPI")
            else:
                problems.append("INVALID_TIN_TYPE")
            yield npi, tin_type, tin_value, tin_raw, ref_label, f"group{group_index}/npi{npi_index}", ";".join(problems)


class RateExtractor:
    """Run a complete file audit with local-file, manifest, and Python input ports."""

    def __init__(self, *, as_of: date, scratch_dir: Path | None = None):
        self.as_of = as_of
        self.scratch_dir = Path(scratch_dir) if scratch_dir else None

    def run_file(self, source: RateFileInput, output_dir: Path) -> dict:
        path = Path(source.path).resolve()
        if not path.is_file():
            raise FileNotFoundError(path)
        sha256 = _hash(path)
        if source.expected_sha256 and source.expected_sha256.lower() != sha256:
            raise ValueError(f"C3 SHA-256 mismatch for {path.name}")
        file_id = hashlib.sha256((source.source_url or path.name).encode()).hexdigest()[:16]
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        scratch = self.scratch_dir or output_dir
        scratch.mkdir(parents=True, exist_ok=True)
        counters = Counter()
        classification = str(source.file_classification or "UNKNOWN").strip().upper()
        attribution = "SHARED_FILE_UNRESOLVED" if classification == "MIXED" else "UNVERIFIED_NETWORK_MEMBERSHIP"

        with tempfile.TemporaryDirectory(prefix="c4_state_", dir=scratch) as temporary:
            db = sqlite3.connect(str(Path(temporary) / "rates.sqlite"))
            try:
                db.execute("PRAGMA journal_mode=OFF")
                db.execute("PRAGMA synchronous=OFF")
                db.execute("PRAGMA cache_size=-131072")
                db.execute("CREATE TABLE refs (id TEXT PRIMARY KEY, groups TEXT NOT NULL)")
                db.execute("CREATE TABLE rows (id INTEGER PRIMARY KEY, context BLOB, amount REAL, fingerprint BLOB, payload TEXT NOT NULL, decision TEXT NOT NULL, reason TEXT NOT NULL)")
                db.execute("CREATE TABLE seen (fingerprint BLOB PRIMARY KEY, row_id INTEGER NOT NULL) WITHOUT ROWID")

                for ref in _iter_provider_references(path):
                    counters["provider_reference_objects"] += 1
                    if not isinstance(ref, dict) or ref.get("provider_group_id") is None or not isinstance(ref.get("provider_groups"), list):
                        counters["invalid_provider_reference_objects"] += 1
                        continue
                    try:
                        db.execute("INSERT INTO refs VALUES (?,?)", (str(ref["provider_group_id"]), _json(ref["provider_groups"])))
                    except sqlite3.IntegrityError:
                        raise ValueError(f"Ambiguous duplicate provider_group_id {ref['provider_group_id']} in {path.name}")
                db.commit()

                with _open(path) as stream:
                    for item_index, item in enumerate(ijson.items(stream, "in_network.item")):
                        counters["in_network_items"] += 1
                        if not isinstance(item, dict):
                            counters["invalid_in_network_items"] += 1
                            continue
                        arrangement = str(item.get("negotiation_arrangement") or "").strip().lower()
                        code_type = str(item.get("billing_code_type") or "").strip().upper()
                        code_version = str(item.get("billing_code_type_version") or "").strip()
                        code = str(item.get("billing_code") or "").strip()
                        item_name = str(item.get("name") or "").strip()
                        description = str(item.get("description") or "").strip()
                        bundled = _json(item.get("bundled_codes") or [])
                        covered = _json(item.get("covered_services") or [])
                        item_errors = []
                        if not code_type or not code:
                            item_errors.append("MISSING_BILLING_CODE")
                        if not code_version:
                            item_errors.append("MISSING_BILLING_CODE_VERSION")
                        if not item_name or not description:
                            item_errors.append("MISSING_ITEM_DESCRIPTION")
                        if arrangement not in ARRANGEMENTS:
                            item_errors.append("INVALID_ARRANGEMENT")
                        rates = item.get("negotiated_rates")
                        if not isinstance(rates, list):
                            counters["invalid_rate_groups"] += 1
                            continue

                        for rate_index, rate_group in enumerate(rates):
                            counters["negotiated_rate_groups"] += 1
                            if not isinstance(rate_group, dict):
                                counters["invalid_rate_groups"] += 1
                                continue
                            groups = []
                            unresolved_ids = []
                            direct = rate_group.get("provider_groups") or []
                            if isinstance(direct, list):
                                groups.extend((g, "DIRECT") for g in direct)
                            else:
                                counters["invalid_direct_group_lists"] += 1
                            refs = rate_group.get("provider_references") or []
                            if isinstance(refs, list):
                                for ref_id in refs:
                                    found = db.execute("SELECT groups FROM refs WHERE id=?", (str(ref_id),)).fetchone()
                                    if found:
                                        groups.extend((g, str(ref_id)) for g in json.loads(found[0]))
                                    else:
                                        counters["unresolved_reference_uses"] += 1
                                        unresolved_ids.append(str(ref_id))
                            else:
                                counters["invalid_reference_lists"] += 1
                            people = []
                            for provider_group_index, (group, ref_id) in enumerate(groups):
                                people.extend(_providers([group], f"{ref_id}/g{provider_group_index}"))
                            people.extend(("", "", "", "", ref_id, "", "UNRESOLVED_PROVIDER_REFERENCE")
                                          for ref_id in unresolved_ids)
                            if not people:
                                people = [("", "", "", "", "", "", "MISSING_PROVIDER_LINK")]

                            prices = rate_group.get("negotiated_prices")
                            if not isinstance(prices, list):
                                counters["invalid_price_lists"] += 1
                                continue
                            for price_index, price in enumerate(prices):
                                counters["published_prices"] += 1
                                price = price if isinstance(price, dict) else {}
                                kind = str(price.get("negotiated_type") or "").strip().lower()
                                amount = _number(price.get("negotiated_rate"))
                                try:
                                    sortable_amount = float(amount) if amount is not None else None
                                except (OverflowError, ValueError):
                                    sortable_amount = None
                                billing_class = str(price.get("billing_class") or "").strip().lower()
                                setting = str(price.get("setting") or "").strip().lower()
                                expiry_text = str(price.get("expiration_date") or "").strip()
                                expiry = _date(expiry_text)
                                modifiers = price.get("billing_code_modifier") or []
                                if not isinstance(modifiers, list):
                                    modifiers = [str(modifiers)]
                                modifier_text = "|".join(sorted({str(m).strip() for m in modifiers if str(m).strip()}))
                                services = price.get("service_code") or []
                                if not isinstance(services, list):
                                    services = [str(services)]
                                services = sorted({str(s).strip() for s in services if str(s).strip()}) or [""]
                                errors = list(item_errors)
                                if kind not in RATE_TYPES:
                                    errors.append("INVALID_NEGOTIATED_TYPE")
                                if amount is None or amount <= 0:
                                    errors.append("INVALID_NONPOSITIVE_RATE")
                                elif sortable_amount is None or not math.isfinite(sortable_amount) or sortable_amount == 0:
                                    errors.append("RATE_OUTSIDE_SORTABLE_RANGE")
                                if billing_class not in CLASSES:
                                    errors.append("INVALID_BILLING_CLASS")
                                if setting not in SETTINGS:
                                    errors.append("INVALID_SETTING")
                                if expiry is None:
                                    errors.append("MISSING_OR_INVALID_EXPIRATION")
                                elif expiry != date(9999, 12, 31) and expiry < self.as_of:
                                    errors.append("EXPIRED_AS_OF")
                                if billing_class == "professional" and services == [""]:
                                    errors.append("MISSING_PROFESSIONAL_SERVICE_CODE")
                                flags = []
                                if expiry == date(9999, 12, 31):
                                    flags.append("NO_STATED_EXPIRY")
                                for npi, tin_type, tin, tin_raw, ref_id, provider_location, provider_error in people:
                                    for service in services:
                                        row_errors = errors + ([provider_error] if provider_error else [])
                                        locator = f"in_network/{item_index}/negotiated_rates/{rate_index}/negotiated_prices/{price_index}/{ref_id}/{provider_location}/service/{service}"
                                        payload = {
                                            "source_file_id": file_id, "source_file_name": path.name,
                                            "source_url": source.source_url, "source_locator": locator,
                                            "file_classification": classification, "plan_attribution": attribution,
                                            "npi": npi, "tin_type": tin_type, "tin": tin, "tin_raw": tin_raw,
                                            "billing_code_type": code_type, "billing_code_type_version": code_version,
                                            "billing_code": code, "name": item_name, "description": description,
                                            "negotiation_arrangement": arrangement, "negotiated_type": kind,
                                            "rate": str(amount) if amount is not None else str(price.get("negotiated_rate") or ""),
                                            "rate_unit": "PERCENT" if kind == "percentage" else "USD_PER_DAY" if kind == "per diem" else "USD",
                                            "billing_class": billing_class, "setting": setting,
                                            "service_code": service, "billing_code_modifiers": modifier_text,
                                            "expiration_date": expiry_text,
                                            "contract_status": "NO_STATED_EXPIRY" if expiry == date(9999, 12, 31) else "DATED",
                                            "provider_reference_id": ref_id,
                                            "additional_information": str(price.get("additional_information") or ""),
                                            "bundled_codes": bundled, "covered_services": covered,
                                            "quality_flags": "|".join(flags),
                                        }
                                        context = _json([file_id, npi, tin_type, tin, code_type, code_version,
                                                         code, item_name, description, arrangement, kind,
                                                         billing_class, setting, service, modifier_text, bundled, covered,
                                                         payload["additional_information"]])
                                        fingerprint = hashlib.sha256(_json([context, payload["rate"], expiry_text,
                                                                          payload["additional_information"]]).encode()).digest()
                                        benchmark = (arrangement == "ffs" and kind == "negotiated"
                                                     and billing_class == "professional" and code != "CSTM-00"
                                                     and service != "CSTM-00")
                                        if row_errors:
                                            decision, reason = "INVALID", ";".join(row_errors)
                                        elif not benchmark:
                                            decision, reason = "VALID_NON_BENCHMARK", "NOT_DIRECT_PROFESSIONAL_FFS_NEGOTIATED_DOLLAR"
                                        else:
                                            decision, reason = "ELIGIBLE", "PENDING_CONTEXT_SELECTION"
                                        cur = db.execute("INSERT INTO rows (context,amount,fingerprint,payload,decision,reason) VALUES (?,?,?,?,?,?)",
                                                         (context if decision == "ELIGIBLE" else None,
                                                          sortable_amount if sortable_amount is not None and math.isfinite(sortable_amount) else None,
                                                          fingerprint, _json(payload), decision, reason))
                                        if decision == "ELIGIBLE":
                                            try:
                                                db.execute("INSERT INTO seen VALUES (?,?)", (fingerprint, cur.lastrowid))
                                            except sqlite3.IntegrityError:
                                                db.execute("UPDATE rows SET decision='DUPLICATE', reason='EXACT_PUBLISHED_DUPLICATE' WHERE id=?", (cur.lastrowid,))
                                        counters["expanded_rate_rows"] += 1
                            if counters["published_prices"] % 250_000 == 0:
                                db.commit()
                                LOG.info("C4 scanned %s published prices in %s", f"{counters['published_prices']:,}", path.name)
                db.commit()
                db.execute("CREATE INDEX rows_context_amount ON rows(context,amount,id) WHERE context IS NOT NULL")
                db.execute("CREATE TEMP TABLE ranked AS SELECT id, ROW_NUMBER() OVER (PARTITION BY context ORDER BY amount,id) AS rn, COUNT(*) OVER (PARTITION BY context) AS n FROM rows WHERE decision='ELIGIBLE'")
                db.execute("CREATE INDEX ranked_id ON ranked(id)")
                db.execute("CREATE TEMP TABLE choices AS SELECT ranked.id, ranked.n, rows.context, json_extract(rows.payload,'$.source_locator') AS locator FROM ranked JOIN rows ON rows.id=ranked.id WHERE ranked.rn=(ranked.n+1)/2")
                db.execute("CREATE UNIQUE INDEX choices_id ON choices(id)")
                db.execute("CREATE UNIQUE INDEX choices_context ON choices(context)")
                db.execute("UPDATE rows SET decision='SELECTED', reason='LOWER_MEDIAN_OBSERVED_RATE_IN_EXACT_CONTEXT' WHERE id IN (SELECT id FROM choices)")
                db.execute("UPDATE rows SET decision='ALTERNATE', reason='OTHER_PUBLISHED_RATE_IN_EXACT_CONTEXT' WHERE decision='ELIGIBLE'")
                db.commit()

                decisions_tmp = Path(temporary) / "rate_decisions.csv"
                selected_tmp = Path(temporary) / "selected_rates.csv"
                with decisions_tmp.open("w", newline="", encoding="utf-8") as decision_stream, selected_tmp.open("w", newline="", encoding="utf-8") as selected_stream:
                    decisions_writer = csv.DictWriter(decision_stream, fieldnames=FIELDS)
                    selected_writer = csv.DictWriter(selected_stream, fieldnames=FIELDS)
                    decisions_writer.writeheader()
                    selected_writer.writeheader()
                    for record_json, decision, reason, selected_locator, considered in db.execute(
                            "SELECT rows.payload,rows.decision,rows.reason,choices.locator,choices.n "
                            "FROM rows LEFT JOIN choices ON rows.context=choices.context ORDER BY rows.id"):
                        record = json.loads(record_json)
                        record["decision"] = decision
                        record["decision_reason"] = "ONLY_VALID_PUBLISHED_RATE_IN_EXACT_CONTEXT" if decision == "SELECTED" and considered == 1 else reason
                        record["selected_source_locator"] = selected_locator or ""
                        record["rates_considered_count"] = considered or ""
                        counters[decision.lower()] += 1
                        decisions_writer.writerow(record)
                        if decision == "SELECTED":
                            selected_writer.writerow(record)
                summary = {
                    "source_file_id": file_id, "source_file_name": path.name,
                    "source_url": source.source_url, "sha256": sha256, "size_bytes": path.stat().st_size,
                    "as_of": self.as_of.isoformat(), "file_classification": classification,
                    "plan_attribution": attribution, "c3_quality_status": source.c3_quality_status,
                    "selection_policy": "One actual published lower-median amount per exact context; alternate tiers retained in decisions; no PPO membership inferred.",
                    "counts": dict(counters),
                }
                summary_tmp = Path(temporary) / "c4_summary.json"
                summary_tmp.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
                for name in ("rate_decisions.csv", "selected_rates.csv", "c4_summary.json"):
                    os.replace(Path(temporary) / name, output_dir / name)
                return summary
            finally:
                db.close()


def _inputs(files: Iterable[Path], manifest: Path | None, rate_dirs: Iterable[Path], c3_details: Path | None) -> list[RateFileInput]:
    c3_by_url = {}
    c3_by_name = {}
    if c3_details:
        for result in json.loads(Path(c3_details).read_text(encoding="utf-8")):
            if result.get("source_url"):
                c3_by_url[result["source_url"]] = result
            c3_by_name[result["file_name"]] = result
    inputs = [RateFileInput(Path(path)) for path in files]
    if manifest:
        with Path(manifest).open(newline="", encoding="utf-8-sig") as stream:
            for row in csv.DictReader(stream):
                name = row.get("rate_file_name") or row.get("filename")
                if not name:
                    raise ValueError("Manifest needs rate_file_name or filename")
                matches = [Path(folder) / name for folder in rate_dirs if (Path(folder) / name).is_file()]
                if len(matches) != 1:
                    raise ValueError(f"Expected one local file for {name}; found {len(matches)}")
                inputs.append(RateFileInput(matches[0], row.get("rate_file_url", ""), row.get("file_classification", "UNKNOWN")))
    if not inputs:
        raise ValueError("Provide --file or --manifest")
    enriched = []
    for entry in inputs:
        evidence = (c3_by_url.get(entry.source_url) if entry.source_url else c3_by_name.get(entry.path.name)) or {}
        if c3_details and not evidence:
            raise ValueError(f"No matching C3 result for {entry.source_url or entry.path.name}")
        enriched.append(RateFileInput(entry.path, entry.source_url, entry.file_classification,
                                      evidence.get("sha256", ""), evidence.get("quality_status", "NOT_PROVIDED")))
    return enriched


def run_files(inputs: Iterable[RateFileInput], output_dir: Path, *, as_of: date, scratch_dir: Path | None = None) -> list[dict]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    summaries = []
    ids = set()
    for source in inputs:
        file_id = hashlib.sha256((source.source_url or Path(source.path).name).encode()).hexdigest()[:16]
        if file_id in ids:
            raise ValueError(f"Duplicate C4 source identity: {source.source_url or source.path.name}")
        ids.add(file_id)
        result = RateExtractor(as_of=as_of, scratch_dir=scratch_dir).run_file(source, output_dir / file_id)
        summaries.append(result)
    manifest = output_dir / "c4_manifest.csv"
    with manifest.open("w", newline="", encoding="utf-8") as stream:
        columns = ["source_file_id", "source_file_name", "source_url", "sha256", "file_classification",
                   "plan_attribution", "c3_quality_status", "selected_rates_path", "rate_decisions_path"]
        writer = csv.DictWriter(stream, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for result in summaries:
            file_id = result["source_file_id"]
            writer.writerow({**result, "selected_rates_path": f"{file_id}/selected_rates.csv",
                             "rate_decisions_path": f"{file_id}/rate_decisions.csv"})
    return summaries


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Complete-file CMS TiC C4 rate extraction")
    parser.add_argument("--file", action="append", type=Path, default=[])
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--rate-dir", action="append", type=Path, default=[])
    parser.add_argument("--c3-details", type=Path)
    parser.add_argument("--as-of", type=date.fromisoformat, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--scratch-dir", type=Path)
    args = parser.parse_args()
    inputs = _inputs(args.file, args.manifest, args.rate_dir or ([args.manifest.parent] if args.manifest else []), args.c3_details)
    print(json.dumps(run_files(inputs, args.output_dir, as_of=args.as_of, scratch_dir=args.scratch_dir), indent=2))


if __name__ == "__main__":
    main()
