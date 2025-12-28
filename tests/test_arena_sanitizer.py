"""
Arena Sanitizer Boundary Tests.

This test suite protects the output-format boundary:

    Any deck output returned to the user must be Arena-IMPORTABLE,
    not just Arena-legal.

SECURITY FOCUS:
- All tests assert FAILURE (exceptions), not recovery
- Adversarial inputs are explicitly tested
- Partial sanitization is never accepted
"""

from typing import Any

import pytest

from forgebreaker.services.arena_sanitizer import (
    ARENA_INVALID_SETS,
    MAX_CARD_NAME_LENGTH,
    MAX_CARD_QUANTITY,
    MAX_COLLECTOR_NUMBER_LENGTH,
    MAX_SET_CODE_LENGTH,
    MIN_CARD_QUANTITY,
    ArenaImportabilityError,
    ArenaSanitizationError,
    InvalidCardNameError,
    InvalidCollectorNumberError,
    InvalidDeckStructureError,
    InvalidQuantityError,
    InvalidSetCodeError,
    SanitizedDeck,
    get_canonical_arena_printing,
    is_arena_valid_printing,
    sanitize_deck_for_arena,
    validate_arena_export,
    validate_card_name,
    validate_collector_number,
    validate_deck_input,
    validate_quantity,
    validate_set_code,
)

# =============================================================================
# TEST FIXTURES
# =============================================================================


@pytest.fixture
def card_db_with_plst() -> dict[str, dict[str, Any]]:
    """
    Card database where a card's primary printing is from PLST (The List).

    Crystal Grotto is a real example - it exists on Arena but some
    database entries might reference the PLST printing.
    """
    return {
        "Crystal Grotto": {
            "name": "Crystal Grotto",
            "set": "plst",  # Invalid - The List is paper-only
            "collector_number": "DMU-246",
            "type_line": "Land",
            "games": ["paper"],  # NOT on Arena with this printing
        },
        "Lightning Bolt": {
            "name": "Lightning Bolt",
            "set": "sta",  # Valid - Strixhaven Mystical Archive
            "collector_number": "42",
            "type_line": "Instant",
            "games": ["arena", "paper", "mtgo"],
        },
        "Mountain": {
            "name": "Mountain",
            "set": "dmu",  # Valid - Dominaria United
            "collector_number": "269",
            "type_line": "Basic Land — Mountain",
            "games": ["arena", "paper", "mtgo"],
        },
    }


@pytest.fixture
def card_db_valid() -> dict[str, dict[str, Any]]:
    """Card database with all valid Arena printings."""
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


# =============================================================================
# ADVERSARIAL TESTS - CARD NAME VALIDATION
# =============================================================================


class TestAdversarialCardNames:
    """Test card name validation against malicious/malformed input."""

    def test_empty_string_rejected(self) -> None:
        """Empty card name is rejected."""
        with pytest.raises(InvalidCardNameError) as exc_info:
            validate_card_name("")
        assert "empty" in str(exc_info.value).lower()

    def test_whitespace_only_rejected(self) -> None:
        """Whitespace-only card name is rejected."""
        with pytest.raises(InvalidCardNameError) as exc_info:
            validate_card_name("   ")
        assert "whitespace" in str(exc_info.value).lower()

    def test_tabs_only_rejected(self) -> None:
        """Tab-only card name is rejected."""
        with pytest.raises(InvalidCardNameError):
            validate_card_name("\t\t\t")

    def test_newlines_rejected(self) -> None:
        """Card names with newlines are rejected."""
        with pytest.raises(InvalidCardNameError) as exc_info:
            validate_card_name("Lightning\nBolt")
        assert "control character" in str(exc_info.value).lower()

    def test_null_byte_rejected(self) -> None:
        """Null bytes in card names are rejected."""
        with pytest.raises(InvalidCardNameError) as exc_info:
            validate_card_name("Lightning\x00Bolt")
        assert "control character" in str(exc_info.value).lower()

    def test_carriage_return_rejected(self) -> None:
        """Carriage returns in card names are rejected."""
        with pytest.raises(InvalidCardNameError):
            validate_card_name("Card\rName")

    def test_bell_character_rejected(self) -> None:
        """Bell character (ASCII 7) is rejected."""
        with pytest.raises(InvalidCardNameError):
            validate_card_name("Card\x07Name")

    def test_excessive_length_rejected(self) -> None:
        """Card names exceeding max length are rejected."""
        long_name = "A" * (MAX_CARD_NAME_LENGTH + 1)
        with pytest.raises(InvalidCardNameError) as exc_info:
            validate_card_name(long_name)
        assert "maximum length" in str(exc_info.value).lower()

    def test_sql_injection_attempt_rejected(self) -> None:
        """SQL injection attempts are rejected (due to invalid chars)."""
        with pytest.raises(InvalidCardNameError):
            validate_card_name("'; DROP TABLE cards; --")

    def test_html_injection_rejected(self) -> None:
        """HTML/script injection attempts are rejected."""
        with pytest.raises(InvalidCardNameError):
            validate_card_name("<script>alert('xss')</script>")

    def test_arena_format_injection_rejected(self) -> None:
        """Attempts to inject Arena format lines are rejected."""
        # Parentheses are not in allowed pattern
        with pytest.raises(InvalidCardNameError):
            validate_card_name("4 Fake Card (STA) 1")

    def test_unicode_injection_rejected(self) -> None:
        """Unicode confusables are rejected."""
        # Full-width A is not in allowed pattern
        with pytest.raises(InvalidCardNameError):
            validate_card_name("Ｌｉｇｈｔｎｉｎｇ Ｂｏｌｔ")

    def test_valid_card_name_passes(self) -> None:
        """Valid card names pass validation."""
        # These should NOT raise
        validate_card_name("Lightning Bolt")
        validate_card_name("Who/What/When/Where/Why")  # Split cards
        validate_card_name("Ach, Hans' Run")  # Apostrophe
        validate_card_name("Fire-Belly Changeling")  # Hyphen
        validate_card_name("Circle of Protection, Red")  # Comma (though not real)


# =============================================================================
# ADVERSARIAL TESTS - QUANTITY VALIDATION
# =============================================================================


class TestAdversarialQuantities:
    """Test quantity validation against invalid values."""

    def test_zero_quantity_rejected(self) -> None:
        """Zero quantity is rejected."""
        with pytest.raises(InvalidQuantityError) as exc_info:
            validate_quantity("Test Card", 0)
        assert "at least" in str(exc_info.value).lower()

    def test_negative_quantity_rejected(self) -> None:
        """Negative quantity is rejected."""
        with pytest.raises(InvalidQuantityError) as exc_info:
            validate_quantity("Test Card", -1)
        assert "at least" in str(exc_info.value).lower()

    def test_large_negative_rejected(self) -> None:
        """Large negative quantity is rejected."""
        with pytest.raises(InvalidQuantityError):
            validate_quantity("Test Card", -999999)

    def test_excessive_quantity_rejected(self) -> None:
        """Quantity exceeding max is rejected."""
        with pytest.raises(InvalidQuantityError) as exc_info:
            validate_quantity("Test Card", MAX_CARD_QUANTITY + 1)
        assert "maximum" in str(exc_info.value).lower()

    def test_absurdly_large_quantity_rejected(self) -> None:
        """Absurdly large quantities are rejected."""
        with pytest.raises(InvalidQuantityError):
            validate_quantity("Test Card", 10**9)

    def test_float_quantity_rejected(self) -> None:
        """Float quantities are rejected (type check)."""
        with pytest.raises(InvalidQuantityError) as exc_info:
            validate_quantity("Test Card", 4.5)  # type: ignore[arg-type]
        assert "integer" in str(exc_info.value).lower()

    def test_string_quantity_rejected(self) -> None:
        """String quantities are rejected."""
        with pytest.raises(InvalidQuantityError):
            validate_quantity("Test Card", "4")  # type: ignore[arg-type]

    def test_none_quantity_rejected(self) -> None:
        """None quantity is rejected."""
        with pytest.raises(InvalidQuantityError):
            validate_quantity("Test Card", None)  # type: ignore[arg-type]

    def test_valid_quantities_pass(self) -> None:
        """Valid quantities pass validation."""
        validate_quantity("Test Card", MIN_CARD_QUANTITY)
        validate_quantity("Test Card", 4)
        validate_quantity("Basic Land", MAX_CARD_QUANTITY)


# =============================================================================
# ADVERSARIAL TESTS - SET CODE VALIDATION
# =============================================================================


class TestAdversarialSetCodes:
    """Test set code validation against invalid values."""

    def test_empty_set_code_rejected(self) -> None:
        """Empty set code is rejected."""
        with pytest.raises(InvalidSetCodeError) as exc_info:
            validate_set_code("Test Card", "")
        assert "empty" in str(exc_info.value).lower()

    def test_lowercase_set_code_rejected(self) -> None:
        """Lowercase set codes are rejected (must be uppercase)."""
        with pytest.raises(InvalidSetCodeError) as exc_info:
            validate_set_code("Test Card", "sta")
        assert "uppercase" in str(exc_info.value).lower()

    def test_excessive_length_rejected(self) -> None:
        """Set codes exceeding max length are rejected."""
        long_code = "A" * (MAX_SET_CODE_LENGTH + 1)
        with pytest.raises(InvalidSetCodeError) as exc_info:
            validate_set_code("Test Card", long_code)
        assert "maximum length" in str(exc_info.value).lower()

    def test_special_chars_rejected(self) -> None:
        """Set codes with special characters are rejected."""
        with pytest.raises(InvalidSetCodeError):
            validate_set_code("Test Card", "ST@")

    def test_parentheses_rejected(self) -> None:
        """Set codes with parentheses are rejected (format injection)."""
        with pytest.raises(InvalidSetCodeError):
            validate_set_code("Test Card", "(STA)")

    def test_valid_set_codes_pass(self) -> None:
        """Valid set codes pass validation."""
        validate_set_code("Test Card", "STA")
        validate_set_code("Test Card", "M21")
        validate_set_code("Test Card", "DMU")
        validate_set_code("Test Card", "MH2")


# =============================================================================
# ADVERSARIAL TESTS - COLLECTOR NUMBER VALIDATION
# =============================================================================


class TestAdversarialCollectorNumbers:
    """Test collector number validation against invalid values."""

    def test_empty_collector_number_rejected(self) -> None:
        """Empty collector number is rejected."""
        with pytest.raises(InvalidCollectorNumberError) as exc_info:
            validate_collector_number("Test Card", "")
        assert "empty" in str(exc_info.value).lower()

    def test_excessive_length_rejected(self) -> None:
        """Collector numbers exceeding max length are rejected."""
        long_num = "1" * (MAX_COLLECTOR_NUMBER_LENGTH + 1)
        with pytest.raises(InvalidCollectorNumberError) as exc_info:
            validate_collector_number("Test Card", long_num)
        assert "maximum length" in str(exc_info.value).lower()

    def test_special_chars_rejected(self) -> None:
        """Collector numbers with special characters are rejected."""
        with pytest.raises(InvalidCollectorNumberError):
            validate_collector_number("Test Card", "42*")

    def test_spaces_rejected(self) -> None:
        """Collector numbers with spaces are rejected."""
        with pytest.raises(InvalidCollectorNumberError):
            validate_collector_number("Test Card", "42 43")

    def test_valid_collector_numbers_pass(self) -> None:
        """Valid collector numbers pass validation."""
        validate_collector_number("Test Card", "42")
        validate_collector_number("Test Card", "123a")  # Some sets have letter suffixes
        validate_collector_number("Test Card", "DMU246")  # Some formats include set


# =============================================================================
# ADVERSARIAL TESTS - DECK STRUCTURE VALIDATION
# =============================================================================


class TestAdversarialDeckStructure:
    """Test deck structure validation against malformed input."""

    def test_none_maindeck_rejected(self) -> None:
        """None as maindeck is rejected."""
        with pytest.raises(InvalidDeckStructureError) as exc_info:
            validate_deck_input(None, None)  # type: ignore[arg-type]
        assert "cannot be None" in str(exc_info.value)

    def test_list_instead_of_dict_rejected(self) -> None:
        """List instead of dict is rejected."""
        with pytest.raises(InvalidDeckStructureError) as exc_info:
            validate_deck_input(["card1", "card2"], None)  # type: ignore[arg-type]
        assert "must be a dict" in str(exc_info.value)

    def test_string_instead_of_dict_rejected(self) -> None:
        """String instead of dict is rejected."""
        with pytest.raises(InvalidDeckStructureError):
            validate_deck_input("4 Lightning Bolt", None)  # type: ignore[arg-type]

    def test_list_sideboard_rejected(self) -> None:
        """List as sideboard is rejected."""
        with pytest.raises(InvalidDeckStructureError) as exc_info:
            validate_deck_input({}, ["card1"])  # type: ignore[arg-type]
        assert "sideboard" in str(exc_info.value).lower()

    def test_invalid_card_in_deck_rejected(self) -> None:
        """Invalid card name in deck is rejected."""
        with pytest.raises(InvalidCardNameError):
            validate_deck_input({"": 4}, None)

    def test_invalid_quantity_in_deck_rejected(self) -> None:
        """Invalid quantity in deck is rejected."""
        with pytest.raises(InvalidQuantityError):
            validate_deck_input({"Valid Card": 0}, None)

    def test_invalid_card_in_sideboard_rejected(self) -> None:
        """Invalid card in sideboard is rejected."""
        with pytest.raises(InvalidCardNameError):
            validate_deck_input({}, {"<script>": 4})


# =============================================================================
# ADVERSARIAL TESTS - EXPORT VALIDATION
# =============================================================================


class TestAdversarialExportValidation:
    """Test Arena export validation against malformed/injected input."""

    def test_empty_export_rejected(self, card_db_valid: dict[str, dict[str, Any]]) -> None:
        """Empty export is rejected."""
        with pytest.raises(InvalidDeckStructureError) as exc_info:
            validate_arena_export("", card_db_valid)
        assert "empty" in str(exc_info.value).lower()

    def test_missing_deck_section_rejected(self, card_db_valid: dict[str, dict[str, Any]]) -> None:
        """Export without Deck section is rejected."""
        export = """Sideboard
4 Lightning Bolt (STA) 42"""
        with pytest.raises(InvalidDeckStructureError) as exc_info:
            validate_arena_export(export, card_db_valid)
        assert "missing" in str(exc_info.value).lower()

    def test_malformed_line_rejected(self, card_db_valid: dict[str, dict[str, Any]]) -> None:
        """Malformed card lines are rejected."""
        export = """Deck
Lightning Bolt"""  # Missing quantity and set info
        with pytest.raises(InvalidDeckStructureError) as exc_info:
            validate_arena_export(export, card_db_valid)
        assert "malformed" in str(exc_info.value).lower()

    def test_invalid_set_in_export_rejected(self, card_db_valid: dict[str, dict[str, Any]]) -> None:
        """Invalid set codes in export are rejected."""
        export = """Deck
4 Lightning Bolt (PLST) 42"""
        with pytest.raises(ArenaImportabilityError) as exc_info:
            validate_arena_export(export, card_db_valid)
        assert "PLST" in str(exc_info.value)

    def test_unknown_section_rejected(self, card_db_valid: dict[str, dict[str, Any]]) -> None:
        """Unknown section headers are rejected."""
        export = """Deck
4 Lightning Bolt (STA) 42
MaliciousSection
4 Shock (M21) 159"""
        with pytest.raises(InvalidDeckStructureError) as exc_info:
            validate_arena_export(export, card_db_valid)
        assert "unknown section" in str(exc_info.value).lower()

    def test_injection_via_section_rejected(self, card_db_valid: dict[str, dict[str, Any]]) -> None:
        """Injection attempts via section headers are rejected."""
        export = """Deck
4 Lightning Bolt (STA) 42
ScriptInjection:
<script>alert(1)</script>"""
        with pytest.raises(InvalidDeckStructureError):
            validate_arena_export(export, card_db_valid)

    def test_zero_quantity_in_export_rejected(
        self, card_db_valid: dict[str, dict[str, Any]]
    ) -> None:
        """Zero quantity in export is rejected."""
        export = """Deck
0 Lightning Bolt (STA) 42"""
        with pytest.raises(InvalidQuantityError):
            validate_arena_export(export, card_db_valid)

    def test_negative_quantity_in_export_rejected(
        self, card_db_valid: dict[str, dict[str, Any]]
    ) -> None:
        """Negative quantities in export are rejected (won't match pattern)."""
        export = """Deck
-4 Lightning Bolt (STA) 42"""
        with pytest.raises(InvalidDeckStructureError):
            validate_arena_export(export, card_db_valid)

    def test_partial_truncated_export_rejected(
        self, card_db_valid: dict[str, dict[str, Any]]
    ) -> None:
        """Truncated/incomplete card lines are rejected."""
        export = """Deck
4 Lightning Bolt ("""  # Truncated
        with pytest.raises(InvalidDeckStructureError):
            validate_arena_export(export, card_db_valid)


# =============================================================================
# ORIGINAL BOUNDARY TESTS (PRESERVED)
# =============================================================================


class TestInvalidSetDetection:
    """Tests for detecting invalid Arena set codes."""

    def test_plst_is_invalid(self) -> None:
        """PLST (The List) is not valid for Arena import."""
        assert "plst" in ARENA_INVALID_SETS

    def test_mul_is_invalid(self) -> None:
        """MUL (Multiverse Legends) is not valid for Arena import."""
        assert "mul" in ARENA_INVALID_SETS

    def test_sld_is_invalid(self) -> None:
        """SLD (Secret Lair) is not valid for Arena import."""
        assert "sld" in ARENA_INVALID_SETS

    def test_sta_is_valid(self) -> None:
        """STA (Strixhaven Mystical Archive) IS valid for Arena."""
        assert "sta" not in ARENA_INVALID_SETS

    def test_is_arena_valid_printing_rejects_plst(
        self, card_db_with_plst: dict[str, dict[str, Any]]
    ) -> None:
        """is_arena_valid_printing returns False for PLST."""
        card_data = card_db_with_plst["Crystal Grotto"]
        assert not is_arena_valid_printing("plst", card_data)

    def test_is_arena_valid_printing_accepts_valid_set(
        self, card_db_valid: dict[str, dict[str, Any]]
    ) -> None:
        """is_arena_valid_printing returns True for valid sets."""
        card_data = card_db_valid["Lightning Bolt"]
        assert is_arena_valid_printing("sta", card_data)


class TestCanonicalPrinting:
    """Tests for getting canonical Arena-valid printings."""

    def test_valid_set_passes_through(self, card_db_valid: dict[str, dict[str, Any]]) -> None:
        """Valid set codes are returned unchanged."""
        set_code, collector_num = get_canonical_arena_printing(
            "Lightning Bolt", "sta", card_db_valid
        )
        assert set_code == "STA"
        assert collector_num == "42"

    def test_invalid_set_raises_error(self, card_db_with_plst: dict[str, dict[str, Any]]) -> None:
        """Invalid set codes raise ArenaImportabilityError."""
        with pytest.raises(ArenaImportabilityError) as exc_info:
            get_canonical_arena_printing("Crystal Grotto", "plst", card_db_with_plst)

        error = exc_info.value
        assert error.card_name == "Crystal Grotto"
        assert error.set_code == "plst"
        assert "not valid for Arena" in str(error)

    def test_unknown_card_raises_error(self, card_db_valid: dict[str, dict[str, Any]]) -> None:
        """Unknown cards raise ArenaImportabilityError."""
        with pytest.raises(ArenaImportabilityError) as exc_info:
            get_canonical_arena_printing("Nonexistent Card", "xxx", card_db_valid)

        assert exc_info.value.card_name == "Nonexistent Card"
        assert "not found" in str(exc_info.value).lower()


class TestDeckSanitization:
    """Tests for full deck sanitization."""

    def test_valid_deck_sanitizes_successfully(
        self, card_db_valid: dict[str, dict[str, Any]]
    ) -> None:
        """Deck with all valid printings sanitizes successfully."""
        cards = {"Lightning Bolt": 4, "Shock": 4}

        result = sanitize_deck_for_arena(cards, card_db_valid)

        assert isinstance(result, SanitizedDeck)
        assert len(result.cards) == 2

    def test_sanitized_deck_produces_arena_format(
        self, card_db_valid: dict[str, dict[str, Any]]
    ) -> None:
        """Sanitized deck can be exported to Arena format."""
        cards = {"Lightning Bolt": 4}

        result = sanitize_deck_for_arena(cards, card_db_valid)
        arena_format = result.to_arena_format()

        assert "Deck" in arena_format
        assert "4 Lightning Bolt (STA) 42" in arena_format

    def test_invalid_printing_fails_entire_deck(
        self, card_db_with_plst: dict[str, dict[str, Any]]
    ) -> None:
        """
        Deck with ONE invalid printing fails ENTIRELY.

        This is the core contract: no partial sanitization.
        """
        cards = {
            "Lightning Bolt": 4,  # Valid
            "Crystal Grotto": 4,  # Invalid - PLST printing
        }

        with pytest.raises(ArenaImportabilityError) as exc_info:
            sanitize_deck_for_arena(cards, card_db_with_plst)

        # Verify the error identifies the problematic card
        assert exc_info.value.card_name == "Crystal Grotto"
        assert exc_info.value.set_code == "plst"  # Reports the actual invalid set

    def test_empty_deck_succeeds(self, card_db_valid: dict[str, dict[str, Any]]) -> None:
        """Empty deck is valid (edge case)."""
        result = sanitize_deck_for_arena({}, card_db_valid)
        assert isinstance(result, SanitizedDeck)
        assert len(result.cards) == 0

    def test_invalid_card_name_fails_sanitization(
        self, card_db_valid: dict[str, dict[str, Any]]
    ) -> None:
        """Invalid card name fails entire sanitization."""
        with pytest.raises(InvalidCardNameError):
            sanitize_deck_for_arena({"": 4}, card_db_valid)

    def test_invalid_quantity_fails_sanitization(
        self, card_db_valid: dict[str, dict[str, Any]]
    ) -> None:
        """Invalid quantity fails entire sanitization."""
        with pytest.raises(InvalidQuantityError):
            sanitize_deck_for_arena({"Lightning Bolt": 0}, card_db_valid)


class TestArenaSanitizationError:
    """Tests for the sanitization error types."""

    def test_base_error_works(self) -> None:
        """Base ArenaSanitizationError can be raised."""
        with pytest.raises(ArenaSanitizationError):
            raise ArenaSanitizationError("Test error")

    def test_invalid_card_name_error_contains_info(self) -> None:
        """InvalidCardNameError contains card name and reason."""
        error = InvalidCardNameError("Bad Card", "Test reason")
        assert error.card_name == "Bad Card"
        assert error.reason == "Test reason"
        assert "Bad Card" in str(error)
        assert "Test reason" in str(error)

    def test_invalid_quantity_error_contains_info(self) -> None:
        """InvalidQuantityError contains all relevant info."""
        error = InvalidQuantityError("Test Card", -5, "Must be positive")
        assert error.card_name == "Test Card"
        assert error.quantity == -5
        assert error.reason == "Must be positive"
        assert "-5" in str(error)

    def test_invalid_set_code_error_contains_info(self) -> None:
        """InvalidSetCodeError contains all relevant info."""
        error = InvalidSetCodeError("Test Card", "PLST", "Not valid")
        assert error.card_name == "Test Card"
        assert error.set_code == "PLST"
        assert "PLST" in str(error)

    def test_arena_importability_error_contains_info(self) -> None:
        """ArenaImportabilityError contains all relevant info."""
        error = ArenaImportabilityError("Crystal Grotto", "plst", "Paper only")
        assert error.card_name == "Crystal Grotto"
        assert error.set_code == "plst"
        assert error.reason == "Paper only"
        assert "Crystal Grotto" in str(error)

    def test_error_truncates_long_names(self) -> None:
        """Long card names are truncated in error messages."""
        long_name = "A" * 100
        error = InvalidCardNameError(long_name, "Too long")
        # Error message should contain truncated version
        assert len(str(error)) < 200


class TestBoundaryContract:
    """
    Core boundary test: proves the sanitizer protects the output contract.

    A deck containing a valid card with an invalid printing must be:
    - Canonicalized to a valid printing, OR
    - Rejected with an explicit error

    This test is intentionally stable across refactors.
    """

    def test_invalid_printing_is_handled_explicitly(
        self, card_db_with_plst: dict[str, dict[str, Any]]
    ) -> None:
        """
        A valid card with an invalid printing must be handled explicitly.

        Either:
        1. The sanitizer finds a valid alternative printing, OR
        2. The sanitizer raises a clear, typed error

        This test does NOT assert on exact formatting.
        It only verifies the boundary is enforced.
        """
        cards = {"Crystal Grotto": 4}

        # The sanitizer must either succeed with valid output or fail explicitly
        try:
            result = sanitize_deck_for_arena(cards, card_db_with_plst)
            # If it succeeded, the output must be valid
            arena_output = result.to_arena_format()
            # Post-validation must not raise
            validate_arena_export(arena_output, card_db_with_plst)
        except ArenaSanitizationError as e:
            # If it failed, the error must be explicit and typed
            assert isinstance(e, ArenaSanitizationError)
            # Must have identifying information
            if isinstance(e, ArenaImportabilityError):
                assert e.card_name == "Crystal Grotto"
                assert e.reason is not None

    def test_all_errors_inherit_from_base(self) -> None:
        """All sanitization errors inherit from base class."""
        assert issubclass(InvalidCardNameError, ArenaSanitizationError)
        assert issubclass(InvalidQuantityError, ArenaSanitizationError)
        assert issubclass(InvalidSetCodeError, ArenaSanitizationError)
        assert issubclass(InvalidCollectorNumberError, ArenaSanitizationError)
        assert issubclass(InvalidDeckStructureError, ArenaSanitizationError)
        assert issubclass(ArenaImportabilityError, ArenaSanitizationError)

    def test_fail_closed_no_partial_recovery(
        self, card_db_valid: dict[str, dict[str, Any]]
    ) -> None:
        """
        Sanitizer never returns partial results.

        If ANY card fails validation, the entire deck is rejected.
        """
        # Mix valid and invalid
        cards = {
            "Lightning Bolt": 4,  # Valid
            "": 4,  # Invalid - empty name
        }

        # Must fail entirely, not return partial result
        with pytest.raises(ArenaSanitizationError):
            sanitize_deck_for_arena(cards, card_db_valid)
