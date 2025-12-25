"""Tests for deck improvement service."""

from typing import Any

import pytest

from forgebreaker.models.collection import Collection
from forgebreaker.services.deck_improver import (
    CardSuggestion,
    DeckAnalysis,
    analyze_and_improve_deck,
    format_deck_analysis,
)


@pytest.fixture
def card_db() -> dict[str, dict[str, Any]]:
    """Sample card database for testing."""
    return {
        "Lightning Bolt": {
            "name": "Lightning Bolt",
            "type_line": "Instant",
            "colors": ["R"],
            "cmc": 1,
            "rarity": "uncommon",
            "oracle_text": "Lightning Bolt deals 3 damage to any target.",
        },
        "Shock": {
            "name": "Shock",
            "type_line": "Instant",
            "colors": ["R"],
            "cmc": 1,
            "rarity": "common",
            "oracle_text": "Shock deals 2 damage to any target.",
        },
        "Goblin Guide": {
            "name": "Goblin Guide",
            "type_line": "Creature — Goblin Scout",
            "colors": ["R"],
            "cmc": 1,
            "rarity": "rare",
            "oracle_text": "Haste",
        },
        "Monastery Swiftspear": {
            "name": "Monastery Swiftspear",
            "type_line": "Creature — Human Monk",
            "colors": ["R"],
            "cmc": 1,
            "rarity": "uncommon",
            "oracle_text": "Haste. Prowess",
        },
        "Mountain": {
            "name": "Mountain",
            "type_line": "Basic Land — Mountain",
            "colors": [],
            "cmc": 0,
            "rarity": "common",
            "oracle_text": "",
        },
        "Sheoldred, the Apocalypse": {
            "name": "Sheoldred, the Apocalypse",
            "type_line": "Legendary Creature — Phyrexian Praetor",
            "colors": ["B"],
            "cmc": 4,
            "rarity": "mythic",
            "oracle_text": "Deathtouch. Whenever you draw a card, you gain 2 life.",
        },
        "Bloodtithe Harvester": {
            "name": "Bloodtithe Harvester",
            "type_line": "Creature — Vampire",
            "colors": ["B", "R"],
            "cmc": 2,
            "rarity": "uncommon",
            "oracle_text": "When Bloodtithe Harvester enters, create a Blood token.",
        },
    }


@pytest.fixture
def sample_deck_text() -> str:
    """Sample deck list in Arena format."""
    return """Deck
4 Shock (STA) 44
4 Monastery Swiftspear (BRO) 144
20 Mountain (FDN) 279
"""


class TestAnalyzeAndImproveDeck:
    """Tests for analyze_and_improve_deck function."""

    def test_parses_deck_correctly(
        self, sample_deck_text: str, card_db: dict[str, dict[str, Any]]
    ) -> None:
        """Correctly parses and analyzes a deck."""
        collection = Collection(cards={"Lightning Bolt": 4})

        analysis = analyze_and_improve_deck(
            deck_text=sample_deck_text,
            collection=collection,
            card_db=card_db,
        )

        assert analysis.total_cards == 28
        assert "Shock" in analysis.original_cards
        assert analysis.original_cards["Shock"] == 4

    def test_detects_colors(
        self, sample_deck_text: str, card_db: dict[str, dict[str, Any]]
    ) -> None:
        """Correctly detects deck colors."""
        collection = Collection()

        analysis = analyze_and_improve_deck(
            deck_text=sample_deck_text,
            collection=collection,
            card_db=card_db,
        )

        assert "R" in analysis.colors

    def test_counts_card_types(
        self, sample_deck_text: str, card_db: dict[str, dict[str, Any]]
    ) -> None:
        """Correctly counts creatures, spells, and lands."""
        collection = Collection()

        analysis = analyze_and_improve_deck(
            deck_text=sample_deck_text,
            collection=collection,
            card_db=card_db,
        )

        assert analysis.creature_count == 4
        assert analysis.spell_count == 4
        assert analysis.land_count == 20

    def test_suggests_upgrades(
        self, sample_deck_text: str, card_db: dict[str, dict[str, Any]]
    ) -> None:
        """Suggests upgrades when better cards are available in collection."""
        # User owns Lightning Bolt which is better than Shock
        collection = Collection(cards={"Lightning Bolt": 4})

        analysis = analyze_and_improve_deck(
            deck_text=sample_deck_text,
            collection=collection,
            card_db=card_db,
        )

        # Should suggest replacing Shock with Lightning Bolt
        shock_suggestions = [s for s in analysis.suggestions if s.remove_card == "Shock"]
        assert len(shock_suggestions) > 0

    def test_respects_color_identity(self, card_db: dict[str, dict[str, Any]]) -> None:
        """Does not suggest cards outside deck's color identity."""
        deck_text = """Deck
4 Shock (STA) 44
20 Mountain (FDN) 279
"""
        # Sheoldred is black, deck is red
        collection = Collection(cards={"Sheoldred, the Apocalypse": 4})

        analysis = analyze_and_improve_deck(
            deck_text=deck_text,
            collection=collection,
            card_db=card_db,
        )

        # Should not suggest Sheoldred for a mono-red deck
        sheoldred_suggestions = [
            s for s in analysis.suggestions if s.add_card == "Sheoldred, the Apocalypse"
        ]
        assert len(sheoldred_suggestions) == 0

    def test_no_suggestions_when_already_optimal(self, card_db: dict[str, dict[str, Any]]) -> None:
        """No suggestions when deck already uses best available cards."""
        deck_text = """Deck
4 Lightning Bolt (STA) 42
20 Mountain (FDN) 279
"""
        # User only owns Shock which is worse
        collection = Collection(cards={"Shock": 4})

        analysis = analyze_and_improve_deck(
            deck_text=deck_text,
            collection=collection,
            card_db=card_db,
        )

        # Should not suggest downgrading to Shock
        assert len(analysis.suggestions) == 0

    def test_warns_low_land_count(self, card_db: dict[str, dict[str, Any]]) -> None:
        """Warns when deck has too few lands."""
        deck_text = """Deck
40 Shock (STA) 44
10 Mountain (FDN) 279
"""
        collection = Collection()

        analysis = analyze_and_improve_deck(
            deck_text=deck_text,
            collection=collection,
            card_db=card_db,
        )

        assert any("land" in w.lower() for w in analysis.warnings)

    def test_warns_low_card_count(self, card_db: dict[str, dict[str, Any]]) -> None:
        """Warns when deck has fewer than 60 cards."""
        deck_text = """Deck
4 Shock (STA) 44
10 Mountain (FDN) 279
"""
        collection = Collection()

        analysis = analyze_and_improve_deck(
            deck_text=deck_text,
            collection=collection,
            card_db=card_db,
        )

        assert any("14 cards" in w for w in analysis.warnings)

    def test_handles_empty_deck(self, card_db: dict[str, dict[str, Any]]) -> None:
        """Handles empty deck input gracefully."""
        collection = Collection()

        analysis = analyze_and_improve_deck(
            deck_text="",
            collection=collection,
            card_db=card_db,
        )

        assert analysis.total_cards == 0
        assert len(analysis.warnings) > 0

    def test_respects_max_suggestions(self, card_db: dict[str, dict[str, Any]]) -> None:
        """Respects max_suggestions parameter."""
        deck_text = """Deck
4 Shock (STA) 44
4 Monastery Swiftspear (BRO) 144
20 Mountain (FDN) 279
"""
        collection = Collection(
            cards={
                "Lightning Bolt": 4,
                "Goblin Guide": 4,
            }
        )

        analysis = analyze_and_improve_deck(
            deck_text=deck_text,
            collection=collection,
            card_db=card_db,
            max_suggestions=1,
        )

        assert len(analysis.suggestions) <= 1


class TestFormatDeckAnalysis:
    """Tests for format_deck_analysis function."""

    def test_formats_basic_analysis(self) -> None:
        """Formats a basic analysis correctly."""
        analysis = DeckAnalysis(
            original_cards={"Lightning Bolt": 4, "Mountain": 20},
            total_cards=24,
            colors={"R"},
            creature_count=0,
            spell_count=4,
            land_count=20,
        )

        formatted = format_deck_analysis(analysis)

        assert "24 cards" in formatted
        assert "R" in formatted

    def test_includes_suggestions(self) -> None:
        """Includes suggestions in formatted output."""
        analysis = DeckAnalysis(
            original_cards={},
            total_cards=60,
            colors={"R"},
            creature_count=20,
            spell_count=16,
            land_count=24,
            suggestions=[
                CardSuggestion(
                    remove_card="Shock",
                    remove_quantity=4,
                    add_card="Lightning Bolt",
                    add_quantity=4,
                    reason="better damage output",
                )
            ],
        )

        formatted = format_deck_analysis(analysis)

        assert "Shock" in formatted
        assert "Lightning Bolt" in formatted
        assert "better damage output" in formatted

    def test_includes_warnings(self) -> None:
        """Includes warnings in formatted output."""
        analysis = DeckAnalysis(
            original_cards={},
            total_cards=40,
            colors=set(),
            creature_count=0,
            spell_count=0,
            land_count=10,
            warnings=["Deck has only 40 cards."],
        )

        formatted = format_deck_analysis(analysis)

        assert "40 cards" in formatted
        assert "Issues" in formatted

    def test_includes_general_advice(self) -> None:
        """Includes general advice in formatted output."""
        analysis = DeckAnalysis(
            original_cards={},
            total_cards=60,
            colors={"R"},
            creature_count=20,
            spell_count=16,
            land_count=24,
            general_advice=["Consider adding more removal."],
        )

        formatted = format_deck_analysis(analysis)

        assert "removal" in formatted
        assert "Tips" in formatted
