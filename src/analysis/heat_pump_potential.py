"""
Heat Pump Potential Analysis Module

Assesses the suitability of properties for heat pump installation.
Key ADE policy metric for understanding heat pump deployment potential.

Provides:
- Suitability assessment based on fabric and heat demand
- Barrier analysis (insulation, heat demand, property type)
- Geographic breakdown of potential
- Priority targeting for heat pump rollout
"""

import pandas as pd
import numpy as np
from pathlib import Path
from typing import Dict, List, Optional
from loguru import logger

import sys
sys.path.append(str(Path(__file__).parent.parent.parent))
from config.config import load_config, DATA_OUTPUTS_DIR


class HeatPumpPotentialAnalyzer:
    """
    Analyzes heat pump deployment potential across the building stock.

    Categorizes properties by readiness and identifies barriers to overcome.
    """

    # Suitability tiers
    SUITABILITY_TIERS = {
        1: "Ready now (good fabric, low heat demand)",
        2: "Ready with minor improvements (loft insulation top-up)",
        3: "Requires moderate fabric work (wall insulation needed)",
        4: "Requires major fabric work (solid wall insulation)",
        5: "Challenging (very high heat demand, multiple barriers)"
    }

    def __init__(self):
        """Initialize the heat pump potential analyzer."""
        self.config = load_config()
        self.policy_config = self.config.get('policy_metrics', {}).get('heat_pump', {})
        self.results = {}
        logger.info("Initialized Heat Pump Potential Analyzer")

    def assess_suitability(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Assess heat pump suitability for each property.

        Criteria:
        - EPC rating (D+ preferred)
        - Wall insulation status
        - Loft insulation
        - Heat demand (kWh/m²/year)

        Args:
            df: EPC DataFrame

        Returns:
            DataFrame with suitability tier added
        """
        logger.info(f"Assessing heat pump suitability for {len(df):,} properties...")

        df_assessed = df.copy()

        # Initialize tier column
        df_assessed['hp_suitability_tier'] = 5  # Default: challenging
        df_assessed['hp_barriers'] = ''
        df_assessed['hp_fabric_cost_estimate'] = 0

        # Get config thresholds
        min_epc = self.policy_config.get('min_epc_for_direct_install', 'D')
        max_heat_demand = self.policy_config.get('max_heat_demand_kwh_m2', 150)

        # Tier 1: Ready now
        # Good EPC (C+), decent heat demand
        tier_1_mask = (
            (df_assessed['CURRENT_ENERGY_RATING'].isin(['A', 'B', 'C'])) &
            (df_assessed.get('ENERGY_CONSUMPTION_CURRENT', 999) < max_heat_demand)
        )
        df_assessed.loc[tier_1_mask, 'hp_suitability_tier'] = 1
        df_assessed.loc[tier_1_mask, 'hp_barriers'] = 'None - ready for installation'

        # Tier 2: Minor improvements needed
        # EPC D, may need loft top-up
        tier_2_mask = (
            (df_assessed['CURRENT_ENERGY_RATING'] == 'D') &
            (~tier_1_mask)
        )
        df_assessed.loc[tier_2_mask, 'hp_suitability_tier'] = 2
        df_assessed.loc[tier_2_mask, 'hp_barriers'] = 'Minor - loft insulation top-up recommended'
        df_assessed.loc[tier_2_mask, 'hp_fabric_cost_estimate'] = 1200  # Loft top-up cost

        # Tier 3: Moderate work (cavity wall insulation)
        # EPC E, likely cavity walls
        tier_3_mask = (
            (df_assessed['CURRENT_ENERGY_RATING'] == 'E') &
            (~tier_1_mask) &
            (~tier_2_mask)
        )
        df_assessed.loc[tier_3_mask, 'hp_suitability_tier'] = 3
        df_assessed.loc[tier_3_mask, 'hp_barriers'] = 'Moderate - wall and loft insulation needed'
        df_assessed.loc[tier_3_mask, 'hp_fabric_cost_estimate'] = 4000  # Cavity wall + loft

        # Tier 4: Major work (solid wall insulation)
        # EPC F, likely solid walls
        tier_4_mask = (
            (df_assessed['CURRENT_ENERGY_RATING'] == 'F') &
            (~tier_1_mask) &
            (~tier_2_mask) &
            (~tier_3_mask)
        )
        df_assessed.loc[tier_4_mask, 'hp_suitability_tier'] = 4
        df_assessed.loc[tier_4_mask, 'hp_barriers'] = 'Major - solid wall insulation required'
        df_assessed.loc[tier_4_mask, 'hp_fabric_cost_estimate'] = 12000  # SWI + loft

        # Tier 5: Challenging (EPC G or very high demand)
        tier_5_mask = (
            (df_assessed['CURRENT_ENERGY_RATING'] == 'G') |
            (df_assessed.get('ENERGY_CONSUMPTION_CURRENT', 0) > max_heat_demand * 1.5)
        )
        df_assessed.loc[tier_5_mask, 'hp_suitability_tier'] = 5
        df_assessed.loc[tier_5_mask, 'hp_barriers'] = 'Challenging - extensive fabric upgrade needed'
        df_assessed.loc[tier_5_mask, 'hp_fabric_cost_estimate'] = 15000  # Extensive work

        # Log summary
        tier_distribution = df_assessed['hp_suitability_tier'].value_counts().sort_index()
        logger.info("Heat Pump Suitability Distribution:")
        for tier, count in tier_distribution.items():
            pct = count / len(df_assessed) * 100
            logger.info(f"  Tier {tier} ({self.SUITABILITY_TIERS[tier]}): {count:,} ({pct:.1f}%)")

        return df_assessed

    def categorize_barriers(self, df: pd.DataFrame) -> Dict:
        """
        Categorize barriers to heat pump installation.

        Args:
            df: DataFrame with hp_suitability_tier column

        Returns:
            Dictionary with barrier statistics
        """
        logger.info("Analyzing barriers to heat pump installation...")

        if 'hp_suitability_tier' not in df.columns:
            logger.error("Run assess_suitability() first")
            return {}

        # Count by tier
        tier_counts = df['hp_suitability_tier'].value_counts().sort_index()
        tier_percentages = df['hp_suitability_tier'].value_counts(normalize=True).sort_index() * 100

        # Specific barriers
        barriers = {
            'poor_fabric': len(df[df['hp_suitability_tier'] >= 3]),
            'very_poor_fabric': len(df[df['hp_suitability_tier'] >= 4]),
            'ready_or_minor_work': len(df[df['hp_suitability_tier'] <= 2]),
        }

        # Average fabric cost
        avg_fabric_cost = df['hp_fabric_cost_estimate'].mean()
        total_fabric_cost = df['hp_fabric_cost_estimate'].sum()

        results = {
            'tier_counts': tier_counts.to_dict(),
            'tier_percentages': tier_percentages.to_dict(),
            'barriers': barriers,
            'avg_fabric_cost_per_property': float(avg_fabric_cost),
            'total_fabric_investment_needed': float(total_fabric_cost),
        }

        logger.info(f"Properties ready or needing minor work: {barriers['ready_or_minor_work']:,} ({barriers['ready_or_minor_work']/len(df)*100:.1f}%)")
        logger.info(f"Average fabric cost per property: £{avg_fabric_cost:,.0f}")
        logger.info(f"Total fabric investment needed: £{total_fabric_cost/1e9:.2f}B")

        self.results['barriers'] = results
        return results

    def calculate_potential_by_geography(
        self,
        df: pd.DataFrame,
        level: str = 'national',
        geography_col: Optional[str] = None
    ) -> pd.DataFrame:
        """
        Calculate heat pump potential by geographic area.

        Args:
            df: DataFrame with hp_suitability_tier column
            level: Geographic level ('national', 'regional', 'local_authority')
            geography_col: Column name for geography

        Returns:
            DataFrame with geographic breakdown
        """
        logger.info(f"Calculating heat pump potential by {level}...")

        if 'hp_suitability_tier' not in df.columns:
            logger.error("Run assess_suitability() first")
            return pd.DataFrame()

        if level == 'national':
            # National summary
            tier_counts = df['hp_suitability_tier'].value_counts().sort_index()
            total = len(df)

            result_df = pd.DataFrame({
                'geography': ['England and Wales'],
                'total_properties': [total],
                'tier_1_ready': [tier_counts.get(1, 0)],
                'tier_2_minor': [tier_counts.get(2, 0)],
                'tier_3_moderate': [tier_counts.get(3, 0)],
                'tier_4_major': [tier_counts.get(4, 0)],
                'tier_5_challenging': [tier_counts.get(5, 0)],
                'pct_ready_or_minor': [(tier_counts.get(1, 0) + tier_counts.get(2, 0)) / total * 100],
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

            # Group and calculate
            geo_summary = []

            for geo_area in df[geography_col].unique():
                if pd.isna(geo_area):
                    continue

                area_df = df[df[geography_col] == geo_area]
                tier_counts = area_df['hp_suitability_tier'].value_counts()
                total = len(area_df)

                geo_summary.append({
                    'geography': geo_area,
                    'total_properties': total,
                    'tier_1_ready': tier_counts.get(1, 0),
                    'tier_2_minor': tier_counts.get(2, 0),
                    'tier_3_moderate': tier_counts.get(3, 0),
                    'tier_4_major': tier_counts.get(4, 0),
                    'tier_5_challenging': tier_counts.get(5, 0),
                    'pct_ready_or_minor': (tier_counts.get(1, 0) + tier_counts.get(2, 0)) / total * 100 if total > 0 else 0,
                })

            result_df = pd.DataFrame(geo_summary)
            result_df['geography_level'] = level

            logger.info(f"Calculated potential for {len(result_df)} {level} areas")

            return result_df

    def identify_priority_areas(
        self,
        df: pd.DataFrame,
        geography_col: str = 'local_authority_name',
        min_ready_pct: float = 30.0
    ) -> pd.DataFrame:
        """
        Identify geographic areas with high heat pump readiness.

        Args:
            df: DataFrame with hp_suitability_tier and geography
            geography_col: Geography column to use
            min_ready_pct: Minimum percentage of ready/minor work properties

        Returns:
            DataFrame of priority areas
        """
        logger.info("Identifying priority areas for heat pump rollout...")

        if geography_col not in df.columns:
            logger.error(f"Geography column not found: {geography_col}")
            return pd.DataFrame()

        # Calculate readiness by area
        geo_summary = self.calculate_potential_by_geography(
            df,
            level='local_authority',
            geography_col=geography_col
        )

        # Filter to priority areas
        priority_areas = geo_summary[geo_summary['pct_ready_or_minor'] >= min_ready_pct].copy()
        priority_areas = priority_areas.sort_values('pct_ready_or_minor', ascending=False)

        logger.info(f"Found {len(priority_areas)} priority areas (>{min_ready_pct}% ready)")

        if len(priority_areas) > 0:
            logger.info("Top 5 priority areas:")
            for idx, row in priority_areas.head(5).iterrows():
                logger.info(f"  {row['geography']}: {row['pct_ready_or_minor']:.1f}% ready ({row['total_properties']:,} properties)")

        return priority_areas

    def save_results(self, output_path: Optional[Path] = None):
        """
        Save analysis results to file.

        Args:
            output_path: Path to save results
        """
        if output_path is None:
            output_path = DATA_OUTPUTS_DIR / "heat_pump_potential_results.txt"

        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write("HEAT PUMP POTENTIAL ANALYSIS RESULTS\n")
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
    """Main execution function for heat pump potential analysis."""
    logger.info("Starting heat pump potential analysis...")

    # Load data
    from config.config import DATA_PROCESSED_DIR
    input_file = DATA_PROCESSED_DIR / "epc_london_validated.csv"

    if not input_file.exists():
        logger.error(f"Input file not found: {input_file}")
        return

    logger.info(f"Loading data from: {input_file}")
    df = pd.read_csv(input_file, low_memory=False)

    # Perform analysis
    analyzer = HeatPumpPotentialAnalyzer()
    df_assessed = analyzer.assess_suitability(df)
    analyzer.categorize_barriers(df_assessed)

    # Save results
    analyzer.save_results()

    # Save assessed data
    output_file = DATA_PROCESSED_DIR / "epc_with_hp_assessment.csv"
    df_assessed.to_csv(output_file, index=False)
    logger.info(f"Assessed data saved to: {output_file}")

    logger.info("Heat pump potential analysis complete!")


if __name__ == "__main__":
    main()
