"""
Heat Network Zone Proximity Analysis Module

Analyzes property proximity to planned heat network zones using DESNZ Heat Networks
Planning Database. Assigns proximity tiers based on distance to nearest heat network.

Based on: Heat Network Zone Proximity Analysis Plan.docx

Proximity Tiers:
- Tier 1: Inside or adjacent to operational/planned heat network (0-250m)
- Tier 2: Within 250m of a heat network
- Tier 3: 250m-1km from nearest heat network
- Tier 4: Over 1km from any heat network

Data Sources:
- DESNZ Heat Networks Planning Database
- https://www.data.gov.uk/dataset/065d267f-23bc-4d0e-9a56-52d388d5835c/desnz-heat-networks-planning-database
"""

import pandas as pd
import geopandas as gpd
from shapely import wkt
from shapely.geometry import Point
from shapely.ops import unary_union
from pathlib import Path
from typing import Dict, Optional, Tuple
from loguru import logger

import sys
sys.path.append(str(Path(__file__).parent.parent.parent))
from config.config import load_config, DATA_RAW_DIR, DATA_PROCESSED_DIR, DATA_OUTPUTS_DIR


class HeatNetworkZoneProximityAnalyzer:
    """
    Analyzes property proximity to planned heat network zones.

    Uses DESNZ Heat Networks Planning Database to determine how close
    properties are to existing or planned heat networks.
    """

    # Proximity tier definitions (in meters)
    PROXIMITY_TIERS = {
        'tier_1': {
            'name': 'Tier 1: Inside or adjacent to heat network',
            'max_distance': 250,
            'description': 'Within 250m of operational or planned heat network'
        },
        'tier_2': {
            'name': 'Tier 2: Within 250m of heat network',
            'max_distance': 250,
            'description': 'Close proximity to heat network infrastructure'
        },
        'tier_3': {
            'name': 'Tier 3: 250m-1km from heat network',
            'max_distance': 1000,
            'description': 'Medium distance from heat network'
        },
        'tier_4': {
            'name': 'Tier 4: Over 1km from heat network',
            'max_distance': float('inf'),
            'description': 'Remote from any planned heat network'
        }
    }

    # Development status weighting (higher = more likely to proceed)
    STATUS_WEIGHTS = {
        'Operational': 1.0,
        'Under Construction': 0.9,
        'Awaiting Construction': 0.8,
        'Application Submitted': 0.5,
        'Revised': 0.5,
        'No Application Required': 0.9
    }

    def __init__(self, heat_network_file: Optional[Path] = None):
        """
        Initialize the heat network zone proximity analyzer.

        Args:
            heat_network_file: Path to DESNZ heat network planning database CSV
        """
        self.config = load_config()

        if heat_network_file is None:
            heat_network_file = DATA_RAW_DIR / "desnz_heat_network_planning_database.csv"

        self.heat_network_file = heat_network_file
        self.heat_networks_gdf = None
        self.results = {}

        logger.info("Initialized Heat Network Zone Proximity Analyzer")

    def load_heat_network_data(self) -> gpd.GeoDataFrame:
        """
        Load DESNZ heat network planning database and convert to GeoDataFrame.

        Returns:
            GeoDataFrame of heat network projects with point geometries
        """
        logger.info(f"Loading heat network data from: {self.heat_network_file}")

        # Load CSV with latin-1 encoding (handles special characters)
        df = pd.read_csv(self.heat_network_file, encoding='latin-1')

        logger.info(f"Loaded {len(df)} heat network projects")

        # Filter to England and Wales only
        df = df[df['Country'].isin(['England', 'Wales'])].copy()
        logger.info(f"Filtered to {len(df)} projects in England and Wales")

        # Filter to records with coordinates
        df = df[df[['X-coordinate', 'Y-coordinate']].notna().all(axis=1)].copy()
        logger.info(f"{len(df)} projects have coordinates")

        # Create point geometries from coordinates
        # Note: DESNZ coordinates are in British National Grid (EPSG:27700)
        geometry = [Point(xy) for xy in zip(df['X-coordinate'], df['Y-coordinate'])]
        gdf = gpd.GeoDataFrame(df, geometry=geometry, crs="EPSG:27700")

        # Store development status distribution
        status_counts = gdf['Development Status (short)'].value_counts()
        logger.info(f"Development status breakdown:\n{status_counts}")

        self.heat_networks_gdf = gdf
        self.results['total_heat_networks'] = len(gdf)
        self.results['status_breakdown'] = status_counts.to_dict()

        return gdf

    def calculate_proximity(
        self,
        properties_gdf: gpd.GeoDataFrame,
        filter_status: Optional[list] = None
    ) -> gpd.GeoDataFrame:
        """
        Calculate proximity of properties to heat networks.

        Args:
            properties_gdf: GeoDataFrame of properties with point geometries
            filter_status: Optional list of development statuses to include
                          (e.g., ['Operational', 'Under Construction'])

        Returns:
            GeoDataFrame with added proximity columns
        """
        if self.heat_networks_gdf is None:
            self.load_heat_network_data()

        logger.info(f"Calculating proximity for {len(properties_gdf):,} properties...")

        # Filter heat networks by status if specified
        hn_gdf = self.heat_networks_gdf.copy()
        if filter_status:
            hn_gdf = hn_gdf[hn_gdf['Development Status (short)'].isin(filter_status)]
            logger.info(f"Using {len(hn_gdf)} heat networks with status: {filter_status}")

        # Ensure both are in British National Grid for accurate distance (meters)
        if properties_gdf.crs != "EPSG:27700":
            logger.info("Reprojecting properties to British National Grid (EPSG:27700)")
            properties_gdf = properties_gdf.to_crs("EPSG:27700")

        # Create union of all heat network points
        hn_union = unary_union(hn_gdf.geometry)

        # Calculate distance to nearest heat network (meters)
        logger.info("Computing distances to nearest heat network...")
        properties_gdf['distance_to_hn_m'] = properties_gdf.geometry.apply(
            lambda pt: pt.distance(hn_union)
        )

        logger.info(f"Distance statistics:")
        logger.info(f"  Min: {properties_gdf['distance_to_hn_m'].min():.0f}m")
        logger.info(f"  Median: {properties_gdf['distance_to_hn_m'].median():.0f}m")
        logger.info(f"  Max: {properties_gdf['distance_to_hn_m'].max():.0f}m")

        # Assign proximity tier
        properties_gdf['hn_zone_proximity_tier'] = properties_gdf['distance_to_hn_m'].apply(
            self._categorize_proximity_tier
        )

        # Add numeric tier for sorting/filtering
        tier_mapping = {
            'Tier 1: Inside or adjacent to heat network': 1,
            'Tier 2: Within 250m of heat network': 2,
            'Tier 3: 250m-1km from heat network': 3,
            'Tier 4: Over 1km from heat network': 4
        }
        properties_gdf['hn_zone_proximity_tier_number'] = (
            properties_gdf['hn_zone_proximity_tier'].map(tier_mapping)
        )

        # Log tier distribution
        tier_counts = properties_gdf['hn_zone_proximity_tier'].value_counts().sort_index()
        logger.info(f"\nProximity tier distribution:")
        for tier, count in tier_counts.items():
            pct = count / len(properties_gdf) * 100
            logger.info(f"  {tier}: {count:,} ({pct:.1f}%)")

        self.results['tier_distribution'] = tier_counts.to_dict()

        return properties_gdf

    def _categorize_proximity_tier(self, distance_m: float) -> str:
        """
        Categorize proximity tier based on distance to nearest heat network.

        Args:
            distance_m: Distance to nearest heat network in meters

        Returns:
            Proximity tier description
        """
        if distance_m <= 250:
            return 'Tier 1: Inside or adjacent to heat network'
        elif distance_m <= 1000:
            return 'Tier 3: 250m-1km from heat network'
        else:
            return 'Tier 4: Over 1km from heat network'

    def analyze_by_constituency(
        self,
        properties_gdf: gpd.GeoDataFrame,
        constituency_col: str = 'CONSTITUENCY'
    ) -> pd.DataFrame:
        """
        Analyze heat network proximity by constituency.

        Args:
            properties_gdf: GeoDataFrame with proximity tiers
            constituency_col: Column name for constituency

        Returns:
            DataFrame with constituency-level summary
        """
        logger.info("Analyzing heat network proximity by constituency...")

        if constituency_col not in properties_gdf.columns:
            logger.error(f"Constituency column '{constituency_col}' not found")
            return pd.DataFrame()

        # Group by constituency and tier
        constituency_summary = properties_gdf.groupby(
            [constituency_col, 'hn_zone_proximity_tier']
        ).size().unstack(fill_value=0)

        # Add total properties
        constituency_summary['total_properties'] = constituency_summary.sum(axis=1)

        # Calculate percentages
        for tier in constituency_summary.columns[:-1]:  # Exclude total_properties
            constituency_summary[f'{tier}_pct'] = (
                constituency_summary[tier] / constituency_summary['total_properties'] * 100
            )

        # Calculate average distance
        avg_distance = properties_gdf.groupby(constituency_col)['distance_to_hn_m'].mean()
        constituency_summary['avg_distance_to_hn_km'] = avg_distance / 1000

        constituency_summary = constituency_summary.reset_index()

        logger.info(f"Generated summary for {len(constituency_summary)} constituencies")

        return constituency_summary

    def save_results(self, output_path: Optional[Path] = None):
        """
        Save analysis results to file.

        Args:
            output_path: Path to save results
        """
        if output_path is None:
            output_path = DATA_OUTPUTS_DIR / "heat_network_zone_proximity_results.txt"

        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write("HEAT NETWORK ZONE PROXIMITY ANALYSIS RESULTS\n")
            f.write("=" * 70 + "\n\n")
            f.write("Data source: DESNZ Heat Networks Planning Database\n")
            f.write("Analysis date: 2024-12-14\n\n")

            f.write(f"Total heat networks analyzed: {self.results.get('total_heat_networks', 0):,}\n\n")

            f.write("Heat network development status:\n")
            for status, count in self.results.get('status_breakdown', {}).items():
                f.write(f"  {status}: {count:,}\n")

            f.write("\n\nProximity tier distribution:\n")
            f.write("-" * 70 + "\n")
            for tier, count in self.results.get('tier_distribution', {}).items():
                f.write(f"{tier}: {count:,}\n")

        logger.info(f"Results saved to: {output_path}")


def main():
    """Main execution function for heat network zone proximity analysis."""
    logger.info("Starting heat network zone proximity analysis...")

    # Initialize analyzer
    analyzer = HeatNetworkZoneProximityAnalyzer()

    # Load heat network data
    hn_gdf = analyzer.load_heat_network_data()

    # For testing, create a small sample of properties
    # In production, this would load the full EPC dataset
    logger.info("Analysis module created successfully")
    logger.info("To use: integrate with EPC pipeline in run_ade_analysis.py")

    # Save results
    analyzer.save_results()


if __name__ == "__main__":
    main()
