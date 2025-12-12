# Manual EPC Data Download Guide

The automatic bulk download is not working because DESNZ has changed their download structure. Here's how to get the data manually:

## Option 1: Test with Sample Data (Recommended for Testing)

Use the existing London EPC data you already have:

```bash
# Check if you have existing data
dir data\processed\*.csv
dir data\raw\*.csv
```

If you have `epc_london_validated.csv`, you can test the analysis modules directly on that.

## Option 2: Download Full England & Wales Dataset

### Step 1: Visit DESNZ Downloads Page

Go to: **https://epc.opendatacommunities.org/downloads**

**IMPORTANT:** You must register and log in to access bulk downloads (authentication required since 2024)

### Step 2: Download Required Files

Look for these downloads:
- **"All domestic certificates"** (England ONLY) ~5-6GB
  - Note: Despite the name "all", this file contains England data only, NOT Wales

  AND separately:
- **"Domestic certificates - Wales"** ~500MB
  - Must be downloaded separately and requires authentication

### Step 3: Save Files

Save downloaded files to:
```
C:\Users\PhilipNicholson\OneDrive - ADE\Documents\experiments\EPC-Reporter\ADEEPC\data\raw\
```

Expected filenames:
- `all-domestic-certificates.zip`
- `domestic-E06000001.zip` (if downloading by region)
- `domestic-wales.zip`

### Step 4: Extract Files

The ZIP files contain CSV files. Extract them to `data/raw/`:
```bash
# Windows PowerShell
Expand-Archive -Path data\raw\all-domestic-certificates.zip -DestinationPath data\raw\all-domestic\
```

### Step 5: Re-run Analysis

Once extracted, run:
```bash
python run_ade_analysis.py
```

The script will detect the extracted CSV files and process them.

## Option 3: Use API for Specific Regions (Slower but Automated)

For smaller datasets, use the existing API downloader:

```bash
python src/acquisition/epc_api_downloader.py
```

This will download via API (slower but works for specific regions/local authorities).

## Option 4: Quick Test with London Data

If you just want to test the new analysis modules:

1. Check if you have London data:
   ```bash
   dir data\processed\epc_london_validated.csv
   ```

2. If yes, create a test script:

```python
# test_analysis.py
import pandas as pd
from src.analysis.heating_fuel_analysis import HeatingFuelAnalyzer
from src.analysis.heat_pump_potential import HeatPumpPotentialAnalyzer

# Load existing London data
df = pd.read_csv("data/processed/epc_london_validated.csv")

# Test fuel analysis
fuel_analyzer = HeatingFuelAnalyzer()
fuel_analyzer.analyze_fuel_mix(df)
fuel_analyzer.save_results()

# Test heat pump analysis
hp_analyzer = HeatPumpPotentialAnalyzer()
df_hp = hp_analyzer.assess_suitability(df)
hp_analyzer.save_results()

print("✓ Analysis complete! Check data/outputs/")
```

3. Run:
   ```bash
   python test_analysis.py
   ```

## Troubleshooting

### Download is Too Slow
- Use a download manager (e.g., Free Download Manager)
- Download during off-peak hours
- Download by region instead of all at once

### File is Corrupted
- Re-download the file
- Check file size matches what's shown on the website
- Verify ZIP file opens correctly

### Out of Disk Space
- You need ~40GB free space for the full dataset
- Download only England OR Wales separately
- Use API download for specific regions only

## Next Steps

Once you have data downloaded:

1. **Validate**: Run data validator
2. **Analyze**: Run the four policy analyses
3. **Report**: Check `data/outputs/` for results

---

**Need Help?**
- Check the QUICKSTART.md for usage examples
- Review individual module documentation
- Raise an issue on GitHub
