"""Challenge C5: NPPES Registry Loader & NUCC Taxonomy Resolver
Enriches raw NPIs with standardized physical addresses, entity types (Type 1 vs Type 2),
and maps 10-character Healthcare Provider Taxonomy codes to NUCC clinical specialties.
"""
from __future__ import annotations

import csv
import gzip
import logging
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import pandas as pd

try:
    from pipeline.c5_address_mapper.address_normalizer import AddressNormalizer
    from pipeline.config import NPPES_DIR, TAXONOMY_DIR
except ImportError:
    from .address_normalizer import AddressNormalizer
    from ..config import NPPES_DIR, TAXONOMY_DIR

logger = logging.getLogger(__name__)

# Standard Fallback NUCC Taxonomy Crosswalk for Major Physician & Facility Specialties
# Sourced from National Uniform Claim Committee (NUCC) Code Set
DEFAULT_NUCC_TAXONOMY_MAP = {
    # Allopathic & Osteopathic Physicians (20...)
    "207Q00000X": "Family Medicine",
    "207R00000X": "Internal Medicine",
    "208D00000X": "General Practice",
    "207V00000X": "Obstetrics & Gynecology",
    "208000000X": "Pediatrics",
    "207Y00000X": "Dermatology",
    "207P00000X": "Emergency Medicine",
    "207T00000X": "Neurological Surgery",
    "207X00000X": "Orthopaedic Surgery",
    "208600000X": "Surgery",
    "207W00000X": "Ophthalmology",
    "208100000X": "Physical Medicine & Rehabilitation",
    "2084N0400X": "Psychiatry",
    "2085R0202X": "Diagnostic Radiology",
    "207RC0000X": "Cardiovascular Disease",
    "207RE0101X": "Endocrinology, Diabetes & Metabolism",
    "207RG0100X": "Gastroenterology",
    "207RH0000X": "Hematology",
    "207RH0003X": "Hematology & Oncology",
    "207RI0011X": "Interventional Cardiology",
    "207RN0300X": "Nephrology",
    "207RP1001X": "Pulmonary Disease",
    "207RR0500X": "Rheumatology",
    # Physician Assistants & Advanced Practice Nursing (36...)
    "363A00000X": "Physician Assistant",
    "363L00000X": "Nurse Practitioner",
    "363LF0000X": "Family Nurse Practitioner",
    # Ambulatory Health Care Facilities & Clinics (26...)
    "261QP2300X": "Primary Care Clinic",
    "261QA0600X": "Adult Day Care Clinic",
    "261QM2500X": "Medical Specialty Clinic",
    "261QR0400X": "Rehabilitation Clinic",
    "261QU0200X": "Urgent Care Clinic",
    # Hospitals (28...)
    "282N00000X": "General Acute Care Hospital",
    "282E00000X": "Critical Access Hospital",
    "283X00000X": "Rehabilitation Hospital"
}


class NPPESTaxonomyResolver:
    """Enriches NPIs with verified California practice locations and clinical specialties."""

    def __init__(
        self,
        nppes_dir: Optional[Path] = None,
        taxonomy_dir: Optional[Path] = None
    ):
        self.nppes_dir = nppes_dir or NPPES_DIR
        self.taxonomy_dir = taxonomy_dir or TAXONOMY_DIR
        self.taxonomy_map: Dict[str, str] = dict(DEFAULT_NUCC_TAXONOMY_MAP)
        self.nppes_cache: Dict[str, Dict] = {}
        self.load_taxonomy_crosswalk()

    def load_taxonomy_crosswalk(self, taxonomy_file: Optional[Path] = None):
        """Loads NUCC taxonomy crosswalk table from CSV if available, supplementing default mappings."""
        target_file = taxonomy_file or (self.taxonomy_dir / "nucc_taxonomy.csv")
        if target_file and target_file.is_file():
            try:
                df = pd.read_csv(target_file, dtype=str)
                code_col = [c for c in df.columns if "code" in c.lower()][0]
                desc_col = [c for c in df.columns if "classification" in c.lower() or "display" in c.lower() or "specialty" in c.lower()][0]
                for _, r in df.iterrows():
                    code = str(r[code_col]).strip()
                    desc = str(r[desc_col]).strip()
                    if code and desc:
                        self.taxonomy_map[code] = desc
                logger.info("Loaded %d taxonomy specialty definitions from %s", len(self.taxonomy_map), target_file.name)
            except Exception as exc:
                logger.warning("Could not load external taxonomy file: %s; using default NUCC crosswalk.", exc)

    def resolve_specialty(self, taxonomy_code: str) -> str:
        """Translates a 10-digit NUCC taxonomy code into a clean clinical specialty description."""
        clean_code = str(taxonomy_code or "").strip()
        if not clean_code:
            return "General Practice"
        return self.taxonomy_map.get(clean_code, "Multi-Specialty Physician")

    def parse_nppes_provider_record(self, raw_row: Dict) -> Dict:
        """Parses a row from the CMS California NPPES extract.

        Extracts:
        - NPI and Entity Type (1 = Individual Physician, 2 = Organizational Clinic/Hospital)
        - Provider Name
        - Physical Practice Address (normalized via USPS standards)
        - Mailing Address (checked for comparison)
        - Primary Taxonomy Code & Resolved Clinical Specialty
        - NPPES Last Update Date
        """
        npi = str(raw_row.get("NPI") or raw_row.get("npi") or "").strip()
        entity_type_code = str(raw_row.get("Entity Type Code") or raw_row.get("entity_type") or "1").strip()
        entity_type = "Individual Practitioner" if entity_type_code == "1" else "Organization / Facility"

        # Provider Name Construction
        if entity_type_code == "1":
            first = str(raw_row.get("Provider First Name") or "").strip()
            last = str(raw_row.get("Provider Last Name (Legal Name)") or raw_row.get("last_name") or "").strip()
            cred = str(raw_row.get("Provider Credential Text") or "").strip()
            name = f"{first} {last}" + (f", {cred}" if cred else "")
        else:
            name = str(raw_row.get("Provider Organization Name (Legal Business Name)") or raw_row.get("org_name") or "").strip()

        # Primary Taxonomy & Specialty
        tax_code = str(raw_row.get("Healthcare Provider Taxonomy Code_1") or raw_row.get("taxonomy_code") or "").strip()
        specialty = self.resolve_specialty(tax_code)

        # 1. Practice Location Address (Physical Rendering Site)
        prac_line1 = str(raw_row.get("Provider First Line Business Practice Location Address") or raw_row.get("practice_address1") or "").strip()
        prac_line2 = str(raw_row.get("Provider Second Line Business Practice Location Address") or raw_row.get("practice_address2") or "").strip()
        prac_city = str(raw_row.get("Provider Business Practice Location Address City Name") or raw_row.get("practice_city") or "").strip()
        prac_state = str(raw_row.get("Provider Business Practice Location Address State Name") or raw_row.get("practice_state") or "CA").strip().upper()
        prac_zip = str(raw_row.get("Provider Business Practice Location Address Postal Code") or raw_row.get("practice_zip") or "").strip()

        prac_norm = AddressNormalizer.format_canonical_address(
            line1=prac_line1,
            line2=prac_line2,
            city=prac_city,
            state=prac_state,
            zip_code=prac_zip
        )

        # 2. Mailing Address (Administrative / Billing Clearinghouse)
        mail_line1 = str(raw_row.get("Provider First Line Business Mailing Address") or "").strip()
        mail_line2 = str(raw_row.get("Provider Second Line Business Mailing Address") or "").strip()
        mail_city = str(raw_row.get("Provider Business Mailing Address City Name") or "").strip()
        mail_state = str(raw_row.get("Provider Business Mailing Address State Name") or "CA").strip().upper()
        mail_zip = str(raw_row.get("Provider Business Mailing Address Postal Code") or "").strip()

        mail_norm = AddressNormalizer.format_canonical_address(
            line1=mail_line1,
            line2=mail_line2,
            city=mail_city,
            state=mail_state,
            zip_code=mail_zip
        )

        last_update = str(raw_row.get("Last Update Date") or raw_row.get("last_updated") or "").strip()

        return {
            "npi": npi,
            "entity_type": entity_type,
            "provider_name": name.strip(),
            "taxonomy_code": tax_code,
            "specialty": specialty,
            "practice_address": prac_norm["canonical_address"],
            "practice_address_hash": prac_norm["address_hash"],
            "is_practice_pobox": prac_norm["is_po_box"],
            "is_practice_ca_zip": prac_norm["is_valid_ca_zip"],
            "mailing_address": mail_norm["canonical_address"],
            "is_mailing_pobox": mail_norm["is_po_box"],
            "last_update_date": last_update
        }
