"""Tests for sample deck functionality."""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from forgebreaker.db.database import get_session
from forgebreaker.main import app
from forgebreaker.models.db import Base
from forgebreaker.services.sample_deck import SAMPLE_DECK, get_sample_deck


class TestSampleDeckDefinition:
    """Tests for the sample deck definition."""

    def test_sample_deck_is_60_cards(self) -> None:
        """Sample deck should be a valid 60-card deck."""
        total = sum(SAMPLE_DECK.cards.values())
        assert total == 60, f"Expected 60 cards, got {total}"

    def test_sample_deck_is_standard_format(self) -> None:
        """Sample deck should be in standard format."""
        assert SAMPLE_DECK.format == "standard"

    def test_sample_deck_has_archetype(self) -> None:
        """Sample deck should have an archetype."""
        assert SAMPLE_DECK.archetype is not None

    def test_get_sample_deck_returns_copy(self) -> None:
        """get_sample_deck() should return a copy, not the original."""
        deck1 = get_sample_deck()
        deck2 = get_sample_deck()

        # Should be equal in content
        assert deck1.name == deck2.name
        assert deck1.cards == deck2.cards

        # But cards dict should be different objects
        assert deck1.cards is not deck2.cards


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


class TestSampleDeckAPI:
    """Tests for the sample deck API endpoint."""

    async def test_create_sample_deck_returns_deck(self, client: AsyncClient) -> None:
        """POST /decks/sample should return the sample deck."""
        response = await client.post("/decks/sample")

        assert response.status_code == 200
        deck = response.json()

        # Deck should match sample deck
        assert deck["name"] == SAMPLE_DECK.name
        assert deck["archetype"] == SAMPLE_DECK.archetype
        assert deck["format"] == SAMPLE_DECK.format
        assert deck["cards"] == SAMPLE_DECK.cards

    async def test_create_sample_deck_persists_to_database(self, client: AsyncClient) -> None:
        """POST /decks/sample should save deck to database."""
        # Create the sample deck
        await client.post("/decks/sample")

        # Fetch it back via the decks API
        response = await client.get(f"/decks/{SAMPLE_DECK.format}/{SAMPLE_DECK.name}")

        assert response.status_code == 200
        deck = response.json()
        assert deck["name"] == SAMPLE_DECK.name

    async def test_create_sample_deck_is_idempotent(self, client: AsyncClient) -> None:
        """Calling POST /decks/sample multiple times should not create duplicates."""
        # Create twice
        response1 = await client.post("/decks/sample")
        response2 = await client.post("/decks/sample")

        # Both should succeed
        assert response1.status_code == 200
        assert response2.status_code == 200

        # Should return the same deck
        assert response1.json() == response2.json()
