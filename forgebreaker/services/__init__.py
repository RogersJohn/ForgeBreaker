"""
ForgeBreaker services.

Business logic for deck building and collection management.
"""

from forgebreaker.services.collection_search import (
    CardSearchResult,
    format_search_results,
    search_collection,
)

__all__ = [
    "CardSearchResult",
    "format_search_results",
    "search_collection",
]
