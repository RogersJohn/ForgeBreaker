"""
Parser for MTG Arena deck/collection export format.

Arena export format:
    <quantity> <card name> (<set_code>) <collector_number>

Example:
    4 Lightning Bolt (LEB) 163
    4 Monastery Swiftspear (BRO) 144

Sections are separated by headers: Deck, Sideboard, Commander, Companion
"""

import re

from forgebreaker.models.canonical_card import InventoryCard
from forgebreaker.models.card import Card
from forgebreaker.models.collection import Collection

# Pattern: "4 Lightning Bolt (LEB) 163" or "4 Card (SET) 290a"
# Groups: (quantity, card_name, set_code, collector_number)
# Collector number uses \S+ to match alphanumeric variants (e.g., "290a", "123s")
ARENA_FULL_PATTERN = re.compile(r"^(\d+)\s+(.+?)\s+\(([A-Z0-9]+)\)\s+(\S+)$")

# Pattern: "4 Lightning Bolt" (no set info)
# Groups: (quantity, card_name)
ARENA_SIMPLE_PATTERN = re.compile(r"^(\d+)\s+(.+)$")

# Section headers in Arena exports
SECTION_HEADERS = frozenset({"deck", "sideboard", "commander", "companion"})


def parse_arena_export(text: str) -> list[Card]:
    """
    Parse Arena deck/collection export text into Card objects.

    Args:
        text: Raw text from Arena export (clipboard paste)

    Returns:
        List of Card objects. Empty list if input is empty/whitespace.

    Handles:
        - Full format: "4 Card Name (SET) 123"
        - Simple format: "4 Card Name"
        - Split cards: "4 Fire // Ice (MH2) 290"
        - Section headers (Deck, Sideboard, etc.)
        - Empty lines between sections
    """
    if not text or not text.strip():
        return []

    cards: list[Card] = []

    for line in text.strip().split("\n"):
        line = line.strip()

        # Skip empty lines
        if not line:
            continue

        # Skip section headers
        if line.lower() in SECTION_HEADERS:
            continue

        # Try full pattern first (with set code)
        match = ARENA_FULL_PATTERN.match(line)
        if match:
            quantity, name, set_code, collector_num = match.groups()
            cards.append(
                Card(
                    name=name,
                    quantity=int(quantity),
                    set_code=set_code,
                    collector_number=collector_num,
                )
            )
            continue

        # Try simple pattern (no set code)
        match = ARENA_SIMPLE_PATTERN.match(line)
        if match:
            quantity, name = match.groups()
            cards.append(
                Card(
                    name=name,
                    quantity=int(quantity),
                )
            )
            continue

        # Line didn't match any pattern - skip silently
        # This handles comments or malformed lines gracefully

    return cards


def parse_arena_to_inventory(text: str) -> list[InventoryCard]:
    """
    Parse Arena export text to InventoryCard list.

    This is the entry point for canonical card resolution.
    Does NOT consolidate - returns one InventoryCard per line.

    Args:
        text: Raw Arena export text

    Returns:
        List of InventoryCard objects (one per valid line)
    """
    if not text or not text.strip():
        return []

    inventory: list[InventoryCard] = []

    for line in text.strip().split("\n"):
        line = line.strip()

        # Skip empty lines
        if not line:
            continue

        # Skip section headers
        if line.lower() in SECTION_HEADERS:
            continue

        # Try full pattern first (with set code)
        match = ARENA_FULL_PATTERN.match(line)
        if match:
            quantity, name, set_code, collector_num = match.groups()
            inventory.append(
                InventoryCard(
                    name=name,
                    set_code=set_code,
                    count=int(quantity),
                    collector_number=collector_num,
                )
            )
            continue

        # Try simple pattern (no set code)
        match = ARENA_SIMPLE_PATTERN.match(line)
        if match:
            quantity, name = match.groups()
            inventory.append(
                InventoryCard(
                    name=name,
                    set_code="",
                    count=int(quantity),
                    collector_number=None,
                )
            )
            continue

        # Line didn't match any pattern - skip silently

    return inventory


def cards_to_collection(cards: list[Card]) -> Collection:
    """
    Aggregate a list of Cards into a Collection.

    Uses max quantity for duplicate card names (same card from different sets).

    Args:
        cards: List of Card objects (possibly with duplicates)

    Returns:
        Collection with max quantities per card name
    """
    collection = Collection()

    for card in cards:
        # Use max to handle same card from different sets (Arena exports each set separately)
        current = collection.cards.get(card.name, 0)
        collection.cards[card.name] = max(current, card.quantity)

    return collection


def parse_arena_to_collection(text: str) -> Collection:
    """
    Convenience function: parse Arena export directly to Collection.

    Args:
        text: Raw Arena export text

    Returns:
        Collection with all cards from export
    """
    cards = parse_arena_export(text)
    return cards_to_collection(cards)
