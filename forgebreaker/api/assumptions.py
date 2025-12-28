"""
Assumptions API endpoint.

Extracts and returns deck assumptions for analysis.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from forgebreaker.analysis.assumptions import extract_assumptions
from forgebreaker.db import get_meta_deck, meta_deck_to_model
from forgebreaker.db.database import get_session
from forgebreaker.services.card_database import get_card_database

router = APIRouter(prefix="/assumptions", tags=["assumptions"])


class AssumptionResponse(BaseModel):
    """A single deck assumption."""

    name: str
    category: str
    description: str
    current_value: Any
    expected_range: list[float]
    health: str
    explanation: str
    adjustable: bool


class AssumptionSetResponse(BaseModel):
    """Complete set of assumptions for a deck."""

    deck_name: str
    archetype: str
    assumptions: list[AssumptionResponse] = Field(default_factory=list)
    overall_fragility: float = Field(ge=0.0, le=1.0)
    fragility_explanation: str


@router.get("/{user_id}/{format_name}/{deck_name}", response_model=AssumptionSetResponse)
async def get_deck_assumptions(
    user_id: str,  # noqa: ARG001  Required for route pattern
    format_name: str,
    deck_name: str,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AssumptionSetResponse:
    """
    Get assumptions for a meta deck.

    Analyzes the deck to identify implicit assumptions about:
    - Mana curve expectations
    - Draw consistency
    - Key card dependencies
    - Interaction timing

    Returns a fragility score indicating how assumption-dependent the deck is.
    """
    # Get the deck
    db_deck = await get_meta_deck(session, deck_name, format_name)
    if db_deck is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Deck '{deck_name}' not found in format '{format_name}'",
        )

    deck = meta_deck_to_model(db_deck)

    # Load card database for analysis
    try:
        card_db = get_card_database()
    except FileNotFoundError:
        # Provide analysis with empty card db (limited info)
        card_db = {}

    # Extract assumptions
    assumption_set = extract_assumptions(deck, card_db)

    # Build response
    return AssumptionSetResponse(
        deck_name=assumption_set.deck_name,
        archetype=assumption_set.archetype,
        assumptions=[
            AssumptionResponse(
                name=a.name,
                category=a.category.value,
                description=a.description,
                current_value=a.current_value,
                expected_range=list(a.expected_range),
                health=a.health.value,
                explanation=a.explanation,
                adjustable=a.adjustable,
            )
            for a in assumption_set.assumptions
        ],
        overall_fragility=assumption_set.overall_fragility,
        fragility_explanation=assumption_set.fragility_explanation,
    )
