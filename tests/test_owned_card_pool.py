"""
Tests for PR3: Owned Card Pool Builder.

INVARIANT: Only cards with count > 0 may appear in the pool.
Count=0 cards must NEVER leak into deck construction.

INVARIANT: No deck may exceed:
  - owned count for any card
  - max copies per card (default 4)
"""

import pytest

from forgebreaker.models.canonical_card import CanonicalCard, OwnedCard
from forgebreaker.models.owned_card_pool import (
    DEFAULT_MAX_COPIES,
    CopyLimitExceededError,
    OwnedCardPool,
    build_owned_pool,
)

# =============================================================================
# TEST FIXTURES
# =============================================================================


@pytest.fixture
def sample_canonical_cards() -> list[CanonicalCard]:
    """Sample canonical cards for testing."""
    return [
        CanonicalCard(
            oracle_id="bolt-123",
            name="Lightning Bolt",
            type_line="Instant",
            colors=("R",),
            legalities={"standard": "not_legal", "historic": "legal"},
        ),
        CanonicalCard(
            oracle_id="mountain-456",
            name="Mountain",
            type_line="Basic Land — Mountain",
            colors=(),
            legalities={"standard": "legal", "historic": "legal"},
        ),
        CanonicalCard(
            oracle_id="counter-789",
            name="Counterspell",
            type_line="Instant",
            colors=("U",),
            legalities={"standard": "not_legal", "historic": "legal"},
        ),
    ]


@pytest.fixture
def owned_cards_with_counts(sample_canonical_cards: list[CanonicalCard]) -> list[OwnedCard]:
    """Owned cards with various counts including zero."""
    return [
        OwnedCard(card=sample_canonical_cards[0], count=4),  # Lightning Bolt x4
        OwnedCard(card=sample_canonical_cards[1], count=20),  # Mountain x20
        OwnedCard(card=sample_canonical_cards[2], count=0),  # Counterspell x0 (PHANTOM)
    ]


# =============================================================================
# CORE INVARIANT TESTS: COUNT > 0
# =============================================================================


class TestCountInvariant:
    """
    Tests proving the count > 0 invariant.

    INVARIANT: Only cards with count > 0 may appear in the pool.
    """

    def test_count_zero_cards_filtered_from_owned_cards(
        self, owned_cards_with_counts: list[OwnedCard]
    ) -> None:
        """
        CRITICAL: Count=0 cards are filtered when building pool.

        Counterspell has count=0 and must NOT appear in the pool.
        """
        pool = OwnedCardPool.from_owned_cards(owned_cards_with_counts)

        # Cards with count > 0 are in pool
        assert "Lightning Bolt" in pool
        assert "Mountain" in pool

        # Card with count=0 is NOT in pool
        assert "Counterspell" not in pool

    def test_count_zero_cards_filtered_from_dict(self) -> None:
        """
        Count=0 cards are filtered when building from dict.
        """
        cards = {
            "Lightning Bolt": 4,
            "Mountain": 20,
            "Counterspell": 0,  # Zero count
        }

        pool = OwnedCardPool.from_dict(cards)

        assert "Lightning Bolt" in pool
        assert "Mountain" in pool
        assert "Counterspell" not in pool

    def test_negative_count_cards_filtered(self) -> None:
        """
        Negative counts are also filtered (defensive).
        """
        cards = {
            "Lightning Bolt": 4,
            "Bad Card": -1,  # Negative count (should never happen)
        }

        pool = OwnedCardPool.from_dict(cards)

        assert "Lightning Bolt" in pool
        assert "Bad Card" not in pool

    def test_pool_length_excludes_zero_count(
        self, owned_cards_with_counts: list[OwnedCard]
    ) -> None:
        """
        Pool length reflects only cards with count > 0.
        """
        pool = OwnedCardPool.from_owned_cards(owned_cards_with_counts)

        # 3 input cards, but only 2 have count > 0
        assert len(pool) == 2

    def test_iteration_excludes_zero_count(self, owned_cards_with_counts: list[OwnedCard]) -> None:
        """
        Iterating pool only yields cards with count > 0.
        """
        pool = OwnedCardPool.from_owned_cards(owned_cards_with_counts)

        card_names = list(pool)

        assert "Lightning Bolt" in card_names
        assert "Mountain" in card_names
        assert "Counterspell" not in card_names

    def test_items_excludes_zero_count(self, owned_cards_with_counts: list[OwnedCard]) -> None:
        """
        items() only yields (name, count) pairs with count > 0.
        """
        pool = OwnedCardPool.from_owned_cards(owned_cards_with_counts)

        items = dict(pool.items())

        assert items["Lightning Bolt"] == 4
        assert items["Mountain"] == 20
        assert "Counterspell" not in items


class TestCountAuthority:
    """
    Tests proving counts are authoritative for deck construction.
    """

    def test_get_count_returns_owned_quantity(
        self, owned_cards_with_counts: list[OwnedCard]
    ) -> None:
        """
        get_count returns the exact owned quantity.
        """
        pool = OwnedCardPool.from_owned_cards(owned_cards_with_counts)

        assert pool.get_count("Lightning Bolt") == 4
        assert pool.get_count("Mountain") == 20

    def test_get_count_returns_zero_for_missing(
        self, owned_cards_with_counts: list[OwnedCard]
    ) -> None:
        """
        get_count returns 0 for cards not in pool.
        """
        pool = OwnedCardPool.from_owned_cards(owned_cards_with_counts)

        # Counterspell was filtered (count=0)
        assert pool.get_count("Counterspell") == 0

        # Card never in collection
        assert pool.get_count("Black Lotus") == 0

    def test_get_max_copies_respects_limit(self, owned_cards_with_counts: list[OwnedCard]) -> None:
        """
        get_max_copies respects the deck limit.
        """
        pool = OwnedCardPool.from_owned_cards(owned_cards_with_counts)

        # Lightning Bolt: own 4, limit 4 -> 4
        assert pool.get_max_copies("Lightning Bolt", limit=4) == 4

        # Mountain: own 20, limit 4 -> 4
        assert pool.get_max_copies("Mountain", limit=4) == 4

        # Mountain: own 20, limit 10 -> 10
        assert pool.get_max_copies("Mountain", limit=10) == 10

    def test_get_max_copies_returns_zero_for_filtered(
        self, owned_cards_with_counts: list[OwnedCard]
    ) -> None:
        """
        get_max_copies returns 0 for cards that were filtered.
        """
        pool = OwnedCardPool.from_owned_cards(owned_cards_with_counts)

        # Counterspell was filtered (count=0)
        assert pool.get_max_copies("Counterspell", limit=4) == 0


class TestPhantomCardPrevention:
    """
    Tests ensuring phantom cards (count=0) never appear downstream.
    """

    def test_phantom_cards_never_in_iteration(self) -> None:
        """
        Phantom cards with count=0 never appear when iterating.

        This is the fundamental guarantee for deck construction.
        """
        cards = {
            "Real Card": 4,
            "Phantom Card": 0,
        }

        pool = OwnedCardPool.from_dict(cards)

        # Collect all cards from iteration
        iterated_cards = set()
        for name in pool:
            iterated_cards.add(name)

        assert "Real Card" in iterated_cards
        assert "Phantom Card" not in iterated_cards

    def test_to_dict_excludes_phantoms(self) -> None:
        """
        to_dict() exports only count > 0 cards.
        """
        cards = {
            "Real Card": 4,
            "Phantom Card": 0,
        }

        pool = OwnedCardPool.from_dict(cards)
        exported = pool.to_dict()

        assert "Real Card" in exported
        assert "Phantom Card" not in exported

    def test_filter_by_names_preserves_invariant(self) -> None:
        """
        Filtering by names still excludes phantoms.
        """
        cards = {
            "Real Card A": 4,
            "Real Card B": 2,
            "Phantom Card": 0,
        }

        pool = OwnedCardPool.from_dict(cards)
        filtered = pool.filter_by_names({"Real Card A", "Real Card B", "Phantom Card"})

        assert "Real Card A" in filtered
        assert "Real Card B" in filtered
        # Phantom was never in pool, so can't be in filtered result
        assert "Phantom Card" not in filtered


class TestDeckConstructionConstraints:
    """
    Tests for deck construction quantity constraints.
    """

    def test_deck_cannot_exceed_owned_quantity(
        self, owned_cards_with_counts: list[OwnedCard]
    ) -> None:
        """
        Deck construction respects owned quantities.

        This is enforced by callers using get_max_copies().
        """
        pool = OwnedCardPool.from_owned_cards(owned_cards_with_counts)

        # Simulate deck construction logic
        deck: dict[str, int] = {}
        for card_name in pool:
            max_copies = pool.get_max_copies(card_name, limit=4)
            if max_copies > 0:
                deck[card_name] = max_copies

        # Check deck respects limits
        assert deck["Lightning Bolt"] == 4  # min(4, 4)
        assert deck["Mountain"] == 4  # min(20, 4)

        # No phantom cards
        assert "Counterspell" not in deck

    def test_total_cards_accurate(self) -> None:
        """
        total_cards() sums only count > 0 cards.
        """
        cards = {
            "Card A": 4,
            "Card B": 10,
            "Phantom": 0,
        }

        pool = OwnedCardPool.from_dict(cards)

        assert pool.total_cards() == 14  # 4 + 10, not counting phantom

    def test_unique_cards_accurate(self) -> None:
        """
        unique_cards() counts only count > 0 cards.
        """
        cards = {
            "Card A": 4,
            "Card B": 10,
            "Phantom": 0,
        }

        pool = OwnedCardPool.from_dict(cards)

        assert pool.unique_cards() == 2  # Not counting phantom


class TestBuildOwnedPool:
    """
    Tests for the build_owned_pool helper function.
    """

    def test_build_with_legal_cards_filter(
        self, sample_canonical_cards: list[CanonicalCard]
    ) -> None:
        """
        build_owned_pool can filter by legal cards.
        """
        owned = [
            OwnedCard(card=sample_canonical_cards[0], count=4),  # Lightning Bolt
            OwnedCard(card=sample_canonical_cards[1], count=20),  # Mountain
        ]

        # Only Mountain is Standard-legal
        legal_cards = {"Mountain"}

        pool = build_owned_pool(owned, legal_cards=legal_cards)

        assert "Mountain" in pool
        assert "Lightning Bolt" not in pool

    def test_build_without_filter(self, sample_canonical_cards: list[CanonicalCard]) -> None:
        """
        build_owned_pool without filter includes all count > 0 cards.
        """
        owned = [
            OwnedCard(card=sample_canonical_cards[0], count=4),  # Lightning Bolt
            OwnedCard(card=sample_canonical_cards[1], count=20),  # Mountain
        ]

        pool = build_owned_pool(owned)

        assert "Lightning Bolt" in pool
        assert "Mountain" in pool


# =============================================================================
# REGRESSION TESTS
# =============================================================================


class TestNoPhantomLeakageRegression:
    """
    Regression tests to prevent phantom card leakage.

    These tests will FAIL if the invariant is broken.
    """

    def test_empty_pool_is_valid(self) -> None:
        """
        Empty pool is valid (no cards owned).
        """
        pool = OwnedCardPool.from_dict({})

        assert len(pool) == 0
        assert pool.total_cards() == 0
        assert list(pool) == []

    def test_all_zero_counts_produces_empty_pool(self) -> None:
        """
        All zero-count cards produce empty pool.
        """
        cards = {
            "Phantom A": 0,
            "Phantom B": 0,
        }

        pool = OwnedCardPool.from_dict(cards)

        assert len(pool) == 0
        assert list(pool) == []

    def test_pool_attribute_immutability(self) -> None:
        """
        Pool attributes are immutable - cannot reassign _cards.
        """
        pool = OwnedCardPool.from_dict({"Card": 4})

        with pytest.raises(AttributeError):
            pool._cards = {}  # type: ignore[misc]


# =============================================================================
# MANDATORY TESTS: COPY LIMIT ENFORCEMENT
# =============================================================================


class TestAvailableCopies:
    """
    Tests for available_copies(card: CanonicalCard) method.

    INVARIANT: Returns min(owned_count, max_copies).
    """

    def test_available_copies_with_canonical_card(
        self, sample_canonical_cards: list[CanonicalCard]
    ) -> None:
        """
        available_copies() accepts CanonicalCard and returns correct count.
        """
        owned = [
            OwnedCard(card=sample_canonical_cards[0], count=4),  # Lightning Bolt
            OwnedCard(card=sample_canonical_cards[1], count=20),  # Mountain
        ]
        pool = OwnedCardPool.from_owned_cards(owned)

        # Lightning Bolt: own 4, max 4 -> 4
        assert pool.available_copies(sample_canonical_cards[0]) == 4

        # Mountain: own 20, max 4 -> 4
        assert pool.available_copies(sample_canonical_cards[1]) == 4

    def test_available_copies_respects_custom_limit(
        self, sample_canonical_cards: list[CanonicalCard]
    ) -> None:
        """
        available_copies() respects custom max_copies limit.
        """
        owned = [
            OwnedCard(card=sample_canonical_cards[1], count=20),  # Mountain
        ]
        pool = OwnedCardPool.from_owned_cards(owned)

        # Custom limit of 10
        assert pool.available_copies(sample_canonical_cards[1], max_copies=10) == 10

        # Custom limit higher than owned
        assert pool.available_copies(sample_canonical_cards[1], max_copies=100) == 20

    def test_available_copies_returns_zero_for_unowned(
        self, sample_canonical_cards: list[CanonicalCard]
    ) -> None:
        """
        available_copies() returns 0 for cards not in pool.
        """
        pool = OwnedCardPool.from_dict({"Other Card": 4})

        # Card not in pool
        assert pool.available_copies(sample_canonical_cards[0]) == 0

    def test_default_max_copies_is_four(self) -> None:
        """
        DEFAULT_MAX_COPIES is 4 for constructed formats.
        """
        assert DEFAULT_MAX_COPIES == 4


class TestDeckExceedsOwnedCopies:
    """
    MANDATORY TEST: No deck exceeds owned copies.
    """

    def test_deck_exceeds_owned_copies_fails(self) -> None:
        """
        Deck requesting more copies than owned raises CopyLimitExceededError.
        """
        pool = OwnedCardPool.from_dict({"Lightning Bolt": 2})

        deck = {"Lightning Bolt": 4}  # Only own 2

        with pytest.raises(CopyLimitExceededError) as exc_info:
            pool.validate_deck(deck)

        error = exc_info.value
        assert error.card_name == "Lightning Bolt"
        assert error.requested == 4
        assert error.available == 2
        assert "only 2 owned" in error.reason

    def test_deck_with_unowned_card_fails(self) -> None:
        """
        Deck requesting unowned card raises CopyLimitExceededError.
        """
        pool = OwnedCardPool.from_dict({"Mountain": 20})

        deck = {"Black Lotus": 1}  # Not owned at all

        with pytest.raises(CopyLimitExceededError) as exc_info:
            pool.validate_deck(deck)

        error = exc_info.value
        assert error.card_name == "Black Lotus"
        assert error.available == 0
        assert "not owned" in error.reason


class TestDeckExceedsMaxCopies:
    """
    MANDATORY TEST: No deck exceeds max copies.
    """

    def test_deck_exceeds_max_copies_fails(self) -> None:
        """
        Deck requesting more than max copies raises CopyLimitExceededError.
        """
        pool = OwnedCardPool.from_dict({"Mountain": 20})

        deck = {"Mountain": 5}  # Max is 4

        with pytest.raises(CopyLimitExceededError) as exc_info:
            pool.validate_deck(deck)

        error = exc_info.value
        assert error.card_name == "Mountain"
        assert error.requested == 5
        assert error.available == 4
        assert "max 4 per deck" in error.reason

    def test_deck_at_max_copies_succeeds(self) -> None:
        """
        Deck at exactly max copies succeeds.
        """
        pool = OwnedCardPool.from_dict({"Mountain": 20})

        deck = {"Mountain": 4}  # Exactly at max

        # Should not raise
        pool.validate_deck(deck)


class TestViolationsAreDeterministic:
    """
    MANDATORY TEST: Violations are deterministic failures.
    """

    def test_same_violation_produces_same_error(self) -> None:
        """
        Same violation produces identical error every time.
        """
        pool = OwnedCardPool.from_dict({"Lightning Bolt": 2})
        deck = {"Lightning Bolt": 4}

        errors = []
        for _ in range(3):
            try:
                pool.validate_deck(deck)
            except CopyLimitExceededError as e:
                errors.append((e.card_name, e.requested, e.available, e.reason))

        # All errors are identical
        assert len(errors) == 3
        assert all(e == errors[0] for e in errors)

    def test_error_contains_full_context(self) -> None:
        """
        CopyLimitExceededError contains full context for debugging.
        """
        pool = OwnedCardPool.from_dict({"Lightning Bolt": 2})
        deck = {"Lightning Bolt": 4}

        with pytest.raises(CopyLimitExceededError) as exc_info:
            pool.validate_deck(deck)

        error = exc_info.value
        # All context is present
        assert hasattr(error, "card_name")
        assert hasattr(error, "requested")
        assert hasattr(error, "available")
        assert hasattr(error, "reason")

        # Error message is informative
        message = str(error)
        assert "Lightning Bolt" in message
        assert "4" in message  # Requested
        assert "2" in message  # Available


class TestConsumeCopies:
    """
    Tests for consume_copies() method.
    """

    def test_consume_copies_returns_new_pool(self) -> None:
        """
        consume_copies() returns a new pool with remaining copies.
        """
        pool = OwnedCardPool.from_dict({"Lightning Bolt": 4, "Mountain": 20})
        deck = {"Lightning Bolt": 4, "Mountain": 4}

        remaining = pool.consume_copies(deck)

        # Original unchanged
        assert pool.get_count("Lightning Bolt") == 4
        assert pool.get_count("Mountain") == 20

        # New pool has remaining
        assert remaining.get_count("Lightning Bolt") == 0  # All used
        assert remaining.get_count("Mountain") == 16  # 20 - 4

    def test_consume_copies_validates_first(self) -> None:
        """
        consume_copies() validates before consuming.
        """
        pool = OwnedCardPool.from_dict({"Lightning Bolt": 2})
        deck = {"Lightning Bolt": 4}  # Too many

        with pytest.raises(CopyLimitExceededError):
            pool.consume_copies(deck)

    def test_consume_removes_zero_count_cards(self) -> None:
        """
        Cards reduced to zero are removed from the pool.
        """
        pool = OwnedCardPool.from_dict({"Lightning Bolt": 4})
        deck = {"Lightning Bolt": 4}

        remaining = pool.consume_copies(deck)

        # Card is no longer in pool
        assert "Lightning Bolt" not in remaining
        assert remaining.get_count("Lightning Bolt") == 0
