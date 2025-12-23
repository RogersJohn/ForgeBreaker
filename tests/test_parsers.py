from pathlib import Path

from forgebreaker.models.card import Card
from forgebreaker.parsers.arena_export import (
    cards_to_collection,
    parse_arena_export,
    parse_arena_to_collection,
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
