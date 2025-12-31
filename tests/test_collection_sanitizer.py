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


@pytest.fixture
def mock_card_db_with_oracle() -> dict:
    """Mock card database with oracle_id for canonical resolution."""
    return {
        "Lightning Bolt": {
            "name": "Lightning Bolt",
            "oracle_id": "oracle-bolt-123",
            "rarity": "common",
            "type_line": "Instant",
            "colors": ["R"],
            "set": "sta",
            "legalities": {"standard": "not_legal", "historic": "legal"},
        },
        "Mountain": {
            "name": "Mountain",
            "oracle_id": "oracle-mountain-456",
            "rarity": "common",
            "type_line": "Basic Land — Mountain",
            "colors": [],
            "set": "dmu",
            "legalities": {"standard": "legal", "historic": "legal"},
        },
        "Counterspell": {
            "name": "Counterspell",
            "oracle_id": "oracle-counter-789",
            "rarity": "uncommon",
            "type_line": "Instant",
            "colors": ["U"],
            "set": "sta",
            "legalities": {"standard": "not_legal", "historic": "legal"},
        },
        "Tarmogoyf": {
            "name": "Tarmogoyf",
            "oracle_id": "oracle-goyf-101",
            "rarity": "mythic",
            "type_line": "Creature — Lhurgoyf",
            "colors": ["G"],
            "set": "mh2",
            "legalities": {"standard": "not_legal", "modern": "legal"},
        },
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
# INTEGRATION TESTS: IMPORT ENDPOINT (CANONICAL RESOLUTION)
# =============================================================================


class TestImportCanonicalResolution:
    """Integration tests for import-time canonical card resolution.

    BEHAVIOR CHANGE: Import now uses CanonicalCardResolver which:
    - Requires all cards to resolve successfully (terminal failure otherwise)
    - No longer sanitizes/removes invalid cards
    - SUMs counts across printings (not MAX)
    """

    async def test_import_succeeds_with_all_valid_cards(
        self, client: AsyncClient, mock_card_db_with_oracle: dict, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Import succeeds when all cards are in the database."""
        monkeypatch.setattr(
            "forgebreaker.api.collection.get_card_database",
            lambda: mock_card_db_with_oracle,
        )

        response = await client.post(
            "/collection/test-user/import",
            json={"text": "4 Lightning Bolt\n20 Mountain"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["cards"]["Lightning Bolt"] == 4
        assert data["cards"]["Mountain"] == 20
        assert data["sanitization"] is None  # No sanitization with canonical resolution

    async def test_import_fails_with_any_invalid_card(
        self, client: AsyncClient, mock_card_db_with_oracle: dict, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """
        BEHAVIOR CHANGE: Import fails if ANY card is not in the database.

        Old behavior: Invalid cards removed, valid cards imported.
        New behavior: Terminal failure, no partial import.
        """
        monkeypatch.setattr(
            "forgebreaker.api.collection.get_card_database",
            lambda: mock_card_db_with_oracle,
        )

        # Import with mix of valid and invalid cards
        response = await client.post(
            "/collection/test-user/import",
            json={"text": "4 Lightning Bolt\n2 Fake Card Alpha\n20 Mountain"},
        )

        # Should fail (terminal error)
        assert response.status_code == 400
        failure = response.json().get("failure", {})
        detail = failure.get("detail", "") or ""
        message = failure.get("message", "") or ""
        assert "could not be resolved" in message or "Fake Card Alpha" in detail

    async def test_import_all_invalid_rejected(
        self, client: AsyncClient, mock_card_db_with_oracle: dict, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Import rejected when ALL cards are invalid."""
        monkeypatch.setattr(
            "forgebreaker.api.collection.get_card_database",
            lambda: mock_card_db_with_oracle,
        )

        response = await client.post(
            "/collection/test-user/import",
            json={"text": "4 Fake Card\n2 Another Fake"},
        )

        assert response.status_code == 400


class TestCanonicalResolutionSumBehavior:
    """Tests verifying SUM behavior for multiple printings."""

    async def test_multiple_printings_sum_counts(
        self, client: AsyncClient, mock_card_db_with_oracle: dict, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """
        BEHAVIOR CHANGE: Multiple printings now SUM counts.

        Old: max(4, 3) = 4
        New: sum(4, 3) = 7
        """
        monkeypatch.setattr(
            "forgebreaker.api.collection.get_card_database",
            lambda: mock_card_db_with_oracle,
        )

        # Import same card with different set codes (Arena format)
        response = await client.post(
            "/collection/test-user/import",
            json={
                "text": "4 Lightning Bolt (STA) 123\n3 Lightning Bolt (DMU) 456",
                "format": "arena",
            },
        )

        assert response.status_code == 200
        data = response.json()

        # Should be SUM (7), not MAX (4)
        assert data["cards"]["Lightning Bolt"] == 7


# Legacy sanitization tests - these test the old behavior for the sanitize_collection
# function itself, which still exists but is no longer used by the import endpoint.
class TestImportSanitizationLegacy:
    """Legacy tests for sanitize_collection function (still exists but not used by import)."""

    async def test_sanitization_function_still_works(self, mock_card_db: dict) -> None:
        """The sanitize_collection function still works for other use cases."""
        cards = {"Lightning Bolt": 4, "Fake Card": 2}

        result = sanitize_collection(cards, mock_card_db)

        assert "Lightning Bolt" in result.sanitized_cards
        assert "Fake Card" not in result.sanitized_cards
        assert result.had_removals is True


class TestUserMessaging:
    """Tests for user-facing messaging behavior (now terminal failure messages)."""

    async def test_terminal_failure_on_invalid_cards(
        self, client: AsyncClient, mock_card_db_with_oracle: dict, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """
        BEHAVIOR CHANGE: Import with invalid cards is now a terminal failure.

        Old: Informational message, import continues.
        New: Terminal error, no partial import.
        """
        monkeypatch.setattr(
            "forgebreaker.api.collection.get_card_database",
            lambda: mock_card_db_with_oracle,
        )

        # Import with invalid cards - should fail
        response = await client.post(
            "/collection/test-user/import",
            json={"text": "4 Lightning Bolt\n2 Fake Card"},
        )

        # Terminal failure instead of sanitization message
        assert response.status_code == 400

    async def test_successful_import_no_sanitization_message(
        self, client: AsyncClient, mock_card_db_with_oracle: dict, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Successful import has no sanitization message (all cards valid)."""
        monkeypatch.setattr(
            "forgebreaker.api.collection.get_card_database",
            lambda: mock_card_db_with_oracle,
        )

        response = await client.post(
            "/collection/test-user/import",
            json={"text": "4 Lightning Bolt"},
        )

        assert response.status_code == 200
        assert response.json()["sanitization"] is None


class TestDeckBuildingRegression:
    """Regression tests for deck-building after canonical resolution."""

    async def test_deck_building_succeeds_after_import(
        self, client: AsyncClient, mock_card_db_with_oracle: dict, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """
        REQUIRED TEST 3: Regression test.

        After import:
        - Only valid cards are imported (invalid causes failure)
        - Deck-building request succeeds
        - No collection/DB mismatch error occurs
        """
        monkeypatch.setattr(
            "forgebreaker.api.collection.get_card_database",
            lambda: mock_card_db_with_oracle,
        )

        # Import collection with ONLY valid cards (invalid would cause failure)
        import_response = await client.post(
            "/collection/test-user/import",
            json={"text": "4 Lightning Bolt\n20 Mountain"},
        )

        assert import_response.status_code == 200
        assert import_response.json()["sanitization"] is None

        # Verify collection has all valid cards
        get_response = await client.get("/collection/test-user")
        cards = get_response.json()["cards"]
        assert "Lightning Bolt" in cards
        assert "Mountain" in cards

    async def test_imported_collection_subset_of_card_db(
        self, client: AsyncClient, mock_card_db_with_oracle: dict, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """
        INVARIANT: After import, collection_cards ⊆ card_database_cards.

        This is the core guarantee that prevents mismatch errors.
        With canonical resolution, this is enforced by terminal failure on invalid.
        """
        monkeypatch.setattr(
            "forgebreaker.api.collection.get_card_database",
            lambda: mock_card_db_with_oracle,
        )

        # Import only valid cards (required for success with canonical resolution)
        await client.post(
            "/collection/test-user/import",
            json={"text": "4 Lightning Bolt\n2 Counterspell\n20 Mountain"},
        )

        # Get persisted collection
        response = await client.get("/collection/test-user")
        collection_cards = set(response.json()["cards"].keys())
        card_db_cards = set(mock_card_db_with_oracle.keys())

        # INVARIANT: collection ⊆ card_db
        assert collection_cards.issubset(card_db_cards)


# =============================================================================
# LIFECYCLE TESTS: DELETE, REPLACE, AND NO-COLLECTION HANDLING
# =============================================================================


class TestDeleteCollection:
    """Tests for collection deletion functionality."""

    async def test_delete_collection_succeeds(
        self, client: AsyncClient, mock_card_db_with_oracle: dict, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """
        REQUIRED TEST: Delete collection capability.

        Assert:
        - Deletion returns success with user_id
        - Subsequent GET returns empty or demo data
        """
        monkeypatch.setattr(
            "forgebreaker.api.collection.get_card_database",
            lambda: mock_card_db_with_oracle,
        )

        # Create a collection
        await client.post(
            "/collection/test-user/import",
            json={"text": "4 Lightning Bolt"},
        )

        # Verify collection exists
        get_response = await client.get("/collection/test-user")
        assert get_response.json()["collection_source"] == "USER"

        # Delete collection
        delete_response = await client.delete("/collection/test-user")
        assert delete_response.status_code == 200
        data = delete_response.json()
        assert data["user_id"] == "test-user"
        assert data["deleted"] is True
        assert "message" in data

        # Subsequent GET should not return user collection
        get_after = await client.get("/collection/test-user")
        # Should either be empty or demo, not USER with Lightning Bolt
        assert get_after.json().get(
            "collection_source"
        ) != "USER" or "Lightning Bolt" not in get_after.json().get("cards", {})

    async def test_delete_nonexistent_collection(self, client: AsyncClient) -> None:
        """Delete of non-existent collection returns deleted=False."""
        response = await client.delete("/collection/nonexistent-user")
        assert response.status_code == 200
        data = response.json()
        assert data["deleted"] is False
        assert "message" in data

    async def test_delete_response_has_user_friendly_message(
        self, client: AsyncClient, mock_card_db_with_oracle: dict, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Delete response includes user-friendly message."""
        monkeypatch.setattr(
            "forgebreaker.api.collection.get_card_database",
            lambda: mock_card_db_with_oracle,
        )

        # Create and delete
        await client.post(
            "/collection/test-user/import",
            json={"text": "4 Lightning Bolt"},
        )
        response = await client.delete("/collection/test-user")

        message = response.json()["message"]
        assert "deleted" in message.lower()
        assert "import" in message.lower()  # Suggests re-import option


class TestExplicitImportMode:
    """Tests for explicit import_mode enforcement (Blocker 2)."""

    async def test_new_mode_rejects_existing_collection(
        self, client: AsyncClient, mock_card_db_with_oracle: dict, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """
        BLOCKER 2 TEST: import_mode='new' fails if collection exists.

        This prevents silent data loss - no implicit overwrite possible.
        """
        monkeypatch.setattr(
            "forgebreaker.api.collection.get_card_database",
            lambda: mock_card_db_with_oracle,
        )

        # Create initial collection
        await client.post(
            "/collection/test-user/import",
            json={"text": "4 Lightning Bolt"},
        )

        # Attempt second import with default mode (new)
        response = await client.post(
            "/collection/test-user/import",
            json={"text": "20 Mountain"},
        )

        assert response.status_code == 409  # CONFLICT
        assert "import_mode='replace'" in response.json()["detail"]

    async def test_replace_mode_deletes_then_imports(
        self, client: AsyncClient, mock_card_db_with_oracle: dict, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """
        BLOCKER 2 TEST: import_mode='replace' deletes existing first.

        Collection A exists, import B with replace -> A removed, B exists.
        """
        monkeypatch.setattr(
            "forgebreaker.api.collection.get_card_database",
            lambda: mock_card_db_with_oracle,
        )

        # Create initial collection A
        await client.post(
            "/collection/test-user/import",
            json={"text": "4 Lightning Bolt"},
        )

        # Replace with collection B
        response = await client.post(
            "/collection/test-user/import",
            json={"text": "20 Mountain", "import_mode": "replace"},
        )

        assert response.status_code == 200
        data = response.json()

        # Collection A removed, Collection B exists
        assert "Mountain" in data["cards"]
        assert data["cards"]["Mountain"] == 20
        assert "Lightning Bolt" not in data["cards"]
        assert data["replaced_existing"] is True

    async def test_first_import_new_mode_succeeds(
        self, client: AsyncClient, mock_card_db_with_oracle: dict, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """First import with mode='new' succeeds when no collection exists."""
        monkeypatch.setattr(
            "forgebreaker.api.collection.get_card_database",
            lambda: mock_card_db_with_oracle,
        )

        # First import - should succeed with default mode
        response = await client.post(
            "/collection/first-time-user/import",
            json={"text": "4 Lightning Bolt"},
        )

        assert response.status_code == 200
        assert response.json()["replaced_existing"] is False

    async def test_no_silent_overwrite_possible(
        self, client: AsyncClient, mock_card_db_with_oracle: dict, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """
        INVARIANT: No silent data loss.

        There must be no code path where a collection exists and
        import silently overwrites it.
        """
        monkeypatch.setattr(
            "forgebreaker.api.collection.get_card_database",
            lambda: mock_card_db_with_oracle,
        )

        # Create collection with Lightning Bolt
        await client.post(
            "/collection/test-user/import",
            json={"text": "4 Lightning Bolt"},
        )

        # Verify Lightning Bolt exists
        get_a = await client.get("/collection/test-user")
        assert "Lightning Bolt" in get_a.json()["cards"]

        # Try to import Mountain without explicit replace - must fail
        response = await client.post(
            "/collection/test-user/import",
            json={"text": "4 Mountain", "import_mode": "new"},
        )
        assert response.status_code == 409

        # Collection with Lightning Bolt still intact
        get_after = await client.get("/collection/test-user")
        assert "Lightning Bolt" in get_after.json()["cards"]
        assert "Mountain" not in get_after.json()["cards"]


class TestImportAfterDelete:
    """Tests for import after delete lifecycle."""

    async def test_import_after_delete_succeeds(
        self, client: AsyncClient, mock_card_db_with_oracle: dict, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Import succeeds with mode='new' after collection is deleted."""
        monkeypatch.setattr(
            "forgebreaker.api.collection.get_card_database",
            lambda: mock_card_db_with_oracle,
        )

        # Create collection
        await client.post(
            "/collection/test-user/import",
            json={"text": "4 Lightning Bolt"},
        )

        # Delete collection
        await client.delete("/collection/test-user")

        # Import again with mode='new' - should succeed
        response = await client.post(
            "/collection/test-user/import",
            json={"text": "20 Mountain"},
        )

        assert response.status_code == 200
        assert response.json()["cards"]["Mountain"] == 20


class TestNoCollectionGuardAllTools:
    """Tests for Blocker 3: No-collection guard across all tools."""

    async def test_build_deck_raises_known_error_when_no_collection(
        self,
    ) -> None:
        """
        BLOCKER 3 TEST: build_deck fails terminally when no collection.
        """
        import pytest
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

        from forgebreaker.mcp.tools import build_deck_tool
        from forgebreaker.models.db import Base
        from forgebreaker.models.failure import FailureKind, KnownError

        engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        async with async_session() as session:
            with pytest.raises(KnownError) as exc_info:
                await build_deck_tool(
                    session=session,
                    user_id="user-without-collection",
                    theme="dragons",
                    card_db={},
                    format_legality={},
                )

            error = exc_info.value
            assert error.kind == FailureKind.NOT_FOUND
            assert "collection" in error.message.lower()
            assert "import" in error.message.lower()

        await engine.dispose()

    async def test_search_collection_raises_known_error_when_no_collection(
        self,
    ) -> None:
        """
        BLOCKER 3 TEST: search_collection fails terminally when no collection.
        """
        import pytest
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

        from forgebreaker.mcp.tools import search_collection_tool
        from forgebreaker.models.db import Base
        from forgebreaker.models.failure import FailureKind, KnownError

        engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        async with async_session() as session:
            with pytest.raises(KnownError) as exc_info:
                await search_collection_tool(
                    session=session,
                    user_id="user-without-collection",
                    card_db={},
                )

            error = exc_info.value
            assert error.kind == FailureKind.NOT_FOUND
            assert "collection" in error.message.lower()

        await engine.dispose()

    async def test_find_synergies_raises_known_error_when_no_collection(
        self,
    ) -> None:
        """
        BLOCKER 3 TEST: find_synergies fails terminally when no collection.
        """
        import pytest
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

        from forgebreaker.mcp.tools import find_synergies_tool
        from forgebreaker.models.db import Base
        from forgebreaker.models.failure import FailureKind, KnownError

        engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        async with async_session() as session:
            with pytest.raises(KnownError) as exc_info:
                await find_synergies_tool(
                    session=session,
                    user_id="user-without-collection",
                    card_name="Lightning Bolt",
                    card_db={},
                )

            error = exc_info.value
            assert error.kind == FailureKind.NOT_FOUND
            assert "collection" in error.message.lower()

        await engine.dispose()

    async def test_improve_deck_raises_known_error_when_no_collection(
        self,
    ) -> None:
        """
        BLOCKER 3 TEST: improve_deck fails terminally when no collection.
        """
        import pytest
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

        from forgebreaker.mcp.tools import improve_deck_tool
        from forgebreaker.models.db import Base
        from forgebreaker.models.failure import FailureKind, KnownError

        engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        async with async_session() as session:
            with pytest.raises(KnownError) as exc_info:
                await improve_deck_tool(
                    session=session,
                    user_id="user-without-collection",
                    deck_text="4 Lightning Bolt",
                    card_db={},
                )

            error = exc_info.value
            assert error.kind == FailureKind.NOT_FOUND
            assert "collection" in error.message.lower()

        await engine.dispose()

    async def test_no_collection_guard_is_terminal(
        self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """
        BLOCKER 3 ACCEPTANCE: Delete collection, attempt deck build, immediate failure.

        The guard must run before any tool execution results in additional work.
        """
        import pytest
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

        from forgebreaker.mcp.tools import build_deck_tool
        from forgebreaker.models.db import Base
        from forgebreaker.models.failure import KnownError

        mock_db = {"Lightning Bolt": {"name": "Lightning Bolt"}}
        monkeypatch.setattr(
            "forgebreaker.services.card_database.get_card_database",
            lambda: mock_db,
        )

        # Create a collection
        await client.post(
            "/collection/test-user/import",
            json={"text": "4 Lightning Bolt"},
        )

        # Delete the collection
        await client.delete("/collection/test-user")

        # Attempt deck-building - must fail terminally
        engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        async with async_session() as session:
            with pytest.raises(KnownError) as exc_info:
                await build_deck_tool(
                    session=session,
                    user_id="test-user",
                    theme="burn",
                    card_db=mock_db,
                    format_legality={},
                )

            error = exc_info.value
            assert "collection" in error.message.lower()
            assert "import" in error.message.lower()

        await engine.dispose()
