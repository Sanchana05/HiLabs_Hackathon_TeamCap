"""Challenge C3: PTD File Quality & Completeness Grader
Evaluates Price Transparency Data (PTD) machine-readable files across 7 mathematical dimensions:
1. Code Coverage (S_code)
2. Provider Coverage (S_prov)
3. Zero & Placeholder Penalty (S_zero)
4. Rate Type Validity (S_type)
5. Outlier & Clinical Reasonableness (S_outlier)
6. Contract Freshness & Staleness (S_fresh)
7. Duplicate Collision Penalty (S_dup)

Produces a weighted Composite File Quality Score (FQS) from 0 to 100 with letter grades.
"""
from __future__ import annotations

import json
import logging
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

try:
    from pipeline.config import BENCHMARK_CODES, QUALITY_METRIC_WEIGHTS
except ImportError:
    from ..config import BENCHMARK_CODES, QUALITY_METRIC_WEIGHTS

logger = logging.getLogger(__name__)


class FileQualityGrader:
    """Grades PTD rate files for completeness, accuracy, and contracting reliability."""

    def __init__(self, weights: Optional[Dict[str, float]] = None):
        self.weights = weights or QUALITY_METRIC_WEIGHTS
        # Ensure weights normalize to 1.0
        total_w = sum(self.weights.values())
        if not math.isclose(total_w, 1.0, rel_tol=1e-3):
            self.weights = {k: v / total_w for k, v in self.weights.items()}

    def grade_extracted_rates(
        self,
        rates_df: pd.DataFrame,
        file_metadata: Optional[Dict] = None,
        expected_npi_benchmark: int = 5000
    ) -> Dict:
        """Evaluates an extracted rate dataframe and returns detailed dimension scores and composite FQS.

        Args:
            rates_df: DataFrame containing extracted rates. Expected columns include:
                      'billing_code', 'rate', 'npi', 'tin', 'negotiated_type',
                      'billing_class', 'expiration_date' (optional).
            file_metadata: Dict with metadata like 'last_updated_on', 'filename', etc.
            expected_npi_benchmark: Estimated baseline active NPI count for commercial group PPO.

        Returns:
            Dictionary containing metrics, sub-scores, composite FQS, letter grade, and diagnostic notes.
        """
        if rates_df.empty:
            return {
                "file_name": file_metadata.get("filename", "unknown") if file_metadata else "unknown",
                "composite_fqs": 0.0,
                "grade": "F",
                "status": "UNUSABLE_EMPTY",
                "metrics": {},
                "diagnostics": ["Rate dataset is completely empty."]
            }

        file_meta = file_metadata or {}
        n_total = len(rates_df)
        diagnostics = []

        # -------------------------------------------------------------
        # 1. Code Coverage (S_code): Weight 20%
        # -------------------------------------------------------------
        present_codes = set(rates_df["billing_code"].dropna().astype(str).str.strip())
        weighted_code_cov = 0.0
        total_bench_w = sum(b["weight"] for b in BENCHMARK_CODES.values())

        for code, b_info in BENCHMARK_CODES.items():
            if code in present_codes:
                weighted_code_cov += b_info["weight"]

        s_code = round((weighted_code_cov / total_bench_w) * 100.0, 2)
        missing_bench_codes = [c for c in BENCHMARK_CODES if c not in present_codes]
        if missing_bench_codes:
            diagnostics.append(f"Missing {len(missing_bench_codes)} key benchmark codes: {missing_bench_codes[:5]}")

        # -------------------------------------------------------------
        # 2. Provider Coverage (S_prov): Weight 20%
        # -------------------------------------------------------------
        unique_npis = rates_df["npi"].dropna().nunique() if "npi" in rates_df.columns else 0
        unique_tins = rates_df["tin"].dropna().nunique() if "tin" in rates_df.columns else 0

        # Saturation relative to commercial target benchmark
        prov_ratio = unique_npis / max(1, expected_npi_benchmark)
        s_prov = round(min(100.0, prov_ratio * 100.0), 2)
        if unique_npis < 500:
            diagnostics.append(f"Low NPI count ({unique_npis}); provider breadth may be limited.")

        # -------------------------------------------------------------
        # 3. Zero-Rate & Dummy Placeholder Cleanliness (S_zero): Weight 20%
        # -------------------------------------------------------------
        numeric_rates = pd.to_numeric(rates_df["rate"], errors="coerce").fillna(0.0)
        zero_or_sub_rates = (numeric_rates <= 0.01).sum()
        garbage_high_rates = (numeric_rates >= 100000.0).sum()
        total_invalid_rates = zero_or_sub_rates + garbage_high_rates

        ratio_invalid_rates = total_invalid_rates / max(1, n_total)
        # Heavy penalty slope: 5% invalid rates drops score by 25 points
        s_zero = round(max(0.0, 100.0 * (1.0 - 5.0 * ratio_invalid_rates)), 2)
        if ratio_invalid_rates > 0.02:
            diagnostics.append(f"Detected {ratio_invalid_rates:.2%} zero/placeholder rates ({total_invalid_rates} rows).")

        # -------------------------------------------------------------
        # 4. Negotiated Rate Type Validity (S_type): Weight 15%
        # -------------------------------------------------------------
        if "negotiated_type" in rates_df.columns:
            types = rates_df["negotiated_type"].astype(str).str.lower().str.strip()
            ffs_count = (types.str.contains("fee") | types.str.contains("negotiated")).sum()
            s_type = round((ffs_count / max(1, n_total)) * 100.0, 2)
        else:
            s_type = 90.0  # Assumed standard if field omitted

        # -------------------------------------------------------------
        # 5. Rate Outlier & Clinical Reasonableness (S_outlier): Weight 10%
        # -------------------------------------------------------------
        valid_rates = numeric_rates[(numeric_rates > 0.01) & (numeric_rates < 100000.0)]
        if len(valid_rates) > 20:
            q25 = valid_rates.quantile(0.25)
            q75 = valid_rates.quantile(0.75)
            iqr = q75 - q25
            lower_bound = max(1.0, q25 - 1.5 * iqr)
            upper_bound = q75 + 1.5 * iqr
            outlier_count = ((valid_rates < lower_bound) | (valid_rates > upper_bound)).sum()
            ratio_outlier = outlier_count / max(1, len(valid_rates))
            s_outlier = round(max(0.0, 100.0 * (1.0 - 2.0 * ratio_outlier)), 2)
        else:
            s_outlier = 85.0

        # -------------------------------------------------------------
        # 6. Contract Freshness & Staleness (S_fresh): Weight 10%
        # -------------------------------------------------------------
        last_updated_str = file_meta.get("last_updated_on", "")
        days_stale = 30
        if last_updated_str:
            try:
                up_dt = datetime.fromisoformat(last_updated_str.replace("Z", "+00:00"))
                now = datetime.now(timezone.utc)
                days_stale = (now - up_dt).days
            except Exception:
                days_stale = 45

        # Penalize if older than 60 days
        staleness_penalty = max(0.0, (days_stale - 30) * 0.5)
        s_fresh = round(max(0.0, min(100.0, 100.0 - staleness_penalty)), 2)
        if days_stale > 60:
            diagnostics.append(f"File contract data is {days_stale} days old; exceeds 30-day TiC mandate.")

        # -------------------------------------------------------------
        # 7. Duplicate Collision Penalty (S_dup): Weight 5%
        # -------------------------------------------------------------
        dup_cols = [c for c in ["npi", "tin", "billing_code", "rate"] if c in rates_df.columns]
        if len(dup_cols) >= 3:
            duplicate_count = rates_df.duplicated(subset=dup_cols).sum()
            ratio_dup = duplicate_count / max(1, n_total)
            s_dup = round(max(0.0, 100.0 * (1.0 - 3.0 * ratio_dup)), 2)
            if ratio_dup > 0.05:
                diagnostics.append(f"Duplicate rate collisions detected: {ratio_dup:.2%} ({duplicate_count} rows).")
        else:
            s_dup = 95.0

        # -------------------------------------------------------------
        # Composite File Quality Score (FQS)
        # -------------------------------------------------------------
        composite_fqs = round(
            self.weights["code_coverage"] * s_code
            + self.weights["provider_coverage"] * s_prov
            + self.weights["zero_rate_penalty"] * s_zero
            + self.weights["rate_type_validity"] * s_type
            + self.weights["outlier_control"] * s_outlier
            + self.weights["contract_freshness"] * s_fresh
            + self.weights["duplicate_penalty"] * s_dup,
            2
        )

        # Assign Letter Grade
        if composite_fqs >= 85.0:
            grade = "A"
            quality_desc = "Institutional / Production Grade"
        elif composite_fqs >= 70.0:
            grade = "B"
            quality_desc = "Good / Usable with Filtering"
        elif composite_fqs >= 50.0:
            grade = "C"
            quality_desc = "Fair / Requires Substantial Cleansing"
        else:
            grade = "F"
            quality_desc = "Poor / High Risk of Spurious Rates"

        return {
            "file_name": file_meta.get("filename", "unknown"),
            "composite_fqs": composite_fqs,
            "grade": grade,
            "quality_status": quality_desc,
            "total_rates_evaluated": n_total,
            "unique_npis": unique_npis,
            "unique_tins": unique_tins,
            "dimension_scores": {
                "S_code_coverage": s_code,
                "S_provider_coverage": s_prov,
                "S_zero_rate_cleanliness": s_zero,
                "S_rate_type_validity": s_type,
                "S_outlier_control": s_outlier,
                "S_contract_freshness": s_fresh,
                "S_duplicate_cleanliness": s_dup
            },
            "metric_weights": self.weights,
            "diagnostics": diagnostics
        }
