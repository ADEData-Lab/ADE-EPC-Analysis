# Quick Start Guide

## Getting Started in 5 Minutes

This guide will help you get the Heat Street EPC Analysis up and running quickly.

## Prerequisites Check

```bash
# Check Python version (need 3.9+)
python --version

# Check pip
pip --version
```

## Installation

```bash
# 1. Clone and navigate
git clone https://github.com/pipnic1234/HeatStreetEPC.git
cd HeatStreetEPC

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Test installation
python -c "from config.config import load_config; print('✅ Ready to go!')"
```

## Quick Data Acquisition

The project needs EPC data from the UK Government register. You have two options:

### Option 1: Download Instructions (Recommended First)

```bash
python main.py --phase acquire --download
```

This creates `data/raw/DOWNLOAD_INSTRUCTIONS.txt` with detailed steps to obtain EPC data.

### Option 2: If You Already Have Data

Place your EPC CSV files in `data/raw/` with pattern `epc_*.csv`, then run:

```bash
python main.py --phase acquire
```

## Running Your First Analysis

Once you have data in `data/raw/`:

### Full Pipeline (All Phases)

```bash
python main.py --phase all
```

This will:
1. ✅ Filter and process EPC data
2. ✅ Validate and clean data
3. ✅ Characterize the housing stock
4. ✅ Model decarbonization scenarios
5. ✅ Analyze heat network zones
6. ✅ Generate reports and visualizations

### Step by Step (Recommended for Learning)

```bash
# Step 1: Clean and validate data
python main.py --phase clean

# Step 2: Analyze property characteristics
python main.py --phase analyze

# Step 3: Model scenarios
python main.py --phase model

# Step 4: Spatial analysis
python main.py --phase spatial

# Step 5: Generate reports
python main.py --phase report
```

## Check Your Results

After running the analysis, check these locations:

```bash
# Validated data
ls data/processed/

# Analysis results
cat data/outputs/heat_network_potential_results.txt
cat data/outputs/demand_reduction_results.txt

# Visualizations
ls data/outputs/figures/

# Executive summary
cat data/outputs/reports/executive_summary.txt

# Interactive map
open data/outputs/maps/heat_network_tiers.html  # Mac
# or
xdg-open data/outputs/maps/heat_network_tiers.html  # Linux
# or just open in browser: file:///path/to/data/outputs/maps/heat_network_tiers.html
```

## Understanding the Outputs

### Key Files Explained

| File | What It Shows |
|------|---------------|
| `epc_england_wales_validated.parquet` | Cleaned EPC dataset (England & Wales) |
| `heat_network_potential_results.txt` | Heat density tiers and connection estimates |
| `demand_reduction_results.txt` | Fabric needs, EPC-C pathway metrics, and savings |
| `pathway_suitability_by_tier.csv` | Which properties suit heat networks vs heat pumps |
| `epc_band_distribution.png` | Visual of current EPC ratings |
| `heat_network_tiers.html` | Interactive map of national heat network tiers |

## Customizing Your Analysis

Edit `config/config.yaml` to change:

```yaml
# Example: Focus on specific boroughs
geography:
  boroughs:
    - "Camden"
    - "Islington"
    - "Hackney"

# Example: Change cost assumptions
costs:
  ashp_installation: 15000  # Instead of default £12,000

# Example: Different subsidy levels
subsidy_levels: [0, 20, 40, 60, 80, 100]
```

Then re-run:
```bash
python run_ade_analysis.py
```

## Common Issues

### "No data files found"
- Make sure you've downloaded EPC data to `data/raw/`
- Files should match pattern `epc_*.csv`
- Run `python main.py --phase acquire --download` for instructions

### "Column not found" errors
- EPC data format may vary by year/region
- Check the column name mapping in `src/cleaning/data_validator.py`
- Update field_mapping dictionary if needed

### Missing spatial analysis results
- Spatial analysis requires coordinates in EPC data (LATITUDE/LONGITUDE columns)
- Or you need to add a geocoding service
- Heat network overlays require supplementary GIS data

### Slow performance
- For 500k+ records, consider:
  - Using parquet format (automatically created)
  - Running phases separately
  - Using a subset for initial testing

## Testing with a Sample

To test with a smaller dataset first:

```python
# In Python console
import pandas as pd

# Load full dataset
df = pd.read_csv('data/raw/epc_london_filtered.csv')

# Create 10,000 record sample
sample = df.sample(n=10000, random_state=42)
sample.to_csv('data/raw/epc_sample.csv', index=False)
```

Then run analysis on sample to verify everything works.

## Next Steps

1. **Review the full README.md** for detailed documentation
2. **Explore the results** in `data/outputs/`
3. **Customize scenarios** in `config/config.yaml`
4. **Run sensitivity analyses** for different subsidy levels
5. **Generate custom visualizations** using the API

## Getting Help

- 📖 Full documentation: `README.md`
- 🔧 Configuration guide: `config/config.yaml`
- 📊 Example notebooks: `notebooks/` (to be created)
- 🐛 Issues: [GitHub Issues](https://github.com/pipnic1234/HeatStreetEPC/issues)

## Example Workflow

Here's a typical workflow:

```bash
# Run the national pipeline end to end
python run_ade_analysis.py

# Review key outputs
cat data/outputs/heat_network_potential_results.txt
cat data/outputs/demand_reduction_results.txt
cat data/outputs/reports/executive_summary.txt
```

## Success Checklist

- [ ] Python 3.9+ installed
- [ ] Virtual environment created and activated
- [ ] Dependencies installed (`pip install -r requirements.txt`)
- [ ] EPC data obtained and placed in `data/raw/`
- [ ] First pipeline run completed (`python run_ade_analysis.py`)
- [ ] Results reviewed in `data/outputs/`
- [ ] Configuration customized for your needs

---

**Happy Analyzing!** 🏠📊🌱
