"""Tests for deck improvement service."""

from typing import Any

import pytest

from forgebreaker.models.collection import Collection
from forgebreaker.services.deck_improver import (
    CardDetails,
    CardSuggestion,
    DeckAnalysis,
    _detect_deck_themes,
    _extract_subtypes,
    analyze_and_improve_deck,
    format_deck_analysis,
)

# Default format for testing - all cards in test db are assumed legal
DEFAULT_FORMAT = "standard"


@pytest.fixture
def card_db() -> dict[str, dict[str, Any]]:
    """Sample card database for testing."""
    return {
        # Goblin tribal cards
        "Goblin Guide": {
            "name": "Goblin Guide",
            "type_line": "Creature — Goblin Scout",
            "colors": ["R"],
            "cmc": 1,
            "rarity": "rare",
            "oracle_text": "Haste. Whenever Goblin Guide attacks, defending player reveals.",
        },
        "Goblin Chieftain": {
            "name": "Goblin Chieftain",
            "type_line": "Creature — Goblin",
            "colors": ["R"],
            "cmc": 3,
            "rarity": "rare",
            "oracle_text": "Haste. Other Goblin creatures you control get +1/+1 and have haste.",
        },
        "Goblin Rabblemaster": {
            "name": "Goblin Rabblemaster",
            "type_line": "Creature — Goblin Warrior",
            "colors": ["R"],
            "cmc": 3,
            "rarity": "rare",
            "oracle_text": "At the beginning of combat, create a 1/1 red Goblin creature token.",
        },
        "Raging Goblin": {
            "name": "Raging Goblin",
            "type_line": "Creature — Goblin Berserker",
            "colors": ["R"],
            "cmc": 1,
            "rarity": "common",
            "oracle_text": "Haste",
        },
        # Non-goblin red creature
        "Monastery Swiftspear": {
            "name": "Monastery Swiftspear",
            "type_line": "Creature — Human Monk",
            "colors": ["R"],
            "cmc": 1,
            "rarity": "uncommon",
            "oracle_text": "Haste. Prowess",
        },
        # Sacrifice theme cards
        "Woe Strider": {
            "name": "Woe Strider",
            "type_line": "Creature — Horror",
            "colors": ["B"],
            "cmc": 3,
            "rarity": "rare",
            "oracle_text": "Create a 0/1 Goat token. Sacrifice another creature: Scry 1.",
        },
        "Mayhem Devil": {
            "name": "Mayhem Devil",
            "type_line": "Creature — Devil",
            "colors": ["B", "R"],
            "cmc": 3,
            "rarity": "uncommon",
            "oracle_text": "Whenever a player sacrifices a permanent, deal 1 damage.",
        },
        "Cauldron Familiar": {
            "name": "Cauldron Familiar",
            "type_line": "Creature — Cat",
            "colors": ["B"],
            "cmc": 1,
            "rarity": "uncommon",
            "oracle_text": "When Cauldron Familiar enters, the opponent loses 1 life. "
            "Sacrifice a Food: Return Cauldron Familiar from your graveyard.",
        },
        "Priest of Forgotten Gods": {
            "name": "Priest of Forgotten Gods",
            "type_line": "Creature — Human Cleric",
            "colors": ["B"],
            "cmc": 2,
            "rarity": "rare",
            "oracle_text": "Sacrifice two other creatures: Each opponent loses 2 life.",
        },
        # Generic cards
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
        "Mountain": {
            "name": "Mountain",
            "type_line": "Basic Land — Mountain",
            "colors": [],
            "cmc": 0,
            "rarity": "common",
            "oracle_text": "",
        },
        "Swamp": {
            "name": "Swamp",
            "type_line": "Basic Land — Swamp",
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
    }


@pytest.fixture
def format_legal_cards(card_db: dict[str, dict[str, Any]]) -> set[str]:
    """All cards in the test db are assumed to be format-legal."""
    return set(card_db.keys())


@pytest.fixture
def goblin_deck_text() -> str:
    """Goblin tribal deck list."""
    return """Deck
4 Goblin Guide (ZEN) 126
4 Raging Goblin (M10) 157
4 Shock (STA) 44
20 Mountain (FDN) 279
"""


@pytest.fixture
def sacrifice_deck_text() -> str:
    """Sacrifice-themed deck list."""
    return """Deck
4 Cauldron Familiar (ELD) 81
4 Woe Strider (THB) 123
4 Priest of Forgotten Gods (RNA) 83
20 Swamp (FDN) 280
"""


class TestExtractSubtypes:
    """Tests for _extract_subtypes function."""

    def test_extracts_single_subtype(self) -> None:
        """Extracts a single creature subtype."""
        subtypes = _extract_subtypes("Creature — Goblin")
        assert "goblin" in subtypes

    def test_extracts_multiple_subtypes(self) -> None:
        """Extracts multiple creature subtypes."""
        subtypes = _extract_subtypes("Creature — Goblin Warrior")
        assert "goblin" in subtypes
        assert "warrior" in subtypes

    def test_handles_legendary(self) -> None:
        """Handles legendary creatures correctly."""
        subtypes = _extract_subtypes("Legendary Creature — Goblin Scout")
        assert "goblin" in subtypes

    def test_no_subtypes_returns_empty(self) -> None:
        """Returns empty set for cards without subtypes."""
        subtypes = _extract_subtypes("Instant")
        assert len(subtypes) == 0


class TestDetectDeckThemes:
    """Tests for _detect_deck_themes function."""

    def test_detects_sacrifice_theme(
        self,
        card_db: dict[str, dict[str, Any]],
    ) -> None:
        """Detects sacrifice theme in deck."""
        deck_cards = {
            "Cauldron Familiar": 4,
            "Woe Strider": 4,
            "Priest of Forgotten Gods": 4,
        }

        themes = _detect_deck_themes(deck_cards, card_db)

        assert "sacrifice" in themes.themes

    def test_detects_tribal_types(
        self,
        card_db: dict[str, dict[str, Any]],
    ) -> None:
        """Detects tribal creature types."""
        deck_cards = {
            "Goblin Guide": 4,
            "Raging Goblin": 4,
            "Goblin Chieftain": 4,
        }

        themes = _detect_deck_themes(deck_cards, card_db)

        assert "goblin" in themes.tribal_types
        assert themes.tribal_types["goblin"] >= 12

    def test_detects_tokens_theme(
        self,
        card_db: dict[str, dict[str, Any]],
    ) -> None:
        """Detects token creation theme."""
        deck_cards = {
            "Goblin Rabblemaster": 4,  # Creates tokens
            "Woe Strider": 4,  # Creates tokens
        }

        themes = _detect_deck_themes(deck_cards, card_db)

        assert "tokens" in themes.themes


class TestAnalyzeAndImproveDeck:
    """Tests for analyze_and_improve_deck function."""

    def test_parses_deck_correctly(
        self,
        goblin_deck_text: str,
        card_db: dict[str, dict[str, Any]],
        format_legal_cards: set[str],
    ) -> None:
        """Correctly parses and analyzes a deck."""
        collection = Collection(cards={"Goblin Chieftain": 4})

        analysis = analyze_and_improve_deck(
            deck_text=goblin_deck_text,
            collection=collection,
            card_db=card_db,
            format_name=DEFAULT_FORMAT,
            format_legal_cards=format_legal_cards,
        )

        assert analysis.total_cards == 32
        assert "Goblin Guide" in analysis.original_cards

    def test_detects_colors(
        self,
        goblin_deck_text: str,
        card_db: dict[str, dict[str, Any]],
        format_legal_cards: set[str],
    ) -> None:
        """Correctly detects deck colors."""
        collection = Collection()

        analysis = analyze_and_improve_deck(
            deck_text=goblin_deck_text,
            collection=collection,
            card_db=card_db,
            format_name=DEFAULT_FORMAT,
            format_legal_cards=format_legal_cards,
        )

        assert "R" in analysis.colors

    def test_counts_card_types(
        self,
        goblin_deck_text: str,
        card_db: dict[str, dict[str, Any]],
        format_legal_cards: set[str],
    ) -> None:
        """Correctly counts creatures, spells, and lands."""
        collection = Collection()

        analysis = analyze_and_improve_deck(
            deck_text=goblin_deck_text,
            collection=collection,
            card_db=card_db,
            format_name=DEFAULT_FORMAT,
            format_legal_cards=format_legal_cards,
        )

        assert analysis.creature_count == 8  # 4 Guide + 4 Raging
        assert analysis.spell_count == 4  # 4 Shock
        assert analysis.land_count == 20

    def test_detects_tribal_deck(
        self,
        goblin_deck_text: str,
        card_db: dict[str, dict[str, Any]],
        format_legal_cards: set[str],
    ) -> None:
        """Detects goblin tribal deck."""
        collection = Collection()

        analysis = analyze_and_improve_deck(
            deck_text=goblin_deck_text,
            collection=collection,
            card_db=card_db,
            format_name=DEFAULT_FORMAT,
            format_legal_cards=format_legal_cards,
        )

        assert analysis.primary_tribe == "goblin"

    def test_suggests_tribal_upgrade(
        self,
        goblin_deck_text: str,
        card_db: dict[str, dict[str, Any]],
        format_legal_cards: set[str],
    ) -> None:
        """Suggests goblin cards for tribal deck."""
        # User owns Goblin Chieftain which fits tribal theme
        collection = Collection(cards={"Goblin Chieftain": 4})

        analysis = analyze_and_improve_deck(
            deck_text=goblin_deck_text,
            collection=collection,
            card_db=card_db,
            format_name=DEFAULT_FORMAT,
            format_legal_cards=format_legal_cards,
        )

        # Should at least detect tribal theme
        assert analysis.primary_tribe == "goblin"

    def test_detects_sacrifice_theme(
        self,
        sacrifice_deck_text: str,
        card_db: dict[str, dict[str, Any]],
        format_legal_cards: set[str],
    ) -> None:
        """Detects sacrifice theme in deck."""
        collection = Collection()

        analysis = analyze_and_improve_deck(
            deck_text=sacrifice_deck_text,
            collection=collection,
            card_db=card_db,
            format_name=DEFAULT_FORMAT,
            format_legal_cards=format_legal_cards,
        )

        assert "sacrifice" in analysis.detected_themes

    def test_respects_color_identity(
        self,
        goblin_deck_text: str,
        card_db: dict[str, dict[str, Any]],
        format_legal_cards: set[str],
    ) -> None:
        """Does not suggest cards outside deck's color identity."""
        # Woe Strider is black, goblin deck is red
        collection = Collection(cards={"Woe Strider": 4})

        analysis = analyze_and_improve_deck(
            deck_text=goblin_deck_text,
            collection=collection,
            card_db=card_db,
            format_name=DEFAULT_FORMAT,
            format_legal_cards=format_legal_cards,
        )

        # Should not suggest black card for mono-red deck
        woe_strider_suggestions = [s for s in analysis.suggestions if s.add_card == "Woe Strider"]
        assert len(woe_strider_suggestions) == 0

    def test_warns_low_card_count(
        self,
        card_db: dict[str, dict[str, Any]],
        format_legal_cards: set[str],
    ) -> None:
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
            format_name=DEFAULT_FORMAT,
            format_legal_cards=format_legal_cards,
        )

        assert any("14 cards" in w for w in analysis.warnings)

    def test_warns_low_land_count(
        self,
        card_db: dict[str, dict[str, Any]],
        format_legal_cards: set[str],
    ) -> None:
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
            format_name=DEFAULT_FORMAT,
            format_legal_cards=format_legal_cards,
        )

        assert any("land" in w.lower() for w in analysis.warnings)

    def test_handles_empty_deck(
        self,
        card_db: dict[str, dict[str, Any]],
        format_legal_cards: set[str],
    ) -> None:
        """Handles empty deck input gracefully."""
        collection = Collection()

        analysis = analyze_and_improve_deck(
            deck_text="",
            collection=collection,
            card_db=card_db,
            format_name=DEFAULT_FORMAT,
            format_legal_cards=format_legal_cards,
        )

        assert analysis.total_cards == 0
        assert len(analysis.warnings) > 0

    def test_respects_max_suggestions(
        self,
        goblin_deck_text: str,
        card_db: dict[str, dict[str, Any]],
        format_legal_cards: set[str],
    ) -> None:
        """Respects max_suggestions parameter."""
        collection = Collection(
            cards={
                "Goblin Chieftain": 4,
                "Goblin Rabblemaster": 4,
                "Lightning Bolt": 4,
            }
        )

        analysis = analyze_and_improve_deck(
            deck_text=goblin_deck_text,
            collection=collection,
            card_db=card_db,
            format_name=DEFAULT_FORMAT,
            format_legal_cards=format_legal_cards,
            max_suggestions=1,
        )

        assert len(analysis.suggestions) <= 1

    def test_includes_card_details(
        self,
        goblin_deck_text: str,
        card_db: dict[str, dict[str, Any]],
        format_legal_cards: set[str],
    ) -> None:
        """Includes card details with oracle text for non-land cards."""
        collection = Collection()

        analysis = analyze_and_improve_deck(
            deck_text=goblin_deck_text,
            collection=collection,
            card_db=card_db,
            format_name=DEFAULT_FORMAT,
            format_legal_cards=format_legal_cards,
        )

        # Should have card details for non-basic-land cards
        assert len(analysis.card_details) > 0

        # Check that Goblin Guide is in the details with oracle text
        goblin_guide = next((c for c in analysis.card_details if c.name == "Goblin Guide"), None)
        assert goblin_guide is not None
        assert "Haste" in goblin_guide.oracle_text

        # Mountains (basic lands) should be excluded
        mountain = next((c for c in analysis.card_details if c.name == "Mountain"), None)
        assert mountain is None

    def test_suggestion_includes_oracle_text(
        self,
        goblin_deck_text: str,
        card_db: dict[str, dict[str, Any]],
        format_legal_cards: set[str],
    ) -> None:
        """Suggestions include oracle text for both cards."""
        collection = Collection(cards={"Goblin Chieftain": 4})

        analysis = analyze_and_improve_deck(
            deck_text=goblin_deck_text,
            collection=collection,
            card_db=card_db,
            format_name=DEFAULT_FORMAT,
            format_legal_cards=format_legal_cards,
        )

        if analysis.suggestions:
            suggestion = analysis.suggestions[0]
            # Should have oracle text for the add card
            assert suggestion.add_card_text != ""


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

    def test_includes_detected_themes(self) -> None:
        """Includes detected themes in formatted output."""
        analysis = DeckAnalysis(
            original_cards={},
            total_cards=60,
            colors={"B"},
            creature_count=20,
            spell_count=16,
            land_count=24,
            detected_themes=["sacrifice", "tokens"],
        )

        formatted = format_deck_analysis(analysis)

        assert "sacrifice" in formatted
        assert "tokens" in formatted

    def test_includes_tribal_info(self) -> None:
        """Includes tribal info in formatted output."""
        analysis = DeckAnalysis(
            original_cards={},
            total_cards=60,
            colors={"R"},
            creature_count=24,
            spell_count=12,
            land_count=24,
            primary_tribe="goblin",
        )

        formatted = format_deck_analysis(analysis)

        assert "Goblin tribal" in formatted

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
                    remove_card="Raging Goblin",
                    remove_quantity=4,
                    add_card="Goblin Chieftain",
                    add_quantity=4,
                    reason="matches goblin tribal theme",
                )
            ],
        )

        formatted = format_deck_analysis(analysis)

        assert "Raging Goblin" in formatted
        assert "Goblin Chieftain" in formatted
        assert "tribal" in formatted

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

    def test_includes_suggestion_oracle_text(self) -> None:
        """Includes oracle text for suggested card swaps."""
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
                    reason="better removal",
                    remove_card_text="Shock deals 2 damage to any target.",
                    add_card_text="Lightning Bolt deals 3 damage to any target.",
                )
            ],
        )

        formatted = format_deck_analysis(analysis)

        assert "Shock deals 2 damage" in formatted
        assert "Lightning Bolt deals 3 damage" in formatted

    def test_includes_card_reference(self) -> None:
        """Includes card reference section with oracle text."""
        analysis = DeckAnalysis(
            original_cards={},
            total_cards=60,
            colors={"R"},
            creature_count=20,
            spell_count=16,
            land_count=24,
            card_details=[
                CardDetails(
                    name="Goblin Guide",
                    quantity=4,
                    type_line="Creature — Goblin Scout",
                    oracle_text="Haste. Whenever Goblin Guide attacks, defending player reveals.",
                )
            ],
        )

        formatted = format_deck_analysis(analysis)

        assert "Card Reference" in formatted
        assert "Goblin Guide" in formatted
        assert "Creature — Goblin Scout" in formatted
        assert "Haste" in formatted
