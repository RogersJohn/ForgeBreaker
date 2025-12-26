"""Tests for 17Lands data loader and schema validation."""

import gzip
from pathlib import Path

import pytest

from forgebreaker.ml.data.loader import (
    load_17lands_csv,
    validate_schema,
    filter_by_set,
    combine_datasets,
    REQUIRED_COLUMNS,
    SchemaValidationError,
)


@pytest.fixture
def sample_csv_content() -> bytes:
    """Valid 17Lands CSV content."""
    header = (
        "expansion,event_type,draft_id,game_time,won,on_play,"
        "num_mulligans,user_game_win_rate_bucket,deck_Lightning_Bolt,deck_Mountain"
    )
    row1 = "BLB,PremierDraft,abc123,2024-01-01,1,1,0,0.5,4,17"
    row2 = "BLB,PremierDraft,abc124,2024-01-01,0,0,1,0.45,3,18"
    return f"{header}\n{row1}\n{row2}\n".encode("utf-8")


@pytest.fixture
def gzipped_csv(tmp_path: Path, sample_csv_content: bytes) -> Path:
    """Create a gzipped CSV file."""
    file_path = tmp_path / "test_data.csv.gz"
    with gzip.open(file_path, "wb") as f:
        f.write(sample_csv_content)
    return file_path


class TestLoadGzippedCsv:
    """Tests for loading gzipped CSV files."""

    def test_loads_gzipped_csv(self, gzipped_csv: Path) -> None:
        """Can load a gzipped CSV file."""
        df = load_17lands_csv(gzipped_csv)
        assert df is not None
        assert len(df) == 2

    def test_returns_dataframe(self, gzipped_csv: Path) -> None:
        """Returns a pandas DataFrame."""
        import pandas as pd

        df = load_17lands_csv(gzipped_csv)
        assert isinstance(df, pd.DataFrame)


class TestSchemaValidation:
    """Tests for schema validation."""

    def test_validates_required_columns(self, gzipped_csv: Path) -> None:
        """Validation passes when all required columns present."""
        df = load_17lands_csv(gzipped_csv)
        # Should not raise
        validate_schema(df)

    def test_expected_columns_present(self, gzipped_csv: Path) -> None:
        """Expected columns are present in the data."""
        df = load_17lands_csv(gzipped_csv)
        for col in REQUIRED_COLUMNS:
            assert col in df.columns

    def test_deck_columns_detected(self, gzipped_csv: Path) -> None:
        """Deck columns (deck_*) are detected."""
        df = load_17lands_csv(gzipped_csv)
        deck_cols = [c for c in df.columns if c.startswith("deck_")]
        assert len(deck_cols) >= 1

    def test_raises_on_missing_columns(self, tmp_path: Path) -> None:
        """Raises SchemaValidationError when required columns missing."""
        # Create CSV missing required columns
        content = b"foo,bar\n1,2\n"
        file_path = tmp_path / "bad_data.csv.gz"
        with gzip.open(file_path, "wb") as f:
            f.write(content)

        df = load_17lands_csv(file_path)
        with pytest.raises(SchemaValidationError, match="Missing required columns"):
            validate_schema(df)


class TestFiltering:
    """Tests for filtering datasets."""

    def test_filters_to_single_set(self, tmp_path: Path) -> None:
        """Can filter data to a single set."""
        # Create CSV with multiple sets
        header = "expansion,event_type,draft_id,game_time,won,on_play,num_mulligans,user_game_win_rate_bucket,deck_Card"
        rows = [
            "BLB,PremierDraft,a,2024-01-01,1,1,0,0.5,4",
            "OTJ,PremierDraft,b,2024-01-01,0,0,1,0.45,3",
            "BLB,PremierDraft,c,2024-01-01,1,1,0,0.5,2",
        ]
        content = (header + "\n" + "\n".join(rows) + "\n").encode("utf-8")

        file_path = tmp_path / "multi_set.csv.gz"
        with gzip.open(file_path, "wb") as f:
            f.write(content)

        df = load_17lands_csv(file_path)
        filtered = filter_by_set(df, "BLB")

        assert len(filtered) == 2
        assert all(filtered["expansion"] == "BLB")


class TestCombineDatasets:
    """Tests for combining multiple datasets."""

    def test_combines_multiple_files(self, tmp_path: Path) -> None:
        """Can combine multiple CSV files into one DataFrame."""
        header = "expansion,event_type,draft_id,game_time,won,on_play,num_mulligans,user_game_win_rate_bucket,deck_Card"

        # File 1
        rows1 = ["BLB,PremierDraft,a,2024-01-01,1,1,0,0.5,4"]
        content1 = (header + "\n" + "\n".join(rows1) + "\n").encode("utf-8")
        file1 = tmp_path / "file1.csv.gz"
        with gzip.open(file1, "wb") as f:
            f.write(content1)

        # File 2
        rows2 = [
            "OTJ,PremierDraft,b,2024-01-01,0,0,1,0.45,3",
            "OTJ,PremierDraft,c,2024-01-01,1,1,0,0.5,2",
        ]
        content2 = (header + "\n" + "\n".join(rows2) + "\n").encode("utf-8")
        file2 = tmp_path / "file2.csv.gz"
        with gzip.open(file2, "wb") as f:
            f.write(content2)

        combined = combine_datasets([file1, file2])

        assert len(combined) == 3
        assert "BLB" in combined["expansion"].values
        assert "OTJ" in combined["expansion"].values
