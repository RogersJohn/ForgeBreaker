"""
Tests for the Card Name Guard — Output Barrier Invariant.

These tests verify the core system invariant:

    No user-visible string may contain a card name unless that name
    is present in a ValidatedDeck object.

These tests MUST fail on any codebase that allows card name leakage.
"""

import pytest

from forgebreaker.models.validated_deck import ValidatedDeck, create_validated_deck
from forgebreaker.services.card_name_guard import (
    CardNameLeakageError,
    create_refusal_response,
    extract_potential_card_names,
    guard_output,
    validate_output_card_names,
)


class TestCardNameExtraction:
    """Tests for extracting potential card names from text."""

    def test_extracts_quantity_prefixed_names(self) -> None:
        """Detects 'Nx Card Name' pattern."""
        text = "4x Lightning Bolt\n2 Mountain"
        names = extract_potential_card_names(text)

        assert "Lightning Bolt" in names
        assert "Mountain" in names

    def test_extracts_markdown_bold_names(self) -> None:
        """Detects **Card Name** pattern."""
        text = "Replace with **Counterspell** for better control."
        names = extract_potential_card_names(text)

        assert "Counterspell" in names

    def test_extracts_bracket_references(self) -> None:
        """Detects [Card Name] pattern."""
        text = "[Lightning Bolt]: Deal 3 damage."
        names = extract_potential_card_names(text)

        assert "Lightning Bolt" in names

    def test_ignores_non_card_words(self) -> None:
        """Does not extract common non-card words."""
        text = "**Deck Analysis** shows issues."
        names = extract_potential_card_names(text)

        assert "Deck Analysis" not in names
        assert "Deck" not in names

    def test_handles_empty_string(self) -> None:
        """Returns empty set for empty input."""
        names = extract_potential_card_names("")
        assert names == set()


class TestValidateOutputCardNames:
    """Tests for validating card names against a ValidatedDeck."""

    @pytest.fixture
    def validated_deck(self) -> ValidatedDeck:
        """Create a validated deck with known cards."""
        return create_validated_deck(
            maindeck={"Lightning Bolt": 4, "Mountain": 20, "Monastery Swiftspear": 4},
            name="Test Deck",
            format_name="standard",
            validation_source="test",
        )

    def test_valid_output_passes(self, validated_deck: ValidatedDeck) -> None:
        """Output with only validated cards passes."""
        output = "4x Lightning Bolt\n20x Mountain"
        result = validate_output_card_names(output, validated_deck)

        assert result.valid is True
        assert result.leaked_names == ()

    def test_invalid_card_detected(self, validated_deck: ValidatedDeck) -> None:
        """Output with unvalidated card is detected."""
        output = "4x Lightning Bolt\n4x Hallucinated Card"
        result = validate_output_card_names(output, validated_deck)

        assert result.valid is False
        assert "Hallucinated Card" in result.leaked_names

    def test_additional_allowed_permits_extra_cards(self, validated_deck: ValidatedDeck) -> None:
        """Additional allowed set permits extra card names."""
        output = "Consider adding **Counterspell** from your collection."
        additional = frozenset(["Counterspell", "Cancel"])

        result = validate_output_card_names(output, validated_deck, additional)

        assert result.valid is True

    def test_empty_output_is_valid(self, validated_deck: ValidatedDeck) -> None:
        """Empty output is always valid."""
        result = validate_output_card_names("", validated_deck)

        assert result.valid is True
        assert result.checked_count == 0


class TestGuardOutput:
    """Tests for the guard_output function — the final barrier."""

    @pytest.fixture
    def validated_deck(self) -> ValidatedDeck:
        """Create a validated deck with known cards."""
        return create_validated_deck(
            maindeck={"Lightning Bolt": 4, "Mountain": 20},
            name="Test Deck",
            format_name="standard",
            validation_source="test",
        )

    def test_valid_output_returned_unchanged(self, validated_deck: ValidatedDeck) -> None:
        """Valid output is returned unchanged."""
        output = "4x Lightning Bolt"
        result = guard_output(output, validated_deck)

        assert result == output

    def test_invalid_card_raises_error(self, validated_deck: ValidatedDeck) -> None:
        """Invalid card name raises CardNameLeakageError."""
        # Use markdown bold for clear card name boundary
        output = "Add **Counterspell** to improve control."

        with pytest.raises(CardNameLeakageError) as exc_info:
            guard_output(output, validated_deck)

        assert "Counterspell" in str(exc_info.value)
        assert exc_info.value.leaked_name == "Counterspell"

    def test_leakage_error_contains_context(self, validated_deck: ValidatedDeck) -> None:
        """Leakage error contains output context for debugging."""
        # Use bracket notation for clear card name boundary
        output = "Replace Mountain with [Hallucinated Card] for better fixing."

        with pytest.raises(CardNameLeakageError) as exc_info:
            guard_output(output, validated_deck)

        assert "Hallucinated Card" in exc_info.value.output_context


class TestInvariantEnforcement:
    """
    Tests that prove the invariant is enforced.

    These tests MUST fail on any codebase that allows card name leakage.
    """

    def test_post_validation_injection_is_blocked(self) -> None:
        """
        INVARIANT TEST: Card names added AFTER validation are blocked.

        This simulates a scenario where the model or formatting layer
        attempts to introduce a card name that wasn't in the validated deck.
        """
        # Deck was validated with these cards only
        validated_deck = create_validated_deck(
            maindeck={"Lightning Bolt": 4, "Mountain": 20},
            validation_source="test",
        )

        # But the output somehow contains a different card
        malicious_output = """
        ## Deck Analysis
        Your deck looks good! Consider adding **Sol Ring** for ramp.
        - 4x Lightning Bolt
        - 20x Mountain
        """

        # The guard MUST detect and block this
        with pytest.raises(CardNameLeakageError) as exc_info:
            guard_output(malicious_output, validated_deck)

        assert exc_info.value.leaked_name == "Sol Ring"

    def test_explanation_cannot_introduce_new_cards(self) -> None:
        """
        INVARIANT TEST: Explanation text cannot introduce cards not in deck.

        Even if the explanation sounds helpful, it must not name cards
        that weren't in the validated deck.
        """
        validated_deck = create_validated_deck(
            maindeck={"Monastery Swiftspear": 4},
            validation_source="test",
        )

        # This explanation helpfully suggests a card, but it's not allowed
        explanation = """
        [Monastery Swiftspear]: Great 1-drop for aggro.
        Consider [Goblin Guide] as another excellent option.
        """

        with pytest.raises(CardNameLeakageError) as exc_info:
            guard_output(explanation, validated_deck)

        assert exc_info.value.leaked_name == "Goblin Guide"

    def test_partial_failure_returns_refusal(self) -> None:
        """
        INVARIANT TEST: Partial failures result in refusal, not best-effort.

        If any part of the output contains an invalid card name,
        the entire response is refused — no partial output.
        """
        validated_deck = create_validated_deck(
            maindeck={"Lightning Bolt": 4},
            validation_source="test",
        )

        # Output has some valid cards but also invalid ones
        partial_output = """
        ## Your Deck
        - 4x Lightning Bolt (valid)
        - 4x Counterspell (NOT in validated deck)
        """

        # Must raise, not return partial output
        with pytest.raises(CardNameLeakageError):
            guard_output(partial_output, validated_deck)


class TestRefusalResponse:
    """Tests for the refusal response generation."""

    def test_refusal_contains_error_details(self) -> None:
        """Refusal response contains appropriate error information."""
        validated_deck = create_validated_deck(
            maindeck={"Lightning Bolt": 4},
            validation_source="test",
        )

        error = CardNameLeakageError(
            leaked_name="Fake Card",
            output_context="Some output with Fake Card",
            validated_deck=validated_deck,
        )

        response = create_refusal_response(error)

        assert response["success"] is False
        assert response["error"] == "card_name_invariant_violation"
        assert "invalid card reference" in response["message"].lower()
        assert "Fake Card" in response["detail"]

    def test_refusal_message_is_user_appropriate(self) -> None:
        """Refusal message is appropriate for user display."""
        validated_deck = create_validated_deck(maindeck={}, validation_source="test")

        error = CardNameLeakageError(
            leaked_name="Test",
            output_context="Test",
            validated_deck=validated_deck,
        )

        response = create_refusal_response(error)

        # Should not expose internal details
        assert "INVARIANT" not in response["message"]
        assert "stack" not in response["message"].lower()


class TestValidatedDeck:
    """Tests for the ValidatedDeck model."""

    def test_immutable_after_creation(self) -> None:
        """ValidatedDeck cannot be modified after creation."""
        deck = create_validated_deck(
            maindeck={"Lightning Bolt": 4},
            validation_source="test",
        )

        # Should raise on attempt to modify
        with pytest.raises(AttributeError):
            deck.cards = frozenset(["New Card"])  # type: ignore

    def test_contains_check(self) -> None:
        """Card membership can be checked."""
        deck = create_validated_deck(
            maindeck={"Lightning Bolt": 4, "Mountain": 20},
            validation_source="test",
        )

        assert "Lightning Bolt" in deck
        assert "Mountain" in deck
        assert "Counterspell" not in deck

    def test_includes_sideboard_cards(self) -> None:
        """Sideboard cards are included in validated set."""
        deck = create_validated_deck(
            maindeck={"Lightning Bolt": 4},
            sideboard={"Pyroblast": 2},
            validation_source="test",
        )

        assert "Lightning Bolt" in deck
        assert "Pyroblast" in deck
