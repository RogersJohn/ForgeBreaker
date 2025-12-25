"""Tests for MCP tool definitions."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from forgebreaker.db import update_collection_cards, upsert_meta_deck
from forgebreaker.mcp.tools import (
    TOOL_DEFINITIONS,
    calculate_deck_distance_tool,
    execute_tool,
    get_collection_stats,
    get_deck_recommendations,
    list_meta_decks,
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
async def session(async_engine):
    """Provide an async session."""
    async_session = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session


@pytest.fixture
async def seeded_db(session: AsyncSession):
    """Seed database with test data."""
    # Create decks
    deck1 = MetaDeck(
        name="Mono Red Aggro",
        archetype="aggro",
        format="standard",
        cards={"Lightning Bolt": 4, "Goblin Guide": 4, "Mountain": 20},
        win_rate=0.55,
        meta_share=0.15,
    )
    deck2 = MetaDeck(
        name="Azorius Control",
        archetype="control",
        format="standard",
        cards={"Counterspell": 4, "Island": 12, "Plains": 12},
        win_rate=0.52,
        meta_share=0.10,
    )

    await upsert_meta_deck(session, deck1)
    await upsert_meta_deck(session, deck2)

    # Create user collection
    collection_cards = {"Lightning Bolt": 4, "Mountain": 20, "Island": 8}
    await update_collection_cards(session, "user123", collection_cards)

    await session.commit()

    return {"decks": [deck1, deck2]}


class TestToolDefinitions:
    def test_all_tools_have_required_fields(self) -> None:
        """All tool definitions have name, description, and parameters."""
        for tool in TOOL_DEFINITIONS:
            assert tool.name
            assert tool.description
            assert tool.parameters
            assert "type" in tool.parameters
            assert "properties" in tool.parameters

    def test_tool_count(self) -> None:
        """Expected number of tools are defined."""
        assert len(TOOL_DEFINITIONS) == 9

    def test_tool_names(self) -> None:
        """Expected tools are defined."""
        names = {t.name for t in TOOL_DEFINITIONS}
        assert "get_deck_recommendations" in names
        assert "calculate_deck_distance" in names
        assert "get_collection_stats" in names
        assert "list_meta_decks" in names
        assert "search_collection" in names
        assert "build_deck" in names
        assert "find_synergies" in names
        assert "export_to_arena" in names
        assert "improve_deck" in names


class TestGetDeckRecommendations:
    async def test_returns_recommendations(
        self,
        session: AsyncSession,
        seeded_db: dict,  # noqa: ARG002
    ) -> None:
        """Returns ranked deck recommendations."""
        result = await get_deck_recommendations(session, "user123", "standard")

        assert "recommendations" in result
        assert len(result["recommendations"]) > 0

    async def test_recommendations_have_required_fields(
        self,
        session: AsyncSession,
        seeded_db: dict,  # noqa: ARG002
    ) -> None:
        """Each recommendation has required fields."""
        result = await get_deck_recommendations(session, "user123", "standard")

        for rec in result["recommendations"]:
            assert "deck_name" in rec
            assert "archetype" in rec
            assert "completion_percentage" in rec
            assert "missing_cards" in rec
            assert "wildcard_cost" in rec

    async def test_empty_format_returns_message(self, session: AsyncSession) -> None:
        """Empty format returns helpful message."""
        result = await get_deck_recommendations(session, "user123", "unknown_format")

        assert result["recommendations"] == []
        assert "message" in result

    async def test_respects_limit(
        self,
        session: AsyncSession,
        seeded_db: dict,  # noqa: ARG002
    ) -> None:
        """Respects the limit parameter."""
        result = await get_deck_recommendations(session, "user123", "standard", limit=1)

        assert len(result["recommendations"]) == 1


class TestCalculateDeckDistance:
    async def test_returns_distance_info(
        self,
        session: AsyncSession,
        seeded_db: dict,  # noqa: ARG002
    ) -> None:
        """Returns distance information for a deck."""
        result = await calculate_deck_distance_tool(
            session, "user123", "standard", "Mono Red Aggro"
        )

        assert result["deck_name"] == "Mono Red Aggro"
        assert "completion_percentage" in result
        assert "owned_cards" in result
        assert "missing_cards" in result
        assert "wildcard_cost" in result

    async def test_deck_not_found(self, session: AsyncSession) -> None:
        """Returns error for unknown deck."""
        result = await calculate_deck_distance_tool(
            session, "user123", "standard", "Nonexistent Deck"
        )

        assert "error" in result

    async def test_wildcard_cost_breakdown(
        self,
        session: AsyncSession,
        seeded_db: dict,  # noqa: ARG002
    ) -> None:
        """Wildcard cost includes breakdown by rarity."""
        result = await calculate_deck_distance_tool(
            session, "user123", "standard", "Mono Red Aggro"
        )

        wc = result["wildcard_cost"]
        assert "common" in wc
        assert "uncommon" in wc
        assert "rare" in wc
        assert "mythic" in wc
        assert "total" in wc


class TestGetCollectionStats:
    async def test_returns_stats_for_existing_collection(
        self,
        session: AsyncSession,
        seeded_db: dict,  # noqa: ARG002
    ) -> None:
        """Returns stats for existing collection."""
        result = await get_collection_stats(session, "user123")

        assert result["has_collection"] is True
        assert "total_cards" in result
        assert "unique_cards" in result

    async def test_returns_message_for_missing_collection(self, session: AsyncSession) -> None:
        """Returns helpful message for missing collection."""
        result = await get_collection_stats(session, "unknown_user")

        assert result["has_collection"] is False
        assert "message" in result


class TestListMetaDecks:
    async def test_returns_deck_list(
        self,
        session: AsyncSession,
        seeded_db: dict,  # noqa: ARG002
    ) -> None:
        """Returns list of meta decks."""
        result = await list_meta_decks(session, "standard")

        assert "decks" in result
        assert len(result["decks"]) == 2

    async def test_deck_info_has_required_fields(
        self,
        session: AsyncSession,
        seeded_db: dict,  # noqa: ARG002
    ) -> None:
        """Each deck has required fields."""
        result = await list_meta_decks(session, "standard")

        for deck in result["decks"]:
            assert "name" in deck
            assert "archetype" in deck
            assert "win_rate" in deck
            assert "meta_share" in deck

    async def test_empty_format(self, session: AsyncSession) -> None:
        """Empty format returns empty list with message."""
        result = await list_meta_decks(session, "unknown_format")

        assert result["decks"] == []
        assert "message" in result

    async def test_respects_limit(
        self,
        session: AsyncSession,
        seeded_db: dict,  # noqa: ARG002
    ) -> None:
        """Respects the limit parameter."""
        result = await list_meta_decks(session, "standard", limit=1)

        assert len(result["decks"]) == 1


class TestExecuteTool:
    async def test_executes_get_deck_recommendations(
        self,
        session: AsyncSession,
        seeded_db: dict,  # noqa: ARG002
    ) -> None:
        """Executes get_deck_recommendations tool."""
        result = await execute_tool(
            session,
            "get_deck_recommendations",
            {"user_id": "user123", "format": "standard"},
        )

        assert "recommendations" in result

    async def test_executes_calculate_deck_distance(
        self,
        session: AsyncSession,
        seeded_db: dict,  # noqa: ARG002
    ) -> None:
        """Executes calculate_deck_distance tool."""
        result = await execute_tool(
            session,
            "calculate_deck_distance",
            {"user_id": "user123", "format": "standard", "deck_name": "Mono Red Aggro"},
        )

        assert "deck_name" in result

    async def test_executes_get_collection_stats(
        self,
        session: AsyncSession,
        seeded_db: dict,  # noqa: ARG002
    ) -> None:
        """Executes get_collection_stats tool."""
        result = await execute_tool(
            session,
            "get_collection_stats",
            {"user_id": "user123"},
        )

        assert "has_collection" in result

    async def test_executes_list_meta_decks(
        self,
        session: AsyncSession,
        seeded_db: dict,  # noqa: ARG002
    ) -> None:
        """Executes list_meta_decks tool."""
        result = await execute_tool(
            session,
            "list_meta_decks",
            {"format": "standard"},
        )

        assert "decks" in result

    async def test_unknown_tool_raises(self, session: AsyncSession) -> None:
        """Raises ValueError for unknown tool."""
        with pytest.raises(ValueError, match="Unknown tool"):
            await execute_tool(session, "unknown_tool", {})
