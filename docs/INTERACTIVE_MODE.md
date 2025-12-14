# Interactive Analysis Mode (Retired)

The previous London-focused interactive prompts and archetype/scenario modelers have been retired. They are available for reference only under `legacy/`. The active workflow is the national pipeline driven by `run_ade_analysis.py`.

## Current recommendation

- **Run the national pipeline:** `python run_ade_analysis.py`
- **Windows launchers:** `run.ps1` / `run.bat` (these now call the national pipeline)
- **Legacy reference:** `legacy/` contains the old interactive code paths.

## What changed

- The London archetype analysis and scenario/pathway modelers are archived and no longer maintained.
- National analyzers (heating fuel, heat pump potential, heat network potential, demand reduction, consumer impact, policy scenarios) remain active and are executed via `run_ade_analysis.py`.
- Outputs are written to `data/outputs/` (text summaries, CSV extracts, optional maps if spatial dependencies are installed).

## Need the old flow?

If you need to inspect historical logic, open the files under `legacy/` for reference. They are not wired into the current pipeline and should not be used for new runs.
