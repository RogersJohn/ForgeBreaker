"""
Tests for PR2: Oracle-Derived Legality Only.

INVARIANT: Format legality MUST come exclusively from CanonicalCard.legalities.
CSV set codes (e.g., "Y24", "FDN", "DFT") must NEVER influence legality decisions.

These tests exist to prevent regression - the system must always use oracle data.
"""

import pytest

from forgebreaker.filtering.candidate_pool import (
    _filter_by_format,
    build_candidate_pool,
)
from forgebreaker.models.canonical_card import InventoryCard
from forgebreaker.models.intent import DeckIntent, Format
from forgebreaker.services.canonical_card_resolver import CanonicalCardResolver

# =============================================================================
# TEST FIXTURES
# =============================================================================


@pytest.fixture
def card_db_with_legalities() -> dict:
    """
    Card database with explicit legality data.

    Key test cases:
    - Lightning Bolt: Historic-legal, NOT Standard-legal
    - Mountain: Standard-legal, Historic-legal
    - Arena Exclusive: Standard-legal (even though set "Y24" is Arena-only)
    """
    return {
        "Lightning Bolt": {
            "oracle_id": "oracle-bolt-123",
            "name": "Lightning Bolt",
            "type_line": "Instant",
            "colors": ["R"],
            "color_identity": ["R"],
            "set": "sta",
            "legalities": {
                "standard": "not_legal",
                "historic": "legal",
                "explorer": "legal",
                "modern": "legal",
            },
        },
        "Mountain": {
            "oracle_id": "oracle-mountain-456",
            "name": "Mountain",
            "type_line": "Basic Land — Mountain",
            "colors": [],
            "color_identity": [],
            "set": "dmu",
            "legalities": {
                "standard": "legal",
                "historic": "legal",
                "explorer": "legal",
                "modern": "legal",
            },
        },
        "Arena Exclusive Card": {
            "oracle_id": "oracle-arena-789",
            "name": "Arena Exclusive Card",
            "type_line": "Creature — Test",
            "colors": ["W"],
            "color_identity": ["W"],
            "set": "y24",  # Arena-only set
            "legalities": {
                "standard": "legal",  # STILL STANDARD-LEGAL per oracle
                "historic": "legal",
                "explorer": "legal",
            },
        },
        "FDN Set Card": {
            "oracle_id": "oracle-fdn-101",
            "name": "FDN Set Card",
            "type_line": "Sorcery",
            "colors": ["U"],
            "color_identity": ["U"],
            "set": "fdn",  # Foundations set
            "legalities": {
                "standard": "legal",
                "historic": "legal",
            },
        },
        "OM1 Set Card": {
            "oracle_id": "oracle-om1-102",
            "name": "OM1 Set Card",
            "type_line": "Enchantment",
            "colors": ["B"],
            "color_identity": ["B"],
            "set": "om1",  # Another special set
            "legalities": {
                "standard": "not_legal",
                "historic": "legal",
            },
        },
    }


@pytest.fixture
def resolver(card_db_with_legalities: dict) -> CanonicalCardResolver:
    """Resolver with test card database."""
    return CanonicalCardResolver(card_db_with_legalities)


# =============================================================================
# CORE INVARIANT TESTS: ORACLE-DERIVED LEGALITY
# =============================================================================


class TestOracleDerivedLegality:
    """
    Tests proving legality comes ONLY from oracle data.

    INVARIANT: CSV set codes must have ZERO effect on legality determination.
    """

    def test_standard_legality_from_oracle_not_set_code(
        self, card_db_with_legalities: dict
    ) -> None:
        """
        Standard legality is determined by oracle legalities field.

        Lightning Bolt is NOT Standard-legal per oracle, regardless of set.
        """
        intent = DeckIntent(format=Format.STANDARD)
        filtered = _filter_by_format(
            set(card_db_with_legalities.keys()), intent, card_db_with_legalities
        )

        # Lightning Bolt: NOT Standard-legal (oracle says so)
        assert "Lightning Bolt" not in filtered
        # Mountain: Standard-legal (oracle says so)
        assert "Mountain" in filtered

    def test_historic_legality_from_oracle_not_set_code(
        self, card_db_with_legalities: dict
    ) -> None:
        """
        Historic legality is determined by oracle legalities field.
        """
        intent = DeckIntent(format=Format.HISTORIC)
        filtered = _filter_by_format(
            set(card_db_with_legalities.keys()), intent, card_db_with_legalities
        )

        # Both Lightning Bolt and Mountain are Historic-legal per oracle
        assert "Lightning Bolt" in filtered
        assert "Mountain" in filtered


class TestArenaOnlyCardsRemainLegal:
    """
    Tests proving arena-only cards remain playable if oracle-legal.

    INVARIANT: arena_only flag must NOT exclude cards from format pools.
    """

    def test_arena_only_standard_legal_card_accepted(self, card_db_with_legalities: dict) -> None:
        """
        Arena-only cards with Standard legality MUST be accepted.

        The "Arena Exclusive Card" has set="y24" (Arena-only) but
        legalities["standard"]="legal" - it MUST pass Standard filter.
        """
        intent = DeckIntent(format=Format.STANDARD)
        filtered = _filter_by_format(
            set(card_db_with_legalities.keys()), intent, card_db_with_legalities
        )

        # Arena Exclusive Card: Standard-legal per oracle, even with Y24 set
        assert "Arena Exclusive Card" in filtered

    def test_arena_only_flag_does_not_affect_candidate_pool(
        self, resolver: CanonicalCardResolver
    ) -> None:
        """
        Arena-only flag is informational only, not a legality filter.

        Cards flagged arena_only=True must still appear in legal pools
        if their oracle legalities allow it.
        """
        # Import card from unknown set (not in card_db's known sets)
        # The resolver builds known_sets from the card_db, so use a set
        # that's NOT in the test fixture
        inventory = [
            InventoryCard(name="Arena Exclusive Card", set_code="ZZZ", count=4),
        ]
        result = resolver.resolve(inventory)

        assert result.all_resolved
        assert len(result.owned_cards) == 1

        owned = result.owned_cards[0]
        # Card is flagged as arena-only (set ZZZ not in known sets)
        assert owned.card.arena_only is True
        # But legalities are preserved from oracle - this is the key invariant
        assert owned.card.legalities["standard"] == "legal"
        assert owned.card.legalities["historic"] == "legal"


class TestSetCodeHasZeroEffectOnLegality:
    """
    Tests proving CSV set codes have ZERO effect on legality.

    INVARIANT: Same card from different sets has identical legality.
    """

    def test_same_card_different_sets_same_legality(self, resolver: CanonicalCardResolver) -> None:
        """
        Importing same card from different sets produces identical legality.

        Lightning Bolt from STA vs DMU vs any set = same legality data.
        """
        # Import from two different sets
        inventory = [
            InventoryCard(name="Lightning Bolt", set_code="STA", count=2),
            InventoryCard(name="Lightning Bolt", set_code="DMU", count=2),
        ]
        result = resolver.resolve(inventory)

        assert result.all_resolved
        # Consolidated to single card
        assert len(result.owned_cards) == 1

        owned = result.owned_cards[0]
        # Legality comes from oracle, not set
        assert owned.card.legalities["standard"] == "not_legal"
        assert owned.card.legalities["historic"] == "legal"

    def test_fdn_set_code_does_not_block_standard(self, card_db_with_legalities: dict) -> None:
        """
        FDN (Foundations) set code must NOT block Standard legality.

        If oracle says legal, the card is legal regardless of set.
        """
        intent = DeckIntent(format=Format.STANDARD)
        filtered = _filter_by_format(
            set(card_db_with_legalities.keys()), intent, card_db_with_legalities
        )

        # FDN Set Card: Standard-legal per oracle
        assert "FDN Set Card" in filtered

    def test_om1_set_code_does_not_grant_standard(self, card_db_with_legalities: dict) -> None:
        """
        OM1 set code must NOT grant Standard legality.

        If oracle says not_legal, the card is not legal regardless of set.
        """
        intent = DeckIntent(format=Format.STANDARD)
        filtered = _filter_by_format(
            set(card_db_with_legalities.keys()), intent, card_db_with_legalities
        )

        # OM1 Set Card: NOT Standard-legal per oracle
        assert "OM1 Set Card" not in filtered

    def test_historic_includes_om1_per_oracle(self, card_db_with_legalities: dict) -> None:
        """
        OM1 cards ARE Historic-legal if oracle says so.
        """
        intent = DeckIntent(format=Format.HISTORIC)
        filtered = _filter_by_format(
            set(card_db_with_legalities.keys()), intent, card_db_with_legalities
        )

        # OM1 Set Card: Historic-legal per oracle
        assert "OM1 Set Card" in filtered


class TestCandidatePoolUsesOracleLegality:
    """
    Tests proving build_candidate_pool uses oracle legality.
    """

    def test_build_candidate_pool_standard_format(self, card_db_with_legalities: dict) -> None:
        """
        build_candidate_pool respects oracle legalities for Standard.
        """
        intent = DeckIntent(format=Format.STANDARD)
        pool = build_candidate_pool(intent, card_db_with_legalities)

        # Standard-legal per oracle
        assert "Mountain" in pool
        assert "Arena Exclusive Card" in pool
        assert "FDN Set Card" in pool

        # NOT Standard-legal per oracle
        assert "Lightning Bolt" not in pool
        assert "OM1 Set Card" not in pool

    def test_build_candidate_pool_historic_format(self, card_db_with_legalities: dict) -> None:
        """
        build_candidate_pool respects oracle legalities for Historic.
        """
        intent = DeckIntent(format=Format.HISTORIC)
        pool = build_candidate_pool(intent, card_db_with_legalities)

        # All cards are Historic-legal per oracle
        assert "Mountain" in pool
        assert "Lightning Bolt" in pool
        assert "Arena Exclusive Card" in pool
        assert "FDN Set Card" in pool
        assert "OM1 Set Card" in pool


# =============================================================================
# REGRESSION PREVENTION TESTS
# =============================================================================


class TestNoSetCodeLegalityRegression:
    """
    Regression tests to prevent future set code legality bugs.

    These tests will FAIL if anyone adds set-code-based legality logic.
    """

    def test_legality_field_is_sole_source_of_truth(self) -> None:
        """
        The legalities dict is the ONLY field checked for format legality.

        This test documents the architectural constraint.
        """
        # Create a card with contradictory signals:
        # - Set code suggests "not Arena legal" (invalid set)
        # - Oracle legalities say "standard: legal"
        test_db = {
            "Test Card": {
                "oracle_id": "test-oracle",
                "name": "Test Card",
                "type_line": "Creature",
                "colors": [],
                "color_identity": [],
                "set": "xxx",  # Invalid/unknown set code
                "legalities": {
                    "standard": "legal",  # Oracle says LEGAL
                },
            }
        }

        intent = DeckIntent(format=Format.STANDARD)
        filtered = _filter_by_format(set(test_db.keys()), intent, test_db)

        # Oracle says legal, so card passes - set code is IGNORED
        assert "Test Card" in filtered

    def test_missing_set_field_does_not_affect_legality(self) -> None:
        """
        Cards without a set field still have correct legality.
        """
        test_db = {
            "No Set Card": {
                "oracle_id": "no-set-oracle",
                "name": "No Set Card",
                "type_line": "Instant",
                "colors": ["R"],
                "color_identity": ["R"],
                # NO "set" field at all
                "legalities": {
                    "standard": "legal",
                    "historic": "legal",
                },
            }
        }

        intent = DeckIntent(format=Format.STANDARD)
        filtered = _filter_by_format(set(test_db.keys()), intent, test_db)

        # Missing set field doesn't affect legality
        assert "No Set Card" in filtered
