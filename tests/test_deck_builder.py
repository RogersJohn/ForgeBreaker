"""Tests for deck builder service."""

from typing import Any

import pytest

from forgebreaker.models.collection import Collection
from forgebreaker.services.deck_builder import (
    BuiltDeck,
    DeckBuildRequest,
    build_deck,
    export_deck_to_arena,
    format_built_deck,
)


@pytest.fixture
def card_db() -> dict[str, dict[str, Any]]:
    """Sample card database for testing."""
    return {
        "Sanctum of Stone Fangs": {
            "type_line": "Legendary Enchantment — Shrine",
            "colors": ["B"],
            "set": "M21",
            "collector_number": "120",
            "cmc": 2,
            "oracle_text": (
                "At the beginning of your precombat main phase, "
                "each opponent loses 1 life for each Shrine you control."
            ),
        },
        "Sanctum of Shattered Heights": {
            "type_line": "Legendary Enchantment — Shrine",
            "colors": ["R"],
            "set": "M21",
            "collector_number": "157",
            "cmc": 3,
            "oracle_text": (
                "Sacrifice a Shrine: Deal damage equal to the number of Shrines you control."
            ),
        },
        "Go for the Throat": {
            "type_line": "Instant",
            "colors": ["B"],
            "set": "MOM",
            "collector_number": "105",
            "cmc": 2,
            "oracle_text": "Destroy target nonartifact creature.",
        },
        "Lightning Bolt": {
            "type_line": "Instant",
            "colors": ["R"],
            "set": "STA",
            "collector_number": "42",
            "cmc": 1,
            "oracle_text": "Lightning Bolt deals 3 damage to any target.",
        },
        "Swamp": {
            "type_line": "Basic Land — Swamp",
            "colors": [],
            "set": "FDN",
            "collector_number": "280",
            "cmc": 0,
            "oracle_text": "",
        },
        "Mountain": {
            "type_line": "Basic Land — Mountain",
            "colors": [],
            "set": "FDN",
            "collector_number": "279",
            "cmc": 0,
            "oracle_text": "",
        },
        "Blood Crypt": {
            "type_line": "Land — Swamp Mountain",
            "colors": [],
            "set": "RNA",
            "collector_number": "245",
            "cmc": 0,
            "oracle_text": (
                "({T}: Add {B} or {R}.) Blood Crypt enters tapped unless you pay 2 life."
            ),
        },
    }


@pytest.fixture
def collection() -> Collection:
    """Sample collection with shrine deck cards."""
    return Collection(
        cards={
            "Sanctum of Stone Fangs": 4,
            "Sanctum of Shattered Heights": 4,
            "Go for the Throat": 4,
            "Lightning Bolt": 4,
            "Swamp": 20,
            "Mountain": 20,
            "Blood Crypt": 4,
        }
    )


@pytest.fixture
def format_legality() -> dict[str, set[str]]:
    """All test cards legal in historic."""
    return {
        "historic": {
            "Sanctum of Stone Fangs",
            "Sanctum of Shattered Heights",
            "Go for the Throat",
            "Lightning Bolt",
            "Swamp",
            "Mountain",
            "Blood Crypt",
        }
    }


class TestBuildDeck:
    """Tests for build_deck function."""

    def test_build_shrine_deck(
        self,
        collection: Collection,
        card_db: dict[str, dict[str, Any]],
        format_legality: dict[str, set[str]],
    ) -> None:
        """Builds deck around shrine theme."""
        request = DeckBuildRequest(
            theme="Shrine",
            format="historic",
        )

        deck = build_deck(request, collection, card_db, format_legality)

        assert deck.name == "Shrine Deck"
        assert "Sanctum of Stone Fangs" in deck.theme_cards
        assert "Sanctum of Shattered Heights" in deck.theme_cards
        assert deck.colors == {"B", "R"}

    def test_build_includes_support(
        self,
        collection: Collection,
        card_db: dict[str, dict[str, Any]],
        format_legality: dict[str, set[str]],
    ) -> None:
        """Support cards are added to deck."""
        request = DeckBuildRequest(
            theme="Shrine",
            format="historic",
        )

        deck = build_deck(request, collection, card_db, format_legality)

        # Should include removal as support
        assert len(deck.support_cards) > 0

    def test_build_includes_lands(
        self,
        collection: Collection,
        card_db: dict[str, dict[str, Any]],
        format_legality: dict[str, set[str]],
    ) -> None:
        """Lands are added to deck."""
        request = DeckBuildRequest(
            theme="Shrine",
            format="historic",
        )

        deck = build_deck(request, collection, card_db, format_legality)

        assert len(deck.lands) > 0
        assert sum(deck.lands.values()) > 0

    def test_build_no_theme_cards(
        self,
        collection: Collection,
        card_db: dict[str, dict[str, Any]],
        format_legality: dict[str, set[str]],
    ) -> None:
        """Returns warning when no theme cards found."""
        request = DeckBuildRequest(
            theme="Dinosaur",  # Not in collection
            format="historic",
        )

        deck = build_deck(request, collection, card_db, format_legality)

        assert len(deck.warnings) > 0
        assert "No cards matching" in deck.warnings[0]

    def test_color_restriction(
        self,
        collection: Collection,
        card_db: dict[str, dict[str, Any]],
        format_legality: dict[str, set[str]],
    ) -> None:
        """Color restriction limits deck colors."""
        request = DeckBuildRequest(
            theme="Shrine",
            colors=["B"],  # Only black
            format="historic",
        )

        deck = build_deck(request, collection, card_db, format_legality)

        assert deck.colors == {"B"}

    def test_include_specific_cards(
        self,
        collection: Collection,
        card_db: dict[str, dict[str, Any]],
        format_legality: dict[str, set[str]],
    ) -> None:
        """Specified cards are included."""
        request = DeckBuildRequest(
            theme="Shrine",
            format="historic",
            include_cards=["Lightning Bolt"],
        )

        deck = build_deck(request, collection, card_db, format_legality)

        assert "Lightning Bolt" in deck.cards

    def test_unknown_format_returns_empty_legality(
        self,
        collection: Collection,
        card_db: dict[str, dict[str, Any]],
        format_legality: dict[str, set[str]],
    ) -> None:
        """Unknown format produces warning about no theme cards."""
        request = DeckBuildRequest(
            theme="Shrine",
            format="unknown_format",
        )

        deck = build_deck(request, collection, card_db, format_legality)

        # No cards are legal, so no theme cards found
        assert len(deck.warnings) > 0

    def test_deck_respects_card_limits(
        self,
        card_db: dict[str, dict[str, Any]],
        format_legality: dict[str, set[str]],
    ) -> None:
        """Cards limited to 4 copies max."""
        # Collection with many copies of one card
        collection = Collection(
            cards={
                "Sanctum of Stone Fangs": 10,
                "Swamp": 40,
            }
        )

        request = DeckBuildRequest(
            theme="Shrine",
            format="historic",
        )

        deck = build_deck(request, collection, card_db, format_legality)

        # Should only include 4 copies max
        assert deck.cards.get("Sanctum of Stone Fangs", 0) <= 4


class TestExportToArena:
    """Tests for export_deck_to_arena function."""

    def test_export_format(
        self,
        collection: Collection,
        card_db: dict[str, dict[str, Any]],
        format_legality: dict[str, set[str]],
    ) -> None:
        """Export produces Arena-compatible format."""
        request = DeckBuildRequest(theme="Shrine", format="historic")
        deck = build_deck(request, collection, card_db, format_legality)

        export = export_deck_to_arena(deck, card_db)

        assert export.startswith("Deck")
        assert "Sanctum of Stone Fangs (M21)" in export

    def test_export_includes_collector_number(
        self,
        collection: Collection,
        card_db: dict[str, dict[str, Any]],
        format_legality: dict[str, set[str]],
    ) -> None:
        """Export includes collector numbers."""
        request = DeckBuildRequest(theme="Shrine", format="historic")
        deck = build_deck(request, collection, card_db, format_legality)

        export = export_deck_to_arena(deck, card_db)

        # M21 120 is Sanctum of Stone Fangs
        assert "(M21) 120" in export


class TestFormatBuiltDeck:
    """Tests for format_built_deck function."""

    def test_format_includes_name(self) -> None:
        """Formatted output includes deck name."""
        deck = BuiltDeck(
            name="Test Deck",
            cards={"Lightning Bolt": 4},
            total_cards=4,
            colors={"R"},
            theme_cards=["Lightning Bolt"],
            support_cards=[],
            lands={},
        )

        formatted = format_built_deck(deck)

        assert "# Test Deck" in formatted

    def test_format_includes_notes(self) -> None:
        """Formatted output includes notes."""
        deck = BuiltDeck(
            name="Test Deck",
            cards={},
            total_cards=0,
            colors=set(),
            theme_cards=[],
            support_cards=[],
            lands={},
            notes=["Found 5 theme cards"],
        )

        formatted = format_built_deck(deck)

        assert "Found 5 theme cards" in formatted

    def test_format_includes_warnings(self) -> None:
        """Formatted output includes warnings."""
        deck = BuiltDeck(
            name="Test Deck",
            cards={},
            total_cards=0,
            colors=set(),
            theme_cards=[],
            support_cards=[],
            lands={},
            warnings=["Not enough lands"],
        )

        formatted = format_built_deck(deck)

        assert "Not enough lands" in formatted

    def test_format_includes_colors(self) -> None:
        """Formatted output includes deck colors."""
        deck = BuiltDeck(
            name="Test Deck",
            cards={},
            total_cards=0,
            colors={"B", "R"},
            theme_cards=[],
            support_cards=[],
            lands={},
        )

        formatted = format_built_deck(deck)

        assert "Colors:" in formatted
        assert "B" in formatted
        assert "R" in formatted
