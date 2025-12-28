"""
Card Legality Boundary Tests — Architectural Contract.

This test protects ForgeBreaker's core invariant:

    Deck construction is selection from an authoritative set,
    never free-form generation.

If a card is not:
1. In the player's collection
2. Legal in the target format

...it must be IMPOSSIBLE for the system to suggest it.

These tests validate that the AllowedCardSet boundary is enforced
and that violations fail loudly, not silently.
"""

import dataclasses

import pytest

from forgebreaker.models.allowed_cards import (
    AllowedCardSet,
    CardNotAllowedError,
    build_allowed_set,
    validate_card_in_allowed_set,
    validate_card_list,
)
from forgebreaker.models.collection import Collection
from forgebreaker.services.deck_improver import analyze_and_improve_deck
from forgebreaker.services.synergy_finder import find_synergies


class TestAllowedCardSetConstruction:
    """Test that AllowedCardSet correctly intersects collection and legality."""

    def test_intersection_filters_illegal_cards(self) -> None:
        """Cards not legal in format are excluded even if owned."""
        collection = {
            "Lightning Bolt": 4,  # Legal in modern
            "Black Lotus": 1,  # Banned everywhere
            "Counterspell": 4,  # Not standard legal
        }
        standard_legal = {"Lightning Bolt", "Shock", "Mountain"}

        allowed = build_allowed_set(collection, standard_legal, "standard")

        assert "Lightning Bolt" in allowed
        assert "Black Lotus" not in allowed
        assert "Counterspell" not in allowed
        assert len(allowed) == 1

    def test_intersection_filters_unowned_cards(self) -> None:
        """Cards legal but not owned are excluded."""
        collection = {"Lightning Bolt": 4}
        standard_legal = {"Lightning Bolt", "Shock", "Mountain"}

        allowed = build_allowed_set(collection, standard_legal, "standard")

        assert "Lightning Bolt" in allowed
        assert "Shock" not in allowed  # Legal but not owned
        assert "Mountain" not in allowed  # Legal but not owned

    def test_quantity_preserved(self) -> None:
        """Owned quantity is preserved in allowed set."""
        collection = {"Lightning Bolt": 3, "Shock": 2}
        legal = {"Lightning Bolt", "Shock"}

        allowed = build_allowed_set(collection, legal, "standard")

        assert allowed.get_quantity("Lightning Bolt") == 3
        assert allowed.get_quantity("Shock") == 2
        assert allowed.get_quantity("Not Owned") == 0

    def test_empty_collection_produces_empty_set(self) -> None:
        """Empty collection produces empty allowed set."""
        allowed = build_allowed_set({}, {"Lightning Bolt"}, "standard")

        assert allowed.is_empty()
        assert len(allowed) == 0

    def test_empty_legality_produces_empty_set(self) -> None:
        """No legal cards produces empty allowed set."""
        allowed = build_allowed_set({"Lightning Bolt": 4}, set(), "standard")

        assert allowed.is_empty()


class TestCardValidation:
    """Test that validation correctly catches violations."""

    @pytest.fixture
    def allowed_set(self) -> AllowedCardSet:
        """Standard allowed set for testing."""
        return build_allowed_set(
            {"Lightning Bolt": 4, "Shock": 2},
            {"Lightning Bolt", "Shock"},
            "standard",
        )

    def test_valid_card_passes(self, allowed_set: AllowedCardSet) -> None:
        """Card in allowed set with sufficient quantity passes."""
        # Should not raise
        validate_card_in_allowed_set("Lightning Bolt", allowed_set, 2)
        validate_card_in_allowed_set("Shock", allowed_set, 1)

    def test_unallowed_card_raises(self, allowed_set: AllowedCardSet) -> None:
        """Card not in allowed set raises CardNotAllowedError."""
        with pytest.raises(CardNotAllowedError) as exc_info:
            validate_card_in_allowed_set("Black Lotus", allowed_set, 1)

        assert "Black Lotus" in str(exc_info.value)
        assert "not allowed" in str(exc_info.value).lower()

    def test_insufficient_quantity_raises(self, allowed_set: AllowedCardSet) -> None:
        """Card with insufficient quantity raises CardNotAllowedError."""
        with pytest.raises(CardNotAllowedError) as exc_info:
            validate_card_in_allowed_set("Shock", allowed_set, 4)  # Only have 2

        assert "Shock" in str(exc_info.value)
        assert "quantity" in str(exc_info.value).lower()

    def test_batch_validation_collects_all_errors(self, allowed_set: AllowedCardSet) -> None:
        """Batch validation returns all violations."""
        cards = {
            "Lightning Bolt": 2,  # Valid
            "Black Lotus": 1,  # Not allowed
            "Shock": 4,  # Quantity exceeded
        }

        violations = validate_card_list(cards, allowed_set)

        assert len(violations) == 2
        assert any("Black Lotus" in v for v in violations)
        assert any("Shock" in v for v in violations)


class TestDeckImproverBoundary:
    """Test that deck improver respects the allowed card boundary."""

    @pytest.fixture
    def card_db(self) -> dict:
        """Minimal card database for testing."""
        return {
            "Lightning Bolt": {
                "name": "Lightning Bolt",
                "type_line": "Instant",
                "oracle_text": "Lightning Bolt deals 3 damage to any target.",
                "cmc": 1,
                "colors": ["R"],
                "legalities": {"standard": "legal", "modern": "legal"},
            },
            "Shock": {
                "name": "Shock",
                "type_line": "Instant",
                "oracle_text": "Shock deals 2 damage to any target.",
                "cmc": 1,
                "colors": ["R"],
                "legalities": {"standard": "legal", "modern": "legal"},
            },
            "Illegal Card": {
                "name": "Illegal Card",
                "type_line": "Instant",
                "oracle_text": "This card is not standard legal.",
                "cmc": 1,
                "colors": ["R"],
                "legalities": {"standard": "not_legal", "modern": "legal"},
            },
            "Mountain": {
                "name": "Mountain",
                "type_line": "Basic Land — Mountain",
                "oracle_text": "",
                "cmc": 0,
                "colors": [],
                "legalities": {"standard": "legal", "modern": "legal"},
            },
        }

    def test_suggestions_only_from_allowed_set(self, card_db: dict) -> None:
        """Suggestions must come from cards that are both owned AND legal."""
        deck_text = """
4 Lightning Bolt
20 Mountain
"""
        # Collection includes an illegal card
        collection = Collection(
            cards={
                "Lightning Bolt": 4,
                "Shock": 4,  # Owned and legal - valid suggestion source
                "Illegal Card": 4,  # Owned but NOT legal - must not be suggested
            }
        )
        standard_legal = {"Lightning Bolt", "Shock", "Mountain"}

        analysis = analyze_and_improve_deck(
            deck_text=deck_text,
            collection=collection,
            card_db=card_db,
            format_name="standard",
            format_legal_cards=standard_legal,
            max_suggestions=5,
        )

        # If any suggestions exist, they must be from allowed cards
        for suggestion in analysis.suggestions:
            assert suggestion.add_card in standard_legal, (
                f"Suggestion '{suggestion.add_card}' is not in allowed set"
            )
            assert suggestion.add_card in collection.cards, (
                f"Suggestion '{suggestion.add_card}' is not owned"
            )
            assert suggestion.add_card != "Illegal Card", (
                "Illegal card was suggested - boundary violated!"
            )


class TestSynergyFinderBoundary:
    """Test that synergy finder respects the allowed card boundary."""

    @pytest.fixture
    def card_db(self) -> dict:
        """Minimal card database for testing."""
        return {
            "Blood Artist": {
                "name": "Blood Artist",
                "type_line": "Creature — Vampire",
                "oracle_text": (
                    "Whenever Blood Artist or another creature dies, "
                    "target player loses 1 life and you gain 1 life."
                ),
                "cmc": 2,
                "colors": ["B"],
                "legalities": {"standard": "legal"},
            },
            "Viscera Seer": {
                "name": "Viscera Seer",
                "type_line": "Creature — Vampire Wizard",
                "oracle_text": "Sacrifice a creature: Scry 1.",
                "cmc": 1,
                "colors": ["B"],
                "legalities": {"standard": "legal"},
            },
            "Illegal Sacrifice": {
                "name": "Illegal Sacrifice",
                "type_line": "Creature",
                "oracle_text": "Sacrifice a creature: Draw a card.",
                "cmc": 2,
                "colors": ["B"],
                "legalities": {"standard": "not_legal"},
            },
        }

    def test_synergies_only_from_allowed_set(self, card_db: dict) -> None:
        """Synergy suggestions must be from cards that are both owned AND legal."""
        # Collection includes an illegal card with sacrifice synergy
        collection = Collection(
            cards={
                "Blood Artist": 4,
                "Viscera Seer": 4,  # Owned and legal
                "Illegal Sacrifice": 4,  # Owned but NOT legal
            }
        )
        standard_legal = {"Blood Artist", "Viscera Seer"}

        result = find_synergies(
            card_name="Blood Artist",
            collection=collection,
            card_db=card_db,
            format_name="standard",
            format_legal_cards=standard_legal,
            max_results=10,
        )

        assert result is not None

        # All synergistic cards must be from allowed set
        for name, _qty, _reason in result.synergistic_cards:
            assert name in standard_legal, f"Synergy '{name}' is not format-legal"
            assert name in collection.cards, f"Synergy '{name}' is not owned"
            assert name != "Illegal Sacrifice", (
                "Illegal card was suggested as synergy - boundary violated!"
            )


class TestBoundaryFailsLoudly:
    """Test that boundary violations fail loudly, not silently."""

    def test_validation_error_includes_context(self) -> None:
        """CardNotAllowedError includes useful debugging context."""
        allowed = build_allowed_set({"Shock": 2}, {"Shock"}, "standard")

        with pytest.raises(CardNotAllowedError) as exc_info:
            validate_card_in_allowed_set("Black Lotus", allowed, 1)

        error = exc_info.value
        assert error.card_name == "Black Lotus"
        assert error.allowed_set == allowed
        assert "standard" in str(error)

    def test_allowed_set_attributes_are_immutable(self) -> None:
        """AllowedCardSet attributes cannot be reassigned after construction."""
        allowed = build_allowed_set({"Shock": 2}, {"Shock"}, "standard")

        # AllowedCardSet is frozen=True, so attribute reassignment should raise
        with pytest.raises((AttributeError, dataclasses.FrozenInstanceError)):
            allowed.format = "modern"  # type: ignore

        with pytest.raises((AttributeError, dataclasses.FrozenInstanceError)):
            allowed.cards = {"Other": 1}  # type: ignore
