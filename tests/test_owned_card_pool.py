"""
Tests for PR3: Owned Card Pool Builder.

INVARIANT: Only cards with count > 0 may appear in the pool.
Count=0 cards must NEVER leak into deck construction.
"""

import pytest

from forgebreaker.models.canonical_card import CanonicalCard, OwnedCard
from forgebreaker.models.owned_card_pool import OwnedCardPool, build_owned_pool

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
