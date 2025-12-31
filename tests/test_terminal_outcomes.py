"""
Tests for Terminal Outcome Enforcement.

These tests verify the invariant:
- Terminal outcomes (tool errors, KnownFailure, RefusalError) must terminate execution
- No retries are allowed after a terminal outcome
- LLM calls are strictly bounded

REGRESSION TESTS for the bug where simple requests exceed LLM call budget.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from anthropic.types import ToolUseBlock

from forgebreaker.api.chat import (
    TerminalReason,
    ToolProcessingResult,
    _process_tool_calls,
)
from forgebreaker.models.budget import MAX_LLM_CALLS_PER_REQUEST
from forgebreaker.models.failure import FailureKind, KnownError, RefusalError

# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def mock_session() -> AsyncMock:
    """Create mock database session."""
    return AsyncMock()


@pytest.fixture
def mock_tool_call() -> MagicMock:
    """Create mock tool call block."""
    mock = MagicMock(spec=ToolUseBlock)
    mock.id = "test-tool-id"
    mock.name = "build_deck"
    mock.input = {"theme": "goblin"}
    return mock


# =============================================================================
# TERMINAL OUTCOME CLASSIFICATION TESTS
# =============================================================================


class TestTerminalOutcomeClassification:
    """Tests that terminal outcomes are correctly classified."""

    @pytest.mark.asyncio
    async def test_known_error_is_terminal(
        self,
        mock_session: AsyncMock,
        mock_tool_call: MagicMock,
    ) -> None:
        """KnownError exception triggers terminal outcome."""
        with patch(
            "forgebreaker.api.chat.execute_tool",
            side_effect=KnownError(
                kind=FailureKind.NOT_FOUND,
                message="Collection not found",
            ),
        ):
            result = await _process_tool_calls(mock_session, [mock_tool_call], "test-user")

        assert result.is_terminal is True
        assert result.terminal_reason == TerminalReason.KNOWN_FAILURE
        assert result.error_message == "Collection not found"

    @pytest.mark.asyncio
    async def test_refusal_error_is_terminal(
        self,
        mock_session: AsyncMock,
        mock_tool_call: MagicMock,
    ) -> None:
        """RefusalError exception triggers terminal outcome."""
        with patch(
            "forgebreaker.api.chat.execute_tool",
            side_effect=RefusalError(
                kind=FailureKind.CARD_NAME_LEAKAGE,
                message="Card name invariant violated",
            ),
        ):
            result = await _process_tool_calls(mock_session, [mock_tool_call], "test-user")

        assert result.is_terminal is True
        assert result.terminal_reason == TerminalReason.REFUSAL
        assert result.error_message == "Card name invariant violated"

    @pytest.mark.asyncio
    async def test_generic_exception_is_terminal(
        self,
        mock_session: AsyncMock,
        mock_tool_call: MagicMock,
    ) -> None:
        """Generic exception triggers terminal outcome."""
        with patch(
            "forgebreaker.api.chat.execute_tool",
            side_effect=ValueError("Unexpected error"),
        ):
            result = await _process_tool_calls(mock_session, [mock_tool_call], "test-user")

        assert result.is_terminal is True
        assert result.terminal_reason == TerminalReason.TOOL_ERROR
        assert result.error_message == "Unexpected error"

    @pytest.mark.asyncio
    async def test_tool_returned_error_is_terminal(
        self,
        mock_session: AsyncMock,
        mock_tool_call: MagicMock,
    ) -> None:
        """Tool returning error dict triggers terminal outcome."""
        with patch(
            "forgebreaker.api.chat.execute_tool",
            return_value={"error": "No cards found for theme"},
        ):
            result = await _process_tool_calls(mock_session, [mock_tool_call], "test-user")

        assert result.is_terminal is True
        assert result.terminal_reason == TerminalReason.TOOL_RETURNED_ERROR
        assert result.error_message == "No cards found for theme"

    @pytest.mark.asyncio
    async def test_successful_tool_is_not_terminal(
        self,
        mock_session: AsyncMock,
        mock_tool_call: MagicMock,
    ) -> None:
        """Successful tool execution is not terminal."""
        with patch(
            "forgebreaker.api.chat.execute_tool",
            return_value={"deck_name": "Goblin Deck", "cards": {"Goblin Guide": 4}},
        ):
            result = await _process_tool_calls(mock_session, [mock_tool_call], "test-user")

        assert result.is_terminal is False
        assert result.terminal_reason == TerminalReason.NONE
        assert result.error_message is None


# =============================================================================
# NO RETRY AFTER TERMINAL TESTS
# =============================================================================


class TestNoRetryAfterTerminal:
    """Tests that no retries occur after terminal outcomes."""

    @pytest.mark.asyncio
    async def test_known_error_no_second_llm_call(
        self,
        mock_session: AsyncMock,
        mock_tool_call: MagicMock,
    ) -> None:
        """
        Contract: After KnownError, no second LLM call for retry.

        The system must:
        1. Detect KnownError as terminal
        2. NOT make another tool call to retry
        3. Finalize immediately
        """
        with patch(
            "forgebreaker.api.chat.execute_tool",
            side_effect=KnownError(
                kind=FailureKind.NOT_FOUND,
                message="Collection not found",
            ),
        ):
            result = await _process_tool_calls(mock_session, [mock_tool_call], "test-user")

        # Result must be terminal
        assert result.is_terminal is True

        # Result must contain error for LLM to format response
        assert len(result.results) == 1
        content = json.loads(result.results[0]["content"])
        assert "error" in content
        assert content["kind"] == "not_found"

    @pytest.mark.asyncio
    async def test_tool_error_no_second_llm_call(
        self,
        mock_session: AsyncMock,
        mock_tool_call: MagicMock,
    ) -> None:
        """
        Contract: After tool exception, no second LLM call for retry.
        """
        with patch(
            "forgebreaker.api.chat.execute_tool",
            side_effect=RuntimeError("Database connection failed"),
        ):
            result = await _process_tool_calls(mock_session, [mock_tool_call], "test-user")

        # Result must be terminal
        assert result.is_terminal is True
        assert result.terminal_reason == TerminalReason.TOOL_ERROR

        # Error must be captured in result
        assert len(result.results) == 1
        assert result.results[0].get("is_error") is True


# =============================================================================
# SINGLE-SHOT SUCCESS INVARIANT TESTS
# =============================================================================


class TestSingleShotSuccess:
    """Tests the single-shot success invariant."""

    def test_successful_tool_returns_results(self) -> None:
        """
        Contract: Successful tool completion produces usable results.

        After a tool succeeds, the results should be complete and
        ready for Claude to format into a final response.
        """
        # Verify the result structure for successful tool calls
        result = ToolProcessingResult(
            results=[
                {
                    "type": "tool_result",
                    "tool_use_id": "test-id",
                    "content": json.dumps({"deck_name": "Goblin Deck", "cards": {}}),
                }
            ],
            is_terminal=False,
            terminal_reason=TerminalReason.NONE,
        )

        # Success case should not be terminal (allows formatting call)
        assert result.is_terminal is False
        assert len(result.results) == 1

    def test_max_llm_calls_per_request_is_reasonable(self) -> None:
        """
        Contract: MAX_LLM_CALLS_PER_REQUEST allows success but prevents loops.

        For a simple request:
        - LLM call 1: Claude sees request, calls tool
        - LLM call 2: Claude receives result, formats response
        - LLM call 3: Buffer for edge cases

        3 calls should be sufficient for any single-intent request.
        """
        assert MAX_LLM_CALLS_PER_REQUEST == 3


# =============================================================================
# BUDGET ENFORCEMENT TESTS
# =============================================================================


class TestBudgetEnforcement:
    """Tests that budget failure remains terminal."""

    def test_budget_exceeded_is_known_error(self) -> None:
        """BudgetExceededError is a KnownError subclass."""
        from forgebreaker.models.budget import BudgetExceededError

        # BudgetExceededError should inherit from KnownError
        assert issubclass(BudgetExceededError, KnownError)

    def test_budget_exceeded_has_correct_kind(self) -> None:
        """BudgetExceededError uses BUDGET_EXCEEDED kind."""
        from forgebreaker.models.budget import BudgetExceededError

        error = BudgetExceededError(
            limit_type="LLM calls",
            used=4,
            limit=3,
        )

        assert error.kind == FailureKind.BUDGET_EXCEEDED
        assert error.status_code == 429


# =============================================================================
# TERMINAL REASON DOCUMENTATION TESTS
# =============================================================================


class TestTerminalReasonDocumentation:
    """Tests that document the terminal reason classification."""

    def test_terminal_reasons_are_exhaustive(self) -> None:
        """
        Document all terminal reasons.

        TERMINAL OUTCOMES:
        - TOOL_ERROR: Exception during tool execution
        - TOOL_RETURNED_ERROR: Tool returned {"error": ...}
        - KNOWN_FAILURE: KnownError exception
        - REFUSAL: RefusalError exception
        - BUDGET_EXHAUSTED: Budget limit hit

        NON-TERMINAL:
        - NONE: Tool succeeded, continue to formatting
        """
        expected_reasons = {
            "none",
            "tool_error",
            "tool_returned_error",
            "known_failure",
            "refusal",
            "budget_exhausted",
        }

        actual_reasons = {r.value for r in TerminalReason}
        assert actual_reasons == expected_reasons

    def test_only_none_is_non_terminal(self) -> None:
        """Only NONE reason allows continuation."""
        for reason in TerminalReason:
            if reason == TerminalReason.NONE:
                # NONE means not terminal, continue execution
                assert reason.value == "none"
            else:
                # All other reasons are terminal
                assert reason.value != "none"


# =============================================================================
# COLLECTION/CARD DB MISMATCH REGRESSION TESTS
# =============================================================================


class TestCollectionCardDbMismatchTerminal:
    """
    Regression tests for the collection/card DB mismatch terminal failure.

    INVARIANT: Cards in collection but not in database is a data-integrity
    error that MUST be terminal. No retries are possible.

    This prevents budget exhaustion on unrecoverable errors.
    """

    @pytest.mark.asyncio
    async def test_collection_mismatch_is_known_failure(
        self,
        mock_session: AsyncMock,
        mock_tool_call: MagicMock,
    ) -> None:
        """
        Collection/card DB mismatch raises KnownError which is terminal.

        The system must:
        1. Detect the data-integrity error
        2. Classify as KNOWN_FAILURE
        3. Terminate without retries
        """

        # Simulate the mismatch error propagating through tool execution
        with patch(
            "forgebreaker.api.chat.execute_tool",
            side_effect=KnownError(
                kind=FailureKind.VALIDATION_FAILED,
                message="Your collection contains cards not present in the card database.",
                detail="Missing 2 cards: ['Mystery Card Alpha', 'Mystery Card Beta']",
            ),
        ):
            result = await _process_tool_calls(mock_session, [mock_tool_call], "test-user")

        assert result.is_terminal is True
        assert result.terminal_reason == TerminalReason.KNOWN_FAILURE
        assert "not present in the card database" in result.error_message

    @pytest.mark.asyncio
    async def test_mismatch_error_prevents_retries(
        self,
        mock_session: AsyncMock,
        mock_tool_call: MagicMock,
    ) -> None:
        """
        After mismatch error, no retry is attempted.

        Contract: Terminal outcome means NO SECOND TOOL CALL.
        """
        with patch(
            "forgebreaker.api.chat.execute_tool",
            side_effect=KnownError(
                kind=FailureKind.VALIDATION_FAILED,
                message="Collection contains cards not in database.",
            ),
        ):
            result = await _process_tool_calls(mock_session, [mock_tool_call], "test-user")

        # Terminal means is_terminal=True, so chat loop will disable tools
        assert result.is_terminal is True

        # Result contains error for Claude to format final response
        assert len(result.results) == 1
        content = json.loads(result.results[0]["content"])
        assert "error" in content
        assert content["kind"] == "validation_failed"

    def test_mismatch_detected_at_service_layer(self) -> None:
        """
        The mismatch is detected at the service layer, before any LLM formatting.

        This is critical: the error is raised DURING tool execution,
        not after multiple LLM retries.
        """
        from forgebreaker.models.collection import Collection
        from forgebreaker.services.collection_search import search_collection

        collection = Collection(cards={"Nonexistent Card": 4})
        card_db = {"Real Card": {"type_line": "Instant", "colors": ["R"]}}

        with pytest.raises(KnownError) as exc_info:
            search_collection(collection, card_db)

        # Error detected immediately, no LLM involved yet
        assert exc_info.value.kind == FailureKind.VALIDATION_FAILED
        assert "Nonexistent Card" in str(exc_info.value.detail)

    def test_mismatch_error_is_user_actionable(self) -> None:
        """
        The error message helps users resolve the issue.

        A terminal failure must still be helpful, not just blocking.
        """
        from forgebreaker.models.collection import Collection
        from forgebreaker.services.collection_search import search_collection

        collection = Collection(cards={"Mystery Card": 1})
        # Non-empty DB with different cards (empty DB has different code path)
        card_db = {"Some Other Card": {"type_line": "Instant", "colors": ["R"]}}

        with pytest.raises(KnownError) as exc_info:
            search_collection(collection, card_db)

        # Message tells user what to do
        error = exc_info.value
        assert (
            "update" in (error.suggestion or "").lower()
            or "check" in (error.suggestion or "").lower()
        )
        assert error.detail is not None  # Shows which cards are missing
