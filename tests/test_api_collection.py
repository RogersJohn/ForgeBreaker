"""Tests for collection API endpoints."""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from forgebreaker.db.database import get_session
from forgebreaker.main import app
from forgebreaker.models.db import Base


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


class TestGetCollection:
    async def test_get_empty_collection(self, client: AsyncClient) -> None:
        """Returns empty collection for new user."""
        response = await client.get("/collection/new-user")

        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == "new-user"
        assert data["cards"] == {}
        assert data["total_cards"] == 0

    async def test_get_existing_collection(self, client: AsyncClient) -> None:
        """Returns collection with cards after update."""
        # First create a collection
        await client.put(
            "/collection/user-123",
            json={"cards": {"Lightning Bolt": 4, "Mountain": 20}},
        )

        response = await client.get("/collection/user-123")

        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == "user-123"
        assert data["cards"]["Lightning Bolt"] == 4
        assert data["cards"]["Mountain"] == 20
        assert data["total_cards"] == 24


class TestUpdateCollection:
    async def test_create_collection(self, client: AsyncClient) -> None:
        """Can create a new collection."""
        response = await client.put(
            "/collection/user-123",
            json={"cards": {"Lightning Bolt": 4, "Mountain": 20}},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == "user-123"
        assert data["cards"]["Lightning Bolt"] == 4
        assert data["total_cards"] == 24

    async def test_update_replaces_collection(self, client: AsyncClient) -> None:
        """Updating replaces entire collection."""
        await client.put(
            "/collection/user-123",
            json={"cards": {"Old Card": 2}},
        )

        response = await client.put(
            "/collection/user-123",
            json={"cards": {"New Card": 4}},
        )

        assert response.status_code == 200
        data = response.json()
        assert "Old Card" not in data["cards"]
        assert data["cards"]["New Card"] == 4
        assert data["total_cards"] == 4

    async def test_empty_cards_rejected(self, client: AsyncClient) -> None:
        """Empty cards dict is rejected."""
        response = await client.put(
            "/collection/user-123",
            json={"cards": {}},
        )

        assert response.status_code == 400
        assert "empty" in response.json()["detail"].lower()

    async def test_zero_quantity_rejected(self, client: AsyncClient) -> None:
        """Zero quantity cards are rejected."""
        response = await client.put(
            "/collection/user-123",
            json={"cards": {"Lightning Bolt": 0}},
        )

        assert response.status_code == 400
        assert "positive" in response.json()["detail"].lower()

    async def test_negative_quantity_rejected(self, client: AsyncClient) -> None:
        """Negative quantity cards are rejected."""
        response = await client.put(
            "/collection/user-123",
            json={"cards": {"Lightning Bolt": -1}},
        )

        assert response.status_code == 400
        assert "positive" in response.json()["detail"].lower()

    async def test_empty_card_name_rejected(self, client: AsyncClient) -> None:
        """Empty card names are rejected."""
        response = await client.put(
            "/collection/user-123",
            json={"cards": {"": 4}},
        )

        assert response.status_code == 400
        assert "empty" in response.json()["detail"].lower()

    async def test_whitespace_card_name_rejected(self, client: AsyncClient) -> None:
        """Whitespace-only card names are rejected."""
        response = await client.put(
            "/collection/user-123",
            json={"cards": {"   ": 4}},
        )

        assert response.status_code == 400
        assert "empty" in response.json()["detail"].lower()


class TestDeleteCollection:
    async def test_delete_existing_collection(self, client: AsyncClient) -> None:
        """Can delete an existing collection."""
        await client.put(
            "/collection/user-123",
            json={"cards": {"Lightning Bolt": 4}},
        )

        response = await client.delete("/collection/user-123")

        assert response.status_code == 200
        assert response.json()["deleted"] is True

        # Verify it's gone
        get_response = await client.get("/collection/user-123")
        assert get_response.json()["cards"] == {}

    async def test_delete_nonexistent_collection(self, client: AsyncClient) -> None:
        """Returns deleted=False for nonexistent collection."""
        response = await client.delete("/collection/nonexistent")

        assert response.status_code == 200
        assert response.json()["deleted"] is False
