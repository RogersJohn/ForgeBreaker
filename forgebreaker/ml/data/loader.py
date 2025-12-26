"""Load and validate 17Lands game data.

Handles gzipped CSV files from 17Lands S3 bucket.
Validates schema and provides filtering utilities.
"""

from pathlib import Path
from typing import Sequence

import pandas as pd


class SchemaValidationError(Exception):
    """Raised when data doesn't match expected schema."""

    pass


# Required columns in 17Lands game data
REQUIRED_COLUMNS = frozenset([
    "expansion",
    "event_type",
    "draft_id",
    "game_time",
    "won",
    "on_play",
    "num_mulligans",
    "user_game_win_rate_bucket",
])


def load_17lands_csv(file_path: Path) -> pd.DataFrame:
    """Load a gzipped 17Lands CSV file.

    Args:
        file_path: Path to .csv.gz file

    Returns:
        DataFrame with game data
    """
    return pd.read_csv(file_path, compression="gzip")


def validate_schema(df: pd.DataFrame) -> None:
    """Validate that DataFrame has required columns.

    Args:
        df: DataFrame to validate

    Raises:
        SchemaValidationError: If required columns are missing
    """
    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise SchemaValidationError(
            f"Missing required columns: {sorted(missing)}"
        )


def get_deck_columns(df: pd.DataFrame) -> list[str]:
    """Get all deck_* columns from DataFrame.

    Args:
        df: DataFrame with deck columns

    Returns:
        List of column names starting with 'deck_'
    """
    return [c for c in df.columns if c.startswith("deck_")]


def filter_by_set(df: pd.DataFrame, set_code: str) -> pd.DataFrame:
    """Filter DataFrame to a single set.

    Args:
        df: DataFrame with expansion column
        set_code: Set code to filter to (e.g., "BLB")

    Returns:
        Filtered DataFrame
    """
    return df[df["expansion"] == set_code.upper()].copy()


def combine_datasets(file_paths: Sequence[Path]) -> pd.DataFrame:
    """Combine multiple 17Lands CSV files into one DataFrame.

    Args:
        file_paths: Paths to .csv.gz files

    Returns:
        Combined DataFrame
    """
    dfs = [load_17lands_csv(fp) for fp in file_paths]
    return pd.concat(dfs, ignore_index=True)
