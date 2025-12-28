"""
Stress testing models.

Represents scenarios that stress deck assumptions to reveal fragility.
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
    A specific stress scenario to apply to a deck.

    Attributes:
        stress_type: The type of stress to apply
        target: What to stress (card name, assumption name, or "all")
        intensity: How severe the stress (0.0 to 1.0)
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
    An assumption after stress has been applied.

    Attributes:
        name: Name of the assumption
        original_value: Value before stress
        stressed_value: Value after stress
        original_health: Health status before stress
        stressed_health: Health status after stress
        change_explanation: Why the value changed
    """

    name: str
    original_value: Any
    stressed_value: Any
    original_health: str
    stressed_health: str
    change_explanation: str


@dataclass
class StressResult:
    """
    Result of applying stress to a deck.

    Attributes:
        deck_name: Name of the deck being stressed
        scenario: The stress scenario that was applied
        original_fragility: Fragility score before stress
        stressed_fragility: Fragility score after stress
        affected_assumptions: List of assumptions that changed
        breaking_point: Whether this stress level breaks the deck
        explanation: Overall explanation of the stress impact
        recommendations: Suggestions for improving resilience
    """

    deck_name: str
    scenario: StressScenario
    original_fragility: float
    stressed_fragility: float
    affected_assumptions: list[StressedAssumption] = field(default_factory=list)
    breaking_point: bool = False
    explanation: str = ""
    recommendations: list[str] = field(default_factory=list)

    def fragility_change(self) -> float:
        """Calculate the change in fragility."""
        return self.stressed_fragility - self.original_fragility

    def is_significant(self) -> bool:
        """Check if the stress had a significant impact."""
        return abs(self.fragility_change()) > 0.1 or self.breaking_point


@dataclass
class BreakingPointAnalysis:
    """
    Analysis of what breaks first in a deck.

    Attributes:
        deck_name: Name of the deck
        weakest_assumption: The assumption most vulnerable to stress
        breaking_intensity: The intensity at which the deck breaks
        breaking_scenario: The scenario that causes the break
        resilience_score: How resilient the deck is (0-1, higher is better)
        explanation: Overall analysis
    """

    deck_name: str
    weakest_assumption: str
    breaking_intensity: float
    breaking_scenario: StressScenario | None
    resilience_score: float
    explanation: str
