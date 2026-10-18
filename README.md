# HiLabs_Hackathon_TeamCap

## Team ideation

See [IDEATION.md](IDEATION.md) for relevant tools, resources, and project ideas. Team members and agents working in this repository can add concise, sourced entries there.

## C3 file-quality audit

The complete-file grader and its methods are in [new/README.md](new/README.md) and [new/docs/C3_FILE_QUALITY_METRICS.md](new/docs/C3_FILE_QUALITY_METRICS.md). Install the pinned dependencies in [new/requirements.txt](new/requirements.txt). To reproduce the September 2026 Health Net input with the existing TOC downloader, run from the repository root:

```powershell
New-Item -ItemType Directory -Force data/indexes | Out-Null
Invoke-WebRequest 'https://www.centene.com/content/dam/centene/Centene%20Corporate/json/DOCUMENT/2026-09-30_healthnet_index.json' -OutFile data/indexes/2026-09-30_healthnet_index.json
python TOC/centene_index_pipeline.py --workdir . --index data/indexes/2026-09-30_healthnet_index.json --download-dir data/ratefiles --download --hash
```

Place any other C2-selected MRFs under ignored `data/ratefiles/`, then run the C3 audit:

```powershell
$env:PYTHONPATH = "new"
python -m pipeline.c3_file_grader.file_grader --manifest new/deliverables/file_manifest.csv --rate-dir data/ratefiles --output-dir outputs/c3 --as-of 2026-10-18
python -m unittest discover -s new/tests -v
```

Use an audit date appropriate to your snapshot. The command writes one scorecard row per selected file plus detailed counts, source hashes, and review flags. The committed C3 scorecard uses the real 2026-09-30 Health Net index and its linked MRF; other committed demonstration deliverables from the earlier pipeline are not verified production outputs.

## C4 complete-file rate extraction

C4 validates all prices and provider links in each local MRF, then writes per-file selected rates, every rate decision, and a source manifest. The selected rows are representative direct professional FFS negotiated dollar rates; they do not prove PPO provider membership. See [C4 methods](new/docs/C4_RATE_EXTRACTION_LOGIC.md).

The [real-file C4 validation summary](new/deliverables/c4_validation_summary.json) records the input hash, audit date, and reconciled counts. Large row-level CSVs are regenerated locally and excluded from Git.

Install the pinned pipeline dependencies with Python 3.12: `python -m pip install -r new/requirements.txt`.

```powershell
$env:PYTHONPATH = "new"
python -m pipeline.c4_rate_extractor.rate_extractor --manifest new/deliverables/file_manifest.csv --rate-dir data/ratefiles --c3-details new/deliverables/file_quality_details.json --as-of 2026-10-18 --output-dir outputs/c4
```
