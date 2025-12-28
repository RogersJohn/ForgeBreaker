"""Tests for synergy finder service."""

from typing import Any

import pytest

from forgebreaker.models.collection import Collection
from forgebreaker.services.synergy_finder import (
    SynergyResult,
    find_synergies,
    format_synergy_results,
)

# Default format for testing - all cards in test db are assumed legal
DEFAULT_FORMAT = "standard"


@pytest.fixture
def card_db() -> dict[str, dict[str, Any]]:
    """Sample card database for testing."""
    return {
        "Mayhem Devil": {
            "type_line": "Creature — Devil",
            "colors": ["B", "R"],
            "set": "WAR",
            "cmc": 3,
            "oracle_text": (
                "Whenever a player sacrifices a permanent, "
                "Mayhem Devil deals 1 damage to any target."
            ),
        },
        "Witch's Oven": {
            "type_line": "Artifact",
            "colors": [],
            "set": "ELD",
            "cmc": 1,
            "oracle_text": (
                "{T}, Sacrifice a creature: Create a Food token. "
                "If the sacrificed creature's toughness was 4 or greater, "
                "create two Food tokens instead."
            ),
        },
        "Cauldron Familiar": {
            "type_line": "Creature — Cat",
            "colors": ["B"],
            "set": "ELD",
            "cmc": 1,
            "oracle_text": (
                "When Cauldron Familiar enters, each opponent loses 1 life. "
                "Sacrifice a Food: Return Cauldron Familiar from your graveyard."
            ),
        },
        "Blood Artist": {
            "type_line": "Creature — Vampire",
            "colors": ["B"],
            "set": "AVR",
            "cmc": 2,
            "oracle_text": (
                "Whenever Blood Artist or another creature dies, "
                "target player loses 1 life and you gain 1 life."
            ),
        },
        "Lightning Bolt": {
            "type_line": "Instant",
            "colors": ["R"],
            "set": "STA",
            "cmc": 1,
            "oracle_text": "Lightning Bolt deals 3 damage to any target.",
        },
        "Monastery Swiftspear": {
            "type_line": "Creature — Human Monk",
            "colors": ["R"],
            "set": "KTK",
            "cmc": 1,
            "oracle_text": (
                "Haste\nProwess (Whenever you cast a noncreature spell, "
                "this creature gets +1/+1 until end of turn.)"
            ),
        },
        "Opt": {
            "type_line": "Instant",
            "colors": ["U"],
            "set": "XLN",
            "cmc": 1,
            "oracle_text": "Scry 1.\nDraw a card.",
        },
        "Graveyard Trespasser": {
            "type_line": "Creature — Human Werewolf",
            "colors": ["B"],
            "set": "MID",
            "cmc": 3,
            "oracle_text": (
                "Ward—Discard a card.\nWhenever Graveyard Trespasser enters "
                "or attacks, exile up to one target card from a graveyard."
            ),
        },
        "Swamp": {
            "type_line": "Basic Land — Swamp",
            "colors": [],
            "set": "FDN",
            "cmc": 0,
            "oracle_text": "",
        },
    }


@pytest.fixture
def sacrifice_collection() -> Collection:
    """Collection with sacrifice synergy cards."""
    return Collection(
        cards={
            "Mayhem Devil": 2,
            "Witch's Oven": 4,
            "Cauldron Familiar": 4,
            "Blood Artist": 3,
            "Lightning Bolt": 4,
            "Swamp": 20,
        }
    )


@pytest.fixture
def spells_collection() -> Collection:
    """Collection with spell synergy cards."""
    return Collection(
        cards={
            "Lightning Bolt": 4,
            "Monastery Swiftspear": 4,
            "Opt": 4,
            "Swamp": 20,
        }
    )


@pytest.fixture
def format_legal_cards(card_db: dict[str, dict[str, Any]]) -> set[str]:
    """All cards in the test db are assumed to be format-legal."""
    return set(card_db.keys())


class TestFindSynergies:
    """Tests for find_synergies function."""

    def test_finds_sacrifice_synergies(
        self,
        sacrifice_collection: Collection,
        card_db: dict[str, dict[str, Any]],
        format_legal_cards: set[str],
    ) -> None:
        """Finds cards that synergize with sacrifice theme."""
        result = find_synergies(
            "Mayhem Devil",
            sacrifice_collection,
            card_db,
            DEFAULT_FORMAT,
            format_legal_cards,
        )

        assert result is not None
        assert result.source_card == "Mayhem Devil"
        assert result.synergy_type == "sacrifice"
        assert len(result.synergistic_cards) > 0

    def test_finds_dies_triggers(
        self,
        sacrifice_collection: Collection,
        card_db: dict[str, dict[str, Any]],
        format_legal_cards: set[str],
    ) -> None:
        """Blood Artist found as synergy (has 'dies' trigger)."""
        result = find_synergies(
            "Mayhem Devil",
            sacrifice_collection,
            card_db,
            DEFAULT_FORMAT,
            format_legal_cards,
        )

        assert result is not None
        card_names = [name for name, _, _ in result.synergistic_cards]
        assert "Blood Artist" in card_names

    def test_finds_food_token_synergies(
        self,
        sacrifice_collection: Collection,
        card_db: dict[str, dict[str, Any]],
        format_legal_cards: set[str],
    ) -> None:
        """Witch's Oven found as synergy (creates food tokens)."""
        result = find_synergies(
            "Mayhem Devil",
            sacrifice_collection,
            card_db,
            DEFAULT_FORMAT,
            format_legal_cards,
        )

        assert result is not None
        card_names = [name for name, _, _ in result.synergistic_cards]
        assert "Witch's Oven" in card_names

    def test_excludes_source_card(
        self,
        sacrifice_collection: Collection,
        card_db: dict[str, dict[str, Any]],
        format_legal_cards: set[str],
    ) -> None:
        """Source card is not included in synergistic cards."""
        result = find_synergies(
            "Mayhem Devil",
            sacrifice_collection,
            card_db,
            DEFAULT_FORMAT,
            format_legal_cards,
        )

        assert result is not None
        card_names = [name for name, _, _ in result.synergistic_cards]
        assert "Mayhem Devil" not in card_names

    def test_card_not_in_db_returns_none(
        self,
        sacrifice_collection: Collection,
        card_db: dict[str, dict[str, Any]],
        format_legal_cards: set[str],
    ) -> None:
        """Returns None for cards not in database."""
        result = find_synergies(
            "Unknown Card",
            sacrifice_collection,
            card_db,
            DEFAULT_FORMAT,
            format_legal_cards,
        )

        assert result is None

    def test_finds_instant_prowess_synergy(
        self,
        spells_collection: Collection,
        card_db: dict[str, dict[str, Any]],
        format_legal_cards: set[str],
    ) -> None:
        """Instants trigger prowess synergies."""
        result = find_synergies(
            "Lightning Bolt",
            spells_collection,
            card_db,
            DEFAULT_FORMAT,
            format_legal_cards,
        )

        assert result is not None
        assert result.synergy_type == "instant"
        card_names = [name for name, _, _ in result.synergistic_cards]
        assert "Monastery Swiftspear" in card_names

    def test_type_based_synergy_fallback(
        self,
        spells_collection: Collection,
        card_db: dict[str, dict[str, Any]],
        format_legal_cards: set[str],
    ) -> None:
        """Falls back to type-based synergies when no keyword match."""
        # Monastery Swiftspear has prowess but no synergy trigger keywords in oracle
        result = find_synergies(
            "Monastery Swiftspear",
            spells_collection,
            card_db,
            DEFAULT_FORMAT,
            format_legal_cards,
        )

        assert result is not None
        # Falls back to creature-type synergy since no pattern triggers matched
        assert result.synergy_type == "creature"

    def test_respects_max_results(
        self,
        sacrifice_collection: Collection,
        card_db: dict[str, dict[str, Any]],
        format_legal_cards: set[str],
    ) -> None:
        """Respects max_results parameter."""
        result = find_synergies(
            "Mayhem Devil",
            sacrifice_collection,
            card_db,
            DEFAULT_FORMAT,
            format_legal_cards,
            max_results=1,
        )

        assert result is not None
        assert len(result.synergistic_cards) <= 1

    def test_includes_quantity_in_results(
        self,
        sacrifice_collection: Collection,
        card_db: dict[str, dict[str, Any]],
        format_legal_cards: set[str],
    ) -> None:
        """Results include quantity owned."""
        result = find_synergies(
            "Mayhem Devil",
            sacrifice_collection,
            card_db,
            DEFAULT_FORMAT,
            format_legal_cards,
        )

        assert result is not None
        for name, qty, _ in result.synergistic_cards:
            assert qty > 0
            assert qty == sacrifice_collection.cards[name]

    def test_includes_reason_in_results(
        self,
        sacrifice_collection: Collection,
        card_db: dict[str, dict[str, Any]],
        format_legal_cards: set[str],
    ) -> None:
        """Results include reason for synergy."""
        result = find_synergies(
            "Mayhem Devil",
            sacrifice_collection,
            card_db,
            DEFAULT_FORMAT,
            format_legal_cards,
        )

        assert result is not None
        for _, _, reason in result.synergistic_cards:
            assert reason.startswith("Has '")


class TestFormatSynergyResults:
    """Tests for format_synergy_results function."""

    def test_formats_with_synergies(
        self,
        sacrifice_collection: Collection,
        card_db: dict[str, dict[str, Any]],
        format_legal_cards: set[str],
    ) -> None:
        """Formats results with synergistic cards."""
        result = find_synergies(
            "Mayhem Devil",
            sacrifice_collection,
            card_db,
            DEFAULT_FORMAT,
            format_legal_cards,
        )
        assert result is not None

        formatted = format_synergy_results(result)

        assert "## Cards that synergize with Mayhem Devil" in formatted
        assert "*Synergy type: sacrifice*" in formatted

    def test_formats_no_synergies(self) -> None:
        """Formats message when no synergies found."""
        result = SynergyResult(
            source_card="Lonely Card",
            synergy_type="general",
            synergistic_cards=[],
        )

        formatted = format_synergy_results(result)

        assert "No synergistic cards found" in formatted

    def test_includes_card_quantities(
        self,
        sacrifice_collection: Collection,
        card_db: dict[str, dict[str, Any]],
        format_legal_cards: set[str],
    ) -> None:
        """Formatted output includes quantities."""
        result = find_synergies(
            "Mayhem Devil",
            sacrifice_collection,
            card_db,
            DEFAULT_FORMAT,
            format_legal_cards,
        )
        assert result is not None

        formatted = format_synergy_results(result)

        # Should contain quantity format like "4x" or "3x"
        assert "x **" in formatted


class TestSynergyPatterns:
    """Tests for synergy pattern matching."""

    def test_graveyard_synergy_detection(
        self,
        card_db: dict[str, dict[str, Any]],
        format_legal_cards: set[str],
    ) -> None:
        """Detects graveyard synergies."""
        collection = Collection(
            cards={
                "Graveyard Trespasser": 4,
                "Blood Artist": 2,  # Has 'dies'
            }
        )

        result = find_synergies(
            "Graveyard Trespasser",
            collection,
            card_db,
            DEFAULT_FORMAT,
            format_legal_cards,
        )

        assert result is not None
        # The card's oracle text includes "graveyard", triggering graveyard synergy detection
        card_names = [name for name, _, _ in result.synergistic_cards]
        assert "Blood Artist" in card_names

    def test_artifact_type_synergy(
        self,
        sacrifice_collection: Collection,
        card_db: dict[str, dict[str, Any]],
        format_legal_cards: set[str],
    ) -> None:
        """Detects artifact type synergies."""
        result = find_synergies(
            "Witch's Oven",
            sacrifice_collection,
            card_db,
            DEFAULT_FORMAT,
            format_legal_cards,
        )

        assert result is not None
        # Witch's Oven is an artifact, should look for artifact synergies
