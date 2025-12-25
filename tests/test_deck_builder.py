"""Tests for deck builder service."""

from typing import Any

import pytest

from forgebreaker.models.collection import Collection
from forgebreaker.services.deck_builder import (
    ARCHETYPE_CURVES,
    ARCHETYPE_INDICATORS,
    BuiltDeck,
    DeckBuildRequest,
    _calculate_curve,
    _detect_archetype,
    _get_cmc_bucket,
    _score_for_curve,
    build_deck,
    export_deck_to_arena,
    format_built_deck,
)


@pytest.fixture
def card_db() -> dict[str, dict[str, Any]]:
    """Sample card database for testing."""
    return {
        "Sanctum of Stone Fangs": {
            "type_line": "Legendary Enchantment — Shrine",
            "colors": ["B"],
            "set": "M21",
            "collector_number": "120",
            "cmc": 2,
            "oracle_text": (
                "At the beginning of your precombat main phase, "
                "each opponent loses 1 life for each Shrine you control."
            ),
        },
        "Sanctum of Shattered Heights": {
            "type_line": "Legendary Enchantment — Shrine",
            "colors": ["R"],
            "set": "M21",
            "collector_number": "157",
            "cmc": 3,
            "oracle_text": (
                "Sacrifice a Shrine: Deal damage equal to the number of Shrines you control."
            ),
        },
        "Go for the Throat": {
            "type_line": "Instant",
            "colors": ["B"],
            "set": "MOM",
            "collector_number": "105",
            "cmc": 2,
            "oracle_text": "Destroy target nonartifact creature.",
        },
        "Lightning Bolt": {
            "type_line": "Instant",
            "colors": ["R"],
            "set": "STA",
            "collector_number": "42",
            "cmc": 1,
            "oracle_text": "Lightning Bolt deals 3 damage to any target.",
        },
        "Swamp": {
            "type_line": "Basic Land — Swamp",
            "colors": [],
            "set": "FDN",
            "collector_number": "280",
            "cmc": 0,
            "oracle_text": "",
        },
        "Mountain": {
            "type_line": "Basic Land — Mountain",
            "colors": [],
            "set": "FDN",
            "collector_number": "279",
            "cmc": 0,
            "oracle_text": "",
        },
        "Blood Crypt": {
            "type_line": "Land — Swamp Mountain",
            "colors": [],
            "set": "RNA",
            "collector_number": "245",
            "cmc": 0,
            "oracle_text": (
                "({T}: Add {B} or {R}.) Blood Crypt enters tapped unless you pay 2 life."
            ),
        },
    }


@pytest.fixture
def collection() -> Collection:
    """Sample collection with shrine deck cards."""
    return Collection(
        cards={
            "Sanctum of Stone Fangs": 4,
            "Sanctum of Shattered Heights": 4,
            "Go for the Throat": 4,
            "Lightning Bolt": 4,
            "Swamp": 20,
            "Mountain": 20,
            "Blood Crypt": 4,
        }
    )


@pytest.fixture
def format_legality() -> dict[str, set[str]]:
    """All test cards legal in historic."""
    return {
        "historic": {
            "Sanctum of Stone Fangs",
            "Sanctum of Shattered Heights",
            "Go for the Throat",
            "Lightning Bolt",
            "Swamp",
            "Mountain",
            "Blood Crypt",
        }
    }


class TestBuildDeck:
    """Tests for build_deck function."""

    def test_build_shrine_deck(
        self,
        collection: Collection,
        card_db: dict[str, dict[str, Any]],
        format_legality: dict[str, set[str]],
    ) -> None:
        """Builds deck around shrine theme."""
        request = DeckBuildRequest(
            theme="Shrine",
            format="historic",
        )

        deck = build_deck(request, collection, card_db, format_legality)

        assert deck.name == "Shrine Deck"
        assert "Sanctum of Stone Fangs" in deck.theme_cards
        assert "Sanctum of Shattered Heights" in deck.theme_cards
        assert deck.colors == {"B", "R"}

    def test_build_includes_support(
        self,
        collection: Collection,
        card_db: dict[str, dict[str, Any]],
        format_legality: dict[str, set[str]],
    ) -> None:
        """Support cards are added to deck."""
        request = DeckBuildRequest(
            theme="Shrine",
            format="historic",
        )

        deck = build_deck(request, collection, card_db, format_legality)

        # Should include removal as support
        assert len(deck.support_cards) > 0

    def test_build_includes_lands(
        self,
        collection: Collection,
        card_db: dict[str, dict[str, Any]],
        format_legality: dict[str, set[str]],
    ) -> None:
        """Lands are added to deck."""
        request = DeckBuildRequest(
            theme="Shrine",
            format="historic",
        )

        deck = build_deck(request, collection, card_db, format_legality)

        assert len(deck.lands) > 0
        assert sum(deck.lands.values()) > 0

    def test_build_no_theme_cards(
        self,
        collection: Collection,
        card_db: dict[str, dict[str, Any]],
        format_legality: dict[str, set[str]],
    ) -> None:
        """Returns warning when no theme cards found."""
        request = DeckBuildRequest(
            theme="Dinosaur",  # Not in collection
            format="historic",
        )

        deck = build_deck(request, collection, card_db, format_legality)

        assert len(deck.warnings) > 0
        assert "No cards matching" in deck.warnings[0]

    def test_color_restriction(
        self,
        collection: Collection,
        card_db: dict[str, dict[str, Any]],
        format_legality: dict[str, set[str]],
    ) -> None:
        """Color restriction limits deck colors."""
        request = DeckBuildRequest(
            theme="Shrine",
            colors=["B"],  # Only black
            format="historic",
        )

        deck = build_deck(request, collection, card_db, format_legality)

        assert deck.colors == {"B"}

    def test_include_specific_cards(
        self,
        collection: Collection,
        card_db: dict[str, dict[str, Any]],
        format_legality: dict[str, set[str]],
    ) -> None:
        """Specified cards are included."""
        request = DeckBuildRequest(
            theme="Shrine",
            format="historic",
            include_cards=["Lightning Bolt"],
        )

        deck = build_deck(request, collection, card_db, format_legality)

        assert "Lightning Bolt" in deck.cards

    def test_unknown_format_returns_empty_legality(
        self,
        collection: Collection,
        card_db: dict[str, dict[str, Any]],
        format_legality: dict[str, set[str]],
    ) -> None:
        """Unknown format produces warning about no theme cards."""
        request = DeckBuildRequest(
            theme="Shrine",
            format="unknown_format",
        )

        deck = build_deck(request, collection, card_db, format_legality)

        # No cards are legal, so no theme cards found
        assert len(deck.warnings) > 0

    def test_deck_respects_card_limits(
        self,
        card_db: dict[str, dict[str, Any]],
        format_legality: dict[str, set[str]],
    ) -> None:
        """Cards limited to 4 copies max."""
        # Collection with many copies of one card
        collection = Collection(
            cards={
                "Sanctum of Stone Fangs": 10,
                "Swamp": 40,
            }
        )

        request = DeckBuildRequest(
            theme="Shrine",
            format="historic",
        )

        deck = build_deck(request, collection, card_db, format_legality)

        # Should only include 4 copies max
        assert deck.cards.get("Sanctum of Stone Fangs", 0) <= 4


class TestExportToArena:
    """Tests for export_deck_to_arena function."""

    def test_export_format(
        self,
        collection: Collection,
        card_db: dict[str, dict[str, Any]],
        format_legality: dict[str, set[str]],
    ) -> None:
        """Export produces Arena-compatible format."""
        request = DeckBuildRequest(theme="Shrine", format="historic")
        deck = build_deck(request, collection, card_db, format_legality)

        export = export_deck_to_arena(deck, card_db)

        assert export.startswith("Deck")
        assert "Sanctum of Stone Fangs (M21)" in export

    def test_export_includes_collector_number(
        self,
        collection: Collection,
        card_db: dict[str, dict[str, Any]],
        format_legality: dict[str, set[str]],
    ) -> None:
        """Export includes collector numbers."""
        request = DeckBuildRequest(theme="Shrine", format="historic")
        deck = build_deck(request, collection, card_db, format_legality)

        export = export_deck_to_arena(deck, card_db)

        # M21 120 is Sanctum of Stone Fangs
        assert "(M21) 120" in export


class TestFormatBuiltDeck:
    """Tests for format_built_deck function."""

    def test_format_includes_name(self) -> None:
        """Formatted output includes deck name."""
        deck = BuiltDeck(
            name="Test Deck",
            cards={"Lightning Bolt": 4},
            total_cards=4,
            colors={"R"},
            theme_cards=["Lightning Bolt"],
            support_cards=[],
            lands={},
        )

        formatted = format_built_deck(deck)

        assert "# Test Deck" in formatted

    def test_format_includes_notes(self) -> None:
        """Formatted output includes notes."""
        deck = BuiltDeck(
            name="Test Deck",
            cards={},
            total_cards=0,
            colors=set(),
            theme_cards=[],
            support_cards=[],
            lands={},
            notes=["Found 5 theme cards"],
        )

        formatted = format_built_deck(deck)

        assert "Found 5 theme cards" in formatted

    def test_format_includes_warnings(self) -> None:
        """Formatted output includes warnings."""
        deck = BuiltDeck(
            name="Test Deck",
            cards={},
            total_cards=0,
            colors=set(),
            theme_cards=[],
            support_cards=[],
            lands={},
            warnings=["Not enough lands"],
        )

        formatted = format_built_deck(deck)

        assert "Not enough lands" in formatted

    def test_format_includes_colors(self) -> None:
        """Formatted output includes deck colors."""
        deck = BuiltDeck(
            name="Test Deck",
            cards={},
            total_cards=0,
            colors={"B", "R"},
            theme_cards=[],
            support_cards=[],
            lands={},
        )

        formatted = format_built_deck(deck)

        assert "Colors:" in formatted
        assert "B" in formatted
        assert "R" in formatted


class TestArchetypeDetection:
    """Tests for archetype detection functions."""

    def test_detect_aggro_from_theme(self) -> None:
        """Detects aggro from aggressive theme keywords."""
        # 3-tuples: (name, qty, card_data)
        theme_cards = [
            ("Monastery Swiftspear", 4, {"cmc": 1, "oracle_text": "Haste, prowess"}),
            ("Goblin Guide", 4, {"cmc": 1, "oracle_text": "Haste. Whenever attacks"}),
            ("Lightning Bolt", 4, {"cmc": 1, "oracle_text": "Deals 3 damage"}),
        ]
        result = _detect_archetype("aggro", theme_cards)
        assert result == "aggro"

    def test_detect_control_from_theme(self) -> None:
        """Detects control from reactive card text."""
        theme_cards = [
            ("Counterspell", 4, {"cmc": 2, "oracle_text": "Counter target spell"}),
            ("Doom Blade", 4, {"cmc": 2, "oracle_text": "Destroy target creature"}),
            ("Sphinx's Revelation", 2, {"cmc": 6, "oracle_text": "Draw a card"}),
        ]
        result = _detect_archetype("control", theme_cards)
        assert result == "control"

    def test_detect_combo_from_keywords(self) -> None:
        """Detects combo from engine pieces."""
        theme_cards = [
            ("Cauldron Familiar", 4, {"cmc": 1, "oracle_text": "Sacrifice this"}),
            ("Witch's Oven", 4, {"cmc": 1, "oracle_text": "Sacrifice a creature"}),
            ("Mayhem Devil", 4, {"cmc": 3, "oracle_text": "Whenever sacrifices"}),
        ]
        result = _detect_archetype("sacrifice", theme_cards)
        assert result == "combo"

    def test_detect_midrange_default(self) -> None:
        """Falls back to midrange for balanced decks."""
        theme_cards = [
            ("Siege Rhino", 4, {"cmc": 4, "oracle_text": "enter battlefield"}),
            ("Courser of Kruphix", 4, {"cmc": 3, "oracle_text": "Play lands"}),
        ]
        result = _detect_archetype("value", theme_cards)
        assert result == "midrange"

    def test_detect_aggro_from_low_cmc(self) -> None:
        """Low average CMC pushes toward aggro detection."""
        theme_cards = [
            ("Card1", 4, {"cmc": 1, "oracle_text": ""}),
            ("Card2", 4, {"cmc": 1, "oracle_text": ""}),
            ("Card3", 4, {"cmc": 2, "oracle_text": ""}),
        ]
        result = _detect_archetype("generic", theme_cards)
        # Avg CMC ~1.33 is well below 2.0 threshold, should be aggro
        assert result == "aggro"


class TestCMCBucket:
    """Tests for CMC bucketing function."""

    def test_bucket_low_cmc(self) -> None:
        """Low CMC cards bucket correctly."""
        assert _get_cmc_bucket(0) == 1
        assert _get_cmc_bucket(1) == 1
        assert _get_cmc_bucket(2) == 2
        assert _get_cmc_bucket(3) == 3

    def test_bucket_high_cmc(self) -> None:
        """High CMC cards bucket to 6."""
        assert _get_cmc_bucket(6) == 6
        assert _get_cmc_bucket(7) == 6
        assert _get_cmc_bucket(10) == 6

    def test_bucket_fractional_cmc(self) -> None:
        """Fractional CMC cards bucket via int() truncation."""
        assert _get_cmc_bucket(2.5) == 2
        assert _get_cmc_bucket(3.5) == 3
        assert _get_cmc_bucket(1.5) == 1


class TestCalculateCurve:
    """Tests for mana curve calculation."""

    def test_calculate_curve_empty(self) -> None:
        """Empty deck has zeroed curve."""
        cards: dict[str, int] = {}
        card_db: dict[str, dict[str, Any]] = {}
        result = _calculate_curve(cards, card_db)
        # All buckets initialized to 0
        assert all(v == 0 for v in result.values())

    def test_calculate_curve_simple(self) -> None:
        """Calculates curve from card CMCs."""
        cards = {"Lightning Bolt": 4, "Goblin Guide": 4}
        card_db = {
            "Lightning Bolt": {"cmc": 1},
            "Goblin Guide": {"cmc": 1},
        }
        result = _calculate_curve(cards, card_db)
        assert result.get(1, 0) == 8

    def test_calculate_curve_mixed(self) -> None:
        """Mixed CMC cards distribute across curve."""
        cards = {"One Drop": 4, "Two Drop": 4, "Three Drop": 4}
        card_db = {
            "One Drop": {"cmc": 1},
            "Two Drop": {"cmc": 2},
            "Three Drop": {"cmc": 3},
        }
        result = _calculate_curve(cards, card_db)
        assert result.get(1, 0) == 4
        assert result.get(2, 0) == 4
        assert result.get(3, 0) == 4


class TestScoreForCurve:
    """Tests for curve scoring function."""

    def test_score_needed_slot(self) -> None:
        """Cards that fill needed curve slots score higher."""
        # Args: (cmc, current_curve, target_curve)
        current = {1: 0, 2: 8, 3: 8}  # Need 1-drops
        target = {1: 8, 2: 8, 3: 8}
        # 1-drop should score higher than 2-drop
        score_1 = _score_for_curve(1, current, target)
        score_2 = _score_for_curve(2, current, target)
        assert score_1 > score_2

    def test_score_filled_slot(self) -> None:
        """Cards in overfilled slots score zero."""
        current = {1: 6}  # Already over target
        target = {1: 4}
        score = _score_for_curve(1, current, target)
        assert score == 0.0

    def test_score_empty_target(self) -> None:
        """Cards in slots with no target score zero."""
        current = {1: 2}
        target = {1: 4}
        # 5-drop has no target in target dict
        score = _score_for_curve(5, current, target)
        assert score == 0.0


class TestArchetypeCurveConstants:
    """Tests for archetype curve constants."""

    def test_all_archetypes_defined(self) -> None:
        """All archetypes have curve definitions."""
        assert "aggro" in ARCHETYPE_CURVES
        assert "midrange" in ARCHETYPE_CURVES
        assert "control" in ARCHETYPE_CURVES
        assert "combo" in ARCHETYPE_CURVES

    def test_aggro_curve_low(self) -> None:
        """Aggro curve is weighted toward low CMC."""
        aggro = ARCHETYPE_CURVES["aggro"]
        low_cmc = aggro.get(1, 0) + aggro.get(2, 0)
        high_cmc = aggro.get(5, 0) + aggro.get(6, 0)
        assert low_cmc > high_cmc

    def test_control_curve_high(self) -> None:
        """Control curve has higher CMC cards."""
        control = ARCHETYPE_CURVES["control"]
        aggro = ARCHETYPE_CURVES["aggro"]
        # Control has more 4+ drops than aggro
        control_high = control.get(4, 0) + control.get(5, 0)
        aggro_high = aggro.get(4, 0) + aggro.get(5, 0)
        assert control_high > aggro_high

    def test_indicators_defined(self) -> None:
        """Archetype indicators are defined."""
        assert len(ARCHETYPE_INDICATORS["aggro"]) > 0
        assert len(ARCHETYPE_INDICATORS["control"]) > 0
        assert len(ARCHETYPE_INDICATORS["combo"]) > 0


class TestBuiltDeckArchetype:
    """Tests for archetype in built decks."""

    def test_built_deck_has_archetype(
        self,
        collection: Collection,
        card_db: dict[str, dict[str, Any]],
        format_legality: dict[str, set[str]],
    ) -> None:
        """Built deck includes archetype field."""
        request = DeckBuildRequest(theme="Shrine", format="historic")
        deck = build_deck(request, collection, card_db, format_legality)
        assert hasattr(deck, "archetype")
        assert deck.archetype in ("aggro", "midrange", "control", "combo")

    def test_built_deck_has_mana_curve(
        self,
        collection: Collection,
        card_db: dict[str, dict[str, Any]],
        format_legality: dict[str, set[str]],
    ) -> None:
        """Built deck includes mana curve."""
        request = DeckBuildRequest(theme="Shrine", format="historic")
        deck = build_deck(request, collection, card_db, format_legality)
        assert hasattr(deck, "mana_curve")
        assert isinstance(deck.mana_curve, dict)

    def test_format_includes_archetype(self) -> None:
        """Formatted output includes archetype."""
        deck = BuiltDeck(
            name="Test Deck",
            cards={"Lightning Bolt": 4},
            total_cards=4,
            colors={"R"},
            theme_cards=["Lightning Bolt"],
            support_cards=[],
            lands={},
            archetype="aggro",
            mana_curve={1: 4},
        )
        formatted = format_built_deck(deck)
        assert "aggro" in formatted.lower()

    def test_format_includes_mana_curve(self) -> None:
        """Formatted output includes mana curve."""
        deck = BuiltDeck(
            name="Test Deck",
            cards={"Lightning Bolt": 4, "Goblin Guide": 4},
            total_cards=8,
            colors={"R"},
            theme_cards=["Lightning Bolt", "Goblin Guide"],
            support_cards=[],
            lands={},
            archetype="aggro",
            mana_curve={1: 8},
        )
        formatted = format_built_deck(deck)
        assert "Mana Curve" in formatted or "curve" in formatted.lower()
