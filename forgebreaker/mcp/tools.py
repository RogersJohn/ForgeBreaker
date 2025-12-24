"""
MCP tool definitions for Claude chat integration.

Defines tools that Claude can call to help users with deck recommendations
and collection management.
"""

import logging
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from forgebreaker.analysis.distance import calculate_deck_distance
from forgebreaker.analysis.ranker import rank_decks
from forgebreaker.db import (
    collection_to_model,
    get_collection,
    get_meta_deck,
    get_meta_decks_by_format,
    meta_deck_to_model,
)
from forgebreaker.models.collection import Collection
from forgebreaker.services.card_database import (
    get_card_database,
    get_format_legality,
)
from forgebreaker.services.collection_search import (
    format_search_results,
    search_collection,
)
from forgebreaker.services.deck_builder import (
    BuiltDeck,
    DeckBuildRequest,
    build_deck,
    export_deck_to_arena,
    format_built_deck,
)
from forgebreaker.services.synergy_finder import (
    find_synergies,
    format_synergy_results,
)

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
        description=(
            "Get ranked deck recommendations based on the user's collection. "
            "Returns decks sorted by how easy they are to build with current cards."
        ),
        parameters={
            "type": "object",
            "properties": {
                "user_id": {
                    "type": "string",
                    "description": "The user's ID",
                },
                "format": {
                    "type": "string",
                    "description": "Game format (standard, historic, explorer, etc.)",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of recommendations to return",
                    "default": 5,
                },
            },
            "required": ["user_id", "format"],
        },
    ),
    ToolDefinition(
        name="calculate_deck_distance",
        description=(
            "Calculate how far a user's collection is from completing a specific deck. "
            "Returns missing cards, wildcard costs, and completion percentage."
        ),
        parameters={
            "type": "object",
            "properties": {
                "user_id": {
                    "type": "string",
                    "description": "The user's ID",
                },
                "format": {
                    "type": "string",
                    "description": "Game format the deck belongs to",
                },
                "deck_name": {
                    "type": "string",
                    "description": "Name of the deck to check",
                },
            },
            "required": ["user_id", "format", "deck_name"],
        },
    ),
    ToolDefinition(
        name="get_collection_stats",
        description=(
            "Get statistics about a user's card collection. Returns total cards and unique cards."
        ),
        parameters={
            "type": "object",
            "properties": {
                "user_id": {
                    "type": "string",
                    "description": "The user's ID",
                },
            },
            "required": ["user_id"],
        },
    ),
    ToolDefinition(
        name="list_meta_decks",
        description=(
            "List available meta decks for a format. "
            "Returns deck names, archetypes, win rates, and meta share."
        ),
        parameters={
            "type": "object",
            "properties": {
                "format": {
                    "type": "string",
                    "description": "Game format (standard, historic, explorer, etc.)",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of decks to return",
                    "default": 10,
                },
            },
            "required": ["format"],
        },
    ),
    ToolDefinition(
        name="search_collection",
        description=(
            "Search the user's card collection for cards matching specific criteria. "
            "Use when the user asks about cards they own, like 'do I have any goblins?' "
            "or 'show me my enchantments' or 'what shrines do I own?'"
        ),
        parameters={
            "type": "object",
            "properties": {
                "user_id": {
                    "type": "string",
                    "description": "The user's ID",
                },
                "name_contains": {
                    "type": "string",
                    "description": "Find cards with this text in the name (case-insensitive)",
                },
                "card_type": {
                    "type": "string",
                    "description": "Filter by card type (Creature, Enchantment, Instant, etc.)",
                },
                "colors": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["W", "U", "B", "R", "G"]},
                    "description": "Filter by color (W=White, U=Blue, B=Black, R=Red, G=Green)",
                },
                "set_code": {
                    "type": "string",
                    "description": "Filter by set code (e.g., 'DMU', 'M21', 'FDN')",
                },
                "rarity": {
                    "type": "string",
                    "enum": ["common", "uncommon", "rare", "mythic"],
                    "description": "Filter by rarity",
                },
                "min_quantity": {
                    "type": "integer",
                    "description": "Only show cards owned in at least this quantity",
                    "default": 1,
                },
            },
            "required": ["user_id"],
        },
    ),
    ToolDefinition(
        name="build_deck",
        description=(
            "Build a custom deck from the user's collection around a theme. "
            "Use when the user asks to build a deck around a card type, creature type, "
            "or keyword like 'build me a shrine deck' or 'make a goblin deck'. "
            "This builds a COMPLETE 60-card deck using ONLY cards they own."
        ),
        parameters={
            "type": "object",
            "properties": {
                "user_id": {
                    "type": "string",
                    "description": "The user's ID",
                },
                "theme": {
                    "type": "string",
                    "description": (
                        "Card name, type, or keyword to build around. "
                        "Examples: 'Shrine', 'Goblin', 'sacrifice', 'graveyard'"
                    ),
                },
                "colors": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["W", "U", "B", "R", "G"]},
                    "description": (
                        "Optional color restriction. "
                        "If not specified, colors are determined from theme cards."
                    ),
                },
                "format": {
                    "type": "string",
                    "enum": ["standard", "historic", "explorer", "timeless", "brawl"],
                    "description": "Format for legality checking",
                    "default": "standard",
                },
                "include_cards": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Specific cards that MUST be included in the deck",
                },
            },
            "required": ["user_id", "theme"],
        },
    ),
    ToolDefinition(
        name="find_synergies",
        description=(
            "Find cards in the user's collection that synergize with a specific card. "
            "Use when the user asks 'what cards work well with X?' or 'find synergies for X'. "
            "Returns cards that share mechanical synergies like sacrifice, graveyard, tokens, etc."
        ),
        parameters={
            "type": "object",
            "properties": {
                "user_id": {
                    "type": "string",
                    "description": "The user's ID",
                },
                "card_name": {
                    "type": "string",
                    "description": "The card to find synergies for",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of synergistic cards to return",
                    "default": 20,
                },
            },
            "required": ["user_id", "card_name"],
        },
    ),
    ToolDefinition(
        name="export_to_arena",
        description=(
            "Convert a deck to MTG Arena import format. "
            "Use this AFTER building a deck with build_deck. "
            "Returns text that can be copy-pasted directly into Arena's import function."
        ),
        parameters={
            "type": "object",
            "properties": {
                "cards": {
                    "type": "object",
                    "description": (
                        "The deck's non-land cards as {card_name: quantity}. "
                        "Get this from the 'cards' field of a build_deck response."
                    ),
                },
                "lands": {
                    "type": "object",
                    "description": (
                        "The deck's lands as {land_name: quantity}. "
                        "Get this from the 'lands' field of a build_deck response."
                    ),
                },
                "deck_name": {
                    "type": "string",
                    "description": "Name for the deck (optional)",
                    "default": "Deck",
                },
            },
            "required": ["cards", "lands"],
        },
    ),
]


async def get_deck_recommendations(
    session: AsyncSession,
    user_id: str,
    format_name: str,
    limit: int = 5,
) -> dict[str, Any]:
    """
    Get ranked deck recommendations for a user.

    Args:
        session: Database session
        user_id: User's ID
        format_name: Game format
        limit: Maximum recommendations to return

    Returns:
        Dict with recommendations list
    """
    # Get user's collection
    db_collection = await get_collection(session, user_id)
    collection = collection_to_model(db_collection) if db_collection else Collection()

    # Get meta decks for format
    db_decks = await get_meta_decks_by_format(session, format_name, limit=50)
    decks = [meta_deck_to_model(d) for d in db_decks]

    if not decks:
        return {"recommendations": [], "message": f"No decks found for {format_name}"}

    # Rank decks by buildability
    rarity_map: dict[str, str] = {}  # TODO: Load from Scryfall
    ranked = rank_decks(decks, collection, rarity_map)

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
            }
        )

    return {"recommendations": recommendations}


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
    name_contains: str | None = None,
    card_type: str | None = None,
    colors: list[str] | None = None,
    set_code: str | None = None,
    rarity: str | None = None,
    min_quantity: int = 1,
) -> dict[str, Any]:
    """
    Search user's collection for cards matching criteria.

    Args:
        session: Database session
        user_id: User's ID
        card_db: Card database from Scryfall
        name_contains: Filter by name substring
        card_type: Filter by type line
        colors: Filter by colors
        set_code: Filter by set
        rarity: Filter by rarity
        min_quantity: Minimum quantity owned

    Returns:
        Dict with search results
    """
    db_collection = await get_collection(session, user_id)

    if db_collection is None:
        return {
            "results": [],
            "message": "No collection found. Import your collection first.",
        }

    collection = collection_to_model(db_collection)

    results = search_collection(
        collection=collection,
        card_db=card_db,
        name_contains=name_contains,
        card_type=card_type,
        colors=colors,
        set_code=set_code,
        rarity=rarity,
        min_quantity=min_quantity,
    )

    formatted = format_search_results(results)

    return {
        "count": len(results),
        "results": [
            {
                "name": r.name,
                "quantity": r.quantity,
                "type": r.type_line,
                "colors": r.colors,
                "rarity": r.rarity,
                "set": r.set_code,
            }
            for r in results
        ],
        "formatted": formatted,
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

    Returns:
        Dict with built deck information
    """
    db_collection = await get_collection(session, user_id)

    if db_collection is None:
        return {
            "success": False,
            "message": "No collection found. Import your collection first.",
        }

    collection = collection_to_model(db_collection)

    request = DeckBuildRequest(
        theme=theme,
        colors=colors,
        format=format_name,
        include_cards=include_cards,
    )

    deck = build_deck(request, collection, card_db, format_legality)
    formatted = format_built_deck(deck)

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
        "formatted": formatted,
    }


async def find_synergies_tool(
    session: AsyncSession,
    user_id: str,
    card_name: str,
    card_db: dict[str, dict[str, Any]],
    max_results: int = 20,
) -> dict[str, Any]:
    """
    Find cards that synergize with a specific card.

    Args:
        session: Database session
        user_id: User's ID
        card_name: Card to find synergies for
        card_db: Card database from Scryfall
        max_results: Maximum synergistic cards to return

    Returns:
        Dict with synergy results
    """
    db_collection = await get_collection(session, user_id)

    if db_collection is None:
        return {
            "found": False,
            "message": "No collection found. Import your collection first.",
        }

    collection = collection_to_model(db_collection)

    result = find_synergies(card_name, collection, card_db, max_results)

    if result is None:
        return {
            "found": False,
            "message": f"Card '{card_name}' not found in database.",
        }

    formatted = format_synergy_results(result)

    return {
        "found": True,
        "source_card": result.source_card,
        "synergy_type": result.synergy_type,
        "synergistic_cards": [
            {"name": name, "quantity": qty, "reason": reason}
            for name, qty, reason in result.synergistic_cards
        ],
        "count": len(result.synergistic_cards),
        "formatted": formatted,
    }


async def export_to_arena_tool(
    cards: dict[str, int],
    lands: dict[str, int],
    card_db: dict[str, dict[str, Any]],
    deck_name: str = "Deck",
) -> dict[str, Any]:
    """
    Export a deck to MTG Arena import format.

    Args:
        cards: Non-land cards {name: quantity}
        lands: Land cards {name: quantity}
        card_db: Card database from Scryfall
        deck_name: Name for the deck

    Returns:
        Dict with arena_format export string
    """
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

    arena_export = export_deck_to_arena(deck, card_db)

    return {
        "success": True,
        "deck_name": deck_name,
        "total_cards": deck.total_cards,
        "arena_format": arena_export,
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
            name_contains=arguments.get("name_contains"),
            card_type=arguments.get("card_type"),
            colors=arguments.get("colors"),
            set_code=arguments.get("set_code"),
            rarity=arguments.get("rarity"),
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
    else:
        raise ValueError(f"Unknown tool: {tool_name}")
