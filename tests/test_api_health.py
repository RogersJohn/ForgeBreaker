"""Tests for health check endpoints."""

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


class TestHealthEndpoint:
    async def test_health_returns_healthy(self, client: AsyncClient) -> None:
        """Liveness probe returns healthy."""
        response = await client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"

    async def test_health_no_db_check(self, client: AsyncClient) -> None:
        """Health endpoint does not include database status."""
        response = await client.get("/health")

        data = response.json()
        assert data.get("database") is None


class TestReadyEndpoint:
    async def test_ready_returns_ready(self, client: AsyncClient) -> None:
        """Readiness probe returns ready when DB is connected."""
        response = await client.get("/ready")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ready"
        assert data["database"] == "connected"

    async def test_ready_checks_database(self, client: AsyncClient) -> None:
        """Ready endpoint verifies database connectivity."""
        response = await client.get("/ready")

        data = response.json()
        assert "database" in data

    async def test_ready_returns_503_on_db_failure(self) -> None:
        """Readiness probe returns 503 when DB is unavailable."""
        from unittest.mock import AsyncMock

        async def override_get_session_broken():
            mock_session = AsyncMock()
            mock_session.execute.side_effect = Exception("Database connection failed")
            yield mock_session

        app.dependency_overrides[get_session] = override_get_session_broken

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/ready")

        app.dependency_overrides.clear()

        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "not ready"
        assert data["database"] == "disconnected"
