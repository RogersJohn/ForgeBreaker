"""
Deck ranking algorithm.

Ranks meta decks by suitability for a user's collection, considering
completion percentage, wildcard cost, win rate, and meta share.
"""

from forgebreaker.analysis.distance import calculate_deck_distance
from forgebreaker.models.collection import Collection
from forgebreaker.models.deck import DeckDistance, MetaDeck, RankedDeck

# Default wildcard budget thresholds (rare-equivalent)
DEFAULT_BUDGET = 20.0


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
    # Cap at 50% meta share for scoring
    meta_score = min(meta_share, 0.5) * 20.0

    return completion_score + wildcard_score + win_rate_score + meta_score


def _generate_recommendation_reason(
    distance: DeckDistance,
    can_build: bool,
    within_budget: bool,
) -> str:
    """Generate a human-readable recommendation reason."""
    if can_build:
        return "You can build this deck now!"

    missing = distance.missing_cards
    pct = int(distance.completion_percentage * 100)
    cost = distance.wildcard_cost

    if within_budget:
        return f"{pct}% complete, needs {missing} cards ({cost.total()} wildcards)"

    # Highlight the expensive rarities
    expensive_parts: list[str] = []
    if cost.mythic > 0:
        expensive_parts.append(f"{cost.mythic} mythic")
    if cost.rare > 0:
        expensive_parts.append(f"{cost.rare} rare")

    if expensive_parts:
        return f"{pct}% complete, needs {', '.join(expensive_parts)} wildcards"

    return f"{pct}% complete, needs {missing} cards"


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
