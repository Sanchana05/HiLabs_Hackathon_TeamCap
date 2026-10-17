# Challenge C4: Rate Extraction & Multi-Rate Conflict Resolution Logic

## 1. Executive Summary & Objective

In **Challenge C4**, our pipeline extracts in-network negotiated rates for every provider in Centene's California Commercial Group PPO network. 

The central challenge in CMS Price Transparency Data (PTD) is that a single provider (defined by an NPI and TIN tuple) rarely has only one rate for a billing code. Instead, a provider frequently has **3 to 10 distinct negotiated rates for the exact same CPT code** under the same contract.

The hackathon explicitly requires:
> **"Where a provider has several rates for one code, state which one you keep and why."**

This document establishes our **4-Tier Hierarchical Disambiguation Protocol**, explains the healthcare reimbursement principles governing each tier, and details how our engine resolves multi-rate conflicts deterministically with a complete audit trail.

---

## 2. In-Network Rate File Architecture & Dereferencing

### 2.1 The Two-Pass Streaming Engine
Centene's California in-network file (`...healthnet-ca_in-network.json`) spans gigabytes. Loading this JSON into memory at once causes `MemoryError` crashes. 

Our extraction engine (`RateExtractor`) implements a bounded-memory, two-pass streaming parser:
1. **Pass 1 (`provider_references` scanning)**: Streams top-level provider reference dictionaries into an indexed hash map:
   $$\text{Reference Map}: \text{provider\_group\_id} \longrightarrow [\{\text{tin}: \dots, \text{npi}: [\dots]\}, \dots]$$
2. **Pass 2 (`in_network.item` streaming with early code pruning)**: Streams code items, filters immediately for target benchmark codes (e.g., CMS shoppable & HiLabs weighted codes), dereferences provider groups, and unpacks individual provider records.

### 2.2 Unpacking Individual NPIs (Resolving the Naive Aggregation Bug)
A critical flaw in naive pipelines is recording `len(npi_list)` instead of iterating over providers. In the TiC schema, a `provider_group` contains an array of hundreds of individual NPIs billing under a common TIN. Our engine iterates over every NPI in the array:
```python
for npi in group.get("npi", []):
    yield {
        "npi": str(npi).strip(),
        "tin": tin_value,
        "billing_code": code,
        "rate": negotiated_rate,
        "billing_class": billing_class,
        "service_codes": service_codes,
        "expiration_date": expiration_date
    }
```
This guarantees that **Deliverable 1** and **Deliverable 4** receive individual provider-level granularity.

---

## 3. Why Providers Have Multiple Rates for the Same Billing Code

Multi-rate occurrences in PTD files are not random noise; they arise from specific statutory and contractual structures:

```
                               RAW RATES FOR (NPI, TIN, CODE)
                                            │
                              [Tier 1: Billing Class Filter]
                               Professional vs Institutional?
                                            │
                                  Keep 'Professional'
                     (Physician fee; removes hospital facility charge)
                                            │
                              [Tier 2: Place of Service Filter]
                                POS 11 (Office) vs POS 21/22?
                                            │
                                   Keep POS 11 (Office)
                     (Standard ambulatory baseline; removes facility fee)
                                            │
                             [Tier 3: Contract Freshness Filter]
                                Different Expiration Dates?
                                            │
                                  Keep Latest Expiration
                         (Current active renegotiated schedule)
                                            │
                             [Tier 4: Statistical Tiebreaker]
                              Multiple Active Negotiated Tiers?
                                            │
                                     Keep MEDIAN Rate
                       (Eliminates extreme high/low tier outliers)
                                            │
                             SINGLE DETERMINISTIC RATE SAVED
```

---

## 4. The 4-Tier Conflict Resolution Protocol: Which Rate We Keep and Why

When a provider tuple $\langle \text{NPI}, \text{TIN}, \text{billing\_code} \rangle$ has multiple rates, we apply the following hierarchical decision rules:

### Tier 1: Billing Class Precedence (Keep `professional` over `institutional`)
* **Rule**: If both `professional` and `institutional` rates exist, **keep `professional`** and discard `institutional`.
* **Why**:
  - `professional`: The reimbursement paid to the physician for cognitive and surgical work (CMS Form 1500).
  - `institutional`: The facility overhead reimbursement paid to a hospital or ambulatory surgery center (UB-04).
  - Payer contracting teams benchmark physician compensation using professional fee schedules. Retaining an institutional rate for a physician distorts market benchmarking by conflating facility overhead with doctor pay.

### Tier 2: Place of Service (POS) Precedence (Keep POS 11 `Office` over Hospital Facility)
* **Rule**: If rates differ by `service_code`, **keep POS 11 (Office / Non-Facility)** over POS 21 (Inpatient Hospital) or POS 22 (Outpatient Hospital).
* **Why**:
  - In commercial health insurance, the standard benchmark for outpatient care (E/M visits, diagnostic exams) is the **Office** setting.
  - In facility settings (POS 21/22), the physician's professional fee is discounted because practice expenses (nursing staff, equipment, rent) are separately billed by the hospital. 
  - Standardizing on POS 11 provides an apples-to-apples baseline across independent practices and health systems.

### Tier 3: Contract Freshness Precedence (Keep Latest `expiration_date`)
* **Rule**: If rates originate from multiple contract schedules with different expiration dates, **keep the rate with the latest expiration date**.
* **Why**:
  - Payers frequently publish overlapping legacy contracts during multi-year renegotiation transitions.
  - The schedule with the furthest future expiration date represents the most recently executed, legally active contract.

### Tier 4: Statistical Median Tiebreaker across Active Tiers
* **Rule**: If multiple active rates still exist within the same billing class, setting, and expiration date (e.g., multi-tier employer group rates), **keep the MEDIAN rate**.
* **Why**:
  - Commercial plans occasionally negotiate tiered rates (e.g. Tier 1 preferred copay network vs Tier 2 standard network).
  - Taking the mathematical median eliminates skew from promotional discounts or super-specialized outlier carve-outs, delivering a statistically representative rate that reflects true central market tendency.

---

## 5. Audit Trail & Rationale Tracking

Every curated rate record in our pipeline includes an auditable `selection_rationale` column:
- `UNIQUE_RATE`: Only one published rate existed.
- `CONFLICT_RESOLVED: Selected 'professional' billing class over institutional facility rate.`
- `CONFLICT_RESOLVED: Selected Office (POS 11) ambulatory rate over hospital facility rate.`
- `CONFLICT_RESOLVED: Multiple active tiers found (3 rates). Filtered by professional office POS and selected MEDIAN rate ($135.50) to eliminate tier outliers.`

This guarantees 100% transparency for regulatory audits and executive review.
