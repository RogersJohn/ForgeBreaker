"""Tests for canonical card resolution layer."""

import pytest

from forgebreaker.models.canonical_card import (
    CanonicalCard,
    CardMetadata,
    InventoryCard,
    OwnedCard,
    ResolvedCard,
)
from forgebreaker.models.failure import FailureKind, KnownError
from forgebreaker.services.canonical_card_resolver import (
    CanonicalCardResolver,
    ResolutionEvent,
    ResolutionReason,
    ResolutionReport,
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
    """Tests for CanonicalCard dataclass (identity only)."""

    def test_creation(self) -> None:
        """CanonicalCard can be created with identity fields only."""
        card = CanonicalCard(
            oracle_id="oracle-123",
            name="Lightning Bolt",
        )
        assert card.oracle_id == "oracle-123"
        assert card.name == "Lightning Bolt"

    def test_frozen(self) -> None:
        """CanonicalCard is immutable."""
        card = CanonicalCard(
            oracle_id="oracle-123",
            name="Test",
        )
        with pytest.raises(AttributeError):
            card.name = "Changed"  # type: ignore[misc]

    def test_slots(self) -> None:
        """CanonicalCard uses slots for memory efficiency."""
        card = CanonicalCard(oracle_id="oracle-123", name="Test")
        assert not hasattr(card, "__dict__")


class TestCardMetadataModel:
    """Tests for CardMetadata dataclass."""

    def test_creation(self) -> None:
        """CardMetadata can be created with semantic fields."""
        meta = CardMetadata(
            type_line="Instant",
            colors=("R",),
            legalities={"standard": "not_legal"},
        )
        assert meta.type_line == "Instant"
        assert meta.colors == ("R",)
        assert meta.legalities == {"standard": "not_legal"}

    def test_frozen(self) -> None:
        """CardMetadata is immutable."""
        meta = CardMetadata(type_line="Instant", colors=(), legalities={})
        with pytest.raises(AttributeError):
            meta.type_line = "Sorcery"  # type: ignore[misc]

    def test_colors_is_tuple(self) -> None:
        """colors field uses tuple for immutability."""
        meta = CardMetadata(type_line="Instant", colors=("W", "U"), legalities={})
        assert isinstance(meta.colors, tuple)


class TestResolvedCardModel:
    """Tests for ResolvedCard dataclass."""

    def test_creation(self) -> None:
        """ResolvedCard combines identity and metadata."""
        identity = CanonicalCard(oracle_id="oracle-123", name="Lightning Bolt")
        metadata = CardMetadata(type_line="Instant", colors=("R",), legalities={})
        resolved = ResolvedCard(identity=identity, metadata=metadata)

        assert resolved.identity == identity
        assert resolved.metadata == metadata
        assert resolved.arena_only is False  # Default

    def test_convenience_accessors(self) -> None:
        """ResolvedCard has convenience property accessors."""
        identity = CanonicalCard(oracle_id="oracle-123", name="Lightning Bolt")
        metadata = CardMetadata(
            type_line="Instant",
            colors=("R",),
            legalities={"standard": "not_legal"},
        )
        resolved = ResolvedCard(identity=identity, metadata=metadata)

        assert resolved.oracle_id == "oracle-123"
        assert resolved.name == "Lightning Bolt"
        assert resolved.type_line == "Instant"
        assert resolved.colors == ("R",)
        assert resolved.legalities == {"standard": "not_legal"}

    def test_arena_only_flag(self) -> None:
        """arena_only can be explicitly set."""
        identity = CanonicalCard(oracle_id="oracle-123", name="Arena Exclusive")
        metadata = CardMetadata(type_line="Creature", colors=(), legalities={})
        resolved = ResolvedCard(identity=identity, metadata=metadata, arena_only=True)

        assert resolved.arena_only is True

    def test_frozen(self) -> None:
        """ResolvedCard is immutable."""
        identity = CanonicalCard(oracle_id="oracle-123", name="Test")
        metadata = CardMetadata(type_line="Instant", colors=(), legalities={})
        resolved = ResolvedCard(identity=identity, metadata=metadata)

        with pytest.raises(AttributeError):
            resolved.arena_only = True  # type: ignore[misc]


class TestOwnedCardModel:
    """Tests for OwnedCard dataclass."""

    def test_creation(self) -> None:
        """OwnedCard pairs ResolvedCard with count."""
        identity = CanonicalCard(oracle_id="oracle-123", name="Lightning Bolt")
        metadata = CardMetadata(type_line="Instant", colors=("R",), legalities={})
        resolved = ResolvedCard(identity=identity, metadata=metadata)
        owned = OwnedCard(card=resolved, count=4)

        assert owned.card == resolved
        assert owned.count == 4

    def test_frozen(self) -> None:
        """OwnedCard is immutable."""
        identity = CanonicalCard(oracle_id="oracle-123", name="Test")
        metadata = CardMetadata(type_line="Instant", colors=(), legalities={})
        resolved = ResolvedCard(identity=identity, metadata=metadata)
        owned = OwnedCard(card=resolved, count=4)

        with pytest.raises(AttributeError):
            owned.count = 10  # type: ignore[misc]


# =============================================================================
# RESOLUTION REPORT TESTS
# =============================================================================


class TestResolutionReason:
    """Tests for ResolutionReason enum."""

    def test_success_reasons(self) -> None:
        """Success reason codes are strings."""
        assert ResolutionReason.RESOLVED.value == "resolved"
        assert ResolutionReason.NORMALIZED.value == "normalized"
        assert ResolutionReason.ARENA_FLAGGED.value == "arena_flagged"

    def test_failure_reasons(self) -> None:
        """Failure reason codes are strings."""
        assert ResolutionReason.NOT_FOUND.value == "not_found"
        assert ResolutionReason.NO_ORACLE_ID.value == "no_oracle_id"
        assert ResolutionReason.INVALID_DATA.value == "invalid_data"


class TestResolutionEvent:
    """Tests for ResolutionEvent dataclass."""

    def test_success_event(self) -> None:
        """ResolutionEvent captures successful resolution."""
        event = ResolutionEvent(
            input_name="Lightning Bolt",
            input_set_code="STA",
            input_count=4,
            reason=ResolutionReason.RESOLVED,
            output_oracle_id="oracle-bolt-123",
            output_name="Lightning Bolt",
        )
        assert event.reason == ResolutionReason.RESOLVED
        assert event.output_oracle_id == "oracle-bolt-123"

    def test_failure_event(self) -> None:
        """ResolutionEvent captures failed resolution."""
        event = ResolutionEvent(
            input_name="Fake Card",
            input_set_code="XXX",
            input_count=4,
            reason=ResolutionReason.NOT_FOUND,
        )
        assert event.reason == ResolutionReason.NOT_FOUND
        assert event.output_oracle_id is None

    def test_frozen(self) -> None:
        """ResolutionEvent is immutable."""
        event = ResolutionEvent(
            input_name="Test",
            input_set_code="DMU",
            input_count=1,
            reason=ResolutionReason.RESOLVED,
        )
        with pytest.raises(AttributeError):
            event.reason = ResolutionReason.NOT_FOUND  # type: ignore[misc]


class TestResolutionReport:
    """Tests for ResolutionReport dataclass."""

    def test_all_resolved_true_when_empty_rejected(self) -> None:
        """all_resolved is True when no rejected cards."""
        report = ResolutionReport(
            resolved=(),
            normalized=(),
            arena_flagged=(),
            rejected=(),
        )
        assert report.all_resolved is True

    def test_all_resolved_false_when_has_rejected(self) -> None:
        """all_resolved is False when rejected cards exist."""
        event = ResolutionEvent(
            input_name="Fake",
            input_set_code="XXX",
            input_count=1,
            reason=ResolutionReason.NOT_FOUND,
        )
        report = ResolutionReport(
            resolved=(),
            normalized=(),
            arena_flagged=(),
            rejected=(event,),
        )
        assert report.all_resolved is False

    def test_counts(self) -> None:
        """Report provides correct counts."""
        resolved_event = ResolutionEvent(
            input_name="Bolt",
            input_set_code="STA",
            input_count=4,
            reason=ResolutionReason.RESOLVED,
        )
        rejected_event = ResolutionEvent(
            input_name="Fake",
            input_set_code="XXX",
            input_count=1,
            reason=ResolutionReason.NOT_FOUND,
        )
        report = ResolutionReport(
            resolved=(resolved_event,),
            normalized=(),
            arena_flagged=(),
            rejected=(rejected_event,),
        )
        assert report.total_resolved == 1
        assert report.total_rejected == 1

    def test_get_rejected_names(self) -> None:
        """get_rejected_names returns card names."""
        events = [
            ResolutionEvent(
                input_name=f"Fake Card {i}",
                input_set_code="XXX",
                input_count=1,
                reason=ResolutionReason.NOT_FOUND,
            )
            for i in range(10)
        ]
        report = ResolutionReport(rejected=tuple(events))
        names = report.get_rejected_names(5)
        assert len(names) == 5
        assert names[0] == "Fake Card 0"


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
        """Unknown cards are tracked as rejected in report."""
        inventory = [InventoryCard(name="Fake Card", set_code="XXX", count=4)]
        result = resolver.resolve(inventory)

        assert not result.all_resolved
        assert result.report.total_rejected == 1
        assert result.report.rejected[0].input_name == "Fake Card"
        assert result.report.rejected[0].reason == ResolutionReason.NOT_FOUND

    def test_mixed_valid_invalid(self, resolver: CanonicalCardResolver) -> None:
        """Mix of valid and invalid cards tracked correctly."""
        inventory = [
            InventoryCard(name="Lightning Bolt", set_code="STA", count=4),
            InventoryCard(name="Fake Card", set_code="XXX", count=2),
        ]
        result = resolver.resolve(inventory)

        assert not result.all_resolved
        assert len(result.owned_cards) == 1
        assert result.report.total_rejected == 1

    def test_report_includes_resolved_events(self, resolver: CanonicalCardResolver) -> None:
        """Report includes events for resolved cards."""
        inventory = [InventoryCard(name="Lightning Bolt", set_code="STA", count=4)]
        result = resolver.resolve(inventory)

        assert result.report.total_resolved == 1
        event = result.report.resolved[0]
        assert event.input_name == "Lightning Bolt"
        assert event.reason == ResolutionReason.RESOLVED
        assert event.output_oracle_id == "oracle-bolt-123"


class TestArenaOnlyDetection:
    """Tests for arena_only flag detection."""

    def test_arena_only_when_set_not_in_scryfall(self, resolver: CanonicalCardResolver) -> None:
        """Cards with Arena-only set codes are flagged."""
        # Y24 is not in sample_card_db's known sets
        inventory = [InventoryCard(name="Lightning Bolt", set_code="Y24", count=4)]
        result = resolver.resolve(inventory)

        assert result.all_resolved
        assert result.owned_cards[0].card.arena_only is True
        assert result.report.total_arena_only == 1

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

    def test_arena_flagged_in_report(self, resolver: CanonicalCardResolver) -> None:
        """Arena-only cards appear in report's arena_flagged."""
        inventory = [InventoryCard(name="Lightning Bolt", set_code="Y24", count=4)]
        result = resolver.resolve(inventory)

        assert len(result.report.arena_flagged) == 1
        assert result.report.arena_flagged[0].reason == ResolutionReason.ARENA_FLAGGED


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


class TestResolveWithReport:
    """Tests for resolve_with_report method."""

    def test_returns_cards_and_report(self, resolver: CanonicalCardResolver) -> None:
        """resolve_with_report returns both owned cards and report."""
        inventory = [InventoryCard(name="Lightning Bolt", set_code="STA", count=4)]
        owned, report = resolver.resolve_with_report(inventory)

        assert len(owned) == 1
        assert report.total_resolved == 1
        assert report.all_resolved

    def test_raises_on_failure(self, resolver: CanonicalCardResolver) -> None:
        """resolve_with_report raises on any failure."""
        inventory = [InventoryCard(name="Fake Card", set_code="XXX", count=4)]

        with pytest.raises(KnownError) as exc_info:
            resolver.resolve_with_report(inventory)

        assert exc_info.value.kind == FailureKind.VALIDATION_FAILED


class TestResolutionResult:
    """Tests for ResolutionResult dataclass."""

    def test_all_resolved_delegates_to_report(self) -> None:
        """all_resolved delegates to report."""
        report = ResolutionReport(resolved=(), normalized=(), arena_flagged=(), rejected=())
        result = ResolutionResult(owned_cards=(), report=report)
        assert result.all_resolved is True


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

    def test_identity_metadata_separation(self, resolver: CanonicalCardResolver) -> None:
        """Identity and metadata are properly separated."""
        inventory = [InventoryCard(name="Lightning Bolt", set_code="STA", count=4)]
        result = resolver.resolve(inventory)

        card = result.owned_cards[0].card

        # Identity is separate
        assert card.identity.oracle_id == "oracle-bolt-123"
        assert card.identity.name == "Lightning Bolt"

        # Metadata is separate
        assert card.metadata.type_line == "Instant"
        assert card.metadata.colors == ("R",)
        assert card.metadata.legalities == {
            "standard": "not_legal",
            "historic": "legal",
            "modern": "legal",
        }
