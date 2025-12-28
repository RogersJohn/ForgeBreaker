"""
Deck assumption models.

Represents the implicit assumptions a deck relies on for success.
These assumptions become visible and inspectable to help players
understand deck fragility.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class AssumptionCategory(str, Enum):
    """Categories of deck assumptions."""

    MANA_CURVE = "mana_curve"
    DRAW_CONSISTENCY = "draw_consistency"
    KEY_CARDS = "key_cards"
    INTERACTION_TIMING = "interaction_timing"


class AssumptionHealth(str, Enum):
    """Health status of an assumption."""

    HEALTHY = "healthy"  # Within expected range
    WARNING = "warning"  # Slightly outside expectations
    CRITICAL = "critical"  # Significantly outside expectations


@dataclass
class DeckAssumption:
    """
    A single assumption a deck relies on.

    Attributes:
        name: Human-readable name (e.g., "Mana Curve Expectation")
        category: Type of assumption
        description: Explanation of what this assumption means
        current_value: The actual computed value for this deck
        expected_range: Tuple of (min, max) for healthy values
        health: Whether this assumption is in a healthy state
        explanation: Why this matters for the deck
        adjustable: Whether the user can modify this in stress testing
    """

    name: str
    category: AssumptionCategory
    description: str
    current_value: Any
    expected_range: tuple[float, float]
    health: AssumptionHealth
    explanation: str
    adjustable: bool = True

    def is_within_range(self) -> bool:
        """Check if current value is within expected range."""
        if isinstance(self.current_value, int | float):
            return self.expected_range[0] <= self.current_value <= self.expected_range[1]
        return True


@dataclass
class DeckAssumptionSet:
    """
    Complete set of assumptions for a deck.

    Attributes:
        deck_name: Name of the deck being analyzed
        archetype: Detected archetype (aggro, midrange, control, combo)
        assumptions: List of individual assumptions
        overall_fragility: 0-1 score indicating how assumption-dependent the deck is
        fragility_explanation: Why the deck has this fragility level
    """

    deck_name: str
    archetype: str
    assumptions: list[DeckAssumption] = field(default_factory=list)
    overall_fragility: float = 0.0
    fragility_explanation: str = ""

    def get_by_category(self, category: AssumptionCategory) -> list[DeckAssumption]:
        """Get all assumptions in a category."""
        return [a for a in self.assumptions if a.category == category]

    def get_warnings(self) -> list[DeckAssumption]:
        """Get assumptions that are in warning or critical state."""
        return [
            a
            for a in self.assumptions
            if a.health in (AssumptionHealth.WARNING, AssumptionHealth.CRITICAL)
        ]

    def get_critical(self) -> list[DeckAssumption]:
        """Get assumptions in critical state."""
        return [a for a in self.assumptions if a.health == AssumptionHealth.CRITICAL]

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            "deck_name": self.deck_name,
            "archetype": self.archetype,
            "assumptions": [
                {
                    "name": a.name,
                    "category": a.category.value,
                    "description": a.description,
                    "current_value": a.current_value,
                    "expected_range": list(a.expected_range),
                    "health": a.health.value,
                    "explanation": a.explanation,
                    "adjustable": a.adjustable,
                }
                for a in self.assumptions
            ],
            "overall_fragility": self.overall_fragility,
            "fragility_explanation": self.fragility_explanation,
        }
