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
    async def test_get_empty_collection(
        self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Returns empty collection for new user when demo not available."""
        # Disable demo mode for this test to verify empty behavior
        monkeypatch.setattr("forgebreaker.api.collection.demo_collection_available", lambda: False)

        response = await client.get("/collection/new-user")

        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == "new-user"
        assert data["cards"] == {}
        assert data["total_cards"] == 0
        assert data["collection_source"] == "USER"

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
    async def test_delete_existing_collection(
        self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Can delete an existing collection."""
        # Disable demo mode to verify empty collection after delete
        monkeypatch.setattr("forgebreaker.api.collection.demo_collection_available", lambda: False)

        await client.put(
            "/collection/user-123",
            json={"cards": {"Lightning Bolt": 4}},
        )

        response = await client.delete("/collection/user-123")

        assert response.status_code == 200
        assert response.json()["deleted"] is True

        # Verify it's gone (empty without demo mode)
        get_response = await client.get("/collection/user-123")
        assert get_response.json()["cards"] == {}

    async def test_delete_nonexistent_collection(self, client: AsyncClient) -> None:
        """Returns deleted=False for nonexistent collection."""
        response = await client.delete("/collection/nonexistent")

        assert response.status_code == 200
        assert response.json()["deleted"] is False


class TestImportCollection:
    async def test_import_simple_format(self, client: AsyncClient) -> None:
        """Can import collection from simple text format."""
        response = await client.post(
            "/collection/user-123/import",
            json={"text": "4 Lightning Bolt\n20 Mountain"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == "user-123"
        assert data["cards_imported"] == 2
        assert data["cards"]["Lightning Bolt"] == 4
        assert data["cards"]["Mountain"] == 20

    async def test_import_empty_text_rejected(self, client: AsyncClient) -> None:
        """Empty import text is rejected."""
        response = await client.post(
            "/collection/user-123/import",
            json={"text": ""},
        )

        assert response.status_code == 400
        assert "empty" in response.json()["detail"].lower()

    async def test_import_merge_mode(self, client: AsyncClient) -> None:
        """Merge mode keeps max quantity from both sources."""
        # Create initial collection
        await client.put(
            "/collection/user-123",
            json={"cards": {"Lightning Bolt": 4, "Mountain": 10}},
        )

        # Import with merge (Mountain 20 > 10, but Lightning Bolt 2 < 4)
        response = await client.post(
            "/collection/user-123/import",
            json={"text": "2 Lightning Bolt\n20 Mountain", "merge": True},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["cards"]["Lightning Bolt"] == 4  # Kept existing (4 > 2)
        assert data["cards"]["Mountain"] == 20  # Used import (20 > 10)


class TestCollectionStats:
    async def test_stats_empty_collection(
        self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Returns empty stats for nonexistent collection when demo not available."""
        # Disable demo mode to verify empty stats behavior
        monkeypatch.setattr("forgebreaker.api.collection.demo_collection_available", lambda: False)

        response = await client.get("/collection/new-user/stats")

        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == "new-user"
        assert data["total_cards"] == 0
        assert data["unique_cards"] == 0
        assert data["collection_source"] == "USER"

    async def test_stats_basic_counts(self, client: AsyncClient) -> None:
        """Returns basic counts even without card database."""
        # Create a collection
        await client.put(
            "/collection/user-123",
            json={"cards": {"Lightning Bolt": 4, "Mountain": 20}},
        )

        response = await client.get("/collection/user-123/stats")

        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == "user-123"
        assert data["total_cards"] == 24
        assert data["unique_cards"] == 2

    async def test_stats_with_mock_card_db(
        self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Returns rarity/color/type breakdowns with mocked card database."""
        # Mock card database
        mock_db = {
            "Lightning Bolt": {
                "name": "Lightning Bolt",
                "rarity": "common",
                "colors": ["R"],
                "type_line": "Instant",
            },
            "Counterspell": {
                "name": "Counterspell",
                "rarity": "uncommon",
                "colors": ["U"],
                "type_line": "Instant",
            },
            "Tarmogoyf": {
                "name": "Tarmogoyf",
                "rarity": "mythic",
                "colors": ["G"],
                "type_line": "Creature — Lhurgoyf",
            },
        }

        monkeypatch.setattr("forgebreaker.api.collection.get_card_database", lambda: mock_db)

        # Create a collection
        await client.put(
            "/collection/user-123",
            json={
                "cards": {
                    "Lightning Bolt": 4,
                    "Counterspell": 2,
                    "Tarmogoyf": 1,
                }
            },
        )

        response = await client.get("/collection/user-123/stats")

        assert response.status_code == 200
        data = response.json()

        # Check rarity breakdown
        assert data["by_rarity"]["common"] == 4  # 4 Lightning Bolt
        assert data["by_rarity"]["uncommon"] == 2  # 2 Counterspell
        assert data["by_rarity"]["mythic"] == 1  # 1 Tarmogoyf

        # Check color breakdown
        assert data["by_color"]["R"] == 4  # 4 Lightning Bolt
        assert data["by_color"]["U"] == 2  # 2 Counterspell
        assert data["by_color"]["G"] == 1  # 1 Tarmogoyf

        # Check type breakdown
        assert data["by_type"]["Instant"] == 6  # 4 + 2
        assert data["by_type"]["Creature"] == 1  # 1 Tarmogoyf

    async def test_stats_multicolor_cards(
        self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Multicolor cards are counted correctly."""
        mock_db = {
            "Niv-Mizzet, Parun": {
                "name": "Niv-Mizzet, Parun",
                "rarity": "rare",
                "colors": ["U", "R"],
                "type_line": "Legendary Creature — Dragon Wizard",
            },
        }

        monkeypatch.setattr("forgebreaker.api.collection.get_card_database", lambda: mock_db)

        await client.put(
            "/collection/user-123",
            json={"cards": {"Niv-Mizzet, Parun": 2}},
        )

        response = await client.get("/collection/user-123/stats")

        data = response.json()
        assert data["by_color"]["multicolor"] == 2

    async def test_stats_colorless_cards(
        self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Colorless cards are counted correctly."""
        mock_db = {
            "Sol Ring": {
                "name": "Sol Ring",
                "rarity": "uncommon",
                "colors": [],
                "type_line": "Artifact",
            },
        }

        monkeypatch.setattr("forgebreaker.api.collection.get_card_database", lambda: mock_db)

        await client.put(
            "/collection/user-123",
            json={"cards": {"Sol Ring": 4}},
        )

        response = await client.get("/collection/user-123/stats")

        data = response.json()
        assert data["by_color"]["colorless"] == 4
        assert data["by_type"]["Artifact"] == 4

    async def test_stats_nonstandard_rarity(
        self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Non-standard rarities (special, bonus) are counted as other."""
        mock_db = {
            "Black Lotus": {
                "name": "Black Lotus",
                "rarity": "special",
                "colors": [],
                "type_line": "Artifact",
            },
        }

        monkeypatch.setattr("forgebreaker.api.collection.get_card_database", lambda: mock_db)

        await client.put(
            "/collection/user-123",
            json={"cards": {"Black Lotus": 1}},
        )

        response = await client.get("/collection/user-123/stats")

        data = response.json()
        assert data["by_rarity"]["other"] == 1
        assert data["by_rarity"]["common"] == 0


class TestDemoModeBoundary:
    """
    Tests for demo mode boundary protection.

    These tests verify that:
    - Users with no collection see demo data with collection_source="DEMO"
    - Users who import get collection_source="USER"
    - Demo data is fully replaced when user imports their own
    """

    async def test_empty_user_gets_demo_collection(
        self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """New user gets demo collection with DEMO source."""
        # Mock demo collection to be available
        demo_cards = {"Demo Card A": 2, "Demo Card B": 1}

        def mock_demo_available() -> bool:
            return True

        def mock_get_demo():
            from forgebreaker.models.collection import Collection

            return Collection(cards=demo_cards.copy())

        monkeypatch.setattr(
            "forgebreaker.api.collection.demo_collection_available", mock_demo_available
        )
        monkeypatch.setattr("forgebreaker.api.collection.get_demo_collection", mock_get_demo)

        response = await client.get("/collection/new-user")

        assert response.status_code == 200
        data = response.json()
        assert data["collection_source"] == "DEMO"
        assert data["cards"]["Demo Card A"] == 2
        assert data["cards"]["Demo Card B"] == 1
        assert data["total_cards"] == 3

    async def test_import_switches_to_user_source(
        self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Importing collection switches source to USER."""
        # Mock demo collection
        demo_cards = {"Demo Card": 4}

        def mock_demo_available() -> bool:
            return True

        def mock_get_demo():
            from forgebreaker.models.collection import Collection

            return Collection(cards=demo_cards.copy())

        monkeypatch.setattr(
            "forgebreaker.api.collection.demo_collection_available", mock_demo_available
        )
        monkeypatch.setattr("forgebreaker.api.collection.get_demo_collection", mock_get_demo)

        # First verify user gets demo data
        response = await client.get("/collection/test-user")
        assert response.json()["collection_source"] == "DEMO"

        # Now import user's own collection
        import_response = await client.post(
            "/collection/test-user/import",
            json={"text": "4 Lightning Bolt\n4 Mountain"},
        )

        assert import_response.status_code == 200
        import_data = import_response.json()
        assert import_data["collection_source"] == "USER"

        # Verify subsequent GET also returns USER source
        get_response = await client.get("/collection/test-user")
        get_data = get_response.json()
        assert get_data["collection_source"] == "USER"
        assert "Demo Card" not in get_data["cards"]
        assert get_data["cards"]["Lightning Bolt"] == 4

    async def test_user_collection_returns_user_source(self, client: AsyncClient) -> None:
        """User with existing collection gets USER source."""
        # Create user collection directly
        await client.put(
            "/collection/user-with-data",
            json={"cards": {"User Card": 3}},
        )

        response = await client.get("/collection/user-with-data")

        assert response.status_code == 200
        data = response.json()
        assert data["collection_source"] == "USER"
        assert data["cards"]["User Card"] == 3

    async def test_demo_stats_returns_demo_source(
        self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Stats for demo collection returns DEMO source."""
        demo_cards = {"Demo Card": 2}

        def mock_demo_available() -> bool:
            return True

        def mock_get_demo():
            from forgebreaker.models.collection import Collection

            return Collection(cards=demo_cards.copy())

        monkeypatch.setattr(
            "forgebreaker.api.collection.demo_collection_available", mock_demo_available
        )
        monkeypatch.setattr("forgebreaker.api.collection.get_demo_collection", mock_get_demo)

        response = await client.get("/collection/new-user/stats")

        assert response.status_code == 200
        data = response.json()
        assert data["collection_source"] == "DEMO"
        assert data["total_cards"] == 2

    async def test_user_stats_returns_user_source(self, client: AsyncClient) -> None:
        """Stats for user collection returns USER source."""
        await client.put(
            "/collection/user-123",
            json={"cards": {"User Card": 5}},
        )

        response = await client.get("/collection/user-123/stats")

        assert response.status_code == 200
        data = response.json()
        assert data["collection_source"] == "USER"
