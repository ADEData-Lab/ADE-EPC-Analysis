# Quick Start Guide - Windows

## Setup

1. **Clone the repo**
   ```powershell
   git clone https://github.com/ADEData-Lab/ADE-EPC-Analysis.git
   cd ADE-EPC-Analysis
   ```
2. **Run the setup script (installs venv + deps)**
   ```powershell
   ./setup.ps1
   ```
   If you see an execution policy warning, run:
   ```powershell
   Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
   ```
3. **Run the national pipeline**
   ```powershell
   ./run.ps1
   ```
   or, with an active venv:
   ```powershell
   python run_ade_analysis.py
   ```

## What the pipeline does

- Downloads England EPC data (Wales requires manual download per `MANUAL_DOWNLOAD_GUIDE.md`).
- Validates and enriches the data.
- Runs national analyzers: heating fuel, heat pump potential, heat network potential, demand reduction, consumer impact, and policy scenarios.
- Saves outputs to `data/outputs/` (text summaries, CSV extracts, reports, and optional maps if spatial dependencies are installed).

## Viewing outputs

```powershell
explorer data\outputs
Get-Content data\outputs\heat_pump_potential_results.txt
start data\outputs\maps\heat_network_tiers.html  # if maps exist
```

## Troubleshooting

- **Python not found**: Install Python 3.11+ and ensure "Add Python to PATH" was selected.
- **Spatial analysis missing**: Install `requirements-spatial.txt` or use the Conda launcher (`run-conda.ps1`).
- **Legacy interactive flow**: Archived under `legacy/` for reference only; it is not used by the current pipeline.
