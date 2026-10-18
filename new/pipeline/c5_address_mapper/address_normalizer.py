"""Challenge C5: Address Normalization & CASS Standardizer
Implements USPS Publication 28 postal addressing standards, detects PO Boxes and commercial drops,
and formats physical addresses into canonical strings for deduplication and matching.
"""
from __future__ import annotations

import hashlib
import re
from typing import Dict, Optional, Tuple

# USPS Publication 28 standard street suffix abbreviations
STREET_SUFFIXES = {
    "AVENUE": "AVE", "BOULEVARD": "BLVD", "CIRCLE": "CIR", "COURT": "CT",
    "DRIVE": "DR", "EXPRESSWAY": "EXPY", "HIGHWAY": "HWY", "LANE": "LN",
    "PARKWAY": "PKWY", "PLACE": "PL", "ROAD": "RD", "STREET": "ST",
    "SUITE": "STE", "WAY": "WAY", "TERRACE": "TER"
}

# Secondary unit indicators
UNIT_INDICATORS = {
    "APARTMENT": "APT", "BUILDING": "BLDG", "DEPARTMENT": "DEPT",
    "FLOOR": "FL", "ROOM": "RM", "SUITE": "STE", "UNIT": "UNIT"
}

# Directional abbreviations
DIRECTIONALS = {
    "NORTH": "N", "SOUTH": "S", "EAST": "E", "WEST": "W",
    "NORTHEAST": "NE", "NORTHWEST": "NW", "SOUTHEAST": "SE", "SOUTHWEST": "SW"
}

# PO Box and Virtual Mail Drop Detection
RE_PO_BOX = re.compile(
    r"\b(?:P\.?\s*O\.?\s*BOX|POST\s+OFFICE\s+BOX|P\s*BOX|POB|BOX\s+\d+|PMB\s+\d+)\b",
    re.I
)

# California ZIP Code Bounds (90001 - 96162)
CA_ZIP_PATTERN = re.compile(r"^(9[0-6]\d{3})(?:-?(\d{4}))?$")


class AddressNormalizer:
    """Standardizes healthcare practice addresses using USPS postal rules."""

    @staticmethod
    def is_po_box(address_line: str) -> bool:
        """Detects whether an address contains a Post Office Box or Mail Drop."""
        if not address_line:
            return False
        return bool(RE_PO_BOX.search(address_line))

    @classmethod
    def clean_token(cls, token: str) -> str:
        """Normalizes a single word token according to USPS abbreviations."""
        t_upper = token.upper().strip(".,#")
        if t_upper in STREET_SUFFIXES:
            return STREET_SUFFIXES[t_upper]
        if t_upper in UNIT_INDICATORS:
            return UNIT_INDICATORS[t_upper]
        if t_upper in DIRECTIONALS:
            return DIRECTIONALS[t_upper]
        return t_upper

    @classmethod
    def standardize_line(cls, line: str) -> str:
        """Standardizes a street address line."""
        if not line:
            return ""
        # Remove special characters except alphanumeric, spaces, and hyphens
        cleaned = re.sub(r"[^A-Za-z0-9\s\-#]", " ", line)
        tokens = cleaned.split()
        normalized_tokens = [cls.clean_token(t) for t in tokens]
        return " ".join(normalized_tokens)

    @classmethod
    def standardize_zip(cls, zip_code: str) -> Tuple[str, bool]:
        """Validates and standardizes a ZIP code, checking California ranges.

        Returns:
            canonical_zip: 5-digit or 9-digit standardized ZIP.
            is_valid_ca: True if within California ZIP boundaries (90001 - 96162).
        """
        if not zip_code:
            return "", False
        clean = re.sub(r"[^\d]", "", str(zip_code))
        if len(clean) >= 5:
            five_digit = clean[:5]
            is_ca = bool(CA_ZIP_PATTERN.match(five_digit))
            return five_digit, is_ca
        return clean, False

    @classmethod
    def format_canonical_address(
        cls,
        line1: str,
        line2: str = "",
        city: str = "",
        state: str = "CA",
        zip_code: str = ""
    ) -> Dict:
        """Produces a standardized, auditable physical address representation.

        Returns:
            Dict containing:
                canonical_address: formatted single-line address.
                address_hash: SHA-256 fingerprint for deduplication.
                is_po_box: True if flagged as PO Box / non-physical.
                is_valid_ca_zip: True if ZIP is valid California.
        """
        clean_line1 = cls.standardize_line(line1)
        clean_line2 = cls.standardize_line(line2)
        clean_city = cls.clean_token(city).title() if city else ""
        clean_state = (state or "CA").strip().upper()
        clean_zip, is_ca_zip = cls.standardize_zip(zip_code)

        is_pobox = cls.is_po_box(line1) or cls.is_po_box(line2)

        street_part = clean_line1
        if clean_line2:
            street_part = f"{clean_line1} {clean_line2}"

        # Combine into canonical format: "123 MAIN ST STE 100, LOS ANGELES, CA 90012"
        parts = [street_part]
        if clean_city:
            parts.append(clean_city)
        if clean_state and clean_zip:
            parts.append(f"{clean_state} {clean_zip}")
        elif clean_state:
            parts.append(clean_state)

        canonical_str = ", ".join(filter(None, parts)).strip()

        # SHA-256 fingerprint
        address_hash = hashlib.sha256(canonical_str.upper().encode("utf-8")).hexdigest()[:16]

        return {
            "street": street_part,
            "city": clean_city,
            "state": clean_state,
            "zip": clean_zip,
            "canonical_address": canonical_str,
            "address_hash": address_hash,
            "is_po_box": is_pobox,
            "is_valid_ca_zip": is_ca_zip
        }
