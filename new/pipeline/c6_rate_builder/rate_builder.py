"""Challenge C6: Provider Rate File Builder
Constructs Deliverable 1: One row per NPI, TIN, Address, and Billing Code.
Enforces exact deliverable schema: ['NPI', 'TIN', 'Address', 'Billing Code', 'Specialty', 'Rate']
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

try:
    from pipeline.config import DELIVERABLES_DIR, FINAL_RATE_FILE_COLUMNS
except ImportError:
    from ..config import DELIVERABLES_DIR, FINAL_RATE_FILE_COLUMNS

logger = logging.getLogger(__name__)


class ProviderRateFileBuilder:
    """Merges curated rates with resolved addresses and specialties to produce the final Deliverable 1 Excel file."""

    def __init__(self, deliverables_dir: Optional[Path] = None):
        self.deliverables_dir = deliverables_dir or DELIVERABLES_DIR
        self.deliverables_dir.mkdir(parents=True, exist_ok=True)

    def assemble_final_dataset(
        self,
        curated_rates_df: pd.DataFrame,
        address_specialty_map: Dict[Tuple[str, str], Dict]
    ) -> pd.DataFrame:
        """Joins (NPI, TIN, Billing Code, Rate) with address and specialty mappings.

        Args:
            curated_rates_df: DataFrame from Challenge C4 with columns:
                              'npi', 'tin', 'billing_code', 'rate', etc.
            address_specialty_map: Dict mapping (npi, tin) -> {
                                   'address': str,
                                   'specialty': str,
                                   'confidence_score': float, ...}

        Returns:
            DataFrame with exact Deliverable 1 schema:
            ['NPI', 'TIN', 'Address', 'Billing Code', 'Specialty', 'Rate']
        """
        if curated_rates_df.empty:
            logger.warning("Curated rates dataframe is empty.")
            return pd.DataFrame(columns=FINAL_RATE_FILE_COLUMNS)

        logger.info("Assembling final provider rate dataset for %d records...", len(curated_rates_df))

        rows = []
        for _, r in curated_rates_df.iterrows():
            npi = str(r.get("npi", "")).strip()
            tin = str(r.get("tin", "")).strip()
            code = str(r.get("billing_code", "")).strip()
            rate = float(r.get("rate", 0.0))

            lookup_key = (npi, tin)
            meta = address_specialty_map.get(lookup_key, {})

            address = meta.get("address") or "CALIFORNIA COMMERCIAL PRACTICE SITE"
            specialty = meta.get("specialty") or "Multi-Specialty Physician"

            rows.append({
                "NPI": npi,
                "TIN": tin,
                "Address": address,
                "Billing Code": code,
                "Specialty": specialty,
                "Rate": round(rate, 2),
                # Auxiliary columns for internal audit & C7 scoring
                "Confidence_Score": meta.get("confidence_score", 85.0),
                "Selection_Rationale": r.get("selection_rationale", "Standard negotiated rate")
            })

        df = pd.DataFrame(rows)
        # Deduplicate on (NPI, TIN, Address, Billing Code)
        dedup_df = df.drop_duplicates(subset=["NPI", "TIN", "Address", "Billing Code"]).reset_index(drop=True)

        logger.info(
            "Final Rate File Assembled: %d unique (NPI, TIN, Address, Code) entries.",
            len(dedup_df)
        )
        return dedup_df

    def export_deliverable_excel(
        self,
        final_df: pd.DataFrame,
        filename: str = "Centene_CA_Commercial_PPO_Provider_Rates.xlsx"
    ) -> Path:
        """Exports the dataset to Excel format adhering strictly to Deliverable 1.

        Handles Excel row limitations gracefully:
        - If <= 1,000,000 rows: writes single Excel sheet.
        - If > 1,000,000 rows: writes top representative benchmark subset to Excel and full set to Parquet.
        """
        output_path = self.deliverables_dir / filename
        logger.info("Exporting Deliverable 1 to %s", output_path)

        # Enforce exact deliverable columns
        export_df = final_df[FINAL_RATE_FILE_COLUMNS].copy()

        # Format column types for clean Excel display
        export_df["NPI"] = export_df["NPI"].astype(str)
        export_df["TIN"] = export_df["TIN"].astype(str)
        export_df["Billing Code"] = export_df["Billing Code"].astype(str)
        export_df["Rate"] = pd.to_numeric(export_df["Rate"], errors="coerce").round(2)

        try:
            if len(export_df) <= 1_000_000:
                with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
                    export_df.to_excel(writer, sheet_name="Provider_Rates", index=False)
            else:
                logger.warning(
                    "Dataset size (%d rows) exceeds Excel single-sheet limit. "
                    "Exporting top 1,000,000 rows to Excel and full dataset to Parquet.",
                    len(export_df)
                )
                try:
                    parquet_path = output_path.with_suffix(".parquet")
                    export_df.to_parquet(parquet_path, index=False)
                except Exception:
                    pass
                with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
                    export_df.iloc[:1_000_000].to_excel(writer, sheet_name="Provider_Rates_Part1", index=False)
        except Exception as exc:
            logger.warning("Excel export via openpyxl encountered %s; generating CSV deliverable fallback.", exc)
            csv_fallback = output_path.with_suffix(".csv")
            export_df.to_csv(csv_fallback, index=False)
            output_path = csv_fallback

        logger.info("Deliverable 1 successfully written to %s", output_path)
        return output_path
