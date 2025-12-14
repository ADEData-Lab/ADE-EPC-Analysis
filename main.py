"""Compatibility entrypoint for the ADE EPC national analysis pipeline.

The project has been fully migrated from the London-centric "Heat Street" flow
to the England & Wales pipeline defined in ``run_ade_analysis.py``. This module
exists to provide a stable ``python main.py`` entry point that simply delegates
execution to the new pipeline while keeping logging initialisation consistent.
"""

from pathlib import Path
from loguru import logger
import sys

# Ensure the repository root is importable when running directly
sys.path.append(str(Path(__file__).parent))

from run_ade_analysis import main as run_national_pipeline


def setup_logging(log_file: Path | None = None) -> None:
    """Configure console and optional file logging."""

    logger.remove()
    logger.add(
        sys.stderr,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | <level>{message}</level>",
        level="INFO",
    )

    if log_file:
        logger.add(
            log_file,
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}",
            level="DEBUG",
            rotation="10 MB",
        )


def main(log_file: Path | None = None) -> None:
    """Run the national pipeline with standard logging configuration."""

    setup_logging(log_file)
    run_national_pipeline()


if __name__ == "__main__":
    setup_logging()
    run_national_pipeline()
