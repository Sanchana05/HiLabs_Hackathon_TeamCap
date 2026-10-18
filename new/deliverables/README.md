# Submission artifact index

The committed files in this directory come from the 2026-10-18 source run. The Health Net source MRF is linked to PPO and non-PPO plans (`MIXED`), so a source-file rate is not proof of a PPO-specific contract. Historical synthetic workbooks and C7 rankings have been removed from this submission directory.

| Artifact | Status | Meaning |
| --- | --- | --- |
| `Logic_File.md` | Current | C1–C2 network rules, C4 rate-selection policy, and C5–C6 evidence gates. |
| `File_Quality_Metrics.md`, `file_quality_scorecard.csv`, `file_quality_details.json` | Current | C3 complete-file audit; grade B, review required. |
| `Summary_Metrics.md`, `Summary_Metrics.json` | Current | C1–C6 run counts, with candidate and verified outputs distinguished. |
| `c5/` | Current evidence audit | NPI/site candidates, corroboration, conflicts, and unresolved pairs. SQLite work files are excluded. |
| `c6/Centene_CA_Commercial_PPO_Provider_Rates.xlsx` | Strict verified output; headers only | No rate passes the current PPO attribution, direct TIN/site, and PPO/site gates. |
| `Centene_CA_Commercial_PPO_Rate_Candidates.xlsx` | Research candidates | 220 PPO-linked source-file rate candidates with independently corroborated addresses. Its evidence sheets state the missing TIN/site and exact PPO/site proof. |
| `Project_Evaluation_Scorecard.md` | Current project scorecard | Separates source quality, candidate coverage, verified linkage, and rate yield. |
| `VIDEO_SCRIPT.md` | Recording plan | A video file has not been recorded or exported. |

The optional C7 provider cost-effectiveness file is absent because there are no verified PPO-specific C6 rows to benchmark. Recreate the files with the documented master command in `../README.md`; it requires the large local source MRF and NPPES inputs, which are excluded from Git.
