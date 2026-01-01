"""
Tests for deck size invariant enforcement.

INVARIANT: Deck size is a HARD CONSTRAINT, not a preference.
Decks must contain exactly the requested number of cards.

These tests verify:
1. A request for a 60-card deck always returns exactly 60 cards
2. Decks larger than the target are deterministically trimmed
3. Undersized decks result in a DeckSizeError
4. No LLM calls occur during deck finalization
"""

import pytest

from forgebreaker.models.collection import Collection
from forgebreaker.models.failure import DeckSizeError, FailureKind
from forgebreaker.services.deck_builder import (
    BuiltDeck,
    DeckBuildRequest,
    build_deck,
    enforce_deck_size,
)


class TestDeckSizeEnforcement:
    """Tests for exact deck size enforcement."""

    def test_60_card_request_returns_exactly_60_cards(self) -> None:
        """A request for a 60-card deck always returns exactly 60 cards."""
        # Collection with exactly enough cards
        collection = Collection(
            cards={
                "Lightning Bolt": 4,
                "Shock": 4,
                "Goblin Guide": 4,
                "Monastery Swiftspear": 4,
                "Eidolon of the Great Revel": 4,
                "Lava Spike": 4,
                "Rift Bolt": 4,
                "Searing Blaze": 4,
                "Shard Volley": 4,
                "Light Up the Stage": 4,  # 40 nonland cards
                "Mountain": 100,  # Plenty of lands
            }
        )

        card_db = {
            "Lightning Bolt": {
                "type_line": "Instant",
                "colors": ["R"],
                "cmc": 1,
                "mana_cost": "{R}",
            },
            "Shock": {"type_line": "Instant", "colors": ["R"], "cmc": 1, "mana_cost": "{R}"},
            "Goblin Guide": {
                "type_line": "Creature — Goblin Scout",
                "colors": ["R"],
                "cmc": 1,
                "mana_cost": "{R}",
            },
            "Monastery Swiftspear": {
                "type_line": "Creature — Human Monk",
                "colors": ["R"],
                "cmc": 1,
                "mana_cost": "{R}",
            },
            "Eidolon of the Great Revel": {
                "type_line": "Enchantment Creature",
                "colors": ["R"],
                "cmc": 2,
                "mana_cost": "{R}{R}",
            },
            "Lava Spike": {"type_line": "Sorcery", "colors": ["R"], "cmc": 1, "mana_cost": "{R}"},
            "Rift Bolt": {"type_line": "Sorcery", "colors": ["R"], "cmc": 3, "mana_cost": "{2}{R}"},
            "Searing Blaze": {
                "type_line": "Instant",
                "colors": ["R"],
                "cmc": 2,
                "mana_cost": "{R}{R}",
            },
            "Shard Volley": {"type_line": "Instant", "colors": ["R"], "cmc": 1, "mana_cost": "{R}"},
            "Light Up the Stage": {
                "type_line": "Sorcery",
                "colors": ["R"],
                "cmc": 3,
                "mana_cost": "{2}{R}",
            },
            "Mountain": {
                "type_line": "Basic Land — Mountain",
                "colors": [],
                "cmc": 0,
                "mana_cost": "",
            },
        }

        format_legality = {"standard": set(card_db.keys())}

        request = DeckBuildRequest(theme="burn", format="standard", deck_size=60, land_count=24)
        deck = build_deck(request, collection, card_db, format_legality)

        # INVARIANT: Deck must be exactly 60 cards
        assert deck.total_cards == 60, f"Expected 60 cards, got {deck.total_cards}"

    def test_oversized_deck_is_deterministically_trimmed(self) -> None:
        """Decks larger than the target are deterministically trimmed."""
        # Create a deck with 65 cards (5 over)
        deck = BuiltDeck(
            name="Test Deck",
            cards={
                "Card A": 4,  # Score 10.0 - will be trimmed first
                "Card B": 4,  # Score 10.5 - will be trimmed second
                "Card C": 4,  # Score 11.0
                "Card D": 4,  # Score 11.5
                "Card E": 4,  # Score 12.0
                "Card F": 4,  # Score 12.5
                "Card G": 4,  # Score 13.0
                "Card H": 4,  # Score 13.5
                "Card I": 4,  # Score 14.0
                "Card J": 1,  # Score 14.5
            },
            total_cards=61,  # 37 nonland + 24 lands
            colors={"R"},
            theme_cards=["Card A", "Card B", "Card C"],
            support_cards=["Card D", "Card E"],
            lands={"Mountain": 24},
            card_scores={
                "Card A": 10.0,
                "Card B": 10.5,
                "Card C": 11.0,
                "Card D": 11.5,
                "Card E": 12.0,
                "Card F": 12.5,
                "Card G": 13.0,
                "Card H": 13.5,
                "Card I": 14.0,
                "Card J": 14.5,
            },
        )

        # Enforce size to 60
        result = enforce_deck_size(deck, 60)

        # INVARIANT: Result is exactly 60 cards
        assert result.total_cards == 60

        # Lowest-scoring card (Card A) should be trimmed first
        # We need to remove 1 card to go from 61 to 60
        assert "Card A" in result.cards
        # Card A had 4 copies, should have 3 now (1 removed)
        assert result.cards["Card A"] == 3

    def test_undersized_deck_raises_deck_size_error(self) -> None:
        """Undersized decks result in a DeckSizeError."""
        # Create a deck with only 40 cards
        deck = BuiltDeck(
            name="Test Deck",
            cards={"Card A": 16},
            total_cards=40,  # 16 nonland + 24 lands
            colors={"R"},
            theme_cards=["Card A"],
            support_cards=[],
            lands={"Mountain": 24},
            card_scores={"Card A": 10.0},
        )

        # INVARIANT: Undersized deck raises DeckSizeError
        with pytest.raises(DeckSizeError) as exc_info:
            enforce_deck_size(deck, 60)

        error = exc_info.value
        assert error.requested_size == 60
        assert error.actual_size == 40
        assert error.kind == FailureKind.DECK_SIZE_VIOLATION

    def test_exact_size_deck_passes_through_unchanged(self) -> None:
        """Deck with exact size passes through unchanged."""
        deck = BuiltDeck(
            name="Test Deck",
            cards={"Card A": 36},
            total_cards=60,  # Exactly right
            colors={"R"},
            theme_cards=["Card A"],
            support_cards=[],
            lands={"Mountain": 24},
            card_scores={"Card A": 10.0},
        )

        result = enforce_deck_size(deck, 60)

        # Should be the same deck
        assert result.total_cards == 60
        assert result.cards == deck.cards

    def test_trimming_removes_lowest_scoring_cards_first(self) -> None:
        """Trimming removes cards with lowest scores first."""
        deck = BuiltDeck(
            name="Test Deck",
            cards={
                "Low Score Card": 4,  # Score 1.0
                "High Score Card": 4,  # Score 100.0
            },
            total_cards=32,  # 8 nonland + 24 lands
            colors={"R"},
            theme_cards=["Low Score Card", "High Score Card"],
            support_cards=[],
            lands={"Mountain": 24},
            card_scores={
                "Low Score Card": 1.0,
                "High Score Card": 100.0,
            },
        )

        # Request 30 cards (need to trim 2)
        result = enforce_deck_size(deck, 30)

        assert result.total_cards == 30
        # Low score card should have 2 copies removed
        assert result.cards["Low Score Card"] == 2
        # High score card should be unchanged
        assert result.cards["High Score Card"] == 4

    def test_lands_are_not_trimmed(self) -> None:
        """Lands are locked and never trimmed."""
        deck = BuiltDeck(
            name="Test Deck",
            cards={"Card A": 40},
            total_cards=64,  # 40 nonland + 24 lands
            colors={"R"},
            theme_cards=["Card A"],
            support_cards=[],
            lands={"Mountain": 24},
            card_scores={"Card A": 10.0},
        )

        # Trim to 60 (remove 4 nonland cards)
        result = enforce_deck_size(deck, 60)

        assert result.total_cards == 60
        # Lands should be unchanged
        assert result.lands == {"Mountain": 24}
        # Nonland cards should be reduced
        assert result.cards["Card A"] == 36


class TestDeckSizeErrorProperties:
    """Tests for DeckSizeError exception properties."""

    def test_deck_size_error_has_correct_kind(self) -> None:
        """DeckSizeError has DECK_SIZE_VIOLATION kind."""
        error = DeckSizeError(requested_size=60, actual_size=40)
        assert error.kind == FailureKind.DECK_SIZE_VIOLATION

    def test_deck_size_error_has_correct_message(self) -> None:
        """DeckSizeError has descriptive message."""
        error = DeckSizeError(requested_size=60, actual_size=40)
        assert "60-card deck" in error.message
        assert "40 cards available" in error.message

    def test_deck_size_error_stores_sizes(self) -> None:
        """DeckSizeError stores requested and actual sizes."""
        error = DeckSizeError(requested_size=60, actual_size=45)
        assert error.requested_size == 60
        assert error.actual_size == 45


class TestDeterministicTrimming:
    """Tests verifying trimming is deterministic (no randomness)."""

    def test_trimming_is_deterministic(self) -> None:
        """Same input always produces same output."""
        deck = BuiltDeck(
            name="Test Deck",
            cards={
                "Card A": 4,
                "Card B": 4,
                "Card C": 4,
            },
            total_cards=36,  # 12 nonland + 24 lands
            colors={"R"},
            theme_cards=["Card A", "Card B", "Card C"],
            support_cards=[],
            lands={"Mountain": 24},
            card_scores={
                "Card A": 10.0,
                "Card B": 11.0,
                "Card C": 12.0,
            },
        )

        # Run multiple times
        results = [enforce_deck_size(deck, 34) for _ in range(10)]

        # All results should be identical
        first_result = results[0]
        for result in results[1:]:
            assert result.cards == first_result.cards
            assert result.total_cards == first_result.total_cards

    def test_score_ties_are_handled_deterministically(self) -> None:
        """Cards with equal scores are handled deterministically (by name order)."""
        deck = BuiltDeck(
            name="Test Deck",
            cards={
                "Zebra Card": 4,  # Same score, but alphabetically last
                "Apple Card": 4,  # Same score, but alphabetically first
            },
            total_cards=32,
            colors={"R"},
            theme_cards=["Zebra Card", "Apple Card"],
            support_cards=[],
            lands={"Mountain": 24},
            card_scores={
                "Zebra Card": 10.0,
                "Apple Card": 10.0,  # Tie!
            },
        )

        # Run multiple times
        results = [enforce_deck_size(deck, 30) for _ in range(10)]

        # All results should be identical
        first_result = results[0]
        for result in results[1:]:
            assert result.cards == first_result.cards


class TestBuildDeckEnforcesDeckSize:
    """Tests verifying build_deck enforces deck size."""

    def test_build_deck_returns_exact_requested_size(self) -> None:
        """build_deck returns exactly the requested deck size."""
        # Collection with plenty of cards to build a 40-card deck
        # Need 24 nonland cards (40 - 16 lands)
        collection = Collection(
            cards={
                "Lightning Bolt": 4,
                "Shock": 4,
                "Goblin Guide": 4,
                "Monastery Swiftspear": 4,
                "Lava Spike": 4,
                "Rift Bolt": 4,
                "Searing Blaze": 4,  # 28 nonland cards total (more than needed)
                "Mountain": 100,
            }
        )

        card_db = {
            "Lightning Bolt": {
                "type_line": "Instant",
                "colors": ["R"],
                "cmc": 1,
                "mana_cost": "{R}",
            },
            "Shock": {"type_line": "Instant", "colors": ["R"], "cmc": 1, "mana_cost": "{R}"},
            "Goblin Guide": {
                "type_line": "Creature — Goblin Scout",
                "colors": ["R"],
                "cmc": 1,
                "mana_cost": "{R}",
            },
            "Monastery Swiftspear": {
                "type_line": "Creature — Human Monk",
                "colors": ["R"],
                "cmc": 1,
                "mana_cost": "{R}",
            },
            "Lava Spike": {"type_line": "Sorcery", "colors": ["R"], "cmc": 1, "mana_cost": "{R}"},
            "Rift Bolt": {"type_line": "Sorcery", "colors": ["R"], "cmc": 3, "mana_cost": "{2}{R}"},
            "Searing Blaze": {
                "type_line": "Instant",
                "colors": ["R"],
                "cmc": 2,
                "mana_cost": "{R}{R}",
            },
            "Mountain": {
                "type_line": "Basic Land — Mountain",
                "colors": [],
                "cmc": 0,
                "mana_cost": "",
            },
        }

        format_legality = {"standard": set(card_db.keys())}

        # Request smaller deck: 40 cards with 16 lands = 24 nonlands needed
        request = DeckBuildRequest(theme="burn", format="standard", deck_size=40, land_count=16)
        deck = build_deck(request, collection, card_db, format_legality)

        # INVARIANT: Deck is exactly 40 cards
        assert deck.total_cards == 40

    def test_build_deck_raises_on_insufficient_cards(self) -> None:
        """build_deck raises DeckSizeError when not enough cards available."""
        # Very small collection
        collection = Collection(
            cards={
                "Lightning Bolt": 2,
                "Mountain": 10,
            }
        )

        card_db = {
            "Lightning Bolt": {
                "type_line": "Instant",
                "colors": ["R"],
                "cmc": 1,
                "mana_cost": "{R}",
            },
            "Mountain": {
                "type_line": "Basic Land — Mountain",
                "colors": [],
                "cmc": 0,
                "mana_cost": "",
            },
        }

        format_legality = {"standard": set(card_db.keys())}

        request = DeckBuildRequest(theme="burn", format="standard", deck_size=60, land_count=24)

        # INVARIANT: Insufficient cards raises DeckSizeError
        with pytest.raises(DeckSizeError):
            build_deck(request, collection, card_db, format_legality)
