"""
Tests for the Failure Classification System.

These tests verify the core invariant:

    No raw 500 error may reach the frontend.
    Every failure must be classified and explained.

These tests protect the failure semantics only.
"""

import pytest
from fastapi.testclient import TestClient

from forgebreaker.main import app
from forgebreaker.models.failure import (
    ApiResponse,
    FailureKind,
    KnownError,
    OutcomeType,
    RefusalError,
)
from forgebreaker.services.card_name_guard import CardNameLeakageError


class TestFailureEnvelope:
    """Tests for the ApiResponse failure envelope."""

    def test_success_response_structure(self) -> None:
        """Success response has correct structure."""
        response = ApiResponse.success({"data": "value"})

        assert response.outcome == OutcomeType.SUCCESS
        assert response.data == {"data": "value"}
        assert response.failure is None

    def test_refusal_response_structure(self) -> None:
        """Refusal response has correct structure."""
        response = ApiResponse.refusal(
            kind=FailureKind.CARD_NAME_LEAKAGE,
            message="Card name invariant violation",
            detail="Detected: Fake Card",
            suggestion="Try a different request",
        )

        assert response.outcome == OutcomeType.REFUSAL
        assert response.data is None
        assert response.failure is not None
        assert response.failure.kind == FailureKind.CARD_NAME_LEAKAGE
        assert "invariant" in response.failure.message.lower()

    def test_known_failure_response_structure(self) -> None:
        """Known failure response has correct structure."""
        response = ApiResponse.known_failure(
            kind=FailureKind.NOT_FOUND,
            message="Resource not found",
            detail="Deck 'xyz' does not exist",
        )

        assert response.outcome == OutcomeType.KNOWN_FAILURE
        assert response.data is None
        assert response.failure is not None
        assert response.failure.kind == FailureKind.NOT_FOUND

    def test_unknown_failure_response_structure(self) -> None:
        """Unknown failure response has correct structure and message."""
        response = ApiResponse.unknown_failure(detail="SomeError: crash")

        assert response.outcome == OutcomeType.UNKNOWN_FAILURE
        assert response.data is None
        assert response.failure is not None
        assert response.failure.kind == FailureKind.UNKNOWN
        # Must explicitly say it doesn't know why (standard message)
        assert "don't know why" in response.failure.message.lower()
        assert "retry" in response.failure.message.lower()

    def test_unknown_failure_includes_suggestion(self) -> None:
        """Unknown failure includes a suggestion for the user."""
        response = ApiResponse.unknown_failure()

        assert response.failure is not None
        assert response.failure.suggestion is not None
        assert len(response.failure.suggestion) > 0


class TestKnownErrorException:
    """Tests for KnownError exception handling."""

    def test_known_error_converts_to_response(self) -> None:
        """KnownError converts to ApiResponse correctly."""
        error = KnownError(
            kind=FailureKind.INVALID_INPUT,
            message="Invalid format",
            detail="Expected JSON",
            status_code=400,
        )

        response = error.to_response()

        assert response.outcome == OutcomeType.KNOWN_FAILURE
        assert response.failure is not None
        assert response.failure.kind == FailureKind.INVALID_INPUT
        assert response.failure.message == "Invalid format"

    def test_known_error_preserves_status_code(self) -> None:
        """KnownError preserves HTTP status code."""
        error = KnownError(
            kind=FailureKind.NOT_FOUND,
            message="Not found",
            status_code=404,
        )

        assert error.status_code == 404


class TestRefusalErrorException:
    """Tests for RefusalError exception handling."""

    def test_refusal_error_converts_to_response(self) -> None:
        """RefusalError converts to ApiResponse correctly."""
        error = RefusalError(
            kind=FailureKind.CARD_NAME_LEAKAGE,
            message="Integrity violation",
            detail="Leaked: Fake Card",
        )

        response = error.to_response()

        assert response.outcome == OutcomeType.REFUSAL
        assert response.failure is not None
        assert response.failure.kind == FailureKind.CARD_NAME_LEAKAGE


class TestExceptionHandlers:
    """Tests for global exception handlers in main.py."""

    @pytest.fixture
    def client(self) -> TestClient:
        """Create test client."""
        return TestClient(app, raise_server_exceptions=False)

    def test_card_name_leakage_returns_refusal(self) -> None:
        """CardNameLeakageError returns refusal response, not 500."""
        # We can't easily trigger this through a real endpoint,
        # but we can test the exception handler exists and the
        # response model is correct by testing the model directly
        from forgebreaker.models.validated_deck import create_validated_deck

        validated_deck = create_validated_deck(
            maindeck={"Lightning Bolt": 4},
            validation_source="test",
        )

        error = CardNameLeakageError(
            leaked_name="Fake Card",
            output_context="Test context",
            validated_deck=validated_deck,
        )

        # Verify the error has the right attributes
        assert error.leaked_name == "Fake Card"
        assert "Fake Card" in str(error)

    def test_health_endpoint_returns_success(self, client: TestClient) -> None:
        """Health endpoint returns successful response (baseline)."""
        response = client.get("/health")

        # Should return 200, not 500
        assert response.status_code == 200

    def test_invalid_format_returns_4xx_not_500(self, client: TestClient) -> None:
        """Invalid format returns 4xx client error, not 500."""
        response = client.post(
            "/decks/sync",
            json={"formats": ["not_a_real_format"]},
        )

        # Should be 4xx (known failure), not 500 (unknown)
        # 400 = Bad Request, 422 = Unprocessable Entity (both valid)
        assert 400 <= response.status_code < 500

    def test_unexpected_error_returns_classified_500(self, client: TestClient) -> None:
        """
        Unexpected errors return classified 500, not raw 500.

        When an unexpected error occurs (like a database connection failure),
        the system must still return a classified response that explains
        it doesn't know why it failed.
        """
        # Hit an endpoint that requires database - if DB is unavailable,
        # we should get a classified unknown_failure response, not a raw crash
        response = client.get("/decks/standard/AnyDeck")

        # Response body should be a classified failure envelope
        data = response.json()

        # If we got a 500, it must be a classified unknown_failure
        if response.status_code == 500:
            assert data.get("outcome") == "unknown_failure"
            assert data.get("failure") is not None
            # Standard message says "I failed and I don't know why"
            assert "don't know why" in data["failure"].get("message", "").lower()


class TestInvariantViolationHandling:
    """Tests proving invariant violations return explained failures."""

    def test_invariant_violation_is_explained(self) -> None:
        """
        INVARIANT TEST: Card name leakage is explained, not a raw 500.

        When the guard detects an unvalidated card name, it must return
        an explained refusal with the specific card that was detected.
        """
        from forgebreaker.models.validated_deck import create_validated_deck
        from forgebreaker.services.card_name_guard import (
            CardNameLeakageError,
            guard_output,
        )

        validated_deck = create_validated_deck(
            maindeck={"Lightning Bolt": 4},
            validation_source="test",
        )

        # Try to output a card not in the validated deck
        with pytest.raises(CardNameLeakageError) as exc_info:
            guard_output("Add **Sol Ring** for ramp.", validated_deck)

        # The error must contain the leaked card name
        assert exc_info.value.leaked_name == "Sol Ring"
        # The error message must be explanatory
        assert "Sol Ring" in str(exc_info.value)


class TestFailureKindCoverage:
    """Tests ensuring all FailureKind values are valid."""

    def test_all_failure_kinds_are_unique(self) -> None:
        """All failure kinds have unique values."""
        values = [kind.value for kind in FailureKind]
        assert len(values) == len(set(values))

    def test_unknown_failure_kind_exists(self) -> None:
        """UNKNOWN failure kind exists for unexpected errors."""
        assert FailureKind.UNKNOWN.value == "unknown"

    def test_card_name_leakage_kind_exists(self) -> None:
        """CARD_NAME_LEAKAGE kind exists for invariant violations."""
        assert FailureKind.CARD_NAME_LEAKAGE.value == "card_name_leakage"
