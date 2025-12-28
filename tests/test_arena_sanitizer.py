"""
Arena Deck Sanitizer Tests.

THIS TEST SUITE PROVES THE TRUST BOUNDARY IS ENFORCED.

=============================================================================
TEST PHILOSOPHY
=============================================================================

1. Tests assert REJECTION, not recovery
2. Adversarial inputs are explicitly tested
3. Partial success is NEVER accepted
4. The sanitizer class is tested as THE entry point

=============================================================================
WHAT WE ARE TESTING
=============================================================================

ArenaDeckSanitizer is THE trust boundary for Arena deck text.
All raw input must pass through sanitize() before use.

The tests prove:
- Invalid input is REJECTED (exceptions raised)
- No output is produced for invalid input
- Fail-closed behavior is enforced throughout
- Parser success does NOT imply sanitizer success
"""

from typing import Any

import pytest

from forgebreaker.services.arena_parser import ArenaParser, parse_arena_deck
from forgebreaker.services.arena_sanitizer import (
    ARENA_INVALID_SETS,
    MAX_CARD_NAME_LENGTH,
    MAX_CARD_QUANTITY,
    MAX_DECK_ENTRIES,
    ArenaDeckSanitizer,
    ArenaImportabilityError,
    ArenaSanitizationError,
    DuplicateCardError,
    InvalidCardNameError,
    InvalidCollectorNumberError,
    InvalidDeckStructureError,
    InvalidQuantityError,
    InvalidRawInputError,
    InvalidSetCodeError,
    SanitizedDeck,
    is_arena_valid_printing,
    sanitize_arena_deck_input,
    sanitize_deck_for_arena,
    validate_card_name,
    validate_collector_number,
    validate_quantity,
    validate_set_code,
)

# =============================================================================
# TEST FIXTURES
# =============================================================================


@pytest.fixture
def card_db() -> dict[str, dict[str, Any]]:
    """Card database with valid Arena printings."""
    return {
        "Lightning Bolt": {
            "name": "Lightning Bolt",
            "set": "sta",
            "collector_number": "42",
            "type_line": "Instant",
            "games": ["arena", "paper", "mtgo"],
        },
        "Shock": {
            "name": "Shock",
            "set": "m21",
            "collector_number": "159",
            "type_line": "Instant",
            "games": ["arena", "paper", "mtgo"],
        },
        "Mountain": {
            "name": "Mountain",
            "set": "dmu",
            "collector_number": "269",
            "type_line": "Basic Land — Mountain",
            "games": ["arena", "paper", "mtgo"],
        },
    }


@pytest.fixture
def card_db_with_plst() -> dict[str, dict[str, Any]]:
    """Card database with invalid PLST printing."""
    return {
        "Crystal Grotto": {
            "name": "Crystal Grotto",
            "set": "plst",
            "collector_number": "DMU-246",
            "type_line": "Land",
            "games": ["paper"],  # NOT on Arena
        },
        "Lightning Bolt": {
            "name": "Lightning Bolt",
            "set": "sta",
            "collector_number": "42",
            "type_line": "Instant",
            "games": ["arena", "paper", "mtgo"],
        },
    }


@pytest.fixture
def sanitizer(card_db: dict[str, dict[str, Any]]) -> ArenaDeckSanitizer:
    """Create a sanitizer instance."""
    return ArenaDeckSanitizer(card_db)


# =============================================================================
# ARCHITECTURE BOUNDARY TESTS
# =============================================================================


class TestArchitectureBoundary:
    """
    Tests proving parser and sanitizer are separate.

    Parser success does NOT imply sanitizer success.
    """

    def test_parser_success_does_not_imply_sanitizer_success(
        self, card_db: dict[str, dict[str, Any]]
    ) -> None:
        """Parser can succeed while sanitizer fails."""
        # This input is syntactically valid but semantically invalid
        raw_input = "Deck\n4 Totally Fake Card"

        # Parser succeeds
        parsed = parse_arena_deck(raw_input)
        assert len(parsed.sections) == 1
        assert len(parsed.sections[0].entries) == 1

        # Sanitizer fails
        sanitizer = ArenaDeckSanitizer(card_db)
        with pytest.raises(ArenaImportabilityError):
            sanitizer.sanitize(raw_input)

    def test_parser_is_separate_module(self) -> None:
        """Parser is a separate class that can be used independently."""
        parser = ArenaParser()
        parsed = parser.parse("Deck\n4 Some Card")

        # Parser produces intermediate structure
        assert parsed.sections[0].entries[0].card_name == "Some Card"

    def test_parser_does_not_validate(self) -> None:
        """Parser extracts structure without validating values."""
        parser = ArenaParser()

        # Control characters pass through parser
        parsed = parser.parse("Deck\n4 Card\x00Name")
        assert "\x00" in parsed.sections[0].entries[0].card_name

        # Invalid quantities pass through parser
        parsed = parser.parse("Deck\n999999 Some Card")
        assert parsed.sections[0].entries[0].quantity_str == "999999"


# =============================================================================
# CORE SANITIZER CLASS TESTS
# =============================================================================


class TestArenaDeckSanitizer:
    """
    Tests for ArenaDeckSanitizer - THE trust boundary.

    These tests prove that the sanitizer:
    - Accepts UNTRUSTED raw text
    - Returns TRUSTED SanitizedDeck OR throws
    - NEVER returns partial results
    - NEVER silently recovers
    """

    def test_sanitize_valid_full_format(self, sanitizer: ArenaDeckSanitizer) -> None:
        """Valid full format Arena text is sanitized successfully."""
        raw_input = """Deck
4 Lightning Bolt (STA) 42
4 Shock (M21) 159

Sideboard
2 Mountain (DMU) 269"""

        result = sanitizer.sanitize(raw_input)

        assert isinstance(result, SanitizedDeck)
        assert len(result.cards) == 2
        assert len(result.sideboard) == 1

    def test_sanitize_valid_simple_format(self, card_db: dict[str, dict[str, Any]]) -> None:
        """Simple format (no set info) is sanitized with database lookup."""
        sanitizer = ArenaDeckSanitizer(card_db)
        raw_input = """Deck
4 Lightning Bolt
4 Shock"""

        result = sanitizer.sanitize(raw_input)

        assert isinstance(result, SanitizedDeck)
        assert len(result.cards) == 2
        # Set codes should come from database (uppercased)
        assert result.cards[0].set_code == "STA"

    def test_sanitize_returns_immutable_deck(self, sanitizer: ArenaDeckSanitizer) -> None:
        """Sanitized deck is immutable."""
        raw_input = """Deck
4 Lightning Bolt (STA) 42"""

        result = sanitizer.sanitize(raw_input)

        # SanitizedDeck uses frozen=True
        with pytest.raises((TypeError, AttributeError)):
            result.cards = ()  # type: ignore[misc]

    def test_output_is_canonicalized(self, sanitizer: ArenaDeckSanitizer) -> None:
        """Output is alphabetically ordered (canonicalized)."""
        raw_input = """Deck
4 Shock (M21) 159
4 Lightning Bolt (STA) 42"""

        result = sanitizer.sanitize(raw_input)

        # Should be alphabetical
        assert result.cards[0].name == "Lightning Bolt"
        assert result.cards[1].name == "Shock"


# =============================================================================
# RAW INPUT VALIDATION TESTS
# =============================================================================


class TestRawInputValidation:
    """
    Tests for raw input validation (pre-parse).

    These tests prove the sanitizer rejects malformed input
    BEFORE attempting to parse it.
    """

    def test_empty_string_rejected(self, sanitizer: ArenaDeckSanitizer) -> None:
        """Empty string is rejected."""
        with pytest.raises(InvalidRawInputError) as exc_info:
            sanitizer.sanitize("")
        assert "empty" in str(exc_info.value).lower()

    def test_whitespace_only_rejected(self, sanitizer: ArenaDeckSanitizer) -> None:
        """Whitespace-only input is rejected."""
        with pytest.raises(InvalidRawInputError) as exc_info:
            sanitizer.sanitize("   \n\t  ")
        assert "whitespace" in str(exc_info.value).lower()

    def test_null_bytes_rejected(self, sanitizer: ArenaDeckSanitizer) -> None:
        """Input with null bytes is rejected."""
        with pytest.raises(InvalidRawInputError) as exc_info:
            sanitizer.sanitize("Deck\x004 Lightning Bolt")
        assert "null" in str(exc_info.value).lower()

    def test_excessive_length_rejected(self, sanitizer: ArenaDeckSanitizer) -> None:
        """Input exceeding max length is rejected."""
        # Use long lines to exceed length limit before entry count limit
        long_name = "A" * 990
        huge_input = "Deck\n" + f"4 {long_name}\n" * 150
        with pytest.raises(InvalidRawInputError) as exc_info:
            sanitizer.sanitize(huge_input)
        assert "maximum length" in str(exc_info.value).lower()

    def test_non_string_rejected(self, card_db: dict[str, dict[str, Any]]) -> None:
        """Non-string input is rejected."""
        sanitizer = ArenaDeckSanitizer(card_db)
        with pytest.raises(InvalidRawInputError) as exc_info:
            sanitizer.sanitize(12345)  # type: ignore[arg-type]
        assert "string" in str(exc_info.value).lower()


# =============================================================================
# STRUCTURAL INVARIANT TESTS
# =============================================================================


class TestDeckStructureValidation:
    """
    Tests for deck structure validation.

    These tests prove structural invariants are enforced.
    """

    def test_unknown_section_header_rejected(self, sanitizer: ArenaDeckSanitizer) -> None:
        """Unknown section headers are rejected.

        Lines that look like section headers but aren't recognized
        are treated as malformed lines and cause rejection.
        """
        raw_input = """Deck
4 Lightning Bolt (STA) 42
MaliciousSection
4 Shock (M21) 159"""

        with pytest.raises(InvalidDeckStructureError) as exc_info:
            sanitizer.sanitize(raw_input)
        # Unknown headers are rejected as malformed (fail-closed)
        assert "malformed" in str(exc_info.value).lower()

    def test_duplicate_section_rejected(self, sanitizer: ArenaDeckSanitizer) -> None:
        """Duplicate sections are rejected."""
        raw_input = """Deck
4 Lightning Bolt (STA) 42
Deck
4 Shock (M21) 159"""

        with pytest.raises(InvalidDeckStructureError) as exc_info:
            sanitizer.sanitize(raw_input)
        assert "duplicate section" in str(exc_info.value).lower()

    def test_malformed_line_rejected(self, sanitizer: ArenaDeckSanitizer) -> None:
        """Malformed card lines are rejected."""
        raw_input = """Deck
Lightning Bolt"""  # Missing quantity

        with pytest.raises(InvalidDeckStructureError) as exc_info:
            sanitizer.sanitize(raw_input)
        assert "malformed" in str(exc_info.value).lower()

    def test_excessive_entries_rejected(self, card_db: dict[str, dict[str, Any]]) -> None:
        """Decks with too many entries are rejected."""
        sanitizer = ArenaDeckSanitizer(card_db)
        entries = "\n".join(["1 Lightning Bolt (STA) 42" for _ in range(MAX_DECK_ENTRIES + 1)])
        raw_input = f"Deck\n{entries}"

        with pytest.raises(InvalidDeckStructureError) as exc_info:
            sanitizer.sanitize(raw_input)
        assert "exceeds maximum" in str(exc_info.value).lower()

    def test_empty_deck_section_rejected(self, sanitizer: ArenaDeckSanitizer) -> None:
        """Deck with only sideboard (no main deck cards) is rejected."""
        raw_input = """Deck
Sideboard
4 Lightning Bolt (STA) 42"""

        with pytest.raises(InvalidDeckStructureError) as exc_info:
            sanitizer.sanitize(raw_input)
        assert "at least one card" in str(exc_info.value).lower()

    def test_partial_truncated_input_rejected(self, sanitizer: ArenaDeckSanitizer) -> None:
        """Truncated/partial input with unparseable lines is rejected."""
        raw_input = """Deck
4 Lightning Bolt (STA) 42
This is not a valid card line at all
4 Shock"""

        with pytest.raises(InvalidDeckStructureError) as exc_info:
            sanitizer.sanitize(raw_input)
        assert "malformed" in str(exc_info.value).lower()


# =============================================================================
# SEMANTIC INVARIANT TESTS
# =============================================================================


class TestSemanticInvariants:
    """
    Tests for semantic invariants.

    No duplicate card names within a section.
    """

    def test_duplicate_card_in_section_rejected(self, sanitizer: ArenaDeckSanitizer) -> None:
        """Duplicate card names in same section are rejected."""
        raw_input = """Deck
4 Lightning Bolt (STA) 42
2 Lightning Bolt (STA) 42"""

        with pytest.raises(DuplicateCardError) as exc_info:
            sanitizer.sanitize(raw_input)
        assert "duplicate" in str(exc_info.value).lower()
        assert exc_info.value.card_name == "Lightning Bolt"

    def test_same_card_in_different_sections_allowed(self, sanitizer: ArenaDeckSanitizer) -> None:
        """Same card in deck and sideboard is allowed."""
        raw_input = """Deck
4 Lightning Bolt (STA) 42

Sideboard
2 Lightning Bolt (STA) 42"""

        result = sanitizer.sanitize(raw_input)

        assert len(result.cards) == 1
        assert len(result.sideboard) == 1


# =============================================================================
# CARD NAME VALIDATION TESTS (ADVERSARIAL)
# =============================================================================


class TestCardNameValidation:
    """
    Tests for card name validation (adversarial).

    These tests prove malicious/malformed card names are rejected.
    """

    def test_control_characters_rejected(self, sanitizer: ArenaDeckSanitizer) -> None:
        """Card names with control characters are rejected."""
        raw_input = "Deck\n4 Lightning\x07Bolt (STA) 42"

        with pytest.raises(InvalidCardNameError) as exc_info:
            sanitizer.sanitize(raw_input)
        assert "control character" in str(exc_info.value).lower()

    def test_sql_injection_rejected(self, sanitizer: ArenaDeckSanitizer) -> None:
        """SQL injection attempts are rejected."""
        raw_input = "Deck\n4 '; DROP TABLE cards; -- (STA) 42"

        with pytest.raises(InvalidCardNameError):
            sanitizer.sanitize(raw_input)

    def test_html_injection_rejected(self, sanitizer: ArenaDeckSanitizer) -> None:
        """HTML injection attempts are rejected."""
        raw_input = "Deck\n4 <script>alert(1)</script> (STA) 42"

        with pytest.raises(InvalidCardNameError):
            sanitizer.sanitize(raw_input)

    def test_excessive_length_rejected(self, sanitizer: ArenaDeckSanitizer) -> None:
        """Excessively long card names are rejected."""
        long_name = "A" * (MAX_CARD_NAME_LENGTH + 1)
        raw_input = f"Deck\n4 {long_name} (STA) 42"

        with pytest.raises(InvalidCardNameError) as exc_info:
            sanitizer.sanitize(raw_input)
        assert "maximum length" in str(exc_info.value).lower()

    def test_unicode_escape_injection_rejected(self, sanitizer: ArenaDeckSanitizer) -> None:
        """Unicode escape sequences in names are rejected."""
        raw_input = "Deck\n4 Card\\u0000Name (STA) 42"

        with pytest.raises(InvalidCardNameError):
            sanitizer.sanitize(raw_input)

    def test_path_traversal_rejected(self, sanitizer: ArenaDeckSanitizer) -> None:
        """Path traversal attempts are rejected."""
        raw_input = "Deck\n4 ../../../etc/passwd (STA) 42"

        with pytest.raises(InvalidCardNameError):
            sanitizer.sanitize(raw_input)


# =============================================================================
# QUANTITY VALIDATION TESTS (ADVERSARIAL)
# =============================================================================


class TestQuantityValidation:
    """
    Tests for quantity validation (adversarial).

    These tests prove invalid quantities are rejected.
    """

    def test_zero_quantity_rejected(self, sanitizer: ArenaDeckSanitizer) -> None:
        """Zero quantity is rejected."""
        raw_input = "Deck\n0 Lightning Bolt (STA) 42"

        with pytest.raises(InvalidQuantityError) as exc_info:
            sanitizer.sanitize(raw_input)
        assert "at least" in str(exc_info.value).lower()

    def test_negative_quantity_pattern_fails(self, sanitizer: ArenaDeckSanitizer) -> None:
        """Negative quantities don't match pattern (rejected as malformed)."""
        raw_input = "Deck\n-4 Lightning Bolt (STA) 42"

        with pytest.raises(InvalidDeckStructureError):
            sanitizer.sanitize(raw_input)

    def test_excessive_quantity_rejected(self, sanitizer: ArenaDeckSanitizer) -> None:
        """Quantities exceeding max are rejected."""
        raw_input = f"Deck\n{MAX_CARD_QUANTITY + 1} Lightning Bolt (STA) 42"

        with pytest.raises(InvalidQuantityError) as exc_info:
            sanitizer.sanitize(raw_input)
        assert "maximum" in str(exc_info.value).lower()


# =============================================================================
# SET CODE VALIDATION TESTS (ADVERSARIAL)
# =============================================================================


class TestSetCodeValidation:
    """
    Tests for set code validation (adversarial).

    These tests prove invalid set codes are rejected.
    """

    def test_invalid_set_rejected(self, sanitizer: ArenaDeckSanitizer) -> None:
        """Known invalid sets are rejected."""
        raw_input = "Deck\n4 Lightning Bolt (PLST) 42"

        with pytest.raises(ArenaImportabilityError) as exc_info:
            sanitizer.sanitize(raw_input)
        assert "PLST" in str(exc_info.value)

    def test_lowercase_set_rejected(self, sanitizer: ArenaDeckSanitizer) -> None:
        """Lowercase set codes don't match full format pattern.

        The line falls back to simple format, making the card name
        'Lightning Bolt (sta) 42' which then fails card name validation
        or database lookup. Either way, the input is REJECTED.
        """
        raw_input = "Deck\n4 Lightning Bolt (sta) 42"

        # Fails because the malformed card name is rejected
        with pytest.raises(ArenaSanitizationError):
            sanitizer.sanitize(raw_input)


# =============================================================================
# ARENA IMPORTABILITY TESTS
# =============================================================================


class TestArenaImportability:
    """
    Tests for Arena importability validation.

    These tests prove cards not on Arena are rejected.
    """

    def test_paper_only_card_rejected(self, card_db_with_plst: dict[str, dict[str, Any]]) -> None:
        """Paper-only cards are rejected."""
        sanitizer = ArenaDeckSanitizer(card_db_with_plst)
        raw_input = "Deck\n4 Crystal Grotto"

        with pytest.raises(ArenaImportabilityError):
            sanitizer.sanitize(raw_input)

    def test_unknown_card_rejected(self, card_db: dict[str, dict[str, Any]]) -> None:
        """Unknown cards (not in database) are rejected."""
        sanitizer = ArenaDeckSanitizer(card_db)
        raw_input = "Deck\n4 Totally Fake Card"

        with pytest.raises(ArenaImportabilityError):
            sanitizer.sanitize(raw_input)


# =============================================================================
# CONVENIENCE FUNCTION TESTS
# =============================================================================


class TestSanitizeArenaDeckInput:
    """Tests for the sanitize_arena_deck_input convenience function."""

    def test_valid_input_returns_deck(self, card_db: dict[str, dict[str, Any]]) -> None:
        """Valid input returns SanitizedDeck."""
        raw_input = """Deck
4 Lightning Bolt (STA) 42"""

        result = sanitize_arena_deck_input(raw_input, card_db)

        assert isinstance(result, SanitizedDeck)

    def test_invalid_input_throws(self, card_db: dict[str, dict[str, Any]]) -> None:
        """Invalid input throws exception."""
        with pytest.raises(ArenaSanitizationError):
            sanitize_arena_deck_input("", card_db)


# =============================================================================
# DICT-BASED API TESTS
# =============================================================================


class TestSanitizeDeckForArena:
    """Tests for dict-based sanitization."""

    def test_valid_dict_sanitizes(self, card_db: dict[str, dict[str, Any]]) -> None:
        """Valid dict is sanitized."""
        cards = {"Lightning Bolt": 4}

        result = sanitize_deck_for_arena(cards, card_db)

        assert isinstance(result, SanitizedDeck)
        assert "4 Lightning Bolt (STA) 42" in result.to_arena_format()

    def test_invalid_card_name_rejected(self, card_db: dict[str, dict[str, Any]]) -> None:
        """Invalid card names in dict are rejected."""
        cards = {"": 4}

        with pytest.raises(InvalidCardNameError):
            sanitize_deck_for_arena(cards, card_db)

    def test_invalid_quantity_rejected(self, card_db: dict[str, dict[str, Any]]) -> None:
        """Invalid quantities in dict are rejected."""
        cards = {"Lightning Bolt": 0}

        with pytest.raises(InvalidQuantityError):
            sanitize_deck_for_arena(cards, card_db)

    def test_empty_dict_rejected(self, card_db: dict[str, dict[str, Any]]) -> None:
        """Empty dict is rejected."""
        with pytest.raises(InvalidDeckStructureError) as exc_info:
            sanitize_deck_for_arena({}, card_db)
        assert "at least" in str(exc_info.value).lower()


# =============================================================================
# VALIDATION FUNCTION TESTS (ISOLATED)
# =============================================================================


class TestValidateCardName:
    """Tests for standalone card name validation."""

    def test_empty_rejected(self) -> None:
        """Empty name is rejected."""
        with pytest.raises(InvalidCardNameError):
            validate_card_name("")

    def test_whitespace_rejected(self) -> None:
        """Whitespace-only name is rejected."""
        with pytest.raises(InvalidCardNameError):
            validate_card_name("   ")

    def test_control_chars_rejected(self) -> None:
        """Control characters are rejected."""
        with pytest.raises(InvalidCardNameError):
            validate_card_name("Test\x00Card")

    def test_valid_names_pass(self) -> None:
        """Valid names pass."""
        validate_card_name("Lightning Bolt")
        validate_card_name("Who/What/When/Where/Why")
        validate_card_name("Fire-Belly Changeling")


class TestValidateQuantity:
    """Tests for standalone quantity validation."""

    def test_zero_rejected(self) -> None:
        """Zero is rejected."""
        with pytest.raises(InvalidQuantityError):
            validate_quantity("Test", 0)

    def test_negative_rejected(self) -> None:
        """Negative is rejected."""
        with pytest.raises(InvalidQuantityError):
            validate_quantity("Test", -1)

    def test_excessive_rejected(self) -> None:
        """Excessive quantity is rejected."""
        with pytest.raises(InvalidQuantityError):
            validate_quantity("Test", MAX_CARD_QUANTITY + 1)

    def test_non_int_rejected(self) -> None:
        """Non-integer is rejected."""
        with pytest.raises(InvalidQuantityError):
            validate_quantity("Test", 4.5)  # type: ignore[arg-type]

    def test_valid_quantities_pass(self) -> None:
        """Valid quantities pass."""
        validate_quantity("Test", 1)
        validate_quantity("Test", 4)
        validate_quantity("Basic", MAX_CARD_QUANTITY)


class TestValidateSetCode:
    """Tests for standalone set code validation."""

    def test_empty_rejected(self) -> None:
        """Empty set code is rejected."""
        with pytest.raises(InvalidSetCodeError):
            validate_set_code("Test", "")

    def test_lowercase_rejected(self) -> None:
        """Lowercase set code is rejected."""
        with pytest.raises(InvalidSetCodeError):
            validate_set_code("Test", "sta")

    def test_valid_codes_pass(self) -> None:
        """Valid set codes pass."""
        validate_set_code("Test", "STA")
        validate_set_code("Test", "M21")


class TestValidateCollectorNumber:
    """Tests for standalone collector number validation."""

    def test_empty_rejected(self) -> None:
        """Empty collector number is rejected."""
        with pytest.raises(InvalidCollectorNumberError):
            validate_collector_number("Test", "")

    def test_valid_numbers_pass(self) -> None:
        """Valid collector numbers pass."""
        validate_collector_number("Test", "42")
        validate_collector_number("Test", "123a")


# =============================================================================
# INVALID SET DETECTION TESTS
# =============================================================================


class TestInvalidSetDetection:
    """Tests for invalid Arena set detection."""

    def test_plst_is_invalid(self) -> None:
        """PLST is invalid."""
        assert "plst" in ARENA_INVALID_SETS

    def test_mul_is_invalid(self) -> None:
        """MUL is invalid."""
        assert "mul" in ARENA_INVALID_SETS

    def test_sld_is_invalid(self) -> None:
        """SLD is invalid."""
        assert "sld" in ARENA_INVALID_SETS

    def test_sta_is_valid(self) -> None:
        """STA is valid."""
        assert "sta" not in ARENA_INVALID_SETS


class TestIsArenaValidPrinting:
    """Tests for is_arena_valid_printing."""

    def test_invalid_set_returns_false(self) -> None:
        """Invalid set returns False."""
        card_data: dict[str, Any] = {"games": ["arena", "paper"]}
        assert not is_arena_valid_printing("plst", card_data)

    def test_no_arena_returns_false(self) -> None:
        """No arena in games returns False."""
        card_data: dict[str, Any] = {"games": ["paper"]}
        assert not is_arena_valid_printing("STA", card_data)

    def test_valid_returns_true(self) -> None:
        """Valid printing returns True."""
        card_data: dict[str, Any] = {"games": ["arena", "paper"]}
        assert is_arena_valid_printing("STA", card_data)


# =============================================================================
# EXCEPTION HIERARCHY TESTS
# =============================================================================


class TestExceptionHierarchy:
    """Tests for the exception hierarchy."""

    def test_all_inherit_from_base(self) -> None:
        """All exceptions inherit from base."""
        assert issubclass(InvalidRawInputError, ArenaSanitizationError)
        assert issubclass(InvalidCardNameError, ArenaSanitizationError)
        assert issubclass(InvalidQuantityError, ArenaSanitizationError)
        assert issubclass(InvalidSetCodeError, ArenaSanitizationError)
        assert issubclass(InvalidCollectorNumberError, ArenaSanitizationError)
        assert issubclass(InvalidDeckStructureError, ArenaSanitizationError)
        assert issubclass(ArenaImportabilityError, ArenaSanitizationError)
        assert issubclass(DuplicateCardError, ArenaSanitizationError)

    def test_exceptions_contain_context(self) -> None:
        """Exceptions contain useful context."""
        error = InvalidCardNameError("Test Card", "bad reason")
        assert error.card_name == "Test Card"
        assert error.reason == "bad reason"
        assert "Test Card" in str(error)

    def test_duplicate_error_contains_context(self) -> None:
        """DuplicateCardError contains context."""
        error = DuplicateCardError("Lightning Bolt", "Deck")
        assert error.card_name == "Lightning Bolt"
        assert error.section == "Deck"
        assert "Lightning Bolt" in str(error)


# =============================================================================
# BOUNDARY CONTRACT TESTS
# =============================================================================


class TestBoundaryContract:
    """
    Core boundary tests.

    These prove the trust boundary is enforced:
    - Invalid input is REJECTED
    - Valid input produces TRUSTED output
    - No partial results ever
    """

    def test_fail_closed_no_partial_results(self, card_db: dict[str, dict[str, Any]]) -> None:
        """
        If ANY card fails, the ENTIRE deck is rejected.

        No partial sanitization. Ever.
        """
        sanitizer = ArenaDeckSanitizer(card_db)

        # Mix valid and invalid
        raw_input = """Deck
4 Lightning Bolt (STA) 42
4 <script>alert(1)</script> (STA) 1"""

        with pytest.raises(ArenaSanitizationError):
            sanitizer.sanitize(raw_input)

    def test_valid_produces_trusted_output(self, card_db: dict[str, dict[str, Any]]) -> None:
        """Valid input produces trusted, exportable output."""
        sanitizer = ArenaDeckSanitizer(card_db)

        raw_input = """Deck
4 Lightning Bolt (STA) 42"""

        result = sanitizer.sanitize(raw_input)

        # Output can be safely exported
        arena_format = result.to_arena_format()
        assert "Deck" in arena_format
        assert "4 Lightning Bolt (STA) 42" in arena_format

    def test_sanitizer_is_reusable(self, card_db: dict[str, dict[str, Any]]) -> None:
        """Sanitizer can be reused for multiple inputs."""
        sanitizer = ArenaDeckSanitizer(card_db)

        input1 = "Deck\n4 Lightning Bolt (STA) 42"
        input2 = "Deck\n4 Shock (M21) 159"

        result1 = sanitizer.sanitize(input1)
        result2 = sanitizer.sanitize(input2)

        assert len(result1.cards) == 1
        assert len(result2.cards) == 1

    def test_no_output_on_failure(self, card_db: dict[str, dict[str, Any]]) -> None:
        """Failed sanitization produces NO output."""
        sanitizer = ArenaDeckSanitizer(card_db)

        # Verify exception is raised (no output produced)
        with pytest.raises(ArenaSanitizationError):
            sanitizer.sanitize("Deck\n4 <invalid>")
