"""
Base Analyzer Class

Provides common functionality for all analysis modules to eliminate duplication.
Reduces ~200-560 lines of duplicated initialization, validation, and saving logic
across 12 analysis modules.

Created as part of code optimization initiative.
"""

import pandas as pd
from pathlib import Path
from typing import Dict, List, Optional, Any, Union
from loguru import logger
from datetime import datetime

import sys
sys.path.append(str(Path(__file__).parent.parent.parent))
from config.config import load_config, DATA_OUTPUTS_DIR


class BaseAnalyzer:
    """
    Base class for all analysis modules.

    Provides standardized:
    - Configuration loading
    - Logging initialization
    - Column validation
    - Results management
    - Results saving

    Usage:
    -----
    class MyAnalyzer(BaseAnalyzer):
        def __init__(self):
            super().__init__(
                name="My Analyzer",
                config_section="policy_metrics.my_section"
            )

        def analyze(self, df: pd.DataFrame) -> Dict:
            self.validate_required_columns(df, ['column1', 'column2'])
            # ... perform analysis
            self.results['my_results'] = results
            return self.results
    """

    def __init__(
        self,
        name: str,
        config_section: Optional[str] = None,
        auto_init_results: bool = True
    ):
        """
        Initialize the base analyzer.

        Args:
            name: Human-readable name for this analyzer
            config_section: Dot-separated path to config section (e.g., 'policy_metrics.heat_pump')
            auto_init_results: If True, initializes self.results = {}
        """
        self.name = name
        self.config = load_config()

        # Load specific config section if provided
        self.section_config = {}
        if config_section:
            self.section_config = self._get_nested_config(config_section)

        # Initialize results dictionary
        if auto_init_results:
            self.results = {}

        logger.info(f"Initialized {self.name}")

    def _get_nested_config(self, section_path: str) -> Dict:
        """
        Get nested configuration using dot notation.

        Args:
            section_path: Dot-separated path (e.g., 'policy_metrics.heat_pump')

        Returns:
            Configuration dictionary for that section
        """
        parts = section_path.split('.')
        config = self.config

        for part in parts:
            config = config.get(part, {})
            if not isinstance(config, dict):
                logger.warning(f"Config section not found: {section_path}")
                return {}

        return config

    def validate_required_columns(
        self,
        df: pd.DataFrame,
        required: List[str],
        optional: Optional[List[str]] = None,
        raise_error: bool = True
    ) -> bool:
        """
        Validate that DataFrame has required columns.

        Args:
            df: DataFrame to validate
            required: List of required column names
            optional: List of optional column names (logged as warnings if missing)
            raise_error: If True, raises ValueError on missing required columns

        Returns:
            True if all required columns present, False otherwise

        Raises:
            ValueError: If raise_error=True and required columns missing
        """
        missing_required = [col for col in required if col not in df.columns]
        missing_optional = [col for col in (optional or []) if col not in df.columns]

        if missing_required:
            msg = f"{self.name}: Missing required columns: {missing_required}"
            logger.error(msg)
            if raise_error:
                raise ValueError(msg)
            return False

        if missing_optional:
            logger.warning(f"{self.name}: Missing optional columns: {missing_optional}")

        return True

    def get_column_with_fallback(
        self,
        df: pd.DataFrame,
        primary: str,
        fallbacks: List[str],
        raise_error: bool = False
    ) -> Optional[str]:
        """
        Get column name with fallback options.

        Args:
            df: DataFrame to check
            primary: Primary column name to try
            fallbacks: List of fallback column names
            raise_error: If True, raises ValueError if no column found

        Returns:
            Column name found, or None
        """
        if primary in df.columns:
            return primary

        for fallback in fallbacks:
            if fallback in df.columns:
                logger.warning(
                    f"{self.name}: Column '{primary}' not found, "
                    f"using fallback: '{fallback}'"
                )
                return fallback

        msg = f"{self.name}: No column found. Tried: {[primary] + fallbacks}"
        logger.error(msg)
        if raise_error:
            raise ValueError(msg)

        return None

    def log_dataframe_info(
        self,
        df: pd.DataFrame,
        name: str = "DataFrame",
        show_columns: bool = False
    ):
        """
        Log DataFrame information for debugging.

        Args:
            df: DataFrame to log
            name: Name for logging
            show_columns: If True, shows column names
        """
        logger.info(f"{name}: {len(df):,} rows, {len(df.columns)} columns")

        if show_columns:
            logger.debug(f"Columns: {list(df.columns)}")

        # Memory usage
        memory_mb = df.memory_usage(deep=True).sum() / 1024 / 1024
        logger.debug(f"Memory usage: {memory_mb:.1f} MB")

    def add_result(
        self,
        key: str,
        value: Any,
        overwrite: bool = True
    ):
        """
        Add result to results dictionary.

        Args:
            key: Result key
            value: Result value
            overwrite: If False, raises error if key already exists
        """
        if not overwrite and key in self.results:
            raise ValueError(f"Result key already exists: {key}")

        self.results[key] = value
        logger.debug(f"Added result: {key}")

    def get_result(
        self,
        key: str,
        default: Any = None
    ) -> Any:
        """
        Get result from results dictionary.

        Args:
            key: Result key
            default: Default value if key not found

        Returns:
            Result value or default
        """
        return self.results.get(key, default)

    def save_results(
        self,
        output_path: Optional[Path] = None,
        title: Optional[str] = None,
        sections: Optional[List[str]] = None
    ):
        """
        Save results to text file.

        Args:
            output_path: Output file path (default: DATA_OUTPUTS_DIR/[name]_results.txt)
            title: Report title (default: self.name + " Results")
            sections: List of result keys to include (default: all)
        """
        if output_path is None:
            # Create default filename from analyzer name
            filename = self.name.lower().replace(' ', '_') + '_results.txt'
            output_path = DATA_OUTPUTS_DIR / filename

        output_path.parent.mkdir(parents=True, exist_ok=True)

        if title is None:
            title = f"{self.name} - Analysis Results"

        # Determine sections to save
        if sections is None:
            sections = list(self.results.keys())

        # Write results
        with open(output_path, 'w', encoding='utf-8') as f:
            # Header
            f.write("=" * 80 + "\n")
            f.write(f"{title}\n")
            f.write("=" * 80 + "\n\n")

            # Timestamp
            f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Analyzer: {self.name}\n\n")

            # Results sections
            for section in sections:
                if section not in self.results:
                    logger.warning(f"Result section not found: {section}")
                    continue

                f.write("\n" + "-" * 80 + "\n")
                f.write(f"{section.replace('_', ' ').upper()}\n")
                f.write("-" * 80 + "\n\n")

                self._format_result_section(f, self.results[section])

            f.write("\n" + "=" * 80 + "\n")
            f.write("End of Report\n")
            f.write("=" * 80 + "\n")

        logger.info(f"Results saved to: {output_path}")

    def _format_result_section(self, file_handle, data: Any, indent: int = 0):
        """
        Format and write result section to file.

        Args:
            file_handle: Open file handle
            data: Data to format (dict, DataFrame, list, or primitive)
            indent: Indentation level
        """
        prefix = "  " * indent

        if isinstance(data, dict):
            for key, value in data.items():
                if isinstance(value, (dict, list, pd.DataFrame)):
                    file_handle.write(f"{prefix}{key}:\n")
                    self._format_result_section(file_handle, value, indent + 1)
                else:
                    file_handle.write(f"{prefix}{key}: {self._format_value(value)}\n")

        elif isinstance(data, pd.DataFrame):
            # Format DataFrame as table
            file_handle.write(f"{prefix}{data.to_string(index=False)}\n")

        elif isinstance(data, list):
            for i, item in enumerate(data):
                if isinstance(item, (dict, list, pd.DataFrame)):
                    file_handle.write(f"{prefix}[{i}]:\n")
                    self._format_result_section(file_handle, item, indent + 1)
                else:
                    file_handle.write(f"{prefix}- {self._format_value(item)}\n")

        else:
            file_handle.write(f"{prefix}{self._format_value(data)}\n")

    def _format_value(self, value: Any) -> str:
        """Format a value for display."""
        if isinstance(value, float):
            if abs(value) >= 1000:
                return f"{value:,.1f}"
            else:
                return f"{value:.2f}"
        elif isinstance(value, int):
            return f"{value:,}"
        else:
            return str(value)

    def save_dataframe_csv(
        self,
        df: pd.DataFrame,
        filename: str,
        output_dir: Optional[Path] = None
    ):
        """
        Save DataFrame to CSV.

        Args:
            df: DataFrame to save
            filename: Output filename (e.g., 'results.csv')
            output_dir: Output directory (default: DATA_OUTPUTS_DIR)
        """
        if output_dir is None:
            output_dir = DATA_OUTPUTS_DIR

        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / filename

        df.to_csv(output_path, index=False, encoding='utf-8')
        logger.info(f"DataFrame saved to: {output_path} ({len(df):,} rows)")

    def get_config_value(
        self,
        key: str,
        default: Any = None,
        section: Optional[str] = None
    ) -> Any:
        """
        Get configuration value.

        Args:
            key: Configuration key
            default: Default value if key not found
            section: Config section to search (default: self.section_config)

        Returns:
            Configuration value or default
        """
        config = self.section_config if section is None else self._get_nested_config(section)
        return config.get(key, default)

    def log_summary_statistics(
        self,
        df: pd.DataFrame,
        column: str,
        label: Optional[str] = None
    ):
        """
        Log summary statistics for a column.

        Args:
            df: DataFrame
            column: Column name
            label: Optional label for logging (default: column name)
        """
        if column not in df.columns:
            logger.warning(f"Column not found: {column}")
            return

        if label is None:
            label = column

        values = df[column].dropna()

        logger.info(f"{label} statistics:")
        logger.info(f"  Count: {len(values):,}")
        logger.info(f"  Mean: {values.mean():.2f}")
        logger.info(f"  Median: {values.median():.2f}")
        logger.info(f"  Std: {values.std():.2f}")
        logger.info(f"  Min: {values.min():.2f}")
        logger.info(f"  Max: {values.max():.2f}")
        logger.info(f"  25th percentile: {values.quantile(0.25):.2f}")
        logger.info(f"  75th percentile: {values.quantile(0.75):.2f}")


# Convenience decorator for analysis methods
def requires_columns(*columns):
    """
    Decorator to validate required columns before running analysis method.

    Usage:
        @requires_columns('ENERGY_CONSUMPTION_CURRENT', 'TOTAL_FLOOR_AREA')
        def analyze(self, df: pd.DataFrame) -> Dict:
            # ... analysis code
    """
    def decorator(func):
        def wrapper(self, df: pd.DataFrame, *args, **kwargs):
            if not hasattr(self, 'validate_required_columns'):
                raise AttributeError(
                    "Method must be used with BaseAnalyzer subclass"
                )

            self.validate_required_columns(df, list(columns))
            return func(self, df, *args, **kwargs)

        return wrapper
    return decorator
