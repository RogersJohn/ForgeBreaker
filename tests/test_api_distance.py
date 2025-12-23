"""Tests for distance API endpoint."""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from forgebreaker.db import update_collection_cards, upsert_meta_deck
from forgebreaker.db.database import get_session
from forgebreaker.main import app
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
async def client(async_engine):
    """Provide an async test client with overridden database session."""
    async_session = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)

    async def override_get_session():
        async with async_session() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_session] = override_get_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()


@pytest.fixture
async def seeded_db(async_engine):
    """Seed database with test deck and collection."""
    async_session = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)

    deck = MetaDeck(
        name="Mono Red Aggro",
        archetype="aggro",
        format="standard",
        cards={"Lightning Bolt": 4, "Goblin Guide": 4, "Mountain": 20},
        sideboard={"Abrade": 2},
        win_rate=0.55,
        meta_share=0.15,
    )

    # User owns some but not all cards
    collection_cards = {"Lightning Bolt": 4, "Mountain": 20, "Forest": 10}

    async with async_session() as session:
        await upsert_meta_deck(session, deck)
        await update_collection_cards(session, "user123", collection_cards)
        await session.commit()

    return {"deck": deck, "collection_cards": collection_cards}


class TestCalculateDistance:
    async def test_distance_partial_collection(
        self,
        client: AsyncClient,
        seeded_db: dict,  # noqa: ARG002
    ) -> None:
        """Returns correct distance for partial collection."""
        response = await client.get("/distance/user123/standard/Mono Red Aggro")

        assert response.status_code == 200
        data = response.json()

        assert data["deck_name"] == "Mono Red Aggro"
        assert data["deck_format"] == "standard"
        assert data["owned_cards"] == 24  # 4 Lightning Bolt + 20 Mountain
        assert data["missing_cards"] == 6  # 4 Goblin Guide + 2 Abrade (sideboard)
        assert data["total_cards"] == 30  # includes sideboard
        assert data["is_complete"] is False
        assert 0.0 <= data["completion_percentage"] <= 1.0

    async def test_distance_missing_deck(self, client: AsyncClient) -> None:
        """Returns 404 for nonexistent deck."""
        response = await client.get("/distance/user123/standard/Nonexistent Deck")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    async def test_distance_empty_collection(
        self,
        client: AsyncClient,
        seeded_db: dict,  # noqa: ARG002
    ) -> None:
        """Returns full distance for user with no collection."""
        response = await client.get("/distance/new_user/standard/Mono Red Aggro")

        assert response.status_code == 200
        data = response.json()

        assert data["owned_cards"] == 0
        assert data["missing_cards"] == 30  # includes sideboard
        assert data["is_complete"] is False
        assert data["completion_percentage"] == 0.0

    async def test_distance_includes_wildcard_cost(
        self,
        client: AsyncClient,
        seeded_db: dict,  # noqa: ARG002
    ) -> None:
        """Response includes wildcard cost breakdown."""
        response = await client.get("/distance/user123/standard/Mono Red Aggro")

        assert response.status_code == 200
        data = response.json()

        wildcard_cost = data["wildcard_cost"]
        assert "common" in wildcard_cost
        assert "uncommon" in wildcard_cost
        assert "rare" in wildcard_cost
        assert "mythic" in wildcard_cost
        assert "total" in wildcard_cost
        assert wildcard_cost["total"] >= 0

    async def test_distance_includes_missing_card_list(
        self,
        client: AsyncClient,
        seeded_db: dict,  # noqa: ARG002
    ) -> None:
        """Response includes list of missing cards."""
        response = await client.get("/distance/user123/standard/Mono Red Aggro")

        assert response.status_code == 200
        data = response.json()

        missing_list = data["missing_card_list"]
        assert isinstance(missing_list, list)
        assert len(missing_list) == 2  # Goblin Guide + Abrade (sideboard)

        # Check that expected cards are missing
        missing_names = {card["name"] for card in missing_list}
        assert "Goblin Guide" in missing_names
        assert "Abrade" in missing_names

        # Verify structure
        for card in missing_list:
            assert "name" in card
            assert "quantity" in card
            assert "rarity" in card

    async def test_distance_wrong_format(
        self,
        client: AsyncClient,
        seeded_db: dict,  # noqa: ARG002
    ) -> None:
        """Returns 404 if deck exists but in different format."""
        response = await client.get("/distance/user123/historic/Mono Red Aggro")

        assert response.status_code == 404


class TestDistanceCompleteCollection:
    @pytest.fixture
    async def complete_collection_db(self, async_engine):
        """Seed database with complete collection for deck."""
        async_session = async_sessionmaker(
            async_engine, class_=AsyncSession, expire_on_commit=False
        )

        deck = MetaDeck(
            name="Simple Deck",
            archetype="aggro",
            format="standard",
            cards={"Lightning Bolt": 4},
        )

        collection_cards = {"Lightning Bolt": 4}

        async with async_session() as session:
            await upsert_meta_deck(session, deck)
            await update_collection_cards(session, "complete_user", collection_cards)
            await session.commit()

        return {"deck": deck, "collection_cards": collection_cards}

    async def test_complete_collection(
        self,
        client: AsyncClient,
        complete_collection_db: dict,  # noqa: ARG002
    ) -> None:
        """Returns is_complete=True when user has all cards."""
        response = await client.get("/distance/complete_user/standard/Simple Deck")

        assert response.status_code == 200
        data = response.json()

        assert data["is_complete"] is True
        assert data["missing_cards"] == 0
        assert data["completion_percentage"] == 1.0
        assert data["missing_card_list"] == []
