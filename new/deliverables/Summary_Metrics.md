# Executive Run Summary: Centene CA Commercial PPO Rate Curation
**Pursuant to Centene California Commercial-Group PPO Classification Plan**

**Status:** The C3 score below was independently rerun on the complete downloaded Centene MRF as of 2026-10-18. C4–C7 figures in this older summary came from synthetic demonstration rows and are not verified submission results. Use `file_quality_details.json` for C3 evidence.

- **Execution Date**: 2026-10-17 17:38:31 UTC
- **Target Snapshot Date**: 2026-09-30
- **Target Payer**: Centene Corporation (Health Net Life Insurance Company)
- **Target Market**: Commercial Group, California (CA)
- **Target Network**: Health Net Full Network PPO

## High-Level Execution Metrics (Deliverable 4)

| Metric Category | Metric Name | Measured Value | Plan Reference |
| :--- | :--- | :--- | :--- |
| **C1: Index Inventory** | Index Files Successfully Parsed | 11 | All Centene brand indexes (Health Net, Ambetter, Fidelis, QualChoice) |
| | Raw Plan Records Discovered | 3275 | Full reporting structure edges |
| | Unique Deduplicated Plans | 3270 | Deduplicated on brand/name/id/market/url |
| **C2: Network Decisions** | **Confirmed CA Commercial PPO Plans** | **30** | Exact 2026 Small Group Full Network PPO EOC match |
| | **Provisional CA Commercial PPO Plans** | **422** | Custom employer group PPO schedules + HDHP 1800 variants |
| | **Total CA Commercial PPO Universe** | **452** | Combined Confirmed + Provisional PPO candidate scope |
| | Ruled Out Knox-Keene HMO Plans | 2810 | Excluded: Capitated IPAs (CanopyCare, SmartCare, Salud) + EOA HMO |
| | Ruled Out POS Plans | 6 | Excluded: Two-tiered gatekeeper requiring PCP referral |
| | EOA Overlap Sensitivity Cohort | 127 | Exclusive Option Advantage (HMO with PPO tier; flagged for sensitivity) |
| | Collapsed Token Anomaly (CUSPPO) | 1 | Recovered via regex punctuation tokenization (`CA L CUSPPO`) |
| | Retiree / Government Review Queue | 1 | Flagged for active commercial group employment eligibility audit |
| | Unresolved Plans in Review Queue | 8 | Zero silent defaults; published in `review_queue.csv` |
| **C2: Rate File Attribution** | Distinct Rate Files Referenced | 1 | `healthnet-ca_in-network.json` |
| | **Rate File Classification** | **MIXED** | Linked by both HMO and PPO plans; cannot assume PPO exclusivity |
| | **Plan Attribution Limitation** | **SHARED_FILE_UNRESOLVED** | Rate records preserved without false plan-level multiplication |
| **C3: File Quality** | **Complete-file composite** | **83.33 / 100 (Grade B; review required)** | 1,500,288 published prices audited; see scorecard and detailed review flags |
| **C4: Rates Curation** | Raw Rates Extracted | 8 | Streamed from shared in-network file |
| | Curated Conflict-Resolved Rates | 7 | 4-Tier Protocol (Prof > POS 11 Office > Freshness > Median) |
| **C5: Address Resolution** | Unique In-Network NPIs | 5 | Type 1 Individuals & Type 2 Organizations |
| | Unique Contracted TINs | 4 | Medical groups and health systems |
| | Unique Verified Practice Sites | 4 | Physical addresses (PO Boxes strictly rejected) |
| | **Share of NPIs with Verified Address** | **100.0%** | Triangulated via TIN Co-occurrence Consensus + CASS |

## Deliverables & Audit Files Generated

1. `Centene_CA_Commercial_PPO_Provider_Rates.xlsx` (Deliverable 1: Final Provider Rate File)
2. `Logic_File.md` (Deliverable 2: Logic for Network ID and Address Mapping)
3. `File_Quality_Metrics.md` & `file_quality_scorecard.csv` (Deliverable 3: Quality Metrics & Scores)
4. `Summary_Metrics.json` & `Summary_Metrics.md` (Deliverable 4: Summary Metrics)
5. `plan_decisions.csv` (C2 Plan Decisions with Product and Network Statuses)
6. `file_manifest.csv` (C2 Rate File Manifest with MIXED classification)
7. `review_queue.csv` (C2 Unresolved Review Queue)
8. `provider_cost_effectiveness_benchmark.csv` (Deliverable 7: C7 Cost Effectiveness)
