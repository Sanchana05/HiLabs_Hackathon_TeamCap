# Challenge C3: File Quality & Completeness Grading Metrics

## 1. Executive Summary & Contracting Rationale

Under the Transparency in Coverage (TiC) mandate, payers publish machine-readable rate files that frequently span tens of gigabytes. However, raw TiC files are plagued by severe data pathologies:
- **$0.00 and Placeholder Rates**: Artifacts from claims billing fee schedules where codes are marked as covered at \$0 (e.g. bundled or non-covered services) rather than true negotiated rates.
- **Contract Staleness**: Rates published under expired employer contracts that have not been renegotiated.
- **Missing Core Codes**: Files omitting bread-and-butter Evaluation & Management (E/M) codes, rendering them useless for provider benchmarking.
- **Duplicate Records**: Multiplied Cartesian joins between providers, plans, and TINs inflating dataset sizes.

For a payer contracting team, utilizing an unvetted rate file to negotiate reimbursement contracts introduces immense financial risk. If a benchmark is skewed by \$0 rates or extreme outliers, the payer may severely underpay (leading to network inadequacy) or overpay (leading to underwriting loss).

To address **Challenge C3** (worth **35 points** in the competition rubric), we have formulated a **7-Dimensional File Quality Framework** that evaluates rate files and synthesizes them into an auditable **Composite File Quality Score (FQS)** from 0 to 100.

---

## 2. Mathematical Definition of the 7 Quality Dimensions

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                        COMPOSITE FILE QUALITY SCORE (FQS) ARCHITECTURE                  │
├─────────────────────────┬────────┬─────────────────────────────────────────────────────┤
│ Metric Dimension        │ Weight │ What It Measures & Formula                          │
├─────────────────────────┼────────┼─────────────────────────────────────────────────────┤
│ 1. Code Coverage        │ 20%    │ Weighted representation of core benchmark codes     │
│ 2. Provider Coverage    │ 20%    │ Breadth of unique NPI/TIN network representation    │
│ 3. Zero-Rate Penalty    │ 20%    │ Penalizes $0.00, sub-dollar, and dummy rates        │
│ 4. Rate Type Validity   │ 15%    │ Proportion of clean fee-for-service allowed amounts │
│ 5. Outlier Control      │ 10%    │ Rates within statistical IQR / clinical bounds      │
│ 6. Contract Freshness   │ 10%    │ Recency of file and contract expiration compliance  │
│ 7. Duplicate Penalty    │ 5%     │ Deduplication integrity against Cartesian repeats   │
└─────────────────────────┴────────┴─────────────────────────────────────────────────────┘
```

---

### Dimension 1: Code Completeness & Weighted Coverage ($S_{\text{code}}$)
* **Contracting Rationale**: A price transparency file must contain high-volume "shoppable" services and core physician Evaluation & Management (E/M) codes to enable market comparisons.
* **Calculation**:
  Let $\mathcal{C}_{\text{bench}}$ be the set of standardized benchmark codes (CMS Top 500 Shoppable Services + HiLabs Benchmark Weights), where each code $c$ has an economic volume weight $w_c \in (0, 1)$ such that $\sum w_c = 1.0$.
  $$S_{\text{code}} = \left( \sum_{c \in \mathcal{C}_{\text{bench}}} w_c \cdot \mathbb{I}(c \in \mathcal{C}_{\text{file}}) \right) \times 100$$
  where $\mathbb{I}(\cdot)$ is the indicator function returning $1$ if the billing code is present in the file, and $0$ otherwise.
* **Scoring Range**: $0 \le S_{\text{code}} \le 100$.

---

### Dimension 2: Provider Universe Coverage ($S_{\text{prov}}$)
* **Contracting Rationale**: A file purporting to represent Centene's commercial California PPO network must reflect sufficient provider density across both Type 1 (individual practitioners) and Type 2 (groups/facilities). A file with only a handful of providers is an incomplete or test extract.
* **Calculation**:
  $$S_{\text{prov}} = \min\left(100.0,\, \frac{N_{\text{unique\_npi}}}{N_{\text{benchmark\_target}}} \times 100.0\right)$$
  where $N_{\text{benchmark\_target}}$ is set to the baseline commercial PPO active provider threshold ($5,000$ active NPIs for statewide California commercial group coverage).
* **Scoring Range**: $0 \le S_{\text{prov}} \le 100$.

---

### Dimension 3: Zero-Rate & Dummy Placeholder Cleanliness ($S_{\text{zero}}$)
* **Contracting Rationale**: Rate files frequently contain \$0.00, negative numbers, or dummy values (\$0.01, \$99,999.00). Ingesting these values destroys mean/median calculations and creates artificial contracting targets.
* **Calculation**:
  Let $\mathcal{R}_{\text{invalid}}$ be the set of rates where $\text{rate} \le \$0.01$ or $\text{rate} \ge \$100,000.00$.
  $$R_{\text{invalid}} = \frac{|\mathcal{R}_{\text{invalid}}|}{N_{\text{total\_rates}}}$$
  $$S_{\text{zero}} = \max\left(0.0,\, 100.0 \times \left(1.0 - 5.0 \cdot R_{\text{invalid}}\right)\right)$$
  *Penalty Slope*: A steep penalty factor of $5.0$ ensures that if even $2\%$ of a file is garbage rates, the score is penalized by $10$ points; if invalid rates exceed $20\%$, $S_{\text{zero}} = 0$.

---

### Dimension 4: Negotiated Rate Type Validity ($S_{\text{type}}$)
* **Contracting Rationale**: CMS TiC schema allows multiple `negotiated_type` values (`fee for service`, `percentage`, `per diem`, `capitation`). Payer benchmarking requires dollar-denominated allowed amounts (`fee for service`). Percent-of-charge rates (e.g. "80% of billed charges") are volatile and impossible to compare across providers without chargemaster data.
* **Calculation**:
  $$S_{\text{type}} = \frac{N_{\text{fee\_for\_service}}}{N_{\text{total\_rates}}} \times 100.0$$
* **Scoring Range**: $0 \le S_{\text{type}} \le 100$.

---

### Dimension 5: Rate Outlier & Clinical Reasonableness ($S_{\text{outlier}}$)
* **Contracting Rationale**: Rates must conform to standard medical economics. For example, a routine 15-minute office visit (CPT 99213) has a commercial median of ~\$120 in California. Rates under \$15 or over \$2,500 for this service reflect data extraction corruption or hospital facility charge pass-throughs.
* **Calculation**:
  For each billing code, we determine the Interquartile Range ($\text{IQR} = Q_3 - Q_1$) across clean rates:
  $$\text{Lower Bound} = \max(1.0,\, Q_1 - 1.5 \cdot \text{IQR})$$
  $$\text{Upper Bound} = Q_3 + 1.5 \cdot \text{IQR}$$
  $$R_{\text{outlier}} = \frac{N_{\text{rates outside bounds}}}{N_{\text{valid\_rates}}}$$
  $$S_{\text{outlier}} = \max\left(0.0,\, 100.0 \times \left(1.0 - 2.0 \cdot R_{\text{outlier}}\right)\right)$$

---

### Dimension 6: Contract Freshness & Staleness Score ($S_{\text{fresh}}$)
* **Contracting Rationale**: Federal TiC regulations require monthly updates (30-day cadence). If a file has not been refreshed or contains expired contract schedules, the rates do not reflect current market negotiations.
* **Calculation**:
  Let $\Delta t$ be the elapsed days between the current date and the file's `last_updated_on` date:
  $$\text{Staleness Penalty} = \max(0.0,\, (\Delta t - 30) \times 0.5)$$
  $$S_{\text{fresh}} = \max\left(0.0,\, \min(100.0,\, 100.0 - \text{Staleness Penalty})\right)$$
  Files updated within 30 days receive $100.0$. A file that is 90 days stale loses 30 points.

---

### Dimension 7: Duplicate Collision Cleanliness ($S_{\text{dup}}$)
* **Contracting Rationale**: Duplicated rates for the exact same tuple $\langle \text{NPI}, \text{TIN}, \text{billing\_code}, \text{rate} \rangle$ artificially inflate volume and slow downstream analytics.
* **Calculation**:
  $$R_{\text{dup}} = \frac{N_{\text{duplicate\_records}}}{N_{\text{total\_records}}}$$
  $$S_{\text{dup}} = \max\left(0.0,\, 100.0 \times \left(1.0 - 3.0 \cdot R_{\text{dup}}\right)\right)$$

---

## 3. The Composite File Quality Score (FQS)

The final score is computed as the linearly weighted combination of all 7 dimension scores:
$$\text{FQS} = \sum_{i=1}^{7} w_i \cdot S_i$$
with weights:
- $w_{\text{code}} = 0.20$ (Code Coverage)
- $w_{\text{prov}} = 0.20$ (Provider Coverage)
- $w_{\text{zero}} = 0.20$ (Zero-Rate Cleanliness)
- $w_{\text{type}} = 0.15$ (Rate Type Validity)
- $w_{\text{outlier}} = 0.10$ (Outlier Control)
- $w_{\text{fresh}} = 0.10$ (Freshness)
- $w_{\text{dup}} = 0.05$ (Duplicate Cleanliness)
$$\sum_{i=1}^{7} w_i = 1.00$$

### Quality Tiers & Letter Grades

| Score Range | Grade | Payer Decision Recommendation |
| :--- | :---: | :--- |
| **85.0 – 100.0** | **Grade A** | **Accepted for Production Benchmarking**: High provider density, clean fee-for-service rates, robust code coverage. |
| **70.0 – 84.9** | **Grade B** | **Usable with Filtering**: Passes baseline requirements; requires automated outlier pruning and zero-rate filtering. |
| **50.0 – 69.9** | **Grade C** | **Conditional / High Risk**: File suffers from significant staleness, low NPI density, or missing service lines. |
| **< 50.0** | **Grade F** | **Rejected**: Corrupted, empty, or predominantly zero-rate file. Unsuitable for contracting decisions. |

---

## 4. File Quality Deliverable Output

The file grading engine generates two deliverables:
1. `file_quality_scorecard.csv`: Individual row per evaluated rate file containing all 7 dimension scores, composite FQS, and assigned letter grade.
2. `file_quality_summary.json`: High-level summary of total rates analyzed, invalid rate proportions, and diagnostic warnings.
