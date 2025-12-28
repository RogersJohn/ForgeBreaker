"""
Explanation models for transparent outcomes.

Explanations describe consequences tied to player beliefs, not prescriptions.
They help players understand what happened and why, not what to do next.

ForgeBreaker explains, it does not advise.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class OutcomeExplanation:
    """
    Explanation for a single outcome or metric.

    Explanations are conditional interpretations tied to player beliefs.
    They describe what something means given certain assumptions,
    not what the player should do about it.

    Attributes:
        summary: What this metric represents given current assumptions
        assumptions_involved: Which beliefs this interpretation depends on
        conditional: What would change this interpretation
    """

    summary: str
    assumptions_involved: list[str] = field(default_factory=list)
    conditional: str = ""  # Renamed from 'uncertainty' - what changes the interpretation

    def full_text(self) -> str:
        """Generate full explanation text."""
        parts = [self.summary]
        if self.assumptions_involved:
            parts.append(f"This interpretation depends on: {', '.join(self.assumptions_involved)}.")
        if self.conditional:
            parts.append(self.conditional)
        return " ".join(parts)


@dataclass
class ExplainedResult:
    """
    A result with an attached explanation.

    The explanation makes the reasoning transparent without
    implying that the result is authoritative or prescriptive.
    """

    value: float | int | str | list[Any] | dict[str, Any]
    explanation: OutcomeExplanation
    label: str = ""  # Human-readable label for the value

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            "value": self.value,
            "label": self.label,
            "explanation": {
                "summary": self.explanation.summary,
                "assumptions_involved": self.explanation.assumptions_involved,
                "conditional": self.explanation.conditional,
                "full_text": self.explanation.full_text(),
            },
        }


# Conditional phrases for consistent language
# These describe what would change an interpretation, not what will happen
CONDITIONAL_PHRASES = {
    "key_cards": "If key cards perform differently than expected, this interpretation changes.",
    "mana_curve": "If land drops differ from the typical pattern, this shifts.",
    "draw_consistency": "With different card selection density, this would vary.",
    "interaction": "If opponent interaction differs from typical, this changes.",
    "meta_dependent": "Under different meta compositions, this interpretation shifts.",
    "sample_size": "With more data, this interpretation may change.",
    "assumption_based": "This interpretation is based on current assumptions about the deck.",
}


def create_completion_explanation(
    completion_pct: float,
    missing_cards: int,
    has_key_cards: bool,
) -> OutcomeExplanation:
    """Create explanation for deck completion percentage."""
    if completion_pct >= 100:
        summary = "All cards for this deck are present in your collection."
        conditional = ""
    elif completion_pct >= 75:
        summary = (
            f"Your collection contains most cards for this deck. "
            f"{missing_cards} cards are not present."
        )
        conditional = "If you acquire cards through other means, this count changes."
    else:
        summary = f"Your collection is missing {missing_cards} cards for this deck."
        conditional = (
            "This count reflects exact matches. Functional alternatives are not considered."
        )

    assumptions = []
    if has_key_cards:
        assumptions.append("Key Card Dependency")

    return OutcomeExplanation(
        summary=summary,
        assumptions_involved=assumptions,
        conditional=conditional,
    )


def create_recommendation_explanation(
    score: float,
    completion_pct: float,
    archetype: str,
    fragility: float | None = None,
) -> OutcomeExplanation:
    """Create explanation for a deck recommendation score."""
    # Describe what the score represents, not what the player should do
    if score > 0.8:
        summary = (
            f"This {archetype} deck scores highly given your collection. "
            f"You have {completion_pct:.0f}% of the cards."
        )
    elif score > 0.5:
        summary = (
            f"This {archetype} deck has a moderate score. "
            f"You have {completion_pct:.0f}% of the cards."
        )
    else:
        summary = (
            f"This {archetype} deck scores lower given your collection. "
            f"Currently at {completion_pct:.0f}%."
        )

    assumptions = ["Mana Curve", "Key Card Dependency"]
    conditional_parts = [CONDITIONAL_PHRASES["assumption_based"]]

    if fragility is not None and fragility > 0.5:
        conditional_parts.append(
            "Given high deviation from convention, this interpretation may shift under stress."
        )
        assumptions.append("Overall Fragility")

    return OutcomeExplanation(
        summary=summary,
        assumptions_involved=assumptions,
        conditional=" ".join(conditional_parts),
    )


def create_fragility_explanation(
    fragility: float,
    warnings: int,
    criticals: int,
    archetype: str,
) -> OutcomeExplanation:
    """Create explanation for fragility score."""
    # Describe what fragility represents, not what to do about it
    if fragility < 0.2:
        summary = (
            f"This {archetype} deck's characteristics are within typical ranges for its archetype."
        )
    elif fragility < 0.5:
        summary = (
            f"This {archetype} deck has {warnings} characteristic(s) that differ "
            "from typical patterns for its archetype."
        )
    else:
        summary = (
            f"This {archetype} deck has {criticals} significant difference(s) "
            f"and {warnings} other difference(s) from typical patterns."
        )

    return OutcomeExplanation(
        summary=summary,
        assumptions_involved=["Overall Fragility", "Key Card Dependency"],
        conditional=CONDITIONAL_PHRASES["key_cards"],
    )
