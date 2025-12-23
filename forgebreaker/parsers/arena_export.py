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

from forgebreaker.models.card import Card
from forgebreaker.models.collection import Collection

# Pattern: "4 Lightning Bolt (LEB) 163"
# Groups: (quantity, card_name, set_code, collector_number)
ARENA_FULL_PATTERN = re.compile(r"^(\d+)\s+(.+?)\s+\(([A-Z0-9]+)\)\s+(\d+)$")

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


def cards_to_collection(cards: list[Card]) -> Collection:
    """
    Aggregate a list of Cards into a Collection.

    Combines quantities for duplicate card names.

    Args:
        cards: List of Card objects (possibly with duplicates)

    Returns:
        Collection with aggregated quantities
    """
    collection = Collection()

    for card in cards:
        collection.add_card(card.name, card.quantity)

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
