"""
Allowed Card Set — Hard Boundary for Card Suggestions.

This module enforces ForgeBreaker's core invariant:

    Deck construction is selection from an authoritative set,
    never free-form generation.

The AllowedCardSet represents the intersection of:
1. Cards the player actually owns (from their collection)
2. Cards legal in the target format (from Scryfall legality data)

Any card suggestion that falls outside this set is a trust violation.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class AllowedCardSet:
    """
    An immutable set of cards that may be suggested to a player.

    This is the ONLY valid universe for card selection.
    Cards not in this set must never be suggested silently.

    Attributes:
        cards: Mapping of card name to owned quantity (only legal cards)
        format: The format this set is valid for
        source: Description of how this set was constructed
    """

    cards: dict[str, int] = field(default_factory=dict)
    format: str = ""
    source: str = ""

    def __contains__(self, card_name: str) -> bool:
        """Check if a card is in the allowed set."""
        return card_name in self.cards

    def __len__(self) -> int:
        """Number of unique cards in the allowed set."""
        return len(self.cards)

    def get_quantity(self, card_name: str) -> int:
        """Get owned quantity of a card, or 0 if not allowed."""
        return self.cards.get(card_name, 0)

    def is_empty(self) -> bool:
        """Check if the allowed set is empty."""
        return len(self.cards) == 0


class CardNotAllowedError(Exception):
    """
    Raised when a card suggestion violates the allowed set boundary.

    This is a trust violation — the system attempted to suggest
    a card that the player does not own or that is not legal.
    """

    def __init__(self, card_name: str, reason: str, allowed_set: AllowedCardSet):
        self.card_name = card_name
        self.reason = reason
        self.allowed_set = allowed_set
        super().__init__(
            f"Card '{card_name}' is not allowed: {reason}. "
            f"Format: {allowed_set.format}. "
            f"Allowed set contains {len(allowed_set)} cards."
        )


def build_allowed_set(
    collection_cards: dict[str, int],
    format_legal_cards: set[str],
    format_name: str,
) -> AllowedCardSet:
    """
    Build an AllowedCardSet from collection and format legality.

    This is the ONLY way to construct a valid allowed set.
    The result is the intersection of owned cards and legal cards.

    Args:
        collection_cards: Player's collection {card_name: quantity}
        format_legal_cards: Set of cards legal in the target format
        format_name: Name of the format (e.g., "standard", "historic")

    Returns:
        AllowedCardSet containing only cards that are both owned AND legal
    """
    allowed: dict[str, int] = {}

    for card_name, quantity in collection_cards.items():
        if card_name in format_legal_cards:
            allowed[card_name] = quantity

    return AllowedCardSet(
        cards=allowed,
        format=format_name,
        source=f"Intersection of {len(collection_cards)} owned cards "
        f"and {len(format_legal_cards)} {format_name}-legal cards",
    )


def validate_card_in_allowed_set(
    card_name: str,
    allowed_set: AllowedCardSet,
    required_quantity: int = 1,
) -> None:
    """
    Validate that a card is in the allowed set with sufficient quantity.

    This function MUST be called before suggesting any card.
    Violations raise CardNotAllowedError — they do not fail silently.

    Args:
        card_name: The card to validate
        allowed_set: The authoritative allowed set
        required_quantity: Minimum quantity needed (default 1)

    Raises:
        CardNotAllowedError: If card is not allowed or quantity insufficient
    """
    if card_name not in allowed_set:
        raise CardNotAllowedError(
            card_name=card_name,
            reason="not in player's collection or not legal in format",
            allowed_set=allowed_set,
        )

    owned = allowed_set.get_quantity(card_name)
    if owned < required_quantity:
        raise CardNotAllowedError(
            card_name=card_name,
            reason=f"owned quantity ({owned}) less than required ({required_quantity})",
            allowed_set=allowed_set,
        )


def validate_card_list(
    cards: dict[str, int],
    allowed_set: AllowedCardSet,
) -> list[str]:
    """
    Validate a list of cards against the allowed set.

    Returns list of violation messages. Empty list means all valid.
    Use this for batch validation where you want to collect all errors.

    Args:
        cards: Cards to validate {name: quantity}
        allowed_set: The authoritative allowed set

    Returns:
        List of violation messages (empty if all valid)
    """
    violations: list[str] = []

    for card_name, required_qty in cards.items():
        if card_name not in allowed_set:
            violations.append(f"'{card_name}' is not in allowed set for {allowed_set.format}")
        elif allowed_set.get_quantity(card_name) < required_qty:
            owned = allowed_set.get_quantity(card_name)
            violations.append(
                f"'{card_name}' requires {required_qty} copies but only {owned} owned"
            )

    return violations
