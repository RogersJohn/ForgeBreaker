"""
MCP tool definitions for Claude chat integration.

Defines tools that Claude can call to help users with deck recommendations
and collection management.
"""

import logging
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from forgebreaker.analysis.assumptions import surface_assumptions
from forgebreaker.analysis.distance import calculate_deck_distance
from forgebreaker.analysis.ranker import rank_decks, rank_decks_with_ml
from forgebreaker.analysis.stress import apply_stress, find_breaking_point
from forgebreaker.db import (
    collection_to_model,
    get_collection,
    get_meta_deck,
    get_meta_decks_by_format,
    meta_deck_to_model,
)
from forgebreaker.models.collection import Collection
from forgebreaker.models.failure import FailureKind, KnownError
from forgebreaker.models.stress import StressScenario, StressType
from forgebreaker.services.assumption_surfacing import (
    BuildDeckDefaults,
    format_build_deck_assumptions,
)
from forgebreaker.services.card_database import (
    get_card_database,
    get_format_legality,
)
from forgebreaker.services.collection_search import search_collection
from forgebreaker.services.deck_builder import (
    BuiltDeck,
    DeckBuildRequest,
    build_deck,
    export_deck_to_arena,
)
from forgebreaker.services.deck_improver import analyze_and_improve_deck
from forgebreaker.services.synergy_finder import find_synergies

logger = logging.getLogger(__name__)

# Cached card database and format legality (loaded once)
_card_db_cache: dict[str, dict[str, Any]] | None = None
_format_legality_cache: dict[str, set[str]] | None = None


def _get_card_db_safe() -> dict[str, dict[str, Any]]:
    """Get card database, returning empty dict if not available."""
    global _card_db_cache
    if _card_db_cache is not None:
        return _card_db_cache
    try:
        _card_db_cache = get_card_database()
        return _card_db_cache
    except FileNotFoundError:
        logger.warning("Card database not found - tools will have limited functionality")
        return {}


def _get_format_legality_safe() -> dict[str, set[str]]:
    """Get format legality, returning empty dict if not available."""
    global _format_legality_cache
    if _format_legality_cache is not None:
        return _format_legality_cache
    card_db = _get_card_db_safe()
    if card_db:
        _format_legality_cache = get_format_legality(card_db)
        return _format_legality_cache
    return {}


@dataclass
class ToolDefinition:
    """Definition of an MCP tool."""

    name: str
    description: str
    parameters: dict[str, Any]


# Tool definitions for Claude
TOOL_DEFINITIONS: list[ToolDefinition] = [
    ToolDefinition(
        name="get_deck_recommendations",
        description="Get ranked deck recommendations based on user's collection.",
        parameters={
            "type": "object",
            "properties": {
                "format": {
                    "type": "string",
                    "description": "Game format",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max recommendations",
                    "default": 5,
                },
            },
            "required": ["format"],
        },
    ),
    ToolDefinition(
        name="calculate_deck_distance",
        description="Calculate missing cards and wildcard cost for a deck.",
        parameters={
            "type": "object",
            "properties": {
                "format": {
                    "type": "string",
                    "description": "Game format",
                },
                "deck_name": {
                    "type": "string",
                    "description": "Deck name",
                },
            },
            "required": ["format", "deck_name"],
        },
    ),
    ToolDefinition(
        name="get_collection_stats",
        description="Get card collection statistics.",
        parameters={
            "type": "object",
            "properties": {},
            "required": [],
        },
    ),
    ToolDefinition(
        name="list_meta_decks",
        description="List available meta decks for a format.",
        parameters={
            "type": "object",
            "properties": {
                "format": {
                    "type": "string",
                    "description": "Game format",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max decks",
                    "default": 10,
                },
            },
            "required": ["format"],
        },
    ),
    ToolDefinition(
        name="search_collection",
        description="Search user's collection for cards matching criteria.",
        parameters={
            "type": "object",
            "properties": {
                "name_contains": {
                    "type": "string",
                    "description": "Text in card name",
                },
                "oracle_text": {
                    "type": "string",
                    "description": "Text in rules text",
                },
                "card_type": {
                    "type": "string",
                    "description": "Type line filter",
                },
                "colors": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["W", "U", "B", "R", "G"]},
                    "description": "Color identity filter",
                },
                "color_exact": {
                    "type": "boolean",
                    "description": "Require exact color match",
                    "default": False,
                },
                "cmc": {
                    "type": "integer",
                    "description": "Exact mana value",
                },
                "cmc_min": {
                    "type": "integer",
                    "description": "Minimum mana value",
                },
                "cmc_max": {
                    "type": "integer",
                    "description": "Maximum mana value",
                },
                "keywords": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Required keyword abilities",
                },
                "set_code": {
                    "type": "string",
                    "description": "Set code filter",
                },
                "rarity": {
                    "type": "string",
                    "enum": ["common", "uncommon", "rare", "mythic"],
                    "description": "Rarity filter",
                },
                "format_legal": {
                    "type": "string",
                    "enum": [
                        "standard",
                        "historic",
                        "explorer",
                        "pioneer",
                        "modern",
                        "legacy",
                        "vintage",
                        "brawl",
                        "timeless",
                    ],
                    "description": "Format legality filter",
                },
                "power_min": {
                    "type": "integer",
                    "description": "Min power",
                },
                "power_max": {
                    "type": "integer",
                    "description": "Max power",
                },
                "toughness_min": {
                    "type": "integer",
                    "description": "Min toughness",
                },
                "toughness_max": {
                    "type": "integer",
                    "description": "Max toughness",
                },
                "min_quantity": {
                    "type": "integer",
                    "description": "Min owned quantity",
                    "default": 1,
                },
            },
            "required": [],
        },
    ),
    ToolDefinition(
        name="build_deck",
        description="Build a 60-card deck from user's collection around a theme.",
        parameters={
            "type": "object",
            "properties": {
                "theme": {
                    "type": "string",
                    "description": "Theme to build around",
                },
                "colors": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["W", "U", "B", "R", "G"]},
                    "description": "Color restriction",
                },
                "format": {
                    "type": "string",
                    "enum": ["standard", "historic", "explorer", "timeless", "brawl"],
                    "description": "Format for legality",
                    "default": "standard",
                },
                "include_cards": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Cards to include",
                },
            },
            "required": ["theme"],
        },
    ),
    ToolDefinition(
        name="find_synergies",
        description="Find cards that synergize with a specific card.",
        parameters={
            "type": "object",
            "properties": {
                "card_name": {
                    "type": "string",
                    "description": "Card to find synergies for",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Max results",
                    "default": 20,
                },
            },
            "required": ["card_name"],
        },
    ),
    ToolDefinition(
        name="export_to_arena",
        description="Convert a deck to MTG Arena import format.",
        parameters={
            "type": "object",
            "properties": {
                "cards": {
                    "type": "object",
                    "description": "Non-land cards {name: qty}",
                },
                "lands": {
                    "type": "object",
                    "description": "Land cards {name: qty}",
                },
                "deck_name": {
                    "type": "string",
                    "description": "Deck name",
                    "default": "Deck",
                },
            },
            "required": ["cards", "lands"],
        },
    ),
    ToolDefinition(
        name="improve_deck",
        description="Suggest improvements to a deck from user's collection.",
        parameters={
            "type": "object",
            "properties": {
                "deck_text": {
                    "type": "string",
                    "description": "Deck list in Arena format",
                },
                "max_suggestions": {
                    "type": "integer",
                    "description": "Max suggestions",
                    "default": 5,
                },
            },
            "required": ["deck_text"],
        },
    ),
    ToolDefinition(
        name="get_deck_assumptions",
        description="Analyze a deck's implicit assumptions and fragility.",
        parameters={
            "type": "object",
            "properties": {
                "format": {
                    "type": "string",
                    "description": "Game format",
                },
                "deck_name": {
                    "type": "string",
                    "description": "Deck name",
                },
            },
            "required": ["format", "deck_name"],
        },
    ),
    ToolDefinition(
        name="stress_deck_assumption",
        description="Apply stress to a deck and measure fragility impact.",
        parameters={
            "type": "object",
            "properties": {
                "format": {
                    "type": "string",
                    "description": "Game format",
                },
                "deck_name": {
                    "type": "string",
                    "description": "Deck name",
                },
                "stress_type": {
                    "type": "string",
                    "enum": ["underperform", "missing", "delayed", "hostile_meta"],
                    "description": "Type of stress",
                },
                "target": {
                    "type": "string",
                    "description": "Card name or 'all'",
                },
                "intensity": {
                    "type": "number",
                    "description": "Intensity 0.0-1.0",
                    "default": 0.5,
                },
            },
            "required": ["format", "deck_name", "stress_type", "target"],
        },
    ),
    ToolDefinition(
        name="find_deck_breaking_point",
        description="Find the weakest point in a deck.",
        parameters={
            "type": "object",
            "properties": {
                "format": {
                    "type": "string",
                    "description": "Game format",
                },
                "deck_name": {
                    "type": "string",
                    "description": "Deck name",
                },
            },
            "required": ["format", "deck_name"],
        },
    ),
]


async def get_deck_recommendations(
    session: AsyncSession,
    user_id: str,
    format_name: str,
    limit: int = 5,
    use_ml: bool = True,
) -> dict[str, Any]:
    """
    Get ranked deck recommendations for a user.

    Uses MLForge ML-based scoring when available, falling back to
    heuristic scoring if MLForge is unavailable.

    Data flow:
    1. Load user collection from database
    2. Load meta decks for format
    3. Extract features & call MLForge for ML scoring
    4. Blend ML score with completion/wildcard heuristics
    5. Return ranked recommendations

    Args:
        session: Database session
        user_id: User's ID
        format_name: Game format
        limit: Maximum recommendations to return
        use_ml: Whether to use MLForge scoring (default True)

    Returns:
        Dict with recommendations list and scoring metadata
    """
    # Get user's collection
    db_collection = await get_collection(session, user_id)
    collection = collection_to_model(db_collection) if db_collection else Collection()

    # Get meta decks for format
    db_decks = await get_meta_decks_by_format(session, format_name, limit=50)
    decks = [meta_deck_to_model(d) for d in db_decks]

    if not decks:
        return {"recommendations": [], "message": f"No decks found for {format_name}"}

    # Build rarity map from card database for accurate wildcard costs
    card_db = _get_card_db_safe()
    rarity_map: dict[str, str] = {
        name: data.get("rarity", "common") for name, data in card_db.items()
    }

    # Rank decks using ML scoring if enabled, otherwise basic scoring
    if use_ml:
        ranked = await rank_decks_with_ml(decks, collection, rarity_map)
        scoring_method = "ml_blended"
    else:
        ranked = rank_decks(decks, collection, rarity_map)
        scoring_method = "heuristic"

    recommendations = []
    for ranked_deck in ranked[:limit]:
        recommendations.append(
            {
                "deck_name": ranked_deck.deck.name,
                "archetype": ranked_deck.deck.archetype,
                "completion_percentage": round(ranked_deck.distance.completion_percentage * 100, 1),
                "missing_cards": ranked_deck.distance.missing_cards,
                "wildcard_cost": ranked_deck.distance.wildcard_cost.total(),
                "score": round(ranked_deck.score, 2),
                "can_build_now": ranked_deck.can_build_now,
            }
        )

    return {
        "recommendations": recommendations,
        "scoring_method": scoring_method,
        "format": format_name,
    }


async def calculate_deck_distance_tool(
    session: AsyncSession,
    user_id: str,
    format_name: str,
    deck_name: str,
) -> dict[str, Any]:
    """
    Calculate distance between collection and a specific deck.

    Args:
        session: Database session
        user_id: User's ID
        format_name: Game format
        deck_name: Name of deck to check

    Returns:
        Dict with distance information
    """
    # Get the deck
    db_deck = await get_meta_deck(session, deck_name, format_name)
    if db_deck is None:
        return {"error": f"Deck '{deck_name}' not found in {format_name}"}

    deck = meta_deck_to_model(db_deck)

    # Get user's collection
    db_collection = await get_collection(session, user_id)
    collection = collection_to_model(db_collection) if db_collection else Collection()

    # Calculate distance
    rarity_map: dict[str, str] = {}  # TODO: Load from Scryfall
    distance = calculate_deck_distance(deck, collection, rarity_map)

    return {
        "deck_name": deck.name,
        "archetype": deck.archetype,
        "completion_percentage": round(distance.completion_percentage * 100, 1),
        "owned_cards": distance.owned_cards,
        "missing_cards": distance.missing_cards,
        "is_complete": distance.is_complete,
        "wildcard_cost": {
            "common": distance.wildcard_cost.common,
            "uncommon": distance.wildcard_cost.uncommon,
            "rare": distance.wildcard_cost.rare,
            "mythic": distance.wildcard_cost.mythic,
            "total": distance.wildcard_cost.total(),
        },
        "missing_card_list": [
            {"name": name, "quantity": qty, "rarity": rarity}
            for name, qty, rarity in distance.missing_card_list[:10]
        ],
    }


async def get_collection_stats(
    session: AsyncSession,
    user_id: str,
) -> dict[str, Any]:
    """
    Get statistics about a user's collection.

    Args:
        session: Database session
        user_id: User's ID

    Returns:
        Dict with collection statistics
    """
    db_collection = await get_collection(session, user_id)

    if db_collection is None:
        return {
            "has_collection": False,
            "message": "No collection found. Import your collection first.",
        }

    collection = collection_to_model(db_collection)

    return {
        "has_collection": True,
        "total_cards": collection.total_cards(),
        "unique_cards": collection.unique_cards(),
    }


async def list_meta_decks(
    session: AsyncSession,
    format_name: str,
    limit: int = 10,
) -> dict[str, Any]:
    """
    List available meta decks for a format.

    Args:
        session: Database session
        format_name: Game format
        limit: Maximum decks to return

    Returns:
        Dict with deck list
    """
    db_decks = await get_meta_decks_by_format(session, format_name, limit=limit)

    if not db_decks:
        return {"decks": [], "message": f"No decks found for {format_name}"}

    decks = []
    for db_deck in db_decks:
        deck = meta_deck_to_model(db_deck)
        decks.append(
            {
                "name": deck.name,
                "archetype": deck.archetype,
                "win_rate": round((deck.win_rate or 0) * 100, 1),
                "meta_share": round((deck.meta_share or 0) * 100, 1),
                "card_count": deck.maindeck_count(),
            }
        )

    return {"format": format_name, "decks": decks}


async def search_collection_tool(
    session: AsyncSession,
    user_id: str,
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
) -> dict[str, Any]:
    """
    Search user's collection for cards matching criteria.

    Supports comprehensive queries like:
    - "how many black dragons?" -> card_type="Dragon", colors=["B"]
    - "what creatures have flying?" -> card_type="Creature", keywords=["flying"]
    - "show me my 3-drops" -> cmc=3
    - "what cards draw cards?" -> oracle_text="draw"
    - "what mono-red cards?" -> colors=["R"], color_exact=True
    - "what Standard-legal rares?" -> format_legal="standard", rarity="rare"
    """
    db_collection = await get_collection(session, user_id)

    if db_collection is None:
        # Terminal failure: no collection = cannot search
        # This is a KnownError that results in zero additional LLM calls
        raise KnownError(
            kind=FailureKind.NOT_FOUND,
            message=(
                "You don't have a collection imported yet. Please import one to search your cards."
            ),
            suggestion="Use the collection import endpoint to upload your collection.",
        )

    collection = collection_to_model(db_collection)

    results = search_collection(
        collection=collection,
        card_db=card_db,
        name_contains=name_contains,
        oracle_text=oracle_text,
        card_type=card_type,
        colors=colors,
        color_exact=color_exact,
        cmc=cmc,
        cmc_min=cmc_min,
        cmc_max=cmc_max,
        keywords=keywords,
        set_code=set_code,
        rarity=rarity,
        format_legal=format_legal,
        power_min=power_min,
        power_max=power_max,
        toughness_min=toughness_min,
        toughness_max=toughness_max,
        min_quantity=min_quantity,
    )

    # Calculate totals
    total_cards = sum(r.quantity for r in results)

    # Return structured data only - LLM formats the response
    return {
        "unique_count": len(results),
        "total_cards": total_cards,
        "results": [
            {
                "name": r.name,
                "quantity": r.quantity,
                "type": r.type_line,
                "colors": r.colors,
                "rarity": r.rarity,
                "set": r.set_code,
                "cmc": r.cmc,
                "keywords": r.keywords,
            }
            for r in results
        ],
    }


async def build_deck_tool(
    session: AsyncSession,
    user_id: str,
    theme: str,
    card_db: dict[str, dict[str, Any]],
    format_legality: dict[str, set[str]],
    colors: list[str] | None = None,
    format_name: str = "standard",
    include_cards: list[str] | None = None,
    *,
    format_explicit: bool = False,
    colors_explicit: bool = False,
) -> dict[str, Any]:
    """
    Build a deck from user's collection around a theme.

    Args:
        session: Database session
        user_id: User's ID
        theme: Theme to build around
        card_db: Card database from Scryfall
        format_legality: Legal cards per format
        colors: Optional color restriction
        format_name: Format for legality
        include_cards: Cards that must be included
        format_explicit: Whether format was explicitly provided (not defaulted)
        colors_explicit: Whether colors were explicitly provided (not defaulted)

    Returns:
        Dict with built deck information
    """
    db_collection = await get_collection(session, user_id)

    if db_collection is None:
        # Terminal failure: no collection = no deck building
        # This is a KnownError that results in zero LLM calls
        raise KnownError(
            kind=FailureKind.NOT_FOUND,
            message="You don't have a collection imported yet. Please import one to build decks.",
            suggestion="Use the collection import endpoint to upload your MTG Arena collection.",
        )

    collection = collection_to_model(db_collection)

    request = DeckBuildRequest(
        theme=theme,
        colors=colors,
        format=format_name,
        include_cards=include_cards,
    )

    deck = build_deck(request, collection, card_db, format_legality)

    # Generate assumptions section for UX transparency (PR 6)
    defaults = BuildDeckDefaults(
        format_defaulted=not format_explicit,
        colors_defaulted=not colors_explicit,
    )
    assumptions_section = format_build_deck_assumptions(
        format_name=format_name,
        colors=colors,
        defaults=defaults,
    )

    # Return structured data only - LLM formats the response
    return {
        "success": True,
        "deck_name": deck.name,
        "total_cards": deck.total_cards,
        "colors": list(deck.colors),
        "theme_cards": deck.theme_cards,
        "support_cards": deck.support_cards,
        "lands": deck.lands,
        "cards": deck.cards,
        "notes": deck.notes,
        "warnings": deck.warnings,
        "assumptions": assumptions_section,
    }


async def find_synergies_tool(
    session: AsyncSession,
    user_id: str,
    card_name: str,
    card_db: dict[str, dict[str, Any]],
    format_name: str = "standard",
    max_results: int = 20,
) -> dict[str, Any]:
    """
    Find cards that synergize with a specific card.

    IMPORTANT: Only cards that are BOTH owned AND format-legal are returned.
    This is a hard boundary that cannot be bypassed.

    Args:
        session: Database session
        user_id: User's ID
        card_name: Card to find synergies for
        card_db: Card database from Scryfall
        format_name: Target format for legality checking (default: "standard")
        max_results: Maximum synergistic cards to return

    Returns:
        Dict with synergy results
    """
    db_collection = await get_collection(session, user_id)

    if db_collection is None:
        # Terminal failure: no collection = cannot find synergies
        # This is a KnownError that results in zero additional LLM calls
        raise KnownError(
            kind=FailureKind.NOT_FOUND,
            message=(
                "You don't have a collection imported yet. Please import one to find synergies."
            ),
            suggestion="Use the collection import endpoint to upload your collection.",
        )

    collection = collection_to_model(db_collection)

    # Get format legality - REQUIRED for hard boundary enforcement
    format_legality = _get_format_legality_safe()
    format_legal_cards = format_legality.get(format_name.lower(), set())

    if not format_legal_cards:
        return {
            "found": False,
            "message": (
                f"Unknown format '{format_name}'. Supported: standard, historic, "
                "explorer, pioneer, modern, legacy, vintage, brawl, timeless."
            ),
        }

    result = find_synergies(
        card_name,
        collection,
        card_db,
        format_name,
        format_legal_cards,
        max_results,
    )

    if result is None:
        return {
            "found": False,
            "message": f"Card '{card_name}' not found in database.",
        }

    # Return structured data only - LLM formats the response
    return {
        "found": True,
        "source_card": result.source_card,
        "synergy_type": result.synergy_type,
        "synergistic_cards": [
            {"name": name, "quantity": qty, "reason": reason}
            for name, qty, reason in result.synergistic_cards
        ],
        "count": len(result.synergistic_cards),
    }


async def export_to_arena_tool(
    cards: dict[str, int],
    lands: dict[str, int],
    card_db: dict[str, dict[str, Any]],
    deck_name: str = "Deck",
) -> dict[str, Any]:
    """
    Export a deck to MTG Arena import format.

    Uses the Arena Sanitizer to ensure all printings are Arena-valid.
    If any card has an invalid printing that cannot be canonicalized,
    the entire export fails with an explicit error message.

    Args:
        cards: Non-land cards {name: quantity}
        lands: Land cards {name: quantity}
        card_db: Card database from Scryfall
        deck_name: Name for the deck

    Returns:
        Dict with arena_format export string, or failure message
    """
    from forgebreaker.services.arena_sanitizer import ArenaSanitizationError

    # Create a minimal BuiltDeck for export
    deck = BuiltDeck(
        name=deck_name,
        cards=cards,
        total_cards=sum(cards.values()) + sum(lands.values()),
        colors=set(),
        theme_cards=[],
        support_cards=[],
        lands=lands,
    )

    try:
        arena_export = export_deck_to_arena(deck, card_db)
    except ArenaSanitizationError as e:
        # Hard failure - do not return partial output
        # Extract attributes safely - different error types have different attrs
        card_name = getattr(e, "card_name", "Unknown")
        set_code = getattr(e, "set_code", "Unknown")
        reason = getattr(e, "reason", str(e))

        return {
            "success": False,
            "error": "arena_sanitization_failed",
            "message": (
                f"Deck export failed: '{card_name}' cannot be imported into MTG Arena. "
                f"The printing from set '{set_code}' is not accepted by Arena. "
                f"Reason: {reason}"
            ),
            "card_name": card_name,
            "invalid_set": set_code,
        }

    return {
        "success": True,
        "deck_name": deck_name,
        "total_cards": deck.total_cards,
        "arena_format": arena_export,
    }


async def improve_deck_tool(
    session: AsyncSession,
    user_id: str,
    deck_text: str,
    card_db: dict[str, dict[str, Any]],
    format_name: str = "standard",
    max_suggestions: int = 5,
) -> dict[str, Any]:
    """
    Analyze a deck and suggest improvements from user's collection.

    IMPORTANT: Only cards that are BOTH owned AND format-legal can be suggested.
    This is a hard boundary that cannot be bypassed.

    Args:
        session: Database session
        user_id: User's ID
        deck_text: Arena-format deck list
        card_db: Card database from Scryfall
        format_name: Target format for legality checking (default: "standard")
        max_suggestions: Maximum suggestions to return

    Returns:
        Dict with analysis and suggestions
    """
    db_collection = await get_collection(session, user_id)

    if db_collection is None:
        # Terminal failure: no collection = cannot suggest improvements
        # This is a KnownError that results in zero additional LLM calls
        raise KnownError(
            kind=FailureKind.NOT_FOUND,
            message=(
                "You don't have a collection imported yet. "
                "Please import one to get deck improvements."
            ),
            suggestion="Use the collection import endpoint to upload your collection.",
        )

    collection = collection_to_model(db_collection)

    # Get format legality - REQUIRED for hard boundary enforcement
    format_legality = _get_format_legality_safe()
    format_legal_cards = format_legality.get(format_name.lower(), set())

    if not format_legal_cards:
        return {
            "success": False,
            "message": (
                f"Unknown format '{format_name}'. Supported: standard, historic, "
                "explorer, pioneer, modern, legacy, vintage, brawl, timeless."
            ),
        }

    analysis = analyze_and_improve_deck(
        deck_text=deck_text,
        collection=collection,
        card_db=card_db,
        format_name=format_name,
        format_legal_cards=format_legal_cards,
        max_suggestions=max_suggestions,
    )

    # Return structured data only - LLM formats the response
    return {
        "success": True,
        "total_cards": analysis.total_cards,
        "colors": list(analysis.colors),
        "creature_count": analysis.creature_count,
        "spell_count": analysis.spell_count,
        "land_count": analysis.land_count,
        "suggestions": [
            {
                "remove": f"{s.remove_quantity}x {s.remove_card}",
                "add": f"{s.add_quantity}x {s.add_card}",
                "reason": s.reason,
            }
            for s in analysis.suggestions
        ],
        "general_advice": analysis.general_advice,
        "warnings": analysis.warnings,
    }


async def get_deck_assumptions_tool(
    session: AsyncSession,
    format_name: str,
    deck_name: str,
) -> dict[str, Any]:
    """
    Analyze a deck to surface its implicit assumptions.

    Args:
        session: Database session
        format_name: Game format
        deck_name: Name of the deck to analyze

    Returns:
        Dict with deck assumptions and fragility analysis
    """
    # Get the deck
    db_deck = await get_meta_deck(session, deck_name, format_name)
    if db_deck is None:
        return {"error": f"Deck '{deck_name}' not found in {format_name}"}

    deck = meta_deck_to_model(db_deck)
    card_db = _get_card_db_safe()

    # Surface assumptions for player examination
    assumption_set = surface_assumptions(deck, card_db)

    return {
        "deck_name": assumption_set.deck_name,
        "archetype": assumption_set.archetype,
        "overall_fragility": round(assumption_set.overall_fragility, 2),
        "fragility_explanation": assumption_set.fragility_explanation,
        "assumptions": [
            {
                "name": a.name,
                "category": a.category.value,
                "description": a.description,
                "observed_value": a.observed_value,
                "typical_range": list(a.typical_range),
                "health": a.health.value,
                "explanation": a.explanation,
                "adjustable": a.adjustable,
            }
            for a in assumption_set.assumptions
        ],
        "warnings": [
            {
                "name": a.name,
                "description": a.description,
                "explanation": a.explanation,
            }
            for a in assumption_set.get_warnings()
        ],
    }


async def stress_deck_assumption_tool(
    session: AsyncSession,
    format_name: str,
    deck_name: str,
    stress_type: str,
    target: str,
    intensity: float = 0.5,
) -> dict[str, Any]:
    """
    Apply stress to a deck and measure the impact.

    Args:
        session: Database session
        format_name: Game format
        deck_name: Name of the deck to stress
        stress_type: Type of stress to apply
        target: What to stress (card name or 'all')
        intensity: Stress intensity 0.0-1.0

    Returns:
        Dict with stress results and recommendations
    """
    # Get the deck
    db_deck = await get_meta_deck(session, deck_name, format_name)
    if db_deck is None:
        return {"error": f"Deck '{deck_name}' not found in {format_name}"}

    deck = meta_deck_to_model(db_deck)
    card_db = _get_card_db_safe()

    # Parse stress type
    try:
        stress_type_enum = StressType(stress_type)
    except ValueError:
        return {
            "error": f"Invalid stress type '{stress_type}'. "
            f"Valid types: {', '.join(t.value for t in StressType)}"
        }

    # Create and apply scenario
    scenario = StressScenario(
        stress_type=stress_type_enum,
        target=target,
        intensity=intensity,
        description=f"Stress test: {stress_type} on {target}",
    )

    result = apply_stress(deck, card_db, scenario)

    return {
        "deck_name": result.deck_name,
        "stress_type": result.scenario.stress_type.value,
        "target": result.scenario.target,
        "intensity": result.scenario.intensity,
        "original_fragility": round(result.original_fragility, 2),
        "stressed_fragility": round(result.stressed_fragility, 2),
        "fragility_change": round(result.fragility_change(), 2),
        "breaking_point": result.breaking_point,
        "affected_assumptions": [
            {
                "name": a.name,
                "original_value": a.original_value,
                "stressed_value": a.stressed_value,
                "original_health": a.original_health,
                "stressed_health": a.stressed_health,
                "change_explanation": a.change_explanation,
            }
            for a in result.affected_assumptions
        ],
        "explanation": result.explanation,
        "recommendations": result.recommendations,
    }


async def find_deck_breaking_point_tool(
    session: AsyncSession,
    format_name: str,
    deck_name: str,
) -> dict[str, Any]:
    """
    Find the weakest point in a deck.

    Args:
        session: Database session
        format_name: Game format
        deck_name: Name of the deck to analyze

    Returns:
        Dict with breaking point analysis
    """
    # Get the deck
    db_deck = await get_meta_deck(session, deck_name, format_name)
    if db_deck is None:
        return {"error": f"Deck '{deck_name}' not found in {format_name}"}

    deck = meta_deck_to_model(db_deck)
    card_db = _get_card_db_safe()

    analysis = find_breaking_point(deck, card_db)

    breaking_scenario = None
    if analysis.breaking_scenario:
        breaking_scenario = {
            "stress_type": analysis.breaking_scenario.stress_type.value,
            "target": analysis.breaking_scenario.target,
            "intensity": analysis.breaking_scenario.intensity,
        }

    return {
        "deck_name": analysis.deck_name,
        "weakest_assumption": analysis.weakest_assumption,
        "breaking_intensity": round(analysis.breaking_intensity, 2),
        "resilience_score": round(analysis.resilience_score, 2),
        "breaking_scenario": breaking_scenario,
        "explanation": analysis.explanation,
    }


async def execute_tool(
    session: AsyncSession,
    tool_name: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    """
    Execute an MCP tool by name.

    Args:
        session: Database session
        tool_name: Name of the tool to execute
        arguments: Tool arguments

    Returns:
        Tool result as dict

    Raises:
        ValueError: If tool name is unknown
    """
    if tool_name == "get_deck_recommendations":
        return await get_deck_recommendations(
            session,
            user_id=arguments["user_id"],
            format_name=arguments["format"],
            limit=arguments.get("limit", 5),
        )
    elif tool_name == "calculate_deck_distance":
        return await calculate_deck_distance_tool(
            session,
            user_id=arguments["user_id"],
            format_name=arguments["format"],
            deck_name=arguments["deck_name"],
        )
    elif tool_name == "get_collection_stats":
        return await get_collection_stats(
            session,
            user_id=arguments["user_id"],
        )
    elif tool_name == "list_meta_decks":
        return await list_meta_decks(
            session,
            format_name=arguments["format"],
            limit=arguments.get("limit", 10),
        )
    elif tool_name == "search_collection":
        card_db = _get_card_db_safe()
        return await search_collection_tool(
            session,
            user_id=arguments["user_id"],
            card_db=card_db,
            # Name and text filters
            name_contains=arguments.get("name_contains"),
            oracle_text=arguments.get("oracle_text"),
            # Type filters
            card_type=arguments.get("card_type"),
            # Color filters
            colors=arguments.get("colors"),
            color_exact=arguments.get("color_exact", False),
            # Mana cost filters
            cmc=arguments.get("cmc"),
            cmc_min=arguments.get("cmc_min"),
            cmc_max=arguments.get("cmc_max"),
            # Keyword filters
            keywords=arguments.get("keywords"),
            # Set and rarity filters
            set_code=arguments.get("set_code"),
            rarity=arguments.get("rarity"),
            # Format legality
            format_legal=arguments.get("format_legal"),
            # Creature stat filters
            power_min=arguments.get("power_min"),
            power_max=arguments.get("power_max"),
            toughness_min=arguments.get("toughness_min"),
            toughness_max=arguments.get("toughness_max"),
            # Quantity filters
            min_quantity=arguments.get("min_quantity", 1),
        )
    elif tool_name == "build_deck":
        card_db = _get_card_db_safe()
        format_legality = _get_format_legality_safe()
        return await build_deck_tool(
            session,
            user_id=arguments["user_id"],
            theme=arguments["theme"],
            card_db=card_db,
            format_legality=format_legality,
            colors=arguments.get("colors"),
            format_name=arguments.get("format", "standard"),
            include_cards=arguments.get("include_cards"),
            format_explicit="format" in arguments,
            colors_explicit="colors" in arguments,
        )
    elif tool_name == "find_synergies":
        card_db = _get_card_db_safe()
        return await find_synergies_tool(
            session,
            user_id=arguments["user_id"],
            card_name=arguments["card_name"],
            card_db=card_db,
            max_results=arguments.get("max_results", 20),
        )
    elif tool_name == "export_to_arena":
        card_db = _get_card_db_safe()
        return await export_to_arena_tool(
            cards=arguments["cards"],
            lands=arguments["lands"],
            card_db=card_db,
            deck_name=arguments.get("deck_name", "Deck"),
        )
    elif tool_name == "improve_deck":
        card_db = _get_card_db_safe()
        return await improve_deck_tool(
            session,
            user_id=arguments["user_id"],
            deck_text=arguments["deck_text"],
            card_db=card_db,
            max_suggestions=arguments.get("max_suggestions", 5),
        )
    elif tool_name == "get_deck_assumptions":
        return await get_deck_assumptions_tool(
            session,
            format_name=arguments["format"],
            deck_name=arguments["deck_name"],
        )
    elif tool_name == "stress_deck_assumption":
        return await stress_deck_assumption_tool(
            session,
            format_name=arguments["format"],
            deck_name=arguments["deck_name"],
            stress_type=arguments["stress_type"],
            target=arguments["target"],
            intensity=arguments.get("intensity", 0.5),
        )
    elif tool_name == "find_deck_breaking_point":
        return await find_deck_breaking_point_tool(
            session,
            format_name=arguments["format"],
            deck_name=arguments["deck_name"],
        )
    else:
        raise ValueError(f"Unknown tool: {tool_name}")
