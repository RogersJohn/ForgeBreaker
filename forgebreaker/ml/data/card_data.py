"""Fetch and cache card data from Scryfall.

Provides card metadata (types, mana values, colors) for feature engineering.
Respects Scryfall rate limits (10 requests/second).
"""

import asyncio
import json
from pathlib import Path
from typing import Any

import httpx

# Scryfall API base URL
_SCRYFALL_API = "https://api.scryfall.com"

# Rate limit: max 10 requests per second, so delay 100ms between requests
_RATE_LIMIT_DELAY = 0.1


class FetchError(Exception):
    """Raised when fetching card data fails."""

    pass


async def fetch_set_cards(set_code: str) -> dict[str, dict[str, Any]]:
    """Fetch all cards for a set from Scryfall.

    Args:
        set_code: MTG set code (e.g., "BLB")

    Returns:
        Dict mapping card name to card data

    Raises:
        FetchError: If API request fails
    """
    cards: dict[str, dict[str, Any]] = {}
    url = f"{_SCRYFALL_API}/cards/search"
    params = {"q": f"set:{set_code.lower()}"}

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            has_more = True
            while has_more:
                response = await client.get(url, params=params)
                response.raise_for_status()
                data = response.json()

                for card in data.get("data", []):
                    cards[card["name"]] = card

                has_more = data.get("has_more", False)
                if has_more:
                    url = data.get("next_page", "")
                    params = {}  # Next page URL includes params
                    await asyncio.sleep(_RATE_LIMIT_DELAY)
    except httpx.HTTPStatusError as e:
        raise FetchError(
            f"Failed to fetch cards for {set_code}: HTTP {e.response.status_code}"
        ) from e
    except httpx.RequestError as e:
        raise FetchError(f"Failed to fetch cards for {set_code}: {e}") from e

    return cards


class CardDataCache:
    """Cache for Scryfall card data.

    Stores fetched data to avoid repeated API calls.
    """

    def __init__(self, cache_dir: Path | None = None) -> None:
        """Initialize cache.

        Args:
            cache_dir: Directory to store cache files.
                      Defaults to .cache/scryfall in current directory.
        """
        self.cache_dir = cache_dir or Path(".cache/scryfall")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._memory_cache: dict[str, dict[str, dict[str, Any]]] = {}

    def _cache_path(self, set_code: str) -> Path:
        """Get cache file path for a set."""
        return self.cache_dir / f"{set_code.upper()}.json"

    async def get_set_cards(self, set_code: str) -> dict[str, dict[str, Any]]:
        """Get cards for a set, using cache if available.

        Args:
            set_code: MTG set code

        Returns:
            Dict mapping card name to card data
        """
        set_code = set_code.upper()

        # Check memory cache first
        if set_code in self._memory_cache:
            return self._memory_cache[set_code]

        # Check file cache
        cache_path = self._cache_path(set_code)
        if cache_path.exists():
            with open(cache_path, encoding="utf-8") as f:
                cards = json.load(f)
            self._memory_cache[set_code] = cards
            return cards

        # Fetch from API
        cards = await fetch_set_cards(set_code)

        # Save to caches
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(cards, f)
        self._memory_cache[set_code] = cards

        return cards


def extract_card_type(card: dict[str, Any]) -> str:
    """Extract primary card type from card data.

    Args:
        card: Card data dict with type_line field

    Returns:
        Primary type: creature, instant, sorcery, land, enchantment,
                     artifact, planeswalker, or other
    """
    type_line = card.get("type_line", "").lower()

    # Check types in priority order
    type_priorities = [
        "creature",
        "planeswalker",
        "instant",
        "sorcery",
        "enchantment",
        "artifact",
        "land",
    ]

    for card_type in type_priorities:
        if card_type in type_line:
            return card_type

    return "other"


def extract_mana_value(card: dict[str, Any]) -> int:
    """Extract mana value (CMC) from card data.

    Args:
        card: Card data dict with cmc field

    Returns:
        Mana value as integer, 0 if not present
    """
    return int(card.get("cmc", 0))


def extract_colors(card: dict[str, Any]) -> set[str]:
    """Extract colors from card data.

    Args:
        card: Card data dict with colors field

    Returns:
        Set of color codes (W, U, B, R, G)
    """
    return set(card.get("colors", []))
