"""
MLForge inference client.

Calls the MLForge API for deck recommendation scoring.
"""

from dataclasses import dataclass

import httpx

from forgebreaker.config import settings
from forgebreaker.ml.features import DeckFeatures


@dataclass
class RecommendationScore:
    """Score returned by MLForge for a deck recommendation."""

    deck_name: str
    score: float
    confidence: float


class MLForgeClient:
    """
    Client for the MLForge recommendation API.

    Sends deck features to MLForge and receives recommendation scores.
    """

    def __init__(self, base_url: str | None = None, timeout: float = 30.0) -> None:
        """
        Initialize the MLForge client.

        Args:
            base_url: MLForge API base URL. Defaults to settings.mlforge_url.
            timeout: Request timeout in seconds.
        """
        self.base_url = base_url or settings.mlforge_url
        self.timeout = timeout

    async def score_deck(self, features: DeckFeatures) -> RecommendationScore:
        """
        Get recommendation score for a single deck.

        Args:
            features: Extracted deck features

        Returns:
            RecommendationScore with score and confidence

        Raises:
            httpx.HTTPError: If API request fails
        """
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/api/v1/score",
                json={"features": features.to_dict()},
            )
            response.raise_for_status()

            data = response.json()
            return RecommendationScore(
                deck_name=features.deck_name,
                score=data.get("score", 0.0),
                confidence=data.get("confidence", 0.0),
            )

    async def score_decks(self, features_list: list[DeckFeatures]) -> list[RecommendationScore]:
        """
        Get recommendation scores for multiple decks.

        Args:
            features_list: List of extracted deck features

        Returns:
            List of RecommendationScores, one per deck

        Raises:
            httpx.HTTPError: If API request fails
        """
        if not features_list:
            return []

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/api/v1/score/batch",
                json={"decks": [f.to_dict() for f in features_list]},
            )
            response.raise_for_status()

            data = response.json()
            scores = data.get("scores", [])

            return [
                RecommendationScore(
                    deck_name=features_list[i].deck_name,
                    score=s.get("score", 0.0),
                    confidence=s.get("confidence", 0.0),
                )
                for i, s in enumerate(scores)
            ]

    async def health_check(self) -> bool:
        """
        Check if MLForge API is available.

        Returns:
            True if API is healthy, False otherwise
        """
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.base_url}/health")
                return response.status_code == 200
        except httpx.HTTPError:
            return False


# Default client instance
_client: MLForgeClient | None = None


def get_mlforge_client() -> MLForgeClient:
    """
    Get the default MLForge client instance.

    Returns:
        Singleton MLForgeClient instance
    """
    global _client
    if _client is None:
        _client = MLForgeClient()
    return _client
