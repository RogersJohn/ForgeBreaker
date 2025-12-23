"""
Database CRUD operations.

Provides async functions for creating, reading, updating, and deleting
collections and meta decks.
"""

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from forgebreaker.models.collection import Collection
from forgebreaker.models.db import CardOwnershipDB, MetaDeckDB, UserCollectionDB
from forgebreaker.models.deck import MetaDeck

# --- Collection Operations ---


async def get_collection(session: AsyncSession, user_id: str) -> UserCollectionDB | None:
    """
    Get a user's collection by user_id.

    Returns None if no collection exists for this user.
    """
    result = await session.execute(
        select(UserCollectionDB)
        .where(UserCollectionDB.user_id == user_id)
        .options(selectinload(UserCollectionDB.cards))
    )
    return result.scalar_one_or_none()


async def create_collection(session: AsyncSession, user_id: str) -> UserCollectionDB:
    """
    Create a new collection for a user.

    Raises IntegrityError if collection already exists.
    """
    collection = UserCollectionDB(user_id=user_id)
    session.add(collection)
    await session.flush()
    return collection


async def get_or_create_collection(
    session: AsyncSession, user_id: str
) -> tuple[UserCollectionDB, bool]:
    """
    Get existing collection or create new one.

    Returns:
        Tuple of (collection, created) where created is True if new.
    """
    collection = await get_collection(session, user_id)
    if collection:
        return collection, False

    collection = await create_collection(session, user_id)
    return collection, True


async def update_collection_cards(
    session: AsyncSession,
    user_id: str,
    cards: dict[str, int],
) -> UserCollectionDB:
    """
    Replace a user's collection with new card data.

    Deletes existing cards and creates new ownership records.
    """
    # Use get_or_create to ensure collection exists
    await get_or_create_collection(session, user_id)

    # Always re-fetch with eager loading to avoid async lazy load issues
    loaded = await get_collection(session, user_id)
    if not loaded:
        msg = f"Collection for user {user_id} not found after creation"
        raise RuntimeError(msg)
    collection = loaded

    # Delete existing cards from database first
    await session.execute(
        delete(CardOwnershipDB).where(CardOwnershipDB.collection_id == collection.id)
    )
    # Clear the ORM list to stay in sync
    collection.cards.clear()

    # Add new cards
    for card_name, quantity in cards.items():
        collection.cards.append(CardOwnershipDB(card_name=card_name, quantity=quantity))

    await session.flush()
    return collection


def collection_to_model(collection: UserCollectionDB) -> Collection:
    """Convert a database collection to a domain model."""
    cards = {card.card_name: card.quantity for card in collection.cards}
    return Collection(cards=cards)


async def delete_collection(session: AsyncSession, user_id: str) -> bool:
    """
    Delete a user's collection.

    Returns True if deleted, False if not found.
    """
    collection = await get_collection(session, user_id)
    if not collection:
        return False

    await session.delete(collection)
    return True


# --- Meta Deck Operations ---


async def get_meta_deck(session: AsyncSession, name: str, format_name: str) -> MetaDeckDB | None:
    """Get a meta deck by name and format."""
    result = await session.execute(
        select(MetaDeckDB).where(
            MetaDeckDB.name == name,
            MetaDeckDB.format == format_name,
        )
    )
    return result.scalar_one_or_none()


async def get_meta_decks_by_format(
    session: AsyncSession, format_name: str, limit: int = 50
) -> list[MetaDeckDB]:
    """Get all meta decks for a format, ordered by meta share."""
    result = await session.execute(
        select(MetaDeckDB)
        .where(MetaDeckDB.format == format_name)
        .order_by(MetaDeckDB.meta_share.desc().nulls_last())
        .limit(limit)
    )
    return list(result.scalars().all())


async def upsert_meta_deck(session: AsyncSession, deck: MetaDeck) -> MetaDeckDB:
    """
    Insert or update a meta deck.

    If a deck with the same name+format exists, updates it.
    Otherwise creates a new record.
    """
    existing = await get_meta_deck(session, deck.name, deck.format)

    if existing:
        existing.archetype = deck.archetype
        existing.cards = deck.cards
        existing.sideboard = deck.sideboard
        existing.win_rate = deck.win_rate
        existing.meta_share = deck.meta_share
        existing.source_url = deck.source_url
        await session.flush()
        return existing

    db_deck = MetaDeckDB(
        name=deck.name,
        archetype=deck.archetype,
        format=deck.format,
        cards=deck.cards,
        sideboard=deck.sideboard,
        win_rate=deck.win_rate,
        meta_share=deck.meta_share,
        source_url=deck.source_url,
    )
    session.add(db_deck)
    await session.flush()
    return db_deck


def meta_deck_to_model(db_deck: MetaDeckDB) -> MetaDeck:
    """Convert a database meta deck to a domain model."""
    return MetaDeck(
        name=db_deck.name,
        archetype=db_deck.archetype,
        format=db_deck.format,
        cards=db_deck.cards,
        sideboard=db_deck.sideboard,
        win_rate=db_deck.win_rate,
        meta_share=db_deck.meta_share,
        source_url=db_deck.source_url,
    )


async def delete_meta_decks_by_format(session: AsyncSession, format_name: str) -> int:
    """
    Delete all meta decks for a format.

    Returns the number of deleted records.
    """
    result = await session.execute(delete(MetaDeckDB).where(MetaDeckDB.format == format_name))
    # rowcount is available on DELETE results; type stubs incomplete for async
    return int(result.rowcount)  # type: ignore[attr-defined]


async def sync_meta_decks(session: AsyncSession, format_name: str, decks: list[MetaDeck]) -> int:
    """
    Sync meta decks for a format.

    Upserts all provided decks. Returns count of decks synced.
    Validates that all decks match the specified format.
    """
    for deck in decks:
        if deck.format != format_name:
            msg = f"Deck '{deck.name}' has format '{deck.format}', expected '{format_name}'"
            raise ValueError(msg)
        await upsert_meta_deck(session, deck)

    return len(decks)
