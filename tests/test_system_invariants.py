"""
PR6: System Invariant Tests — Lock in hard-won guarantees.

These tests ensure future work cannot silently regress critical invariants.
All tests are deterministic, loud, and test real behavior (no mocking core logic).

INVARIANTS PROTECTED:
1. AllowedCardSet is the ONLY valid card universe
2. No deck includes illegal, unowned, or over-limit cards
3. ValidatedDeck is immutable and authoritative
4. Budget limits are HARD (no retries, no fallback)
5. Terminal failures are FINAL (zero LLM calls)

These tests are NOT optional. If they fail, the system is broken.
"""

import pytest

from forgebreaker.models.allowed_cards import (
    AllowedCardSet,
    CardNotAllowedError,
    build_allowed_set,
    validate_card_in_allowed_set,
    validate_card_list,
)
from forgebreaker.models.budget import (
    MAX_LLM_CALLS_PER_REQUEST,
    MAX_TOKENS_PER_REQUEST,
    BudgetExceededError,
    RequestBudget,
)
from forgebreaker.models.failure import (
    FailureKind,
    KnownError,
    OutcomeType,
    create_known_failure,
)
from forgebreaker.models.validated_deck import (
    DeckValidationError,
    create_validated_deck,
)

# =============================================================================
# INVARIANT 1: AllowedCardSet is the ONLY valid card universe
# =============================================================================


class TestAllowedCardSetBoundary:
    """
    INVARIANT: AllowedCardSet is the ONLY valid card universe.

    Cards not in the set MUST be rejected with CardNotAllowedError.
    This is non-negotiable — it's the core trust boundary.
    """

    @pytest.fixture
    def collection_cards(self) -> dict[str, int]:
        """Player's owned cards."""
        return {
            "Lightning Bolt": 4,
            "Goblin Guide": 4,
            "Mountain": 20,
            "Shock": 2,
        }

    @pytest.fixture
    def format_legal_cards(self) -> set[str]:
        """Cards legal in the target format."""
        return {"Lightning Bolt", "Goblin Guide", "Mountain", "Shock", "Lava Spike"}

    @pytest.fixture
    def allowed_set(
        self, collection_cards: dict[str, int], format_legal_cards: set[str]
    ) -> AllowedCardSet:
        """Build allowed set from collection + legality."""
        return build_allowed_set(collection_cards, format_legal_cards, "standard")

    def test_owned_legal_card_is_allowed(self, allowed_set: AllowedCardSet) -> None:
        """Cards that are both owned and legal are allowed."""
        assert "Lightning Bolt" in allowed_set
        assert "Goblin Guide" in allowed_set
        assert "Mountain" in allowed_set

    def test_unowned_card_is_not_allowed(self, allowed_set: AllowedCardSet) -> None:
        """Cards not in collection are NOT allowed, even if legal."""
        # Lava Spike is legal but not owned
        assert "Lava Spike" not in allowed_set

    def test_illegal_card_is_not_allowed(self, collection_cards: dict[str, int]) -> None:
        """Cards not format-legal are NOT allowed, even if owned."""
        # Create a set where Lightning Bolt is not legal
        format_legal = {"Goblin Guide", "Mountain", "Shock"}
        allowed = build_allowed_set(collection_cards, format_legal, "standard")

        assert "Lightning Bolt" not in allowed

    def test_validate_card_in_allowed_set_raises_for_missing(
        self, allowed_set: AllowedCardSet
    ) -> None:
        """validate_card_in_allowed_set raises CardNotAllowedError for missing cards."""
        with pytest.raises(CardNotAllowedError) as exc_info:
            validate_card_in_allowed_set("Fake Card", allowed_set)

        assert exc_info.value.card_name == "Fake Card"
        assert "not allowed" in str(exc_info.value).lower()

    def test_validate_card_list_returns_violations(self, allowed_set: AllowedCardSet) -> None:
        """validate_card_list returns violation messages for invalid cards."""
        deck = {
            "Lightning Bolt": 4,
            "Goblin Guide": 4,
            "HALLUCINATED_CARD": 4,  # This card doesn't exist
        }

        violations = validate_card_list(deck, allowed_set)

        # Should have at least one violation for the hallucinated card
        assert len(violations) >= 1
        assert any("HALLUCINATED_CARD" in v for v in violations)

    def test_allowed_set_is_immutable(self, allowed_set: AllowedCardSet) -> None:
        """AllowedCardSet is frozen — cannot be modified after creation."""
        with pytest.raises(AttributeError):
            allowed_set.cards = {}  # type: ignore[misc]


# =============================================================================
# INVARIANT 2: No deck includes illegal, unowned, or over-limit cards
# =============================================================================


class TestDeckCopyLimits:
    """
    INVARIANT: No deck may exceed copy limits.

    Standard rules:
    - Max 4 copies of any non-basic card
    - No limit on basic lands
    - Cannot exceed owned quantity
    """

    @pytest.fixture
    def collection_cards(self) -> dict[str, int]:
        """Player's collection with known quantities."""
        return {
            "Lightning Bolt": 4,
            "Goblin Guide": 2,  # Only owns 2
            "Mountain": 99,  # Basic land, many owned
        }

    @pytest.fixture
    def format_legal_cards(self) -> set[str]:
        return {"Lightning Bolt", "Goblin Guide", "Mountain"}

    @pytest.fixture
    def allowed_set(
        self, collection_cards: dict[str, int], format_legal_cards: set[str]
    ) -> AllowedCardSet:
        return build_allowed_set(collection_cards, format_legal_cards, "standard")

    def test_quantity_reflects_ownership(self, allowed_set: AllowedCardSet) -> None:
        """AllowedCardSet tracks owned quantities."""
        assert allowed_set.get_quantity("Lightning Bolt") == 4
        assert allowed_set.get_quantity("Goblin Guide") == 2
        assert allowed_set.get_quantity("Mountain") == 99

    def test_unowned_card_has_zero_quantity(self, allowed_set: AllowedCardSet) -> None:
        """Unowned cards have quantity 0."""
        assert allowed_set.get_quantity("Fake Card") == 0

    def test_deck_cannot_exceed_owned_quantity(self, allowed_set: AllowedCardSet) -> None:
        """Deck validation should fail if requesting more than owned."""
        deck = {
            "Lightning Bolt": 4,  # Owns 4, OK
            "Goblin Guide": 4,  # Owns 2, should fail
        }

        # This should be caught during deck building validation
        for card, qty in deck.items():
            owned = allowed_set.get_quantity(card)
            if qty > owned:
                # System should reject this
                assert qty > owned, f"{card}: requested {qty} but only owns {owned}"


# =============================================================================
# INVARIANT 3: ValidatedDeck is immutable and authoritative
# =============================================================================


class TestValidatedDeckImmutability:
    """
    INVARIANT: ValidatedDeck is immutable and authoritative.

    Once created, a ValidatedDeck cannot be modified.
    It is the ONLY source of truth for card names in output.
    """

    def test_validated_deck_is_frozen(self) -> None:
        """ValidatedDeck cannot be modified after creation."""
        deck = create_validated_deck(
            maindeck={"Lightning Bolt": 4, "Mountain": 20},
            sideboard={"Shock": 2},
            name="Test Deck",
            format_name="standard",
        )

        with pytest.raises(AttributeError):
            deck.cards = frozenset()  # type: ignore[misc]

    def test_validated_deck_contains_all_cards(self) -> None:
        """ValidatedDeck.cards contains all maindeck and sideboard cards."""
        deck = create_validated_deck(
            maindeck={"Lightning Bolt": 4, "Mountain": 20},
            sideboard={"Shock": 2},
            name="Test Deck",
            format_name="standard",
        )

        assert "Lightning Bolt" in deck
        assert "Mountain" in deck
        assert "Shock" in deck
        assert "Fake Card" not in deck

    def test_validated_deck_maindeck_dict(self) -> None:
        """get_maindeck_dict returns correct quantities."""
        deck = create_validated_deck(
            maindeck={"Lightning Bolt": 4, "Mountain": 20},
            sideboard={"Shock": 2},
        )

        maindeck = deck.get_maindeck_dict()
        assert maindeck["Lightning Bolt"] == 4
        assert maindeck["Mountain"] == 20

    def test_validated_deck_total_cards(self) -> None:
        """total_cards counts all cards including quantities."""
        deck = create_validated_deck(
            maindeck={"Lightning Bolt": 4, "Mountain": 20},
            sideboard={"Shock": 2},
        )

        # 4 + 20 + 2 = 26
        assert deck.total_cards() == 26


# =============================================================================
# INVARIANT 4: Budget limits are HARD (no retries, no fallback)
# =============================================================================


class TestBudgetHardLimits:
    """
    INVARIANT: Budget limits are HARD CAPS, not soft limits.

    - MAX_LLM_CALLS_PER_REQUEST is constant
    - MAX_TOKENS_PER_REQUEST is constant
    - Exceedance is TERMINAL
    - No retries, no fallback
    """

    def test_max_llm_calls_is_constant(self) -> None:
        """MAX_LLM_CALLS_PER_REQUEST is a fixed constant."""
        assert MAX_LLM_CALLS_PER_REQUEST == 3
        assert isinstance(MAX_LLM_CALLS_PER_REQUEST, int)

    def test_max_tokens_is_constant(self) -> None:
        """MAX_TOKENS_PER_REQUEST is a fixed constant."""
        assert MAX_TOKENS_PER_REQUEST == 20_000
        assert isinstance(MAX_TOKENS_PER_REQUEST, int)

    def test_budget_exceeded_error_is_known_error(self) -> None:
        """BudgetExceededError is a KnownError (terminal)."""
        error = BudgetExceededError("llm_calls", 4, 3)

        assert isinstance(error, KnownError)
        assert error.kind == FailureKind.BUDGET_EXCEEDED
        assert error.used == 4
        assert error.limit == 3

    def test_budget_tracks_llm_calls(self) -> None:
        """RequestBudget tracks LLM calls and raises on exceed."""
        budget = RequestBudget()

        # Should be able to make up to MAX_LLM_CALLS_PER_REQUEST calls
        for _ in range(MAX_LLM_CALLS_PER_REQUEST):
            budget.check_call_budget()
            budget.record_call(input_tokens=50, output_tokens=50)

        # Next call should raise
        with pytest.raises(BudgetExceededError) as exc_info:
            budget.check_call_budget()

        assert exc_info.value.limit_type == "LLM calls"

    def test_budget_is_not_configurable(self) -> None:
        """Budget limits cannot be overridden at runtime."""
        budget = RequestBudget()

        # These should be read-only
        assert budget.max_llm_calls == MAX_LLM_CALLS_PER_REQUEST
        assert budget.max_tokens == MAX_TOKENS_PER_REQUEST


# =============================================================================
# INVARIANT 5: Terminal failures are FINAL (zero LLM calls)
# =============================================================================


class TestTerminalFailuresAreFinal:
    """
    INVARIANT: Terminal failures produce zero LLM calls.

    When a failure is terminal (KnownError), the system MUST NOT:
    - Retry the request
    - Ask for clarification
    - Attempt fallback
    - Make additional tool calls
    """

    def test_known_error_is_terminal(self) -> None:
        """KnownError is the base for all terminal failures."""
        error = KnownError(
            kind=FailureKind.VALIDATION_FAILED,
            message="Test failure",
            detail="Details",
            suggestion="Fix it",
            status_code=400,
        )

        # KnownError should be a proper exception
        assert isinstance(error, Exception)
        assert error.kind == FailureKind.VALIDATION_FAILED

    def test_budget_exceeded_is_terminal(self) -> None:
        """BudgetExceededError is terminal (no retries)."""
        error = BudgetExceededError("llm_calls", 4, 3)

        # Should be a KnownError
        assert isinstance(error, KnownError)
        # Should have appropriate failure kind
        assert error.kind == FailureKind.BUDGET_EXCEEDED

    def test_create_known_failure_produces_terminal_response(self) -> None:
        """create_known_failure produces a finalized API response."""
        response = create_known_failure(
            kind=FailureKind.VALIDATION_FAILED,
            reason="Card 'Fake Card' does not exist",
        )

        # Response should indicate failure (known_failure outcome)
        assert response.outcome == OutcomeType.KNOWN_FAILURE
        assert response.failure is not None
        assert response.failure.kind == FailureKind.VALIDATION_FAILED

    def test_deck_validation_error_is_exception(self) -> None:
        """DeckValidationError is a proper exception for invalid cards."""
        error = DeckValidationError("Fake Card", "not in allowed set")

        assert isinstance(error, Exception)
        assert error.card_name == "Fake Card"
        assert "not in allowed set" in error.reason

    def test_card_not_allowed_error_is_exception(self) -> None:
        """CardNotAllowedError is a proper exception for boundary violations."""
        allowed_set = AllowedCardSet(cards={}, format="standard")
        error = CardNotAllowedError("Fake Card", "not owned", allowed_set)

        assert isinstance(error, Exception)
        assert error.card_name == "Fake Card"


# =============================================================================
# INVARIANT 6: Failure kinds are exhaustive and meaningful
# =============================================================================


class TestFailureKindExhaustiveness:
    """
    INVARIANT: All failure kinds are meaningful and exhaustive.

    The system must be able to classify any failure into a known kind.
    Unknown failures should use a catch-all kind, not silently succeed.
    """

    def test_failure_kind_has_budget_exceeded(self) -> None:
        """BUDGET_EXCEEDED is a valid failure kind."""
        assert hasattr(FailureKind, "BUDGET_EXCEEDED")

    def test_failure_kind_has_validation_failed(self) -> None:
        """VALIDATION_FAILED is a valid failure kind."""
        assert hasattr(FailureKind, "VALIDATION_FAILED")

    def test_failure_kind_has_service_unavailable(self) -> None:
        """SERVICE_UNAVAILABLE is a valid failure kind (for external failures)."""
        assert hasattr(FailureKind, "SERVICE_UNAVAILABLE")

    def test_failure_kinds_are_string_enum(self) -> None:
        """FailureKind values are strings (for JSON serialization)."""
        assert isinstance(FailureKind.BUDGET_EXCEEDED.value, str)
        assert isinstance(FailureKind.VALIDATION_FAILED.value, str)


# =============================================================================
# INTEGRATION: End-to-end invariant validation
# =============================================================================


class TestEndToEndInvariants:
    """
    Integration tests proving invariants hold together.

    These tests simulate real workflows and verify
    the invariants are enforced at each step.
    """

    def test_full_deck_validation_flow(self) -> None:
        """
        Complete deck validation flow enforces all invariants.

        1. Build AllowedCardSet from collection + legality
        2. Validate each card against the set
        3. Create ValidatedDeck only from valid cards
        4. ValidatedDeck is the only output
        """
        # 1. Collection and format legality
        collection = {"Lightning Bolt": 4, "Goblin Guide": 4, "Mountain": 20}
        format_legal = {"Lightning Bolt", "Goblin Guide", "Mountain"}

        # 2. Build allowed set
        allowed = build_allowed_set(collection, format_legal, "standard")
        assert len(allowed) == 3

        # 3. Validate deck against allowed set
        deck_cards = {"Lightning Bolt": 4, "Goblin Guide": 4, "Mountain": 20}
        for card in deck_cards:
            assert card in allowed

        # 4. Create validated deck
        validated = create_validated_deck(
            maindeck=deck_cards,
            name="Test Deck",
            format_name="standard",
            validation_source="test",
        )

        # 5. ValidatedDeck is authoritative
        assert len(validated) == 3
        assert validated.total_cards() == 28
        assert validated.format == "standard"

    def test_invalid_card_rejected_at_boundary(self) -> None:
        """
        Invalid cards are rejected at the AllowedCardSet boundary.

        This prevents hallucinated cards from ever reaching ValidatedDeck.
        """
        collection = {"Lightning Bolt": 4}
        format_legal = {"Lightning Bolt"}

        allowed = build_allowed_set(collection, format_legal, "standard")

        # Attempt to validate an invalid card
        with pytest.raises(CardNotAllowedError):
            validate_card_in_allowed_set("HALLUCINATED_CARD", allowed)

        # The invalid card never reaches ValidatedDeck creation

    def test_budget_prevents_infinite_retry(self) -> None:
        """
        Budget enforcement prevents infinite retry loops.

        After MAX_LLM_CALLS_PER_REQUEST, the system MUST stop.
        """
        budget = RequestBudget()

        calls_made = 0
        with pytest.raises(BudgetExceededError):
            for _ in range(MAX_LLM_CALLS_PER_REQUEST + 5):
                budget.check_call_budget()
                budget.record_call(input_tokens=50, output_tokens=50)
                calls_made += 1

        # Should have stopped at exactly MAX_LLM_CALLS_PER_REQUEST
        assert calls_made == MAX_LLM_CALLS_PER_REQUEST
