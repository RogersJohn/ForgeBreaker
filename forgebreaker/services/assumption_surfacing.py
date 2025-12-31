"""
Assumption Surfacing — UX Transparency for Applied Defaults.

This module provides formatting functions to surface assumptions made
during deck building. It uses already-inferred intent and applied defaults
to generate user-facing text.

CONSTRAINTS:
- Output-only changes — no new inference
- Zero additional LLM calls — pure formatting
- Uses DeckIntent + applied defaults already computed
- Deterministic behavior
"""

from dataclasses import dataclass

from forgebreaker.models.intent import DeckIntent

# Color code to name mapping
COLOR_NAMES: dict[str, str] = {
    "W": "White",
    "U": "Blue",
    "B": "Black",
    "R": "Red",
    "G": "Green",
}

# Standard adjustment affordance — calm, non-questioning
ADJUSTMENT_AFFORDANCE = (
    "If you want something different (format, colors, or style), just say so and I'll adjust."
)


@dataclass(frozen=True)
class AppliedDefaults:
    """
    Tracks which fields were defaulted during intent processing.

    Only fields that were None in the original intent and received
    defaults are marked as True here.
    """

    format_defaulted: bool = False
    archetype_defaulted: bool = False
    colors_defaulted: bool = False

    @property
    def any_applied(self) -> bool:
        """Check if any defaults were applied."""
        return self.format_defaulted or self.archetype_defaulted or self.colors_defaulted


def track_applied_defaults(
    original_intent: DeckIntent,
    resolved_intent: DeckIntent,
) -> AppliedDefaults:
    """
    Determine which defaults were applied by comparing original and resolved intents.

    Args:
        original_intent: The intent before defaults were applied
        resolved_intent: The intent after defaults were applied

    Returns:
        AppliedDefaults indicating which fields were defaulted
    """
    return AppliedDefaults(
        format_defaulted=(original_intent.format is None and resolved_intent.format is not None),
        archetype_defaulted=(
            original_intent.archetype is None and resolved_intent.archetype is not None
        ),
        colors_defaulted=(original_intent.colors is None and resolved_intent.colors is not None),
    )


def _format_colors(colors: frozenset[str] | list[str] | None) -> str:
    """Format color set as human-readable string."""
    if colors is None or len(colors) == 0:
        return "Based on theme cards"

    color_list = sorted(colors)
    names = [COLOR_NAMES.get(c, c) for c in color_list]

    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]}/{names[1]}"
    return "/".join(names)


def format_assumptions_section(
    resolved_intent: DeckIntent,
    applied_defaults: AppliedDefaults,
) -> str | None:
    """
    Format the assumptions section for a deck building response.

    Only generates output if defaults were applied. If the user explicitly
    specified all values, returns None (no assumptions to show).

    Args:
        resolved_intent: The intent after defaults were applied
        applied_defaults: Which fields were defaulted

    Returns:
        Formatted assumptions section, or None if no defaults were applied
    """
    if not applied_defaults.any_applied:
        return None

    lines: list[str] = ["Assumptions I made:"]

    if applied_defaults.format_defaulted and resolved_intent.format is not None:
        format_name = resolved_intent.format.value.title()
        lines.append(f"- Format: {format_name}")

    if applied_defaults.archetype_defaulted and resolved_intent.archetype is not None:
        archetype_name = resolved_intent.archetype.value.title()
        lines.append(f"- Archetype: {archetype_name}")

    if applied_defaults.colors_defaulted:
        color_str = _format_colors(resolved_intent.colors)
        lines.append(f"- Colors: {color_str}")

    # Add adjustment affordance
    lines.append("")
    lines.append(ADJUSTMENT_AFFORDANCE)

    return "\n".join(lines)


def format_full_assumptions_section(
    original_intent: DeckIntent,
    resolved_intent: DeckIntent,
) -> str | None:
    """
    Convenience function that tracks defaults and formats in one call.

    Args:
        original_intent: The intent before defaults were applied
        resolved_intent: The intent after defaults were applied

    Returns:
        Formatted assumptions section, or None if no defaults were applied
    """
    applied_defaults = track_applied_defaults(original_intent, resolved_intent)
    return format_assumptions_section(resolved_intent, applied_defaults)


# =============================================================================
# TOOL-LEVEL ASSUMPTION FORMATTING
# =============================================================================


@dataclass(frozen=True)
class BuildDeckDefaults:
    """
    Tracks which parameters were defaulted in build_deck_tool.

    This is used when we don't have a full DeckIntent flow,
    but need to track defaults for transparency.
    """

    format_defaulted: bool = False
    colors_defaulted: bool = False

    @property
    def any_applied(self) -> bool:
        """Check if any defaults were applied."""
        return self.format_defaulted or self.colors_defaulted


def format_build_deck_assumptions(
    format_name: str,
    colors: list[str] | None,
    defaults: BuildDeckDefaults,
) -> str | None:
    """
    Format assumptions section for build_deck tool response.

    Args:
        format_name: The resolved format name
        colors: The resolved colors (or None if derived from theme)
        defaults: Which parameters were defaulted

    Returns:
        Formatted assumptions section, or None if no defaults were applied
    """
    if not defaults.any_applied:
        return None

    lines: list[str] = ["Assumptions I made:"]

    if defaults.format_defaulted:
        lines.append(f"- Format: {format_name.title()}")

    if defaults.colors_defaulted:
        color_str = _format_colors(colors)
        lines.append(f"- Colors: {color_str}")

    # Add adjustment affordance
    lines.append("")
    lines.append(ADJUSTMENT_AFFORDANCE)

    return "\n".join(lines)
