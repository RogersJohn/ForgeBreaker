"""Tests for Arena export tool."""

from typing import Any

import pytest

from forgebreaker.mcp.tools import export_to_arena_tool


@pytest.fixture
def card_db() -> dict[str, dict[str, Any]]:
    """Sample card database for testing."""
    return {
        "Lightning Bolt": {
            "type_line": "Instant",
            "colors": ["R"],
            "set": "STA",
            "collector_number": "42",
            "cmc": 1,
        },
        "Sanctum of Stone Fangs": {
            "type_line": "Legendary Enchantment — Shrine",
            "colors": ["B"],
            "set": "M21",
            "collector_number": "120",
            "cmc": 2,
        },
        "Mountain": {
            "type_line": "Basic Land — Mountain",
            "colors": [],
            "set": "FDN",
            "collector_number": "279",
            "cmc": 0,
        },
        "Swamp": {
            "type_line": "Basic Land — Swamp",
            "colors": [],
            "set": "FDN",
            "collector_number": "280",
            "cmc": 0,
        },
    }


class TestExportToArenaTool:
    """Tests for export_to_arena_tool function."""

    def test_export_basic_deck(
        self,
        card_db: dict[str, dict[str, Any]],
    ) -> None:
        """Exports a basic deck to Arena format."""
        cards = {"Lightning Bolt": 4, "Sanctum of Stone Fangs": 4}
        lands = {"Mountain": 12, "Swamp": 12}

        result = export_to_arena_tool(cards, lands, card_db)

        assert result["success"] is True
        assert result["total_cards"] == 32
        assert "arena_format" in result

    def test_export_starts_with_deck(
        self,
        card_db: dict[str, dict[str, Any]],
    ) -> None:
        """Arena export starts with 'Deck'."""
        cards = {"Lightning Bolt": 4}
        lands = {"Mountain": 20}

        result = export_to_arena_tool(cards, lands, card_db)

        assert result["arena_format"].startswith("Deck")

    def test_export_includes_set_codes(
        self,
        card_db: dict[str, dict[str, Any]],
    ) -> None:
        """Arena export includes set codes."""
        cards = {"Lightning Bolt": 4}
        lands = {"Mountain": 20}

        result = export_to_arena_tool(cards, lands, card_db)

        assert "(STA)" in result["arena_format"]
        assert "(FDN)" in result["arena_format"]

    def test_export_includes_collector_numbers(
        self,
        card_db: dict[str, dict[str, Any]],
    ) -> None:
        """Arena export includes collector numbers."""
        cards = {"Lightning Bolt": 4}
        lands = {}

        result = export_to_arena_tool(cards, lands, card_db)

        # Lightning Bolt is (STA) 42
        assert "42" in result["arena_format"]

    def test_export_format_line_structure(
        self,
        card_db: dict[str, dict[str, Any]],
    ) -> None:
        """Each line follows Arena format: 'N CardName (SET) CollectorNum'."""
        cards = {"Lightning Bolt": 4}
        lands = {}

        result = export_to_arena_tool(cards, lands, card_db)

        lines = result["arena_format"].split("\n")
        # First line is "Deck"
        assert lines[0] == "Deck"
        # Second line should be the card
        assert "4 Lightning Bolt (STA) 42" in lines[1]

    def test_export_custom_deck_name(
        self,
        card_db: dict[str, dict[str, Any]],
    ) -> None:
        """Custom deck name is returned."""
        cards = {"Lightning Bolt": 4}
        lands = {}

        result = export_to_arena_tool(cards, lands, card_db, deck_name="My Deck")

        assert result["deck_name"] == "My Deck"

    def test_export_empty_deck(
        self,
        card_db: dict[str, dict[str, Any]],
    ) -> None:
        """Empty deck produces minimal export."""
        cards: dict[str, int] = {}
        lands: dict[str, int] = {}

        result = export_to_arena_tool(cards, lands, card_db)

        assert result["success"] is True
        assert result["total_cards"] == 0
        assert result["arena_format"] == "Deck"

    def test_export_unknown_cards_use_defaults(self) -> None:
        """Cards not in database use default set code."""
        card_db: dict[str, dict[str, Any]] = {}
        cards = {"Unknown Card": 4}
        lands = {}

        result = export_to_arena_tool(cards, lands, card_db)

        assert result["success"] is True
        # Should still produce output with default set
        assert "Unknown Card" in result["arena_format"]

    def test_export_includes_all_cards(
        self,
        card_db: dict[str, dict[str, Any]],
    ) -> None:
        """All cards and lands are included in export."""
        cards = {"Lightning Bolt": 4, "Sanctum of Stone Fangs": 4}
        lands = {"Mountain": 12, "Swamp": 12}

        result = export_to_arena_tool(cards, lands, card_db)

        arena_format = result["arena_format"]
        assert "Lightning Bolt" in arena_format
        assert "Sanctum of Stone Fangs" in arena_format
        assert "Mountain" in arena_format
        assert "Swamp" in arena_format
