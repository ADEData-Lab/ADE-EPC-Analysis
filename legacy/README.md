# Legacy Heat Street Components

This folder preserves the retired London-centric pipeline and supporting utilities from the former "Heat Street" project. These modules are **not** used by the national ADE pipeline (`run_ade_analysis.py`) and are retained only for historical reference.

## Contents
- `heat_street/src/acquisition/` – EPC API and GIS downloaders tailored to London/Edwardian runs.
- `heat_street/src/analysis/archetype_analysis.py` – Archetype summaries for the legacy dashboard.
- `heat_street/src/modeling/` – Scenario and pathway modelers for the old cost-benefit workflow.
- `heat_street/tests/` – Legacy regression tests for the deprecated modeling code.

If you need to revive the legacy workflow, work from these archived files in a separate branch; do not reintroduce them to the main ADE pipeline without a clear migration plan.
