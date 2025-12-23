"""Tests for ML feature engineering."""

import pytest

from forgebreaker.ml.features import (
    CollectionFeatures,
    encode_archetype,
    extract_collection_features,
    extract_deck_features,
)
from forgebreaker.models.collection import Collection
from forgebreaker.models.deck import DeckDistance, MetaDeck, WildcardCost


class TestEncodeArchetype:
    def test_encode_aggro(self) -> None:
        """Aggro encodes to [1, 0, 0, 0]."""
        result = encode_archetype("aggro")
        assert result == [1.0, 0.0, 0.0, 0.0]

    def test_encode_midrange(self) -> None:
        """Midrange encodes to [0, 1, 0, 0]."""
        result = encode_archetype("midrange")
        assert result == [0.0, 1.0, 0.0, 0.0]

    def test_encode_control(self) -> None:
        """Control encodes to [0, 0, 1, 0]."""
        result = encode_archetype("control")
        assert result == [0.0, 0.0, 1.0, 0.0]

    def test_encode_combo(self) -> None:
        """Combo encodes to [0, 0, 0, 1]."""
        result = encode_archetype("combo")
        assert result == [0.0, 0.0, 0.0, 1.0]

    def test_encode_case_insensitive(self) -> None:
        """Encoding is case insensitive."""
        assert encode_archetype("AGGRO") == [1.0, 0.0, 0.0, 0.0]
        assert encode_archetype("Control") == [0.0, 0.0, 1.0, 0.0]

    def test_encode_unknown(self) -> None:
        """Unknown archetype encodes to all zeros."""
        result = encode_archetype("unknown")
        assert result == [0.0, 0.0, 0.0, 0.0]


class TestExtractCollectionFeatures:
    def test_empty_collection(self) -> None:
        """Empty collection returns zero features."""
        collection = Collection()
        features = extract_collection_features(collection, {})

        assert features.total_cards == 0
        assert features.unique_cards == 0
        assert features.common_count == 0
        assert features.uncommon_count == 0
        assert features.rare_count == 0
        assert features.mythic_count == 0

    def test_counts_by_rarity(self) -> None:
        """Cards are counted by their rarity."""
        collection = Collection(
            cards={
                "Lightning Bolt": 4,
                "Monastery Swiftspear": 4,
                "Sheoldred, the Apocalypse": 2,
                "Den of the Bugbear": 4,
            }
        )
        rarity_map = {
            "Lightning Bolt": "common",
            "Monastery Swiftspear": "uncommon",
            "Sheoldred, the Apocalypse": "mythic",
            "Den of the Bugbear": "rare",
        }

        features = extract_collection_features(collection, rarity_map)

        assert features.total_cards == 14
        assert features.unique_cards == 4
        assert features.common_count == 4
        assert features.uncommon_count == 4
        assert features.rare_count == 4
        assert features.mythic_count == 2

    def test_unknown_rarity_defaults_to_common(self) -> None:
        """Cards not in rarity map are counted as common."""
        collection = Collection(cards={"Unknown Card": 4})
        features = extract_collection_features(collection, {})

        assert features.common_count == 4

    def test_unexpected_rarity_falls_back_to_common(self) -> None:
        """Cards with unexpected rarity values are counted as common."""
        collection = Collection(cards={"Special Card": 4})
        rarity_map = {"Special Card": "special"}  # Not a standard rarity

        features = extract_collection_features(collection, rarity_map)

        assert features.common_count == 4

    def test_to_dict(self) -> None:
        """Features convert to dictionary."""
        features = CollectionFeatures(
            total_cards=100,
            unique_cards=50,
            common_count=40,
            uncommon_count=30,
            rare_count=20,
            mythic_count=10,
        )

        result = features.to_dict()

        assert result["total_cards"] == 100
        assert result["unique_cards"] == 50
        assert result["common_count"] == 40
        assert result["uncommon_count"] == 30
        assert result["rare_count"] == 20
        assert result["mythic_count"] == 10


class TestExtractDeckFeatures:
    @pytest.fixture
    def sample_deck(self) -> MetaDeck:
        return MetaDeck(
            name="Mono-Red Aggro",
            archetype="aggro",
            format="standard",
            cards={"Lightning Bolt": 4, "Mountain": 20},
            sideboard={"Abrade": 2},
            win_rate=0.55,
            meta_share=0.15,
        )

    @pytest.fixture
    def sample_distance(self, sample_deck: MetaDeck) -> DeckDistance:
        return DeckDistance(
            deck=sample_deck,
            owned_cards=20,
            missing_cards=4,
            completion_percentage=0.83,
            wildcard_cost=WildcardCost(common=4),
            missing_card_list=[("Lightning Bolt", 4, "common")],
        )

    def test_extracts_deck_metadata(
        self, sample_deck: MetaDeck, sample_distance: DeckDistance
    ) -> None:
        """Extracts deck name, archetype, format."""
        features = extract_deck_features(sample_deck, sample_distance)

        assert features.deck_name == "Mono-Red Aggro"
        assert features.archetype == "aggro"
        assert features.format == "standard"

    def test_extracts_composition(
        self, sample_deck: MetaDeck, sample_distance: DeckDistance
    ) -> None:
        """Extracts deck composition features."""
        features = extract_deck_features(sample_deck, sample_distance)

        assert features.maindeck_size == 24
        assert features.sideboard_size == 2
        assert features.unique_cards == 3  # Lightning Bolt, Mountain, Abrade

    def test_extracts_meta_stats(
        self, sample_deck: MetaDeck, sample_distance: DeckDistance
    ) -> None:
        """Extracts win rate and meta share."""
        features = extract_deck_features(sample_deck, sample_distance)

        assert features.win_rate == pytest.approx(0.55)
        assert features.meta_share == pytest.approx(0.15)

    def test_extracts_distance_features(
        self, sample_deck: MetaDeck, sample_distance: DeckDistance
    ) -> None:
        """Extracts ownership and completion features."""
        features = extract_deck_features(sample_deck, sample_distance)

        assert features.owned_cards == 20
        assert features.missing_cards == 4
        assert features.completion_percentage == pytest.approx(0.83)

    def test_extracts_wildcard_costs(
        self, sample_deck: MetaDeck, sample_distance: DeckDistance
    ) -> None:
        """Extracts wildcard cost breakdown."""
        features = extract_deck_features(sample_deck, sample_distance)

        assert features.common_needed == 4
        assert features.uncommon_needed == 0
        assert features.rare_needed == 0
        assert features.mythic_needed == 0
        assert features.total_wildcards == 4

    def test_extracts_derived_features(
        self, sample_deck: MetaDeck, sample_distance: DeckDistance
    ) -> None:
        """Extracts can_build and archetype encoding."""
        features = extract_deck_features(sample_deck, sample_distance)

        assert features.can_build is False
        assert features.archetype_encoded == [1.0, 0.0, 0.0, 0.0]

    def test_handles_none_meta_stats(self) -> None:
        """Handles None win_rate and meta_share."""
        deck = MetaDeck(
            name="Test",
            archetype="control",
            format="standard",
            cards={"Island": 20},
        )
        distance = DeckDistance(
            deck=deck,
            owned_cards=20,
            missing_cards=0,
            completion_percentage=1.0,
            wildcard_cost=WildcardCost(),
            missing_card_list=[],
        )

        features = extract_deck_features(deck, distance)

        assert features.win_rate == 0.0
        assert features.meta_share == 0.0

    def test_to_dict(self, sample_deck: MetaDeck, sample_distance: DeckDistance) -> None:
        """Features convert to dictionary."""
        features = extract_deck_features(sample_deck, sample_distance)
        result = features.to_dict()

        assert result["deck_name"] == "Mono-Red Aggro"
        assert result["archetype"] == "aggro"
        assert result["can_build"] is False
        assert result["archetype_encoded"] == [1.0, 0.0, 0.0, 0.0]
