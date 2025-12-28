"""
Arena Deck Sanitizer.

THIS MODULE IS THE TRUST BOUNDARY FOR ARENA DECK TEXT.

=============================================================================
SECURITY INVARIANTS (Non-Negotiable)
=============================================================================

1. All input is HOSTILE by default
2. Invalid input causes HARD FAILURE (exceptions)
3. No silent cleanup, no "best effort" recovery
4. No guessing user intent
5. If input violates invariants, the system REFUSES to proceed

=============================================================================
ARCHITECTURE
=============================================================================

ArenaDeckSanitizer is THE sanitizer. All raw Arena deck text must pass
through sanitize_arena_deck_input() before being used anywhere in the system.

The sanitization pipeline is:

    Raw Text (UNTRUSTED)
         │
         ▼
    ┌─────────────────────────────────────────┐
    │  ArenaDeckSanitizer.sanitize()          │
    │  ─────────────────────────────────      │
    │  1. Validate raw input (pre-parse)      │
    │  2. Parse to intermediate structure     │  ◄── PARSING (separate)
    │  3. Sanitize parsed structure           │  ◄── SANITIZATION (separate)
    │  4. Build immutable output              │
    └─────────────────────────────────────────┘
         │
         ▼
    SanitizedDeck (TRUSTED)

PARSING is NOT sanitization. Parsing extracts structure.
SANITIZATION validates and rejects invalid input.

These are SEPARATE concerns with SEPARATE code paths.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

# =============================================================================
# VALIDATION CONSTANTS
# =============================================================================

# Maximum raw input length (prevent DoS via huge input)
MAX_RAW_INPUT_LENGTH = 100_000

# Maximum card name length (longest real MTG card name is ~50 chars)
MAX_CARD_NAME_LENGTH = 150

# Maximum quantity per card entry
MAX_CARD_QUANTITY = 250

# Minimum quantity (must be positive)
MIN_CARD_QUANTITY = 1

# Maximum set code length
MAX_SET_CODE_LENGTH = 10

# Maximum collector number length
MAX_COLLECTOR_NUMBER_LENGTH = 10

# Maximum number of cards in a deck (prevent abuse)
MAX_DECK_ENTRIES = 500

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
VALID_CARD_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9 ',\-/]+$")

# Pattern for valid set codes: uppercase alphanumeric
VALID_SET_CODE_PATTERN = re.compile(r"^[A-Z0-9]+$")

# Pattern for valid collector numbers: alphanumeric
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
        "30a",
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

    This is a HARD FAILURE - the entire operation is rejected.
    No partial results. No recovery. No guessing.
    """

    pass


class InvalidRawInputError(ArenaSanitizationError):
    """Raised when raw input fails pre-parse validation."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"Invalid raw input: {reason}")


class InvalidCardNameError(ArenaSanitizationError):
    """Raised when a card name fails validation."""

    def __init__(self, card_name: str, reason: str) -> None:
        self.card_name = card_name
        self.reason = reason
        safe_name = repr(card_name[:50]) if len(card_name) > 50 else repr(card_name)
        super().__init__(f"Invalid card name {safe_name}: {reason}")


class InvalidQuantityError(ArenaSanitizationError):
    """Raised when a quantity fails validation."""

    def __init__(self, card_name: str, quantity: int | str, reason: str) -> None:
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
# INTERMEDIATE PARSED STRUCTURE (NOT YET SANITIZED)
# =============================================================================


@dataclass
class ParsedCardEntry:
    """
    A card entry extracted from parsing. NOT YET SANITIZED.

    This is an intermediate structure. Do not use outside the sanitizer.
    """

    quantity_str: str  # Raw string, not yet validated as int
    card_name: str  # Raw string, not yet validated
    set_code: str | None  # May be None if format doesn't include it
    collector_number: str | None  # May be None if format doesn't include it
    line_number: int  # For error reporting


@dataclass
class ParsedDeckStructure:
    """
    Parsed deck structure. NOT YET SANITIZED.

    This is an intermediate structure. Do not use outside the sanitizer.
    """

    deck_entries: list[ParsedCardEntry]
    sideboard_entries: list[ParsedCardEntry]
    has_deck_section: bool


# =============================================================================
# SANITIZED OUTPUT STRUCTURES (TRUSTED)
# =============================================================================


@dataclass(frozen=True)
class SanitizedCard:
    """
    A card with validated, Arena-safe information.

    Construction of this object implies ALL validation has passed.
    This is an IMMUTABLE, TRUSTED data structure.
    """

    name: str
    quantity: int
    set_code: str
    collector_number: str


@dataclass(frozen=True)
class SanitizedDeck:
    """
    A deck with all cards validated for Arena import.

    Construction of this object implies ALL validation has passed.
    This is an IMMUTABLE, TRUSTED data structure.
    """

    cards: tuple[SanitizedCard, ...]
    sideboard: tuple[SanitizedCard, ...]

    def to_arena_format(self) -> str:
        """Export to Arena import format."""
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
# THE SANITIZER (TRUST BOUNDARY)
# =============================================================================


class ArenaDeckSanitizer:
    """
    THE trust boundary for Arena deck text.

    This class is the ONLY acceptable way to process raw Arena deck text.
    All raw input MUST pass through sanitize() before use.

    SECURITY CONTRACT:
    - sanitize() accepts UNTRUSTED raw text
    - sanitize() returns TRUSTED SanitizedDeck OR throws
    - There is NO partial success
    - There is NO silent recovery
    - There is NO guessing

    Usage:
        sanitizer = ArenaDeckSanitizer(card_db)
        try:
            deck = sanitizer.sanitize(raw_text)
            # deck is now TRUSTED
        except ArenaSanitizationError as e:
            # Input was REJECTED - handle error
    """

    # Pattern to match Arena format: "4 Card Name (SET) 123"
    _FULL_FORMAT_PATTERN = re.compile(r"^(\d+)\s+(.+?)\s+\(([A-Z0-9]+)\)\s+(\S+)$")

    # Pattern to match simple format: "4 Card Name" (no set info)
    _SIMPLE_FORMAT_PATTERN = re.compile(r"^(\d+)\s+(.+)$")

    def __init__(self, card_db: dict[str, dict[str, Any]]) -> None:
        """
        Initialize the sanitizer with a card database.

        Args:
            card_db: Dictionary mapping card names to card data.
                     Required for Arena importability checks.
        """
        self._card_db = card_db

    def sanitize(self, raw_input: str) -> SanitizedDeck:
        """
        Sanitize raw Arena deck text.

        This is THE entry point. All raw Arena text must pass through here.

        Args:
            raw_input: Raw, UNTRUSTED Arena deck text

        Returns:
            SanitizedDeck: TRUSTED, validated deck structure

        Raises:
            InvalidRawInputError: If raw input fails pre-parse validation
            InvalidDeckStructureError: If structure is invalid
            InvalidCardNameError: If any card name is invalid
            InvalidQuantityError: If any quantity is invalid
            InvalidSetCodeError: If any set code is invalid
            InvalidCollectorNumberError: If any collector number is invalid
            ArenaImportabilityError: If any card cannot be imported to Arena
        """
        # Step 1: Validate raw input BEFORE parsing
        self._validate_raw_input(raw_input)

        # Step 2: Parse to intermediate structure (PARSING ONLY)
        parsed = self._parse_to_structure(raw_input)

        # Step 3: Sanitize the parsed structure (SANITIZATION)
        sanitized_cards, sanitized_sideboard = self._sanitize_structure(parsed)

        # Step 4: Build immutable output
        return SanitizedDeck(
            cards=tuple(sanitized_cards),
            sideboard=tuple(sanitized_sideboard),
        )

    def _validate_raw_input(self, raw_input: str) -> None:
        """
        Validate raw input BEFORE parsing.

        This catches obviously malformed input before we try to parse it.

        Raises:
            InvalidRawInputError: If input fails validation
        """
        # Check type
        if not isinstance(raw_input, str):
            raise InvalidRawInputError(f"Input must be a string, got {type(raw_input).__name__}")

        # Check for empty
        if not raw_input:
            raise InvalidRawInputError("Input is empty")

        if not raw_input.strip():
            raise InvalidRawInputError("Input is whitespace-only")

        # Check length (DoS prevention)
        if len(raw_input) > MAX_RAW_INPUT_LENGTH:
            raise InvalidRawInputError(
                f"Input exceeds maximum length of {MAX_RAW_INPUT_LENGTH} characters"
            )

        # Check for null bytes (injection prevention)
        if "\x00" in raw_input:
            raise InvalidRawInputError("Input contains null bytes")

    def _parse_to_structure(self, raw_input: str) -> ParsedDeckStructure:
        """
        Parse raw input to intermediate structure.

        THIS IS PARSING ONLY. No validation of values happens here.
        We extract structure, not validate it.

        Raises:
            InvalidDeckStructureError: If structure cannot be parsed
        """
        lines = raw_input.split("\n")

        deck_entries: list[ParsedCardEntry] = []
        sideboard_entries: list[ParsedCardEntry] = []
        current_section = "deck"  # Default to deck
        has_deck_section = False

        for line_num, line in enumerate(lines, 1):
            line = line.strip()

            # Skip empty lines
            if not line:
                continue

            # Check for section headers
            line_lower = line.lower()
            if line_lower in VALID_ARENA_SECTIONS:
                if line_lower == "deck":
                    has_deck_section = True
                    current_section = "deck"
                elif line_lower == "sideboard":
                    current_section = "sideboard"
                else:
                    current_section = line_lower
                continue

            # Check for unknown section headers (potential injection)
            if self._looks_like_section_header(line) and line_lower not in VALID_ARENA_SECTIONS:
                raise InvalidDeckStructureError(
                    f"Unknown section header at line {line_num}: {repr(line)}"
                )

            # Try to parse as card entry
            entry = self._parse_card_line(line, line_num)
            if entry is None:
                raise InvalidDeckStructureError(
                    f"Malformed line at line {line_num}: {repr(line[:50])}"
                )

            # Add to appropriate section
            if current_section == "sideboard":
                sideboard_entries.append(entry)
            else:
                deck_entries.append(entry)

        return ParsedDeckStructure(
            deck_entries=deck_entries,
            sideboard_entries=sideboard_entries,
            has_deck_section=has_deck_section,
        )

    def _looks_like_section_header(self, line: str) -> bool:
        """Check if a line looks like a section header."""
        # Single word starting with uppercase
        if len(line.split()) == 1 and line and line[0].isupper():
            return True
        # Ends with colon
        return line.endswith(":")

    def _parse_card_line(self, line: str, line_num: int) -> ParsedCardEntry | None:
        """
        Parse a single card line.

        Returns None if line doesn't match any known format.
        This is PARSING ONLY - no validation of values.
        """
        # Try full Arena format first: "4 Card Name (SET) 123"
        match = self._FULL_FORMAT_PATTERN.match(line)
        if match:
            qty_str, name, set_code, collector_num = match.groups()
            return ParsedCardEntry(
                quantity_str=qty_str,
                card_name=name,
                set_code=set_code,
                collector_number=collector_num,
                line_number=line_num,
            )

        # Try simple format: "4 Card Name"
        match = self._SIMPLE_FORMAT_PATTERN.match(line)
        if match:
            qty_str, name = match.groups()
            return ParsedCardEntry(
                quantity_str=qty_str,
                card_name=name.strip(),
                set_code=None,
                collector_number=None,
                line_number=line_num,
            )

        return None

    def _sanitize_structure(
        self, parsed: ParsedDeckStructure
    ) -> tuple[list[SanitizedCard], list[SanitizedCard]]:
        """
        Sanitize the parsed structure.

        THIS IS SANITIZATION. All validation happens here.
        If ANY entry fails, the ENTIRE deck is rejected.

        Raises:
            InvalidDeckStructureError: If structure is invalid
            InvalidCardNameError: If any card name is invalid
            InvalidQuantityError: If any quantity is invalid
            InvalidSetCodeError: If any set code is invalid
            InvalidCollectorNumberError: If any collector number is invalid
            ArenaImportabilityError: If any card cannot be imported
        """
        # Validate structure requirements
        if not parsed.has_deck_section and not parsed.deck_entries:
            raise InvalidDeckStructureError(
                "Deck must have a 'Deck' section header or contain cards"
            )

        total_entries = len(parsed.deck_entries) + len(parsed.sideboard_entries)
        if total_entries > MAX_DECK_ENTRIES:
            raise InvalidDeckStructureError(
                f"Deck has {total_entries} entries, exceeds maximum of {MAX_DECK_ENTRIES}"
            )

        # Sanitize each card entry
        sanitized_cards = [self._sanitize_card_entry(entry) for entry in parsed.deck_entries]
        sanitized_sideboard = [
            self._sanitize_card_entry(entry) for entry in parsed.sideboard_entries
        ]

        return sanitized_cards, sanitized_sideboard

    def _sanitize_card_entry(self, entry: ParsedCardEntry) -> SanitizedCard:
        """
        Sanitize a single card entry.

        ALL validation happens here. If anything fails, we throw.

        Raises:
            InvalidCardNameError: If card name is invalid
            InvalidQuantityError: If quantity is invalid
            InvalidSetCodeError: If set code is invalid
            InvalidCollectorNumberError: If collector number is invalid
            ArenaImportabilityError: If card cannot be imported
        """
        # Validate and convert quantity
        quantity = self._sanitize_quantity(entry.card_name, entry.quantity_str)

        # Validate card name
        self._sanitize_card_name(entry.card_name)

        # Get or validate set code and collector number
        set_code, collector_number = self._get_arena_printing(
            entry.card_name,
            entry.set_code,
            entry.collector_number,
        )

        return SanitizedCard(
            name=entry.card_name,
            quantity=quantity,
            set_code=set_code,
            collector_number=collector_number,
        )

    def _sanitize_quantity(self, card_name: str, quantity_str: str) -> int:
        """
        Validate and convert quantity string to int.

        Raises:
            InvalidQuantityError: If quantity is invalid
        """
        # Try to parse
        try:
            quantity = int(quantity_str)
        except ValueError as e:
            raise InvalidQuantityError(
                card_name, quantity_str, f"Cannot parse as integer: {quantity_str}"
            ) from e

        # Check bounds
        if quantity < MIN_CARD_QUANTITY:
            raise InvalidQuantityError(card_name, quantity, f"Must be at least {MIN_CARD_QUANTITY}")

        if quantity > MAX_CARD_QUANTITY:
            raise InvalidQuantityError(
                card_name, quantity, f"Exceeds maximum of {MAX_CARD_QUANTITY}"
            )

        return quantity

    def _sanitize_card_name(self, name: str) -> None:
        """
        Validate card name.

        Raises:
            InvalidCardNameError: If name is invalid
        """
        if not name:
            raise InvalidCardNameError(name, "Card name cannot be empty")

        if not name.strip():
            raise InvalidCardNameError(name, "Card name cannot be whitespace-only")

        if len(name) > MAX_CARD_NAME_LENGTH:
            raise InvalidCardNameError(name, f"Exceeds maximum length of {MAX_CARD_NAME_LENGTH}")

        # Check for control characters
        for char in name:
            if ord(char) < 32 or ord(char) == 127:
                raise InvalidCardNameError(name, f"Contains control character (ord={ord(char)})")

        # Check against allowed pattern
        if not VALID_CARD_NAME_PATTERN.match(name):
            raise InvalidCardNameError(
                name,
                "Contains invalid characters. "
                "Only letters, numbers, spaces, apostrophes, commas, hyphens, slashes allowed.",
            )

    def _get_arena_printing(
        self,
        card_name: str,
        set_code: str | None,
        collector_number: str | None,
    ) -> tuple[str, str]:
        """
        Get validated Arena printing for a card.

        If set/collector are provided, validate them.
        If not provided, look up from database.

        Raises:
            InvalidSetCodeError: If set code is invalid
            InvalidCollectorNumberError: If collector number is invalid
            ArenaImportabilityError: If card cannot be imported
        """
        card_data = self._card_db.get(card_name)

        # If set info provided, validate it
        if set_code is not None and collector_number is not None:
            # Validate set code format
            if not set_code:
                raise InvalidSetCodeError(card_name, set_code, "Set code cannot be empty")
            if len(set_code) > MAX_SET_CODE_LENGTH:
                raise InvalidSetCodeError(
                    card_name, set_code, f"Exceeds maximum length of {MAX_SET_CODE_LENGTH}"
                )
            if not VALID_SET_CODE_PATTERN.match(set_code):
                raise InvalidSetCodeError(card_name, set_code, "Must be uppercase alphanumeric")

            # Validate collector number format
            if not collector_number:
                raise InvalidCollectorNumberError(card_name, collector_number, "Cannot be empty")
            if len(collector_number) > MAX_COLLECTOR_NUMBER_LENGTH:
                raise InvalidCollectorNumberError(
                    card_name,
                    collector_number,
                    f"Exceeds maximum length of {MAX_COLLECTOR_NUMBER_LENGTH}",
                )
            if not VALID_COLLECTOR_NUMBER_PATTERN.match(collector_number):
                raise InvalidCollectorNumberError(
                    card_name, collector_number, "Must be alphanumeric"
                )

            # Check if set is known-invalid
            if set_code.lower() in ARENA_INVALID_SETS:
                raise ArenaImportabilityError(
                    card_name, set_code, f"Set '{set_code}' is not valid for Arena import"
                )

            # Check Arena availability if we have card data
            if card_data:
                games = card_data.get("games", [])
                if "arena" not in games:
                    raise ArenaImportabilityError(
                        card_name, set_code, "Card is not available on Arena"
                    )

            return set_code, collector_number

        # No set info provided - look up from database
        if not card_data:
            raise ArenaImportabilityError(
                card_name, "UNKNOWN", "Card not found in database and no set info provided"
            )

        # Get set from database
        db_set = card_data.get("set", "")
        if not db_set:
            raise ArenaImportabilityError(card_name, "UNKNOWN", "No set information available")

        db_set = db_set.upper()
        db_collector = str(card_data.get("collector_number", "1"))

        # Check if database printing is Arena-valid
        if db_set.lower() in ARENA_INVALID_SETS:
            raise ArenaImportabilityError(
                card_name, db_set, f"Set '{db_set}' is not valid for Arena import"
            )

        games = card_data.get("games", [])
        if "arena" not in games:
            raise ArenaImportabilityError(card_name, db_set, "Card is not available on Arena")

        # Validate the database values
        if not VALID_SET_CODE_PATTERN.match(db_set):
            raise InvalidSetCodeError(card_name, db_set, "Database set code is malformed")
        if not VALID_COLLECTOR_NUMBER_PATTERN.match(db_collector):
            raise InvalidCollectorNumberError(
                card_name, db_collector, "Database collector number is malformed"
            )

        return db_set, db_collector


# =============================================================================
# PUBLIC API (CONVENIENCE FUNCTIONS)
# =============================================================================


def sanitize_arena_deck_input(
    raw_input: str,
    card_db: dict[str, dict[str, Any]],
) -> SanitizedDeck:
    """
    Sanitize raw Arena deck text.

    This is the PRIMARY entry point for sanitizing Arena deck input.
    Use this function when you have raw, untrusted Arena deck text.

    Args:
        raw_input: Raw, UNTRUSTED Arena deck text
        card_db: Card database for Arena validation

    Returns:
        SanitizedDeck: TRUSTED, validated deck structure

    Raises:
        ArenaSanitizationError: If sanitization fails (any subclass)

    Example:
        try:
            deck = sanitize_arena_deck_input(user_input, card_db)
            # deck is now trusted
            arena_export = deck.to_arena_format()
        except ArenaSanitizationError as e:
            # Handle rejection
            print(f"Invalid input: {e}")
    """
    sanitizer = ArenaDeckSanitizer(card_db)
    return sanitizer.sanitize(raw_input)


# =============================================================================
# DICT-BASED SANITIZATION (FOR INTERNAL USE)
# =============================================================================


def validate_card_name(name: str) -> None:
    """
    Validate a card name in isolation.

    Use this for validating card names that don't come from Arena text.

    Raises:
        InvalidCardNameError: If name is invalid
    """
    if not name:
        raise InvalidCardNameError(name, "Card name cannot be empty")

    if not name.strip():
        raise InvalidCardNameError(name, "Card name cannot be whitespace-only")

    if len(name) > MAX_CARD_NAME_LENGTH:
        raise InvalidCardNameError(name, f"Exceeds maximum length of {MAX_CARD_NAME_LENGTH}")

    for char in name:
        if ord(char) < 32 or ord(char) == 127:
            raise InvalidCardNameError(name, f"Contains control character (ord={ord(char)})")

    if not VALID_CARD_NAME_PATTERN.match(name):
        raise InvalidCardNameError(
            name,
            "Contains invalid characters. "
            "Only letters, numbers, spaces, apostrophes, commas, hyphens, slashes allowed.",
        )


def validate_quantity(card_name: str, quantity: int) -> None:
    """
    Validate a card quantity in isolation.

    Raises:
        InvalidQuantityError: If quantity is invalid
    """
    if not isinstance(quantity, int):
        raise InvalidQuantityError(
            card_name, quantity, f"Must be an integer, got {type(quantity).__name__}"
        )

    if quantity < MIN_CARD_QUANTITY:
        raise InvalidQuantityError(card_name, quantity, f"Must be at least {MIN_CARD_QUANTITY}")

    if quantity > MAX_CARD_QUANTITY:
        raise InvalidQuantityError(card_name, quantity, f"Exceeds maximum of {MAX_CARD_QUANTITY}")


def validate_set_code(card_name: str, set_code: str) -> None:
    """Validate a set code in isolation."""
    if not set_code:
        raise InvalidSetCodeError(card_name, set_code, "Cannot be empty")

    if len(set_code) > MAX_SET_CODE_LENGTH:
        raise InvalidSetCodeError(
            card_name, set_code, f"Exceeds maximum length of {MAX_SET_CODE_LENGTH}"
        )

    if not VALID_SET_CODE_PATTERN.match(set_code):
        raise InvalidSetCodeError(card_name, set_code, "Must be uppercase alphanumeric")


def validate_collector_number(card_name: str, collector_number: str) -> None:
    """Validate a collector number in isolation."""
    if not collector_number:
        raise InvalidCollectorNumberError(card_name, collector_number, "Cannot be empty")

    if len(collector_number) > MAX_COLLECTOR_NUMBER_LENGTH:
        raise InvalidCollectorNumberError(
            card_name, collector_number, f"Exceeds maximum length of {MAX_COLLECTOR_NUMBER_LENGTH}"
        )

    if not VALID_COLLECTOR_NUMBER_PATTERN.match(collector_number):
        raise InvalidCollectorNumberError(card_name, collector_number, "Must be alphanumeric")


def validate_deck_input(cards: dict[str, int], sideboard: dict[str, int] | None) -> None:
    """
    Validate dict-based deck input structure.

    Use this for validating deck dicts, not raw Arena text.

    Raises:
        InvalidDeckStructureError: If structure is invalid
        InvalidCardNameError: If any card name is invalid
        InvalidQuantityError: If any quantity is invalid
    """
    if cards is None:
        raise InvalidDeckStructureError("Maindeck cards cannot be None")

    if not isinstance(cards, dict):
        raise InvalidDeckStructureError(f"Maindeck must be a dict, got {type(cards).__name__}")

    if sideboard is not None and not isinstance(sideboard, dict):
        raise InvalidDeckStructureError(
            f"Sideboard must be a dict or None, got {type(sideboard).__name__}"
        )

    for card_name, quantity in cards.items():
        validate_card_name(card_name)
        validate_quantity(card_name, quantity)

    if sideboard:
        for card_name, quantity in sideboard.items():
            validate_card_name(card_name)
            validate_quantity(card_name, quantity)


def sanitize_deck_for_arena(
    cards: dict[str, int],
    card_db: dict[str, dict[str, Any]],
    sideboard: dict[str, int] | None = None,
) -> SanitizedDeck:
    """
    Sanitize a dict-based deck for Arena export.

    Use this when you already have structured dict data (not raw text).
    For raw Arena text, use sanitize_arena_deck_input() instead.

    Args:
        cards: Maindeck cards {name: quantity}
        card_db: Card database
        sideboard: Optional sideboard {name: quantity}

    Returns:
        SanitizedDeck ready for Arena export

    Raises:
        ArenaSanitizationError: If any validation fails
    """
    # Validate structure
    validate_deck_input(cards, sideboard)

    # Build deck entries
    sanitized_cards: list[SanitizedCard] = []
    for card_name, quantity in sorted(cards.items()):
        card_data = card_db.get(card_name, {})
        original_set = card_data.get("set", "")

        set_code, collector_number = _get_canonical_printing(card_name, original_set, card_db)

        sanitized_cards.append(
            SanitizedCard(
                name=card_name,
                quantity=quantity,
                set_code=set_code,
                collector_number=collector_number,
            )
        )

    # Build sideboard entries
    sanitized_sideboard: list[SanitizedCard] = []
    if sideboard:
        for card_name, quantity in sorted(sideboard.items()):
            card_data = card_db.get(card_name, {})
            original_set = card_data.get("set", "")

            set_code, collector_number = _get_canonical_printing(card_name, original_set, card_db)

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


def _get_canonical_printing(
    card_name: str,
    original_set: str,
    card_db: dict[str, dict[str, Any]],
) -> tuple[str, str]:
    """Get canonical Arena-valid printing for a card."""
    card_data = card_db.get(card_name)
    if not card_data:
        raise ArenaImportabilityError(
            card_name, original_set or "UNKNOWN", "Card not found in database"
        )

    # Check if card is Arena-available
    games = card_data.get("games", [])
    if "arena" not in games:
        raise ArenaImportabilityError(
            card_name,
            original_set or card_data.get("set", "UNKNOWN"),
            "Card is not available on Arena",
        )

    # Get set code
    set_code = card_data.get("set", "").upper()
    if not set_code:
        raise ArenaImportabilityError(card_name, "UNKNOWN", "No set information available")

    # Check if set is valid
    if set_code.lower() in ARENA_INVALID_SETS:
        raise ArenaImportabilityError(
            card_name, set_code, f"Set '{set_code}' is not valid for Arena import"
        )

    collector_number = str(card_data.get("collector_number", "1"))

    # Validate output
    validate_set_code(card_name, set_code)
    validate_collector_number(card_name, collector_number)

    return set_code, collector_number


# =============================================================================
# OUTPUT VALIDATION (POST-HOC CHECK)
# =============================================================================


def validate_arena_export(
    arena_export: str,
    card_db: dict[str, dict[str, Any]],
) -> None:
    """
    Validate that an Arena export string is valid.

    This is a POST-HOC validation check. It validates already-formatted
    Arena text, NOT raw input. For raw input, use sanitize_arena_deck_input().

    Throws on ANY validation failure.

    Args:
        arena_export: Arena format string to validate
        card_db: Card database

    Raises:
        ArenaSanitizationError: If validation fails
    """
    # Re-parse through the sanitizer to validate
    # This ensures the same rules are applied
    sanitizer = ArenaDeckSanitizer(card_db)
    sanitizer.sanitize(arena_export)


# =============================================================================
# LEGACY COMPATIBILITY
# =============================================================================

# These are kept for compatibility but delegate to proper functions


def is_arena_valid_printing(set_code: str, card_data: dict[str, Any]) -> bool:
    """Check if a printing is valid for Arena."""
    if set_code.lower() in ARENA_INVALID_SETS:
        return False
    games = card_data.get("games", [])
    return "arena" in games


def get_canonical_arena_printing(
    card_name: str,
    original_set: str,
    card_db: dict[str, dict[str, Any]],
) -> tuple[str, str]:
    """Get canonical Arena printing. Raises on failure."""
    return _get_canonical_printing(card_name, original_set, card_db)
