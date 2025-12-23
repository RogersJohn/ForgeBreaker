"""
Parser for various collection export formats.

Supports:
- Simple format: "4 Lightning Bolt" or "4x Lightning Bolt"
- CSV format: "Card Name",Quantity,Set (MTGGoldfish style)
- Arena deck export format (delegates to arena_export.py)
"""

import csv
import re
from io import StringIO
from typing import Literal

from forgebreaker.models.collection import Collection

# Pattern: "4 Lightning Bolt" or "4x Lightning Bolt" or "4X Lightning Bolt"
# Groups: (quantity, card_name)
SIMPLE_PATTERN = re.compile(r"^(\d+)x?\s+(.+)$", re.IGNORECASE)


def parse_simple_format(text: str) -> dict[str, int]:
    """
    Parse simple "quantity card_name" format.

    Accepts:
        - "4 Lightning Bolt"
        - "4x Lightning Bolt"
        - "4X Lightning Bolt"

    Returns:
        Dict mapping card names to quantities.
    """
    cards: dict[str, int] = {}

    for line in text.strip().split("\n"):
        line = line.strip()
        if not line:
            continue

        match = SIMPLE_PATTERN.match(line)
        if match:
            quantity = int(match.group(1))
            name = match.group(2).strip()
            if name:
                # Aggregate duplicates
                cards[name] = cards.get(name, 0) + quantity

    return cards


def parse_csv_format(text: str) -> dict[str, int]:
    """
    Parse CSV collection export format.

    Expected columns (flexible ordering):
        - Card Name / Name / Card
        - Quantity / Count / Qty
        - Set (optional)

    Returns:
        Dict mapping card names to quantities.
    """
    cards: dict[str, int] = {}

    # Use StringIO to parse CSV from text
    reader = csv.DictReader(StringIO(text))

    if not reader.fieldnames:
        return cards

    # Find the card name column (case-insensitive)
    name_col = None
    for col in reader.fieldnames:
        if col.lower() in ("card name", "name", "card"):
            name_col = col
            break

    # Find the quantity column (case-insensitive)
    qty_col = None
    for col in reader.fieldnames:
        if col.lower() in ("quantity", "count", "qty"):
            qty_col = col
            break

    if not name_col:
        return cards

    for row in reader:
        name = row.get(name_col, "").strip()
        if not name:
            continue

        # Default to 1 if no quantity column
        qty_str = row.get(qty_col, "1") if qty_col else "1"
        try:
            quantity = int(qty_str) if qty_str else 1
        except ValueError:
            quantity = 1

        if quantity > 0:
            cards[name] = cards.get(name, 0) + quantity

    return cards


def detect_format(text: str) -> Literal["simple", "csv", "arena"]:
    """
    Auto-detect the format of collection text.

    Returns:
        - "csv" if text appears to be CSV (comma-separated with header)
        - "arena" if text matches Arena deck format (with set codes)
        - "simple" otherwise
    """
    text = text.strip()
    if not text:
        return "simple"

    lines = text.split("\n")
    first_line = lines[0].strip()

    # Check for CSV: first line has commas and looks like a header
    if "," in first_line:
        lower_first = first_line.lower()
        if any(h in lower_first for h in ("card name", "name", "quantity", "count")):
            return "csv"

    # Check for Arena format: lines have set codes in parentheses
    # Pattern: "4 Card Name (SET) 123"
    arena_pattern = re.compile(r"^\d+\s+.+\s+\([A-Z0-9]+\)\s+\S+$")
    for line in lines[:10]:  # Check first 10 lines
        line = line.strip()
        if line and arena_pattern.match(line):
            return "arena"

    return "simple"


def parse_collection_text(
    text: str, format_hint: Literal["auto", "simple", "csv", "arena"] = "auto"
) -> dict[str, int]:
    """
    Parse collection text in various formats.

    Args:
        text: Raw collection text (pasted from export)
        format_hint: Format to use, or "auto" to detect

    Returns:
        Dict mapping card names to quantities.
    """
    if not text or not text.strip():
        return {}

    # Determine format
    if format_hint == "auto":
        format_hint = detect_format(text)

    # Parse based on format
    if format_hint == "csv":
        return parse_csv_format(text)
    elif format_hint == "arena":
        # Delegate to arena parser, then convert to dict
        from forgebreaker.parsers.arena_export import parse_arena_to_collection

        collection = parse_arena_to_collection(text)
        return collection.cards
    else:
        return parse_simple_format(text)


def merge_collections(base: dict[str, int], new: dict[str, int]) -> dict[str, int]:
    """
    Merge two collections, keeping the maximum quantity for each card.

    This is useful when importing from multiple decks - we want the
    highest count seen for each card as the minimum collection size.
    """
    result = dict(base)
    for name, qty in new.items():
        result[name] = max(result.get(name, 0), qty)
    return result


def parse_multiple_decks(deck_texts: list[str]) -> Collection:
    """
    Parse multiple deck exports and merge into a collection.

    Takes the maximum quantity of each card across all decks.
    This represents the minimum collection needed to build all decks.

    Args:
        deck_texts: List of deck export texts

    Returns:
        Merged collection with max quantities
    """
    merged: dict[str, int] = {}

    for text in deck_texts:
        if not text or not text.strip():
            continue
        deck_cards = parse_collection_text(text, "auto")
        merged = merge_collections(merged, deck_cards)

    collection = Collection()
    for name, qty in merged.items():
        collection.add_card(name, qty)

    return collection
