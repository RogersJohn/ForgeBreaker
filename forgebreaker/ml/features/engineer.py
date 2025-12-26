"""Feature engineering for deck win rate prediction.

Transforms 17Lands game data into ML-ready features.
"""

from typing import Any

import pandas as pd

# Feature names for the model
FEATURES = [
    # Deck composition
    "n_cards_in_deck",
    "n_creatures",
    "n_lands",
    "n_noncreature_spells",
    "avg_mana_value",
    "curve_1_drop",
    "curve_2_drop",
    "curve_3_drop",
    "curve_4_drop",
    "curve_5plus_drop",
    # Colors (one-hot)
    "color_W",
    "color_U",
    "color_B",
    "color_R",
    "color_G",
    # Game context
    "on_play",
    "num_mulligans",
    "user_skill_bucket",
]

TARGET = "won"


def extract_deck_card_columns(df: pd.DataFrame) -> list[str]:
    """Get all deck_* column names.

    Args:
        df: DataFrame with deck columns

    Returns:
        List of column names starting with 'deck_'
    """
    return [c for c in df.columns if c.startswith("deck_")]


def _get_card_name(col: str) -> str:
    """Extract card name from deck column name.

    Args:
        col: Column name like 'deck_Lightning_Bolt'

    Returns:
        Card name like 'Lightning_Bolt'
    """
    return col.replace("deck_", "")


def count_total_cards(df: pd.DataFrame) -> pd.Series:
    """Count total cards in each deck.

    Args:
        df: DataFrame with deck columns

    Returns:
        Series with total card count per row
    """
    deck_cols = extract_deck_card_columns(df)
    return df[deck_cols].sum(axis=1)


def count_card_types(df: pd.DataFrame, card_data: dict[str, dict[str, Any]]) -> pd.DataFrame:
    """Count cards by type (creatures, lands, spells).

    Args:
        df: DataFrame with deck columns
        card_data: Dict mapping card names to card data

    Returns:
        DataFrame with n_creatures, n_lands, n_noncreature_spells columns
    """
    deck_cols = extract_deck_card_columns(df)

    creatures = pd.Series(0, index=df.index)
    lands = pd.Series(0, index=df.index)
    spells = pd.Series(0, index=df.index)

    for col in deck_cols:
        card_name = _get_card_name(col)
        card = card_data.get(card_name, {})
        type_line = card.get("type_line", "").lower()

        if "creature" in type_line:
            creatures += df[col]
        elif "land" in type_line:
            lands += df[col]
        else:
            spells += df[col]

    return pd.DataFrame(
        {
            "n_creatures": creatures,
            "n_lands": lands,
            "n_noncreature_spells": spells,
        }
    )


def calculate_average_mana_value(
    df: pd.DataFrame, card_data: dict[str, dict[str, Any]]
) -> pd.Series:
    """Calculate average mana value of non-land cards.

    Args:
        df: DataFrame with deck columns
        card_data: Dict mapping card names to card data

    Returns:
        Series with average mana value per deck
    """
    deck_cols = extract_deck_card_columns(df)

    total_mv = pd.Series(0.0, index=df.index)
    total_nonland_cards = pd.Series(0, index=df.index)

    for col in deck_cols:
        card_name = _get_card_name(col)
        card = card_data.get(card_name, {})
        type_line = card.get("type_line", "").lower()

        if "land" not in type_line:
            cmc = card.get("cmc", 0.0)
            total_mv += df[col] * cmc
            total_nonland_cards += df[col]

    # Avoid division by zero
    return total_mv / total_nonland_cards.replace(0, 1)


def calculate_mana_curve(df: pd.DataFrame, card_data: dict[str, dict[str, Any]]) -> pd.DataFrame:
    """Calculate mana curve distribution.

    Args:
        df: DataFrame with deck columns
        card_data: Dict mapping card names to card data

    Returns:
        DataFrame with curve_1_drop through curve_5plus_drop columns
    """
    deck_cols = extract_deck_card_columns(df)

    curve = {
        "curve_1_drop": pd.Series(0, index=df.index),
        "curve_2_drop": pd.Series(0, index=df.index),
        "curve_3_drop": pd.Series(0, index=df.index),
        "curve_4_drop": pd.Series(0, index=df.index),
        "curve_5plus_drop": pd.Series(0, index=df.index),
    }

    for col in deck_cols:
        card_name = _get_card_name(col)
        card = card_data.get(card_name, {})
        type_line = card.get("type_line", "").lower()

        # Skip lands
        if "land" in type_line:
            continue

        cmc = int(card.get("cmc", 0))

        if cmc == 1:
            curve["curve_1_drop"] += df[col]
        elif cmc == 2:
            curve["curve_2_drop"] += df[col]
        elif cmc == 3:
            curve["curve_3_drop"] += df[col]
        elif cmc == 4:
            curve["curve_4_drop"] += df[col]
        elif cmc >= 5:
            curve["curve_5plus_drop"] += df[col]

    return pd.DataFrame(curve)


def extract_colors(df: pd.DataFrame, card_data: dict[str, dict[str, Any]]) -> pd.DataFrame:
    """Extract deck colors as one-hot encoding.

    Args:
        df: DataFrame with deck columns
        card_data: Dict mapping card names to card data

    Returns:
        DataFrame with color_W, color_U, color_B, color_R, color_G columns
    """
    deck_cols = extract_deck_card_columns(df)
    color_map = {c: f"color_{c}" for c in "WUBRG"}

    colors = {f"color_{c}": pd.Series(0, index=df.index) for c in "WUBRG"}

    for col in deck_cols:
        card_name = _get_card_name(col)
        card = card_data.get(card_name, {})
        card_colors = card.get("colors", [])

        for color in card_colors:
            col_name = color_map.get(color)
            if col_name:
                # Mark as 1 if any card of this color is in deck
                colors[col_name] = colors[col_name] | (df[col] > 0).astype(int)

    return pd.DataFrame(colors)


def engineer_features(df: pd.DataFrame, card_data: dict[str, dict[str, Any]]) -> pd.DataFrame:
    """Engineer all features from 17Lands data.

    Args:
        df: DataFrame with 17Lands game data
        card_data: Dict mapping card names to card data

    Returns:
        DataFrame with engineered features and target
    """
    result = pd.DataFrame(index=df.index)

    # Deck composition
    result["n_cards_in_deck"] = count_total_cards(df)

    card_types = count_card_types(df, card_data)
    result["n_creatures"] = card_types["n_creatures"]
    result["n_lands"] = card_types["n_lands"]
    result["n_noncreature_spells"] = card_types["n_noncreature_spells"]

    result["avg_mana_value"] = calculate_average_mana_value(df, card_data)

    # Mana curve
    curve = calculate_mana_curve(df, card_data)
    for col in curve.columns:
        result[col] = curve[col]

    # Colors
    colors = extract_colors(df, card_data)
    for col in colors.columns:
        result[col] = colors[col]

    # Game context
    result["on_play"] = df["on_play"]
    result["num_mulligans"] = df["num_mulligans"]
    result["user_skill_bucket"] = df["user_game_win_rate_bucket"]

    # Target
    result[TARGET] = df["won"]

    return result
