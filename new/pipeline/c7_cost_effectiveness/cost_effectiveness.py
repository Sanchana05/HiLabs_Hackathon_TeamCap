"""Challenge C7: Cost Effectiveness Benchmarking Engine
Evaluates whether a provider is cost-effective relative to similar peers.

Definitions:
- Similar Providers: Same clinical specialty (NUCC) within the same geographic market/state,
  operating under professional non-facility billing.
- Core Metrics:
  1. Specialty Price Index (SPI): Volume-weighted ratio vs market median.
  2. Peer Percentile Rank: Relative cost ranking within clinical specialty.
  3. Net Savings Opportunity (NSO): Quantified reduction if rates renegotiated to median.
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

try:
    from pipeline.config import BENCHMARK_CODES
except ImportError:
    from ..config import BENCHMARK_CODES

logger = logging.getLogger(__name__)


class CostEffectivenessEngine:
    """Computes payer contracting cost-effectiveness metrics across provider peer groups."""

    def __init__(self, benchmark_weights: Optional[Dict[str, Dict]] = None):
        self.code_weights = benchmark_weights or BENCHMARK_CODES

    def get_code_weight(self, code: str) -> float:
        """Retrieves economic volume weight for a billing code."""
        info = self.code_weights.get(code, {})
        return float(info.get("weight", 0.05))

    def evaluate_cost_effectiveness(self, rate_dataset: pd.DataFrame) -> pd.DataFrame:
        """Calculates cost-effectiveness metrics for every provider in the dataset.

        Args:
            rate_dataset: DataFrame containing columns:
                          ['NPI', 'TIN', 'Address', 'Billing Code', 'Specialty', 'Rate']

        Returns:
            DataFrame enriched with:
            ['Peer_Median_Rate', 'Code_Weight', 'SPI', 'Peer_Percentile', 'Cost_Tier', 'Savings_Opportunity']
        """
        if rate_dataset.empty:
            return pd.DataFrame()

        df = rate_dataset.copy()
        df["Rate"] = pd.to_numeric(df["Rate"], errors="coerce")
        df["Code_Weight"] = df["Billing Code"].apply(self.get_code_weight)

        # 1. Calculate Market Peer Median for each (Specialty, Billing Code)
        # Defines 'Similar': Same clinical specialty practicing in California
        logger.info("Computing peer medians across specialty peer groups...")
        peer_medians = df.groupby(["Specialty", "Billing Code"])["Rate"].median().reset_index()
        peer_medians.rename(columns={"Rate": "Peer_Median_Rate"}, inplace=True)

        df = df.merge(peer_medians, on=["Specialty", "Billing Code"], how="left")

        # 2. Compute Specialty Price Index (SPI) per Provider (NPI + TIN)
        # SPI = sum(w * Rate) / sum(w * Peer_Median_Rate)
        grouped = df.groupby(["NPI", "TIN", "Specialty"])
        provider_summaries = []

        for (npi, tin, specialty), group in grouped:
            weighted_actual = (group["Rate"] * group["Code_Weight"]).sum()
            weighted_median = (group["Peer_Median_Rate"] * group["Code_Weight"]).sum()

            if weighted_median > 0:
                spi = round(weighted_actual / weighted_median, 3)
            else:
                spi = 1.0

            # Potential savings if rates above median are reduced to median
            savings = max(0.0, weighted_actual - weighted_median)

            provider_summaries.append({
                "NPI": npi,
                "TIN": tin,
                "Specialty": specialty,
                "Codes_Evaluated": len(group),
                "Weighted_Rate_Score": round(weighted_actual, 2),
                "Peer_Median_Score": round(weighted_median, 2),
                "SPI": spi,
                "Savings_Opportunity_Index": round(savings, 2)
            })

        prov_df = pd.DataFrame(provider_summaries)

        # 3. Compute Specialty Peer Percentile Rank within each Specialty
        prov_df["Specialty_Peer_Percentile"] = prov_df.groupby("Specialty")["SPI"].rank(pct=True).round(2) * 100.0

        # 4. Assign Cost Effectiveness Tier
        def assign_tier(row):
            pct = row["Specialty_Peer_Percentile"]
            spi = row["SPI"]
            if spi <= 0.90 or pct <= 33.0:
                return "Tier 1: Highly Cost-Effective (Below Market Median)"
            elif spi <= 1.10 or pct <= 66.0:
                return "Tier 2: Market Parity (Competitive)"
            else:
                return "Tier 3: High Cost (Contract Renegotiation Target)"

        prov_df["Cost_Effectiveness_Tier"] = prov_df.apply(assign_tier, axis=1)

        logger.info(
            "Cost Effectiveness Analysis Complete: %d providers evaluated across %d specialties.",
            len(prov_df), prov_df["Specialty"].nunique()
        )
        return prov_df
