"""
Add Heat Network Zone Proximity Tiers to EPC Data

Integrates DESNZ Heat Networks Planning Database proximity analysis with EPC data.
Adds proximity tiers based on distance to nearest heat network.

Usage:
    python add_heat_network_proximity_tiers.py

Outputs:
    - Updated EPC data with proximity tiers
    - Constituency-level proximity summary
    - Analysis report
"""

import sys
from pathlib import Path
from loguru import logger
import pandas as pd
import geopandas as gpd

sys.path.append(str(Path(__file__).parent))

from config.config import DATA_PROCESSED_DIR, DATA_OUTPUTS_DIR
from src.spatial.heat_network_zone_proximity import HeatNetworkZoneProximityAnalyzer
from src.spatial.postcode_geocoder import PostcodeGeocoder


def load_epc_sample(n_sample: int = 100000):
    """
    Load a sample of EPC data for testing.

    Args:
        n_sample: Number of records to sample

    Returns:
        DataFrame with EPC data
    """
    enriched_file = DATA_PROCESSED_DIR / "epc_england_wales_enriched.parquet"

    if not enriched_file.exists():
        logger.error(f"EPC data file not found: {enriched_file}")
        return None

    logger.info(f"Loading EPC data from: {enriched_file}")

    # Load specific columns to reduce memory
    columns_needed = [
        'POSTCODE', 'CONSTITUENCY', 'CONSTITUENCY_LABEL', 'LOCAL_AUTHORITY',
        'CURRENT_ENERGY_RATING', 'MAIN_FUEL', 'TOTAL_FLOOR_AREA',
        'ENERGY_CONSUMPTION_CURRENT', 'PROPERTY_TYPE'
    ]

    try:
        df = pd.read_parquet(enriched_file, columns=columns_needed)
        logger.info(f"Loaded {len(df):,} total records")

        # Sample for testing (remove this for full analysis)
        if n_sample and n_sample < len(df):
            df = df.sample(n=n_sample, random_state=42)
            logger.info(f"Sampled {len(df):,} records for testing")

        return df

    except Exception as e:
        logger.error(f"Error loading EPC data: {e}")
        return None


def geocode_postcodes(df: pd.DataFrame) -> gpd.GeoDataFrame:
    """
    Geocode postcodes to create point geometries using postcodes.io.

    Args:
        df: DataFrame with POSTCODE column

    Returns:
        GeoDataFrame with geometry column
    """
    logger.info("Geocoding postcodes via postcodes.io (batch)...")

    cache_file = DATA_OUTPUTS_DIR / "geocoding_cache.csv"
    geocoder = PostcodeGeocoder(cache_file=cache_file)

    gdf = geocoder.geocode_dataframe(df, postcode_column='POSTCODE', batch_mode=True)
    if gdf is None or gdf.empty:
        logger.error("Failed to geocode any properties - skipping proximity analysis")
        return None

    # Project to British National Grid for distance calculations
    gdf = gdf.to_crs("EPSG:27700")

    if len(gdf) < len(df):
        logger.warning(f"Geocoded {len(gdf):,} of {len(df):,} properties with valid coordinates")

    return gdf


def main():
    """Main execution function."""
    logger.info("=" * 70)
    logger.info("HEAT NETWORK ZONE PROXIMITY TIER INTEGRATION")
    logger.info("=" * 70)

    # 1. Load EPC data (sample for testing)
    logger.info("\n### Step 1: Load EPC Data ###")
    df = load_epc_sample(n_sample=50000)  # Use smaller sample for testing

    if df is None:
        logger.error("Failed to load EPC data - exiting")
        return

    # 2. Geocode postcodes
    logger.info("\n### Step 2: Geocode Postcodes ###")
    properties_gdf = geocode_postcodes(df)

    if properties_gdf is None or properties_gdf.empty:
        logger.error("No geocoded properties available - exiting")
        return

    # 3. Initialize heat network proximity analyzer
    logger.info("\n### Step 3: Load Heat Network Data ###")
    analyzer = HeatNetworkZoneProximityAnalyzer()
    analyzer.load_heat_network_data()

    # 4. Calculate proximity tiers
    logger.info("\n### Step 4: Calculate Proximity Tiers ###")
    properties_gdf = analyzer.calculate_proximity(properties_gdf)

    # 5. Analyze by constituency
    logger.info("\n### Step 5: Constituency-Level Analysis ###")
    constituency_summary = analyzer.analyze_by_constituency(properties_gdf, 'CONSTITUENCY')

    # Save constituency summary
    if len(constituency_summary) > 0:
        # Add constituency names
        lookup_file = Path("data/supplementary/constituency_lookup.csv")
        if lookup_file.exists():
            lookup_df = pd.read_csv(lookup_file)
            constituency_summary = constituency_summary.merge(
                lookup_df,
                left_on='CONSTITUENCY',
                right_on='CONSTITUENCY',
                how='left'
            )
            # Reorder columns
            cols = ['CONSTITUENCY', 'CONSTITUENCY_LABEL', 'total_properties'] + \
                   [c for c in constituency_summary.columns
                    if c not in ['CONSTITUENCY', 'CONSTITUENCY_LABEL', 'total_properties']]
            constituency_summary = constituency_summary[cols]

        output_path = DATA_OUTPUTS_DIR / "constituency_heat_network_proximity.csv"
        constituency_summary.to_csv(output_path, index=False)
        logger.info(f"Saved constituency summary: {output_path}")

    # 6. Save enriched dataset
    logger.info("\n### Step 6: Save Enriched Dataset ###")

    # Convert back to DataFrame for CSV export
    output_df = properties_gdf.copy()
    output_df['LATITUDE'] = output_df.geometry.to_crs("EPSG:4326").y
    output_df['LONGITUDE'] = output_df.geometry.to_crs("EPSG:4326").x
    output_df = output_df.drop(columns=['geometry'])

    # Select key columns for output
    output_columns = [
        'POSTCODE', 'CONSTITUENCY', 'CONSTITUENCY_LABEL', 'LOCAL_AUTHORITY',
        'CURRENT_ENERGY_RATING', 'MAIN_FUEL', 'PROPERTY_TYPE',
        'LATITUDE', 'LONGITUDE',
        'distance_to_hn_m', 'hn_zone_proximity_tier', 'hn_zone_proximity_tier_number'
    ]

    # Filter to existing columns
    output_columns = [c for c in output_columns if c in output_df.columns]
    output_df = output_df[output_columns]

    output_path = DATA_OUTPUTS_DIR / "epc_with_heat_network_proximity_tiers.csv"
    output_df.to_csv(output_path, index=False)
    logger.info(f"Saved enriched dataset: {output_path} ({len(output_df):,} records)")

    # 7. Save analysis report
    logger.info("\n### Step 7: Save Analysis Report ###")
    analyzer.save_results()

    # 8. Summary statistics
    logger.info("\n### Summary Statistics ###")
    logger.info(f"Total properties analyzed: {len(properties_gdf):,}")
    logger.info(f"\nTier Distribution:")
    tier_counts = properties_gdf['hn_zone_proximity_tier'].value_counts().sort_index()
    for tier, count in tier_counts.items():
        pct = count / len(properties_gdf) * 100
        logger.info(f"  {tier}: {count:,} ({pct:.1f}%)")

    logger.info("\n" + "=" * 70)
    logger.info("ANALYSIS COMPLETE")
    logger.info("=" * 70)


if __name__ == "__main__":
    main()
