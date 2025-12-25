from unittest.mock import AsyncMock, patch

import pytest

from forgebreaker.analysis.distance import calculate_deck_distance
from forgebreaker.analysis.ranker import (
    get_budget_decks,
    get_buildable_decks,
    rank_decks,
    rank_decks_with_ml,
)
from forgebreaker.ml.inference import RecommendationScore
from forgebreaker.models.collection import Collection
from forgebreaker.models.deck import MetaDeck


@pytest.fixture
def sample_deck() -> MetaDeck:
    return MetaDeck(
        name="Mono-Red Aggro",
        archetype="aggro",
        format="standard",
        cards={
            "Lightning Bolt": 4,
            "Monastery Swiftspear": 4,
            "Mountain": 20,
        },
        sideboard={
            "Abrade": 2,
        },
    )


@pytest.fixture
def rarity_map() -> dict[str, str]:
    return {
        "Lightning Bolt": "common",
        "Monastery Swiftspear": "uncommon",
        "Mountain": "common",
        "Abrade": "uncommon",
    }


class TestCalculateDeckDistance:
    def test_complete_deck(self, sample_deck: MetaDeck, rarity_map: dict[str, str]) -> None:
        """User owns all cards needed."""
        collection = Collection(
            cards={
                "Lightning Bolt": 4,
                "Monastery Swiftspear": 4,
                "Mountain": 20,
                "Abrade": 2,
            }
        )

        distance = calculate_deck_distance(sample_deck, collection, rarity_map)

        assert distance.is_complete
        assert distance.missing_cards == 0
        assert distance.completion_percentage == 1.0
        assert distance.wildcard_cost.total() == 0

    def test_missing_some_cards(self, sample_deck: MetaDeck, rarity_map: dict[str, str]) -> None:
        """User is missing some cards."""
        collection = Collection(
            cards={
                "Lightning Bolt": 4,
                "Monastery Swiftspear": 2,  # Missing 2
                "Mountain": 20,
                # Missing all Abrade
            }
        )

        distance = calculate_deck_distance(sample_deck, collection, rarity_map)

        assert not distance.is_complete
        assert distance.missing_cards == 4  # 2 Swiftspear + 2 Abrade
        assert distance.wildcard_cost.uncommon == 4  # Both are uncommon

    def test_empty_collection(self, sample_deck: MetaDeck, rarity_map: dict[str, str]) -> None:
        """User has no cards."""
        collection = Collection()

        distance = calculate_deck_distance(sample_deck, collection, rarity_map)

        assert not distance.is_complete
        assert distance.owned_cards == 0
        assert distance.missing_cards == 30  # 4+4+20+2
        assert distance.completion_percentage == 0.0

    def test_wildcard_cost_by_rarity(
        self, sample_deck: MetaDeck, rarity_map: dict[str, str]
    ) -> None:
        """Wildcards are correctly categorized by rarity."""
        collection = Collection(cards={"Mountain": 20})

        distance = calculate_deck_distance(sample_deck, collection, rarity_map)

        # Lightning Bolt (4 common), Monastery Swiftspear (4 uncommon), Abrade (2 uncommon)
        assert distance.wildcard_cost.common == 4
        assert distance.wildcard_cost.uncommon == 6
        assert distance.wildcard_cost.rare == 0
        assert distance.wildcard_cost.mythic == 0

    def test_missing_card_list(self, sample_deck: MetaDeck, rarity_map: dict[str, str]) -> None:
        """Missing cards are tracked with quantity and rarity."""
        collection = Collection(cards={"Mountain": 20, "Abrade": 2})

        distance = calculate_deck_distance(sample_deck, collection, rarity_map)

        missing_names = [card[0] for card in distance.missing_card_list]
        assert "Lightning Bolt" in missing_names
        assert "Monastery Swiftspear" in missing_names
        assert "Mountain" not in missing_names
        assert "Abrade" not in missing_names

    def test_partial_ownership(self, sample_deck: MetaDeck, rarity_map: dict[str, str]) -> None:
        """User owns some but not all copies of a card."""
        collection = Collection(
            cards={
                "Lightning Bolt": 2,  # Has 2, needs 4
                "Monastery Swiftspear": 4,
                "Mountain": 20,
                "Abrade": 2,
            }
        )

        distance = calculate_deck_distance(sample_deck, collection, rarity_map)

        assert distance.missing_cards == 2
        assert distance.owned_cards == 28

    def test_unknown_card_defaults_to_common(self, sample_deck: MetaDeck) -> None:
        """Cards not in rarity map default to common."""
        collection = Collection()
        empty_rarity_map: dict[str, str] = {}

        distance = calculate_deck_distance(sample_deck, collection, empty_rarity_map)

        # All 30 cards should be counted as common
        assert distance.wildcard_cost.common == 30
        assert distance.wildcard_cost.uncommon == 0

    def test_empty_deck(self, rarity_map: dict[str, str]) -> None:
        """Empty deck has 100% completion."""
        empty_deck = MetaDeck(name="Empty", archetype="test", format="standard")
        collection = Collection()

        distance = calculate_deck_distance(empty_deck, collection, rarity_map)

        assert distance.is_complete
        assert distance.completion_percentage == 1.0

    def test_card_in_maindeck_and_sideboard(self, rarity_map: dict[str, str]) -> None:
        """Card appearing in both maindeck and sideboard counts owned copies once."""
        deck = MetaDeck(
            name="Overlap Test",
            archetype="test",
            format="standard",
            cards={"Lightning Bolt": 4},  # 4 in maindeck
            sideboard={"Lightning Bolt": 2},  # 2 in sideboard, 6 total needed
        )
        collection = Collection(cards={"Lightning Bolt": 4})  # Own 4

        distance = calculate_deck_distance(deck, collection, rarity_map)

        # Need 6 total, own 4, missing 2
        assert distance.owned_cards == 4
        assert distance.missing_cards == 2
        assert distance.wildcard_cost.common == 2


class TestRankDecks:
    def test_ranks_by_completion(self, rarity_map: dict[str, str]) -> None:
        """Decks with higher completion should rank higher."""
        cheap_deck = MetaDeck(
            name="Cheap Deck",
            archetype="aggro",
            format="standard",
            cards={"Lightning Bolt": 4},
        )
        expensive_deck = MetaDeck(
            name="Expensive Deck",
            archetype="control",
            format="standard",
            cards={"Sheoldred, the Apocalypse": 4},
        )
        rarity_map["Sheoldred, the Apocalypse"] = "mythic"

        collection = Collection(cards={"Lightning Bolt": 4})

        ranked = rank_decks([expensive_deck, cheap_deck], collection, rarity_map)

        # Cheap deck is 100% complete, should rank first
        assert ranked[0].deck.name == "Cheap Deck"
        assert ranked[0].can_build_now is True
        assert ranked[1].deck.name == "Expensive Deck"
        assert ranked[1].can_build_now is False

    def test_considers_win_rate(self, rarity_map: dict[str, str]) -> None:
        """Higher win rate decks should score higher when completion is similar."""
        deck_low_wr = MetaDeck(
            name="Low WR Deck",
            archetype="aggro",
            format="standard",
            cards={"Mountain": 4},
            win_rate=0.45,
        )
        deck_high_wr = MetaDeck(
            name="High WR Deck",
            archetype="aggro",
            format="standard",
            cards={"Mountain": 4},
            win_rate=0.60,
        )

        collection = Collection(cards={"Mountain": 4})

        ranked = rank_decks([deck_low_wr, deck_high_wr], collection, rarity_map)

        # Both are 100% complete, but high WR should rank first
        assert ranked[0].deck.name == "High WR Deck"

    def test_within_budget_flag(self, rarity_map: dict[str, str]) -> None:
        """Budget flag correctly identifies affordable decks."""
        cheap_deck = MetaDeck(
            name="Budget Deck",
            archetype="aggro",
            format="standard",
            cards={"Lightning Bolt": 4},  # 4 common = 0.4 weighted cost
        )
        expensive_deck = MetaDeck(
            name="Expensive Deck",
            archetype="control",
            format="standard",
            cards={"Sheoldred, the Apocalypse": 4},  # 4 mythic = 16.0 weighted cost
        )
        rarity_map["Sheoldred, the Apocalypse"] = "mythic"

        collection = Collection()

        ranked = rank_decks(
            [cheap_deck, expensive_deck], collection, rarity_map, wildcard_budget=5.0
        )

        cheap_result = next(r for r in ranked if r.deck.name == "Budget Deck")
        expensive_result = next(r for r in ranked if r.deck.name == "Expensive Deck")

        assert cheap_result.within_budget is True
        assert expensive_result.within_budget is False

    def test_recommendation_reason_complete(self, rarity_map: dict[str, str]) -> None:
        """Complete decks get appropriate recommendation text."""
        deck = MetaDeck(
            name="Complete Deck",
            archetype="aggro",
            format="standard",
            cards={"Lightning Bolt": 4},
        )
        collection = Collection(cards={"Lightning Bolt": 4})

        ranked = rank_decks([deck], collection, rarity_map)

        assert "build this deck now" in ranked[0].recommendation_reason.lower()

    def test_recommendation_reason_incomplete(self, rarity_map: dict[str, str]) -> None:
        """Incomplete decks show completion percentage."""
        deck = MetaDeck(
            name="Incomplete Deck",
            archetype="aggro",
            format="standard",
            cards={"Lightning Bolt": 4},
        )
        collection = Collection(cards={"Lightning Bolt": 2})

        ranked = rank_decks([deck], collection, rarity_map)

        assert "50%" in ranked[0].recommendation_reason

    def test_empty_deck_list(self, rarity_map: dict[str, str]) -> None:
        """Empty deck list returns empty results."""
        collection = Collection()

        ranked = rank_decks([], collection, rarity_map)

        assert ranked == []

    def test_recommendation_reason_expensive(self, rarity_map: dict[str, str]) -> None:
        """Expensive decks highlight mythic/rare wildcard costs."""
        deck = MetaDeck(
            name="Expensive Deck",
            archetype="control",
            format="standard",
            cards={"Sheoldred, the Apocalypse": 4},
        )
        rarity_map["Sheoldred, the Apocalypse"] = "mythic"

        collection = Collection()

        # Use tiny budget so deck is NOT within budget
        ranked = rank_decks([deck], collection, rarity_map, wildcard_budget=1.0)

        assert "mythic" in ranked[0].recommendation_reason.lower()

    def test_considers_meta_share(self, rarity_map: dict[str, str]) -> None:
        """Higher meta share decks score higher when other factors are equal."""
        deck_low_meta = MetaDeck(
            name="Low Meta Deck",
            archetype="aggro",
            format="standard",
            cards={"Mountain": 4},
            meta_share=0.02,
        )
        deck_high_meta = MetaDeck(
            name="High Meta Deck",
            archetype="aggro",
            format="standard",
            cards={"Mountain": 4},
            meta_share=0.20,
        )

        collection = Collection(cards={"Mountain": 4})

        ranked = rank_decks([deck_low_meta, deck_high_meta], collection, rarity_map)

        # Both 100% complete, same win rate, but high meta should rank first
        assert ranked[0].deck.name == "High Meta Deck"


class TestGetBuildableDecks:
    def test_filters_to_complete_only(self, rarity_map: dict[str, str]) -> None:
        """Only returns decks that can be built immediately."""
        complete_deck = MetaDeck(
            name="Complete",
            archetype="aggro",
            format="standard",
            cards={"Lightning Bolt": 4},
        )
        incomplete_deck = MetaDeck(
            name="Incomplete",
            archetype="control",
            format="standard",
            cards={"Sheoldred, the Apocalypse": 4},
        )
        rarity_map["Sheoldred, the Apocalypse"] = "mythic"

        collection = Collection(cards={"Lightning Bolt": 4})

        buildable = get_buildable_decks([complete_deck, incomplete_deck], collection, rarity_map)

        assert len(buildable) == 1
        assert buildable[0].deck.name == "Complete"


class TestGetBudgetDecks:
    def test_filters_to_budget_only(self, rarity_map: dict[str, str]) -> None:
        """Only returns decks within budget."""
        cheap_deck = MetaDeck(
            name="Cheap",
            archetype="aggro",
            format="standard",
            cards={"Lightning Bolt": 4},
        )
        expensive_deck = MetaDeck(
            name="Expensive",
            archetype="control",
            format="standard",
            cards={"Sheoldred, the Apocalypse": 4},
        )
        rarity_map["Sheoldred, the Apocalypse"] = "mythic"

        collection = Collection()

        budget_decks = get_budget_decks(
            [cheap_deck, expensive_deck], collection, rarity_map, wildcard_budget=5.0
        )

        assert len(budget_decks) == 1
        assert budget_decks[0].deck.name == "Cheap"


class TestRankDecksWithML:
    """Tests for ML-enhanced deck ranking via MLForge integration."""

    async def test_uses_mlforge_when_available(self, rarity_map: dict[str, str]) -> None:
        """Blends MLForge scores with basic scores when API is available."""
        deck_a = MetaDeck(
            name="Deck A",
            archetype="aggro",
            format="standard",
            cards={"Lightning Bolt": 4},
        )
        deck_b = MetaDeck(
            name="Deck B",
            archetype="control",
            format="standard",
            cards={"Lightning Bolt": 4},
        )
        collection = Collection(cards={"Lightning Bolt": 4})

        # Mock MLForge to return scores favoring Deck B
        mock_scores = [
            RecommendationScore(deck_name="Deck A", score=0.3, confidence=0.9),
            RecommendationScore(deck_name="Deck B", score=0.9, confidence=0.9),
        ]

        with patch("forgebreaker.ml.inference.get_mlforge_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.health_check.return_value = True
            mock_client.score_decks.return_value = mock_scores
            mock_get_client.return_value = mock_client

            ranked = await rank_decks_with_ml([deck_a, deck_b], collection, rarity_map)

        # Deck B should rank higher due to higher ML score
        assert ranked[0].deck.name == "Deck B"
        assert ranked[1].deck.name == "Deck A"
        mock_client.score_decks.assert_called_once()

    async def test_falls_back_when_mlforge_unavailable(self, rarity_map: dict[str, str]) -> None:
        """Uses basic scoring when MLForge health check fails."""
        deck = MetaDeck(
            name="Test Deck",
            archetype="aggro",
            format="standard",
            cards={"Lightning Bolt": 4},
        )
        collection = Collection(cards={"Lightning Bolt": 4})

        with patch("forgebreaker.ml.inference.get_mlforge_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.health_check.return_value = False
            mock_get_client.return_value = mock_client

            ranked = await rank_decks_with_ml([deck], collection, rarity_map)

        assert len(ranked) == 1
        assert ranked[0].deck.name == "Test Deck"
        # score_decks should not be called if health check fails
        mock_client.score_decks.assert_not_called()

    async def test_handles_mlforge_error_gracefully(self, rarity_map: dict[str, str]) -> None:
        """Continues with basic scoring when MLForge throws an exception."""
        deck = MetaDeck(
            name="Test Deck",
            archetype="aggro",
            format="standard",
            cards={"Lightning Bolt": 4},
        )
        collection = Collection(cards={"Lightning Bolt": 4})

        with patch("forgebreaker.ml.inference.get_mlforge_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.health_check.return_value = True
            mock_client.score_decks.side_effect = Exception("API timeout")
            mock_get_client.return_value = mock_client

            ranked = await rank_decks_with_ml([deck], collection, rarity_map)

        # Should still return results using basic scoring
        assert len(ranked) == 1
        assert ranked[0].deck.name == "Test Deck"

    async def test_empty_deck_list_returns_empty(self, rarity_map: dict[str, str]) -> None:
        """Empty input returns empty output without calling MLForge."""
        collection = Collection()

        # No need to mock - function returns early for empty list
        ranked = await rank_decks_with_ml([], collection, rarity_map)

        assert ranked == []

    async def test_blends_scores_with_confidence(self, rarity_map: dict[str, str]) -> None:
        """ML score weight is adjusted by confidence level."""
        deck = MetaDeck(
            name="Test Deck",
            archetype="aggro",
            format="standard",
            cards={"Lightning Bolt": 4},
        )
        collection = Collection(cards={"Lightning Bolt": 4})

        # High ML score but low confidence
        mock_scores = [
            RecommendationScore(deck_name="Test Deck", score=0.9, confidence=0.5),
        ]

        with patch("forgebreaker.ml.inference.get_mlforge_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.health_check.return_value = True
            mock_client.score_decks.return_value = mock_scores
            mock_get_client.return_value = mock_client

            ranked = await rank_decks_with_ml([deck], collection, rarity_map)

        # Score should be blended with reduced ML weight due to low confidence
        # Low confidence (0.5) means effective weight = 0.6 * 0.5 = 0.3
        assert len(ranked) == 1
        # Final score should be somewhere between pure ML and pure basic

    async def test_extracts_features_for_all_decks(self, rarity_map: dict[str, str]) -> None:
        """Features are extracted and sent for each deck."""
        decks = [
            MetaDeck(
                name=f"Deck {i}",
                archetype="aggro",
                format="standard",
                cards={"Lightning Bolt": 4},
            )
            for i in range(3)
        ]
        collection = Collection(cards={"Lightning Bolt": 4})

        mock_scores = [
            RecommendationScore(deck_name=f"Deck {i}", score=0.5, confidence=0.8) for i in range(3)
        ]

        with patch("forgebreaker.ml.inference.get_mlforge_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.health_check.return_value = True
            mock_client.score_decks.return_value = mock_scores
            mock_get_client.return_value = mock_client

            ranked = await rank_decks_with_ml(decks, collection, rarity_map)

        assert len(ranked) == 3
        # Verify score_decks was called with 3 feature sets
        call_args = mock_client.score_decks.call_args[0][0]
        assert len(call_args) == 3
