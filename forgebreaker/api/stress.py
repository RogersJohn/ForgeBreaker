"""
Stress testing API endpoint.

Explore hypothetical scenarios with decks to examine which beliefs
might not hold under certain conditions.

This is exploration, not prediction.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from forgebreaker.analysis.stress import apply_stress, find_breaking_point
from forgebreaker.db import get_meta_deck, meta_deck_to_model
from forgebreaker.db.database import get_session
from forgebreaker.models.stress import StressScenario, StressType
from forgebreaker.services.card_database import get_card_database

router = APIRouter(prefix="/stress", tags=["stress"])


class StressScenarioRequest(BaseModel):
    """Request to explore a stress scenario."""

    stress_type: str = Field(
        description="Type of stress: underperform, missing, delayed, hostile_meta"
    )
    target: str = Field(description="What to stress (card name or assumption category)")
    intensity: float = Field(
        default=0.5, ge=0.0, le=1.0, description="Stress intensity from 0.0 to 1.0"
    )


class StressedAssumptionResponse(BaseModel):
    """How a belief changes under stress."""

    name: str
    original_value: Any
    stressed_value: Any
    original_health: str
    stressed_health: str
    change_explanation: str
    belief_violated: bool = False
    violation_reason: str = ""


class StressResultResponse(BaseModel):
    """
    Result of exploring a stress scenario with a deck.

    A breaking point occurs when a specific belief can no longer be held,
    NOT when a numeric threshold is crossed.
    """

    deck_name: str
    stress_type: str
    target: str
    intensity: float
    original_fragility: float
    stressed_fragility: float
    fragility_change: float
    affected_assumptions: list[StressedAssumptionResponse]
    # New semantic fields
    assumption_violated: bool
    violated_belief: str
    violation_explanation: str
    exploration_summary: str
    considerations: list[str]
    # Backwards compatibility
    breaking_point: bool  # Deprecated: use assumption_violated
    explanation: str  # Deprecated: use exploration_summary
    recommendations: list[str]  # Deprecated: use considerations


class BreakingPointResponse(BaseModel):
    """
    Analysis of which belief fails first under stress.

    This identifies the most vulnerable assumption, not a prediction of failure.
    """

    deck_name: str
    # New semantic fields
    most_vulnerable_belief: str
    stress_threshold: float
    failing_scenario: StressScenarioRequest | None
    exploration_insight: str
    # Backwards compatibility
    weakest_assumption: str  # Deprecated: use most_vulnerable_belief
    breaking_intensity: float  # Deprecated: use stress_threshold
    resilience_score: float  # Deprecated: removed concept
    breaking_scenario: StressScenarioRequest | None  # Deprecated: use failing_scenario
    explanation: str  # Deprecated: use exploration_insight


@router.post("/{user_id}/{format_name}/{deck_name}", response_model=StressResultResponse)
async def stress_deck(
    user_id: str,  # noqa: ARG001  Required for route pattern
    format_name: str,
    deck_name: str,
    scenario: StressScenarioRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> StressResultResponse:
    """
    Explore what happens to deck beliefs under a hypothetical scenario.

    This does NOT predict how the deck will perform. It helps players
    examine which of their beliefs might not hold under certain conditions.

    Stress types:
    - underperform: What if key cards are drawn less frequently?
    - missing: What if a specific card is unavailable?
    - delayed: What if mana development is problematic?
    - hostile_meta: What if opponents have more answers?

    Returns insight into how beliefs change under stress.
    """
    # Get the deck
    db_deck = await get_meta_deck(session, deck_name, format_name)
    if db_deck is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Deck '{deck_name}' not found in format '{format_name}'",
        )

    deck = meta_deck_to_model(db_deck)

    # Load card database
    try:
        card_db = get_card_database()
    except FileNotFoundError:
        card_db = {}

    # Parse stress type
    try:
        stress_type = StressType(scenario.stress_type)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Invalid stress type '{scenario.stress_type}'. "
                f"Valid types: {', '.join(t.value for t in StressType)}"
            ),
        ) from None

    # Create and apply scenario
    stress_scenario = StressScenario(
        stress_type=stress_type,
        target=scenario.target,
        intensity=scenario.intensity,
        description=f"What if {stress_type.value} affects {scenario.target}?",
    )

    result = apply_stress(deck, card_db, stress_scenario)

    return StressResultResponse(
        deck_name=result.deck_name,
        stress_type=result.scenario.stress_type.value,
        target=result.scenario.target,
        intensity=result.scenario.intensity,
        original_fragility=result.original_fragility,
        stressed_fragility=result.stressed_fragility,
        fragility_change=result.fragility_change(),
        affected_assumptions=[
            StressedAssumptionResponse(
                name=a.name,
                original_value=a.original_value,
                stressed_value=a.stressed_value,
                original_health=a.original_health,
                stressed_health=a.stressed_health,
                change_explanation=a.change_explanation,
                belief_violated=a.belief_violated,
                violation_reason=a.violation_reason,
            )
            for a in result.affected_assumptions
        ],
        # New semantic fields
        assumption_violated=result.assumption_violated,
        violated_belief=result.violated_belief,
        violation_explanation=result.violation_explanation,
        exploration_summary=result.exploration_summary,
        considerations=result.considerations,
        # Backwards compatibility
        breaking_point=result.assumption_violated,
        explanation=result.exploration_summary,
        recommendations=result.considerations,
    )


@router.get(
    "/breaking-point/{user_id}/{format_name}/{deck_name}", response_model=BreakingPointResponse
)
async def get_breaking_point(
    user_id: str,  # noqa: ARG001  Required for route pattern
    format_name: str,
    deck_name: str,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> BreakingPointResponse:
    """
    Identify which belief fails first under increasing stress.

    This explores which assumption is most sensitive to change—
    not a prediction of failure, but insight into deck dependencies.
    """
    # Get the deck
    db_deck = await get_meta_deck(session, deck_name, format_name)
    if db_deck is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Deck '{deck_name}' not found in format '{format_name}'",
        )

    deck = meta_deck_to_model(db_deck)

    # Load card database
    try:
        card_db = get_card_database()
    except FileNotFoundError:
        card_db = {}

    analysis = find_breaking_point(deck, card_db)

    failing_scenario = None
    if analysis.failing_scenario:
        failing_scenario = StressScenarioRequest(
            stress_type=analysis.failing_scenario.stress_type.value,
            target=analysis.failing_scenario.target,
            intensity=analysis.failing_scenario.intensity,
        )

    return BreakingPointResponse(
        deck_name=analysis.deck_name,
        # New semantic fields
        most_vulnerable_belief=analysis.most_vulnerable_belief,
        stress_threshold=analysis.stress_threshold,
        failing_scenario=failing_scenario,
        exploration_insight=analysis.exploration_insight,
        # Backwards compatibility
        weakest_assumption=analysis.most_vulnerable_belief,
        breaking_intensity=analysis.stress_threshold,
        resilience_score=analysis.stress_threshold,  # Deprecated concept
        breaking_scenario=failing_scenario,
        explanation=analysis.exploration_insight,
    )
