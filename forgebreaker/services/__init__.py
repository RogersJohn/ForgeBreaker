"""
ForgeBreaker services.

Business logic for deck building and collection management.
"""

from forgebreaker.services.arena_formatter import format_deck_for_arena
from forgebreaker.services.arena_parser import (
    ArenaParseError,
    ArenaParser,
    ParsedCardEntry,
    ParsedDeckStructure,
    ParsedSection,
    parse_arena_deck,
)
from forgebreaker.services.arena_sanitizer import (
    # The sanitizer class (THE trust boundary)
    ArenaDeckSanitizer,
    ArenaImportabilityError,
    # Exception hierarchy
    ArenaSanitizationError,
    DuplicateCardError,
    InvalidCardNameError,
    InvalidCollectorNumberError,
    InvalidDeckStructureError,
    InvalidQuantityError,
    InvalidRawInputError,
    InvalidSetCodeError,
    # Sanitized output structures
    SanitizedCard,
    SanitizedDeck,
    # Primary entry point for raw Arena text
    sanitize_arena_deck_input,
    # Dict-based sanitization (for internal use)
    sanitize_deck_for_arena,
    validate_arena_export,
)
from forgebreaker.services.card_name_guard import (
    CardNameLeakageError,
    GuardResult,
    create_refusal_response,
    extract_potential_card_names,
    guard_output,
    validate_output_card_names,
)
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
from forgebreaker.services.demo_collection import (
    DemoCollectionError,
    demo_collection_available,
    get_demo_cards,
    get_demo_collection,
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
    # Arena parser (syntax extraction only)
    "ArenaParser",
    "ArenaParseError",
    "ParsedCardEntry",
    "ParsedSection",
    "ParsedDeckStructure",
    "parse_arena_deck",
    # Arena sanitization - THE trust boundary
    "ArenaDeckSanitizer",
    "sanitize_arena_deck_input",
    # Exception hierarchy
    "ArenaSanitizationError",
    "ArenaImportabilityError",
    "DuplicateCardError",
    "InvalidCardNameError",
    "InvalidQuantityError",
    "InvalidSetCodeError",
    "InvalidCollectorNumberError",
    "InvalidDeckStructureError",
    "InvalidRawInputError",
    # Sanitized output structures
    "SanitizedCard",
    "SanitizedDeck",
    # Arena formatter (output rendering)
    "format_deck_for_arena",
    # Dict-based API (for internal use)
    "sanitize_deck_for_arena",
    "validate_arena_export",
    # Demo collection
    "DemoCollectionError",
    "get_demo_collection",
    "get_demo_cards",
    "demo_collection_available",
    # Card name guard - output barrier
    "CardNameLeakageError",
    "GuardResult",
    "create_refusal_response",
    "extract_potential_card_names",
    "guard_output",
    "validate_output_card_names",
]
