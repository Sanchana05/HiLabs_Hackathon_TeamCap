# Ideation

Keep relevant resources and ideas here. For each addition, briefly state how it helps the problem statement and link to its source.

## HiLabs tools to explore

| Tool | What it does | Potential use in this project | Access and cost |
| --- | --- | --- | --- |
| [MCheck Provider Directory Accuracy](https://www.hilabs.com/our-solutions/mcheck-directory-accuracy) (includes the R3 engine) | Validates provider attributes against multiple sources and scores reliability, relevance, and recency. | C5: evaluate candidate NPI practice addresses, flag stale or conflicting locations, and retain evidence and confidence for each match. | Commercial product; no public price or free plan found. Ask HiLabs about hackathon access. |
| [MCheck NetworkIQ](https://www.hilabs.com/our-solutions/mcheck-networkiq) | Combines provider, network, geographic, and pricing data for network analysis and benchmarking. | C2/C7: support review of PPO network context and compare rates among similar providers by specialty and geography. Its output would supplement, not replace, documented network-identification logic. | Commercial product; no public price or free plan found. Ask HiLabs about hackathon access. |

Access to either tool has not been confirmed. The pipeline should remain reproducible from documented inputs if these products are unavailable.

## Public Data Standards and Methods

| Resource / Standard | What it provides | Potential use in this project | Source |
| --- | --- | --- | --- |
| [CMS TiC In-Network Schema v1.1.0](https://github.com/CMSgov/price-transparency-guide) | Official JSON schema defining `in_network`, `negotiated_prices`, and `provider_references` structures. | C1/C3/C4: parse multi-GB files deterministically, correctly dereference nested provider groups, and validate schema integrity. | CMS Price Transparency Guide |
| [NUCC Health Care Provider Taxonomy Code Set](https://www.nucc.org/) | Hierarchical mapping of 10-digit taxonomy codes to Provider Type, Classification, and Specialization. | C5/C6: enrich raw NPIs with standardized clinical specialties required for final rate deliverable. | National Uniform Claim Committee |
| [CMS NPPES Data Dissemination](https://download.cms.gov/nppes/NPI_Files.html) | Full weekly/monthly NPI registry files with entity type (Type 1 individual vs Type 2 org), primary/secondary taxonomy, and practice vs mailing addresses. | C5: baseline provider entity resolution, specialty assignment, and practicing address candidate pool. | CMS.gov |
| [USPS Publication 28 (Postal Addressing Standards)](https://pe.usps.com/text/pub28/welcome.htm) | Standardized address parsing rules (street suffixes, directional abbreviations, secondary unit indicators). | C5: eliminate false address variations between NPPES, clinic sites, and billing locations before deduplication. | USPS Postal Explorer |
| [CMS Medicare Physician Fee Schedule (MPFS) & Relative Value Units (RVUs)](https://www.cms.gov/medicare/payment/fee-schedules/physician) | National and geographic practice cost index (GPCI) benchmark payment amounts for CPT codes. | C3/C7: detect $0 or absurd outlier rates (Z-score vs Medicare median), and establish baseline for cost-effectiveness scoring. | CMS.gov Fee Schedules |

