# Executive Run Summary: Centene CA Commercial PPO Rate Curation
**Pursuant to Centene California Commercial-Group PPO Classification Plan**

**Validation scope:** C2 classifies the supplied indexes; C3/C4 audit complete selected MRFs. A PPO-linked shared MRF does not establish provider membership or PPO-specific rates. C5 runs only when real NPPES inputs are supplied and reports evidence statuses separately. C6 exports only rows meeting the exact PPO site, direct TIN/site, and attributable-rate gates; withheld rows remain auditable.

- **Execution Date**: 2026-10-18 14:21:02 UTC
- **Target Snapshot Date**: 2026-09-30
- **Target Payer**: Centene / Health Net (index issuer: Healthnet, LLC)
- **Target Market**: Commercial Group, California (CA)
- **Target Network**: Health Net Full Network PPO

## High-Level Execution Metrics (Deliverable 4)

| Metric Category | Metric Name | Measured Value | Plan Reference |
| :--- | :--- | :--- | :--- |
| **C1: Index Inventory** | Index Files Successfully Parsed | 11 | All Centene brand indexes (Health Net, Ambetter, Fidelis, QualChoice) |
| | Raw Plan Records Discovered | 3275 | Full reporting structure edges |
| | Unique Plan-File Edges | 3270 | Deduplicated on brand/name/id/id-type/market/url |
| **C2: Network Decisions** | **Confirmed PPO plan-file edges across all brands** | **89** | Exact 2026 EOC or CMS plan-attribute match |
| | **Provisional PPO plan-file edges across all brands** | **662** | Explicit PPO token without an exact matching authority |
| | **Health Net CA group PPO handoff edges** | **30 confirmed; 422 provisional** | Only these PPO-linked files enter C3/C4 |
| | **PPO-Labeled Candidate Edges** | **751** | Confirmed + provisional; not a unique-product count |
| | Explicit Non-PPO Labels | 1239 | HMO, EPO, POS, or EOA token; no inferred contract model |
| | Out-of-Scope Edges | 0 | Invalid provenance or index date; geography and market are classified in C2 |
| | EOA Overlap Sensitivity Cohort | 127 | Exclusive Option Advantage (HMO with PPO tier; flagged for sensitivity) |
| | Collapsed Token Anomaly (CUSPPO) | 1 | Recovered via regex punctuation tokenization (`CA L CUSPPO`) |
| | Retiree / Government Review Queue | 3 | Flagged for active commercial group employment eligibility audit |
| | Unresolved Edges | 1280 | Review queue also includes provisional PPO edges |
| **C2: Rate File Attribution** | Distinct Rate Files Referenced | 1 | See `file_manifest.csv` |
| | **Rate File Classification** | **MIXED** | From the C2 file manifest; not provider-level membership proof |
| | **Plan Attribution Limitation** | **SHARED_FILE_UNRESOLVED** | Source-file rows retain their attribution status |
| **C3: File Quality** | **Complete-file grades** | **2026-09-30_centene-management-company-llc_healthnet-ca_in-network.json: 83.33 (B)** | See per-file counts and limitations in file_quality_details.json |
| **C4: Rates Curation** | Expanded Rate Rows Audited | 1,795,989 | Complete selected MRFs; all decisions in `c4/` |
| | Selected Direct Professional FFS Rates | 14,443 | Actual lower-median published rate per exact service context; alternatives preserved |
| **C5: Address Resolution** | Unique C4 NPIs evaluated | 3,155 | Source-file providers; PPO membership assessed separately |
| | Unique C4 TINs evaluated | 2,465 | TIN/site relationship requires direct evidence |
| | Unique physical address candidates | 4,323 | Format-filtered candidates, not automatically verified |
| | NPIs with a corroborated practice site | 5.61% | Independent or direct practice-site evidence |
| | **NPIs with verified NPI/TIN/PPO site link** | **0.0%** | Direct TIN/site and exact PPO/site evidence both required |
| **C6: Research candidates** | Six-column candidate rows | 220 | Independently corroborated address; exact PPO/site and TIN/site unverified |

## Deliverables & Audit Files Generated

1. `c6/Centene_CA_Commercial_PPO_Provider_Rates.xlsx` if C5 inputs are supplied (Deliverable 1; may have zero rows when proof is unavailable)
2. `Logic_File.md` (Deliverable 2: Logic for Network ID and Address Mapping)
3. `File_Quality_Metrics.md` & `file_quality_scorecard.csv` (Deliverable 3: Quality Metrics & Scores)
4. `Summary_Metrics.json` & `Summary_Metrics.md` (Deliverable 4: Summary Metrics)
5. `plan_decisions.csv` (C2 Plan Decisions with Product and Network Statuses)
6. `file_manifest.csv` (C2 Rate File Manifest with MIXED classification)
7. `review_queue.csv` (C2 Unresolved Review Queue)
8. `provider_cost_effectiveness_benchmark.csv` only when verified C6 rows are available (Deliverable 7)
9. `c4/c4_manifest.csv` and per-file C4 audit CSVs (complete source-file rate extraction)
10. `c5/c5_provider_locations.csv`, `c5/c5_evidence.csv`, `c5/c5_review_queue.csv`, and `c5/c5_summary.json` when C5 is run
