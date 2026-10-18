# C1 and C2: index inventory and PPO evidence

## Input and identity

Run C1/C2 from the 11 supplied September 2026 index files. C1 preserves the source index, source block, index date, issuer, plan sponsor, exact plan name, plan ID, and `plan_id_type` on each plan-to-file edge. Deduplication removes only identical edges. A sponsor EIN is not a unique product ID; distinct names sharing an EIN remain distinct rows. CMS defines `plan_id_type` as EIN or HIOS in its [Table of Contents schema](https://github.com/CMSgov/price-transparency-guide/blob/master/schemas/table-of-contents/table-of-contents.json).

The 11 filenames contain 10 distinct file hashes: `2026-09-28_qualchoice_city_of_fort_smith_index.json` is byte-identical to `2026-09-28_qualchoice_big_four_index.json`. The inventory records this duplicate and C1 retains both source names on any deduplicated edge.

The index date proves when the index was last updated. It does not prove that every listed employer plan was active on that date. C2 rejects post-cutoff or missing dates, but does not assert active enrollment.

## Evidence rules

The versioned register in `config/ppo_evidence_sources.csv` contains 34 direct 2026 Health Net Small Group Full Network PPO EOC links from [Health Net's official plan materials](https://www.healthnet.com/content/healthnet/en_us/find-a-plan/small-business/small-plans/forms-and-documents.html). The exact EOC title is matched to the exact index plan name after case and whitespace normalization only. Benefit variants, percentages, and `INF` suffixes are never merged. A HIOS plan ID is matched only when the evidence register supplies the same HIOS ID. An EIN can confirm the published plan *type* through an exact name match, but cannot establish product identity or provider membership. An invalid EIN format is retained as an anomaly.

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

From the repository root with the dependencies in `requirements.txt`:

```powershell
$env:PYTHONPATH = "new"
python -m pipeline.c2_network_mapper.run_c2 --index-dir data/indexes --output-dir deliverables
python -m unittest discover -s tests -p test_c2_network_mapper.py -v
```

Use `--index-dir` for another directory, repeated `--index` arguments for explicit files, or `--evidence` for a reviewed Health Net evidence register. `c2_summary.json` records input index and all evidence SHA-256 hashes. The 11 supplied indexes are versioned under `data/indexes`; the much larger rate MRF remains a local input.
