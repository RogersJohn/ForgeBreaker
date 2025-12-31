"""Tests for canonical card resolution layer."""

import pytest

from forgebreaker.models.canonical_card import CanonicalCard, InventoryCard, OwnedCard
from forgebreaker.models.failure import FailureKind, KnownError
from forgebreaker.services.canonical_card_resolver import (
    CanonicalCardResolver,
    ResolutionResult,
)

# =============================================================================
# TEST FIXTURES
# =============================================================================


@pytest.fixture
def sample_card_db() -> dict:
    """Scryfall-like card database for testing."""
    return {
        "Lightning Bolt": {
            "oracle_id": "oracle-bolt-123",
            "name": "Lightning Bolt",
            "type_line": "Instant",
            "colors": ["R"],
            "set": "sta",
            "legalities": {"standard": "not_legal", "historic": "legal", "modern": "legal"},
        },
        "Mountain": {
            "oracle_id": "oracle-mountain-456",
            "name": "Mountain",
            "type_line": "Basic Land — Mountain",
            "colors": [],
            "set": "dmu",
            "legalities": {"standard": "legal", "historic": "legal", "modern": "legal"},
        },
        "Counterspell": {
            "oracle_id": "oracle-counter-789",
            "name": "Counterspell",
            "type_line": "Instant",
            "colors": ["U"],
            "set": "sta",
            "legalities": {"standard": "not_legal", "historic": "legal", "modern": "legal"},
        },
    }


@pytest.fixture
def resolver(sample_card_db: dict) -> CanonicalCardResolver:
    """Pre-configured resolver with sample card database."""
    return CanonicalCardResolver(sample_card_db)


# =============================================================================
# MODEL TESTS
# =============================================================================


class TestInventoryCardModel:
    """Tests for InventoryCard dataclass."""

    def test_creation(self) -> None:
        """InventoryCard can be created with required fields."""
        inv = InventoryCard(name="Lightning Bolt", set_code="STA", count=4)
        assert inv.name == "Lightning Bolt"
        assert inv.set_code == "STA"
        assert inv.count == 4
        assert inv.collector_number is None

    def test_with_collector_number(self) -> None:
        """InventoryCard can include collector number."""
        inv = InventoryCard(
            name="Lightning Bolt",
            set_code="STA",
            count=4,
            collector_number="123a",
        )
        assert inv.collector_number == "123a"

    def test_frozen(self) -> None:
        """InventoryCard is immutable."""
        inv = InventoryCard(name="Test", set_code="DMU", count=4)
        with pytest.raises(AttributeError):
            inv.name = "Changed"  # type: ignore[misc]

    def test_slots(self) -> None:
        """InventoryCard uses slots for memory efficiency."""
        inv = InventoryCard(name="Test", set_code="DMU", count=4)
        assert not hasattr(inv, "__dict__")


class TestCanonicalCardModel:
    """Tests for CanonicalCard dataclass."""

    def test_creation(self) -> None:
        """CanonicalCard can be created with required fields."""
        card = CanonicalCard(
            oracle_id="oracle-123",
            name="Lightning Bolt",
            type_line="Instant",
            colors=("R",),
            legalities={"standard": "not_legal"},
        )
        assert card.oracle_id == "oracle-123"
        assert card.name == "Lightning Bolt"
        assert card.type_line == "Instant"
        assert card.colors == ("R",)
        assert card.legalities == {"standard": "not_legal"}
        assert card.arena_only is False  # Default

    def test_arena_only_flag(self) -> None:
        """arena_only can be explicitly set."""
        card = CanonicalCard(
            oracle_id="oracle-123",
            name="Arena Exclusive",
            type_line="Creature",
            colors=(),
            legalities={},
            arena_only=True,
        )
        assert card.arena_only is True

    def test_frozen(self) -> None:
        """CanonicalCard is immutable."""
        card = CanonicalCard(
            oracle_id="oracle-123",
            name="Test",
            type_line="Instant",
            colors=(),
            legalities={},
        )
        with pytest.raises(AttributeError):
            card.name = "Changed"  # type: ignore[misc]

    def test_colors_is_tuple(self) -> None:
        """colors field uses tuple for immutability."""
        card = CanonicalCard(
            oracle_id="oracle-123",
            name="Test",
            type_line="Instant",
            colors=("W", "U"),
            legalities={},
        )
        assert isinstance(card.colors, tuple)


class TestCanonicalCardIdentity:
    """
    Tests for oracle_id-based identity.

    INVARIANT: CanonicalCard identity is oracle_id ONLY.
    Two cards with same oracle_id are equal, regardless of other fields.
    This handles split cards, adventures, MDFCs, rebalanced cards.
    """

    def test_equality_based_on_oracle_id(self) -> None:
        """Two CanonicalCards with same oracle_id are equal."""
        card1 = CanonicalCard(
            oracle_id="oracle-123",
            name="Lightning Bolt",
            type_line="Instant",
            colors=("R",),
            legalities={"standard": "legal"},
        )
        card2 = CanonicalCard(
            oracle_id="oracle-123",
            name="Lightning Bolt (Variant)",  # Different name
            type_line="Instant - Rebalanced",  # Different type
            colors=("R", "W"),  # Different colors
            legalities={"standard": "not_legal"},  # Different legalities
        )
        assert card1 == card2

    def test_inequality_based_on_oracle_id(self) -> None:
        """Two CanonicalCards with different oracle_id are not equal."""
        card1 = CanonicalCard(
            oracle_id="oracle-123",
            name="Lightning Bolt",
            type_line="Instant",
            colors=("R",),
            legalities={},
        )
        card2 = CanonicalCard(
            oracle_id="oracle-456",
            name="Lightning Bolt",  # Same name!
            type_line="Instant",
            colors=("R",),
            legalities={},
        )
        assert card1 != card2

    def test_hash_based_on_oracle_id(self) -> None:
        """Hash is consistent with oracle_id-based equality."""
        card1 = CanonicalCard(
            oracle_id="oracle-123",
            name="Lightning Bolt",
            type_line="Instant",
            colors=("R",),
            legalities={},
        )
        card2 = CanonicalCard(
            oracle_id="oracle-123",
            name="Different Name",  # Different name, same oracle
            type_line="Different Type",
            colors=("U",),
            legalities={"modern": "legal"},
        )
        assert hash(card1) == hash(card2)

    def test_set_deduplication_by_oracle_id(self) -> None:
        """CanonicalCards deduplicate correctly in sets."""
        card1 = CanonicalCard(
            oracle_id="oracle-123",
            name="Version A",
            type_line="Type A",
            colors=(),
            legalities={},
        )
        card2 = CanonicalCard(
            oracle_id="oracle-123",  # Same oracle
            name="Version B",
            type_line="Type B",
            colors=(),
            legalities={},
        )
        card3 = CanonicalCard(
            oracle_id="oracle-456",  # Different oracle
            name="Version A",  # Same name as card1
            type_line="Type A",
            colors=(),
            legalities={},
        )
        card_set = {card1, card2, card3}
        assert len(card_set) == 2  # card1 and card2 dedupe

    def test_dict_key_by_oracle_id(self) -> None:
        """CanonicalCards work as dict keys based on oracle_id."""
        card1 = CanonicalCard(
            oracle_id="oracle-123",
            name="Name A",
            type_line="Type",
            colors=(),
            legalities={},
        )
        card2 = CanonicalCard(
            oracle_id="oracle-123",  # Same oracle
            name="Name B",
            type_line="Type",
            colors=(),
            legalities={},
        )
        card_dict: dict[CanonicalCard, int] = {card1: 100}
        # card2 should access same entry
        assert card_dict[card2] == 100
        card_dict[card2] = 200
        assert card_dict[card1] == 200
        assert len(card_dict) == 1

    def test_not_equal_to_non_card(self) -> None:
        """CanonicalCard is not equal to non-card objects."""
        card = CanonicalCard(
            oracle_id="oracle-123",
            name="Test",
            type_line="Instant",
            colors=(),
            legalities={},
        )
        assert card != "oracle-123"
        assert card != 123
        assert card != {"oracle_id": "oracle-123"}


class TestOwnedCardModel:
    """Tests for OwnedCard dataclass."""

    def test_creation(self) -> None:
        """OwnedCard pairs CanonicalCard with count."""
        canonical = CanonicalCard(
            oracle_id="oracle-123",
            name="Lightning Bolt",
            type_line="Instant",
            colors=("R",),
            legalities={},
        )
        owned = OwnedCard(card=canonical, count=4)
        assert owned.card == canonical
        assert owned.count == 4

    def test_frozen(self) -> None:
        """OwnedCard is immutable."""
        canonical = CanonicalCard(
            oracle_id="oracle-123",
            name="Test",
            type_line="Instant",
            colors=(),
            legalities={},
        )
        owned = OwnedCard(card=canonical, count=4)
        with pytest.raises(AttributeError):
            owned.count = 10  # type: ignore[misc]


# =============================================================================
# RESOLVER TESTS
# =============================================================================


class TestCanonicalCardResolver:
    """Tests for CanonicalCardResolver resolution logic."""

    def test_resolve_single_card(self, resolver: CanonicalCardResolver) -> None:
        """Single card resolves correctly."""
        inventory = [InventoryCard(name="Lightning Bolt", set_code="STA", count=4)]
        result = resolver.resolve(inventory)

        assert result.all_resolved
        assert len(result.owned_cards) == 1
        assert result.owned_cards[0].card.name == "Lightning Bolt"
        assert result.owned_cards[0].card.oracle_id == "oracle-bolt-123"
        assert result.owned_cards[0].count == 4

    def test_resolve_multiple_cards(self, resolver: CanonicalCardResolver) -> None:
        """Multiple different cards resolve correctly."""
        inventory = [
            InventoryCard(name="Lightning Bolt", set_code="STA", count=4),
            InventoryCard(name="Mountain", set_code="DMU", count=20),
        ]
        result = resolver.resolve(inventory)

        assert result.all_resolved
        assert len(result.owned_cards) == 2

    def test_consolidates_by_sum(self, resolver: CanonicalCardResolver) -> None:
        """
        BEHAVIOR CHANGE: Multiple printings SUM counts.

        Previous: max(4, 3) = 4
        New:      sum(4, 3) = 7
        """
        inventory = [
            InventoryCard(name="Lightning Bolt", set_code="STA", count=4),
            InventoryCard(name="Lightning Bolt", set_code="DMU", count=3),
        ]
        result = resolver.resolve(inventory)

        assert result.all_resolved
        assert len(result.owned_cards) == 1
        assert result.owned_cards[0].count == 7  # SUM, not MAX

    def test_consolidates_three_printings(self, resolver: CanonicalCardResolver) -> None:
        """Three printings of same card sum to total."""
        inventory = [
            InventoryCard(name="Lightning Bolt", set_code="STA", count=2),
            InventoryCard(name="Lightning Bolt", set_code="LEA", count=1),
            InventoryCard(name="Lightning Bolt", set_code="DMU", count=4),
        ]
        result = resolver.resolve(inventory)

        assert result.all_resolved
        assert len(result.owned_cards) == 1
        assert result.owned_cards[0].count == 7  # 2 + 1 + 4

    def test_unresolved_card_tracked(self, resolver: CanonicalCardResolver) -> None:
        """Unknown cards are tracked as unresolved."""
        inventory = [InventoryCard(name="Fake Card", set_code="XXX", count=4)]
        result = resolver.resolve(inventory)

        assert not result.all_resolved
        assert len(result.unresolved) == 1
        assert result.unresolved[0][0].name == "Fake Card"
        assert "not found" in result.unresolved[0][1].lower()

    def test_consolidates_by_oracle_id_not_name(self) -> None:
        """
        CRITICAL: Consolidation is by oracle_id, not name.

        This handles split cards, adventures, MDFCs, rebalanced cards.
        Example: "Fire // Ice" and "Fire" might resolve to same oracle_id.
        """
        # Card DB with two names mapping to same oracle_id
        card_db = {
            "Fire // Ice": {
                "oracle_id": "oracle-fire-ice",
                "name": "Fire // Ice",
                "type_line": "Instant // Instant",
                "colors": ["R", "U"],
                "set": "mh2",
                "legalities": {"modern": "legal"},
            },
            "Fire": {
                "oracle_id": "oracle-fire-ice",  # Same oracle_id!
                "name": "Fire",
                "type_line": "Instant",
                "colors": ["R"],
                "set": "mh2",
                "legalities": {"modern": "legal"},
            },
        }
        resolver = CanonicalCardResolver(card_db)

        inventory = [
            InventoryCard(name="Fire // Ice", set_code="MH2", count=4),
            InventoryCard(name="Fire", set_code="MH2", count=2),  # Different name!
        ]
        result = resolver.resolve(inventory)

        assert result.all_resolved
        # Should consolidate to ONE card (same oracle_id)
        assert len(result.owned_cards) == 1
        assert result.owned_cards[0].count == 6  # 4 + 2

    def test_mixed_valid_invalid(self, resolver: CanonicalCardResolver) -> None:
        """Mix of valid and invalid cards tracked correctly."""
        inventory = [
            InventoryCard(name="Lightning Bolt", set_code="STA", count=4),
            InventoryCard(name="Fake Card", set_code="XXX", count=2),
        ]
        result = resolver.resolve(inventory)

        assert not result.all_resolved
        assert len(result.owned_cards) == 1
        assert len(result.unresolved) == 1


class TestArenaOnlyDetection:
    """Tests for arena_only flag detection."""

    def test_arena_only_when_set_not_in_scryfall(self, resolver: CanonicalCardResolver) -> None:
        """Cards with Arena-only set codes are flagged."""
        # Y24 is not in sample_card_db's known sets
        inventory = [InventoryCard(name="Lightning Bolt", set_code="Y24", count=4)]
        result = resolver.resolve(inventory)

        assert result.all_resolved
        assert result.owned_cards[0].card.arena_only is True
        assert result.arena_only_count == 1

    def test_not_arena_only_when_set_in_scryfall(self, resolver: CanonicalCardResolver) -> None:
        """Cards with known set codes are not flagged."""
        # STA is in sample_card_db
        inventory = [InventoryCard(name="Lightning Bolt", set_code="STA", count=4)]
        result = resolver.resolve(inventory)

        assert result.all_resolved
        assert result.owned_cards[0].card.arena_only is False

    def test_arena_only_cards_not_excluded(self, resolver: CanonicalCardResolver) -> None:
        """Arena-only cards are included, just flagged."""
        inventory = [InventoryCard(name="Lightning Bolt", set_code="Y24", count=4)]
        result = resolver.resolve(inventory)

        assert result.all_resolved
        assert len(result.owned_cards) == 1

    def test_empty_set_code_not_arena_only(self, resolver: CanonicalCardResolver) -> None:
        """Empty set code (non-Arena format) not flagged as arena-only."""
        inventory = [InventoryCard(name="Lightning Bolt", set_code="", count=4)]
        result = resolver.resolve(inventory)

        assert result.all_resolved
        assert result.owned_cards[0].card.arena_only is False


class TestResolveOrFail:
    """Tests for terminal failure behavior."""

    def test_success_returns_owned_cards(self, resolver: CanonicalCardResolver) -> None:
        """resolve_or_fail returns list on success."""
        inventory = [InventoryCard(name="Lightning Bolt", set_code="STA", count=4)]
        owned = resolver.resolve_or_fail(inventory)

        assert len(owned) == 1
        assert owned[0].card.name == "Lightning Bolt"

    def test_raises_on_any_failure(self, resolver: CanonicalCardResolver) -> None:
        """resolve_or_fail raises KnownError on ANY unresolved card."""
        inventory = [
            InventoryCard(name="Lightning Bolt", set_code="STA", count=4),
            InventoryCard(name="Fake Card", set_code="XXX", count=2),
        ]

        with pytest.raises(KnownError) as exc_info:
            resolver.resolve_or_fail(inventory)

        assert exc_info.value.kind == FailureKind.VALIDATION_FAILED
        assert "Fake Card" in str(exc_info.value.detail)

    def test_error_is_terminal(self, resolver: CanonicalCardResolver) -> None:
        """Resolution failure is terminal (correct error properties)."""
        inventory = [InventoryCard(name="Fake Card", set_code="XXX", count=4)]

        with pytest.raises(KnownError) as exc_info:
            resolver.resolve_or_fail(inventory)

        error = exc_info.value
        assert error.kind == FailureKind.VALIDATION_FAILED
        assert error.status_code == 400
        assert error.suggestion is not None

    def test_error_message_truncates_long_lists(self, resolver: CanonicalCardResolver) -> None:
        """Error message truncates when many cards fail."""
        inventory = [
            InventoryCard(name=f"Fake Card {i}", set_code="XXX", count=1) for i in range(10)
        ]

        with pytest.raises(KnownError) as exc_info:
            resolver.resolve_or_fail(inventory)

        # Should show first 5 + "and X more"
        detail = exc_info.value.detail
        assert detail is not None
        assert "and 5 more" in detail


class TestResolutionResult:
    """Tests for ResolutionResult dataclass."""

    def test_all_resolved_true_when_empty_unresolved(self) -> None:
        """all_resolved is True when no unresolved cards."""
        result = ResolutionResult(
            owned_cards=[],
            unresolved=[],
            arena_only_count=0,
        )
        assert result.all_resolved is True

    def test_all_resolved_false_when_has_unresolved(self) -> None:
        """all_resolved is False when unresolved cards exist."""
        inv = InventoryCard(name="Fake", set_code="XXX", count=1)
        result = ResolutionResult(
            owned_cards=[],
            unresolved=[(inv, "not found")],
            arena_only_count=0,
        )
        assert result.all_resolved is False


# =============================================================================
# INTEGRATION TESTS
# =============================================================================


class TestEndToEndResolution:
    """Integration tests for complete resolution flow."""

    def test_realistic_collection_import(self, resolver: CanonicalCardResolver) -> None:
        """Realistic collection with multiple cards and printings."""
        inventory = [
            InventoryCard(name="Lightning Bolt", set_code="STA", count=4),
            InventoryCard(name="Lightning Bolt", set_code="LEA", count=1),  # Different print
            InventoryCard(name="Mountain", set_code="DMU", count=20),
            InventoryCard(name="Counterspell", set_code="STA", count=4),
        ]
        result = resolver.resolve(inventory)

        assert result.all_resolved
        assert len(result.owned_cards) == 3  # 3 unique cards

        # Find Lightning Bolt - should have summed count
        bolt = next(oc for oc in result.owned_cards if oc.card.name == "Lightning Bolt")
        assert bolt.count == 5  # 4 + 1

    def test_canonical_data_preserved(self, resolver: CanonicalCardResolver) -> None:
        """Oracle data is correctly extracted."""
        inventory = [InventoryCard(name="Lightning Bolt", set_code="STA", count=4)]
        result = resolver.resolve(inventory)

        card = result.owned_cards[0].card
        assert card.oracle_id == "oracle-bolt-123"
        assert card.type_line == "Instant"
        assert card.colors == ("R",)
        assert "historic" in card.legalities
