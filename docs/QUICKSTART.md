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
3. ✅ Run national policy analyzers (heating fuel, heat pump potential, heat network potential, demand reduction)
4. ✅ Generate reports and visualizations

### Step by Step (Recommended for Learning)

```bash
# Step 1: Clean and validate data
python run_ade_analysis.py  # runs the full national pipeline
```

## Check Your Results

After running the analysis, check these locations:

```bash
# Validated data
ls data/processed/

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
| `epc_england_wales_validated.parquet` | Your cleaned dataset |
| `heating_fuel_results.txt` | National heating fuel mix and gas boiler counts |
| `heat_pump_potential_results.txt` | Conversion readiness and potential heat pump uptake |
| `heat_network_potential_results.txt` | Properties within heat network proximity tiers |
| `demand_reduction_results.txt` | Fabric upgrade needs and EPC-C readiness |
| `epc_band_distribution.png` | Visual of current EPC ratings |
| `heat_network_tiers.html` | Interactive map of your properties |

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
python main.py --phase model
python main.py --phase report
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
3. **Adjust policy assumptions** in `config/config.yaml`
4. **Run sensitivity analyses** for different subsidy levels
5. **Generate custom visualizations** using the API

## Getting Help

- 📖 Full documentation: `README.md`
- 🔧 Configuration guide: `config/config.yaml`
- 📊 Example notebooks: `notebooks/` (to be created)
- 🐛 Issues: [GitHub Issues](https://github.com/pipnic1234/HeatStreetEPC/issues)

## Example Workflow

Here's a typical workflow for the national pipeline:

```bash
# Day 1: Acquire and validate data
python run_ade_analysis.py
# Review: data/outputs/heat_pump_potential_results.txt

# Day 2: Explore spatial outputs (if spatial dependencies installed)
ls data/outputs/maps/

# Day 3: Review policy reports
ls data/outputs/reports/
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
