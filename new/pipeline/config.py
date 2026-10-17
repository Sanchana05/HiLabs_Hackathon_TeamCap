"""Configuration module for Centene TiC Price Transparency Data (PTD) Pipeline.
Ensures zero hardcoded paths, enables local-first data discovery, and centralizes all business rules.
Adheres strictly to the Centene California Commercial Group PPO Classification Plan.
"""
from pathlib import Path
import os
import re

# Directory hierarchy (strictly relative to repository root)
PIPELINE_DIR = Path(__file__).resolve().parent
NEW_DIR = PIPELINE_DIR.parent
REPO_ROOT = NEW_DIR.parent

DATA_DIR = NEW_DIR / "data"
RAW_INDEX_DIR = DATA_DIR / "raw_indexes"
RATEFILES_DIR = DATA_DIR / "rate_files"
NPPES_DIR = DATA_DIR / "nppes"
TAXONOMY_DIR = DATA_DIR / "nucc_taxonomy"
DELIVERABLES_DIR = NEW_DIR / "deliverables"
DOCS_DIR = NEW_DIR / "docs"
CACHE_DIR = NEW_DIR / "cache"
CONFIG_DIR = NEW_DIR / "config"
OUTPUTS_PPO_DIR = NEW_DIR / "outputs" / "ppo"

# Ensure runtime directories exist
for directory in [DATA_DIR, RAW_INDEX_DIR, RATEFILES_DIR, NPPES_DIR, TAXONOMY_DIR,
                  DELIVERABLES_DIR, DOCS_DIR, CACHE_DIR, CONFIG_DIR, OUTPUTS_PPO_DIR]:
    directory.mkdir(parents=True, exist_ok=True)

# Candidate local directories to search for indexes and rate files (local-first design)
SEARCH_DIRECTORIES = [
    RAW_INDEX_DIR,
    RATEFILES_DIR,
    DATA_DIR,
    NEW_DIR,
    REPO_ROOT,
    REPO_ROOT / "TOC",
    REPO_ROOT / "healthnet_ratefiles",
    REPO_ROOT / "data" / "indexes",
    REPO_ROOT / "data" / "ratefiles"
]

# Versioned Evidence Register for Authoritative Plan / Network Verification
EVIDENCE_REGISTER_PATHS = [
    CONFIG_DIR / "ppo_evidence_sources.csv",
    REPO_ROOT / "config" / "ppo_evidence_sources.csv"
]

# Official Centene Transparency in Coverage entrypoint
CENTENE_TIC_PAGE_URL = "https://www.centene.com/price-transparency-files.html"

# Target Snapshot Date (Frozen to September 2026)
TARGET_SNAPSHOT_DATE = "2026-09-30"

# HTTP Client Settings
HTTP_HEADERS = {
    "User-Agent": "CentenePTDPipeline/2.0 (Healthcare Economic Research & Provider Rate Curation)"
}
HTTP_TIMEOUT = (15, 120)  # (connect timeout, read timeout in seconds)

# Scope Definition (Hackathon Section 3)
TARGET_STATE = "CA"
TARGET_MARKET = "group"       # Commercial Group
TARGET_NETWORK = "PPO"        # Preferred Provider Organization

# Centene Brands Evaluation
CENTENE_BRANDS = {
    "healthnet": {
        "description": "Health Net of California, Inc. & Health Net Life Insurance Company",
        "has_ca_commercial_ppo": True,
        "primary_entity": "Health Net Life Insurance Company (CDI-regulated PPO underwriter in CA)"
    },
    "ambetter": {
        "description": "Ambetter (Individual ACA Marketplace on Covered CA)",
        "has_ca_commercial_ppo": False,  # Evaluated and confirmed out-of-scope for Commercial Group PPO
        "primary_entity": "Ambetter from Health Net"
    },
    "fidelis": {
        "description": "Fidelis Care (New York State Medicaid/Medicare/Exchange)",
        "has_ca_commercial_ppo": False,  # NY only
        "primary_entity": "New York Catholic Health Plan, Inc."
    },
    "qualchoice": {
        "description": "QualChoice Health Insurance (Arkansas market)",
        "has_ca_commercial_ppo": False,  # AR only
        "primary_entity": "QCA Health Plan / QualChoice Life & Health"
    }
}

# Network Disambiguation Regex Tokens
REGEX_CA = re.compile(r"(?:\bCA\b|\bCALIFORNIA\b|healthnet-ca|ambetter-ca)", re.I)
REGEX_PPO = re.compile(r"(?<![A-Za-z])PPO(?![A-Za-z])", re.I)
REGEX_HMO = re.compile(r"(?<![A-Za-z])HMO(?![A-Za-z])", re.I)
REGEX_EPO = re.compile(r"(?<![A-Za-z])EPO(?![A-Za-z])", re.I)
REGEX_POS = re.compile(r"(?<![A-Za-z])POS(?![A-Za-z])", re.I)
REGEX_EOA = re.compile(r"(?<![A-Za-z])EOA(?![A-Za-z])", re.I)  # Exclusive Option Advantage (HMO with PPO tier)
REGEX_CUSPPO = re.compile(r"CUSPPO", re.I)                     # Collapsed spelling anomaly (e.g. CA L CUSPPO)
REGEX_RETIREE = re.compile(r"\b(?:retiree|senior|medicare|medi-cal|part\s*d)\b", re.I)

# Product Status Enums (Plan Step 5)
STATUS_CONFIRMED_PPO = "CONFIRMED_PPO"
STATUS_PROVISIONAL_PPO = "PROVISIONAL_PPO"
STATUS_EXCLUDED_NON_PPO = "EXCLUDED_NON_PPO"
STATUS_UNRESOLVED = "UNRESOLVED"

# Network Status Enums (Plan Step 5)
NET_CONFIRMED = "CONFIRMED_NETWORK"
NET_PROVISIONAL = "PROVISIONAL_NETWORK"
NET_UNKNOWN = "UNKNOWN_NETWORK"

# Rate File Classification Enums (Plan Step 6)
FILE_PPO_ONLY = "PPO_ONLY"
FILE_MIXED = "MIXED"
FILE_UNKNOWN = "UNKNOWN"

# High-volume Benchmark Codes (CMS Top Shoppable + HiLabs Rate Benchmarking Weights)
BENCHMARK_CODES = {
    # Evaluation & Management (E/M)
    "99213": {"category": "E/M Office Visit Est Low-Mod", "weight": 0.25},
    "99214": {"category": "E/M Office Visit Est Mod-High", "weight": 0.30},
    "99203": {"category": "E/M Office Visit New Low-Mod", "weight": 0.10},
    "99204": {"category": "E/M Office Visit New Mod-High", "weight": 0.10},
    # Preventive Medicine
    "99395": {"category": "Preventive Visit Est 18-39yr", "weight": 0.05},
    "99396": {"category": "Preventive Visit Est 40-64yr", "weight": 0.05},
    # Diagnostic Imaging & Radiology
    "70450": {"category": "CT Head/Brain w/o Contrast", "weight": 0.03},
    "71250": {"category": "CT Thorax w/o Contrast", "weight": 0.02},
    "72148": {"category": "MRI Lumbar Spine w/o Contrast", "weight": 0.02},
    "73721": {"category": "MRI Lower Extremity Joint", "weight": 0.02},
    # Clinical Laboratory & Pathology
    "80053": {"category": "Comprehensive Metabolic Panel", "weight": 0.02},
    "85025": {"category": "Complete Blood Count (CBC) with Diff", "weight": 0.02},
    # Endoscopy / Surgery
    "45378": {"category": "Diagnostic Colonoscopy", "weight": 0.01},
    "45380": {"category": "Colonoscopy with Biopsy", "weight": 0.01}
}

# Quality Scoring Thresholds (Challenge C3)
QUALITY_METRIC_WEIGHTS = {
    "code_coverage": 0.20,       # Presence of standard benchmark CPT/HCPCS codes
    "provider_coverage": 0.20,   # Volume of unique active NPIs
    "zero_rate_penalty": 0.20,   # Penalty for zero/sub-dollar rates
    "rate_type_validity": 0.15,  # Percentage of clean fee-for-service allowed amounts
    "outlier_control": 0.10,     # Percentage of rates within statistical IQR / clinical bounds
    "contract_freshness": 0.10,  # Recency of contract update date (< 60 days)
    "duplicate_penalty": 0.05    # Penalty for identical provider/code duplicate rate collisions
}

# Final Deliverable Schema (Challenge C6 / Deliverable 1)
FINAL_RATE_FILE_COLUMNS = [
    "NPI",
    "TIN",
    "Address",
    "Billing Code",
    "Specialty",
    "Rate"
]
