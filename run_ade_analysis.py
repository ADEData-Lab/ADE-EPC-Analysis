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

    cache_file = DATA_OUTPUTS_DIR / "geocoding_cache.csv"
    geocoder = PostcodeGeocoder(cache_file=cache_file)
    properties_gdf = geocoder.geocode_dataframe(df_sample, postcode_column='POSTCODE', batch_mode=True)

    if properties_gdf is None or properties_gdf.empty:
        console.print("[red]No properties could be geocoded - skipping heat network proximity[/red]")
        return None, None

    # Project to British National Grid for distance calculations
    properties_gdf = properties_gdf.to_crs("EPSG:27700")

    analyzer = HeatNetworkZoneProximityAnalyzer()
    analyzer.load_heat_network_data()
    properties_gdf = analyzer.calculate_proximity(properties_gdf)

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
            properties_gdf = properties_gdf.merge(lookup_df, how='left', on='CONSTITUENCY')

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
            console.print("[yellow]Consider running phases 3-5 separately with chunked processing[/yellow]")
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
