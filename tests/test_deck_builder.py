"""Tests for deck builder service."""

from typing import Any

import pytest

from forgebreaker.models.collection import Collection
from forgebreaker.services.deck_builder import (
    ARCHETYPE_CURVES,
    ARCHETYPE_INDICATORS,
    ARCHETYPE_ROLE_TARGETS,
    DECK_ROLES,
    BuiltDeck,
    DeckBuildRequest,
    _calculate_curve,
    _count_color_pips,
    _count_deck_roles,
    _detect_archetype,
    _get_card_role,
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
            "games": ["arena", "paper", "mtgo"],
            "mana_cost": "{1}{B}",
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
            "games": ["arena", "paper", "mtgo"],
            "mana_cost": "{2}{R}",
        },
        "Go for the Throat": {
            "type_line": "Instant",
            "colors": ["B"],
            "set": "MOM",
            "collector_number": "105",
            "cmc": 2,
            "oracle_text": "Destroy target nonartifact creature.",
            "games": ["arena", "paper", "mtgo"],
            "mana_cost": "{1}{B}",
        },
        "Lightning Bolt": {
            "type_line": "Instant",
            "colors": ["R"],
            "set": "STA",
            "collector_number": "42",
            "cmc": 1,
            "oracle_text": "Lightning Bolt deals 3 damage to any target.",
            "games": ["arena", "paper", "mtgo"],
            "mana_cost": "{R}",
        },
        # Additional cards for 60-card deck support
        "Shock": {
            "type_line": "Instant",
            "colors": ["R"],
            "set": "M21",
            "collector_number": "159",
            "cmc": 1,
            "oracle_text": "Shock deals 2 damage to any target.",
            "games": ["arena", "paper", "mtgo"],
            "mana_cost": "{R}",
        },
        "Duress": {
            "type_line": "Sorcery",
            "colors": ["B"],
            "set": "M21",
            "collector_number": "96",
            "cmc": 1,
            "oracle_text": "Target opponent reveals their hand. You choose a noncreature spell.",
            "games": ["arena", "paper", "mtgo"],
            "mana_cost": "{B}",
        },
        "Terminate": {
            "type_line": "Instant",
            "colors": ["B", "R"],
            "set": "MH2",
            "collector_number": "215",
            "cmc": 2,
            "oracle_text": "Destroy target creature. It can't be regenerated.",
            "games": ["arena", "paper", "mtgo"],
            "mana_cost": "{B}{R}",
        },
        "Blightning": {
            "type_line": "Sorcery",
            "colors": ["B", "R"],
            "set": "A25",
            "collector_number": "198",
            "cmc": 3,
            "oracle_text": "Blightning deals 3 damage to target player and they discard two cards.",
            "games": ["arena", "paper", "mtgo"],
            "mana_cost": "{1}{B}{R}",
        },
        "Dreadbore": {
            "type_line": "Sorcery",
            "colors": ["B", "R"],
            "set": "RTR",
            "collector_number": "157",
            "cmc": 2,
            "oracle_text": "Destroy target creature or planeswalker.",
            "games": ["arena", "paper", "mtgo"],
            "mana_cost": "{B}{R}",
        },
        "Swamp": {
            "type_line": "Basic Land — Swamp",
            "colors": [],
            "set": "FDN",
            "collector_number": "280",
            "cmc": 0,
            "oracle_text": "",
            "games": ["arena", "paper", "mtgo"],
            "mana_cost": "",
        },
        "Mountain": {
            "type_line": "Basic Land — Mountain",
            "colors": [],
            "set": "FDN",
            "collector_number": "279",
            "cmc": 0,
            "oracle_text": "",
            "games": ["arena", "paper", "mtgo"],
            "mana_cost": "",
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
            "games": ["arena", "paper", "mtgo"],
            "mana_cost": "",
        },
    }


@pytest.fixture
def collection() -> Collection:
    """Sample collection with shrine deck cards (enough for 60-card deck)."""
    return Collection(
        cards={
            # Theme cards (Shrines)
            "Sanctum of Stone Fangs": 4,
            "Sanctum of Shattered Heights": 4,
            # Support cards (36 nonland total needed)
            "Go for the Throat": 4,
            "Lightning Bolt": 4,
            "Shock": 4,
            "Duress": 4,
            "Terminate": 4,
            "Blightning": 4,
            "Dreadbore": 4,  # 32 nonland + 4 shrines = 36 nonland total
            # Additional cards to ensure we have enough
            # Lands
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
            "Shock",
            "Duress",
            "Terminate",
            "Blightning",
            "Dreadbore",
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
        # Use 44-card deck (20 nonland + 24 lands) to match available cards
        request = DeckBuildRequest(
            theme="Shrine",
            format="historic",
            deck_size=44,
            land_count=24,
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
            deck_size=44,
            land_count=24,
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
            deck_size=44,
            land_count=24,
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
            deck_size=44,
            land_count=24,
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
        # Black + Red allowed so we have enough cards
        request = DeckBuildRequest(
            theme="Shrine",
            colors=["B", "R"],  # Rakdos colors
            format="historic",
            deck_size=44,
            land_count=24,
        )

        deck = build_deck(request, collection, card_db, format_legality)

        # All cards in the deck should be B and/or R
        assert deck.colors.issubset({"B", "R"})

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
            deck_size=44,
            land_count=24,
        )

        deck = build_deck(request, collection, card_db, format_legality)

        assert "Lightning Bolt" in deck.cards

    def test_unknown_format_raises_deck_size_error(
        self,
        collection: Collection,
        card_db: dict[str, dict[str, Any]],
        format_legality: dict[str, set[str]],
    ) -> None:
        """Unknown format with no legal cards raises DeckSizeError."""
        from forgebreaker.models.failure import DeckSizeError

        request = DeckBuildRequest(
            theme="Shrine",
            format="unknown_format",
            deck_size=60,
            land_count=24,
        )

        # No cards are legal, so deck cannot be built
        with pytest.raises(DeckSizeError):
            build_deck(request, collection, card_db, format_legality)

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

        # Only 4 nonland + 24 lands = 28 cards possible
        request = DeckBuildRequest(
            theme="Shrine",
            format="historic",
            deck_size=28,
            land_count=24,
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
        request = DeckBuildRequest(theme="Shrine", format="historic", deck_size=44, land_count=24)
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
        request = DeckBuildRequest(theme="Shrine", format="historic", deck_size=44, land_count=24)
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

    def test_score_exact_target(self) -> None:
        """Cards at exact target also score zero."""
        current = {1: 4}  # Exactly at target
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
        request = DeckBuildRequest(theme="Shrine", format="historic", deck_size=44, land_count=24)
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
        request = DeckBuildRequest(theme="Shrine", format="historic", deck_size=44, land_count=24)
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
        assert "**Archetype:** Aggro" in formatted

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
        assert "**Mana Curve:**" in formatted


class TestRoleDetection:
    """Tests for card role detection."""

    def test_get_card_role_removal(self) -> None:
        """Detects removal cards."""
        assert _get_card_role("Destroy target creature.") == "removal"
        assert _get_card_role("Exile target permanent.") == "removal"
        assert _get_card_role("Lightning Bolt deals 3 damage to any target.") == "removal"

    def test_get_card_role_card_draw(self) -> None:
        """Detects card draw cards."""
        assert _get_card_role("Draw a card.") == "card_draw"
        assert _get_card_role("Scry 2, then draw a card.") == "card_draw"
        assert _get_card_role("Look at the top three cards.") == "card_draw"

    def test_get_card_role_ramp(self) -> None:
        """Detects ramp cards."""
        assert _get_card_role("Add {G}{G}.") == "ramp"
        assert _get_card_role("Search your library for a basic land.") == "ramp"

    def test_get_card_role_finisher(self) -> None:
        """Detects finisher cards."""
        assert _get_card_role("Flying, trample") == "finisher"
        assert _get_card_role("This creature can't be blocked.") == "finisher"

    def test_get_card_role_none(self) -> None:
        """Returns None for cards without clear role."""
        assert _get_card_role("When this creature enters the battlefield") is None
        assert _get_card_role("") is None


class TestDeckRoles:
    """Tests for deck role counting."""

    def test_count_deck_roles_empty(self) -> None:
        """Empty deck has zero roles."""
        cards: dict[str, int] = {}
        card_db: dict[str, dict[str, Any]] = {}
        result = _count_deck_roles(cards, card_db)
        assert all(v == 0 for v in result.values())

    def test_count_deck_roles_removal(self) -> None:
        """Counts removal cards."""
        cards = {"Murder": 4, "Lightning Bolt": 4}
        card_db = {
            "Murder": {"type_line": "Instant", "oracle_text": "Destroy target creature."},
            "Lightning Bolt": {"type_line": "Instant", "oracle_text": "Damage to any target."},
        }
        result = _count_deck_roles(cards, card_db)
        assert result["removal"] == 8

    def test_count_deck_roles_skips_lands(self) -> None:
        """Lands are not counted for roles."""
        cards = {"Mountain": 10, "Lightning Bolt": 4}
        card_db = {
            "Mountain": {"type_line": "Basic Land — Mountain", "oracle_text": ""},
            "Lightning Bolt": {"type_line": "Instant", "oracle_text": "Damage to any target."},
        }
        result = _count_deck_roles(cards, card_db)
        assert result["removal"] == 4


class TestColorPipCounting:
    """Tests for color pip counting."""

    def test_count_color_pips_empty(self) -> None:
        """Empty deck has zero pips."""
        cards: dict[str, int] = {}
        card_db: dict[str, dict[str, Any]] = {}
        result = _count_color_pips(cards, card_db)
        assert all(v == 0 for v in result.values())

    def test_count_color_pips_single_color(self) -> None:
        """Counts pips for single color cards."""
        cards = {"Lightning Bolt": 4}
        card_db = {"Lightning Bolt": {"type_line": "Instant", "mana_cost": "{R}"}}
        result = _count_color_pips(cards, card_db)
        assert result["R"] == 4
        assert result["W"] == 0

    def test_count_color_pips_multicolor(self) -> None:
        """Counts pips for multicolor cards."""
        cards = {"Terminate": 4}
        card_db = {"Terminate": {"type_line": "Instant", "mana_cost": "{B}{R}"}}
        result = _count_color_pips(cards, card_db)
        assert result["B"] == 4
        assert result["R"] == 4

    def test_count_color_pips_double_pip(self) -> None:
        """Counts double pips correctly."""
        cards = {"Counterspell": 4}
        card_db = {"Counterspell": {"type_line": "Instant", "mana_cost": "{U}{U}"}}
        result = _count_color_pips(cards, card_db)
        assert result["U"] == 8  # 2 pips × 4 copies

    def test_count_color_pips_skips_lands(self) -> None:
        """Lands are not counted for pips."""
        cards = {"Island": 10, "Counterspell": 4}
        card_db = {
            "Island": {"type_line": "Basic Land — Island", "mana_cost": ""},
            "Counterspell": {"type_line": "Instant", "mana_cost": "{U}{U}"},
        }
        result = _count_color_pips(cards, card_db)
        assert result["U"] == 8


class TestRoleConstants:
    """Tests for role constants."""

    def test_all_roles_defined(self) -> None:
        """All expected roles are defined."""
        assert "removal" in DECK_ROLES
        assert "card_draw" in DECK_ROLES
        assert "ramp" in DECK_ROLES
        assert "finisher" in DECK_ROLES

    def test_all_archetypes_have_role_targets(self) -> None:
        """All archetypes have role targets."""
        assert "aggro" in ARCHETYPE_ROLE_TARGETS
        assert "midrange" in ARCHETYPE_ROLE_TARGETS
        assert "control" in ARCHETYPE_ROLE_TARGETS
        assert "combo" in ARCHETYPE_ROLE_TARGETS

    def test_control_has_most_removal(self) -> None:
        """Control decks target most removal."""
        control_removal = ARCHETYPE_ROLE_TARGETS["control"]["removal"]
        aggro_removal = ARCHETYPE_ROLE_TARGETS["aggro"]["removal"]
        assert control_removal > aggro_removal


class TestBuiltDeckRoles:
    """Tests for role counts in built decks."""

    def test_built_deck_has_role_counts(
        self,
        collection: Collection,
        card_db: dict[str, dict[str, Any]],
        format_legality: dict[str, set[str]],
    ) -> None:
        """Built deck includes role_counts field."""
        request = DeckBuildRequest(theme="Shrine", format="historic", deck_size=44, land_count=24)
        deck = build_deck(request, collection, card_db, format_legality)
        assert hasattr(deck, "role_counts")
        assert isinstance(deck.role_counts, dict)

    def test_format_includes_roles(self) -> None:
        """Formatted output includes roles."""
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
            role_counts={"removal": 4, "card_draw": 0, "ramp": 0, "finisher": 0},
        )
        formatted = format_built_deck(deck)
        assert "**Roles:**" in formatted
        assert "removal:4" in formatted  # "removal" has no underscore
