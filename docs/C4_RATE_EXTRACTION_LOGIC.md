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
python -m pipeline.c4_rate_extractor.rate_extractor --manifest outputs/pipeline-smoke/file_manifest.csv --rate-dir data/ratefiles --c3-details audit/file_quality_details.json --as-of 2026-10-18 --output-dir outputs/c4
```

Alternatively repeat `--file path/to/file.json.gz`. The Python port is `run_files([RateFileInput(path, source_url, file_classification, expected_sha256, c3_quality_status)], output_dir, as_of=date(...))`.

## Gates and interpretation

The full master runner executes C4 after C3 and records C4's complete counts. C5 takes the full selected-rate CSV as its input. Do not label C4 rows as PPO-network rates until the C1/C2 attribution and plan-specific provider evidence are established.
