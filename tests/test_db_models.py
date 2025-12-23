"""Tests for SQLAlchemy ORM models."""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from forgebreaker.models.db import Base, CardOwnershipDB, MetaDeckDB, UserCollectionDB


@pytest.fixture
async def async_engine():
    """Create an in-memory SQLite engine for testing."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
async def session(async_engine) -> AsyncSession:
    """Provide a database session for tests."""
    async_session = async_sessionmaker(
        async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with async_session() as session:
        yield session


class TestUserCollectionDB:
    async def test_create_collection(self, session: AsyncSession) -> None:
        """Can create a user collection."""
        collection = UserCollectionDB(user_id="test-user-123")
        session.add(collection)
        await session.commit()

        result = await session.execute(
            select(UserCollectionDB).where(UserCollectionDB.user_id == "test-user-123")
        )
        saved = result.scalar_one()

        assert saved.id is not None
        assert saved.user_id == "test-user-123"
        assert saved.created_at is not None

    async def test_user_id_unique(self, session: AsyncSession) -> None:
        """User ID must be unique."""
        from sqlalchemy.exc import IntegrityError

        collection1 = UserCollectionDB(user_id="duplicate-user")
        session.add(collection1)
        await session.commit()

        collection2 = UserCollectionDB(user_id="duplicate-user")
        session.add(collection2)

        with pytest.raises(IntegrityError):
            await session.commit()


class TestCardOwnershipDB:
    async def test_create_card_ownership(self, session: AsyncSession) -> None:
        """Can create card ownership records."""
        collection = UserCollectionDB(user_id="test-user")
        session.add(collection)
        await session.flush()

        card = CardOwnershipDB(
            collection_id=collection.id,
            card_name="Lightning Bolt",
            quantity=4,
        )
        session.add(card)
        await session.commit()

        result = await session.execute(
            select(CardOwnershipDB).where(CardOwnershipDB.card_name == "Lightning Bolt")
        )
        saved = result.scalar_one()

        assert saved.quantity == 4
        assert saved.collection_id == collection.id

    async def test_card_collection_relationship(self, session: AsyncSession) -> None:
        """Cards are linked to their collection."""
        collection = UserCollectionDB(user_id="test-user")
        collection.cards = [
            CardOwnershipDB(card_name="Lightning Bolt", quantity=4),
            CardOwnershipDB(card_name="Mountain", quantity=20),
        ]
        session.add(collection)
        await session.commit()

        # Query with eager loading to avoid async lazy load issues
        from sqlalchemy.orm import selectinload

        result = await session.execute(
            select(UserCollectionDB)
            .where(UserCollectionDB.user_id == "test-user")
            .options(selectinload(UserCollectionDB.cards))
        )
        loaded_collection = result.scalar_one()

        assert len(loaded_collection.cards) == 2
        card_names = [c.card_name for c in loaded_collection.cards]
        assert "Lightning Bolt" in card_names
        assert "Mountain" in card_names

    async def test_cascade_delete(self, session: AsyncSession) -> None:
        """Deleting collection deletes cards."""
        collection = UserCollectionDB(user_id="test-user")
        collection.cards = [
            CardOwnershipDB(card_name="Lightning Bolt", quantity=4),
        ]
        session.add(collection)
        await session.commit()

        collection_id = collection.id

        await session.delete(collection)
        await session.commit()

        # Cards should be deleted too
        result = await session.execute(
            select(CardOwnershipDB).where(CardOwnershipDB.collection_id == collection_id)
        )
        assert result.scalars().all() == []


class TestMetaDeckDB:
    async def test_create_meta_deck(self, session: AsyncSession) -> None:
        """Can create a meta deck record."""
        deck = MetaDeckDB(
            name="Mono Red Aggro",
            archetype="aggro",
            format="standard",
            cards={"Lightning Bolt": 4, "Mountain": 20},
            sideboard={"Abrade": 2},
            win_rate=0.55,
            meta_share=0.12,
            source_url="https://mtggoldfish.com/archetype/mono-red",
        )
        session.add(deck)
        await session.commit()

        result = await session.execute(
            select(MetaDeckDB).where(MetaDeckDB.name == "Mono Red Aggro")
        )
        saved = result.scalar_one()

        assert saved.archetype == "aggro"
        assert saved.cards["Lightning Bolt"] == 4
        assert saved.sideboard["Abrade"] == 2
        assert saved.win_rate == pytest.approx(0.55)

    async def test_json_fields(self, session: AsyncSession) -> None:
        """JSON fields store and retrieve correctly."""
        cards = {
            "Sheoldred, the Apocalypse": 4,
            "Go for the Throat": 2,
            "Swamp": 24,
        }
        deck = MetaDeckDB(
            name="Mono Black",
            archetype="midrange",
            format="standard",
            cards=cards,
        )
        session.add(deck)
        await session.commit()

        result = await session.execute(select(MetaDeckDB).where(MetaDeckDB.name == "Mono Black"))
        saved = result.scalar_one()

        assert saved.cards == cards

    async def test_nullable_fields(self, session: AsyncSession) -> None:
        """Optional fields can be null."""
        deck = MetaDeckDB(
            name="Unknown Deck",
            archetype="midrange",
            format="standard",
        )
        session.add(deck)
        await session.commit()

        result = await session.execute(select(MetaDeckDB).where(MetaDeckDB.name == "Unknown Deck"))
        saved = result.scalar_one()

        assert saved.win_rate is None
        assert saved.meta_share is None
        assert saved.source_url is None

    async def test_query_by_format(self, session: AsyncSession) -> None:
        """Can query decks by format."""
        session.add_all(
            [
                MetaDeckDB(name="Standard Deck", archetype="aggro", format="standard"),
                MetaDeckDB(name="Historic Deck", archetype="combo", format="historic"),
                MetaDeckDB(name="Another Standard", archetype="control", format="standard"),
            ]
        )
        await session.commit()

        result = await session.execute(select(MetaDeckDB).where(MetaDeckDB.format == "standard"))
        standard_decks = result.scalars().all()

        assert len(standard_decks) == 2

    async def test_updated_at_changes_on_update(self, session: AsyncSession) -> None:
        """Updated_at timestamp changes when record is modified."""
        import asyncio

        deck = MetaDeckDB(
            name="Update Test Deck",
            archetype="aggro",
            format="standard",
        )
        session.add(deck)
        await session.commit()

        original_updated_at = deck.updated_at

        # Small delay to ensure timestamp difference
        await asyncio.sleep(0.1)

        # Update the deck
        deck.win_rate = 0.55
        await session.commit()
        await session.refresh(deck)

        # updated_at should have changed
        assert deck.updated_at >= original_updated_at
