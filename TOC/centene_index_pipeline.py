"""Centene index inventory and conservative CA commercial-group PPO candidate pipeline.
Python 3.11. Install: pip install requests pandas ijson
Safe defaults: local-first, no large downloads, no large-JSON validation.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import os
import re
import sys
import tempfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urljoin, urlsplit, urlunsplit

import pandas as pd
import requests

PAGE = "https://www.centene.com/price-transparency-files.html"
TIMEOUT = (15, 120)
UA = {"User-Agent": "CenteneIndexResearch/1.0 (academic data pipeline)"}
NETWORK_RE = {n: re.compile(rf"(?<![A-Za-z]){n}(?![A-Za-z])", re.I) for n in ("PPO", "HMO", "EPO", "POS")}
RAW_COLUMNS = ["source_index", "index_brand_hint", "source_block", "source_plan_position", "source_file_position", "raw_plan_json", "raw_file_json", "raw_index_metadata_json", "plan_name", "plan_id", "plan_id_type", "market_type", "issuer_name", "plan_sponsor_name", "network_metadata", "state_metadata", "raw_url", "normalized_url", "file_description", "last_updated_on", "version"]


def compact(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def jsonstr(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, default=str)


def canonical_url(url):
    url = compact(url)
    if not url:
        return ""
    p = urlsplit(url)
    if p.scheme.lower() not in ("http", "https") or not p.netloc:
        return ""
    return urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path, p.query, ""))


def fname(url):
    return Path(unquote(urlsplit(url).path)).name if url else ""


def file_sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def atomic_text(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="", dir=path.parent, delete=False) as tmp:
        tmp.write(content)
        temp_name = tmp.name
    os.replace(temp_name, path)


def save_csv(path, rows, columns=None):
    df = pd.DataFrame(rows)
    if columns:
        for c in columns:
            if c not in df.columns:
                df[c] = ""
        df = df[list(columns) + [c for c in df.columns if c not in columns]]
    for c in df.columns:
        df[c] = df[c].map(lambda x: jsonstr(x) if isinstance(x, (dict, list)) else x)
    temp = path.with_name(path.name + ".tmp")
    df.to_csv(temp, index=False, encoding="utf-8-sig")
    os.replace(temp, path)
    return df


class JsonLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls = set()

    def handle_starttag(self, tag, attrs):
        if tag != "a":
            return
        d = dict(attrs)
        href = d.get("href", "")
        if re.search(r"_index\.json(?:\?|$)", href, re.I):
            self.urls.add(urljoin(PAGE, href))


def request_bytes(session, url):
    r = session.get(url, timeout=TIMEOUT, headers=UA)
    r.raise_for_status()
    return r.content


def source_indexes(args, session, warnings):
    """Find local *index.json files, with optional official-page discovery."""
    result = []
    if args.index:
        for val in args.index:
            if val.startswith(("https://", "http://")):
                result.append((val, None))
            else:
                path = Path(val).expanduser().resolve()
                if not path.is_file():
                    raise FileNotFoundError(f"Index input not found: {path}")
                result.append((str(path), path))
    else:
        paths = sorted(set(args.workdir.glob("*index*.json")) | set(args.workdir.glob("**/*_index.json")))
        result += [(str(p.resolve()), p.resolve()) for p in paths]
    if args.fetch_page:
        try:
            html = request_bytes(session, PAGE).decode("utf-8", errors="replace")
            parser = JsonLinks()
            parser.feed(html)
            discovered = sorted(parser.urls)
            if not discovered:
                raise ValueError("Official page contained no discoverable *_index.json links; layout may have changed")
            result += [(u, None) for u in discovered]
        except Exception as e:
            if not result:
                raise RuntimeError(f"Could not discover official indexes: {e}") from e
            warnings.append(f"Official-page index discovery failed: {e}")
    distinct = {}
    for identifier, local in result:
        distinct[identifier] = (identifier, local)
    if not distinct:
        raise RuntimeError("No local index JSON found. Supply --index PATH, or use --fetch-page to discover official indexes.")
    return list(distinct.values())


def extract_links(node):
    """Collect nested index links only (never rate-file links)."""
    found = []
    def walk(x, key=""):
        if isinstance(x, dict):
            for k, v in x.items():
                kl = k.lower()
                if isinstance(v, str) and ("index" in kl or "sub_index" in kl) and re.search(r"\.json(?:\?|$)", v, re.I):
                    found.append(v)
                else:
                    walk(v, kl)
        elif isinstance(x, list):
            for y in x:
                walk(y, key)
    walk(node)
    return found


def load_indexes(inputs, session, warnings, args):
    queue = [(ident, path, 0) for ident, path in inputs]
    done = set()
    records = []
    inventories = []
    while queue:
        src, path, depth = queue.pop(0)
        key = canonical_url(src) or str(Path(src).resolve())
        if key in done:
            continue
        done.add(key)
        if depth > args.max_index_depth:
            warnings.append(f"Index nesting depth exceeded: {src}")
            continue
        try:
            content = path.read_bytes() if path else request_bytes(session, src)
            obj = json.loads(content)
            if not isinstance(obj, dict) or not isinstance(obj.get("reporting_structure"), list):
                raise ValueError("Missing top-level reporting_structure list")
            meta = {k: v for k, v in obj.items() if k != "reporting_structure"}
            brand = fname(src).lower().replace("_index.json", "")
            inventories.append({"source_index": src, "blocks": len(obj["reporting_structure"]), "last_updated_on": obj.get("last_updated_on", ""), "version": obj.get("version", "")})
            for bi, block in enumerate(obj["reporting_structure"]):
                if not isinstance(block, dict):
                    warnings.append(f"Invalid reporting_structure block {bi} in {src}")
                    continue
                plans = block.get("reporting_plans") or []
                files = block.get("in_network_files") or []
                if not isinstance(plans, list) or not isinstance(files, list):
                    warnings.append(f"Wrong reporting_plans/in_network_files type block {bi} {src}")
                    continue
                # Preserve a plan entry even if there are no file links.
                if not plans:
                    plans = [{}]
                if not files:
                    files = [{}]
                for pi, plan in enumerate(plans):
                    if not isinstance(plan, dict):
                        continue
                    for fi, fil in enumerate(files):
                        if not isinstance(fil, dict):
                            continue
                        u = compact(fil.get("location", ""))
                        network = plan.get("network_type") or plan.get("network_name") or plan.get("network") or block.get("network_type") or ""
                        state = plan.get("state") or plan.get("market_state") or block.get("state") or ""
                        records.append({"source_index": src, "index_brand_hint": brand, "source_block": bi, "source_plan_position": pi, "source_file_position": fi,
                                        "raw_plan_json": jsonstr(plan), "raw_file_json": jsonstr(fil), "raw_index_metadata_json": jsonstr(meta),
                                        "plan_name": compact(plan.get("plan_name")), "plan_id": compact(plan.get("plan_id")),
                                        "plan_id_type": compact(plan.get("plan_id_type")), "market_type": compact(plan.get("plan_market_type")),
                                        "issuer_name": compact(plan.get("issuer_name")), "plan_sponsor_name": compact(plan.get("plan_sponsor_name")),
                                        "network_metadata": compact(network), "state_metadata": compact(state), "raw_url": u,
                                        "normalized_url": canonical_url(u), "file_description": compact(fil.get("description")),
                                        "last_updated_on": obj.get("last_updated_on", ""), "version": obj.get("version", "")})
            for sub in extract_links(obj):
                link = urljoin(src, sub) if canonical_url(src) else (str((Path(src).parent / sub).resolve()) if not canonical_url(sub) else sub)
                queue.append((link, None if canonical_url(link) else Path(link), depth + 1))
        except Exception as exc:
            warnings.append(f"Could not parse index {src}: {type(exc).__name__}: {exc}")
    if not inventories:
        raise RuntimeError("No index file parsed successfully; inspect warnings and source files.")
    return records, inventories


def classify(row):
    """Conservative evidence-based classification; never silently infer missing group/state."""
    name = row["plan_name"]
    url = row["normalized_url"]
    meta_net = row["network_metadata"]
    market = row["market_type"].lower()
    state = row["state_metadata"].upper()
    words = set(re.findall(r"[A-Z0-9]+", name.upper()))
    flags = sorted(k for k, pat in NETWORK_RE.items() if pat.search(name + " " + meta_net))
    state_name = "CA" in words or "CALIFORNIA" in words
    # Filename indicates market context, not sufficient proof of plan residency.
    state_file = bool(re.search(r"(?:^|[-_])(?:healthnet|ambetter)[-_]ca(?:[-_.]|$)", fname(url), re.I))
    state_explicit = state in {"CA", "CALIFORNIA"}
    other_state = bool(state and state not in {"CA", "CALIFORNIA"})
    market_excluded = market in {"individual", "medicaid", "medicare"}
    commercial_hint = market == "group"
    evidence = {"state_explicit": state_explicit, "state_name": state_name, "state_file_hint": state_file,
                "market": market, "network_metadata": meta_net, "network_tokens": flags, "issuer": row["issuer_name"]}
    reasons = []
    if not name or not url:
        reasons.append("MISSING_PLAN_OR_VALID_URL")
    if other_state:
        reasons.append("EXPLICIT_NON_CA_STATE")
    if market_excluded:
        reasons.append("OUT_OF_SCOPE_MARKET")
    if any(n in flags for n in ("HMO", "EPO", "POS")):
        reasons.append("CONFLICTING_OR_NON_PPO_TYPE")
    if not (state_explicit or state_name or state_file):
        reasons.append("CA_NOT_ESTABLISHED")
    if not commercial_hint:
        reasons.append("GROUP_MARKET_NOT_ESTABLISHED")
    if "PPO" not in flags:
        reasons.append("PPO_NOT_ESTABLISHED")
    if not reasons:
        return "INCLUDE", "Explicit PPO and group signals with CA evidence; verify product/network externally", "STRONG_CANDIDATE", jsonstr(evidence)
    hard = {"EXPLICIT_NON_CA_STATE", "OUT_OF_SCOPE_MARKET"}
    if hard.intersection(reasons) or ("CONFLICTING_OR_NON_PPO_TYPE" in reasons and "PPO" not in flags):
        status, strength = "EXCLUDE", "HIGH"
    else:
        status, strength = "REVIEW_REQUIRED", "LOW"
    return status, ";".join(reasons), strength, jsonstr(evidence)


def atomic_download(session, url, dest):
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    with session.get(url, headers=UA, timeout=TIMEOUT, stream=True) as resp:
        resp.raise_for_status()
        with part.open("wb") as w:
            for chunk in resp.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    w.write(chunk)
        stated = resp.headers.get("Content-Length", "")
        if stated.isdigit() and part.stat().st_size != int(stated):
            part.unlink(missing_ok=True)
            raise IOError("Download length differs from Content-Length")
    os.replace(part, dest)


def validate_json_stream(path):
    """Complete syntactic validation; bounded memory, useful top-level fields/counts."""
    try:
        import ijson
    except ImportError as exc:
        raise RuntimeError("pip install ijson (required for --validate)") from exc
    root_fields = set()
    field_hints = set()
    counts = Counter()
    keywords = ("billing_code", "negotiated_rate", "negotiated_type", "npi", "tin", "provider_reference", "provider_group", "service_code", "expiration_date", "address", "modifier")
    with path.open("rb") as f:
        for prefix, event, value in ijson.parse(f):
            if not prefix and event != "start_map":
                raise ValueError("Expected top-level JSON object")
            if prefix == "" and event == "map_key":
                root_fields.add(value)
            if event == "start_map" and prefix in ("in_network.item", "provider_references.item", "reporting_structure.item"):
                counts[prefix] += 1
            if event == "map_key" and any(k in str(value).lower() for k in keywords):
                if len(field_hints) < 40:
                    field_hints.add(str(value))
    return {"status": "PASS", "top_level_fields": jsonstr(sorted(root_fields)), "identified_field_names": jsonstr(sorted(field_hints)), "record_counts": jsonstr(dict(counts)), "error": ""}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--workdir", type=Path, default=Path.cwd())
    ap.add_argument("--output", type=Path, default=None)
    ap.add_argument("--download-dir", type=Path, default=None)
    ap.add_argument("--index", action="append", help="Local index JSON or verified index URL (repeatable)")
    ap.add_argument("--fetch-page", action="store_true", help="Discover official index links from Centene page")
    ap.add_argument("--download", action="store_true", help="Download missing in-network files (OFF by default)")
    ap.add_argument("--download-all", action="store_true", help="Include non-PPO referenced rate files in downloading (requires --download)")
    ap.add_argument("--validate", action="store_true", help="Stream-validate matched local JSON files")
    ap.add_argument("--validate-all", action="store_true", help="Validate all matched local files, not only included candidates")
    ap.add_argument("--hash", action="store_true", help="SHA-256 local files (may take time)")
    ap.add_argument("--max-index-depth", type=int, default=5)
    args = ap.parse_args()
    args.workdir = args.workdir.expanduser().resolve()
    args.output = (args.output or args.workdir / "outputs" / "centene_index_pipeline").resolve()
    args.download_dir = (args.download_dir or args.workdir / "ratefiles").resolve()
    args.output.mkdir(parents=True, exist_ok=True)
    warnings, errors = [], []
    session = requests.Session()
    sources = source_indexes(args, session, warnings)
    rows, indexes = load_indexes(sources, session, warnings, args)
    print("Input index files successfully parsed:", len(indexes))
    for inv in indexes:
        print(" ", inv["source_index"], "blocks=", inv["blocks"])
    print("Raw columns:", sorted({k for r in rows for k in json.loads(r["raw_plan_json"]).keys()}))
    print("Normalized columns:", RAW_COLUMNS)
    plan_df = save_csv(args.output / "centene_plan_index.csv", rows, RAW_COLUMNS)
    # Stable plan/file relationships: identical records in repeated blocks are collapsed.
    relations = []
    seen_rel = set()
    dup_rel = 0
    for r in rows:
        if not r["normalized_url"]:
            continue
        plan_key = (r["plan_id_type"], r["plan_id"], r["plan_name"], r["market_type"], r["issuer_name"], r["source_index"])
        relkey = (plan_key, r["normalized_url"])
        if relkey in seen_rel:
            dup_rel += 1
            continue
        seen_rel.add(relkey)
        relations.append(dict(r))
    relations.sort(key=lambda x: (x["normalized_url"], x["plan_name"], x["plan_id"]))
    save_csv(args.output / "centene_plan_file_relationships.csv", relations, RAW_COLUMNS)
    classified = []
    for r in relations:
        d, reason, strength, ev = classify(r)
        classified.append({**r, "network_classification": d, "classification_reason": reason,
                           "classification_confidence": strength, "classification_evidence": ev})
    class_cols = RAW_COLUMNS + ["network_classification", "classification_reason", "classification_confidence", "classification_evidence"]
    save_csv(args.output / "centene_plan_classification.csv", classified, class_cols)
    included = [r for r in classified if r["network_classification"] == "INCLUDE"]
    save_csv(args.output / "centene_ca_commercial_ppo_candidates.csv", included, class_cols)
    by_url = defaultdict(list)
    for r in classified:
        by_url[r["normalized_url"]].append(r)
    manifest = []
    file_checks = []
    existing = [p for folder in (args.download_dir, args.workdir) if folder.is_dir() for p in folder.iterdir() if p.is_file() and p.suffix.lower() in (".json", ".gz")]
    local_by_name = defaultdict(list)
    for p in existing:
        local_by_name[p.name.lower()].append(p)
    used_local = set()
    hash_locations = defaultdict(list)
    for url in sorted(by_url):
        rr = by_url[url]
        included_ref = any(x["network_classification"] == "INCLUDE" for x in rr)
        name = fname(url)
        paths = local_by_name.get(name.lower(), [])
        if len(paths) > 1:
            warnings.append(f"Multiple local files match name {name}; requires reconciliation")
        local = paths[0] if len(paths) == 1 else None
        status = "ALREADY_LOCAL" if local else ("AMBIGUOUS_LOCAL" if paths else "MISSING")
        if not local and args.download and (included_ref or args.download_all):
            dest = args.download_dir / name
            # Prevent accidentally writing two different URLs to the same filename.
            clash = sum(1 for u in by_url if u != url and fname(u).lower() == name.lower())
            if clash:
                dest = args.download_dir / (hashlib.sha256(url.encode()).hexdigest()[:12] + "_" + name)
            try:
                print("Downloading:", name)
                atomic_download(session, url, dest)
                local, status = dest, "DOWNLOADED"
            except Exception as exc:
                errors.append(f"Download failed {url}: {exc}")
                status = "DOWNLOAD_FAILED"
        size = local.stat().st_size if local and local.is_file() else None
        sha = file_sha256(local) if local and args.hash else ""
        if sha:
            hash_locations[sha].append(str(local))
        if local:
            used_local.add(local.resolve())
        names = sorted({r["plan_name"] for r in rr if r["plan_name"]})
        ids = sorted({r["plan_id"] for r in rr if r["plan_id"]})
        brands = sorted({r["issuer_name"] or r["index_brand_hint"] for r in rr})
        markets = sorted({r["market_type"] for r in rr})
        m = {"original_url": rr[0]["raw_url"], "normalized_url": url, "filename": name,
             "associated_plan_count": len({(r["plan_id"], r["plan_name"], r["issuer_name"]) for r in rr}),
             "associated_plan_names": jsonstr(names), "associated_plan_ids": jsonstr(ids),
             "associated_brands": jsonstr(brands), "associated_markets": jsonstr(markets),
             "has_included_ppo_candidate": included_ref, "relevant_to_target_scope": included_ref,
             "local_file_path": str(local) if local else "", "download_status": status,
             "size_bytes": size if size is not None else "", "size_mb": round(size / 1e6, 3) if size is not None else "",
             "sha256": sha, "source_update_dates": jsonstr(sorted({str(r["last_updated_on"]) for r in rr if r["last_updated_on"]})),
             "validation_status": "NOT_RUN", "validation_errors": ""}
        if local and args.validate and (included_ref or args.validate_all):
            try:
                check = validate_json_stream(local)
                m["validation_status"] = check["status"]
                file_checks.append({"file": str(local), "url": url, **check})
            except Exception as exc:
                err = f"{type(exc).__name__}: {exc}"
                m["validation_status"], m["validation_errors"] = "FAIL", err
                file_checks.append({"file": str(local), "url": url, "status": "FAIL", "top_level_fields": "", "identified_field_names": "", "record_counts": "", "error": err})
        manifest.append(m)
    unmatched = sorted(str(p) for p in existing if p.resolve() not in used_local and p.name.lower() not in {Path(i["source_index"]).name.lower() for i in indexes})
    for p in unmatched:
        file_checks.append({"file": p, "url": "", "status": "UNMATCHED_LOCAL_FILE", "top_level_fields": "", "identified_field_names": "", "record_counts": "", "error": "No uniquely matched URL"})
    duplicate_groups = [v for v in hash_locations.values() if len(v) > 1]
    save_csv(args.output / "centene_file_manifest.csv", manifest)
    save_csv(args.output / "centene_file_validation.csv", file_checks, ["file", "url", "status", "top_level_fields", "identified_field_names", "record_counts", "error"])
    stats = Counter(r["network_classification"] for r in classified)
    distinct_plans = len({(r["plan_id_type"], r["plan_id"], r["plan_name"], r["issuer_name"]) for r in rows})
    summary = {"generated_utc": datetime.now(timezone.utc).isoformat(), "working_directory": str(args.workdir),
               "input_indexes": indexes, "raw_index_entries": len(rows), "missing_plan_names": sum(not r["plan_name"] for r in rows),
               "missing_or_invalid_urls": sum(not r["normalized_url"] for r in rows), "unique_plans": distinct_plans,
               "plan_file_relationships": len(relations), "duplicate_relationship_rows": dup_rel,
               "unique_rate_urls": len(by_url), "classification_counts": dict(stats),
               "unique_included_file_urls": sum(bool(m["has_included_ppo_candidate"]) for m in manifest),
               "matched_or_downloaded_local_files": sum(m["download_status"] in ("ALREADY_LOCAL", "DOWNLOADED") for m in manifest),
               "missing_expected_files": sum(m["download_status"] == "MISSING" and m["has_included_ppo_candidate"] for m in manifest),
               "unmatched_local_files": unmatched, "identical_content_groups": duplicate_groups,
               "validated_pass": sum(c["status"] == "PASS" for c in file_checks),
               "validated_fail": sum(c["status"] == "FAIL" for c in file_checks),
               "warnings": warnings, "errors": errors,
               "output_files": sorted(p.name for p in args.output.glob("centene_*.csv"))}
    if not included:
        warnings.append("No confident CA commercial-group PPO candidates; review source fields and classification rules")
    rules = """Centene CA commercial group PPO classification (candidate discovery, NOT ground truth).
INCLUDE: valid rate URL; group market; PPO token; CA state/name/filename evidence; no HMO/EPO/POS conflict.
EXCLUDE: explicit non-CA state or individual/Medicare/Medicaid market; clear HMO/EPO/POS without PPO.
REVIEW_REQUIRED: missing/contradictory network, market, geography, name or URL evidence.
Filename CA hints do not prove a plan's state. PPO labels alone do not prove network membership.
Check included candidates against product-level metadata/provider directories before final submissions.
No source fields are invented. Source plans and raw file JSON are preserved in centene_plan_index.csv.
A file linked by multiple plans is represented once in the manifest, but every plan/file relation is retained.
Rate extraction is intentionally out of scope. JSON validation does not confirm rate correctness.
"""
    atomic_text(args.output / "centene_classification_rules.txt", rules)
    summary["warnings"] = warnings
    atomic_text(args.output / "centene_pipeline_summary.json", json.dumps(summary, indent=2, ensure_ascii=False, default=str))
    pretty = "\n".join(["CENTENE INDEX PIPELINE SUMMARY", "=" * 40] + [f"{k}: {v}" for k, v in summary.items() if k not in ("input_indexes", "warnings", "errors", "unmatched_local_files", "identical_content_groups")])
    pretty += "\nWARNINGS:\n" + "\n".join(warnings) + "\nERRORS:\n" + "\n".join(errors) + "\n"
    atomic_text(args.output / "centene_pipeline_summary.txt", pretty)
    print(pretty)
    print("All outputs:", args.output)
    if errors:
        print("Completed with errors; inspect summary.json", file=sys.stderr)


if __name__ == "__main__":
    main()
