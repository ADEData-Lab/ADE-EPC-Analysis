"""
Geographic Aggregation Utilities

Centralized utilities for geographic analysis and aggregation.
Eliminates duplication across heat_pump_potential, heat_network_potential,
heating_fuel_analysis, and other modules.

Created as part of code optimization initiative to reduce 240-300 lines
of duplicated geographic aggregation logic.
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple, Union, Callable
from loguru import logger


class GeographicAggregator:
    """
    Centralized geographic analysis and aggregation utilities.

    Provides standardized methods for:
    - Geographic column resolution with fallbacks
    - Multi-level aggregation (national, regional, LA, constituency)
    - Flexible metric aggregation
    - Summary formatting

    Example Usage:
    -------------
    >>> agg = GeographicAggregator()
    >>> result = agg.aggregate_by_geography(
    ...     df,
    ...     metrics={
    ...         'energy_consumption': 'mean',
    ...         'property_count': 'count',
    ...         'epc_rating': lambda x: x.value_counts().to_dict()
    ...     },
    ...     level='local_authority'
    ... )
    """

    # Standard geography column mappings by level
    GEOGRAPHY_COLUMNS = {
        'national': None,  # Special case - no column needed
        'regional': ['region_name', 'REGION', 'GOR'],
        'local_authority': [
            'local_authority_name',
            'LOCAL_AUTHORITY',
            'LOCAL_AUTHORITY_LABEL',
            'LA_NAME',
            'POSTTOWN'
        ],
        'constituency': [
            'constituency_name',
            'CONSTITUENCY',
            'CONSTITUENCY_NAME',
            'PCON'
        ]
    }

    def __init__(self):
        """Initialize the geographic aggregator."""
        logger.debug("Initialized GeographicAggregator")

    def get_geography_column(
        self,
        df: pd.DataFrame,
        level: str,
        custom_col: Optional[str] = None,
        allow_fallback: bool = True
    ) -> Optional[str]:
        """
        Resolve geography column with fallback logic.

        Args:
            df: DataFrame to check
            level: Geographic level ('regional', 'local_authority', 'constituency')
            custom_col: Custom column name (if provided, checks this first)
            allow_fallback: If True, tries fallback columns

        Returns:
            Column name found, or None if not found
        """
        if level == 'national':
            return None  # National doesn't need a column

        # Try custom column first
        if custom_col and custom_col in df.columns:
            return custom_col

        # Try standard columns for this level
        if level in self.GEOGRAPHY_COLUMNS:
            for col in self.GEOGRAPHY_COLUMNS[level]:
                if col in df.columns:
                    logger.debug(f"Using geography column: {col} for level: {level}")
                    return col

        # Last resort: try all fallbacks
        if allow_fallback:
            for fallback_level, cols in self.GEOGRAPHY_COLUMNS.items():
                if cols:  # Skip national (None)
                    for col in cols:
                        if col in df.columns:
                            logger.warning(
                                f"Geography column for '{level}' not found, "
                                f"using fallback: {col}"
                            )
                            return col

        logger.error(f"No geography column found for level: {level}")
        logger.debug(f"Available columns: {list(df.columns)[:20]}...")
        return None

    def aggregate_by_geography(
        self,
        df: pd.DataFrame,
        metrics: Dict[str, Union[str, Callable]],
        level: str = 'national',
        geography_col: Optional[str] = None,
        include_percentages: bool = False
    ) -> pd.DataFrame:
        """
        Aggregate data by geographic level.

        Args:
            df: DataFrame with data to aggregate
            metrics: Dictionary of {column: aggregation_function}
                    Aggregation can be string ('mean', 'sum', 'count') or callable
            level: Geographic level ('national', 'regional', 'local_authority', 'constituency')
            geography_col: Optional specific column to use
            include_percentages: If True, adds percentage columns for counts

        Returns:
            DataFrame with aggregated results by geography

        Example:
            >>> metrics = {
            ...     'energy_consumption': 'mean',
            ...     'property_count': 'count',
            ...     'epc_rating': lambda x: x.value_counts().to_dict()
            ... }
            >>> result = agg.aggregate_by_geography(df, metrics, 'local_authority')
        """
        if level == 'national':
            return self._aggregate_national(df, metrics, include_percentages)

        # Resolve geography column
        geo_col = self.get_geography_column(df, level, geography_col)
        if geo_col is None:
            logger.error(f"Cannot aggregate: no geography column for level '{level}'")
            return pd.DataFrame()

        return self._aggregate_by_column(
            df, geo_col, metrics, level, include_percentages
        )

    def _aggregate_national(
        self,
        df: pd.DataFrame,
        metrics: Dict[str, Union[str, Callable]],
        include_percentages: bool
    ) -> pd.DataFrame:
        """Aggregate at national level (single row summary)."""
        total = len(df)
        result = {'geography': 'England and Wales', 'total_properties': total}

        for column, agg_func in metrics.items():
            if column not in df.columns:
                logger.warning(f"Column not found: {column}")
                continue

            try:
                if callable(agg_func):
                    result[column] = agg_func(df[column])
                elif agg_func == 'count':
                    result[column] = total
                elif agg_func in ['mean', 'median', 'sum', 'min', 'max', 'std']:
                    result[column] = getattr(df[column], agg_func)()
                else:
                    result[column] = df[column].agg(agg_func)
            except Exception as e:
                logger.error(f"Error aggregating {column} with {agg_func}: {e}")
                result[column] = None

        result_df = pd.DataFrame([result])
        result_df['geography_level'] = 'National'

        return result_df

    def _aggregate_by_column(
        self,
        df: pd.DataFrame,
        geo_col: str,
        metrics: Dict[str, Union[str, Callable]],
        level: str,
        include_percentages: bool
    ) -> pd.DataFrame:
        """Aggregate by specific geography column."""
        # Filter out missing geographies
        df_clean = df[df[geo_col].notna()].copy()

        if len(df_clean) == 0:
            logger.warning("No valid geography values found")
            return pd.DataFrame()

        # Build aggregation dictionary
        agg_dict = {}
        for column, agg_func in metrics.items():
            if column in df_clean.columns:
                agg_dict[column] = agg_func

        # Add property count if not already included
        if 'property_count' not in agg_dict:
            agg_dict['_count'] = 'size'

        # Perform aggregation
        try:
            result_df = df_clean.groupby(geo_col, as_index=False).agg(agg_dict)
        except Exception as e:
            logger.error(f"Aggregation failed: {e}")
            return pd.DataFrame()

        # Rename columns
        result_df = result_df.rename(columns={geo_col: 'geography'})
        if '_count' in result_df.columns:
            result_df = result_df.rename(columns={'_count': 'property_count'})

        # Add percentages if requested
        if include_percentages and 'property_count' in result_df.columns:
            total = result_df['property_count'].sum()
            result_df['pct_of_total'] = (result_df['property_count'] / total * 100)

        # Add metadata
        result_df['geography_level'] = level

        # Sort by property count descending
        if 'property_count' in result_df.columns:
            result_df = result_df.sort_values('property_count', ascending=False)

        logger.info(f"Aggregated {len(result_df)} {level} areas")

        return result_df

    def calculate_tier_distribution(
        self,
        df: pd.DataFrame,
        tier_column: str,
        geography_col: Optional[str] = None,
        level: str = 'local_authority'
    ) -> pd.DataFrame:
        """
        Calculate tier distribution by geography.

        Specialized method for suitability tiers, heat network tiers, etc.

        Args:
            df: DataFrame with tier classifications
            tier_column: Column containing tier values
            geography_col: Geography column to group by
            level: Geographic level

        Returns:
            DataFrame with tier counts/percentages by geography
        """
        if tier_column not in df.columns:
            logger.error(f"Tier column not found: {tier_column}")
            return pd.DataFrame()

        # Get tier value counts as aggregation function
        def tier_counts(x):
            return x.value_counts().to_dict()

        # Aggregate
        result = self.aggregate_by_geography(
            df,
            metrics={tier_column: tier_counts},
            level=level,
            geography_col=geography_col
        )

        if result.empty:
            return result

        # Expand tier counts to separate columns
        tier_dicts = result[tier_column].apply(
            lambda x: x if isinstance(x, dict) else {}
        )

        # Get all unique tiers
        all_tiers = set()
        for tier_dict in tier_dicts:
            all_tiers.update(tier_dict.keys())

        # Create column for each tier
        for tier in sorted(all_tiers):
            result[f'tier_{tier}'] = tier_dicts.apply(
                lambda x: x.get(tier, 0)
            )

        # Remove the original tier_column with dicts
        result = result.drop(columns=[tier_column])

        return result

    def identify_priority_areas(
        self,
        df: pd.DataFrame,
        metric_column: str,
        threshold: float,
        geography_col: Optional[str] = None,
        level: str = 'local_authority',
        ascending: bool = False
    ) -> pd.DataFrame:
        """
        Identify priority geographic areas based on a metric threshold.

        Args:
            df: DataFrame with data
            metric_column: Column to use for prioritization
            threshold: Minimum/maximum threshold value
            geography_col: Geography column
            level: Geographic level
            ascending: If True, values below threshold are priority (lower is better)

        Returns:
            DataFrame of priority areas
        """
        # Aggregate data
        result = self.aggregate_by_geography(
            df,
            metrics={metric_column: 'mean'},  # Can be customized
            level=level,
            geography_col=geography_col
        )

        if result.empty:
            return result

        # Filter by threshold
        if ascending:
            priority = result[result[metric_column] <= threshold].copy()
        else:
            priority = result[result[metric_column] >= threshold].copy()

        # Sort
        priority = priority.sort_values(metric_column, ascending=ascending)

        logger.info(
            f"Identified {len(priority)} priority areas "
            f"(threshold: {threshold}, metric: {metric_column})"
        )

        return priority

    def format_summary_text(
        self,
        summary_df: pd.DataFrame,
        title: str = "Geographic Summary",
        top_n: int = 10
    ) -> str:
        """
        Format geographic summary as text for reports.

        Args:
            summary_df: DataFrame from aggregate_by_geography()
            title: Report title
            top_n: Number of top areas to show

        Returns:
            Formatted text string
        """
        lines = [
            title,
            "=" * len(title),
            "",
            f"Total areas: {len(summary_df)}",
            ""
        ]

        if 'property_count' in summary_df.columns:
            total_properties = summary_df['property_count'].sum()
            lines.append(f"Total properties: {total_properties:,}")
            lines.append("")

        if len(summary_df) > 0:
            lines.append(f"Top {min(top_n, len(summary_df))} Areas:")
            lines.append("-" * 70)

            for idx, row in summary_df.head(top_n).iterrows():
                geo_name = row.get('geography', 'Unknown')
                prop_count = row.get('property_count', 0)

                line = f"{idx+1}. {geo_name}: {prop_count:,} properties"

                # Add other metrics
                for col in summary_df.columns:
                    if col not in ['geography', 'property_count', 'geography_level', 'pct_of_total']:
                        value = row.get(col)
                        if pd.notna(value):
                            if isinstance(value, float):
                                line += f", {col}: {value:.1f}"
                            else:
                                line += f", {col}: {value}"

                lines.append(line)

        return "\n".join(lines)


# Convenience functions for backward compatibility

def aggregate_by_geography(
    df: pd.DataFrame,
    metrics: Dict[str, Union[str, Callable]],
    level: str = 'national',
    geography_col: Optional[str] = None
) -> pd.DataFrame:
    """
    Convenience function for geographic aggregation.

    See GeographicAggregator.aggregate_by_geography() for full documentation.
    """
    agg = GeographicAggregator()
    return agg.aggregate_by_geography(df, metrics, level, geography_col)


def get_geography_column(
    df: pd.DataFrame,
    level: str,
    custom_col: Optional[str] = None
) -> Optional[str]:
    """
    Convenience function to resolve geography column.

    See GeographicAggregator.get_geography_column() for full documentation.
    """
    agg = GeographicAggregator()
    return agg.get_geography_column(df, level, custom_col)
