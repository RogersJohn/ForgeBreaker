"""
ForgeBreaker services.

Business logic for deck building and collection management.
"""

from forgebreaker.services.collection_search import (
    CardSearchResult,
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
from forgebreaker.services.deck_improver import (
    CardSuggestion,
    DeckAnalysis,
    analyze_and_improve_deck,
    format_deck_analysis,
)
from forgebreaker.services.synergy_finder import (
    SynergyResult,
    find_synergies,
    format_synergy_results,
)

__all__ = [
    "CardSearchResult",
    "format_search_results",
    "search_collection",
    "BuiltDeck",
    "DeckBuildRequest",
    "build_deck",
    "export_deck_to_arena",
    "format_built_deck",
    "SynergyResult",
    "find_synergies",
    "format_synergy_results",
    "CardSuggestion",
    "DeckAnalysis",
    "analyze_and_improve_deck",
    "format_deck_analysis",
]
