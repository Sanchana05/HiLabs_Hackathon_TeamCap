# Centene California PPO rate curation

**HiLabs Hackathon submission | TeamCap | 2026 source snapshot**

This repository parses Centene Transparency in Coverage indexes, identifies California commercial group PPO plan references, audits the linked machine readable rate file, selects published professional rates, and checks provider practice sites against independent sources. The final export separates **research candidates** from **verified PPO rates**. A shared rate file is not proof of a PPO-specific contract.

## Submission files

All current submission artifacts are in [deliverables](deliverables/README.md).

| Requirement | File | Current result |
| --- | --- | --- |
| Six-column Excel rate file | [Rate candidates](deliverables/Centene_CA_Commercial_PPO_Rate_Candidates.xlsx) | 220 published-rate research candidates, with evidence and scope sheets; PPO/site and TIN/site links remain unverified. |
| Strict PPO rate export | [Verified workbook](deliverables/c6/Centene_CA_Commercial_PPO_Provider_Rates.xlsx) | Header only: zero rows satisfy every evidence gate. |
| Logic | [Logic file](deliverables/Logic_File.md) | Network, rate, and address rules. |
| File quality | [Quality metrics](deliverables/File_Quality_Metrics.md) and [scorecard](deliverables/file_quality_scorecard.csv) | Complete-file grade B, 83.33; review required. |
| Summary | [Summary metrics](deliverables/Summary_Metrics.md) and [JSON](deliverables/Summary_Metrics.json) | C1–C6 counts and limitations. |
| Video | [Recording script](deliverables/VIDEO_SCRIPT.md) | Recording still required; no video is represented as delivered. |

The optional C7 benchmark is withheld until a verified C6 rate exists. [Project scorecard](deliverables/Project_Evaluation_Scorecard.md) tracks candidate coverage and verified yield separately.

## Reproduce the pipeline

Use Python 3.12 and the repository root as the working directory. The code resolves its configuration and output paths from this checkout; the command accepts input paths as arguments. No machine-specific paths are embedded in the pipeline.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

The 11 small source indexes are committed in `data/indexes/`. Supply these large public source files locally; they are excluded from Git:

| Input | Place at |
| --- | --- |
| Centene Health Net 2026-09-30 in-network JSON referenced by the committed index | `data/ratefiles/2026-09-30_centene-management-company-llc_healthnet-ca_in-network.json` |
| NPPES monthly V2 main CSV through 2026-10-11 | `data/nppes/npidata_pfile_20050523-20261011.csv` |
| NPPES monthly V2 secondary practice locations CSV | `data/nppes/pl_pfile_20050523-20261011.csv` |
| NPPES deactivated NPI report | `data/nppes/NPPES Deactivated NPI Report 20261012.xlsx` |
| NUCC taxonomy CSV | `data/nucc/nucc_taxonomy_261.csv` |

The dated, NPI-filtered CMS clinician extract is committed at `evidence/cms_clinicians_ca_matched_2026-10-02.csv`. The Health Net rate JSON can be obtained from its URL in `data/indexes/2026-09-30_healthnet_index.json`, or by the downloader in `legacy/toc/centene_index_pipeline.py`. Obtain the matching [NPPES monthly and deactivation files](https://download.cms.gov/nppes/NPI_Files.html) and [NUCC taxonomy CSV](https://nucc.org/index.php/code-sets-mainmenu-41/provider-taxonomy-mainmenu-40/csv-mainmenu-57), then extract them to the paths above. For different filenames or snapshots, change the corresponding command arguments and dates.

Run from the repository root:

```powershell
python -m pipeline.run_pipeline `
  --rate-file data/ratefiles/2026-09-30_centene-management-company-llc_healthnet-ca_in-network.json `
  --nppes data/nppes/npidata_pfile_20050523-20261011.csv `
  --nppes-secondary data/nppes/pl_pfile_20050523-20261011.csv `
  --nppes-monthly-through 2026-10-11 `
  --nppes-deactivations 'data/nppes/NPPES Deactivated NPI Report 20261012.xlsx' `
  --nucc data/nucc/nucc_taxonomy_261.csv `
  --cms-clinicians evidence/cms_clinicians_ca_matched_2026-10-02.csv `
  --cms-snapshot 2026-10-02 `
  --as-of 2026-10-18 `
  --output-dir outputs/full-run
```

The command creates `outputs/full-run/Centene_CA_Commercial_PPO_Rate_Candidates.xlsx` **as part of the run**, alongside `outputs/full-run/c6/Centene_CA_Commercial_PPO_Provider_Rates.xlsx`, logic, quality, summary, and C1–C6 audit files. The output directory is ignored by Git so reruns do not silently change the committed submission. To refresh the submission after reviewing a rerun, use `--output-dir deliverables` and commit its generated files. A different snapshot may produce different counts.

Validate the workbook and run the tests:

```powershell
python tools/audit_rate_candidate_workbook.py `
  --c4-manifest outputs/full-run/c4/c4_manifest.csv `
  --c5-locations outputs/full-run/c5/c5_provider_locations.csv `
  --c5-evidence outputs/full-run/c5/c5_evidence.csv `
  --candidate-csv outputs/full-run/c6/c6_supported_rate_candidates.csv `
  --workbook outputs/full-run/Centene_CA_Commercial_PPO_Rate_Candidates.xlsx `
  --output outputs/full-run/c6/c6_workbook_validation.json
python -m pytest tests -q
```

## Evidence gates

1. **C1–C2:** Parse indexes and classify plan/network evidence, keeping provisional and excluded plans separate.
2. **C3–C4:** Score the complete MRF; validate, de-duplicate, and select published professional rates with row decisions.
3. **C5:** Match NPI/TIN pairs to dated NPPES and CMS practice-site evidence, recording conflicts and provenance.
4. **C6:** Export corroborated-site **candidates** and strictly verified rates separately. Verified rows require direct TIN/site and exact PPO/site evidence plus rate attribution. The current Health Net MRF is `MIXED`, so it yields no verified PPO rates.
5. **C7:** Produce cost-effectiveness rankings only when verified rates exist.

See [the methodology](docs/PIPELINE_GUIDE.md), [full-run validation](docs/INTEGRATION_VALIDATION.md), and [historical code and outputs](legacy/README.md). The active submission is in `pipeline/`, `config/`, `tests/`, `tools/`, `evidence/`, and `deliverables/`.
