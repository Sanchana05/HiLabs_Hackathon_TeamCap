# Integration validation

Branch: `integration/full-pipeline`. The full C1–C6 master command completed successfully from this merged checkout with the local Centene MRF, monthly NPPES V2 main and secondary files, the NPPES deactivation report, NUCC taxonomy, and the dated CMS clinician extract. The run used `--as-of 2026-10-18` and wrote to ignored `new/outputs/integration-full-run/` so the committed submission artifacts were preserved.

| Check | Result |
| --- | ---: |
| Automated tests | 31 passed, plus 3 subtests |
| Index files / deduplicated plan-file edges | 11 / 3,270 |
| Target PPO-linked rate files | 1, classified `MIXED` |
| C3 complete-file score | 83.33/100, grade B, `REVIEW_REQUIRED` |
| C4 expanded rows / selected rate contexts | 1,795,989 / 14,443 |
| C5 unique NPIs / TINs / NPI–TIN pairs | 3,155 / 2,465 / 3,195 |
| C5 corroborated practice locations | 181 |
| C6 research candidate rows / verified PPO rate rows | 220 / 0 |
| Candidate workbook audit | Passed; 220 rows, 220 unique six-column keys, no mismatch or missing fields |

The fresh run matched the committed `Summary_Metrics.json` on the listed C1–C6 counts, C5 corroboration and verified-link shares, and the C6 candidate yield. C3 and C4 used the same source MRF SHA-256: `3b3e4e220f421010b8ef925a51d4a3c17863b9fbaa853841c1a4927eb74a0960`.

The strict verified workbook has headers and zero data rows because the shared MRF does not prove PPO-specific rate attribution, and no direct TIN/site plus exact PPO/site evidence was supplied. The candidate workbook is labeled for research review. The run demonstrates reproducibility with the available local source files; it does not establish source-rate agreement against the competition's answer key or satisfy the evidence gate for a populated verified PPO rate file.
