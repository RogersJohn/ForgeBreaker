from pathlib import Path

import pytest

from forgebreaker.parsers.scryfall import (
    load_arena_id_mapping,
    load_card_data,
    load_rarity_mapping,
)


@pytest.fixture
def sample_bulk_path() -> Path:
    return Path(__file__).parent / "fixtures" / "scryfall_sample.json"


class TestLoadArenaIdMapping:
    def test_loads_arena_ids(self, sample_bulk_path: Path) -> None:
        mapping = load_arena_id_mapping(sample_bulk_path)

        assert mapping[12345] == "Lightning Bolt"
        assert mapping[82377] == "Sheoldred, the Apocalypse"

    def test_skips_cards_without_arena_id(self, sample_bulk_path: Path) -> None:
        mapping = load_arena_id_mapping(sample_bulk_path)

        # Should only have 3 entries (one card has no arena_id)
        assert len(mapping) == 3


class TestLoadRarityMapping:
    def test_loads_rarities(self, sample_bulk_path: Path) -> None:
        mapping = load_rarity_mapping(sample_bulk_path)

        assert mapping["Lightning Bolt"] == "common"
        assert mapping["Sheoldred, the Apocalypse"] == "mythic"
        assert mapping["Monastery Swiftspear"] == "uncommon"
        assert mapping["Card Without Arena ID"] == "rare"


class TestLoadCardData:
    def test_loads_complete_data(self, sample_bulk_path: Path) -> None:
        data = load_card_data(sample_bulk_path)

        bolt = data["Lightning Bolt"]
        assert bolt["name"] == "Lightning Bolt"
        assert bolt["arena_id"] == 12345
        assert bolt["rarity"] == "common"

    def test_handles_missing_arena_id(self, sample_bulk_path: Path) -> None:
        data = load_card_data(sample_bulk_path)

        card = data["Card Without Arena ID"]
        assert card["arena_id"] is None
