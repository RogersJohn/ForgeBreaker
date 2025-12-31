"""
Tests for Payload Filtering (PR 4).

These tests verify:
- Flag OFF → payload identical to pre-PR behavior
- Flag ON + valid pool → reduced payload
- Flag ON + empty pool → fallback to full collection
- Flag ON + oversized pool → fallback to full collection
- Regression: deck build still completes
"""

from unittest.mock import patch

import pytest

from forgebreaker.config import (
    MAX_CANDIDATE_POOL_SIZE,
    MIN_CANDIDATE_POOL_SIZE,
)
from forgebreaker.filtering.payload import (
    FallbackReason,
    filter_card_db_for_payload,
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
        "Counterspell": 2,
        "Island": 10,
    }


@pytest.fixture
def sample_card_db() -> dict[str, dict]:
    """Sample card database."""
    return {
        "Lightning Bolt": {
            "name": "Lightning Bolt",
            "type_line": "Instant",
            "mana_cost": "{R}",
            "cmc": 1,
            "colors": ["R"],
            "color_identity": ["R"],
            "keywords": [],
            "rarity": "common",
            "oracle_text": "Lightning Bolt deals 3 damage to any target.",
            "legalities": {"modern": "legal", "standard": "not_legal"},
        },
        "Shock": {
            "name": "Shock",
            "type_line": "Instant",
            "mana_cost": "{R}",
            "cmc": 1,
            "colors": ["R"],
            "color_identity": ["R"],
            "keywords": [],
            "rarity": "common",
            "oracle_text": "Shock deals 2 damage to any target.",
            "legalities": {"modern": "legal", "standard": "legal"},
        },
        "Goblin Guide": {
            "name": "Goblin Guide",
            "type_line": "Creature — Goblin Scout",
            "mana_cost": "{R}",
            "cmc": 1,
            "colors": ["R"],
            "color_identity": ["R"],
            "keywords": ["Haste"],
            "rarity": "rare",
            "oracle_text": "Haste. Whenever Goblin Guide attacks...",
            "legalities": {"modern": "legal", "standard": "not_legal"},
        },
        "Monastery Swiftspear": {
            "name": "Monastery Swiftspear",
            "type_line": "Creature — Human Monk",
            "mana_cost": "{R}",
            "cmc": 1,
            "colors": ["R"],
            "color_identity": ["R"],
            "keywords": ["Haste", "Prowess"],
            "rarity": "uncommon",
            "oracle_text": "Haste. Prowess.",
            "legalities": {"modern": "legal", "standard": "legal"},
        },
        "Mountain": {
            "name": "Mountain",
            "type_line": "Basic Land — Mountain",
            "mana_cost": "",
            "cmc": 0,
            "colors": [],
            "color_identity": [],
            "keywords": [],
            "rarity": "common",
            "legalities": {"modern": "legal", "standard": "legal"},
        },
        "Counterspell": {
            "name": "Counterspell",
            "type_line": "Instant",
            "mana_cost": "{U}{U}",
            "cmc": 2,
            "colors": ["U"],
            "color_identity": ["U"],
            "keywords": [],
            "rarity": "common",
            "oracle_text": "Counter target spell.",
            "legalities": {"modern": "legal", "standard": "not_legal"},
        },
        "Island": {
            "name": "Island",
            "type_line": "Basic Land — Island",
            "mana_cost": "",
            "cmc": 0,
            "colors": [],
            "color_identity": [],
            "keywords": [],
            "rarity": "common",
            "legalities": {"modern": "legal", "standard": "legal"},
        },
    }


class TestFlagOff:
    """Tests when USE_FILTERED_CANDIDATE_POOL is False."""

    def test_collection_unchanged_when_flag_off(
        self,
        sample_collection: dict[str, int],
        sample_card_db: dict[str, dict],
    ) -> None:
        """Flag OFF → collection returned unchanged."""
        with patch("forgebreaker.filtering.payload.settings") as mock_settings:
            mock_settings.use_filtered_candidate_pool = False

            intent = DeckIntent(format=Format.MODERN, colors=frozenset({"R"}), confidence=0.5)
            filtered, metrics = filter_collection_for_payload(
                intent, sample_collection, sample_card_db
            )

        # Collection should be identical
        assert filtered == sample_collection
        assert metrics.fallback_reason == FallbackReason.FLAG_OFF
        assert metrics.feature_flag_enabled is False

    def test_card_db_unchanged_when_flag_off(
        self,
        sample_card_db: dict[str, dict],
    ) -> None:
        """Flag OFF → card DB returned unchanged."""
        with patch("forgebreaker.filtering.payload.settings") as mock_settings:
            mock_settings.use_filtered_candidate_pool = False

            intent = DeckIntent(format=Format.MODERN, confidence=0.5)
            filtered, metrics = filter_card_db_for_payload(intent, sample_card_db)

        # Card DB should be identical (same reference)
        assert filtered is sample_card_db
        assert metrics.fallback_reason == FallbackReason.FLAG_OFF


class TestFlagOnValidPool:
    """Tests when flag ON with valid candidate pool."""

    def test_collection_filtered_when_flag_on(
        self,
        sample_collection: dict[str, int],
        sample_card_db: dict[str, dict],
    ) -> None:
        """Flag ON + valid pool → collection is filtered."""
        with patch("forgebreaker.filtering.payload.settings") as mock_settings:
            mock_settings.use_filtered_candidate_pool = True

            # Create intent that will produce a valid-sized pool
            # Modern red cards: Lightning Bolt, Shock, Goblin Guide, Monastery Swiftspear, Mountain
            intent = DeckIntent(format=Format.MODERN, colors=frozenset({"R"}), confidence=0.5)

            # Mock build_candidate_pool to return a valid-sized pool
            with patch("forgebreaker.filtering.payload.build_candidate_pool") as mock_pool:
                # Return pool with cards that match collection
                mock_pool.return_value = {
                    "Lightning Bolt",
                    "Shock",
                    "Goblin Guide",
                    "Monastery Swiftspear",
                    "Mountain",
                    # Add more to exceed MIN_CANDIDATE_POOL_SIZE
                    "Card1",
                    "Card2",
                    "Card3",
                    "Card4",
                    "Card5",
                }

                filtered, metrics = filter_collection_for_payload(
                    intent, sample_collection, sample_card_db
                )

        # Filtered collection should only have cards in candidate pool
        assert "Lightning Bolt" in filtered
        assert "Shock" in filtered
        assert "Counterspell" not in filtered  # Not in pool
        assert "Island" not in filtered  # Not in pool
        assert metrics.fallback_reason == FallbackReason.NONE
        assert metrics.filtered_collection_size < metrics.full_collection_size

    def test_token_count_reduced(
        self,
        sample_collection: dict[str, int],
        sample_card_db: dict[str, dict],
    ) -> None:
        """Flag ON + valid pool → token estimate is reduced."""
        with patch("forgebreaker.filtering.payload.settings") as mock_settings:
            mock_settings.use_filtered_candidate_pool = True

            intent = DeckIntent(format=Format.MODERN, colors=frozenset({"R"}), confidence=0.5)

            with patch("forgebreaker.filtering.payload.build_candidate_pool") as mock_pool:
                # Pool with only red cards
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

                _, metrics = filter_collection_for_payload(
                    intent, sample_collection, sample_card_db
                )

        # Token estimate should be less than full collection
        full_tokens = len(sample_collection) * 20  # ~20 tokens per card
        assert metrics.tokens_estimated < full_tokens

    def test_card_db_excludes_oracle_text(
        self,
        sample_card_db: dict[str, dict],
    ) -> None:
        """Flag ON → filtered card DB excludes oracle_text."""
        with patch("forgebreaker.filtering.payload.settings") as mock_settings:
            mock_settings.use_filtered_candidate_pool = True

            intent = DeckIntent(format=Format.MODERN, confidence=0.5)

            with patch("forgebreaker.filtering.payload.build_candidate_pool") as mock_pool:
                # Return pool with all sample cards + extra to exceed MIN_CANDIDATE_POOL_SIZE
                pool = set(sample_card_db.keys())
                for i in range(MIN_CANDIDATE_POOL_SIZE):
                    pool.add(f"ExtraCard{i}")
                mock_pool.return_value = pool

                filtered, metrics = filter_card_db_for_payload(intent, sample_card_db)

        # Verify we got filtered output (not fallback)
        assert metrics.fallback_reason == FallbackReason.NONE

        # Check that oracle_text is NOT in filtered cards
        for name, card in filtered.items():
            assert "oracle_text" not in card, f"{name} has oracle_text"
            # But should have high-level info
            assert "type_line" in card
            assert "mana_cost" in card
            assert "cmc" in card


class TestFlagOnEmptyPool:
    """Tests when flag ON but pool is empty."""

    def test_empty_pool_fallback(
        self,
        sample_collection: dict[str, int],
        sample_card_db: dict[str, dict],
    ) -> None:
        """Flag ON + empty pool → full collection used."""
        with patch("forgebreaker.filtering.payload.settings") as mock_settings:
            mock_settings.use_filtered_candidate_pool = True

            intent = DeckIntent(confidence=0.5)

            with patch("forgebreaker.filtering.payload.build_candidate_pool") as mock_pool:
                mock_pool.return_value = set()  # Empty pool

                filtered, metrics = filter_collection_for_payload(
                    intent, sample_collection, sample_card_db
                )

        assert filtered == sample_collection
        assert metrics.fallback_reason == FallbackReason.POOL_EMPTY

    def test_empty_pool_logged(
        self,
        sample_collection: dict[str, int],
        sample_card_db: dict[str, dict],
    ) -> None:
        """Fallback due to empty pool is logged."""
        with patch("forgebreaker.filtering.payload.settings") as mock_settings:
            mock_settings.use_filtered_candidate_pool = True

            with patch("forgebreaker.filtering.payload.build_candidate_pool") as mock_pool:
                mock_pool.return_value = set()

                with patch("forgebreaker.filtering.payload.logger") as mock_logger:
                    intent = DeckIntent(confidence=0.5)
                    filter_collection_for_payload(intent, sample_collection, sample_card_db)

        # Check that warning was logged
        mock_logger.warning.assert_called()


class TestFlagOnOversizedPool:
    """Tests when flag ON but pool exceeds MAX_CANDIDATE_POOL_SIZE."""

    def test_oversized_pool_fallback(
        self,
        sample_collection: dict[str, int],
        sample_card_db: dict[str, dict],
    ) -> None:
        """Flag ON + oversized pool → full collection used."""
        with patch("forgebreaker.filtering.payload.settings") as mock_settings:
            mock_settings.use_filtered_candidate_pool = True

            intent = DeckIntent(confidence=0.5)

            with patch("forgebreaker.filtering.payload.build_candidate_pool") as mock_pool:
                # Create pool larger than MAX
                large_pool = {f"Card{i}" for i in range(MAX_CANDIDATE_POOL_SIZE + 10)}
                mock_pool.return_value = large_pool

                filtered, metrics = filter_collection_for_payload(
                    intent, sample_collection, sample_card_db
                )

        assert filtered == sample_collection
        assert metrics.fallback_reason == FallbackReason.POOL_TOO_LARGE

    def test_oversized_pool_logged(
        self,
        sample_collection: dict[str, int],
        sample_card_db: dict[str, dict],
    ) -> None:
        """Fallback due to oversized pool is logged."""
        with patch("forgebreaker.filtering.payload.settings") as mock_settings:
            mock_settings.use_filtered_candidate_pool = True

            with patch("forgebreaker.filtering.payload.build_candidate_pool") as mock_pool:
                large_pool = {f"Card{i}" for i in range(MAX_CANDIDATE_POOL_SIZE + 10)}
                mock_pool.return_value = large_pool

                with patch("forgebreaker.filtering.payload.logger") as mock_logger:
                    intent = DeckIntent(confidence=0.5)
                    filter_collection_for_payload(intent, sample_collection, sample_card_db)

        mock_logger.warning.assert_called()


class TestFlagOnUndersizedPool:
    """Tests when flag ON but pool is below MIN_CANDIDATE_POOL_SIZE."""

    def test_undersized_pool_fallback(
        self,
        sample_collection: dict[str, int],
        sample_card_db: dict[str, dict],
    ) -> None:
        """Flag ON + undersized pool → full collection used."""
        with patch("forgebreaker.filtering.payload.settings") as mock_settings:
            mock_settings.use_filtered_candidate_pool = True

            intent = DeckIntent(confidence=0.5)

            with patch("forgebreaker.filtering.payload.build_candidate_pool") as mock_pool:
                # Create pool smaller than MIN
                small_pool = {f"Card{i}" for i in range(MIN_CANDIDATE_POOL_SIZE - 1)}
                mock_pool.return_value = small_pool

                filtered, metrics = filter_collection_for_payload(
                    intent, sample_collection, sample_card_db
                )

        assert filtered == sample_collection
        assert metrics.fallback_reason == FallbackReason.POOL_TOO_SMALL


class TestExceptionHandling:
    """Tests for exception handling and fail-safe behavior."""

    def test_exception_fallback(
        self,
        sample_collection: dict[str, int],
        sample_card_db: dict[str, dict],
    ) -> None:
        """Exception during filtering → full collection used."""
        with patch("forgebreaker.filtering.payload.settings") as mock_settings:
            mock_settings.use_filtered_candidate_pool = True

            with patch("forgebreaker.filtering.payload.build_candidate_pool") as mock_pool:
                mock_pool.side_effect = RuntimeError("Unexpected error")

                intent = DeckIntent(confidence=0.5)
                filtered, metrics = filter_collection_for_payload(
                    intent, sample_collection, sample_card_db
                )

        assert filtered == sample_collection
        assert metrics.fallback_reason == FallbackReason.EXCEPTION

    def test_exception_logged(
        self,
        sample_collection: dict[str, int],
        sample_card_db: dict[str, dict],
    ) -> None:
        """Exception is logged."""
        with patch("forgebreaker.filtering.payload.settings") as mock_settings:
            mock_settings.use_filtered_candidate_pool = True

            with patch("forgebreaker.filtering.payload.build_candidate_pool") as mock_pool:
                mock_pool.side_effect = RuntimeError("Test error")

                with patch("forgebreaker.filtering.payload.logger") as mock_logger:
                    intent = DeckIntent(confidence=0.5)
                    filter_collection_for_payload(intent, sample_collection, sample_card_db)

        mock_logger.exception.assert_called()


class TestMetrics:
    """Tests for metrics recording."""

    def test_metrics_recorded_flag_off(
        self,
        sample_collection: dict[str, int],
        sample_card_db: dict[str, dict],
    ) -> None:
        """Metrics recorded even when flag is off."""
        with patch("forgebreaker.filtering.payload.settings") as mock_settings:
            mock_settings.use_filtered_candidate_pool = False

            intent = DeckIntent(confidence=0.5)
            filter_collection_for_payload(intent, sample_collection, sample_card_db)

        metrics = get_payload_metrics()
        assert len(metrics) == 1
        assert metrics[0].feature_flag_enabled is False

    def test_metrics_recorded_flag_on(
        self,
        sample_collection: dict[str, int],
        sample_card_db: dict[str, dict],
    ) -> None:
        """Metrics recorded when flag is on."""
        with patch("forgebreaker.filtering.payload.settings") as mock_settings:
            mock_settings.use_filtered_candidate_pool = True

            with patch("forgebreaker.filtering.payload.build_candidate_pool") as mock_pool:
                mock_pool.return_value = set(sample_card_db.keys())

                intent = DeckIntent(confidence=0.5)
                filter_collection_for_payload(intent, sample_collection, sample_card_db)

        metrics = get_payload_metrics()
        assert len(metrics) == 1
        assert metrics[0].feature_flag_enabled is True

    def test_multiple_calls_accumulate_metrics(
        self,
        sample_collection: dict[str, int],
        sample_card_db: dict[str, dict],
    ) -> None:
        """Multiple filter calls accumulate metrics."""
        with patch("forgebreaker.filtering.payload.settings") as mock_settings:
            mock_settings.use_filtered_candidate_pool = False

            intent = DeckIntent(confidence=0.5)
            filter_collection_for_payload(intent, sample_collection, sample_card_db)
            filter_collection_for_payload(intent, sample_collection, sample_card_db)
            filter_collection_for_payload(intent, sample_collection, sample_card_db)

        metrics = get_payload_metrics()
        assert len(metrics) == 3


class TestSafetyLimits:
    """Tests for safety limit constants."""

    def test_min_pool_size_reasonable(self) -> None:
        """MIN_CANDIDATE_POOL_SIZE is a reasonable value."""
        assert MIN_CANDIDATE_POOL_SIZE >= 5
        assert MIN_CANDIDATE_POOL_SIZE <= 20

    def test_max_pool_size_reasonable(self) -> None:
        """MAX_CANDIDATE_POOL_SIZE is a reasonable value."""
        assert MAX_CANDIDATE_POOL_SIZE >= 50
        assert MAX_CANDIDATE_POOL_SIZE <= 200

    def test_min_less_than_max(self) -> None:
        """MIN < MAX."""
        assert MIN_CANDIDATE_POOL_SIZE < MAX_CANDIDATE_POOL_SIZE


class TestRegression:
    """Regression tests to ensure deck building still works."""

    def test_empty_collection_handled(
        self,
        sample_card_db: dict[str, dict],
    ) -> None:
        """Empty collection doesn't cause issues."""
        with patch("forgebreaker.filtering.payload.settings") as mock_settings:
            mock_settings.use_filtered_candidate_pool = True

            with patch("forgebreaker.filtering.payload.build_candidate_pool") as mock_pool:
                mock_pool.return_value = {"SomeCard"}

                intent = DeckIntent(confidence=0.5)
                filtered, metrics = filter_collection_for_payload(intent, {}, sample_card_db)

        # Should return empty collection (not crash)
        assert filtered == {}

    def test_empty_card_db_handled(self) -> None:
        """Empty card DB doesn't cause issues."""
        with patch("forgebreaker.filtering.payload.settings") as mock_settings:
            mock_settings.use_filtered_candidate_pool = True

            with patch("forgebreaker.filtering.payload.build_candidate_pool") as mock_pool:
                mock_pool.return_value = set()

                intent = DeckIntent(confidence=0.5)
                filtered, metrics = filter_card_db_for_payload(intent, {})

        # Should return empty card DB (not crash)
        assert filtered == {}
