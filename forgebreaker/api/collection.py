"""
Collection API endpoints.

Provides CRUD operations for user card collections.
"""

from typing import Annotated, Literal

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
from forgebreaker.parsers.collection_import import parse_collection_text

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


class CollectionImportRequest(BaseModel):
    """Request model for importing a collection from text."""

    text: str = Field(
        ...,
        description="Raw collection text (CSV, simple format, or Arena export)",
        examples=["4 Lightning Bolt\n4 Monastery Swiftspear"],
    )
    format: Literal["auto", "simple", "csv", "arena"] = Field(
        default="auto",
        description="Format hint: auto-detect, simple (4 Card), csv, or arena",
    )
    merge: bool = Field(
        default=False,
        description="If true, merge with existing collection (keep max qty)",
    )


class ImportResponse(BaseModel):
    """Response model for collection import."""

    user_id: str
    cards_imported: int
    total_cards: int
    cards: dict[str, int] = Field(default_factory=dict)


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

    return CollectionResponse(user_id=user_id, cards=model.cards, total_cards=model.total_cards())


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

    # Validate card names and quantities
    for card_name, qty in request.cards.items():
        if not card_name or not card_name.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Card names cannot be empty",
            )
        if qty <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Quantity for '{card_name}' must be positive",
            )

    db_collection = await update_collection_cards(session, user_id, request.cards)
    model = collection_to_model(db_collection)

    return CollectionResponse(user_id=user_id, cards=model.cards, total_cards=model.total_cards())


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


@router.post("/{user_id}/import", response_model=ImportResponse)
async def import_user_collection(
    user_id: str,
    request: CollectionImportRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ImportResponse:
    """
    Import a collection from text in various formats.

    Supported formats (auto-detected):
    - Simple: "4 Lightning Bolt" or "4x Lightning Bolt"
    - CSV: "Card Name",Quantity,Set (MTGGoldfish/DeckStats style)
    - Arena: "4 Lightning Bolt (LEB) 163"

    If merge=true, keeps the maximum quantity for each card
    between existing and imported collections.
    """
    if not request.text or not request.text.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Import text cannot be empty",
        )

    # Parse the import text
    parsed_cards = parse_collection_text(request.text, request.format)

    if not parsed_cards:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No valid cards found in import text",
        )

    # If merge mode, combine with existing collection
    if request.merge:
        existing = await get_collection(session, user_id)
        if existing:
            existing_model = collection_to_model(existing)
            for name, qty in existing_model.cards.items():
                parsed_cards[name] = max(parsed_cards.get(name, 0), qty)

    # Save the collection
    db_collection = await update_collection_cards(session, user_id, parsed_cards)
    model = collection_to_model(db_collection)

    return ImportResponse(
        user_id=user_id,
        cards_imported=len(parsed_cards),
        total_cards=model.total_cards(),
        cards=model.cards,
    )
