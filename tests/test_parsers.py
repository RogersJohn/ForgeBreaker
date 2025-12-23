from pathlib import Path

from forgebreaker.models.card import Card
from forgebreaker.parsers.arena_export import (
    cards_to_collection,
    parse_arena_export,
    parse_arena_to_collection,
)
from forgebreaker.parsers.collection_import import (
    detect_format,
    merge_collections,
    parse_collection_text,
    parse_csv_format,
    parse_multiple_decks,
    parse_simple_format,
)


class TestParseArenaExport:
    def test_parse_full_format(self) -> None:
        text = "4 Lightning Bolt (LEB) 163"
        result = parse_arena_export(text)

        assert len(result) == 1
        assert result[0].name == "Lightning Bolt"
        assert result[0].quantity == 4
        assert result[0].set_code == "LEB"
        assert result[0].collector_number == "163"

    def test_parse_simple_format(self) -> None:
        text = "4 Lightning Bolt"
        result = parse_arena_export(text)

        assert len(result) == 1
        assert result[0].name == "Lightning Bolt"
        assert result[0].quantity == 4
        assert result[0].set_code is None
        assert result[0].collector_number is None

    def test_parse_alphanumeric_collector_number(self) -> None:
        """Collector numbers can be alphanumeric (e.g., alternate art versions)."""
        text = "4 Mountain (NEO) 290a"
        result = parse_arena_export(text)

        assert len(result) == 1
        assert result[0].name == "Mountain"
        assert result[0].collector_number == "290a"

    def test_parse_split_card(self) -> None:
        """Split cards have // in the name."""
        text = "4 Fire // Ice (MH2) 290"
        result = parse_arena_export(text)

        assert len(result) == 1
        assert result[0].name == "Fire // Ice"

    def test_parse_empty_input(self) -> None:
        assert parse_arena_export("") == []
        assert parse_arena_export("   ") == []
        assert parse_arena_export("\n\n\n") == []

    def test_parse_with_section_headers(self) -> None:
        text = """Deck
4 Lightning Bolt (LEB) 163

Sideboard
2 Abrade (VOW) 139"""
        result = parse_arena_export(text)

        assert len(result) == 2
        assert result[0].name == "Lightning Bolt"
        assert result[1].name == "Abrade"

    def test_parse_ignores_malformed_lines(self) -> None:
        text = """4 Lightning Bolt (LEB) 163
This is not a valid card line
Another invalid line
2 Mountain (NEO) 290"""
        result = parse_arena_export(text)

        assert len(result) == 2
        assert result[0].name == "Lightning Bolt"
        assert result[1].name == "Mountain"

    def test_parse_card_with_comma_in_name(self) -> None:
        text = "2 Sheoldred, the Apocalypse (DMU) 107"
        result = parse_arena_export(text)

        assert len(result) == 1
        assert result[0].name == "Sheoldred, the Apocalypse"

    def test_parse_basic_land_high_quantity(self) -> None:
        """Basic lands can have more than 4 copies."""
        text = "24 Mountain (NEO) 290"
        result = parse_arena_export(text)

        assert len(result) == 1
        assert result[0].quantity == 24

    def test_parse_fixture_file(self) -> None:
        """Test parsing the fixture file."""
        fixture_path = Path(__file__).parent / "fixtures" / "sample_collection.txt"
        text = fixture_path.read_text()
        result = parse_arena_export(text)

        assert len(result) == 7
        names = [c.name for c in result]
        assert "Lightning Bolt" in names
        assert "Fire // Ice" in names
        assert "Sheoldred, the Apocalypse" in names


class TestCardsToCollection:
    def test_aggregates_duplicates(self) -> None:
        cards = [
            Card(name="Lightning Bolt", quantity=2),
            Card(name="Lightning Bolt", quantity=2),
        ]
        collection = cards_to_collection(cards)

        assert collection.get_quantity("Lightning Bolt") == 4

    def test_preserves_unique_cards(self) -> None:
        cards = [
            Card(name="Lightning Bolt", quantity=4),
            Card(name="Mountain", quantity=20),
        ]
        collection = cards_to_collection(cards)

        assert collection.unique_cards() == 2
        assert collection.total_cards() == 24


class TestParseArenaToCollection:
    def test_convenience_function(self) -> None:
        text = """4 Lightning Bolt (LEB) 163
4 Mountain (NEO) 290"""
        collection = parse_arena_to_collection(text)

        assert collection.owns("Lightning Bolt", 4)
        assert collection.owns("Mountain", 4)


class TestParseSimpleFormat:
    def test_basic_format(self) -> None:
        text = "4 Lightning Bolt"
        result = parse_simple_format(text)

        assert result == {"Lightning Bolt": 4}

    def test_format_with_x(self) -> None:
        text = "4x Lightning Bolt"
        result = parse_simple_format(text)

        assert result == {"Lightning Bolt": 4}

    def test_format_with_uppercase_x(self) -> None:
        text = "4X Lightning Bolt"
        result = parse_simple_format(text)

        assert result == {"Lightning Bolt": 4}

    def test_multiple_cards(self) -> None:
        text = """4 Lightning Bolt
2x Monastery Swiftspear
20 Mountain"""
        result = parse_simple_format(text)

        assert result == {
            "Lightning Bolt": 4,
            "Monastery Swiftspear": 2,
            "Mountain": 20,
        }

    def test_aggregates_duplicates(self) -> None:
        text = """4 Lightning Bolt
2 Lightning Bolt"""
        result = parse_simple_format(text)

        assert result == {"Lightning Bolt": 6}

    def test_empty_input(self) -> None:
        assert parse_simple_format("") == {}
        assert parse_simple_format("   ") == {}


class TestParseCsvFormat:
    def test_basic_csv(self) -> None:
        text = """Card Name,Quantity,Set
Lightning Bolt,4,LEB
Mountain,20,NEO"""
        result = parse_csv_format(text)

        assert result == {"Lightning Bolt": 4, "Mountain": 20}

    def test_csv_with_different_column_names(self) -> None:
        text = """Name,Count
Lightning Bolt,4"""
        result = parse_csv_format(text)

        assert result == {"Lightning Bolt": 4}

    def test_csv_defaults_quantity_to_1(self) -> None:
        text = """Card Name
Lightning Bolt
Mountain"""
        result = parse_csv_format(text)

        assert result == {"Lightning Bolt": 1, "Mountain": 1}

    def test_csv_empty_input(self) -> None:
        assert parse_csv_format("") == {}


class TestDetectFormat:
    def test_detects_csv(self) -> None:
        text = """Card Name,Quantity,Set
Lightning Bolt,4,LEB"""
        assert detect_format(text) == "csv"

    def test_detects_arena(self) -> None:
        text = "4 Lightning Bolt (LEB) 163"
        assert detect_format(text) == "arena"

    def test_defaults_to_simple(self) -> None:
        text = "4 Lightning Bolt"
        assert detect_format(text) == "simple"

    def test_empty_defaults_to_simple(self) -> None:
        assert detect_format("") == "simple"


class TestParseCollectionText:
    def test_auto_detect_simple(self) -> None:
        text = "4 Lightning Bolt"
        result = parse_collection_text(text)

        assert result == {"Lightning Bolt": 4}

    def test_auto_detect_csv(self) -> None:
        text = """Card Name,Quantity
Lightning Bolt,4"""
        result = parse_collection_text(text)

        assert result == {"Lightning Bolt": 4}

    def test_auto_detect_arena(self) -> None:
        text = "4 Lightning Bolt (LEB) 163"
        result = parse_collection_text(text)

        assert result == {"Lightning Bolt": 4}

    def test_explicit_format_hint(self) -> None:
        text = "4 Lightning Bolt"
        result = parse_collection_text(text, format_hint="simple")

        assert result == {"Lightning Bolt": 4}

    def test_empty_returns_empty(self) -> None:
        assert parse_collection_text("") == {}
        assert parse_collection_text("   ") == {}


class TestMergeCollections:
    def test_merge_keeps_max(self) -> None:
        base = {"Lightning Bolt": 2, "Mountain": 10}
        new = {"Lightning Bolt": 4, "Forest": 5}
        result = merge_collections(base, new)

        assert result == {
            "Lightning Bolt": 4,
            "Mountain": 10,
            "Forest": 5,
        }

    def test_merge_with_empty_base(self) -> None:
        result = merge_collections({}, {"Lightning Bolt": 4})

        assert result == {"Lightning Bolt": 4}


class TestParseMultipleDecks:
    def test_merge_decks(self) -> None:
        deck1 = "4 Lightning Bolt\n2 Mountain"
        deck2 = "2 Lightning Bolt\n4 Forest"
        result = parse_multiple_decks([deck1, deck2])

        # Should keep max quantities
        assert result.get_quantity("Lightning Bolt") == 4
        assert result.get_quantity("Mountain") == 2
        assert result.get_quantity("Forest") == 4

    def test_skips_empty_decks(self) -> None:
        result = parse_multiple_decks(["4 Lightning Bolt", "", "   "])

        assert result.get_quantity("Lightning Bolt") == 4
