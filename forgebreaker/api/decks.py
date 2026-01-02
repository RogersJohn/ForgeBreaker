"""
Deck API endpoints.

Provides endpoints for querying meta decks by format.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from forgebreaker.db import (
    get_meta_deck,
    get_meta_decks_by_format,
    meta_deck_to_model,
    upsert_meta_deck,
)
from forgebreaker.db.database import get_session
from forgebreaker.jobs.update_meta import run_meta_update
from forgebreaker.scrapers.mtggoldfish import VALID_FORMATS
from forgebreaker.services.sample_deck import get_sample_deck

router = APIRouter(prefix="/decks", tags=["decks"])


class DeckResponse(BaseModel):
    """Response model for a single deck."""

    name: str
    archetype: str
    format: str
    cards: dict[str, int] = Field(default_factory=dict)
    sideboard: dict[str, int] = Field(default_factory=dict)
    win_rate: float | None = None
    meta_share: float | None = None
    source_url: str | None = None


class DeckListResponse(BaseModel):
    """Response model for a list of decks."""

    format: str
    decks: list[DeckResponse]
    count: int


class SyncResponse(BaseModel):
    """Response model for sync operation."""

    synced: dict[str, int]
    total: int


@router.post("/sync", response_model=SyncResponse)
async def sync_meta_decks(
    formats: list[str] | None = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 15,
) -> SyncResponse:
    """
    Trigger meta deck sync from MTGGoldfish.

    Scrapes current meta decks and saves to database.
    If formats is None, syncs all valid Arena formats.
    """
    if formats:
        invalid = set(formats) - VALID_FORMATS
        if invalid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid formats: {invalid}. Valid: {list(VALID_FORMATS)}",
            )

    results = await run_meta_update(formats=formats, limit=limit)
    return SyncResponse(synced=results, total=sum(results.values()))


@router.get("/{format_name}", response_model=DeckListResponse)
async def get_decks_by_format(
    format_name: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> DeckListResponse:
    """
    Get meta decks for a format.

    Returns decks ordered by meta share (descending).
    """
    db_decks = await get_meta_decks_by_format(session, format_name, limit=limit)

    decks: list[DeckResponse] = []
    for d in db_decks:
        model = meta_deck_to_model(d)
        decks.append(
            DeckResponse(
                name=model.name,
                archetype=model.archetype,
                format=model.format,
                cards=model.cards,
                sideboard=model.sideboard or {},
                win_rate=model.win_rate,
                meta_share=model.meta_share,
                source_url=model.source_url,
            )
        )

    return DeckListResponse(format=format_name, decks=decks, count=len(decks))


@router.get("/{format_name}/{deck_name}", response_model=DeckResponse)
async def get_deck_by_name(
    format_name: str,
    deck_name: str,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> DeckResponse:
    """
    Get a specific deck by format and name.

    Returns 404 if deck not found.
    """
    db_deck = await get_meta_deck(session, deck_name, format_name)

    if db_deck is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Deck '{deck_name}' not found in format '{format_name}'",
        )

    model = meta_deck_to_model(db_deck)

    return DeckResponse(
        name=model.name,
        archetype=model.archetype,
        format=model.format,
        cards=model.cards,
        sideboard=model.sideboard or {},
        win_rate=model.win_rate,
        meta_share=model.meta_share,
        source_url=model.source_url,
    )


@router.post("/sample", response_model=DeckResponse)
async def create_sample_deck(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> DeckResponse:
    """
    Create a sample deck for exploring ForgeBreaker.

    Uses the same persistence as all other decks.
    """
    sample = get_sample_deck()
    await upsert_meta_deck(session, sample)

    return DeckResponse(
        name=sample.name,
        archetype=sample.archetype,
        format=sample.format,
        cards=sample.cards,
        sideboard=sample.sideboard or {},
        win_rate=sample.win_rate,
        meta_share=sample.meta_share,
        source_url=sample.source_url,
    )
