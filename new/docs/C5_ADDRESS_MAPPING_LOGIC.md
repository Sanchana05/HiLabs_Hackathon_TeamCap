# C5: Evidence-backed NPI/TIN/practice-site mapping

## Scope and core rule

The C4 rate rows provide an NPI and a TIN but no practice address. The selected Health Net MRF currently has `file_classification=MIXED` and `plan_attribution=SHARED_FILE_UNRESOLVED`: a rate or provider in that file cannot automatically be attributed to the California commercial group PPO.

C5 therefore makes **three separate decisions** for each `(NPI, TIN type, TIN, location)`:

1. **Practice site** — `corroborated`, `candidate`, `conflicted`, or `unresolved`.
2. **TIN/site link** — `proven` only when a current payer or provider/group record explicitly contains the same TIN and site; otherwise `unproven`.
3. **PPO/site participation** — `confirmed` only for a current payer record matching the NPI, physical location, exact configured PPO plan/network name, and plan year; `possible` for an exact-name result lacking current proof; otherwise `unknown`.

One provider may retain several location rows. A TIN with many providers may have several sites. Counts of peers sharing an address are never used to assign another provider to that address. NPPES-only addresses remain candidates even if the record was recently updated: its update timestamp is not an address-verification timestamp. The case statement's “about 80% stale” figure is a problem assumption, not a measured property of our extract.

## Sources and contribution

| Source | Role | Limitation |
| --- | --- | --- |
| C4 selected rates | Set of in-scope `(NPI, TIN type, TIN)` pairs and MRF provenance | No address or PPO-specific provider membership |
| NPPES V2 monthly primary and separate non-primary practice-location file | Type 1/2 identity, taxonomy, physical site candidates | Does not validate that a clinician currently practices at a site or is credentialed |
| NPPES overlapping weekly and deactivation data | Replace newer NPI records only when the weekly snapshot is later; flag deactivated NPIs | The weekly release overlapping the monthly snapshot is skipped to avoid duplicate support |
| NUCC taxonomy CSV | Standard specialty display name for the designated primary taxonomy | Taxonomy does not verify current specialty or service site |
| CMS Doctors and Clinicians national file | Independent NPI/site corroboration for Medicare-enrolled clinicians | Not a commercial PPO roster and not a PTD TIN crosswalk |
| Health Net commercial group PPO directory evidence | Exact plan/NPI/site confirmation, when a dated record can be obtained | No bulk/API route for this product has been established in the supplied materials; directory may not expose TIN or every provider |
| Provider/group-confirmed roster | Independent current site evidence; explicit TIN/site link if present | Requires an attributable, dated, authorized source |

NPPES [distributes secondary practice locations separately](https://download.cms.gov/nppes/NPI_Files.html) and says NPI issuance does not validate credentialing. CMS [publishes clinician/enrollment/group/address rows](https://data.cms.gov/provider-data/dataset/mj5m-pzi6). Health Net's [provider search](https://findaprovider.healthnetcalifornia.com/) is plan-filtered and updated more frequently than print, but its availability does not imply a public commercial group PPO API. The [CMS Provider Directory API FAQ](https://www.cms.gov/initiatives/burden-reduction/overview/interoperability/frequently-asked-questions/provider-directory-api) addresses other regulated products; it does not establish one for this PPO.

## Repeatable transformation

1. Stream every C4 `selected_rates.csv` into a disk-backed distinct provider-pair table. Keep TIN type, TIN as text, and C4 file IDs.
2. Stream the NPPES V2 main CSV using only needed column indexes; read its non-primary location file separately. Reconcile weekly updates only if their through-date is later than the monthly snapshot. Read the deactivation report. Select only NPIs present in C4. Type 1 and Type 2 both remain in scope.
3. Ingest any supplied CMS, payer, and provider/group evidence CSV. Each observation retains source, record locator, date, raw and normalized address, identity, plan name/year, and TIN when directly present.
4. Normalize common street suffixes, directional tokens, city, and ZIP to group the *same* site. Reject PO boxes as physical sites. Preserve suites; different suites in the same building trigger review in the absence of direct current evidence. This token normalizer is **not CASS or DPV certification** and does not assert deliverability.
5. Group observations by exact NPI and normalized location. NPPES primary and secondary observations are a single source family, not two independent votes. A current payer or provider/group confirmation, or current CMS clinician data agreeing with NPPES, can corroborate a site. A wrong-plan directory record never confirms this PPO. A deactivated NPI cannot yield a corroborated site. Site conflicts remain in the review queue.
6. Write `c5_provider_locations.csv`, `c5_evidence.csv`, `c5_review_queue.csv`, and `c5_summary.json`. An NPI with no valid site appears in the review queue with an empty address. The summary reports separate candidate, corroborated, TIN-link, and PPO-site coverage with clear NPI and pair denominators.

The implementation is in `pipeline/c5_address_mapper/resolve.py`; `C5_IMPLEMENTATION_PLAN.md` records the original execution plan and acceptance cases.

## C6 handoff and withholding rules

`pipeline/c6_rate_builder/verified_builder.py` consumes all C4 selected files and the C5 location table. Its six-column Excel/CSV rate file admits a row only when:

- the exact NPI/TIN/site is corroborated, the TIN/site link is proven, and the PPO/site is confirmed;
- the C4 rate row has an explicitly allowed PPO-only `plan_attribution`, and its source file is not `MIXED`; and
- exactly one C4 rate context projects to the requested `(NPI, TIN, address, billing code)` key.

The complete admitted C4 contexts are retained in `c6_rate_context_audit.csv`. Multiple settings, modifiers, rate types, or other contexts that collapse to the same six-column key go to `c6_ambiguous_projection.csv`. When current evidence cannot clear the gates, an Excel file with headers and zero rows is the honest result. The current shared MRF cannot produce verified PPO-specific rates by itself.

### Evidence-limited research candidates

CMS [permits the same in-network MRF to serve multiple plans when negotiated data is common](https://www.cms.gov/files/document/transparency-coverage-8-steps-508.pdf). The C2 index therefore supports treating rates in this Health Net shared file as **PPO-linked published candidates**, while the MRF does not identify the service site or independently verify current plan participation for each NPI/TIN/site. This is a narrower assertion than a verified PPO contract row.

`candidate_builder.py` writes a separate six-column candidate rate CSV and row-level evidence/review files. It admits only a C4 rate in a source URL linked by C2 to a confirmed California group PPO, for an NPI with exactly one C4 TIN and exactly one corroborated California site and no other plausible site candidate. It withholds conflicting code types or rates that would collapse into one six-column key. The Excel candidate workbook repeats the six required columns and carries `Evidence` and `Scope and sources` sheets explaining that TIN/site and exact PPO/site links remain unproven. The strict verified file is retained separately and remains empty until direct payer/roster evidence resolves those links.

## Reproduction and review

The README shows the standalone CLI and external evidence CSV schema. Input paths, monthly snapshot date, evaluation date, and exact PPO plan names are explicit. The standalone C5 command works while C2 is still running; the master runner calls the same function after C4. Tests cover multi-site NPI, shared TIN/different sites, wrong-plan record, direct TIN/site proof, PO-box-only unresolved case, and C6 ambiguous rate projection. This is evidence-based address mapping, not a claim that every provider has been verified.
