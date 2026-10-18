# C3: Complete-file quality audit, version 2

The input is each unmodified CMS in-network MRF selected by C2. The grader runs **before** C4 filters codes, drops zero rates, or resolves conflicting rates. It scans the entire JSON or gzip JSON. The unit for price proportions is a published `negotiated_prices` object; provider-price duplicates are measured after resolving provider references to NPI/TIN pairs. Every output includes source URL when available, SHA-256, byte size, audit date, update-date source, counts, and a warning list. A failed parse fails the run instead of producing a score from partial data.

The composite measures **fitness for direct dollar benchmarking**. It is not proof that the file represents only PPO members, that a rate is contractually active, or that the payer's full PPO provider roster is present. On a mixed HMO/PPO file, the score applies to the shared file. Product attribution remains C2/C5 work.

## Dimensions and formulas

Scores are 0–100. Composite = 0.25 code panel + 0.15 provider linkage + 0.15 usable prices + 0.10 direct dollar share + 0.10 outlier control + 0.05 publication freshness + 0.20 duplicate control. The coefficients are a declared contracting-use priority, not statistically learned weights. Code coverage and duplicate inflation receive the largest weights because either can distort a service-level market benchmark even when the file is recent and parseable. Raw numerators and denominators are in `file_quality_details.json` so the team can revise the weights without rescanning the source.

| Dimension | Exact measure | Why it helps |
| --- | --- | --- |
| Code panel coverage | 100 × sum of weights for expected CPT/HCPCS codes present ÷ sum of all panel weights | Checks whether the file contains services in the chosen comparison panel. It is **not** total universe coverage. |
| Provider linkage | 100 × published prices with at least one resolvable NPI–TIN pair ÷ all published prices | A price without a usable provider pair cannot feed C6. Distinct NPI/TIN counts are also reported. |
| Usable price share | 100 × prices with numeric amount > $0.01 ÷ all published prices | Zero, negative, missing, nonnumeric, and penny prices are unusable as direct positive-dollar benchmarks. Each is counted separately; a high price is flagged, not automatically declared invalid. |
| Direct dollar share | 100 × prices whose type is `negotiated` or `fee schedule` ÷ all published prices | A percentage or per-diem rate needs different comparison logic. All official rate types are retained and counted. |
| Outlier control | 100 × (1 − flagged prices ÷ eligible prices) | Relative anomaly measure. A seeded 128-price reservoir establishes quartile bounds within each billing-code type, code, version, name/description, arrangement, billing class, rate type, service code, and modifier. At least 20 prices and nonzero IQR are required. A rate outside Q1 − 3×IQR or Q3 + 3×IQR is flagged. |
| Publication freshness | 100 through day 31 since the MRF update date, then loses 2 points per extra day, floored at 0 | Distinguishes a current publication from a stale one. Expired, missing, and far-future contract expiration dates are reported separately; publication recency does not verify contract activity. |
| Duplicate control | 100 × (1 − extra exact provider-price rows ÷ all expanded provider-price rows) | Deduplication key includes the full item identity, full negotiated-price JSON, NPI, TIN type, and TIN value. Legitimate differences in settings or modifiers must survive. |

Letter grades use A ≥ 85, B ≥ 70, C ≥ 50, F < 50. These are comparative audit bands, **not automatic permission to use raw rates in contracting**. Independent review flags are emitted when duplicate inflation exceeds 20%, code-panel coverage is below 80%, more than half of expiration dates are far-future sentinels (year ≥ 2100), the PPO roster is absent, or structural/reference errors occur. Any flag sets `quality_status=REVIEW_REQUIRED`. The thresholds are declared operational review gates, not calibrated clinical cutoffs.

For outliers, if fewer than 80% of positive numeric prices fall in scorable strata, the dimension is `null`, and no composite or letter grade is issued. An absent update date or no linked provider-price rows also leaves a required dimension unknown and blocks a letter grade. The tool never grants default points for missing data. A syntactically malformed MRF raises an error.

## The benchmark panel

The included [panel](../config/c3_benchmark_codes.csv) was generated from the supplied `Rate Benchmarking Individual Weights_Hackathon.xlsx`, `Spec-Proc Weights` sheet. The [builder](../tools/build_c3_benchmark.py) sums positive `SPEC_PROC_WEIGHT` values across specialties for each procedure. It contains 579 distinct CPT/HCPCS-like procedure codes. It is an **individual-specialty benchmark**, not a complete Type 2 facility/service denominator. The scorer accepts a replacement weighted CSV through `--benchmark-csv`. Do not describe this panel as “CMS Top 500”; it is the case supplement.

External PPO provider coverage is reported only when `--expected-npis-csv` supplies a verified roster (`npi` column). Without a roster, that percentage is `null`; the scored provider metric remains *linkage*, not network completeness. NPPES alone is not a valid PPO roster.

The rate-type parser follows the [CMS in-network field guide](https://github.com/CMSgov/price-transparency-guide/blob/master/schemas/in-network-rates/README.md): `negotiated`, `derived`, `fee schedule`, `percentage`, and `per diem` are valid types. `negotiated` and `fee schedule` are the two direct dollar types scored for this use case; the other valid types are counted without calling the file corrupt. CMS permits `npi: [0]` when the NPI is unavailable, so that value does not count as a linked provider.

## Run and audit

From the repository root, after installing `ijson`, run:

```powershell
$env:PYTHONPATH = "new"
python -m pipeline.c3_file_grader.file_grader --manifest audit/file_manifest.csv --rate-dir data/ratefiles --output-dir outputs/c3 --as-of 2026-10-18
python -m unittest discover -s tests -v
```

Alternatively, repeat `--file PATH` for explicit files. The master runner calls the same `grade_file` API for every C2-selected URL, writes `file_quality_scorecard.csv` and `file_quality_details.json`, and fails if a selected rate file is missing. The temporary SQLite state lives under the output directory and is removed after the audit. `--as-of` freezes date-sensitive calculations; a repeated run on unchanged inputs produces the same counts and scores.

The scorecard records one row per file. Review the JSON for counts, rate-type distribution, outlier coverage, benchmark identity, update-date provenance, and limitations before using a letter grade. C4 and C5 have separate correctness requirements; a passing C3 grade does not validate their results.
