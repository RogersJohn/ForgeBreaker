"""Tests for database CRUD operations."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from forgebreaker.db.operations import (
    collection_to_model,
    create_collection,
    delete_collection,
    delete_meta_decks_by_format,
    get_collection,
    get_meta_deck,
    get_meta_decks_by_format,
    get_or_create_collection,
    meta_deck_to_model,
    sync_meta_decks,
    update_collection_cards,
    upsert_meta_deck,
)
from forgebreaker.models.db import Base
from forgebreaker.models.deck import MetaDeck


@pytest.fixture
async def async_engine():
    """Create an in-memory SQLite engine for testing."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
async def session(async_engine) -> AsyncSession:
    """Provide a database session for tests."""
    async_session = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session


class TestCollectionOperations:
    async def test_create_collection(self, session: AsyncSession) -> None:
        """Can create a new collection."""
        collection = await create_collection(session, "user-123")

        assert collection.id is not None
        assert collection.user_id == "user-123"

    async def test_get_collection(self, session: AsyncSession) -> None:
        """Can retrieve an existing collection."""
        await create_collection(session, "user-123")
        await session.commit()

        collection = await get_collection(session, "user-123")

        assert collection is not None
        assert collection.user_id == "user-123"

    async def test_get_collection_not_found(self, session: AsyncSession) -> None:
        """Returns None for non-existent collection."""
        collection = await get_collection(session, "nonexistent")

        assert collection is None

    async def test_get_or_create_existing(self, session: AsyncSession) -> None:
        """Returns existing collection without creating new."""
        await create_collection(session, "user-123")
        await session.commit()

        collection, created = await get_or_create_collection(session, "user-123")

        assert created is False
        assert collection.user_id == "user-123"

    async def test_get_or_create_new(self, session: AsyncSession) -> None:
        """Creates new collection if none exists."""
        collection, created = await get_or_create_collection(session, "new-user")

        assert created is True
        assert collection.user_id == "new-user"

    async def test_update_collection_cards(self, session: AsyncSession) -> None:
        """Can update collection with new cards."""
        cards = {"Lightning Bolt": 4, "Mountain": 20}

        collection = await update_collection_cards(session, "user-123", cards)
        await session.commit()

        assert len(collection.cards) == 2
        card_dict = {c.card_name: c.quantity for c in collection.cards}
        assert card_dict["Lightning Bolt"] == 4
        assert card_dict["Mountain"] == 20

    async def test_update_collection_replaces_cards(self, session: AsyncSession) -> None:
        """Updating cards replaces existing ones."""
        await update_collection_cards(session, "user-123", {"Old Card": 2})
        await session.commit()

        collection = await update_collection_cards(session, "user-123", {"New Card": 4})
        await session.commit()

        assert len(collection.cards) == 1
        assert collection.cards[0].card_name == "New Card"

    async def test_collection_to_model(self, session: AsyncSession) -> None:
        """Can convert DB collection to domain model."""
        await update_collection_cards(session, "user-123", {"Lightning Bolt": 4, "Mountain": 20})
        await session.commit()

        db_collection = await get_collection(session, "user-123")
        model = collection_to_model(db_collection)

        assert model.get_quantity("Lightning Bolt") == 4
        assert model.get_quantity("Mountain") == 20

    async def test_delete_collection(self, session: AsyncSession) -> None:
        """Can delete a collection."""
        await create_collection(session, "user-123")
        await session.commit()

        deleted = await delete_collection(session, "user-123")
        await session.commit()

        assert deleted is True
        assert await get_collection(session, "user-123") is None

    async def test_delete_collection_not_found(self, session: AsyncSession) -> None:
        """Returns False when deleting non-existent collection."""
        deleted = await delete_collection(session, "nonexistent")

        assert deleted is False


class TestMetaDeckOperations:
    @pytest.fixture
    def sample_deck(self) -> MetaDeck:
        return MetaDeck(
            name="Mono Red Aggro",
            archetype="aggro",
            format="standard",
            cards={"Lightning Bolt": 4, "Mountain": 20},
            sideboard={"Abrade": 2},
            win_rate=0.55,
            meta_share=0.12,
            source_url="https://mtggoldfish.com/mono-red",
        )

    async def test_upsert_creates_new(self, session: AsyncSession, sample_deck: MetaDeck) -> None:
        """Upsert creates new deck if none exists."""
        db_deck = await upsert_meta_deck(session, sample_deck)
        await session.commit()

        assert db_deck.id is not None
        assert db_deck.name == "Mono Red Aggro"

    async def test_upsert_updates_existing(
        self, session: AsyncSession, sample_deck: MetaDeck
    ) -> None:
        """Upsert updates existing deck."""
        await upsert_meta_deck(session, sample_deck)
        await session.commit()

        updated_deck = MetaDeck(
            name="Mono Red Aggro",
            archetype="aggro",
            format="standard",
            cards={"Goblin Guide": 4},
            win_rate=0.60,
        )
        db_deck = await upsert_meta_deck(session, updated_deck)
        await session.commit()

        assert db_deck.cards == {"Goblin Guide": 4}
        assert db_deck.win_rate == pytest.approx(0.60)

    async def test_get_meta_deck(self, session: AsyncSession, sample_deck: MetaDeck) -> None:
        """Can retrieve a meta deck by name and format."""
        await upsert_meta_deck(session, sample_deck)
        await session.commit()

        db_deck = await get_meta_deck(session, "Mono Red Aggro", "standard")

        assert db_deck is not None
        assert db_deck.archetype == "aggro"

    async def test_get_meta_deck_not_found(self, session: AsyncSession) -> None:
        """Returns None for non-existent deck."""
        db_deck = await get_meta_deck(session, "Nonexistent", "standard")

        assert db_deck is None

    async def test_get_meta_decks_by_format(self, session: AsyncSession) -> None:
        """Can get all decks for a format ordered by meta share."""
        decks = [
            MetaDeck(name="Deck A", archetype="aggro", format="standard", meta_share=0.05),
            MetaDeck(name="Deck B", archetype="control", format="standard", meta_share=0.15),
            MetaDeck(name="Deck C", archetype="combo", format="historic"),
        ]
        for deck in decks:
            await upsert_meta_deck(session, deck)
        await session.commit()

        standard_decks = await get_meta_decks_by_format(session, "standard")

        assert len(standard_decks) == 2
        # Should be ordered by meta_share descending
        assert standard_decks[0].name == "Deck B"
        assert standard_decks[1].name == "Deck A"

    async def test_meta_deck_to_model(self, session: AsyncSession, sample_deck: MetaDeck) -> None:
        """Can convert DB deck to domain model."""
        db_deck = await upsert_meta_deck(session, sample_deck)
        await session.commit()

        model = meta_deck_to_model(db_deck)

        assert model.name == "Mono Red Aggro"
        assert model.cards["Lightning Bolt"] == 4
        assert model.win_rate == pytest.approx(0.55)

    async def test_delete_meta_decks_by_format(self, session: AsyncSession) -> None:
        """Can delete all decks for a format."""
        decks = [
            MetaDeck(name="Deck A", archetype="aggro", format="standard"),
            MetaDeck(name="Deck B", archetype="control", format="standard"),
            MetaDeck(name="Deck C", archetype="combo", format="historic"),
        ]
        for deck in decks:
            await upsert_meta_deck(session, deck)
        await session.commit()

        count = await delete_meta_decks_by_format(session, "standard")
        await session.commit()

        assert count == 2
        assert len(await get_meta_decks_by_format(session, "standard")) == 0
        assert len(await get_meta_decks_by_format(session, "historic")) == 1

    async def test_sync_meta_decks(self, session: AsyncSession) -> None:
        """Can sync multiple decks at once."""
        decks = [
            MetaDeck(name="Deck A", archetype="aggro", format="standard"),
            MetaDeck(name="Deck B", archetype="control", format="standard"),
        ]

        count = await sync_meta_decks(session, "standard", decks)
        await session.commit()

        assert count == 2
        assert len(await get_meta_decks_by_format(session, "standard")) == 2
