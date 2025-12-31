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
from forgebreaker.models.canonical_card import InventoryCard
from forgebreaker.models.failure import KnownError
from forgebreaker.parsers.arena_export import parse_arena_to_inventory
from forgebreaker.parsers.collection_import import parse_collection_text
from forgebreaker.services.canonical_card_resolver import CanonicalCardResolver
from forgebreaker.services.card_database import (
    get_card_colors,
    get_card_database,
    get_card_rarity,
    get_card_type,
)
from forgebreaker.services.demo_collection import (
    demo_collection_available,
    get_demo_collection,
)

# Collection source type for demo/user distinction
CollectionSource = Literal["DEMO", "USER"]

router = APIRouter(prefix="/collection", tags=["collection"])


class CollectionResponse(BaseModel):
    """Response model for collection data."""

    user_id: str
    cards: dict[str, int] = Field(default_factory=dict)
    total_cards: int = 0
    unique_cards: int = 0
    collection_source: CollectionSource = Field(
        default="USER",
        description="Source of collection data: DEMO (sample data) or USER (user-uploaded)",
    )


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
    import_mode: Literal["new", "replace"] = Field(
        default="new",
        description="Import mode: 'new' for first import (fails if collection exists), "
        "'replace' to explicitly replace existing collection.",
    )


class SanitizationInfo(BaseModel):
    """Information about collection sanitization during import."""

    cards_removed: int = Field(
        ...,
        description="Number of unique cards removed during sanitization",
    )
    message: str = Field(
        ...,
        description="User-friendly message about sanitization",
    )


class ImportResponse(BaseModel):
    """Response model for collection import."""

    user_id: str
    cards_imported: int
    total_cards: int
    cards: dict[str, int] = Field(default_factory=dict)
    collection_source: CollectionSource = Field(
        default="USER",
        description="Always USER after import (user data replaces demo)",
    )
    replaced_existing: bool = Field(
        default=False,
        description="True if an existing collection was replaced",
    )
    sanitization: SanitizationInfo | None = Field(
        default=None,
        description="Sanitization info if cards were removed (non-blocking, informational)",
    )


class DeleteResponse(BaseModel):
    """Response model for delete operations."""

    user_id: str
    deleted: bool
    message: str = Field(
        default="",
        description="User-friendly message about the deletion",
    )


class CollectionStatsResponse(BaseModel):
    """Response model for detailed collection statistics."""

    user_id: str
    total_cards: int = 0
    unique_cards: int = 0
    by_rarity: dict[str, int] = Field(
        default_factory=dict,
        description="Card counts by rarity (common, uncommon, rare, mythic)",
    )
    by_color: dict[str, int] = Field(
        default_factory=dict,
        description="Card counts by color (W, U, B, R, G, colorless, multicolor)",
    )
    by_type: dict[str, int] = Field(
        default_factory=dict,
        description="Card counts by primary type (Creature, Instant, etc.)",
    )
    collection_source: CollectionSource = Field(
        default="USER",
        description="Source of collection data: DEMO (sample data) or USER (user-uploaded)",
    )


def _extract_primary_type(type_line: str) -> str:
    """Extract primary card type from type line."""
    if not type_line:
        return "Unknown"

    # Handle double-faced cards (take first face)
    type_line = type_line.split("//")[0].strip()

    # Order matters - check by priority order (first match wins)
    type_order = [
        "Creature",
        "Planeswalker",
        "Instant",
        "Sorcery",
        "Enchantment",
        "Artifact",
        "Land",
    ]

    for card_type in type_order:
        if card_type in type_line:
            return card_type

    return "Other"


@router.get("/{user_id}", response_model=CollectionResponse)
async def get_user_collection(
    user_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CollectionResponse:
    """
    Get a user's card collection.

    Returns the collection with all cards and quantities.
    If user has no collection, returns demo collection (sample data).
    The collection_source field indicates DEMO or USER origin.
    """
    db_collection = await get_collection(session, user_id)

    if db_collection is None:
        # No user collection - return demo data if available
        if demo_collection_available():
            demo = get_demo_collection()
            return CollectionResponse(
                user_id=user_id,
                cards=demo.cards,
                total_cards=demo.total_cards(),
                unique_cards=demo.unique_cards(),
                collection_source="DEMO",
            )
        # Demo not available - return empty
        return CollectionResponse(
            user_id=user_id,
            cards={},
            total_cards=0,
            unique_cards=0,
            collection_source="USER",
        )

    model = collection_to_model(db_collection)

    return CollectionResponse(
        user_id=user_id,
        cards=model.cards,
        total_cards=model.total_cards(),
        unique_cards=model.unique_cards(),
        collection_source="USER",
    )


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

    return CollectionResponse(
        user_id=user_id,
        cards=model.cards,
        total_cards=model.total_cards(),
        unique_cards=model.unique_cards(),
        collection_source="USER",
    )


@router.delete("/{user_id}", response_model=DeleteResponse)
async def delete_user_collection(
    user_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> DeleteResponse:
    """
    Delete a user's card collection.

    This is an explicit, irreversible operation that:
    - Removes all cards from the user's collection
    - Clears associated metadata
    - Leaves the user with no collection

    After deletion, deck-building will fail until a new collection is imported.
    """
    deleted = await delete_collection(session, user_id)

    if deleted:
        message = "Your collection has been deleted. You can import a new collection at any time."
    else:
        message = "No collection found to delete."

    return DeleteResponse(user_id=user_id, deleted=deleted, message=message)


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

    Import modes (explicit, required):
    - import_mode="new": First import. Fails if collection already exists.
    - import_mode="replace": Explicitly replaces existing collection.

    INVARIANT: No silent data loss. Overwrite requires explicit replace mode.
    """
    if not request.text or not request.text.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Import text cannot be empty",
        )

    # Parse to InventoryCard list
    # For Arena format, use direct parsing to preserve set codes
    # For other formats, parse to dict then convert (loses set code info)
    if request.format == "arena" or (
        request.format == "auto" and "(" in request.text and ")" in request.text
    ):
        # Arena format - parse directly to InventoryCard
        inventory = parse_arena_to_inventory(request.text)
    else:
        # Other formats - parse to dict then convert to InventoryCard
        parsed_cards = parse_collection_text(request.text, request.format)
        inventory = [
            InventoryCard(name=name, set_code="", count=qty) for name, qty in parsed_cards.items()
        ]

    if not inventory:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No valid cards found in import text",
        )

    # Check for existing collection
    existing = await get_collection(session, user_id)
    had_existing_collection = existing is not None

    # INVARIANT: No silent data loss
    # If collection exists and mode is not "replace", fail explicitly
    if had_existing_collection and request.import_mode != "replace":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A collection already exists. "
            "To replace it, explicitly set import_mode='replace'.",
        )

    # If replacing, delete existing collection first
    if had_existing_collection and request.import_mode == "replace":
        await delete_collection(session, user_id)

    # Resolve inventory to canonical cards
    # This is the trust boundary: untrusted InventoryCard -> trusted OwnedCard
    # Terminal failure (KnownError) if ANY card fails resolution
    try:
        card_db = get_card_database()
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Card database not available. Please try again later.",
        ) from e

    resolver = CanonicalCardResolver(card_db)

    try:
        owned_cards = resolver.resolve_or_fail(inventory)
    except KnownError:
        # Re-raise as-is - will be handled by error middleware
        raise

    # Convert to dict for storage (canonical name -> summed count)
    cards_to_save = {oc.card.name: oc.count for oc in owned_cards}

    # Save the resolved collection
    db_collection = await update_collection_cards(session, user_id, cards_to_save)
    model = collection_to_model(db_collection)

    return ImportResponse(
        user_id=user_id,
        cards_imported=len(cards_to_save),
        total_cards=model.total_cards(),
        cards=model.cards,
        collection_source="USER",
        replaced_existing=had_existing_collection and request.import_mode == "replace",
        sanitization=None,  # No sanitization with canonical resolution - failures are terminal
    )


@router.get("/{user_id}/stats", response_model=CollectionStatsResponse)
async def get_collection_stats(
    user_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CollectionStatsResponse:
    """
    Get detailed statistics about a user's collection.

    Returns breakdowns by rarity, color, and card type when the card database
    is available. Falls back to basic counts (total and unique cards) if the
    card database is unavailable.

    If user has no collection, returns stats for demo collection.
    """
    db_collection = await get_collection(session, user_id)

    # Determine collection source and get collection data
    if db_collection is None:
        # No user collection - use demo data if available
        if demo_collection_available():
            collection = get_demo_collection()
            collection_source: CollectionSource = "DEMO"
        else:
            return CollectionStatsResponse(user_id=user_id, collection_source="USER")
    else:
        collection = collection_to_model(db_collection)
        collection_source = "USER"

    # Try to load card database for detailed stats
    try:
        card_db = get_card_database()
    except FileNotFoundError:
        # Return basic stats if card database not available
        return CollectionStatsResponse(
            user_id=user_id,
            total_cards=collection.total_cards(),
            unique_cards=collection.unique_cards(),
            collection_source=collection_source,
        )

    # Calculate breakdowns
    by_rarity: dict[str, int] = {
        "common": 0,
        "uncommon": 0,
        "rare": 0,
        "mythic": 0,
        "other": 0,
    }
    by_color: dict[str, int] = {
        "W": 0,
        "U": 0,
        "B": 0,
        "R": 0,
        "G": 0,
        "colorless": 0,
        "multicolor": 0,
        "other": 0,
    }
    by_type: dict[str, int] = {}

    for card_name, quantity in collection.cards.items():
        # Rarity (handles special/bonus rarities via "other")
        rarity = get_card_rarity(card_name, card_db)
        if rarity in by_rarity and rarity != "other":
            by_rarity[rarity] += quantity
        else:
            by_rarity["other"] += quantity

        # Colors (handles non-WUBRG colors via "other")
        colors = get_card_colors(card_name, card_db)
        if not colors:
            by_color["colorless"] += quantity
        elif len(colors) > 1:
            by_color["multicolor"] += quantity
        else:
            color = colors[0]
            if color in by_color and color not in ("colorless", "multicolor", "other"):
                by_color[color] += quantity
            else:
                by_color["other"] += quantity

        # Type
        type_line = get_card_type(card_name, card_db)
        primary_type = _extract_primary_type(type_line)
        by_type[primary_type] = by_type.get(primary_type, 0) + quantity

    return CollectionStatsResponse(
        user_id=user_id,
        total_cards=collection.total_cards(),
        unique_cards=collection.unique_cards(),
        by_rarity=by_rarity,
        by_color=by_color,
        by_type=by_type,
        collection_source=collection_source,
    )
