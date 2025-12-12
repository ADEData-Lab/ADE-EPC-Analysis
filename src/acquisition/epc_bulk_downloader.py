"""
EPC Bulk Data Acquisition Module

Downloads and processes bulk EPC data from DESNZ Open Data Communities.
Handles the full England and Wales domestic EPC dataset efficiently.

Data source: https://epc.opendatacommunities.org/downloads
"""

import os
import zipfile
import requests
from pathlib import Path
from typing import List, Optional, Generator
import pandas as pd
from tqdm import tqdm
from loguru import logger
from datetime import datetime

import sys
sys.path.append(str(Path(__file__).parent.parent.parent))
from config.config import load_config, DATA_RAW_DIR


class EPCBulkDownloader:
    """
    Downloads and processes bulk EPC data from DESNZ.

    The bulk files are much faster than API calls for large-scale analysis.
    Files are typically organized by region and updated quarterly.
    """

    # Base URL for bulk downloads
    BASE_URL = "https://epc.opendatacommunities.org/files"

    # Available bulk file identifiers
    # Note: Actual filenames may vary - check the downloads page
    # Wales download requires authentication since 2024
    # Direct URL access returns HTML login page
    # Users must download manually from https://epc.opendatacommunities.org/downloads
    BULK_FILES = {
        "england": "all-domestic-certificates.zip",  # England only (not combined)
        "wales": "domestic-wales.zip"  # Requires authentication
    }

    def __init__(self):
        """Initialize the bulk downloader."""
        self.config = load_config()
        DATA_RAW_DIR.mkdir(parents=True, exist_ok=True)
        logger.info("Initialized EPC Bulk Downloader")

    def download_bulk_file(
        self,
        region: str,
        output_dir: Optional[Path] = None,
        force_redownload: bool = False
    ) -> Path:
        """
        Download a bulk EPC file for a specific region.

        Args:
            region: Region identifier ('england' or 'wales')
            output_dir: Output directory (default: DATA_RAW_DIR)
            force_redownload: Force redownload even if file exists

        Returns:
            Path to downloaded ZIP file
        """
        if region not in self.BULK_FILES:
            raise ValueError(f"Unknown region: {region}. Available: {list(self.BULK_FILES.keys())}")

        if output_dir is None:
            output_dir = DATA_RAW_DIR

        filename = self.BULK_FILES[region]
        output_path = output_dir / filename

        # Check if file already exists
        if output_path.exists() and not force_redownload:
            logger.info(f"Bulk file already exists: {output_path}")
            logger.info(f"File size: {output_path.stat().st_size / (1024**3):.2f} GB")
            return output_path

        # Download file
        url = f"{self.BASE_URL}/{filename}"
        logger.info(f"Downloading {region} bulk data from {url}")
        logger.info("This may take a while (file size: ~2-5 GB)...")

        try:
            response = requests.get(url, stream=True)
            response.raise_for_status()

            # Get total size for progress bar
            total_size = int(response.headers.get('content-length', 0))

            # Download with progress bar
            with open(output_path, 'wb') as f:
                with tqdm(
                    total=total_size,
                    unit='B',
                    unit_scale=True,
                    desc=f"Downloading {region}"
                ) as pbar:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                        pbar.update(len(chunk))

            # Validate that downloaded file is a valid ZIP file
            try:
                with zipfile.ZipFile(output_path, 'r') as test_zip:
                    test_zip.namelist()  # Quick validation
            except zipfile.BadZipFile:
                # File is not a ZIP - likely HTML error page
                output_path.unlink()  # Delete invalid file
                error_msg = (
                    f"Downloaded file for {region} is not a valid ZIP file.\n"
                    f"The DESNZ website now requires authentication.\n"
                    f"Please download manually from: https://epc.opendatacommunities.org/downloads\n"
                    f"See MANUAL_DOWNLOAD_GUIDE.md for instructions."
                )
                logger.error(error_msg)
                raise ValueError(error_msg)

            logger.info(f"Downloaded: {output_path}")
            logger.info(f"File size: {output_path.stat().st_size / (1024**3):.2f} GB")
            return output_path

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to download {region} bulk data: {e}")
            raise

    def extract_bulk_file(
        self,
        zip_path: Path,
        extract_dir: Optional[Path] = None
    ) -> List[Path]:
        """
        Extract a bulk EPC ZIP file.

        Args:
            zip_path: Path to ZIP file
            extract_dir: Directory to extract to (default: same as ZIP)

        Returns:
            List of extracted CSV file paths
        """
        if extract_dir is None:
            extract_dir = zip_path.parent / zip_path.stem

        extract_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"Extracting {zip_path.name}...")

        try:
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                # Get list of CSV files
                csv_files = [f for f in zip_ref.namelist() if f.endswith('.csv')]

                logger.info(f"Found {len(csv_files)} CSV files in archive")

                # Extract with progress bar
                with tqdm(total=len(csv_files), desc="Extracting files") as pbar:
                    for file in csv_files:
                        zip_ref.extract(file, extract_dir)
                        pbar.update(1)

            # Get paths to extracted files
            extracted_paths = [extract_dir / f for f in csv_files]

            logger.info(f"Extracted {len(extracted_paths)} files to {extract_dir}")
            return extracted_paths

        except zipfile.BadZipFile as e:
            logger.error(f"Invalid ZIP file: {e}")
            raise

    def load_csv_in_chunks(
        self,
        csv_path: Path,
        chunk_size: int = 100000
    ) -> Generator[pd.DataFrame, None, None]:
        """
        Load a large CSV file in chunks for memory efficiency.

        Args:
            csv_path: Path to CSV file
            chunk_size: Number of rows per chunk

        Yields:
            DataFrame chunks
        """
        logger.info(f"Reading {csv_path.name} in chunks of {chunk_size:,} rows...")

        try:
            # Count total rows for progress bar
            total_rows = sum(1 for _ in open(csv_path, encoding='utf-8', errors='ignore')) - 1

            logger.info(f"Total rows: {total_rows:,}")

            # Read in chunks
            chunk_iterator = pd.read_csv(
                csv_path,
                chunksize=chunk_size,
                low_memory=False,
                encoding='utf-8',
                on_bad_lines='skip'
            )

            with tqdm(total=total_rows, desc=f"Processing {csv_path.name}") as pbar:
                for chunk in chunk_iterator:
                    yield chunk
                    pbar.update(len(chunk))

        except Exception as e:
            logger.error(f"Error reading CSV {csv_path}: {e}")
            raise

    def _clean_dataframe_for_parquet(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Clean dataframe for parquet conversion by ensuring consistent types.

        Converts all object columns to strings to avoid mixed type issues.

        Args:
            df: DataFrame to clean

        Returns:
            Cleaned DataFrame
        """
        # Convert all object columns to strings to avoid mixed type issues
        for col in df.columns:
            if df[col].dtype == 'object':
                # Handle NaN and mixed types explicitly
                df[col] = df[col].apply(lambda x: '' if pd.isna(x) else str(x))

        return df

    def combine_bulk_data(
        self,
        csv_paths: List[Path],
        output_path: Optional[Path] = None,
        chunk_size: int = 100000,
        filters: Optional[dict] = None
    ) -> Path:
        """
        Combine multiple bulk CSV files into a single dataset.

        Args:
            csv_paths: List of CSV file paths to combine
            output_path: Output file path (default: DATA_RAW_DIR/combined_epc.parquet)
            chunk_size: Chunk size for processing
            filters: Optional filters to apply (e.g., {'PROPERTY_TYPE': ['House']})

        Returns:
            Path to combined output file
        """
        if output_path is None:
            output_path = DATA_RAW_DIR / "epc_england_wales_combined.parquet"

        logger.info(f"Combining {len(csv_paths)} CSV files...")

        # Process and combine files
        all_chunks = []
        total_records = 0

        for csv_path in csv_paths:
            logger.info(f"Processing {csv_path.name}...")

            for chunk in self.load_csv_in_chunks(csv_path, chunk_size):
                # Apply filters if specified
                if filters:
                    for column, values in filters.items():
                        if column in chunk.columns:
                            chunk = chunk[chunk[column].isin(values)]

                all_chunks.append(chunk)
                total_records += len(chunk)

                # Periodically save to avoid memory issues
                if len(all_chunks) >= 10:
                    logger.info(f"Saving intermediate batch ({total_records:,} records so far)...")
                    temp_df = pd.concat(all_chunks, ignore_index=True)

                    # Clean data types before saving to parquet
                    temp_df = self._clean_dataframe_for_parquet(temp_df)

                    # Save or append
                    if output_path.exists():
                        # Append to existing file
                        existing_df = pd.read_parquet(output_path)
                        temp_df = pd.concat([existing_df, temp_df], ignore_index=True)

                    temp_df.to_parquet(output_path, index=False)
                    all_chunks = []

        # Save remaining chunks
        if all_chunks:
            logger.info(f"Saving final batch ({total_records:,} total records)...")
            final_df = pd.concat(all_chunks, ignore_index=True)

            # Clean data types before saving to parquet
            final_df = self._clean_dataframe_for_parquet(final_df)

            if output_path.exists():
                existing_df = pd.read_parquet(output_path)
                final_df = pd.concat([existing_df, final_df], ignore_index=True)

            final_df.to_parquet(output_path, index=False)

        logger.info(f"Combined dataset saved: {output_path}")
        logger.info(f"Total records: {total_records:,}")
        logger.info(f"File size: {output_path.stat().st_size / (1024**3):.2f} GB")

        return output_path

    def download_and_process_all(
        self,
        regions: List[str] = ["england", "wales"],
        force_redownload: bool = False,
        extract: bool = True,
        combine: bool = True
    ) -> Path:
        """
        Complete workflow: download, extract, and combine all regions.

        Args:
            regions: List of regions to download
            force_redownload: Force redownload even if files exist
            extract: Whether to extract ZIP files
            combine: Whether to combine into single dataset

        Returns:
            Path to final combined dataset
        """
        logger.info("Starting bulk EPC data acquisition...")
        logger.info(f"Regions: {regions}")

        all_csv_paths = []

        for region in regions:
            # Download
            zip_path = self.download_bulk_file(
                region,
                force_redownload=force_redownload
            )

            # Extract
            if extract:
                csv_paths = self.extract_bulk_file(zip_path)
                all_csv_paths.extend(csv_paths)

        # Combine
        if combine and all_csv_paths:
            combined_path = self.combine_bulk_data(all_csv_paths)
            return combined_path

        return None


def main():
    """Main execution function for bulk data acquisition."""
    logger.info("Starting EPC bulk data acquisition...")

    downloader = EPCBulkDownloader()

    # Download and process England and Wales
    output_path = downloader.download_and_process_all(
        regions=["england", "wales"],
        force_redownload=False,
        extract=True,
        combine=True
    )

    if output_path:
        logger.info("Bulk data acquisition complete!")
        logger.info(f"Final dataset: {output_path}")
    else:
        logger.error("Bulk data acquisition failed")


if __name__ == "__main__":
    main()
