"""
Heating Fuel Mix Analysis Module

Analyzes current heating fuel sources across the domestic building stock.
Key ADE policy metric for understanding decarbonisation baseline and potential.

Provides:
- Fuel type breakdown (gas, electric, oil, LPG, heat networks, renewables)
- Off-gas grid properties identification
- Electrification rate tracking
- Geographic breakdowns
"""

import pandas as pd
import numpy as np
from pathlib import Path
from typing import Dict, List, Optional
from loguru import logger

import sys
sys.path.append(str(Path(__file__).parent.parent.parent))
from config.config import load_config, DATA_OUTPUTS_DIR


class HeatingFuelAnalyzer:
    """
    Analyzes heating fuel mix in the domestic building stock.

    Focus on understanding current fuel sources and identifying opportunities
    for fuel switching and electrification.
    """

    # Fuel type categorization (based on common EPC field values)
    FUEL_CATEGORIES = {
        'mains_gas': ['mains gas', 'natural gas', 'gas'],
        'electric': ['electricity', 'electric'],
        'oil': ['oil', 'heating oil', 'lpg'],
        'lpg': ['lpg', 'bottled lpg', 'bulk lpg'],
        'heat_network': ['heat network', 'community heating', 'district heating'],
        'coal': ['coal', 'smokeless coal', 'anthracite'],
        'wood': ['wood', 'wood pellets', 'biomass'],
        'renewable': ['heat pump', 'ground source', 'air source'],
        'other': ['other']
    }

    def __init__(self):
        """Initialize the heating fuel analyzer."""
        self.config = load_config()
        self.results = {}
        logger.info("Initialized Heating Fuel Analyzer")

    def categorize_fuel_type(self, fuel_description: str) -> str:
        """
        Categorize a fuel description into standard fuel types.

        Args:
            fuel_description: Raw fuel type from EPC

        Returns:
            Standardized fuel category
        """
        if pd.isna(fuel_description):
            return 'unknown'

        fuel_lower = str(fuel_description).lower()

        # Check each category
        for category, keywords in self.FUEL_CATEGORIES.items():
            if any(keyword in fuel_lower for keyword in keywords):
                return category

        return 'other'

    def analyze_fuel_mix(self, df: pd.DataFrame, fuel_col: str = 'MAINHEAT_ENERGY_EFF') -> Dict:
        """
        Analyze overall heating fuel mix.

        Args:
            df: EPC DataFrame
            fuel_col: Column containing fuel type information

        Returns:
            Dictionary with fuel mix statistics
        """
        logger.info(f"Analyzing heating fuel mix for {len(df):,} properties...")

        # Categorize fuels
        if fuel_col not in df.columns:
            # Try alternative column names
            alt_cols = ['MAIN_FUEL', 'MAINHEAT_DESCRIPTION', 'MAIN_HEATING_FUEL']
            fuel_col = next((col for col in alt_cols if col in df.columns), None)

            if fuel_col is None:
                logger.error("No fuel type column found in dataset")
                return {}

        logger.info(f"Using column: {fuel_col}")

        # Categorize
        df['fuel_category'] = df[fuel_col].apply(self.categorize_fuel_type)

        # Calculate distribution
        fuel_counts = df['fuel_category'].value_counts()
        fuel_percentages = df['fuel_category'].value_counts(normalize=True) * 100

        results = {
            'total_properties': len(df),
            'fuel_counts': fuel_counts.to_dict(),
            'fuel_percentages': fuel_percentages.to_dict(),
            'fuel_category_column': fuel_col
        }

        # Log summary
        logger.info("Heating Fuel Mix:")
        for fuel, count in fuel_counts.items():
            pct = fuel_percentages.get(fuel, 0)
            logger.info(f"  {fuel}: {count:,} ({pct:.1f}%)")

        self.results['fuel_mix'] = results
        return results

    def identify_off_gas_properties(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Identify properties not connected to mains gas.

        These are priority targets for heat pump installation.

        Args:
            df: EPC DataFrame with fuel_category column

        Returns:
            DataFrame of off-gas properties
        """
        logger.info("Identifying off-gas properties...")

        if 'fuel_category' not in df.columns:
            logger.error("Run analyze_fuel_mix() first to categorize fuels")
            return pd.DataFrame()

        # Off-gas properties
        off_gas_mask = df['fuel_category'] != 'mains_gas'
        off_gas_df = df[off_gas_mask].copy()

        logger.info(f"Off-gas properties: {len(off_gas_df):,} ({len(off_gas_df)/len(df)*100:.1f}%)")

        # Breakdown by fuel type
        off_gas_breakdown = off_gas_df['fuel_category'].value_counts()
        logger.info("Off-gas fuel breakdown:")
        for fuel, count in off_gas_breakdown.items():
            logger.info(f"  {fuel}: {count:,}")

        self.results['off_gas'] = {
            'total_off_gas': len(off_gas_df),
            'percentage_off_gas': len(off_gas_df) / len(df) * 100,
            'breakdown': off_gas_breakdown.to_dict()
        }

        return off_gas_df

    def calculate_electrification_rate(self, df: pd.DataFrame) -> float:
        """
        Calculate the current electrification rate (properties with electric/heat pump heating).

        Args:
            df: EPC DataFrame with fuel_category column

        Returns:
            Electrification rate (%)
        """
        logger.info("Calculating electrification rate...")

        if 'fuel_category' not in df.columns:
            logger.error("Run analyze_fuel_mix() first to categorize fuels")
            return 0.0

        # Electric heating (including heat pumps)
        electric_mask = df['fuel_category'].isin(['electric', 'renewable'])
        electric_count = electric_mask.sum()

        electrification_rate = (electric_count / len(df)) * 100

        logger.info(f"Electrification rate: {electrification_rate:.2f}%")
        logger.info(f"Electric/heat pump properties: {electric_count:,} / {len(df):,}")

        self.results['electrification'] = {
            'electrification_rate': electrification_rate,
            'electric_properties': int(electric_count),
            'total_properties': len(df)
        }

        return electrification_rate

    def analyze_by_geography(
        self,
        df: pd.DataFrame,
        level: str = 'national',
        geography_col: Optional[str] = None
    ) -> pd.DataFrame:
        """
        Analyze fuel mix by geographic level.

        Args:
            df: EPC DataFrame with fuel_category column
            level: Geographic level ('national', 'regional', 'local_authority')
            geography_col: Column name for geography (e.g., 'region_name', 'local_authority_name')

        Returns:
            DataFrame with fuel mix by geography
        """
        logger.info(f"Analyzing fuel mix by {level}...")

        if 'fuel_category' not in df.columns:
            logger.error("Run analyze_fuel_mix() first to categorize fuels")
            return pd.DataFrame()

        if level == 'national':
            # National summary
            fuel_mix = df['fuel_category'].value_counts(normalize=True) * 100
            result_df = pd.DataFrame({
                'geography': ['England and Wales'],
                'geography_level': ['National'],
                **{fuel: [fuel_mix.get(fuel, 0)] for fuel in self.FUEL_CATEGORIES.keys()}
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
                logger.info("Please enrich data with geographic information first")
                return pd.DataFrame()

            # Group and calculate percentages
            fuel_by_geo = pd.crosstab(
                df[geography_col],
                df['fuel_category'],
                normalize='index'
            ) * 100

            # Add counts
            total_counts = df.groupby(geography_col).size()
            fuel_by_geo['total_properties'] = total_counts

            # Reset index
            fuel_by_geo = fuel_by_geo.reset_index()
            fuel_by_geo.rename(columns={geography_col: 'geography'}, inplace=True)
            fuel_by_geo['geography_level'] = level

            logger.info(f"Fuel mix calculated for {len(fuel_by_geo)} {level} areas")

            return fuel_by_geo

    def identify_fuel_switching_opportunities(self, df: pd.DataFrame) -> Dict:
        """
        Identify properties with good potential for fuel switching.

        Focuses on:
        - Off-gas properties (priority for heat pumps)
        - Oil/LPG properties (expensive fuels, good candidates)
        - Properties with good fabric (EPC C+)

        Args:
            df: EPC DataFrame

        Returns:
            Dictionary with fuel switching opportunity statistics
        """
        logger.info("Identifying fuel switching opportunities...")

        if 'fuel_category' not in df.columns:
            logger.error("Run analyze_fuel_mix() first")
            return {}

        # Priority 1: Off-gas with good fabric (EPC C or better)
        if 'CURRENT_ENERGY_RATING' in df.columns:
            priority_1 = df[
                (df['fuel_category'].isin(['oil', 'lpg', 'coal'])) &
                (df['CURRENT_ENERGY_RATING'].isin(['A', 'B', 'C']))
            ]
            logger.info(f"Priority 1 (off-gas + good fabric): {len(priority_1):,} properties")
        else:
            priority_1 = pd.DataFrame()

        # Priority 2: All off-gas
        priority_2 = df[df['fuel_category'].isin(['oil', 'lpg', 'coal'])]
        logger.info(f"Priority 2 (all off-gas): {len(priority_2):,} properties")

        # Priority 3: Mains gas with excellent fabric (EPC A/B)
        if 'CURRENT_ENERGY_RATING' in df.columns:
            priority_3 = df[
                (df['fuel_category'] == 'mains_gas') &
                (df['CURRENT_ENERGY_RATING'].isin(['A', 'B']))
            ]
            logger.info(f"Priority 3 (gas + excellent fabric): {len(priority_3):,} properties")
        else:
            priority_3 = pd.DataFrame()

        results = {
            'priority_1_count': len(priority_1),
            'priority_1_pct': len(priority_1) / len(df) * 100 if len(df) > 0 else 0,
            'priority_2_count': len(priority_2),
            'priority_2_pct': len(priority_2) / len(df) * 100 if len(df) > 0 else 0,
            'priority_3_count': len(priority_3),
            'priority_3_pct': len(priority_3) / len(df) * 100 if len(df) > 0 else 0,
        }

        self.results['fuel_switching_opportunities'] = results
        return results

    def save_results(self, output_path: Optional[Path] = None):
        """
        Save analysis results to file.

        Args:
            output_path: Path to save results (default: DATA_OUTPUTS_DIR)
        """
        if output_path is None:
            output_path = DATA_OUTPUTS_DIR / "heating_fuel_analysis_results.txt"

        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write("HEATING FUEL MIX ANALYSIS RESULTS\n")
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
    """Main execution function for heating fuel analysis."""
    logger.info("Starting heating fuel analysis...")

    # Load data
    from config.config import DATA_PROCESSED_DIR
    input_file = DATA_PROCESSED_DIR / "epc_london_validated.csv"

    if not input_file.exists():
        logger.error(f"Input file not found: {input_file}")
        return

    logger.info(f"Loading data from: {input_file}")
    df = pd.read_csv(input_file, low_memory=False)

    # Perform analysis
    analyzer = HeatingFuelAnalyzer()
    analyzer.analyze_fuel_mix(df)
    analyzer.identify_off_gas_properties(df)
    analyzer.calculate_electrification_rate(df)
    analyzer.identify_fuel_switching_opportunities(df)

    # Save results
    analyzer.save_results()

    logger.info("Heating fuel analysis complete!")


if __name__ == "__main__":
    main()
