"""
Explanation models for transparent outcomes.

Every result in ForgeBreaker should be accompanied by an explanation
that references the assumptions involved and includes uncertainty language.
"""

from dataclasses import dataclass, field


@dataclass
class OutcomeExplanation:
    """
    Explanation for a single outcome or metric.

    Attributes:
        summary: Brief explanation of what the metric means
        assumptions_involved: List of assumption names this metric relies on
        uncertainty: Statement about what could change this outcome
        confidence: How confident we are in this explanation (low/medium/high)
    """

    summary: str
    assumptions_involved: list[str] = field(default_factory=list)
    uncertainty: str = ""
    confidence: str = "medium"

    def full_text(self) -> str:
        """Generate full explanation text."""
        parts = [self.summary]
        if self.assumptions_involved:
            parts.append(
                f"This depends on: {', '.join(self.assumptions_involved)}."
            )
        if self.uncertainty:
            parts.append(self.uncertainty)
        return " ".join(parts)


@dataclass
class ExplainedResult:
    """
    A result with an attached explanation.

    Wraps any result value with an explanation that makes
    the reasoning transparent.
    """

    value: float | int | str | list | dict
    explanation: OutcomeExplanation
    label: str = ""  # Human-readable label for the value

    def to_dict(self) -> dict:
        """Convert to dictionary for API responses."""
        return {
            "value": self.value,
            "label": self.label,
            "explanation": {
                "summary": self.explanation.summary,
                "assumptions_involved": self.explanation.assumptions_involved,
                "uncertainty": self.explanation.uncertainty,
                "confidence": self.explanation.confidence,
                "full_text": self.explanation.full_text(),
            },
        }


# Standard uncertainty phrases for consistent language
UNCERTAINTY_PHRASES = {
    "key_cards": "Results may vary if key cards underperform or are answered.",
    "mana_curve": "Outcomes depend on hitting land drops on curve.",
    "draw_consistency": "May differ with more or less card selection.",
    "interaction": "Results assume typical interaction from opponents.",
    "meta_dependent": "Performance varies based on current meta composition.",
    "sample_size": "Based on limited data; actual results may differ.",
    "assumption_based": "Based on current assumptions about the deck.",
}


def create_completion_explanation(
    completion_pct: float,
    missing_cards: int,
    has_key_cards: bool,
) -> OutcomeExplanation:
    """Create explanation for deck completion percentage."""
    if completion_pct >= 100:
        summary = "You have all cards needed to build this deck."
        uncertainty = ""
    elif completion_pct >= 75:
        summary = f"You're close to completing this deck, missing {missing_cards} cards."
        uncertainty = (
            "Wildcards needed may change if you acquire missing cards through packs."
        )
    else:
        summary = f"You need {missing_cards} more cards to complete this deck."
        uncertainty = (
            "Consider checking if you have functional replacements "
            "for some missing cards."
        )

    assumptions = []
    if has_key_cards:
        assumptions.append("Key Card Dependency")

    return OutcomeExplanation(
        summary=summary,
        assumptions_involved=assumptions,
        uncertainty=uncertainty,
        confidence="high" if completion_pct >= 75 else "medium",
    )


def create_recommendation_explanation(
    score: float,
    completion_pct: float,
    archetype: str,
    fragility: float | None = None,
) -> OutcomeExplanation:
    """Create explanation for a deck recommendation score."""
    if score > 0.8:
        summary = (
            f"Highly recommended {archetype} deck. "
            f"You have {completion_pct:.0f}% of the cards needed."
        )
    elif score > 0.5:
        summary = (
            f"Good option for {archetype}. "
            f"You have {completion_pct:.0f}% of the cards."
        )
    else:
        summary = (
            f"This {archetype} deck requires more cards to complete. "
            f"Currently at {completion_pct:.0f}%."
        )

    assumptions = ["Mana Curve", "Key Card Dependency"]
    uncertainty_parts = [UNCERTAINTY_PHRASES["assumption_based"]]

    if fragility is not None and fragility > 0.5:
        uncertainty_parts.append(
            "This deck has higher fragility - test with stress scenarios."
        )
        assumptions.append("Overall Fragility")

    return OutcomeExplanation(
        summary=summary,
        assumptions_involved=assumptions,
        uncertainty=" ".join(uncertainty_parts),
        confidence="medium",
    )


def create_fragility_explanation(
    fragility: float,
    warnings: int,
    criticals: int,
    archetype: str,
) -> OutcomeExplanation:
    """Create explanation for fragility score."""
    if fragility < 0.2:
        summary = (
            f"This {archetype} deck is stable with assumptions in healthy ranges."
        )
        confidence = "high"
    elif fragility < 0.5:
        summary = (
            f"This {archetype} deck has {warnings} warning(s) that may affect "
            "consistency under certain conditions."
        )
        confidence = "medium"
    else:
        summary = (
            f"This {archetype} deck has {criticals} critical issue(s) "
            f"and {warnings} warning(s). Consider stress testing."
        )
        confidence = "low"

    return OutcomeExplanation(
        summary=summary,
        assumptions_involved=["Overall Fragility", "Key Card Dependency"],
        uncertainty=UNCERTAINTY_PHRASES["key_cards"],
        confidence=confidence,
    )
