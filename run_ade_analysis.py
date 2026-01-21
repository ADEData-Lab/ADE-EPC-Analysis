"""
ADE EPC Analysis - Main Pipeline

Simplified pipeline for analyzing all domestic EPCs in England and Wales.
Focuses on four key policy metrics:
1. Heating fuel mix
2. Heat pump potential
3. Heat network potential
4. Demand reduction

Usage:
    python run_ade_analysis.py
"""

import sys
import random
from collections import Counter, defaultdict
from pathlib import Path
import pandas as pd
from loguru import logger
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.panel import Panel
from rich.prompt import Confirm
import time

# Add src to path
sys.path.append(str(Path(__file__).parent))

from config.config import (
    load_config,
    ensure_directories,
    DATA_RAW_DIR,
    DATA_PROCESSED_DIR,
    DATA_OUTPUTS_DIR,
    DATA_SUPPLEMENTARY_DIR,
)
from src.acquisition.epc_bulk_downloader import EPCBulkDownloader
from src.cleaning.data_validator import EPCDataValidator
from src.utils.geography_lookup import GeographyLookup
from src.analysis.heating_fuel_analysis import HeatingFuelAnalyzer
from src.analysis.heat_pump_potential import HeatPumpPotentialAnalyzer
from src.analysis.heat_network_potential import HeatNetworkPotentialAnalyzer
from src.analysis.demand_reduction_analysis import DemandReductionAnalyzer
from src.analysis.consumer_impact_analysis import ConsumerImpactAnalyzer
from src.analysis.policy_scenarios import PolicyScenarioAnalyzer
from src.spatial.postcode_geocoder import PostcodeGeocoder
from src.spatial.heat_network_zone_proximity import HeatNetworkZoneProximityAnalyzer
from src.utils.memory_utils import log_memory, MemoryMonitor

console = Console()


def load_existing_parquet(file_path: Path, description: str):
    """Prompt to reuse an existing parquet file and return its contents if confirmed."""

    if not file_path.exists():
        return None

    file_size_gb = file_path.stat().st_size / (1024**3)
    console.print(f"[green]✓[/green] Existing {description} found: {file_path.name}")
    console.print(f"  File size: {file_size_gb:.2f} GB")

    try:
        import pyarrow.parquet as pq
        metadata = pq.read_metadata(file_path)
        console.print(f"  Records: {metadata.num_rows:,}")
    except Exception as e:
        console.print(f"[yellow]⚠[/yellow] Could not read {description} metadata: {e}")

    use_existing = Confirm.ask(f"Use existing {description}?", default=True)

    if use_existing:
        try:
            df = pd.read_parquet(file_path)
            console.print(f"[green]✓[/green] Using existing {description}")
            return df
        except Exception as e:
            console.print(f"[yellow]⚠[/yellow] Failed to load existing {description}: {e}")
            console.print("[yellow]Recomputing...[/yellow]")

    return None


def iter_parquet_batches(file_path: Path, batch_size: int, columns: list[str] | None = None):
    """Yield DataFrame batches from a parquet file."""
    import pyarrow.parquet as pq

    parquet_file = pq.ParquetFile(file_path)
    for batch in parquet_file.iter_batches(batch_size=batch_size, columns=columns):
        yield batch.to_pandas()


def select_available_columns(file_path: Path, desired_columns: list[str]) -> list[str]:
    """Return available columns from parquet file that match desired columns."""
    import pyarrow.parquet as pq

    parquet_file = pq.ParquetFile(file_path)
    available = set(parquet_file.schema.names)
    return [col for col in desired_columns if col in available]


def select_fuel_column(df: pd.DataFrame) -> str | None:
    """Select the most appropriate fuel column."""
    for col in ['MAIN_FUEL', 'MAINHEAT_DESCRIPTION', 'MAIN_HEATING_FUEL']:
        if col in df.columns:
            return col
    return None


def apply_heat_pump_suitability(df: pd.DataFrame, policy_config: dict) -> pd.DataFrame:
    """Apply heat pump suitability tiers and fabric cost estimates in-place."""
    max_heat_demand = policy_config.get('max_heat_demand_kwh_m2', 150)

    df['hp_suitability_tier'] = 5
    df['hp_barriers'] = ''
    df['hp_fabric_cost_estimate'] = 0

    tier_1_mask = (
        (df['CURRENT_ENERGY_RATING'].isin(['A', 'B', 'C'])) &
        (df.get('ENERGY_CONSUMPTION_CURRENT', 999) < max_heat_demand)
    )
    df.loc[tier_1_mask, 'hp_suitability_tier'] = 1
    df.loc[tier_1_mask, 'hp_barriers'] = 'None - ready for installation'

    tier_2_mask = (
        (df['CURRENT_ENERGY_RATING'] == 'D') &
        (~tier_1_mask)
    )
    df.loc[tier_2_mask, 'hp_suitability_tier'] = 2
    df.loc[tier_2_mask, 'hp_barriers'] = 'Minor - loft insulation top-up recommended'
    df.loc[tier_2_mask, 'hp_fabric_cost_estimate'] = 1200

    tier_3_mask = (
        (df['CURRENT_ENERGY_RATING'] == 'E') &
        (~tier_1_mask) &
        (~tier_2_mask)
    )
    df.loc[tier_3_mask, 'hp_suitability_tier'] = 3
    df.loc[tier_3_mask, 'hp_barriers'] = 'Moderate - wall and loft insulation needed'
    df.loc[tier_3_mask, 'hp_fabric_cost_estimate'] = 4000

    tier_4_mask = (
        (df['CURRENT_ENERGY_RATING'] == 'F') &
        (~tier_1_mask) &
        (~tier_2_mask) &
        (~tier_3_mask)
    )
    df.loc[tier_4_mask, 'hp_suitability_tier'] = 4
    df.loc[tier_4_mask, 'hp_barriers'] = 'Major - solid wall insulation required'
    df.loc[tier_4_mask, 'hp_fabric_cost_estimate'] = 12000

    tier_5_mask = (
        (df['CURRENT_ENERGY_RATING'] == 'G') |
        (df.get('ENERGY_CONSUMPTION_CURRENT', 0) > max_heat_demand * 1.5)
    )
    df.loc[tier_5_mask, 'hp_suitability_tier'] = 5
    df.loc[tier_5_mask, 'hp_barriers'] = 'Challenging - extensive fabric upgrade needed'
    df.loc[tier_5_mask, 'hp_fabric_cost_estimate'] = 15000

    return df


def update_reservoir(sample: list[float], total_seen: int, values: pd.Series, max_size: int, rng: random.Random) -> int:
    """Update reservoir sample with new values."""
    for value in values.dropna().tolist():
        total_seen += 1
        if len(sample) < max_size:
            sample.append(value)
        else:
            idx = rng.randint(1, total_seen)
            if idx <= max_size:
                sample[idx - 1] = value
    return total_seen


def run_chunked_pipeline(validated_path: Path, batch_size: int = 100000):
    """Run phases 3-5 using chunked processing to reduce memory use."""
    console.print()
    console.print("[cyan]Running chunked processing for phases 3-5...[/cyan]")

    log_memory("Pipeline start")

    output_file = DATA_PROCESSED_DIR / "epc_england_wales_enriched.parquet"
    source_path = validated_path
    needs_enrichment = True

    if output_file.exists():
        console.print(f"[green]✓[/green] Existing enriched dataset found: {output_file.name}")
        if Confirm.ask("Use existing enriched dataset for chunked analysis?", default=True):
            source_path = output_file
            needs_enrichment = False

    geo = GeographyLookup()
    fuel_analyzer = HeatingFuelAnalyzer()
    hp_analyzer = HeatPumpPotentialAnalyzer()
    hn_analyzer = HeatNetworkPotentialAnalyzer()
    dr_analyzer = DemandReductionAnalyzer()
    ci_analyzer = ConsumerImpactAnalyzer()
    ps_analyzer = PolicyScenarioAnalyzer()

    rng = random.Random(42)

    fuel_counts = Counter()
    off_gas_count = 0
    electrification_count = 0
    total_properties = 0
    fuel_col = None

    hp_tier_counts = Counter()
    hp_fabric_cost_sum = 0.0

    local_authority_heat = defaultdict(lambda: {'heat_demand_kwh': 0.0, 'property_count': 0})
    constituency_heat = defaultdict(lambda: {'heat_demand_kwh': 0.0, 'property_count': 0})

    fabric_needs = Counter()
    wall_type_counts = Counter()
    energy_consumption_sum = 0.0
    floor_area_sum = 0.0
    epc_counts = Counter()

    annual_bill_sum = 0.0
    annual_emissions_sum = 0.0
    annual_energy_sum = 0.0
    annual_bill_sample = []
    annual_emissions_sample = []
    annual_bill_seen = 0
    annual_emissions_seen = 0

    constituency_fuel = defaultdict(lambda: Counter())
    constituency_counts = Counter()
    constituency_hp_tiers = defaultdict(lambda: Counter())
    constituency_epc = defaultdict(lambda: Counter())
    constituency_sap_sum = defaultdict(float)
    constituency_sap_count = Counter()
    constituency_bill_sum = defaultdict(float)
    constituency_emissions_sum = defaultdict(float)
    constituency_bill_sample = defaultdict(list)
    constituency_emissions_sample = defaultdict(list)
    constituency_bill_seen = Counter()
    constituency_emissions_seen = Counter()
    constituency_floor_area_sum = defaultdict(float)

    proximity_sample = []
    proximity_seen = 0

    import pyarrow as pa
    import pyarrow.parquet as pq
    writer = None

    desired_columns = [
        'POSTCODE',
        'LOCAL_AUTHORITY',
        'LOCAL_AUTHORITY_LABEL',
        'local_authority_name',
        'region_name',
        'constituency_name',
        'MAIN_FUEL',
        'MAINHEAT_DESCRIPTION',
        'MAIN_HEATING_FUEL',
        'CURRENT_ENERGY_RATING',
        'ENERGY_CONSUMPTION_CURRENT',
        'TOTAL_FLOOR_AREA',
        'ROOF_DESCRIPTION',
        'wall_type',
        'wall_insulated',
        'WINDOWS_DESCRIPTION',
        'FLOOR_DESCRIPTION',
        'CURRENT_ENERGY_EFFICIENCY',
    ]
    selected_columns = select_available_columns(source_path, desired_columns)
    if not selected_columns:
        raise ValueError(f"No required columns found in {source_path}")

    console.print(f"[cyan]Chunk size:[/cyan] {batch_size:,} rows")
    console.print(f"[cyan]Columns loaded:[/cyan] {len(selected_columns)}")

    chunk_num = 0
    for df in iter_parquet_batches(source_path, batch_size=batch_size, columns=selected_columns):
        chunk_num += 1

        if chunk_num % 5 == 1:  # Log every 5th chunk
            log_memory(f"Processing chunk {chunk_num} ({len(df):,} rows)", level="debug")
        if needs_enrichment:
            df = geo.enrich_epc_data(df)

        if fuel_col is None:
            fuel_col = select_fuel_column(df)

        if fuel_col:
            df['fuel_category'] = df[fuel_col].apply(fuel_analyzer.categorize_fuel_type)
            fuel_counts.update(df['fuel_category'].value_counts().to_dict())
            off_gas_count += (df['fuel_category'] != 'mains_gas').sum()
            electrification_count += df['fuel_category'].isin(['electric', 'renewable']).sum()

        if 'CURRENT_ENERGY_RATING' in df.columns:
            df = apply_heat_pump_suitability(df, hp_analyzer.policy_config)
            hp_tier_counts.update(df['hp_suitability_tier'].value_counts().to_dict())
            hp_fabric_cost_sum += df['hp_fabric_cost_estimate'].sum()

        if 'ENERGY_CONSUMPTION_CURRENT' in df.columns:
            df['annual_heat_demand_kwh'] = df['ENERGY_CONSUMPTION_CURRENT']
        elif 'TOTAL_FLOOR_AREA' in df.columns:
            df['annual_heat_demand_kwh'] = df['TOTAL_FLOOR_AREA'] * 100
        else:
            df['annual_heat_demand_kwh'] = 1000

        for la, values in df.groupby('local_authority_name')['annual_heat_demand_kwh'].agg(['sum', 'count']).iterrows():
            local_authority_heat[la]['heat_demand_kwh'] += values['sum']
            local_authority_heat[la]['property_count'] += int(values['count'])

        if 'constituency_name' in df.columns:
            for const, values in df.groupby('constituency_name')['annual_heat_demand_kwh'].agg(['sum', 'count']).iterrows():
                constituency_heat[const]['heat_demand_kwh'] += values['sum']
                constituency_heat[const]['property_count'] += int(values['count'])

        if 'ROOF_DESCRIPTION' in df.columns:
            fabric_needs['loft'] += df['ROOF_DESCRIPTION'].str.contains(
                'no insulation|<100mm|100mm|150mm|200mm',
                case=False,
                na=False,
                regex=True
            ).sum()

        if 'wall_type' in df.columns and 'wall_insulated' in df.columns:
            needs_wall = ~df['wall_insulated']
            fabric_needs['wall'] += needs_wall.sum()
            wall_type_counts.update(df.loc[needs_wall, 'wall_type'].value_counts().to_dict())

        if 'WINDOWS_DESCRIPTION' in df.columns:
            fabric_needs['glazing'] += df['WINDOWS_DESCRIPTION'].str.contains(
                'single',
                case=False,
                na=False
            ).sum()

        if 'FLOOR_DESCRIPTION' in df.columns:
            fabric_needs['floor'] += (~df['FLOOR_DESCRIPTION'].str.contains('insulated', case=False, na=False)).sum()

        if 'ENERGY_CONSUMPTION_CURRENT' in df.columns:
            energy_consumption_sum += df['ENERGY_CONSUMPTION_CURRENT'].sum()
        if 'TOTAL_FLOOR_AREA' in df.columns:
            floor_area_sum += df['TOTAL_FLOOR_AREA'].sum()

        if 'CURRENT_ENERGY_RATING' in df.columns:
            epc_counts.update(df['CURRENT_ENERGY_RATING'].value_counts().to_dict())

        total_properties += len(df)

        if 'CURRENT_ENERGY_EFFICIENCY' in df.columns and 'constituency_name' in df.columns:
            sap_group = df.groupby('constituency_name')['CURRENT_ENERGY_EFFICIENCY'].agg(['sum', 'count'])
            for const, values in sap_group.iterrows():
                constituency_sap_sum[const] += values['sum']
                constituency_sap_count[const] += int(values['count'])

        if 'constituency_name' in df.columns:
            constituency_counts.update(df['constituency_name'].value_counts().to_dict())

        if fuel_col and 'constituency_name' in df.columns:
            for const, counts in df.groupby('constituency_name')['fuel_category'].value_counts().groupby(level=0):
                constituency_fuel[const].update(counts.droplevel(0).to_dict())

        if 'hp_suitability_tier' in df.columns and 'constituency_name' in df.columns:
            for const, counts in df.groupby('constituency_name')['hp_suitability_tier'].value_counts().groupby(level=0):
                constituency_hp_tiers[const].update(counts.droplevel(0).to_dict())

        if 'CURRENT_ENERGY_RATING' in df.columns and 'constituency_name' in df.columns:
            for const, counts in df.groupby('constituency_name')['CURRENT_ENERGY_RATING'].value_counts().groupby(level=0):
                constituency_epc[const].update(counts.droplevel(0).to_dict())

        if 'ENERGY_CONSUMPTION_CURRENT' in df.columns:
            df['annual_energy_kwh'] = df['ENERGY_CONSUMPTION_CURRENT']
        elif 'TOTAL_FLOOR_AREA' in df.columns:
            df['annual_energy_kwh'] = df['TOTAL_FLOOR_AREA'] * 120
        else:
            df['annual_energy_kwh'] = 12000
        annual_energy_sum += df['annual_energy_kwh'].sum()

        current_prices = ci_analyzer.energy_prices.get('current', {})
        gas_price = current_prices.get('gas', 0.0624)
        elec_price = current_prices.get('electricity', 0.26)

        if 'fuel_category' in df.columns:
            gas_mask = df['fuel_category'] == 'mains_gas'
            elec_mask = df['fuel_category'].isin(['electric', 'renewable'])
            other_mask = ~gas_mask & ~elec_mask

            df.loc[gas_mask, 'annual_bill'] = df.loc[gas_mask, 'annual_energy_kwh'] / 0.85 * gas_price
            df.loc[elec_mask, 'annual_bill'] = df.loc[elec_mask, 'annual_energy_kwh'] * elec_price
            df.loc[other_mask, 'annual_bill'] = df.loc[other_mask, 'annual_energy_kwh'] / 0.85 * gas_price
        else:
            df['annual_bill'] = df['annual_energy_kwh'] / 0.85 * gas_price

        df['annual_bill'] = df['annual_bill'] + 100
        annual_bill_sum += df['annual_bill'].sum()

        current_factors = ci_analyzer.carbon_factors.get('current', {})
        gas_carbon = current_factors.get('gas', 0.183)
        elec_carbon = current_factors.get('electricity', 0.233)

        if 'fuel_category' in df.columns:
            gas_mask = df['fuel_category'] == 'mains_gas'
            elec_mask = df['fuel_category'].isin(['electric', 'renewable'])
            other_mask = ~gas_mask & ~elec_mask

            df.loc[gas_mask, 'annual_emissions_kg'] = df.loc[gas_mask, 'annual_energy_kwh'] / 0.85 * gas_carbon
            df.loc[elec_mask, 'annual_emissions_kg'] = df.loc[elec_mask, 'annual_energy_kwh'] * elec_carbon
            df.loc[other_mask, 'annual_emissions_kg'] = df.loc[other_mask, 'annual_energy_kwh'] / 0.85 * gas_carbon
        else:
            df['annual_emissions_kg'] = df['annual_energy_kwh'] / 0.85 * gas_carbon

        df['annual_emissions_tonnes'] = df['annual_emissions_kg'] / 1000
        annual_emissions_sum += df['annual_emissions_tonnes'].sum()

        annual_bill_seen = update_reservoir(annual_bill_sample, annual_bill_seen, df['annual_bill'], 100000, rng)
        annual_emissions_seen = update_reservoir(annual_emissions_sample, annual_emissions_seen, df['annual_emissions_tonnes'], 100000, rng)

        if 'constituency_name' in df.columns:
            for const, group in df.groupby('constituency_name'):
                constituency_bill_sum[const] += group['annual_bill'].sum()
                constituency_emissions_sum[const] += group['annual_emissions_tonnes'].sum()
                if 'TOTAL_FLOOR_AREA' in group.columns:
                    constituency_floor_area_sum[const] += group['TOTAL_FLOOR_AREA'].sum()
                constituency_bill_seen[const] = update_reservoir(
                    constituency_bill_sample[const],
                    constituency_bill_seen[const],
                    group['annual_bill'],
                    500,
                    rng
                )
                constituency_emissions_seen[const] = update_reservoir(
                    constituency_emissions_sample[const],
                    constituency_emissions_seen[const],
                    group['annual_emissions_tonnes'],
                    500,
                    rng
                )

        if 'POSTCODE' in df.columns:
            proximity_seen = update_reservoir(proximity_sample, proximity_seen, df['POSTCODE'], 50000, rng)

        if needs_enrichment:
            table = pa.Table.from_pandas(df, preserve_index=False)
            if writer is None:
                writer = pq.ParquetWriter(output_file, table.schema)
            writer.write_table(table)

    if writer is not None:
        writer.close()
        console.print(f"[green]✓[/green] Enriched data saved: {output_file}")

    log_memory("After chunked processing")

    fuel_percentages = {k: v / total_properties * 100 for k, v in fuel_counts.items()}
    fuel_results = {
        'total_properties': total_properties,
        'fuel_counts': dict(fuel_counts),
        'fuel_percentages': fuel_percentages,
        'fuel_category_column': fuel_col
    }

    off_gas_breakdown = {k: v for k, v in fuel_counts.items() if k != 'mains_gas'}
    off_gas_results = {
        'total_off_gas': off_gas_count,
        'percentage_off_gas': off_gas_count / total_properties * 100 if total_properties else 0,
        'breakdown': off_gas_breakdown
    }

    electrification_results = {
        'electrification_rate': electrification_count / total_properties * 100 if total_properties else 0,
        'electric_properties': int(electrification_count),
        'total_properties': total_properties
    }

    fuel_analyzer.results = {
        'fuel_mix': fuel_results,
        'off_gas': off_gas_results,
        'electrification': electrification_results
    }
    fuel_analyzer.save_results()

    tier_percentages = {k: v / total_properties * 100 for k, v in hp_tier_counts.items()}
    barrier_results = {
        'tier_counts': dict(hp_tier_counts),
        'tier_percentages': tier_percentages,
        'barriers': {
            'poor_fabric': int(sum(v for k, v in hp_tier_counts.items() if k >= 3)),
            'very_poor_fabric': int(sum(v for k, v in hp_tier_counts.items() if k >= 4)),
            'ready_or_minor_work': int(sum(v for k, v in hp_tier_counts.items() if k <= 2)),
        },
        'avg_fabric_cost_per_property': float(hp_fabric_cost_sum / total_properties) if total_properties else 0,
        'total_fabric_investment_needed': float(hp_fabric_cost_sum),
    }

    hp_analyzer.results = {
        'barriers': barrier_results
    }
    hp_analyzer.save_results()

    local_authority_df = pd.DataFrame([
        {
            'local_authority_name': name,
            'property_count': data['property_count'],
            'total_heat_demand_gwh': data['heat_demand_kwh'] / 1e6,
            'heat_density_proxy': data['property_count'],
            'using_proxy': True
        }
        for name, data in local_authority_heat.items()
        if pd.notna(name)
    ])

    if not local_authority_df.empty:
        local_authority_df['density_tier'] = local_authority_df['heat_density_proxy'].apply(
            lambda x: hn_analyzer.classify_density_tier(x, use_proxy=True)
        )

        tier_summary = local_authority_df.groupby('density_tier').agg({
            'property_count': 'sum',
            'total_heat_demand_gwh': 'sum'
        }).reset_index()
        tier_summary['connection_cost_m'] = tier_summary['property_count'] * 5000 / 1e6

        viable_tiers = tier_summary[tier_summary['density_tier'].isin(['high', 'medium'])]
        network_results = {
            'total_viable_properties': int(viable_tiers['property_count'].sum()),
            'total_viable_heat_demand_gwh': float(viable_tiers['total_heat_demand_gwh'].sum()),
            'total_connection_cost_bn': float(viable_tiers['connection_cost_m'].sum() / 1000),
            'tier_breakdown': tier_summary.to_dict('records'),
            'pct_viable': float(viable_tiers['property_count'].sum() / total_properties * 100) if total_properties else 0
        }
    else:
        network_results = {
            'total_viable_properties': 0,
            'total_viable_heat_demand_gwh': 0.0,
            'total_connection_cost_bn': 0.0,
            'tier_breakdown': [],
            'pct_viable': 0.0
        }

    hn_analyzer.results = {
        'network_potential': network_results
    }
    hn_analyzer.save_results()

    fabric_results = {
        'total_properties': total_properties,
        'needs_improvement': dict(fabric_needs),
        'wall_insulation_by_type': dict(wall_type_counts)
    }

    if energy_consumption_sum > 0:
        current_demand = energy_consumption_sum / 1e6
    elif floor_area_sum > 0:
        current_demand = floor_area_sum * 100 / 1e6
    else:
        current_demand = 0

    avg_demand = current_demand * 1e6 / total_properties if total_properties else 0
    loft_savings_gwh = total_properties * 0.5 * avg_demand * dr_analyzer.FABRIC_MEASURES['loft_insulation']['heat_saving_pct'] / 1e6 if total_properties else 0
    wall_savings_gwh = total_properties * 0.3 * avg_demand * 0.25 / 1e6 if total_properties else 0
    glazing_savings_gwh = total_properties * 0.2 * avg_demand * dr_analyzer.FABRIC_MEASURES['double_glazing']['heat_saving_pct'] / 1e6 if total_properties else 0
    total_savings_gwh = loft_savings_gwh + wall_savings_gwh + glazing_savings_gwh

    savings_results = {
        'current_total_demand_gwh': float(current_demand),
        'post_improvement_demand_gwh': float(current_demand - total_savings_gwh),
        'total_savings_gwh': float(total_savings_gwh),
        'total_co2_savings_kt': float(total_savings_gwh * 0.183),
        'total_bill_savings_m': float(total_savings_gwh * 1e6 * 0.0624 / 1e6),
        'pct_reduction': float(total_savings_gwh / current_demand * 100) if current_demand > 0 else 0
    }

    epc_bands = dr_analyzer.EPC_BANDS
    target_epc = dr_analyzer.target_epc
    better_bands = epc_bands[epc_bands.index(target_epc):]
    already_compliant = sum(epc_counts.get(band, 0) for band in better_bands)
    improvement_needed = {
        'already_compliant': already_compliant,
        'one_band': epc_counts.get('D', 0),
        'two_bands': epc_counts.get('E', 0),
        'three_plus_bands': epc_counts.get('F', 0) + epc_counts.get('G', 0)
    }
    needs_improvement = total_properties - already_compliant
    total_cost_bn = (
        improvement_needed['one_band'] * 3000 +
        improvement_needed['two_bands'] * 8000 +
        improvement_needed['three_plus_bands'] * 15000
    ) / 1e9

    path_results = {
        'target_band': target_epc,
        'total_properties': total_properties,
        'already_compliant': improvement_needed['already_compliant'],
        'pct_compliant': float(already_compliant / total_properties * 100) if total_properties else 0,
        'needs_improvement': int(needs_improvement),
        'improvement_breakdown': improvement_needed,
        'estimated_total_cost_bn': float(total_cost_bn),
        'avg_cost_per_property': float(total_cost_bn * 1e9 / needs_improvement) if needs_improvement else 0
    }

    national_results = {
        'sample_size': total_properties,
        'national_stock_estimate': dr_analyzer.NATIONAL_HOUSING_STOCK,
        'measures': {}
    }

    if total_properties > 0:
        loft_count = fabric_needs.get('loft', 0)
        loft_pct = loft_count / total_properties
        national_loft = int(dr_analyzer.NATIONAL_HOUSING_STOCK * loft_pct)
        national_results['measures']['loft_insulation'] = {
            'sample_count': loft_count,
            'sample_percent': round(loft_pct * 100, 1),
            'national_estimate': national_loft,
            'cost_per_home': 1200,
            'total_investment_bn': round(national_loft * 1200 / 1e9, 1)
        }

    total_investment = sum(
        measure.get('total_investment_bn', 0)
        for measure in national_results['measures'].values()
    )
    national_results['total_fabric_investment_bn'] = round(total_investment, 1)
    jobs_per_bn = 12000
    national_results['estimated_jobs'] = int(total_investment * jobs_per_bn)
    national_results['ade_jobs_target_2030'] = 200000

    dr_analyzer.results = {
        'fabric_potential': fabric_results,
        'savings_potential': savings_results,
        'path_to_epc_c': path_results,
        'national_investment': national_results
    }
    dr_analyzer.save_results()

    annual_bill_series = pd.Series(annual_bill_sample)
    annual_emissions_series = pd.Series(annual_emissions_sample)

    household_bills = {
        'total_properties': total_properties,
        'avg_annual_bill': float(annual_bill_sum / total_properties) if total_properties else 0,
        'median_annual_bill': float(annual_bill_series.median()) if not annual_bill_series.empty else 0,
        'bill_25th_percentile': float(annual_bill_series.quantile(0.25)) if not annual_bill_series.empty else 0,
        'bill_75th_percentile': float(annual_bill_series.quantile(0.75)) if not annual_bill_series.empty else 0,
        'total_annual_bills_bn': float(annual_bill_sum / 1e9),
        'avg_energy_consumption_kwh': float(annual_energy_sum / total_properties) if total_properties else 0,
        'gas_price_used': gas_price,
        'electricity_price_used': elec_price
    }

    household_emissions = {
        'avg_emissions_tonnes': float(annual_emissions_sum / total_properties) if total_properties else 0,
        'median_emissions_tonnes': float(annual_emissions_series.median()) if not annual_emissions_series.empty else 0,
        'total_emissions_mt': float(annual_emissions_sum / 1e6),
        'emissions_25th_percentile': float(annual_emissions_series.quantile(0.25)) if not annual_emissions_series.empty else 0,
        'emissions_75th_percentile': float(annual_emissions_series.quantile(0.75)) if not annual_emissions_series.empty else 0,
        'gas_carbon_factor': gas_carbon,
        'electricity_carbon_factor': elec_carbon
    }

    avg_demand_kwh = annual_energy_sum / total_properties if total_properties else 12000
    hp_scop = ci_analyzer.config.get('heat_pump', {}).get('scop', 3.0)
    gas_boiler_efficiency = 0.85

    price_scenarios = ci_analyzer.financial.get('price_scenarios', {})
    running_cost_comparison = {
        'avg_heat_demand_kwh': float(avg_demand_kwh),
        'heat_pump_scop': hp_scop,
        'gas_boiler_efficiency': gas_boiler_efficiency,
        'scenarios': {}
    }

    for scenario_name, prices in price_scenarios.items():
        gas_price_s = prices.get('gas', 0.0624)
        elec_price_s = prices.get('electricity', 0.26)
        gas_cost = (avg_demand_kwh / gas_boiler_efficiency) * gas_price_s
        hp_cost = (avg_demand_kwh / hp_scop) * elec_price_s
        running_cost_comparison['scenarios'][scenario_name] = {
            'name': prices.get('name', scenario_name),
            'gas_price': gas_price_s,
            'electricity_price': elec_price_s,
            'gas_boiler_annual_cost': round(gas_cost, 0),
            'heat_pump_annual_cost': round(hp_cost, 0),
            'hp_vs_gas_difference': round(hp_cost - gas_cost, 0),
            'heat_pump_cheaper': hp_cost < gas_cost,
            'annual_savings': round(abs(gas_cost - hp_cost), 0),
            'savings_percent': round((abs(gas_cost - hp_cost) / gas_cost * 100), 1) if gas_cost else 0
        }

    ci_analyzer.results = {
        'household_bills': household_bills,
        'household_emissions': household_emissions,
        'running_cost_comparison': running_cost_comparison
    }
    ci_analyzer.save_results()

    suitable_properties = sum(epc_counts.get(band, 0) for band in ['A', 'B', 'C', 'D'])
    existing_hp = fuel_counts.get('renewable', 0)
    gas_properties = fuel_counts.get('mains_gas', 0)
    low_carbon = fuel_counts.get('electric', 0) + fuel_counts.get('renewable', 0) + fuel_counts.get('heat_network', 0)

    current_year = time.localtime().tm_year
    target_year = 2028
    current_rate = ps_analyzer.POLICY_TARGETS['heat_pump_current_rate']
    target_rate = ps_analyzer.POLICY_TARGETS['heat_pump_target_2028']
    years_remaining = target_year - current_year
    multiplier_needed = target_rate / current_rate if current_rate else 0
    cagr_needed = (target_rate / current_rate) ** (1 / years_remaining) - 1 if years_remaining > 0 else 0

    installation_rate_results = {
        'current_annual_rate': current_rate,
        'target_annual_rate_2028': target_rate,
        'multiplier_needed': round(multiplier_needed, 1),
        'years_to_target': years_remaining,
        'cagr_needed_percent': round(cagr_needed * 100, 1),
        'uk_ranking_heat_pumps': '21st of 21 (last in Europe)',
        'suitable_properties_in_data': int(suitable_properties),
        'existing_heat_pumps_estimate': int(existing_hp),
        'remaining_potential': int(suitable_properties - existing_hp),
        'years_to_complete_at_current_rate': round((suitable_properties - existing_hp) / current_rate, 0) if current_rate else 0,
        'years_to_complete_at_target_rate': round((suitable_properties - existing_hp) / target_rate, 0) if target_rate else 0
    }

    phaseout_year = ps_analyzer.POLICY_TARGETS['boiler_phaseout_year']
    years_remaining = phaseout_year - current_year
    annual_conversion_needed = gas_properties / years_remaining if years_remaining > 0 else gas_properties
    multiplier_vs_current = annual_conversion_needed / current_rate if current_rate else 0
    boiler_phaseout_results = {
        'phaseout_year': phaseout_year,
        'years_remaining': years_remaining,
        'total_properties': int(total_properties),
        'gas_heated_properties': int(gas_properties),
        'gas_percentage': round(gas_properties / total_properties * 100, 1) if total_properties else 0,
        'already_low_carbon': int(low_carbon),
        'conversions_needed': int(gas_properties),
        'annual_conversions_needed': int(annual_conversion_needed),
        'vs_current_hp_rate': f"{multiplier_vs_current:.0f}x current rate",
        'implied_monthly_conversions': int(annual_conversion_needed / 12) if years_remaining > 0 else 0,
        'implied_daily_conversions': int(annual_conversion_needed / 365) if years_remaining > 0 else 0
    }

    current_prices = ps_analyzer.financial.get('price_scenarios', {}).get('baseline', {})
    rebalanced_prices = ps_analyzer.financial.get('price_scenarios', {}).get('rebalanced', {})
    gas_cost_current = (avg_demand_kwh / 0.85) * current_prices.get('gas', 0.0624)
    hp_cost_current = (avg_demand_kwh / hp_scop) * current_prices.get('electricity', 0.26)
    gas_cost_rebalanced = (avg_demand_kwh / 0.85) * rebalanced_prices.get('gas', 0.10)
    hp_cost_rebalanced = (avg_demand_kwh / hp_scop) * rebalanced_prices.get('electricity', 0.15)

    price_rebalancing_results = {
        'avg_heat_demand_kwh': float(avg_demand_kwh),
        'current_prices': {
            'gas_price': current_prices.get('gas', 0.0624),
            'electricity_price': current_prices.get('electricity', 0.26),
            'gas_boiler_annual_cost': round(gas_cost_current, 0),
            'heat_pump_annual_cost': round(hp_cost_current, 0),
            'hp_vs_gas_difference': round(hp_cost_current - gas_cost_current, 0),
            'hp_premium_percent': round((hp_cost_current / gas_cost_current - 1) * 100, 1) if gas_cost_current else 0
        },
        'rebalanced_prices': {
            'gas_price': rebalanced_prices.get('gas', 0.10),
            'electricity_price': rebalanced_prices.get('electricity', 0.15),
            'gas_boiler_annual_cost': round(gas_cost_rebalanced, 0),
            'heat_pump_annual_cost': round(hp_cost_rebalanced, 0),
            'hp_vs_gas_difference': round(hp_cost_rebalanced - gas_cost_rebalanced, 0),
            'hp_saving_percent': round((1 - hp_cost_rebalanced / gas_cost_rebalanced) * 100, 1) if gas_cost_rebalanced else 0
        },
        'policy_impact': {
            'current_hp_premium': round(hp_cost_current - gas_cost_current, 0),
            'rebalanced_hp_saving': round(gas_cost_rebalanced - hp_cost_rebalanced, 0),
            'total_improvement': round((hp_cost_current - gas_cost_current) - (hp_cost_rebalanced - gas_cost_rebalanced), 0)
        }
    }

    needs_insulation = epc_counts.get('D', 0) + epc_counts.get('E', 0) + epc_counts.get('F', 0) + epc_counts.get('G', 0)
    needs_heating_upgrade = fuel_counts.get('mains_gas', 0) + fuel_counts.get('oil', 0) + fuel_counts.get('lpg', 0) + fuel_counts.get('coal', 0)
    retrofit_investment_bn = (needs_insulation * 8000) / 1e9
    heating_investment_bn = (needs_heating_upgrade * 12000) / 1e9
    total_investment_bn = retrofit_investment_bn + heating_investment_bn
    retrofit_jobs = retrofit_investment_bn * 1000 * 12
    heating_jobs = heating_investment_bn * 1000 * 4
    total_jobs = retrofit_jobs + heating_jobs

    job_creation_results = {
        'properties_needing_retrofit': int(needs_insulation),
        'properties_needing_heating_upgrade': int(needs_heating_upgrade),
        'estimated_retrofit_investment_bn': round(retrofit_investment_bn, 1),
        'estimated_heating_investment_bn': round(heating_investment_bn, 1),
        'total_investment_potential_bn': round(total_investment_bn, 1),
        'jobs_from_retrofit': int(retrofit_jobs),
        'jobs_from_heating': int(heating_jobs),
        'total_jobs_potential': int(total_jobs),
        'ade_target_2030': ps_analyzer.POLICY_TARGETS['jobs_target_2030'],
        'vs_ade_target': f"{total_jobs / ps_analyzer.POLICY_TARGETS['jobs_target_2030'] * 100:.0f}% of ADE target" if ps_analyzer.POLICY_TARGETS['jobs_target_2030'] else "0%"
    }

    ps_analyzer.results = {
        'price_rebalancing': price_rebalancing_results,
        'installation_rates': installation_rate_results,
        'boiler_phaseout': boiler_phaseout_results,
        'job_creation': job_creation_results
    }
    ps_analyzer.save_results()

    results = {
        'fuel': fuel_analyzer.results,
        'heat_pump': hp_analyzer.results,
        'heat_network': hn_analyzer.results,
        'demand_reduction': dr_analyzer.results,
        'consumer_impact': ci_analyzer.results,
        'policy_scenarios': ps_analyzer.results
    }

    constituency_outputs = {}
    if constituency_counts:
        fuel_rows = []
        for const, counts in constituency_fuel.items():
            total = constituency_counts.get(const, 0)
            row = {'geography': const, 'geography_level': 'constituency', 'total_properties': total}
            for category in fuel_analyzer.FUEL_CATEGORIES.keys():
                row[category] = counts.get(category, 0) / total * 100 if total else 0
            fuel_rows.append(row)
        fuel_df = pd.DataFrame(fuel_rows)
        output_path = DATA_OUTPUTS_DIR / "constituency_fuel_mix.csv"
        fuel_df.to_csv(output_path, index=False)
        constituency_outputs['fuel_mix'] = output_path

        hp_rows = []
        for const, counts in constituency_hp_tiers.items():
            total = constituency_counts.get(const, 0)
            hp_rows.append({
                'geography': const,
                'total_properties': total,
                'tier_1_ready': counts.get(1, 0),
                'tier_2_minor': counts.get(2, 0),
                'tier_3_moderate': counts.get(3, 0),
                'tier_4_major': counts.get(4, 0),
                'tier_5_challenging': counts.get(5, 0),
                'pct_ready_or_minor': (counts.get(1, 0) + counts.get(2, 0)) / total * 100 if total else 0
            })
        hp_df = pd.DataFrame(hp_rows)
        output_path = DATA_OUTPUTS_DIR / "constituency_heat_pump_potential.csv"
        hp_df.to_csv(output_path, index=False)
        constituency_outputs['heat_pump'] = output_path

        hn_rows = []
        for const, data in constituency_heat.items():
            hn_rows.append({
                'geography': const,
                'property_count': data['property_count'],
                'total_heat_demand_gwh': data['heat_demand_kwh'] / 1e6,
                'heat_density_proxy': data['property_count'],
                'density_tier': hn_analyzer.classify_density_tier(data['property_count'], use_proxy=True)
            })
        hn_df = pd.DataFrame(hn_rows)
        output_path = DATA_OUTPUTS_DIR / "constituency_heat_network_potential.csv"
        hn_df.to_csv(output_path, index=False)
        constituency_outputs['heat_network'] = output_path

        epc_rows = []
        for const, counts in constituency_epc.items():
            total = constituency_counts.get(const, 0)
            compliant = sum(counts.get(band, 0) for band in ['A', 'B', 'C'])
            row = {'constituency_name': const, 'total_properties': total}
            for band, count in counts.items():
                row[band] = count / total * 100 if total else 0
            row['pct_epc_c_plus'] = compliant / total * 100 if total else 0
            if constituency_sap_count.get(const):
                row['avg_sap_score'] = constituency_sap_sum[const] / constituency_sap_count[const]
            epc_rows.append(row)
        epc_df = pd.DataFrame(epc_rows)
        output_path = DATA_OUTPUTS_DIR / "constituency_epc_distribution.csv"
        epc_df.to_csv(output_path, index=False)
        constituency_outputs['epc_distribution'] = output_path

        consumer_rows = []
        for const, total in constituency_counts.items():
            bills = pd.Series(constituency_bill_sample[const])
            emissions = pd.Series(constituency_emissions_sample[const])
            consumer_rows.append({
                'constituency_name': const,
                'avg_annual_bill': constituency_bill_sum[const] / total if total else 0,
                'median_annual_bill': float(bills.median()) if not bills.empty else 0,
                'total_annual_bills': constituency_bill_sum[const],
                'avg_emissions_tonnes': constituency_emissions_sum[const] / total if total else 0,
                'total_emissions_tonnes': constituency_emissions_sum[const],
                'total_properties': total
            })
        consumer_df = pd.DataFrame(consumer_rows)
        output_path = DATA_OUTPUTS_DIR / "constituency_consumer_impact.csv"
        consumer_df.to_csv(output_path, index=False)
        constituency_outputs['consumer_impact'] = output_path

        summary_rows = []
        for const, total in constituency_counts.items():
            summary_rows.append({
                'constituency_name': const,
                'total_properties': total,
                'avg_floor_area': constituency_floor_area_sum[const] / total if total else 0,
                'pct_gas_heated': (constituency_fuel[const].get('mains_gas', 0) / total * 100) if total else 0,
                'pct_hp_ready': (constituency_hp_tiers[const].get(1, 0) + constituency_hp_tiers[const].get(2, 0)) / total * 100 if total else 0
            })
        summary_df = pd.DataFrame(summary_rows)
        output_path = DATA_OUTPUTS_DIR / "constituency_summary.csv"
        summary_df.to_csv(output_path, index=False)
        constituency_outputs['summary'] = output_path

    proximity_results = None
    if proximity_sample:
        sample_df = pd.DataFrame({'POSTCODE': proximity_sample})
        _, proximity_results = phase_3b_heat_network_proximity(sample_df)

    return results, constituency_outputs, proximity_results


def print_header():
    """Print welcome header."""
    console.clear()
    console.print(Panel.fit(
        "[bold cyan]ADE EPC Analysis[/bold cyan]\n"
        "[white]England & Wales Domestic EPC Analysis[/white]\n"
        "[dim]Heat Decarbonisation Policy Metrics[/dim]",
        border_style="cyan"
    ))
    console.print()


def phase_1_data_acquisition():
    """Phase 1: Download and extract EPC bulk data."""
    console.print()
    console.print(Panel("[bold]Phase 1: Data Acquisition[/bold]", border_style="blue"))
    console.print()

    console.print("[cyan]This phase downloads bulk EPC data from DESNZ[/cyan]")
    console.print("[yellow]Warning: Files are large (~5GB compressed, ~20GB uncompressed)[/yellow]")
    console.print()
    console.print("[cyan]Note: Downloading England data only (Wales requires manual download)[/cyan]")
    console.print("[dim]See MANUAL_DOWNLOAD_GUIDE.md for Wales data instructions[/dim]")
    console.print()

    # Check if data already exists
    combined_file = DATA_RAW_DIR / "epc_england_wales_combined.parquet"

    if combined_file.exists():
        file_size_gb = combined_file.stat().st_size / (1024**3)
        console.print(f"[green]✓[/green] Existing parquet file found: {combined_file.name}")
        console.print(f"  File size: {file_size_gb:.2f} GB")

        # Try to validate the file by reading metadata
        try:
            import pyarrow.parquet as pq
            parquet_file = pq.ParquetFile(combined_file)
            num_rows = parquet_file.metadata.num_rows
            num_cols = parquet_file.metadata.num_columns
            console.print(f"  Records: {num_rows:,}")
            console.print(f"  Columns: {num_cols}")
            console.print()

            use_existing = Confirm.ask("Use existing data file?", default=True)

            if use_existing:
                console.print(f"[green]✓[/green] Using existing data file")
                return combined_file
            else:
                console.print("[yellow]Will reprocess data from CSV files...[/yellow]")
                # Delete existing file to start fresh
                combined_file.unlink()

        except Exception as e:
            console.print(f"[yellow]⚠[/yellow] Existing file appears corrupted: {e}")
            console.print("[yellow]Will reprocess data from CSV files...[/yellow]")
            combined_file.unlink()

    # Download data
    downloader = EPCBulkDownloader()

    try:
        output_path = downloader.download_and_process_all(
            regions=["england"],  # Wales requires manual download (authentication required)
            force_redownload=False,
            extract=True,
            combine=True
        )

        console.print(f"[green]✓[/green] Data acquisition complete!")
        console.print(f"  Output: {output_path}")

        return output_path

    except Exception as e:
        console.print(f"[red]✗[/red] Data acquisition failed: {e}")
        logger.exception("Data acquisition error")
        return None


def phase_2_data_validation(data_path: Path):
    """Phase 2: Validate and clean EPC data using chunked processing."""
    console.print()
    console.print(Panel("[bold]Phase 2: Data Validation[/bold]", border_style="blue"))
    console.print()

    output_file = DATA_PROCESSED_DIR / "epc_england_wales_validated.parquet"

    # Check if validated file already exists
    if output_file.exists():
        file_size_gb = output_file.stat().st_size / (1024**3)
        console.print(f"[green]✓[/green] Existing validated file found: {output_file.name}")
        console.print(f"  File size: {file_size_gb:.2f} GB")

        num_rows = None
        try:
            import pyarrow.parquet as pq
            # Read metadata and close file immediately
            metadata = pq.read_metadata(output_file)
            num_rows = metadata.num_rows
            console.print(f"  Records: {num_rows:,}")
            console.print()
        except Exception as e:
            console.print(f"[yellow]⚠[/yellow] Could not read file metadata: {e}")

        use_existing = Confirm.ask("Use existing validated file?", default=True)

        if use_existing:
            console.print(f"[green]✓[/green] Using existing validated file")
            return output_file
        else:
            console.print("[yellow]Will re-validate data...[/yellow]")
            # Try to delete, but if locked just rename/move aside
            try:
                output_file.unlink()
            except PermissionError:
                # File is locked (OneDrive, etc.) - rename it instead
                import time
                backup_name = output_file.with_suffix(f'.parquet.old_{int(time.time())}')
                console.print(f"[yellow]File locked, renaming to {backup_name.name}[/yellow]")
                output_file.rename(backup_name)

    console.print("[cyan]Running quality assurance checks (chunked processing)...[/cyan]")
    console.print(f"Input: {data_path.name}")
    console.print()

    # Use chunked validation to avoid memory issues
    validator = EPCDataValidator()

    try:
        validated_path, report = validator.validate_dataset_chunked(
            input_path=data_path,
            output_path=output_file,
            chunk_size=500000  # 500K rows per chunk
        )

        console.print(f"[green]✓[/green] Validation complete")
        console.print(f"  Records passed: {report['records_passed']:,} ({report['records_passed']/report['total_records']*100:.1f}%)")
        console.print(f"  Duplicates removed: {report['duplicates_removed']:,}")
        console.print(f"[green]✓[/green] Validated data saved: {validated_path}")

        return validated_path

    except Exception as e:
        console.print(f"[red]✗[/red] Validation failed: {e}")
        logger.exception("Validation error")
        return None


def phase_3_geographic_enrichment(df):
    """Phase 3: Add geographic hierarchies."""
    console.print()
    console.print(Panel("[bold]Phase 3: Geographic Enrichment[/bold]", border_style="blue"))
    console.print()

    console.print("[cyan]Adding geographic hierarchies (national/regional/LA/constituency)...[/cyan]")

    output_file = DATA_PROCESSED_DIR / "epc_england_wales_enriched.parquet"

    existing_df = load_existing_parquet(output_file, "geographically enriched dataset")
    if existing_df is not None:
        return existing_df

    geo = GeographyLookup()
    df_enriched = geo.enrich_epc_data(df)

    console.print(f"[green]✓[/green] Geographic enrichment complete")

    # Save enriched data
    df_enriched.to_parquet(output_file, index=False)

    console.print(f"[green]✓[/green] Enriched data saved: {output_file}")

    return df_enriched


def phase_3b_heat_network_proximity(df, sample_size: int | None = None):
    """
    Optional: analyze proximity to DESNZ heat network planning database.

    Uses postcodes.io for geocoding (cached) and assigns proximity tiers.
    """
    console.print()
    console.print(Panel("[bold]Phase 3b: Heat Network Proximity[/bold]", border_style="blue"))
    console.print()

    properties_output = DATA_OUTPUTS_DIR / "epc_heat_network_proximity_sample.csv"
    constituency_output = DATA_OUTPUTS_DIR / "constituency_heat_network_proximity.csv"
    results_output = DATA_OUTPUTS_DIR / "heat_network_zone_proximity_results.txt"

    existing_outputs = [
        path for path in [properties_output, constituency_output, results_output]
        if path.exists()
    ]

    if existing_outputs:
        console.print("[green]✓[/green] Existing heat network proximity outputs detected:")
        for path in existing_outputs:
            size_mb = path.stat().st_size / (1024**2)
            console.print(f"  • {path.name} ({size_mb:.1f} MB)")

        if Confirm.ask("Use existing heat network proximity outputs?", default=True):
            try:
                if properties_output.exists():
                    sample_df = pd.read_csv(properties_output)
                else:
                    sample_df = pd.DataFrame()

                tier_distribution = {}
                if not sample_df.empty and 'hn_zone_proximity_tier' in sample_df.columns:
                    tier_distribution = sample_df['hn_zone_proximity_tier'].value_counts().to_dict()

                proximity_results = {
                    "tier_distribution": tier_distribution,
                    "properties_output": properties_output if properties_output.exists() else None,
                    "constituency_output": constituency_output if constituency_output.exists() else None,
                    "sample_size": len(sample_df)
                }

                console.print("[green]✓[/green] Using existing heat network proximity outputs")
                return None, proximity_results

            except Exception as e:
                console.print(f"[yellow]⚠[/yellow] Could not load existing proximity outputs: {e}")
                console.print("[yellow]Recomputing heat network proximity...[/yellow]")

    if 'POSTCODE' not in df.columns:
        console.print("[yellow]⚠ POSTCODE column not found - skipping heat network proximity[/yellow]")
        return None, None

    # Optionally sample to keep runtime manageable when requested
    if sample_size is not None and len(df) > sample_size:
        console.print(
            f"[yellow]Sampling {sample_size:,} properties for proximity analysis out of {len(df):,}[/yellow]"
        )
        df_sample = df.sample(n=sample_size, random_state=42)
    else:
        df_sample = df

    # Check if coordinates already exist to avoid repeated geocoding
    has_coords = 'LATITUDE' in df_sample.columns and 'LONGITUDE' in df_sample.columns

    if has_coords:
        console.print("[green]Using existing coordinates from dataset (skipping geocoding)[/green]")
        # Create GeoDataFrame from existing coordinates
        from shapely.geometry import Point
        geometry = [
            Point(lon, lat) if pd.notna(lon) and pd.notna(lat) else None
            for lon, lat in zip(df_sample['LONGITUDE'], df_sample['LATITUDE'])
        ]
        properties_gdf = gpd.GeoDataFrame(df_sample, geometry=geometry, crs='EPSG:4326')
        properties_gdf = properties_gdf[properties_gdf.geometry.notna()].copy()
        console.print(f"  Created GeoDataFrame from {len(properties_gdf):,} properties with coordinates")
    else:
        console.print("[cyan]No coordinates found - geocoding from postcodes...[/cyan]")
        cache_file = DATA_OUTPUTS_DIR / "geocoding_cache.csv"

        with MemoryMonitor("Geocoding properties"):
            geocoder = PostcodeGeocoder(cache_file=cache_file)
            properties_gdf = geocoder.geocode_dataframe(df_sample, postcode_column='POSTCODE', batch_mode=True)

    if properties_gdf is None or properties_gdf.empty:
        console.print("[red]No properties could be geocoded - skipping heat network proximity[/red]")
        return None, None

    # Project to British National Grid for distance calculations
    log_memory("Before CRS projection")
    properties_gdf = properties_gdf.to_crs("EPSG:27700")
    log_memory("After CRS projection")

    with MemoryMonitor("Heat network proximity calculation"):
        analyzer = HeatNetworkZoneProximityAnalyzer()
        analyzer.load_heat_network_data()
        properties_gdf = analyzer.calculate_proximity(properties_gdf, chunk_size=10000)

    # Save property-level sample output
    output_df = properties_gdf.copy()
    latlon = output_df.geometry.to_crs("EPSG:4326")
    output_df['LATITUDE'] = latlon.y
    output_df['LONGITUDE'] = latlon.x
    output_df = output_df.drop(columns=['geometry'])
    output_df.to_csv(properties_output, index=False)
    console.print(f"[green]Saved property-level proximity sample: {properties_output.name} ({len(output_df):,} records)[/green]")

    # Constituency summary (if codes available)
    constituency_output = None
    if 'CONSTITUENCY' in properties_gdf.columns:
        lookup_file = DATA_SUPPLEMENTARY_DIR / "constituency_lookup.csv"
        if lookup_file.exists():
            lookup_df = pd.read_csv(lookup_file)
            # Use Series.map to avoid losing GeoDataFrame geometry in merge
            for col in lookup_df.columns:
                if col != 'CONSTITUENCY' and col not in properties_gdf.columns:
                    lookup_map = dict(zip(lookup_df['CONSTITUENCY'], lookup_df[col]))
                    properties_gdf[col] = properties_gdf['CONSTITUENCY'].map(lookup_map)

        constituency_summary = analyzer.analyze_by_constituency(properties_gdf, constituency_col='CONSTITUENCY')
        if len(constituency_summary) > 0:
            constituency_output = DATA_OUTPUTS_DIR / "constituency_heat_network_proximity.csv"
            constituency_summary.to_csv(constituency_output, index=False)
            console.print(f"[green]Saved constituency proximity summary: {constituency_output.name}[/green]")

    analyzer.save_results()

    proximity_results = {
        "tier_distribution": analyzer.results.get("tier_distribution", {}),
        "properties_output": properties_output,
        "constituency_output": constituency_output,
        "sample_size": len(output_df),
    }

    console.print(f"[green]Heat network proximity analysis complete on {len(output_df):,} properties[/green]")

    return properties_gdf, proximity_results


def phase_4_policy_analysis(df, df_hp=None):
    """Phase 4: Run all policy analyses."""
    console.print()
    console.print(Panel("[bold]Phase 4: Policy Analysis[/bold]", border_style="blue"))
    console.print()

    results = {}

    # 4a: Heating Fuel Mix
    console.print("[cyan]4a. Analyzing heating fuel mix...[/cyan]")
    fuel_analyzer = HeatingFuelAnalyzer()
    fuel_analyzer.analyze_fuel_mix(df)
    fuel_analyzer.identify_off_gas_properties(df)
    fuel_analyzer.calculate_electrification_rate(df)
    fuel_analyzer.identify_fuel_switching_opportunities(df)
    fuel_analyzer.save_results()
    results['fuel'] = fuel_analyzer.results
    results['fuel_analyzer'] = fuel_analyzer  # Keep for constituency analysis
    console.print(f"[green]✓[/green] Fuel mix analysis complete")

    # 4b: Heat Pump Potential
    console.print("[cyan]4b. Analyzing heat pump potential...[/cyan]")
    hp_analyzer = HeatPumpPotentialAnalyzer()
    df_hp = hp_analyzer.assess_suitability(df)
    hp_analyzer.categorize_barriers(df_hp)
    hp_analyzer.save_results()
    results['heat_pump'] = hp_analyzer.results
    results['hp_analyzer'] = hp_analyzer  # Keep for constituency analysis
    results['df_hp'] = df_hp  # Keep assessed dataframe
    console.print(f"[green]✓[/green] Heat pump potential analysis complete")

    # 4c: Heat Network Potential
    console.print("[cyan]4c. Analyzing heat network potential...[/cyan]")
    hn_analyzer = HeatNetworkPotentialAnalyzer()
    hn_analyzer.identify_priority_areas(df, min_tier='medium')
    hn_analyzer.calculate_network_potential(df)
    hn_analyzer.save_results()
    results['heat_network'] = hn_analyzer.results
    results['hn_analyzer'] = hn_analyzer  # Keep for constituency analysis
    console.print(f"[green]✓[/green] Heat network potential analysis complete")

    # 4d: Demand Reduction
    console.print("[cyan]4d. Analyzing demand reduction potential...[/cyan]")
    dr_analyzer = DemandReductionAnalyzer()
    dr_analyzer.analyze_fabric_potential(df)
    dr_analyzer.calculate_savings_potential(df)
    dr_analyzer.analyze_path_to_epc_c(df)
    dr_analyzer.calculate_national_investment(df)  # NEW: National investment estimates
    dr_analyzer.save_results()
    results['demand_reduction'] = dr_analyzer.results
    results['dr_analyzer'] = dr_analyzer  # Keep for constituency analysis
    console.print(f"[green]✓[/green] Demand reduction analysis complete")

    # 4e: Consumer Impact Analysis (NEW)
    console.print("[cyan]4e. Analyzing consumer impacts...[/cyan]")
    ci_analyzer = ConsumerImpactAnalyzer()
    ci_analyzer.analyze_all(df)
    ci_analyzer.save_results()
    results['consumer_impact'] = ci_analyzer.results
    results['ci_analyzer'] = ci_analyzer  # Keep for constituency analysis
    console.print(f"[green]✓[/green] Consumer impact analysis complete")

    # 4f: Policy Scenario Analysis (NEW)
    console.print("[cyan]4f. Analyzing policy scenarios...[/cyan]")
    ps_analyzer = PolicyScenarioAnalyzer()
    ps_analyzer.analyze_all(df)
    ps_analyzer.save_results()
    results['policy_scenarios'] = ps_analyzer.results
    console.print(f"[green]✓[/green] Policy scenario analysis complete")

    console.print()
    console.print("[green]✓[/green] All policy analyses complete!")

    return results


def phase_4b_constituency_analysis(df, results):
    """Phase 4b: Generate constituency-level outputs for all analyses."""
    console.print()
    console.print(Panel("[bold]Phase 4b: Constituency-Level Analysis[/bold]", border_style="blue"))
    console.print()

    expected_outputs = {
        'fuel_mix': DATA_OUTPUTS_DIR / "constituency_fuel_mix.csv",
        'heat_pump': DATA_OUTPUTS_DIR / "constituency_heat_pump_potential.csv",
        'heat_network': DATA_OUTPUTS_DIR / "constituency_heat_network_potential.csv",
        'epc_distribution': DATA_OUTPUTS_DIR / "constituency_epc_distribution.csv",
        'consumer_impact': DATA_OUTPUTS_DIR / "constituency_consumer_impact.csv",
        'summary': DATA_OUTPUTS_DIR / "constituency_summary.csv",
    }

    existing_outputs = {name: path for name, path in expected_outputs.items() if path.exists()}

    if existing_outputs:
        console.print("[green]✓[/green] Existing constituency-level outputs detected:")
        for name, path in existing_outputs.items():
            console.print(f"  • {name.replace('_', ' ').title()}: {path.name}")

        if Confirm.ask("Use existing constituency outputs and skip regeneration?", default=True):
            console.print("[green]✓[/green] Using existing constituency outputs")
            return existing_outputs

    import pandas as pd

    # Check if constituency_name column exists
    if 'constituency_name' not in df.columns:
        console.print("[yellow]⚠ constituency_name column not found - skipping constituency analysis[/yellow]")
        return

    constituency_outputs = {}

    # 1. Heating Fuel Mix by Constituency
    console.print("[cyan]Generating constituency-level fuel mix...[/cyan]")
    if 'fuel_analyzer' in results:
        fuel_by_const = results['fuel_analyzer'].analyze_by_geography(df, level='constituency')
        if len(fuel_by_const) > 0:
            output_path = DATA_OUTPUTS_DIR / "constituency_fuel_mix.csv"
            fuel_by_const.to_csv(output_path, index=False)
            constituency_outputs['fuel_mix'] = output_path
            console.print(f"[green]✓[/green] Saved: {output_path.name} ({len(fuel_by_const)} constituencies)")

    # 2. Heat Pump Potential by Constituency
    console.print("[cyan]Generating constituency-level heat pump potential...[/cyan]")
    if 'hp_analyzer' in results and 'df_hp' in results:
        hp_by_const = results['hp_analyzer'].calculate_potential_by_geography(
            results['df_hp'], level='constituency'
        )
        if len(hp_by_const) > 0:
            output_path = DATA_OUTPUTS_DIR / "constituency_heat_pump_potential.csv"
            hp_by_const.to_csv(output_path, index=False)
            constituency_outputs['heat_pump'] = output_path
            console.print(f"[green]✓[/green] Saved: {output_path.name} ({len(hp_by_const)} constituencies)")

    # 3. Heat Network Potential by Constituency
    console.print("[cyan]Generating constituency-level heat network potential...[/cyan]")
    if 'hn_analyzer' in results:
        hn_by_const = results['hn_analyzer'].analyze_by_geography(
            df, level='constituency'
        )
        if len(hn_by_const) > 0:
            output_path = DATA_OUTPUTS_DIR / "constituency_heat_network_potential.csv"
            hn_by_const.to_csv(output_path, index=False)
            constituency_outputs['heat_network'] = output_path
            console.print(f"[green]✓[/green] Saved: {output_path.name} ({len(hn_by_const)} constituencies)")

    # 4. EPC Distribution by Constituency
    console.print("[cyan]Generating constituency-level EPC distribution...[/cyan]")
    if 'CURRENT_ENERGY_RATING' in df.columns:
        epc_by_const = pd.crosstab(
            df['constituency_name'],
            df['CURRENT_ENERGY_RATING'],
            normalize='index'
        ) * 100

        # Add property counts
        const_counts = df.groupby('constituency_name').size()
        epc_by_const['total_properties'] = const_counts

        # Add percentage EPC C+ (compliant)
        compliant_cols = [col for col in ['A', 'B', 'C'] if col in epc_by_const.columns]
        epc_by_const['pct_epc_c_plus'] = epc_by_const[compliant_cols].sum(axis=1)

        # Calculate average SAP score if available
        if 'CURRENT_ENERGY_EFFICIENCY' in df.columns:
            avg_sap = df.groupby('constituency_name')['CURRENT_ENERGY_EFFICIENCY'].mean()
            epc_by_const['avg_sap_score'] = avg_sap

        epc_by_const = epc_by_const.reset_index()
        output_path = DATA_OUTPUTS_DIR / "constituency_epc_distribution.csv"
        epc_by_const.to_csv(output_path, index=False)
        constituency_outputs['epc_distribution'] = output_path
        console.print(f"[green]✓[/green] Saved: {output_path.name} ({len(epc_by_const)} constituencies)")

    # 5. Consumer Impact by Constituency
    console.print("[cyan]Generating constituency-level consumer impact...[/cyan]")
    if 'annual_bill' in df.columns and 'annual_emissions_tonnes' in df.columns:
        consumer_by_const = df.groupby('constituency_name').agg({
            'annual_bill': ['mean', 'median', 'sum'],
            'annual_emissions_tonnes': ['mean', 'sum'],
            'constituency_name': 'count'
        })
        consumer_by_const.columns = [
            'avg_annual_bill', 'median_annual_bill', 'total_annual_bills',
            'avg_emissions_tonnes', 'total_emissions_tonnes', 'total_properties'
        ]
        consumer_by_const = consumer_by_const.reset_index()
        output_path = DATA_OUTPUTS_DIR / "constituency_consumer_impact.csv"
        consumer_by_const.to_csv(output_path, index=False)
        constituency_outputs['consumer_impact'] = output_path
        console.print(f"[green]✓[/green] Saved: {output_path.name} ({len(consumer_by_const)} constituencies)")

    # 6. Summary statistics
    console.print("[cyan]Generating constituency summary...[/cyan]")
    const_summary = df.groupby('constituency_name').agg({
        'constituency_name': 'count',
        'TOTAL_FLOOR_AREA': 'mean' if 'TOTAL_FLOOR_AREA' in df.columns else 'count'
    })
    const_summary.columns = ['total_properties', 'avg_floor_area']
    const_summary = const_summary.reset_index()

    # Add fuel category if available
    if 'fuel_category' in df.columns:
        gas_pct = df[df['fuel_category'] == 'mains_gas'].groupby('constituency_name').size() / df.groupby('constituency_name').size() * 100
        const_summary['pct_gas_heated'] = const_summary['constituency_name'].map(gas_pct).fillna(0)

    # Add HP suitability if available
    if 'hp_suitability_tier' in results.get('df_hp', pd.DataFrame()).columns:
        df_hp = results['df_hp']
        ready_pct = (
            df_hp[df_hp['hp_suitability_tier'] <= 2]
            .groupby('constituency_name').size() /
            df_hp.groupby('constituency_name').size() * 100
        )
        const_summary['pct_hp_ready'] = const_summary['constituency_name'].map(ready_pct).fillna(0)

    output_path = DATA_OUTPUTS_DIR / "constituency_summary.csv"
    const_summary.to_csv(output_path, index=False)
    constituency_outputs['summary'] = output_path
    console.print(f"[green]✓[/green] Saved: {output_path.name} ({len(const_summary)} constituencies)")

    console.print()
    console.print(f"[green]✓[/green] Generated {len(constituency_outputs)} constituency-level output files")

    return constituency_outputs


def phase_5_reporting(results):
    """Phase 5: Generate summary reports."""
    console.print()
    console.print(Panel("[bold]Phase 5: Report Generation[/bold]", border_style="blue"))
    console.print()

    console.print("[cyan]Generating summary report...[/cyan]")

    # Create summary report
    report_path = DATA_OUTPUTS_DIR / "ade_policy_analysis_summary.txt"

    if report_path.exists():
        modified = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(report_path.stat().st_mtime))
        size_mb = report_path.stat().st_size / (1024**2)
        console.print(f"[green]✓[/green] Existing summary report found: {report_path.name} ({size_mb:.1f} MB, last updated {modified})")
        if Confirm.ask("Use existing summary report and skip regeneration?", default=True):
            console.print("[green]✓[/green] Using existing summary report")
            console.print()
            console.print(f"[cyan]📁 All outputs saved to:[/cyan] {DATA_OUTPUTS_DIR}")
            return report_path

    with open(report_path, 'w') as f:
        f.write("ADE EPC POLICY ANALYSIS - SUMMARY REPORT\n")
        f.write("=" * 70 + "\n\n")
        f.write(f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")

        # Fuel mix summary
        if 'fuel' in results and results['fuel']:
            f.write("\n1. HEATING FUEL MIX\n")
            f.write("-" * 70 + "\n")
            if 'fuel_mix' in results['fuel']:
                fuel_mix = results['fuel']['fuel_mix']
                f.write(f"Total properties: {fuel_mix.get('total_properties', 0):,}\n")
                f.write("\nFuel type breakdown:\n")
                for fuel, pct in fuel_mix.get('fuel_percentages', {}).items():
                    count = fuel_mix.get('fuel_counts', {}).get(fuel, 0)
                    f.write(f"  {fuel}: {count:,} ({pct:.1f}%)\n")

            if 'electrification' in results['fuel']:
                elec = results['fuel']['electrification']
                f.write(f"\nElectrification rate: {elec.get('electrification_rate', 0):.2f}%\n")

        # Heat pump summary
        if 'heat_pump' in results and results['heat_pump']:
            f.write("\n\n2. HEAT PUMP POTENTIAL\n")
            f.write("-" * 70 + "\n")
            if 'barriers' in results['heat_pump']:
                barriers = results['heat_pump']['barriers']
                f.write(f"Ready or minor work: {barriers.get('ready_or_minor_work', 0):,} properties\n")
                f.write(f"Average fabric cost: £{barriers.get('avg_fabric_cost_per_property', 0):,.0f}\n")
                f.write(f"Total fabric investment: £{barriers.get('total_fabric_investment_needed', 0)/1e9:.2f}B\n")

        # Heat network summary
        if 'heat_network' in results and results['heat_network']:
            f.write("\n\n3. HEAT NETWORK POTENTIAL\n")
            f.write("-" * 70 + "\n")
            if 'network_potential' in results['heat_network']:
                hn = results['heat_network']['network_potential']
                f.write(f"Viable properties: {hn.get('total_viable_properties', 0):,} ({hn.get('pct_viable', 0):.1f}%)\n")
                f.write(f"Total heat demand: {hn.get('total_viable_heat_demand_gwh', 0):.1f} GWh\n")
                f.write(f"Connection cost: £{hn.get('total_connection_cost_bn', 0):.2f}B\n")

        # Heat network proximity (sampled)
        if 'heat_network_proximity' in results and results['heat_network_proximity']:
            prox = results['heat_network_proximity']
            f.write("\n\n3b. HEAT NETWORK PROXIMITY (DESNZ PLANNING DB)\n")
            f.write("-" * 70 + "\n")
            f.write(f"Sample analyzed: {prox.get('sample_size', 0):,} properties\n")
            if prox.get('tier_distribution'):
                f.write("Tier distribution (sample):\n")
                for tier, count in prox['tier_distribution'].items():
                    f.write(f"  {tier}: {count:,}\n")
            if prox.get('properties_output'):
                f.write(f"Property-level output: {prox['properties_output']}\n")
            if prox.get('constituency_output'):
                f.write(f"Constituency summary: {prox['constituency_output']}\n")

        # Demand reduction summary
        if 'demand_reduction' in results and results['demand_reduction']:
            f.write("\n\n4. DEMAND REDUCTION\n")
            f.write("-" * 70 + "\n")
            if 'path_to_epc_c' in results['demand_reduction']:
                epc = results['demand_reduction']['path_to_epc_c']
                f.write(f"Already EPC C+: {epc.get('already_compliant', 0):,} ({epc.get('pct_compliant', 0):.1f}%)\n")
                f.write(f"Need improvement: {epc.get('needs_improvement', 0):,}\n")
                f.write(f"Estimated cost to EPC C: £{epc.get('estimated_total_cost_bn', 0):.2f}B\n")

            if 'savings_potential' in results['demand_reduction']:
                savings = results['demand_reduction']['savings_potential']
                f.write(f"\nPotential savings: {savings.get('total_savings_gwh', 0):.1f} GWh/year\n")
                f.write(f"CO2 reduction: {savings.get('total_co2_savings_kt', 0):.0f} kt/year\n")

            if 'national_investment' in results['demand_reduction']:
                ni = results['demand_reduction']['national_investment']
                f.write(f"\nNational fabric investment needed: £{ni.get('total_fabric_investment_bn', 0):.0f}B\n")
                f.write(f"Job creation potential: {ni.get('estimated_jobs', 0):,}\n")

        # Consumer Impact summary (NEW)
        if 'consumer_impact' in results and results['consumer_impact']:
            f.write("\n\n5. CONSUMER IMPACT\n")
            f.write("-" * 70 + "\n")

            if 'household_bills' in results['consumer_impact']:
                bills = results['consumer_impact']['household_bills']
                f.write(f"Average annual heating bill: £{bills.get('avg_annual_bill', 0):,.0f}\n")

            if 'household_emissions' in results['consumer_impact']:
                emissions = results['consumer_impact']['household_emissions']
                f.write(f"Average annual emissions: {emissions.get('avg_emissions_tonnes', 0):.2f} tonnes CO2\n")
                f.write(f"Total stock emissions: {emissions.get('total_emissions_mt', 0):.1f} Mt CO2/year\n")

            if 'running_cost_comparison' in results['consumer_impact']:
                comparison = results['consumer_impact']['running_cost_comparison']
                scenarios = comparison.get('scenarios', {})

                if 'baseline' in scenarios:
                    baseline = scenarios['baseline']
                    f.write(f"\nAt current prices:\n")
                    f.write(f"  Gas boiler: £{baseline.get('gas_boiler_annual_cost', 0):,.0f}/year\n")
                    f.write(f"  Heat pump: £{baseline.get('heat_pump_annual_cost', 0):,.0f}/year\n")

                if 'rebalanced' in scenarios:
                    rebalanced = scenarios['rebalanced']
                    f.write(f"\nWith price rebalancing:\n")
                    f.write(f"  Gas boiler: £{rebalanced.get('gas_boiler_annual_cost', 0):,.0f}/year\n")
                    f.write(f"  Heat pump: £{rebalanced.get('heat_pump_annual_cost', 0):,.0f}/year\n")
                    if rebalanced.get('heat_pump_cheaper', False):
                        f.write(f"  Heat pump SAVES: £{rebalanced.get('annual_savings', 0):,.0f}/year\n")

        # Policy Scenarios summary (NEW)
        if 'policy_scenarios' in results and results['policy_scenarios']:
            f.write("\n\n6. POLICY IMPLICATIONS\n")
            f.write("-" * 70 + "\n")

            if 'installation_rates' in results['policy_scenarios']:
                ir = results['policy_scenarios']['installation_rates']
                f.write(f"Heat pump installation rate increase needed: {ir.get('multiplier_needed', 0):.0f}x\n")
                f.write(f"Current: {ir.get('current_annual_rate', 0):,}/year\n")
                f.write(f"Target: {ir.get('target_annual_rate_2028', 0):,}/year by 2028\n")

            if 'boiler_phaseout' in results['policy_scenarios']:
                bp = results['policy_scenarios']['boiler_phaseout']
                f.write(f"\n2035 boiler phase-out:\n")
                f.write(f"  Gas properties to convert: {bp.get('gas_heated_properties', 0):,}\n")
                f.write(f"  Annual conversions needed: {bp.get('annual_conversions_needed', 0):,}\n")

            if 'job_creation' in results['policy_scenarios']:
                jc = results['policy_scenarios']['job_creation']
                f.write(f"\nJob creation potential: {jc.get('total_jobs_potential', 0):,}\n")
                f.write(f"Total investment opportunity: £{jc.get('total_investment_potential_bn', 0):.0f}B\n")

    console.print(f"[green]✓[/green] Summary report saved: {report_path}")
    console.print()
    console.print(f"[cyan]📁 All outputs saved to:[/cyan] {DATA_OUTPUTS_DIR}")

    return report_path


def main():
    """Main execution function."""
    print_header()

    # Ensure directories exist
    ensure_directories()

    start_time = time.time()

    try:
        # Phase 1: Data Acquisition
        data_path = phase_1_data_acquisition()
        if data_path is None:
            console.print("[red]Pipeline stopped - data acquisition failed[/red]")
            return

        # Phase 2: Validation (chunked - returns path)
        validated_path = phase_2_data_validation(data_path)
        if validated_path is None:
            console.print("[red]Pipeline stopped - validation failed[/red]")
            return

        # Load validated data for subsequent phases
        # Note: This loads entire dataset into memory - may need optimization for very large datasets
        console.print()
        console.print("[cyan]Loading validated data for analysis phases...[/cyan]")
        import pandas as pd
        try:
            df_validated = pd.read_parquet(validated_path)
            console.print(f"[green]✓[/green] Loaded {len(df_validated):,} validated records")
        except Exception as e:
            console.print(f"[red]✗[/red] Failed to load validated data: {e}")
            console.print("[yellow]Consider running phases 3-5 with chunked processing[/yellow]")
            if Confirm.ask("Run phases 3-5 with chunked processing now?", default=True):
                results, constituency_outputs, proximity_results = run_chunked_pipeline(validated_path)
                if proximity_results:
                    results['heat_network_proximity'] = proximity_results
                report_path = phase_5_reporting(results)
                elapsed = time.time() - start_time
                total_props = results.get('fuel', {}).get('fuel_mix', {}).get('total_properties', 0)
                console.print()
                console.print(Panel.fit(
                    f"[bold green]✓ Analysis Complete![/bold green]\n\n"
                    f"Time elapsed: {elapsed/60:.1f} minutes\n"
                    f"Properties analyzed: {total_props:,}\n\n"
                    f"[cyan]Results:[/cyan]\n"
                    f"  • Summary report: {report_path}\n"
                    f"  • Detailed outputs: {DATA_OUTPUTS_DIR}",
                    border_style="green"
                ))
                return
            return

        # Phase 3: Geographic Enrichment
        df_enriched = phase_3_geographic_enrichment(df_validated)

        # Phase 3b: Heat Network Proximity (sampled)
        _, proximity_results = phase_3b_heat_network_proximity(df_enriched)

        # Phase 4: Policy Analysis
        results = phase_4_policy_analysis(df_enriched)
        if proximity_results:
            results['heat_network_proximity'] = proximity_results

        # Phase 4b: Constituency-Level Analysis
        constituency_outputs = phase_4b_constituency_analysis(df_enriched, results)

        # Phase 5: Reporting
        report_path = phase_5_reporting(results)

        # Complete
        elapsed = time.time() - start_time

        console.print()
        console.print(Panel.fit(
            f"[bold green]✓ Analysis Complete![/bold green]\n\n"
            f"Time elapsed: {elapsed/60:.1f} minutes\n"
            f"Properties analyzed: {len(df_enriched):,}\n\n"
            f"[cyan]Results:[/cyan]\n"
            f"  • Summary report: {report_path}\n"
            f"  • Detailed outputs: {DATA_OUTPUTS_DIR}",
            border_style="green"
        ))

    except KeyboardInterrupt:
        console.print("\n[yellow]Analysis interrupted by user[/yellow]")
    except Exception as e:
        console.print(f"\n[red]Error: {e}[/red]")
        logger.exception("Pipeline error")


if __name__ == "__main__":
    main()
