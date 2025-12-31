"""
Collection sanitization service.

Sanitizes user collections at import time by removing cards
not present in the card database. This ensures that:
- collection_cards ⊆ card_database_cards
- Deck-building never fails due to collection/DB mismatch

INVARIANT: Collections are sanitized ONCE at import time,
not at request time. This is a data hygiene operation.
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class SanitizationResult:
    """Result of sanitizing a collection."""

    sanitized_cards: dict[str, int]
    """Cards that passed validation (present in card database)."""

    removed_cards: dict[str, int]
    """Cards that were removed (not in card database)."""

    removed_count: int
    """Total number of card copies removed."""

    removed_unique_count: int
    """Number of unique cards removed."""

    timestamp: datetime
    """When sanitization occurred."""

    @property
    def had_removals(self) -> bool:
        """Whether any cards were removed."""
        return self.removed_unique_count > 0

    def get_user_message(self) -> str | None:
        """
        Get user-facing message about sanitization.

        Returns None if no sanitization occurred.
        Message is calm, factual, and non-blocking.
        """
        if not self.had_removals:
            return None

        if self.removed_unique_count == 1:
            return (
                "We cleaned up your collection by removing 1 card that isn't "
                "recognized by the current card database. Everything else "
                "imported successfully."
            )

        return (
            f"We cleaned up your collection by removing {self.removed_unique_count} "
            f"cards that aren't recognized by the current card database. "
            f"Everything else imported successfully."
        )


def sanitize_collection(
    cards: dict[str, int],
    card_db: dict[str, dict[str, Any]],
) -> SanitizationResult:
    """
    Sanitize a collection by removing cards not in the card database.

    This is the single point of sanitization. After this function,
    all cards in the result are guaranteed to be in the card database.

    Args:
        cards: Raw card collection {name: quantity}
        card_db: Card database {name: card_data}

    Returns:
        SanitizationResult with sanitized cards and removal metadata.

    INVARIANT: sanitized_cards.keys() ⊆ card_db.keys()
    """
    valid_card_names = set(card_db.keys())
    collection_card_names = set(cards.keys())

    # Compute invalid cards
    invalid_card_names = collection_card_names - valid_card_names

    # Build sanitized collection
    sanitized: dict[str, int] = {}
    removed: dict[str, int] = {}

    for name, qty in cards.items():
        if name in invalid_card_names:
            removed[name] = qty
        else:
            sanitized[name] = qty

    # Calculate removal stats
    removed_count = sum(removed.values())
    removed_unique_count = len(removed)

    # Log removals for debugging
    if removed:
        logger.info(
            "collection_sanitized",
            extra={
                "removed_unique_count": removed_unique_count,
                "removed_total_count": removed_count,
                "removed_card_names": list(removed.keys())[:10],  # Log first 10
                "sanitized_unique_count": len(sanitized),
            },
        )

    return SanitizationResult(
        sanitized_cards=sanitized,
        removed_cards=removed,
        removed_count=removed_count,
        removed_unique_count=removed_unique_count,
        timestamp=datetime.now(UTC),
    )


def try_sanitize_collection(
    cards: dict[str, int],
) -> SanitizationResult | None:
    """
    Attempt to sanitize collection using the global card database.

    Returns None if card database is unavailable (graceful degradation).
    In this case, no sanitization is performed and the collection
    is stored as-is. The request-time guard will catch any issues.

    Args:
        cards: Raw card collection {name: quantity}

    Returns:
        SanitizationResult if card database available, None otherwise.
    """
    try:
        from forgebreaker.services.card_database import get_card_database

        card_db = get_card_database()
        return sanitize_collection(cards, card_db)
    except FileNotFoundError:
        logger.warning(
            "card_database_unavailable_skipping_sanitization",
            extra={"reason": "Card database not found, skipping import sanitization"},
        )
        return None
