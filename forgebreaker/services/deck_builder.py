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

# Target mana curve distributions by archetype (CMC bucket -> card count)
# These are for 36 nonland cards (60 - 24 lands)
ARCHETYPE_CURVES: dict[str, dict[int, int]] = {
    "aggro": {1: 10, 2: 12, 3: 8, 4: 4, 5: 2, 6: 0},  # avg ~2.0
    "midrange": {1: 4, 2: 8, 3: 10, 4: 8, 5: 4, 6: 2},  # avg ~3.0
    "control": {1: 2, 2: 6, 3: 8, 4: 10, 5: 6, 6: 4},  # avg ~3.5
    "combo": {1: 6, 2: 8, 3: 8, 4: 6, 5: 4, 6: 4},  # varies
}

# Keywords that indicate deck archetype
ARCHETYPE_INDICATORS: dict[str, list[str]] = {
    "aggro": ["haste", "first strike", "menace", "prowess", "attacks"],
    "control": ["counter target", "destroy target", "exile target", "draw a card"],
    "combo": ["whenever", "sacrifice", "untap", "add {", "copy"],
    "midrange": ["enter", "gain life", "dies", "when this creature"],
}

# Keywords that identify card roles in a deck
DECK_ROLES: dict[str, list[str]] = {
    "removal": ["destroy target", "exile target", "damage to any", "damage to target"],
    "card_draw": ["draw a card", "draw two", "scry", "look at the top"],
    "ramp": ["add {", "search your library for a basic land"],
    "finisher": ["trample", "flying", "can't be blocked", "double strike"],
}

# Minimum cards per role by archetype
ARCHETYPE_ROLE_TARGETS: dict[str, dict[str, int]] = {
    "aggro": {"removal": 4, "card_draw": 0, "ramp": 0, "finisher": 4},
    "midrange": {"removal": 6, "card_draw": 2, "ramp": 2, "finisher": 4},
    "control": {"removal": 8, "card_draw": 4, "ramp": 0, "finisher": 2},
    "combo": {"removal": 4, "card_draw": 4, "ramp": 2, "finisher": 0},
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
    archetype: str = "midrange"  # aggro, midrange, control, combo
    mana_curve: dict[int, int] = field(default_factory=dict)  # CMC -> count
    role_counts: dict[str, int] = field(default_factory=dict)  # role -> count
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

    # Step 2.5: Detect archetype and get curve targets
    archetype = _detect_archetype(request.theme, theme_cards)
    target_curve = ARCHETYPE_CURVES.get(archetype, ARCHETYPE_CURVES["midrange"])
    notes.append(f"Detected archetype: {archetype}")

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

    # Add theme cards (prioritize by curve fit)
    current_curve = _calculate_curve(deck, card_db)

    # Sort theme cards by curve fit score, keeping card_data for later use
    scored_theme: list[tuple[str, int, float, dict[str, Any]]] = []
    for card_name, qty, card_data in theme_cards:
        if card_name in deck:
            continue
        cmc = card_data.get("cmc", 2)
        curve_score = _score_for_curve(cmc, current_curve, target_curve)
        scored_theme.append((card_name, qty, curve_score, card_data))

    # Add cards that fill curve gaps first
    scored_theme.sort(key=lambda x: -x[2])

    for card_name, qty, _, card_data in scored_theme:
        add_qty = min(qty, 4)
        deck[card_name] = add_qty
        # Update curve after adding
        cmc = card_data.get("cmc", 2)
        bucket = _get_cmc_bucket(cmc)
        current_curve[bucket] = current_curve.get(bucket, 0) + add_qty

    current_count = sum(deck.values())
    theme_card_names = [name for name, _, _ in theme_cards]

    # Step 4: Add support cards (curve-aware)
    support_cards: list[str] = []

    if current_count < nonland_target:
        # current_curve already updated in theme card loop above
        support = _find_support_cards(
            collection,
            card_db,
            legal_cards,
            deck_colors,
            set(deck.keys()),
            nonland_target - current_count,
            current_curve,
            target_curve,
        )

        for card_name, qty in support:
            deck[card_name] = qty
            support_cards.append(card_name)

    current_count = sum(deck.values())

    if current_count < nonland_target:
        warnings.append(f"Could only find {current_count} nonland cards (target: {nonland_target})")

    # Calculate final curve for output
    final_curve = _calculate_curve(deck, card_db)

    # Count color pips for land distribution
    pip_counts = _count_color_pips(deck, card_db)

    # Step 5: Add lands (proportional to color pips)
    lands = _build_mana_base(
        collection, card_db, legal_cards, deck_colors, request.land_count, pip_counts
    )

    total_lands = sum(lands.values())
    if total_lands < request.land_count:
        warnings.append(
            f"Could only find {total_lands} appropriate lands (target: {request.land_count})"
        )

    total_cards = current_count + total_lands

    # Count roles in the deck
    role_counts = _count_deck_roles(deck, card_db)
    role_targets = ARCHETYPE_ROLE_TARGETS.get(archetype, {})

    # Add role warnings
    for role, target in role_targets.items():
        actual = role_counts.get(role, 0)
        if target > 0 and actual < target:
            warnings.append(f"Low {role}: {actual}/{target} cards. Consider adding more.")

    # Add curve warnings for archetype mismatch
    avg_cmc = sum(cmc * count for cmc, count in final_curve.items()) / max(
        sum(final_curve.values()), 1
    )
    if archetype == "aggro" and avg_cmc > 2.5:
        warnings.append(f"Aggro deck avg CMC is {avg_cmc:.1f}. Consider lower-cost cards.")
    elif archetype == "control" and avg_cmc < 2.5:
        warnings.append(f"Control deck avg CMC is {avg_cmc:.1f}. May lack late-game power.")

    return BuiltDeck(
        name=f"{request.theme.title()} Deck",
        cards=deck,
        total_cards=total_cards,
        colors=deck_colors,
        theme_cards=theme_card_names,
        support_cards=support_cards,
        lands=lands,
        archetype=archetype,
        mana_curve=final_curve,
        role_counts=role_counts,
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


def _detect_archetype(
    theme: str,
    theme_cards: list[tuple[str, int, dict[str, Any]]],
) -> str:
    """
    Detect deck archetype from theme and card characteristics.

    Analyzes theme cards' oracle text and CMC to classify as:
    - aggro: Low CMC, combat keywords (haste, first strike)
    - control: High CMC, removal/counter keywords
    - combo: Engine pieces, sacrifice/untap effects
    - midrange: Default, balanced approach
    """
    # Score each archetype based on keyword matches
    scores: dict[str, int] = {"aggro": 0, "control": 0, "combo": 0, "midrange": 0}

    total_cmc = 0.0
    card_count = 0

    for _, qty, card_data in theme_cards:
        oracle = card_data.get("oracle_text", "").lower()
        cmc = card_data.get("cmc", 2)

        total_cmc += cmc * qty
        card_count += qty

        for archetype, keywords in ARCHETYPE_INDICATORS.items():
            for keyword in keywords:
                if keyword in oracle:
                    scores[archetype] += qty
                    break

    # Average CMC influences archetype
    avg_cmc = total_cmc / card_count if card_count > 0 else 3.0

    if avg_cmc <= 2.0:
        scores["aggro"] += 5
    elif avg_cmc >= 3.5:
        scores["control"] += 3

    # Theme-based hints
    theme_lower = theme.lower()
    if any(kw in theme_lower for kw in ["aggro", "burn", "red deck", "sligh"]):
        scores["aggro"] += 10
    elif any(kw in theme_lower for kw in ["control", "draw", "counter"]):
        scores["control"] += 10
    elif any(kw in theme_lower for kw in ["combo", "storm", "sacrifice"]):
        scores["combo"] += 10

    # Return highest scoring archetype, default to midrange
    best = max(scores.items(), key=lambda x: x[1])
    return best[0] if best[1] > 0 else "midrange"


def _get_cmc_bucket(cmc: float) -> int:
    """Convert CMC to curve bucket (1-6, where 6 = 6+)."""
    if cmc <= 0:
        return 1
    if cmc >= 6:
        return 6
    return int(cmc)


def _calculate_curve(
    cards: dict[str, int],
    card_db: dict[str, dict[str, Any]],
) -> dict[int, int]:
    """Calculate mana curve distribution for nonland cards."""
    curve: dict[int, int] = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0}

    for card_name, qty in cards.items():
        card_data = card_db.get(card_name)
        if not card_data:
            continue

        # Skip lands
        if "Land" in card_data.get("type_line", ""):
            continue

        cmc = card_data.get("cmc", 2)
        bucket = _get_cmc_bucket(cmc)
        curve[bucket] += qty

    return curve


def _score_for_curve(
    cmc: float,
    current_curve: dict[int, int],
    target_curve: dict[int, int],
) -> float:
    """Score a card based on how much it helps fill curve gaps."""
    bucket = _get_cmc_bucket(cmc)
    current = current_curve.get(bucket, 0)
    target = target_curve.get(bucket, 0)

    # No target for this CMC bucket means it doesn't contribute to score
    if target == 0:
        return 0.0
    if current >= target:
        return 0.0  # Already have enough at this CMC
    return (target - current) / target  # 0-1 score, higher = more needed


def _get_card_role(oracle_text: str) -> str | None:
    """Identify the primary role of a card from its oracle text."""
    oracle_lower = oracle_text.lower()
    for role, keywords in DECK_ROLES.items():
        if any(kw in oracle_lower for kw in keywords):
            return role
    return None


def _count_deck_roles(
    cards: dict[str, int],
    card_db: dict[str, dict[str, Any]],
) -> dict[str, int]:
    """Count cards by role in the deck."""
    role_counts: dict[str, int] = dict.fromkeys(DECK_ROLES, 0)

    for card_name, qty in cards.items():
        card_data = card_db.get(card_name)
        if not card_data:
            continue

        # Skip lands
        if "Land" in card_data.get("type_line", ""):
            continue

        oracle = card_data.get("oracle_text", "")
        role = _get_card_role(oracle)
        if role:
            role_counts[role] += qty

    return role_counts


def _count_color_pips(
    cards: dict[str, int],
    card_db: dict[str, dict[str, Any]],
) -> dict[str, int]:
    """Count color pips in mana costs for land distribution."""
    # Pattern: {W}, {U}, {B}, {R}, {G} in mana_cost field
    pip_counts: dict[str, int] = {"W": 0, "U": 0, "B": 0, "R": 0, "G": 0}

    for card_name, qty in cards.items():
        card_data = card_db.get(card_name)
        if not card_data:
            continue

        # Skip lands
        if "Land" in card_data.get("type_line", ""):
            continue

        mana_cost = card_data.get("mana_cost", "")
        for color in pip_counts:
            # Count occurrences of {W}, {U}, etc.
            pip_counts[color] += mana_cost.count(f"{{{color}}}") * qty

    return pip_counts


def _find_support_cards(
    collection: Collection,
    card_db: dict[str, dict[str, Any]],
    legal_cards: set[str],
    colors: set[str],
    exclude: set[str],
    count_needed: int,
    current_curve: dict[int, int] | None = None,
    target_curve: dict[int, int] | None = None,
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

    # (name, qty, cmc, curve_score)
    candidates: list[tuple[str, int, float, float]] = []

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
            # Calculate curve fit score if curves provided
            curve_score = 0.0
            if current_curve and target_curve:
                curve_score = _score_for_curve(cmc, current_curve, target_curve)
            candidates.append((card_name, qty, cmc, curve_score))

    # Sort by curve fit first (higher = fills gap), then by CMC
    candidates.sort(key=lambda x: (-x[3], x[2]))

    result: list[tuple[str, int]] = []
    added = 0

    for card_name, qty, _, _ in candidates:
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
    pip_counts: dict[str, int] | None = None,
) -> dict[str, int]:
    """Build a mana base from owned lands, using pip counts for distribution."""
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

    # Fill rest with basics proportional to pip counts
    if added < land_count and colors:
        basics_needed = land_count - added
        colors_list = sorted(colors - {"C"})

        if colors_list:
            # Use pip counts if provided, otherwise equal distribution
            if pip_counts:
                total_pips = sum(pip_counts.get(c, 0) for c in colors_list)
                if total_pips > 0:
                    # Proportional to pips, with rounding
                    for color in colors_list:
                        basic_name = COLOR_TO_BASIC_LAND.get(color)
                        if basic_name:
                            pips = pip_counts.get(color, 0)
                            desired = round(basics_needed * pips / total_pips)
                            owned = collection.cards.get(basic_name, 0)
                            add_qty = min(desired, owned, land_count - added)
                            if add_qty > 0:
                                lands[basic_name] = add_qty
                                added += add_qty
                else:
                    # No pips, fall back to equal distribution
                    pip_counts = None

            if not pip_counts:
                # Equal distribution fallback
                per_color = basics_needed // len(colors_list)
                remainder = basics_needed % len(colors_list)

                for i, color in enumerate(colors_list):
                    basic_name = COLOR_TO_BASIC_LAND.get(color)
                    if basic_name:
                        desired = per_color + (1 if i < remainder else 0)
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
    lines.append(f"**Archetype:** {deck.archetype.title()}")
    lines.append(f"**Total Cards:** {deck.total_cards}")

    # Mana curve (only show buckets with cards)
    if deck.mana_curve:
        curve_items = [(cmc, count) for cmc, count in sorted(deck.mana_curve.items()) if count > 0]
        if curve_items:
            curve_str = " | ".join(f"{cmc}:{count}" for cmc, count in curve_items)
            lines.append(f"**Mana Curve:** {curve_str}")

    # Role counts (only show roles with cards)
    if deck.role_counts:
        role_items = [(role, count) for role, count in deck.role_counts.items() if count > 0]
        if role_items:
            role_str = " | ".join(f"{role}:{count}" for role, count in role_items)
            lines.append(f"**Roles:** {role_str}")
    lines.append("")

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
