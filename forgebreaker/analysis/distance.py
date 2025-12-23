"""
Deck distance calculation.

Calculates how far a user's collection is from completing a specific deck,
including wildcard costs and missing card lists.
"""

from forgebreaker.models.collection import Collection
from forgebreaker.models.deck import DeckDistance, MetaDeck, WildcardCost


def calculate_deck_distance(
    deck: MetaDeck,
    collection: Collection,
    rarity_map: dict[str, str],
) -> DeckDistance:
    """
    Calculate how far a collection is from completing a deck.

    Args:
        deck: The target deck to measure against
        collection: User's card collection
        rarity_map: Mapping of card names to rarities

    Returns:
        DeckDistance with completion stats and missing cards
    """
    # Aggregate total needed for each card (maindeck + sideboard)
    total_needed: dict[str, int] = {}
    for card_name, qty in deck.cards.items():
        total_needed[card_name] = total_needed.get(card_name, 0) + qty
    for card_name, qty in deck.sideboard.items():
        total_needed[card_name] = total_needed.get(card_name, 0) + qty

    owned_cards = 0
    missing_cards = 0
    missing_card_list: list[tuple[str, int, str]] = []
    wildcard_cost = WildcardCost()

    # Check each unique card once
    for card_name, needed in total_needed.items():
        owned = collection.get_quantity(card_name)
        have = min(owned, needed)
        owned_cards += have

        if owned < needed:
            missing_qty = needed - owned
            missing_cards += missing_qty

            rarity = rarity_map.get(card_name, "common")
            missing_card_list.append((card_name, missing_qty, rarity))

            _add_wildcard_cost(wildcard_cost, rarity, missing_qty)

    # Calculate completion percentage
    total_cards = sum(total_needed.values())
    completion_pct = owned_cards / total_cards if total_cards > 0 else 1.0

    return DeckDistance(
        deck=deck,
        owned_cards=owned_cards,
        missing_cards=missing_cards,
        completion_percentage=completion_pct,
        wildcard_cost=wildcard_cost,
        missing_card_list=missing_card_list,
    )


def _add_wildcard_cost(cost: WildcardCost, rarity: str, quantity: int) -> None:
    """Add wildcards to cost based on rarity."""
    if rarity == "mythic":
        cost.mythic += quantity
    elif rarity == "rare":
        cost.rare += quantity
    elif rarity == "uncommon":
        cost.uncommon += quantity
    else:
        cost.common += quantity
