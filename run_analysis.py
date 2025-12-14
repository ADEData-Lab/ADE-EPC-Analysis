"""
Heat Street EPC Analysis (Retired)

This interactive pipeline previously powered London-specific archetype and
scenario modeling. The modeling components have been retired and archived
under the ``legacy`` directory. Use ``run_ade_analysis.py`` for the active
national analysis pipeline.
"""

from rich import print as rprint


def main():
    """Warn users that this script is retired."""
    rprint("[bold yellow]This interactive pipeline has been retired.[/bold yellow]")
    rprint("Use [cyan]python run_ade_analysis.py[/cyan] for the active national analysis.")
    rprint(
        "Legacy scenario and pathway modelers are available under the [cyan]legacy/[/cyan] "
        "directory for reference only."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
