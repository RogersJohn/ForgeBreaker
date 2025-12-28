"""
Arena Deck Output Sanitizer.

SECURITY INVARIANTS (Non-Negotiable):
1. All input is treated as UNTRUSTED
2. Invalid input causes HARD FAILURE (exceptions)
3. No silent cleanup, no "best effort" recovery
4. No guessing user intent

This sanitizer validates and normalizes deck output for Arena import.
It enforces strict constraints on:
- Card name format (no empty, no control chars, bounded length)
- Quantity bounds (positive integers within sane limits)
- Set code format (alphanumeric, bounded length)
- Collector number format (alphanumeric, bounded length)
- Deck structure (valid sections only)

If ANY validation fails, the ENTIRE deck is rejected.
"""

import re
from dataclasses import dataclass
from typing import Any

# =============================================================================
# VALIDATION CONSTANTS
# =============================================================================

# Maximum card name length (longest real MTG card name is ~50 chars)
MAX_CARD_NAME_LENGTH = 150

# Maximum quantity per card entry (4 for most cards, but basics can be higher)
MAX_CARD_QUANTITY = 250

# Minimum quantity (must be positive)
MIN_CARD_QUANTITY = 1

# Maximum set code length (standard is 3-4, but some are longer)
MAX_SET_CODE_LENGTH = 10

# Maximum collector number length
MAX_COLLECTOR_NUMBER_LENGTH = 10

# Valid Arena section headers (lowercase for comparison)
VALID_ARENA_SECTIONS: frozenset[str] = frozenset(
    {
        "deck",
        "sideboard",
        "commander",
        "companion",
    }
)

# Pattern for valid card names: printable ASCII, no control characters
# Allows letters, numbers, spaces, apostrophes, commas, hyphens, slashes
VALID_CARD_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9 ',\-/]+$")

# Pattern for valid set codes: uppercase alphanumeric
VALID_SET_CODE_PATTERN = re.compile(r"^[A-Z0-9]+$")

# Pattern for valid collector numbers: alphanumeric with optional suffix
VALID_COLLECTOR_NUMBER_PATTERN = re.compile(r"^[a-zA-Z0-9]+$")

# Set codes that Arena does NOT accept for import
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


# =============================================================================
# EXCEPTION HIERARCHY
# =============================================================================


class ArenaSanitizationError(Exception):
    """
    Base exception for all sanitization failures.

    This is a HARD FAILURE - we do not partially sanitize or drop cards.
    The entire deck output is rejected with a clear explanation.
    """

    pass


class InvalidCardNameError(ArenaSanitizationError):
    """Raised when a card name fails validation."""

    def __init__(self, card_name: str, reason: str) -> None:
        self.card_name = card_name
        self.reason = reason
        # Truncate for safety in error message
        safe_name = repr(card_name[:50]) if len(card_name) > 50 else repr(card_name)
        super().__init__(f"Invalid card name {safe_name}: {reason}")


class InvalidQuantityError(ArenaSanitizationError):
    """Raised when a quantity fails validation."""

    def __init__(self, card_name: str, quantity: int, reason: str) -> None:
        self.card_name = card_name
        self.quantity = quantity
        self.reason = reason
        super().__init__(f"Invalid quantity {quantity} for '{card_name}': {reason}")


class InvalidSetCodeError(ArenaSanitizationError):
    """Raised when a set code fails validation."""

    def __init__(self, card_name: str, set_code: str, reason: str) -> None:
        self.card_name = card_name
        self.set_code = set_code
        self.reason = reason
        safe_code = repr(set_code[:20]) if len(set_code) > 20 else repr(set_code)
        super().__init__(f"Invalid set code {safe_code} for '{card_name}': {reason}")


class InvalidCollectorNumberError(ArenaSanitizationError):
    """Raised when a collector number fails validation."""

    def __init__(self, card_name: str, collector_number: str, reason: str) -> None:
        self.card_name = card_name
        self.collector_number = collector_number
        self.reason = reason
        super().__init__(
            f"Invalid collector number '{collector_number}' for '{card_name}': {reason}"
        )


class InvalidDeckStructureError(ArenaSanitizationError):
    """Raised when deck structure is invalid."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"Invalid deck structure: {reason}")


class ArenaImportabilityError(ArenaSanitizationError):
    """Raised when a card printing is not importable to Arena."""

    def __init__(self, card_name: str, set_code: str, reason: str) -> None:
        self.card_name = card_name
        self.set_code = set_code
        self.reason = reason
        super().__init__(f"Cannot import '{card_name}' (set: {set_code}) to Arena: {reason}")


# =============================================================================
# VALIDATION FUNCTIONS
# =============================================================================


def validate_card_name(name: str) -> None:
    """
    Validate a card name is safe and well-formed.

    Raises:
        InvalidCardNameError: If the name is invalid
    """
    # Check for empty or whitespace-only
    if not name:
        raise InvalidCardNameError(name, "Card name cannot be empty")

    if not name.strip():
        raise InvalidCardNameError(name, "Card name cannot be whitespace-only")

    # Check length bounds
    if len(name) > MAX_CARD_NAME_LENGTH:
        raise InvalidCardNameError(
            name, f"Card name exceeds maximum length of {MAX_CARD_NAME_LENGTH}"
        )

    # Check for control characters (ASCII 0-31, 127)
    for char in name:
        if ord(char) < 32 or ord(char) == 127:
            raise InvalidCardNameError(
                name, f"Card name contains control character (ord={ord(char)})"
            )

    # Check against allowed pattern
    if not VALID_CARD_NAME_PATTERN.match(name):
        raise InvalidCardNameError(
            name,
            "Card name contains invalid characters. "
            "Only letters, numbers, spaces, apostrophes, commas, hyphens, and slashes allowed.",
        )


def validate_quantity(card_name: str, quantity: int) -> None:
    """
    Validate a card quantity is within acceptable bounds.

    Raises:
        InvalidQuantityError: If the quantity is invalid
    """
    if not isinstance(quantity, int):
        raise InvalidQuantityError(
            card_name, quantity, f"Quantity must be an integer, got {type(quantity).__name__}"
        )

    if quantity < MIN_CARD_QUANTITY:
        raise InvalidQuantityError(
            card_name, quantity, f"Quantity must be at least {MIN_CARD_QUANTITY}"
        )

    if quantity > MAX_CARD_QUANTITY:
        raise InvalidQuantityError(
            card_name, quantity, f"Quantity exceeds maximum of {MAX_CARD_QUANTITY}"
        )


def validate_set_code(card_name: str, set_code: str) -> None:
    """
    Validate a set code is well-formed.

    Raises:
        InvalidSetCodeError: If the set code is invalid
    """
    if not set_code:
        raise InvalidSetCodeError(card_name, set_code, "Set code cannot be empty")

    if len(set_code) > MAX_SET_CODE_LENGTH:
        raise InvalidSetCodeError(
            card_name, set_code, f"Set code exceeds maximum length of {MAX_SET_CODE_LENGTH}"
        )

    if not VALID_SET_CODE_PATTERN.match(set_code):
        raise InvalidSetCodeError(card_name, set_code, "Set code must be uppercase alphanumeric")


def validate_collector_number(card_name: str, collector_number: str) -> None:
    """
    Validate a collector number is well-formed.

    Raises:
        InvalidCollectorNumberError: If the collector number is invalid
    """
    if not collector_number:
        raise InvalidCollectorNumberError(
            card_name, collector_number, "Collector number cannot be empty"
        )

    if len(collector_number) > MAX_COLLECTOR_NUMBER_LENGTH:
        raise InvalidCollectorNumberError(
            card_name,
            collector_number,
            f"Collector number exceeds maximum length of {MAX_COLLECTOR_NUMBER_LENGTH}",
        )

    if not VALID_COLLECTOR_NUMBER_PATTERN.match(collector_number):
        raise InvalidCollectorNumberError(
            card_name, collector_number, "Collector number must be alphanumeric"
        )


def validate_deck_input(cards: dict[str, int], sideboard: dict[str, int] | None) -> None:
    """
    Validate the structure of deck input.

    Raises:
        InvalidDeckStructureError: If the deck structure is invalid
    """
    if cards is None:
        raise InvalidDeckStructureError("Maindeck cards cannot be None")

    if not isinstance(cards, dict):
        raise InvalidDeckStructureError(f"Maindeck must be a dict, got {type(cards).__name__}")

    if sideboard is not None and not isinstance(sideboard, dict):
        raise InvalidDeckStructureError(
            f"Sideboard must be a dict or None, got {type(sideboard).__name__}"
        )

    # Validate all entries in maindeck
    for card_name, quantity in cards.items():
        validate_card_name(card_name)
        validate_quantity(card_name, quantity)

    # Validate all entries in sideboard
    if sideboard:
        for card_name, quantity in sideboard.items():
            validate_card_name(card_name)
            validate_quantity(card_name, quantity)


# =============================================================================
# DATA CLASSES
# =============================================================================


@dataclass(frozen=True)
class SanitizedCard:
    """
    A card with validated, Arena-safe printing information.

    All fields have been validated before construction.
    """

    name: str
    quantity: int
    set_code: str
    collector_number: str


@dataclass(frozen=True)
class SanitizedDeck:
    """
    A deck with all cards validated for Arena import.

    Construction of this object implies all validation has passed.
    """

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


# =============================================================================
# PRINTING VALIDATION
# =============================================================================


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


def get_canonical_arena_printing(
    card_name: str,
    original_set: str,
    card_db: dict[str, dict[str, Any]],
) -> tuple[str, str]:
    """
    Get the canonical Arena-valid printing for a card.

    If the original set is invalid, attempts to find a valid alternative.
    If no valid printing exists, raises ArenaImportabilityError.

    Args:
        card_name: Name of the card (must be pre-validated)
        original_set: The set code from the original deck/database
        card_db: Card database

    Returns:
        Tuple of (set_code, collector_number)

    Raises:
        ArenaImportabilityError: If no valid printing can be found
    """
    card_data = card_db.get(card_name)
    if not card_data:
        raise ArenaImportabilityError(
            card_name=card_name,
            set_code=original_set,
            reason="Card not found in database",
        )

    # First, check if the original set is valid
    if is_arena_valid_printing(original_set, card_data):
        set_code = original_set.upper()
        collector_number = str(card_data.get("collector_number", "1"))

        # Validate the output
        validate_set_code(card_name, set_code)
        validate_collector_number(card_name, collector_number)

        return (set_code, collector_number)

    # Original set is invalid - check if the database printing is valid
    db_set = card_data.get("set", "").upper()
    if db_set and is_arena_valid_printing(db_set, card_data):
        collector_number = str(card_data.get("collector_number", "1"))

        # Validate the output
        validate_set_code(card_name, db_set)
        validate_collector_number(card_name, collector_number)

        return (db_set, collector_number)

    # No valid printing found
    raise ArenaImportabilityError(
        card_name=card_name,
        set_code=original_set,
        reason=(
            f"Set '{original_set}' is not valid for Arena import and "
            "no alternative Arena-valid printing was found"
        ),
    )


# =============================================================================
# MAIN SANITIZATION FUNCTION
# =============================================================================


def sanitize_deck_for_arena(
    cards: dict[str, int],
    card_db: dict[str, dict[str, Any]],
    sideboard: dict[str, int] | None = None,
) -> SanitizedDeck:
    """
    Sanitize a deck for Arena import.

    This function:
    1. Validates ALL input (names, quantities, structure)
    2. Ensures all card printings are Arena-valid
    3. Returns a SanitizedDeck ready for export

    FAIL-CLOSED: If ANY validation fails, the entire deck is rejected.
    No partial sanitization. No silent fixes. No guessing.

    Args:
        cards: Maindeck cards {name: quantity}
        card_db: Card database with printing information
        sideboard: Optional sideboard cards {name: quantity}

    Returns:
        SanitizedDeck ready for Arena export

    Raises:
        InvalidDeckStructureError: If deck structure is invalid
        InvalidCardNameError: If any card name is invalid
        InvalidQuantityError: If any quantity is invalid
        ArenaImportabilityError: If any card cannot be imported to Arena
    """
    # Step 1: Validate deck structure and all input
    validate_deck_input(cards, sideboard)

    # Step 2: Process maindeck
    sanitized_cards: list[SanitizedCard] = []

    for card_name, quantity in sorted(cards.items()):
        card_data = card_db.get(card_name, {})
        original_set = card_data.get("set", "UNKNOWN")

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

    # Step 3: Process sideboard
    sanitized_sideboard: list[SanitizedCard] = []
    if sideboard:
        for card_name, quantity in sorted(sideboard.items()):
            card_data = card_db.get(card_name, {})
            original_set = card_data.get("set", "UNKNOWN")

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


# =============================================================================
# OUTPUT VALIDATION (FAIL-CLOSED)
# =============================================================================


def validate_arena_export(
    arena_export: str,
    card_db: dict[str, dict[str, Any]],
) -> None:
    """
    Validate that an Arena export string is fully importable.

    This is a POST-SANITIZATION check that throws on ANY error.
    It does NOT return errors - it raises exceptions.

    Args:
        arena_export: The Arena format string
        card_db: Card database

    Raises:
        InvalidDeckStructureError: If structure is invalid
        InvalidCardNameError: If any card name is invalid
        InvalidQuantityError: If any quantity is invalid
        InvalidSetCodeError: If any set code is invalid
        ArenaImportabilityError: If any card is not Arena-importable
    """
    # Pattern to match Arena format lines: "4 Card Name (SET) 123"
    line_pattern = re.compile(r"^(\d+)\s+(.+?)\s+\(([A-Z0-9]+)\)\s+(\S+)$")

    if not arena_export or not arena_export.strip():
        raise InvalidDeckStructureError("Export is empty")

    lines = arena_export.split("\n")

    has_deck_section = False

    for line_num, line in enumerate(lines, 1):
        line = line.strip()

        # Skip empty lines
        if not line:
            continue

        # Check for section headers
        if line.lower() in VALID_ARENA_SECTIONS:
            if line.lower() == "deck":
                has_deck_section = True
            continue

        # Check for unknown section headers (potential injection)
        is_potential_header = line.endswith(":") or (len(line.split()) == 1 and line[0].isupper())
        if is_potential_header and line.lower() not in VALID_ARENA_SECTIONS:
            raise InvalidDeckStructureError(
                f"Unknown section header at line {line_num}: {repr(line)}"
            )

        # Parse card line
        match = line_pattern.match(line)
        if not match:
            raise InvalidDeckStructureError(
                f"Malformed card line at line {line_num}: {repr(line[:50])}"
            )

        quantity_str, card_name, set_code, collector_num = match.groups()

        # Validate quantity
        try:
            quantity = int(quantity_str)
        except ValueError as e:
            raise InvalidQuantityError(
                card_name, 0, f"Cannot parse quantity: {quantity_str}"
            ) from e

        validate_quantity(card_name, quantity)

        # Validate card name
        validate_card_name(card_name)

        # Validate set code
        validate_set_code(card_name, set_code)

        # Validate collector number
        validate_collector_number(card_name, collector_num)

        # Check if set is known invalid
        if set_code.lower() in ARENA_INVALID_SETS:
            raise ArenaImportabilityError(
                card_name, set_code, f"Set '{set_code}' is not valid for Arena import"
            )

        # Check if card exists in database and is Arena-available
        card_data = card_db.get(card_name)
        if card_data:
            games = card_data.get("games", [])
            if "arena" not in games:
                raise ArenaImportabilityError(card_name, set_code, "Card is not available on Arena")

    if not has_deck_section:
        raise InvalidDeckStructureError("Export missing required 'Deck' section")
