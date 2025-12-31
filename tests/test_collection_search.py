import pytest

from forgebreaker.models.collection import Collection
from forgebreaker.models.failure import FailureKind, KnownError
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

    def test_card_not_in_database_raises_error(
        self, sample_collection: Collection, sample_card_db: dict[str, dict]
    ) -> None:
        """Card in collection but not in DB raises terminal KnownError."""
        # Add card that's not in the database
        sample_collection.cards["Unknown Card XYZ"] = 4

        with pytest.raises(KnownError) as exc_info:
            search_collection(sample_collection, sample_card_db)

        assert exc_info.value.kind == FailureKind.VALIDATION_FAILED
        assert "Unknown Card XYZ" in str(exc_info.value.detail)


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
                cmc=1,
                oracle_text="Lightning Bolt deals 3 damage to any target.",
                keywords=[],
                power=None,
                toughness=None,
            )
        ]

        formatted = format_search_results(results)
        assert "Found 4 cards (1 unique)" in formatted
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
                cmc=1,
                oracle_text="{T}: Add {C}{C}.",
                keywords=[],
                power=None,
                toughness=None,
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


class TestCMCFiltering:
    """Tests for mana value (CMC) filtering."""

    @pytest.fixture
    def cmc_card_db(self) -> dict[str, dict]:
        return {
            "Lightning Bolt": {
                "type_line": "Instant",
                "colors": ["R"],
                "color_identity": ["R"],
                "cmc": 1,
                "set": "LEB",
                "rarity": "common",
            },
            "Counterspell": {
                "type_line": "Instant",
                "colors": ["U"],
                "color_identity": ["U"],
                "cmc": 2,
                "set": "LEB",
                "rarity": "uncommon",
            },
            "Murder": {
                "type_line": "Instant",
                "colors": ["B"],
                "color_identity": ["B"],
                "cmc": 3,
                "set": "M21",
                "rarity": "common",
            },
            "Wrath of God": {
                "type_line": "Sorcery",
                "colors": ["W"],
                "color_identity": ["W"],
                "cmc": 4,
                "set": "M21",
                "rarity": "rare",
            },
            "Niv-Mizzet, Parun": {
                "type_line": "Legendary Creature — Dragon Wizard",
                "colors": ["U", "R"],
                "color_identity": ["U", "R"],
                "cmc": 6,
                "set": "GRN",
                "rarity": "rare",
            },
        }

    @pytest.fixture
    def cmc_collection(self) -> Collection:
        return Collection(
            cards={
                "Lightning Bolt": 4,
                "Counterspell": 4,
                "Murder": 2,
                "Wrath of God": 2,
                "Niv-Mizzet, Parun": 1,
            }
        )

    def test_exact_cmc(self, cmc_collection: Collection, cmc_card_db: dict) -> None:
        """Filter by exact mana value."""
        results = search_collection(cmc_collection, cmc_card_db, cmc=1)
        assert len(results) == 1
        assert results[0].name == "Lightning Bolt"

    def test_cmc_min(self, cmc_collection: Collection, cmc_card_db: dict) -> None:
        """Filter by minimum mana value."""
        results = search_collection(cmc_collection, cmc_card_db, cmc_min=4)
        names = {r.name for r in results}
        assert names == {"Wrath of God", "Niv-Mizzet, Parun"}

    def test_cmc_max(self, cmc_collection: Collection, cmc_card_db: dict) -> None:
        """Filter by maximum mana value."""
        results = search_collection(cmc_collection, cmc_card_db, cmc_max=2)
        names = {r.name for r in results}
        assert names == {"Lightning Bolt", "Counterspell"}

    def test_cmc_range(self, cmc_collection: Collection, cmc_card_db: dict) -> None:
        """Filter by mana value range."""
        results = search_collection(cmc_collection, cmc_card_db, cmc_min=2, cmc_max=4)
        names = {r.name for r in results}
        assert names == {"Counterspell", "Murder", "Wrath of God"}


class TestKeywordFiltering:
    """Tests for keyword ability filtering."""

    @pytest.fixture
    def keyword_card_db(self) -> dict[str, dict]:
        return {
            "Serra Angel": {
                "type_line": "Creature — Angel",
                "colors": ["W"],
                "color_identity": ["W"],
                "cmc": 5,
                "keywords": ["Flying", "Vigilance"],
                "power": "4",
                "toughness": "4",
                "set": "DMR",
                "rarity": "uncommon",
            },
            "Vampire Nighthawk": {
                "type_line": "Creature — Vampire Shaman",
                "colors": ["B"],
                "color_identity": ["B"],
                "cmc": 3,
                "keywords": ["Flying", "Deathtouch", "Lifelink"],
                "power": "2",
                "toughness": "3",
                "set": "M21",
                "rarity": "uncommon",
            },
            "Questing Beast": {
                "type_line": "Legendary Creature — Beast",
                "colors": ["G"],
                "color_identity": ["G"],
                "cmc": 4,
                "keywords": ["Vigilance", "Deathtouch", "Haste"],
                "power": "4",
                "toughness": "4",
                "set": "ELD",
                "rarity": "mythic",
            },
            "Grizzly Bears": {
                "type_line": "Creature — Bear",
                "colors": ["G"],
                "color_identity": ["G"],
                "cmc": 2,
                "keywords": [],
                "power": "2",
                "toughness": "2",
                "set": "M10",
                "rarity": "common",
            },
        }

    @pytest.fixture
    def keyword_collection(self) -> Collection:
        return Collection(
            cards={
                "Serra Angel": 2,
                "Vampire Nighthawk": 4,
                "Questing Beast": 1,
                "Grizzly Bears": 4,
            }
        )

    def test_single_keyword(self, keyword_collection: Collection, keyword_card_db: dict) -> None:
        """Filter by single keyword."""
        results = search_collection(keyword_collection, keyword_card_db, keywords=["Flying"])
        names = {r.name for r in results}
        assert names == {"Serra Angel", "Vampire Nighthawk"}

    def test_multiple_keywords_and(
        self, keyword_collection: Collection, keyword_card_db: dict
    ) -> None:
        """Filter by multiple keywords - card must have ALL."""
        results = search_collection(
            keyword_collection, keyword_card_db, keywords=["Flying", "Lifelink"]
        )
        assert len(results) == 1
        assert results[0].name == "Vampire Nighthawk"

    def test_keyword_case_insensitive(
        self, keyword_collection: Collection, keyword_card_db: dict
    ) -> None:
        """Keyword matching should be case-insensitive."""
        results = search_collection(keyword_collection, keyword_card_db, keywords=["flying"])
        assert len(results) == 2

    def test_no_matching_keyword(
        self, keyword_collection: Collection, keyword_card_db: dict
    ) -> None:
        """No cards with nonexistent keyword."""
        results = search_collection(keyword_collection, keyword_card_db, keywords=["Trample"])
        assert len(results) == 0


class TestOracleTextSearch:
    """Tests for oracle/rules text searching."""

    @pytest.fixture
    def oracle_card_db(self) -> dict[str, dict]:
        return {
            "Lightning Bolt": {
                "type_line": "Instant",
                "colors": ["R"],
                "color_identity": ["R"],
                "cmc": 1,
                "oracle_text": "Lightning Bolt deals 3 damage to any target.",
                "set": "LEB",
                "rarity": "common",
            },
            "Divination": {
                "type_line": "Sorcery",
                "colors": ["U"],
                "color_identity": ["U"],
                "cmc": 3,
                "oracle_text": "Draw two cards.",
                "set": "M21",
                "rarity": "common",
            },
            "Murder": {
                "type_line": "Instant",
                "colors": ["B"],
                "color_identity": ["B"],
                "cmc": 3,
                "oracle_text": "Destroy target creature.",
                "set": "M21",
                "rarity": "common",
            },
            "Hero's Downfall": {
                "type_line": "Instant",
                "colors": ["B"],
                "color_identity": ["B"],
                "cmc": 3,
                "oracle_text": "Destroy target creature or planeswalker.",
                "set": "THS",
                "rarity": "rare",
            },
        }

    @pytest.fixture
    def oracle_collection(self) -> Collection:
        return Collection(
            cards={
                "Lightning Bolt": 4,
                "Divination": 2,
                "Murder": 4,
                "Hero's Downfall": 2,
            }
        )

    def test_oracle_text_simple(self, oracle_collection: Collection, oracle_card_db: dict) -> None:
        """Search for cards with specific text."""
        results = search_collection(oracle_collection, oracle_card_db, oracle_text="draw")
        assert len(results) == 1
        assert results[0].name == "Divination"

    def test_oracle_text_destroy(self, oracle_collection: Collection, oracle_card_db: dict) -> None:
        """Search for cards that destroy things."""
        results = search_collection(oracle_collection, oracle_card_db, oracle_text="destroy target")
        names = {r.name for r in results}
        assert names == {"Murder", "Hero's Downfall"}

    def test_oracle_text_case_insensitive(
        self, oracle_collection: Collection, oracle_card_db: dict
    ) -> None:
        """Oracle text search should be case-insensitive."""
        results = search_collection(oracle_collection, oracle_card_db, oracle_text="DAMAGE")
        assert len(results) == 1
        assert results[0].name == "Lightning Bolt"


class TestMonoColorFiltering:
    """Tests for exact/mono-color filtering."""

    @pytest.fixture
    def color_card_db(self) -> dict[str, dict]:
        return {
            "Lightning Bolt": {
                "type_line": "Instant",
                "colors": ["R"],
                "color_identity": ["R"],
                "set": "LEB",
                "rarity": "common",
            },
            "Goblin Guide": {
                "type_line": "Creature — Goblin Scout",
                "colors": ["R"],
                "color_identity": ["R"],
                "set": "ZEN",
                "rarity": "rare",
            },
            "Rakdos Cackler": {
                "type_line": "Creature — Devil",
                "colors": ["R"],
                "color_identity": ["B", "R"],
                "set": "RTR",
                "rarity": "uncommon",
            },
            "Graven Cairns": {
                "type_line": "Land",
                "colors": [],
                "color_identity": ["B", "R"],
                "set": "SHM",
                "rarity": "rare",
            },
        }

    @pytest.fixture
    def color_collection(self) -> Collection:
        return Collection(
            cards={
                "Lightning Bolt": 4,
                "Goblin Guide": 4,
                "Rakdos Cackler": 4,
                "Graven Cairns": 2,
            }
        )

    def test_mono_red_exact(self, color_collection: Collection, color_card_db: dict) -> None:
        """Filter for mono-red cards only (exactly R, nothing else)."""
        results = search_collection(color_collection, color_card_db, colors=["R"], color_exact=True)
        names = {r.name for r in results}
        # Excludes Rakdos Cackler (BR) and Graven Cairns (BR)
        assert names == {"Lightning Bolt", "Goblin Guide"}

    def test_includes_red_default(self, color_collection: Collection, color_card_db: dict) -> None:
        """Default color filter includes multi-color cards."""
        results = search_collection(
            color_collection, color_card_db, colors=["R"], color_exact=False
        )
        names = {r.name for r in results}
        # Includes Rakdos Cackler and Graven Cairns (they have R in identity)
        assert names == {"Lightning Bolt", "Goblin Guide", "Rakdos Cackler", "Graven Cairns"}


class TestFormatLegalityFiltering:
    """Tests for format legality filtering."""

    @pytest.fixture
    def format_card_db(self) -> dict[str, dict]:
        return {
            "Lightning Bolt": {
                "type_line": "Instant",
                "colors": ["R"],
                "color_identity": ["R"],
                "cmc": 1,
                "legalities": {
                    "standard": "not_legal",
                    "historic": "legal",
                    "modern": "legal",
                    "legacy": "legal",
                },
                "set": "LEB",
                "rarity": "common",
            },
            "Play with Fire": {
                "type_line": "Instant",
                "colors": ["R"],
                "color_identity": ["R"],
                "cmc": 1,
                "legalities": {
                    "standard": "legal",
                    "historic": "legal",
                    "modern": "legal",
                    "legacy": "legal",
                },
                "set": "MID",
                "rarity": "uncommon",
            },
            "Ancestral Recall": {
                "type_line": "Instant",
                "colors": ["U"],
                "color_identity": ["U"],
                "cmc": 1,
                "legalities": {
                    "standard": "not_legal",
                    "historic": "not_legal",
                    "modern": "not_legal",
                    "legacy": "banned",
                    "vintage": "restricted",
                },
                "set": "LEB",
                "rarity": "rare",
            },
        }

    @pytest.fixture
    def format_collection(self) -> Collection:
        return Collection(
            cards={
                "Lightning Bolt": 4,
                "Play with Fire": 4,
                "Ancestral Recall": 1,
            }
        )

    def test_standard_legal(self, format_collection: Collection, format_card_db: dict) -> None:
        """Filter for Standard-legal cards."""
        results = search_collection(format_collection, format_card_db, format_legal="standard")
        assert len(results) == 1
        assert results[0].name == "Play with Fire"

    def test_modern_legal(self, format_collection: Collection, format_card_db: dict) -> None:
        """Filter for Modern-legal cards."""
        results = search_collection(format_collection, format_card_db, format_legal="modern")
        names = {r.name for r in results}
        assert names == {"Lightning Bolt", "Play with Fire"}


class TestPowerToughnessFiltering:
    """Tests for creature power/toughness filtering."""

    @pytest.fixture
    def pt_card_db(self) -> dict[str, dict]:
        return {
            "Llanowar Elves": {
                "type_line": "Creature — Elf Druid",
                "colors": ["G"],
                "color_identity": ["G"],
                "cmc": 1,
                "power": "1",
                "toughness": "1",
                "set": "M21",
                "rarity": "common",
            },
            "Grizzly Bears": {
                "type_line": "Creature — Bear",
                "colors": ["G"],
                "color_identity": ["G"],
                "cmc": 2,
                "power": "2",
                "toughness": "2",
                "set": "M10",
                "rarity": "common",
            },
            "Gigantosaurus": {
                "type_line": "Creature — Dinosaur",
                "colors": ["G"],
                "color_identity": ["G"],
                "cmc": 5,
                "power": "10",
                "toughness": "10",
                "set": "M19",
                "rarity": "rare",
            },
            "Tarmogoyf": {
                "type_line": "Creature — Lhurgoyf",
                "colors": ["G"],
                "color_identity": ["G"],
                "cmc": 2,
                "power": "*",
                "toughness": "1+*",
                "set": "FUT",
                "rarity": "rare",
            },
        }

    @pytest.fixture
    def pt_collection(self) -> Collection:
        return Collection(
            cards={
                "Llanowar Elves": 4,
                "Grizzly Bears": 4,
                "Gigantosaurus": 1,
                "Tarmogoyf": 4,
            }
        )

    def test_power_min(self, pt_collection: Collection, pt_card_db: dict) -> None:
        """Filter by minimum power."""
        results = search_collection(pt_collection, pt_card_db, power_min=5)
        assert len(results) == 1
        assert results[0].name == "Gigantosaurus"

    def test_power_max(self, pt_collection: Collection, pt_card_db: dict) -> None:
        """Filter by maximum power."""
        results = search_collection(pt_collection, pt_card_db, power_max=1)
        assert len(results) == 1
        assert results[0].name == "Llanowar Elves"

    def test_variable_power_excluded(self, pt_collection: Collection, pt_card_db: dict) -> None:
        """Cards with variable power (*) are excluded from power filters."""
        results = search_collection(pt_collection, pt_card_db, power_min=0)
        names = {r.name for r in results}
        # Tarmogoyf excluded (power is "*")
        assert "Tarmogoyf" not in names


class TestCardsNotInDatabase:
    """Tests for handling cards not found in the database.

    INVARIANT: Cards in collection but not in DB is a TERMINAL FAILURE.
    This is a data-integrity error that cannot be resolved by LLM retries.
    The system must fail fast before any LLM call to prevent budget exhaustion.
    """

    def test_missing_cards_raises_known_error(self, sample_card_db: dict[str, dict]) -> None:
        """Cards in collection but not in DB raises KnownError (terminal failure)."""
        collection = Collection(
            cards={
                "Lightning Bolt": 4,  # In DB
                "Mystery Card Alpha": 2,  # Not in DB
                "Mystery Card Beta": 1,  # Not in DB
            }
        )

        with pytest.raises(KnownError) as exc_info:
            search_collection(collection, sample_card_db)

        # Verify terminal failure classification
        assert exc_info.value.kind == FailureKind.VALIDATION_FAILED

        # Verify user-actionable error message
        assert "not present in the card database" in exc_info.value.message
        assert "Mystery Card Alpha" in str(exc_info.value.detail)

    def test_all_cards_missing_raises_known_error(self) -> None:
        """If all collection cards are missing from DB, raises KnownError."""
        card_db = {"Some Other Card": {"type_line": "Instant", "colors": ["R"]}}
        collection = Collection(cards={"Unknown Card 1": 4, "Unknown Card 2": 2})

        with pytest.raises(KnownError) as exc_info:
            search_collection(collection, card_db)

        assert exc_info.value.kind == FailureKind.VALIDATION_FAILED
        assert "Unknown Card 1" in str(exc_info.value.detail)

    def test_missing_card_error_has_suggestion(self, sample_card_db: dict[str, dict]) -> None:
        """KnownError includes actionable suggestion for user."""
        collection = Collection(cards={"Nonexistent Card": 1})

        with pytest.raises(KnownError) as exc_info:
            search_collection(collection, sample_card_db)

        # Verify suggestion helps user resolve the issue
        assert exc_info.value.suggestion is not None
        assert (
            "update" in exc_info.value.suggestion.lower()
            or "check" in exc_info.value.suggestion.lower()
        )
