# C5 implementation plan: PTD NPI/TIN to practice location

**Status:** Implemented in `pipeline/c5_address_mapper/resolve.py` with a guarded C6 handoff; the real-input validation is recorded in `C5_VALIDATION_RESULTS.md`.  **Target:** California commercial group Health Net PPO.  **Rate-file snapshot:** 2026-09-30.  **Evidence evaluated as of:** 2026-10-18.  Preserve both dates; a current address does not prove where a provider practiced on the rate-file date.

## 1. Decision C5 must make

For every distinct `(npi, tin_type, tin)` from C4, produce zero or more *supported* California practice sites, with provenance and a reason for each decision. Record two independent conclusions:

- **Practice-site status:** `corroborated`, `candidate`, `conflicted`, or `unresolved`. This answers whether the NPI is supported at a physical service location and, when possible, whether that location is linked to this TIN.
- **PPO participation status:** `confirmed`, `possible`, or `unknown`. `confirmed` requires a current, exact Health Net commercial group PPO directory/roster result for that NPI and location, with plan/network identity; a rate in the shared MRF, an NPPES entry, or a Medicare record cannot establish it. If the directory does not expose a TIN, record `tin_link_status=unproven` even when PPO participation is confirmed.

Do not force one address per NPI or TIN. Do not infer that every NPI under a TIN practices at the TIN's most common address. TIN co-occurrence is a lead for searching, not independent confirmation of an individual site. A physical-looking address or California ZIP range is validation of format/geography, not proof of practice. Treat the PS's “about 80%” stale-address figure as a supplied problem assumption, not a measured result for our extract.

## 2. Actual handoff and data available

| Source | Current state | C5 use |
| --- | --- | --- |
| C2 `file_manifest.csv` | The Health Net California MRF is `MIXED`; 30 confirmed PPO plans and many other plans share it. C2 is still being refined. | Carry file and plan-attribution flags into C5. Do not mark all C4 providers PPO. |
| C4 `selected_rates.csv` / `c4_manifest.csv` | C4 selected rows include `npi`, `tin_type`, `tin`, `source_file_id`, `source_url`, `file_classification`, `plan_attribution`, billing context, and rate. One local MRF has a validation summary with 14,443 selected rate rows. | Stream distinct `(npi, tin_type, tin)`; preserve C4 source IDs and lineage. C5 must work from either a completed manifest or an explicit selected-rates file for independent development. |
| NPPES V2 monthly, 2026-10-12 | Available locally in `HiLabs_Hackathon_TeamCap/data/nppes/monthly_2026_10_12/`; main NPI and separate non-primary practice-location CSVs. | Baseline candidate locations and taxonomy, for Type 1 and Type 2. |
| NPPES weekly, 2026-10-05–11, and deactivation report | Available locally; weekly period overlaps the monthly snapshot. | Reconcile by NPI/update date; never append overlapping files as new independent evidence. Remove or flag deactivated NPIs. |
| NUCC 26.1 CSV | Available locally in `HiLabs_Hackathon_TeamCap/data/nucc/`. | Specialty label, with source/version retained. Check licensing before redistribution. |
| Health Net commercial group PPO directory/roster | Not supplied in the PS or checked-in data. Health Net offers a plan-filtered online directory. A bulk/API route for this specific product has not been established. | Highest-value plan/location evidence. First validate access, plan selection, NPI exposure, capture method, terms, and freshness on a small sample. Do not substitute a Medi-Cal or Marketplace directory. |
| CMS Doctors and Clinicians national file | Public Medicare clinician/enrollment/group/address rows. | Independent practice-location corroboration for covered clinicians. It cannot prove commercial PPO participation or the PTD TIN. |
| Provider or group website/confirmed roster | Optional public or authorized input, if dated and attributable. | Independent site corroboration; an authorized roster can link TIN where it contains that field. |

The existing `run_pipeline.py` C5–C7 path is only a 10,000-row demonstration from the first C4 file and includes synthetic NPPES seed rows and fallback addresses. Its address verification percentage and Excel file cannot be reported as measured C5 coverage.

## 3. Build sequence

### Phase A — Source feasibility and frozen input contract

1. Finalize the C4 handoff: read every selected-rates path from `c4_manifest.csv`, or an explicit path in standalone mode; require valid NPI and retain `tin_type` (`ein` versus `npi`). Deduplicate provider keys on disk so the MRF is never loaded into RAM.
2. Record input paths, hashes, versions, extraction date, and observation date. Use CLI/config parameters rather than machine-specific paths. C2 may finish later; C5 consumes its completed manifest when available but can be developed against the C4 validation output now.
3. Test the [Health Net Find a Provider](https://findaprovider.healthnetcalifornia.com/) flow for the **exact 2026 commercial group Full Network PPO** used by C2. Determine whether it offers a documented feed, export, or reproducible plan-filtered result with NPI and location. Save a sample evidence record and date. If only a human search page exists, use it for a limited adjudication set and leave remaining cases `unknown`; do not promise mass verification. Health Net says its online directory is updated more frequently than print and warns that some providers may be absent from the directory.

### Phase B — Candidate generation and identity checks

4. Stream the NPPES monthly V2 main file **and** separate non-primary practice-location file, selecting C4 NPIs. Reconcile the overlapping weekly update and deactivation report. Preserve every primary and non-primary physical candidate, the record update date, entity type, name, taxonomy, and raw address. Do not promote mailing addresses to practice sites; keep them only as audit clues.
5. Ingest a dated CMS Doctors and Clinicians snapshot for California, filtering C4 NPIs. Its clinician/enrollment/group/address rows may corroborate several sites per NPI. Treat Type 2 records separately because this file is clinician focused.
6. Add optional adapters for dated Health Net directory results and authorized provider/group rosters. Each adapter emits the same evidence schema. Validate NPI identity, Type 1 versus Type 2, name/organization compatibility, state, and site status before matching addresses. A directory result under a different plan or product is retained as a conflict, never as PPO proof.

### Phase C — Normalize, link, and adjudicate

7. Normalize street number, street name, suffix, unit, city, state, and ZIP; keep raw text and normalized fields. Reject obvious PO boxes as physical sites. Resolve unit-level differences conservatively: same building with different suites is not automatically the same practice site. A simple token normalizer is **not USPS CASS-certified**; report CASS/DPV validation only if a licensed validator is actually run.
8. Create one candidate row per `(npi, tin_type, tin, normalized_location, source)`, then group corroborating source observations under a stable location key. Do not count two NPPES releases as two independent sources. Keep an explicit `npi_location` link and a separate `tin_location` link. Link the latter only from a directory/roster or other direct organizational evidence; TIN peer clustering may prioritize manual review but cannot create it.
9. Apply auditable rules before any optional score:
   - `corroborated`: direct provider/group confirmation or matching independent current sources for the exact NPI and site, with no material conflict; state whether the TIN link is proven.
   - `candidate`: one plausible physical source or an old agreement without recent confirmation.
   - `conflicted`: current sources disagree on site, unit, identity, or active status.
   - `unresolved`: no valid physical practice site.
   - `ppo=confirmed`: exact Health Net commercial group PPO, NPI, and site match from a dated payer directory/roster. Otherwise use `possible` only for weaker plan evidence and `unknown` for no plan evidence. Never equate `corroborated` with PPO membership.
10. Retain all supported sites. If C6 needs a preferred display site, choose one only by explicit tie-breaker (direct exact PPO+TIN site, then direct provider-confirmed site, then most recent independent corroboration); preserve other locations and an ambiguity flag. Never create a placeholder string that looks like a real address.

### Phase D — Integration and measurement

11. Emit `c5_provider_locations.csv` or Parquet (one row per NPI/TIN/location decision), `c5_evidence.csv` (one row per source observation), `c5_review_queue.csv`, and `c5_summary.json`. The primary location table includes `npi`, `tin_type`, `tin`, `entity_type`, `address`, `specialty`, `practice_site_status`, `tin_link_status`, `ppo_participation_status`, `source_ids`, `observed_as_of`, `last_confirmed`, `reason_codes`, and C4 source file ID. Evidence contains exact source URL/file, record locator, raw/normalized address, source snapshot date, retrieval date, plan/network label, and hashes where appropriate.
12. Make C6 join one-to-many on `(npi, tin_type, tin)` only for eligible C5 locations. Preserve C4 rate context (code type, modifier, setting, rate type, file attribution) until the final projection so distinct rates are not silently collapsed when expanded across addresses. The six required competition columns may be exported, but a companion audit file must retain status and provenance. Unresolved providers go to a separate file, not a fabricated address row. A `MIXED` file cannot yield a universally “PPO verified” Excel deliverable without provider-level evidence.
13. Summary metrics must report denominators clearly: unique C4 NPIs, unique NPI/TIN pairs, share with ≥1 physical candidate, share with a corroborated site, share with an evidenced TIN-site link, share with exact PPO site confirmation, and unresolved/conflicted shares. Break out Type 1 and Type 2. Do not label NPPES-only or synthetic matches “verified.”

## 4. Acceptance gates before plugging into the pipeline

- A standalone C5 run accepts C4 output and explicit evidence files, writes deterministic results, and works while C2 is still running.
- Tests cover two NPIs sharing a TIN but practicing at different sites; one NPI with two sites; conflicting suites; Type 2 organization; deactivated NPI; mailing-only/PO-box data; missing directory evidence; wrong-plan directory hit; exact PPO hit without TIN; and overlapping NPPES monthly/weekly records.
- Review a stratified sample of decisions against source records: corroborated, candidate, conflicted, unresolved, Type 1, Type 2, and multi-location. Report both false-link and missed-link findings.
- Every `confirmed` PPO site points to a dated exact-plan payer record. Every `corroborated` practice site points to direct confirmation or independent supporting records. No synthetic address or unsupported confidence score reaches C6.
- README and master logic document the sources actually used, unavailable sources, source dates, rules, review queue, and measured coverage. The current C5 demo language and “CASS compliant” claim must be replaced when implementation begins.

## Source notes

- [Problem statement](../../../PS.txt): permits additional public sources, explicitly flags NPPES staleness and multi-location relationships, and requires logic and verified-address coverage.
- [CMS NPPES downloadable files](https://download.cms.gov/nppes/NPI_Files.html): V2 includes the separate non-primary practice-location file; NPI issuance does not validate licensing or credentialing.
- [CMS Doctors and Clinicians national file](https://data.cms.gov/provider-data/dataset/mj5m-pzi6): clinician/enrollment/group/address level with multiple rows for multiple practice locations.
- [Health Net Find a Provider](https://findaprovider.healthnetcalifornia.com/) and [ProviderSearch](https://www.healthnet.com/portal/member/providerSearch.action?access=true): plan selection matters; the directory can change and may omit some providers.
- [CMS Provider Directory API FAQ](https://www.cms.gov/initiatives/burden-reduction/overview/interoperability/frequently-asked-questions/provider-directory-api): the public API mandate discussed there covers MA/Medicaid/CHIP and certain exchange issuers; it does not establish a commercial group PPO API for this use case.
