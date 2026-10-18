# Local data inventory

Checked on 2026-10-17. Raw data and generated files are ignored by Git.

| Input | Local status | Use |
| --- | --- | --- |
| NPPES monthly V2, dated 2026-10-12 | ZIP at repo root; 10 files extracted to `data/nppes/monthly_2026_10_12/` | Main NPI records, primary practice address, taxonomy codes, and the separate non-primary practice-location file. |
| NPPES weekly V2, 2026-10-05 through 2026-10-11 | ZIP at repo root; 10 files extracted to `data/nppes/weekly_2026_10_05_11/` | Incremental update. Its date range overlaps the monthly snapshot; do not append it without reconciling by NPI. |
| NPPES deactivation report, dated 2026-10-12 | ZIP at repo root; workbook extracted to `data/nppes/deactivated_2026_10_12/` | Cross-check deactivated NPIs. |
| `Rate Benchmarking Individual Weights_Hackathon.xlsx` | At repo root | Contains `Taxonomy-Spec Xwalk` (213 individual-provider mappings), `Specialty Weights` (48 records), and `Spec-Proc Weights` (946 records). The crosswalk does not cover Type 2 organizations. |
| Centene index files | 11 JSON files committed under `data/indexes/` in the current submission | Required to run network mapping. |
| NUCC taxonomy CSV, version 26.1 | Downloaded to `data/nucc/nucc_taxonomy_261.csv` from [NUCC](https://nucc.org/index.php/code-sets-mainmenu-41/provider-taxonomy-mainmenu-40/csv-mainmenu-57); 883 rows | Maps taxonomy codes to standard grouping, classification, specialization, and display names, including Type 2 taxonomy. |

Checks performed: all 21 extracted files match their archive entry sizes; the monthly and weekly NPI and practice-location CSVs parse with the expected header/data column counts; both workbooks open. This is a structural check, not a complete row-by-row data audit.

The NUCC CSV parses with 883 rows and eight columns. NUCC states that commercial use requires a license.

For the current submission, the small indexes are versioned. The large rate and NPPES source files remain local prerequisites for a full rerun; see the root README for the exact input layout and commands.
