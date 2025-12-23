"""
Collection API endpoints.

Provides CRUD operations for user card collections.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from forgebreaker.db import (
    collection_to_model,
    delete_collection,
    get_collection,
    update_collection_cards,
)
from forgebreaker.db.database import get_session

router = APIRouter(prefix="/collection", tags=["collection"])


class CollectionResponse(BaseModel):
    """Response model for collection data."""

    user_id: str
    cards: dict[str, int] = Field(default_factory=dict)
    total_cards: int = 0


class CollectionUpdateRequest(BaseModel):
    """Request model for updating a collection."""

    cards: dict[str, int] = Field(
        ...,
        description="Map of card names to quantities",
        examples=[{"Lightning Bolt": 4, "Mountain": 20}],
    )


class DeleteResponse(BaseModel):
    """Response model for delete operations."""

    deleted: bool


@router.get("/{user_id}", response_model=CollectionResponse)
async def get_user_collection(
    user_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CollectionResponse:
    """
    Get a user's card collection.

    Returns the collection with all cards and quantities.
    Returns empty collection if user has no collection.
    """
    db_collection = await get_collection(session, user_id)

    if db_collection is None:
        return CollectionResponse(user_id=user_id, cards={}, total_cards=0)

    model = collection_to_model(db_collection)
    total = sum(model.cards.values())

    return CollectionResponse(user_id=user_id, cards=model.cards, total_cards=total)


@router.put("/{user_id}", response_model=CollectionResponse)
async def update_user_collection(
    user_id: str,
    request: CollectionUpdateRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CollectionResponse:
    """
    Update a user's card collection.

    Replaces the entire collection with the provided cards.
    Creates a new collection if one doesn't exist.
    """
    if not request.cards:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cards cannot be empty",
        )

    # Validate quantities are positive
    for card_name, qty in request.cards.items():
        if qty <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Quantity for '{card_name}' must be positive",
            )

    db_collection = await update_collection_cards(session, user_id, request.cards)
    model = collection_to_model(db_collection)
    total = sum(model.cards.values())

    return CollectionResponse(user_id=user_id, cards=model.cards, total_cards=total)


@router.delete("/{user_id}", response_model=DeleteResponse)
async def delete_user_collection(
    user_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> DeleteResponse:
    """
    Delete a user's card collection.

    Returns whether a collection was actually deleted.
    """
    deleted = await delete_collection(session, user_id)
    return DeleteResponse(deleted=deleted)
