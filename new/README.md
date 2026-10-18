# Centene California Commercial PPO Rate Curation Engine
**HiLabs Hackathon Submission: Data Pipeline Curation for Provider Rates**

---

## 1. Executive Summary

Under the federal **Transparency in Coverage (TiC)** mandate (45 CFR § 147.212), health insurance issuers must publish machine-readable rate files containing their negotiated reimbursement rates with in-network providers. Payer contracting teams rely on competitor price transparency data (PTD) to establish market benchmarks and negotiate competitive provider contracts.

However, extracting reliable intelligence from raw PTD is notoriously difficult:
1. **Network Disambiguation**: Centene publishes monolithic index files covering hundreds of plans across brands (Health Net, Ambetter, Fidelis, QualChoice). Plan names are inconsistent, and many do not explicitly state a network type.
2. **Data Quality Deficits**: Published rate files are plagued by $0.00 rates, placeholder rates ($0.01, $99,999), Cartesian duplicates, missing core E/M codes, and contract staleness.
3. **Provider Context**: Raw rate files link rates to an NPI and Tax ID (TIN) without practice addresses or specialties. NPPES address and taxonomy records require independent verification before they can support a provider-level deliverable.

Current status: C1/C2 runs repeatably across all four indexed brands with official 2026 EOC and CMS plan-attribute evidence and a conservative review queue. The C3/C4 handoff remains the Health Net California group file. C3 grades complete source files and C4 audits and selects published rate contexts. C5 maps C4 provider pairs with NPPES and the dated CMS clinician file, retaining unresolved sites. C6 keeps a strict verified output separate from a populated, explicitly labeled PPO-linked research-candidate output. Direct TIN/site and exact PPO/site evidence is still needed for verified rows.

Use the fresh `c5/` and `c6/` evidence outputs and `Centene_CA_Commercial_PPO_Rate_Candidates.xlsx` for review. Older demonstration metrics and workbooks must not be treated as current evidence. The UI reads the gated outputs.

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
│   ├── c5_address_mapper/            # C5: streaming, evidence-backed provider/site resolver
│   │   ├── __init__.py
│   │   ├── address_normalizer.py
│   │   └── resolve.py
│   ├── c6_rate_builder/              # C6: evidence-gated rate projection (Excel/CSV/audit)
│   │   ├── __init__.py
│   │   └── verified_builder.py
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
│   ├── c5/                                          # Sourced site/evidence/review outputs when supplied
│   ├── c6/                                          # Evidence-gated rate Excel/CSV/audit when C5 runs
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
- Classifies Health Net, Ambetter, Fidelis, and QualChoice plan-file edges across their indexed states and markets:
  1. **Scope**: Requires a recognized brand, source index, consistent state clues, and an index date no later than the September 2026 cutoff.
  2. **Evidence**: Uses exact 2026 Health Net and California Ambetter EOC titles; matches Ambetter plans to the CMS 2026 Plan Attributes PUF by state, market, HIOS product ID, and exact marketing name. Fidelis Essential Plan carrier evidence excludes that non-PPO family. QualChoice PPO family evidence supports provisional, not plan-specific, classification.
  3. **Review**: Keeps other PPO names provisional, conflicting or unlabeled names unresolved, and explicit HMO/EPO/POS/EOA names out of the pure PPO set.
  4. **Handoff**: Emits only the Health Net California group PPO-linked file manifest for C3/C4 and marks shared files `MIXED`; file linkage does not establish provider-level PPO membership.

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
- **Module**: `pipeline/c5_address_mapper/resolve.py`
- **Documentation**: [`docs/C5_ADDRESS_MAPPING_LOGIC.md`](docs/C5_ADDRESS_MAPPING_LOGIC.md)
- Streams C4 pairs and NPPES V2 primary and secondary locations through a SQLite work table. Optional dated CMS, payer, and provider/group records add independent evidence.
- Retains every plausible location and separates practice-site, direct TIN/site, and exact PPO/site decisions. NPPES-only sites stay candidates. Address token normalization is not CASS certification.
- Emits a location table, observation-level evidence, a review queue, and coverage metrics. Missing site data produces an empty address in review, never a placeholder.

### Challenge C6: Provider Rate File Builder
- **Module**: `pipeline/c6_rate_builder/verified_builder.py`
- Exports rates only when the NPI/site, TIN/site, PPO/site, and PPO-specific rate attribution gates all pass:
  $$\text{Columns: } [\text{NPI}, \text{TIN}, \text{Address}, \text{Billing Code}, \text{Specialty}, \text{Rate}]$$
- Preserves all admitted C4 contexts in an audit CSV and withholds ambiguous six-column projections. The current mixed file will yield zero verified PPO-specific rows without further rate attribution evidence.
- Also writes a separate PPO-linked **research candidate** table from one-TIN, one-site, independently corroborated California matches. The six-column Excel workbook carries `Evidence` and `Scope and sources` sheets. Candidate rows do not assert a proven TIN/site contract or exact PPO/site participation. [CMS shared-file guidance](https://www.cms.gov/files/document/transparency-coverage-8-steps-508.pdf) supports using a common MRF as published rate evidence for its linked plans, subject to the publisher's compliance.

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

When NPPES paths are omitted, the master run finishes C1–C4 and skips C5/C6 without producing synthetic addresses. To run C5 after C4, supply the main and non-primary NPPES V2 files and the snapshot through-date. Optional evidence files use the CSV contract below.

```powershell
$env:PYTHONPATH = "new"
python new/pipeline/run_pipeline.py --as-of 2026-10-18 `
  --nppes path/to/npidata_pfile.csv --nppes-secondary path/to/pl_pfile.csv `
  --nppes-monthly-through 2026-10-11 --nucc path/to/nucc_taxonomy.csv `
  --nppes-deactivations path/to/deactivated.xlsx
```

Outputs are under `new/deliverables/`, with C5 and C6 subfolders when those stages run. To add independent CMS practice-site evidence, stream the official clinician dataset down to the C4 NPIs, then pass the filtered CSV to the master runner:

```powershell
$env:PYTHONPATH = "new"
# Optional refresh; the dated, filtered source and metadata are included under new/evidence/.
python new/tools/fetch_cms_clinicians.py --selected-rates new/outputs/c4/<file_id>/selected_rates.csv `
  --output new/evidence/cms_clinicians_ca_matched_2026-10-02.csv --as-of 2026-10-18
python new/pipeline/run_pipeline.py --as-of 2026-10-18 `
  --nppes path/to/npidata_pfile.csv --nppes-secondary path/to/pl_pfile.csv `
  --nppes-monthly-through 2026-10-11 --nucc path/to/nucc_taxonomy.csv `
  --nppes-deactivations path/to/deactivated.xlsx `
  --cms-clinicians new/evidence/cms_clinicians_ca_matched_2026-10-02.csv
```

The committed filtered CMS source has SHA-256 `47d4149de03c29ca795ff8b2f0e562407079070bc6e05dc976856cfde7c7a8b1`; the optional fetch reads current CMS metadata and may produce a newer snapshot on a later date. It is address evidence, not commercial PPO evidence. The master runner writes strict verified-rate results and separate research-candidate CSV/evidence/review files under `c6/`.

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

### Standalone C5 while C2 is being finalized

The standalone command accepts one or more C4 selected-rate CSVs or a completed `c4_manifest.csv`. It does not rerun C1–C4:

```powershell
$env:PYTHONPATH = "new"
python -m pipeline.c5_address_mapper.resolve --selected-rates path/to/selected_rates.csv `
  --nppes-main path/to/npidata_pfile.csv --nppes-secondary path/to/pl_pfile.csv `
  --monthly-through 2026-10-11 --nucc path/to/nucc_taxonomy.csv `
  --as-of 2026-10-18 --output-dir path/to/c5_output
```

Optional `--cms`, `--payer-directory`, and `--provider-roster` accept UTF-8 CSV. Payer and roster evidence uses `npi,address_line1,address_line2,city,state,zip,source_date,record_url` (or `record_id`). The native CMS file columns `NPI,adr_ln_1,adr_ln_2,citytown,state,zip_code,pri_spec` are also accepted. Supply `--cms-snapshot`, `--payer-snapshot`, or `--roster-snapshot` when the corresponding CSV has one known publication date rather than a date in every row. Payer evidence additionally needs `plan_name,plan_year`; pass its exact accepted name with `--ppo-plan`. A payer or provider/group CSV may contain `tin_type,tin` for direct TIN/site evidence. Use `--nppes-weekly-main`, `--nppes-weekly-secondary`, and `--weekly-through` together when the weekly snapshot is newer than the monthly one. If its period overlaps the monthly snapshot, C5 skips it.

For the master runner, the corresponding flags are `--cms-clinicians`, `--payer-directory`, `--provider-roster`, `--ppo-directory-plan`, and `--ppo-rate-attribution`. The latter is an explicit allowlist for C4 `plan_attribution` values; the builder still refuses `MIXED` files. No Health Net commercial group PPO bulk directory feed or authorized roster was supplied, so exact PPO confirmation requires obtaining and recording that evidence.

When C2 later establishes a PPO-only rate attribution, rerun C6 without rescanning NPPES:

```powershell
$env:PYTHONPATH = "new"
python -m pipeline.c6_rate_builder.verified_builder --c4-manifest new/outputs/c4/c4_manifest.csv `
  --c5-locations new/outputs/c5/c5_provider_locations.csv `
  --allow-plan-attribution PPO_ONLY --output-dir new/outputs/c6
```

Use the actual C4 attribution value, supported by C2 evidence. A `MIXED` source remains withheld even if its attribution string is placed on the allowlist.

To rebuild the populated research-candidate Excel workbook from the fresh master output, run the workbook authoring script with Node.js and `@oai/artifact-tool` available:

```powershell
node new/tools/build_rate_candidate_workbook.mjs new/deliverables/c6 `
  new/deliverables/Centene_CA_Commercial_PPO_Rate_Candidates.xlsx
```

The first sheet has exactly the six requested columns. The `Evidence` and `Scope and sources` sheets disclose that these are candidates; a direct TIN/site roster and plan-filtered Health Net directory are still required to call any row verified.

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
| **Deliverable 1, research candidate** | `new/deliverables/Centene_CA_Commercial_PPO_Rate_Candidates.xlsx` | Six requested columns plus evidence and scope sheets; independently corroborated addresses, unverified TIN/site and exact PPO/site links |
| **Strict verified output** | `new/deliverables/c6/Centene_CA_Commercial_PPO_Provider_Rates.xlsx` | Evidence-gated six-column workbook; zero rows until direct PPO and TIN/site proof is supplied |
| **Deliverable 2** | `new/deliverables/Logic_File.md` | Logic for PPO network identification and TIN/NPI/Address mapping |
| **Deliverable 3** | `new/deliverables/File_Quality_Metrics.md`, `file_quality_scorecard.csv`, `file_quality_details.json` | Complete-file methodology, scorecard, raw counts, and review flags |
| **Deliverable 4** | `new/deliverables/Summary_Metrics.md` & `Summary_Metrics.json` | High-level execution metrics and run statistics |
| **C5 audit** | `new/deliverables/c5/c5_provider_locations.csv`, `c5_evidence.csv`, `c5_review_queue.csv`, `c5_summary.json` | Candidate and corroborated sites, evidence, and unresolved cases |
| **Deliverable 7** | `new/deliverables/provider_cost_effectiveness_benchmark.csv` & `new/ui/app.py` | C7 Cost-effectiveness metrics & Interactive Streamlit Dashboard |

The master runner refreshes the logic, file-quality, and summary documents. A submission video requires separate recording. The scorecard must keep candidate-address reach, verified linkage, and final verified-rate yield distinct.
