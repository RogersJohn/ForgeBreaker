"""
Stress testing models.

Stress testing is a way to explore hypothetical scenarios, not to predict outcomes.
A breaking point occurs when a player belief can no longer be reasonably held—
not when a numeric threshold is crossed.

These tools help players ask "what if?" questions about their decks.
They do not tell players what will happen.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class StressType(str, Enum):
    """Types of stress that can be applied to deck assumptions."""

    UNDERPERFORM = "underperform"  # Key cards appear less frequently
    MISSING = "missing"  # Remove copies of cards
    DELAYED = "delayed"  # Shift mana curve up (slower draws)
    HOSTILE_META = "hostile_meta"  # Opponent has more interaction


@dataclass
class StressScenario:
    """
    A hypothetical scenario to explore with a deck.

    This represents a "what if" question the player wants to examine.
    It is not a prediction of what will happen in games.

    Attributes:
        stress_type: The type of stress to explore
        target: What to stress (card name, assumption name, or "all")
        intensity: How severe the hypothetical (0.0 to 1.0)
        description: Human-readable description of the scenario
    """

    stress_type: StressType
    target: str
    intensity: float = 0.5  # 0.0 = minimal, 1.0 = maximum stress
    description: str = ""

    def __post_init__(self) -> None:
        """Validate intensity is in range."""
        self.intensity = max(0.0, min(1.0, self.intensity))


@dataclass
class StressedAssumption:
    """
    How a player belief changes under a hypothetical scenario.

    Attributes:
        name: Name of the belief being examined
        original_value: Observed value before stress
        stressed_value: What the value would be under this scenario
        original_health: Health status before stress
        stressed_health: Health status under this scenario
        change_explanation: Why the belief changes under stress
        belief_violated: Whether this stress invalidates the belief entirely
        violation_reason: If violated, why the belief can no longer hold
    """

    name: str
    original_value: Any
    stressed_value: Any
    original_health: str
    stressed_health: str
    change_explanation: str
    belief_violated: bool = False
    violation_reason: str = ""


@dataclass
class StressResult:
    """
    Result of exploring a stress scenario with a deck.

    A breaking point is NOT a numeric threshold. It occurs when a specific
    player belief can no longer be reasonably held under the scenario.

    Attributes:
        deck_name: Name of the deck being explored
        scenario: The hypothetical scenario that was explored
        original_fragility: Deviation from convention before stress
        stressed_fragility: Deviation from convention under stress
        affected_assumptions: List of beliefs that change under stress
        assumption_violated: Whether any belief is invalidated (true breaking point)
        violated_belief: Name of the specific belief that fails (if any)
        violation_explanation: Why this belief fails under this scenario
        exploration_summary: What this scenario reveals about the deck
        considerations: Things to think about based on this exploration
    """

    deck_name: str
    scenario: StressScenario
    original_fragility: float
    stressed_fragility: float
    affected_assumptions: list[StressedAssumption] = field(default_factory=list)
    assumption_violated: bool = False
    violated_belief: str = ""
    violation_explanation: str = ""
    exploration_summary: str = ""
    considerations: list[str] = field(default_factory=list)

    # Keep for backwards compatibility but deprecated
    @property
    def breaking_point(self) -> bool:
        """Deprecated: Use assumption_violated instead."""
        return self.assumption_violated

    @property
    def explanation(self) -> str:
        """Deprecated: Use exploration_summary instead."""
        return self.exploration_summary

    @property
    def recommendations(self) -> list[str]:
        """Deprecated: Use considerations instead."""
        return self.considerations

    def fragility_change(self) -> float:
        """Calculate the change in fragility."""
        return self.stressed_fragility - self.original_fragility

    def has_significant_change(self) -> bool:
        """Check if the stress reveals meaningful information."""
        return self.assumption_violated or any(a.belief_violated for a in self.affected_assumptions)


@dataclass
class BreakingPointAnalysis:
    """
    Analysis of which belief fails first under stress.

    This identifies the assumption most vulnerable to invalidation—
    not a prediction of deck failure, but insight into which beliefs
    are most sensitive to change.

    Attributes:
        deck_name: Name of the deck
        most_vulnerable_belief: The belief most easily invalidated
        stress_threshold: The intensity at which the belief fails
        failing_scenario: The scenario that invalidates the belief
        exploration_insight: What this analysis reveals
    """

    deck_name: str
    most_vulnerable_belief: str
    stress_threshold: float
    failing_scenario: StressScenario | None
    exploration_insight: str

    # Deprecated properties for backwards compatibility
    @property
    def weakest_assumption(self) -> str:
        """Deprecated: Use most_vulnerable_belief instead."""
        return self.most_vulnerable_belief

    @property
    def breaking_intensity(self) -> float:
        """Deprecated: Use stress_threshold instead."""
        return self.stress_threshold

    @property
    def breaking_scenario(self) -> StressScenario | None:
        """Deprecated: Use failing_scenario instead."""
        return self.failing_scenario

    @property
    def resilience_score(self) -> float:
        """Deprecated: Resilience scoring removed. Returns threshold for compat."""
        return self.stress_threshold

    @property
    def explanation(self) -> str:
        """Deprecated: Use exploration_insight instead."""
        return self.exploration_insight
