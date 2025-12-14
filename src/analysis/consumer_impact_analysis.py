"""
Consumer Impact Analysis Module

Calculates consumer-facing energy and financial metrics for ADE policy analysis.
Aligned with ADE's strategic priorities on making low-carbon heating affordable.

Provides:
- Annual household heating bills (current and post-improvement)
- Per-household CO2 emissions
- Heat pump vs gas boiler running cost comparison
- Payback period analysis with subsidy scenarios
- Price rebalancing impact assessment
"""

import pandas as pd
import numpy as np
from pathlib import Path
from typing import Dict, Optional, Tuple
from loguru import logger

import sys
sys.path.append(str(Path(__file__).parent.parent.parent))
from config.config import load_config, DATA_OUTPUTS_DIR


class ConsumerImpactAnalyzer:
    """
    Analyzes consumer-facing impacts of heating decarbonisation.

    Key focus areas aligned with ADE priorities:
    - Running cost parity between heat pumps and gas boilers
    - Impact of price rebalancing policies
    - Affordability and payback periods
    """

    def __init__(self):
        """Initialize the consumer impact analyzer."""
        self.config = load_config()
        self.energy_prices = self.config.get('energy_prices', {})
        self.carbon_factors = self.config.get('carbon_factors', {})
        self.costs = self.config.get('costs', {})
        self.financial = self.config.get('financial', {})
        self.results = {}
        logger.info("Initialized Consumer Impact Analyzer")

    def calculate_household_bills(self, df: pd.DataFrame) -> Dict:
        """
        Calculate current annual heating bills per household.

        Uses ENERGY_CONSUMPTION_CURRENT from EPC data with current energy prices.

        Args:
            df: EPC DataFrame with energy consumption data

        Returns:
            Dictionary with bill statistics
        """
        logger.info("Calculating household heating bills...")

        # Get energy consumption
        if 'ENERGY_CONSUMPTION_CURRENT' not in df.columns:
            logger.warning("ENERGY_CONSUMPTION_CURRENT not found - using estimates")
            if 'TOTAL_FLOOR_AREA' in df.columns:
                # Rough estimate: 120 kWh/m²/year for heating
                df['annual_energy_kwh'] = df['TOTAL_FLOOR_AREA'] * 120
            else:
                df['annual_energy_kwh'] = 12000  # UK average
        else:
            df['annual_energy_kwh'] = df['ENERGY_CONSUMPTION_CURRENT']

        # Get current prices
        current_prices = self.energy_prices.get('current', {})
        gas_price = current_prices.get('gas', 0.0624)
        elec_price = current_prices.get('electricity', 0.26)

        # Estimate fuel split (use MAIN_FUEL if available)
        if 'fuel_category' in df.columns:
            # Calculate bills based on actual fuel type
            gas_mask = df['fuel_category'] == 'mains_gas'
            elec_mask = df['fuel_category'].isin(['electric', 'renewable'])

            # Gas boiler efficiency ~85%
            df.loc[gas_mask, 'annual_bill'] = (
                df.loc[gas_mask, 'annual_energy_kwh'] / 0.85 * gas_price
            )
            # Electric heating (direct or storage heaters, assume COP ~1)
            df.loc[elec_mask, 'annual_bill'] = (
                df.loc[elec_mask, 'annual_energy_kwh'] * elec_price
            )
            # Other fuels - use gas price as proxy
            other_mask = ~gas_mask & ~elec_mask
            df.loc[other_mask, 'annual_bill'] = (
                df.loc[other_mask, 'annual_energy_kwh'] / 0.85 * gas_price
            )
        else:
            # Assume gas heating for most properties (82% of stock)
            df['annual_bill'] = df['annual_energy_kwh'] / 0.85 * gas_price

        # Add standing charge estimate (~£100/year)
        df['annual_bill'] = df['annual_bill'] + 100

        # Calculate statistics
        results = {
            'total_properties': len(df),
            'avg_annual_bill': float(df['annual_bill'].mean()),
            'median_annual_bill': float(df['annual_bill'].median()),
            'bill_25th_percentile': float(df['annual_bill'].quantile(0.25)),
            'bill_75th_percentile': float(df['annual_bill'].quantile(0.75)),
            'total_annual_bills_bn': float(df['annual_bill'].sum() / 1e9),
            'avg_energy_consumption_kwh': float(df['annual_energy_kwh'].mean()),
            'gas_price_used': gas_price,
            'electricity_price_used': elec_price
        }

        logger.info(f"Average annual heating bill: £{results['avg_annual_bill']:,.0f}")
        logger.info(f"Median annual heating bill: £{results['median_annual_bill']:,.0f}")

        self.results['household_bills'] = results
        return results

    def calculate_household_emissions(self, df: pd.DataFrame) -> Dict:
        """
        Calculate current CO2 emissions per household.

        Args:
            df: EPC DataFrame with energy consumption data

        Returns:
            Dictionary with emissions statistics
        """
        logger.info("Calculating household emissions...")

        # Get energy consumption
        if 'annual_energy_kwh' not in df.columns:
            if 'ENERGY_CONSUMPTION_CURRENT' in df.columns:
                df['annual_energy_kwh'] = df['ENERGY_CONSUMPTION_CURRENT']
            else:
                df['annual_energy_kwh'] = 12000  # UK average

        # Get carbon factors
        current_factors = self.carbon_factors.get('current', {})
        gas_carbon = current_factors.get('gas', 0.183)
        elec_carbon = current_factors.get('electricity', 0.233)

        # Calculate emissions based on fuel type
        if 'fuel_category' in df.columns:
            gas_mask = df['fuel_category'] == 'mains_gas'
            elec_mask = df['fuel_category'].isin(['electric', 'renewable'])

            # Gas emissions (accounting for boiler efficiency)
            df.loc[gas_mask, 'annual_emissions_kg'] = (
                df.loc[gas_mask, 'annual_energy_kwh'] / 0.85 * gas_carbon
            )
            # Electric emissions
            df.loc[elec_mask, 'annual_emissions_kg'] = (
                df.loc[elec_mask, 'annual_energy_kwh'] * elec_carbon
            )
            # Other fuels - use gas factor as proxy
            other_mask = ~gas_mask & ~elec_mask
            df.loc[other_mask, 'annual_emissions_kg'] = (
                df.loc[other_mask, 'annual_energy_kwh'] / 0.85 * gas_carbon
            )
        else:
            df['annual_emissions_kg'] = df['annual_energy_kwh'] / 0.85 * gas_carbon

        # Convert to tonnes
        df['annual_emissions_tonnes'] = df['annual_emissions_kg'] / 1000

        results = {
            'avg_emissions_tonnes': float(df['annual_emissions_tonnes'].mean()),
            'median_emissions_tonnes': float(df['annual_emissions_tonnes'].median()),
            'total_emissions_mt': float(df['annual_emissions_tonnes'].sum() / 1e6),
            'emissions_25th_percentile': float(df['annual_emissions_tonnes'].quantile(0.25)),
            'emissions_75th_percentile': float(df['annual_emissions_tonnes'].quantile(0.75)),
            'gas_carbon_factor': gas_carbon,
            'electricity_carbon_factor': elec_carbon
        }

        logger.info(f"Average annual emissions: {results['avg_emissions_tonnes']:.2f} tonnes CO2")
        logger.info(f"Total stock emissions: {results['total_emissions_mt']:.1f} Mt CO2/year")

        self.results['household_emissions'] = results
        return results

    def compare_heating_running_costs(self, df: pd.DataFrame) -> Dict:
        """
        Compare running costs: gas boiler vs heat pump under different price scenarios.

        This is a key metric for ADE's advocacy on price rebalancing.

        Args:
            df: EPC DataFrame with energy consumption data

        Returns:
            Dictionary with cost comparison results
        """
        logger.info("Comparing heating running costs (gas vs heat pump)...")

        # Get energy demand
        if 'annual_energy_kwh' not in df.columns:
            if 'ENERGY_CONSUMPTION_CURRENT' in df.columns:
                df['annual_energy_kwh'] = df['ENERGY_CONSUMPTION_CURRENT']
            else:
                df['annual_energy_kwh'] = 12000

        avg_demand = df['annual_energy_kwh'].mean()

        # Heat pump parameters
        hp_scop = self.config.get('heat_pump', {}).get('scop', 3.0)
        gas_boiler_efficiency = 0.85

        # Get price scenarios
        price_scenarios = self.financial.get('price_scenarios', {})

        results = {
            'avg_heat_demand_kwh': float(avg_demand),
            'heat_pump_scop': hp_scop,
            'gas_boiler_efficiency': gas_boiler_efficiency,
            'scenarios': {}
        }

        for scenario_name, prices in price_scenarios.items():
            gas_price = prices.get('gas', 0.0624)
            elec_price = prices.get('electricity', 0.26)

            # Gas boiler annual cost
            gas_annual_cost = (avg_demand / gas_boiler_efficiency) * gas_price + 100  # +standing charge

            # Heat pump annual cost
            hp_annual_cost = (avg_demand / hp_scop) * elec_price + 100  # +standing charge

            # Difference
            savings = gas_annual_cost - hp_annual_cost
            savings_pct = (savings / gas_annual_cost) * 100

            results['scenarios'][scenario_name] = {
                'name': prices.get('name', scenario_name),
                'gas_price': gas_price,
                'electricity_price': elec_price,
                'gas_boiler_annual_cost': round(gas_annual_cost, 0),
                'heat_pump_annual_cost': round(hp_annual_cost, 0),
                'annual_savings': round(savings, 0),
                'savings_percent': round(savings_pct, 1),
                'heat_pump_cheaper': savings > 0
            }

            logger.info(
                f"  {prices.get('name', scenario_name)}: "
                f"Gas £{gas_annual_cost:.0f}/yr, HP £{hp_annual_cost:.0f}/yr "
                f"({'saves £' + str(abs(int(savings))) if savings > 0 else 'costs £' + str(abs(int(savings))) + ' more'}/yr)"
            )

        self.results['running_cost_comparison'] = results
        return results

    def calculate_payback_periods(
        self,
        df: pd.DataFrame,
        subsidy_scenarios: list = [0, 0.25, 0.50, 0.75, 1.0]
    ) -> Dict:
        """
        Calculate heat pump payback periods under different subsidy scenarios.

        Args:
            df: EPC DataFrame
            subsidy_scenarios: List of subsidy percentages (0 = no subsidy, 1 = 100% funded)

        Returns:
            Dictionary with payback analysis
        """
        logger.info("Calculating heat pump payback periods...")

        # Get costs
        hp_cost = self.costs.get('ashp_installation', 12000)
        radiator_upgrade = self.costs.get('radiator_upsizing', 2500)
        total_hp_cost = hp_cost + radiator_upgrade  # Full heat pump pathway

        # Get current grant (BUS = £7500)
        current_grant = 7500

        # Get running cost comparison for savings
        if 'running_cost_comparison' not in self.results:
            self.compare_heating_running_costs(df)

        # Use current prices scenario for payback
        current_scenario = self.results['running_cost_comparison']['scenarios'].get('baseline', {})
        annual_savings = current_scenario.get('annual_savings', 0)

        # Use rebalanced scenario if available
        rebalanced_scenario = self.results['running_cost_comparison']['scenarios'].get('rebalanced', {})
        annual_savings_rebalanced = rebalanced_scenario.get('annual_savings', 0)

        results = {
            'base_hp_cost': hp_cost,
            'total_hp_pathway_cost': total_hp_cost,
            'current_bus_grant': current_grant,
            'payback_scenarios': {}
        }

        for subsidy_pct in subsidy_scenarios:
            net_cost = total_hp_cost * (1 - subsidy_pct)

            # Payback at current prices
            if annual_savings > 0:
                payback_current = net_cost / annual_savings
            else:
                payback_current = float('inf')  # Never pays back if no savings

            # Payback with rebalanced prices
            if annual_savings_rebalanced > 0:
                payback_rebalanced = net_cost / annual_savings_rebalanced
            else:
                payback_rebalanced = float('inf')

            results['payback_scenarios'][f"{int(subsidy_pct*100)}%_subsidy"] = {
                'subsidy_percent': subsidy_pct * 100,
                'net_cost_to_consumer': round(net_cost, 0),
                'payback_years_current_prices': round(payback_current, 1) if payback_current < 100 else 'N/A',
                'payback_years_rebalanced': round(payback_rebalanced, 1) if payback_rebalanced < 100 else 'N/A'
            }

            logger.info(
                f"  {int(subsidy_pct*100)}% subsidy: £{net_cost:.0f} net cost, "
                f"payback {payback_current:.1f} yrs (current) / {payback_rebalanced:.1f} yrs (rebalanced)"
            )

        # With current BUS grant
        bus_net_cost = total_hp_cost - current_grant
        if annual_savings > 0:
            bus_payback = bus_net_cost / annual_savings
        else:
            bus_payback = float('inf')
        if annual_savings_rebalanced > 0:
            bus_payback_rebalanced = bus_net_cost / annual_savings_rebalanced
        else:
            bus_payback_rebalanced = float('inf')

        results['with_bus_grant'] = {
            'net_cost': round(bus_net_cost, 0),
            'payback_years_current': round(bus_payback, 1) if bus_payback < 100 else 'N/A',
            'payback_years_rebalanced': round(bus_payback_rebalanced, 1) if bus_payback_rebalanced < 100 else 'N/A'
        }

        self.results['payback_analysis'] = results
        return results

    def analyze_all(self, df: pd.DataFrame) -> Dict:
        """
        Run all consumer impact analyses.

        Args:
            df: EPC DataFrame

        Returns:
            Complete results dictionary
        """
        logger.info("Running complete consumer impact analysis...")

        # First ensure fuel_category exists (from heating fuel analysis)
        if 'fuel_category' not in df.columns and 'MAIN_FUEL' in df.columns:
            from src.analysis.heating_fuel_analysis import HeatingFuelAnalyzer
            fuel_analyzer = HeatingFuelAnalyzer()
            fuel_analyzer.analyze_fuel_mix(df)

        self.calculate_household_bills(df)
        self.calculate_household_emissions(df)
        self.compare_heating_running_costs(df)
        self.calculate_payback_periods(df)

        logger.info("Consumer impact analysis complete")
        return self.results

    def save_results(self, output_path: Optional[Path] = None):
        """
        Save analysis results to file.

        Args:
            output_path: Path to save results
        """
        if output_path is None:
            output_path = DATA_OUTPUTS_DIR / "consumer_impact_results.txt"

        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write("CONSUMER IMPACT ANALYSIS RESULTS\n")
            f.write("=" * 70 + "\n")
            f.write("Aligned with ADE's strategic priorities on affordable decarbonisation\n\n")

            # Household Bills
            if 'household_bills' in self.results:
                bills = self.results['household_bills']
                f.write("\nHOUSEHOLD HEATING BILLS (CURRENT)\n")
                f.write("-" * 70 + "\n")
                f.write(f"Total properties analyzed: {bills['total_properties']:,}\n")
                f.write(f"Average annual heating bill: £{bills['avg_annual_bill']:,.0f}\n")
                f.write(f"Median annual heating bill: £{bills['median_annual_bill']:,.0f}\n")
                f.write(f"25th percentile: £{bills['bill_25th_percentile']:,.0f}\n")
                f.write(f"75th percentile: £{bills['bill_75th_percentile']:,.0f}\n")
                f.write(f"Total annual heating bills (all properties): £{bills['total_annual_bills_bn']:.1f}B\n")

            # Household Emissions
            if 'household_emissions' in self.results:
                emissions = self.results['household_emissions']
                f.write("\nHOUSEHOLD EMISSIONS (CURRENT)\n")
                f.write("-" * 70 + "\n")
                f.write(f"Average annual emissions: {emissions['avg_emissions_tonnes']:.2f} tonnes CO2\n")
                f.write(f"Median annual emissions: {emissions['median_emissions_tonnes']:.2f} tonnes CO2\n")
                f.write(f"Total stock emissions: {emissions['total_emissions_mt']:.1f} Mt CO2/year\n")

            # Running Cost Comparison
            if 'running_cost_comparison' in self.results:
                comparison = self.results['running_cost_comparison']
                f.write("\nHEAT PUMP VS GAS BOILER RUNNING COSTS\n")
                f.write("-" * 70 + "\n")
                f.write(f"Average heat demand: {comparison['avg_heat_demand_kwh']:,.0f} kWh/year\n")
                f.write(f"Heat pump SCOP assumed: {comparison['heat_pump_scop']}\n")
                f.write(f"Gas boiler efficiency assumed: {comparison['gas_boiler_efficiency']*100:.0f}%\n\n")

                for scenario_key, scenario in comparison['scenarios'].items():
                    f.write(f"{scenario['name']}:\n")
                    f.write(f"  Gas boiler: £{scenario['gas_boiler_annual_cost']:,.0f}/year\n")
                    f.write(f"  Heat pump: £{scenario['heat_pump_annual_cost']:,.0f}/year\n")
                    if scenario['heat_pump_cheaper']:
                        f.write(f"  Heat pump SAVES: £{scenario['annual_savings']:,.0f}/year ({scenario['savings_percent']:.0f}%)\n")
                    else:
                        f.write(f"  Heat pump COSTS MORE: £{abs(scenario['annual_savings']):,.0f}/year\n")
                    f.write("\n")

            # Payback Analysis
            if 'payback_analysis' in self.results:
                payback = self.results['payback_analysis']
                f.write("\nHEAT PUMP PAYBACK ANALYSIS\n")
                f.write("-" * 70 + "\n")
                f.write(f"Base heat pump cost: £{payback['base_hp_cost']:,}\n")
                f.write(f"Total pathway cost (inc radiators): £{payback['total_hp_pathway_cost']:,}\n")
                f.write(f"Current BUS grant: £{payback['current_bus_grant']:,}\n\n")

                f.write("With BUS grant (£7,500):\n")
                bus = payback['with_bus_grant']
                f.write(f"  Net cost to consumer: £{bus['net_cost']:,}\n")
                f.write(f"  Payback (current prices): {bus['payback_years_current']} years\n")
                f.write(f"  Payback (rebalanced prices): {bus['payback_years_rebalanced']} years\n\n")

                f.write("Subsidy sensitivity:\n")
                for scenario_key, scenario in payback['payback_scenarios'].items():
                    f.write(f"  {scenario['subsidy_percent']:.0f}% subsidy: ")
                    f.write(f"£{scenario['net_cost_to_consumer']:,.0f} net, ")
                    f.write(f"payback {scenario['payback_years_current_prices']} yrs\n")

        logger.info(f"Results saved to: {output_path}")


def main():
    """Main execution function for consumer impact analysis."""
    logger.info("Starting consumer impact analysis...")

    from config.config import DATA_PROCESSED_DIR
    input_file = DATA_PROCESSED_DIR / "epc_england_wales_validated.parquet"

    if not input_file.exists():
        logger.error(f"Input file not found: {input_file}")
        return

    import pandas as pd
    logger.info(f"Loading data from: {input_file}")
    df = pd.read_parquet(input_file)

    analyzer = ConsumerImpactAnalyzer()
    analyzer.analyze_all(df)
    analyzer.save_results()

    logger.info("Consumer impact analysis complete!")


if __name__ == "__main__":
    main()
