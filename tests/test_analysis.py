import pytest

from forgebreaker.analysis.distance import calculate_deck_distance
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
