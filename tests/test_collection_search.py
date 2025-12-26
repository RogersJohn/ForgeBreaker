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
            "color_identity": ["B"],
            "set": "M21",
            "rarity": "uncommon",
            "mana_cost": "{1}{B}",
        },
        "Sanctum of Shattered Heights": {
            "type_line": "Legendary Enchantment — Shrine",
            "colors": ["R"],
            "color_identity": ["R"],
            "set": "M21",
            "rarity": "uncommon",
            "mana_cost": "{2}{R}",
        },
        "Lightning Bolt": {
            "type_line": "Instant",
            "colors": ["R"],
            "color_identity": ["R"],
            "set": "LEB",
            "rarity": "common",
            "mana_cost": "{R}",
        },
        "Sheoldred, the Apocalypse": {
            "type_line": "Legendary Creature — Phyrexian Praetor",
            "colors": ["B"],
            "color_identity": ["B"],
            "set": "DMU",
            "rarity": "mythic",
            "mana_cost": "{2}{B}{B}",
        },
        "Forest": {
            "type_line": "Basic Land — Forest",
            "colors": [],
            "color_identity": [],
            "set": "FDN",
            "rarity": "common",
            "mana_cost": "",
        },
    }


@pytest.fixture
def dragon_card_db() -> dict[str, dict]:
    """Card database with black dragons matching user's Arena collection."""
    return {
        "Scavenger Regent": {
            "type_line": "Creature — Dragon",
            "colors": ["B"],
            "color_identity": ["B"],
            "set": "FDN",
            "rarity": "rare",
            "mana_cost": "{3}{B}{B}",
        },
        "Purging Stormbrood": {
            "type_line": "Creature — Dragon",
            "colors": ["B"],
            "color_identity": ["B"],
            "set": "OTJ",
            "rarity": "rare",
            "mana_cost": "{4}{B}{B}",
        },
        "Feral Deathgorger": {
            "type_line": "Creature — Dragon",
            "colors": ["B"],
            "color_identity": ["B"],
            "set": "FDN",
            "rarity": "uncommon",
            "mana_cost": "{2}{B}",
        },
        "Decadent Dragon": {
            "type_line": "Creature — Dragon",
            "colors": ["R"],
            "color_identity": ["R"],
            "set": "WOE",
            "rarity": "rare",
            "mana_cost": "{2}{R}{R}",
        },
        "Akul the Unrepentant": {
            "type_line": "Legendary Creature — Dragon Rogue",
            "colors": ["B", "R"],
            "color_identity": ["B", "R"],
            "set": "OTJ",
            "rarity": "mythic",
            "mana_cost": "{2}{B}{R}",
        },
        "Immerstum Predator": {
            "type_line": "Creature — Vampire Dragon",
            "colors": ["B", "R"],
            "color_identity": ["B", "R"],
            "set": "KHM",
            "rarity": "rare",
            "mana_cost": "{2}{B}{R}",
        },
        "Betor, Kin to All": {
            "type_line": "Legendary Creature — Elder Dragon",
            "colors": ["B", "G", "R", "U", "W"],
            "color_identity": ["B", "G", "R", "U", "W"],
            "set": "FDN",
            "rarity": "mythic",
            "mana_cost": "{W}{U}{B}{R}{G}",
        },
        "Sonic Shrieker": {
            "type_line": "Creature — Dragon Bat",
            "colors": ["B"],
            "color_identity": ["B"],
            "set": "FDN",
            "rarity": "common",
            "mana_cost": "{3}{B}",
        },
        "Armament Dragon": {
            "type_line": "Creature — Dragon",
            "colors": ["B"],
            "color_identity": ["B"],
            "set": "FDN",
            "rarity": "uncommon",
            "mana_cost": "{4}{B}",
        },
        "Keru Goldkeeper": {
            "type_line": "Creature — Dragon",
            "colors": ["B"],
            "color_identity": ["B"],
            "set": "FDN",
            "rarity": "common",
            "mana_cost": "{2}{B}",
        },
        "Teval, Arbiter of Virtue": {
            "type_line": "Legendary Creature — Dragon",
            "colors": ["W"],
            "color_identity": ["W"],
            "set": "FDN",
            "rarity": "rare",
            "mana_cost": "{3}{W}{W}",
        },
        # Red dragon (not black) to ensure we filter correctly
        "Shivan Dragon": {
            "type_line": "Creature — Dragon",
            "colors": ["R"],
            "color_identity": ["R"],
            "set": "FDN",
            "rarity": "rare",
            "mana_cost": "{4}{R}{R}",
        },
    }


@pytest.fixture
def dragon_collection() -> Collection:
    """User's dragon collection from Arena."""
    return Collection(
        cards={
            "Scavenger Regent": 4,
            "Purging Stormbrood": 2,
            "Feral Deathgorger": 4,
            "Decadent Dragon": 1,
            "Akul the Unrepentant": 1,
            "Immerstum Predator": 1,
            "Betor, Kin to All": 1,
            "Sonic Shrieker": 2,
            "Armament Dragon": 4,
            "Keru Goldkeeper": 3,
            "Teval, Arbiter of Virtue": 1,
            "Shivan Dragon": 2,
        }
    )


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


class TestBlackDragonsSearch:
    """
    Critical tests for the black dragons use case.

    User reported: "If I filter by Dragon and color black in Arena, I see many cards.
    But when I ask the deck advisor how many black dragons I have, it returns 0 or 1."

    These tests verify the fix for color_identity filtering.
    """

    def test_search_black_dragons_finds_all(
        self, dragon_collection: Collection, dragon_card_db: dict[str, dict]
    ) -> None:
        """Search for black dragons should find all dragons with black in color identity."""
        results = search_collection(
            dragon_collection, dragon_card_db, card_type="Dragon", colors=["B"]
        )

        # Should find all dragons that have B in their color_identity
        # Mono-black: Scavenger Regent, Purging Stormbrood, Feral Deathgorger,
        #             Sonic Shrieker, Armament Dragon, Keru Goldkeeper
        # Multi-color with B: Akul (BR), Immerstum Predator (BR), Betor (WUBRG)
        # NOT: Decadent Dragon (R only), Teval (W only), Shivan Dragon (R only)
        expected_black_dragons = {
            "Scavenger Regent",
            "Purging Stormbrood",
            "Feral Deathgorger",
            "Sonic Shrieker",
            "Armament Dragon",
            "Keru Goldkeeper",
            "Akul the Unrepentant",
            "Immerstum Predator",
            "Betor, Kin to All",
        }

        result_names = {r.name for r in results}
        assert result_names == expected_black_dragons, (
            f"Expected {len(expected_black_dragons)} black dragons, got {len(results)}. "
            f"Missing: {expected_black_dragons - result_names}, "
            f"Extra: {result_names - expected_black_dragons}"
        )

    def test_search_black_dragons_count(
        self, dragon_collection: Collection, dragon_card_db: dict[str, dict]
    ) -> None:
        """Should find exactly 9 black dragons (the specific count matters for user trust)."""
        results = search_collection(
            dragon_collection, dragon_card_db, card_type="Dragon", colors=["B"]
        )

        assert len(results) == 9, f"Expected 9 black dragons, got {len(results)}"

    def test_search_excludes_non_black_dragons(
        self, dragon_collection: Collection, dragon_card_db: dict[str, dict]
    ) -> None:
        """Dragons without black in color identity should be excluded."""
        results = search_collection(
            dragon_collection, dragon_card_db, card_type="Dragon", colors=["B"]
        )

        result_names = {r.name for r in results}
        # These should NOT be in results (no B in color_identity)
        assert "Decadent Dragon" not in result_names  # Red only
        assert "Teval, Arbiter of Virtue" not in result_names  # White only
        assert "Shivan Dragon" not in result_names  # Red only

    def test_search_all_dragons_no_color_filter(
        self, dragon_collection: Collection, dragon_card_db: dict[str, dict]
    ) -> None:
        """Search for all dragons without color filter."""
        results = search_collection(dragon_collection, dragon_card_db, card_type="Dragon")

        # Should find all 12 dragons in collection
        assert len(results) == 12

    def test_multicolor_dragon_matches_black(
        self, dragon_collection: Collection, dragon_card_db: dict[str, dict]
    ) -> None:
        """Multicolor dragons with B should match black filter."""
        results = search_collection(
            dragon_collection, dragon_card_db, card_type="Dragon", colors=["B"]
        )

        result_names = {r.name for r in results}
        # BR dragons should be included
        assert "Akul the Unrepentant" in result_names
        assert "Immerstum Predator" in result_names
        # 5-color dragon should be included
        assert "Betor, Kin to All" in result_names

    def test_dragon_bat_matches_dragon_type(
        self, dragon_collection: Collection, dragon_card_db: dict[str, dict]
    ) -> None:
        """Cards with Dragon as part of creature type should match."""
        results = search_collection(
            dragon_collection, dragon_card_db, card_type="Dragon", colors=["B"]
        )

        result_names = {r.name for r in results}
        # "Creature — Dragon Bat" should match "Dragon" type filter
        assert "Sonic Shrieker" in result_names


class TestColorIdentityVsColors:
    """
    Tests verifying we use color_identity, not colors field.

    The Scryfall 'colors' field only includes mana cost colors.
    The 'color_identity' field includes all colors (cost + abilities + color indicators).
    """

    def test_uses_color_identity_not_colors(self) -> None:
        """Cards where color_identity differs from colors should match correctly."""
        # Card with ability that adds to color identity but not mana cost
        card_db = {
            "Hybrid Card": {
                "type_line": "Creature — Human",
                "colors": ["W"],  # Only white in mana cost
                "color_identity": ["B", "W"],  # Has black ability
                "set": "TST",
                "rarity": "rare",
                "mana_cost": "{1}{W}",
            }
        }
        collection = Collection(cards={"Hybrid Card": 2})

        # Should find when searching for black (even though colors is only W)
        results = search_collection(collection, card_db, colors=["B"])
        assert len(results) == 1
        assert results[0].name == "Hybrid Card"

    def test_color_identity_multicolor(self) -> None:
        """Multicolor cards should match any of their colors."""
        card_db = {
            "Rakdos Card": {
                "type_line": "Creature — Demon",
                "colors": ["B", "R"],
                "color_identity": ["B", "R"],
                "set": "TST",
                "rarity": "rare",
                "mana_cost": "{B}{R}",
            }
        }
        collection = Collection(cards={"Rakdos Card": 1})

        # Should match black search
        results_b = search_collection(collection, card_db, colors=["B"])
        assert len(results_b) == 1

        # Should match red search
        results_r = search_collection(collection, card_db, colors=["R"])
        assert len(results_r) == 1

        # Should match green search (should NOT match)
        results_g = search_collection(collection, card_db, colors=["G"])
        assert len(results_g) == 0

    def test_fallback_to_colors_if_no_color_identity(self) -> None:
        """If color_identity is missing, fall back to colors field."""
        card_db = {
            "Old Format Card": {
                "type_line": "Creature — Elf",
                "colors": ["G"],
                # No color_identity field (old data format)
                "set": "OLD",
                "rarity": "common",
                "mana_cost": "{G}",
            }
        }
        collection = Collection(cards={"Old Format Card": 3})

        results = search_collection(collection, card_db, colors=["G"])
        assert len(results) == 1


class TestEmptyCardDatabase:
    """Tests for empty card database handling."""

    def test_empty_db_returns_empty_results(self, sample_collection: Collection) -> None:
        """Empty card database should return empty results, not error."""
        results = search_collection(sample_collection, {})
        assert results == []

    def test_empty_db_logs_warning(
        self, sample_collection: Collection, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Empty card database should log a warning."""
        import logging

        with caplog.at_level(logging.WARNING):
            search_collection(sample_collection, {})

        assert "Card database is empty" in caplog.text


class TestCardsNotInDatabase:
    """Tests for handling cards not found in the database."""

    def test_missing_cards_logged(
        self, sample_card_db: dict[str, dict], caplog: pytest.LogCaptureFixture
    ) -> None:
        """Cards in collection but not in DB should be logged."""
        import logging

        collection = Collection(
            cards={
                "Lightning Bolt": 4,  # In DB
                "Mystery Card Alpha": 2,  # Not in DB
                "Mystery Card Beta": 1,  # Not in DB
            }
        )

        with caplog.at_level(logging.WARNING):
            results = search_collection(collection, sample_card_db)

        # Should still find cards that are in DB
        assert len(results) == 1
        assert results[0].name == "Lightning Bolt"

        # Should log warning about missing cards
        assert "cards in collection but not in card database" in caplog.text

    def test_all_cards_missing_returns_empty(self, caplog: pytest.LogCaptureFixture) -> None:
        """If all collection cards are missing from DB, return empty and log."""
        import logging

        card_db = {"Some Other Card": {"type_line": "Instant", "colors": ["R"]}}
        collection = Collection(cards={"Unknown Card 1": 4, "Unknown Card 2": 2})

        with caplog.at_level(logging.WARNING):
            results = search_collection(collection, card_db)

        assert results == []
        assert "cards in collection but not in card database" in caplog.text
