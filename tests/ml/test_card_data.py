"""Tests for Scryfall card data fetching."""

from pathlib import Path

import httpx
import pytest
import respx

from forgebreaker.ml.data.card_data import (
    CardDataCache,
    FetchError,
    extract_card_type,
    extract_colors,
    extract_mana_value,
    fetch_set_cards,
)


@pytest.fixture
def sample_scryfall_response() -> dict:
    """Sample Scryfall API response."""
    return {
        "object": "list",
        "has_more": False,
        "data": [
            {
                "name": "Lightning Bolt",
                "type_line": "Instant",
                "mana_cost": "{R}",
                "cmc": 1.0,
                "colors": ["R"],
            },
            {
                "name": "Llanowar Elves",
                "type_line": "Creature — Elf Druid",
                "mana_cost": "{G}",
                "cmc": 1.0,
                "colors": ["G"],
            },
            {
                "name": "Counterspell",
                "type_line": "Instant",
                "mana_cost": "{U}{U}",
                "cmc": 2.0,
                "colors": ["U"],
            },
        ],
    }


class TestFetchSetCards:
    """Tests for fetching cards from Scryfall."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_fetches_set_cards(self, sample_scryfall_response: dict) -> None:
        """Can fetch cards for a set from Scryfall API."""
        # Match pattern for Scryfall search API
        respx.get("https://api.scryfall.com/cards/search").mock(
            return_value=httpx.Response(200, json=sample_scryfall_response)
        )

        cards = await fetch_set_cards("BLB")

        assert len(cards) == 3
        assert "Lightning Bolt" in cards
        assert cards["Lightning Bolt"]["cmc"] == 1.0

    @pytest.mark.asyncio
    @respx.mock
    async def test_raises_on_http_error(self) -> None:
        """HTTP errors are wrapped in FetchError."""
        respx.get("https://api.scryfall.com/cards/search").mock(return_value=httpx.Response(404))

        with pytest.raises(FetchError, match="Failed to fetch cards"):
            await fetch_set_cards("INVALID")


class TestCardDataCache:
    """Tests for card data caching."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_caches_card_data(self, tmp_path: Path, sample_scryfall_response: dict) -> None:
        """Doesn't re-fetch if data is cached."""
        respx.get("https://api.scryfall.com/cards/search").mock(
            return_value=httpx.Response(200, json=sample_scryfall_response)
        )

        cache = CardDataCache(cache_dir=tmp_path)

        # First fetch - should hit API
        cards1 = await cache.get_set_cards("BLB")
        assert len(cards1) == 3

        # Second fetch - should use cache, not API
        # Clear the mock to verify no new calls
        respx.reset()
        cards2 = await cache.get_set_cards("BLB")
        assert len(cards2) == 3
        assert cards1 == cards2


class TestExtractCardType:
    """Tests for extracting card types."""

    def test_extracts_creature(self) -> None:
        """Identifies creature cards."""
        card = {"type_line": "Creature — Elf Druid"}
        assert extract_card_type(card) == "creature"

    def test_extracts_instant(self) -> None:
        """Identifies instant cards."""
        card = {"type_line": "Instant"}
        assert extract_card_type(card) == "instant"

    def test_extracts_sorcery(self) -> None:
        """Identifies sorcery cards."""
        card = {"type_line": "Sorcery"}
        assert extract_card_type(card) == "sorcery"

    def test_extracts_land(self) -> None:
        """Identifies land cards."""
        card = {"type_line": "Basic Land — Mountain"}
        assert extract_card_type(card) == "land"

    def test_extracts_enchantment(self) -> None:
        """Identifies enchantment cards."""
        card = {"type_line": "Enchantment"}
        assert extract_card_type(card) == "enchantment"

    def test_extracts_artifact(self) -> None:
        """Identifies artifact cards."""
        card = {"type_line": "Artifact"}
        assert extract_card_type(card) == "artifact"

    def test_extracts_planeswalker(self) -> None:
        """Identifies planeswalker cards."""
        card = {"type_line": "Legendary Planeswalker — Jace"}
        assert extract_card_type(card) == "planeswalker"


class TestExtractManaValue:
    """Tests for extracting mana value (CMC)."""

    def test_extracts_mana_value(self) -> None:
        """Extracts CMC from card data."""
        card = {"cmc": 3.0}
        assert extract_mana_value(card) == 3

    def test_handles_zero_cmc(self) -> None:
        """Handles cards with zero mana cost."""
        card = {"cmc": 0.0}
        assert extract_mana_value(card) == 0

    def test_handles_missing_cmc(self) -> None:
        """Returns 0 for cards missing CMC (lands)."""
        card = {}
        assert extract_mana_value(card) == 0


class TestExtractColors:
    """Tests for extracting card colors."""

    def test_extracts_single_color(self) -> None:
        """Extracts single color."""
        card = {"colors": ["R"]}
        assert extract_colors(card) == {"R"}

    def test_extracts_multiple_colors(self) -> None:
        """Extracts multiple colors."""
        card = {"colors": ["U", "B"]}
        assert extract_colors(card) == {"U", "B"}

    def test_handles_colorless(self) -> None:
        """Handles colorless cards."""
        card = {"colors": []}
        assert extract_colors(card) == set()

    def test_handles_missing_colors(self) -> None:
        """Handles cards missing colors field (lands)."""
        card = {}
        assert extract_colors(card) == set()
