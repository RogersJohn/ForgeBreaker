"""Tests for chat API endpoint."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from forgebreaker.db import update_collection_cards, upsert_meta_deck
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
async def session(async_engine):
    """Provide an async session."""
    async_session = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session


@pytest.fixture
async def seeded_db(session: AsyncSession):
    """Seed database with test data."""
    deck = MetaDeck(
        name="Mono Red Aggro",
        archetype="aggro",
        format="standard",
        cards={"Lightning Bolt": 4, "Goblin Guide": 4, "Mountain": 20},
        win_rate=0.55,
        meta_share=0.15,
    )
    await upsert_meta_deck(session, deck)
    await update_collection_cards(session, "user123", {"Lightning Bolt": 4, "Mountain": 20})
    await session.commit()


class TestChatEndpoint:
    def test_missing_api_key_returns_503(self) -> None:
        """Returns 503 when API key not configured."""
        with patch("forgebreaker.api.chat.settings") as mock_settings:
            mock_settings.anthropic_api_key = ""

            client = TestClient(app)
            response = client.post(
                "/chat/",
                json={
                    "user_id": "user123",
                    "messages": [{"role": "user", "content": "Hello"}],
                },
            )

            assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
            assert "API key" in response.json()["detail"]

    def test_successful_chat_without_tools(self) -> None:
        """Returns response when Claude doesn't use tools."""
        from anthropic.types import TextBlock

        mock_text_block = MagicMock(spec=TextBlock)
        mock_text_block.text = "Hello! How can I help?"

        mock_response = MagicMock()
        mock_response.content = [mock_text_block]
        mock_response.usage.input_tokens = 100
        mock_response.usage.output_tokens = 50

        with (
            patch("forgebreaker.api.chat.settings") as mock_settings,
            patch("forgebreaker.api.chat.anthropic.Anthropic") as mock_anthropic,
        ):
            mock_settings.anthropic_api_key = "test-key"
            mock_client = MagicMock()
            mock_client.messages.create.return_value = mock_response
            mock_anthropic.return_value = mock_client

            client = TestClient(app)
            response = client.post(
                "/chat/",
                json={
                    "user_id": "user123",
                    "messages": [{"role": "user", "content": "Hello"}],
                },
            )

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["message"]["role"] == "assistant"
            assert data["message"]["content"] == "Hello! How can I help?"
            assert data["tool_calls"] == []

    def test_invalid_role_rejected(self) -> None:
        """Rejects messages with invalid role."""
        with patch("forgebreaker.api.chat.settings") as mock_settings:
            mock_settings.anthropic_api_key = "test-key"

            client = TestClient(app)
            response = client.post(
                "/chat/",
                json={
                    "user_id": "user123",
                    "messages": [{"role": "system", "content": "Hello"}],
                },
            )

            assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_empty_messages_rejected(self) -> None:
        """Rejects empty message list."""
        with patch("forgebreaker.api.chat.settings") as mock_settings:
            mock_settings.anthropic_api_key = "test-key"

            client = TestClient(app)
            response = client.post(
                "/chat/",
                json={
                    "user_id": "user123",
                    "messages": [],
                },
            )

            assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


class TestToolConversion:
    def test_tools_converted_to_anthropic_format(self) -> None:
        """Tool definitions are correctly converted."""
        from forgebreaker.api.chat import _get_anthropic_tools

        tools = _get_anthropic_tools()

        assert len(tools) == 12
        for tool in tools:
            assert "name" in tool
            assert "description" in tool
            assert "input_schema" in tool

    def test_get_deck_recommendations_tool_present(self) -> None:
        """get_deck_recommendations tool is included."""
        from forgebreaker.api.chat import _get_anthropic_tools

        tools = _get_anthropic_tools()
        names = [t["name"] for t in tools]

        assert "get_deck_recommendations" in names


class TestChatRequestValidation:
    def test_user_id_required(self) -> None:
        """user_id is required in request."""
        with patch("forgebreaker.api.chat.settings") as mock_settings:
            mock_settings.anthropic_api_key = "test-key"

            client = TestClient(app)
            response = client.post(
                "/chat/",
                json={
                    "messages": [{"role": "user", "content": "Hello"}],
                },
            )

            assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_messages_required(self) -> None:
        """messages is required in request."""
        with patch("forgebreaker.api.chat.settings") as mock_settings:
            mock_settings.anthropic_api_key = "test-key"

            client = TestClient(app)
            response = client.post(
                "/chat/",
                json={
                    "user_id": "user123",
                },
            )

            assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


class TestTerminalSuccessInvariant:
    """
    Tests for terminal success control-flow invariant.

    INVARIANT: Successful tool calls that complete the user's request
    must terminate immediately with NO additional LLM calls.
    """

    def test_build_deck_terminates_after_one_llm_call(self) -> None:
        """
        CRITICAL TEST: A simple deck build request must complete with exactly 1 LLM call.

        This test verifies the terminal success invariant:
        - User asks to build a deck
        - LLM decides to call build_deck tool
        - Tool returns successful deck
        - Response is returned IMMEDIATELY
        - NO second LLM call is made

        If this test fails, the bug is back and requests will hit budget_exceeded.
        """
        from anthropic.types import ToolUseBlock

        # First LLM response: Claude decides to use build_deck
        mock_tool_use = MagicMock(spec=ToolUseBlock)
        mock_tool_use.type = "tool_use"
        mock_tool_use.id = "tool_123"
        mock_tool_use.name = "build_deck"
        mock_tool_use.input = {"theme": "goblin"}

        mock_response = MagicMock()
        mock_response.content = [mock_tool_use]
        mock_response.usage = MagicMock()
        mock_response.usage.input_tokens = 500
        mock_response.usage.output_tokens = 100

        # Successful deck result
        mock_deck_result = {
            "success": True,
            "deck_name": "Goblin Tribal",
            "total_cards": 60,
            "colors": ["R"],
            "theme_cards": 12,
            "cards": {"Goblin Guide": 4, "Goblin Chainwhirler": 4},
            "lands": {"Mountain": 24},
            "notes": "Fast aggro deck",
            "warnings": [],
            "assumptions": "",
        }

        with (
            patch("forgebreaker.api.chat.settings") as mock_settings,
            patch("forgebreaker.api.chat.anthropic.Anthropic") as mock_anthropic,
            patch("forgebreaker.api.chat.execute_tool") as mock_execute_tool,
        ):
            mock_settings.anthropic_api_key = "test-key"
            mock_settings.use_filtered_candidate_pool = True

            mock_client = MagicMock()
            mock_client.messages.create.return_value = mock_response
            mock_anthropic.return_value = mock_client

            # Tool execution returns successful deck
            mock_execute_tool.return_value = mock_deck_result

            client = TestClient(app)
            response = client.post(
                "/chat/",
                json={
                    "user_id": "user123",
                    "messages": [{"role": "user", "content": "Build me a goblin deck"}],
                },
            )

            # MUST succeed
            assert response.status_code == status.HTTP_200_OK

            # CRITICAL ASSERTION: Exactly 1 LLM call was made
            assert mock_client.messages.create.call_count == 1, (
                f"Expected exactly 1 LLM call, got {mock_client.messages.create.call_count}. "
                "Terminal success invariant violated - loop continued after success!"
            )

            # Response should contain the deck
            data = response.json()
            assert data["message"]["role"] == "assistant"
            assert "Goblin Tribal" in data["message"]["content"]
            assert len(data["tool_calls"]) == 1
            assert data["tool_calls"][0]["name"] == "build_deck"

    def test_search_collection_terminates_after_one_llm_call(self) -> None:
        """search_collection also terminates immediately on success."""
        from anthropic.types import ToolUseBlock

        mock_tool_use = MagicMock(spec=ToolUseBlock)
        mock_tool_use.type = "tool_use"
        mock_tool_use.id = "tool_456"
        mock_tool_use.name = "search_collection"
        mock_tool_use.input = {"name_contains": "goblin"}

        mock_response = MagicMock()
        mock_response.content = [mock_tool_use]
        mock_response.usage = MagicMock()
        mock_response.usage.input_tokens = 300
        mock_response.usage.output_tokens = 50

        mock_search_result = {
            "results": [
                {"name": "Goblin Guide", "count": 4},
                {"name": "Goblin Chainwhirler", "count": 2},
            ],
            "total": 2,
            "query": "goblin",
        }

        with (
            patch("forgebreaker.api.chat.settings") as mock_settings,
            patch("forgebreaker.api.chat.anthropic.Anthropic") as mock_anthropic,
            patch("forgebreaker.api.chat.execute_tool") as mock_execute_tool,
        ):
            mock_settings.anthropic_api_key = "test-key"
            mock_settings.use_filtered_candidate_pool = True

            mock_client = MagicMock()
            mock_client.messages.create.return_value = mock_response
            mock_anthropic.return_value = mock_client

            mock_execute_tool.return_value = mock_search_result

            client = TestClient(app)
            response = client.post(
                "/chat/",
                json={
                    "user_id": "user123",
                    "messages": [{"role": "user", "content": "Do I have any goblins?"}],
                },
            )

            assert response.status_code == status.HTTP_200_OK
            assert mock_client.messages.create.call_count == 1

    def test_terminal_success_detection(self) -> None:
        """_is_terminal_success correctly identifies successful tool results."""
        from forgebreaker.api.chat import _is_terminal_success

        # build_deck with success=True is terminal
        assert _is_terminal_success("build_deck", {"success": True, "deck_name": "Test"})

        # build_deck with error is NOT terminal success
        assert not _is_terminal_success("build_deck", {"error": "No cards found"})

        # search_collection with results is terminal
        assert _is_terminal_success("search_collection", {"results": [], "total": 0})

        # Unknown tool is NOT terminal
        assert not _is_terminal_success("unknown_tool", {"success": True})

        # Non-dict result is NOT terminal
        assert not _is_terminal_success("build_deck", "string result")
