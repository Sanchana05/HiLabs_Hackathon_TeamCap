# C5–C6 validation on the supplied local data

The full C1–C6 pipeline completed on 2026-10-18 against the 2026-09-30 Health Net California in-network MRF. C2 linked that file to 30 confirmed California group PPO plan edges, while it is also linked to non-PPO plans. C3 scored the complete MRF 83.33/100 (B, `REVIEW_REQUIRED`); C4 selected 14,443 direct professional FFS rate contexts. The MRF SHA-256 is `3b3e4e220f421010b8ef925a51d4a3c17863b9fbaa853841c1a4927eb74a0960`.

C5 streamed the NPPES V2 main and secondary practice-location files through 2026-10-11, the 2026-10-12 deactivation report, and NUCC 26.1. An official [CMS Doctors and Clinicians file](https://data.cms.gov/provider-data/dataset/mj5m-pzi6), modified 2026-10-02, was streamed and filtered to the C4 NPIs. It yielded 482 California address records for 324 target NPIs. Its filtered file SHA-256 is `47d4149de03c29ca795ff8b2f0e562407079070bc6e05dc976856cfde7c7a8b1`.

| Measure | Result | Meaning |
| --- | ---: | --- |
| C4 selected rate contexts | 14,443 | Published rates in the PPO-linked shared file |
| Unique NPIs / TINs / NPI–TIN pairs | 3,155 / 2,465 / 3,195 | C5 input population |
| NPIs with a physical site candidate | 3,033 (96.13%) | Primarily NPPES; not independently verified |
| NPIs with a corroborated practice site | 177 (5.61%) | NPPES and CMS agree on at least one physical site |
| Direct TIN/site links | 0 | Neither CMS nor NPPES supplies this contract relationship |
| Exact Health Net PPO/site confirmations | 0 | No dated plan-filtered directory or authorized roster was supplied |
| Strict verified C6 rate rows | 0 | Exact PPO/site, TIN/site, and plan attribution gates remain unmet |
| C6 research-candidate rows | 220 | One TIN, one corroborated CA site, no alternate site, and one six-column rate per code |

The candidate Excel workbook has the six requested columns on its first sheet plus `Evidence` and `Scope and sources`. All 220 rows were independently reconciled to C4 rates and C5 CMS/NPPES address observations, with 220 distinct six-column keys. Its rate file is a **research candidate**, not a confirmed PPO contract file. [CMS shared-file guidance](https://www.cms.gov/files/document/transparency-coverage-8-steps-508.pdf) permits common negotiated data in a file linked to multiple plans; it does not establish the exact TIN/site or current PPO/site relationship for a provider. A current Health Net plan-filtered provider directory or contracted roster is still needed to resolve those links.

The master outputs are under `new/deliverables/`; the README records the rerun commands. `c5_summary.json`, `c6_candidate_summary.json`, and `c6_workbook_validation.json` retain the counts and validation result. Tests cover site conflicts, multi-site and multi-TIN cases, code-type and rate ambiguities, and strict verified-rate withholding.
