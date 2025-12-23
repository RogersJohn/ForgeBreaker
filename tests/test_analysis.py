import pytest

from forgebreaker.analysis.distance import calculate_deck_distance
from forgebreaker.analysis.ranker import get_budget_decks, get_buildable_decks, rank_decks
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
