import pytest

from forgebreaker.models.collection import Collection
from forgebreaker.services.collection_search import (
    CardSearchResult,
    format_search_results,
    search_collection,
)


@pytest.fixture
def sample_card_db() -> dict[str, dict]:
    return {
        "Sanctum of Stone Fangs": {
            "type_line": "Legendary Enchantment — Shrine",
            "colors": ["B"],
            "set": "M21",
            "rarity": "uncommon",
            "mana_cost": "{1}{B}",
        },
        "Sanctum of Shattered Heights": {
            "type_line": "Legendary Enchantment — Shrine",
            "colors": ["R"],
            "set": "M21",
            "rarity": "uncommon",
            "mana_cost": "{2}{R}",
        },
        "Lightning Bolt": {
            "type_line": "Instant",
            "colors": ["R"],
            "set": "LEB",
            "rarity": "common",
            "mana_cost": "{R}",
        },
        "Sheoldred, the Apocalypse": {
            "type_line": "Legendary Creature — Phyrexian Praetor",
            "colors": ["B"],
            "set": "DMU",
            "rarity": "mythic",
            "mana_cost": "{2}{B}{B}",
        },
        "Forest": {
            "type_line": "Basic Land — Forest",
            "colors": [],
            "set": "FDN",
            "rarity": "common",
            "mana_cost": "",
        },
    }


@pytest.fixture
def sample_collection() -> Collection:
    return Collection(
        cards={
            "Sanctum of Stone Fangs": 4,
            "Sanctum of Shattered Heights": 3,
            "Lightning Bolt": 4,
            "Sheoldred, the Apocalypse": 2,
            "Forest": 20,
        }
    )


class TestSearchCollection:
    def test_search_by_name(
        self, sample_collection: Collection, sample_card_db: dict[str, dict]
    ) -> None:
        results = search_collection(sample_collection, sample_card_db, name_contains="sanctum")

        assert len(results) == 2
        names = [r.name for r in results]
        assert "Sanctum of Stone Fangs" in names
        assert "Sanctum of Shattered Heights" in names

    def test_search_by_type(
        self, sample_collection: Collection, sample_card_db: dict[str, dict]
    ) -> None:
        results = search_collection(sample_collection, sample_card_db, card_type="Shrine")

        assert len(results) == 2
        for r in results:
            assert "Shrine" in r.type_line

    def test_search_by_color(
        self, sample_collection: Collection, sample_card_db: dict[str, dict]
    ) -> None:
        results = search_collection(sample_collection, sample_card_db, colors=["R"])

        assert len(results) == 2
        names = [r.name for r in results]
        assert "Lightning Bolt" in names
        assert "Sanctum of Shattered Heights" in names

    def test_search_by_set(
        self, sample_collection: Collection, sample_card_db: dict[str, dict]
    ) -> None:
        results = search_collection(sample_collection, sample_card_db, set_code="M21")

        assert len(results) == 2
        for r in results:
            assert r.set_code == "M21"

    def test_search_by_rarity(
        self, sample_collection: Collection, sample_card_db: dict[str, dict]
    ) -> None:
        results = search_collection(sample_collection, sample_card_db, rarity="mythic")

        assert len(results) == 1
        assert results[0].name == "Sheoldred, the Apocalypse"

    def test_search_combined_filters(
        self, sample_collection: Collection, sample_card_db: dict[str, dict]
    ) -> None:
        """Multiple filters should AND together."""
        results = search_collection(
            sample_collection, sample_card_db, card_type="Enchantment", colors=["B"]
        )

        assert len(results) == 1
        assert results[0].name == "Sanctum of Stone Fangs"

    def test_search_no_results(
        self, sample_collection: Collection, sample_card_db: dict[str, dict]
    ) -> None:
        results = search_collection(sample_collection, sample_card_db, name_contains="nonexistent")

        assert results == []

    def test_search_min_quantity(
        self, sample_collection: Collection, sample_card_db: dict[str, dict]
    ) -> None:
        results = search_collection(sample_collection, sample_card_db, min_quantity=4)

        # Only cards with 4+ copies
        names = [r.name for r in results]
        assert "Lightning Bolt" in names
        assert "Sanctum of Stone Fangs" in names
        assert "Forest" in names  # 20 copies
        assert "Sheoldred, the Apocalypse" not in names  # only 2

    def test_search_max_results(
        self, sample_collection: Collection, sample_card_db: dict[str, dict]
    ) -> None:
        results = search_collection(sample_collection, sample_card_db, max_results=2)

        assert len(results) == 2

    def test_search_results_sorted_by_quantity(
        self, sample_collection: Collection, sample_card_db: dict[str, dict]
    ) -> None:
        results = search_collection(sample_collection, sample_card_db)

        # Should be sorted by quantity descending
        quantities = [r.quantity for r in results]
        assert quantities == sorted(quantities, reverse=True)

    def test_card_not_in_database_skipped(
        self, sample_collection: Collection, sample_card_db: dict[str, dict]
    ) -> None:
        # Add card that's not in the database
        sample_collection.cards["Unknown Card XYZ"] = 4
        results = search_collection(sample_collection, sample_card_db)

        names = [r.name for r in results]
        assert "Unknown Card XYZ" not in names


class TestFormatSearchResults:
    def test_format_empty(self) -> None:
        result = format_search_results([])
        assert "No cards found" in result

    def test_format_results(self) -> None:
        results = [
            CardSearchResult(
                name="Lightning Bolt",
                quantity=4,
                set_code="LEB",
                rarity="common",
                colors=["R"],
                type_line="Instant",
                mana_cost="{R}",
            )
        ]

        formatted = format_search_results(results)
        assert "Found 1 card" in formatted
        assert "4x Lightning Bolt" in formatted
        assert "(R)" in formatted  # Color

    def test_format_colorless_card(self) -> None:
        results = [
            CardSearchResult(
                name="Sol Ring",
                quantity=1,
                set_code="CMD",
                rarity="uncommon",
                colors=[],
                type_line="Artifact",
                mana_cost="{1}",
            )
        ]

        formatted = format_search_results(results)
        assert "(C)" in formatted  # Colorless indicator
