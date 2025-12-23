"""
Distance API endpoint.

Calculates how far a user's collection is from completing a deck.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from forgebreaker.analysis.distance import calculate_deck_distance
from forgebreaker.db import (
    collection_to_model,
    get_collection,
    get_meta_deck,
    meta_deck_to_model,
)
from forgebreaker.db.database import get_session
from forgebreaker.models.collection import Collection

router = APIRouter(prefix="/distance", tags=["distance"])


class WildcardCostResponse(BaseModel):
    """Wildcard cost breakdown by rarity."""

    common: int = 0
    uncommon: int = 0
    rare: int = 0
    mythic: int = 0
    total: int = 0


class MissingCard(BaseModel):
    """A card missing from the collection."""

    name: str
    quantity: int
    rarity: str


class DistanceResponse(BaseModel):
    """Response model for deck distance calculation."""

    deck_name: str
    deck_format: str
    owned_cards: int
    missing_cards: int
    total_cards: int
    completion_percentage: float = Field(ge=0.0, le=1.0)
    is_complete: bool
    wildcard_cost: WildcardCostResponse
    missing_card_list: list[MissingCard] = Field(default_factory=list)


@router.get("/{user_id}/{format_name}/{deck_name}", response_model=DistanceResponse)
async def calculate_distance(
    user_id: str,
    format_name: str,
    deck_name: str,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> DistanceResponse:
    """
    Calculate distance between a user's collection and a deck.

    Returns completion percentage, wildcard costs, and missing cards.
    """
    # Get the deck
    db_deck = await get_meta_deck(session, deck_name, format_name)
    if db_deck is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Deck '{deck_name}' not found in format '{format_name}'",
        )

    deck = meta_deck_to_model(db_deck)

    # Get user's collection (empty if not found)
    db_collection = await get_collection(session, user_id)
    collection = Collection() if db_collection is None else collection_to_model(db_collection)

    # Calculate distance (using empty rarity map - defaults to common)
    # TODO: Load rarity data from Scryfall when available
    rarity_map: dict[str, str] = {}
    distance = calculate_deck_distance(deck, collection, rarity_map)

    # Build response
    total_cards = distance.owned_cards + distance.missing_cards

    return DistanceResponse(
        deck_name=deck.name,
        deck_format=deck.format,
        owned_cards=distance.owned_cards,
        missing_cards=distance.missing_cards,
        total_cards=total_cards,
        completion_percentage=distance.completion_percentage,
        is_complete=distance.is_complete,
        wildcard_cost=WildcardCostResponse(
            common=distance.wildcard_cost.common,
            uncommon=distance.wildcard_cost.uncommon,
            rare=distance.wildcard_cost.rare,
            mythic=distance.wildcard_cost.mythic,
            total=distance.wildcard_cost.total(),
        ),
        missing_card_list=[
            MissingCard(name=name, quantity=qty, rarity=rarity)
            for name, qty, rarity in distance.missing_card_list
        ],
    )
