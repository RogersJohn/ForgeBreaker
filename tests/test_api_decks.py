"""Tests for deck API endpoints."""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from forgebreaker.db import upsert_meta_deck
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
    """Seed database with test decks."""
    async_session = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)

    decks = [
        MetaDeck(
            name="Mono Red Aggro",
            archetype="aggro",
            format="standard",
            cards={"Lightning Bolt": 4, "Mountain": 20},
            sideboard={"Abrade": 2},
            win_rate=0.55,
            meta_share=0.15,
            source_url="https://example.com/mono-red",
        ),
        MetaDeck(
            name="Azorius Control",
            archetype="control",
            format="standard",
            cards={"Counterspell": 4, "Island": 12, "Plains": 12},
            win_rate=0.52,
            meta_share=0.10,
        ),
        MetaDeck(
            name="Historic Elves",
            archetype="combo",
            format="historic",
            cards={"Llanowar Elves": 4, "Forest": 20},
            meta_share=0.08,
        ),
    ]

    async with async_session() as session:
        for deck in decks:
            await upsert_meta_deck(session, deck)
        await session.commit()

    return decks


class TestGetDecksByFormat:
    async def test_get_empty_format(self, client: AsyncClient) -> None:
        """Returns empty list for format with no decks."""
        response = await client.get("/decks/standard")

        assert response.status_code == 200
        data = response.json()
        assert data["format"] == "standard"
        assert data["decks"] == []
        assert data["count"] == 0

    async def test_get_decks_by_format(
        self,
        client: AsyncClient,
        seeded_db: list[MetaDeck],  # noqa: ARG002
    ) -> None:
        """Returns decks for a specific format."""
        response = await client.get("/decks/standard")

        assert response.status_code == 200
        data = response.json()
        assert data["format"] == "standard"
        assert data["count"] == 2

        # Should be ordered by meta_share descending
        assert data["decks"][0]["name"] == "Mono Red Aggro"
        assert data["decks"][1]["name"] == "Azorius Control"

    async def test_get_decks_with_limit(
        self,
        client: AsyncClient,
        seeded_db: list[MetaDeck],  # noqa: ARG002
    ) -> None:
        """Respects limit parameter."""
        response = await client.get("/decks/standard?limit=1")

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 1
        assert data["decks"][0]["name"] == "Mono Red Aggro"

    async def test_deck_includes_all_fields(
        self,
        client: AsyncClient,
        seeded_db: list[MetaDeck],  # noqa: ARG002
    ) -> None:
        """Deck response includes all expected fields."""
        response = await client.get("/decks/standard")

        assert response.status_code == 200
        deck = response.json()["decks"][0]

        assert deck["name"] == "Mono Red Aggro"
        assert deck["archetype"] == "aggro"
        assert deck["format"] == "standard"
        assert deck["cards"]["Lightning Bolt"] == 4
        assert deck["sideboard"]["Abrade"] == 2
        assert deck["win_rate"] == pytest.approx(0.55)
        assert deck["meta_share"] == pytest.approx(0.15)
        assert deck["source_url"] == "https://example.com/mono-red"

    async def test_different_format_returns_different_decks(
        self,
        client: AsyncClient,
        seeded_db: list[MetaDeck],  # noqa: ARG002
    ) -> None:
        """Each format returns only its own decks."""
        response = await client.get("/decks/historic")

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 1
        assert data["decks"][0]["name"] == "Historic Elves"


class TestGetDeckByName:
    async def test_get_deck_by_name(
        self,
        client: AsyncClient,
        seeded_db: list[MetaDeck],  # noqa: ARG002
    ) -> None:
        """Can retrieve a specific deck by name."""
        response = await client.get("/decks/standard/Mono Red Aggro")

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Mono Red Aggro"
        assert data["archetype"] == "aggro"
        assert data["cards"]["Lightning Bolt"] == 4

    async def test_deck_not_found(self, client: AsyncClient) -> None:
        """Returns 404 for nonexistent deck."""
        response = await client.get("/decks/standard/Nonexistent Deck")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    async def test_deck_wrong_format(
        self,
        client: AsyncClient,
        seeded_db: list[MetaDeck],  # noqa: ARG002
    ) -> None:
        """Returns 404 if deck exists but in different format."""
        response = await client.get("/decks/historic/Mono Red Aggro")

        assert response.status_code == 404
