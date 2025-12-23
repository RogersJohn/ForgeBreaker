"""Tests for MLForge inference client."""

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from forgebreaker.ml.features import DeckFeatures
from forgebreaker.ml.inference import (
    MLForgeClient,
    RecommendationScore,
    get_mlforge_client,
    reset_mlforge_client,
)


@pytest.fixture
def sample_features() -> DeckFeatures:
    return DeckFeatures(
        deck_name="Mono-Red Aggro",
        archetype="aggro",
        format="standard",
        maindeck_size=60,
        completion_percentage=0.85,
        total_wildcards=8,
    )


@pytest.fixture
def client() -> MLForgeClient:
    return MLForgeClient(base_url="https://test-mlforge.example.com")


class TestMLForgeClient:
    def test_init_with_default_url(self) -> None:
        """Client uses settings URL by default."""
        client = MLForgeClient()
        assert client.base_url == "https://backend-production-b2b8.up.railway.app"

    def test_init_with_custom_url(self) -> None:
        """Client accepts custom URL."""
        client = MLForgeClient(base_url="https://custom.example.com")
        assert client.base_url == "https://custom.example.com"

    def test_init_with_custom_timeout(self) -> None:
        """Client accepts custom timeout."""
        client = MLForgeClient(timeout=60.0)
        assert client.timeout == 60.0


class TestScoreDeck:
    async def test_score_deck_success(
        self, client: MLForgeClient, sample_features: DeckFeatures
    ) -> None:
        """Returns score from API response."""
        from unittest.mock import MagicMock

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"score": 0.85, "confidence": 0.92}
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.post.return_value = mock_response
            mock_instance.__aenter__.return_value = mock_instance
            mock_instance.__aexit__.return_value = None
            mock_client.return_value = mock_instance

            result = await client.score_deck(sample_features)

        assert isinstance(result, RecommendationScore)
        assert result.deck_name == "Mono-Red Aggro"
        assert result.score == 0.85
        assert result.confidence == 0.92

    async def test_score_deck_calls_correct_endpoint(
        self, client: MLForgeClient, sample_features: DeckFeatures
    ) -> None:
        """Calls the correct API endpoint."""
        from unittest.mock import MagicMock

        mock_response = MagicMock()
        mock_response.json.return_value = {"score": 0.5, "confidence": 0.5}
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.post.return_value = mock_response
            mock_instance.__aenter__.return_value = mock_instance
            mock_instance.__aexit__.return_value = None
            mock_client.return_value = mock_instance

            await client.score_deck(sample_features)

            mock_instance.post.assert_called_once()
            call_args = mock_instance.post.call_args
            assert call_args[0][0] == "https://test-mlforge.example.com/api/v1/score"

    async def test_score_deck_handles_missing_fields(
        self, client: MLForgeClient, sample_features: DeckFeatures
    ) -> None:
        """Defaults to 0.0 for missing response fields."""
        from unittest.mock import MagicMock

        mock_response = MagicMock()
        mock_response.json.return_value = {}  # Empty response
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.post.return_value = mock_response
            mock_instance.__aenter__.return_value = mock_instance
            mock_instance.__aexit__.return_value = None
            mock_client.return_value = mock_instance

            result = await client.score_deck(sample_features)

        assert result.score == 0.0
        assert result.confidence == 0.0


class TestScoreDecks:
    async def test_score_decks_empty_list(self, client: MLForgeClient) -> None:
        """Returns empty list for empty input."""
        result = await client.score_decks([])
        assert result == []

    async def test_score_decks_success(self, client: MLForgeClient) -> None:
        """Returns scores for multiple decks."""
        from unittest.mock import MagicMock

        features_list = [
            DeckFeatures(deck_name="Deck A", archetype="aggro", format="standard"),
            DeckFeatures(deck_name="Deck B", archetype="control", format="standard"),
        ]

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "scores": [
                {"score": 0.9, "confidence": 0.95},
                {"score": 0.7, "confidence": 0.85},
            ]
        }
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.post.return_value = mock_response
            mock_instance.__aenter__.return_value = mock_instance
            mock_instance.__aexit__.return_value = None
            mock_client.return_value = mock_instance

            result = await client.score_decks(features_list)

        assert len(result) == 2
        assert result[0].deck_name == "Deck A"
        assert result[0].score == 0.9
        assert result[1].deck_name == "Deck B"
        assert result[1].score == 0.7

    async def test_score_decks_calls_batch_endpoint(self, client: MLForgeClient) -> None:
        """Calls the batch scoring endpoint."""
        from unittest.mock import MagicMock

        features_list = [DeckFeatures(deck_name="Test", archetype="aggro", format="standard")]

        mock_response = MagicMock()
        mock_response.json.return_value = {"scores": [{"score": 0.5, "confidence": 0.5}]}
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.post.return_value = mock_response
            mock_instance.__aenter__.return_value = mock_instance
            mock_instance.__aexit__.return_value = None
            mock_client.return_value = mock_instance

            await client.score_decks(features_list)

            call_args = mock_instance.post.call_args
            assert call_args[0][0] == "https://test-mlforge.example.com/api/v1/score/batch"

    async def test_score_decks_raises_on_length_mismatch(self, client: MLForgeClient) -> None:
        """Raises ValueError if API returns wrong number of scores."""
        from unittest.mock import MagicMock

        features_list = [
            DeckFeatures(deck_name="Deck A", archetype="aggro", format="standard"),
            DeckFeatures(deck_name="Deck B", archetype="control", format="standard"),
        ]

        mock_response = MagicMock()
        # Return only 1 score for 2 decks
        mock_response.json.return_value = {"scores": [{"score": 0.9, "confidence": 0.95}]}
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.post.return_value = mock_response
            mock_instance.__aenter__.return_value = mock_instance
            mock_instance.__aexit__.return_value = None
            mock_client.return_value = mock_instance

            with pytest.raises(ValueError, match="1 scores for 2 decks"):
                await client.score_decks(features_list)


class TestHealthCheck:
    async def test_health_check_success(self, client: MLForgeClient) -> None:
        """Returns True when API is healthy."""
        mock_response = AsyncMock()
        mock_response.status_code = 200

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get.return_value = mock_response
            mock_instance.__aenter__.return_value = mock_instance
            mock_instance.__aexit__.return_value = None
            mock_client.return_value = mock_instance

            result = await client.health_check()

        assert result is True

    async def test_health_check_failure(self, client: MLForgeClient) -> None:
        """Returns False when API is unhealthy."""
        mock_response = AsyncMock()
        mock_response.status_code = 503

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get.return_value = mock_response
            mock_instance.__aenter__.return_value = mock_instance
            mock_instance.__aexit__.return_value = None
            mock_client.return_value = mock_instance

            result = await client.health_check()

        assert result is False

    async def test_health_check_connection_error(self, client: MLForgeClient) -> None:
        """Returns False when connection fails."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get.side_effect = httpx.ConnectError("Connection failed")
            mock_instance.__aenter__.return_value = mock_instance
            mock_instance.__aexit__.return_value = None
            mock_client.return_value = mock_instance

            result = await client.health_check()

        assert result is False


class TestGetMLForgeClient:
    def test_returns_singleton(self) -> None:
        """Returns the same instance on multiple calls."""
        reset_mlforge_client()

        client1 = get_mlforge_client()
        client2 = get_mlforge_client()

        assert client1 is client2

    def test_creates_client_on_first_call(self) -> None:
        """Creates client instance on first call."""
        reset_mlforge_client()

        client = get_mlforge_client()

        assert isinstance(client, MLForgeClient)
