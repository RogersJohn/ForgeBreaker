"""
Failure Explanation Envelope — Unified Response Classification.

This module defines the response envelope that ALL API endpoints must use
to communicate outcomes to the frontend. Every user-visible failure must
be classified and explained.

INVARIANT: No raw 500 errors may reach the frontend.

Response types:
- Success: Operation completed successfully
- Refusal: System chose not to proceed (expected, explainable)
- KnownFailure: System knows why it failed
- UnknownFailure: System does not know why it failed

AUTHORITY BOUNDARY:
All user-visible responses MUST pass through `finalize_response()`.
This is the single exit point that guarantees failure classification.

This is enforced by code, not convention.
"""

from enum import Enum
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field


class FailureKind(str, Enum):
    """Classification of failure types."""

    # Input validation failures
    INVALID_INPUT = "invalid_input"
    MISSING_REQUIRED = "missing_required"

    # Resource failures
    NOT_FOUND = "not_found"
    EMPTY_RESULT = "empty_result"

    # Constraint violations
    CARD_NAME_LEAKAGE = "card_name_leakage"
    VALIDATION_FAILED = "validation_failed"
    FORMAT_ILLEGAL = "format_illegal"
    BUDGET_EXCEEDED = "budget_exceeded"
    DECK_SIZE_VIOLATION = "deck_size_violation"

    # Service failures
    SERVICE_UNAVAILABLE = "service_unavailable"
    EXTERNAL_API_ERROR = "external_api_error"

    # Internal errors
    INVARIANT_VIOLATION = "invariant_violation"

    # Unknown
    UNKNOWN = "unknown"


class OutcomeType(str, Enum):
    """High-level outcome classification."""

    SUCCESS = "success"
    REFUSAL = "refusal"
    KNOWN_FAILURE = "known_failure"
    UNKNOWN_FAILURE = "unknown_failure"


T = TypeVar("T")


class FailureDetail(BaseModel):
    """Detailed information about a failure."""

    kind: FailureKind = Field(
        ...,
        description="Classification of the failure",
    )
    message: str = Field(
        ...,
        description="User-appropriate explanation of what went wrong",
    )
    detail: str | None = Field(
        default=None,
        description="Additional technical detail (optional)",
    )
    suggestion: str | None = Field(
        default=None,
        description="Suggested action for the user",
    )


class ApiResponse(BaseModel, Generic[T]):
    """
    Universal response envelope for all API endpoints.

    Every response is classified into one of four outcome types,
    ensuring no failure reaches the user unexplained.
    """

    outcome: OutcomeType = Field(
        ...,
        description="High-level classification of the result",
    )
    data: T | None = Field(
        default=None,
        description="Response data (present on success)",
    )
    failure: FailureDetail | None = Field(
        default=None,
        description="Failure details (present on non-success)",
    )

    @classmethod
    def success(cls, data: T) -> "ApiResponse[T]":
        """Create a success response."""
        return cls(outcome=OutcomeType.SUCCESS, data=data)

    @classmethod
    def refusal(
        cls,
        kind: FailureKind,
        message: str,
        detail: str | None = None,
        suggestion: str | None = None,
    ) -> "ApiResponse[Any]":
        """
        Create a refusal response.

        Use when the system chose not to proceed due to a constraint.
        Example: Card name invariant violation.
        """
        return cls(
            outcome=OutcomeType.REFUSAL,
            failure=FailureDetail(
                kind=kind,
                message=message,
                detail=detail,
                suggestion=suggestion,
            ),
        )

    @classmethod
    def known_failure(
        cls,
        kind: FailureKind,
        message: str,
        detail: str | None = None,
        suggestion: str | None = None,
    ) -> "ApiResponse[Any]":
        """
        Create a known failure response.

        Use when the system knows exactly why the operation failed.
        Example: Resource not found, invalid input format.
        """
        return cls(
            outcome=OutcomeType.KNOWN_FAILURE,
            failure=FailureDetail(
                kind=kind,
                message=message,
                detail=detail,
                suggestion=suggestion,
            ),
        )

    @classmethod
    def unknown_failure(
        cls,
        detail: str | None = None,
    ) -> "ApiResponse[Any]":
        """
        Create an unknown failure response.

        Use when the system does not know why it failed.
        This is the catch-all for unexpected exceptions.

        NOTE: Prefer create_unknown_failure() which auto-finalizes.
        """
        return cls(
            outcome=OutcomeType.UNKNOWN_FAILURE,
            failure=FailureDetail(
                kind=FailureKind.UNKNOWN,
                # Use the standard message - fixed and boring
                message=("I failed and I don't know why. Try simplifying the request or retrying."),
                detail=detail,
                suggestion="If this persists, please report the issue.",
            ),
        )


# Standard exception types that map to known failures


class KnownError(Exception):
    """
    Base class for exceptions that represent known, explainable failures.

    Subclass this for errors where the system knows exactly what went wrong.
    """

    def __init__(
        self,
        kind: FailureKind,
        message: str,
        detail: str | None = None,
        suggestion: str | None = None,
        status_code: int = 400,
    ):
        self.kind = kind
        self.message = message
        self.detail = detail
        self.suggestion = suggestion
        self.status_code = status_code
        super().__init__(message)

    def to_response(self) -> ApiResponse[Any]:
        """Convert to an ApiResponse."""
        return ApiResponse.known_failure(
            kind=self.kind,
            message=self.message,
            detail=self.detail,
            suggestion=self.suggestion,
        )


class RefusalError(Exception):
    """
    Exception for constraint-based refusals.

    Use when the system refuses to proceed due to an integrity constraint.
    Example: Card name invariant violation.
    """

    def __init__(
        self,
        kind: FailureKind,
        message: str,
        detail: str | None = None,
        suggestion: str | None = None,
    ):
        self.kind = kind
        self.message = message
        self.detail = detail
        self.suggestion = suggestion
        super().__init__(message)

    def to_response(self) -> ApiResponse[Any]:
        """Convert to an ApiResponse."""
        return ApiResponse.refusal(
            kind=self.kind,
            message=self.message,
            detail=self.detail,
            suggestion=self.suggestion,
        )


class DeckSizeError(KnownError):
    """
    Exception for deck size constraint violations.

    Raised when the deck builder cannot construct a deck of the requested size.
    This is a hard failure - undersized decks are never acceptable.
    """

    def __init__(
        self,
        requested_size: int,
        actual_size: int,
        detail: str | None = None,
    ):
        self.requested_size = requested_size
        self.actual_size = actual_size
        message = (
            f"Unable to construct a {requested_size}-card deck. "
            f"Only {actual_size} cards available with the given constraints."
        )
        super().__init__(
            kind=FailureKind.DECK_SIZE_VIOLATION,
            message=message,
            detail=detail,
            suggestion="Try relaxing color or theme constraints, or import more cards.",
            status_code=400,
        )


# =============================================================================
# FAILURE AUTHORITY BOUNDARY
# =============================================================================
#
# All user-visible responses MUST pass through this boundary.
# This is the ONLY exit point for API responses.
#
# =============================================================================


# Standard messages — fixed, boring, predictable
# These MUST NOT vary based on runtime inference or LLM output.

STANDARD_MESSAGES: dict[OutcomeType, str] = {
    OutcomeType.REFUSAL: (
        "The system cannot proceed with this request due to a constraint violation."
    ),
    OutcomeType.KNOWN_FAILURE: "The operation failed due to a known issue.",
    OutcomeType.UNKNOWN_FAILURE: (
        "I failed and I don't know why. Try simplifying the request or retrying."
    ),
}

STANDARD_SUGGESTIONS: dict[OutcomeType, str] = {
    OutcomeType.REFUSAL: "Please modify your request to satisfy the constraint.",
    OutcomeType.KNOWN_FAILURE: "Check the error details and adjust your request.",
    OutcomeType.UNKNOWN_FAILURE: "If this persists, please report the issue.",
}


class _FinalizedMarker:
    """
    Internal marker indicating a response has passed through the authority boundary.

    This class is not exported. It exists only to detect boundary bypass.
    """

    __slots__ = ("_finalized",)

    def __init__(self) -> None:
        self._finalized = True


# Track finalized responses (weak reference would be ideal, but dict is simpler)
_finalized_responses: set[int] = set()


def finalize_response(response: ApiResponse[Any]) -> ApiResponse[Any]:
    """
    Finalize a response through the authority boundary.

    This is the SINGLE exit point for all user-visible responses.
    Every response that passes through this function is guaranteed to:
    1. Have a valid outcome classification
    2. Have appropriate failure details if not successful
    3. Use standardized, predictable language

    Args:
        response: The ApiResponse to finalize

    Returns:
        The same response, marked as having passed through the boundary

    Raises:
        ValueError: If response structure is invalid
    """
    # Validate response structure
    if response.outcome == OutcomeType.SUCCESS:
        if response.failure is not None:
            raise ValueError("Success response must not have failure details")
    else:
        if response.failure is None:
            raise ValueError(f"{response.outcome.value} response must have failure details")

    # Mark as finalized
    _finalized_responses.add(id(response))

    return response


def is_finalized(response: ApiResponse[Any]) -> bool:
    """
    Check if a response has passed through the authority boundary.

    This is used by tests to verify that no endpoint bypasses the boundary.

    Args:
        response: The ApiResponse to check

    Returns:
        True if the response was finalized, False otherwise
    """
    return id(response) in _finalized_responses


def create_unknown_failure(
    exception: Exception,
    include_type: bool = True,
) -> ApiResponse[Any]:
    """
    Create an unknown failure response from an exception.

    This is the ONLY way to create an unknown failure response.
    The message is fixed and cannot be customized.

    Args:
        exception: The exception that caused the failure
        include_type: Whether to include exception type in detail

    Returns:
        A finalized unknown failure response
    """
    detail = None
    if include_type:
        detail = f"{type(exception).__name__}"

    response: ApiResponse[Any] = ApiResponse(
        outcome=OutcomeType.UNKNOWN_FAILURE,
        failure=FailureDetail(
            kind=FailureKind.UNKNOWN,
            message=STANDARD_MESSAGES[OutcomeType.UNKNOWN_FAILURE],
            detail=detail,
            suggestion=STANDARD_SUGGESTIONS[OutcomeType.UNKNOWN_FAILURE],
        ),
    )

    return finalize_response(response)


def create_known_failure(
    kind: FailureKind,
    reason: str,
) -> ApiResponse[Any]:
    """
    Create a known failure response.

    The message is standardized. Only the reason (technical detail) varies.

    Args:
        kind: The classification of the failure
        reason: Technical description of what went wrong (not user-facing prose)

    Returns:
        A finalized known failure response
    """
    response: ApiResponse[Any] = ApiResponse(
        outcome=OutcomeType.KNOWN_FAILURE,
        failure=FailureDetail(
            kind=kind,
            message=STANDARD_MESSAGES[OutcomeType.KNOWN_FAILURE],
            detail=reason,
            suggestion=STANDARD_SUGGESTIONS[OutcomeType.KNOWN_FAILURE],
        ),
    )

    return finalize_response(response)


def create_refusal(
    kind: FailureKind,
    constraint: str,
) -> ApiResponse[Any]:
    """
    Create a refusal response.

    The message is standardized. Only the constraint name varies.

    Args:
        kind: The classification of the constraint violation
        constraint: Name of the constraint that was violated (not prose)

    Returns:
        A finalized refusal response
    """
    response: ApiResponse[Any] = ApiResponse(
        outcome=OutcomeType.REFUSAL,
        failure=FailureDetail(
            kind=kind,
            message=STANDARD_MESSAGES[OutcomeType.REFUSAL],
            detail=f"Constraint violated: {constraint}",
            suggestion=STANDARD_SUGGESTIONS[OutcomeType.REFUSAL],
        ),
    )

    return finalize_response(response)


def create_success(data: T) -> ApiResponse[T]:
    """
    Create a success response.

    Args:
        data: The response data

    Returns:
        A finalized success response
    """
    response = ApiResponse[T](outcome=OutcomeType.SUCCESS, data=data)
    return finalize_response(response)
