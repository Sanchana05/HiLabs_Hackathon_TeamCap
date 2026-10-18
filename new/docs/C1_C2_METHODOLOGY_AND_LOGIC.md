# C1 and C2: index inventory and PPO evidence

## Input and identity

Run C1/C2 from the 11 supplied September 2026 index files. C1 preserves the source index, source block, index date, issuer, plan sponsor, exact plan name, plan ID, and `plan_id_type` on each plan-to-file edge. Deduplication removes only identical edges. A sponsor EIN is not a unique product ID; distinct names sharing an EIN remain distinct rows. CMS defines `plan_id_type` as EIN or HIOS in its [Table of Contents schema](https://github.com/CMSgov/price-transparency-guide/blob/master/schemas/table-of-contents/table-of-contents.json).

The 11 filenames contain 10 distinct file hashes: `2026-09-28_qualchoice_city_of_fort_smith_index.json` is byte-identical to `2026-09-28_qualchoice_big_four_index.json`. The inventory records this duplicate and C1 retains both source names on any deduplicated edge.

The index date proves when the index was last updated. It does not prove that every listed employer plan was active on that date. C2 rejects post-cutoff or missing dates, but does not assert active enrollment.

## Evidence rules

The versioned register in `new/config/ppo_evidence_sources.csv` contains 34 direct 2026 Health Net Small Group Full Network PPO EOC links from [Health Net's official plan materials](https://www.healthnet.com/content/healthnet/en_us/find-a-plan/small-business/small-plans/forms-and-documents.html). The exact EOC title is matched to the exact index plan name after case and whitespace normalization only. Benefit variants, percentages, and `INF` suffixes are never merged. A HIOS plan ID is matched only when the evidence register supplies the same HIOS ID. An EIN can confirm the published plan *type* through an exact name match, but cannot establish product identity or provider membership. An invalid EIN format is retained as an anomaly.

C2 fails if its evidence register is missing, duplicated, malformed, or outside the expected 2026 CA group PPO EOC scope. It never substitutes a generic product brochure or an invented identifier for a plan-specific EOC. The register may be replaced with `--evidence` when an additional verified EOC is available.

## Decision order

1. Require a Centene brand, explicit CA marker in the rate-file URL, group market, a source index, and index date no later than 2026-09-30. Failed edges are `OUT_OF_SCOPE`.
2. Put PPO+HMO/EPO/POS/EOA conflicts and retiree/public-program names into `UNRESOLVED`. Do this before any collapsed PPO token rule.
3. Exclude explicitly HMO, EPO, POS, or EOA-labeled plans from the pure PPO candidate set as `EXCLUDED_NON_PPO`. This is a name-based exclusion, not a claim about the precise contract or benefit design.
4. Confirm `CONFIRMED_PPO` and `CONFIRMED_NETWORK` only for exact applicable official 2026 EOC names. The confirmed network name is the EOC's **Full Network PPO**.
5. Keep other in-scope PPO-labeled plans, including `CUSPPO`, as `PROVISIONAL_PPO` with `UNKNOWN_NETWORK`. Keep unlabeled plans `UNRESOLVED`.

Every decision retains a rule version, reason, anomaly tags, evidence ID and URL when present, match basis, and required follow-up evidence. The review queue includes both provisional and unresolved edges.

The supplied Health Net index uses an alphanumeric value `67138CA073` on the 30 EOC-matched metal plans even though it labels that field as EIN. C2 flags `INVALID_EIN_FORMAT`. The exact EOC names support PPO product-type classification; the anomalous identifier cannot be used as an EIN or plan-level join key.

## Rate-file handoff

The C2 `file_manifest.csv` includes only PPO-linked files and preserves `rate_file_url`, `rate_file_name`, and `file_classification` for C3/C4. `all_file_inventory.csv` lists every referenced file. A file linked by PPO and explicit non-PPO plans is `MIXED` with `SHARED_FILE_UNRESOLVED`. A provisional-only file is `UNKNOWN`; `PPO_ONLY` is reserved for files with confirmed PPO links and no provisional, non-PPO, or unresolved links in the supplied indexes. It still never proves every rate or provider belongs to the PPO network. CMS permits multiple plans to reference one rate file ([technical clarification](https://www.cms.gov/initiatives/healthplan-price-transparency/overview/resources/technical-clarification)).

For the supplied corpus, the single Health Net CA rate file has 30 confirmed and 422 provisional PPO-linked plan-file edges, 852 explicitly non-PPO edges, and 8 unresolved edges. It is `MIXED`. Provider-level PPO membership remains unverified and must not be inferred by C3/C4 from this file alone.

## Repeatable run

From the repository root with the dependencies in `new/requirements.txt`:

```powershell
$env:PYTHONPATH = "new"
python -m pipeline.c2_network_mapper.run_c2 --index-dir data/indexes --output-dir new/deliverables
python -m unittest discover -s new/tests -p test_c2_network_mapper.py -v
```

Use `--index-dir` for another directory, repeated `--index` arguments for explicit files, or `--evidence` for a reviewed evidence register. `c2_summary.json` records input index and evidence SHA-256 hashes. The 11 supplied indexes are versioned under `data/indexes`; the much larger rate MRF remains a local input.
