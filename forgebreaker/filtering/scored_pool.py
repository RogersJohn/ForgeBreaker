"""
Scored Candidate Pool - scoring replaces elimination.

INVARIANT: Cards are scored by query relevance, not eliminated.
This ends "empty pool" failures without relaxing correctness.

INVARIANT: Each selected card carries a ScoreBreakdown explaining its score.
This makes candidate selection explainable by construction.

Safety bounds preserved:
- MIN_POOL_SIZE = 10 (below this, fallback)
- MAX_POOL_SIZE = 100 (above this, return top 100)
"""

from dataclasses import dataclass, field
from enum import Enum
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

# Base score for all cards
BASE_SCORE = 100


class InclusionReason(str, Enum):
    """Why a card was included in the pool."""

    MATCHES_TRIBE = "matches_tribe"
    MATCHES_THEME = "matches_theme"
    MATCHES_COLOR = "matches_color"
    MATCHES_ARCHETYPE = "matches_archetype"
    FORMAT_LEGAL = "format_legal"
    BASE_INCLUSION = "base_inclusion"  # Always included with base score


class ExclusionReason(str, Enum):
    """Why a card was excluded (score=0)."""

    FORMAT_ILLEGAL = "format_illegal"
    REQUIRED_SIGNAL_FAILED = "required_signal_failed"


@dataclass(frozen=True, slots=True)
class ScoreBreakdown:
    """
    Detailed breakdown of a card's score.

    INVARIANT: Every selected card must carry this breakdown.
    This makes scoring explainable by construction.
    """

    base_score: int
    preference_contributions: dict[str, int] = field(default_factory=dict)
    inclusion_reasons: tuple[str, ...] = field(default_factory=tuple)
    exclusion_reason: str | None = None

    @property
    def total_score(self) -> int:
        """Total score = base + sum(contributions)."""
        if self.exclusion_reason:
            return 0
        return self.base_score + sum(self.preference_contributions.values())

    def explain(self) -> str:
        """Human-readable explanation of the score."""
        if self.exclusion_reason:
            return f"Excluded: {self.exclusion_reason}"

        parts = [f"Base: {self.base_score}"]
        for signal, contrib in self.preference_contributions.items():
            if contrib > 0:
                parts.append(f"+{contrib} ({signal})")
        parts.append(f"= {self.total_score}")

        return ", ".join(parts)


@dataclass(frozen=True, slots=True)
class ScoredCard:
    """
    A card with its relevance score and breakdown.

    INVARIANT: breakdown is always present and explains the score.
    """

    name: str
    score: int
    breakdown: ScoreBreakdown

    def __lt__(self, other: "ScoredCard") -> bool:
        """Sort by score descending."""
        return self.score > other.score


@dataclass(frozen=True)
class ScoredCandidatePool:
    """
    Candidate pool built by scoring, not elimination.

    INVARIANT: Pool is never empty if input was non-empty.
    Low-scoring cards are included at the bottom, not excluded.

    INVARIANT: Every card has a ScoreBreakdown explaining its score.
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
        Get top N cards with their scores and breakdowns.

        Args:
            n: Maximum number of cards to return

        Returns:
            List of ScoredCard objects with breakdowns, highest scoring first
        """
        return list(self.scored_cards[:n])

    def get_score(self, card_name: str) -> int:
        """
        Get score for a specific card.

        Returns 0 if card not in pool.
        """
        for card in self.scored_cards:
            if card.name == card_name:
                return card.score
        return 0

    def get_breakdown(self, card_name: str) -> ScoreBreakdown | None:
        """
        Get score breakdown for a specific card.

        Returns None if card not in pool.
        """
        for card in self.scored_cards:
            if card.name == card_name:
                return card.breakdown
        return None

    def get_included_cards(self) -> list[ScoredCard]:
        """
        Get all cards with score > 0 (not excluded).
        """
        return [c for c in self.scored_cards if c.score > 0]

    def get_excluded_cards(self) -> list[ScoredCard]:
        """
        Get all cards with score = 0 (excluded by REQUIRED signal).
        """
        return [c for c in self.scored_cards if c.score == 0]

    def is_empty(self) -> bool:
        """Check if pool is empty."""
        return len(self.scored_cards) == 0

    def explain_card(self, card_name: str) -> str:
        """
        Get human-readable explanation for a card's score.

        Returns explanation string or "Card not in pool".
        """
        breakdown = self.get_breakdown(card_name)
        if breakdown is None:
            return "Card not in pool"
        return breakdown.explain()


# =============================================================================
# SCORING FUNCTIONS
# =============================================================================


def _score_tribe_match(card_data: dict[str, Any], tribe: str) -> tuple[int, str | None]:
    """
    Score how well a card matches a tribe signal.

    Returns:
        (score, reason) tuple
        - (50, "matches_tribe") - Card IS the tribe (type_line contains tribe)
        - (25, "matches_tribe") - Card SYNERGIZES with tribe (oracle text mentions tribe)
        - (0, None) - No tribal relevance
    """
    type_line = card_data.get("type_line", "").lower()
    oracle_text = card_data.get("oracle_text", "").lower()
    tribe_lower = tribe.lower()

    # Direct tribe match in type line
    if tribe_lower in type_line:
        return (50, InclusionReason.MATCHES_TRIBE.value)

    # Tribal synergy in oracle text (e.g., "Goblin creatures you control")
    if tribe_lower in oracle_text:
        return (25, InclusionReason.MATCHES_TRIBE.value)

    return (0, None)


def _score_theme_match(card_data: dict[str, Any], theme: str) -> tuple[int, str | None]:
    """
    Score how well a card matches a theme signal.

    Returns:
        (score, reason) tuple
    """
    name = card_data.get("name", "").lower()
    type_line = card_data.get("type_line", "").lower()
    oracle_text = card_data.get("oracle_text", "").lower()
    theme_lower = theme.lower()

    # Theme in name or type line
    if theme_lower in name or theme_lower in type_line:
        return (50, InclusionReason.MATCHES_THEME.value)

    # Theme in oracle text
    if theme_lower in oracle_text:
        return (35, InclusionReason.MATCHES_THEME.value)

    return (0, None)


def _score_color_match(card_data: dict[str, Any], colors: frozenset[str]) -> tuple[int, str | None]:
    """
    Score how well a card matches color signals.

    Returns:
        (score, reason) tuple
    """
    card_colors = set(card_data.get("colors", []))
    card_identity = set(card_data.get("color_identity", []))

    # Colorless cards are always fine
    if not card_colors and not card_identity:
        return (25, InclusionReason.MATCHES_COLOR.value)

    # Check if card's identity is subset of allowed colors
    if card_identity <= colors:
        return (50, InclusionReason.MATCHES_COLOR.value)

    # Card has colors outside the allowed set - penalty but not excluded
    return (0, None)


def _score_archetype_match(card_data: dict[str, Any], archetype: str) -> tuple[int, str | None]:
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
                return (50, InclusionReason.MATCHES_ARCHETYPE.value)
            return (35, InclusionReason.MATCHES_ARCHETYPE.value)
        return (10, InclusionReason.MATCHES_ARCHETYPE.value)

    if archetype_lower == "control":
        # Control likes counterspells, removal, draw
        if "counter target" in oracle_text or "destroy target" in oracle_text:
            return (50, InclusionReason.MATCHES_ARCHETYPE.value)
        if "draw" in oracle_text and "card" in oracle_text:
            return (40, InclusionReason.MATCHES_ARCHETYPE.value)
        return (10, InclusionReason.MATCHES_ARCHETYPE.value)

    if archetype_lower == "midrange":
        # Midrange likes value creatures
        if "creature" in type_line and 3 <= cmc <= 5:
            return (40, InclusionReason.MATCHES_ARCHETYPE.value)
        return (15, InclusionReason.MATCHES_ARCHETYPE.value)

    if archetype_lower == "combo":
        # Combo likes cards that search or enable
        if "search" in oracle_text or "untap" in oracle_text:
            return (40, InclusionReason.MATCHES_ARCHETYPE.value)
        return (10, InclusionReason.MATCHES_ARCHETYPE.value)

    # Unknown archetype - neutral score
    return (15, None)


def _score_format_match(
    card_data: dict[str, Any], format_name: str
) -> tuple[int, str | None, str | None]:
    """
    Score format legality.

    Returns:
        (score, inclusion_reason, exclusion_reason) tuple
        - (0, None, "format_illegal") - Not legal = excluded
        - (0, "format_legal", None) - Legal (no bonus, but included)
    """
    legalities = card_data.get("legalities", {})
    if legalities.get(format_name) == "legal":
        return (0, InclusionReason.FORMAT_LEGAL.value, None)
    return (0, None, ExclusionReason.FORMAT_ILLEGAL.value)


def _score_signal(
    card_data: dict[str, Any], signal: QuerySignal
) -> tuple[int, str | None, str | None]:
    """
    Score a card against a single signal.

    Returns:
        (score, inclusion_reason, exclusion_reason) tuple
    """
    if signal.signal_type == QuerySignalType.TRIBE:
        score, reason = _score_tribe_match(card_data, signal.value)
        return (score, reason, None)
    if signal.signal_type == QuerySignalType.THEME:
        score, reason = _score_theme_match(card_data, signal.value)
        return (score, reason, None)
    if signal.signal_type == QuerySignalType.COLOR:
        score, reason = _score_color_match(card_data, frozenset([signal.value]))
        return (score, reason, None)
    if signal.signal_type == QuerySignalType.ARCHETYPE:
        score, reason = _score_archetype_match(card_data, signal.value)
        return (score, reason, None)
    if signal.signal_type == QuerySignalType.FORMAT:
        return _score_format_match(card_data, signal.value)

    # Unknown signal type - neutral score
    return (25, None, None)


def _get_strength_weight(strength: SignalStrength) -> float:
    """
    Get the weight multiplier for a signal strength.
    """
    weights = {
        SignalStrength.REQUIRED: 1.0,  # Required doesn't add bonus, just validates
        SignalStrength.STRONG: 1.0,
        SignalStrength.MODERATE: 0.6,
        SignalStrength.WEAK: 0.3,
    }
    return weights.get(strength, 1.0)


def score_card(card_name: str, card_data: dict[str, Any], query: DeckQuery) -> ScoredCard:
    """
    Score a card against all query signals.

    INVARIANT: Returns a ScoreBreakdown explaining the score.
    INVARIANT: Required signals that fail result in exclusion with reason.
    Preference signals modulate the score but don't eliminate.
    """
    preference_contributions: dict[str, int] = {}
    inclusion_reasons: list[str] = [InclusionReason.BASE_INCLUSION.value]
    exclusion_reason: str | None = None

    for signal in query.signals:
        raw_score, inc_reason, exc_reason = _score_signal(card_data, signal)
        weight = _get_strength_weight(signal.strength)

        # Required signals that fail = immediate exclusion
        if signal.is_required() and exc_reason:
            failed = ExclusionReason.REQUIRED_SIGNAL_FAILED.value
            exclusion_reason = f"{failed}: {signal.signal_type.value}={signal.value}"
            breakdown = ScoreBreakdown(
                base_score=BASE_SCORE,
                preference_contributions={},
                inclusion_reasons=(),
                exclusion_reason=exclusion_reason,
            )
            return ScoredCard(name=card_name, score=0, breakdown=breakdown)

        # Add weighted score contribution
        weighted_score = int(raw_score * weight)
        if weighted_score > 0:
            signal_key = f"{signal.signal_type.value}:{signal.value}"
            preference_contributions[signal_key] = weighted_score

        # Track inclusion reason
        if inc_reason and inc_reason not in inclusion_reasons:
            inclusion_reasons.append(inc_reason)

    breakdown = ScoreBreakdown(
        base_score=BASE_SCORE,
        preference_contributions=preference_contributions,
        inclusion_reasons=tuple(inclusion_reasons),
        exclusion_reason=exclusion_reason,
    )

    return ScoredCard(name=card_name, score=breakdown.total_score, breakdown=breakdown)


def build_scored_pool(
    query: DeckQuery,
    card_names: set[str],
    card_db: dict[str, dict[str, Any]],
) -> ScoredCandidatePool:
    """
    Build a scored candidate pool from a query.

    INVARIANT: Pool is never empty if input was non-empty.
    INVARIANT: Every card has a ScoreBreakdown.
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


class PoolBuildError(Exception):
    """Error building candidate pool."""

    def __init__(self, message: str, binding_constraint: str) -> None:
        self.binding_constraint = binding_constraint
        super().__init__(f"{message} (binding constraint: {binding_constraint})")


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

    INVARIANT: Failure messages state which constraint was binding.

    Args:
        pool: The scored candidate pool
        max_size: Maximum cards to return (default 100)
        min_size: Minimum cards to return if available (default 10)

    Returns:
        List of card names, highest scoring first

    Raises:
        PoolBuildError: If pool has no valid candidates (all excluded)
    """
    if pool.is_empty():
        return []

    # Get cards with score > 0
    valid_cards = pool.get_included_cards()

    if not valid_cards:
        # All cards were excluded - report binding constraint
        excluded = pool.get_excluded_cards()
        if excluded:
            first_reason = excluded[0].breakdown.exclusion_reason or "unknown"
            raise PoolBuildError(
                f"All {len(excluded)} candidates were excluded",
                binding_constraint=first_reason,
            )
        return []

    # Get top max_size cards from valid cards
    candidates = [c.name for c in valid_cards[:max_size]]

    # If we have fewer than min_size, return everything we have
    if len(candidates) < min_size and len(valid_cards) >= min_size:
        candidates = [c.name for c in valid_cards[:min_size]]

    return candidates
