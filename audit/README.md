# Supporting audit artifacts

The four requested submission files are together in the flat [deliverables](../deliverables) folder. This directory retains the source-run evidence, intermediate outputs, and optional material outside that submission folder.

| Artifact | Purpose |
| --- | --- |
| `Summary_Metrics.json` and `Project_Evaluation_Scorecard.md` | Machine-readable run metrics and project evaluation. |
| `file_quality_scorecard.csv` and `file_quality_details.json` | C3 scoring detail behind the submitted metrics document. |
| `plan_decisions.csv`, `file_manifest.csv`, and other C1/C2 CSVs | Network decisions and source-file provenance. |
| `c5/` | Provider-site evidence, conflicts, review queue, and summary. |
| `c6/` | Candidate evidence, workbook validation, and the strict verified workbook. |
| `VIDEO_SCRIPT.md` | Recording plan; a finished video is not yet available. |

The selected Health Net source rate file is shared by PPO and non-PPO plans (`MIXED`). The submitted candidate Excel contains 220 published-rate research candidates; the strict verified workbook here has zero data rows pending direct TIN/site, exact PPO/site, and rate-attribution proof. The optional C7 benchmark is withheld until verified rows exist.

The large source MRF and NPPES files are excluded from Git. Reproduction steps and input locations are in the [root README](../README.md).
