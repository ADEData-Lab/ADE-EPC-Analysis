"""
Heat Network Potential Analysis Module

Analyzes heat network deployment potential across geographic areas.
Key ADE policy metric for identifying priority areas for heat network development.

Provides:
- Heat density calculation (kWh/m/year or GWh/km²)
- Priority area identification (high/medium/low density)
- Geographic breakdown of network potential
- Aggregated heat demand by area
"""

import pandas as pd
import numpy as np
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from loguru import logger

import sys
sys.path.append(str(Path(__file__).parent.parent.parent))
from config.config import load_config, DATA_OUTPUTS_DIR


class HeatNetworkPotentialAnalyzer:
    """
    Analyzes heat network deployment potential by geographic area.

    Focuses on heat density as the key metric for network viability.
    """

    # Density classification thresholds (from config)
    DENSITY_TIERS = {
        'high': "High priority (>3,000 kWh/m/year)",
        'medium': "Medium priority (1,500-3,000 kWh/m/year)",
        'low': "Low priority (500-1,500 kWh/m/year)",
        'very_low': "Not viable (<500 kWh/m/year)"
    }

    # Property count thresholds for proxy density (when area data unavailable)
    # Based on typical UK LA sizes: urban LAs have more properties in smaller areas
    PROXY_DENSITY_THRESHOLDS = {
        'high': 100000,      # Major urban centres (Birmingham, Leeds, Manchester)
        'medium': 50000,     # Urban/suburban areas
        'low': 25000,        # Mixed urban-rural
        'very_low': 0        # Rural areas
    }

    def __init__(self):
        """Initialize the heat network potential analyzer."""
        self.config = load_config()
        self.policy_config = self.config.get('policy_metrics', {}).get('heat_network', {})
        self.results = {}
        logger.info("Initialized Heat Network Potential Analyzer")

    def calculate_heat_density(
        self,
        df: pd.DataFrame,
        geography_col: str = 'local_authority_name',
        area_col: Optional[str] = None
    ) -> pd.DataFrame:
        """
        Calculate heat density by geographic area.

        Heat density = Total annual heat demand / Area

        Args:
            df: EPC DataFrame with heat demand and geography
            geography_col: Column for geographic grouping
            area_col: Column with area (km²). If None, uses property count as proxy

        Returns:
            DataFrame with heat density by area
        """
        logger.info(f"Calculating heat density by {geography_col}...")

        # Try fallback columns if primary geography column not found
        if geography_col not in df.columns:
            # Try common fallback columns
            fallback_cols = ['LOCAL_AUTHORITY', 'LOCAL_AUTHORITY_LABEL', 'POSTTOWN']
            for fallback in fallback_cols:
                if fallback in df.columns:
                    logger.warning(f"Geography column '{geography_col}' not found, using '{fallback}' instead")
                    geography_col = fallback
                    break
            else:
                logger.error(f"Geography column not found: {geography_col} (and no fallbacks available)")
                logger.info(f"Available columns: {list(df.columns)[:20]}...")
                return pd.DataFrame()

        # Calculate annual heat demand per property (kWh/year)
        if 'ENERGY_CONSUMPTION_CURRENT' in df.columns:
            # Use current energy consumption if available
            df['annual_heat_demand_kwh'] = df['ENERGY_CONSUMPTION_CURRENT']
        elif 'TOTAL_FLOOR_AREA' in df.columns:
            # Estimate from floor area (rough approximation)
            # Assume ~100 kWh/m²/year average for heating
            df['annual_heat_demand_kwh'] = df['TOTAL_FLOOR_AREA'] * 100
        else:
            logger.warning("No heat demand data available - using property count only")
            df['annual_heat_demand_kwh'] = 1000  # Placeholder

        # Aggregate by geography
        geo_summary = df.groupby(geography_col).agg({
            'annual_heat_demand_kwh': 'sum',
            geography_col: 'count'  # Property count
        }).rename(columns={geography_col: 'property_count'})

        # Convert to GWh
        geo_summary['total_heat_demand_gwh'] = geo_summary['annual_heat_demand_kwh'] / 1e6

        # If area is provided, calculate density
        if area_col and area_col in df.columns:
            # Get area for each geography
            area_lookup = df.groupby(geography_col)[area_col].first()
            geo_summary['area_km2'] = area_lookup
            geo_summary['heat_density_gwh_per_km2'] = (
                geo_summary['total_heat_demand_gwh'] / geo_summary['area_km2']
            )
        else:
            # Use property count as density proxy (more properties = likely denser urban area)
            geo_summary['heat_density_proxy'] = geo_summary['property_count']
            geo_summary['using_proxy'] = True

        geo_summary = geo_summary.reset_index()
        geo_summary['_geography_col'] = geography_col  # Store the actual column name used

        logger.info(f"Calculated heat density for {len(geo_summary)} areas")

        return geo_summary

    def classify_density_tier(self, heat_density: float, use_proxy: bool = False) -> str:
        """
        Classify heat density into tiers.

        Args:
            heat_density: Heat density (kWh/m/year) or property count (if proxy)
            use_proxy: If True, use property count thresholds instead of kWh/m

        Returns:
            Density tier classification
        """
        if use_proxy:
            # Use property count thresholds
            if heat_density >= self.PROXY_DENSITY_THRESHOLDS['high']:
                return 'high'
            elif heat_density >= self.PROXY_DENSITY_THRESHOLDS['medium']:
                return 'medium'
            elif heat_density >= self.PROXY_DENSITY_THRESHOLDS['low']:
                return 'low'
            else:
                return 'very_low'
        else:
            # Use kWh/m thresholds from config
            high_threshold = self.policy_config.get('high_density_threshold', 3000)
            medium_threshold = self.policy_config.get('medium_density_threshold', 1500)
            low_threshold = self.policy_config.get('low_density_threshold', 500)

            if heat_density >= high_threshold:
                return 'high'
            elif heat_density >= medium_threshold:
                return 'medium'
            elif heat_density >= low_threshold:
                return 'low'
            else:
                return 'very_low'

    def identify_priority_areas(
        self,
        df: pd.DataFrame,
        geography_col: str = 'local_authority_name',
        min_tier: str = 'medium'
    ) -> pd.DataFrame:
        """
        Identify priority areas for heat network development.

        Args:
            df: DataFrame with heat density calculations
            geography_col: Geography column
            min_tier: Minimum tier to include ('high', 'medium', 'low')

        Returns:
            DataFrame of priority areas
        """
        logger.info("Identifying priority areas for heat network development...")

        # Calculate heat density
        density_df = self.calculate_heat_density(df, geography_col)

        # Handle empty result (geography column not found)
        if density_df.empty:
            logger.warning("No density data calculated - returning empty results")
            self.results['priority_areas'] = {
                'total_priority_areas': 0,
                'total_heat_demand_gwh': 0.0,
                'total_properties': 0,
                'tier_breakdown': {}
            }
            return pd.DataFrame()

        # Get the actual geography column used (may differ from parameter due to fallback)
        actual_geography_col = density_df['_geography_col'].iloc[0] if '_geography_col' in density_df.columns else geography_col

        # Classify tiers
        use_proxy = 'using_proxy' in density_df.columns and density_df['using_proxy'].iloc[0]

        if 'heat_density_gwh_per_km2' in density_df.columns:
            density_col = 'heat_density_gwh_per_km2'
            # Convert GWh/km² to kWh/m for comparison with thresholds
            # 1 GWh/km² = 1000 kWh/m (linear meter of street)
            density_df['density_metric'] = density_df[density_col] * 1000
        else:
            density_col = 'heat_density_proxy'
            # Proxy uses property count as density indicator
            density_df['density_metric'] = density_df[density_col]

        density_df['density_tier'] = density_df['density_metric'].apply(
            lambda x: self.classify_density_tier(x, use_proxy=use_proxy)
        )

        # Filter to priority areas
        tier_order = ['high', 'medium', 'low', 'very_low']
        min_tier_idx = tier_order.index(min_tier)
        priority_tiers = tier_order[:min_tier_idx + 1]

        priority_areas = density_df[density_df['density_tier'].isin(priority_tiers)].copy()
        priority_areas = priority_areas.sort_values('density_metric', ascending=False)

        logger.info(f"Found {len(priority_areas)} priority areas ({min_tier}+ tier)")

        # Log top areas
        if len(priority_areas) > 0:
            logger.info("Top 10 priority areas for heat networks:")
            for idx, row in priority_areas.head(10).iterrows():
                logger.info(
                    f"  {row[actual_geography_col]}: {row['density_tier']} "
                    f"({row['total_heat_demand_gwh']:.1f} GWh, {row['property_count']:,} properties)"
                )

        self.results['priority_areas'] = {
            'total_priority_areas': len(priority_areas),
            'total_heat_demand_gwh': float(priority_areas['total_heat_demand_gwh'].sum()),
            'total_properties': int(priority_areas['property_count'].sum()),
            'tier_breakdown': priority_areas['density_tier'].value_counts().to_dict()
        }

        return priority_areas

    def analyze_by_geography(
        self,
        df: pd.DataFrame,
        level: str = 'national',
        geography_col: Optional[str] = None
    ) -> pd.DataFrame:
        """
        Analyze heat network potential by geographic level.

        Args:
            df: EPC DataFrame
            level: Geographic level ('national', 'regional', 'local_authority')
            geography_col: Column name for geography

        Returns:
            DataFrame with heat network potential summary
        """
        logger.info(f"Analyzing heat network potential by {level}...")

        if level == 'national':
            # National summary
            if 'annual_heat_demand_kwh' not in df.columns:
                if 'ENERGY_CONSUMPTION_CURRENT' in df.columns:
                    df['annual_heat_demand_kwh'] = df['ENERGY_CONSUMPTION_CURRENT']
                else:
                    logger.warning("No heat demand data - using estimates")
                    df['annual_heat_demand_kwh'] = df.get('TOTAL_FLOOR_AREA', 100) * 100

            total_heat_gwh = df['annual_heat_demand_kwh'].sum() / 1e6
            total_properties = len(df)

            result_df = pd.DataFrame({
                'geography': ['England and Wales'],
                'geography_level': ['National'],
                'total_properties': [total_properties],
                'total_heat_demand_gwh': [total_heat_gwh],
                'avg_heat_per_property_kwh': [df['annual_heat_demand_kwh'].mean()]
            })

            return result_df

        else:
            # Geographic breakdown
            if geography_col is None:
                if level == 'regional':
                    geography_col = 'region_name'
                elif level == 'local_authority':
                    geography_col = 'local_authority_name'
                elif level == 'constituency':
                    geography_col = 'constituency_name'

            if geography_col not in df.columns:
                logger.error(f"Geography column not found: {geography_col}")
                return pd.DataFrame()

            # Calculate heat density
            result_df = self.calculate_heat_density(df, geography_col)
            result_df['geography_level'] = level

            # Add tier classification
            if 'heat_density_kwh_per_m' in result_df.columns:
                result_df['density_tier'] = result_df['heat_density_kwh_per_m'].apply(
                    self.classify_density_tier
                )
            elif 'heat_density_proxy' in result_df.columns:
                result_df['density_tier'] = result_df['heat_density_proxy'].apply(
                    self.classify_density_tier
                )

            logger.info(f"Analyzed {len(result_df)} {level} areas")

            return result_df

    def calculate_network_potential(
        self,
        df: pd.DataFrame,
        connection_cost_per_property: float = 5000,
        network_efficiency: float = 0.90
    ) -> Dict:
        """
        Calculate overall heat network deployment potential.

        Args:
            df: EPC DataFrame
            connection_cost_per_property: Average connection cost (£)
            network_efficiency: Heat network efficiency (0-1)

        Returns:
            Dictionary with network potential statistics
        """
        logger.info("Calculating overall heat network potential...")

        # Calculate heat density by area - will use fallback column if needed
        density_df = self.calculate_heat_density(df, 'local_authority_name')

        # Handle empty result
        if density_df.empty:
            logger.warning("No density data - returning minimal network potential results")
            results = {
                'total_viable_properties': 0,
                'total_viable_heat_demand_gwh': 0.0,
                'total_connection_cost_bn': 0.0,
                'tier_breakdown': [],
                'pct_viable': 0.0
            }
            self.results['network_potential'] = results
            return results

        # Classify areas
        use_proxy = 'using_proxy' in density_df.columns and density_df['using_proxy'].iloc[0]

        if 'heat_density_gwh_per_km2' in density_df.columns:
            density_df['density_metric'] = density_df['heat_density_gwh_per_km2'] * 1000
        else:
            density_df['density_metric'] = density_df['heat_density_proxy']

        density_df['density_tier'] = density_df['density_metric'].apply(
            lambda x: self.classify_density_tier(x, use_proxy=use_proxy)
        )

        # Calculate potential by tier
        tier_summary = density_df.groupby('density_tier').agg({
            'property_count': 'sum',
            'total_heat_demand_gwh': 'sum'
        }).reset_index()

        # Calculate costs
        tier_summary['connection_cost_m'] = (
            tier_summary['property_count'] * connection_cost_per_property / 1e6
        )

        # High and medium tiers are viable for networks
        viable_tiers = tier_summary[tier_summary['density_tier'].isin(['high', 'medium'])]

        results = {
            'total_viable_properties': int(viable_tiers['property_count'].sum()),
            'total_viable_heat_demand_gwh': float(viable_tiers['total_heat_demand_gwh'].sum()),
            'total_connection_cost_bn': float(viable_tiers['connection_cost_m'].sum() / 1000),
            'tier_breakdown': tier_summary.to_dict('records'),
            'pct_viable': float(viable_tiers['property_count'].sum() / df.shape[0] * 100)
        }

        logger.info(f"Heat network viable properties: {results['total_viable_properties']:,} ({results['pct_viable']:.1f}%)")
        logger.info(f"Total heat demand (viable areas): {results['total_viable_heat_demand_gwh']:.1f} GWh")
        logger.info(f"Estimated connection cost: £{results['total_connection_cost_bn']:.2f}B")

        self.results['network_potential'] = results
        return results

    def save_results(self, output_path: Optional[Path] = None):
        """
        Save analysis results to file.

        Args:
            output_path: Path to save results
        """
        if output_path is None:
            output_path = DATA_OUTPUTS_DIR / "heat_network_potential_results.txt"

        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write("HEAT NETWORK POTENTIAL ANALYSIS RESULTS\n")
            f.write("=" * 70 + "\n\n")

            for section, data in self.results.items():
                f.write(f"\n{section.replace('_', ' ').upper()}\n")
                f.write("-" * 70 + "\n")

                if isinstance(data, dict):
                    for key, value in data.items():
                        f.write(f"{key}: {value}\n")
                else:
                    f.write(str(data) + "\n")

        logger.info(f"Results saved to: {output_path}")


def main():
    """Main execution function for heat network potential analysis."""
    logger.info("Starting heat network potential analysis...")

    # Load data
    from config.config import DATA_PROCESSED_DIR
    input_file = DATA_PROCESSED_DIR / "epc_london_validated.csv"

    if not input_file.exists():
        logger.error(f"Input file not found: {input_file}")
        return

    logger.info(f"Loading data from: {input_file}")
    df = pd.read_csv(input_file, low_memory=False)

    # Perform analysis
    analyzer = HeatNetworkPotentialAnalyzer()
    priority_areas = analyzer.identify_priority_areas(df, min_tier='medium')
    network_potential = analyzer.calculate_network_potential(df)

    # Save results
    analyzer.save_results()

    # Save priority areas
    output_file = DATA_OUTPUTS_DIR / "heat_network_priority_areas.csv"
    priority_areas.to_csv(output_file, index=False)
    logger.info(f"Priority areas saved to: {output_file}")

    logger.info("Heat network potential analysis complete!")


if __name__ == "__main__":
    main()
