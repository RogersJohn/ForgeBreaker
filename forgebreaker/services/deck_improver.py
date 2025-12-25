"""
Deck improvement service.

Analyzes an existing deck and suggests upgrades from the user's collection.
"""

from dataclasses import dataclass, field
from typing import Any

from forgebreaker.models.collection import Collection
from forgebreaker.parsers.arena_export import parse_arena_export


@dataclass
class CardSuggestion:
    """A suggested card swap."""

    remove_card: str
    remove_quantity: int
    add_card: str
    add_quantity: int
    reason: str


@dataclass
class DeckAnalysis:
    """Analysis of a deck with improvement suggestions."""

    original_cards: dict[str, int]
    total_cards: int
    colors: set[str]
    creature_count: int
    spell_count: int
    land_count: int
    suggestions: list[CardSuggestion] = field(default_factory=list)
    general_advice: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _get_card_type_category(type_line: str) -> str:
    """Categorize a card by its type line."""
    type_lower = type_line.lower()
    if "land" in type_lower:
        return "land"
    if "creature" in type_lower:
        return "creature"
    if "instant" in type_lower or "sorcery" in type_lower:
        return "spell"
    if "enchantment" in type_lower:
        return "enchantment"
    if "artifact" in type_lower:
        return "artifact"
    if "planeswalker" in type_lower:
        return "planeswalker"
    return "other"


def _get_card_colors(card_data: dict[str, Any]) -> set[str]:
    """Extract colors from card data."""
    colors = card_data.get("colors", [])
    return set(colors) if colors else set()


def _calculate_power_level(card_data: dict[str, Any]) -> float:
    """
    Estimate card power level based on various factors.

    Higher score = stronger card. Uses rarity, CMC efficiency, and keywords.
    """
    score = 0.0

    # Rarity bonus
    rarity = card_data.get("rarity", "common")
    rarity_scores = {"common": 1.0, "uncommon": 2.0, "rare": 3.0, "mythic": 4.0}
    score += rarity_scores.get(rarity, 1.0)

    # CMC efficiency (lower CMC is generally better)
    cmc = card_data.get("cmc", 3)
    if cmc > 0:
        score += max(0, 4 - cmc) * 0.5

    # Keyword abilities add value
    oracle_text = card_data.get("oracle_text", "").lower()
    valuable_keywords = [
        "draw a card",
        "destroy",
        "exile",
        "counter",
        "lifelink",
        "deathtouch",
        "flying",
        "haste",
        "trample",
        "vigilance",
        "flash",
    ]
    for keyword in valuable_keywords:
        if keyword in oracle_text:
            score += 0.5

    return score


def _find_upgrades_for_card(
    card_name: str,
    card_quantity: int,
    card_data: dict[str, Any] | None,
    collection: Collection,
    card_db: dict[str, dict[str, Any]],
    deck_cards: set[str],
    deck_colors: set[str],
) -> CardSuggestion | None:
    """Find a potential upgrade for a specific card."""
    if card_data is None:
        return None

    card_type = _get_card_type_category(card_data.get("type_line", ""))

    # Don't suggest replacing lands with non-lands
    if card_type == "land":
        return None

    card_power = _calculate_power_level(card_data)
    card_cmc = card_data.get("cmc", 0)

    best_upgrade: tuple[str, float, str] | None = None  # (name, power_diff, reason)

    for owned_card, owned_qty in collection.cards.items():
        # Skip if already in deck
        if owned_card in deck_cards:
            continue

        # Skip if we don't own enough copies
        if owned_qty < card_quantity:
            continue

        owned_data = card_db.get(owned_card)
        if owned_data is None:
            continue

        owned_type = _get_card_type_category(owned_data.get("type_line", ""))

        # Must be same general category
        if owned_type != card_type:
            continue

        owned_colors = _get_card_colors(owned_data)

        # Must fit in deck's color identity
        if owned_colors and not owned_colors.issubset(deck_colors):
            continue

        owned_cmc = owned_data.get("cmc", 0)
        owned_power = _calculate_power_level(owned_data)

        # Only suggest if it's meaningfully better
        power_diff = owned_power - card_power
        if power_diff < 1.0:
            continue

        # Prefer similar CMC
        cmc_diff = abs(owned_cmc - card_cmc)
        if cmc_diff > 2:
            continue

        # Build reason
        reasons = []
        owned_rarity = owned_data.get("rarity", "common")
        if owned_rarity in ("rare", "mythic"):
            reasons.append(f"higher rarity ({owned_rarity})")

        owned_oracle = owned_data.get("oracle_text", "").lower()
        if "draw" in owned_oracle:
            reasons.append("provides card advantage")
        if "destroy" in owned_oracle or "exile" in owned_oracle:
            reasons.append("better removal")

        if not reasons:
            reasons.append("stronger card")

        reason = ", ".join(reasons)

        if best_upgrade is None or power_diff > best_upgrade[1]:
            best_upgrade = (owned_card, power_diff, reason)

    if best_upgrade:
        return CardSuggestion(
            remove_card=card_name,
            remove_quantity=card_quantity,
            add_card=best_upgrade[0],
            add_quantity=card_quantity,
            reason=best_upgrade[2],
        )

    return None


def analyze_and_improve_deck(
    deck_text: str,
    collection: Collection,
    card_db: dict[str, dict[str, Any]],
    max_suggestions: int = 5,
) -> DeckAnalysis:
    """
    Analyze a deck and suggest improvements from the user's collection.

    Args:
        deck_text: Arena-format deck list
        collection: User's card collection
        card_db: Scryfall card database
        max_suggestions: Maximum number of suggestions to return

    Returns:
        DeckAnalysis with suggestions and advice
    """
    # Parse the deck
    cards = parse_arena_export(deck_text)

    if not cards:
        return DeckAnalysis(
            original_cards={},
            total_cards=0,
            colors=set(),
            creature_count=0,
            spell_count=0,
            land_count=0,
            warnings=["Could not parse any cards from the deck list."],
        )

    # Build deck dictionary
    deck_cards: dict[str, int] = {}
    for card in cards:
        deck_cards[card.name] = deck_cards.get(card.name, 0) + card.quantity

    # Analyze deck composition
    colors: set[str] = set()
    creature_count = 0
    spell_count = 0
    land_count = 0

    for card_name in deck_cards:
        card_data = card_db.get(card_name)
        if card_data:
            colors.update(_get_card_colors(card_data))
            card_type = _get_card_type_category(card_data.get("type_line", ""))
            if card_type == "creature":
                creature_count += deck_cards[card_name]
            elif card_type == "spell":
                spell_count += deck_cards[card_name]
            elif card_type == "land":
                land_count += deck_cards[card_name]

    total_cards = sum(deck_cards.values())

    # Find upgrade suggestions
    suggestions: list[CardSuggestion] = []
    deck_card_set = set(deck_cards.keys())

    # Sort by quantity (suggest replacing 4-ofs first for bigger impact)
    sorted_cards = sorted(deck_cards.items(), key=lambda x: -x[1])

    for card_name, quantity in sorted_cards:
        if len(suggestions) >= max_suggestions:
            break

        card_data = card_db.get(card_name)
        suggestion = _find_upgrades_for_card(
            card_name,
            quantity,
            card_data,
            collection,
            card_db,
            deck_card_set,
            colors if colors else {"W", "U", "B", "R", "G"},
        )

        if suggestion:
            suggestions.append(suggestion)

    # Generate general advice
    general_advice: list[str] = []
    warnings: list[str] = []

    if total_cards < 60:
        warnings.append(f"Deck has only {total_cards} cards. Standard decks need 60.")
    elif total_cards > 60:
        general_advice.append(f"Deck has {total_cards} cards. Consider cutting to exactly 60.")

    if land_count < 20:
        warnings.append(f"Only {land_count} lands may cause mana problems. Consider 22-26 lands.")
    elif land_count > 26:
        general_advice.append(f"{land_count} lands is high. Consider cutting 1-2.")

    if creature_count == 0 and spell_count > 0:
        general_advice.append("No creatures detected. Make sure you have win conditions.")

    if not suggestions:
        general_advice.append(
            "No direct upgrades found. Your deck may already use your best cards!"
        )

    return DeckAnalysis(
        original_cards=deck_cards,
        total_cards=total_cards,
        colors=colors,
        creature_count=creature_count,
        spell_count=spell_count,
        land_count=land_count,
        suggestions=suggestions,
        general_advice=general_advice,
        warnings=warnings,
    )


def format_deck_analysis(analysis: DeckAnalysis) -> str:
    """Format deck analysis for display."""
    lines: list[str] = []

    # Summary
    color_str = "".join(sorted(analysis.colors)) if analysis.colors else "Colorless"
    lines.append(f"**Deck Analysis** ({analysis.total_cards} cards, {color_str})")
    lines.append(
        f"- Creatures: {analysis.creature_count}, "
        f"Spells: {analysis.spell_count}, Lands: {analysis.land_count}"
    )
    lines.append("")

    # Warnings first
    if analysis.warnings:
        lines.append("**Issues:**")
        for warning in analysis.warnings:
            lines.append(f"- {warning}")
        lines.append("")

    # Suggestions
    if analysis.suggestions:
        lines.append("**Suggested Upgrades:**")
        for i, suggestion in enumerate(analysis.suggestions, 1):
            lines.append(
                f"{i}. Replace {suggestion.remove_quantity}x {suggestion.remove_card} "
                f"with {suggestion.add_quantity}x {suggestion.add_card}"
            )
            lines.append(f"   Reason: {suggestion.reason}")
        lines.append("")

    # General advice
    if analysis.general_advice:
        lines.append("**Tips:**")
        for advice in analysis.general_advice:
            lines.append(f"- {advice}")

    return "\n".join(lines)
