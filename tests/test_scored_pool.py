"""
Tests for PR5: Scored Candidate Pool Builder.

INVARIANT: Cards are scored by relevance, not eliminated.
Pool is never empty unless truly impossible.
"""

import pytest

from forgebreaker.filtering.scored_pool import (
    MAX_POOL_SIZE,
    MIN_POOL_SIZE,
    ScoredCard,
    build_scored_pool,
    score_card,
    select_candidates,
)
from forgebreaker.models.deck_query import DeckQuery

# =============================================================================
# TEST FIXTURES
# =============================================================================


@pytest.fixture
def card_db() -> dict:
    """Test card database with diverse cards."""
    return {
        # Goblin creatures
        "Goblin Guide": {
            "name": "Goblin Guide",
            "type_line": "Creature — Goblin Scout",
            "oracle_text": "Haste. Whenever Goblin Guide attacks...",
            "colors": ["R"],
            "color_identity": ["R"],
            "cmc": 1,
            "legalities": {"standard": "not_legal", "historic": "legal"},
        },
        "Goblin Warchief": {
            "name": "Goblin Warchief",
            "type_line": "Creature — Goblin Warrior",
            "oracle_text": "Goblin spells you cast cost 1 less. Goblins you control have haste.",
            "colors": ["R"],
            "color_identity": ["R"],
            "cmc": 3,
            "legalities": {"standard": "not_legal", "historic": "legal"},
        },
        # Goblin synergy (not a Goblin itself)
        "Goblin Bombardment": {
            "name": "Goblin Bombardment",
            "type_line": "Enchantment",
            "oracle_text": "Sacrifice a creature: Goblin Bombardment deals 1 damage...",
            "colors": ["R"],
            "color_identity": ["R"],
            "cmc": 2,
            "legalities": {"standard": "not_legal", "historic": "legal"},
        },
        # Non-Goblin red creature
        "Lightning Bolt": {
            "name": "Lightning Bolt",
            "type_line": "Instant",
            "oracle_text": "Lightning Bolt deals 3 damage...",
            "colors": ["R"],
            "color_identity": ["R"],
            "cmc": 1,
            "legalities": {"standard": "not_legal", "historic": "legal"},
        },
        # Blue control card
        "Counterspell": {
            "name": "Counterspell",
            "type_line": "Instant",
            "oracle_text": "Counter target spell.",
            "colors": ["U"],
            "color_identity": ["U"],
            "cmc": 2,
            "legalities": {"standard": "not_legal", "historic": "legal"},
        },
        # Colorless
        "Sol Ring": {
            "name": "Sol Ring",
            "type_line": "Artifact",
            "oracle_text": "Tap: Add two colorless mana.",
            "colors": [],
            "color_identity": [],
            "cmc": 1,
            "legalities": {"standard": "not_legal", "historic": "legal"},
        },
        # Standard legal
        "Mountain": {
            "name": "Mountain",
            "type_line": "Basic Land — Mountain",
            "oracle_text": "",
            "colors": [],
            "color_identity": [],
            "cmc": 0,
            "legalities": {"standard": "legal", "historic": "legal"},
        },
    }


# =============================================================================
# CORE INVARIANT TESTS: SCORING NOT ELIMINATION
# =============================================================================


class TestScoringNotElimination:
    """
    Tests proving cards are scored, not eliminated.
    """

    def test_all_cards_in_pool(self, card_db: dict) -> None:
        """
        CRITICAL: All cards appear in the scored pool.

        Non-matching cards get low scores, not excluded.
        """
        query = DeckQuery.for_tribal("Goblin")
        pool = build_scored_pool(query, set(card_db.keys()), card_db)

        # ALL cards are in the pool
        assert pool.size == len(card_db)

        # Every card has a score
        for card_name in card_db:
            assert pool.get_score(card_name) >= 0

    def test_low_score_cards_not_excluded(self, card_db: dict) -> None:
        """
        Low-scoring cards remain in pool, just ranked lower.
        """
        query = DeckQuery.for_tribal("Goblin", colors=["R"])
        pool = build_scored_pool(query, set(card_db.keys()), card_db)

        # Counterspell (blue, not goblin) is still in pool
        counterspell_score = pool.get_score("Counterspell")
        assert counterspell_score >= 0  # Still has a score
        assert "Counterspell" in [c.name for c in pool.scored_cards]

    def test_pool_never_empty(self, card_db: dict) -> None:
        """
        Pool is never empty if input was non-empty.
        """
        # Even with impossible query, pool contains all cards
        query = DeckQuery.for_tribal("NonExistentTribe")
        pool = build_scored_pool(query, set(card_db.keys()), card_db)

        assert not pool.is_empty()
        assert pool.size == len(card_db)


class TestGoblinDeckScoring:
    """
    Tests for Goblin deck query scoring.

    REQUIREMENT: Goblin deck succeeds on real collection.
    """

    def test_goblin_creatures_score_highest(self, card_db: dict) -> None:
        """
        Goblin creatures score highest for Goblin query.
        """
        query = DeckQuery.for_tribal("Goblin")
        pool = build_scored_pool(query, set(card_db.keys()), card_db)

        goblin_guide_score = pool.get_score("Goblin Guide")
        goblin_warchief_score = pool.get_score("Goblin Warchief")
        bolt_score = pool.get_score("Lightning Bolt")

        # Goblins score higher than non-Goblins
        assert goblin_guide_score > bolt_score
        assert goblin_warchief_score > bolt_score

    def test_goblin_synergy_cards_score_well(self, card_db: dict) -> None:
        """
        Goblin-synergy cards (not Goblins) score well.

        "Goblin Bombardment" mentions Goblins and should score
        higher than generic red cards.
        """
        query = DeckQuery.for_tribal("Goblin")
        pool = build_scored_pool(query, set(card_db.keys()), card_db)

        bombardment_score = pool.get_score("Goblin Bombardment")
        bolt_score = pool.get_score("Lightning Bolt")

        # Goblin Bombardment has "Goblin" in oracle text
        # It should score better than Lightning Bolt
        assert bombardment_score > bolt_score

    def test_top_cards_are_goblins(self, card_db: dict) -> None:
        """
        Top-ranked cards for Goblin query are Goblins.
        """
        query = DeckQuery.for_tribal("Goblin", colors=["R"])
        pool = build_scored_pool(query, set(card_db.keys()), card_db)

        # Get top 3 cards
        top_3 = pool.top(3)

        # Top cards should include Goblins
        goblin_cards = {"Goblin Guide", "Goblin Warchief", "Goblin Bombardment"}
        assert any(card in goblin_cards for card in top_3)


class TestFormatLegalityScoring:
    """
    Tests for format legality scoring.
    """

    def test_illegal_cards_score_zero(self, card_db: dict) -> None:
        """
        Format-illegal cards get score 0 (REQUIRED signal fails).
        """
        query = DeckQuery.for_tribal("Goblin", format="standard")
        pool = build_scored_pool(query, set(card_db.keys()), card_db)

        # Goblin Guide is NOT Standard-legal
        goblin_guide_score = pool.get_score("Goblin Guide")
        assert goblin_guide_score == 0.0

        # Mountain IS Standard-legal
        mountain_score = pool.get_score("Mountain")
        assert mountain_score > 0.0

    def test_format_required_signal_dominates(self, card_db: dict) -> None:
        """
        Format legality dominates other signals (REQUIRED).
        """
        query = DeckQuery.for_tribal("Goblin", format="standard")
        pool = build_scored_pool(query, set(card_db.keys()), card_db)

        # Even though Goblin Guide is a perfect Goblin, it's not legal
        goblin_guide_score = pool.get_score("Goblin Guide")

        # Mountain is legal (even though not a Goblin)
        mountain_score = pool.get_score("Mountain")

        # Legal card beats illegal card (even perfect match)
        assert mountain_score > goblin_guide_score


class TestSafetyBounds:
    """
    Tests for safety bounds preservation.
    """

    def test_min_pool_size_constant(self) -> None:
        """
        MIN_POOL_SIZE is 10.
        """
        assert MIN_POOL_SIZE == 10

    def test_max_pool_size_constant(self) -> None:
        """
        MAX_POOL_SIZE is 100.
        """
        assert MAX_POOL_SIZE == 100

    def test_select_candidates_respects_max(self, card_db: dict) -> None:
        """
        select_candidates returns at most max_size cards.
        """
        query = DeckQuery.for_tribal("Goblin")
        pool = build_scored_pool(query, set(card_db.keys()), card_db)

        # Request up to 3 cards
        candidates = select_candidates(pool, max_size=3)

        assert len(candidates) <= 3

    def test_select_candidates_respects_available(self, card_db: dict) -> None:
        """
        select_candidates returns all available if less than min.
        """
        query = DeckQuery.for_tribal("Goblin")
        pool = build_scored_pool(query, set(card_db.keys()), card_db)

        # Pool has 7 cards, request min_size=10
        candidates = select_candidates(pool, min_size=10)

        # Returns all 7 (doesn't artificially expand)
        assert len(candidates) == pool.size


class TestNoRetriesNoSilentRelaxations:
    """
    Tests ensuring no retries or silent relaxations.
    """

    def test_scoring_is_deterministic(self, card_db: dict) -> None:
        """
        Same query + cards = same scores.
        """
        query = DeckQuery.for_tribal("Goblin")

        pool1 = build_scored_pool(query, set(card_db.keys()), card_db)
        pool2 = build_scored_pool(query, set(card_db.keys()), card_db)

        for card_name in card_db:
            assert pool1.get_score(card_name) == pool2.get_score(card_name)

    def test_no_query_relaxation(self, card_db: dict) -> None:
        """
        Query is not silently relaxed if results are poor.
        """
        # Query for non-existent tribe
        query = DeckQuery.for_tribal("NonExistentTribe")
        pool = build_scored_pool(query, set(card_db.keys()), card_db)

        # All cards get low scores (no tribe match)
        for card in pool.scored_cards:
            # No card should have high tribe score
            if "tribe:NonExistentTribe" in card.breakdown:
                assert card.breakdown["tribe:NonExistentTribe"] == 0.0


class TestScoredCardModel:
    """
    Tests for ScoredCard dataclass.
    """

    def test_scored_card_ordering(self) -> None:
        """
        ScoredCards sort by score descending.
        """
        high = ScoredCard(name="High", score=0.9)
        medium = ScoredCard(name="Medium", score=0.5)
        low = ScoredCard(name="Low", score=0.1)

        cards = [medium, low, high]
        cards.sort()

        assert cards[0].name == "High"
        assert cards[1].name == "Medium"
        assert cards[2].name == "Low"

    def test_scored_card_breakdown(self, card_db: dict) -> None:
        """
        ScoredCard includes score breakdown.
        """
        query = DeckQuery.for_tribal("Goblin", colors=["R"])

        scored = score_card("Goblin Guide", card_db["Goblin Guide"], query)

        # Breakdown includes signal components
        assert len(scored.breakdown) > 0


class TestPoolOperations:
    """
    Tests for ScoredCandidatePool operations.
    """

    def test_top_returns_card_names(self, card_db: dict) -> None:
        """
        top() returns card names in score order.
        """
        query = DeckQuery.for_tribal("Goblin")
        pool = build_scored_pool(query, set(card_db.keys()), card_db)

        top_2 = pool.top(2)

        assert len(top_2) == 2
        assert all(isinstance(name, str) for name in top_2)

    def test_top_with_scores_returns_scored_cards(self, card_db: dict) -> None:
        """
        top_with_scores() returns ScoredCard objects.
        """
        query = DeckQuery.for_tribal("Goblin")
        pool = build_scored_pool(query, set(card_db.keys()), card_db)

        top_2 = pool.top_with_scores(2)

        assert len(top_2) == 2
        assert all(isinstance(card, ScoredCard) for card in top_2)

    def test_get_score_missing_card(self, card_db: dict) -> None:
        """
        get_score() returns 0.0 for missing cards.
        """
        query = DeckQuery.for_tribal("Goblin")
        pool = build_scored_pool(query, set(card_db.keys()), card_db)

        assert pool.get_score("Non Existent Card") == 0.0


class TestColorScoring:
    """
    Tests for color matching in scoring.
    """

    def test_colorless_cards_neutral_score(self, card_db: dict) -> None:
        """
        Colorless cards get neutral color score.
        """
        query = DeckQuery.for_tribal("Goblin", colors=["R"])
        pool = build_scored_pool(query, set(card_db.keys()), card_db)

        sol_ring_score = pool.get_score("Sol Ring")

        # Sol Ring is colorless - should have some score
        assert sol_ring_score > 0

    def test_wrong_color_low_score(self, card_db: dict) -> None:
        """
        Wrong-colored cards score lower.
        """
        query = DeckQuery.for_tribal("Goblin", colors=["R"])
        pool = build_scored_pool(query, set(card_db.keys()), card_db)

        counterspell_score = pool.get_score("Counterspell")
        goblin_guide_score = pool.get_score("Goblin Guide")

        # Blue card scores lower than red Goblin
        assert counterspell_score < goblin_guide_score
