"""
Payload Filtering — Reduce LLM Payload Using Candidate Pool.

This module provides payload filtering to reduce what's sent to the LLM
by using the candidate pool instead of the full collection/card database.

FEATURE FLAG: USE_FILTERED_CANDIDATE_POOL
- OFF: Full collection passed (unchanged behavior)
- ON: Only candidate pool cards passed

FAIL-SAFE: Always falls back to full collection on any issue.
"""

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any

from forgebreaker.config import (
    MAX_CANDIDATE_POOL_SIZE,
    MIN_CANDIDATE_POOL_SIZE,
    settings,
)
from forgebreaker.filtering.candidate_pool import build_candidate_pool
from forgebreaker.models.intent import DeckIntent

logger = logging.getLogger(__name__)


class FallbackReason(str, Enum):
    """Reasons for falling back to full collection."""

    NONE = "none"
    FLAG_OFF = "flag_off"
    POOL_EMPTY = "pool_empty"
    POOL_TOO_SMALL = "pool_too_small"
    POOL_TOO_LARGE = "pool_too_large"
    EXCEPTION = "exception"


@dataclass
class PayloadFilterMetrics:
    """Metrics for a single payload filtering operation."""

    feature_flag_enabled: bool
    candidate_pool_size: int
    full_collection_size: int
    filtered_collection_size: int
    fallback_reason: FallbackReason
    tokens_estimated: int  # Rough estimate based on card count


# Module-level metrics accumulator
_metrics_history: list[PayloadFilterMetrics] = []


def get_payload_metrics() -> list[PayloadFilterMetrics]:
    """Get all recorded metrics."""
    return _metrics_history.copy()


def reset_payload_metrics() -> None:
    """Reset metrics history (for testing)."""
    _metrics_history.clear()


def _estimate_tokens(card_count: int) -> int:
    """
    Estimate tokens for a payload based on card count.

    Rough estimate: ~20 tokens per card (name + basic info).
    """
    return card_count * 20


def filter_collection_for_payload(
    intent: DeckIntent,
    collection_cards: dict[str, int],
    card_db: dict[str, dict[str, Any]],
) -> tuple[dict[str, int], PayloadFilterMetrics]:
    """
    Filter collection using candidate pool for reduced LLM payload.

    Args:
        intent: The inferred deck intent
        collection_cards: Full collection (card_name -> quantity)
        card_db: Full card database

    Returns:
        Tuple of (filtered_collection, metrics)
        - If flag OFF or fallback triggered: returns full collection
        - If flag ON and pool valid: returns filtered collection

    INVARIANT: Never returns empty collection if input was non-empty.
    INVARIANT: Falls back to full collection on any error.
    """
    full_size = len(collection_cards)
    metrics = PayloadFilterMetrics(
        feature_flag_enabled=settings.use_filtered_candidate_pool,
        candidate_pool_size=0,
        full_collection_size=full_size,
        filtered_collection_size=full_size,
        fallback_reason=FallbackReason.NONE,
        tokens_estimated=_estimate_tokens(full_size),
    )

    # Check feature flag first
    if not settings.use_filtered_candidate_pool:
        metrics.fallback_reason = FallbackReason.FLAG_OFF
        _metrics_history.append(metrics)
        logger.debug("payload_filter_skipped: flag_off")
        return collection_cards, metrics

    try:
        # Build candidate pool
        candidate_pool = build_candidate_pool(intent, card_db)
        pool_size = len(candidate_pool)
        metrics.candidate_pool_size = pool_size

        # Check pool size limits
        if pool_size == 0:
            metrics.fallback_reason = FallbackReason.POOL_EMPTY
            _metrics_history.append(metrics)
            logger.warning(
                "payload_filter_fallback",
                extra={
                    "filtered_candidate_pool_fallback_reason": "pool_empty",
                    "intent": str(intent),
                },
            )
            return collection_cards, metrics

        if pool_size < MIN_CANDIDATE_POOL_SIZE:
            metrics.fallback_reason = FallbackReason.POOL_TOO_SMALL
            _metrics_history.append(metrics)
            logger.warning(
                "payload_filter_fallback",
                extra={
                    "filtered_candidate_pool_fallback_reason": "pool_too_small",
                    "pool_size": pool_size,
                    "min_required": MIN_CANDIDATE_POOL_SIZE,
                },
            )
            return collection_cards, metrics

        if pool_size > MAX_CANDIDATE_POOL_SIZE:
            metrics.fallback_reason = FallbackReason.POOL_TOO_LARGE
            _metrics_history.append(metrics)
            logger.warning(
                "payload_filter_fallback",
                extra={
                    "filtered_candidate_pool_fallback_reason": "pool_too_large",
                    "pool_size": pool_size,
                    "max_allowed": MAX_CANDIDATE_POOL_SIZE,
                },
            )
            return collection_cards, metrics

        # Filter collection to only include cards in candidate pool
        filtered = {name: qty for name, qty in collection_cards.items() if name in candidate_pool}

        # Safety check: don't return empty if we had cards
        if not filtered and collection_cards:
            metrics.fallback_reason = FallbackReason.POOL_EMPTY
            _metrics_history.append(metrics)
            logger.warning(
                "payload_filter_fallback",
                extra={
                    "filtered_candidate_pool_fallback_reason": "filtered_empty",
                    "original_size": full_size,
                },
            )
            return collection_cards, metrics

        metrics.filtered_collection_size = len(filtered)
        metrics.tokens_estimated = _estimate_tokens(len(filtered))
        _metrics_history.append(metrics)

        logger.info(
            "payload_filter_applied",
            extra={
                "filtered_candidate_pool_enabled": True,
                "original_size": full_size,
                "filtered_size": len(filtered),
                "pool_size": pool_size,
                "reduction_pct": round(100 * (1 - len(filtered) / full_size), 1)
                if full_size > 0
                else 0,
            },
        )

        return filtered, metrics

    except Exception as e:
        metrics.fallback_reason = FallbackReason.EXCEPTION
        _metrics_history.append(metrics)
        logger.exception(
            "payload_filter_exception",
            extra={"error": str(e)},
        )
        return collection_cards, metrics


def filter_card_db_for_payload(
    intent: DeckIntent,
    card_db: dict[str, dict[str, Any]],
) -> tuple[dict[str, dict[str, Any]], PayloadFilterMetrics]:
    """
    Filter card database using candidate pool for reduced LLM payload.

    Similar to filter_collection_for_payload but for full card database.
    Returns only high-level card info (no oracle text).

    Args:
        intent: The inferred deck intent
        card_db: Full card database

    Returns:
        Tuple of (filtered_card_db, metrics)
    """
    full_size = len(card_db)
    metrics = PayloadFilterMetrics(
        feature_flag_enabled=settings.use_filtered_candidate_pool,
        candidate_pool_size=0,
        full_collection_size=full_size,
        filtered_collection_size=full_size,
        fallback_reason=FallbackReason.NONE,
        tokens_estimated=_estimate_tokens(full_size),
    )

    if not settings.use_filtered_candidate_pool:
        metrics.fallback_reason = FallbackReason.FLAG_OFF
        _metrics_history.append(metrics)
        return card_db, metrics

    try:
        candidate_pool = build_candidate_pool(intent, card_db)
        pool_size = len(candidate_pool)
        metrics.candidate_pool_size = pool_size

        if pool_size == 0:
            metrics.fallback_reason = FallbackReason.POOL_EMPTY
            _metrics_history.append(metrics)
            return card_db, metrics

        if pool_size < MIN_CANDIDATE_POOL_SIZE:
            metrics.fallback_reason = FallbackReason.POOL_TOO_SMALL
            _metrics_history.append(metrics)
            return card_db, metrics

        if pool_size > MAX_CANDIDATE_POOL_SIZE:
            metrics.fallback_reason = FallbackReason.POOL_TOO_LARGE
            _metrics_history.append(metrics)
            return card_db, metrics

        # Filter to candidate pool with only high-level info (no oracle_text)
        filtered: dict[str, dict[str, Any]] = {}
        for name in candidate_pool:
            if name in card_db:
                card = card_db[name]
                filtered[name] = {
                    "name": card.get("name"),
                    "type_line": card.get("type_line"),
                    "mana_cost": card.get("mana_cost"),
                    "cmc": card.get("cmc"),
                    "colors": card.get("colors", []),
                    "color_identity": card.get("color_identity", []),
                    "keywords": card.get("keywords", []),
                    "rarity": card.get("rarity"),
                    "legalities": card.get("legalities", {}),
                    # Explicitly NOT including oracle_text
                }

        if not filtered and card_db:
            metrics.fallback_reason = FallbackReason.POOL_EMPTY
            _metrics_history.append(metrics)
            return card_db, metrics

        metrics.filtered_collection_size = len(filtered)
        metrics.tokens_estimated = _estimate_tokens(len(filtered))
        _metrics_history.append(metrics)

        logger.info(
            "card_db_filter_applied",
            extra={
                "original_size": full_size,
                "filtered_size": len(filtered),
                "pool_size": pool_size,
            },
        )

        return filtered, metrics

    except Exception:
        metrics.fallback_reason = FallbackReason.EXCEPTION
        _metrics_history.append(metrics)
        logger.exception("card_db_filter_exception")
        return card_db, metrics
