# Centene California PPO rate curation

**HiLabs Hackathon submission | TeamCap | 2026 source snapshot**

This repository parses Centene Transparency in Coverage indexes, identifies California commercial group PPO plan references, audits the linked machine readable rate file, selects published professional rates, and checks provider practice sites against independent sources. The final export separates **research candidates** from **verified PPO rates**. A shared rate file is not proof of a PPO-specific contract.

## Submission files

The flat [deliverables](deliverables) folder contains exactly the four files requested in the problem statement. Supporting run outputs, the strict verified workbook, and the video script are in [audit](audit/README.md).

| Requirement | File | Current result |
| --- | --- | --- |
| Rate file (Excel) | [Centene_CA_Commercial_PPO_Rate_Candidates.xlsx](deliverables/Centene_CA_Commercial_PPO_Rate_Candidates.xlsx) | 220 published-rate research candidates. The workbook discloses that PPO/site and TIN/site links remain unverified. |
| Logic file | [Logic_File.md](deliverables/Logic_File.md) | Network, rate, and address rules. |
| File quality metrics | [File_Quality_Metrics.md](deliverables/File_Quality_Metrics.md) | C3 methodology and scores. |
| Summary file | [Summary_Metrics.md](deliverables/Summary_Metrics.md) | C1–C6 run counts and limitations. |

The [strict verified workbook](audit/c6/Centene_CA_Commercial_PPO_Provider_Rates.xlsx) has headers only because zero rows pass every evidence gate. The optional C7 benchmark is withheld until a verified C6 rate exists. The [project scorecard](audit/Project_Evaluation_Scorecard.md) tracks candidate coverage and verified yield separately. The [video script](audit/VIDEO_SCRIPT.md) is ready; no video recording has been delivered.

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

The command creates `outputs/full-run/Centene_CA_Commercial_PPO_Rate_Candidates.xlsx` **as part of the run**, alongside `outputs/full-run/c6/Centene_CA_Commercial_PPO_Provider_Rates.xlsx`, logic, quality, summary, and C1–C6 audit files. The output directory is ignored by Git so reruns do not silently change the committed submission. After reviewing a future run, copy only the four named submission files into `deliverables/`; place supporting audit outputs in `audit/`. Never direct the full runner at `deliverables/`, which is reserved for the four-file submission. A different snapshot may produce different counts.

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

See [the methodology](docs/PIPELINE_GUIDE.md), [full-run validation](docs/INTEGRATION_VALIDATION.md), [supporting audit files](audit/README.md), and [historical code and outputs](legacy/README.md). The active submission is in `pipeline/`, `config/`, `tests/`, `tools/`, `evidence/`, `audit/`, and `deliverables/`.
