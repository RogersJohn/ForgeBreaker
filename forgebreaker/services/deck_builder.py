"""
Deck building service.

Builds playable decks from user's collection around a theme.

INVARIANT: Theme matching is a PREFERENCE, not a FILTER.
Zero theme matches must NOT produce an empty candidate pool.

INVARIANT: Deck size is a HARD CONSTRAINT, not a preference.
Decks must contain exactly the requested number of cards.
"""

import logging
from dataclasses import dataclass, field
from typing import Any

from forgebreaker.models.collection import Collection
from forgebreaker.models.failure import DeckSizeError
from forgebreaker.models.theme_intent import (
    ThemeIntent,
    card_matches_tribe,
    normalize_theme,
)

logger = logging.getLogger(__name__)

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
    card_scores: dict[str, float] = field(default_factory=dict)  # card_name -> score


@dataclass
class DeckBuildRequest:
    """Parameters for deck building."""

    theme: str  # Card name, type, or keyword to build around
    colors: list[str] | None = None  # Color restriction
    format: str = "standard"  # Format for legality checking
    include_cards: list[str] | None = None  # Must-include cards
    deck_size: int = 60  # Target deck size
    land_count: int = 24  # Target land count


def enforce_deck_size(
    deck: BuiltDeck,
    requested_size: int,
) -> BuiltDeck:
    """
    Enforce exact deck size as a hard invariant.

    INVARIANT: Deck size is a HARD CONSTRAINT, not a preference.

    This function runs after deck construction and before terminal success.
    It guarantees that the returned deck has exactly the requested number of cards.

    Enforcement rules:
    1. If total > requested: trim lowest-scoring non-lands (deterministic)
    2. If total < requested: raise DeckSizeError (hard failure)
    3. If total == requested: return as-is

    Args:
        deck: The constructed deck with card_scores populated
        requested_size: The exact number of cards required

    Returns:
        BuiltDeck with exactly requested_size cards

    Raises:
        DeckSizeError: If deck cannot meet the size requirement
    """
    initial_size = deck.total_cards

    # Case 1: Exact size - no action needed
    if initial_size == requested_size:
        logger.info(
            "DECK_SIZE_ENFORCED",
            extra={
                "requested_size": requested_size,
                "initial_size": initial_size,
                "final_size": requested_size,
                "trimmed": 0,
            },
        )
        return deck

    # Case 2: Undersized - hard failure
    if initial_size < requested_size:
        logger.warning(
            "DECK_SIZE_VIOLATION",
            extra={
                "requested_size": requested_size,
                "actual_size": initial_size,
                "shortfall": requested_size - initial_size,
            },
        )
        raise DeckSizeError(
            requested_size=requested_size,
            actual_size=initial_size,
            detail=f"Shortfall of {requested_size - initial_size} cards",
        )

    # Case 3: Oversized - deterministic trimming
    excess = initial_size - requested_size

    # Lock lands - only trim non-lands
    # Sort non-land cards by score (lowest first for removal)
    scored_cards: list[tuple[str, float, int]] = []
    for card_name, qty in deck.cards.items():
        score = deck.card_scores.get(card_name, 0.0)
        scored_cards.append((card_name, score, qty))

    # Sort by score ascending (lowest score = first to remove)
    scored_cards.sort(key=lambda x: x[1])

    cards_to_remove: dict[str, int] = {}
    removed_count = 0

    for card_name, _score, qty in scored_cards:
        if removed_count >= excess:
            break

        # How many can we remove from this card?
        can_remove = min(qty, excess - removed_count)
        if can_remove > 0:
            cards_to_remove[card_name] = can_remove
            removed_count += can_remove

    # Apply removals
    new_cards = dict(deck.cards)
    for card_name, remove_qty in cards_to_remove.items():
        current_qty = new_cards[card_name]
        new_qty = current_qty - remove_qty
        if new_qty <= 0:
            del new_cards[card_name]
        else:
            new_cards[card_name] = new_qty

    # Update totals
    new_nonland_count = sum(new_cards.values())
    new_land_count = sum(deck.lands.values())
    new_total = new_nonland_count + new_land_count

    # Update theme_cards and support_cards lists to reflect removals
    new_theme_cards = [name for name in deck.theme_cards if name in new_cards]
    new_support_cards = [name for name in deck.support_cards if name in new_cards]

    logger.info(
        "DECK_SIZE_ENFORCED",
        extra={
            "requested_size": requested_size,
            "initial_size": initial_size,
            "final_size": new_total,
            "trimmed": removed_count,
        },
    )

    return BuiltDeck(
        name=deck.name,
        cards=new_cards,
        total_cards=new_total,
        colors=deck.colors,
        theme_cards=new_theme_cards,
        support_cards=new_support_cards,
        lands=deck.lands,
        archetype=deck.archetype,
        mana_curve=_calculate_curve(new_cards, {}),  # Recalculate with empty db (safe)
        role_counts=deck.role_counts,
        notes=deck.notes,
        warnings=deck.warnings,
        card_scores=deck.card_scores,
    )


def build_deck(
    request: DeckBuildRequest,
    collection: Collection,
    card_db: dict[str, dict[str, Any]],
    format_legality: dict[str, set[str]],
) -> BuiltDeck:
    """
    Build a deck from user's collection around a theme.

    Strategy:
    1. Normalize theme intent (extract tribe if tribal request)
    2. Find all legal cards user owns (candidate pool)
    3. Apply theme as PREFERENCE (not filter) to prioritize theme cards
    4. Determine color identity from theme cards (or all cards if no theme match)
    5. Add support cards (removal, card draw) in those colors
    6. Fill mana base from owned lands
    7. Validate deck size and provide warnings

    INVARIANT: Theme matching is a PREFERENCE, not a FILTER.
    Zero theme matches must NOT produce an empty candidate pool.

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

    # Step 0: Normalize theme intent
    theme_intent = normalize_theme(request.theme)

    logger.info(
        "THEME_INTENT_NORMALIZED",
        extra={
            "raw_theme": request.theme,
            "tribe": theme_intent.tribe,
            "format": request.format,
        },
    )

    # Step 1: Build candidate pool (ALL legal owned cards, not filtered by theme)
    candidate_pool: list[tuple[str, int, dict[str, Any]]] = []

    for card_name, qty in collection.cards.items():
        if card_name not in legal_cards:
            continue

        card_data = card_db.get(card_name)
        if not card_data:
            continue

        # Skip lands for now (added separately)
        if "Land" in card_data.get("type_line", ""):
            continue

        candidate_pool.append((card_name, qty, card_data))

    candidate_pool_size = len(candidate_pool)

    logger.info(
        "CANDIDATE_POOL_BEFORE_THEME",
        extra={
            "candidate_count": candidate_pool_size,
            "format": request.format,
        },
    )

    # Step 2: Find theme cards (PREFERENCE, not FILTER)
    theme_cards: list[tuple[str, int, dict[str, Any]]] = []

    for card_name, qty, card_data in candidate_pool:
        if _matches_theme_intent(card_name, card_data, theme_intent):
            theme_cards.append((card_name, qty, card_data))

    theme_cards_count = len(theme_cards)

    logger.info(
        "CANDIDATE_POOL_AFTER_THEME",
        extra={
            "theme_card_count": theme_cards_count,
            "candidate_count": candidate_pool_size,
            "tribe": theme_intent.tribe,
        },
    )

    # INVARIANT: Theme mismatch does NOT produce empty candidate pool
    # If no theme cards found, we still build a deck from all owned cards
    if not theme_cards:
        warnings.append(
            f"No cards matching theme '{request.theme}' found in your collection. "
            "Building deck from available cards."
        )
        # Use all candidates as "theme" cards (preference becomes non-selective)
        theme_cards = candidate_pool
        notes.append("Using all available cards (no specific theme match)")
    else:
        notes.append(f"Found {theme_cards_count} cards matching theme '{request.theme}'")

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
    card_scores: dict[str, float] = {}  # Track scores for size enforcement
    nonland_target = request.deck_size - request.land_count

    # Add must-include cards first (highest priority score)
    if request.include_cards:
        for card_name in request.include_cards:
            owned = collection.get_quantity(card_name)
            if owned > 0 and card_name in legal_cards:
                deck[card_name] = min(owned, 4)
                card_scores[card_name] = 100.0  # Must-include = highest score
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

    for card_name, qty, score, card_data in scored_theme:
        add_qty = min(qty, 4)
        deck[card_name] = add_qty
        # Theme cards get base score of 10 + curve_score (range 10-11)
        card_scores[card_name] = 10.0 + score
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
            # Support cards get base score of 5 (lower than theme cards)
            card_scores[card_name] = 5.0

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

    # Add role warnings (replace underscores for readability)
    for role, target in role_targets.items():
        actual = role_counts.get(role, 0)
        if target > 0 and actual < target:
            role_display = role.replace("_", " ")
            warnings.append(f"Low {role_display}: {actual}/{target} cards. Consider adding more.")

    # Add curve warnings for archetype mismatch
    avg_cmc = sum(cmc * count for cmc, count in final_curve.items()) / max(
        sum(final_curve.values()), 1
    )
    if archetype == "aggro" and avg_cmc > 2.5:
        warnings.append(f"Aggro deck avg CMC is {avg_cmc:.1f}. Consider lower-cost cards.")
    elif archetype == "control" and avg_cmc < 2.5:
        warnings.append(f"Control deck avg CMC is {avg_cmc:.1f}. May lack late-game power.")

    # Build the preliminary deck
    preliminary_deck = BuiltDeck(
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
        card_scores=card_scores,
    )

    # INVARIANT: Deck size is a HARD CONSTRAINT
    # Enforce exact deck size before returning (may trim or raise DeckSizeError)
    return enforce_deck_size(preliminary_deck, request.deck_size)


def _matches_theme(card_name: str, card_data: dict[str, Any], theme: str) -> bool:
    """
    DEPRECATED: Use _matches_theme_intent() instead.

    This function is kept for backwards compatibility but should not be used
    for new code. It performs raw string matching which fails on phrases like
    "goblin tribal".
    """
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


def _matches_theme_intent(
    card_name: str,
    card_data: dict[str, Any],
    theme_intent: ThemeIntent,
) -> bool:
    """
    Check if a card matches the normalized theme intent.

    This function uses structured matching based on ThemeIntent:
    1. If theme has a tribe, match against oracle subtypes and card name tokens
    2. If no tribe extracted, fall back to raw theme matching

    Args:
        card_name: Name of the card
        card_data: Scryfall card data
        theme_intent: Normalized theme intent

    Returns:
        True if card matches the theme intent
    """
    # Primary: If we have a tribe, use oracle subtype matching
    if theme_intent.has_tribe():
        # has_tribe() guarantees tribe is not None
        assert theme_intent.tribe is not None
        return card_matches_tribe(card_name, card_data, theme_intent.tribe)

    # Fallback: No tribe extracted, use raw theme matching
    # This handles non-tribal themes like "burn", "control", etc.
    return _matches_theme(card_name, card_data, theme_intent.raw_theme)


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
                    # Proportional to pips using floor + remainder distribution
                    allocations: list[tuple[str, str, int, float]] = []
                    for color in colors_list:
                        basic_name = COLOR_TO_BASIC_LAND.get(color)
                        if basic_name:
                            pips = pip_counts.get(color, 0)
                            exact = basics_needed * pips / total_pips
                            floor_val = int(exact)
                            remainder = exact - floor_val
                            allocations.append((color, basic_name, floor_val, remainder))

                    # Sort by remainder descending to distribute extras fairly
                    allocations.sort(key=lambda x: -x[3])
                    total_floor = sum(a[2] for a in allocations)
                    extras = basics_needed - total_floor

                    for i, (_, basic_name, floor_val, _) in enumerate(allocations):
                        desired = floor_val + (1 if i < extras else 0)
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

    # Role counts (only show roles with cards, replace underscores for readability)
    if deck.role_counts:
        role_items = [(role, count) for role, count in deck.role_counts.items() if count > 0]
        if role_items:
            role_str = " | ".join(f"{role.replace('_', ' ')}:{count}" for role, count in role_items)
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
    """
    Export deck to Arena import format.

    Uses the Arena Sanitizer to ensure all printings are Arena-valid.
    This guarantees the output can be copy/pasted into Arena without manual edits.

    Args:
        deck: The built deck to export
        card_db: Card database with printing information

    Returns:
        Arena-format string ready for import

    Raises:
        ArenaSanitizationError: If any card cannot be sanitized for Arena.
            The entire export fails - no partial output.
    """
    from forgebreaker.services.arena_sanitizer import sanitize_deck_for_arena

    # Combine cards and lands for sanitization
    all_cards = {**deck.cards, **deck.lands}

    # Sanitize all printings (raises ArenaSanitizationError if impossible)
    sanitized = sanitize_deck_for_arena(all_cards, card_db)

    return sanitized.to_arena_format()
