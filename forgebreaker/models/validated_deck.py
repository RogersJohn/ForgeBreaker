"""
ValidatedDeck — The Single Source of Truth for Card Names in Output.

This module defines the ValidatedDeck type, which represents a deck that has
passed ALL validation stages:
1. AllowedCardSet validation (owned + format-legal)
2. Arena Deck Output Sanitization (Arena-importable)
3. Final structural validation

INVARIANT: No user-visible string may contain a card name unless that name
is present in a ValidatedDeck object.

This is enforced by code, not by convention.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ValidatedDeck:
    """
    An immutable deck whose cards have passed all validation.

    This is the ONLY authoritative source for card names that may appear
    in user-visible output. All formatters, explanation generators, and
    response builders MUST reference cards through this object.

    Attributes:
        cards: Frozen set of validated card names (maindeck + sideboard)
        maindeck: Validated maindeck {card_name: quantity}
        sideboard: Validated sideboard {card_name: quantity}
        name: Deck name (if known)
        format: Format this deck is validated for
        validation_source: Description of validation path taken
    """

    cards: frozenset[str] = field(default_factory=frozenset)
    maindeck: tuple[tuple[str, int], ...] = field(default_factory=tuple)
    sideboard: tuple[tuple[str, int], ...] = field(default_factory=tuple)
    name: str = ""
    format: str = ""
    validation_source: str = ""

    def __contains__(self, card_name: str) -> bool:
        """Check if a card is in this validated deck."""
        return card_name in self.cards

    def __len__(self) -> int:
        """Number of unique cards in this deck."""
        return len(self.cards)

    def get_maindeck_dict(self) -> dict[str, int]:
        """Get maindeck as mutable dict (for compatibility)."""
        return dict(self.maindeck)

    def get_sideboard_dict(self) -> dict[str, int]:
        """Get sideboard as mutable dict (for compatibility)."""
        return dict(self.sideboard)

    def total_cards(self) -> int:
        """Total number of cards (counting quantities)."""
        main_count = sum(qty for _, qty in self.maindeck)
        side_count = sum(qty for _, qty in self.sideboard)
        return main_count + side_count


class DeckValidationError(Exception):
    """
    Raised when deck validation fails.

    This indicates a card was found that should not be in the deck.
    The entire operation should fail — no partial output.
    """

    def __init__(self, card_name: str, reason: str):
        self.card_name = card_name
        self.reason = reason
        super().__init__(f"Deck validation failed for '{card_name}': {reason}")


def create_validated_deck(
    maindeck: dict[str, int],
    sideboard: dict[str, int] | None = None,
    name: str = "",
    format_name: str = "",
    validation_source: str = "direct",
) -> ValidatedDeck:
    """
    Create a ValidatedDeck from validated card dictionaries.

    This function should ONLY be called after all validation has passed.
    It creates an immutable record of the validated cards.

    Args:
        maindeck: Validated maindeck {card_name: quantity}
        sideboard: Validated sideboard {card_name: quantity}
        name: Deck name
        format_name: Format this deck is for
        validation_source: Description of validation path

    Returns:
        Immutable ValidatedDeck object
    """
    sideboard = sideboard or {}

    # Collect all unique card names
    all_cards = frozenset(maindeck.keys()) | frozenset(sideboard.keys())

    return ValidatedDeck(
        cards=all_cards,
        maindeck=tuple(sorted(maindeck.items())),
        sideboard=tuple(sorted(sideboard.items())),
        name=name,
        format=format_name,
        validation_source=validation_source,
    )
