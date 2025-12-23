"""MCP tool definitions for Claude integration."""

from forgebreaker.mcp.tools import (
    TOOL_DEFINITIONS,
    calculate_deck_distance_tool,
    execute_tool,
    get_collection_stats,
    get_deck_recommendations,
    list_meta_decks,
)

__all__ = [
    "TOOL_DEFINITIONS",
    "calculate_deck_distance_tool",
    "execute_tool",
    "get_collection_stats",
    "get_deck_recommendations",
    "list_meta_decks",
]
