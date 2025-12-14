"""
Test script for constituency-level analysis.
Runs just the constituency analysis on existing validated data.
Uses chunked processing to avoid memory issues.
"""

import sys
from pathlib import Path
from loguru import logger

# Add src to path
sys.path.append(str(Path(__file__).parent))

from config.config import load_config, DATA_PROCESSED_DIR, DATA_OUTPUTS_DIR

import pandas as pd

def main():
    """Test constituency analysis on existing data."""
    # Load constituency lookup
    lookup_file = Path("data/supplementary/constituency_lookup.csv")
    if lookup_file.exists():
        constituency_lookup = pd.read_csv(lookup_file)
        logger.info(f"Loaded constituency lookup with {len(constituency_lookup)} constituencies")
    else:
        logger.warning("No constituency lookup file found - will use codes only")
        constituency_lookup = None

    # Load enriched data
    enriched_file = DATA_PROCESSED_DIR / "epc_england_wales_enriched.parquet"

    if not enriched_file.exists():
        # Try validated file
        enriched_file = DATA_PROCESSED_DIR / "epc_england_wales_validated.parquet"

    if not enriched_file.exists():
        logger.error(f"No data file found in {DATA_PROCESSED_DIR}")
        return

    logger.info(f"Loading data from: {enriched_file}")

    # Load specific columns to reduce memory
    columns_needed = [
        'CONSTITUENCY', 'LOCAL_AUTHORITY', 'CURRENT_ENERGY_RATING',
        'MAIN_FUEL', 'TOTAL_FLOOR_AREA', 'ENERGY_CONSUMPTION_CURRENT',
        'CURRENT_ENERGY_EFFICIENCY'
    ]

    try:
        df = pd.read_parquet(enriched_file, columns=columns_needed)
    except Exception as e:
        logger.warning(f"Could not load specific columns: {e}")
        df = pd.read_parquet(enriched_file)

    logger.info(f"Loaded {len(df):,} records")

    # Check columns
    logger.info(f"Columns: {list(df.columns)}")

    # Use CONSTITUENCY column (from EPC raw data)
    constituency_col = None
    if 'CONSTITUENCY' in df.columns:
        constituency_col = 'CONSTITUENCY'
        const_count = df[constituency_col].nunique()
        logger.info(f"Found {const_count} unique constituencies (using CONSTITUENCY column)")
    elif 'constituency_name' in df.columns:
        constituency_col = 'constituency_name'
        const_count = df[constituency_col].nunique()
        logger.info(f"Found {const_count} unique constituencies (using constituency_name column)")
    else:
        logger.error("No constituency column found!")
        logger.info(f"Available columns: {list(df.columns)}")
        return

    # Categorize fuels
    from src.analysis.heating_fuel_analysis import HeatingFuelAnalyzer
    fuel_analyzer = HeatingFuelAnalyzer()

    if 'MAIN_FUEL' in df.columns:
        logger.info("\n=== Categorizing fuels ===")
        df['fuel_category'] = df['MAIN_FUEL'].apply(fuel_analyzer.categorize_fuel_type)
        logger.info("Fuel categories added")

    # Function to add constituency names
    def add_constituency_names(result_df, constituency_lookup):
        """Add constituency names to results dataframe."""
        if constituency_lookup is not None:
            result_df = result_df.merge(
                constituency_lookup,
                left_on='constituency',
                right_on='CONSTITUENCY',
                how='left'
            )
            # Reorder columns to put name first
            cols = list(result_df.columns)
            if 'CONSTITUENCY_LABEL' in cols:
                cols.remove('CONSTITUENCY_LABEL')
                cols.remove('CONSTITUENCY')
                cols = ['constituency', 'CONSTITUENCY_LABEL'] + [c for c in cols if c != 'constituency']
                result_df = result_df[cols]
                result_df.rename(columns={'CONSTITUENCY_LABEL': 'constituency_name'}, inplace=True)
        return result_df

    # 1. Fuel Mix by Constituency
    logger.info("\n=== HEATING FUEL MIX BY CONSTITUENCY ===")
    if 'fuel_category' in df.columns:
        fuel_by_const = pd.crosstab(
            df[constituency_col],
            df['fuel_category'],
            normalize='index'
        ) * 100

        # Add property counts
        const_counts = df.groupby(constituency_col).size()
        fuel_by_const['total_properties'] = const_counts
        fuel_by_const = fuel_by_const.reset_index()
        fuel_by_const.rename(columns={constituency_col: 'constituency'}, inplace=True)

        # Add constituency names
        fuel_by_const = add_constituency_names(fuel_by_const, constituency_lookup)

        output_path = DATA_OUTPUTS_DIR / "constituency_fuel_mix.csv"
        fuel_by_const.to_csv(output_path, index=False)
        logger.info(f"Saved: {output_path} ({len(fuel_by_const)} constituencies)")
        logger.info(f"Sample:\n{fuel_by_const.head()}")

    # 2. EPC Distribution by Constituency
    logger.info("\n=== EPC DISTRIBUTION BY CONSTITUENCY ===")
    if 'CURRENT_ENERGY_RATING' in df.columns:
        epc_by_const = pd.crosstab(
            df[constituency_col],
            df['CURRENT_ENERGY_RATING'],
            normalize='index'
        ) * 100

        # Add property counts
        const_counts = df.groupby(constituency_col).size()
        epc_by_const['total_properties'] = const_counts

        # Add percentage EPC C+ (compliant)
        compliant_cols = [col for col in ['A', 'B', 'C'] if col in epc_by_const.columns]
        epc_by_const['pct_epc_c_plus'] = epc_by_const[compliant_cols].sum(axis=1)

        # Calculate average SAP score if available
        if 'CURRENT_ENERGY_EFFICIENCY' in df.columns:
            avg_sap = df.groupby(constituency_col)['CURRENT_ENERGY_EFFICIENCY'].mean()
            epc_by_const['avg_sap_score'] = avg_sap

        epc_by_const = epc_by_const.reset_index()
        epc_by_const.rename(columns={constituency_col: 'constituency'}, inplace=True)

        # Add constituency names
        epc_by_const = add_constituency_names(epc_by_const, constituency_lookup)

        output_path = DATA_OUTPUTS_DIR / "constituency_epc_distribution.csv"
        epc_by_const.to_csv(output_path, index=False)
        logger.info(f"Saved: {output_path} ({len(epc_by_const)} constituencies)")
        logger.info(f"Sample:\n{epc_by_const.head()}")

    # 3. Heat Pump Suitability by Constituency (simplified, no df.copy())
    logger.info("\n=== HEAT PUMP SUITABILITY BY CONSTITUENCY ===")
    if 'CURRENT_ENERGY_RATING' in df.columns:
        # Tier based on EPC rating
        epc_tier_map = {
            'A': 1, 'B': 1, 'C': 1,  # Ready
            'D': 2,  # Minor work
            'E': 3,  # Moderate work
            'F': 4,  # Major work
            'G': 5   # Challenging
        }
        df['hp_tier'] = df['CURRENT_ENERGY_RATING'].map(epc_tier_map).fillna(5)

        hp_by_const = df.groupby(constituency_col).agg({
            'hp_tier': ['mean', 'count'],
            'CURRENT_ENERGY_RATING': lambda x: (x.isin(['A', 'B', 'C', 'D'])).sum()
        })
        hp_by_const.columns = ['avg_hp_tier', 'total_properties', 'ready_or_minor']
        hp_by_const['pct_ready_or_minor'] = hp_by_const['ready_or_minor'] / hp_by_const['total_properties'] * 100
        hp_by_const = hp_by_const.reset_index()
        hp_by_const.rename(columns={constituency_col: 'constituency'}, inplace=True)

        # Add constituency names
        hp_by_const = add_constituency_names(hp_by_const, constituency_lookup)

        output_path = DATA_OUTPUTS_DIR / "constituency_heat_pump_potential.csv"
        hp_by_const.to_csv(output_path, index=False)
        logger.info(f"Saved: {output_path} ({len(hp_by_const)} constituencies)")
        logger.info(f"Sample:\n{hp_by_const.head()}")

    # 4. Heat Network Potential by Constituency
    logger.info("\n=== HEAT NETWORK POTENTIAL BY CONSTITUENCY ===")
    if 'ENERGY_CONSUMPTION_CURRENT' in df.columns:
        hn_by_const = df.groupby(constituency_col).agg({
            'ENERGY_CONSUMPTION_CURRENT': ['sum', 'mean', 'count']
        })
        hn_by_const.columns = ['total_heat_demand_kwh', 'avg_heat_demand_kwh', 'total_properties']
        hn_by_const['total_heat_demand_gwh'] = hn_by_const['total_heat_demand_kwh'] / 1e6

        # Classify by property count (proxy for density)
        def classify_density(count):
            if count >= 50000:
                return 'high'
            elif count >= 25000:
                return 'medium'
            elif count >= 10000:
                return 'low'
            else:
                return 'very_low'

        hn_by_const['density_tier'] = hn_by_const['total_properties'].apply(classify_density)
        hn_by_const = hn_by_const.reset_index()
        hn_by_const.rename(columns={constituency_col: 'constituency'}, inplace=True)

        # Add constituency names
        hn_by_const = add_constituency_names(hn_by_const, constituency_lookup)

        output_path = DATA_OUTPUTS_DIR / "constituency_heat_network_potential.csv"
        hn_by_const.to_csv(output_path, index=False)
        logger.info(f"Saved: {output_path} ({len(hn_by_const)} constituencies)")
        logger.info(f"Sample:\n{hn_by_const.head()}")

    # 5. Constituency Summary
    logger.info("\n=== CONSTITUENCY SUMMARY ===")
    const_summary = df.groupby(constituency_col).agg({
        constituency_col: 'count'
    }).rename(columns={constituency_col: 'total_properties'})

    if 'TOTAL_FLOOR_AREA' in df.columns:
        avg_area = df.groupby(constituency_col)['TOTAL_FLOOR_AREA'].mean()
        const_summary['avg_floor_area'] = avg_area

    if 'fuel_category' in df.columns:
        gas_pct = (
            df[df['fuel_category'] == 'mains_gas']
            .groupby(constituency_col).size() /
            df.groupby(constituency_col).size() * 100
        )
        const_summary['pct_gas_heated'] = gas_pct

    if 'CURRENT_ENERGY_RATING' in df.columns:
        epc_c_pct = (
            df[df['CURRENT_ENERGY_RATING'].isin(['A', 'B', 'C'])]
            .groupby(constituency_col).size() /
            df.groupby(constituency_col).size() * 100
        )
        const_summary['pct_epc_c_plus'] = epc_c_pct

    const_summary = const_summary.reset_index()
    const_summary.rename(columns={constituency_col: 'constituency'}, inplace=True)

    # Add constituency names
    const_summary = add_constituency_names(const_summary, constituency_lookup)

    output_path = DATA_OUTPUTS_DIR / "constituency_summary.csv"
    const_summary.to_csv(output_path, index=False)
    logger.info(f"Saved: {output_path} ({len(const_summary)} constituencies)")
    logger.info(f"Sample:\n{const_summary.head()}")

    logger.info("\n=== CONSTITUENCY ANALYSIS COMPLETE ===")
    logger.info(f"Output directory: {DATA_OUTPUTS_DIR}")

    # Show file list
    output_files = list(DATA_OUTPUTS_DIR.glob("constituency_*.csv"))
    logger.info(f"\nGenerated {len(output_files)} constituency CSV files:")
    for f in output_files:
        size_kb = f.stat().st_size / 1024
        logger.info(f"  {f.name} ({size_kb:.1f} KB)")


if __name__ == "__main__":
    main()
