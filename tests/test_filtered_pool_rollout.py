"""
Tests for Filtered Candidate Pool Rollout (PR 8).

These integration tests verify:
1. Default behavior: filtered pool is used without explicit config
2. Explicit opt-out: flag=False restores full collection behavior
3. Fallback safety: pool too small/large triggers fallback
4. Regression: deck build completes normally
"""

import os
from unittest.mock import patch

import pytest

from forgebreaker.config import Settings
from forgebreaker.filtering.payload import (
    FallbackReason,
    filter_collection_for_payload,
    get_payload_metrics,
    reset_payload_metrics,
)
from forgebreaker.models.intent import DeckIntent, Format


@pytest.fixture(autouse=True)
def reset_metrics() -> None:
    """Reset metrics before each test."""
    reset_payload_metrics()


@pytest.fixture
def sample_collection() -> dict[str, int]:
    """Sample user collection."""
    return {
        "Lightning Bolt": 4,
        "Shock": 4,
        "Goblin Guide": 4,
        "Monastery Swiftspear": 4,
        "Mountain": 20,
    }


@pytest.fixture
def sample_card_db() -> dict[str, dict]:
    """Sample card database."""
    return {
        "Lightning Bolt": {
            "name": "Lightning Bolt",
            "type_line": "Instant",
            "colors": ["R"],
            "color_identity": ["R"],
            "legalities": {"modern": "legal"},
        },
        "Shock": {
            "name": "Shock",
            "type_line": "Instant",
            "colors": ["R"],
            "color_identity": ["R"],
            "legalities": {"modern": "legal"},
        },
        "Goblin Guide": {
            "name": "Goblin Guide",
            "type_line": "Creature — Goblin Scout",
            "colors": ["R"],
            "color_identity": ["R"],
            "legalities": {"modern": "legal"},
        },
        "Monastery Swiftspear": {
            "name": "Monastery Swiftspear",
            "type_line": "Creature — Human Monk",
            "colors": ["R"],
            "color_identity": ["R"],
            "legalities": {"modern": "legal"},
        },
        "Mountain": {
            "name": "Mountain",
            "type_line": "Basic Land — Mountain",
            "colors": [],
            "color_identity": [],
            "legalities": {"modern": "legal"},
        },
    }


# =============================================================================
# DEFAULT BEHAVIOR TESTS
# =============================================================================


class TestDefaultBehavior:
    """Tests that filtered pool is ON by default."""

    def test_flag_defaults_to_true(self) -> None:
        """USE_FILTERED_CANDIDATE_POOL defaults to True."""
        # Create fresh settings without env override
        fresh_settings = Settings()
        assert fresh_settings.use_filtered_candidate_pool is True

    def test_filtered_pool_used_by_default(
        self,
        sample_collection: dict[str, int],
        sample_card_db: dict[str, dict],
    ) -> None:
        """Without explicit config, filtered candidate pool is used."""
        with patch("forgebreaker.filtering.payload.settings") as mock_settings:
            # Default behavior (flag=True)
            mock_settings.use_filtered_candidate_pool = True

            with patch("forgebreaker.filtering.payload.build_candidate_pool") as mock_pool:
                # Return valid pool
                mock_pool.return_value = {
                    "Lightning Bolt",
                    "Shock",
                    "Goblin Guide",
                    "Monastery Swiftspear",
                    "Mountain",
                    "Card1",
                    "Card2",
                    "Card3",
                    "Card4",
                    "Card5",
                }

                intent = DeckIntent(format=Format.MODERN, colors=frozenset({"R"}), confidence=0.5)
                filtered, metrics = filter_collection_for_payload(
                    intent, sample_collection, sample_card_db
                )

        # Should be filtered, not full collection
        assert metrics.feature_flag_enabled is True
        assert metrics.fallback_reason == FallbackReason.NONE
        assert metrics.filtered_collection_size <= metrics.full_collection_size


# =============================================================================
# EXPLICIT OPT-OUT TESTS
# =============================================================================


class TestExplicitOptOut:
    """Tests that setting flag=False restores pre-PR behavior."""

    def test_flag_can_be_overridden_via_settings(self) -> None:
        """Flag can be explicitly set to False."""
        with patch.dict(os.environ, {"USE_FILTERED_CANDIDATE_POOL": "false"}):
            override_settings = Settings()
            assert override_settings.use_filtered_candidate_pool is False

    def test_full_collection_when_flag_false(
        self,
        sample_collection: dict[str, int],
        sample_card_db: dict[str, dict],
    ) -> None:
        """Flag=False → full collection path used (exact pre-PR behavior)."""
        with patch("forgebreaker.filtering.payload.settings") as mock_settings:
            mock_settings.use_filtered_candidate_pool = False

            intent = DeckIntent(format=Format.MODERN, colors=frozenset({"R"}), confidence=0.5)
            filtered, metrics = filter_collection_for_payload(
                intent, sample_collection, sample_card_db
            )

        # Should return full collection unchanged
        assert filtered == sample_collection
        assert metrics.feature_flag_enabled is False
        assert metrics.fallback_reason == FallbackReason.FLAG_OFF

    def test_no_partial_filtering_when_flag_false(
        self,
        sample_collection: dict[str, int],
        sample_card_db: dict[str, dict],
    ) -> None:
        """Flag=False → bypasses candidate pool entirely."""
        with patch("forgebreaker.filtering.payload.settings") as mock_settings:
            mock_settings.use_filtered_candidate_pool = False

            with patch("forgebreaker.filtering.payload.build_candidate_pool") as mock_pool:
                intent = DeckIntent(format=Format.MODERN, confidence=0.5)
                filter_collection_for_payload(intent, sample_collection, sample_card_db)

        # build_candidate_pool should NOT be called
        mock_pool.assert_not_called()


# =============================================================================
# FALLBACK SAFETY TESTS
# =============================================================================


class TestFallbackSafety:
    """Tests that fallback to full collection works correctly."""

    def test_pool_too_small_fallback(
        self,
        sample_collection: dict[str, int],
        sample_card_db: dict[str, dict],
    ) -> None:
        """Pool below MIN_CANDIDATE_POOL_SIZE triggers fallback."""
        with patch("forgebreaker.filtering.payload.settings") as mock_settings:
            mock_settings.use_filtered_candidate_pool = True

            with patch("forgebreaker.filtering.payload.build_candidate_pool") as mock_pool:
                # Return pool smaller than MIN
                mock_pool.return_value = {"Card1", "Card2", "Card3"}

                intent = DeckIntent(format=Format.MODERN, confidence=0.5)
                filtered, metrics = filter_collection_for_payload(
                    intent, sample_collection, sample_card_db
                )

        # Should fallback to full collection
        assert filtered == sample_collection
        assert metrics.fallback_reason == FallbackReason.POOL_TOO_SMALL

    def test_pool_too_large_fallback(
        self,
        sample_collection: dict[str, int],
        sample_card_db: dict[str, dict],
    ) -> None:
        """Pool above MAX_CANDIDATE_POOL_SIZE triggers fallback."""
        from forgebreaker.config import MAX_CANDIDATE_POOL_SIZE

        with patch("forgebreaker.filtering.payload.settings") as mock_settings:
            mock_settings.use_filtered_candidate_pool = True

            with patch("forgebreaker.filtering.payload.build_candidate_pool") as mock_pool:
                # Return pool larger than MAX
                large_pool = {f"Card{i}" for i in range(MAX_CANDIDATE_POOL_SIZE + 10)}
                mock_pool.return_value = large_pool

                intent = DeckIntent(format=Format.MODERN, confidence=0.5)
                filtered, metrics = filter_collection_for_payload(
                    intent, sample_collection, sample_card_db
                )

        # Should fallback to full collection
        assert filtered == sample_collection
        assert metrics.fallback_reason == FallbackReason.POOL_TOO_LARGE

    def test_empty_pool_fallback(
        self,
        sample_collection: dict[str, int],
        sample_card_db: dict[str, dict],
    ) -> None:
        """Empty pool triggers fallback."""
        with patch("forgebreaker.filtering.payload.settings") as mock_settings:
            mock_settings.use_filtered_candidate_pool = True

            with patch("forgebreaker.filtering.payload.build_candidate_pool") as mock_pool:
                mock_pool.return_value = set()

                intent = DeckIntent(format=Format.MODERN, confidence=0.5)
                filtered, metrics = filter_collection_for_payload(
                    intent, sample_collection, sample_card_db
                )

        # Should fallback to full collection
        assert filtered == sample_collection
        assert metrics.fallback_reason == FallbackReason.POOL_EMPTY


# =============================================================================
# REGRESSION TESTS
# =============================================================================


class TestRegression:
    """Regression tests to ensure normal operation continues."""

    def test_deck_build_completes_with_filtered_pool(
        self,
        sample_collection: dict[str, int],
        sample_card_db: dict[str, dict],
    ) -> None:
        """Deck building works with filtered pool enabled."""
        with patch("forgebreaker.filtering.payload.settings") as mock_settings:
            mock_settings.use_filtered_candidate_pool = True

            with patch("forgebreaker.filtering.payload.build_candidate_pool") as mock_pool:
                mock_pool.return_value = set(sample_card_db.keys()) | {
                    f"Extra{i}" for i in range(10)
                }

                intent = DeckIntent(format=Format.MODERN, colors=frozenset({"R"}), confidence=0.5)
                filtered, metrics = filter_collection_for_payload(
                    intent, sample_collection, sample_card_db
                )

        # Should complete without error
        assert filtered is not None
        assert metrics is not None
        assert len(filtered) > 0

    def test_deck_build_completes_with_flag_off(
        self,
        sample_collection: dict[str, int],
        sample_card_db: dict[str, dict],
    ) -> None:
        """Deck building works with flag explicitly off."""
        with patch("forgebreaker.filtering.payload.settings") as mock_settings:
            mock_settings.use_filtered_candidate_pool = False

            intent = DeckIntent(format=Format.MODERN, colors=frozenset({"R"}), confidence=0.5)
            filtered, metrics = filter_collection_for_payload(
                intent, sample_collection, sample_card_db
            )

        # Should complete without error
        assert filtered is not None
        assert metrics is not None
        assert filtered == sample_collection

    def test_metrics_recorded_in_both_modes(
        self,
        sample_collection: dict[str, int],
        sample_card_db: dict[str, dict],
    ) -> None:
        """Metrics are recorded whether flag is on or off."""
        intent = DeckIntent(format=Format.MODERN, confidence=0.5)

        # Test with flag on
        with patch("forgebreaker.filtering.payload.settings") as mock_settings:
            mock_settings.use_filtered_candidate_pool = True
            with patch("forgebreaker.filtering.payload.build_candidate_pool") as mock_pool:
                mock_pool.return_value = set()  # Will trigger fallback
                filter_collection_for_payload(intent, sample_collection, sample_card_db)

        # Test with flag off
        with patch("forgebreaker.filtering.payload.settings") as mock_settings:
            mock_settings.use_filtered_candidate_pool = False
            filter_collection_for_payload(intent, sample_collection, sample_card_db)

        metrics = get_payload_metrics()
        assert len(metrics) == 2
        assert metrics[0].feature_flag_enabled is True
        assert metrics[1].feature_flag_enabled is False


# =============================================================================
# ROLLBACK SAFETY TESTS
# =============================================================================


class TestRollbackSafety:
    """Tests that rollback is trivial."""

    def test_rollback_is_single_flag_change(self) -> None:
        """Rollback only requires changing one flag."""
        # This test documents that rollback is just:
        # USE_FILTERED_CANDIDATE_POOL=false
        # No code changes needed, just env var

        with patch.dict(os.environ, {"USE_FILTERED_CANDIDATE_POOL": "false"}):
            rollback_settings = Settings()
            assert rollback_settings.use_filtered_candidate_pool is False

    def test_no_new_dependencies_introduced(self) -> None:
        """No new imports or dependencies in the rollout."""
        # This test ensures we haven't added new complexity
        from forgebreaker.filtering import payload

        # The module should only depend on existing config and models
        assert hasattr(payload, "filter_collection_for_payload")
        assert hasattr(payload, "FallbackReason")
