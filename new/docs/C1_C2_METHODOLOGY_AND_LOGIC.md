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
