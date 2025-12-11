"""
Geography Lookup Module

Provides geographic hierarchies and lookups for EPC analysis:
- Postcode → Local Authority
- Local Authority → Region
- Postcode → Parliamentary Constituency
- Local Authority name/code standardization

Data sources: ONS Postcode Directory, ONS Geographic Lookups
"""

import pandas as pd
from pathlib import Path
from typing import Dict, Optional
from loguru import logger
import requests
from io import BytesIO
import zipfile

import sys
sys.path.append(str(Path(__file__).parent.parent.parent))
from config.config import load_config, DATA_RAW_DIR


class GeographyLookup:
    """
    Manages geographic lookups and hierarchies for England and Wales.

    Provides mapping between different geographic levels:
    - Postcode
    - Local Authority District (LAD)
    - Region (Government Office Region)
    - Parliamentary Constituency
    """

    # ONS lookup table URLs (these may need updating)
    ONS_URLS = {
        "postcode_directory": "https://www.arcgis.com/sharing/rest/content/items/d5e42412aef04d3da69ab79ae8157b84/data",
        "lad_to_region": "https://services1.arcgis.com/ESMARspQHYMw9BZ9/arcgis/rest/services/LAD_DEC_2021_GB_NC/FeatureServer/0/query?outFields=*&where=1%3D1&f=geojson"
    }

    # Government Office Regions for England
    REGIONS = [
        "North East",
        "North West",
        "Yorkshire and The Humber",
        "East Midlands",
        "West Midlands",
        "East of England",
        "London",
        "South East",
        "South West",
        "Wales"
    ]

    def __init__(self, data_dir: Optional[Path] = None):
        """
        Initialize geography lookup.

        Args:
            data_dir: Directory for lookup data (default: DATA_RAW_DIR/geography)
        """
        if data_dir is None:
            data_dir = DATA_RAW_DIR / "geography"

        self.data_dir = data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # Lookup tables (loaded on demand)
        self._postcode_lookup = None
        self._lad_lookup = None
        self._constituency_lookup = None

        logger.info(f"Initialized GeographyLookup (data dir: {self.data_dir})")

    def download_ons_postcode_directory(self, force_redownload: bool = False) -> Path:
        """
        Download ONS Postcode Directory.

        This contains postcode to LAD, region, constituency mappings.

        Args:
            force_redownload: Force redownload even if file exists

        Returns:
            Path to downloaded CSV file
        """
        output_file = self.data_dir / "onspd_latest.csv"

        if output_file.exists() and not force_redownload:
            logger.info(f"ONS Postcode Directory already exists: {output_file}")
            return output_file

        logger.info("Downloading ONS Postcode Directory...")
        logger.info("Note: This is a large file (~500MB compressed, ~2GB uncompressed)")

        # NOTE: The actual ONS Postcode Directory URL structure is complex
        # Users should download manually from:
        # https://geoportal.statistics.gov.uk/datasets/ons-postcode-directory-latest-centroids
        #
        # For now, create a placeholder function

        logger.warning("Automatic download not implemented yet.")
        logger.info("Please download manually from:")
        logger.info("https://geoportal.statistics.gov.uk/datasets/ons-postcode-directory-latest-centroids")
        logger.info(f"Save to: {output_file}")

        return None

    def load_postcode_lookup(self, csv_path: Optional[Path] = None) -> pd.DataFrame:
        """
        Load postcode to geographic area lookup table.

        Args:
            csv_path: Path to ONSPD CSV (default: auto-detect in data_dir)

        Returns:
            DataFrame with postcode mappings
        """
        if self._postcode_lookup is not None:
            return self._postcode_lookup

        if csv_path is None:
            csv_path = self.data_dir / "onspd_latest.csv"

        if not csv_path.exists():
            logger.error(f"Postcode lookup not found: {csv_path}")
            logger.info("Creating minimal lookup from EPC data...")
            return self._create_minimal_lookup()

        logger.info(f"Loading postcode lookup from {csv_path}...")

        # Load relevant columns
        # Actual ONSPD columns: pcd, ladcd, lsoa11, msoa11, oslaua, osward, ctry, rgn, pcon
        try:
            self._postcode_lookup = pd.read_csv(
                csv_path,
                usecols=[
                    'pcds',      # Postcode (current)
                    'oslaua',    # Local Authority District code
                    'oseast1m',  # Easting
                    'osnrth1m',  # Northing
                    'rgn',       # Region code
                    'pcon',      # Parliamentary Constituency code
                    'ctry'       # Country code
                ],
                low_memory=False
            )

            logger.info(f"Loaded {len(self._postcode_lookup):,} postcode mappings")
            return self._postcode_lookup

        except Exception as e:
            logger.error(f"Error loading postcode lookup: {e}")
            return self._create_minimal_lookup()

    def _create_minimal_lookup(self) -> pd.DataFrame:
        """
        Create minimal lookup table from existing EPC data.

        This is a fallback when ONS data is not available.
        """
        logger.info("Creating minimal geographic lookup...")

        # Check if we have processed EPC data to derive lookups from
        processed_file = DATA_RAW_DIR.parent / "processed" / "epc_london_validated.csv"

        if processed_file.exists():
            logger.info(f"Deriving lookup from {processed_file}...")
            df = pd.read_csv(processed_file, usecols=['POSTCODE', 'LOCAL_AUTHORITY'], nrows=100000)

            # Create minimal lookup
            lookup = df.groupby('POSTCODE')['LOCAL_AUTHORITY'].first().reset_index()
            lookup.columns = ['postcode', 'local_authority']

            self._postcode_lookup = lookup
            return lookup
        else:
            logger.warning("No data available for minimal lookup")
            return pd.DataFrame(columns=['postcode', 'local_authority', 'region', 'constituency'])

    def get_lad_name_lookup(self) -> Dict[str, str]:
        """
        Get Local Authority District code to name mapping.

        Returns:
            Dictionary mapping LAD code to name
        """
        # Hardcoded common LADs (should be replaced with full ONS lookup)
        lad_names = {
            # London
            'E09000001': 'City of London',
            'E09000002': 'Barking and Dagenham',
            'E09000003': 'Barnet',
            'E09000004': 'Bexley',
            'E09000005': 'Brent',
            'E09000006': 'Bromley',
            'E09000007': 'Camden',
            'E09000008': 'Croydon',
            'E09000009': 'Ealing',
            'E09000010': 'Enfield',
            'E09000011': 'Greenwich',
            'E09000012': 'Hackney',
            'E09000013': 'Hammersmith and Fulham',
            'E09000014': 'Haringey',
            'E09000015': 'Harrow',
            'E09000016': 'Havering',
            'E09000017': 'Hillingdon',
            'E09000018': 'Hounslow',
            'E09000019': 'Islington',
            'E09000020': 'Kensington and Chelsea',
            'E09000021': 'Kingston upon Thames',
            'E09000022': 'Lambeth',
            'E09000023': 'Lewisham',
            'E09000024': 'Merton',
            'E09000025': 'Newham',
            'E09000026': 'Redbridge',
            'E09000027': 'Richmond upon Thames',
            'E09000028': 'Southwark',
            'E09000029': 'Sutton',
            'E09000030': 'Tower Hamlets',
            'E09000031': 'Waltham Forest',
            'E09000032': 'Wandsworth',
            'E09000033': 'Westminster',
        }

        return lad_names

    def get_region_name_lookup(self) -> Dict[str, str]:
        """
        Get region code to name mapping.

        Returns:
            Dictionary mapping region code to name
        """
        region_names = {
            'E12000001': 'North East',
            'E12000002': 'North West',
            'E12000003': 'Yorkshire and The Humber',
            'E12000004': 'East Midlands',
            'E12000005': 'West Midlands',
            'E12000006': 'East of England',
            'E12000007': 'London',
            'E12000008': 'South East',
            'E12000009': 'South West',
            'W92000004': 'Wales'
        }

        return region_names

    def enrich_epc_data(
        self,
        df: pd.DataFrame,
        postcode_col: str = 'POSTCODE'
    ) -> pd.DataFrame:
        """
        Enrich EPC data with geographic hierarchies.

        Adds columns:
        - local_authority_name
        - region_name
        - constituency_name

        Args:
            df: EPC DataFrame
            postcode_col: Name of postcode column

        Returns:
            Enriched DataFrame
        """
        logger.info("Enriching EPC data with geographic information...")

        # Load lookup tables
        postcode_lookup = self.load_postcode_lookup()

        if postcode_lookup is None or postcode_lookup.empty:
            logger.warning("No postcode lookup available - skipping geographic enrichment")
            return df

        # Clean postcodes
        df['postcode_clean'] = df[postcode_col].str.upper().str.replace(' ', '')

        if 'postcode' in postcode_lookup.columns:
            postcode_lookup['postcode_clean'] = postcode_lookup['postcode'].str.upper().str.replace(' ', '')

            # Merge
            df_enriched = df.merge(
                postcode_lookup,
                on='postcode_clean',
                how='left'
            )

            # Add name lookups
            lad_names = self.get_lad_name_lookup()
            region_names = self.get_region_name_lookup()

            if 'local_authority' in df_enriched.columns:
                df_enriched['local_authority_name'] = df_enriched['local_authority'].map(lad_names)

            if 'region' in df_enriched.columns:
                df_enriched['region_name'] = df_enriched['region'].map(region_names)

            logger.info("Geographic enrichment complete")
            return df_enriched

        else:
            logger.warning("Postcode lookup format not recognized")
            return df

    def aggregate_by_geography(
        self,
        df: pd.DataFrame,
        level: str,
        metrics: Dict[str, str]
    ) -> pd.DataFrame:
        """
        Aggregate EPC data by geographic level.

        Args:
            df: Enriched EPC DataFrame
            level: Geographic level ('national', 'regional', 'local_authority', 'constituency')
            metrics: Dictionary of {column: aggregation} e.g., {'PROPERTY_COUNT': 'count'}

        Returns:
            Aggregated DataFrame
        """
        logger.info(f"Aggregating by {level}...")

        if level == 'national':
            # National aggregate
            agg_df = df.agg(metrics).to_frame().T
            agg_df['geography_level'] = 'National'
            agg_df['geography_name'] = 'England and Wales'

        elif level == 'regional':
            if 'region_name' not in df.columns:
                logger.error("region_name column not found - run enrich_epc_data() first")
                return pd.DataFrame()

            agg_df = df.groupby('region_name').agg(metrics).reset_index()
            agg_df['geography_level'] = 'Regional'
            agg_df.rename(columns={'region_name': 'geography_name'}, inplace=True)

        elif level == 'local_authority':
            if 'local_authority_name' not in df.columns:
                logger.error("local_authority_name column not found - run enrich_epc_data() first")
                return pd.DataFrame()

            agg_df = df.groupby('local_authority_name').agg(metrics).reset_index()
            agg_df['geography_level'] = 'Local Authority'
            agg_df.rename(columns={'local_authority_name': 'geography_name'}, inplace=True)

        elif level == 'constituency':
            if 'constituency_name' not in df.columns:
                logger.error("constituency_name column not found - run enrich_epc_data() first")
                return pd.DataFrame()

            agg_df = df.groupby('constituency_name').agg(metrics).reset_index()
            agg_df['geography_level'] = 'Constituency'
            agg_df.rename(columns={'constituency_name': 'geography_name'}, inplace=True)

        else:
            raise ValueError(f"Unknown geography level: {level}")

        logger.info(f"Aggregation complete: {len(agg_df)} {level} areas")
        return agg_df


def main():
    """Test geography lookup functionality."""
    logger.info("Testing Geography Lookup...")

    geo = GeographyLookup()

    # Test LAD lookup
    lad_names = geo.get_lad_name_lookup()
    logger.info(f"Loaded {len(lad_names)} LAD name mappings")

    # Test region lookup
    region_names = geo.get_region_name_lookup()
    logger.info(f"Loaded {len(region_names)} region name mappings")

    logger.info("Geography Lookup test complete")


if __name__ == "__main__":
    main()
