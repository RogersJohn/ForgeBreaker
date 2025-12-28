"""
Stress testing API endpoint.

Apply stress scenarios to decks and analyze breaking points.
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
    """Request to apply a stress scenario."""

    stress_type: str = Field(
        description="Type of stress: underperform, missing, delayed, hostile_meta"
    )
    target: str = Field(
        description="What to stress (card name or assumption category)"
    )
    intensity: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Stress intensity from 0.0 to 1.0"
    )


class StressedAssumptionResponse(BaseModel):
    """A single assumption after stress."""

    name: str
    original_value: Any
    stressed_value: Any
    original_health: str
    stressed_health: str
    change_explanation: str


class StressResultResponse(BaseModel):
    """Result of applying stress to a deck."""

    deck_name: str
    stress_type: str
    target: str
    intensity: float
    original_fragility: float
    stressed_fragility: float
    fragility_change: float
    affected_assumptions: list[StressedAssumptionResponse]
    breaking_point: bool
    explanation: str
    recommendations: list[str]


class BreakingPointResponse(BaseModel):
    """Analysis of deck breaking points."""

    deck_name: str
    weakest_assumption: str
    breaking_intensity: float
    resilience_score: float
    breaking_scenario: StressScenarioRequest | None
    explanation: str


@router.post("/{user_id}/{format_name}/{deck_name}", response_model=StressResultResponse)
async def stress_deck(
    user_id: str,  # noqa: ARG001  Required for route pattern
    format_name: str,
    deck_name: str,
    scenario: StressScenarioRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> StressResultResponse:
    """
    Apply a stress scenario to a deck.

    Stress types:
    - underperform: Key cards appear less frequently
    - missing: Remove copies of a specific card
    - delayed: Simulate mana problems
    - hostile_meta: Face more interaction than expected

    Returns before/after fragility comparison and recommendations.
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
        description=f"Stress test: {stress_type.value} on {scenario.target}",
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
            )
            for a in result.affected_assumptions
        ],
        breaking_point=result.breaking_point,
        explanation=result.explanation,
        recommendations=result.recommendations,
    )


@router.get(
    "/breaking-point/{user_id}/{format_name}/{deck_name}",
    response_model=BreakingPointResponse
)
async def get_breaking_point(
    user_id: str,  # noqa: ARG001  Required for route pattern
    format_name: str,
    deck_name: str,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> BreakingPointResponse:
    """
    Find the breaking point of a deck.

    Analyzes the deck under multiple stress scenarios to find
    its weakest point and overall resilience.
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

    breaking_scenario = None
    if analysis.breaking_scenario:
        breaking_scenario = StressScenarioRequest(
            stress_type=analysis.breaking_scenario.stress_type.value,
            target=analysis.breaking_scenario.target,
            intensity=analysis.breaking_scenario.intensity,
        )

    return BreakingPointResponse(
        deck_name=analysis.deck_name,
        weakest_assumption=analysis.weakest_assumption,
        breaking_intensity=analysis.breaking_intensity,
        resilience_score=analysis.resilience_score,
        breaking_scenario=breaking_scenario,
        explanation=analysis.explanation,
    )
