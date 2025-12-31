"""
Owned Card Pool - count-aware pool for deck construction.

INVARIANT: Only cards with count > 0 may appear in the pool.
This eliminates the Count == 0 vs Count > 0 ambiguity globally.

INVARIANT: No deck may exceed:
  - owned count
  - max copy limit (default 4)
"""

from collections.abc import Iterator
from dataclasses import dataclass, field

from forgebreaker.models.canonical_card import CanonicalCard, OwnedCard

# Default max copies per card in constructed formats
DEFAULT_MAX_COPIES = 4


class CopyLimitExceededError(Exception):
    """Raised when a deck would exceed copy limits."""

    def __init__(self, card_name: str, requested: int, available: int, reason: str) -> None:
        self.card_name = card_name
        self.requested = requested
        self.available = available
        self.reason = reason
        super().__init__(
            f"Cannot use {requested} copies of '{card_name}': only {available} available ({reason})"
        )


@dataclass(frozen=True, slots=True)
class OwnedCardPool:
    """
    Immutable pool of owned cards with enforced count > 0 invariant.

    INVARIANT: Every card in the pool has count >= 1.
    Zero-count cards are rejected at construction time.

    INVARIANT: available_copies() enforces both ownership and max copy limits.

    Usage:
        pool = OwnedCardPool.from_owned_cards(owned_cards)
        for name, count in pool.items():
            # count is guaranteed > 0
            ...

    The pool provides:
        - Iteration over (name, count) pairs
        - Quantity lookup by card name
        - Membership testing
        - Subset extraction for deck construction
        - Copy limit enforcement
    """

    _cards: dict[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate all counts are positive."""
        for name, count in self._cards.items():
            if count <= 0:
                raise ValueError(f"Card '{name}' has invalid count {count} (must be > 0)")

    @classmethod
    def from_owned_cards(cls, owned_cards: list[OwnedCard]) -> "OwnedCardPool":
        """
        Build pool from canonical OwnedCard list.

        Filters out any cards with count <= 0 (should not exist,
        but defensive against upstream bugs).
        """
        cards = {}
        for owned in owned_cards:
            if owned.count > 0:
                cards[owned.card.name] = owned.count
            # Silently skip count <= 0 (defensive)
        return cls(_cards=cards)

    @classmethod
    def from_dict(cls, cards: dict[str, int]) -> "OwnedCardPool":
        """
        Build pool from card name -> count dict.

        Filters out any cards with count <= 0.
        """
        filtered = {name: count for name, count in cards.items() if count > 0}
        return cls(_cards=filtered)

    def __contains__(self, card_name: str) -> bool:
        """Check if card is in pool (with count > 0)."""
        return card_name in self._cards

    def __len__(self) -> int:
        """Number of unique cards in pool."""
        return len(self._cards)

    def __iter__(self) -> Iterator[str]:
        """Iterate over card names."""
        return iter(self._cards)

    def items(self) -> Iterator[tuple[str, int]]:
        """Iterate over (name, count) pairs."""
        return iter(self._cards.items())

    def get_count(self, card_name: str) -> int:
        """
        Get owned count for a card.

        Returns 0 if card not in pool (never owned or count was 0).
        """
        return self._cards.get(card_name, 0)

    def available_copies(
        self,
        card: CanonicalCard,
        max_copies: int = DEFAULT_MAX_COPIES,
    ) -> int:
        """
        Get available copies of a card for deck construction.

        INVARIANT: Returns min(owned_count, max_copies).
        This enforces both ownership limits AND deck construction rules.

        Args:
            card: The canonical card to check
            max_copies: Maximum copies allowed per deck (default 4)

        Returns:
            Number of copies available (0 if not owned)
        """
        owned = self._cards.get(card.name, 0)
        return min(owned, max_copies)

    def get_max_copies(self, card_name: str, limit: int = DEFAULT_MAX_COPIES) -> int:
        """
        Get maximum usable copies of a card.

        Args:
            card_name: Name of the card
            limit: Maximum copies allowed (default 4 for constructed)

        Returns:
            min(owned_count, limit), or 0 if not owned
        """
        return min(self._cards.get(card_name, 0), limit)

    def validate_deck(
        self,
        deck: dict[str, int],
        max_copies: int = DEFAULT_MAX_COPIES,
    ) -> None:
        """
        Validate a deck against ownership and copy limits.

        INVARIANT: No deck may exceed:
          - owned count for any card
          - max copies per card

        Args:
            deck: Card name -> count mapping for the deck
            max_copies: Maximum copies allowed per card (default 4)

        Raises:
            CopyLimitExceededError: If any card exceeds limits
        """
        for card_name, requested in deck.items():
            owned = self._cards.get(card_name, 0)
            limit = min(owned, max_copies)

            if requested > limit:
                if owned == 0:
                    reason = "not owned"
                elif owned < max_copies:
                    reason = f"only {owned} owned"
                else:
                    reason = f"max {max_copies} per deck"
                raise CopyLimitExceededError(
                    card_name=card_name,
                    requested=requested,
                    available=limit,
                    reason=reason,
                )

    def consume_copies(
        self,
        deck: dict[str, int],
        max_copies: int = DEFAULT_MAX_COPIES,
    ) -> "OwnedCardPool":
        """
        Create a new pool with copies consumed by a deck.

        INVARIANT: Validates deck before consuming.

        Args:
            deck: Card name -> count mapping for the deck
            max_copies: Maximum copies allowed per card (default 4)

        Returns:
            New OwnedCardPool with remaining copies

        Raises:
            CopyLimitExceededError: If any card exceeds limits
        """
        # Validate first
        self.validate_deck(deck, max_copies)

        # Create new pool with consumed copies
        remaining = dict(self._cards)
        for card_name, consumed in deck.items():
            remaining[card_name] = remaining.get(card_name, 0) - consumed

        # Filter out zero counts
        return OwnedCardPool.from_dict(remaining)

    def total_cards(self) -> int:
        """Total cards across all copies."""
        return sum(self._cards.values())

    def unique_cards(self) -> int:
        """Number of unique cards (same as __len__)."""
        return len(self._cards)

    def filter_by_names(self, allowed_names: set[str]) -> "OwnedCardPool":
        """
        Create new pool with only cards in allowed_names.

        Preserves counts for matching cards.
        """
        filtered = {name: count for name, count in self._cards.items() if name in allowed_names}
        return OwnedCardPool(_cards=filtered)

    def to_dict(self) -> dict[str, int]:
        """Export as dict (for compatibility with existing code)."""
        return dict(self._cards)


def build_owned_pool(
    owned_cards: list[OwnedCard],
    legal_cards: set[str] | None = None,
) -> OwnedCardPool:
    """
    Build an OwnedCardPool from canonical cards.

    Args:
        owned_cards: List of OwnedCard from canonical resolution
        legal_cards: Optional set of format-legal card names for filtering

    Returns:
        OwnedCardPool with only count > 0 cards, optionally filtered by legality
    """
    pool = OwnedCardPool.from_owned_cards(owned_cards)

    if legal_cards is not None:
        pool = pool.filter_by_names(legal_cards)

    return pool
