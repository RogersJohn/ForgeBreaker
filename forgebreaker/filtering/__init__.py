"""
Candidate pool filtering for pre-LLM card universe reduction.

This module provides deterministic filtering to reduce the card universe
before the LLM is called.

Shadow mode (PR 3): Filtering computed but not used.
Payload filtering (PR 4): Filtering used behind feature flag.
Scored pool (PR 5): Scoring replaces elimination.
"""

from forgebreaker.filtering.candidate_pool import (
    CandidatePoolMetrics,
    build_candidate_pool,
    get_pool_metrics,
    reset_pool_metrics,
)
from forgebreaker.filtering.payload import (
    FallbackReason,
    PayloadFilterMetrics,
    filter_card_db_for_payload,
    filter_collection_for_payload,
    get_payload_metrics,
    reset_payload_metrics,
)
from forgebreaker.filtering.scored_pool import (
    MAX_POOL_SIZE,
    MIN_POOL_SIZE,
    ScoredCandidatePool,
    ScoredCard,
    build_scored_pool,
    score_card,
    select_candidates,
)

__all__ = [
    # Candidate pool (PR 3)
    "CandidatePoolMetrics",
    "build_candidate_pool",
    "get_pool_metrics",
    "reset_pool_metrics",
    # Payload filtering (PR 4)
    "FallbackReason",
    "PayloadFilterMetrics",
    "filter_card_db_for_payload",
    "filter_collection_for_payload",
    "get_payload_metrics",
    "reset_payload_metrics",
    # Scored pool (PR 5)
    "MAX_POOL_SIZE",
    "MIN_POOL_SIZE",
    "ScoredCandidatePool",
    "ScoredCard",
    "build_scored_pool",
    "score_card",
    "select_candidates",
]
