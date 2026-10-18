# Centene California commercial-group PPO classification plan

**Purpose:** identify the PPO *plans*, the provider *network(s)* those plans use, and the Centene rate *files* that reference them. Preserve evidence and uncertainty at each level. This is the implementation plan for C1 and C2 of the local `../PS.txt`; it defines the handoff to C3–C6 without claiming that a plan name or shared rate file proves network membership.

**Snapshot:** use the date on each Centene index and its linked rate file. The Health Net California index inspected in the team Drive is dated **2026-09-30**. Do not mix later product changes into that snapshot. Health Net says its California commercial-group exit begins **2027-02-28**, with employer-specific end dates; its 2026 coverage remains relevant to this challenge ([Health Net transition notice](https://www.healthnet.com/content/healthnet/en_us/providers/commercial-group-transition.html)).

## 1. What counts as success under the problem statement

The target is **Centene → California → commercial group → PPO**. We must explain how HMO, EPO, POS, and ambiguous plans were ruled out. C1 needs a complete plan-to-file table with duplicate relationships removed. C2 needs an auditable plan and network decision, plus the distinct file URLs used by included plans. A shared URL does **not** become a PPO-only file. C3 must grade every rate file used; C4–C6 must carry the network decision and its limits into provider rates, including both Type 1 and Type 2 NPIs. The PS values explained logic over tooling and requires a reproducible repo without hardcoded paths.

The three distinct objects must stay separate:

| Object | Identity to retain | What we can conclude |
| --- | --- | --- |
| Plan/product | Index snapshot, issuer, market, `plan_id_type`, `plan_id`, exact plan name, source block | Whether this *plan* is documented as PPO. An EIN may identify an employer/sponsor, so it is not a unique product key by itself. |
| Provider network | Network name/ID, geography, effective period, authoritative source | Whether the plan uses a specific PPO network. Plan type and network name are related but not interchangeable. |
| Rate file | Canonical URL, file date, hash, every linked plan | Which plans reference the file. The rate records alone may not say which one of several linked products they belong to. |

CMS's [Table of Contents schema](https://github.com/CMSgov/price-transparency-guide/blob/master/schemas/table-of-contents/table-of-contents.json) defines `reporting_plans`, `plan_market_type`, and linked `in_network_files`, but does not require a PPO field in the September 2026 index. CMS explicitly permits multiple plans to share one file when the negotiated data is the same ([technical clarification, questions 22 and 4](https://www.cms.gov/initiatives/healthplan-price-transparency/overview/resources/technical-clarification)). **Inference:** a file linked by HMO and PPO entries cannot, by its URL alone, establish a PPO-only provider roster.

## 2. Evidence: what other organizations publish and what we can adapt

There is no public, universal algorithm that turns a Centene index row into a verified PPO plan. Use the following evidence in descending order of authority. Record the source URL, document title, plan year/effective date, exact name/identifier, network label, page or section, capture date, and the reviewer decision. A document for another year or another market is context, not a match.

| Evidence | How to use it here | Limit |
| --- | --- | --- |
| Current plan-specific Evidence of Coverage (EOC), Certificate of Insurance, Summary of Benefits and Coverage (SBC), employer benefit document, or insurer product crosswalk | Seek an exact plan or contract ID; confirm California group market, PPO label, named network, and relevant effective date. Check routine out-of-network benefits and referral/PCP rules when the label conflicts. | Generic PPO brochures do not prove a custom employer plan is PPO. An SBC is useful only when its exact plan/year matches. |
| Payer's plan/network selector and provider directory | Check that the specific plan appears under a PPO network; save network name/ID and geography. Compare a stratified sample of NPIs later as a consistency check. | A provider's appearance in a broad directory does not prove that every linked plan uses that network. Health Net itself says to select the correct plan because networks differ ([ProviderSearch](https://www.healthnet.com/portal/member/providerSearch.action?access=true)). |
| Payer's 2026 product materials | Build a controlled vocabulary of PPO, HMO, EPO, POS, and EOA product families. [Health Net's 2026 small-group EOCs](https://www.healthnet.com/content/healthnet/en_us/find-a-plan/small-business/small-plans/forms-and-documents.html) list Full Network PPO products; its [large-group guide](https://www.healthnet.com/content/dam/centene/healthnet/pdfs/broker/ca/large/fb/2026/ec-portfolio-guide-2026.pdf) distinguishes traditional PPO from EOA. | A family match supports, but does not settle, a custom plan or an altered deductible variant. |
| Centene index and in-network MRF | Establish issuer, market, exact plan-file relationship, reporting date, and any explicit network/product metadata actually present. | `group` alone does not establish commercial PPO; `healthnet-ca` in a filename establishes file context, not each plan's state or network. |
| State filings, insurer confirmation, or employer benefits administrator | Escalate custom, conflicting, or unlabeled products with exact name/ID and effective date. Log the response. | Availability varies; an unverified assumption must stay unresolved. |
| Similar plan names, shared EIN, provider overlap, or model/RAG output | Generate candidate matches and prioritize review. | Supporting clues only; they cannot override contradictory plan-specific documents. |

The classification distinction is substantive: a PPO generally covers non-emergency out-of-network care at higher cost, while an EPO generally does not; POS typically has referral/gatekeeper rules ([CMS network-type guide](https://www.cms.gov/about-cms/agency-information/omh/downloads/omh_dwnld-enrollmenttoolkit.pdf)). Health Net calls EOA an HMO product that offers a PPO tier for some services ([large-group options](https://www.healthnet.com/en_us/find-a-plan/large-employers/type-of-plans.html)). **Decision for this PS:** exclude EOA from the *pure PPO-plan* set, but flag its PPO-tier overlap for a separate sensitivity analysis. EPO, HMO, and POS labels also remain out unless a plan-specific authoritative document resolves the apparent conflict. Do not infer PPO merely from “no referral”: EPO products can share that feature.

HiLabs publicly describes [MCheck NetworkIQ](https://www.hilabs.com/our-solutions/mcheck-networkiq) as reconciling internal, credentialing, claims, and third-party provider data, and [MCheck Provider Data Accuracy](https://www.hilabs.com/our-solutions/mcheck-directory-accuracy) as scoring provider attributes for reliability, relevance, and recency. **Adaptation, not a claim about HiLabs' proprietary PPO classifier:** keep source-specific evidence, conflict flags, recency, confidence, and a human review loop for *plan/network* facts. The products' public pages do not disclose a Centene plan-classification algorithm or establish our access to them. MCheck/R3 is especially relevant later to C5; it does not by itself solve C2.

## 3. Baseline to reconcile before new decisions

The [team's Health Net index](https://drive.google.com/file/d/1wJwcdXBqdhlE5FHnXt-Wybx3hKZqsJsX/view) has **1,312** group-plan entries in its `healthnet-ca` block. The [prior candidate CSV](https://drive.google.com/file/d/1vN9RL7HZLznGycxD0scNgKjYfq5z9xLJ/view) contains **452** explicit, non-conflicting `PPO`-name entries; all point to the same in-network URL. In the CA block there are also 719 explicit HMO, 6 explicit POS, 3 names containing both PPO and EPO, and 132 without a standalone PPO/HMO/EPO/POS token. Of those 132, **127** contain `EOA`; one is `CA L CUSPPO 15/250/20% RAP`, which the word-boundary rule misses. These are *entry counts from one snapshot*, not counts of distinct networks or validated products.

The 452 include 34 standard metal-plan name variants. Thirty have an exact name on Health Net's 2026 Full Network PPO EOC list. Four index entries—Gold and Silver HDHP `1800` variants, each with/without `INF`—differ from the official `1700` names and need a date/version check. `CA L CUS PPO HN Retiree` needs a commercial-group eligibility check. Treat the rest, especially custom employer plans, as candidates until plan-specific evidence is recorded. These findings are a **review starting point**, not final labels.

## 4. Stepwise implementation, with a PS check at every gate

### Step 0 — Freeze inputs and the target date

1. Put the four Centene index families and any nested indexes in ignored `data/indexes/`; put rate files in ignored `data/ratefiles/`. Preserve original filenames and bytes. Record URL/Drive source, download time, `last_updated_on`, byte size, and SHA-256 in a manifest.
2. Choose a single September 2026 Centene snapshot. Do not compare a 2027 benefit document to a 2026 plan without explicit continuity evidence. Keep later sources in a separate `valid_from`/`valid_to` field.
3. Save the relevant issuer product documents or stable links in an evidence register. Record inaccessible evidence as `not_obtained`, never as a negative match.

**PS check:** Centene only, with a reproducible input manifest; no provider or address work yet. **Exit condition:** all index families expected by the PS are parsed or documented as missing.

### Step 1 — Build C1's lossless plan-to-file inventory

1. Reuse `TOC/centene_index_pipeline.py` to traverse all `reporting_structure` blocks and nested indexes. Keep one raw row per plan/file relation and source row position, plus the original JSON fields for audit.
2. Canonicalize URLs conservatively (scheme/host case, fragment removal; do not strip meaningful query parameters). Deduplicate *identical plan-file relationships* using snapshot, source, issuer, plan ID type/value, exact name, market, and URL. Keep a second table with one row per unique URL. Never collapse plans because they share an EIN or URL.
3. Validate required index fields against the [CMS schema](https://github.com/CMSgov/price-transparency-guide/blob/master/schemas/table-of-contents/table-of-contents.json). Count missing names, IDs, markets, invalid URLs, duplicate relationships, and failures by brand.

**PS check:** directly satisfies C1's brand/name/ID/market/URL table and duplicate handling. **Exit condition:** every input plan-file edge is accounted for, and totals reconcile to the raw blocks.

### Step 2 — Apply strict scope gates before network classification

For each row, evaluate separately: `payer=Centene`, `state=CA`, `market=group`, `commercial=true`, and `snapshot_active=true`. Use explicit plan metadata first. Use insurer/brand, a CA source block or filename, and 2026 product materials as corroboration. Do **not** treat a CA filename as sufficient proof of a plan's state; do not treat `group` as sufficient proof of commercial status when names like “Retiree” or public-program terms conflict. Hold contradictory or missing fields for review. Exclude explicit individual, Medicare, Medicaid/Medi-Cal, out-of-state, or out-of-period entries with a reason code.

**PS check:** enforces Centene / CA / commercial group before PPO; prevents a PPO in Oregon or Medicare from entering C2. **Exit condition:** every row has a scope decision, evidence fields, and a reason code.

### Step 3 — Generate network candidates without finalizing them

1. Tokenize names on word and punctuation boundaries; retain the raw string. Recognize `PPO`, `HMO`, `EPO`, `POS`, `EOA`, and likely collapsed strings such as `CUSPPO`. Use aliases only if backed by product documents. Search plan name and any real network/product metadata separately.
2. Put `PPO` alone into `PPO_CANDIDATE`; `PPO+EPO/HMO/POS` into `CONFLICT_REVIEW`; clear HMO/EPO/POS/EOA into `NON_PPO_CANDIDATE`; no label into `UNLABELED_REVIEW`. Add anomaly queues for retiree/public-program words, exact-name mismatch, missing URL, and same plan key with conflicting labels.
3. Avoid a hard “PPO” label from a generic metal level, HSA/HDHP, `INF`, an employer name, a shared EIN, or a shared MRF. HSA/HDHP and infertility variants are benefit features, not network proof.

**PS check:** C2 explicitly asks for inconsistent and unlabeled names, and how HMO/EPO/POS were ruled out. **Exit condition:** every in-scope plan is in a candidate or review bucket; no silent default to PPO.

### Step 4 — Resolve with a documented evidence hierarchy

For each candidate or ambiguous family, search in this order:

1. Exact 2026 plan ID/contract or exact plan name in a plan-specific EOC, COI, SBC, employer document, or insurer crosswalk. Capture the explicit plan type and network name/ID. If no exact ID exists, require exact issuer, market, year, and benefit variant; fuzzy name similarity alone is insufficient.
2. The payer's plan-specific provider-directory selector. Record the selected plan, displayed network, geography, and capture date. A directory can corroborate a product document; a general list of PPO physicians cannot prove the product label.
3. Official 2026 product family materials to interpret abbreviations (for example EOA) and check whether a PPO product is actually offered in CA group business. Use regulator filings or an insurer/employer answer for custom products if accessible.
4. Compare same-name/ID rows across snapshots or related indexes for contradictions. Compare a small, stratified NPI set against the directory only as a plausibility check. A shared file or high provider overlap is never decisive because product networks may overlap.

Record **both** supporting and contradictory sources. A newer generic web page cannot overturn a dated, exact plan-specific document. If two authoritative sources disagree on the same effective period, leave the decision unresolved and escalate rather than averaging scores.

**PS check:** this is the explainable C2 verification step, including explicit HMO/EPO/POS exclusion. **Exit condition:** every proposed final PPO plan has traceable positive evidence and no unresolved same-period contradiction; all unresolved rows are published in the review queue.

### Step 5 — Make two decisions: product type and network identity

Use fixed statuses rather than a single opaque confidence score:

| Product status | Minimum rule | Downstream treatment |
| --- | --- | --- |
| `CONFIRMED_PPO` | In scope, exact plan/year match to an authoritative PPO document or explicit product-type field, and no unresolved contradiction | Main C2 set. |
| `PROVISIONAL_PPO` | In scope with explicit PPO name and corroborating family/market evidence, but no exact plan-specific confirmation | Separate sensitivity set; report its count. |
| `EXCLUDED_NON_PPO` | Authoritative HMO/EPO/POS/EOA type, or explicit out-of-scope market/state | Exclude, retain reason. |
| `UNRESOLVED` | Missing, mixed, conflicting, or custom-plan evidence | Review queue; do not silently include. |

Store `network_status` separately: `CONFIRMED_NETWORK`, `PROVISIONAL_NETWORK`, or `UNKNOWN_NETWORK`, with the network name/ID and service area where evidenced. A confirmed PPO *product* with an unknown network is still not proof that every provider in a shared MRF belongs to one PPO network. Keep the main set conservative; publish a separate scenario that includes provisional plans to show coverage impact.

**PS check:** explicitly identifies plans **and** their network(s), as C2 requests. **Exit condition:** a reproducible decision table, reviewed exceptions, and counts by status and network.

### Step 6 — Map plans to files without assigning false exclusivity

Join the decision table to the lossless C1 edges. For each URL report the number and names of confirmed PPO, provisional PPO, excluded, and unresolved plans; mark `PPO_ONLY`, `MIXED`, or `UNKNOWN` according to *linked products*, not the filename. Download or process each unique URL only once. On the September Health Net CA index, the shared file should be marked **MIXED**. Its presence in the main PPO file list means “needed to inspect PPO-linked negotiated rates,” not “all its records are exclusive to PPO.”

Inspect the MRF schema and any network/product metadata actually present. If rates have no plan-level discriminator, preserve `plan_attribution=SHARED_FILE_UNRESOLVED`; do not duplicate one rate across 452 plans or assert that a listed provider is enrolled in all 452. A plan-specific directory or contract crosswalk can later establish provider participation for a particular network. CMS says a shared file may legitimately represent identical negotiated data across products ([technical clarification](https://www.cms.gov/initiatives/healthplan-price-transparency/overview/resources/technical-clarification)); this does not certify identical product benefits or memberships.

**PS check:** supplies C2's rate-file list while protecting C3/C4 from a false network assignment. **Exit condition:** every selected URL has a mixed/exclusive flag and explicit plan-attribution limitations.

### Step 7 — Validate decisions and make review measurable

Create a stratified manual review sample across standard PPO, custom PPO, unlabeled, EOA, HMO, EPO/PPO mixed, POS, retiree, and non-CA plans. Two reviewers independently assign labels for difficult cases; reconcile disagreements with a cited source. Test rule behavior on known positives and negatives, plus `CUSPPO`, doubled spaces, punctuation, and similarly named plans from another year/state. Report precision and recall **against the adjudicated sample**, not against the original regex; show false-positive and false-negative cases. Track unresolved rate and evidence coverage by plan family. A high unresolved rate should trigger more source gathering, not looser rules.

RAG/LLM may retrieve passages from EOCs or suggest aliases, with exact citations and human checking. It must not be the final classifier or manufacture network IDs. Freeze prompts/model versions if used so the run remains explainable.

**PS check:** demonstrates why each decision is sound, which the PS prioritizes. **Exit condition:** review log, sampled error metrics, and a clear remaining-uncertainty section.

### Step 8 — Hand off to the rest of the PS

Pass the distinct PPO-linked files and their mixed-file flags to C3. Grade their schema validity, code and provider coverage, rate type and `$0` prevalence, duplicate/outlier rates, and staleness; classification confidence is **not** a substitute for file quality. Stream the rate file for C4 and retain source URL, NPI, TIN, billing code, rate, modifiers, service code, and negotiated type before choosing among duplicate rates. For C5, validate Type 1 and Type 2 NPI–TIN–address associations with the CA NPPES extract **plus** plan-specific directory or other corroborating sources; NPPES alone is not enough. C6's Excel rows should retain a link or stable identifier back to the PPO decision and source rate record. These steps are downstream work, not reasons to broaden the C2 scope.

**PS check:** preserves the three core problems and the required Excel/logic/quality/summary deliverables without claiming C3–C6 are solved by plan classification.

## 5. Files and code changes to implement this plan

Keep source data under ignored `data/` and generated data under ignored `outputs/`; commit code, configuration templates, logic, and small aggregate examples only.

| File or artifact | Action |
| --- | --- |
| `TOC/centene_index_pipeline.py` | Keep lossless C1 extraction; split `INCLUDE` into `PPO_CANDIDATE` and reviewed final status; add collapsed-token and EOA flags; stop treating filename CA evidence as final plan proof. |
| `TOC/verify_ppo_network.py` | New deterministic command: read C1 CSVs and evidence register, apply dated scope/evidence rules, emit decisions and a review queue. No hardcoded machine paths. |
| `config/ppo_evidence_sources.csv` | Versioned, human-editable evidence register: source URL, document type, plan/contract ID, exact name, issuer, year, market, state, product/network labels, effective dates, page/section, capture date, reviewer, and conflict note. Do not put member data here. |
| `outputs/ppo/plan_decisions.csv` | One row per unique plan-snapshot-file edge with scope/product/network status, reason codes, evidence IDs, rule version, and reviewer override history. |
| `outputs/ppo/file_manifest.csv` | One row per URL/hash with all linked product statuses, mixed-file flag, dates, byte size, and later C3 grade. |
| `outputs/ppo/review_queue.csv` and `review_log.csv` | Exact unresolved issue, competing claims, source links, decision, reviewer, decision date. |
| `outputs/ppo/summary.json` and repo logic document | Reconciled counts, included/provisional/excluded/unresolved totals, evidence coverage, review error metrics, file count, and limitations for the required summary/logic deliverables. |
| `README.md` | Commands for copying inputs to ignored paths, running C1 then C2, and regenerating the published summaries from a clean checkout. |

Recommended run order once the Drive indexes are copied locally:

```powershell
python TOC/centene_index_pipeline.py --workdir . --output outputs/centene_index_pipeline --index data/indexes/healthnet_index.json --index data/indexes/ambetter_index.json --index data/indexes/fidelis_index.json --index data/indexes/qualchoice_index.json
python TOC/verify_ppo_network.py --plans outputs/centene_index_pipeline/centene_plan_file_relationships.csv --evidence config/ppo_evidence_sources.csv --output outputs/ppo
```

The second command is **planned**, not present yet. Confirm nested QualChoice indexes are traversed or pass them explicitly. Do not run `--download` simply to classify plan names. Run large-file retrieval and streaming only after the reviewed URL manifest is stable.

## 6. Immediate review order for this dataset

1. Confirm the 30 exact-match standard 2026 PPO variants; log their EOC links and the shared-file caveat.
2. Resolve the four `1800` versus `1700` HDHP variants by document effective date or issuer clarification; do not silently normalize the number.
3. Review the `CUSPPO` spelling anomaly and the `HN Retiree` entry for product and market eligibility.
4. Review the three PPO+EPO names, all six POS names, and EOA as excluded or unresolved with source-backed reasons. The EOA/PPO tier should be documented as overlap, not folded into pure PPO.
5. Work through the remaining custom and unlabeled group plans by exact employer documents or payer confirmation; prioritize those with high provider/rate coverage once C3 sampling is available.
6. Publish confirmed and provisional counts separately. If exact custom-plan documents cannot be obtained, state the coverage limitation rather than claiming a complete verified PPO roster.

## 7. Future schema note and source list

CMS finalized additional product-type and network-name/identifier fields in October 2026, with later applicability dates ([CMS 2026 TiC fact sheet](https://www.cms.gov/newsroom/fact-sheets/transparency-coverage-final-rules-cms-9882-f)). The September 2026 index predates that requirement; **do not assume those fields exist in these files**. When newer MRFs contain them, use them as direct evidence and compare with the historical classifications.

Primary references: local `PS.txt` in the parent workspace; [Centene transparency page](https://www.centene.com/price-transparency-files.html); [CMS TiC guide and shared-file convention](https://github.com/CMSgov/price-transparency-guide); [CMS TOC schema](https://github.com/CMSgov/price-transparency-guide/blob/master/schemas/table-of-contents/table-of-contents.json); [CMS technical clarifications](https://www.cms.gov/initiatives/healthplan-price-transparency/overview/resources/technical-clarification); [Health Net 2026 small-group documents](https://www.healthnet.com/content/healthnet/en_us/find-a-plan/small-business/small-plans/forms-and-documents.html); [Health Net 2026 large-group guide](https://www.healthnet.com/content/dam/centene/healthnet/pdfs/broker/ca/large/fb/2026/ec-portfolio-guide-2026.pdf); [Health Net plan directory](https://www.healthnet.com/portal/member/providerSearch.action?access=true); [HiLabs NetworkIQ](https://www.hilabs.com/our-solutions/mcheck-networkiq); [HiLabs MCheck Provider Data Accuracy](https://www.hilabs.com/our-solutions/mcheck-directory-accuracy).
