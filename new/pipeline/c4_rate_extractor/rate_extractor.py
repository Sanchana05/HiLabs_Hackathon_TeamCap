"""Challenge C4: Rate Extractor & Multi-Rate Conflict Resolver
Streams CMS TiC in-network rate files, unpacks provider groups into individual NPIs,
and applies deterministic, defensible selection rules to resolve multi-rate conflicts.
"""
from __future__ import annotations

import csv
import gzip
import io
import json
import logging
from collections import defaultdict
from pathlib import Path
from typing import Dict, Generator, Iterable, List, Optional, Set, Tuple

import pandas as pd

try:
    from pipeline.config import BENCHMARK_CODES, RATEFILES_DIR
except ImportError:
    from ..config import BENCHMARK_CODES, RATEFILES_DIR

logger = logging.getLogger(__name__)


class RateExtractor:
    """Streams and extracts provider-level rates from CMS TiC In-Network JSON files."""

    def __init__(
        self,
        target_codes: Optional[Set[str]] = None,
        max_records_per_code: Optional[int] = None
    ):
        # Default to all benchmark codes if not specified
        self.target_codes = target_codes if target_codes is not None else set(BENCHMARK_CODES.keys())
        self.max_records_per_code = max_records_per_code
        self.extraction_stats = {
            "total_items_scanned": 0,
            "target_code_items_found": 0,
            "raw_provider_rates_extracted": 0,
            "conflicts_resolved": 0
        }

    def _open_file(self, file_path: Path):
        """Opens normal or gzipped JSON file."""
        if str(file_path).endswith(".gz"):
            return gzip.open(file_path, "rb")
        return open(file_path, "rb")

    def load_provider_references(self, file_path: Path) -> Dict[int, List[Dict]]:
        """Pass 1: Pre-loads provider references if the file uses indirect provider grouping."""
        refs: Dict[int, List[Dict]] = {}
        try:
            import ijson
        except ImportError:
            logger.warning("ijson not installed; provider reference streaming unavailable.")
            return refs

        logger.info("Pass 1: Scanning provider_references in %s", file_path.name)
        try:
            with self._open_file(file_path) as f:
                for pr in ijson.items(f, "provider_references.item"):
                    group_id = pr.get("provider_group_id")
                    if group_id is not None:
                        refs[group_id] = pr.get("provider_groups", [])
            logger.info("Loaded %d provider reference groups from %s", len(refs), file_path.name)
        except Exception as exc:
            logger.warning("Provider references pass encountered: %s", exc)
        return refs

    def stream_raw_rates(
        self,
        file_path: Path,
        provider_refs: Optional[Dict[int, List[Dict]]] = None
    ) -> Generator[Dict, None, None]:
        """Pass 2: Streams in-network items, applies early code filtering,
        unpacks provider groups to individual NPIs, and yields raw provider rate records.
        """
        refs = provider_refs if provider_refs is not None else self.load_provider_references(file_path)

        try:
            import ijson
        except ImportError:
            raise RuntimeError("ijson library is required for high-volume TiC streaming.")

        logger.info("Pass 2: Streaming negotiated rates for %d target codes from %s",
                    len(self.target_codes), file_path.name)

        code_record_counts = defaultdict(int)

        with self._open_file(file_path) as f:
            for item in ijson.items(f, "in_network.item"):
                self.extraction_stats["total_items_scanned"] += 1
                code = str(item.get("billing_code", "")).strip()

                # Early filtering: Skip codes not in target benchmark set
                if self.target_codes and code not in self.target_codes:
                    continue

                if self.max_records_per_code and code_record_counts[code] >= self.max_records_per_code:
                    continue

                self.extraction_stats["target_code_items_found"] += 1
                billing_code_type = str(item.get("billing_code_type", "")).strip()
                description = str(item.get("description", "")).strip()

                for nr in item.get("negotiated_rates", []):
                    # Combine direct provider groups and dereferenced groups
                    groups = list(nr.get("provider_groups", []))
                    for rid in nr.get("provider_references", []):
                        if rid in refs:
                            groups.extend(refs[rid])

                    # Extract price structures
                    for pr in nr.get("negotiated_prices", []):
                        raw_rate = pr.get("negotiated_rate")
                        try:
                            rate = float(raw_rate)
                        except (ValueError, TypeError):
                            continue

                        # Filter out invalid $0 or negative rates early
                        if rate <= 0.01:
                            continue

                        neg_type = str(pr.get("negotiated_type", "fee for service")).strip()
                        billing_class = str(pr.get("billing_class", "professional")).strip().lower()
                        service_codes = pr.get("service_code", [])
                        if isinstance(service_codes, str):
                            service_codes = [service_codes]
                        exp_date = str(pr.get("expiration_date", "")).strip()

                        # UNPACK individual NPIs from each provider group
                        for group in groups:
                            tin_obj = group.get("tin", {})
                            tin_val = str(tin_obj.get("value", "") if isinstance(tin_obj, dict) else tin_obj).strip()
                            npi_list = group.get("npi", [])

                            for npi in npi_list:
                                npi_str = str(npi).strip()
                                if not npi_str:
                                    continue

                                record = {
                                    "npi": npi_str,
                                    "tin": tin_val,
                                    "billing_code": code,
                                    "billing_code_type": billing_code_type,
                                    "description": description,
                                    "rate": rate,
                                    "negotiated_type": neg_type,
                                    "billing_class": billing_class,
                                    "service_codes": "|".join(service_codes) if service_codes else "11",
                                    "expiration_date": exp_date
                                }
                                self.extraction_stats["raw_provider_rates_extracted"] += 1
                                code_record_counts[code] += 1
                                yield record

    def resolve_multi_rate_conflicts(self, raw_rates_df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict]:
        """Challenge C4 Core Requirement:
        Where a provider has several rates for one code, state WHICH ONE YOU KEEP AND WHY.

        Selection Rules Applied (Hierarchical Precedence):
        1. Billing Class Priority: Prioritize 'professional' over 'institutional' for individual
           provider rate benchmarking (excludes facility overhead).
        2. Place of Service (POS) Priority: Prioritize POS 11 (Office / Non-facility) over
           POS 21/22 (Inpatient/Outpatient hospital facility rates).
        3. Contract Freshness: Prioritize active / latest expiration date.
        4. Tiebreaker: If multiple valid rates remain under the same class/setting, select the
           MEDIAN rate across tiers to mitigate contractual outliers.

        Returns:
            resolved_df: Curated DataFrame with one rate per (NPI, TIN, billing_code).
            audit_summary: Statistics on conflicts resolved and rules applied.
        """
        if raw_rates_df.empty:
            return pd.DataFrame(), {}

        logger.info("Resolving multi-rate conflicts across %d raw records...", len(raw_rates_df))

        # Sort keys to enforce deterministic precedence
        # 1. Billing class: 'professional' first, then 'institutional'
        raw_rates_df["is_professional"] = raw_rates_df["billing_class"].str.contains("prof", case=False).astype(int)
        # 2. Service code: '11' (Office) first
        raw_rates_df["is_office_pos"] = raw_rates_df["service_codes"].str.contains("11").astype(int)
        # 3. Clean expiration date for sorting
        raw_rates_df["exp_sort"] = raw_rates_df["expiration_date"].fillna("")

        conflict_stats = {
            "total_raw_pairs": len(raw_rates_df),
            "unique_provider_code_tuples": raw_rates_df.groupby(["npi", "tin", "billing_code"]).ngroups,
            "records_with_multiple_rates": 0,
            "professional_preference_applied": 0,
            "office_pos_preference_applied": 0,
            "freshness_preference_applied": 0,
            "median_tiebreaker_applied": 0
        }

        resolved_records = []
        grouped = raw_rates_df.groupby(["npi", "tin", "billing_code"])

        for (npi, tin, code), group in grouped:
            if len(group) == 1:
                # No conflict
                rec = group.iloc[0].to_dict()
                rec["selection_rationale"] = "UNIQUE_RATE: Single active rate published for provider/code."
                rec["rates_considered_count"] = 1
                resolved_records.append(rec)
                continue

            conflict_stats["records_with_multiple_rates"] += 1
            rates_count = len(group)

            # Step 1: Billing Class Filter (Professional > Institutional)
            if group["is_professional"].nunique() > 1:
                group = group[group["is_professional"] == 1]
                conflict_stats["professional_preference_applied"] += 1
                step1_reason = "Selected 'professional' billing class over institutional facility rate."
            else:
                step1_reason = "Uniform billing class."

            if len(group) == 1:
                rec = group.iloc[0].to_dict()
                rec["selection_rationale"] = f"CONFLICT_RESOLVED: {step1_reason}"
                rec["rates_considered_count"] = rates_count
                resolved_records.append(rec)
                continue

            # Step 2: Place of Service Filter (Office POS 11 > Facility)
            if group["is_office_pos"].nunique() > 1:
                group = group[group["is_office_pos"] == 1]
                conflict_stats["office_pos_preference_applied"] += 1
                step2_reason = "Selected Office (POS 11) ambulatory rate over hospital facility rate."
            else:
                step2_reason = "Uniform service code setting."

            if len(group) == 1:
                rec = group.iloc[0].to_dict()
                rec["selection_rationale"] = f"CONFLICT_RESOLVED: {step1_reason} {step2_reason}"
                rec["rates_considered_count"] = rates_count
                resolved_records.append(rec)
                continue

            # Step 3: Contract Freshness / Latest Expiration
            if group["exp_sort"].nunique() > 1:
                latest_exp = group["exp_sort"].max()
                group = group[group["exp_sort"] == latest_exp]
                conflict_stats["freshness_preference_applied"] += 1
                step3_reason = f"Selected latest active contract schedule (exp: {latest_exp})."
            else:
                step3_reason = "Identical expiration dates."

            if len(group) == 1:
                rec = group.iloc[0].to_dict()
                rec["selection_rationale"] = f"CONFLICT_RESOLVED: {step1_reason} {step2_reason} {step3_reason}"
                rec["rates_considered_count"] = rates_count
                resolved_records.append(rec)
                continue

            # Step 4: Final Tiebreaker -> Median Rate across remaining tiers
            # Prevents outlier distortion while delivering a single representative benchmark rate
            median_val = float(group["rate"].median())
            conflict_stats["median_tiebreaker_applied"] += 1

            # Pick the row closest to median
            closest_idx = (group["rate"] - median_val).abs().idxmin()
            rec = group.loc[closest_idx].to_dict()
            rec["rate"] = median_val
            rec["selection_rationale"] = (
                f"CONFLICT_RESOLVED: Multiple active tiers found ({rates_count} rates). "
                f"Filtered by {step1_reason} {step2_reason} and selected MEDIAN rate (${median_val:.2f}) "
                f"to eliminate tier outliers."
            )
            rec["rates_considered_count"] = rates_count
            resolved_records.append(rec)

        resolved_df = pd.DataFrame(resolved_records)
        logger.info(
            "Conflict Resolution Complete: %d raw records reduced to %d distinct (NPI, TIN, Code) rates.",
            len(raw_rates_df), len(resolved_df)
        )
        return resolved_df, conflict_stats
