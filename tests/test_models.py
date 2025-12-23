import pytest

from forgebreaker.models.card import Card
from forgebreaker.models.collection import Collection
from forgebreaker.models.deck import DeckDistance, MetaDeck, WildcardCost


class TestCard:
    def test_card_creation(self) -> None:
        card = Card(name="Lightning Bolt", quantity=4, set_code="LEB")
        assert card.name == "Lightning Bolt"
        assert card.quantity == 4
        assert card.set_code == "LEB"

    def test_card_immutable(self) -> None:
        card = Card(name="Lightning Bolt", quantity=4)
        with pytest.raises(AttributeError):
            card.quantity = 3  # type: ignore[misc]

    def test_card_optional_fields(self) -> None:
        card = Card(name="Mountain", quantity=20)
        assert card.set_code is None
        assert card.collector_number is None
        assert card.arena_id is None


class TestCollection:
    def test_empty_collection(self) -> None:
        collection = Collection()
        assert collection.total_cards() == 0
        assert collection.unique_cards() == 0

    def test_add_card(self) -> None:
        collection = Collection()
        collection.add_card("Lightning Bolt", 4)
        assert collection.get_quantity("Lightning Bolt") == 4

    def test_add_card_stacks(self) -> None:
        collection = Collection()
        collection.add_card("Lightning Bolt", 2)
        collection.add_card("Lightning Bolt", 2)
        assert collection.get_quantity("Lightning Bolt") == 4

    def test_owns_card(self) -> None:
        collection = Collection(cards={"Lightning Bolt": 4})
        assert collection.owns("Lightning Bolt", 4) is True
        assert collection.owns("Lightning Bolt", 5) is False
        assert collection.owns("Counterspell", 1) is False

    def test_get_quantity_missing_card(self) -> None:
        collection = Collection()
        assert collection.get_quantity("Nonexistent Card") == 0


class TestMetaDeck:
    def test_maindeck_count(self) -> None:
        deck = MetaDeck(
            name="Test Deck",
            archetype="aggro",
            format="standard",
            cards={"Lightning Bolt": 4, "Mountain": 20},
        )
        assert deck.maindeck_count() == 24

    def test_all_cards_includes_sideboard(self) -> None:
        deck = MetaDeck(
            name="Test Deck",
            archetype="aggro",
            format="standard",
            cards={"Lightning Bolt": 4},
            sideboard={"Abrade": 2},
        )
        assert deck.all_cards() == {"Lightning Bolt", "Abrade"}


class TestWildcardCost:
    def test_total(self) -> None:
        cost = WildcardCost(common=4, uncommon=8, rare=12, mythic=2)
        assert cost.total() == 26

    def test_weighted_cost(self) -> None:
        # 4 mythics = 16.0 weighted
        # 4 rares = 4.0 weighted
        # Total = 20.0
        cost = WildcardCost(rare=4, mythic=4)
        assert cost.weighted_cost() == 20.0

    def test_weighted_cost_empty(self) -> None:
        cost = WildcardCost()
        assert cost.weighted_cost() == 0.0


class TestDeckDistance:
    def test_is_complete(self) -> None:
        deck = MetaDeck(name="Test", archetype="aggro", format="standard")

        complete = DeckDistance(
            deck=deck,
            owned_cards=60,
            missing_cards=0,
            completion_percentage=1.0,
            wildcard_cost=WildcardCost(),
            missing_card_list=[],
        )
        assert complete.is_complete is True

        incomplete = DeckDistance(
            deck=deck,
            owned_cards=56,
            missing_cards=4,
            completion_percentage=0.93,
            wildcard_cost=WildcardCost(rare=4),
            missing_card_list=[("Sheoldred", 4, "mythic")],
        )
        assert incomplete.is_complete is False
