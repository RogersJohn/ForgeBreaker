"""
Candidate pool filtering for pre-LLM card universe reduction.

This module provides deterministic filtering to reduce the card universe
before the LLM is called. Currently in shadow mode — filtering results
are computed but not used.
"""

from forgebreaker.filtering.candidate_pool import (
    CandidatePoolMetrics,
    build_candidate_pool,
    get_pool_metrics,
    reset_pool_metrics,
)

__all__ = [
    "CandidatePoolMetrics",
    "build_candidate_pool",
    "get_pool_metrics",
    "reset_pool_metrics",
]
