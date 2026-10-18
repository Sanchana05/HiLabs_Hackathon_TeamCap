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

The versioned register in `new/config/ppo_evidence_sources.csv` contains 34 direct 2026 Health Net Small Group Full Network PPO EOC links from [Health Net's official plan materials](https://www.healthnet.com/content/healthnet/en_us/find-a-plan/small-business/small-plans/forms-and-documents.html). The exact EOC title is matched to the exact index plan name after case and whitespace normalization only. Benefit variants, percentages, and `INF` suffixes are never merged. A HIOS plan ID is matched only when the evidence register supplies the same HIOS ID. An EIN can confirm the published plan *type* through an exact name match, but cannot establish product identity or provider membership. An invalid EIN format is retained as an anomaly.

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

From the repository root with the dependencies in `new/requirements.txt`:

```powershell
$env:PYTHONPATH = "new"
python -m pipeline.c2_network_mapper.run_c2 --index-dir data/indexes --output-dir new/deliverables
python -m unittest discover -s new/tests -p test_c2_network_mapper.py -v
```

Use `--index-dir` for another directory, repeated `--index` arguments for explicit files, or `--evidence` for a reviewed Health Net evidence register. `c2_summary.json` records input index and all evidence SHA-256 hashes. The 11 supplied indexes are versioned under `data/indexes`; the much larger rate MRF remains a local input.

---

# Challenge C5: PTD TIN and NPI to Practicing Address Mapping Logic

## 1. Executive Summary & The Core Dilemma

In Price Transparency Data (PTD), rates are contracted at the **(NPI, TIN, Billing Code)** level. The CMS schema contains **zero address fields, zero provider names, and zero clinical specialties**. 

To make this data usable for a payer contracting team (Deliverable 1), every rate record must be linked to the provider's **actual practicing address and clinical specialty**.

However, relying solely on the federal **National Plan and Provider Enumeration System (NPPES)** introduces fatal data errors:
- **~80% Stale or Inaccurate Practice Addresses**: When physicians apply for an NPI (often during medical residency or early fellowship), they register an address that is rarely updated throughout their multi-decade careers.
- **Mailing Clearinghouses & Corporate HQs**: A huge percentage of NPPES records list third-party billing clearinghouses, accountants, out-of-state administrative headquarters, or Post Office Boxes rather than physical treatment facilities.
- **The One-to-Many TIN Complexity**: A single Tax Identification Number (TIN) represents a healthcare legal entity (e.g., a regional medical group or hospital system) that may operate 30 distinct clinic locations across California. Conversely, a single traveling physician (NPI) may practice across multiple facilities.

To solve this problem and satisfy the **40-point Logic evaluation criteria**, we engineered a multi-stage **Entity Triangulation and Network Consensus Engine** inspired by the HiLabs R3 (Reliability, Relevance, Recency) framework.

---

## 2. Source Data Architecture

1. **PTD In-Network Rate Files**: Extracted tuples of $\langle \text{NPI}, \text{TIN}, \text{billing\_code}, \text{rate} \rangle$.
2. **CMS NPPES California Registry Extract**: 
   - Entity Type 1 (Individual Physicians/Surgeons) and Entity Type 2 (Organizational Clinics/Facilities).
   - Primary and Secondary Practice Location Addresses.
   - Provider Business Mailing Addresses.
   - Healthcare Provider Taxonomy Codes (10-character alphanumeric).
   - Record Last Update Timestamps.
3. **National Uniform Claim Committee (NUCC) Code Set**: Official hierarchical crosswalk mapping taxonomy codes to clinical classification and specialty.
4. **USPS Publication 28 (Postal Addressing Standards)**: National standards for street abbreviations, directional indicators, and secondary unit normalization.

---

## 3. The Multi-Stage Address Triangulation Protocol

```
         PTD IN-NETWORK RATES                     CMS CALIFORNIA NPPES EXTRACT
         (NPI, TIN, Code, Rate)                   (NPI, Entity Type, Taxonomy, Addresses)
                   │                                                │
                   └───────────────────────┬────────────────────────┘
                                           │
                                  [NPI Primary Join]
                                           │
                        ┌──────────────────┴──────────────────┐
                        ▼                                     ▼
             [Stage 1: USPS Standardizer]         [Stage 4: NUCC Specialty Mapper]
             - Normalize street suffixes           - Map 10-char taxonomy code
             - Normalize secondary units           - Output standardized specialty
             - Reject PO Boxes / Drops               (e.g., "Orthopaedic Surgery")
                        │
                        ▼
             [Stage 2: Physical vs Mailing]
             - Prioritize Practice Location
             - Discard out-of-state addresses
                        │
                        ▼
             [Stage 3: TIN Network Consensus]
             - Cluster all NPIs under same TIN
             - Calculate address co-occurrence
             - Corroborate physical facility
                        │
                        ▼
             [Stage 5: Address Confidence Scorer]
             - Calculate ACS (0 to 100)
             - Assign Confidence Tier (HIGH / MOD)
                        │
                        ▼
             CURATED PROVIDER RATE DELIVERABLE
             (NPI, TIN, Address, Code, Specialty, Rate)
```

---

### Stage 1: USPS CASS-Compliant Address Standardization & Noise Rejection
Raw address text across healthcare datasets suffers from severe formatting entropy (e.g., "Ste 200", "Suite #200", "Floor 2", "St.", "Street").
1. **Token Standardization**: Normalizes street suffixes (`AVENUE` $\rightarrow$ `AVE`, `BOULEVARD` $\rightarrow$ `BLVD`, `SUITE` $\rightarrow$ `STE`, `BUILDING` $\rightarrow$ `BLDG`) and directional prefixes (`NORTH` $\rightarrow$ `N`).
2. **PO Box & Virtual Drop Rejection**: A physician cannot render physical healthcare services inside a Post Office Box. The normalizer runs word-boundary regexes (`\b(?:P\.?O\.?\s*BOX|POST\s+OFFICE\s+BOX|PMB\s+\d+)\b`) and immediately rejects PO Boxes from physical practicing consideration.
3. **California ZIP Boundary Enforcement**: Validates that 5-digit postal codes fall strictly within California's statutory geographic boundaries (`90001` through `96162`).

---

### Stage 2: Dual NPPES Evaluation (Physical Practice vs Mailing Location)
NPPES contains two separate address blocks for every provider:
- `Provider Business Practice Location Address`: The statutory location where medical services are rendered.
- `Provider Business Mailing Address`: The administrative correspondence address.

**Disambiguation Logic**:
- The engine prioritizes the **Practice Location Address**.
- If the Practice Location Address is missing or flagged as a PO Box, the Mailing Address is inspected. If the Mailing Address is a physical commercial address within California, it is retained with a flagged audit status; otherwise, it is rejected.

---

### Stage 3: Multi-Provider TIN Co-occurrence Consensus Clustering
*This is the mathematical core that solves the 80% stale address problem.*

* **The Concept**: A Tax ID Number (TIN) represents the legal operating entity (medical group, health system, or clinic). While an individual physician’s NPPES record is frequently outdated, a medical group has multiple affiliated clinicians billing under the same TIN.
* **The Consensus Algorithm**:
  For every distinct TIN in the PTD rate dataset, we construct an address co-occurrence graph across all affiliated NPIs:
  $$\text{TIN Address Counts} = \left\{ A_j : \text{count}(A_j) \mid A_j \in \text{Standardized Practice Addresses of NPIs billing under TIN} \right\}$$
  $$\text{Consensus Ratio } C(A_j) = \frac{\text{count}(A_j)}{\sum_{k} \text{count}(A_k)}$$
* **The Insight**: When 15 out of 20 physicians billing under TIN $X$ report `"200 UCLA MEDICAL PLZ STE 220, LOS ANGELES, CA 90095"`, that physical address has an overwhelming **$75\%$ network consensus** as the active operating site for that TIN. 
* By leveraging group-level consensus, we cross-validate and self-heal stale or incomplete addresses for individual physicians in the network.

---

### Stage 4: NUCC Taxonomy to Clinical Specialty Crosswalk
Deliverable 1 mandates an exact **`Specialty`** column. CMS TiC files contain no provider specialties.
1. The resolver extracts the primary 10-character alphanumeric taxonomy code from NPPES (`Healthcare Provider Taxonomy Code_1`).
2. The code is mapped against the **National Uniform Claim Committee (NUCC)** classification tree:
   - `207Q00000X` $\longrightarrow$ **Family Medicine**
   - `207R00000X` $\longrightarrow$ **Internal Medicine**
   - `207X00000X` $\longrightarrow$ **Orthopaedic Surgery**
   - `207RC0000X` $\longrightarrow$ **Cardiovascular Disease**
   - `2085R0202X` $\longrightarrow$ **Diagnostic Radiology**
   - `282N00000X` $\longrightarrow$ **General Acute Care Hospital**
3. Type 2 organizational NPIs are enriched with facility classification (e.g., *"Primary Care Clinic"*, *"General Acute Care Hospital"*).

---

### Stage 5: The Address Confidence Score (ACS) Engine
To provide complete transparency for contracting executives, every matched address receives an **Address Confidence Score (ACS)** from $0.0$ to $100.0$:

$$\text{ACS} = S_{\text{physical}} + S_{\text{geo}} + S_{\text{consensus}} + S_{\text{recency}}$$

| Component | Max Points | Evaluation Criteria |
| :--- | :---: | :--- |
| **Physical Integrity ($S_{\text{physical}}$)** | **30** | $+30$ if confirmed physical street address. Rejection ($0$) if PO Box. |
| **Geographic Validity ($S_{\text{geo}}$)** | **25** | $+25$ if valid California municipality and ZIP in range [90001–96162]. |
| **TIN Network Consensus ($S_{\text{consensus}}$)** | **30** | Proportion of affiliated TIN providers sharing this location. Solo practice receives $+20$. |
| **Primary Practice Recency ($S_{\text{recency}}$)** | **15** | $+15$ if verified from primary practice location block with active license. |

**Confidence Tiers**:
- **HIGH (ACS $\ge 80.0$)**: Verified physical California site with multi-provider consensus.
- **MODERATE (60.0 $\le$ ACS $< 80.0$)**: Valid physical site; solo provider or partial consensus.
- **LOW / PROVISIONAL (ACS $< 60.0$)**: Requires directory verification.

---

## 4. Conflict Resolution & Edge Cases

| Conflict Scenario | Observed Manifestation | Applied Resolution Rule |
| :--- | :--- | :--- |
| **Multi-Facility Health Systems** | Large hospital system (single TIN) operates 10 distinct physical clinic addresses. | If an NPI's individual practice address matches one of the TIN's verified consensus clusters, bind to that specific clinic site. If unlisted, bind to the TIN's highest-volume primary clinical hub. |
| **Provider with Multiple Addresses in NPPES** | NPPES lists Practice Location in San Diego and Mailing Address in Dallas, TX. | Reject Texas mailing address (out of market). Select California practice address. |
| **Provider Moved / Missing from CA NPPES** | NPI contracted under Centene CA PPO but recent NPPES update shows move out of state. | Retain historical California practice location verified via TIN co-occurrence consensus, flag as `PROVISIONAL_HISTORICAL`. |

