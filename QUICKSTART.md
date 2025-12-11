# ADE EPC Analysis - Quick Start Guide

## Running the Analysis

Run the complete analysis pipeline:

```bash
python run_ade_analysis.py
```

This will:
1. Download bulk EPC data from DESNZ (~5GB compressed)
2. Extract and combine data (~20GB uncompressed)
3. Validate and clean data
4. Add geographic hierarchies
5. Run all four policy analyses
6. Generate summary reports

**Time**: First run 2-4 hours (mostly downloading). Subsequent runs ~30 mins.

## Output Files

All results saved to `data/outputs/`:
- `ade_policy_analysis_summary.txt` - Main summary
- `heating_fuel_analysis_results.txt` - Fuel mix details
- `heat_pump_potential_results.txt` - Heat pump analysis  
- `heat_network_potential_results.txt` - Network analysis
- `demand_reduction_results.txt` - Demand reduction analysis

## Key Metrics

1. **Heating Fuel Mix** - Current fuel sources, electrification rate
2. **Heat Pump Potential** - Suitability classification, barriers
3. **Heat Network Potential** - Heat density, priority areas
4. **Demand Reduction** - Path to EPC C, savings potential

See README.md for full documentation.
