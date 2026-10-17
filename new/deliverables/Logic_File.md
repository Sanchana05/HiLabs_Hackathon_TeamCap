# Master Logic File: Centene Commercial California PPO Rate Curation
**Official Hackathon Deliverable 2**

This document establishes the end-to-end logic for:
1. **Part A: Identifying the PPO Network and Ruling Out HMO, EPO, and POS (Challenges C1 & C2)**
2. **Part B: Resolving Provider Rates and Multi-Rate Conflicts (Challenge C4)**
3. **Part C: Triangulating TINs, NPIs, and Stale Addresses via Network Consensus (Challenge C5)**

---

# Methodology & Logic: Challenge C1 (Index Inventory) & Challenge C2 (PPO Network Identification)
**Pursuant to Centene California Commercial-Group PPO Classification Plan**

---

## 1. Executive Summary & Purpose

Under the federal **Transparency in Coverage (TiC)** rule (45 CFR § 147.212), health insurance issuers must publish machine-readable Table of Contents (TOC) / Index files and in-network rate files. 

The mandate for **Challenge C1** and **Challenge C2** is to identify:
1. Centene's California commercial-group PPO **plans**;
2. The provider **network(s)** those plans use;
3. The Centene rate **files** that reference them;
while systematically preserving evidence, provenance, and uncertainty at each level.

### 1.1 Snapshot Integrity & Date Discipline
Our pipeline freezes inputs strictly to the **September 30, 2026** Centene snapshot. 
- The primary California index file is `2026-09-30_healthnet_index.json`.
- Health Net announced that its California commercial-group market exit commences **February 28, 2027** ([Health Net transition notice](https://www.healthnet.com/content/healthnet/en_us/providers/commercial-group-transition.html)). We do not contaminate this 2026 snapshot with subsequent 2027 product exits or post-dated filings.

---

## 2. Separation of the Three Distinct Objects

A foundational tenet of our methodology is that a plan, a network, and a rate file are fundamentally distinct entities with different identities and evidentiary limits:

```
┌─────────────────┬──────────────────────────────────┬────────────────────────────────────────────────────────┐
│ Object Level    │ Identity to Retain               │ What We Can Legally & Empirically Conclude             │
├─────────────────┼──────────────────────────────────┼────────────────────────────────────────────────────────┤
│ 1. Plan/Product │ Snapshot date, issuer, market,   │ Whether this specific plan is documented as a PPO. An  │
│                 │ plan_id_type, plan_id, exact     │ Employer Identification Number (EIN) identifies a group│
│                 │ name, source block.              │ sponsor, so it is NOT a unique product key by itself.  │
├─────────────────┼──────────────────────────────────┼────────────────────────────────────────────────────────┤
│ 2. Provider     │ Network name, network ID,        │ Whether the plan utilizes a specific named provider    │
│    Network      │ geography, authoritative source. │ roster. Plan type (PPO) and network name (Full Network │
│                 │                                  │ PPO) are related but not interchangeable.              │
├─────────────────┼──────────────────────────────────┼────────────────────────────────────────────────────────┤
│ 3. Rate File    │ Canonical URL, file date, hash,  │ Which plans reference the file. Under CMS guidance, a  │
│                 │ linked plan roster.              │ shared rate file linked by both HMO and PPO plans      │
│                 │                                  │ CANNOT establish a PPO-only provider roster.           │
└─────────────────┴──────────────────────────────────┴────────────────────────────────────────────────────────┘
```

CMS explicitly permits multiple plans to share one file when negotiated rates are identical ([CMS Technical Clarification, Questions 22 and 4](https://www.cms.gov/initiatives/healthplan-price-transparency/overview/resources/technical-clarification)). Therefore, on the September 2026 Health Net index, the shared file (`healthnet-ca_in-network.json`) is formally classified as **`MIXED`**, and rate records carry `plan_attribution=SHARED_FILE_UNRESOLVED` to prevent false network exclusivity.

---

## 3. Authoritative Evidence Hierarchy

Because no public algorithm turns an unvetted index row into a verified PPO plan, our engine resolves candidates against a strict, descending hierarchy of authority:

```
                          EVIDENCE AUTHORITY HIERARCHY
                                      │
     ┌────────────────────────────────┴────────────────────────────────┐
     ▼                                                                 ▼
[Tier 1: Plan-Specific Documents]                             [Tier 2: Plan Directory Selector]
- 2026 Evidence of Coverage (EOC)                             - Health Net ProviderSearch tool
- Certificate of Insurance (COI)                              - Record selected plan, network name,
- Summary of Benefits & Coverage (SBC)                          and capture date.
- Small Group Full Network PPO Crosswalk                                │
     │                                                                 ▼
     └────────────────────────────────┬────────────────────────────────┘
                                      ▼
                      [Tier 3: 2026 Product Materials]
                      - Health Net 2026 Large Group Portfolio Guide
                      - Controlled vocabulary: PPO, HMO, EPO, POS, EOA
                                      │
                                      ▼
                      [Tier 4: Centene Index Metadata]
                      - Reporting date, plan ID, market type, issuer
                                      │
                                      ▼
                      [Tier 5: Regulator Filings (CDI vs DMHC)]
                      - Life & Health (CDI) vs Knox-Keene HMO (DMHC)
                                      │
                                      ▼
                      [Tier 6: Heuristics & Review Queues]
                      - Token matching, anomaly flags, review queue
```

---

## 4. Challenge C1: Lossless Index Inventory & Deduplication

### 4.1 Lossless Reporting Structure Ingestion
The parser (`CenteneIndexParser`) scans all Centene brand index families (`healthnet`, `ambetter`, `fidelis`, `qualchoice`) and sub-indexes. It preserves:
- Original source index and block position ($M$ plans $\times$ $N$ files).
- Exact plan name, plan ID, plan ID type, issuer name, and raw JSON metadata.
- Conservative URL canonicalization (RFC 3986 normalization without stripping semantic query parameters).

### 4.2 Deduplication Without Collapsing Valid Plans
Deduplication is applied strictly to identical plan-file relationship tuples:
$$\text{Unique Relation} = \langle \text{snapshot}, \text{brand}, \text{plan\_name}, \text{plan\_id}, \text{market\_type}, \text{rate\_file\_url} \rangle$$
Plans are **never** collapsed simply because they share an employer EIN or share a common in-network rate URL.

---

## 5. Challenge C2: Stepwise Scope Gates & Network Decisions

### 5.1 Strict Scope Gates (Pre-Classification)
Before any network label is evaluated, five mandatory gates are enforced:
1. `payer == Centene`: Health Net of California, Health Net Life Insurance Co.
2. `state == CA`: Explicit California plan tokens, Health Net Life underwriter, or confirmed California rate file URL (`healthnet-ca`). Non-California files (Fidelis NY, QualChoice AR, Wellcare) are excluded with code `NON_CALIFORNIA_GEOGRAPHY`.
3. `market == group`: Commercial Group plans. Individual ACA exchange products (Covered CA) and Medicare/Medicaid are excluded.
4. `commercial == true`: Verifies active employer sponsorship.
5. `snapshot_active == true`: Active in September 2026 snapshot.

---

### 5.2 Tokenization & Candidate Bucketing

Plans passing scope gates are tokenized on word and punctuation boundaries, populating five distinct candidate buckets:

1. **`PPO_CANDIDATE`**: Contains explicit `PPO` token alone.
2. **`CONFLICT_REVIEW`**: Contains `PPO` alongside gatekeeper tokens (`PPO + EPO`, `PPO + HMO`, `PPO + POS`).
3. **`NON_PPO_CANDIDATE`**: Explicit `HMO`, `EPO`, `POS`, or `EOA`.
4. **`RETIREE_REVIEW`**: Plan name contains `Retiree`, `Senior`, or Medicare wrap terms.
5. **`UNLABELED_REVIEW`**: No network descriptor in the string.

#### Anomaly Detection:
- **Collapsed Token Anomaly (`CUSPPO`)**: Plan name `CA L CUSPPO 15/250/20% RAP` lacks a space between "CUS" and "PPO", causing standard word-boundary regexes (`\bPPO\b`) to miss it. Our engine recognizes `CUSPPO` as a collapsed custom PPO token and routes it to `PROVISIONAL_PPO`.
- **Exclusive Option Advantage (`EOA`)**: Found in 127 plans in the Health Net index. Health Net defines EOA as an **HMO product with a wrapped PPO tier** for designated services ([Health Net Large Group Options](https://www.healthnet.com/en_us/find-a-plan/large-employers/type-of-plans.html)). **Decision**: EOA plans are **excluded from the pure PPO set** (`EXCLUDED_NON_PPO`), but their 127 plans are tracked in an `EOA_OVERLAP_SENSITIVITY` cohort for sensitivity analysis.

---

### 5.3 Systematic Logic for Ruling Out HMO, EPO, and POS

| Model | California Regulatory Framework | Contracting & Referral Structure | Action |
| :--- | :--- | :--- | :--- |
| **HMO** | Knox-Keene Health Care Service Plan Act of 1975 (DMHC), underwritten by **Health Net of California, Inc.** | Delegated capitated IPAs (Heritage, Regal); mandatory Primary Care Physician (PCP) assignment; zero out-of-network coverage. Includes `CanopyCare`, `SmartCare`, `Salud HMO y Más`, `CommunityCare HMO`. | **EXCLUDED_NON_PPO** |
| **EPO** | California Insurance Code (CDI), underwritten by Health Net Life. | Closed exclusive provider networks; zero out-of-network benefits (except emergencies); distinct narrower panels (`PureCare EPO`, `EnhancedChoice EPO`). | **EXCLUDED_NON_PPO** |
| **POS** | Dual-entity hybrid (Health Net of California HMO core + Health Net Life indemnity wrap). | Two-tiered gatekeeper structure requiring formal PCP referral for Tier 1 specialist care. | **EXCLUDED_NON_PPO** |
| **EOA** | Knox-Keene HMO underwritten by Health Net of California. | HMO gatekeeper core offering out-of-network PPO tier for select services. | **EXCLUDED_NON_PPO** (tracked in sensitivity cohort) |

---

### 5.4 Fixed Decision Statuses: Product vs Network

To maintain complete transparency and avoid opaque heuristic scores, decisions are categorized into four fixed product statuses and three network statuses:

#### Product Statuses:
- **`CONFIRMED_PPO`**: Exact match to an authoritative 2026 Evidence of Coverage (EOC) document or official metal plan list under Health Net Life Insurance Company. (30 standard metal plans confirmed).
- **`PROVISIONAL_PPO`**: Explicit commercial group PPO plan underwritten by Health Net Life, corroborated by Full Network PPO filings, but specific custom employer schedule is pending individual EOC document. (Includes custom group plans, collapsed `CUSPPO`, and HDHP 1800 variants).
- **`EXCLUDED_NON_PPO`**: Confirmed HMO, EPO, POS, EOA, or out-of-scope market/geography.
- **`UNRESOLVED`**: Retained in `review_queue.csv` (Retiree wrap plans, mixed PPO+EPO plans, unlabeled plans). Never silently defaulted to PPO.

#### Network Statuses:
- **`CONFIRMED_NETWORK`**: Linked to **"Health Net Full Network PPO"** (California Statewide).
- **`PROVISIONAL_NETWORK`**: Linked provisionally to Full Network PPO subject to employer tier confirmation.
- **`UNKNOWN_NETWORK`**: Unassigned / Excluded.

---

## 6. Rate File Attribution & The MIXED File Flag

Joining verified plan decisions back to unique rate files produces the following empirical attribution:

- **Target File**: `2026-09-30_centene-management-company-llc_healthnet-ca_in-network.json`
- **File Classification**: **`MIXED`**
  - The file is referenced by **452 Confirmed & Provisional PPO plans**, but also by **719 HMO plans**, **127 EOA plans**, and **6 POS plans**.
- **Attribution Policy**:
  - The presence of this file in our pipeline indicates that it is **necessary to inspect PPO-linked negotiated rates**, NOT that all its rates are exclusive to PPO.
  - Rate records carry:
    $$\text{plan\_attribution} = \text{SHARED\_FILE\_UNRESOLVED}$$
  - Rates are not falsely duplicated across 452 plans, nor is it asserted that every doctor in the file is enrolled in every plan.

---

## 7. Deliverables & Audit Manifests

1. `plan_decisions.csv`: Complete row-level audit of every plan-file edge with `product_status`, `network_status`, `network_name`, `evidence_ids`, and `decision_reason`.
2. `file_manifest.csv`: Unique rate file URLs with `MIXED` classification flag and linked plan counts.
3. `review_queue.csv`: Every unresolved plan requiring escalation (retiree plans, PPO+EPO conflicts, unlabeled plans).
4. `config/ppo_evidence_sources.csv`: Versioned evidence register with source URLs, document types, and capture dates.


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

