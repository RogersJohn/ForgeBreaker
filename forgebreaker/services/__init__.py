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
from forgebreaker.services.canonical_card_resolver import (
    CanonicalCardResolver,
    ResolutionEvent,
    ResolutionReason,
    ResolutionReport,
    ResolutionResult,
)
from forgebreaker.services.card_name_guard import (
    CardNameLeakageError,
    GuardResult,
    canonical_card_key,
    create_refusal_response,
    extract_potential_card_names,
    get_guard_stats,
    guard_output,
    reset_guard_stats,
    validate_output_card_names,
)
from forgebreaker.services.clarification import (
    create_policy,
    evaluate_clarification,
    get_next_clarification,
    record_clarification,
    resolve_intent_with_policy,
    should_ask_clarification,
)
from forgebreaker.services.collection_sanitizer import (
    SanitizationResult,
    sanitize_collection,
    try_sanitize_collection,
)
from forgebreaker.services.collection_search import (
    CardSearchResult,
    format_search_results,
    search_collection,
)
from forgebreaker.services.cost_controls import (
    DailyBudgetExceededError,
    DailyUsageTracker,
    LLMDisabledError,
    RateLimitExceededError,
    check_llm_enabled,
    enforce_cost_controls,
    get_usage_tracker,
    reset_usage_tracker,
)
from forgebreaker.services.deck_builder import (
    BuiltDeck,
    DeckBuildRequest,
    build_deck,
    enforce_deck_size,
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
from forgebreaker.services.sample_deck import get_sample_deck
from forgebreaker.services.synergy_finder import (
    SynergyResult,
    find_synergies,
    format_synergy_results,
)

__all__ = [
    # Canonical card resolution (collection import trust boundary)
    "CanonicalCardResolver",
    "ResolutionEvent",
    "ResolutionReason",
    "ResolutionReport",
    "ResolutionResult",
    # Collection search
    "CardSearchResult",
    "format_search_results",
    "search_collection",
    "BuiltDeck",
    "DeckBuildRequest",
    "build_deck",
    "enforce_deck_size",
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
    # Sample deck
    "get_sample_deck",
    # Collection sanitization (import-time)
    "SanitizationResult",
    "sanitize_collection",
    "try_sanitize_collection",
    # Card name guard - output barrier
    "CardNameLeakageError",
    "GuardResult",
    "canonical_card_key",
    "create_refusal_response",
    "extract_potential_card_names",
    "get_guard_stats",
    "guard_output",
    "reset_guard_stats",
    "validate_output_card_names",
    # Clarification policy
    "create_policy",
    "evaluate_clarification",
    "get_next_clarification",
    "record_clarification",
    "resolve_intent_with_policy",
    "should_ask_clarification",
    # Cost controls
    "DailyBudgetExceededError",
    "DailyUsageTracker",
    "LLMDisabledError",
    "RateLimitExceededError",
    "check_llm_enabled",
    "enforce_cost_controls",
    "get_usage_tracker",
    "reset_usage_tracker",
]
