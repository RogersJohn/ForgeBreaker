"""Tests for feature engineering."""

import pandas as pd
import pytest

from forgebreaker.ml.features.engineer import (
    FEATURES,
    TARGET,
    calculate_average_mana_value,
    calculate_mana_curve,
    count_card_types,
    count_total_cards,
    engineer_features,
    extract_colors,
    extract_deck_card_columns,
)


@pytest.fixture
def sample_card_data() -> dict:
    """Card data for test cards."""
    return {
        "Lightning_Bolt": {"type_line": "Instant", "cmc": 1.0, "colors": ["R"]},
        "Llanowar_Elves": {"type_line": "Creature — Elf", "cmc": 1.0, "colors": ["G"]},
        "Mountain": {"type_line": "Basic Land — Mountain", "cmc": 0.0, "colors": []},
        "Shivan_Dragon": {"type_line": "Creature — Dragon", "cmc": 6.0, "colors": ["R"]},
        "Giant_Growth": {"type_line": "Instant", "cmc": 1.0, "colors": ["G"]},
    }


@pytest.fixture
def sample_df() -> pd.DataFrame:
    """Sample 17Lands-style DataFrame."""
    return pd.DataFrame(
        {
            "expansion": ["BLB", "BLB"],
            "event_type": ["PremierDraft", "PremierDraft"],
            "draft_id": ["abc", "def"],
            "game_time": ["2024-01-01", "2024-01-01"],
            "won": [1, 0],
            "on_play": [1, 0],
            "num_mulligans": [0, 1],
            "user_game_win_rate_bucket": [0.5, 0.45],
            "deck_Lightning_Bolt": [4, 3],
            "deck_Llanowar_Elves": [4, 0],
            "deck_Mountain": [17, 18],
            "deck_Shivan_Dragon": [2, 1],
            "deck_Giant_Growth": [0, 2],
        }
    )


class TestExtractDeckColumns:
    """Tests for extracting deck card columns."""

    def test_extracts_deck_card_columns(self, sample_df: pd.DataFrame) -> None:
        """Extracts columns starting with deck_."""
        deck_cols = extract_deck_card_columns(sample_df)
        assert len(deck_cols) == 5
        assert all(c.startswith("deck_") for c in deck_cols)


class TestCountTotalCards:
    """Tests for counting total cards."""

    def test_counts_total_cards(self, sample_df: pd.DataFrame) -> None:
        """Counts sum of all deck_ columns per row."""
        totals = count_total_cards(sample_df)
        # Row 1: 4+4+17+2+0 = 27
        # Row 2: 3+0+18+1+2 = 24
        assert totals.iloc[0] == 27
        assert totals.iloc[1] == 24


class TestCountCardTypes:
    """Tests for counting card types."""

    def test_counts_creatures_lands_spells(
        self, sample_df: pd.DataFrame, sample_card_data: dict
    ) -> None:
        """Counts creatures, lands, and spells using card data."""
        counts = count_card_types(sample_df, sample_card_data)

        # Row 1: Creatures: 4 Llanowar + 2 Shivan = 6
        #        Lands: 17 Mountain = 17
        #        Spells: 4 Lightning = 4
        assert counts["n_creatures"].iloc[0] == 6
        assert counts["n_lands"].iloc[0] == 17
        assert counts["n_noncreature_spells"].iloc[0] == 4


class TestCalculateManaValue:
    """Tests for mana value calculations."""

    def test_calculates_average_mana_value(
        self, sample_df: pd.DataFrame, sample_card_data: dict
    ) -> None:
        """Calculates average mana value of non-land cards."""
        avg_mv = calculate_average_mana_value(sample_df, sample_card_data)
        # Row 1: (4*1 + 4*1 + 2*6) / (4+4+2) = 20/10 = 2.0
        assert avg_mv.iloc[0] == pytest.approx(2.0)


class TestManaCurve:
    """Tests for mana curve calculations."""

    def test_calculates_mana_curve(self, sample_df: pd.DataFrame, sample_card_data: dict) -> None:
        """Calculates counts at each point in the curve."""
        curve = calculate_mana_curve(sample_df, sample_card_data)
        # Row 1: 1-drops: 4 Lightning + 4 Llanowar = 8
        #        5+ drops: 2 Shivan = 2
        assert curve["curve_1_drop"].iloc[0] == 8
        assert curve["curve_5plus_drop"].iloc[0] == 2


class TestExtractColors:
    """Tests for color extraction."""

    def test_extracts_color_pair(self, sample_df: pd.DataFrame, sample_card_data: dict) -> None:
        """Extracts deck colors as one-hot encoding."""
        colors = extract_colors(sample_df, sample_card_data)
        # Row 1 has R (Lightning, Shivan) and G (Llanowar)
        assert colors["color_R"].iloc[0] == 1
        assert colors["color_G"].iloc[0] == 1
        assert colors["color_U"].iloc[0] == 0
        assert colors["color_B"].iloc[0] == 0
        assert colors["color_W"].iloc[0] == 0


class TestEngineerFeatures:
    """Tests for full feature engineering pipeline."""

    def test_preserves_game_context_features(
        self, sample_df: pd.DataFrame, sample_card_data: dict
    ) -> None:
        """Preserves on_play, num_mulligans, user_skill_bucket."""
        features = engineer_features(sample_df, sample_card_data)
        assert "on_play" in features.columns
        assert "num_mulligans" in features.columns
        assert "user_skill_bucket" in features.columns
        assert features["on_play"].iloc[0] == 1
        assert features["num_mulligans"].iloc[1] == 1

    def test_creates_target_column(self, sample_df: pd.DataFrame, sample_card_data: dict) -> None:
        """Creates binary 'won' target column."""
        features = engineer_features(sample_df, sample_card_data)
        assert TARGET in features.columns
        assert features[TARGET].iloc[0] == 1
        assert features[TARGET].iloc[1] == 0

    def test_output_is_numeric(self, sample_df: pd.DataFrame, sample_card_data: dict) -> None:
        """All feature columns are numeric."""
        features = engineer_features(sample_df, sample_card_data)
        for col in FEATURES:
            if col in features.columns:
                assert features[col].dtype in ["int64", "float64", "int32", "float32"]

    def test_all_expected_features_present(
        self, sample_df: pd.DataFrame, sample_card_data: dict
    ) -> None:
        """All expected feature columns are present."""
        features = engineer_features(sample_df, sample_card_data)
        for feat in FEATURES:
            assert feat in features.columns, f"Missing feature: {feat}"
