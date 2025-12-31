"""
Request Budget — Hard Limits on Model Usage Per Request.

This module enforces absolute limits on:
- Number of LLM calls per request
- Total tokens consumed per request

INVARIANTS:
- Limits are HARD CAPS, not soft limits
- Exceedance is TERMINAL — no retries, no fallback
- Guard memoization prevents retry loops from re-validating same output

AUTHORITY:
- MAX_LLM_CALLS_PER_REQUEST and MAX_TOKENS_PER_REQUEST are constants
- They are NOT configurable at runtime
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from hashlib import sha256

from forgebreaker.models.failure import FailureKind, KnownError

# =============================================================================
# HARD LIMITS (Constants — NOT Configurable)
# =============================================================================

MAX_LLM_CALLS_PER_REQUEST = 3
MAX_TOKENS_PER_REQUEST = 20_000


# =============================================================================
# BUDGET EXCEEDED ERROR (Terminal)
# =============================================================================


class BudgetExceededError(KnownError):
    """
    Terminal exception raised when request budget is exceeded.

    This error is FINAL. The system MUST NOT:
    - Retry the request
    - Ask for clarification
    - Attempt fallback
    - Make additional tool calls

    This is enforced by code, not convention.
    """

    def __init__(self, limit_type: str, used: int, limit: int):
        self.limit_type = limit_type
        self.used = used
        self.limit = limit
        super().__init__(
            kind=FailureKind.BUDGET_EXCEEDED,
            message=f"Request budget exceeded: {limit_type}",
            detail=f"{limit_type}: {used}/{limit}",
            suggestion="Simplify your request or try a more specific query.",
            status_code=429,
        )


# =============================================================================
# REQUEST BUDGET
# =============================================================================


@dataclass
class RequestBudget:
    """
    Tracks and enforces budget limits for a single request.

    INVARIANTS:
    - Once finalized, no further operations are allowed
    - Budget checks happen BEFORE each LLM call
    - Token accounting happens AFTER each LLM call
    - Failures are terminal

    Guard memoization:
    - Tracks hashes of rejected outputs
    - Prevents re-validation of same output in retry loops
    """

    max_llm_calls: int = MAX_LLM_CALLS_PER_REQUEST
    max_tokens: int = MAX_TOKENS_PER_REQUEST
    llm_calls_used: int = 0
    tokens_used: int = 0
    _finalized: bool = field(default=False, repr=False)
    _rejected_hashes: set[str] = field(default_factory=set, repr=False)

    def check_call_budget(self) -> None:
        """
        Check if another LLM call is allowed.

        MUST be called BEFORE each LLM invocation.

        Raises:
            BudgetExceededError: If call limit would be exceeded (terminal)
            RuntimeError: If budget is already finalized
        """
        if self._finalized:
            raise RuntimeError("Budget is finalized — no further operations allowed")

        if self.llm_calls_used >= self.max_llm_calls:
            self._finalized = True
            raise BudgetExceededError(
                limit_type="LLM calls",
                used=self.llm_calls_used,
                limit=self.max_llm_calls,
            )

    def record_call(self, input_tokens: int, output_tokens: int) -> None:
        """
        Record an LLM call and its token usage.

        MUST be called AFTER each LLM invocation.

        Args:
            input_tokens: Tokens used in the request
            output_tokens: Tokens used in the response

        Raises:
            BudgetExceededError: If token limit exceeded (terminal)
            RuntimeError: If budget is already finalized
        """
        if self._finalized:
            raise RuntimeError("Budget is finalized — no further operations allowed")

        self.llm_calls_used += 1
        total_call_tokens = input_tokens + output_tokens
        self.tokens_used += total_call_tokens

        if self.tokens_used > self.max_tokens:
            self._finalized = True
            raise BudgetExceededError(
                limit_type="tokens",
                used=self.tokens_used,
                limit=self.max_tokens,
            )

    def finalize(self) -> None:
        """
        Mark the budget as finalized.

        After finalization, no further LLM calls are allowed.
        This is called automatically on budget exceedance.
        """
        self._finalized = True

    @property
    def is_finalized(self) -> bool:
        """Check if budget has been finalized."""
        return self._finalized

    @property
    def remaining_calls(self) -> int:
        """Number of LLM calls remaining."""
        return max(0, self.max_llm_calls - self.llm_calls_used)

    @property
    def remaining_tokens(self) -> int:
        """Number of tokens remaining."""
        return max(0, self.max_tokens - self.tokens_used)

    # =========================================================================
    # GUARD MEMOIZATION
    # =========================================================================

    def hash_output(self, output: str) -> str:
        """
        Generate a hash for output content.

        Used for guard memoization to prevent re-validation.
        """
        return sha256(output.encode()).hexdigest()[:16]

    def is_output_rejected(self, output: str) -> bool:
        """
        Check if this output has already been rejected.

        Returns:
            True if output was previously rejected, False otherwise
        """
        output_hash = self.hash_output(output)
        return output_hash in self._rejected_hashes

    def mark_output_rejected(self, output: str) -> None:
        """
        Mark an output as rejected.

        Prevents re-validation of the same output in retry loops.
        """
        output_hash = self.hash_output(output)
        self._rejected_hashes.add(output_hash)

    def guard_output(self, output: str, validator: Callable[[str], bool]) -> bool:
        """
        Run a validator on output with memoization.

        If the output was previously rejected, returns False immediately
        without running the validator again.

        Args:
            output: The output to validate
            validator: A callable that returns True if valid, False if invalid

        Returns:
            True if valid, False if rejected (either now or previously)
        """
        # Check memoization first
        if self.is_output_rejected(output):
            return False

        # Run validator
        is_valid = validator(output)

        if not is_valid:
            self.mark_output_rejected(output)

        return is_valid
