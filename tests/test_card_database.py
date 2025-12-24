import json
from pathlib import Path

import pytest

from forgebreaker.services.card_database import (
    get_card_colors,
    get_card_rarity,
    get_card_type,
    get_format_legality,
    load_card_database,
)


@pytest.fixture
def sample_cards() -> list[dict]:
    """Sample Scryfall card data."""
    return [
        {
            "name": "Lightning Bolt",
            "type_line": "Instant",
            "colors": ["R"],
            "rarity": "common",
            "mana_cost": "{R}",
            "set": "LEB",
            "legalities": {
                "standard": "not_legal",
                "historic": "legal",
                "modern": "legal",
                "legacy": "legal",
            },
        },
        {
            "name": "Counterspell",
            "type_line": "Instant",
            "colors": ["U"],
            "rarity": "common",
            "mana_cost": "{U}{U}",
            "set": "LEB",
            "legalities": {
                "standard": "not_legal",
                "historic": "legal",
                "modern": "not_legal",
                "legacy": "legal",
            },
        },
        {
            "name": "Sheoldred, the Apocalypse",
            "type_line": "Legendary Creature — Phyrexian Praetor",
            "colors": ["B"],
            "rarity": "mythic",
            "mana_cost": "{2}{B}{B}",
            "set": "DMU",
            "legalities": {
                "standard": "legal",
                "historic": "legal",
                "modern": "legal",
                "legacy": "legal",
            },
        },
        {
            "name": "Sol Ring",
            "type_line": "Artifact",
            "colors": [],
            "rarity": "uncommon",
            "mana_cost": "{1}",
            "set": "CMD",
            "legalities": {
                "standard": "not_legal",
                "historic": "not_legal",
                "modern": "not_legal",
                "legacy": "banned",
            },
        },
    ]


@pytest.fixture
def card_db_file(sample_cards: list[dict], tmp_path: Path) -> Path:
    """Create a temporary card database file."""
    db_path = tmp_path / "cards.json"
    with open(db_path, "w", encoding="utf-8") as f:
        json.dump(sample_cards, f)
    return db_path


class TestLoadCardDatabase:
    def test_loads_cards_by_name(self, card_db_file: Path) -> None:
        """Cards are indexed by name."""
        db = load_card_database(card_db_file)

        assert "Lightning Bolt" in db
        assert "Counterspell" in db
        assert "Sheoldred, the Apocalypse" in db
        assert "Sol Ring" in db

    def test_returns_card_data(self, card_db_file: Path) -> None:
        """Card data is accessible."""
        db = load_card_database(card_db_file)

        bolt = db["Lightning Bolt"]
        assert bolt["type_line"] == "Instant"
        assert bolt["colors"] == ["R"]
        assert bolt["rarity"] == "common"

    def test_file_not_found_raises(self, tmp_path: Path) -> None:
        """Missing file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            load_card_database(tmp_path / "nonexistent.json")

    def test_corrupted_json_raises_value_error(self, tmp_path: Path) -> None:
        """Corrupted JSON raises ValueError with helpful message."""
        db_path = tmp_path / "corrupted.json"
        db_path.write_text("{ invalid json }", encoding="utf-8")

        with pytest.raises(ValueError, match="corrupted"):
            load_card_database(db_path)

    def test_first_printing_wins(self, tmp_path: Path) -> None:
        """First printing of a card is used if duplicates exist."""
        cards = [
            {"name": "Lightning Bolt", "set": "LEB", "rarity": "common"},
            {"name": "Lightning Bolt", "set": "M21", "rarity": "uncommon"},
        ]
        db_path = tmp_path / "cards.json"
        with open(db_path, "w", encoding="utf-8") as f:
            json.dump(cards, f)

        db = load_card_database(db_path)

        # First printing should win
        assert db["Lightning Bolt"]["set"] == "LEB"


class TestGetFormatLegality:
    def test_builds_legality_map(self, card_db_file: Path) -> None:
        """Legality map is correctly built."""
        db = load_card_database(card_db_file)
        legality = get_format_legality(db)

        assert "Lightning Bolt" in legality["historic"]
        assert "Lightning Bolt" in legality["modern"]
        assert "Lightning Bolt" not in legality["standard"]

    def test_standard_legality(self, card_db_file: Path) -> None:
        """Standard-legal cards are correctly identified."""
        db = load_card_database(card_db_file)
        legality = get_format_legality(db)

        assert "Sheoldred, the Apocalypse" in legality["standard"]
        assert "Lightning Bolt" not in legality["standard"]

    def test_all_formats_present(self, card_db_file: Path) -> None:
        """All expected formats are in the legality map."""
        db = load_card_database(card_db_file)
        legality = get_format_legality(db)

        expected = [
            "standard",
            "historic",
            "explorer",
            "pioneer",
            "modern",
            "legacy",
            "vintage",
            "brawl",
            "timeless",
        ]
        for fmt in expected:
            assert fmt in legality


class TestGetCardRarity:
    def test_returns_rarity(self, card_db_file: Path) -> None:
        """Returns correct rarity for known cards."""
        db = load_card_database(card_db_file)

        assert get_card_rarity("Lightning Bolt", db) == "common"
        assert get_card_rarity("Sol Ring", db) == "uncommon"
        assert get_card_rarity("Sheoldred, the Apocalypse", db) == "mythic"

    def test_unknown_card_defaults_to_rare(self, card_db_file: Path) -> None:
        """Unknown cards default to rare."""
        db = load_card_database(card_db_file)

        assert get_card_rarity("Unknown Card", db) == "rare"


class TestGetCardColors:
    def test_returns_colors(self, card_db_file: Path) -> None:
        """Returns correct colors for known cards."""
        db = load_card_database(card_db_file)

        assert get_card_colors("Lightning Bolt", db) == ["R"]
        assert get_card_colors("Counterspell", db) == ["U"]
        assert get_card_colors("Sheoldred, the Apocalypse", db) == ["B"]

    def test_colorless_returns_empty(self, card_db_file: Path) -> None:
        """Colorless cards return empty list."""
        db = load_card_database(card_db_file)

        assert get_card_colors("Sol Ring", db) == []

    def test_unknown_card_returns_empty(self, card_db_file: Path) -> None:
        """Unknown cards return empty list."""
        db = load_card_database(card_db_file)

        assert get_card_colors("Unknown Card", db) == []


class TestGetCardType:
    def test_returns_type_line(self, card_db_file: Path) -> None:
        """Returns correct type line for known cards."""
        db = load_card_database(card_db_file)

        assert get_card_type("Lightning Bolt", db) == "Instant"
        assert get_card_type("Sol Ring", db) == "Artifact"
        assert "Praetor" in get_card_type("Sheoldred, the Apocalypse", db)

    def test_unknown_card_returns_empty(self, card_db_file: Path) -> None:
        """Unknown cards return empty string."""
        db = load_card_database(card_db_file)

        assert get_card_type("Unknown Card", db) == ""
