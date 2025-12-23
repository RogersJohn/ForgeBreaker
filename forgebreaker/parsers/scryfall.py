"""
Scryfall bulk data loader.

Downloads and parses Scryfall's bulk card data to build lookup tables
for arena_id -> card_name mapping and card rarities.

Bulk data: https://scryfall.com/docs/api/bulk-data
"""

import json
from pathlib import Path
from typing import TypedDict

import httpx

SCRYFALL_BULK_API = "https://api.scryfall.com/bulk-data"

VALID_RARITIES = frozenset({"common", "uncommon", "rare", "mythic"})


def _normalize_rarity(rarity: str) -> str:
    """Normalize rarity to one of: common, uncommon, rare, mythic."""
    return rarity if rarity in VALID_RARITIES else "common"


class CardData(TypedDict):
    """Minimal card data we need from Scryfall."""

    name: str
    arena_id: int | None
    rarity: str  # common, uncommon, rare, mythic


def get_bulk_data_url() -> str:
    """
    Fetch the download URL for Scryfall's default-cards bulk data.

    Returns:
        URL to download the bulk JSON file

    Raises:
        httpx.HTTPError: If API request fails
    """
    response = httpx.get(
        SCRYFALL_BULK_API,
        headers={"User-Agent": "ForgeBreaker/1.0"},
    )
    response.raise_for_status()

    data = response.json()

    # Find the "default_cards" entry
    for entry in data["data"]:
        if entry["type"] == "default_cards":
            return str(entry["download_uri"])

    raise ValueError("Could not find default_cards bulk data URL")


def download_bulk_data(output_path: Path) -> None:
    """
    Download Scryfall bulk data to a file.

    Args:
        output_path: Where to save the JSON file

    Note:
        File is ~80MB, download may take a minute.
    """
    url = get_bulk_data_url()

    # Stream download due to file size
    with httpx.stream(
        "GET",
        url,
        headers={"User-Agent": "ForgeBreaker/1.0"},
        follow_redirects=True,
    ) as response:
        response.raise_for_status()
        with open(output_path, "wb") as f:
            for chunk in response.iter_bytes(chunk_size=8192):
                f.write(chunk)


def load_arena_id_mapping(bulk_data_path: Path) -> dict[int, str]:
    """
    Build arena_id -> card_name mapping from bulk data.

    Args:
        bulk_data_path: Path to downloaded Scryfall bulk JSON

    Returns:
        Dict mapping Arena card IDs to card names
    """
    mapping: dict[int, str] = {}

    with open(bulk_data_path, encoding="utf-8") as f:
        cards = json.load(f)

    for card in cards:
        arena_id = card.get("arena_id")
        if arena_id is not None:
            mapping[arena_id] = card["name"]

    return mapping


def load_rarity_mapping(bulk_data_path: Path) -> dict[str, str]:
    """
    Build card_name -> rarity mapping from bulk data.

    Args:
        bulk_data_path: Path to downloaded Scryfall bulk JSON

    Returns:
        Dict mapping card names to rarities (common, uncommon, rare, mythic)

    Note:
        For cards printed at multiple rarities, uses the most recent printing.
    """
    mapping: dict[str, str] = {}

    with open(bulk_data_path, encoding="utf-8") as f:
        cards = json.load(f)

    for card in cards:
        name = card["name"]
        rarity = _normalize_rarity(card.get("rarity", "common"))

        # Later entries overwrite earlier (more recent printings)
        mapping[name] = rarity

    return mapping


def load_card_data(bulk_data_path: Path) -> dict[str, CardData]:
    """
    Load complete card data keyed by name.

    Args:
        bulk_data_path: Path to downloaded Scryfall bulk JSON

    Returns:
        Dict mapping card names to CardData
    """
    data: dict[str, CardData] = {}

    with open(bulk_data_path, encoding="utf-8") as f:
        cards = json.load(f)

    for card in cards:
        name = card["name"]
        data[name] = CardData(
            name=name,
            arena_id=card.get("arena_id"),
            rarity=_normalize_rarity(card.get("rarity", "common")),
        )

    return data
