"""
Card database service.

Loads and caches Scryfall card data with format legality.
"""

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import httpx

SCRYFALL_BULK_API = "https://api.scryfall.com/bulk-data"
DATA_DIR = Path(__file__).parent.parent / "data"


async def download_card_database(output_path: Path | None = None) -> Path:
    """
    Download latest Scryfall default-cards bulk data.

    Args:
        output_path: Where to save the file. Defaults to data/default-cards.json

    Returns:
        Path to downloaded file.

    Raises:
        ValueError: If bulk data URL not found
        httpx.HTTPError: If download fails
    """
    if output_path is None:
        output_path = DATA_DIR / "default-cards.json"

    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Get download URL from Scryfall API
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(SCRYFALL_BULK_API)
        response.raise_for_status()
        data = response.json()

        download_url = None
        for item in data["data"]:
            if item["type"] == "default_cards":
                download_url = item["download_uri"]
                break

        if not download_url:
            raise ValueError("Could not find default_cards bulk data URL")

        # Stream download (file is ~70MB)
        async with client.stream("GET", download_url, timeout=300.0) as response:
            response.raise_for_status()
            with open(output_path, "wb") as f:
                async for chunk in response.aiter_bytes(8192):
                    f.write(chunk)

    return output_path


def load_card_database(path: Path | None = None) -> dict[str, dict[str, Any]]:
    """
    Load card database from file.

    Args:
        path: Path to JSON file. Defaults to data/default-cards.json

    Returns:
        Dict mapping card names to card data.

    Raises:
        FileNotFoundError: If database file doesn't exist
    """
    if path is None:
        path = DATA_DIR / "default-cards.json"

    if not path.exists():
        raise FileNotFoundError(
            f"Card database not found at {path}. "
            "Run `python -m forgebreaker.jobs.download_cards` first."
        )

    with open(path, encoding="utf-8") as f:
        cards = json.load(f)

    # Index by name (use first printing for each card)
    db: dict[str, dict[str, Any]] = {}
    for card in cards:
        name = card.get("name")
        if name and name not in db:
            db[name] = card

    return db


@lru_cache(maxsize=1)
def get_card_database() -> dict[str, dict[str, Any]]:
    """
    Get cached card database.

    Returns:
        Dict mapping card names to card data.
        Cached after first load.

    Raises:
        FileNotFoundError: If database file doesn't exist
    """
    return load_card_database()


def get_format_legality(card_db: dict[str, dict[str, Any]]) -> dict[str, set[str]]:
    """
    Build format -> legal cards mapping.

    Args:
        card_db: Card database from load_card_database

    Returns:
        Dict mapping format names to sets of legal card names.
        Example: {"standard": {"Lightning Bolt", "Shock", ...}}
    """
    formats = [
        "standard",
        "historic",
        "explorer",
        "pioneer",
        "modern",
        "legacy",
        "vintage",
        "brawl",
        "timeless",
    ]
    legality: dict[str, set[str]] = {f: set() for f in formats}

    for name, card in card_db.items():
        card_legalities = card.get("legalities", {})
        for fmt in formats:
            if card_legalities.get(fmt) == "legal":
                legality[fmt].add(name)

    return legality


def get_card_rarity(card_name: str, card_db: dict[str, dict[str, Any]]) -> str:
    """
    Get rarity for a card.

    Args:
        card_name: Name of the card
        card_db: Card database

    Returns:
        Rarity string ("common", "uncommon", "rare", "mythic").
        Defaults to "rare" if unknown.
    """
    card = card_db.get(card_name)
    if card:
        rarity: str = card.get("rarity", "rare")
        return rarity
    return "rare"


def get_card_colors(card_name: str, card_db: dict[str, dict[str, Any]]) -> list[str]:
    """
    Get colors for a card.

    Args:
        card_name: Name of the card
        card_db: Card database

    Returns:
        List of color letters (W, U, B, R, G).
        Empty list for colorless cards.
    """
    card = card_db.get(card_name)
    if card:
        colors: list[str] = card.get("colors", [])
        return colors
    return []


def get_card_type(card_name: str, card_db: dict[str, dict[str, Any]]) -> str:
    """
    Get type line for a card.

    Args:
        card_name: Name of the card
        card_db: Card database

    Returns:
        Type line string (e.g., "Creature — Human Wizard").
        Empty string if unknown.
    """
    card = card_db.get(card_name)
    if card:
        type_line: str = card.get("type_line", "")
        return type_line
    return ""
