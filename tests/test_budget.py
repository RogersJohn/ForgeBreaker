"""
Tests for Request Budget Enforcement (PR 5).

These tests verify:
1. LLM call cap enforcement
2. Token cap enforcement
3. Terminal failure behavior (no retry after failure)
4. Guard memoization (same output rejected once, guard runs once)
5. Budget finalization prevents further operations
"""

import pytest

from forgebreaker.models.budget import (
    MAX_LLM_CALLS_PER_REQUEST,
    MAX_TOKENS_PER_REQUEST,
    BudgetExceededError,
    RequestBudget,
)
from forgebreaker.models.failure import FailureKind

# =============================================================================
# CONSTANTS TESTS
# =============================================================================


class TestBudgetConstants:
    """Verify hard limits are defined correctly."""

    def test_max_llm_calls_is_3(self) -> None:
        """MAX_LLM_CALLS_PER_REQUEST must be 3."""
        assert MAX_LLM_CALLS_PER_REQUEST == 3

    def test_max_tokens_is_20000(self) -> None:
        """MAX_TOKENS_PER_REQUEST must be 20,000."""
        assert MAX_TOKENS_PER_REQUEST == 20_000


# =============================================================================
# REQUEST BUDGET INITIALIZATION
# =============================================================================


class TestRequestBudgetInit:
    """Test RequestBudget initialization."""

    def test_default_limits(self) -> None:
        """Budget uses constants as defaults."""
        budget = RequestBudget()
        assert budget.max_llm_calls == MAX_LLM_CALLS_PER_REQUEST
        assert budget.max_tokens == MAX_TOKENS_PER_REQUEST

    def test_custom_limits(self) -> None:
        """Budget accepts custom limits."""
        budget = RequestBudget(max_llm_calls=5, max_tokens=10_000)
        assert budget.max_llm_calls == 5
        assert budget.max_tokens == 10_000

    def test_initial_state(self) -> None:
        """Budget starts with zero usage and not finalized."""
        budget = RequestBudget()
        assert budget.llm_calls_used == 0
        assert budget.tokens_used == 0
        assert not budget.is_finalized

    def test_remaining_calls_initial(self) -> None:
        """Remaining calls equals max at start."""
        budget = RequestBudget(max_llm_calls=3)
        assert budget.remaining_calls == 3

    def test_remaining_tokens_initial(self) -> None:
        """Remaining tokens equals max at start."""
        budget = RequestBudget(max_tokens=20_000)
        assert budget.remaining_tokens == 20_000


# =============================================================================
# LLM CALL CAP ENFORCEMENT
# =============================================================================


class TestLLMCallCap:
    """Test LLM call limit enforcement."""

    def test_check_allows_first_call(self) -> None:
        """First call check passes."""
        budget = RequestBudget(max_llm_calls=3)
        budget.check_call_budget()  # Should not raise

    def test_record_increments_call_count(self) -> None:
        """Recording a call increments the counter."""
        budget = RequestBudget(max_llm_calls=3)
        budget.check_call_budget()
        budget.record_call(100, 50)
        assert budget.llm_calls_used == 1

    def test_allows_up_to_max_calls(self) -> None:
        """Budget allows exactly max_llm_calls calls."""
        budget = RequestBudget(max_llm_calls=3, max_tokens=100_000)

        for _ in range(3):
            budget.check_call_budget()
            budget.record_call(100, 50)

        assert budget.llm_calls_used == 3

    def test_exceeds_call_limit_raises_terminal_error(self) -> None:
        """Exceeding call limit raises BudgetExceededError."""
        budget = RequestBudget(max_llm_calls=2, max_tokens=100_000)

        # Use up budget
        for _ in range(2):
            budget.check_call_budget()
            budget.record_call(100, 50)

        # Next check should fail
        with pytest.raises(BudgetExceededError) as exc_info:
            budget.check_call_budget()

        assert exc_info.value.limit_type == "LLM calls"
        assert exc_info.value.used == 2
        assert exc_info.value.limit == 2
        assert exc_info.value.kind == FailureKind.BUDGET_EXCEEDED

    def test_call_limit_error_is_terminal(self) -> None:
        """After call limit error, budget is finalized."""
        budget = RequestBudget(max_llm_calls=1, max_tokens=100_000)

        budget.check_call_budget()
        budget.record_call(100, 50)

        with pytest.raises(BudgetExceededError):
            budget.check_call_budget()

        assert budget.is_finalized

    def test_remaining_calls_decrements(self) -> None:
        """Remaining calls decreases with each call."""
        budget = RequestBudget(max_llm_calls=3, max_tokens=100_000)

        budget.check_call_budget()
        budget.record_call(100, 50)
        assert budget.remaining_calls == 2

        budget.check_call_budget()
        budget.record_call(100, 50)
        assert budget.remaining_calls == 1


# =============================================================================
# TOKEN CAP ENFORCEMENT
# =============================================================================


class TestTokenCap:
    """Test token limit enforcement."""

    def test_record_adds_tokens(self) -> None:
        """Recording a call adds input + output tokens."""
        budget = RequestBudget(max_tokens=20_000)
        budget.check_call_budget()
        budget.record_call(1000, 500)
        assert budget.tokens_used == 1500

    def test_allows_up_to_max_tokens(self) -> None:
        """Budget allows up to max_tokens."""
        budget = RequestBudget(max_llm_calls=10, max_tokens=5000)

        budget.check_call_budget()
        budget.record_call(2000, 2000)  # 4000 total
        assert budget.tokens_used == 4000
        assert not budget.is_finalized

    def test_exceeds_token_limit_raises_terminal_error(self) -> None:
        """Exceeding token limit raises BudgetExceededError."""
        budget = RequestBudget(max_llm_calls=10, max_tokens=5000)

        budget.check_call_budget()
        with pytest.raises(BudgetExceededError) as exc_info:
            budget.record_call(3000, 3000)  # 6000 > 5000

        assert exc_info.value.limit_type == "tokens"
        assert exc_info.value.used == 6000
        assert exc_info.value.limit == 5000
        assert exc_info.value.kind == FailureKind.BUDGET_EXCEEDED

    def test_token_limit_error_is_terminal(self) -> None:
        """After token limit error, budget is finalized."""
        budget = RequestBudget(max_llm_calls=10, max_tokens=1000)

        budget.check_call_budget()
        with pytest.raises(BudgetExceededError):
            budget.record_call(2000, 0)

        assert budget.is_finalized

    def test_remaining_tokens_decrements(self) -> None:
        """Remaining tokens decreases with usage."""
        budget = RequestBudget(max_tokens=10_000)

        budget.check_call_budget()
        budget.record_call(1000, 500)
        assert budget.remaining_tokens == 8500

    def test_cumulative_token_tracking(self) -> None:
        """Tokens accumulate across multiple calls."""
        budget = RequestBudget(max_llm_calls=5, max_tokens=10_000)

        budget.check_call_budget()
        budget.record_call(1000, 500)  # 1500

        budget.check_call_budget()
        budget.record_call(2000, 1000)  # 3000 more = 4500 total

        budget.check_call_budget()
        budget.record_call(3000, 1500)  # 4500 more = 9000 total

        assert budget.tokens_used == 9000
        assert budget.remaining_tokens == 1000


# =============================================================================
# TERMINAL FAILURE - NO RETRY
# =============================================================================


class TestNoRetryAfterTerminal:
    """Test that no operations are allowed after terminal failure."""

    def test_no_check_after_call_limit_exceeded(self) -> None:
        """Cannot check budget after call limit exceeded."""
        budget = RequestBudget(max_llm_calls=1, max_tokens=100_000)

        budget.check_call_budget()
        budget.record_call(100, 50)

        with pytest.raises(BudgetExceededError):
            budget.check_call_budget()

        # Further checks should raise RuntimeError, not BudgetExceededError
        with pytest.raises(RuntimeError, match="finalized"):
            budget.check_call_budget()

    def test_no_record_after_call_limit_exceeded(self) -> None:
        """Cannot record calls after call limit exceeded."""
        budget = RequestBudget(max_llm_calls=1, max_tokens=100_000)

        budget.check_call_budget()
        budget.record_call(100, 50)

        with pytest.raises(BudgetExceededError):
            budget.check_call_budget()

        with pytest.raises(RuntimeError, match="finalized"):
            budget.record_call(100, 50)

    def test_no_check_after_token_limit_exceeded(self) -> None:
        """Cannot check budget after token limit exceeded."""
        budget = RequestBudget(max_llm_calls=10, max_tokens=1000)

        budget.check_call_budget()
        with pytest.raises(BudgetExceededError):
            budget.record_call(2000, 0)

        with pytest.raises(RuntimeError, match="finalized"):
            budget.check_call_budget()

    def test_no_record_after_token_limit_exceeded(self) -> None:
        """Cannot record calls after token limit exceeded."""
        budget = RequestBudget(max_llm_calls=10, max_tokens=1000)

        budget.check_call_budget()
        with pytest.raises(BudgetExceededError):
            budget.record_call(2000, 0)

        with pytest.raises(RuntimeError, match="finalized"):
            budget.record_call(100, 50)

    def test_manual_finalize_prevents_operations(self) -> None:
        """Manual finalize() prevents further operations."""
        budget = RequestBudget()

        budget.finalize()

        with pytest.raises(RuntimeError, match="finalized"):
            budget.check_call_budget()

        with pytest.raises(RuntimeError, match="finalized"):
            budget.record_call(100, 50)


# =============================================================================
# GUARD MEMOIZATION
# =============================================================================


class TestGuardMemoization:
    """Test guard memoization to prevent re-validation loops."""

    def test_hash_output_deterministic(self) -> None:
        """Same output produces same hash."""
        budget = RequestBudget()
        output = "Some LLM output text"

        hash1 = budget.hash_output(output)
        hash2 = budget.hash_output(output)

        assert hash1 == hash2

    def test_hash_output_different_for_different_inputs(self) -> None:
        """Different outputs produce different hashes."""
        budget = RequestBudget()

        hash1 = budget.hash_output("Output A")
        hash2 = budget.hash_output("Output B")

        assert hash1 != hash2

    def test_mark_rejected_tracks_output(self) -> None:
        """Marking output as rejected tracks it."""
        budget = RequestBudget()
        output = "Bad output"

        assert not budget.is_output_rejected(output)

        budget.mark_output_rejected(output)

        assert budget.is_output_rejected(output)

    def test_guard_output_runs_validator_once(self) -> None:
        """Validator runs only once for same rejected output."""
        budget = RequestBudget()
        output = "Invalid output"
        call_count = 0

        def validator(_text: str) -> bool:
            nonlocal call_count
            call_count += 1
            return False  # Always reject

        # First call runs validator
        result1 = budget.guard_output(output, validator)
        assert result1 is False
        assert call_count == 1

        # Second call with same output does NOT run validator
        result2 = budget.guard_output(output, validator)
        assert result2 is False
        assert call_count == 1  # Still 1

    def test_guard_output_allows_valid_output(self) -> None:
        """Valid output passes and is not rejected."""
        budget = RequestBudget()
        output = "Valid output"

        def validator(_text: str) -> bool:
            return True

        result = budget.guard_output(output, validator)
        assert result is True
        assert not budget.is_output_rejected(output)

    def test_guard_output_rejects_invalid_output(self) -> None:
        """Invalid output is rejected and marked."""
        budget = RequestBudget()
        output = "Invalid output"

        def validator(_text: str) -> bool:
            return False

        result = budget.guard_output(output, validator)
        assert result is False
        assert budget.is_output_rejected(output)

    def test_guard_memoization_is_per_output(self) -> None:
        """Different outputs have independent memoization."""
        budget = RequestBudget()
        call_count = 0

        def validator(text: str) -> bool:
            nonlocal call_count
            call_count += 1
            return "good" in text

        # First output: bad (rejected)
        result1 = budget.guard_output("bad output", validator)
        assert result1 is False
        assert call_count == 1

        # Second output: different, good (valid)
        result2 = budget.guard_output("good output", validator)
        assert result2 is True
        assert call_count == 2

        # First output again: memoized, no validator call
        result3 = budget.guard_output("bad output", validator)
        assert result3 is False
        assert call_count == 2  # Still 2


# =============================================================================
# BUDGET EXCEEDED ERROR
# =============================================================================


class TestBudgetExceededError:
    """Test BudgetExceededError properties."""

    def test_error_has_correct_kind(self) -> None:
        """Error has BUDGET_EXCEEDED failure kind."""
        error = BudgetExceededError("LLM calls", 3, 3)
        assert error.kind == FailureKind.BUDGET_EXCEEDED

    def test_error_has_429_status_code(self) -> None:
        """Error has 429 (Too Many Requests) status code."""
        error = BudgetExceededError("tokens", 25000, 20000)
        assert error.status_code == 429

    def test_error_message_includes_limit_type(self) -> None:
        """Error message includes the limit type."""
        error = BudgetExceededError("LLM calls", 3, 3)
        assert "LLM calls" in error.message

    def test_error_detail_includes_usage(self) -> None:
        """Error detail includes usage stats."""
        error = BudgetExceededError("tokens", 25000, 20000)
        assert "25000" in error.detail
        assert "20000" in error.detail

    def test_error_to_response(self) -> None:
        """Error converts to ApiResponse correctly."""
        error = BudgetExceededError("LLM calls", 4, 3)
        response = error.to_response()

        assert response.failure is not None
        assert response.failure.kind == FailureKind.BUDGET_EXCEEDED


# =============================================================================
# INTEGRATION: REALISTIC SCENARIO
# =============================================================================


class TestRealisticScenario:
    """Test realistic usage patterns."""

    def test_typical_chat_flow_within_budget(self) -> None:
        """Typical 2-call chat flow stays within budget."""
        budget = RequestBudget()

        # First call: user message
        budget.check_call_budget()
        budget.record_call(500, 200)  # 700 tokens

        # Second call: after tool use
        budget.check_call_budget()
        budget.record_call(1500, 500)  # 2000 tokens

        assert budget.llm_calls_used == 2
        assert budget.tokens_used == 2700
        assert not budget.is_finalized

    def test_complex_flow_hits_call_limit(self) -> None:
        """Complex flow with many tools hits call limit."""
        budget = RequestBudget(max_llm_calls=3, max_tokens=100_000)

        for _ in range(3):
            budget.check_call_budget()
            budget.record_call(500, 200)

        # Fourth call fails
        with pytest.raises(BudgetExceededError) as exc_info:
            budget.check_call_budget()

        assert exc_info.value.limit_type == "LLM calls"
        assert budget.is_finalized

    def test_large_context_hits_token_limit(self) -> None:
        """Large context accumulates to token limit."""
        budget = RequestBudget(max_llm_calls=10, max_tokens=5000)

        # First call: moderate
        budget.check_call_budget()
        budget.record_call(1000, 500)  # 1500

        # Second call: growing context
        budget.check_call_budget()
        budget.record_call(2000, 800)  # 2800 more = 4300

        # Third call: would exceed
        budget.check_call_budget()
        with pytest.raises(BudgetExceededError) as exc_info:
            budget.record_call(1000, 500)  # Would be 5800 > 5000

        assert exc_info.value.limit_type == "tokens"
        assert budget.is_finalized

    def test_guard_prevents_infinite_retry_loop(self) -> None:
        """Guard memoization prevents infinite retry loops."""
        budget = RequestBudget(max_llm_calls=5)
        bad_output = "Card: Fake Card Name"
        validation_attempts = 0

        def validate_card_names(output: str) -> bool:
            nonlocal validation_attempts
            validation_attempts += 1
            return "Fake" not in output

        # Simulate retry loop - guard should prevent re-validation
        for _ in range(10):
            is_valid = budget.guard_output(bad_output, validate_card_names)
            if not is_valid:
                # Normally would retry, but guard prevents re-validation
                pass

        # Validator should only run once due to memoization
        assert validation_attempts == 1
