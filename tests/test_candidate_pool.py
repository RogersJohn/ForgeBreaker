"""
Tests for Candidate Pool Builder.

These tests verify:
- Format filtering (non-legal cards removed)
- Color filtering (off-color cards removed, colorless retained)
- Tribe filtering (non-tribal cards removed)
- Monotonicity (each filter reduces or preserves size)
- Determinism (same intent + DB → same pool)
- No-intent passthrough (empty intent → full DB)
"""

import pytest

from forgebreaker.filtering.candidate_pool import (
    build_candidate_pool,
    get_pool_metrics,
    reset_pool_metrics,
)
from forgebreaker.models.intent import Archetype, DeckIntent, Format


@pytest.fixture(autouse=True)
def reset_metrics() -> None:
    """Reset metrics before each test."""
    reset_pool_metrics()


@pytest.fixture
def sample_card_db() -> dict[str, dict]:
    """Sample card database for testing."""
    return {
        "Lightning Bolt": {
            "name": "Lightning Bolt",
            "type_line": "Instant",
            "color_identity": ["R"],
            "legalities": {
                "standard": "not_legal",
                "modern": "legal",
                "legacy": "legal",
            },
        },
        "Shock": {
            "name": "Shock",
            "type_line": "Instant",
            "color_identity": ["R"],
            "legalities": {
                "standard": "legal",
                "modern": "legal",
                "legacy": "legal",
            },
        },
        "Counterspell": {
            "name": "Counterspell",
            "type_line": "Instant",
            "color_identity": ["U"],
            "legalities": {
                "standard": "not_legal",
                "modern": "legal",
                "legacy": "legal",
            },
        },
        "Sol Ring": {
            "name": "Sol Ring",
            "type_line": "Artifact",
            "color_identity": [],
            "legalities": {
                "standard": "not_legal",
                "modern": "not_legal",
                "legacy": "banned",
            },
        },
        "Shivan Dragon": {
            "name": "Shivan Dragon",
            "type_line": "Creature — Dragon",
            "color_identity": ["R"],
            "legalities": {
                "standard": "not_legal",
                "modern": "legal",
                "legacy": "legal",
            },
        },
        "Elvish Mystic": {
            "name": "Elvish Mystic",
            "type_line": "Creature — Elf Druid",
            "color_identity": ["G"],
            "legalities": {
                "standard": "not_legal",
                "modern": "legal",
                "legacy": "legal",
            },
        },
        "Llanowar Elves": {
            "name": "Llanowar Elves",
            "type_line": "Creature — Elf Druid",
            "color_identity": ["G"],
            "legalities": {
                "standard": "legal",
                "modern": "legal",
                "legacy": "legal",
            },
        },
        "Ornithopter": {
            "name": "Ornithopter",
            "type_line": "Artifact Creature — Thopter",
            "color_identity": [],
            "legalities": {
                "standard": "legal",
                "modern": "legal",
                "legacy": "legal",
            },
        },
        "Nicol Bolas, Dragon-God": {
            "name": "Nicol Bolas, Dragon-God",
            "type_line": "Legendary Planeswalker — Bolas",
            "color_identity": ["U", "B", "R"],
            "legalities": {
                "standard": "not_legal",
                "modern": "legal",
                "legacy": "legal",
            },
        },
        "Terror of the Peaks": {
            "name": "Terror of the Peaks",
            "type_line": "Creature — Dragon",
            "color_identity": ["R"],
            "legalities": {
                "standard": "legal",
                "modern": "legal",
                "legacy": "legal",
            },
        },
    }


class TestFormatFiltering:
    """Tests for format legality filtering."""

    def test_removes_non_legal_cards(self, sample_card_db: dict) -> None:
        """Non-legal cards are removed from pool."""
        intent = DeckIntent(format=Format.STANDARD, confidence=0.5)
        pool = build_candidate_pool(intent, sample_card_db)

        # Lightning Bolt is not legal in Standard
        assert "Lightning Bolt" not in pool
        # Shock is legal in Standard
        assert "Shock" in pool

    def test_keeps_legal_cards(self, sample_card_db: dict) -> None:
        """Legal cards remain in pool."""
        intent = DeckIntent(format=Format.MODERN, confidence=0.5)
        pool = build_candidate_pool(intent, sample_card_db)

        assert "Lightning Bolt" in pool
        assert "Shock" in pool
        assert "Counterspell" in pool

    def test_no_format_passthrough(self, sample_card_db: dict) -> None:
        """No format specified → all cards pass."""
        intent = DeckIntent(confidence=0.5)
        pool = build_candidate_pool(intent, sample_card_db)

        assert len(pool) == len(sample_card_db)


class TestColorFiltering:
    """Tests for color identity filtering."""

    def test_removes_off_color_cards(self, sample_card_db: dict) -> None:
        """Off-color cards are removed from pool."""
        intent = DeckIntent(colors=frozenset({"R"}), confidence=0.5)
        pool = build_candidate_pool(intent, sample_card_db)

        # Blue card should be removed
        assert "Counterspell" not in pool
        # Green cards should be removed
        assert "Elvish Mystic" not in pool
        # Red cards should remain
        assert "Shock" in pool
        assert "Lightning Bolt" in pool

    def test_retains_colorless(self, sample_card_db: dict) -> None:
        """Colorless cards are always retained."""
        intent = DeckIntent(colors=frozenset({"R"}), confidence=0.5)
        pool = build_candidate_pool(intent, sample_card_db)

        # Sol Ring is colorless
        assert "Sol Ring" in pool
        # Ornithopter is colorless
        assert "Ornithopter" in pool

    def test_multicolor_subset(self, sample_card_db: dict) -> None:
        """Multi-color cards pass if identity is subset of allowed."""
        intent = DeckIntent(colors=frozenset({"U", "B", "R"}), confidence=0.5)
        pool = build_candidate_pool(intent, sample_card_db)

        # Nicol Bolas is UBR — exact match
        assert "Nicol Bolas, Dragon-God" in pool

    def test_multicolor_not_subset(self, sample_card_db: dict) -> None:
        """Multi-color cards fail if identity is not subset."""
        intent = DeckIntent(colors=frozenset({"R", "G"}), confidence=0.5)
        pool = build_candidate_pool(intent, sample_card_db)

        # Nicol Bolas is UBR — not a subset of RG
        assert "Nicol Bolas, Dragon-God" not in pool

    def test_no_colors_passthrough(self, sample_card_db: dict) -> None:
        """No colors specified → all cards pass."""
        intent = DeckIntent(confidence=0.5)
        pool = build_candidate_pool(intent, sample_card_db)

        assert len(pool) == len(sample_card_db)


class TestTribeFiltering:
    """Tests for creature type filtering."""

    def test_removes_non_tribal_cards(self, sample_card_db: dict) -> None:
        """Non-tribal cards are removed when tribe is set."""
        intent = DeckIntent(tribe="Dragon", confidence=0.5)
        pool = build_candidate_pool(intent, sample_card_db)

        # Non-dragons should be removed
        assert "Shock" not in pool
        assert "Elvish Mystic" not in pool
        # Dragons should remain
        assert "Shivan Dragon" in pool
        assert "Terror of the Peaks" in pool

    def test_case_insensitive(self, sample_card_db: dict) -> None:
        """Tribe matching is case insensitive."""
        intent = DeckIntent(tribe="dragon", confidence=0.5)
        pool = build_candidate_pool(intent, sample_card_db)

        assert "Shivan Dragon" in pool

    def test_partial_type_line_match(self, sample_card_db: dict) -> None:
        """Tribe can match part of type line."""
        intent = DeckIntent(tribe="Elf", confidence=0.5)
        pool = build_candidate_pool(intent, sample_card_db)

        # "Creature — Elf Druid" contains "Elf"
        assert "Elvish Mystic" in pool
        assert "Llanowar Elves" in pool

    def test_no_tribe_passthrough(self, sample_card_db: dict) -> None:
        """No tribe specified → all cards pass."""
        intent = DeckIntent(confidence=0.5)
        pool = build_candidate_pool(intent, sample_card_db)

        assert len(pool) == len(sample_card_db)


class TestArchetypeFiltering:
    """Tests for archetype filtering."""

    def test_archetype_passthrough(self, sample_card_db: dict) -> None:
        """Archetype filter is currently a passthrough."""
        intent = DeckIntent(archetype=Archetype.AGGRO, confidence=0.5)
        pool = build_candidate_pool(intent, sample_card_db)

        # All cards should remain (archetype tagging not implemented)
        assert len(pool) == len(sample_card_db)


class TestMonotonicity:
    """Tests that filtering is monotonic (only removes cards)."""

    def test_each_filter_reduces_or_preserves(self, sample_card_db: dict) -> None:
        """Each filter step reduces or preserves pool size."""
        intent = DeckIntent(
            format=Format.MODERN,
            colors=frozenset({"R"}),
            tribe="Dragon",
            confidence=0.5,
        )
        build_candidate_pool(intent, sample_card_db)

        metrics = get_pool_metrics()[0]

        # Each step should be ≤ previous
        assert metrics.after_format_filter <= metrics.total_cards
        assert metrics.after_color_filter <= metrics.after_format_filter
        assert metrics.after_tribe_filter <= metrics.after_color_filter
        assert metrics.after_archetype_filter <= metrics.after_tribe_filter
        assert metrics.final_pool_size <= metrics.after_archetype_filter

    def test_progressive_reduction(self, sample_card_db: dict) -> None:
        """Applying more filters results in smaller or equal pool."""
        # No filters
        intent_none = DeckIntent(confidence=0.5)
        pool_none = build_candidate_pool(intent_none, sample_card_db)

        # Format only
        intent_format = DeckIntent(format=Format.MODERN, confidence=0.5)
        pool_format = build_candidate_pool(intent_format, sample_card_db)

        # Format + color
        intent_format_color = DeckIntent(
            format=Format.MODERN,
            colors=frozenset({"R"}),
            confidence=0.5,
        )
        pool_format_color = build_candidate_pool(intent_format_color, sample_card_db)

        assert len(pool_format) <= len(pool_none)
        assert len(pool_format_color) <= len(pool_format)


class TestDeterminism:
    """Tests that filtering is deterministic."""

    def test_same_input_same_output(self, sample_card_db: dict) -> None:
        """Same intent + DB → same pool."""
        intent = DeckIntent(
            format=Format.STANDARD,
            colors=frozenset({"R", "G"}),
            tribe="Dragon",
            confidence=0.5,
        )

        pools = [build_candidate_pool(intent, sample_card_db) for _ in range(5)]

        # All pools should be identical
        assert all(pool == pools[0] for pool in pools)

    def test_deterministic_across_calls(self, sample_card_db: dict) -> None:
        """Multiple calls produce identical results."""
        intent = DeckIntent(
            format=Format.MODERN,
            colors=frozenset({"U", "R"}),
            confidence=0.5,
        )

        pool1 = build_candidate_pool(intent, sample_card_db)
        pool2 = build_candidate_pool(intent, sample_card_db)

        assert pool1 == pool2


class TestNoIntentPassthrough:
    """Tests that empty intent returns full DB."""

    def test_empty_intent_full_db(self, sample_card_db: dict) -> None:
        """Empty intent → full DB returned."""
        intent = DeckIntent(confidence=0.1)
        pool = build_candidate_pool(intent, sample_card_db)

        assert pool == set(sample_card_db.keys())

    def test_empty_intent_no_reduction(self, sample_card_db: dict) -> None:
        """Empty intent shows no reduction in metrics."""
        intent = DeckIntent(confidence=0.1)
        build_candidate_pool(intent, sample_card_db)

        metrics = get_pool_metrics()[0]
        assert metrics.total_cards == metrics.final_pool_size


class TestMetrics:
    """Tests for metrics recording."""

    def test_metrics_recorded(self, sample_card_db: dict) -> None:
        """Metrics are recorded after each build."""
        intent = DeckIntent(format=Format.STANDARD, confidence=0.5)
        build_candidate_pool(intent, sample_card_db)

        metrics_list = get_pool_metrics()
        assert len(metrics_list) == 1

    def test_multiple_builds_multiple_metrics(self, sample_card_db: dict) -> None:
        """Multiple builds record multiple metrics."""
        intent = DeckIntent(confidence=0.5)

        build_candidate_pool(intent, sample_card_db)
        build_candidate_pool(intent, sample_card_db)
        build_candidate_pool(intent, sample_card_db)

        metrics_list = get_pool_metrics()
        assert len(metrics_list) == 3

    def test_metrics_values(self, sample_card_db: dict) -> None:
        """Metrics contain correct values."""
        intent = DeckIntent(
            format=Format.STANDARD,
            colors=frozenset({"R"}),
            confidence=0.5,
        )
        build_candidate_pool(intent, sample_card_db)

        metrics = get_pool_metrics()[0]

        assert metrics.total_cards == 10  # Sample DB size
        assert isinstance(metrics.after_format_filter, int)
        assert isinstance(metrics.after_color_filter, int)
        assert isinstance(metrics.final_pool_size, int)

    def test_reset_clears_metrics(self, sample_card_db: dict) -> None:
        """reset_pool_metrics clears history."""
        intent = DeckIntent(confidence=0.5)
        build_candidate_pool(intent, sample_card_db)

        reset_pool_metrics()
        assert len(get_pool_metrics()) == 0


class TestCombinedFilters:
    """Tests for multiple filters applied together."""

    def test_format_and_color(self, sample_card_db: dict) -> None:
        """Format + color filters combine correctly."""
        intent = DeckIntent(
            format=Format.STANDARD,
            colors=frozenset({"R"}),
            confidence=0.5,
        )
        pool = build_candidate_pool(intent, sample_card_db)

        # Shock: Standard-legal, red
        assert "Shock" in pool
        # Lightning Bolt: Not Standard-legal
        assert "Lightning Bolt" not in pool
        # Llanowar Elves: Standard-legal but green
        assert "Llanowar Elves" not in pool
        # Terror of the Peaks: Standard-legal, red dragon
        assert "Terror of the Peaks" in pool
        # Ornithopter: Standard-legal, colorless
        assert "Ornithopter" in pool

    def test_all_filters(self, sample_card_db: dict) -> None:
        """All filters combine correctly."""
        intent = DeckIntent(
            format=Format.MODERN,
            colors=frozenset({"R"}),
            tribe="Dragon",
            archetype=Archetype.AGGRO,
            confidence=0.5,
        )
        pool = build_candidate_pool(intent, sample_card_db)

        # Only red dragons legal in Modern should remain
        assert "Shivan Dragon" in pool
        assert "Terror of the Peaks" in pool
        # Non-dragons removed by tribe filter
        assert "Lightning Bolt" not in pool
        # Wrong color removed
        assert "Counterspell" not in pool


class TestEdgeCases:
    """Tests for edge cases."""

    def test_empty_db(self) -> None:
        """Empty database returns empty pool."""
        intent = DeckIntent(confidence=0.5)
        pool = build_candidate_pool(intent, {})

        assert pool == set()

    def test_missing_legalities(self) -> None:
        """Cards with missing legalities are filtered out."""
        card_db = {
            "Unknown Card": {
                "name": "Unknown Card",
                "type_line": "Creature",
                # No legalities field
            },
        }
        intent = DeckIntent(format=Format.STANDARD, confidence=0.5)
        pool = build_candidate_pool(intent, card_db)

        assert "Unknown Card" not in pool

    def test_missing_color_identity(self) -> None:
        """Cards with missing color_identity fall back to colors."""
        card_db = {
            "Old Card": {
                "name": "Old Card",
                "type_line": "Instant",
                "colors": ["R"],
                # No color_identity field
            },
        }
        intent = DeckIntent(colors=frozenset({"R"}), confidence=0.5)
        pool = build_candidate_pool(intent, card_db)

        assert "Old Card" in pool

    def test_card_not_in_db(self) -> None:
        """Filter handles cards that somehow disappear from DB."""
        # This shouldn't happen in practice, but we should handle it
        card_db = {
            "Existing Card": {
                "name": "Existing Card",
                "type_line": "Creature",
                "color_identity": ["R"],
                "legalities": {"standard": "legal"},
            },
        }
        intent = DeckIntent(format=Format.STANDARD, confidence=0.5)
        pool = build_candidate_pool(intent, card_db)

        assert "Existing Card" in pool
        assert len(pool) == 1
