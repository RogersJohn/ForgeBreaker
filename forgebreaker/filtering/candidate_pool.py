"""
Candidate Pool Builder — Deterministic Pre-LLM Filtering.

This module provides deterministic filtering to reduce the card universe
before the LLM is called. Currently in SHADOW MODE — filtering results
are computed for metrics but not used to alter execution paths.

INVARIANTS:
- Filtering is monotonic (only removes cards, never adds)
- Same intent + DB → same pool (deterministic)
- Empty intent → full DB returned (passthrough)
"""

import logging
from dataclasses import dataclass
from typing import Any

from forgebreaker.models.intent import DeckIntent

logger = logging.getLogger(__name__)

# Type alias for card database
CardDatabase = dict[str, dict[str, Any]]


@dataclass
class CandidatePoolMetrics:
    """Metrics recorded per candidate pool build."""

    total_cards: int = 0
    after_format_filter: int = 0
    after_color_filter: int = 0
    after_tribe_filter: int = 0
    after_archetype_filter: int = 0
    final_pool_size: int = 0


# Module-level metrics accumulator
_metrics_history: list[CandidatePoolMetrics] = []


def get_pool_metrics() -> list[CandidatePoolMetrics]:
    """Get all recorded metrics."""
    return _metrics_history.copy()


def reset_pool_metrics() -> None:
    """Reset metrics history (for testing)."""
    _metrics_history.clear()


def _filter_by_format(
    candidates: set[str],
    intent: DeckIntent,
    card_db: CardDatabase,
) -> set[str]:
    """
    Filter by format legality.

    If intent.format is set, include only cards legal in that format.
    """
    if intent.format is None:
        return candidates

    format_name = intent.format.value.lower()
    result: set[str] = set()

    for card_name in candidates:
        card_data = card_db.get(card_name)
        if card_data is None:
            continue

        legalities = card_data.get("legalities", {})
        if legalities.get(format_name) == "legal":
            result.add(card_name)

    return result


def _filter_by_color(
    candidates: set[str],
    intent: DeckIntent,
    card_db: CardDatabase,
) -> set[str]:
    """
    Filter by color identity.

    If intent.colors is set, include only cards whose color identity
    is a subset of the intent colors. Colorless cards are always allowed.
    """
    if intent.colors is None:
        return candidates

    allowed_colors = set(intent.colors)
    result: set[str] = set()

    for card_name in candidates:
        card_data = card_db.get(card_name)
        if card_data is None:
            continue

        # Get color identity (fall back to colors if not present)
        identity_data = card_data.get("color_identity") or card_data.get("colors") or []
        card_identity = set(identity_data)

        # Colorless cards (empty identity) are always allowed
        if not card_identity:
            result.add(card_name)
            continue

        # Card identity must be subset of allowed colors
        if card_identity <= allowed_colors:
            result.add(card_name)

    return result


def _filter_by_tribe(
    candidates: set[str],
    intent: DeckIntent,
    card_db: CardDatabase,
) -> set[str]:
    """
    Filter by creature type.

    If intent.tribe is set, include only:
    - Cards with that creature type in type_line
    - Cards tagged as tribal synergies (not yet implemented)

    Note: Currently only checks type_line. Tribal synergy tagging
    would require additional card metadata.
    """
    if intent.tribe is None:
        return candidates

    tribe_lower = intent.tribe.lower()
    result: set[str] = set()

    for card_name in candidates:
        card_data = card_db.get(card_name)
        if card_data is None:
            continue

        type_line = card_data.get("type_line", "").lower()

        # Check if tribe appears in type line
        # This handles "Creature — Dragon" and "Legendary Creature — Dragon Warrior"
        if tribe_lower in type_line:
            result.add(card_name)
            continue

        # TODO: Check tribal synergy tags when available
        # For now, non-creature tribal synergies are not detected

    return result


def _filter_by_archetype(
    candidates: set[str],
    intent: DeckIntent,
    card_db: CardDatabase,  # noqa: ARG001
) -> set[str]:
    """
    Filter by archetype.

    If intent.archetype is set, include cards tagged for that archetype.

    Note: Currently a passthrough. Archetype tagging requires additional
    card metadata that doesn't exist in Scryfall data.
    """
    if intent.archetype is None:
        return candidates

    # TODO: Implement archetype filtering when tagging system exists
    # For now, passthrough — all candidates remain
    # This is intentional for shadow mode: we record metrics but don't filter
    return candidates


def build_candidate_pool(
    intent: DeckIntent,
    card_db: CardDatabase,
) -> set[str]:
    """
    Build a candidate pool by filtering the card database.

    Applies filters in order (authoritative):
    1. Format legality
    2. Color identity
    3. Tribe
    4. Archetype

    Each filter is:
    - Pure (no side effects except logging)
    - Deterministic (same input → same output)
    - Monotonic (only removes cards)

    Args:
        intent: The inferred deck intent
        card_db: The full card database

    Returns:
        Set of card names that pass all applicable filters
    """
    metrics = CandidatePoolMetrics()

    # Start with all cards
    candidates = set(card_db.keys())
    metrics.total_cards = len(candidates)

    # Apply filters in order
    candidates = _filter_by_format(candidates, intent, card_db)
    metrics.after_format_filter = len(candidates)

    candidates = _filter_by_color(candidates, intent, card_db)
    metrics.after_color_filter = len(candidates)

    candidates = _filter_by_tribe(candidates, intent, card_db)
    metrics.after_tribe_filter = len(candidates)

    candidates = _filter_by_archetype(candidates, intent, card_db)
    metrics.after_archetype_filter = len(candidates)

    metrics.final_pool_size = len(candidates)

    # Record metrics
    _metrics_history.append(metrics)

    # Log for shadow mode observability
    logger.info(
        "candidate_pool_built",
        extra={
            "total": metrics.total_cards,
            "after_format": metrics.after_format_filter,
            "after_color": metrics.after_color_filter,
            "after_tribe": metrics.after_tribe_filter,
            "final": metrics.final_pool_size,
            "reduction_pct": (
                round(100 * (1 - metrics.final_pool_size / metrics.total_cards), 1)
                if metrics.total_cards > 0
                else 0
            ),
        },
    )

    return candidates
