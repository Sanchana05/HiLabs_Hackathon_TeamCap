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
