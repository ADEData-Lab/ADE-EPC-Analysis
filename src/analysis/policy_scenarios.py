"""
Policy Scenario Analysis Module

Analyzes the impact of key policy interventions aligned with ADE's advocacy:
- Energy price rebalancing (shifting levies from electricity to gas)
- 2035 gas boiler phase-out timeline
- Heat pump installation target (600k/year by 2028)
- Heat network zoning policy

Provides evidence-based projections to support ADE's policy recommendations.
"""

import pandas as pd
import numpy as np
from pathlib import Path
from typing import Dict, Optional, List
from loguru import logger
from datetime import datetime

import sys
sys.path.append(str(Path(__file__).parent.parent.parent))
from config.config import load_config, DATA_OUTPUTS_DIR


class PolicyScenarioAnalyzer:
    """
    Analyzes policy scenarios for heat decarbonisation.

    Aligned with ADE's key policy asks:
    - Price rebalancing to achieve running cost parity
    - Ambitious heat pump deployment targets
    - Clear 2035 gas boiler phase-out pathway
    """

    # Policy targets (from ADE manifesto and government commitments)
    POLICY_TARGETS = {
        'heat_pump_target_2028': 600000,  # per year
        'heat_pump_current_rate': 39000,  # 2023 figure
        'boiler_phaseout_year': 2035,
        'heat_network_target_2040_pct': 20,  # 20% of heat by 2040
        'epc_c_target_year': 2035,  # All homes EPC C by 2035
        'jobs_target_2030': 200000  # Retrofit jobs
    }

    def __init__(self):
        """Initialize the policy scenario analyzer."""
        self.config = load_config()
        self.energy_prices = self.config.get('energy_prices', {})
        self.carbon_factors = self.config.get('carbon_factors', {})
        self.financial = self.config.get('financial', {})
        self.results = {}
        logger.info("Initialized Policy Scenario Analyzer")

    def analyze_price_rebalancing_impact(self, df: pd.DataFrame) -> Dict:
        """
        Analyze the impact of energy price rebalancing on heat pump economics.

        Key ADE policy ask: shift levies from electricity to gas to achieve
        running cost parity between heat pumps and gas boilers by 2030.

        Args:
            df: EPC DataFrame

        Returns:
            Dictionary with price rebalancing analysis
        """
        logger.info("Analyzing price rebalancing impact...")

        # Get average heat demand
        if 'ENERGY_CONSUMPTION_CURRENT' in df.columns:
            avg_demand = df['ENERGY_CONSUMPTION_CURRENT'].mean()
        else:
            avg_demand = 12000  # UK average

        # Heat pump and boiler parameters
        hp_scop = self.config.get('heat_pump', {}).get('scop', 3.0)
        gas_eff = 0.85

        # Price scenarios
        price_scenarios = self.financial.get('price_scenarios', {})

        current = price_scenarios.get('baseline', {})
        rebalanced = price_scenarios.get('rebalanced', {})

        # Current scenario
        current_gas = current.get('gas', 0.0624)
        current_elec = current.get('electricity', 0.26)

        gas_cost_current = (avg_demand / gas_eff) * current_gas
        hp_cost_current = (avg_demand / hp_scop) * current_elec

        # Rebalanced scenario
        rebalanced_gas = rebalanced.get('gas', 0.10)
        rebalanced_elec = rebalanced.get('electricity', 0.15)

        gas_cost_rebalanced = (avg_demand / gas_eff) * rebalanced_gas
        hp_cost_rebalanced = (avg_demand / hp_scop) * rebalanced_elec

        results = {
            'avg_heat_demand_kwh': float(avg_demand),
            'current_prices': {
                'gas_price': current_gas,
                'electricity_price': current_elec,
                'gas_boiler_annual_cost': round(gas_cost_current, 0),
                'heat_pump_annual_cost': round(hp_cost_current, 0),
                'hp_vs_gas_difference': round(hp_cost_current - gas_cost_current, 0),
                'hp_premium_percent': round((hp_cost_current / gas_cost_current - 1) * 100, 1)
            },
            'rebalanced_prices': {
                'gas_price': rebalanced_gas,
                'electricity_price': rebalanced_elec,
                'gas_boiler_annual_cost': round(gas_cost_rebalanced, 0),
                'heat_pump_annual_cost': round(hp_cost_rebalanced, 0),
                'hp_vs_gas_difference': round(hp_cost_rebalanced - gas_cost_rebalanced, 0),
                'hp_saving_percent': round((1 - hp_cost_rebalanced / gas_cost_rebalanced) * 100, 1)
            },
            'policy_impact': {
                'current_hp_premium': round(hp_cost_current - gas_cost_current, 0),
                'rebalanced_hp_saving': round(gas_cost_rebalanced - hp_cost_rebalanced, 0),
                'total_improvement': round(
                    (hp_cost_current - gas_cost_current) - (hp_cost_rebalanced - gas_cost_rebalanced), 0
                )
            }
        }

        logger.info(f"Current prices: HP costs £{results['current_prices']['hp_vs_gas_difference']:+.0f}/yr vs gas")
        logger.info(f"Rebalanced: HP saves £{results['rebalanced_prices']['hp_vs_gas_difference']*-1:.0f}/yr vs gas")

        self.results['price_rebalancing'] = results
        return results

    def project_installation_rates(self, df: pd.DataFrame) -> Dict:
        """
        Project heat pump installation rates needed to meet 2028 target.

        Government target: 600,000 heat pumps installed per year by 2028.
        Current rate: ~39,000 per year (2023).

        Args:
            df: EPC DataFrame

        Returns:
            Dictionary with installation rate projections
        """
        logger.info("Projecting heat pump installation rates...")

        current_year = datetime.now().year
        target_year = 2028

        current_rate = self.POLICY_TARGETS['heat_pump_current_rate']
        target_rate = self.POLICY_TARGETS['heat_pump_target_2028']

        years_remaining = target_year - current_year
        multiplier_needed = target_rate / current_rate

        # Calculate compound annual growth rate needed
        if years_remaining > 0:
            cagr_needed = (target_rate / current_rate) ** (1 / years_remaining) - 1
        else:
            cagr_needed = 0

        # Estimate properties suitable for heat pumps (from our data)
        # Properties at EPC C+ or D are most suitable
        suitable_mask = df['CURRENT_ENERGY_RATING'].isin(['A', 'B', 'C', 'D']) if 'CURRENT_ENERGY_RATING' in df.columns else pd.Series([True] * len(df))
        suitable_properties = suitable_mask.sum()

        # Currently with heat pumps (estimate from fuel analysis)
        existing_hp = 0
        if 'fuel_category' in df.columns:
            existing_hp = (df['fuel_category'] == 'renewable').sum()

        remaining_potential = suitable_properties - existing_hp

        # Years to complete at different rates
        years_at_current = remaining_potential / current_rate if current_rate > 0 else float('inf')
        years_at_target = remaining_potential / target_rate if target_rate > 0 else float('inf')

        results = {
            'current_annual_rate': current_rate,
            'target_annual_rate_2028': target_rate,
            'multiplier_needed': round(multiplier_needed, 1),
            'years_to_target': years_remaining,
            'cagr_needed_percent': round(cagr_needed * 100, 1),
            'uk_ranking_heat_pumps': '21st of 21 (last in Europe)',  # From ADE doc
            'suitable_properties_in_data': int(suitable_properties),
            'existing_heat_pumps_estimate': int(existing_hp),
            'remaining_potential': int(remaining_potential),
            'years_to_complete_at_current_rate': round(years_at_current, 0),
            'years_to_complete_at_target_rate': round(years_at_target, 0)
        }

        logger.info(f"Need {multiplier_needed:.0f}x increase in installation rate")
        logger.info(f"Current: {current_rate:,}/year → Target: {target_rate:,}/year by {target_year}")

        self.results['installation_rates'] = results
        return results

    def analyze_boiler_phaseout_timeline(self, df: pd.DataFrame) -> Dict:
        """
        Analyze implications of 2035 gas boiler phase-out.

        ADE supports legislating a gas boiler phase-out by 2035.
        This analysis projects the scale of conversion needed.

        Args:
            df: EPC DataFrame

        Returns:
            Dictionary with phase-out analysis
        """
        logger.info("Analyzing 2035 boiler phase-out timeline...")

        current_year = datetime.now().year
        phaseout_year = self.POLICY_TARGETS['boiler_phaseout_year']
        years_remaining = phaseout_year - current_year

        # Count gas-heated properties
        total_properties = len(df)
        gas_properties = 0

        if 'fuel_category' in df.columns:
            gas_properties = (df['fuel_category'] == 'mains_gas').sum()
        elif 'MAINS_GAS_FLAG' in df.columns:
            gas_properties = (df['MAINS_GAS_FLAG'] == 'Y').sum()
        else:
            # Estimate 82% on gas
            gas_properties = int(total_properties * 0.82)

        # Properties already with low-carbon heating
        low_carbon = 0
        if 'fuel_category' in df.columns:
            low_carbon = df['fuel_category'].isin(['electric', 'renewable', 'heat_network']).sum()

        # Conversion rate needed
        if years_remaining > 0:
            annual_conversion_needed = gas_properties / years_remaining
        else:
            annual_conversion_needed = gas_properties  # All at once

        # Compare to current rates
        current_hp_rate = self.POLICY_TARGETS['heat_pump_current_rate']
        multiplier_vs_current = annual_conversion_needed / current_hp_rate if current_hp_rate > 0 else 0

        results = {
            'phaseout_year': phaseout_year,
            'years_remaining': years_remaining,
            'total_properties': int(total_properties),
            'gas_heated_properties': int(gas_properties),
            'gas_percentage': round(gas_properties / total_properties * 100, 1),
            'already_low_carbon': int(low_carbon),
            'conversions_needed': int(gas_properties),
            'annual_conversions_needed': int(annual_conversion_needed),
            'vs_current_hp_rate': f"{multiplier_vs_current:.0f}x current rate",
            'implied_monthly_conversions': int(annual_conversion_needed / 12),
            'implied_daily_conversions': int(annual_conversion_needed / 365)
        }

        logger.info(f"Gas properties to convert: {gas_properties:,}")
        logger.info(f"Annual conversions needed: {annual_conversion_needed:,.0f} ({multiplier_vs_current:.0f}x current)")

        self.results['boiler_phaseout'] = results
        return results

    def estimate_job_creation(self, df: pd.DataFrame) -> Dict:
        """
        Estimate job creation potential from heat decarbonisation.

        ADE estimates 200,000 new full-time jobs by 2030 from combined
        efficiency upgrades and low-carbon heat rollout.

        Args:
            df: EPC DataFrame

        Returns:
            Dictionary with job creation estimates
        """
        logger.info("Estimating job creation potential...")

        total_properties = len(df)

        # Estimate properties needing work
        needs_insulation = 0
        needs_heating_upgrade = 0

        if 'CURRENT_ENERGY_RATING' in df.columns:
            # Properties below EPC C need work
            below_c = df['CURRENT_ENERGY_RATING'].isin(['D', 'E', 'F', 'G']).sum()
            needs_insulation = below_c

        if 'fuel_category' in df.columns:
            # Fossil fuel properties need heating upgrade
            needs_heating_upgrade = df['fuel_category'].isin(['mains_gas', 'oil', 'lpg', 'coal']).sum()

        # Job intensity estimates (from industry research)
        # Retrofit: ~10-15 jobs per £1M invested
        # Heat pump installation: ~3-5 jobs per £1M invested
        jobs_per_million_retrofit = 12
        jobs_per_million_heating = 4

        # Cost estimates
        avg_retrofit_cost = 8000  # Average fabric improvement
        avg_hp_cost = 12000  # Heat pump installation

        # Total investment potential
        retrofit_investment_bn = (needs_insulation * avg_retrofit_cost) / 1e9
        heating_investment_bn = (needs_heating_upgrade * avg_hp_cost) / 1e9
        total_investment_bn = retrofit_investment_bn + heating_investment_bn

        # Job creation estimate
        retrofit_jobs = retrofit_investment_bn * 1000 * jobs_per_million_retrofit
        heating_jobs = heating_investment_bn * 1000 * jobs_per_million_heating
        total_jobs = retrofit_jobs + heating_jobs

        results = {
            'properties_needing_retrofit': int(needs_insulation),
            'properties_needing_heating_upgrade': int(needs_heating_upgrade),
            'estimated_retrofit_investment_bn': round(retrofit_investment_bn, 1),
            'estimated_heating_investment_bn': round(heating_investment_bn, 1),
            'total_investment_potential_bn': round(total_investment_bn, 1),
            'jobs_from_retrofit': int(retrofit_jobs),
            'jobs_from_heating': int(heating_jobs),
            'total_jobs_potential': int(total_jobs),
            'ade_target_2030': self.POLICY_TARGETS['jobs_target_2030'],
            'vs_ade_target': f"{total_jobs / self.POLICY_TARGETS['jobs_target_2030'] * 100:.0f}% of ADE target"
        }

        logger.info(f"Total investment potential: £{total_investment_bn:.0f}B")
        logger.info(f"Job creation potential: {total_jobs:,.0f}")

        self.results['job_creation'] = results
        return results

    def analyze_all(self, df: pd.DataFrame) -> Dict:
        """
        Run all policy scenario analyses.

        Args:
            df: EPC DataFrame

        Returns:
            Complete results dictionary
        """
        logger.info("Running complete policy scenario analysis...")

        # Ensure fuel_category exists
        if 'fuel_category' not in df.columns and 'MAIN_FUEL' in df.columns:
            from src.analysis.heating_fuel_analysis import HeatingFuelAnalyzer
            fuel_analyzer = HeatingFuelAnalyzer()
            fuel_analyzer.analyze_fuel_mix(df)

        self.analyze_price_rebalancing_impact(df)
        self.project_installation_rates(df)
        self.analyze_boiler_phaseout_timeline(df)
        self.estimate_job_creation(df)

        logger.info("Policy scenario analysis complete")
        return self.results

    def save_results(self, output_path: Optional[Path] = None):
        """
        Save analysis results to file.

        Args:
            output_path: Path to save results
        """
        if output_path is None:
            output_path = DATA_OUTPUTS_DIR / "policy_scenarios_results.txt"

        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write("POLICY SCENARIO ANALYSIS RESULTS\n")
            f.write("=" * 70 + "\n")
            f.write("Evidence base for ADE policy recommendations\n\n")

            # Price Rebalancing
            if 'price_rebalancing' in self.results:
                pr = self.results['price_rebalancing']
                f.write("\n1. ENERGY PRICE REBALANCING IMPACT\n")
                f.write("-" * 70 + "\n")
                f.write("ADE Policy Ask: Shift levies from electricity to gas\n\n")

                f.write("Current Prices (Ofgem cap):\n")
                curr = pr['current_prices']
                f.write(f"  Gas: {curr['gas_price']*100:.1f}p/kWh, Electricity: {curr['electricity_price']*100:.1f}p/kWh\n")
                f.write(f"  Gas boiler running cost: £{curr['gas_boiler_annual_cost']:,.0f}/year\n")
                f.write(f"  Heat pump running cost: £{curr['heat_pump_annual_cost']:,.0f}/year\n")
                f.write(f"  Heat pump premium: £{curr['hp_vs_gas_difference']:+,.0f}/year ({curr['hp_premium_percent']:+.0f}%)\n\n")

                f.write("With Price Rebalancing:\n")
                reb = pr['rebalanced_prices']
                f.write(f"  Gas: {reb['gas_price']*100:.1f}p/kWh, Electricity: {reb['electricity_price']*100:.1f}p/kWh\n")
                f.write(f"  Gas boiler running cost: £{reb['gas_boiler_annual_cost']:,.0f}/year\n")
                f.write(f"  Heat pump running cost: £{reb['heat_pump_annual_cost']:,.0f}/year\n")
                f.write(f"  Heat pump SAVING: £{-reb['hp_vs_gas_difference']:,.0f}/year ({reb['hp_saving_percent']:.0f}%)\n\n")

                f.write(f"Policy Impact: Price rebalancing would shift heat pumps from\n")
                f.write(f"£{pr['policy_impact']['current_hp_premium']:,.0f}/yr MORE expensive to ")
                f.write(f"£{pr['policy_impact']['rebalanced_hp_saving']:,.0f}/yr CHEAPER than gas\n")

            # Installation Rates
            if 'installation_rates' in self.results:
                ir = self.results['installation_rates']
                f.write("\n\n2. HEAT PUMP INSTALLATION RATES\n")
                f.write("-" * 70 + "\n")
                f.write("Government Target: 600,000 heat pumps/year by 2028\n\n")

                f.write(f"Current installation rate: {ir['current_annual_rate']:,}/year\n")
                f.write(f"Target rate: {ir['target_annual_rate_2028']:,}/year\n")
                f.write(f"Increase needed: {ir['multiplier_needed']:.0f}x ({ir['cagr_needed_percent']:.0f}% annual growth)\n")
                f.write(f"UK ranking for heat pump installs: {ir['uk_ranking_heat_pumps']}\n\n")

                f.write(f"In our dataset:\n")
                f.write(f"  Suitable properties: {ir['suitable_properties_in_data']:,}\n")
                f.write(f"  Existing heat pumps: {ir['existing_heat_pumps_estimate']:,}\n")
                f.write(f"  Years to complete at current rate: {ir['years_to_complete_at_current_rate']:.0f}\n")
                f.write(f"  Years to complete at target rate: {ir['years_to_complete_at_target_rate']:.0f}\n")

            # Boiler Phase-out
            if 'boiler_phaseout' in self.results:
                bp = self.results['boiler_phaseout']
                f.write("\n\n3. 2035 GAS BOILER PHASE-OUT\n")
                f.write("-" * 70 + "\n")
                f.write("ADE Policy Ask: Legislate gas boiler phase-out by 2035\n\n")

                f.write(f"Years remaining: {bp['years_remaining']}\n")
                f.write(f"Gas-heated properties: {bp['gas_heated_properties']:,} ({bp['gas_percentage']:.0f}%)\n")
                f.write(f"Already low-carbon: {bp['already_low_carbon']:,}\n\n")

                f.write(f"To meet 2035 deadline:\n")
                f.write(f"  Annual conversions needed: {bp['annual_conversions_needed']:,}\n")
                f.write(f"  Monthly conversions: {bp['implied_monthly_conversions']:,}\n")
                f.write(f"  Daily conversions: {bp['implied_daily_conversions']:,}\n")
                f.write(f"  vs current HP rate: {bp['vs_current_hp_rate']}\n")

            # Job Creation
            if 'job_creation' in self.results:
                jc = self.results['job_creation']
                f.write("\n\n4. JOB CREATION POTENTIAL\n")
                f.write("-" * 70 + "\n")
                f.write("ADE Projection: 200,000 new jobs by 2030\n\n")

                f.write(f"Investment potential:\n")
                f.write(f"  Retrofit (fabric): £{jc['estimated_retrofit_investment_bn']:.0f}B\n")
                f.write(f"  Heating systems: £{jc['estimated_heating_investment_bn']:.0f}B\n")
                f.write(f"  Total: £{jc['total_investment_potential_bn']:.0f}B\n\n")

                f.write(f"Job creation potential:\n")
                f.write(f"  From retrofit: {jc['jobs_from_retrofit']:,}\n")
                f.write(f"  From heating upgrades: {jc['jobs_from_heating']:,}\n")
                f.write(f"  Total: {jc['total_jobs_potential']:,}\n")
                f.write(f"  vs ADE 2030 target: {jc['vs_ade_target']}\n")

        logger.info(f"Results saved to: {output_path}")


def main():
    """Main execution function for policy scenario analysis."""
    logger.info("Starting policy scenario analysis...")

    from config.config import DATA_PROCESSED_DIR
    input_file = DATA_PROCESSED_DIR / "epc_england_wales_validated.parquet"

    if not input_file.exists():
        logger.error(f"Input file not found: {input_file}")
        return

    import pandas as pd
    logger.info(f"Loading data from: {input_file}")
    df = pd.read_parquet(input_file)

    analyzer = PolicyScenarioAnalyzer()
    analyzer.analyze_all(df)
    analyzer.save_results()

    logger.info("Policy scenario analysis complete!")


if __name__ == "__main__":
    main()
