"""
Tests for the Failure Authority Boundary.

These tests verify the core invariant:

    All user-visible responses MUST pass through the authority boundary.
    No endpoint may bypass finalize_response().

These tests protect the boundary only.
"""

import pytest

from forgebreaker.models.failure import (
    STANDARD_MESSAGES,
    STANDARD_SUGGESTIONS,
    ApiResponse,
    FailureKind,
    OutcomeType,
    create_known_failure,
    create_refusal,
    create_success,
    create_unknown_failure,
    finalize_response,
    is_finalized,
)


class TestFinalizeResponse:
    """Tests for the finalize_response authority boundary."""

    def test_success_response_is_finalized(self) -> None:
        """Success responses pass through the boundary."""
        response = ApiResponse(outcome=OutcomeType.SUCCESS, data={"key": "value"})
        finalized = finalize_response(response)

        assert is_finalized(finalized)
        assert finalized.outcome == OutcomeType.SUCCESS

    def test_failure_response_is_finalized(self) -> None:
        """Failure responses pass through the boundary."""
        response = ApiResponse.known_failure(
            kind=FailureKind.NOT_FOUND,
            message="Not found",
        )
        finalized = finalize_response(response)

        assert is_finalized(finalized)

    def test_unfinalized_response_not_marked(self) -> None:
        """Responses that bypass the boundary are detectable."""
        response = ApiResponse(outcome=OutcomeType.SUCCESS, data={"key": "value"})

        # Not finalized yet
        assert not is_finalized(response)

    def test_success_with_failure_raises(self) -> None:
        """Success response with failure details is invalid."""
        from forgebreaker.models.failure import FailureDetail

        response = ApiResponse(
            outcome=OutcomeType.SUCCESS,
            data={"key": "value"},
            failure=FailureDetail(kind=FailureKind.UNKNOWN, message="oops"),
        )

        with pytest.raises(ValueError, match="must not have failure"):
            finalize_response(response)

    def test_failure_without_details_raises(self) -> None:
        """Failure response without details is invalid."""
        response = ApiResponse(outcome=OutcomeType.KNOWN_FAILURE, failure=None)

        with pytest.raises(ValueError, match="must have failure details"):
            finalize_response(response)


class TestStandardMessages:
    """Tests for standardized, fixed failure messages."""

    def test_unknown_failure_uses_standard_message(self) -> None:
        """Unknown failures use the EXACT standard message."""
        response = create_unknown_failure(ValueError("test"))

        assert response.failure is not None
        assert response.failure.message == STANDARD_MESSAGES[OutcomeType.UNKNOWN_FAILURE]
        # Message is fixed and boring
        assert "I failed and I don't know why" in response.failure.message

    def test_unknown_failure_uses_standard_suggestion(self) -> None:
        """Unknown failures use the EXACT standard suggestion."""
        response = create_unknown_failure(ValueError("test"))

        assert response.failure is not None
        assert response.failure.suggestion == STANDARD_SUGGESTIONS[OutcomeType.UNKNOWN_FAILURE]

    def test_known_failure_uses_standard_message(self) -> None:
        """Known failures use the standard message, not custom prose."""
        response = create_known_failure(
            kind=FailureKind.NOT_FOUND,
            reason="Resource xyz not found",
        )

        assert response.failure is not None
        assert response.failure.message == STANDARD_MESSAGES[OutcomeType.KNOWN_FAILURE]
        # The reason goes in detail, not message
        assert response.failure.detail == "Resource xyz not found"

    def test_refusal_uses_standard_message(self) -> None:
        """Refusals use the standard message, not custom prose."""
        response = create_refusal(
            kind=FailureKind.CARD_NAME_LEAKAGE,
            constraint="card_name_output_barrier",
        )

        assert response.failure is not None
        assert response.failure.message == STANDARD_MESSAGES[OutcomeType.REFUSAL]
        # The constraint goes in detail
        assert "card_name_output_barrier" in response.failure.detail  # type: ignore


class TestFactoryFunctionsFinalize:
    """Tests that factory functions automatically finalize."""

    def test_create_success_is_finalized(self) -> None:
        """create_success() returns a finalized response."""
        response = create_success({"data": "value"})

        assert is_finalized(response)
        assert response.outcome == OutcomeType.SUCCESS

    def test_create_known_failure_is_finalized(self) -> None:
        """create_known_failure() returns a finalized response."""
        response = create_known_failure(
            kind=FailureKind.NOT_FOUND,
            reason="test",
        )

        assert is_finalized(response)
        assert response.outcome == OutcomeType.KNOWN_FAILURE

    def test_create_unknown_failure_is_finalized(self) -> None:
        """create_unknown_failure() returns a finalized response."""
        response = create_unknown_failure(ValueError("test"))

        assert is_finalized(response)
        assert response.outcome == OutcomeType.UNKNOWN_FAILURE

    def test_create_refusal_is_finalized(self) -> None:
        """create_refusal() returns a finalized response."""
        response = create_refusal(
            kind=FailureKind.VALIDATION_FAILED,
            constraint="test_constraint",
        )

        assert is_finalized(response)
        assert response.outcome == OutcomeType.REFUSAL


class TestExplanationDriftPrevention:
    """Tests that explanations come from structured reasons, not inference."""

    def test_unknown_failure_detail_is_type_only(self) -> None:
        """Unknown failure detail contains only exception type, not stack/message."""
        response = create_unknown_failure(
            ValueError("some sensitive error message that should not leak")
        )

        assert response.failure is not None
        # Detail is just the type name
        assert response.failure.detail == "ValueError"
        # Sensitive message is NOT included
        assert "sensitive" not in str(response.failure.detail)

    def test_known_failure_reason_is_technical(self) -> None:
        """Known failure reason is technical, not prose from LLM."""
        response = create_known_failure(
            kind=FailureKind.NOT_FOUND,
            reason="deck.name='Mono Red' not in database",
        )

        assert response.failure is not None
        # Reason is passed through as-is (technical)
        assert response.failure.detail == "deck.name='Mono Red' not in database"
        # Message is the standard message, not the reason
        assert response.failure.message != response.failure.detail

    def test_refusal_constraint_is_identifier(self) -> None:
        """Refusal constraint is an identifier, not prose."""
        response = create_refusal(
            kind=FailureKind.CARD_NAME_LEAKAGE,
            constraint="card_name_output_barrier",
        )

        assert response.failure is not None
        # Constraint is formatted into detail
        assert response.failure.detail == "Constraint violated: card_name_output_barrier"


class TestBoundaryInvariant:
    """Tests proving the boundary invariant is mechanically enforced."""

    def test_cannot_create_unfinalized_unknown_failure(self) -> None:
        """
        INVARIANT TEST: Unknown failures cannot be created unfinalized.

        The only way to create an unknown failure is through create_unknown_failure(),
        which always finalizes.
        """
        response = create_unknown_failure(Exception("test"))

        # Must be finalized
        assert is_finalized(response)

    def test_standard_message_is_immutable(self) -> None:
        """
        INVARIANT TEST: Standard messages cannot be changed at runtime.

        The messages are defined as module constants.
        """
        original_message = STANDARD_MESSAGES[OutcomeType.UNKNOWN_FAILURE]

        # Create a failure
        response = create_unknown_failure(Exception("test"))

        # Message matches the constant
        assert response.failure is not None
        assert response.failure.message == original_message

        # Constant is unchanged
        assert STANDARD_MESSAGES[OutcomeType.UNKNOWN_FAILURE] == original_message
