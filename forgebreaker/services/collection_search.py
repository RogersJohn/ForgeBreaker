"""
Collection search service.

Provides filtered search over a user's card collection.
"""

from dataclasses import dataclass
from typing import Any

from forgebreaker.models.collection import Collection


@dataclass
class CardSearchResult:
    """A card matching search criteria."""

    name: str
    quantity: int
    set_code: str | None
    rarity: str
    colors: list[str]
    type_line: str
    mana_cost: str


def search_collection(
    collection: Collection,
    card_db: dict[str, dict[str, Any]],
    name_contains: str | None = None,
    card_type: str | None = None,
    colors: list[str] | None = None,
    set_code: str | None = None,
    rarity: str | None = None,
    min_quantity: int = 1,
    max_results: int = 50,
) -> list[CardSearchResult]:
    """
    Search user's collection for cards matching criteria.

    Args:
        collection: User's card collection
        card_db: Scryfall card database {name: card_data}
        name_contains: Filter cards with this text in name (case-insensitive)
        card_type: Filter by type line (e.g., "Creature", "Enchantment", "Shrine")
        colors: Filter by color identity (e.g., ["R", "W"])
        set_code: Filter by set (e.g., "DMU", "M21")
        rarity: Filter by rarity ("common", "uncommon", "rare", "mythic")
        min_quantity: Only return cards owned in at least this quantity
        max_results: Maximum results to return

    Returns:
        List of CardSearchResult matching all criteria

    Example:
        >>> search_collection(collection, card_db, name_contains="shrine")
        [CardSearchResult(name="Sanctum of Stone Fangs", quantity=4, ...)]
    """
    results: list[CardSearchResult] = []

    for card_name, quantity in collection.cards.items():
        # Skip if below minimum quantity
        if quantity < min_quantity:
            continue

        # Get card data from database
        card_data = card_db.get(card_name)
        if not card_data:
            # Card not in database, skip (might be a renamed card)
            continue

        # Apply name filter
        if name_contains and name_contains.lower() not in card_name.lower():
            continue

        # Apply type filter
        if card_type:
            type_line = card_data.get("type_line", "")
            if card_type.lower() not in type_line.lower():
                continue

        # Apply color filter
        if colors:
            card_colors = set(card_data.get("colors", []))
            filter_colors = {c.upper() for c in colors}
            # Card must have at least one matching color from the filter
            if filter_colors and not card_colors.intersection(filter_colors):
                continue

        # Apply set filter
        if set_code and card_data.get("set", "").upper() != set_code.upper():
            continue

        # Apply rarity filter
        if rarity and card_data.get("rarity", "").lower() != rarity.lower():
            continue

        # Card passed all filters
        results.append(
            CardSearchResult(
                name=card_name,
                quantity=quantity,
                set_code=card_data.get("set"),
                rarity=card_data.get("rarity", "common"),
                colors=card_data.get("colors", []),
                type_line=card_data.get("type_line", ""),
                mana_cost=card_data.get("mana_cost", ""),
            )
        )

    # Sort by quantity descending, then name, then truncate to max_results
    results.sort(key=lambda x: (-x.quantity, x.name))

    return results[:max_results]


def format_search_results(results: list[CardSearchResult]) -> str:
    """
    Format search results for LLM response.

    Returns human-readable string listing cards found.
    """
    if not results:
        return "No cards found matching your criteria."

    lines = [f"Found {len(results)} {'card' if len(results) == 1 else 'cards'}:\n"]

    for card in results:
        colors_str = "".join(card.colors) if card.colors else "C"
        lines.append(f"- {card.quantity}x {card.name} ({colors_str}) - {card.type_line}")

    return "\n".join(lines)
