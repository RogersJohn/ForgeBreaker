"""
Deck building service.

Builds playable decks from user's collection around a theme.
"""

from dataclasses import dataclass, field
from typing import Any

from forgebreaker.models.collection import Collection

# Color mappings used throughout deck building
COLOR_TO_BASIC_LAND = {
    "W": "Plains",
    "U": "Island",
    "B": "Swamp",
    "R": "Mountain",
    "G": "Forest",
}

COLOR_TO_WORD = {
    "W": "white",
    "U": "blue",
    "B": "black",
    "R": "red",
    "G": "green",
}


@dataclass
class BuiltDeck:
    """A deck constructed from user's collection."""

    name: str
    cards: dict[str, int]  # card_name -> quantity
    total_cards: int
    colors: set[str]
    theme_cards: list[str]
    support_cards: list[str]
    lands: dict[str, int]
    notes: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class DeckBuildRequest:
    """Parameters for deck building."""

    theme: str  # Card name, type, or keyword to build around
    colors: list[str] | None = None  # Color restriction
    format: str = "standard"  # Format for legality checking
    include_cards: list[str] | None = None  # Must-include cards
    deck_size: int = 60  # Target deck size
    land_count: int = 24  # Target land count


def build_deck(
    request: DeckBuildRequest,
    collection: Collection,
    card_db: dict[str, dict[str, Any]],
    format_legality: dict[str, set[str]],
) -> BuiltDeck:
    """
    Build a deck from user's collection around a theme.

    Strategy:
    1. Find all cards matching the theme that user owns
    2. Determine color identity from theme cards
    3. Add support cards (removal, card draw) in those colors
    4. Fill mana base from owned lands
    5. Validate deck size and provide warnings

    Args:
        request: Deck building parameters
        collection: User's card collection
        card_db: Scryfall card database
        format_legality: Legal cards per format

    Returns:
        BuiltDeck with cards, lands, and notes
    """
    notes: list[str] = []
    warnings: list[str] = []

    legal_cards = format_legality.get(request.format, set())

    # Step 1: Find theme cards
    theme_cards: list[tuple[str, int, dict[str, Any]]] = []

    for card_name, qty in collection.cards.items():
        if card_name not in legal_cards:
            continue

        card_data = card_db.get(card_name)
        if not card_data:
            continue

        # Check if card matches theme
        if _matches_theme(card_name, card_data, request.theme):
            theme_cards.append((card_name, qty, card_data))

    if not theme_cards:
        warnings.append(f"No cards matching theme '{request.theme}' found in your collection")
        return BuiltDeck(
            name=f"{request.theme} Deck",
            cards={},
            total_cards=0,
            colors=set(),
            theme_cards=[],
            support_cards=[],
            lands={},
            notes=notes,
            warnings=warnings,
        )

    notes.append(f"Found {len(theme_cards)} cards matching theme '{request.theme}'")

    # Step 2: Determine colors
    deck_colors: set[str] = set()
    for _, _, card_data in theme_cards:
        deck_colors.update(card_data.get("colors", []))

    if request.colors:
        requested_colors = {c.upper() for c in request.colors}
        deck_colors = deck_colors.intersection(requested_colors)

        # Filter theme cards to only those matching color restriction
        theme_cards = [
            (name, qty, data)
            for name, qty, data in theme_cards
            if not data.get("colors") or set(data.get("colors", [])).issubset(requested_colors)
        ]

        if not theme_cards:
            warnings.append(f"No theme cards match color restriction {request.colors}")

    if not deck_colors:
        deck_colors = {"C"}  # Colorless

    notes.append(f"Deck colors: {', '.join(sorted(deck_colors))}")

    # Step 3: Build deck
    deck: dict[str, int] = {}
    nonland_target = request.deck_size - request.land_count

    # Add must-include cards first
    if request.include_cards:
        for card_name in request.include_cards:
            owned = collection.get_quantity(card_name)
            if owned > 0 and card_name in legal_cards:
                deck[card_name] = min(owned, 4)
            else:
                warnings.append(f"Cannot include {card_name} - not owned or not legal")

    # Add theme cards (prioritize)
    for card_name, qty, _ in theme_cards:
        if card_name in deck:
            continue
        deck[card_name] = min(qty, 4)

    current_count = sum(deck.values())
    theme_card_names = [name for name, _, _ in theme_cards]

    # Step 4: Add support cards
    support_cards: list[str] = []

    if current_count < nonland_target:
        support = _find_support_cards(
            collection,
            card_db,
            legal_cards,
            deck_colors,
            set(deck.keys()),
            nonland_target - current_count,
        )

        for card_name, qty in support:
            deck[card_name] = qty
            support_cards.append(card_name)

    current_count = sum(deck.values())

    if current_count < nonland_target:
        warnings.append(f"Could only find {current_count} nonland cards (target: {nonland_target})")

    # Step 5: Add lands
    lands = _build_mana_base(collection, card_db, legal_cards, deck_colors, request.land_count)

    total_lands = sum(lands.values())
    if total_lands < request.land_count:
        warnings.append(
            f"Could only find {total_lands} appropriate lands (target: {request.land_count})"
        )

    total_cards = current_count + total_lands

    return BuiltDeck(
        name=f"{request.theme.title()} Deck",
        cards=deck,
        total_cards=total_cards,
        colors=deck_colors,
        theme_cards=theme_card_names,
        support_cards=support_cards,
        lands=lands,
        notes=notes,
        warnings=warnings,
    )


def _matches_theme(card_name: str, card_data: dict[str, Any], theme: str) -> bool:
    """Check if a card matches the deck theme."""
    theme_lower = theme.lower()

    # Check name
    if theme_lower in card_name.lower():
        return True

    # Check type line
    type_line = card_data.get("type_line", "").lower()
    if theme_lower in type_line:
        return True

    # Check oracle text for keywords
    oracle = card_data.get("oracle_text", "").lower()
    return theme_lower in oracle


def _find_support_cards(
    collection: Collection,
    card_db: dict[str, dict[str, Any]],
    legal_cards: set[str],
    colors: set[str],
    exclude: set[str],
    count_needed: int,
) -> list[tuple[str, int]]:
    """Find support cards (removal, draw, etc.) in the right colors."""
    # Keywords that indicate useful support cards
    support_keywords = [
        "destroy target",
        "exile target",
        "deals damage",
        "draw a card",
        "counter target",
        "return target",
    ]

    candidates: list[tuple[str, int, float]] = []  # (name, qty, cmc)

    for card_name, qty in collection.cards.items():
        if card_name in exclude:
            continue
        if card_name not in legal_cards:
            continue

        card_data = card_db.get(card_name)
        if not card_data:
            continue

        # Check color compatibility
        card_colors = set(card_data.get("colors", []))
        if card_colors and not card_colors.issubset(colors):
            continue

        # Skip lands
        if "Land" in card_data.get("type_line", ""):
            continue

        # Check if it's a support card
        oracle = card_data.get("oracle_text", "").lower()
        if any(kw in oracle for kw in support_keywords):
            cmc = card_data.get("cmc", 5)
            candidates.append((card_name, qty, cmc))

    # Sort by CMC (prefer cheaper cards)
    candidates.sort(key=lambda x: x[2])

    result: list[tuple[str, int]] = []
    added = 0

    for card_name, qty, _ in candidates:
        if added >= count_needed:
            break
        add_qty = min(qty, 4, count_needed - added)
        result.append((card_name, add_qty))
        added += add_qty

    return result


def _build_mana_base(
    collection: Collection,
    card_db: dict[str, dict[str, Any]],
    legal_cards: set[str],
    colors: set[str],
    land_count: int,
) -> dict[str, int]:
    """Build a mana base from owned lands."""
    lands: dict[str, int] = {}
    added = 0

    # First, add dual/utility lands
    for card_name, qty in collection.cards.items():
        if added >= land_count:
            break
        if card_name not in legal_cards:
            continue

        card_data = card_db.get(card_name)
        if not card_data:
            continue

        type_line = card_data.get("type_line", "")
        if "Land" not in type_line:
            continue

        # Skip basic lands for now (add at end)
        if "Basic" in type_line:
            continue

        # Check if land produces needed colors
        oracle = card_data.get("oracle_text", "").lower()
        produces_needed = False

        for color in colors:
            color_word = COLOR_TO_WORD.get(color, "")
            if color_word and color_word in oracle:
                produces_needed = True
                break

        if produces_needed or "any color" in oracle:
            add_qty = min(qty, 4, land_count - added)
            lands[card_name] = add_qty
            added += add_qty

    # Fill rest with basics (only use what the user owns)
    if added < land_count and colors:
        basics_needed = land_count - added
        colors_list = sorted(colors - {"C"})

        if colors_list:
            per_color = basics_needed // len(colors_list)
            remainder = basics_needed % len(colors_list)

            for i, color in enumerate(colors_list):
                basic_name = COLOR_TO_BASIC_LAND.get(color)
                if basic_name:
                    desired = per_color + (1 if i < remainder else 0)
                    # Only add basics the user actually owns
                    owned = collection.cards.get(basic_name, 0)
                    add_qty = min(desired, owned, land_count - added)
                    if add_qty > 0:
                        lands[basic_name] = add_qty
                        added += add_qty

    return lands


def format_built_deck(deck: BuiltDeck) -> str:
    """Format a built deck for display."""
    lines = [f"# {deck.name}\n"]

    if deck.notes:
        lines.append("**Notes:**")
        for note in deck.notes:
            lines.append(f"- {note}")
        lines.append("")

    if deck.warnings:
        lines.append("**Warnings:**")
        for warning in deck.warnings:
            lines.append(f"- {warning}")
        lines.append("")

    lines.append(f"**Colors:** {', '.join(sorted(deck.colors)) or 'Colorless'}")
    lines.append(f"**Total Cards:** {deck.total_cards}\n")

    # Theme cards
    if deck.theme_cards:
        lines.append("## Theme Cards")
        for name in deck.theme_cards:
            qty = deck.cards.get(name, 0)
            lines.append(f"- {qty}x {name}")
        lines.append("")

    # Support cards
    if deck.support_cards:
        lines.append("## Support Cards")
        for name in deck.support_cards:
            qty = deck.cards.get(name, 0)
            lines.append(f"- {qty}x {name}")
        lines.append("")

    # Lands
    if deck.lands:
        lines.append("## Lands")
        for name, qty in sorted(deck.lands.items()):
            lines.append(f"- {qty}x {name}")
        lines.append("")

    return "\n".join(lines)


def export_deck_to_arena(deck: BuiltDeck, card_db: dict[str, dict[str, Any]]) -> str:
    """Export deck to Arena import format."""
    lines = ["Deck"]

    # Non-land cards (default to FDN set if unknown)
    for card_name, qty in sorted(deck.cards.items()):
        card_data = card_db.get(card_name, {})
        set_code = card_data.get("set", "FDN").upper()
        collector_num = card_data.get("collector_number", "1")
        lines.append(f"{qty} {card_name} ({set_code}) {collector_num}")

    # Lands
    for card_name, qty in sorted(deck.lands.items()):
        card_data = card_db.get(card_name, {})
        set_code = card_data.get("set", "FDN").upper()
        collector_num = card_data.get("collector_number", "1")
        lines.append(f"{qty} {card_name} ({set_code}) {collector_num}")

    return "\n".join(lines)
