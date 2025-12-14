# ADE EPC Analysis (England & Wales)

National-scale Energy Performance Certificate (EPC) analysis for domestic properties across England and Wales, aligned to the Association for Decentralised Energy's heat decarbonisation policy objectives.

## What this project delivers
- **Heating fuel mix**: Current fuel sources, electrification rate, and off-gas prevalence.
- **Heat pump potential**: Suitability assessment and barrier categorisation using EPC attributes.
- **Heat network potential**: Heat-density tiers, priority area identification, and investment signals.
- **Demand reduction**: Fabric improvement needs, savings potential, and path-to-EPC-C costs.
- **Constituency-ready outputs**: Automated breakdowns for parliamentary constituencies and other geographies.

## Current status (January 2025)
- ✅ National pipeline implemented and wired to the new analyzers.
- ✅ Heat network potential, demand reduction, and geographic enrichment workflows completed.
- ✅ Simplified validator supports chunked processing for 20M+ records.
- ✅ Documentation rewritten for national deployment.

## Repository layout
```
ADE-EPC-Analysis/
├── config/                # YAML configuration and directory helpers
├── data/                  # Raw, processed, supplementary, and output data
├── docs/                  # Supporting documentation
├── src/                   # All application modules
│   ├── acquisition/       # Bulk downloaders, geocoding utilities
│   ├── analysis/          # Policy metric analyzers
│   ├── cleaning/          # Quality assurance and validation
│   ├── reporting/         # Reporting helpers
│   ├── spatial/           # Spatial enrichment and proximity analysis
│   └── utils/             # Shared utilities (geography lookup, helpers)
├── run_ade_analysis.py    # Primary CLI pipeline (recommended entrypoint)
├── main.py                # Compatibility shim that delegates to run_ade_analysis
├── legacy/                # Archived London archetype and scenario modelers
└── requirements*.txt      # Dependency pins
```

## Quick start
### Recommended: Conda launcher (Windows-friendly, supports spatial analysis)
```bash
# Clone the repo (replace with your fork or the upstream ADEData-Lab repo)
git clone https://github.com/ADEData-Lab/ADE-EPC-Analysis.git
cd ADE-EPC-Analysis

# Windows Command Prompt
run-conda.bat

# Windows PowerShell
./run-conda.ps1
```
This creates a Python 3.11 environment, installs geopandas/GDAL, installs other dependencies, and launches the interactive pipeline.

### Standard launcher (core analysis only)
```bash
git clone https://github.com/ADEData-Lab/ADE-EPC-Analysis.git
cd ADE-EPC-Analysis

# Windows Command Prompt
run.bat

# Windows PowerShell
./run.ps1

# Linux/Mac
python run_ade_analysis.py
```
The standard path installs core dependencies and runs the national pipeline. Spatial features are optional; the pipeline will skip heat-network proximity if geopandas/GDAL are unavailable.

### Manual setup
If you prefer to manage environments yourself, use Python 3.11+, create a virtual environment, and install either `requirements.txt` (core) or `requirements-spatial.txt` (adds geopandas/GDAL). Then run:
```bash
python run_ade_analysis.py
```

## Pipeline overview
`run_ade_analysis.py` orchestrates end-to-end processing with five phases:
1. **Data acquisition** – Downloads and combines DESNZ EPC bulk data (England); Wales is supported via manual download instructions.
2. **Data validation** – Chunked quality assurance using `EPCDataValidator`, producing `epc_england_wales_validated.parquet`.
3. **Geographic enrichment** – Adds national/regional/local-authority/constituency labels via `GeographyLookup`; optional heat-network proximity sampling is available when spatial dependencies are installed.
4. **Policy analysis** – Runs heating fuel, heat pump, heat network, demand reduction, consumer impact, and policy scenario analyzers; constituency-level rollups are generated automatically.
5. **Reporting** – Summarises results to `data/outputs/reports` and writes CSV outputs for downstream dashboards.

Legacy London-specific archetype and scenario/pathway modeling code now lives under `legacy/` for reference and is no longer part of the active pipeline.

You can rerun individual phases by commenting within `main()` or by calling the helper functions directly (see `phase_*` functions in `run_ade_analysis.py`).

## Key outputs
- `data/outputs/heat_network_potential_results.txt` – Priority tiers and viable connection estimates.
- `data/outputs/demand_reduction_results.txt` – Fabric needs, savings potential, and EPC-C pathway metrics.
- `data/outputs/constituency_*.csv` – Constituency-level slices for policy engagement.
- `data/outputs/reports/` – Combined narrative summary generated in the reporting phase.

## Data requirements
- DESNZ EPC bulk datasets for England (downloaded automatically) and Wales (manual download per `MANUAL_DOWNLOAD_GUIDE.md`).
- Optional postcode lookups for constituency joins (expected under `data/supplementary/`).
- Sufficient disk space: ~20GB for uncompressed parquet and outputs.

## Support and troubleshooting
- For GDAL/geopandas installation issues on Windows, prefer the Conda launcher.
- If validation fails, delete corrupted parquet files under `data/processed/` and rerun.
- The compatibility entrypoint `python main.py` simply delegates to `run_ade_analysis.py`.

## Contributing
1. Fork and create a feature branch.
2. Add or update authoritative source references when changing configuration values.
3. Run the relevant pipeline phases locally before opening a PR.
4. Keep documentation aligned with the national pipeline defaults.
