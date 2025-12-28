"""
Arena Deck Output Sanitizer.

Ensures deck exports are not just Arena-legal but Arena-IMPORTABLE.

This module addresses the gap between:
- Card identity legality (handled by AllowedCardSet)
- Import compatibility (specific printings Arena accepts)

A card can be Arena-legal but have an invalid printing (PLST, MUL, promos).
This sanitizer canonicalizes printings to Arena-accepted versions.

IMPORTANT: This layer is for OUTPUT CORRECTNESS only.
It does NOT modify deck composition or card selection.
"""

from dataclasses import dataclass
from typing import Any

# Set codes that Arena does NOT accept for import
# These are paper-only, promo-only, or special distribution sets
ARENA_INVALID_SETS: frozenset[str] = frozenset(
    {
        # The List (paper-only reprints)
        "plst",
        "plist",
        # Multiverse Legends (paper-only in MOM)
        "mul",
        # Mystery Booster (paper-only)
        "mb1",
        "mb2",
        "fmb1",
        # Secret Lair (mostly paper-only)
        "sld",
        # Promo sets
        "prm",
        "phed",
        "plg20",
        "plg21",
        "plg22",
        "plg23",
        "pmei",
        "pnat",
        # Judge promos
        "j14",
        "j15",
        "j16",
        "j17",
        "j18",
        "j19",
        "j20",
        "j21",
        "j22",
        # World Championship decks (gold-bordered)
        "wc97",
        "wc98",
        "wc99",
        "wc00",
        "wc01",
        "wc02",
        "wc03",
        "wc04",
        # Collectors' Edition (square corners)
        "cei",
        "ced",
        # Other paper-only
        "cmb1",
        "cmb2",
        "30a",  # 30th Anniversary Edition
        # Foreign-only sets
        "rin",
        "ren",
    }
)


@dataclass(frozen=True)
class SanitizedCard:
    """A card with Arena-valid printing information."""

    name: str
    quantity: int
    set_code: str
    collector_number: str


@dataclass(frozen=True)
class SanitizedDeck:
    """A deck with all printings validated for Arena import."""

    cards: tuple[SanitizedCard, ...]
    sideboard: tuple[SanitizedCard, ...]

    def to_arena_format(self) -> str:
        """
        Export to Arena import format.

        Returns:
            String ready for copy/paste into Arena.
        """
        lines = ["Deck"]
        for card in self.cards:
            lines.append(f"{card.quantity} {card.name} ({card.set_code}) {card.collector_number}")

        if self.sideboard:
            lines.append("")
            lines.append("Sideboard")
            for card in self.sideboard:
                lines.append(
                    f"{card.quantity} {card.name} ({card.set_code}) {card.collector_number}"
                )

        return "\n".join(lines)


class ArenaSanitizationError(Exception):
    """
    Raised when a deck cannot be sanitized for Arena import.

    This is a HARD FAILURE - we do not partially sanitize or drop cards.
    The entire deck output is rejected with a clear explanation.
    """

    def __init__(
        self,
        card_name: str,
        invalid_set: str,
        reason: str,
    ) -> None:
        self.card_name = card_name
        self.invalid_set = invalid_set
        self.reason = reason
        super().__init__(f"Cannot sanitize '{card_name}' (set: {invalid_set}): {reason}")


def is_arena_valid_printing(set_code: str, card_data: dict[str, Any]) -> bool:
    """
    Check if a specific printing is valid for Arena import.

    Args:
        set_code: The set code to check
        card_data: Scryfall card data for the card

    Returns:
        True if this printing can be imported into Arena
    """
    # Check against known invalid sets
    if set_code.lower() in ARENA_INVALID_SETS:
        return False

    # Check if this card exists in Arena (via Scryfall's games field)
    games = card_data.get("games", [])
    return "arena" in games


def find_arena_valid_printing(
    card_name: str,
    card_db: dict[str, dict[str, Any]],
    preferred_set: str | None = None,
) -> tuple[str, str] | None:
    """
    Find an Arena-valid printing for a card.

    Args:
        card_name: Name of the card
        card_db: Full card database (keyed by name, but we need all printings)
        preferred_set: Prefer this set if it's valid

    Returns:
        Tuple of (set_code, collector_number) or None if no valid printing exists
    """
    card_data = card_db.get(card_name)
    if not card_data:
        return None

    # Check if the card's current printing is valid
    current_set = card_data.get("set", "").upper()
    if (
        preferred_set
        and preferred_set.lower() == current_set.lower()
        and is_arena_valid_printing(current_set, card_data)
    ):
        return (current_set, card_data.get("collector_number", "1"))

    # The card database is indexed by name with only one printing per card
    # Check if that printing is valid
    if is_arena_valid_printing(current_set, card_data):
        return (current_set, card_data.get("collector_number", "1"))

    # No valid printing found in our database
    # This means we need to look for alternative printings
    # For now, return None and let the caller handle it
    return None


def get_canonical_arena_printing(
    card_name: str,
    original_set: str,
    card_db: dict[str, dict[str, Any]],
) -> tuple[str, str]:
    """
    Get the canonical Arena-valid printing for a card.

    If the original set is invalid, finds a valid alternative.
    If no valid printing exists, raises ArenaSanitizationError.

    Args:
        card_name: Name of the card
        original_set: The set code from the original deck/database
        card_db: Card database

    Returns:
        Tuple of (set_code, collector_number)

    Raises:
        ArenaSanitizationError: If no valid printing can be found
    """
    card_data = card_db.get(card_name)
    if not card_data:
        raise ArenaSanitizationError(
            card_name=card_name,
            invalid_set=original_set,
            reason="Card not found in database",
        )

    # First, check if the original set is valid
    if is_arena_valid_printing(original_set, card_data):
        return (original_set.upper(), card_data.get("collector_number", "1"))

    # Original set is invalid - try to find a valid alternative
    result = find_arena_valid_printing(card_name, card_db)
    if result:
        return result

    # No valid printing found
    raise ArenaSanitizationError(
        card_name=card_name,
        invalid_set=original_set,
        reason=(
            f"Set '{original_set}' is not valid for Arena import and "
            "no alternative Arena-valid printing was found"
        ),
    )


def sanitize_deck_for_arena(
    cards: dict[str, int],
    card_db: dict[str, dict[str, Any]],
    sideboard: dict[str, int] | None = None,
) -> SanitizedDeck:
    """
    Sanitize a deck for Arena import.

    Ensures all card printings are Arena-valid.
    Does NOT modify deck composition - only corrects printings.

    This function must be called AFTER AllowedCardSet validation,
    BEFORE returning deck output to the user.

    Args:
        cards: Maindeck cards {name: quantity}
        card_db: Card database with printing information
        sideboard: Optional sideboard cards {name: quantity}

    Returns:
        SanitizedDeck ready for Arena export

    Raises:
        ArenaSanitizationError: If ANY card cannot be sanitized.
            The entire deck is rejected - no partial sanitization.
    """
    sanitized_cards: list[SanitizedCard] = []

    for card_name, quantity in sorted(cards.items()):
        card_data = card_db.get(card_name, {})
        original_set = card_data.get("set", "unknown")

        # Get canonical Arena-valid printing (raises if impossible)
        set_code, collector_number = get_canonical_arena_printing(card_name, original_set, card_db)

        sanitized_cards.append(
            SanitizedCard(
                name=card_name,
                quantity=quantity,
                set_code=set_code,
                collector_number=collector_number,
            )
        )

    sanitized_sideboard: list[SanitizedCard] = []
    if sideboard:
        for card_name, quantity in sorted(sideboard.items()):
            card_data = card_db.get(card_name, {})
            original_set = card_data.get("set", "unknown")

            set_code, collector_number = get_canonical_arena_printing(
                card_name, original_set, card_db
            )

            sanitized_sideboard.append(
                SanitizedCard(
                    name=card_name,
                    quantity=quantity,
                    set_code=set_code,
                    collector_number=collector_number,
                )
            )

    return SanitizedDeck(
        cards=tuple(sanitized_cards),
        sideboard=tuple(sanitized_sideboard),
    )


def validate_arena_importability(
    arena_export: str,
    card_db: dict[str, dict[str, Any]],
) -> list[str]:
    """
    Validate that an Arena export string is fully importable.

    This is a post-sanitization check to ensure the output is correct.

    Args:
        arena_export: The Arena format string
        card_db: Card database

    Returns:
        List of validation errors (empty if valid)
    """
    import re

    errors: list[str] = []

    # Pattern to match Arena format lines: "4 Card Name (SET) 123"
    pattern = re.compile(r"^(\d+)\s+(.+?)\s+\(([A-Z0-9]+)\)\s+(\S+)$")

    for line in arena_export.split("\n"):
        line = line.strip()

        # Skip section headers and empty lines
        if not line or line.lower() in {"deck", "sideboard", "commander", "companion"}:
            continue

        match = pattern.match(line)
        if not match:
            errors.append(f"Malformed line: {line}")
            continue

        _quantity, card_name, set_code, _collector_num = match.groups()

        # Check if set is known invalid
        if set_code.lower() in ARENA_INVALID_SETS:
            errors.append(
                f"Invalid set '{set_code}' for '{card_name}' - Arena will not accept this import"
            )

        # Check if card exists in database
        card_data = card_db.get(card_name)
        if card_data:
            games = card_data.get("games", [])
            if "arena" not in games:
                errors.append(f"Card '{card_name}' is not available on Arena")

    return errors
