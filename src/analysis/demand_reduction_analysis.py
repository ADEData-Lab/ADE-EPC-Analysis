"""
Demand Reduction Analysis Module

Analyzes fabric improvement potential and demand reduction opportunities.
Key ADE policy metric for understanding energy efficiency potential.

Provides:
- Fabric improvement needs (wall, loft, floor, windows)
- Energy savings potential
- EPC band improvement potential
- Path to EPC C analysis
- Cost-benefit of fabric improvements
"""

import pandas as pd
import numpy as np
from pathlib import Path
from typing import Dict, List, Optional
from loguru import logger

import sys
sys.path.append(str(Path(__file__).parent.parent.parent))
from config.config import load_config, DATA_OUTPUTS_DIR


class DemandReductionAnalyzer:
    """
    Analyzes demand reduction potential through fabric improvements.

    Focuses on path to EPC C (national target) and heat demand reduction.
    """

    # EPC band hierarchy
    EPC_BANDS = ['G', 'F', 'E', 'D', 'C', 'B', 'A']

    # National housing stock estimates (England & Wales, 2023)
    NATIONAL_HOUSING_STOCK = 24_000_000  # ~24 million homes
    NATIONAL_SOLID_WALL_HOMES = 8_000_000  # ~8 million solid wall homes
    NATIONAL_CAVITY_WALL_HOMES = 14_000_000  # ~14 million cavity wall homes

    # Typical fabric improvements and savings
    FABRIC_MEASURES = {
        'loft_insulation': {
            'cost': 1200,
            'heat_saving_pct': 0.15,  # 15% reduction
            'applicability': 'properties with loft access'
        },
        'cavity_wall_insulation': {
            'cost': 2500,
            'heat_saving_pct': 0.20,  # 20% reduction
            'applicability': 'cavity wall properties'
        },
        'solid_wall_insulation': {
            'cost': 10000,
            'heat_saving_pct': 0.30,  # 30% reduction
            'applicability': 'solid wall properties'
        },
        'floor_insulation': {
            'cost': 1500,
            'heat_saving_pct': 0.05,  # 5% reduction
            'applicability': 'suspended timber floors'
        },
        'double_glazing': {
            'cost': 6000,
            'heat_saving_pct': 0.10,  # 10% reduction
            'applicability': 'single glazed properties'
        },
        'draught_proofing': {
            'cost': 500,
            'heat_saving_pct': 0.05,  # 5% reduction
            'applicability': 'all properties'
        }
    }

    def __init__(self):
        """Initialize the demand reduction analyzer."""
        self.config = load_config()
        self.policy_config = self.config.get('policy_metrics', {}).get('demand_reduction', {})
        self.target_epc = self.policy_config.get('target_epc_band', 'C')
        self.results = {}
        logger.info("Initialized Demand Reduction Analyzer")
        logger.info(f"Target EPC band: {self.target_epc}")

    def analyze_fabric_potential(self, df: pd.DataFrame) -> Dict:
        """
        Analyze fabric improvement needs across the stock.

        Args:
            df: EPC DataFrame

        Returns:
            Dictionary with fabric improvement statistics
        """
        logger.info(f"Analyzing fabric improvement potential for {len(df):,} properties...")

        fabric_stats = {
            'total_properties': len(df),
            'needs_improvement': {},
            'measure_applicability': {}
        }

        # Loft insulation needs
        if 'ROOF_DESCRIPTION' in df.columns:
            # Properties with inadequate loft insulation (<270mm)
            needs_loft = df['ROOF_DESCRIPTION'].str.contains(
                'no insulation|<100mm|100mm|150mm|200mm',
                case=False,
                na=False,
                regex=True
            )
            fabric_stats['needs_improvement']['loft'] = int(needs_loft.sum())
            logger.info(f"Need loft insulation: {needs_loft.sum():,} ({needs_loft.sum()/len(df)*100:.1f}%)")

        # Wall insulation needs
        if 'wall_type' in df.columns and 'wall_insulated' in df.columns:
            # Uninsulated walls
            needs_wall = ~df['wall_insulated']
            fabric_stats['needs_improvement']['wall'] = int(needs_wall.sum())
            logger.info(f"Need wall insulation: {needs_wall.sum():,} ({needs_wall.sum()/len(df)*100:.1f}%)")

            # Breakdown by wall type
            if 'wall_type' in df.columns:
                wall_breakdown = df[needs_wall]['wall_type'].value_counts()
                fabric_stats['wall_insulation_by_type'] = wall_breakdown.to_dict()

        # Glazing needs
        if 'WINDOWS_DESCRIPTION' in df.columns:
            # Single glazed properties
            needs_glazing = df['WINDOWS_DESCRIPTION'].str.contains(
                'single',
                case=False,
                na=False
            )
            fabric_stats['needs_improvement']['glazing'] = int(needs_glazing.sum())
            logger.info(f"Need glazing upgrade: {needs_glazing.sum():,} ({needs_glazing.sum()/len(df)*100:.1f}%)")

        # Floor insulation needs
        if 'FLOOR_DESCRIPTION' in df.columns:
            # Uninsulated floors
            needs_floor = ~df['FLOOR_DESCRIPTION'].str.contains(
                'insulated',
                case=False,
                na=False
            )
            fabric_stats['needs_improvement']['floor'] = int(needs_floor.sum())

        self.results['fabric_potential'] = fabric_stats
        return fabric_stats

    def calculate_savings_potential(self, df: pd.DataFrame) -> Dict:
        """
        Calculate energy and cost savings potential from fabric improvements.

        Args:
            df: EPC DataFrame

        Returns:
            Dictionary with savings potential
        """
        logger.info("Calculating savings potential from fabric improvements...")

        savings = {
            'current_total_demand_gwh': 0,
            'post_improvement_demand_gwh': 0,
            'total_savings_gwh': 0,
            'total_co2_savings_kt': 0,
            'total_bill_savings_m': 0,
            'by_measure': {}
        }

        # Calculate current heat demand
        if 'ENERGY_CONSUMPTION_CURRENT' in df.columns:
            current_demand = df['ENERGY_CONSUMPTION_CURRENT'].sum() / 1e6  # GWh
        elif 'TOTAL_FLOOR_AREA' in df.columns:
            # Estimate from floor area
            current_demand = (df['TOTAL_FLOOR_AREA'] * 100).sum() / 1e6  # GWh
        else:
            logger.warning("No energy consumption data available")
            current_demand = 0

        savings['current_total_demand_gwh'] = float(current_demand)

        # Estimate savings from each measure
        # This is a simplified calculation - real savings depend on property specifics

        # Assume 50% of properties need loft top-up
        loft_applicable = len(df) * 0.5
        loft_savings_gwh = (
            loft_applicable *
            (current_demand / len(df)) *  # Average demand per property
            self.FABRIC_MEASURES['loft_insulation']['heat_saving_pct']
        )

        # Assume 30% of properties need wall insulation (mix of cavity and solid)
        wall_applicable = len(df) * 0.3
        wall_savings_gwh = (
            wall_applicable *
            (current_demand / len(df)) *
            0.25  # Average of cavity and solid wall savings
        )

        # Assume 20% need double glazing
        glazing_applicable = len(df) * 0.2
        glazing_savings_gwh = (
            glazing_applicable *
            (current_demand / len(df)) *
            self.FABRIC_MEASURES['double_glazing']['heat_saving_pct']
        )

        total_potential_savings_gwh = loft_savings_gwh + wall_savings_gwh + glazing_savings_gwh

        savings['total_savings_gwh'] = float(total_potential_savings_gwh)
        savings['post_improvement_demand_gwh'] = float(current_demand - total_potential_savings_gwh)
        savings['pct_reduction'] = float(total_potential_savings_gwh / current_demand * 100) if current_demand > 0 else 0

        # CO2 savings (assuming gas heating, 0.183 kgCO2/kWh)
        savings['total_co2_savings_kt'] = float(total_potential_savings_gwh * 0.183)

        # Bill savings (assuming £0.0624/kWh gas price)
        savings['total_bill_savings_m'] = float(total_potential_savings_gwh * 1e6 * 0.0624 / 1e6)

        logger.info(f"Current heat demand: {current_demand:.1f} GWh/year")
        logger.info(f"Potential savings: {total_potential_savings_gwh:.1f} GWh/year ({savings['pct_reduction']:.1f}%)")
        logger.info(f"CO2 savings: {savings['total_co2_savings_kt']:.0f} kt/year")
        logger.info(f"Bill savings: £{savings['total_bill_savings_m']:.1f}M/year")

        self.results['savings_potential'] = savings
        return savings

    def analyze_path_to_epc_c(self, df: pd.DataFrame) -> Dict:
        """
        Analyze the path to EPC C for all properties.

        Args:
            df: EPC DataFrame with CURRENT_ENERGY_RATING

        Returns:
            Dictionary with EPC C pathway statistics
        """
        logger.info(f"Analyzing path to EPC {self.target_epc}...")

        if 'CURRENT_ENERGY_RATING' not in df.columns:
            logger.error("CURRENT_ENERGY_RATING column not found")
            return {}

        # Current distribution
        current_dist = df['CURRENT_ENERGY_RATING'].value_counts()

        # Properties already at target or better
        better_bands = self.EPC_BANDS[self.EPC_BANDS.index(self.target_epc):]
        already_compliant = df['CURRENT_ENERGY_RATING'].isin(better_bands)

        # Properties needing improvement
        needs_improvement = ~already_compliant

        # Categorize by improvement needed
        improvement_needed = {
            'already_compliant': int(already_compliant.sum()),
            'one_band': int((df['CURRENT_ENERGY_RATING'] == 'D').sum()),
            'two_bands': int((df['CURRENT_ENERGY_RATING'] == 'E').sum()),
            'three_plus_bands': int((df['CURRENT_ENERGY_RATING'].isin(['F', 'G'])).sum())
        }

        # Estimate costs to reach EPC C
        # Very rough estimates based on typical improvement costs
        cost_estimates = {
            'one_band': 3000,      # D→C: loft + minor improvements
            'two_bands': 8000,     # E→C: loft + wall insulation
            'three_plus_bands': 15000  # F/G→C: comprehensive fabric upgrade
        }

        total_cost_bn = (
            improvement_needed['one_band'] * cost_estimates['one_band'] +
            improvement_needed['two_bands'] * cost_estimates['two_bands'] +
            improvement_needed['three_plus_bands'] * cost_estimates['three_plus_bands']
        ) / 1e9

        results = {
            'target_band': self.target_epc,
            'total_properties': len(df),
            'already_compliant': improvement_needed['already_compliant'],
            'pct_compliant': float(improvement_needed['already_compliant'] / len(df) * 100),
            'needs_improvement': int(needs_improvement.sum()),
            'improvement_breakdown': improvement_needed,
            'estimated_total_cost_bn': float(total_cost_bn),
            'avg_cost_per_property': float(total_cost_bn * 1e9 / needs_improvement.sum()) if needs_improvement.sum() > 0 else 0
        }

        logger.info(f"Already EPC {self.target_epc}+: {results['already_compliant']:,} ({results['pct_compliant']:.1f}%)")
        logger.info(f"Need improvement: {results['needs_improvement']:,}")
        logger.info(f"  One band (D→C): {improvement_needed['one_band']:,}")
        logger.info(f"  Two bands (E→C): {improvement_needed['two_bands']:,}")
        logger.info(f"  Three+ bands (F/G→C): {improvement_needed['three_plus_bands']:,}")
        logger.info(f"Estimated total cost: £{total_cost_bn:.2f}B")

        self.results['path_to_epc_c'] = results
        return results

    def calculate_national_investment(self, df: pd.DataFrame) -> Dict:
        """
        Calculate national-scale investment estimates for fabric retrofit.

        Extrapolates from our dataset to the full England & Wales housing stock.
        Aligned with ADE's emphasis on quantifying the scale of the retrofit challenge.

        Args:
            df: EPC DataFrame

        Returns:
            Dictionary with national investment estimates
        """
        logger.info("Calculating national retrofit investment estimates...")

        total_properties = len(df)
        results = {
            'sample_size': total_properties,
            'national_stock_estimate': self.NATIONAL_HOUSING_STOCK,
            'measures': {}
        }

        # Cost assumptions
        costs = self.config.get('costs', {})
        loft_cost = costs.get('loft_insulation_topup', 1200)
        cavity_cost = costs.get('cavity_wall_insulation', 2500)
        solid_ewi_cost = costs.get('solid_wall_insulation_ewi', 10000)
        solid_iwi_cost = costs.get('solid_wall_insulation_iwi', 14000)
        glazing_cost = costs.get('double_glazing_upgrade', 6000)
        floor_cost = costs.get('floor_insulation', 1500)

        # Loft insulation
        if 'needs_improvement' in self.results.get('fabric_potential', {}):
            loft_count = self.results['fabric_potential']['needs_improvement'].get('loft', 0)
            loft_pct = loft_count / total_properties if total_properties > 0 else 0
            national_loft = int(self.NATIONAL_HOUSING_STOCK * loft_pct)
            loft_investment = national_loft * loft_cost / 1e9

            results['measures']['loft_insulation'] = {
                'sample_count': loft_count,
                'sample_percent': round(loft_pct * 100, 1),
                'national_estimate': national_loft,
                'cost_per_home': loft_cost,
                'total_investment_bn': round(loft_investment, 1)
            }
            logger.info(f"Loft insulation: {national_loft:,} homes, £{loft_investment:.1f}B")

        # Wall insulation (from fabric potential)
        wall_count = self.results.get('fabric_potential', {}).get('needs_improvement', {}).get('wall', 0)
        wall_by_type = self.results.get('fabric_potential', {}).get('wall_insulation_by_type', {})

        if wall_count > 0 or wall_by_type:
            # Use wall type breakdown if available
            solid_count = sum(v for k, v in wall_by_type.items()
                            if 'solid' in k.lower() or 'stone' in k.lower())
            cavity_count = wall_by_type.get('cavity', 0)
            other_count = wall_count - solid_count - cavity_count if wall_count > 0 else 0

            # If no breakdown, estimate 60% solid, 30% cavity based on national averages
            if solid_count == 0 and cavity_count == 0 and wall_count > 0:
                solid_count = int(wall_count * 0.60)
                cavity_count = int(wall_count * 0.30)
                other_count = wall_count - solid_count - cavity_count

            wall_pct = wall_count / total_properties if total_properties > 0 else 0
            solid_pct = solid_count / total_properties if total_properties > 0 else 0
            cavity_pct = cavity_count / total_properties if total_properties > 0 else 0

            # National estimates
            national_solid = int(self.NATIONAL_HOUSING_STOCK * solid_pct)
            national_cavity = int(self.NATIONAL_HOUSING_STOCK * cavity_pct)

            # Average solid wall cost (80% EWI, 20% IWI)
            avg_solid_cost = solid_ewi_cost * 0.8 + solid_iwi_cost * 0.2

            solid_investment = national_solid * avg_solid_cost / 1e9
            cavity_investment = national_cavity * cavity_cost / 1e9

            results['measures']['solid_wall_insulation'] = {
                'sample_count': solid_count,
                'sample_percent': round(solid_pct * 100, 1),
                'national_estimate': national_solid,
                'cost_per_home_ewi': solid_ewi_cost,
                'cost_per_home_iwi': solid_iwi_cost,
                'total_investment_bn': round(solid_investment, 1)
            }

            results['measures']['cavity_wall_insulation'] = {
                'sample_count': cavity_count,
                'sample_percent': round(cavity_pct * 100, 1),
                'national_estimate': national_cavity,
                'cost_per_home': cavity_cost,
                'total_investment_bn': round(cavity_investment, 1)
            }

            logger.info(f"Solid wall insulation: {national_solid:,} homes, £{solid_investment:.1f}B")
            logger.info(f"Cavity wall insulation: {national_cavity:,} homes, £{cavity_investment:.1f}B")

        # Glazing
        glazing_count = self.results.get('fabric_potential', {}).get('needs_improvement', {}).get('glazing', 0)
        if glazing_count > 0:
            glazing_pct = glazing_count / total_properties
            national_glazing = int(self.NATIONAL_HOUSING_STOCK * glazing_pct)
            glazing_investment = national_glazing * glazing_cost / 1e9

            results['measures']['double_glazing'] = {
                'sample_count': glazing_count,
                'sample_percent': round(glazing_pct * 100, 1),
                'national_estimate': national_glazing,
                'cost_per_home': glazing_cost,
                'total_investment_bn': round(glazing_investment, 1)
            }
            logger.info(f"Double glazing: {national_glazing:,} homes, £{glazing_investment:.1f}B")

        # Floor insulation
        floor_count = self.results.get('fabric_potential', {}).get('needs_improvement', {}).get('floor', 0)
        if floor_count > 0:
            floor_pct = floor_count / total_properties
            # Only ~40% of homes have suspended timber floors (applicable for insulation)
            applicable_pct = min(floor_pct, 0.40)
            national_floor = int(self.NATIONAL_HOUSING_STOCK * applicable_pct)
            floor_investment = national_floor * floor_cost / 1e9

            results['measures']['floor_insulation'] = {
                'sample_count': floor_count,
                'sample_percent': round(floor_pct * 100, 1),
                'national_estimate': national_floor,
                'cost_per_home': floor_cost,
                'total_investment_bn': round(floor_investment, 1),
                'note': 'Limited to ~40% homes with suspended timber floors'
            }

        # Total investment
        total_investment = sum(
            m.get('total_investment_bn', 0)
            for m in results['measures'].values()
        )
        results['total_fabric_investment_bn'] = round(total_investment, 1)

        # Jobs estimate (from ADE: 200k jobs by 2030, ~12 jobs per £1M invested)
        jobs_per_bn = 12000  # 12 jobs per £1M = 12,000 per £1B
        results['estimated_jobs'] = int(total_investment * jobs_per_bn)
        results['ade_jobs_target_2030'] = 200000

        logger.info(f"TOTAL FABRIC INVESTMENT NEEDED: £{total_investment:.0f}B")
        logger.info(f"Estimated jobs potential: {results['estimated_jobs']:,}")

        self.results['national_investment'] = results
        return results

    def prioritize_improvements(
        self,
        df: pd.DataFrame,
        geography_col: str = 'local_authority_name'
    ) -> pd.DataFrame:
        """
        Prioritize properties for fabric improvements.

        Priority based on:
        1. Current EPC rating (worst first)
        2. Geographic area (for targeting)
        3. Cost-effectiveness

        Args:
            df: EPC DataFrame
            geography_col: Geography column for grouping

        Returns:
            DataFrame with priorities
        """
        logger.info("Prioritizing properties for fabric improvements...")

        df_priority = df.copy()

        # Assign priority score (lower is higher priority)
        epc_score = {
            'G': 1, 'F': 2, 'E': 3, 'D': 4, 'C': 5, 'B': 6, 'A': 7
        }
        df_priority['epc_score'] = df_priority['CURRENT_ENERGY_RATING'].map(epc_score)

        # Geographic grouping
        if geography_col in df.columns:
            geo_summary = df_priority.groupby(geography_col).agg({
                'epc_score': 'mean',
                geography_col: 'count'
            }).rename(columns={geography_col: 'property_count'})

            geo_summary = geo_summary.sort_values('epc_score')
            logger.info(f"\nTop 10 priority areas for fabric improvements:")
            for geo, row in geo_summary.head(10).iterrows():
                logger.info(f"  {geo}: {row['property_count']:,} properties, avg EPC score {row['epc_score']:.1f}")

            return geo_summary.reset_index()

        else:
            logger.warning(f"Geography column {geography_col} not found")
            return df_priority

    def save_results(self, output_path: Optional[Path] = None):
        """
        Save analysis results to file.

        Args:
            output_path: Path to save results
        """
        if output_path is None:
            output_path = DATA_OUTPUTS_DIR / "demand_reduction_results.txt"

        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write("DEMAND REDUCTION ANALYSIS RESULTS\n")
            f.write("=" * 70 + "\n")
            f.write("Aligned with ADE's focus on fabric-first decarbonisation\n\n")

            # Fabric Potential
            if 'fabric_potential' in self.results:
                fp = self.results['fabric_potential']
                f.write("\nFABRIC IMPROVEMENT NEEDS\n")
                f.write("-" * 70 + "\n")
                f.write(f"Total properties analyzed: {fp['total_properties']:,}\n\n")

                f.write("Properties needing improvements:\n")
                for measure, count in fp.get('needs_improvement', {}).items():
                    pct = count / fp['total_properties'] * 100
                    f.write(f"  {measure.title()}: {count:,} ({pct:.1f}%)\n")

                if 'wall_insulation_by_type' in fp:
                    f.write("\nWall insulation needs by type:\n")
                    for wall_type, count in fp['wall_insulation_by_type'].items():
                        f.write(f"  {wall_type}: {count:,}\n")

            # Savings Potential
            if 'savings_potential' in self.results:
                sp = self.results['savings_potential']
                f.write("\n\nSAVINGS POTENTIAL\n")
                f.write("-" * 70 + "\n")
                f.write(f"Current total demand: {sp['current_total_demand_gwh']:.1f} GWh/year\n")
                f.write(f"Post-improvement demand: {sp['post_improvement_demand_gwh']:.1f} GWh/year\n")
                f.write(f"Total savings: {sp['total_savings_gwh']:.1f} GWh/year ({sp.get('pct_reduction', 0):.1f}%)\n")
                f.write(f"CO2 savings: {sp['total_co2_savings_kt']:.0f} kt/year\n")
                f.write(f"Bill savings: £{sp['total_bill_savings_m']:.1f}M/year\n")

            # Path to EPC C
            if 'path_to_epc_c' in self.results:
                epc = self.results['path_to_epc_c']
                f.write("\n\nPATH TO EPC C\n")
                f.write("-" * 70 + "\n")
                f.write(f"Target: EPC Band {epc['target_band']}\n")
                f.write(f"Already compliant: {epc['already_compliant']:,} ({epc['pct_compliant']:.1f}%)\n")
                f.write(f"Need improvement: {epc['needs_improvement']:,}\n\n")

                f.write("Breakdown by improvement needed:\n")
                breakdown = epc.get('improvement_breakdown', {})
                f.write(f"  One band (D to C): {breakdown.get('one_band', 0):,}\n")
                f.write(f"  Two bands (E to C): {breakdown.get('two_bands', 0):,}\n")
                f.write(f"  Three+ bands (F/G to C): {breakdown.get('three_plus_bands', 0):,}\n\n")

                f.write(f"Estimated total cost: £{epc['estimated_total_cost_bn']:.1f}B\n")
                f.write(f"Average cost per property: £{epc['avg_cost_per_property']:,.0f}\n")

            # National Investment (NEW)
            if 'national_investment' in self.results:
                ni = self.results['national_investment']
                f.write("\n\nNATIONAL RETROFIT INVESTMENT CHALLENGE\n")
                f.write("-" * 70 + "\n")
                f.write(f"Sample analyzed: {ni['sample_size']:,} properties\n")
                f.write(f"National housing stock (E&W): {ni['national_stock_estimate']:,}\n\n")

                f.write("Investment needed by measure:\n")
                for measure_name, measure_data in ni.get('measures', {}).items():
                    f.write(f"\n  {measure_name.replace('_', ' ').title()}:\n")
                    f.write(f"    In sample: {measure_data['sample_count']:,} ({measure_data['sample_percent']:.1f}%)\n")
                    f.write(f"    National estimate: {measure_data['national_estimate']:,}\n")
                    if 'cost_per_home_ewi' in measure_data:
                        f.write(f"    Cost per home: £{measure_data['cost_per_home_ewi']:,} (EWI) / £{measure_data['cost_per_home_iwi']:,} (IWI)\n")
                    elif 'cost_per_home' in measure_data:
                        f.write(f"    Cost per home: £{measure_data['cost_per_home']:,}\n")
                    f.write(f"    Total investment: £{measure_data['total_investment_bn']:.1f}B\n")

                f.write(f"\n{'='*50}\n")
                f.write(f"TOTAL FABRIC INVESTMENT NEEDED: £{ni['total_fabric_investment_bn']:.0f}B\n")
                f.write(f"Estimated job creation potential: {ni['estimated_jobs']:,}\n")
                f.write(f"ADE 2030 jobs target: {ni['ade_jobs_target_2030']:,}\n")
                f.write(f"{'='*50}\n")

        logger.info(f"Results saved to: {output_path}")


def main():
    """Main execution function for demand reduction analysis."""
    logger.info("Starting demand reduction analysis...")

    # Load data
    from config.config import DATA_PROCESSED_DIR
    input_file = DATA_PROCESSED_DIR / "epc_london_validated.csv"

    if not input_file.exists():
        logger.error(f"Input file not found: {input_file}")
        return

    logger.info(f"Loading data from: {input_file}")
    df = pd.read_csv(input_file, low_memory=False)

    # Perform analysis
    analyzer = DemandReductionAnalyzer()
    analyzer.analyze_fabric_potential(df)
    analyzer.calculate_savings_potential(df)
    analyzer.analyze_path_to_epc_c(df)
    priority_areas = analyzer.prioritize_improvements(df)

    # Save results
    analyzer.save_results()

    # Save priority areas
    if priority_areas is not None:
        output_file = DATA_OUTPUTS_DIR / "demand_reduction_priority_areas.csv"
        priority_areas.to_csv(output_file, index=False)
        logger.info(f"Priority areas saved to: {output_file}")

    logger.info("Demand reduction analysis complete!")


if __name__ == "__main__":
    main()
