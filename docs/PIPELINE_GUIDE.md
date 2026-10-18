# Pipeline guide

The [root README](../README.md) contains the tested end-to-end rerun command, input layout, deliverable index, and validation command. This document maps the active modules to their methods.

| Stage | Module | Method and audit output |
| --- | --- | --- |
| C1 | `pipeline/c1_index_parser/` | Stream Centene indexes and deduplicate plan-file edges. |
| C2 | `pipeline/c2_network_mapper/` | Classify exact PPO evidence, exclusions, and unresolved plans; output `plan_decisions.csv` and `file_manifest.csv`. |
| C3 | `pipeline/c3_file_grader/` | Score the complete selected machine readable file; output quality scorecard and details. |
| C4 | `pipeline/c4_rate_extractor/` | Validate rate contexts, choose published professional FFS prices, and retain rejected alternatives in the C4 audit. |
| C5 | `pipeline/c5_address_mapper/` | Resolve NPI/TIN practice-site evidence from dated NPPES and CMS sources; retain provenance and conflicts. |
| C6 | `pipeline/c6_rate_builder/` | Generate the strict verified workbook and the separate research-candidate workbook with evidence and scope sheets. |
| C7 | `pipeline/c7_cost_effectiveness/` | Benchmark only verified C6 rows when available. |

The stage methods are documented in [C1–C2](C1_C2_METHODOLOGY_AND_LOGIC.md), [C3](C3_FILE_QUALITY_METRICS.md), [C4](C4_RATE_EXTRACTION_LOGIC.md), [C5](C5_ADDRESS_MAPPING_LOGIC.md), and [C7](C7_COST_EFFECTIVENESS_LOGIC.md). The current source run and limitations are recorded in [integration validation](INTEGRATION_VALIDATION.md).

The master command `python -m pipeline.run_pipeline` always generates the candidate Excel when C5 inputs are present. Its first worksheet has the six requested fields: NPI, TIN, Address, Billing Code, Specialty, Rate. The other worksheets disclose source evidence and unverified claims. No command or code path promotes a `MIXED` source file's rate to a verified PPO rate without the required exact evidence.
