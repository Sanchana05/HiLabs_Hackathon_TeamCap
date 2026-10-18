# Master Logic File: Centene Commercial California PPO Rate Curation
**Official Hackathon Deliverable 2**

This document establishes the end-to-end logic for:
1. **Part A: Identifying the PPO Network and Ruling Out HMO, EPO, and POS (Challenges C1 & C2)**
2. **Part B: Resolving Provider Rates and Multi-Rate Conflicts (Challenge C4)**
3. **Part C: Triangulating TINs, NPIs, and Stale Addresses via Network Consensus (Challenge C5)**

---

# C1 and C2: index inventory and PPO evidence

## Input and identity

Run C1/C2 from the 11 supplied September 2026 index files. C1 preserves the source index, source block, index date, issuer, plan sponsor, exact plan name, plan ID, and `plan_id_type` on each plan-to-file edge. Deduplication removes only identical edges. A sponsor EIN is not a unique product ID; distinct names sharing an EIN remain distinct rows. CMS defines `plan_id_type` as EIN or HIOS in its [Table of Contents schema](https://github.com/CMSgov/price-transparency-guide/blob/master/schemas/table-of-contents/table-of-contents.json).

The 11 filenames contain 10 distinct file hashes: `2026-09-28_qualchoice_city_of_fort_smith_index.json` is byte-identical to `2026-09-28_qualchoice_big_four_index.json`. The inventory records this duplicate and C1 retains both source names on any deduplicated edge.

The index date proves when the index was last updated. It does not prove that every listed employer plan was active on that date. C2 rejects post-cutoff or missing dates, but does not assert active enrollment.

## Evidence rules

The versioned register in `config/ppo_evidence_sources.csv` contains 34 direct 2026 Health Net Small Group Full Network PPO EOC links from [Health Net's official plan materials](https://www.healthnet.com/content/healthnet/en_us/find-a-plan/small-business/small-plans/forms-and-documents.html). The exact EOC title is matched to the exact index plan name after case and whitespace normalization only. Benefit variants, percentages, and `INF` suffixes are never merged. A HIOS plan ID is matched only when the evidence register supplies the same HIOS ID. An EIN can confirm the published plan *type* through an exact name match, but cannot establish product identity or provider membership. An invalid EIN format is retained as an anomaly.

C2 also uses a versioned extract of the [CMS 2026 Plan Attributes PUF](https://www.cms.gov/marketplace/resources/data/public-use-files) and the [CMS data dictionary](https://www.cms.gov/files/document/planattributes-datadictionary-py26.pdf). For Ambetter individual plans, a regulatory plan-type match requires the **same state, market, 10-character HIOS product ID, and exact marketing name**. All matching 14-character standard components must agree on `PlanType`. The product ID alone is not an exact plan ID. CMS `PlanType=PPO` confirms PPO product type, but `NetworkId` does not by itself prove the provider network name or membership. CMS `HMO`, `EPO`, and `POS` matches are excluded from the pure PPO set. A conflicting index name sends the edge to review.

The [Ambetter California 2026 plan-materials page](https://www.ambetterhealth.com/en/ca/health-plans/Plan_Materials/?group=ifp) supplies 51 versioned EOC links. An exact carrier EOC title can confirm PPO or HMO product type for California individual plans. Matching EOCs identify the PPO network as **Ambetter PPO Network**. Names that differ by CSR, Federal, or dental/vision suffix stay provisional or unresolved unless their exact variant is documented. The [Fidelis Essential Plan page](https://www.fideliscare.org/Shop-For-A-Plan/Our-Plans/Essential-Plan) documents in-network-only coverage apart from emergencies, so the six Essential Plan index edges are non-PPO; the two 200–250 variants are additionally flagged because that program ended June 30, 2026. The [QualChoice PPO page](https://www.qualchoice.com/shop-health-plans-and-services/preferred-provider-organization-ppo-plans) establishes a PPO product family, but does not identify a specific indexed employer plan; explicit PPO names therefore remain provisional and unlabeled names remain unresolved.

C2 fails if a versioned reference is missing or malformed. The CMS extract can be rebuilt from the official ZIP with `build_cms_reference.py`; the Ambetter EOC register can be rebuilt from a saved copy of its official plan-materials page with `build_ambetter_reference.py`. The CMS source ZIP used for this run has SHA-256 `954e697885efcb709aed0be1de14075afe11704bf3447372960d08c879950af2`. The committed extracts and their SHA-256 hashes are in `c2_summary.json`.

## Decision order

1. Process all four indexed brands and their group or individual plans. Require a source index and index date no later than 2026-09-30; reject inconsistent URL and HIOS state evidence. A missing state marker can remain unknown without excluding an otherwise valid plan. Fidelis Essential Plan's `EP` identifier is not interpreted as a state code.
2. Apply the Fidelis Essential Plan family rule and exact CMS regulatory plan-type matches for Ambetter where available. Compare plan-name network tokens to regulatory type and review conflicts.
3. Apply exact 2026 Ambetter California EOC matches, then detect PPO+HMO/EPO/POS/EOA conflicts and retiree/public-program names for review.
4. Exclude explicit HMO, EPO, POS, or EOA labels from the pure PPO candidate set. These name-based exclusions do not establish a precise contract or benefit design.
5. Confirm Health Net California group PPO product and **Full Network PPO** only for applicable exact official EOC names. Keep other PPO-labeled plans, including `CUSPPO`, as `PROVISIONAL_PPO` with `UNKNOWN_NETWORK`; keep unlabeled plans `UNRESOLVED`.

Every decision retains a rule version, reason, anomaly tags, evidence ID and URL when present, match basis, and required follow-up evidence. The review queue includes both provisional and unresolved edges.

The supplied Health Net index uses an alphanumeric value `67138CA073` on the 30 EOC-matched metal plans even though it labels that field as EIN. C2 flags `INVALID_EIN_FORMAT`. The exact EOC names support PPO product-type classification; the anomalous identifier cannot be used as an EIN or plan-level join key.

## Rate-file handoff

The C2 `plan_decisions.csv`, `review_queue.csv`, and `all_file_inventory.csv` cover all four brands. The C3/C4 `file_manifest.csv` includes only **Health Net California group PPO-linked files**, marked by `downstream_target` on plan decisions and explicit target PPO counts on the manifest. Ambetter, Fidelis, QualChoice, and Health Net Oregon never enter C3/C4 through this handoff. The manifest preserves `rate_file_url`, `rate_file_name`, and `file_classification`. A file linked by PPO and explicit non-PPO plans is `MIXED` with `SHARED_FILE_UNRESOLVED`. A provisional-only file is `UNKNOWN`; `PPO_ONLY` is reserved for files with confirmed PPO links and no provisional, non-PPO, or unresolved links in the supplied indexes. It still never proves every rate or provider belongs to the PPO network. CMS permits multiple plans to reference one rate file ([technical clarification](https://www.cms.gov/initiatives/healthplan-price-transparency/overview/resources/technical-clarification)).

For the supplied corpus, the single selected Health Net CA rate file has 30 confirmed and 422 provisional PPO-linked plan-file edges, 852 explicitly non-PPO edges, and 8 unresolved edges. It is `MIXED`. Across all 33 rate-file URLs, C2 classifies 3,270 deduplicated plan-file edges and reports per-brand counts in `c2_summary.json`. Provider-level PPO membership remains unverified and must not be inferred by C3/C4 from this file alone.

## Repeatable run

From the repository root with the dependencies in `requirements.txt`:

```powershell
$env:PYTHONPATH = "new"
python -m pipeline.c2_network_mapper.run_c2 --index-dir data/indexes --output-dir deliverables
python -m unittest discover -s tests -p test_c2_network_mapper.py -v
```

Use `--index-dir` for another directory, repeated `--index` arguments for explicit files, or `--evidence` for a reviewed Health Net evidence register. `c2_summary.json` records input index and all evidence SHA-256 hashes. The 11 supplied indexes are versioned under `data/indexes`; the much larger rate MRF remains a local input.


---

# C4: Complete-file rate extraction and auditable selection

## Contract and scope

C4 accepts one or more local CMS Transparency in Coverage in-network files through `RateFileInput`, repeated `--file`, or a C2 `file_manifest.csv` plus `--rate-dir`. Optional C3 details bind each input to its SHA-256 and quality status. C4 processes every `in_network` item and every published price; it has no code or row cap. Files can be JSON or JSON.gz. Its temporary SQLite state is disk-backed and removed after a successful or failed run.

The unit of output is a **file rate**, never a verified PPO contract. A `MIXED` file yields `plan_attribution=SHARED_FILE_UNRESOLVED`; all other files yield `UNVERIFIED_NETWORK_MEMBERSHIP`. A later network-attribution component can join verified plan/provider evidence using the source file ID and NPI/TIN keys without changing C4's extraction.

## Published schema versus our selection policy

[CMS's in-network field guide](https://github.com/CMSgov/price-transparency-guide/blob/master/schemas/in-network-rates/README.md) defines five `negotiated_type` values and distinguishes dollar amounts from whole-number percentages. It makes `billing_class`, `setting`, and (for professional rates) `service_code` relevant, and permits code modifiers, bundled arrangements, `CSTM-00` wildcards, and `9999-12-31` when no expiration is stated. C4 follows those definitions. HiLabs' [public roster-automation paper](https://www.hilabs.com/new-website/pdf/Beyond_Standardization-Maximizing_Value_through_End-to-End_Roster_Automation.pdf) discusses provider-data validation, but gives no published rule for choosing between conflicting TiC negotiated prices. The rate-selection policy below is therefore our explicit analytic policy, **not a HiLabs or CMS mandated preference**.

1. Stream `provider_references` into SQLite, then stream `in_network` items and expand each direct/referenced provider group into NPI/TIN associations. The reference pass handles either top-level JSON property order. Expand every listed service code independently.
2. Validate presence and syntax of item identity, arrangement, negotiated type, amount, billing class, setting, expiration, service code, and provider keys. Normalize a valid hyphenated EIN to nine digits in `tin`, retaining the original spelling in `tin_raw`. Reject missing/unknown provider links, zero, nonnumeric or unrepresentable rates, expired rows (relative to required `--as-of`), and malformed fields. Preserve each rejected row and its reason. `npi: [0]` is an unknown NPI, so cannot be selected as a provider-level rate.
3. Keep valid nonbenchmark rates in the decision file. This includes `derived`, `fee schedule`, `percentage`, `per diem`, institutional/both billing, bundles/capitation, and `CSTM-00`. The `rate_unit` column distinguishes percent, USD per day, and USD. A `VALID_NON_BENCHMARK` decision means the rate was parsed and validated; it does not convert a percentage or per-day amount into a service-dollar benchmark.
4. For **professional, fee-for-service, negotiated dollar** rates with a concrete billing and service code, partition by source file, NPI, TIN type/value, code type/version, code, item name/description, arrangement, negotiated type, billing class, setting, service code, modifiers, bundle contents, covered services, and additional information. These fields are retained because collapsing across them could conflate different services or contracts.
5. Remove exact published duplicates in that context, retaining the duplicate row and reason in the decision file. If one candidate remains, select it. If several distinct published candidates remain, select the **lower median observed candidate** by numeric amount, then source order. The selected amount is always an actual published rate; C4 never calculates and outputs a synthetic median. Alternates remain in the decision file and are **not** claimed to be inactive or wrong. Without plan-tier or contract evidence, the chosen row is a representative benchmark, not the uniquely applicable reimbursement.

Expiration is used to reject dates before the as-of date. A later expiration does **not** prove a newer or more applicable contract. `9999-12-31` is preserved as `NO_STATED_EXPIRY`, not claimed to be an active contract. We do not prefer POS 11 over another place of service: distinct settings remain distinct outputs.

C4 does not impose an arbitrary maximum dollar rate: an unusually high published amount remains traceable and can be reviewed with C3's outlier metric or an external benchmark. A positive amount alone does not establish that a contract is active or applies to the target PPO.

## Outputs and interfaces

`c4_manifest.csv` has one row per input and relative paths. Each file gets a stable directory named by a hash of the source URL (or filename):

- `selected_rates.csv`: one published benchmark candidate per exact context; includes `rate`, source locator, `rates_considered_count`, and `decision_reason`.
- `rate_decisions.csv`: every expanded rate row, including invalid, valid nonbenchmark, exact duplicates, selected, and alternate candidates. An alternate points to `selected_source_locator`.
- `c4_summary.json`: SHA-256, source URL, as-of date, C3 status, file classification, attribution limitation, policy, and reconciled counts.

CSV is the interchange contract for C5/C6 and later network evidence. NPI and TIN must be read as strings. No raw MRF or temporary SQLite database is committed.

Run from the repository root after downloading the files:

```powershell
$env:PYTHONPATH = "new"
python -m pipeline.c4_rate_extractor.rate_extractor --manifest outputs/pipeline-smoke/file_manifest.csv --rate-dir data/ratefiles --c3-details deliverables/file_quality_details.json --as-of 2026-10-18 --output-dir outputs/c4
```

Alternatively repeat `--file path/to/file.json.gz`. The Python port is `run_files([RateFileInput(path, source_url, file_classification, expected_sha256, c3_quality_status)], output_dir, as_of=date(...))`.

## Gates and interpretation

The full master runner executes C4 after C3 and records C4's complete counts. C5 takes the full selected-rate CSV as its input. Do not label C4 rows as PPO-network rates until the C1/C2 attribution and plan-specific provider evidence are established.


---

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

