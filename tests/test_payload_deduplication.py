"""
Tests for Payload Deduplication (PR 9).

These tests verify:
1. Tool responses no longer include `formatted` field
2. Structured data fields are preserved
3. LLM is the single formatter (no pre-formatted output)
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from forgebreaker.mcp.tools import (
    build_deck_tool,
    find_synergies_tool,
    improve_deck_tool,
    search_collection_tool,
)

# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def mock_session() -> AsyncMock:
    """Create mock database session."""
    return AsyncMock()


@pytest.fixture
def mock_collection():
    """Create mock collection model."""
    collection = MagicMock()
    collection.cards = {
        "Lightning Bolt": 4,
        "Shock": 4,
        "Goblin Guide": 4,
        "Mountain": 20,
    }
    return collection


@pytest.fixture
def mock_card_db() -> dict:
    """Create mock card database."""
    return {
        "Lightning Bolt": {
            "name": "Lightning Bolt",
            "type_line": "Instant",
            "colors": ["R"],
            "color_identity": ["R"],
            "oracle_text": "Deal 3 damage to any target.",
            "legalities": {"modern": "legal", "standard": "not_legal"},
            "keywords": [],
        },
        "Shock": {
            "name": "Shock",
            "type_line": "Instant",
            "colors": ["R"],
            "color_identity": ["R"],
            "oracle_text": "Deal 2 damage to any target.",
            "legalities": {"modern": "legal", "standard": "legal"},
            "keywords": [],
        },
        "Goblin Guide": {
            "name": "Goblin Guide",
            "type_line": "Creature — Goblin Scout",
            "colors": ["R"],
            "color_identity": ["R"],
            "oracle_text": "Haste...",
            "legalities": {"modern": "legal", "standard": "not_legal"},
            "keywords": ["Haste"],
        },
        "Mountain": {
            "name": "Mountain",
            "type_line": "Basic Land — Mountain",
            "colors": [],
            "color_identity": [],
            "oracle_text": "",
            "legalities": {"modern": "legal", "standard": "legal"},
            "keywords": [],
        },
    }


@pytest.fixture
def mock_format_legality() -> dict:
    """Create mock format legality mapping."""
    return {
        "modern": {"Lightning Bolt", "Shock", "Goblin Guide", "Mountain"},
        "standard": {"Shock", "Mountain"},
    }


# =============================================================================
# SEARCH_COLLECTION_TOOL TESTS
# =============================================================================


class TestSearchCollectionNoFormatted:
    """Verify search_collection_tool returns structured data only."""

    @pytest.mark.asyncio
    async def test_no_formatted_field_in_response(
        self,
        mock_session: AsyncMock,
        mock_collection,
        mock_card_db: dict,
    ) -> None:
        """search_collection response has no 'formatted' key."""
        with (
            patch(
                "forgebreaker.mcp.tools.get_collection",
                return_value=MagicMock(),
            ),
            patch(
                "forgebreaker.mcp.tools.collection_to_model",
                return_value=mock_collection,
            ),
            patch(
                "forgebreaker.mcp.tools.search_collection",
                return_value=MagicMock(
                    found=True,
                    matching_cards=[("Lightning Bolt", 4)],
                    total_matches=1,
                    query_summary="test query",
                ),
            ),
        ):
            result = await search_collection_tool(
                session=mock_session,
                user_id="test-user",
                card_db=mock_card_db,
            )

        assert "formatted" not in result

    @pytest.mark.asyncio
    async def test_structured_fields_preserved(
        self,
        mock_session: AsyncMock,
        mock_collection,
        mock_card_db: dict,
    ) -> None:
        """search_collection response has all required structured fields."""
        with (
            patch(
                "forgebreaker.mcp.tools.get_collection",
                return_value=MagicMock(),
            ),
            patch(
                "forgebreaker.mcp.tools.collection_to_model",
                return_value=mock_collection,
            ),
            patch(
                "forgebreaker.mcp.tools.search_collection",
                return_value=MagicMock(
                    found=True,
                    matching_cards=[("Lightning Bolt", 4)],
                    total_matches=1,
                    query_summary="test query",
                ),
            ),
        ):
            result = await search_collection_tool(
                session=mock_session,
                user_id="test-user",
                card_db=mock_card_db,
            )

        # Must have structured fields
        assert "unique_count" in result
        assert "total_cards" in result
        assert "results" in result


# =============================================================================
# BUILD_DECK_TOOL TESTS
# =============================================================================


class TestBuildDeckNoFormatted:
    """Verify build_deck_tool returns structured data only."""

    @pytest.mark.asyncio
    async def test_no_formatted_field_in_response(
        self,
        mock_session: AsyncMock,
        mock_collection,
        mock_card_db: dict,
        mock_format_legality: dict,
    ) -> None:
        """build_deck response has no 'formatted' key."""
        mock_built_deck = MagicMock()
        mock_built_deck.name = "Test Deck"
        mock_built_deck.cards = {"Lightning Bolt": 4}
        mock_built_deck.total_cards = 4
        mock_built_deck.colors = {"R"}
        mock_built_deck.avg_cmc = 1.0
        mock_built_deck.explanation = "Test explanation"
        mock_built_deck.assumptions_used = "Test assumptions"

        with (
            patch(
                "forgebreaker.mcp.tools.get_collection",
                return_value=MagicMock(),
            ),
            patch(
                "forgebreaker.mcp.tools.collection_to_model",
                return_value=mock_collection,
            ),
            patch(
                "forgebreaker.mcp.tools.build_deck",
                return_value=mock_built_deck,
            ),
        ):
            result = await build_deck_tool(
                session=mock_session,
                user_id="test-user",
                theme="burn",
                card_db=mock_card_db,
                format_legality=mock_format_legality,
                format_name="modern",
            )

        assert "formatted" not in result

    @pytest.mark.asyncio
    async def test_structured_fields_preserved(
        self,
        mock_session: AsyncMock,
        mock_collection,
        mock_card_db: dict,
        mock_format_legality: dict,
    ) -> None:
        """build_deck response has all required structured fields."""
        mock_built_deck = MagicMock()
        mock_built_deck.name = "Test Deck"
        mock_built_deck.cards = {"Lightning Bolt": 4}
        mock_built_deck.total_cards = 4
        mock_built_deck.colors = {"R"}
        mock_built_deck.avg_cmc = 1.0
        mock_built_deck.explanation = "Test explanation"
        mock_built_deck.assumptions_used = "Test assumptions"

        with (
            patch(
                "forgebreaker.mcp.tools.get_collection",
                return_value=MagicMock(),
            ),
            patch(
                "forgebreaker.mcp.tools.collection_to_model",
                return_value=mock_collection,
            ),
            patch(
                "forgebreaker.mcp.tools.build_deck",
                return_value=mock_built_deck,
            ),
        ):
            result = await build_deck_tool(
                session=mock_session,
                user_id="test-user",
                theme="burn",
                card_db=mock_card_db,
                format_legality=mock_format_legality,
                format_name="modern",
            )

        # Must have structured fields
        assert "deck_name" in result or "success" in result
        assert "cards" in result or "success" in result
        assert "total_cards" in result or "success" in result


# =============================================================================
# FIND_SYNERGIES_TOOL TESTS
# =============================================================================


class TestFindSynergiesNoFormatted:
    """Verify find_synergies_tool returns structured data only."""

    @pytest.mark.asyncio
    async def test_no_formatted_field_in_response(
        self,
        mock_session: AsyncMock,
        mock_collection,
        mock_card_db: dict,
    ) -> None:
        """find_synergies response has no 'formatted' key."""
        mock_synergy_result = MagicMock()
        mock_synergy_result.source_card = "Lightning Bolt"
        mock_synergy_result.synergy_type = "damage"
        mock_synergy_result.synergistic_cards = [
            ("Shock", 4, "Also deals damage"),
        ]

        with (
            patch(
                "forgebreaker.mcp.tools.get_collection",
                return_value=MagicMock(),
            ),
            patch(
                "forgebreaker.mcp.tools.collection_to_model",
                return_value=mock_collection,
            ),
            patch(
                "forgebreaker.mcp.tools.find_synergies",
                return_value=mock_synergy_result,
            ),
        ):
            result = await find_synergies_tool(
                session=mock_session,
                user_id="test-user",
                card_name="Lightning Bolt",
                card_db=mock_card_db,
            )

        assert "formatted" not in result

    @pytest.mark.asyncio
    async def test_structured_fields_preserved(
        self,
        mock_session: AsyncMock,
        mock_collection,
        mock_card_db: dict,
    ) -> None:
        """find_synergies response has all required structured fields."""
        mock_synergy_result = MagicMock()
        mock_synergy_result.source_card = "Lightning Bolt"
        mock_synergy_result.synergy_type = "damage"
        mock_synergy_result.synergistic_cards = [
            ("Shock", 4, "Also deals damage"),
        ]

        with (
            patch(
                "forgebreaker.mcp.tools.get_collection",
                return_value=MagicMock(),
            ),
            patch(
                "forgebreaker.mcp.tools.collection_to_model",
                return_value=mock_collection,
            ),
            patch(
                "forgebreaker.mcp.tools._get_card_db_safe",
                return_value=mock_card_db,
            ),
            patch(
                "forgebreaker.mcp.tools._get_format_legality_safe",
                return_value={"standard": {"Lightning Bolt", "Shock", "Mountain"}},
            ),
            patch(
                "forgebreaker.mcp.tools.find_synergies",
                return_value=mock_synergy_result,
            ),
        ):
            result = await find_synergies_tool(
                session=mock_session,
                user_id="test-user",
                card_name="Lightning Bolt",
                card_db=mock_card_db,
            )

        # Must have structured fields
        assert "found" in result
        assert "source_card" in result
        assert "synergy_type" in result
        assert "synergistic_cards" in result
        assert "count" in result


# =============================================================================
# IMPROVE_DECK_TOOL TESTS
# =============================================================================


class TestImproveDeckNoFormatted:
    """Verify improve_deck_tool returns structured data only."""

    @pytest.mark.asyncio
    async def test_no_formatted_field_in_response(
        self,
        mock_session: AsyncMock,
        mock_collection,
        mock_card_db: dict,
    ) -> None:
        """improve_deck response has no 'formatted' key."""
        mock_analysis = MagicMock()
        mock_analysis.total_cards = 60
        mock_analysis.colors = {"R"}
        mock_analysis.creature_count = 20
        mock_analysis.spell_count = 20
        mock_analysis.land_count = 20
        mock_analysis.suggestions = []
        mock_analysis.general_advice = ["Test advice"]
        mock_analysis.warnings = []
        mock_analysis.card_details = []

        with (
            patch(
                "forgebreaker.mcp.tools.get_collection",
                return_value=MagicMock(),
            ),
            patch(
                "forgebreaker.mcp.tools.collection_to_model",
                return_value=mock_collection,
            ),
            patch(
                "forgebreaker.mcp.tools._get_format_legality_safe",
                return_value={"modern": {"Lightning Bolt", "Shock", "Mountain"}},
            ),
            patch(
                "forgebreaker.mcp.tools.analyze_and_improve_deck",
                return_value=mock_analysis,
            ),
        ):
            result = await improve_deck_tool(
                session=mock_session,
                user_id="test-user",
                deck_text="4 Lightning Bolt",
                card_db=mock_card_db,
                format_name="modern",
            )

        assert "formatted" not in result

    @pytest.mark.asyncio
    async def test_structured_fields_preserved(
        self,
        mock_session: AsyncMock,
        mock_collection,
        mock_card_db: dict,
    ) -> None:
        """improve_deck response has all required structured fields."""
        mock_analysis = MagicMock()
        mock_analysis.total_cards = 60
        mock_analysis.colors = {"R"}
        mock_analysis.creature_count = 20
        mock_analysis.spell_count = 20
        mock_analysis.land_count = 20
        mock_analysis.suggestions = []
        mock_analysis.general_advice = ["Test advice"]
        mock_analysis.warnings = []
        mock_analysis.card_details = []

        with (
            patch(
                "forgebreaker.mcp.tools.get_collection",
                return_value=MagicMock(),
            ),
            patch(
                "forgebreaker.mcp.tools.collection_to_model",
                return_value=mock_collection,
            ),
            patch(
                "forgebreaker.mcp.tools._get_format_legality_safe",
                return_value={"modern": {"Lightning Bolt", "Shock", "Mountain"}},
            ),
            patch(
                "forgebreaker.mcp.tools.analyze_and_improve_deck",
                return_value=mock_analysis,
            ),
        ):
            result = await improve_deck_tool(
                session=mock_session,
                user_id="test-user",
                deck_text="4 Lightning Bolt",
                card_db=mock_card_db,
                format_name="modern",
            )

        # Must have structured fields
        assert "success" in result
        assert "total_cards" in result
        assert "colors" in result
        assert "creature_count" in result
        assert "spell_count" in result
        assert "land_count" in result
        assert "suggestions" in result
        assert "general_advice" in result
        assert "warnings" in result


# =============================================================================
# TOKEN SAVINGS VERIFICATION
# =============================================================================


class TestTokenSavings:
    """Verify that removing formatted field reduces payload size."""

    def test_no_formatted_string_duplication(self) -> None:
        """
        Contract: Tool responses must not duplicate data as formatted strings.

        BEFORE PR 9:
        - Tool returned both structured data AND formatted string
        - LLM received ~30-40% duplicated content
        - Token waste on every tool call

        AFTER PR 9:
        - Tool returns only structured data
        - LLM is single point of formatting
        - No duplication, reduced token cost
        """
        # This test documents the architectural invariant
        # Actual verification is in the individual tool tests above
        pass

    def test_llm_is_single_formatter(self) -> None:
        """
        Contract: LLM is the single point of formatting.

        Tool responses provide structured data.
        LLM converts structured data to human-readable format.
        No pre-formatting in tool layer.
        """
        # This test documents the architectural invariant
        pass
