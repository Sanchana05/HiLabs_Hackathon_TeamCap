# Centene California Commercial PPO Rate Curation Engine
**HiLabs Hackathon Submission: Data Pipeline Curation for Provider Rates**

---

## 1. Executive Summary

Under the federal **Transparency in Coverage (TiC)** mandate (45 CFR § 147.212), health insurance issuers must publish machine-readable rate files containing their negotiated reimbursement rates with in-network providers. Payer contracting teams rely on competitor price transparency data (PTD) to establish market benchmarks and negotiate competitive provider contracts.

However, extracting reliable intelligence from raw PTD is notoriously difficult:
1. **Network Disambiguation**: Centene publishes monolithic index files covering hundreds of plans across brands (Health Net, Ambetter, Fidelis, QualChoice). Plan names are inconsistent, and many do not explicitly state a network type.
2. **Data Quality Deficits**: Published rate files are plagued by $0.00 rates, placeholder rates ($0.01, $99,999), Cartesian duplicates, missing core E/M codes, and contract staleness.
3. **Provider Context**: Raw rate files link rates to an NPI and Tax ID (TIN) without practice addresses or specialties. NPPES address and taxonomy records require independent verification before they can support a provider-level deliverable.

Current status: C1/C2 runs repeatably from the supplied indexes with official 2026 EOC evidence and a conservative review queue. C3 grades complete source files and C4 audits and selects published rate contexts. The shared rate file does not establish PPO provider membership. C5–C7 currently produce demonstration outputs using synthetic address seeds.

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
  │   ├── file_quality_details.json                       # Complete-file counts and review flags
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
  1. **Scope**: Requires a California group file URL and an index date no later than the September 2026 cutoff.
  2. **Evidence**: Confirms PPO product type and Full Network PPO name only on exact 2026 Health Net EOC matches. The published index EIN is sponsor-level, not a product key.
  3. **Review**: Keeps custom PPO plans provisional, conflicting/retiree names unresolved, and explicit HMO/EPO/POS/EOA names out of the pure PPO set.
  4. **Handoff**: Emits a PPO-linked file manifest for C3/C4 and marks shared files `MIXED`; file linkage does not establish provider-level PPO membership.

Run C1/C2 independently, without C3/C4 inputs:

```powershell
$env:PYTHONPATH = "new"
python -m pipeline.c2_network_mapper.run_c2 --index-dir data/indexes --output-dir new/deliverables
```

The output includes C1 provenance, C2 decisions, a provisional/unresolved review queue, an all-file inventory, the PPO-linked `file_manifest.csv`, and SHA-256 input hashes in `c2_summary.json`. See the [C1/C2 methodology](docs/C1_C2_METHODOLOGY_AND_LOGIC.md) for the decision contract.

### Challenge C3: Complete-file quality audit
- **Module**: `pipeline/c3_file_grader/file_grader.py`
- **Methods and limits**: [`docs/C3_FILE_QUALITY_METRICS.md`](docs/C3_FILE_QUALITY_METRICS.md)
- Audits every published price in each C2-selected MRF before C4 filters or selects rates. The scorecard includes raw counts, SHA-256, data-source dates, provider-reference integrity, code-panel coverage, price usability, rate-type mix, comparable-rate outliers, publication freshness, and exact provider-price duplicates.
- The 579-code individual-specialty panel is built from the supplied case workbook; a verified PPO NPI roster can be supplied for external coverage. Without a roster, provider coverage is reported as unknown, while provider **linkage** is scored.
- Missing evidence never receives default points. A malformed or missing file fails the run.

### Challenge C4: Complete-file rate extraction and validation
- **Module**: `pipeline/c4_rate_extractor/rate_extractor.py`
- **Documentation**: [`docs/C4_RATE_EXTRACTION_LOGIC.md`](docs/C4_RATE_EXTRACTION_LOGIC.md)
- Streams every item and price into disk-backed validation without a billing-code or row cap. Expands direct and referenced NPI/TIN groups and preserves every decision in `rate_decisions.csv`.
- Keeps distinct billing classes, settings, service codes, modifiers, rate types, and bundles separate. Only direct professional FFS negotiated dollar rates with concrete codes enter the benchmark selection.
- Chooses an actual published lower-median candidate within an exact context. Duplicates and alternatives remain auditable; the selected rate is a representative benchmark, not a verified plan-specific contract.
- Emits per-file `selected_rates.csv`, `rate_decisions.csv`, `c4_summary.json`, and a `c4_manifest.csv` from the master runner or standalone CLI.

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

## 4. How to Run the Pipeline

### Prerequisites
Install dependencies:
```bash
python -m pip install -r new/requirements.txt
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

# C4 always audits all codes; pass an explicit analysis date for repeatability:
python new/pipeline/run_pipeline.py --as-of 2026-10-18
```

All deliverables are automatically written to `new/deliverables/`.

To run only C3 on the reviewed C2 manifest and local files:

```bash
cd new
python -m pipeline.c3_file_grader.file_grader --manifest deliverables/file_manifest.csv --rate-dir ../data/ratefiles --output-dir ../outputs/c3 --as-of 2026-10-18
```

Repeat `--file PATH` instead of `--manifest` to grade explicit files. The master runner uses the same C3 API for every PPO-linked file; `--as-of`, `--c3-benchmark-csv`, and `--c3-expected-npis-csv` control its C3 inputs.

To run complete C4 independently, use the C2 manifest, local MRFs, and optional C3 details:

```powershell
$env:PYTHONPATH = "new"
python -m pipeline.c4_rate_extractor.rate_extractor --manifest new/deliverables/file_manifest.csv --rate-dir data/ratefiles --c3-details new/deliverables/file_quality_details.json --as-of 2026-10-18 --output-dir outputs/c4
```

The C5–C7 demonstration outputs still include synthetic address data and are **not verified production results**.

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
| **Deliverable 3** | `new/deliverables/File_Quality_Metrics.md`, `file_quality_scorecard.csv`, `file_quality_details.json` | Complete-file methodology, scorecard, raw counts, and review flags |
| **Deliverable 4** | `new/deliverables/Summary_Metrics.md` & `Summary_Metrics.json` | High-level execution metrics and run statistics |
| **Deliverable 7** | `new/deliverables/provider_cost_effectiveness_benchmark.csv` & `new/ui/app.py` | C7 Cost-effectiveness metrics & Interactive Streamlit Dashboard |
