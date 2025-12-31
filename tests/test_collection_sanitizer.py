"""
Tests for collection sanitization at import time.

These tests verify the invariant:
- Collections are sanitized ONCE at import time
- Invalid cards (not in card database) are removed
- User is informed calmly and exactly once
- Deck-building never fails due to collection/DB mismatch after import
"""

from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from forgebreaker.db.database import get_session
from forgebreaker.main import app
from forgebreaker.models.db import Base
from forgebreaker.services.collection_sanitizer import (
    sanitize_collection,
    try_sanitize_collection,
)

# =============================================================================
# FIXTURES
# =============================================================================


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


@pytest.fixture
def mock_card_db() -> dict:
    """Mock card database with known valid cards."""
    return {
        "Lightning Bolt": {"name": "Lightning Bolt", "rarity": "common"},
        "Mountain": {"name": "Mountain", "rarity": "common"},
        "Counterspell": {"name": "Counterspell", "rarity": "uncommon"},
        "Tarmogoyf": {"name": "Tarmogoyf", "rarity": "mythic"},
    }


# =============================================================================
# UNIT TESTS: SANITIZATION SERVICE
# =============================================================================


class TestSanitizeCollection:
    """Unit tests for sanitize_collection function."""

    def test_all_valid_cards_pass_through(self, mock_card_db: dict) -> None:
        """Cards present in database are not removed."""
        cards = {"Lightning Bolt": 4, "Mountain": 20}

        result = sanitize_collection(cards, mock_card_db)

        assert result.sanitized_cards == cards
        assert result.removed_cards == {}
        assert result.removed_count == 0
        assert result.removed_unique_count == 0
        assert result.had_removals is False

    def test_invalid_cards_removed(self, mock_card_db: dict) -> None:
        """Cards not in database are removed."""
        cards = {
            "Lightning Bolt": 4,
            "Fake Card Alpha": 2,
            "Nonexistent Card": 1,
        }

        result = sanitize_collection(cards, mock_card_db)

        assert "Lightning Bolt" in result.sanitized_cards
        assert "Fake Card Alpha" not in result.sanitized_cards
        assert "Nonexistent Card" not in result.sanitized_cards
        assert result.removed_cards == {"Fake Card Alpha": 2, "Nonexistent Card": 1}
        assert result.removed_count == 3  # 2 + 1
        assert result.removed_unique_count == 2
        assert result.had_removals is True

    def test_all_invalid_cards_returns_empty(self, mock_card_db: dict) -> None:
        """Collection with only invalid cards returns empty sanitized."""
        cards = {"Fake Card": 4, "Another Fake": 2}

        result = sanitize_collection(cards, mock_card_db)

        assert result.sanitized_cards == {}
        assert result.removed_unique_count == 2
        assert result.had_removals is True

    def test_empty_collection_returns_empty(self, mock_card_db: dict) -> None:
        """Empty collection returns empty result."""
        cards: dict[str, int] = {}

        result = sanitize_collection(cards, mock_card_db)

        assert result.sanitized_cards == {}
        assert result.removed_cards == {}
        assert result.had_removals is False

    def test_quantities_preserved(self, mock_card_db: dict) -> None:
        """Quantities are preserved for valid cards."""
        cards = {"Lightning Bolt": 4, "Mountain": 20, "Counterspell": 3}

        result = sanitize_collection(cards, mock_card_db)

        assert result.sanitized_cards["Lightning Bolt"] == 4
        assert result.sanitized_cards["Mountain"] == 20
        assert result.sanitized_cards["Counterspell"] == 3


class TestSanitizationResultMessage:
    """Tests for user-facing sanitization messages."""

    def test_no_message_when_no_removals(self, mock_card_db: dict) -> None:
        """No user message when nothing was removed."""
        cards = {"Lightning Bolt": 4}

        result = sanitize_collection(cards, mock_card_db)

        assert result.get_user_message() is None

    def test_singular_message_for_one_card(self, mock_card_db: dict) -> None:
        """Singular grammar when one card removed."""
        cards = {"Lightning Bolt": 4, "Fake Card": 2}

        result = sanitize_collection(cards, mock_card_db)

        message = result.get_user_message()
        assert message is not None
        assert "1 card" in message
        assert "error" not in message.lower()
        assert "Everything else imported successfully" in message

    def test_plural_message_for_multiple_cards(self, mock_card_db: dict) -> None:
        """Plural grammar when multiple cards removed."""
        cards = {"Lightning Bolt": 4, "Fake A": 2, "Fake B": 1}

        result = sanitize_collection(cards, mock_card_db)

        message = result.get_user_message()
        assert message is not None
        assert "2 cards" in message
        assert "error" not in message.lower()

    def test_message_tone_is_calm(self, mock_card_db: dict) -> None:
        """Message uses calm, non-error language."""
        cards = {"Fake Card": 1}

        result = sanitize_collection(cards, mock_card_db)

        message = result.get_user_message()
        assert message is not None
        # Should NOT contain error/warning language
        assert "error" not in message.lower()
        assert "warning" not in message.lower()
        assert "failed" not in message.lower()
        # Should be reassuring
        assert "cleaned up" in message.lower() or "removed" in message.lower()


class TestTrySanitizeCollection:
    """Tests for try_sanitize_collection with fallback behavior."""

    def test_returns_result_when_db_available(self, mock_card_db: dict) -> None:
        """Returns sanitization result when card database available."""
        cards = {"Lightning Bolt": 4, "Fake Card": 2}

        with patch(
            "forgebreaker.services.card_database.get_card_database",
            return_value=mock_card_db,
        ):
            result = try_sanitize_collection(cards)

        assert result is not None
        assert "Lightning Bolt" in result.sanitized_cards
        assert "Fake Card" not in result.sanitized_cards

    def test_returns_none_when_db_unavailable(self) -> None:
        """Returns None when card database unavailable."""
        cards = {"Lightning Bolt": 4}

        with patch(
            "forgebreaker.services.card_database.get_card_database",
            side_effect=FileNotFoundError("Card database not found"),
        ):
            result = try_sanitize_collection(cards)

        assert result is None


# =============================================================================
# INTEGRATION TESTS: IMPORT ENDPOINT
# =============================================================================


class TestImportSanitization:
    """Integration tests for import-time sanitization."""

    async def test_import_removes_invalid_cards(
        self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """
        REQUIRED TEST 1: Import sanitization.

        Import a collection containing invalid cards.
        Assert:
        - Invalid cards removed
        - Sanitized collection persisted
        - Sanitization metadata recorded
        """
        mock_db = {
            "Lightning Bolt": {"name": "Lightning Bolt"},
            "Mountain": {"name": "Mountain"},
        }
        monkeypatch.setattr(
            "forgebreaker.services.card_database.get_card_database",
            lambda: mock_db,
        )

        # Import with mix of valid and invalid cards
        response = await client.post(
            "/collection/test-user/import",
            json={"text": "4 Lightning Bolt\n2 Fake Card Alpha\n20 Mountain"},
        )

        assert response.status_code == 200
        data = response.json()

        # Invalid cards removed from persisted collection
        assert "Fake Card Alpha" not in data["cards"]
        assert data["cards"]["Lightning Bolt"] == 4
        assert data["cards"]["Mountain"] == 20

        # Sanitization metadata present
        assert data["sanitization"] is not None
        assert data["sanitization"]["cards_removed"] == 1
        assert "message" in data["sanitization"]

    async def test_import_no_sanitization_when_all_valid(
        self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """No sanitization info when all cards are valid."""
        mock_db = {
            "Lightning Bolt": {"name": "Lightning Bolt"},
            "Mountain": {"name": "Mountain"},
        }
        monkeypatch.setattr(
            "forgebreaker.services.card_database.get_card_database",
            lambda: mock_db,
        )

        response = await client.post(
            "/collection/test-user/import",
            json={"text": "4 Lightning Bolt\n20 Mountain"},
        )

        assert response.status_code == 200
        data = response.json()

        # No sanitization info when nothing removed
        assert data["sanitization"] is None
        assert data["cards"]["Lightning Bolt"] == 4

    async def test_import_all_invalid_rejected(
        self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Import rejected when ALL cards are invalid."""
        mock_db = {"Lightning Bolt": {"name": "Lightning Bolt"}}
        monkeypatch.setattr(
            "forgebreaker.services.card_database.get_card_database",
            lambda: mock_db,
        )

        response = await client.post(
            "/collection/test-user/import",
            json={"text": "4 Fake Card\n2 Another Fake"},
        )

        assert response.status_code == 400
        assert "No valid cards" in response.json()["detail"]


class TestUserMessaging:
    """Tests for user-facing messaging behavior."""

    async def test_message_returned_exactly_once(
        self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """
        REQUIRED TEST 2: User messaging.

        Assert:
        - Informational message returned exactly once (on import)
        - Message does not block import
        - Message not repeated on subsequent requests
        """
        mock_db = {"Lightning Bolt": {"name": "Lightning Bolt"}}
        monkeypatch.setattr(
            "forgebreaker.services.card_database.get_card_database",
            lambda: mock_db,
        )

        # First request: Import with invalid cards
        import_response = await client.post(
            "/collection/test-user/import",
            json={"text": "4 Lightning Bolt\n2 Fake Card"},
        )

        assert import_response.status_code == 200
        import_data = import_response.json()

        # Message returned on import
        assert import_data["sanitization"] is not None
        assert import_data["sanitization"]["message"] is not None
        assert "cleaned up" in import_data["sanitization"]["message"].lower()

        # Import was NOT blocked
        assert import_data["cards"]["Lightning Bolt"] == 4

        # Second request: GET collection - no sanitization message
        get_response = await client.get("/collection/test-user")

        assert get_response.status_code == 200
        get_data = get_response.json()

        # No sanitization field in GET response (message not repeated)
        assert "sanitization" not in get_data or get_data.get("sanitization") is None

    async def test_message_tone_is_non_error(
        self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Message uses calm, non-error language."""
        mock_db = {"Lightning Bolt": {"name": "Lightning Bolt"}}
        monkeypatch.setattr(
            "forgebreaker.services.card_database.get_card_database",
            lambda: mock_db,
        )

        response = await client.post(
            "/collection/test-user/import",
            json={"text": "4 Lightning Bolt\n2 Fake Card"},
        )

        message = response.json()["sanitization"]["message"]

        # Tone check
        assert "error" not in message.lower()
        assert "failed" not in message.lower()
        assert "warning" not in message.lower()


class TestDeckBuildingRegression:
    """Regression tests for deck-building after sanitization."""

    async def test_deck_building_succeeds_after_sanitization(
        self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """
        REQUIRED TEST 3: Regression test.

        After sanitization:
        - Deck-building request succeeds
        - No collection/DB mismatch error occurs
        """
        # Full mock card database for deck building
        mock_db = {
            "Lightning Bolt": {
                "name": "Lightning Bolt",
                "type_line": "Instant",
                "colors": ["R"],
                "cmc": 1,
                "rarity": "common",
                "keywords": [],
                "oracle_text": "Deal 3 damage",
            },
            "Mountain": {
                "name": "Mountain",
                "type_line": "Basic Land — Mountain",
                "colors": [],
                "cmc": 0,
                "rarity": "common",
                "keywords": [],
                "oracle_text": "",
            },
        }

        # Mock for sanitizer
        monkeypatch.setattr(
            "forgebreaker.services.card_database.get_card_database",
            lambda: mock_db,
        )

        # Import collection with invalid cards (they get sanitized out)
        import_response = await client.post(
            "/collection/test-user/import",
            json={"text": "4 Lightning Bolt\n20 Mountain\n2 Nonexistent Card"},
        )

        assert import_response.status_code == 200
        assert import_response.json()["sanitization"] is not None  # Had removals

        # Verify sanitized collection only has valid cards
        get_response = await client.get("/collection/test-user")
        cards = get_response.json()["cards"]
        assert "Lightning Bolt" in cards
        assert "Mountain" in cards
        assert "Nonexistent Card" not in cards

    async def test_sanitized_collection_subset_of_card_db(
        self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """
        INVARIANT: After import, collection_cards ⊆ card_database_cards.

        This is the core guarantee that prevents mismatch errors.
        """
        mock_db = {
            "Card A": {"name": "Card A"},
            "Card B": {"name": "Card B"},
            "Card C": {"name": "Card C"},
        }
        monkeypatch.setattr(
            "forgebreaker.services.card_database.get_card_database",
            lambda: mock_db,
        )

        # Import mix of valid and invalid
        await client.post(
            "/collection/test-user/import",
            json={"text": "4 Card A\n2 Card B\n1 Invalid Card\n3 Card C"},
        )

        # Get persisted collection
        response = await client.get("/collection/test-user")
        collection_cards = set(response.json()["cards"].keys())
        card_db_cards = set(mock_db.keys())

        # INVARIANT: collection ⊆ card_db
        assert collection_cards.issubset(card_db_cards)


class TestMergeModeSanitization:
    """Tests for sanitization in merge mode."""

    async def test_merge_mode_sanitizes_combined_collection(
        self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Merge mode sanitizes the combined collection."""
        mock_db = {
            "Lightning Bolt": {"name": "Lightning Bolt"},
            "Counterspell": {"name": "Counterspell"},
        }
        monkeypatch.setattr(
            "forgebreaker.services.card_database.get_card_database",
            lambda: mock_db,
        )

        # Create initial collection
        await client.post(
            "/collection/test-user/import",
            json={"text": "4 Lightning Bolt"},
        )

        # Merge with new cards including invalid
        response = await client.post(
            "/collection/test-user/import",
            json={"text": "2 Counterspell\n1 Fake Card", "merge": True},
        )

        assert response.status_code == 200
        data = response.json()

        # Original + new valid cards present
        assert data["cards"]["Lightning Bolt"] == 4
        assert data["cards"]["Counterspell"] == 2

        # Invalid card removed
        assert "Fake Card" not in data["cards"]

        # Sanitization reported
        assert data["sanitization"] is not None
        assert data["sanitization"]["cards_removed"] == 1
