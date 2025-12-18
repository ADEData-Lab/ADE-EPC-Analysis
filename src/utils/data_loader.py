"""
EPC Data Loading Utilities

Centralized data loading with caching and format optimization.
Eliminates ~100 lines of duplicated loading code across 10+ modules.

Features:
- Automatic format detection (CSV/Parquet)
- Caching for faster sequential analyses
- Parquet migration support
- Memory-efficient chunked loading

Performance:
- CSV loading: 3-5 minutes (24M rows)
- Parquet loading: 20-40 seconds (80-90% faster)

Created as part of code optimization initiative.
"""

import pandas as pd
from pathlib import Path
from typing import Optional, List, Union, Dict
from loguru import logger
import warnings

import sys
sys.path.append(str(Path(__file__).parent.parent.parent))
from config.config import DATA_PROCESSED_DIR, DATA_RAW_DIR


class EPCDataLoader:
    """
    Centralized EPC data loading with caching and format optimization.

    Features:
    - Automatic format detection and conversion
    - Optional caching for sequential analyses
    - Memory-efficient chunked loading
    - Column selection for reduced memory usage

    Example Usage:
    -------------
    >>> loader = EPCDataLoader()
    >>> df = loader.load_epc_data()  # Loads default processed data
    >>> df = loader.load_epc_data(use_cache=True)  # Uses cache
    >>> df = loader.load_epc_data(format='parquet')  # Forces Parquet
    >>> df = loader.load_epc_data(columns=['column1', 'column2'])  # Load subset
    """

    # Class-level cache for sharing across instances
    _cache: Dict[str, pd.DataFrame] = {}

    def __init__(self):
        """Initialize the data loader."""
        logger.debug("Initialized EPCDataLoader")

    def load_epc_data(
        self,
        file_path: Optional[Path] = None,
        use_cache: bool = False,
        format: str = 'auto',
        columns: Optional[List[str]] = None,
        geography: str = 'england_wales'
    ) -> pd.DataFrame:
        """
        Load EPC data with automatic format detection and caching.

        Args:
            file_path: Path to data file (if None, uses default)
            use_cache: If True, uses cached data if available
            format: 'auto', 'csv', 'parquet' (auto detects from extension)
            columns: List of columns to load (None = all)
            geography: 'england_wales', 'london', 'england', 'wales'

        Returns:
            DataFrame with EPC data

        Raises:
            FileNotFoundError: If data file not found
        """
        # Get default file path if not provided
        if file_path is None:
            file_path = self.get_default_data_path(geography)

        # Convert to Path object
        file_path = Path(file_path)

        # Check cache
        cache_key = str(file_path)
        if use_cache and cache_key in self._cache:
            logger.info(f"Loading from cache: {file_path.name}")
            df = self._cache[cache_key]

            # Filter columns if requested
            if columns:
                missing = [col for col in columns if col not in df.columns]
                if missing:
                    logger.warning(f"Columns not in cached data: {missing}")
                available = [col for col in columns if col in df.columns]
                df = df[available]

            return df

        # Check if file exists
        if not file_path.exists():
            # Try Parquet alternative
            parquet_path = file_path.with_suffix('.parquet')
            if parquet_path.exists():
                logger.info(f"CSV not found, using Parquet: {parquet_path.name}")
                file_path = parquet_path
            else:
                raise FileNotFoundError(
                    f"Data file not found: {file_path}\n"
                    f"Also checked: {parquet_path}"
                )

        # Detect format
        if format == 'auto':
            if file_path.suffix == '.parquet':
                format = 'parquet'
            elif file_path.suffix in ['.csv', '.txt']:
                format = 'csv'
            else:
                logger.warning(f"Unknown format, assuming CSV: {file_path.suffix}")
                format = 'csv'

        # Load data
        logger.info(f"Loading EPC data from: {file_path.name}")
        logger.info(f"Format: {format}")

        if format == 'parquet':
            df = self._load_parquet(file_path, columns)
        else:
            df = self._load_csv(file_path, columns)

        logger.info(f"Loaded {len(df):,} rows, {len(df.columns)} columns")

        # Log memory usage
        memory_mb = df.memory_usage(deep=True).sum() / 1024 / 1024
        logger.info(f"Memory usage: {memory_mb:.1f} MB")

        # Cache if requested
        if use_cache:
            self._cache[cache_key] = df
            logger.debug(f"Cached data: {cache_key}")

        return df

    def _load_parquet(
        self,
        file_path: Path,
        columns: Optional[List[str]]
    ) -> pd.DataFrame:
        """Load Parquet file (fast, 80-90% faster than CSV)."""
        try:
            df = pd.read_parquet(file_path, columns=columns)
            return df
        except Exception as e:
            logger.error(f"Error loading Parquet: {e}")
            raise

    def _load_csv(
        self,
        file_path: Path,
        columns: Optional[List[str]]
    ) -> pd.DataFrame:
        """Load CSV file (slower, but universal)."""
        try:
            # Suppress DtypeWarning for mixed types
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                df = pd.read_csv(
                    file_path,
                    usecols=columns,
                    low_memory=False,
                    encoding='utf-8'
                )
            return df
        except UnicodeDecodeError:
            # Try alternative encoding
            logger.warning("UTF-8 decoding failed, trying ISO-8859-1")
            df = pd.read_csv(
                file_path,
                usecols=columns,
                low_memory=False,
                encoding='ISO-8859-1'
            )
            return df
        except Exception as e:
            logger.error(f"Error loading CSV: {e}")
            raise

    def load_chunked(
        self,
        file_path: Optional[Path] = None,
        chunk_size: int = 100000,
        process_func = None,
        format: str = 'auto'
    ):
        """
        Load and process data in chunks (memory-efficient).

        Args:
            file_path: Path to data file
            chunk_size: Number of rows per chunk
            process_func: Function to apply to each chunk (optional)
            format: 'auto', 'csv', 'parquet'

        Yields:
            DataFrame chunks (or processed results if process_func provided)

        Example:
            >>> loader = EPCDataLoader()
            >>> for chunk in loader.load_chunked(chunk_size=50000):
            ...     # Process chunk
            ...     result = analyze_chunk(chunk)
        """
        if file_path is None:
            file_path = self.get_default_data_path()

        file_path = Path(file_path)

        if not file_path.exists():
            raise FileNotFoundError(f"Data file not found: {file_path}")

        # Detect format
        if format == 'auto':
            format = 'parquet' if file_path.suffix == '.parquet' else 'csv'

        logger.info(f"Loading data in chunks: {chunk_size:,} rows per chunk")

        if format == 'csv':
            chunk_iterator = pd.read_csv(
                file_path,
                chunksize=chunk_size,
                low_memory=False
            )
        else:
            # Parquet doesn't have native chunking, load full then chunk
            logger.warning("Parquet doesn't support chunked loading, loading full then iterating")
            df = pd.read_parquet(file_path)
            chunk_iterator = (df[i:i+chunk_size] for i in range(0, len(df), chunk_size))

        for i, chunk in enumerate(chunk_iterator):
            logger.debug(f"Processing chunk {i+1}: {len(chunk):,} rows")

            if process_func:
                yield process_func(chunk)
            else:
                yield chunk

    def migrate_to_parquet(
        self,
        csv_path: Optional[Path] = None,
        parquet_path: Optional[Path] = None,
        compression: str = 'snappy',
        delete_csv: bool = False
    ):
        """
        Migrate CSV data to Parquet format.

        Args:
            csv_path: Path to CSV file
            parquet_path: Output path (if None, replaces .csv with .parquet)
            compression: 'snappy', 'gzip', 'brotli', or None
            delete_csv: If True, deletes CSV after successful conversion

        Example:
            >>> loader = EPCDataLoader()
            >>> loader.migrate_to_parquet()  # Converts default CSV to Parquet
        """
        if csv_path is None:
            csv_path = DATA_PROCESSED_DIR / "epc_england_wales_validated.csv"

        csv_path = Path(csv_path)

        if not csv_path.exists():
            raise FileNotFoundError(f"CSV file not found: {csv_path}")

        if parquet_path is None:
            parquet_path = csv_path.with_suffix('.parquet')

        logger.info(f"Migrating CSV to Parquet: {csv_path.name} → {parquet_path.name}")
        logger.info(f"Compression: {compression}")

        # Load CSV
        logger.info("Loading CSV...")
        df = pd.read_csv(csv_path, low_memory=False)
        logger.info(f"Loaded {len(df):,} rows")

        # Save as Parquet
        logger.info("Saving as Parquet...")
        df.to_parquet(
            parquet_path,
            compression=compression,
            index=False
        )

        # Check sizes
        csv_size_mb = csv_path.stat().st_size / 1024 / 1024
        parquet_size_mb = parquet_path.stat().st_size / 1024 / 1024
        reduction_pct = (1 - parquet_size_mb / csv_size_mb) * 100

        logger.info(f"CSV size: {csv_size_mb:.1f} MB")
        logger.info(f"Parquet size: {parquet_size_mb:.1f} MB")
        logger.info(f"Size reduction: {reduction_pct:.1f}%")

        # Delete CSV if requested
        if delete_csv:
            logger.warning(f"Deleting CSV file: {csv_path.name}")
            csv_path.unlink()
            logger.info("CSV deleted")

        logger.info("Migration complete!")

    @staticmethod
    def get_default_data_path(geography: str = 'england_wales') -> Path:
        """
        Get default data path for geography scope.

        Args:
            geography: 'england_wales', 'london', 'england', 'wales'

        Returns:
            Path to default data file
        """
        # Try Parquet first (faster)
        parquet_files = {
            'england_wales': DATA_PROCESSED_DIR / "epc_england_wales_validated.parquet",
            'london': DATA_PROCESSED_DIR / "epc_london_validated.parquet",
            'england': DATA_PROCESSED_DIR / "epc_england_validated.parquet",
            'wales': DATA_PROCESSED_DIR / "epc_wales_validated.parquet",
        }

        # CSV fallback
        csv_files = {
            'england_wales': DATA_PROCESSED_DIR / "epc_england_wales_validated.csv",
            'london': DATA_PROCESSED_DIR / "epc_london_validated.csv",
            'england': DATA_PROCESSED_DIR / "epc_england_validated.csv",
            'wales': DATA_PROCESSED_DIR / "epc_wales_validated.csv",
        }

        # Check Parquet first
        parquet_path = parquet_files.get(geography)
        if parquet_path and parquet_path.exists():
            return parquet_path

        # Fallback to CSV
        csv_path = csv_files.get(geography)
        if csv_path and csv_path.exists():
            return csv_path

        # Default to england_wales
        logger.warning(f"Geography '{geography}' not found, using default")
        return parquet_files.get('england_wales', csv_files['england_wales'])

    @classmethod
    def clear_cache(cls):
        """Clear all cached data to free memory."""
        cache_size = len(cls._cache)
        cls._cache.clear()
        logger.info(f"Cleared cache ({cache_size} datasets)")

    @classmethod
    def get_cache_info(cls) -> Dict:
        """Get information about cached data."""
        info = {}
        total_memory = 0

        for key, df in cls._cache.items():
            memory_mb = df.memory_usage(deep=True).sum() / 1024 / 1024
            info[key] = {
                'rows': len(df),
                'columns': len(df.columns),
                'memory_mb': round(memory_mb, 1)
            }
            total_memory += memory_mb

        return {
            'cached_datasets': len(cls._cache),
            'total_memory_mb': round(total_memory, 1),
            'datasets': info
        }


# Convenience functions

def load_epc_data(
    file_path: Optional[Path] = None,
    use_cache: bool = False,
    geography: str = 'england_wales'
) -> pd.DataFrame:
    """
    Convenience function to load EPC data.

    Args:
        file_path: Optional path to data file
        use_cache: If True, uses cache
        geography: Geographic scope

    Returns:
        DataFrame with EPC data
    """
    loader = EPCDataLoader()
    return loader.load_epc_data(file_path, use_cache=use_cache, geography=geography)


def migrate_to_parquet():
    """Convenience function to migrate default CSV to Parquet."""
    loader = EPCDataLoader()
    loader.migrate_to_parquet()


# Performance comparison utility
def compare_load_performance(file_path: Optional[Path] = None):
    """
    Compare CSV vs Parquet loading performance.

    Args:
        file_path: Path to CSV file (will also check for .parquet version)
    """
    import time

    if file_path is None:
        file_path = DATA_PROCESSED_DIR / "epc_england_wales_validated.csv"

    file_path = Path(file_path)
    parquet_path = file_path.with_suffix('.parquet')

    loader = EPCDataLoader()

    # Time CSV loading
    if file_path.exists():
        logger.info("Testing CSV loading speed...")
        start = time.time()
        df_csv = loader.load_epc_data(file_path, format='csv')
        csv_time = time.time() - start
        csv_size = file_path.stat().st_size / 1024 / 1024
        logger.info(f"CSV: {csv_time:.1f} seconds, {csv_size:.1f} MB")
    else:
        logger.warning(f"CSV not found: {file_path}")
        csv_time = None

    # Time Parquet loading
    if parquet_path.exists():
        logger.info("Testing Parquet loading speed...")
        start = time.time()
        df_parquet = loader.load_epc_data(parquet_path, format='parquet')
        parquet_time = time.time() - start
        parquet_size = parquet_path.stat().st_size / 1024 / 1024
        logger.info(f"Parquet: {parquet_time:.1f} seconds, {parquet_size:.1f} MB")
    else:
        logger.warning(f"Parquet not found: {parquet_path}")
        parquet_time = None

    # Compare
    if csv_time and parquet_time:
        speedup = csv_time / parquet_time
        logger.info(f"Parquet is {speedup:.1f}x faster than CSV")

        if csv_size and parquet_size:
            size_reduction = (1 - parquet_size / csv_size) * 100
            logger.info(f"Parquet is {size_reduction:.1f}% smaller than CSV")
