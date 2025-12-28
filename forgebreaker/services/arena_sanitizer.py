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
5. If input violates invariants, the system REFUSES entirely

=============================================================================
ARCHITECTURE
=============================================================================

    Raw Arena Text (UNTRUSTED)
           │
           ▼
    ┌─────────────────┐
    │  ArenaParser    │  ◄── Syntax extraction ONLY (separate module)
    └─────────────────┘
           │
           ▼
    ParsedDeckStructure (UNTRUSTED)
           │
           ▼
    ┌─────────────────────────────────────────┐
    │  ArenaDeckSanitizer.sanitize()          │  ◄── THIS IS THE TRUST BOUNDARY
    │  ─────────────────────────────────      │
    │  1. Validate raw input (pre-parse)      │
    │  2. Enforce structural invariants       │
    │  3. Enforce card-level invariants       │
    │  4. Enforce semantic invariants         │
    │  5. Canonicalize (after validation)     │
    └─────────────────────────────────────────┘
           │
           ▼
    SanitizedDeck (TRUSTED)

PARSER SUCCESS DOES NOT IMPLY SANITIZER SUCCESS.

=============================================================================
WHAT LIVES IN THIS MODULE
=============================================================================

- Invariant enforcement (ALL structural, card-level, semantic invariants)
- Validation functions
- Refusal (exceptions)
- Canonicalization (limited, after validation)
- Trusted output structures

=============================================================================
WHAT DOES NOT LIVE IN THIS MODULE
=============================================================================

- Parsing logic (see arena_parser.py)
- Formatting/rendering (see arena_formatter.py)
- Service/application logic
- Logging, retries, fallbacks
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from forgebreaker.services.arena_parser import (
    ArenaParser,
    ParsedCardEntry,
    ParsedDeckStructure,
)

# =============================================================================
# VALIDATION CONSTANTS (EXPLICIT HARD LIMITS)
# =============================================================================

# Maximum raw input length (prevent DoS)
MAX_RAW_INPUT_LENGTH = 100_000

# Maximum card name length
MAX_CARD_NAME_LENGTH = 150

# Card quantity bounds
MIN_CARD_QUANTITY = 1
MAX_CARD_QUANTITY = 250

# Maximum set code length
MAX_SET_CODE_LENGTH = 10

# Maximum collector number length
MAX_COLLECTOR_NUMBER_LENGTH = 10

# Maximum total entries in a deck
MAX_DECK_ENTRIES = 500

# Minimum total cards (deck must be non-empty)
MIN_TOTAL_CARDS = 1

# Allowed section names (lowercase for comparison)
ALLOWED_SECTIONS: frozenset[str] = frozenset({
    "deck",
    "sideboard",
    "commander",
    "companion",
})

# Required sections (at least one must be present with cards)
REQUIRED_SECTIONS: frozenset[str] = frozenset({
    "deck",
})

# Valid card name character pattern
VALID_CARD_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9 ',\-/]+$")

# Valid set code pattern (uppercase alphanumeric)
VALID_SET_CODE_PATTERN = re.compile(r"^[A-Z0-9]+$")

# Valid collector number pattern
VALID_COLLECTOR_NUMBER_PATTERN = re.compile(r"^[a-zA-Z0-9]+$")

# Set codes that Arena does NOT accept
ARENA_INVALID_SETS: frozenset[str] = frozenset({
    "plst", "plist",  # The List
    "mul",  # Multiverse Legends
    "mb1", "mb2", "fmb1",  # Mystery Booster
    "sld",  # Secret Lair
    "prm", "phed", "plg20", "plg21", "plg22", "plg23", "pmei", "pnat",  # Promos
    "j14", "j15", "j16", "j17", "j18", "j19", "j20", "j21", "j22",  # Judge promos
    "wc97", "wc98", "wc99", "wc00", "wc01", "wc02", "wc03", "wc04",  # World Champ
    "cei", "ced",  # Collectors' Edition
    "cmb1", "cmb2", "30a",  # Paper-only
    "rin", "ren",  # Foreign-only
})


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


class InvalidDeckStructureError(ArenaSanitizationError):
    """Raised when deck structure violates invariants."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"Invalid deck structure: {reason}")


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


class ArenaImportabilityError(ArenaSanitizationError):
    """Raised when a card printing is not importable to Arena."""

    def __init__(self, card_name: str, set_code: str, reason: str) -> None:
        self.card_name = card_name
        self.set_code = set_code
        self.reason = reason
        super().__init__(f"Cannot import '{card_name}' (set: {set_code}) to Arena: {reason}")


class DuplicateCardError(ArenaSanitizationError):
    """Raised when a card appears multiple times in the same section."""

    def __init__(self, card_name: str, section: str) -> None:
        self.card_name = card_name
        self.section = section
        super().__init__(f"Duplicate card '{card_name}' in section '{section}'")


# =============================================================================
# SANITIZED OUTPUT STRUCTURES (TRUSTED)
# =============================================================================


@dataclass(frozen=True)
class SanitizedCard:
    """
    A card with validated, Arena-safe information.

    Construction of this object implies ALL validation has passed.
    This is an IMMUTABLE, TRUSTED data structure.

    NOTE: This structure contains DATA ONLY.
    For formatting, use arena_formatter.format_deck_for_arena().
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

    NOTE: This structure contains DATA ONLY.
    For formatting, use arena_formatter.format_deck_for_arena().
    """

    cards: tuple[SanitizedCard, ...]
    sideboard: tuple[SanitizedCard, ...]

    def to_arena_format(self) -> str:
        """
        Export to Arena import format.

        DEPRECATED: Use arena_formatter.format_deck_for_arena() instead.
        This method is kept for backwards compatibility only.
        """
        # Import here to avoid circular import
        from forgebreaker.services.arena_formatter import format_deck_for_arena

        return format_deck_for_arena(self)


# =============================================================================
# THE SANITIZER (TRUST BOUNDARY)
# =============================================================================


class ArenaDeckSanitizer:
    """
    THE trust boundary for Arena deck text.

    This class is the ONLY acceptable way to process raw Arena deck text.
    All raw input MUST pass through sanitize() before use.

    =======================================================================
    SECURITY CONTRACT
    =======================================================================

    Input:
        Raw Arena deck output as str
        No assumptions about correctness

    Output:
        On success: a fully validated SanitizedDeck
        On failure: a hard exception, with NO output produced

    =======================================================================
    STRUCTURAL INVARIANTS (ALL ENFORCED)
    =======================================================================

    Deck-level:
        - Exactly one deck
        - Deck is non-empty (total card count > 0)
        - Total card count <= MAX_DECK_ENTRIES

    Section-level:
        - Only explicitly allowed sections
        - Required sections must be present (with cards)
        - No unknown sections
        - No duplicate sections

    Card entry-level:
        - Quantity: integer, >= 1, <= MAX_CARD_QUANTITY
        - Card name: non-empty, valid characters, <= MAX_CARD_NAME_LENGTH
        - Set code: valid format
        - Collector number: valid format

    =======================================================================
    SEMANTIC INVARIANTS (ALL ENFORCED)
    =======================================================================

        - No duplicate card names within a section
        - No inferred or defaulted values (except db lookup for simple format)
        - No normalization that changes meaning

    =======================================================================
    CANONICALIZATION (AFTER VALIDATION ONLY)
    =======================================================================

        - Deterministic ordering (alphabetical)
        - Set codes uppercased
        - Whitespace stripped

    =======================================================================
    FAILURE SEMANTICS
    =======================================================================

        - Fail fast
        - Fail closed
        - Fail loudly
        - Use dedicated error types

    Usage:
        sanitizer = ArenaDeckSanitizer(card_db)
        try:
            deck = sanitizer.sanitize(raw_text)
            # deck is now TRUSTED
        except ArenaSanitizationError as e:
            # Input was REJECTED - handle error
    """

    def __init__(self, card_db: dict[str, dict[str, Any]]) -> None:
        """
        Initialize the sanitizer.

        Args:
            card_db: Card database for Arena validation
        """
        self._card_db = card_db
        self._parser = ArenaParser()

    def sanitize(self, raw_input: str) -> SanitizedDeck:
        """
        Sanitize raw Arena deck text.

        This is THE entry point. All raw Arena text must pass through here.

        Args:
            raw_input: Raw, UNTRUSTED Arena deck text

        Returns:
            SanitizedDeck: TRUSTED, validated deck structure

        Raises:
            ArenaSanitizationError: If ANY invariant is violated
        """
        # Phase 1: Pre-parse validation
        self._validate_raw_input(raw_input)

        # Phase 2: Parse to intermediate structure
        parsed = self._parser.parse(raw_input)

        # Phase 3: Enforce structural invariants
        self._enforce_structural_invariants(parsed)

        # Phase 4: Enforce card-level invariants and build output
        sanitized_cards, sanitized_sideboard = self._sanitize_cards(parsed)

        # Phase 5: Enforce semantic invariants (done during card sanitization)

        # Phase 6: Canonicalize (sort alphabetically)
        sanitized_cards = sorted(sanitized_cards, key=lambda c: c.name)
        sanitized_sideboard = sorted(sanitized_sideboard, key=lambda c: c.name)

        return SanitizedDeck(
            cards=tuple(sanitized_cards),
            sideboard=tuple(sanitized_sideboard),
        )

    # =========================================================================
    # PHASE 1: PRE-PARSE VALIDATION
    # =========================================================================

    def _validate_raw_input(self, raw_input: str) -> None:
        """
        Validate raw input BEFORE parsing.

        Raises:
            InvalidRawInputError: If input fails validation
        """
        # Type check
        if not isinstance(raw_input, str):
            raise InvalidRawInputError(
                f"Input must be a string, got {type(raw_input).__name__}"
            )

        # Empty check
        if not raw_input:
            raise InvalidRawInputError("Input is empty")

        if not raw_input.strip():
            raise InvalidRawInputError("Input is whitespace-only")

        # Length check (DoS prevention)
        if len(raw_input) > MAX_RAW_INPUT_LENGTH:
            raise InvalidRawInputError(
                f"Input exceeds maximum length of {MAX_RAW_INPUT_LENGTH} characters"
            )

        # Null byte check (injection prevention)
        if "\x00" in raw_input:
            raise InvalidRawInputError("Input contains null bytes")

    # =========================================================================
    # PHASE 3: STRUCTURAL INVARIANT ENFORCEMENT
    # =========================================================================

    def _enforce_structural_invariants(self, parsed: ParsedDeckStructure) -> None:
        """
        Enforce all structural invariants.

        Raises:
            InvalidDeckStructureError: If any structural invariant is violated
        """
        # Check for unparseable lines (fail-closed: reject ALL malformed input)
        if parsed.unparseable_lines:
            line_num, line_content = parsed.unparseable_lines[0]
            raise InvalidDeckStructureError(
                f"Malformed line at line {line_num}: {repr(line_content[:50])}"
            )

        # Check for unknown sections
        seen_sections: set[str] = set()
        for section in parsed.sections:
            section_name_lower = section.name_lower.rstrip(":")

            # Check if section is allowed
            if section_name_lower not in ALLOWED_SECTIONS:
                raise InvalidDeckStructureError(
                    f"Unknown section '{section.name}' at line {section.line_number}"
                )

            # Check for duplicate sections
            if section_name_lower in seen_sections:
                raise InvalidDeckStructureError(
                    f"Duplicate section '{section.name}' at line {section.line_number}"
                )
            seen_sections.add(section_name_lower)

        # Check that at least one required section has cards
        has_required_section_with_cards = False
        for section in parsed.sections:
            section_name_lower = section.name_lower.rstrip(":")
            if section_name_lower in REQUIRED_SECTIONS and section.entries:
                has_required_section_with_cards = True
                break

        if not has_required_section_with_cards:
            raise InvalidDeckStructureError(
                "Deck must have at least one card in a required section (Deck)"
            )

        # Check total entry count
        total_entries = sum(len(s.entries) for s in parsed.sections)
        if total_entries > MAX_DECK_ENTRIES:
            raise InvalidDeckStructureError(
                f"Deck has {total_entries} entries, exceeds maximum of {MAX_DECK_ENTRIES}"
            )

        if total_entries < MIN_TOTAL_CARDS:
            raise InvalidDeckStructureError(
                f"Deck must have at least {MIN_TOTAL_CARDS} card"
            )

    # =========================================================================
    # PHASE 4: CARD-LEVEL INVARIANT ENFORCEMENT
    # =========================================================================

    def _sanitize_cards(
        self, parsed: ParsedDeckStructure
    ) -> tuple[list[SanitizedCard], list[SanitizedCard]]:
        """
        Sanitize all cards, enforcing card-level and semantic invariants.

        Raises:
            ArenaSanitizationError: If any card fails validation
        """
        sanitized_deck: list[SanitizedCard] = []
        sanitized_sideboard: list[SanitizedCard] = []

        for section in parsed.sections:
            section_name_lower = section.name_lower.rstrip(":")

            # Track card names for duplicate detection (semantic invariant)
            seen_names_in_section: set[str] = set()

            for entry in section.entries:
                # Validate and sanitize the card entry
                sanitized = self._sanitize_card_entry(entry)

                # Check for duplicates in section (semantic invariant)
                if sanitized.name in seen_names_in_section:
                    raise DuplicateCardError(sanitized.name, section.name)
                seen_names_in_section.add(sanitized.name)

                # Add to appropriate list
                if section_name_lower == "sideboard":
                    sanitized_sideboard.append(sanitized)
                else:
                    sanitized_deck.append(sanitized)

        return sanitized_deck, sanitized_sideboard

    def _sanitize_card_entry(self, entry: ParsedCardEntry) -> SanitizedCard:
        """
        Sanitize a single card entry.

        Enforces ALL card-level invariants.

        Raises:
            ArenaSanitizationError: If any validation fails
        """
        # Validate quantity
        quantity = self._validate_quantity(entry.card_name, entry.quantity_str)

        # Validate card name
        card_name = self._validate_card_name(entry.card_name)

        # Validate or lookup set/collector info
        set_code, collector_number = self._validate_printing(
            card_name,
            entry.set_code,
            entry.collector_number,
        )

        return SanitizedCard(
            name=card_name,
            quantity=quantity,
            set_code=set_code,
            collector_number=collector_number,
        )

    def _validate_quantity(self, card_name: str, quantity_str: str) -> int:
        """
        Validate and convert quantity.

        Raises:
            InvalidQuantityError: If quantity is invalid
        """
        # Parse to int
        try:
            quantity = int(quantity_str)
        except ValueError as e:
            raise InvalidQuantityError(
                card_name, quantity_str, "Cannot parse as integer"
            ) from e

        # Check bounds
        if quantity < MIN_CARD_QUANTITY:
            raise InvalidQuantityError(
                card_name, quantity, f"Must be at least {MIN_CARD_QUANTITY}"
            )

        if quantity > MAX_CARD_QUANTITY:
            raise InvalidQuantityError(
                card_name, quantity, f"Exceeds maximum of {MAX_CARD_QUANTITY}"
            )

        return quantity

    def _validate_card_name(self, name: str) -> str:
        """
        Validate card name.

        Returns the canonical name (stripped).

        Raises:
            InvalidCardNameError: If name is invalid
        """
        # Strip whitespace (canonicalization after validation)
        name = name.strip()

        # Empty check
        if not name:
            raise InvalidCardNameError(name, "Card name cannot be empty")

        # Length check
        if len(name) > MAX_CARD_NAME_LENGTH:
            raise InvalidCardNameError(
                name, f"Exceeds maximum length of {MAX_CARD_NAME_LENGTH}"
            )

        # Control character check
        for char in name:
            if ord(char) < 32 or ord(char) == 127:
                raise InvalidCardNameError(
                    name, f"Contains control character (ord={ord(char)})"
                )

        # Character class check
        if not VALID_CARD_NAME_PATTERN.match(name):
            raise InvalidCardNameError(
                name,
                "Contains invalid characters. "
                "Only letters, numbers, spaces, apostrophes, commas, hyphens, slashes allowed.",
            )

        return name

    def _validate_printing(
        self,
        card_name: str,
        set_code: str | None,
        collector_number: str | None,
    ) -> tuple[str, str]:
        """
        Validate or lookup printing information.

        Raises:
            InvalidSetCodeError: If set code is invalid
            InvalidCollectorNumberError: If collector number is invalid
            ArenaImportabilityError: If card cannot be imported
        """
        # If set info provided, validate it
        if set_code is not None and collector_number is not None:
            return self._validate_provided_printing(card_name, set_code, collector_number)

        # Otherwise, look up from database
        return self._lookup_printing_from_db(card_name)

    def _validate_provided_printing(
        self,
        card_name: str,
        set_code: str,
        collector_number: str,
    ) -> tuple[str, str]:
        """
        Validate explicitly provided printing info.
        """
        # Validate set code format
        if not set_code:
            raise InvalidSetCodeError(card_name, set_code, "Set code cannot be empty")

        if len(set_code) > MAX_SET_CODE_LENGTH:
            raise InvalidSetCodeError(
                card_name, set_code, f"Exceeds maximum length of {MAX_SET_CODE_LENGTH}"
            )

        if not VALID_SET_CODE_PATTERN.match(set_code):
            raise InvalidSetCodeError(
                card_name, set_code, "Must be uppercase alphanumeric"
            )

        # Validate collector number format
        if not collector_number:
            raise InvalidCollectorNumberError(
                card_name, collector_number, "Cannot be empty"
            )

        if len(collector_number) > MAX_COLLECTOR_NUMBER_LENGTH:
            raise InvalidCollectorNumberError(
                card_name, collector_number,
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
        card_data = self._card_db.get(card_name)
        if card_data:
            games = card_data.get("games", [])
            if "arena" not in games:
                raise ArenaImportabilityError(
                    card_name, set_code, "Card is not available on Arena"
                )

        return set_code, collector_number

    def _lookup_printing_from_db(self, card_name: str) -> tuple[str, str]:
        """
        Look up printing from database.

        Raises:
            ArenaImportabilityError: If card not found or not on Arena
        """
        card_data = self._card_db.get(card_name)
        if not card_data:
            raise ArenaImportabilityError(
                card_name, "UNKNOWN", "Card not found in database and no set info provided"
            )

        # Check Arena availability
        games = card_data.get("games", [])
        if "arena" not in games:
            raise ArenaImportabilityError(
                card_name,
                card_data.get("set", "UNKNOWN"),
                "Card is not available on Arena",
            )

        # Get set code (canonicalize to uppercase)
        db_set = card_data.get("set", "")
        if not db_set:
            raise ArenaImportabilityError(
                card_name, "UNKNOWN", "No set information available"
            )
        db_set = db_set.upper()

        # Check if set is valid
        if db_set.lower() in ARENA_INVALID_SETS:
            raise ArenaImportabilityError(
                card_name, db_set, f"Set '{db_set}' is not valid for Arena import"
            )

        db_collector = str(card_data.get("collector_number", "1"))

        # Validate database values
        if not VALID_SET_CODE_PATTERN.match(db_set):
            raise InvalidSetCodeError(
                card_name, db_set, "Database set code is malformed"
            )
        if not VALID_COLLECTOR_NUMBER_PATTERN.match(db_collector):
            raise InvalidCollectorNumberError(
                card_name, db_collector, "Database collector number is malformed"
            )

        return db_set, db_collector


# =============================================================================
# PUBLIC API
# =============================================================================


def sanitize_arena_deck_input(
    raw_input: str,
    card_db: dict[str, dict[str, Any]],
) -> SanitizedDeck:
    """
    Sanitize raw Arena deck text.

    This is the PRIMARY entry point for sanitizing Arena deck input.

    Args:
        raw_input: Raw, UNTRUSTED Arena deck text
        card_db: Card database for Arena validation

    Returns:
        SanitizedDeck: TRUSTED, validated deck structure

    Raises:
        ArenaSanitizationError: If sanitization fails
    """
    sanitizer = ArenaDeckSanitizer(card_db)
    return sanitizer.sanitize(raw_input)


# =============================================================================
# STANDALONE VALIDATION FUNCTIONS
# =============================================================================


def validate_card_name(name: str) -> None:
    """
    Validate a card name in isolation.

    Raises:
        InvalidCardNameError: If name is invalid
    """
    if not name:
        raise InvalidCardNameError(name, "Card name cannot be empty")

    if not name.strip():
        raise InvalidCardNameError(name, "Card name cannot be whitespace-only")

    if len(name) > MAX_CARD_NAME_LENGTH:
        raise InvalidCardNameError(
            name, f"Exceeds maximum length of {MAX_CARD_NAME_LENGTH}"
        )

    for char in name:
        if ord(char) < 32 or ord(char) == 127:
            raise InvalidCardNameError(
                name, f"Contains control character (ord={ord(char)})"
            )

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
        raise InvalidQuantityError(
            card_name, quantity, f"Must be at least {MIN_CARD_QUANTITY}"
        )

    if quantity > MAX_CARD_QUANTITY:
        raise InvalidQuantityError(
            card_name, quantity, f"Exceeds maximum of {MAX_CARD_QUANTITY}"
        )


def validate_set_code(card_name: str, set_code: str) -> None:
    """
    Validate a set code in isolation.

    Raises:
        InvalidSetCodeError: If set code is invalid
    """
    if not set_code:
        raise InvalidSetCodeError(card_name, set_code, "Cannot be empty")

    if len(set_code) > MAX_SET_CODE_LENGTH:
        raise InvalidSetCodeError(
            card_name, set_code, f"Exceeds maximum length of {MAX_SET_CODE_LENGTH}"
        )

    if not VALID_SET_CODE_PATTERN.match(set_code):
        raise InvalidSetCodeError(card_name, set_code, "Must be uppercase alphanumeric")


def validate_collector_number(card_name: str, collector_number: str) -> None:
    """
    Validate a collector number in isolation.

    Raises:
        InvalidCollectorNumberError: If collector number is invalid
    """
    if not collector_number:
        raise InvalidCollectorNumberError(card_name, collector_number, "Cannot be empty")

    if len(collector_number) > MAX_COLLECTOR_NUMBER_LENGTH:
        raise InvalidCollectorNumberError(
            card_name, collector_number,
            f"Exceeds maximum length of {MAX_COLLECTOR_NUMBER_LENGTH}",
        )

    if not VALID_COLLECTOR_NUMBER_PATTERN.match(collector_number):
        raise InvalidCollectorNumberError(
            card_name, collector_number, "Must be alphanumeric"
        )


# =============================================================================
# DICT-BASED SANITIZATION
# =============================================================================


def sanitize_deck_for_arena(
    cards: dict[str, int],
    card_db: dict[str, dict[str, Any]],
    sideboard: dict[str, int] | None = None,
) -> SanitizedDeck:
    """
    Sanitize a dict-based deck for Arena export.

    Use this when you have structured dict data (not raw text).

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
    if cards is None:
        raise InvalidDeckStructureError("Maindeck cards cannot be None")

    if not isinstance(cards, dict):
        raise InvalidDeckStructureError(
            f"Maindeck must be a dict, got {type(cards).__name__}"
        )

    if sideboard is not None and not isinstance(sideboard, dict):
        raise InvalidDeckStructureError(
            f"Sideboard must be a dict or None, got {type(sideboard).__name__}"
        )

    # Check non-empty
    total_cards = len(cards) + (len(sideboard) if sideboard else 0)
    if total_cards < MIN_TOTAL_CARDS:
        raise InvalidDeckStructureError(
            f"Deck must have at least {MIN_TOTAL_CARDS} card"
        )

    # Validate and build maindeck
    sanitized_cards: list[SanitizedCard] = []
    for card_name, quantity in sorted(cards.items()):
        validate_card_name(card_name)
        validate_quantity(card_name, quantity)

        set_code, collector_number = _get_canonical_printing(card_name, card_db)

        sanitized_cards.append(
            SanitizedCard(
                name=card_name,
                quantity=quantity,
                set_code=set_code,
                collector_number=collector_number,
            )
        )

    # Validate and build sideboard
    sanitized_sideboard: list[SanitizedCard] = []
    if sideboard:
        for card_name, quantity in sorted(sideboard.items()):
            validate_card_name(card_name)
            validate_quantity(card_name, quantity)

            set_code, collector_number = _get_canonical_printing(card_name, card_db)

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
    card_db: dict[str, dict[str, Any]],
) -> tuple[str, str]:
    """Get canonical Arena-valid printing for a card."""
    card_data = card_db.get(card_name)
    if not card_data:
        raise ArenaImportabilityError(
            card_name, "UNKNOWN", "Card not found in database"
        )

    # Check Arena availability
    games = card_data.get("games", [])
    if "arena" not in games:
        raise ArenaImportabilityError(
            card_name,
            card_data.get("set", "UNKNOWN"),
            "Card is not available on Arena",
        )

    # Get and validate set code
    set_code = card_data.get("set", "").upper()
    if not set_code:
        raise ArenaImportabilityError(
            card_name, "UNKNOWN", "No set information available"
        )

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
# OUTPUT VALIDATION
# =============================================================================


def validate_arena_export(
    arena_export: str,
    card_db: dict[str, dict[str, Any]],
) -> None:
    """
    Validate that an Arena export string is valid.

    Throws on ANY validation failure.

    Args:
        arena_export: Arena format string to validate
        card_db: Card database

    Raises:
        ArenaSanitizationError: If validation fails
    """
    sanitizer = ArenaDeckSanitizer(card_db)
    sanitizer.sanitize(arena_export)


# =============================================================================
# LEGACY COMPATIBILITY
# =============================================================================


def is_arena_valid_printing(set_code: str, card_data: dict[str, Any]) -> bool:
    """Check if a printing is valid for Arena."""
    if set_code.lower() in ARENA_INVALID_SETS:
        return False
    games = card_data.get("games", [])
    return "arena" in games


def get_canonical_arena_printing(
    card_name: str,
    _original_set: str,
    card_db: dict[str, dict[str, Any]],
) -> tuple[str, str]:
    """Get canonical Arena printing. Raises on failure."""
    return _get_canonical_printing(card_name, card_db)
