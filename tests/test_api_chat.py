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

        assert len(tools) == 5
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
