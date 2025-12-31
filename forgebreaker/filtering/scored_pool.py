"""
Scored Candidate Pool - scoring replaces elimination.

INVARIANT: Cards are scored by query relevance, not eliminated.
This ends "empty pool" failures without relaxing correctness.

Safety bounds preserved:
- MIN_POOL_SIZE = 10 (below this, fallback)
- MAX_POOL_SIZE = 100 (above this, return top 100)
"""

from dataclasses import dataclass, field
from typing import Any

from forgebreaker.models.deck_query import (
    DeckQuery,
    QuerySignal,
    QuerySignalType,
    SignalStrength,
)

# Safety bounds (same as config.py)
MIN_POOL_SIZE = 10
MAX_POOL_SIZE = 100


@dataclass(frozen=True, slots=True)
class ScoredCard:
    """
    A card with its relevance score.

    Higher scores = more relevant to the query.
    """

    name: str
    score: float
    breakdown: dict[str, float] = field(default_factory=dict)

    def __lt__(self, other: "ScoredCard") -> bool:
        """Sort by score descending."""
        return self.score > other.score


@dataclass(frozen=True)
class ScoredCandidatePool:
    """
    Candidate pool built by scoring, not elimination.

    INVARIANT: Pool is never empty if input was non-empty.
    Low-scoring cards are included at the bottom, not excluded.

    Usage:
        pool = build_scored_pool(query, cards, card_db)
        top_cards = pool.top(50)  # Get top 50 cards
    """

    scored_cards: tuple[ScoredCard, ...]
    query: DeckQuery

    @property
    def size(self) -> int:
        """Number of cards in the pool."""
        return len(self.scored_cards)

    def top(self, n: int) -> list[str]:
        """
        Get top N card names by score.

        Args:
            n: Maximum number of cards to return

        Returns:
            List of card names, highest scoring first
        """
        return [c.name for c in self.scored_cards[:n]]

    def top_with_scores(self, n: int) -> list[ScoredCard]:
        """
        Get top N cards with their scores.

        Args:
            n: Maximum number of cards to return

        Returns:
            List of ScoredCard objects, highest scoring first
        """
        return list(self.scored_cards[:n])

    def get_score(self, card_name: str) -> float:
        """
        Get score for a specific card.

        Returns 0.0 if card not in pool.
        """
        for card in self.scored_cards:
            if card.name == card_name:
                return card.score
        return 0.0

    def is_empty(self) -> bool:
        """Check if pool is empty."""
        return len(self.scored_cards) == 0


# =============================================================================
# SCORING FUNCTIONS
# =============================================================================


def _score_tribe_match(card_data: dict[str, Any], tribe: str) -> float:
    """
    Score how well a card matches a tribe signal.

    Returns:
        1.0 - Card IS the tribe (type_line contains tribe)
        0.5 - Card SYNERGIZES with tribe (oracle text mentions tribe)
        0.0 - No tribal relevance
    """
    type_line = card_data.get("type_line", "").lower()
    oracle_text = card_data.get("oracle_text", "").lower()
    tribe_lower = tribe.lower()

    # Direct tribe match in type line
    if tribe_lower in type_line:
        return 1.0

    # Tribal synergy in oracle text (e.g., "Goblin creatures you control")
    if tribe_lower in oracle_text:
        return 0.5

    return 0.0


def _score_theme_match(card_data: dict[str, Any], theme: str) -> float:
    """
    Score how well a card matches a theme signal.

    Returns:
        1.0 - Strong theme match (name or type contains theme)
        0.7 - Moderate match (oracle text contains theme)
        0.0 - No theme relevance
    """
    name = card_data.get("name", "").lower()
    type_line = card_data.get("type_line", "").lower()
    oracle_text = card_data.get("oracle_text", "").lower()
    theme_lower = theme.lower()

    # Theme in name or type line
    if theme_lower in name or theme_lower in type_line:
        return 1.0

    # Theme in oracle text
    if theme_lower in oracle_text:
        return 0.7

    return 0.0


def _score_color_match(card_data: dict[str, Any], colors: frozenset[str]) -> float:
    """
    Score how well a card matches color signals.

    Returns:
        1.0 - Card is exact color match or subset
        0.5 - Colorless card (always playable)
        0.0 - Card has colors outside the allowed set
    """
    card_colors = set(card_data.get("colors", []))
    card_identity = set(card_data.get("color_identity", []))

    # Colorless cards are always fine
    if not card_colors and not card_identity:
        return 0.5

    # Check if card's identity is subset of allowed colors
    if card_identity <= colors:
        return 1.0

    # Card has colors outside the allowed set
    return 0.0


def _score_archetype_match(card_data: dict[str, Any], archetype: str) -> float:
    """
    Score how well a card matches an archetype signal.

    This is a simplified heuristic based on card characteristics.
    """
    cmc = card_data.get("cmc", 0)
    type_line = card_data.get("type_line", "").lower()
    oracle_text = card_data.get("oracle_text", "").lower()

    archetype_lower = archetype.lower()

    if archetype_lower == "aggro":
        # Aggro likes low CMC creatures with haste/menace
        if "creature" in type_line and cmc <= 3:
            if "haste" in oracle_text or "menace" in oracle_text:
                return 1.0
            return 0.7
        return 0.2

    if archetype_lower == "control":
        # Control likes counterspells, removal, draw
        if "counter target" in oracle_text or "destroy target" in oracle_text:
            return 1.0
        if "draw" in oracle_text and "card" in oracle_text:
            return 0.8
        return 0.2

    if archetype_lower == "midrange":
        # Midrange likes value creatures
        if "creature" in type_line and 3 <= cmc <= 5:
            return 0.8
        return 0.3

    if archetype_lower == "combo":
        # Combo likes cards that search or enable
        if "search" in oracle_text or "untap" in oracle_text:
            return 0.8
        return 0.2

    # Unknown archetype - neutral score
    return 0.3


def _score_format_match(card_data: dict[str, Any], format_name: str) -> float:
    """
    Score format legality.

    Returns:
        1.0 - Card is legal in format
        0.0 - Card is not legal (REQUIRED signal)
    """
    legalities = card_data.get("legalities", {})
    if legalities.get(format_name) == "legal":
        return 1.0
    return 0.0


def _score_signal(card_data: dict[str, Any], signal: QuerySignal) -> float:
    """
    Score a card against a single signal.

    Returns a score between 0.0 and 1.0.
    """
    if signal.signal_type == QuerySignalType.TRIBE:
        return _score_tribe_match(card_data, signal.value)
    if signal.signal_type == QuerySignalType.THEME:
        return _score_theme_match(card_data, signal.value)
    if signal.signal_type == QuerySignalType.COLOR:
        return _score_color_match(card_data, frozenset([signal.value]))
    if signal.signal_type == QuerySignalType.ARCHETYPE:
        return _score_archetype_match(card_data, signal.value)
    if signal.signal_type == QuerySignalType.FORMAT:
        return _score_format_match(card_data, signal.value)

    # Unknown signal type - neutral score
    return 0.5


def _get_strength_weight(strength: SignalStrength) -> float:
    """
    Get the weight multiplier for a signal strength.
    """
    weights = {
        SignalStrength.REQUIRED: 10.0,  # Must-have
        SignalStrength.STRONG: 3.0,
        SignalStrength.MODERATE: 1.5,
        SignalStrength.WEAK: 0.5,
    }
    return weights.get(strength, 1.0)


def score_card(card_name: str, card_data: dict[str, Any], query: DeckQuery) -> ScoredCard:
    """
    Score a card against all query signals.

    INVARIANT: Required signals that fail result in score = 0.
    Preference signals modulate the score but don't eliminate.
    """
    breakdown: dict[str, float] = {}
    total_score = 0.0
    total_weight = 0.0

    for signal in query.signals:
        raw_score = _score_signal(card_data, signal)
        weight = _get_strength_weight(signal.strength)

        # Required signals that fail = immediate zero
        if signal.is_required() and raw_score == 0.0:
            return ScoredCard(name=card_name, score=0.0, breakdown={"failed_required": 0.0})

        weighted_score = raw_score * weight
        signal_key = f"{signal.signal_type.value}:{signal.value}"
        breakdown[signal_key] = weighted_score

        total_score += weighted_score
        total_weight += weight

    # Normalize to 0-1 range (no signals = neutral 0.5)
    normalized_score = total_score / total_weight if total_weight > 0 else 0.5

    return ScoredCard(name=card_name, score=normalized_score, breakdown=breakdown)


def build_scored_pool(
    query: DeckQuery,
    card_names: set[str],
    card_db: dict[str, dict[str, Any]],
) -> ScoredCandidatePool:
    """
    Build a scored candidate pool from a query.

    INVARIANT: Pool is never empty if input was non-empty.
    Cards failing REQUIRED signals get score=0 but remain in pool.
    Select by top-N, not by threshold.

    Args:
        query: The semantic deck query
        card_names: Set of card names to consider
        card_db: Card database with oracle data

    Returns:
        ScoredCandidatePool with all cards scored and sorted
    """
    scored_cards = []

    for name in card_names:
        card_data = card_db.get(name, {})
        scored = score_card(name, card_data, query)
        scored_cards.append(scored)

    # Sort by score descending
    scored_cards.sort()

    return ScoredCandidatePool(
        scored_cards=tuple(scored_cards),
        query=query,
    )


def select_candidates(
    pool: ScoredCandidatePool,
    max_size: int = MAX_POOL_SIZE,
    min_size: int = MIN_POOL_SIZE,
) -> list[str]:
    """
    Select top candidates from a scored pool.

    Safety bounds:
    - Returns up to max_size cards
    - Returns at least min_size cards if available
    - Never returns empty if pool is non-empty

    Args:
        pool: The scored candidate pool
        max_size: Maximum cards to return (default 100)
        min_size: Minimum cards to return if available (default 10)

    Returns:
        List of card names, highest scoring first
    """
    if pool.is_empty():
        return []

    # Get top max_size cards
    candidates = pool.top(max_size)

    # If we have fewer than min_size, return everything we have
    # (never artificially expand - just don't shrink below threshold)
    if len(candidates) < min_size and pool.size >= min_size:
        candidates = pool.top(min_size)

    return candidates
