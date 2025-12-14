"""
Test ADE Analysis Modules with Existing London Data

This script tests the new analysis modules using existing London EPC data.
Use this while you arrange to download the full England & Wales dataset.
"""

import pandas as pd
from pathlib import Path
from rich.console import Console
from rich.panel import Panel

from src.analysis.heating_fuel_analysis import HeatingFuelAnalyzer
from src.analysis.heat_pump_potential import HeatPumpPotentialAnalyzer
from src.analysis.heat_network_potential import HeatNetworkPotentialAnalyzer
from src.analysis.demand_reduction_analysis import DemandReductionAnalyzer

console = Console()


def find_london_data():
    """Find existing London EPC data."""
    possible_paths = [
        Path("data/processed/epc_london_validated.csv"),
        Path("data/processed/epc_london_validated.parquet"),
        Path("data/raw/epc_london_filtered.csv"),
    ]

    for path in possible_paths:
        if path.exists():
            console.print(f"[green]✓[/green] Found data: {path}")
            return path

    return None


def main():
    """Main test execution."""
    console.print(Panel.fit(
        "[bold cyan]ADE Analysis Test[/bold cyan]\n"
        "[white]Testing with London EPC Data[/white]",
        border_style="cyan"
    ))
    console.print()

    # Find data
    data_path = find_london_data()

    if data_path is None:
        console.print("[red]✗ No London EPC data found[/red]")
        console.print()
        console.print("Expected locations:")
        console.print("  • data/processed/epc_london_validated.csv")
        console.print("  • data/raw/epc_london_filtered.csv")
        console.print()
        console.print("Please run the old pipeline first or see MANUAL_DOWNLOAD_GUIDE.md")
        return

    # Load data
    console.print(f"[cyan]Loading data from {data_path}...[/cyan]")

    if data_path.suffix == '.parquet':
        df = pd.read_parquet(data_path)
    else:
        df = pd.read_csv(data_path, low_memory=False)

    console.print(f"[green]✓[/green] Loaded {len(df):,} properties")
    console.print()

    # Test 1: Heating Fuel Analysis
    console.print("[cyan]1. Testing Heating Fuel Analysis...[/cyan]")
    try:
        fuel_analyzer = HeatingFuelAnalyzer()
        fuel_analyzer.analyze_fuel_mix(df)
        fuel_analyzer.identify_off_gas_properties(df)
        fuel_analyzer.calculate_electrification_rate(df)
        fuel_analyzer.save_results()
        console.print("[green]✓[/green] Fuel analysis complete")
    except Exception as e:
        console.print(f"[yellow]⚠[/yellow] Fuel analysis error: {e}")
    console.print()

    # Test 2: Heat Pump Potential
    console.print("[cyan]2. Testing Heat Pump Potential Analysis...[/cyan]")
    try:
        hp_analyzer = HeatPumpPotentialAnalyzer()
        df_hp = hp_analyzer.assess_suitability(df)
        hp_analyzer.categorize_barriers(df_hp)
        hp_analyzer.save_results()
        console.print("[green]✓[/green] Heat pump analysis complete")
    except Exception as e:
        console.print(f"[yellow]⚠[/yellow] Heat pump analysis error: {e}")
    console.print()

    # Test 3: Heat Network Potential
    console.print("[cyan]3. Testing Heat Network Potential Analysis...[/cyan]")
    try:
        hn_analyzer = HeatNetworkPotentialAnalyzer()
        hn_analyzer.identify_priority_areas(df, min_tier='medium')
        hn_analyzer.calculate_network_potential(df)
        hn_analyzer.save_results()
        console.print("[green]✓[/green] Heat network analysis complete")
    except Exception as e:
        console.print(f"[yellow]⚠[/yellow] Heat network analysis error: {e}")
    console.print()

    # Test 4: Demand Reduction
    console.print("[cyan]4. Testing Demand Reduction Analysis...[/cyan]")
    try:
        dr_analyzer = DemandReductionAnalyzer()
        dr_analyzer.analyze_fabric_potential(df)
        dr_analyzer.calculate_savings_potential(df)
        dr_analyzer.analyze_path_to_epc_c(df)
        dr_analyzer.save_results()
        console.print("[green]✓[/green] Demand reduction analysis complete")
    except Exception as e:
        console.print(f"[yellow]⚠[/yellow] Demand reduction analysis error: {e}")
    console.print()

    # Summary
    console.print(Panel.fit(
        "[bold green]✓ Test Complete![/bold green]\n\n"
        f"Tested with: {len(df):,} London properties\n\n"
        "[cyan]Results:[/cyan]\n"
        "  • data/outputs/heating_fuel_analysis_results.txt\n"
        "  • data/outputs/heat_pump_potential_results.txt\n"
        "  • data/outputs/heat_network_potential_results.txt\n"
        "  • data/outputs/demand_reduction_results.txt",
        border_style="green"
    ))
    console.print()
    console.print("[dim]Note: This is London data only. For national analysis,[/dim]")
    console.print("[dim]download full dataset - see MANUAL_DOWNLOAD_GUIDE.md[/dim]")


if __name__ == "__main__":
    main()
