"""
Cost Controls — Rate Limiting and Daily Budget Enforcement.

This module protects ForgeBreaker (a demo/portfolio project) from:
- Abuse via excessive requests from a single IP
- Unexpected LLM costs via daily budget caps
- Runaway costs via environment-level kill switch

INVARIANTS:
- All limits are HARD CAPS, not soft limits
- Exceedance is TERMINAL — no retries, no fallback
- Limits are enforced BEFORE any LLM logic runs
- IP-based limits use hashed IPs for privacy in logs

ENFORCEMENT:
- Per-IP: 20 requests per day per IP address
- Global: Configurable daily LLM calls and tokens
- Kill switch: LLM_ENABLED environment variable
"""

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from threading import Lock

from forgebreaker.models.failure import FailureKind, KnownError

logger = logging.getLogger(__name__)

# =============================================================================
# CONFIGURATION DEFAULTS
# =============================================================================

# Per-IP rate limit (requests per day)
DEFAULT_REQUESTS_PER_IP_PER_DAY = 20

# Global daily limits
DEFAULT_MAX_LLM_CALLS_PER_DAY = 500
DEFAULT_MAX_TOKENS_PER_DAY = 500_000


# =============================================================================
# CUSTOM EXCEPTIONS
# =============================================================================


class RateLimitExceededError(KnownError):
    """
    Exception raised when per-IP rate limit is exceeded.

    Returns HTTP 429 with a clear demo message.
    """

    def __init__(self, ip_hash: str, limit: int):
        self.ip_hash = ip_hash
        self.limit = limit
        super().__init__(
            kind=FailureKind.BUDGET_EXCEEDED,
            message=(
                "This is a demo project with limited usage. "
                f"You've reached today's request limit ({limit}). "
                "Please try again tomorrow."
            ),
            detail=f"IP rate limit: {limit}/day",
            suggestion="This limit resets at midnight UTC.",
            status_code=429,
        )


class DailyBudgetExceededError(KnownError):
    """
    Exception raised when global daily LLM budget is exceeded.

    This is a hard failure with no retries.
    """

    def __init__(self, limit_type: str, used: int, limit: int):
        self.limit_type = limit_type
        self.used = used
        self.limit = limit
        super().__init__(
            kind=FailureKind.BUDGET_EXCEEDED,
            message=(
                "This demo project has reached its daily usage limit. "
                "Service will resume tomorrow. Thank you for your interest!"
            ),
            detail=f"Daily {limit_type}: {used}/{limit}",
            suggestion="This limit resets at midnight UTC.",
            status_code=503,
        )


class LLMDisabledError(KnownError):
    """
    Exception raised when LLM is disabled via environment.

    This is an immediate failure with no partial execution.
    """

    def __init__(self) -> None:
        super().__init__(
            kind=FailureKind.SERVICE_UNAVAILABLE,
            message="LLM functionality is currently disabled.",
            detail="LLM_ENABLED=false",
            suggestion="This is intentional. The service may be in maintenance mode.",
            status_code=503,
        )


# =============================================================================
# THREAD-SAFE USAGE TRACKER
# =============================================================================


@dataclass
class DailyUsageTracker:
    """
    Thread-safe tracker for daily usage limits.

    Resets automatically at midnight UTC.

    Tracks:
    - Per-IP request counts (for rate limiting)
    - Global LLM call count (for cost control)
    - Global token count (for cost control)
    """

    # Configuration
    requests_per_ip_per_day: int = DEFAULT_REQUESTS_PER_IP_PER_DAY
    max_llm_calls_per_day: int = DEFAULT_MAX_LLM_CALLS_PER_DAY
    max_tokens_per_day: int = DEFAULT_MAX_TOKENS_PER_DAY

    # State
    _current_date: date = field(default_factory=lambda: datetime.now(UTC).date())
    _ip_request_counts: dict[str, int] = field(default_factory=dict)
    _llm_calls_today: int = 0
    _tokens_today: int = 0
    _lock: Lock = field(default_factory=Lock)

    def _maybe_reset(self) -> None:
        """Reset counters if we've crossed into a new day (UTC)."""
        today = datetime.now(UTC).date()
        if today != self._current_date:
            self._current_date = today
            self._ip_request_counts.clear()
            self._llm_calls_today = 0
            self._tokens_today = 0
            logger.info(
                "DAILY_COUNTERS_RESET",
                extra={"new_date": today.isoformat()},
            )

    def hash_ip(self, ip_address: str) -> str:
        """
        Hash an IP address for privacy-safe logging.

        Uses SHA-256 truncated to 12 characters.
        """
        return hashlib.sha256(ip_address.encode()).hexdigest()[:12]

    def check_ip_rate_limit(self, ip_address: str) -> None:
        """
        Check and increment per-IP rate limit.

        MUST be called BEFORE any LLM logic runs.

        Raises:
            RateLimitExceededError: If daily limit exceeded for this IP
        """
        with self._lock:
            self._maybe_reset()

            ip_hash = self.hash_ip(ip_address)
            current_count = self._ip_request_counts.get(ip_hash, 0)

            if current_count >= self.requests_per_ip_per_day:
                logger.warning(
                    "RATE_LIMIT_EXCEEDED",
                    extra={
                        "ip_hash": ip_hash,
                        "requests_today": current_count,
                        "limit": self.requests_per_ip_per_day,
                    },
                )
                raise RateLimitExceededError(ip_hash, self.requests_per_ip_per_day)

            # Increment count
            self._ip_request_counts[ip_hash] = current_count + 1

    def check_daily_budget(self) -> None:
        """
        Check if global daily LLM budget is available.

        MUST be called BEFORE any LLM call.

        Raises:
            DailyBudgetExceededError: If daily limit exceeded
        """
        with self._lock:
            self._maybe_reset()

            if self._llm_calls_today >= self.max_llm_calls_per_day:
                logger.warning(
                    "DAILY_LLM_BUDGET_EXCEEDED",
                    extra={
                        "llm_calls_today": self._llm_calls_today,
                        "limit": self.max_llm_calls_per_day,
                    },
                )
                raise DailyBudgetExceededError(
                    limit_type="LLM calls",
                    used=self._llm_calls_today,
                    limit=self.max_llm_calls_per_day,
                )

            if self._tokens_today >= self.max_tokens_per_day:
                logger.warning(
                    "DAILY_TOKEN_BUDGET_EXCEEDED",
                    extra={
                        "tokens_today": self._tokens_today,
                        "limit": self.max_tokens_per_day,
                    },
                )
                raise DailyBudgetExceededError(
                    limit_type="tokens",
                    used=self._tokens_today,
                    limit=self.max_tokens_per_day,
                )

    def record_llm_call(self, input_tokens: int, output_tokens: int) -> None:
        """
        Record an LLM call and its token usage.

        MUST be called AFTER each LLM invocation.

        Args:
            input_tokens: Tokens used in the request
            output_tokens: Tokens used in the response
        """
        with self._lock:
            self._maybe_reset()
            self._llm_calls_today += 1
            self._tokens_today += input_tokens + output_tokens

            logger.debug(
                "LLM_CALL_RECORDED",
                extra={
                    "llm_calls_today": self._llm_calls_today,
                    "tokens_today": self._tokens_today,
                },
            )

    def get_diagnostics(self) -> dict[str, int | str]:
        """
        Get current usage diagnostics.

        Returns:
            Dict with current usage and remaining budget.
        """
        with self._lock:
            self._maybe_reset()
            return {
                "date": self._current_date.isoformat(),
                "unique_ips_today": len(self._ip_request_counts),
                "llm_calls_today": self._llm_calls_today,
                "llm_calls_remaining": max(0, self.max_llm_calls_per_day - self._llm_calls_today),
                "tokens_today": self._tokens_today,
                "tokens_remaining": max(0, self.max_tokens_per_day - self._tokens_today),
                "requests_per_ip_limit": self.requests_per_ip_per_day,
                "llm_calls_limit": self.max_llm_calls_per_day,
                "tokens_limit": self.max_tokens_per_day,
            }


# =============================================================================
# GLOBAL TRACKER INSTANCE
# =============================================================================

# Singleton tracker instance
_usage_tracker: DailyUsageTracker | None = None


def get_usage_tracker() -> DailyUsageTracker:
    """Get the global usage tracker instance."""
    global _usage_tracker
    if _usage_tracker is None:
        _usage_tracker = DailyUsageTracker()
    return _usage_tracker


def reset_usage_tracker() -> None:
    """Reset the global usage tracker (for testing)."""
    global _usage_tracker
    _usage_tracker = None


# =============================================================================
# LLM KILL SWITCH
# =============================================================================


def check_llm_enabled(llm_enabled: bool) -> None:
    """
    Check if LLM is enabled.

    MUST be called BEFORE any LLM logic runs.

    Args:
        llm_enabled: Value of LLM_ENABLED setting

    Raises:
        LLMDisabledError: If LLM is disabled
    """
    if not llm_enabled:
        logger.warning("LLM_DISABLED", extra={"llm_enabled": False})
        raise LLMDisabledError()


# =============================================================================
# COMBINED GUARD FUNCTION
# =============================================================================


def enforce_cost_controls(
    ip_address: str,
    llm_enabled: bool,
) -> None:
    """
    Enforce all cost controls before LLM execution.

    This is the single entry point for all cost control checks.
    Call this at the start of any LLM-invoking endpoint.

    Order of checks:
    1. LLM kill switch (fastest, no state)
    2. IP rate limit (per-request, quick)
    3. Daily budget (global, quick)

    Args:
        ip_address: Client IP address
        llm_enabled: Value of LLM_ENABLED setting

    Raises:
        LLMDisabledError: If LLM is disabled
        RateLimitExceededError: If IP rate limit exceeded
        DailyBudgetExceededError: If daily budget exceeded
    """
    # 1. Kill switch (fastest check)
    check_llm_enabled(llm_enabled)

    # 2. IP rate limit
    tracker = get_usage_tracker()
    tracker.check_ip_rate_limit(ip_address)

    # 3. Daily budget
    tracker.check_daily_budget()
