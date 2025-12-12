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
from loguru import logger
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.panel import Panel
import time

# Add src to path
sys.path.append(str(Path(__file__).parent))

from config.config import load_config, ensure_directories, DATA_RAW_DIR, DATA_PROCESSED_DIR, DATA_OUTPUTS_DIR
from src.acquisition.epc_bulk_downloader import EPCBulkDownloader
from src.cleaning.data_validator import EPCDataValidator
from src.utils.geography_lookup import GeographyLookup
from src.analysis.heating_fuel_analysis import HeatingFuelAnalyzer
from src.analysis.heat_pump_potential import HeatPumpPotentialAnalyzer
from src.analysis.heat_network_potential import HeatNetworkPotentialAnalyzer
from src.analysis.demand_reduction_analysis import DemandReductionAnalyzer

console = Console()


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
        console.print(f"[green]✓[/green] Data already downloaded: {combined_file}")
        console.print(f"  File size: {combined_file.stat().st_size / (1024**3):.2f} GB")
        console.print()

        from rich.prompt import Confirm
        redownload = Confirm.ask("Download fresh data?", default=False)

        if not redownload:
            return combined_file

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
    """Phase 2: Validate and clean EPC data."""
    console.print()
    console.print(Panel("[bold]Phase 2: Data Validation[/bold]", border_style="blue"))
    console.print()

    console.print("[cyan]Running quality assurance checks...[/cyan]")

    import pandas as pd

    # Load data (in chunks if needed)
    console.print(f"Loading data from {data_path.name}...")
    df = pd.read_parquet(data_path)

    console.print(f"[green]✓[/green] Loaded {len(df):,} records")

    # Validate
    validator = EPCDataValidator()
    df_validated, report = validator.validate_dataset(df)

    console.print(f"[green]✓[/green] Validation complete")
    console.print(f"  Records passed: {len(df_validated):,} ({len(df_validated)/report['total_records']*100:.1f}%)")
    console.print(f"  Duplicates removed: {report['duplicates_removed']:,}")

    # Save validated data
    output_file = DATA_PROCESSED_DIR / "epc_england_wales_validated.parquet"
    df_validated.to_parquet(output_file, index=False)

    console.print(f"[green]✓[/green] Validated data saved: {output_file}")

    return df_validated


def phase_3_geographic_enrichment(df):
    """Phase 3: Add geographic hierarchies."""
    console.print()
    console.print(Panel("[bold]Phase 3: Geographic Enrichment[/bold]", border_style="blue"))
    console.print()

    console.print("[cyan]Adding geographic hierarchies (national/regional/LA/constituency)...[/cyan]")

    geo = GeographyLookup()
    df_enriched = geo.enrich_epc_data(df)

    console.print(f"[green]✓[/green] Geographic enrichment complete")

    # Save enriched data
    output_file = DATA_PROCESSED_DIR / "epc_england_wales_enriched.parquet"
    df_enriched.to_parquet(output_file, index=False)

    console.print(f"[green]✓[/green] Enriched data saved: {output_file}")

    return df_enriched


def phase_4_policy_analysis(df):
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
    console.print(f"[green]✓[/green] Fuel mix analysis complete")

    # 4b: Heat Pump Potential
    console.print("[cyan]4b. Analyzing heat pump potential...[/cyan]")
    hp_analyzer = HeatPumpPotentialAnalyzer()
    df_hp = hp_analyzer.assess_suitability(df)
    hp_analyzer.categorize_barriers(df_hp)
    hp_analyzer.save_results()
    results['heat_pump'] = hp_analyzer.results
    console.print(f"[green]✓[/green] Heat pump potential analysis complete")

    # 4c: Heat Network Potential
    console.print("[cyan]4c. Analyzing heat network potential...[/cyan]")
    hn_analyzer = HeatNetworkPotentialAnalyzer()
    hn_analyzer.identify_priority_areas(df, min_tier='medium')
    hn_analyzer.calculate_network_potential(df)
    hn_analyzer.save_results()
    results['heat_network'] = hn_analyzer.results
    console.print(f"[green]✓[/green] Heat network potential analysis complete")

    # 4d: Demand Reduction
    console.print("[cyan]4d. Analyzing demand reduction potential...[/cyan]")
    dr_analyzer = DemandReductionAnalyzer()
    dr_analyzer.analyze_fabric_potential(df)
    dr_analyzer.calculate_savings_potential(df)
    dr_analyzer.analyze_path_to_epc_c(df)
    dr_analyzer.save_results()
    results['demand_reduction'] = dr_analyzer.results
    console.print(f"[green]✓[/green] Demand reduction analysis complete")

    console.print()
    console.print("[green]✓[/green] All policy analyses complete!")

    return results


def phase_5_reporting(results):
    """Phase 5: Generate summary reports."""
    console.print()
    console.print(Panel("[bold]Phase 5: Report Generation[/bold]", border_style="blue"))
    console.print()

    console.print("[cyan]Generating summary report...[/cyan]")

    # Create summary report
    report_path = DATA_OUTPUTS_DIR / "ade_policy_analysis_summary.txt"

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

        # Phase 2: Validation
        df_validated = phase_2_data_validation(data_path)

        # Phase 3: Geographic Enrichment
        df_enriched = phase_3_geographic_enrichment(df_validated)

        # Phase 4: Policy Analysis
        results = phase_4_policy_analysis(df_enriched)

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
