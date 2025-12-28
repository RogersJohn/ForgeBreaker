"""
Deck ranking algorithm.

Ranks meta decks by suitability for a user's collection, considering
completion percentage, wildcard cost, win rate, and meta share.
Optionally uses MLForge for ML-based recommendation scoring.

All recommendations include explanatory text with:
- References to relevant assumptions
- Explicit uncertainty language
"""

import logging
from typing import Any

from forgebreaker.analysis.distance import calculate_deck_distance
from forgebreaker.models.collection import Collection
from forgebreaker.models.deck import DeckDistance, MetaDeck, RankedDeck
from forgebreaker.models.explanation import (
    CONDITIONAL_PHRASES,
    create_recommendation_explanation,
)

logger = logging.getLogger(__name__)

# Default wildcard budget thresholds (rare-equivalent)
DEFAULT_BUDGET = 20.0

# Weight for blending ML score with basic score (0.0-1.0)
# 0.6 = 60% ML score, 40% basic score
ML_SCORE_WEIGHT = 0.6


def rank_decks(
    decks: list[MetaDeck],
    collection: Collection,
    rarity_map: dict[str, str],
    wildcard_budget: float = DEFAULT_BUDGET,
) -> list[RankedDeck]:
    """
    Rank meta decks by suitability for a user's collection.

    Args:
        decks: List of meta decks to evaluate
        collection: User's card collection
        rarity_map: Mapping of card names to rarities
        wildcard_budget: Max weighted wildcard cost to consider "within budget"

    Returns:
        List of RankedDeck sorted by score (highest first)
    """
    ranked: list[RankedDeck] = []

    for deck in decks:
        distance = calculate_deck_distance(deck, collection, rarity_map)
        score = _calculate_score(distance)
        can_build = distance.is_complete
        within_budget = distance.wildcard_cost.weighted_cost() <= wildcard_budget
        reason = _generate_recommendation_reason(distance, can_build, within_budget)

        ranked.append(
            RankedDeck(
                deck=deck,
                distance=distance,
                score=score,
                can_build_now=can_build,
                within_budget=within_budget,
                recommendation_reason=reason,
            )
        )

    # Sort by score descending (best first)
    ranked.sort(key=lambda r: r.score, reverse=True)

    return ranked


def _calculate_score(distance: DeckDistance) -> float:
    """
    Calculate a ranking score for a deck based on distance metrics.

    Score formula (higher is better):
    - Completion % contributes 40 points max (0-100% -> 0-40)
    - Low wildcard cost contributes 30 points max (inverse of weighted cost)
    - Win rate contributes 20 points max (0-100% -> 0-20)
    - Meta share contributes 10 points max (0-100% -> 0-10)

    Returns:
        Score from 0-100 (approximately)
    """
    # Completion score: 0-40 points
    completion_score = distance.completion_percentage * 40.0

    # Wildcard cost score: 0-30 points (lower cost = higher score)
    # Use inverse scaling: 30 points at 0 cost, approaches 0 at high cost
    weighted_cost = distance.wildcard_cost.weighted_cost()
    # Diminishing returns: score = 30 / (1 + cost/10)
    wildcard_score = 30.0 / (1.0 + weighted_cost / 10.0)

    # Win rate score: 0-20 points
    win_rate = distance.deck.win_rate or 0.5  # Default 50% if unknown
    win_rate_score = win_rate * 20.0

    # Meta share score: 0-10 points
    meta_share = distance.deck.meta_share or 0.05  # Default 5% if unknown
    # Cap at 50% to prevent dominant decks from overly skewing results
    meta_score = min(meta_share, 0.5) * 20.0

    return completion_score + wildcard_score + win_rate_score + meta_score


def _generate_recommendation_reason(
    distance: DeckDistance,
    can_build: bool,
    within_budget: bool,
) -> str:
    """
    Generate a human-readable reason describing the deck's status.

    Describes consequences, not recommendations.
    """
    if can_build:
        return "All cards for this deck are present in your collection."

    missing = distance.missing_cards
    pct = int(distance.completion_percentage * 100)
    cost = distance.wildcard_cost

    if within_budget:
        reason = f"{pct}% complete, missing {missing} cards ({cost.total()} wildcards). "
        reason += CONDITIONAL_PHRASES["assumption_based"]
        return reason

    # Describe the expensive rarities without advising
    expensive_parts: list[str] = []
    if cost.mythic > 0:
        expensive_parts.append(f"{cost.mythic} mythic")
    if cost.rare > 0:
        expensive_parts.append(f"{cost.rare} rare")

    if expensive_parts:
        reason = f"{pct}% complete, missing {', '.join(expensive_parts)} wildcards."
        return reason

    return f"{pct}% complete, missing {missing} cards"


def generate_explained_recommendation(
    distance: DeckDistance,
    score: float,
    can_build: bool,
    within_budget: bool,
    fragility: float | None = None,
) -> dict[str, Any]:
    """
    Generate a description with full explanation.

    Returns a dictionary suitable for API responses that includes:
    - The status description
    - Assumptions involved
    - Conditional statement (what changes this interpretation)

    Args:
        distance: Deck distance calculation
        score: Ranking score
        can_build: Whether deck can be built now
        within_budget: Whether deck is within wildcard budget
        fragility: Optional fragility score from assumptions analysis

    Returns:
        Dict with reason, explanation, and conditional
    """
    reason = _generate_recommendation_reason(distance, can_build, within_budget)
    explanation = create_recommendation_explanation(
        score=score / 100.0,  # Normalize to 0-1
        completion_pct=distance.completion_percentage * 100,
        archetype=distance.deck.archetype or "unknown",
        fragility=fragility,
    )

    return {
        "reason": reason,
        "summary": explanation.summary,
        "assumptions_involved": explanation.assumptions_involved,
        "conditional": explanation.conditional,
    }


def get_buildable_decks(
    decks: list[MetaDeck],
    collection: Collection,
    rarity_map: dict[str, str],
) -> list[RankedDeck]:
    """
    Get only decks that can be built immediately.

    Convenience function that filters to 100% complete decks.
    """
    ranked = rank_decks(decks, collection, rarity_map)
    return [r for r in ranked if r.can_build_now]


def get_budget_decks(
    decks: list[MetaDeck],
    collection: Collection,
    rarity_map: dict[str, str],
    wildcard_budget: float = DEFAULT_BUDGET,
) -> list[RankedDeck]:
    """
    Get decks within the specified wildcard budget.

    Convenience function that filters to affordable decks.
    """
    ranked = rank_decks(decks, collection, rarity_map, wildcard_budget)
    return [r for r in ranked if r.within_budget]


async def rank_decks_with_ml(
    decks: list[MetaDeck],
    collection: Collection,
    rarity_map: dict[str, str],
    wildcard_budget: float = DEFAULT_BUDGET,
) -> list[RankedDeck]:
    """
    Rank decks using MLForge ML-based scoring blended with basic metrics.

    This function extracts features from each deck, sends them to MLForge
    for ML scoring, then blends the ML score with the basic heuristic score.
    Falls back to basic scoring if MLForge is unavailable.

    Data flow:
    1. Calculate deck distances (completion %, wildcard costs)
    2. Extract ML features (DeckFeatures) for each deck
    3. Call MLForge batch scoring API
    4. Blend ML score (60%) with basic score (40%)
    5. Return ranked list

    Args:
        decks: List of meta decks to evaluate
        collection: User's card collection
        rarity_map: Mapping of card names to rarities
        wildcard_budget: Max weighted wildcard cost to consider "within budget"

    Returns:
        List of RankedDeck sorted by blended score (highest first)
    """
    # Import here to avoid circular imports
    from forgebreaker.ml.features import extract_deck_features
    from forgebreaker.ml.inference import get_mlforge_client

    if not decks:
        return []

    # Step 1: Calculate distances and basic scores for all decks
    deck_data: list[tuple[MetaDeck, DeckDistance, float]] = []
    for deck in decks:
        distance = calculate_deck_distance(deck, collection, rarity_map)
        basic_score = _calculate_score(distance)
        deck_data.append((deck, distance, basic_score))

    # Step 2: Extract ML features for each deck
    features_list = [extract_deck_features(deck, distance) for deck, distance, _ in deck_data]

    # Step 3: Call MLForge for ML-based scoring
    ml_scores: dict[str, float] = {}
    ml_confidences: dict[str, float] = {}
    mlforge_available = False

    client = get_mlforge_client()
    try:
        # Check health first to fail fast
        if await client.health_check():
            mlforge_available = True
            scores = await client.score_decks(features_list)
            for score in scores:
                ml_scores[score.deck_name] = score.score
                ml_confidences[score.deck_name] = score.confidence
            logger.info(
                "MLForge scored %d decks successfully",
                len(scores),
            )
        else:
            logger.info("MLForge health check failed, using basic scoring")
    except Exception as e:
        logger.warning("MLForge scoring failed, using basic scoring: %s", e)
        mlforge_available = False

    # Step 4: Build ranked decks with blended scores
    ranked: list[RankedDeck] = []
    for deck, distance, basic_score in deck_data:
        can_build = distance.is_complete
        within_budget = distance.wildcard_cost.weighted_cost() <= wildcard_budget

        # Blend ML score with basic score if available
        if mlforge_available and deck.name in ml_scores:
            ml_score = ml_scores[deck.name]
            confidence = ml_confidences.get(deck.name, 1.0)
            # Scale ML score (0-1) to match basic score range (0-100)
            scaled_ml_score = ml_score * 100.0
            # Adjust weight by confidence
            effective_weight = ML_SCORE_WEIGHT * confidence
            final_score = effective_weight * scaled_ml_score + (1 - effective_weight) * basic_score
        else:
            final_score = basic_score

        reason = _generate_recommendation_reason(distance, can_build, within_budget)

        ranked.append(
            RankedDeck(
                deck=deck,
                distance=distance,
                score=final_score,
                can_build_now=can_build,
                within_budget=within_budget,
                recommendation_reason=reason,
            )
        )

    # Step 5: Sort by final score descending
    ranked.sort(key=lambda r: r.score, reverse=True)

    return ranked
