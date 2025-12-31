"""
Collection search service.

Provides comprehensive filtered search over a user's card collection.

Supports queries like:
- "How many black dragons do I have?" -> card_type="Dragon", colors=["B"]
- "What creatures have flying?" -> card_type="Creature", keywords=["flying"]
- "Show me my 3-drops" -> cmc=3
- "What cards draw cards?" -> oracle_text="draw"
- "What mono-red cards do I have?" -> colors=["R"], color_exact=True
- "What Standard-legal rares do I have?" -> format_legal="standard", rarity="rare"
"""

import logging
import re
from dataclasses import dataclass
from typing import Any

from forgebreaker.models.collection import Collection
from forgebreaker.models.failure import FailureKind, KnownError

logger = logging.getLogger(__name__)


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
    cmc: float
    oracle_text: str
    keywords: list[str]
    power: str | None
    toughness: str | None


def search_collection(
    collection: Collection,
    card_db: dict[str, dict[str, Any]],
    # Name and text filters
    name_contains: str | None = None,
    oracle_text: str | None = None,
    # Type filters
    card_type: str | None = None,
    # Color filters
    colors: list[str] | None = None,
    color_exact: bool = False,
    # Mana cost filters
    cmc: int | None = None,
    cmc_min: int | None = None,
    cmc_max: int | None = None,
    # Keyword filters
    keywords: list[str] | None = None,
    # Set and rarity filters
    set_code: str | None = None,
    rarity: str | None = None,
    # Format legality
    format_legal: str | None = None,
    # Creature stat filters
    power_min: int | None = None,
    power_max: int | None = None,
    toughness_min: int | None = None,
    toughness_max: int | None = None,
    # Quantity filters
    min_quantity: int = 1,
    max_results: int = 50,
) -> list[CardSearchResult]:
    """
    Search user's collection for cards matching criteria.

    All filters are ANDed together - a card must match ALL specified criteria.

    Args:
        collection: User's card collection
        card_db: Scryfall card database {name: card_data}

        # Name and text filters
        name_contains: Filter cards with this text in name (case-insensitive)
        oracle_text: Filter cards with this text in oracle/rules text

        # Type filters
        card_type: Filter by type line substring (e.g., "Dragon", "Creature", "Instant")

        # Color filters
        colors: Filter by color identity (e.g., ["B"] for black cards)
        color_exact: If True, card must have EXACTLY these colors (for mono-color queries)
                    If False (default), card must have AT LEAST one of these colors

        # Mana cost filters
        cmc: Exact mana value (e.g., cmc=3 for 3-drops)
        cmc_min: Minimum mana value
        cmc_max: Maximum mana value

        # Keyword filters
        keywords: Filter by keyword abilities (e.g., ["flying", "lifelink"])
                 Card must have ALL specified keywords

        # Set and rarity filters
        set_code: Filter by set (e.g., "FDN", "DMU")
        rarity: Filter by rarity ("common", "uncommon", "rare", "mythic")

        # Format legality
        format_legal: Filter by format legality (e.g., "standard", "historic", "pioneer")

        # Creature stat filters
        power_min: Minimum power (creatures only)
        power_max: Maximum power (creatures only)
        toughness_min: Minimum toughness (creatures only)
        toughness_max: Maximum toughness (creatures only)

        # Result filters
        min_quantity: Only return cards owned in at least this quantity
        max_results: Maximum results to return

    Returns:
        List of CardSearchResult matching all criteria

    Examples:
        # Black dragons
        >>> search_collection(collection, card_db, card_type="Dragon", colors=["B"])

        # Mono-red creatures
        >>> search_collection(collection, card_db, card_type="Creature",
        ...                   colors=["R"], color_exact=True)

        # 3-drop creatures with flying
        >>> search_collection(collection, card_db, card_type="Creature",
        ...                   cmc=3, keywords=["flying"])

        # Cards that draw cards
        >>> search_collection(collection, card_db, oracle_text="draw a card")

        # Standard-legal mythics
        >>> search_collection(collection, card_db, format_legal="standard", rarity="mythic")
    """
    results: list[CardSearchResult] = []
    cards_not_in_db: list[str] = []

    # Warn if card database is empty - likely a loading issue
    if not card_db:
        logger.warning(
            "Card database is empty. Collection search will return no results. "
            "Ensure Scryfall data is downloaded."
        )
        return results

    for card_name, quantity in collection.cards.items():
        # Skip if below minimum quantity
        if quantity < min_quantity:
            continue

        # Get card data from database
        card_data = card_db.get(card_name)
        if not card_data:
            # Track cards not in database for logging
            cards_not_in_db.append(card_name)
            continue

        # Apply name filter
        if name_contains and name_contains.lower() not in card_name.lower():
            continue

        # Apply oracle text filter
        if oracle_text:
            card_oracle = card_data.get("oracle_text", "")
            if oracle_text.lower() not in card_oracle.lower():
                continue

        # Apply type filter (matches type line substring, e.g., "Dragon", "Creature")
        if card_type:
            type_line = card_data.get("type_line", "")
            if card_type.lower() not in type_line.lower():
                continue

        # Apply color filter using color_identity
        if colors:
            card_color_identity = set(card_data.get("color_identity", card_data.get("colors", [])))
            filter_colors = {c.upper() for c in colors}

            if color_exact:
                # Exact match: card must have EXACTLY these colors (mono-color queries)
                if card_color_identity != filter_colors:
                    continue
            else:
                # Inclusive match: card must have AT LEAST one matching color
                if filter_colors and not card_color_identity.intersection(filter_colors):
                    continue

        # Apply CMC filters
        card_cmc = card_data.get("cmc", 0)
        if cmc is not None and card_cmc != cmc:
            continue
        if cmc_min is not None and card_cmc < cmc_min:
            continue
        if cmc_max is not None and card_cmc > cmc_max:
            continue

        # Apply keyword filter - card must have ALL specified keywords
        if keywords:
            card_keywords = [k.lower() for k in card_data.get("keywords", [])]
            if not all(kw.lower() in card_keywords for kw in keywords):
                continue

        # Apply set filter
        if set_code and card_data.get("set", "").upper() != set_code.upper():
            continue

        # Apply rarity filter
        if rarity and card_data.get("rarity", "").lower() != rarity.lower():
            continue

        # Apply format legality filter
        if format_legal:
            legalities = card_data.get("legalities", {})
            if legalities.get(format_legal.lower()) != "legal":
                continue

        # Apply power/toughness filters (creatures only)
        if power_min is not None or power_max is not None:
            power_str = card_data.get("power")
            if power_str is None:
                continue  # Not a creature
            power = _parse_pt(power_str)
            if power is None:
                continue  # Non-numeric power (e.g., "*")
            if power_min is not None and power < power_min:
                continue
            if power_max is not None and power > power_max:
                continue

        if toughness_min is not None or toughness_max is not None:
            toughness_str = card_data.get("toughness")
            if toughness_str is None:
                continue  # Not a creature
            toughness = _parse_pt(toughness_str)
            if toughness is None:
                continue  # Non-numeric toughness (e.g., "*")
            if toughness_min is not None and toughness < toughness_min:
                continue
            if toughness_max is not None and toughness > toughness_max:
                continue

        # Card passed all filters
        results.append(
            CardSearchResult(
                name=card_name,
                quantity=quantity,
                set_code=card_data.get("set"),
                rarity=card_data.get("rarity", "common"),
                colors=card_data.get("color_identity", card_data.get("colors", [])),
                type_line=card_data.get("type_line", ""),
                mana_cost=card_data.get("mana_cost", ""),
                cmc=card_data.get("cmc", 0),
                oracle_text=card_data.get("oracle_text", ""),
                keywords=card_data.get("keywords", []),
                power=card_data.get("power"),
                toughness=card_data.get("toughness"),
            )
        )

    # TERMINAL FAILURE: Cards in collection but not in database
    # This is a data-integrity error that cannot be resolved by LLM retries.
    # Fail fast before any LLM call to prevent budget exhaustion.
    if cards_not_in_db:
        raise KnownError(
            kind=FailureKind.VALIDATION_FAILED,
            message=(
                "Your collection contains cards that are not present in the card database. "
                "Please update the card database or remove unsupported cards from the collection."
            ),
            detail=f"Missing {len(cards_not_in_db)} cards: {cards_not_in_db[:10]}",
            suggestion="Run the card database update job or check for typos in card names.",
        )

    # Sort by quantity descending, then name, then truncate to max_results
    results.sort(key=lambda x: (-x.quantity, x.name))

    return results[:max_results]


def _parse_pt(value: str) -> int | None:
    """
    Parse power/toughness value to int.

    Returns None for purely variable values like "*".
    For values like "1+*" or "2+*", extracts the base number (1, 2).
    """
    if not value:
        return None
    # Handle simple numeric values
    if value.isdigit() or (value.startswith("-") and len(value) > 1 and value[1:].isdigit()):
        return int(value)
    # Try to extract leading number (e.g., "2" from "2+*")
    match = re.match(r"^(-?\d+)", value)
    if match:
        return int(match.group(1))
    return None


def format_search_results(
    results: list[CardSearchResult],
    include_quantities: bool = True,
    include_details: bool = False,
) -> str:
    """
    Format search results for LLM response.

    Args:
        results: List of search results
        include_quantities: Include quantity for each card (e.g., "4x")
        include_details: Include additional details (CMC, keywords)

    Returns:
        Human-readable string listing cards found.
    """
    if not results:
        return "No cards found matching your criteria."

    # Calculate totals
    unique_count = len(results)
    total_cards = sum(r.quantity for r in results)

    if include_quantities and unique_count != total_cards:
        lines = [f"Found {total_cards} cards ({unique_count} unique):\n"]
    else:
        lines = [f"Found {unique_count} {'card' if unique_count == 1 else 'cards'}:\n"]

    for card in results:
        colors_str = "".join(card.colors) if card.colors else "C"
        prefix = f"- {card.quantity}x {card.name}" if include_quantities else f"- {card.name}"

        line = f"{prefix} ({colors_str}) - {card.type_line}"

        if include_details:
            details = []
            if card.cmc is not None:
                details.append(f"CMC: {int(card.cmc)}")
            if card.keywords:
                details.append(f"Keywords: {', '.join(card.keywords)}")
            if details:
                line += f" [{', '.join(details)}]"

        lines.append(line)

    return "\n".join(lines)


def get_collection_summary(
    collection: Collection,
    card_db: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """
    Get a comprehensive summary of the collection.

    Returns stats like total cards, breakdown by color, type, rarity, etc.
    Useful for answering "what's in my collection?" type questions.
    """
    summary: dict[str, Any] = {
        "total_cards": 0,
        "unique_cards": 0,
        "by_color": {"W": 0, "U": 0, "B": 0, "R": 0, "G": 0, "colorless": 0, "multicolor": 0},
        "by_type": {},
        "by_rarity": {"common": 0, "uncommon": 0, "rare": 0, "mythic": 0},
        "by_cmc": {},
        "by_keyword": {},
    }

    for card_name, quantity in collection.cards.items():
        card_data = card_db.get(card_name)
        if not card_data:
            continue

        summary["total_cards"] += quantity
        summary["unique_cards"] += 1

        # Color breakdown
        colors = card_data.get("color_identity", card_data.get("colors", []))
        if not colors:
            summary["by_color"]["colorless"] += quantity
        elif len(colors) > 1:
            summary["by_color"]["multicolor"] += quantity
        else:
            color = colors[0]
            if color in summary["by_color"]:
                summary["by_color"][color] += quantity

        # Type breakdown (extract primary type)
        type_line = card_data.get("type_line", "")
        primary_type = _extract_primary_type(type_line)
        if primary_type:
            summary["by_type"][primary_type] = summary["by_type"].get(primary_type, 0) + quantity

        # Rarity breakdown
        rarity = card_data.get("rarity", "common")
        if rarity in summary["by_rarity"]:
            summary["by_rarity"][rarity] += quantity

        # CMC breakdown
        cmc = int(card_data.get("cmc", 0))
        cmc_key = str(cmc) if cmc <= 6 else "7+"
        summary["by_cmc"][cmc_key] = summary["by_cmc"].get(cmc_key, 0) + quantity

        # Keyword breakdown (top keywords only)
        for keyword in card_data.get("keywords", []):
            summary["by_keyword"][keyword] = summary["by_keyword"].get(keyword, 0) + quantity

    # Sort keywords by count and keep top 10
    summary["by_keyword"] = dict(sorted(summary["by_keyword"].items(), key=lambda x: -x[1])[:10])

    return summary


def _extract_primary_type(type_line: str) -> str:
    """Extract primary card type from type line."""
    type_line = type_line.split("//")[0].strip()  # Handle double-faced cards
    type_line = type_line.split("—")[0].strip()  # Remove subtypes

    # Order matters - check most specific first
    type_order = [
        "Creature",
        "Planeswalker",
        "Instant",
        "Sorcery",
        "Enchantment",
        "Artifact",
        "Land",
        "Battle",
    ]
    for t in type_order:
        if t in type_line:
            return t
    return "Other"
