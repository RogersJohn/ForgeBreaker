"""
Tests for Assumption Surfacing (PR 6).

These are snapshot-style tests that verify:
1. Assumptions section appears when defaults are applied
2. No assumptions section when user explicitly specifies all values
3. Only defaulted fields are shown, not explicitly provided ones
4. Deck content is unchanged by adding assumptions
5. Adjustment affordance is included when assumptions are shown
"""

from forgebreaker.models.intent import Archetype, DeckIntent, Format
from forgebreaker.services.assumption_surfacing import (
    ADJUSTMENT_AFFORDANCE,
    AppliedDefaults,
    BuildDeckDefaults,
    format_assumptions_section,
    format_build_deck_assumptions,
    format_full_assumptions_section,
    track_applied_defaults,
)

# =============================================================================
# APPLIED DEFAULTS TRACKING
# =============================================================================


class TestAppliedDefaults:
    """Tests for AppliedDefaults dataclass."""

    def test_no_defaults_applied(self) -> None:
        """When nothing is defaulted, any_applied is False."""
        defaults = AppliedDefaults(
            format_defaulted=False,
            archetype_defaulted=False,
            colors_defaulted=False,
        )
        assert not defaults.any_applied

    def test_format_defaulted_only(self) -> None:
        """When only format is defaulted, any_applied is True."""
        defaults = AppliedDefaults(format_defaulted=True)
        assert defaults.any_applied

    def test_archetype_defaulted_only(self) -> None:
        """When only archetype is defaulted, any_applied is True."""
        defaults = AppliedDefaults(archetype_defaulted=True)
        assert defaults.any_applied

    def test_colors_defaulted_only(self) -> None:
        """When only colors is defaulted, any_applied is True."""
        defaults = AppliedDefaults(colors_defaulted=True)
        assert defaults.any_applied

    def test_all_defaulted(self) -> None:
        """When all are defaulted, any_applied is True."""
        defaults = AppliedDefaults(
            format_defaulted=True,
            archetype_defaulted=True,
            colors_defaulted=True,
        )
        assert defaults.any_applied


class TestTrackAppliedDefaults:
    """Tests for track_applied_defaults function."""

    def test_no_changes(self) -> None:
        """When intents are identical, no defaults were applied."""
        intent = DeckIntent(
            format=Format.STANDARD,
            archetype=Archetype.AGGRO,
            colors=frozenset({"R"}),
            confidence=0.8,
        )
        defaults = track_applied_defaults(intent, intent)

        assert not defaults.format_defaulted
        assert not defaults.archetype_defaulted
        assert not defaults.colors_defaulted

    def test_format_defaulted(self) -> None:
        """Detects when format was defaulted."""
        original = DeckIntent(confidence=0.3)
        resolved = DeckIntent(format=Format.STANDARD, confidence=0.5)

        defaults = track_applied_defaults(original, resolved)

        assert defaults.format_defaulted
        assert not defaults.archetype_defaulted
        assert not defaults.colors_defaulted

    def test_archetype_defaulted(self) -> None:
        """Detects when archetype was defaulted."""
        original = DeckIntent(format=Format.HISTORIC, confidence=0.3)
        resolved = DeckIntent(
            format=Format.HISTORIC,
            archetype=Archetype.MIDRANGE,
            confidence=0.5,
        )

        defaults = track_applied_defaults(original, resolved)

        assert not defaults.format_defaulted
        assert defaults.archetype_defaulted
        assert not defaults.colors_defaulted

    def test_colors_defaulted(self) -> None:
        """Detects when colors were defaulted."""
        original = DeckIntent(format=Format.STANDARD, confidence=0.3)
        resolved = DeckIntent(
            format=Format.STANDARD,
            colors=frozenset({"R", "G"}),
            confidence=0.5,
        )

        defaults = track_applied_defaults(original, resolved)

        assert not defaults.format_defaulted
        assert defaults.colors_defaulted

    def test_all_defaulted(self) -> None:
        """Detects when all fields were defaulted."""
        original = DeckIntent(confidence=0.1)
        resolved = DeckIntent(
            format=Format.STANDARD,
            archetype=Archetype.MIDRANGE,
            colors=frozenset({"W", "U"}),
            confidence=0.5,
        )

        defaults = track_applied_defaults(original, resolved)

        assert defaults.format_defaulted
        assert defaults.archetype_defaulted
        assert defaults.colors_defaulted


# =============================================================================
# ASSUMPTIONS SECTION FORMATTING
# =============================================================================


class TestFormatAssumptionsSection:
    """Tests for format_assumptions_section function."""

    def test_no_defaults_returns_none(self) -> None:
        """When no defaults were applied, returns None."""
        intent = DeckIntent(format=Format.STANDARD, confidence=0.8)
        defaults = AppliedDefaults()

        result = format_assumptions_section(intent, defaults)

        assert result is None

    def test_format_defaulted_shows_format(self) -> None:
        """When format was defaulted, shows format in assumptions."""
        intent = DeckIntent(format=Format.STANDARD, confidence=0.5)
        defaults = AppliedDefaults(format_defaulted=True)

        result = format_assumptions_section(intent, defaults)

        assert result is not None
        assert "Assumptions I made:" in result
        assert "Format: Standard" in result
        assert ADJUSTMENT_AFFORDANCE in result

    def test_archetype_defaulted_shows_archetype(self) -> None:
        """When archetype was defaulted, shows archetype in assumptions."""
        intent = DeckIntent(archetype=Archetype.MIDRANGE, confidence=0.5)
        defaults = AppliedDefaults(archetype_defaulted=True)

        result = format_assumptions_section(intent, defaults)

        assert result is not None
        assert "Archetype: Midrange" in result
        assert ADJUSTMENT_AFFORDANCE in result

    def test_colors_defaulted_shows_colors(self) -> None:
        """When colors were defaulted, shows colors in assumptions."""
        intent = DeckIntent(colors=frozenset({"R", "G"}), confidence=0.5)
        defaults = AppliedDefaults(colors_defaulted=True)

        result = format_assumptions_section(intent, defaults)

        assert result is not None
        assert "Colors:" in result
        assert ADJUSTMENT_AFFORDANCE in result

    def test_multiple_defaults_shows_all(self) -> None:
        """When multiple fields defaulted, shows all in assumptions."""
        intent = DeckIntent(
            format=Format.HISTORIC,
            archetype=Archetype.CONTROL,
            confidence=0.5,
        )
        defaults = AppliedDefaults(
            format_defaulted=True,
            archetype_defaulted=True,
        )

        result = format_assumptions_section(intent, defaults)

        assert result is not None
        assert "Format: Historic" in result
        assert "Archetype: Control" in result
        assert ADJUSTMENT_AFFORDANCE in result

    def test_adjustment_affordance_at_end(self) -> None:
        """Adjustment affordance appears after the assumptions list."""
        intent = DeckIntent(format=Format.STANDARD, confidence=0.5)
        defaults = AppliedDefaults(format_defaulted=True)

        result = format_assumptions_section(intent, defaults)

        assert result is not None
        lines = result.split("\n")
        # Adjustment affordance should be the last non-empty line
        non_empty = [line for line in lines if line.strip()]
        assert non_empty[-1] == ADJUSTMENT_AFFORDANCE


class TestFormatFullAssumptionsSection:
    """Tests for format_full_assumptions_section convenience function."""

    def test_fully_specified_intent_no_assumptions(self) -> None:
        """When user specifies everything, no assumptions shown."""
        intent = DeckIntent(
            format=Format.EXPLORER,
            archetype=Archetype.AGGRO,
            colors=frozenset({"R", "W"}),
            tribe="Goblin",
            confidence=0.9,
        )

        result = format_full_assumptions_section(intent, intent)

        assert result is None

    def test_empty_intent_shows_defaults(self) -> None:
        """When intent is empty and defaults applied, shows assumptions."""
        original = DeckIntent(confidence=0.1)
        resolved = DeckIntent(
            format=Format.STANDARD,
            archetype=Archetype.MIDRANGE,
            confidence=0.5,
        )

        result = format_full_assumptions_section(original, resolved)

        assert result is not None
        assert "Format: Standard" in result
        assert "Archetype: Midrange" in result

    def test_partial_intent_shows_only_defaulted(self) -> None:
        """When user specifies some fields, only shows defaulted ones."""
        original = DeckIntent(
            format=Format.HISTORIC,  # User specified this
            confidence=0.4,
        )
        resolved = DeckIntent(
            format=Format.HISTORIC,
            archetype=Archetype.MIDRANGE,  # This was defaulted
            confidence=0.6,
        )

        result = format_full_assumptions_section(original, resolved)

        assert result is not None
        assert "Format:" not in result  # Not defaulted
        assert "Archetype: Midrange" in result  # Defaulted


# =============================================================================
# BUILD DECK ASSUMPTIONS (TOOL-LEVEL)
# =============================================================================


class TestBuildDeckDefaults:
    """Tests for BuildDeckDefaults dataclass."""

    def test_no_defaults(self) -> None:
        """When nothing defaulted, any_applied is False."""
        defaults = BuildDeckDefaults()
        assert not defaults.any_applied

    def test_format_defaulted(self) -> None:
        """When format defaulted, any_applied is True."""
        defaults = BuildDeckDefaults(format_defaulted=True)
        assert defaults.any_applied

    def test_colors_defaulted(self) -> None:
        """When colors defaulted, any_applied is True."""
        defaults = BuildDeckDefaults(colors_defaulted=True)
        assert defaults.any_applied


class TestFormatBuildDeckAssumptions:
    """Tests for format_build_deck_assumptions function."""

    def test_no_defaults_returns_none(self) -> None:
        """When no defaults, returns None."""
        defaults = BuildDeckDefaults()

        result = format_build_deck_assumptions("historic", ["R", "G"], defaults)

        assert result is None

    def test_format_defaulted(self) -> None:
        """When format defaulted, shows format assumption."""
        defaults = BuildDeckDefaults(format_defaulted=True)

        result = format_build_deck_assumptions("standard", None, defaults)

        assert result is not None
        assert "Format: Standard" in result
        assert ADJUSTMENT_AFFORDANCE in result

    def test_colors_defaulted_none(self) -> None:
        """When colors defaulted to None, shows based on theme."""
        defaults = BuildDeckDefaults(colors_defaulted=True)

        result = format_build_deck_assumptions("standard", None, defaults)

        assert result is not None
        assert "Colors: Based on theme cards" in result

    def test_colors_defaulted_with_values(self) -> None:
        """When colors defaulted but resolved, shows the colors."""
        defaults = BuildDeckDefaults(colors_defaulted=True)

        result = format_build_deck_assumptions("standard", ["R", "G"], defaults)

        assert result is not None
        assert "Colors:" in result
        # Should contain the actual colors
        assert "Green" in result or "Red" in result

    def test_both_defaulted(self) -> None:
        """When both format and colors defaulted, shows both."""
        defaults = BuildDeckDefaults(format_defaulted=True, colors_defaulted=True)

        result = format_build_deck_assumptions("standard", None, defaults)

        assert result is not None
        assert "Format: Standard" in result
        assert "Colors: Based on theme cards" in result
        assert ADJUSTMENT_AFFORDANCE in result


# =============================================================================
# SNAPSHOT TESTS - EXPECTED OUTPUT FORMAT
# =============================================================================


class TestAssumptionsSnapshot:
    """Snapshot tests for exact output format."""

    def test_single_default_snapshot(self) -> None:
        """Verify exact format for single defaulted field."""
        defaults = BuildDeckDefaults(format_defaulted=True)

        result = format_build_deck_assumptions("standard", None, defaults)

        expected = (
            "Assumptions I made:\n"
            "- Format: Standard\n"
            "\n"
            "If you want something different (format, colors, or style), "
            "just say so and I'll adjust."
        )
        assert result == expected

    def test_two_defaults_snapshot(self) -> None:
        """Verify exact format for two defaulted fields."""
        defaults = BuildDeckDefaults(format_defaulted=True, colors_defaulted=True)

        result = format_build_deck_assumptions("standard", None, defaults)

        expected = (
            "Assumptions I made:\n"
            "- Format: Standard\n"
            "- Colors: Based on theme cards\n"
            "\n"
            "If you want something different (format, colors, or style), "
            "just say so and I'll adjust."
        )
        assert result == expected

    def test_no_assumptions_snapshot(self) -> None:
        """Verify None when nothing defaulted."""
        defaults = BuildDeckDefaults()

        result = format_build_deck_assumptions("historic", ["R"], defaults)

        assert result is None


# =============================================================================
# REGRESSION TESTS - DECK CONTENT UNCHANGED
# =============================================================================


class TestDeckContentUnchanged:
    """
    Regression tests to ensure assumptions don't affect deck content.

    These tests verify that the assumptions section is additive only
    and doesn't modify the actual deck building output.
    """

    def test_assumptions_are_metadata_only(self) -> None:
        """Assumptions are returned separately, not mixed with deck data."""
        defaults = BuildDeckDefaults(format_defaulted=True, colors_defaulted=True)

        result = format_build_deck_assumptions("standard", None, defaults)

        # Result is a string, not part of deck structure
        assert isinstance(result, str)
        # Should not contain deck data keywords (card counts, land names, etc.)
        assert "4x" not in result  # Card count format
        assert "lands" not in result.lower()
        assert "mana" not in result.lower()
        assert "mountain" not in result.lower()
        assert "forest" not in result.lower()

    def test_none_result_is_falsy(self) -> None:
        """When no defaults, result is None (not empty string)."""
        defaults = BuildDeckDefaults()

        result = format_build_deck_assumptions("standard", ["R"], defaults)

        assert result is None
        assert not result  # Falsy check
