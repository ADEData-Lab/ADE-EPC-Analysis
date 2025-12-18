"""
Cost Calculation Utilities

Centralized cost calculation utilities to eliminate logic drift and duplication
across analysis modules.

Provides:
- Fabric improvement costs (loft, walls, floors, glazing)
- Heat pump installation costs
- Running cost calculations
- Payback period calculations
- NPV and LCOH calculations

Created as part of code optimization initiative to eliminate cost logic drift
where same costs appeared with slight variations across modules.
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Union
from loguru import logger

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent.parent))
from config.config import load_config


class CostCalculator:
    """
    Centralized cost calculation utilities.

    Single source of truth for all cost assumptions and calculations.

    Example Usage:
    -------------
    >>> calc = CostCalculator()
    >>> fabric_cost = calc.calculate_fabric_costs(
    ...     df,
    ...     measures=['loft_insulation_topup', 'cavity_wall_insulation']
    ... )
    >>> running_costs = calc.calculate_annual_running_costs(
    ...     annual_demand=10000,  # kWh/year
    ...     system_type='heat_pump',
    ...     price_scenario='baseline'
    ... )
    """

    def __init__(self, config: Optional[Dict] = None):
        """
        Initialize cost calculator.

        Args:
            config: Optional config dictionary (loads from config.yaml if None)
        """
        if config is None:
            config = load_config()

        self.config = config
        self.costs = config.get('costs', {})
        self.energy_prices = config.get('energy_prices', {})
        self.carbon_factors = config.get('carbon_factors', {})
        self.heat_pump_config = config.get('heat_pump', {})
        self.financial_config = config.get('financial', {})

        logger.debug("Initialized CostCalculator")

    # ==================== Fabric Improvement Costs ====================

    def get_measure_cost(self, measure: str) -> float:
        """
        Get cost for a specific retrofit measure.

        Args:
            measure: Measure name (e.g., 'loft_insulation_topup', 'ashp_installation')

        Returns:
            Cost in £
        """
        return self.costs.get(measure, 0)

    def calculate_fabric_costs(
        self,
        df: pd.DataFrame,
        measures: List[str],
        floor_area_col: str = 'TOTAL_FLOOR_AREA'
    ) -> pd.Series:
        """
        Calculate total fabric improvement costs per property.

        Args:
            df: DataFrame with property data
            measures: List of measures to apply
            floor_area_col: Column with floor area (m²)

        Returns:
            Series with total fabric costs per property

        Supported measures:
            - loft_insulation_topup
            - cavity_wall_insulation
            - solid_wall_insulation_ewi
            - solid_wall_insulation_iwi
            - floor_insulation
            - double_glazing_upgrade
            - triple_glazing_upgrade
            - draught_proofing
        """
        total_cost = pd.Series(0, index=df.index)

        for measure in measures:
            measure_cost = self.get_measure_cost(measure)

            if measure_cost == 0:
                logger.warning(f"Cost not found for measure: {measure}")
                continue

            # Area-based measures (per m²)
            if measure in ['loft_insulation_per_m2', 'internal_wall_insulation_per_m2',
                          'external_wall_insulation_per_m2', 'double_glazing_per_m2',
                          'triple_glazing_per_m2']:
                # Need area calculation - skip for now
                logger.warning(f"Area-based measure requires geometry: {measure}")
                continue

            # Fixed-cost measures
            else:
                total_cost += measure_cost

        return total_cost

    def calculate_loft_insulation_cost(
        self,
        floor_area: Union[float, pd.Series],
        loft_area_ratio: float = 0.9
    ) -> Union[float, pd.Series]:
        """
        Calculate loft insulation top-up cost.

        Args:
            floor_area: Floor area in m² (scalar or Series)
            loft_area_ratio: Ratio of loft area to floor area (default: 0.9)

        Returns:
            Cost in £
        """
        cost_per_m2 = self.costs.get('loft_insulation_per_m2', 30)
        loft_area = floor_area * loft_area_ratio
        return loft_area * cost_per_m2

    def calculate_wall_insulation_cost(
        self,
        floor_area: Union[float, pd.Series],
        wall_type: str = 'cavity',
        wall_area_ratio: float = 1.5
    ) -> Union[float, pd.Series]:
        """
        Calculate wall insulation cost.

        Args:
            floor_area: Floor area in m²
            wall_type: 'cavity', 'solid_ewi', or 'solid_iwi'
            wall_area_ratio: Ratio of wall area to floor area (default: 1.5)

        Returns:
            Cost in £
        """
        if wall_type == 'cavity':
            return self.costs.get('cavity_wall_insulation', 2500)
        elif wall_type == 'solid_ewi':
            return self.costs.get('solid_wall_insulation_ewi', 10000)
        elif wall_type == 'solid_iwi':
            return self.costs.get('solid_wall_insulation_iwi', 14000)
        else:
            logger.warning(f"Unknown wall type: {wall_type}")
            return 0

    def calculate_glazing_cost(
        self,
        floor_area: Union[float, pd.Series],
        glazing_type: str = 'double',
        window_area_ratio: float = 0.2
    ) -> Union[float, pd.Series]:
        """
        Calculate glazing upgrade cost.

        Args:
            floor_area: Floor area in m²
            glazing_type: 'double' or 'triple'
            window_area_ratio: Ratio of window area to floor area (default: 0.2)

        Returns:
            Cost in £
        """
        if glazing_type == 'double':
            cost_per_m2 = self.costs.get('double_glazing_per_m2', 400)
        elif glazing_type == 'triple':
            cost_per_m2 = self.costs.get('triple_glazing_per_m2', 600)
        else:
            logger.warning(f"Unknown glazing type: {glazing_type}")
            return 0

        window_area = floor_area * window_area_ratio
        return window_area * cost_per_m2

    # ==================== Heat Pump Costs ====================

    def calculate_heat_pump_cost(
        self,
        include_radiator_upgrades: bool = False,
        include_cylinder: bool = False,
        include_electrical_upgrade: bool = False,
        hybrid: bool = False
    ) -> float:
        """
        Calculate heat pump installation cost.

        Args:
            include_radiator_upgrades: Include radiator upsizing cost
            include_cylinder: Include hot water cylinder cost
            include_electrical_upgrade: Include electrical supply upgrade
            hybrid: If True, uses hybrid heat pump cost

        Returns:
            Total cost in £
        """
        if hybrid:
            total = self.costs.get('hybrid_heat_pump', 8000)
        else:
            total = self.costs.get('ashp_installation', 12000)

        if include_radiator_upgrades:
            total += self.costs.get('radiator_upsizing', 2500)

        if include_cylinder:
            total += self.costs.get('hot_water_cylinder', 1200)

        if include_electrical_upgrade:
            total += self.costs.get('electrical_upgrade', 1500)

        return total

    def calculate_emitter_upgrade_cost(
        self,
        flow_temperature: Union[float, pd.Series]
    ) -> Union[float, pd.Series]:
        """
        Calculate emitter (radiator) upgrade cost based on required flow temperature.

        Args:
            flow_temperature: Required flow temperature in °C

        Returns:
            Upgrade cost in £

        Tiers:
            None required (<45°C): £0
            Possible (45-55°C): £1,500
            Likely (55-65°C): £3,500
            Definite (>65°C): £6,000
        """
        if isinstance(flow_temperature, pd.Series):
            cost = pd.Series(0, index=flow_temperature.index)
            cost.loc[flow_temperature >= 45] = 1500
            cost.loc[flow_temperature >= 55] = 3500
            cost.loc[flow_temperature >= 65] = 6000
            return cost
        else:
            if flow_temperature < 45:
                return 0
            elif flow_temperature < 55:
                return 1500
            elif flow_temperature < 65:
                return 3500
            else:
                return 6000

    # ==================== Running Cost Calculations ====================

    def calculate_annual_running_costs(
        self,
        annual_demand: Union[float, pd.Series],
        system_type: str = 'gas_boiler',
        price_scenario: str = 'baseline',
        year: str = 'current'
    ) -> Union[float, pd.Series]:
        """
        Calculate annual running costs.

        Args:
            annual_demand: Annual heat demand in kWh/year
            system_type: 'gas_boiler', 'heat_pump', 'heat_network', 'electric'
            price_scenario: 'baseline', 'low', 'high', 'projected_2030', 'rebalanced'
            year: 'current', '2030', '2040' (for baseline scenario)

        Returns:
            Annual cost in £/year
        """
        # Get energy prices
        prices = self._get_energy_prices(price_scenario, year)

        # System efficiencies
        gas_boiler_eff = 0.85
        hp_scop = self.heat_pump_config.get('scop', 3.0)

        if system_type == 'gas_boiler':
            fuel_used = annual_demand / gas_boiler_eff
            return fuel_used * prices['gas']

        elif system_type == 'heat_pump':
            electricity_used = annual_demand / hp_scop
            return electricity_used * prices['electricity']

        elif system_type == 'heat_network':
            return annual_demand * prices['heat_network']

        elif system_type == 'electric':
            electricity_used = annual_demand  # Direct electric heating
            return electricity_used * prices['electricity']

        else:
            logger.error(f"Unknown system type: {system_type}")
            return 0

    def _get_energy_prices(
        self,
        scenario: str,
        year: str
    ) -> Dict[str, float]:
        """Get energy prices for scenario and year."""
        # Get scenario prices
        if scenario == 'baseline':
            if year == 'current':
                prices = self.energy_prices.get('current', {})
            elif year == '2030':
                prices = self.energy_prices.get('projected_2030', {})
            elif year == '2040':
                prices = self.energy_prices.get('projected_2040', {})
            else:
                logger.warning(f"Unknown year: {year}, using current")
                prices = self.energy_prices.get('current', {})
        else:
            # Get from financial price scenarios
            price_scenarios = self.financial_config.get('price_scenarios', {})
            prices = price_scenarios.get(scenario, {})

        # Ensure we have all required prices
        return {
            'gas': prices.get('gas', 0.0624),
            'electricity': prices.get('electricity', 0.245),
            'heat_network': prices.get('heat_network', 0.08)
        }

    # ==================== Carbon Calculations ====================

    def calculate_annual_carbon_emissions(
        self,
        annual_demand: Union[float, pd.Series],
        system_type: str = 'gas_boiler',
        year: str = 'current'
    ) -> Union[float, pd.Series]:
        """
        Calculate annual carbon emissions.

        Args:
            annual_demand: Annual heat demand in kWh/year
            system_type: 'gas_boiler', 'heat_pump', 'heat_network', 'electric'
            year: 'current', '2030', '2040'

        Returns:
            Annual CO2 emissions in kgCO2/year
        """
        # Get carbon factors
        if year == 'current':
            factors = self.carbon_factors.get('current', {})
        elif year == '2030':
            factors = self.carbon_factors.get('projected_2030', {})
        elif year == '2040':
            factors = self.carbon_factors.get('projected_2040', {})
        else:
            factors = self.carbon_factors.get('current', {})

        gas_carbon = factors.get('gas', 0.183)
        elec_carbon = factors.get('electricity', 0.233)

        # System efficiencies
        gas_boiler_eff = 0.85
        hp_scop = self.heat_pump_config.get('scop', 3.0)

        if system_type == 'gas_boiler':
            fuel_used = annual_demand / gas_boiler_eff
            return fuel_used * gas_carbon

        elif system_type == 'heat_pump':
            electricity_used = annual_demand / hp_scop
            return electricity_used * elec_carbon

        elif system_type == 'heat_network':
            # Assume 40% of gas carbon (60% reduction)
            return annual_demand * gas_carbon * 0.4

        elif system_type == 'electric':
            return annual_demand * elec_carbon

        else:
            logger.error(f"Unknown system type: {system_type}")
            return 0

    # ==================== Financial Calculations ====================

    def calculate_simple_payback(
        self,
        capital_cost: Union[float, pd.Series],
        annual_savings: Union[float, pd.Series]
    ) -> Union[float, pd.Series]:
        """
        Calculate simple payback period.

        Args:
            capital_cost: Upfront capital cost in £
            annual_savings: Annual bill savings in £/year

        Returns:
            Payback period in years (np.inf if savings <= 0)
        """
        if isinstance(annual_savings, pd.Series):
            payback = capital_cost / annual_savings
            payback[annual_savings <= 0] = np.inf
            return payback
        else:
            if annual_savings <= 0:
                return np.inf
            return capital_cost / annual_savings

    def calculate_discounted_payback(
        self,
        capital_cost: float,
        annual_savings: float,
        discount_rate: Optional[float] = None,
        max_years: int = 30
    ) -> float:
        """
        Calculate discounted payback period.

        Args:
            capital_cost: Upfront capital cost in £
            annual_savings: Annual bill savings in £/year
            discount_rate: Real discount rate (default: from config, 3.5%)
            max_years: Maximum years to check

        Returns:
            Payback period in years (max_years if never pays back)
        """
        if discount_rate is None:
            discount_rate = self.financial_config.get('discount_rate', 0.035)

        if annual_savings <= 0:
            return max_years

        cumulative = 0.0
        for year in range(1, max_years + 1):
            discounted = annual_savings / ((1 + discount_rate) ** year)
            cumulative += discounted
            if cumulative >= capital_cost:
                return year

        return max_years

    def calculate_npv(
        self,
        capital_cost: float,
        annual_savings: float,
        lifetime_years: int = 20,
        discount_rate: Optional[float] = None
    ) -> float:
        """
        Calculate Net Present Value.

        Args:
            capital_cost: Upfront capital cost in £
            annual_savings: Annual bill savings in £/year
            lifetime_years: Project lifetime in years
            discount_rate: Real discount rate (default: from config)

        Returns:
            NPV in £
        """
        if discount_rate is None:
            discount_rate = self.financial_config.get('discount_rate', 0.035)

        # Calculate present value of savings
        pv_savings = 0.0
        for year in range(1, lifetime_years + 1):
            pv_savings += annual_savings / ((1 + discount_rate) ** year)

        return pv_savings - capital_cost

    def calculate_lcoh(
        self,
        capital_cost: float,
        annual_running_cost: float,
        annual_heat_delivered: float,
        lifetime_years: int = 20,
        discount_rate: Optional[float] = None
    ) -> float:
        """
        Calculate Levelized Cost of Heat.

        Args:
            capital_cost: Upfront capital cost in £
            annual_running_cost: Annual running cost in £/year
            annual_heat_delivered: Annual heat delivered in kWh/year
            lifetime_years: System lifetime in years
            discount_rate: Real discount rate

        Returns:
            LCOH in £/kWh
        """
        if discount_rate is None:
            discount_rate = self.financial_config.get('discount_rate', 0.035)

        # Calculate annualized capital cost (capital recovery factor)
        crf = (discount_rate * (1 + discount_rate) ** lifetime_years) / \
              ((1 + discount_rate) ** lifetime_years - 1)
        annualized_capex = capital_cost * crf

        # Total annual cost
        total_annual_cost = annualized_capex + annual_running_cost

        # LCOH
        return total_annual_cost / annual_heat_delivered


# Convenience functions

def calculate_fabric_costs(
    df: pd.DataFrame,
    measures: List[str],
    config: Optional[Dict] = None
) -> pd.Series:
    """Convenience function for fabric cost calculation."""
    calc = CostCalculator(config)
    return calc.calculate_fabric_costs(df, measures)


def calculate_heat_pump_cost(
    include_radiator_upgrades: bool = False,
    include_cylinder: bool = False,
    config: Optional[Dict] = None
) -> float:
    """Convenience function for heat pump cost calculation."""
    calc = CostCalculator(config)
    return calc.calculate_heat_pump_cost(
        include_radiator_upgrades=include_radiator_upgrades,
        include_cylinder=include_cylinder
    )
