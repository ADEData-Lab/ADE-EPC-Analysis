# Quick Start Guide

## Get running fast

1. **Clone and enter the repo**
   ```bash
   git clone https://github.com/ADEData-Lab/ADE-EPC-Analysis.git
   cd ADE-EPC-Analysis
   ```
2. **Create/activate a virtual environment (Python 3.11+ recommended)**
   ```bash
   python -m venv venv
   source venv/bin/activate  # Windows: venv\Scripts\activate
   ```
3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```
4. **Run the national pipeline**
   ```bash
   python run_ade_analysis.py
   ```

The pipeline downloads England EPC data (Wales requires manual download per `MANUAL_DOWNLOAD_GUIDE.md`), validates it, enriches geography, runs national analyzers (heating fuel, heat pump potential, heat network potential, demand reduction, consumer impact, policy scenarios), and writes outputs to `data/outputs/`.

## Checking results

- Validated parquet: `data/processed/epc_england_wales_validated.parquet`
- Text summaries: `data/outputs/*_results.txt`
- Reports: `data/outputs/reports/`
- Maps (if spatial deps installed): `data/outputs/maps/`

Example commands:
```bash
ls data/outputs/
cat data/outputs/heat_pump_potential_results.txt
```

## Customising

Edit `config/config.yaml` to adjust geography filters, subsidy levels, or cost assumptions, then rerun `python run_ade_analysis.py`.

## Troubleshooting

- **Missing spatial outputs**: Install `requirements-spatial.txt` or use the Conda launcher.
- **Large datasets**: Ensure ~20GB free disk; rerun if parquet files become corrupted.
- **Legacy archetype/scenario modelers**: Archived under `legacy/` for reference only; the active pipeline does not call them.
