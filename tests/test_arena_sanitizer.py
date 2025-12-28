"""
Arena Sanitizer Boundary Tests.

This test protects the output-format boundary:

    Any deck output returned to the user must be Arena-IMPORTABLE,
    not just Arena-legal.

A card can exist on Arena but have an invalid printing (PLST, MUL, promos).
The sanitizer must canonicalize these or fail loudly.
"""

from typing import Any

import pytest

from forgebreaker.services.arena_sanitizer import (
    ARENA_INVALID_SETS,
    ArenaSanitizationError,
    SanitizedDeck,
    get_canonical_arena_printing,
    is_arena_valid_printing,
    sanitize_deck_for_arena,
    validate_arena_importability,
)


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
        """Invalid set codes raise ArenaSanitizationError."""
        with pytest.raises(ArenaSanitizationError) as exc_info:
            get_canonical_arena_printing("Crystal Grotto", "plst", card_db_with_plst)

        error = exc_info.value
        assert error.card_name == "Crystal Grotto"
        assert error.invalid_set == "plst"
        assert "not valid for Arena" in str(error)

    def test_unknown_card_raises_error(self, card_db_valid: dict[str, dict[str, Any]]) -> None:
        """Unknown cards raise ArenaSanitizationError."""
        with pytest.raises(ArenaSanitizationError) as exc_info:
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

        with pytest.raises(ArenaSanitizationError) as exc_info:
            sanitize_deck_for_arena(cards, card_db_with_plst)

        # Verify the error identifies the problematic card
        assert exc_info.value.card_name == "Crystal Grotto"
        assert exc_info.value.invalid_set == "plst"


class TestArenaSanitizationError:
    """Tests for the sanitization error type."""

    def test_error_includes_card_name(self) -> None:
        """Error includes the problematic card name."""
        error = ArenaSanitizationError(
            card_name="Test Card",
            invalid_set="xxx",
            reason="Test reason",
        )

        assert error.card_name == "Test Card"
        assert "Test Card" in str(error)

    def test_error_includes_set(self) -> None:
        """Error includes the invalid set code."""
        error = ArenaSanitizationError(
            card_name="Test Card",
            invalid_set="plst",
            reason="Test reason",
        )

        assert error.invalid_set == "plst"
        assert "plst" in str(error)

    def test_error_includes_reason(self) -> None:
        """Error includes the failure reason."""
        error = ArenaSanitizationError(
            card_name="Test Card",
            invalid_set="xxx",
            reason="Not available on Arena",
        )

        assert "Not available on Arena" in str(error)


class TestValidateArenaImportability:
    """Tests for post-sanitization validation."""

    def test_valid_export_passes(self, card_db_valid: dict[str, dict[str, Any]]) -> None:
        """Valid Arena export has no errors."""
        arena_export = """Deck
4 Lightning Bolt (STA) 42
4 Shock (M21) 159"""

        errors = validate_arena_importability(arena_export, card_db_valid)

        assert errors == []

    def test_invalid_set_detected(self, card_db_valid: dict[str, dict[str, Any]]) -> None:
        """Invalid set codes are caught in validation."""
        arena_export = """Deck
4 Lightning Bolt (PLST) 42"""

        errors = validate_arena_importability(arena_export, card_db_valid)

        assert len(errors) == 1
        assert "PLST" in errors[0]


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
            errors = validate_arena_importability(arena_output, card_db_with_plst)
            assert errors == [], f"Sanitized output still has errors: {errors}"
        except ArenaSanitizationError as e:
            # If it failed, the error must be explicit and typed
            assert e.card_name == "Crystal Grotto"
            assert e.invalid_set is not None
            assert e.reason is not None
