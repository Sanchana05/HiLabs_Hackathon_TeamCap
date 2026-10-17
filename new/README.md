# Centene California Commercial PPO Rate Curation Engine
**HiLabs Hackathon Submission: Data Pipeline Curation for Provider Rates**

---

## 1. Executive Summary

Under the federal **Transparency in Coverage (TiC)** mandate (45 CFR § 147.212), health insurance issuers must publish machine-readable rate files containing their negotiated reimbursement rates with in-network providers. Payer contracting teams rely on competitor price transparency data (PTD) to establish market benchmarks and negotiate competitive provider contracts.

However, extracting reliable intelligence from raw PTD is notoriously difficult:
1. **Network Disambiguation**: Centene publishes monolithic index files covering hundreds of plans across brands (Health Net, Ambetter, Fidelis, QualChoice). Plan names are inconsistent, and many do not explicitly state a network type.
2. **Data Quality Deficits**: Published rate files are plagued by $0.00 rates, placeholder rates ($0.01, $99,999), Cartesian duplicates, missing core E/M codes, and contract staleness.
3. **The Stale NPPES Crisis**: Raw rate files link rates solely to an NPI and a Tax ID (TIN), with **zero addresses and zero specialties**. Relying on raw federal NPPES data is catastrophic because approximately **80% of NPPES addresses are stale, out-of-state, or administrative PO Boxes**.

This repository implements an end-to-end institutional-grade pipeline that resolves these challenges, isolates Centene's **California Commercial Group PPO network**, grades file quality via a **7-metric Composite File Quality Score (FQS)**, and maps providers to their true physical practicing addresses and NUCC specialties via a **TIN-NPI Co-Occurrence Network Consensus Engine**.

---

## 2. Repository Architecture (`new/`)

```
new/
├── pipeline/
│   ├── __init__.py
│   ├── config.py                     # Central configuration (dynamic paths, regex, benchmarks)
│   ├── c1_index_parser/              # C1: Multi-brand index parser & graph deduplicator
│   │   ├── __init__.py
│   │   └── index_parser.py
│   ├── c2_network_mapper/            # C2: PPO network classifier (rules out HMO, EPO, POS)
│   │   ├── __init__.py
│   │   └── network_classifier.py
│   ├── c3_file_grader/               # C3: 7-Metric Composite File Quality Scorer (FQS)
│   │   ├── __init__.py
│   │   └── file_grader.py
│   ├── c4_rate_extractor/            # C4: Streaming rate parser & multi-rate conflict resolver
│   │   ├── __init__.py
│   │   └── rate_extractor.py
│   ├── c5_address_mapper/            # C5: Address triangulator (USPS CASS, TIN consensus, NUCC)
│   │   ├── __init__.py
│   │   ├── address_normalizer.py
│   │   ├── nppes_taxonomy_resolver.py
│   │   └── tin_address_clusterer.py
│   ├── c6_rate_builder/              # C6: Final provider rate file generator (Excel/Parquet)
│   │   ├── __init__.py
│   │   └── rate_builder.py
│   ├── c7_cost_effectiveness/        # C7 (Bonus): Specialty Price Index & Benchmarking
│   │   ├── __init__.py
│   │   └── cost_effectiveness.py
│   └── run_pipeline.py               # Single master CLI orchestrator
├── docs/                             # In-depth methodology & mathematical defenses
│   ├── C1_C2_METHODOLOGY_AND_LOGIC.md
│   ├── C3_FILE_QUALITY_METRICS.md
│   ├── C4_RATE_EXTRACTION_LOGIC.md
│   ├── C5_ADDRESS_MAPPING_LOGIC.md
│   └── C7_COST_EFFECTIVENESS_LOGIC.md
├── ui/                               # Brownie Points: Interactive Streamlit Dashboard
│   └── app.py
├── deliverables/                     # Output directory for competition deliverables
│   ├── Centene_CA_Commercial_PPO_Provider_Rates.xlsx   # Deliverable 1
│   ├── Logic_File.md                                   # Deliverable 2
│   ├── File_Quality_Metrics.md                         # Deliverable 3
│   ├── file_quality_scorecard.csv                      # Deliverable 3 (Scorecard)
│   ├── Summary_Metrics.json                            # Deliverable 4
│   ├── Summary_Metrics.md                              # Deliverable 4 (Report)
│   └── provider_cost_effectiveness_benchmark.csv       # Deliverable 7 (C7 Bonus)
└── README.md                         # This file
```

---

## 3. Step-by-Step Methodology Breakdown

### Challenge C1: Parse Index Files & Deduplicate
- **Module**: `pipeline/c1_index_parser/index_parser.py`
- Ingests Centene Table of Contents (TOC) JSON files across all brands (`healthnet`, `ambetter`, `fidelis`, `qualchoice`).
- Canonicalizes rate file URLs (normalizes casing, host, path, and strips tracking parameters).
- Flattens nested CMS `reporting_structure` blocks ($M$ plans $\times$ $N$ files) and deduplicates on:
  $$\langle \text{brand}, \text{plan\_name}, \text{plan\_id}, \text{market\_type}, \text{rate\_file\_url} \rangle$$
- Eliminates Cartesian redundant joins while preserving the valid many-to-one relationship between employer groups and rate files.

### Challenge C2: Isolate PPO Network & Rule Out HMO, EPO, and POS
- **Module**: `pipeline/c2_network_mapper/network_classifier.py`
- **Documentation**: [`docs/C1_C2_METHODOLOGY_AND_LOGIC.md`](docs/C1_C2_METHODOLOGY_AND_LOGIC.md)
- Implements statutory and regulatory insurance principles in California:
  1. **Knox-Keene HMO Exclusion**: Commercial HMOs in California are licensed under the Knox-Keene Act via **Health Net of California, Inc.**, utilizing delegated capitated Independent Practice Associations (IPAs) without fee-for-service allowed amounts. Excludes `CanopyCare`, `SmartCare`, `Salud HMO y Más`, `CommunityCare HMO`.
  2. **EPO Exclusion**: Closed exclusive provider networks with zero out-of-network benefits and narrower panels (`PureCare EPO`, `EnhancedChoice EPO`).
  3. **POS Exclusion**: Two-tiered gatekeeper models requiring Primary Care Physician (PCP) referrals.
  4. **PPO Identification**: Isolates open-access PPO health insurance underwritten by **Health Net Life Insurance Company** (regulated by the California Department of Insurance - CDI), mapping to the state commercial in-network rate file (`...healthnet-ca_in-network.json`).

### Challenge C3: File Quality & Completeness Grading (35 Points)
- **Module**: `pipeline/c3_file_grader/file_grader.py`
- **Documentation**: [`docs/C3_FILE_QUALITY_METRICS.md`](docs/C3_FILE_QUALITY_METRICS.md)
- Computes the **Composite File Quality Score (FQS)** from 0 to 100:
  $$\text{FQS} = 0.20 S_{\text{code}} + 0.20 S_{\text{prov}} + 0.20 S_{\text{zero}} + 0.15 S_{\text{type}} + 0.10 S_{\text{outlier}} + 0.10 S_{\text{fresh}} + 0.05 S_{\text{dup}}$$
  - **$S_{\text{code}}$ (20%)**: Volume-weighted coverage of high-impact E/M and benchmark codes.
  - **$S_{\text{prov}}$ (20%)**: California NPI/TIN network breadth.
  - **$S_{\text{zero}}$ (20%)**: Steep penalty for $0.00, negative, and placeholder rates.
  - **$S_{\text{type}}$ (15%)**: Proportion of clean fee-for-service allowed amounts.
  - **$S_{\text{outlier}}$ (10%)**: Rates bounded within statistical IQR.
  - **$S_{\text{fresh}}$ (10%)**: Compliance with 30-day TiC refresh requirements.
  - **$S_{\text{dup}}$ (5%)**: Deduplication integrity against duplicate rows.

### Challenge C4: Streaming Rate Extraction & Multi-Rate Conflict Resolution
- **Module**: `pipeline/c4_rate_extractor/rate_extractor.py`
- **Documentation**: [`docs/C4_RATE_EXTRACTION_LOGIC.md`](docs/C4_RATE_EXTRACTION_LOGIC.md)
- Uses memory-bounded `ijson` streaming with early code pruning.
- **Unpacks individual NPIs** from nested `provider_groups` arrays (fixing the naive `len(npi)` aggregation bug).
- **Multi-Rate Disambiguation Hierarchy** (Which rate we keep and why):
  1. *Billing Class*: Prioritize `professional` over `institutional` (isolates physician reimbursement from facility charges).
  2. *Place of Service*: Prioritize POS 11 (Office / Non-facility) over hospital facility settings.
  3. *Contract Freshness*: Prioritize latest `expiration_date`.
  4. *Statistical Tiebreaker*: Select **median rate** across tied tiers to eliminate promotional or carve-out outliers.

### Challenge C5: Address Mapping & Disambiguation (40 Points Logic)
- **Modules**: `pipeline/c5_address_mapper/`
- **Documentation**: [`docs/C5_ADDRESS_MAPPING_LOGIC.md`](docs/C5_ADDRESS_MAPPING_LOGIC.md)
- Solves the 80% stale NPPES problem through a 5-stage triangulation protocol:
  1. *USPS CASS Standardization*: Canonicalizes street suffixes, units, and directions; rejects PO Boxes and mail drops.
  2. *Dual NPPES Filtering*: Prioritizes physical Practice Location over administrative Mailing Address; enforces California ZIP boundaries (90001–96162).
  3. *TIN Co-Occurrence Consensus*: Aggregates practice addresses across all NPIs billing under the same TIN. When 15 providers under the same TIN report the same clinic address, that location achieves 75% consensus, self-healing individual provider staleness.
  4. *NUCC Taxonomy Crosswalk*: Maps 10-character taxonomy codes to clinical specialties (e.g., `207X00000X` $\rightarrow$ "Orthopaedic Surgery").
  5. *Address Confidence Score (ACS)*: Grades every matched address (0–100) with full audit trail.

### Challenge C6: Provider Rate File Builder
- **Module**: `pipeline/c6_rate_builder/rate_builder.py`
- Merges curated rates with verified addresses and specialties into **Deliverable 1**:
  $$\text{Columns: } [\text{NPI}, \text{TIN}, \text{Address}, \text{Billing Code}, \text{Specialty}, \text{Rate}]$$
- Formats numbers, ensures text preservation for NPI/TINs, and exports to Excel (`Centene_CA_Commercial_PPO_Provider_Rates.xlsx`).

### Challenge C7: Cost-Effectiveness Benchmarking (Brownie Points)
- **Module**: `pipeline/c7_cost_effectiveness/cost_effectiveness.py`
- **Documentation**: [`docs/C7_COST_EFFECTIVENESS_LOGIC.md`](docs/C7_COST_EFFECTIVENESS_LOGIC.md)
- Defines **"Similar Providers"**: Same NUCC specialty practicing within California under professional ambulatory billing.
- Computes:
  - **Specialty Price Index (SPI)**: $\text{SPI}_p = \frac{\sum w_c \cdot \text{Rate}_{p,c}}{\sum w_c \cdot \text{MedianRate}_{\text{peer}, c}}$ ($< 1.00$ indicates cost-effective pricing).
  - **Specialty Peer Percentile Rank**: Positions provider within specialty market distribution.
  - **Net Savings Opportunity**: Potential dollar savings if provider is renegotiated to market median.

---

## 4. How to Run the Pipeline (Zero Hardcoded Paths)

### Prerequisites
Install dependencies:
```bash
pip install pandas openpyxl requests ijson streamlit numpy
```

### Running the End-to-End Pipeline
Execute the master runner from the repository root or `new/` directory:
```bash
python new/pipeline/run_pipeline.py
```

Optional arguments:
```bash
# Point to specific local index or rate file:
python new/pipeline/run_pipeline.py --index path/to/healthnet_index.json --rate-file path/to/in-network.json

# Extract all codes (disabling benchmark code filter):
python new/pipeline/run_pipeline.py --all-codes
```

All deliverables are automatically written to `new/deliverables/`.

---

## 5. Launching the Interactive UI (Deliverable 7 Brownie Points)

To launch the Executive & Analyst Streamlit dashboard:
```bash
streamlit run new/ui/app.py
```

The portal provides:
- **Executive Overview**: High-level KPIs, FQS spider/bar charts, and verified address match rates.
- **Analyst Rate Explorer**: Interactive search by NPI, TIN, Billing Code, Specialty, and Address, with CSV export.
- **C7 Cost Effectiveness**: Provider SPI rankings, percentile tiers, and savings opportunities.
- **Documentation Center**: In-app rendering of Deliverables 2, 3, and 4.

---

## 6. Official Competition Deliverables Index

| Deliverable | File Path | Description |
| :--- | :--- | :--- |
| **Deliverable 1** | `new/deliverables/Centene_CA_Commercial_PPO_Provider_Rates.xlsx` | Curated provider rate file [NPI, TIN, Address, Billing Code, Specialty, Rate] |
| **Deliverable 2** | `new/deliverables/Logic_File.md` | Logic for PPO network identification and TIN/NPI/Address mapping |
| **Deliverable 3** | `new/deliverables/File_Quality_Metrics.md` & `file_quality_scorecard.csv` | 7-metric PTD file grading rubric and file scorecards |
| **Deliverable 4** | `new/deliverables/Summary_Metrics.md` & `Summary_Metrics.json` | High-level execution metrics and run statistics |
| **Deliverable 7** | `new/deliverables/provider_cost_effectiveness_benchmark.csv` & `new/ui/app.py` | C7 Cost-effectiveness metrics & Interactive Streamlit Dashboard |
