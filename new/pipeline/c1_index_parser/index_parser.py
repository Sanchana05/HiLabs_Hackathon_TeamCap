"""Challenge C1: Centene Index Parser
Ingests, extracts, normalizes, and deduplicates Centene index / Table of Contents (TOC) files.

Features:
- Handles multi-brand Centene indexes (Health Net, Ambetter, Fidelis, QualChoice).
- Traverses nested CMS TiC reporting_structure blocks.
- Canonicalizes rate file URLs and extracts file descriptions.
- Eliminates duplicate plan-file relationships.
- Outputs clean tabular datasets meeting C1 specifications.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
from urllib.parse import unquote, urlsplit, urlunsplit

import pandas as pd
try:
    import requests
except ImportError:  # Local index ingestion does not require the optional HTTP client.
    requests = None

try:
    from pipeline.config import (
        CENTENE_BRANDS,
        CENTENE_TIC_PAGE_URL,
        HTTP_HEADERS,
        HTTP_TIMEOUT,
        RAW_INDEX_DIR,
        SEARCH_DIRECTORIES,
    )
except ImportError:
    from ..config import (
        CENTENE_BRANDS,
        CENTENE_TIC_PAGE_URL,
        HTTP_HEADERS,
        HTTP_TIMEOUT,
        RAW_INDEX_DIR,
        SEARCH_DIRECTORIES,
    )

logger = logging.getLogger(__name__)


def canonicalize_url(url: str) -> str:
    """Normalizes an HTTP/HTTPS URL by lowercasing scheme and netloc,
    stripping trailing tracking parameters, and resolving percent encoding.
    """
    if not url or not isinstance(url, str):
        return ""
    clean = url.strip()
    parsed = urlsplit(clean)
    if parsed.scheme.lower() not in ("http", "https") or not parsed.netloc:
        return ""
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path, parsed.query, ""))


def extract_filename_from_url(url: str) -> str:
    """Extracts decoded filename from URL path."""
    if not url:
        return ""
    path = urlsplit(url).path
    return Path(unquote(path)).name


def detect_brand_from_context(source_name: str, plan_name: str = "", url: str = "") -> str:
    """Determines the operating Centene brand using index filename, plan name, and URL tokens."""
    combined = f"{source_name} {plan_name} {url}".lower()
    if "healthnet" in combined or "health net" in combined:
        return "healthnet"
    if "ambetter" in combined:
        return "ambetter"
    if "fidelis" in combined:
        return "fidelis"
    if "qualchoice" in combined:
        return "qualchoice"
    return "centene_corporate"


class CenteneIndexParser:
    """Parser for Centene Table of Contents (TOC) / Index JSON files."""

    def __init__(self, raw_index_dir: Optional[Path] = None):
        self.raw_index_dir = raw_index_dir or RAW_INDEX_DIR
        self.raw_records: List[Dict] = []
        self.index_inventories: List[Dict] = []
        self.warnings: List[str] = []

    def discover_local_index_files(self) -> List[Path]:
        """Discovers local index JSON files across designated search directories."""
        found = set()
        for s_dir in SEARCH_DIRECTORIES:
            if not s_dir.exists():
                continue
            for p in s_dir.glob("*index*.json"):
                if p.is_file():
                    found.add(p.resolve())
            for p in s_dir.glob("**/*_index.json"):
                if p.is_file():
                    found.add(p.resolve())
        return sorted(found)

    def discover_official_index_urls(self, session: Optional[requests.Session] = None) -> List[str]:
        """Scrapes Centene's official price transparency landing page to find active index URLs."""
        if requests is None:
            raise RuntimeError("Online index discovery requires the requests package")
        s = session or requests.Session()
        discovered = set()
        try:
            logger.info("Scanning Centene price transparency portal: %s", CENTENE_TIC_PAGE_URL)
            resp = s.get(CENTENE_TIC_PAGE_URL, headers=HTTP_HEADERS, timeout=HTTP_TIMEOUT)
            resp.raise_for_status()
            html = resp.text
            matches = re.findall(r'href=["\']([^"\']*_index\.json[^"\']*)["\']', html, re.I)
            for m in matches:
                if m.startswith("http"):
                    discovered.add(canonicalize_url(m))
                else:
                    from urllib.parse import urljoin
                    discovered.add(canonicalize_url(urljoin(CENTENE_TIC_PAGE_URL, m)))
            logger.info("Discovered %d official index URLs on landing page", len(discovered))
        except Exception as exc:
            msg = f"Failed to discover online index files: {exc}"
            logger.warning(msg)
            self.warnings.append(msg)
        return sorted(discovered)

    def parse_index_file(self, file_path_or_url: str | Path, content_bytes: Optional[bytes] = None) -> List[Dict]:
        """Parses a single Centene TiC index JSON file and extracts all plan-to-file relationships.

        Returns list of extracted raw records.
        """
        source_str = str(file_path_or_url)
        source_name = Path(source_str).name
        logger.info("Parsing index file: %s", source_name)

        if content_bytes is None:
            if isinstance(file_path_or_url, Path) or Path(source_str).is_file():
                content_bytes = Path(source_str).read_bytes()
            else:
                if requests is None:
                    raise RuntimeError("Remote index ingestion requires the requests package")
                resp = requests.get(source_str, headers=HTTP_HEADERS, timeout=HTTP_TIMEOUT)
                resp.raise_for_status()
                content_bytes = resp.content

        try:
            data = json.loads(content_bytes.decode("utf-8", errors="replace"))
        except Exception as exc:
            err = f"JSON decode failed for {source_name}: {exc}"
            logger.error(err)
            self.warnings.append(err)
            return []

        if not isinstance(data, dict) or "reporting_structure" not in data:
            err = f"Index file {source_name} lacks top-level 'reporting_structure' array."
            logger.error(err)
            self.warnings.append(err)
            return []

        reporting_structure = data.get("reporting_structure", [])
        last_updated_on = str(data.get("last_updated_on", ""))
        version = str(data.get("version", ""))

        self.index_inventories.append({
            "source": source_name,
            "blocks_count": len(reporting_structure),
            "last_updated_on": last_updated_on,
            "version": version
        })

        extracted_rows: List[Dict] = []
        for block_idx, block in enumerate(reporting_structure):
            if not isinstance(block, dict):
                continue

            plans = block.get("reporting_plans", [])
            files = block.get("in_network_files", [])

            # Handle edge cases where plans or files are empty
            if not plans:
                plans = [{}]
            if not files:
                files = [{}]

            for plan_idx, plan in enumerate(plans):
                plan_name = str(plan.get("plan_name") or "").strip()
                plan_id = str(plan.get("plan_id") or "").strip()
                plan_id_type = str(plan.get("plan_id_type") or "").strip()
                market_type = str(plan.get("plan_market_type") or "").strip()
                issuer_name = str(plan.get("issuer_name") or "").strip()
                plan_sponsor_name = str(plan.get("plan_sponsor_name") or "").strip()

                for file_idx, f_info in enumerate(files):
                    raw_url = str(f_info.get("location") or "").strip()
                    clean_url = canonicalize_url(raw_url)
                    file_desc = str(f_info.get("description") or "").strip()

                    brand = detect_brand_from_context(source_name, plan_name, clean_url)

                    row = {
                        "source_index": source_name,
                        "brand": brand,
                        "block_index": block_idx,
                        "plan_position": plan_idx,
                        "file_position": file_idx,
                        "plan_name": plan_name,
                        "plan_id": plan_id,
                        "plan_id_type": plan_id_type,
                        "market_type": market_type,
                        "issuer_name": issuer_name,
                        "plan_sponsor_name": plan_sponsor_name,
                        "rate_file_url": clean_url,
                        "raw_rate_file_url": raw_url,
                        "rate_file_name": extract_filename_from_url(clean_url),
                        "file_description": file_desc,
                        "last_updated_on": last_updated_on,
                        "index_version": version
                    }
                    extracted_rows.append(row)

        self.raw_records.extend(extracted_rows)
        logger.info("Extracted %d plan-file records from %s", len(extracted_rows), source_name)
        return extracted_rows

    def build_deduplicated_plan_table(self) -> pd.DataFrame:
        """Challenge C1 Deliverable:
        Parse Centene's index files into one table:
        columns: brand, plan name, plan ID, market type, rate file URL.
        Many plans point to the same file, so remove duplicates.
        """
        columns = ["brand", "plan_name", "plan_id", "plan_id_type", "market_type",
                   "issuer_name", "plan_sponsor_name", "rate_file_url", "rate_file_name",
                   "source_index", "source_indexes", "block_index", "last_updated_on", "index_version"]
        if not self.raw_records:
            return pd.DataFrame(columns=columns)

        df = pd.DataFrame(self.raw_records)

        # Standardize and filter valid URLs
        valid_df = df[df["rate_file_url"] != ""].copy()

        # A sponsor EIN is not a product key. Preserve each exact plan-file edge
        # and its identifier type, while retaining every source that reported it.
        edge_cols = ["brand", "plan_name", "plan_id", "plan_id_type", "market_type", "rate_file_url"]
        valid_df = valid_df.sort_values(["source_index", "block_index", "plan_position", "file_position"])
        sources = valid_df.groupby(edge_cols, dropna=False, sort=False)["source_index"].agg(
            lambda values: "|".join(sorted(set(values)))
        ).rename("source_indexes")
        dedup_df = valid_df.drop_duplicates(edge_cols).set_index(edge_cols).join(sources).reset_index()
        dedup_df = dedup_df[columns].reset_index(drop=True)

        logger.info(
            "C1 Table Generated: %d total raw entries -> %d deduplicated plan-file relationships",
            len(self.raw_records),
            len(dedup_df)
        )
        return dedup_df

    def get_unique_rate_files_summary(self) -> pd.DataFrame:
        """Summarizes all unique rate file URLs discovered across the index files,
        including associated plan count, associated brands, and market types.
        """
        if not self.raw_records:
            return pd.DataFrame()

        df = pd.DataFrame(self.raw_records)
        grouped = df.groupby("rate_file_url").agg(
            filename=("rate_file_name", "first"),
            associated_plan_count=("plan_name", "nunique"),
            brands=("brand", lambda s: sorted(set(s))),
            market_types=("market_type", lambda s: sorted(set(filter(None, s)))),
            sample_plans=("plan_name", lambda s: sorted(set(filter(None, s)))[:5])
        ).reset_index()

        return grouped
