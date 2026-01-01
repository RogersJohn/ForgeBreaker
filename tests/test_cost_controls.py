"""
Tests for cost controls — rate limiting and daily budget enforcement.

INVARIANTS:
- All limits are HARD CAPS, not soft limits
- Exceedance is TERMINAL — no retries, no fallback
- Limits are enforced BEFORE any LLM logic runs
- IP-based limits use hashed IPs for privacy in logs
"""

import pytest

from forgebreaker.models.failure import FailureKind
from forgebreaker.services.cost_controls import (
    DailyBudgetExceededError,
    DailyUsageTracker,
    LLMDisabledError,
    RateLimitExceededError,
    check_llm_enabled,
    enforce_cost_controls,
    get_usage_tracker,
    reset_usage_tracker,
)


class TestRateLimitEnforcement:
    """Tests for per-IP rate limiting."""

    def setup_method(self) -> None:
        """Reset global tracker before each test."""
        reset_usage_tracker()

    def test_first_request_allowed(self) -> None:
        """First request from an IP is allowed."""
        tracker = DailyUsageTracker(requests_per_ip_per_day=20)
        # Should not raise
        tracker.check_ip_rate_limit("192.168.1.1")

    def test_requests_up_to_limit_allowed(self) -> None:
        """Requests up to the limit are allowed."""
        tracker = DailyUsageTracker(requests_per_ip_per_day=5)
        for _ in range(5):
            tracker.check_ip_rate_limit("192.168.1.1")
        # All 5 should succeed

    def test_request_over_limit_raises(self) -> None:
        """Request over the limit raises RateLimitExceededError."""
        tracker = DailyUsageTracker(requests_per_ip_per_day=3)

        # Use up the limit
        for _ in range(3):
            tracker.check_ip_rate_limit("192.168.1.1")

        # 4th request should fail
        with pytest.raises(RateLimitExceededError) as exc_info:
            tracker.check_ip_rate_limit("192.168.1.1")

        error = exc_info.value
        assert error.limit == 3
        assert error.status_code == 429
        assert error.kind == FailureKind.BUDGET_EXCEEDED
        assert "demo project" in error.message.lower()

    def test_different_ips_have_separate_limits(self) -> None:
        """Different IPs have separate rate limits."""
        tracker = DailyUsageTracker(requests_per_ip_per_day=2)

        # IP 1 uses its limit
        tracker.check_ip_rate_limit("192.168.1.1")
        tracker.check_ip_rate_limit("192.168.1.1")

        # IP 2 should still be allowed
        tracker.check_ip_rate_limit("192.168.1.2")
        tracker.check_ip_rate_limit("192.168.1.2")

        # IP 1 is now blocked
        with pytest.raises(RateLimitExceededError):
            tracker.check_ip_rate_limit("192.168.1.1")

        # IP 2 is now blocked
        with pytest.raises(RateLimitExceededError):
            tracker.check_ip_rate_limit("192.168.1.2")

    def test_ip_hash_is_deterministic(self) -> None:
        """Same IP produces same hash."""
        tracker = DailyUsageTracker()
        hash1 = tracker.hash_ip("192.168.1.1")
        hash2 = tracker.hash_ip("192.168.1.1")
        assert hash1 == hash2

    def test_ip_hash_is_12_chars(self) -> None:
        """IP hash is truncated to 12 characters."""
        tracker = DailyUsageTracker()
        ip_hash = tracker.hash_ip("192.168.1.1")
        assert len(ip_hash) == 12

    def test_different_ips_produce_different_hashes(self) -> None:
        """Different IPs produce different hashes."""
        tracker = DailyUsageTracker()
        hash1 = tracker.hash_ip("192.168.1.1")
        hash2 = tracker.hash_ip("192.168.1.2")
        assert hash1 != hash2


class TestDailyBudgetEnforcement:
    """Tests for global daily LLM budget."""

    def setup_method(self) -> None:
        """Reset global tracker before each test."""
        reset_usage_tracker()

    def test_first_call_allowed(self) -> None:
        """First LLM call is allowed."""
        tracker = DailyUsageTracker(max_llm_calls_per_day=100)
        # Should not raise
        tracker.check_daily_budget()

    def test_calls_up_to_limit_allowed(self) -> None:
        """LLM calls up to the limit are allowed."""
        tracker = DailyUsageTracker(max_llm_calls_per_day=3, max_tokens_per_day=100000)

        for _ in range(3):
            tracker.check_daily_budget()
            tracker.record_llm_call(100, 100)

    def test_call_over_limit_raises(self) -> None:
        """LLM call over the limit raises DailyBudgetExceededError."""
        tracker = DailyUsageTracker(max_llm_calls_per_day=2, max_tokens_per_day=100000)

        # Use up the limit
        tracker.check_daily_budget()
        tracker.record_llm_call(100, 100)
        tracker.check_daily_budget()
        tracker.record_llm_call(100, 100)

        # 3rd call should fail
        with pytest.raises(DailyBudgetExceededError) as exc_info:
            tracker.check_daily_budget()

        error = exc_info.value
        assert error.limit_type == "LLM calls"
        assert error.used == 2
        assert error.limit == 2
        assert error.status_code == 503
        assert "demo project" in error.message.lower()

    def test_token_limit_enforced(self) -> None:
        """Token limit is enforced."""
        tracker = DailyUsageTracker(max_llm_calls_per_day=100, max_tokens_per_day=1000)

        # Use up tokens
        tracker.check_daily_budget()
        tracker.record_llm_call(500, 500)  # 1000 tokens total

        # Next call should fail
        with pytest.raises(DailyBudgetExceededError) as exc_info:
            tracker.check_daily_budget()

        error = exc_info.value
        assert error.limit_type == "tokens"
        assert error.used == 1000
        assert error.limit == 1000

    def test_record_llm_call_tracks_usage(self) -> None:
        """record_llm_call correctly tracks token usage."""
        tracker = DailyUsageTracker()

        tracker.record_llm_call(100, 50)
        tracker.record_llm_call(200, 100)

        diagnostics = tracker.get_diagnostics()
        assert diagnostics["llm_calls_today"] == 2
        assert diagnostics["tokens_today"] == 450  # 100+50+200+100


class TestLLMKillSwitch:
    """Tests for LLM_ENABLED kill switch."""

    def test_llm_enabled_true_allows_calls(self) -> None:
        """When LLM is enabled, calls are allowed."""
        # Should not raise
        check_llm_enabled(True)

    def test_llm_enabled_false_raises(self) -> None:
        """When LLM is disabled, LLMDisabledError is raised."""
        with pytest.raises(LLMDisabledError) as exc_info:
            check_llm_enabled(False)

        error = exc_info.value
        assert error.status_code == 503
        assert error.kind == FailureKind.SERVICE_UNAVAILABLE
        assert "disabled" in error.message.lower()


class TestEnforceCostControls:
    """Tests for the combined enforce_cost_controls function."""

    def setup_method(self) -> None:
        """Reset global tracker before each test."""
        reset_usage_tracker()

    def test_all_checks_pass(self) -> None:
        """When all checks pass, no exception is raised."""
        # Should not raise
        enforce_cost_controls("192.168.1.1", llm_enabled=True)

    def test_kill_switch_checked_first(self) -> None:
        """Kill switch is checked before rate limit."""
        # Even if we haven't hit rate limit, kill switch fails first
        with pytest.raises(LLMDisabledError):
            enforce_cost_controls("192.168.1.1", llm_enabled=False)

    def test_rate_limit_checked_second(self) -> None:
        """Rate limit is checked after kill switch."""
        tracker = get_usage_tracker()
        tracker.requests_per_ip_per_day = 1

        # First request succeeds
        enforce_cost_controls("192.168.1.1", llm_enabled=True)

        # Second request fails with rate limit (not kill switch)
        with pytest.raises(RateLimitExceededError):
            enforce_cost_controls("192.168.1.1", llm_enabled=True)

    def test_budget_checked_last(self) -> None:
        """Daily budget is checked after rate limit."""
        tracker = get_usage_tracker()
        tracker.max_llm_calls_per_day = 1

        # Record a call to exhaust budget
        tracker.record_llm_call(100, 100)

        # Budget check should fail (not rate limit)
        with pytest.raises(DailyBudgetExceededError):
            enforce_cost_controls("192.168.1.1", llm_enabled=True)


class TestDiagnostics:
    """Tests for usage diagnostics."""

    def setup_method(self) -> None:
        """Reset global tracker before each test."""
        reset_usage_tracker()

    def test_diagnostics_returns_all_fields(self) -> None:
        """Diagnostics returns all expected fields."""
        tracker = DailyUsageTracker()
        diagnostics = tracker.get_diagnostics()

        assert "date" in diagnostics
        assert "unique_ips_today" in diagnostics
        assert "llm_calls_today" in diagnostics
        assert "llm_calls_remaining" in diagnostics
        assert "tokens_today" in diagnostics
        assert "tokens_remaining" in diagnostics
        assert "requests_per_ip_limit" in diagnostics
        assert "llm_calls_limit" in diagnostics
        assert "tokens_limit" in diagnostics

    def test_diagnostics_tracks_unique_ips(self) -> None:
        """Diagnostics correctly tracks unique IPs."""
        tracker = DailyUsageTracker()

        tracker.check_ip_rate_limit("192.168.1.1")
        tracker.check_ip_rate_limit("192.168.1.2")
        tracker.check_ip_rate_limit("192.168.1.1")  # Repeat

        diagnostics = tracker.get_diagnostics()
        assert diagnostics["unique_ips_today"] == 2

    def test_diagnostics_shows_remaining_budget(self) -> None:
        """Diagnostics shows correct remaining budget."""
        tracker = DailyUsageTracker(max_llm_calls_per_day=10, max_tokens_per_day=10000)

        tracker.record_llm_call(100, 100)  # 200 tokens
        tracker.record_llm_call(100, 100)  # 400 tokens total

        diagnostics = tracker.get_diagnostics()
        assert diagnostics["llm_calls_today"] == 2
        assert diagnostics["llm_calls_remaining"] == 8
        assert diagnostics["tokens_today"] == 400
        assert diagnostics["tokens_remaining"] == 9600


class TestGlobalTrackerSingleton:
    """Tests for global tracker singleton behavior."""

    def setup_method(self) -> None:
        """Reset global tracker before each test."""
        reset_usage_tracker()

    def test_get_usage_tracker_returns_singleton(self) -> None:
        """get_usage_tracker returns the same instance."""
        tracker1 = get_usage_tracker()
        tracker2 = get_usage_tracker()
        assert tracker1 is tracker2

    def test_reset_usage_tracker_clears_singleton(self) -> None:
        """reset_usage_tracker clears the singleton."""
        tracker1 = get_usage_tracker()
        reset_usage_tracker()
        tracker2 = get_usage_tracker()
        assert tracker1 is not tracker2

    def test_state_persists_across_calls(self) -> None:
        """State persists when using get_usage_tracker."""
        tracker = get_usage_tracker()
        tracker.check_ip_rate_limit("192.168.1.1")

        # Get tracker again
        tracker2 = get_usage_tracker()
        diagnostics = tracker2.get_diagnostics()
        assert diagnostics["unique_ips_today"] == 1


class TestErrorMessages:
    """Tests for user-friendly error messages."""

    def test_rate_limit_message_is_user_friendly(self) -> None:
        """Rate limit error has user-friendly message."""
        error = RateLimitExceededError(ip_hash="abc123", limit=20)
        assert "demo project" in error.message.lower()
        assert "20" in error.message
        assert "tomorrow" in error.message.lower()

    def test_daily_budget_message_is_user_friendly(self) -> None:
        """Daily budget error has user-friendly message."""
        error = DailyBudgetExceededError(limit_type="LLM calls", used=100, limit=100)
        assert "demo project" in error.message.lower()
        assert "tomorrow" in error.message.lower()

    def test_llm_disabled_message_is_user_friendly(self) -> None:
        """LLM disabled error has user-friendly message."""
        error = LLMDisabledError()
        assert "disabled" in error.message.lower()
        assert (
            "maintenance" in error.suggestion.lower() or "intentional" in error.suggestion.lower()
        )
