"""
Canonical Card Resolution Service.

Resolves raw inventory cards to oracle-backed canonical cards.
This is the trust boundary for collection import.

INVARIANTS:
1. Resolution uses Scryfall data ONLY (no network)
2. Resolution failures are TERMINAL (KnownError)
3. Arena-only cards are FLAGGED, not excluded
4. Multiple printings consolidate to ONE canonical card (SUM counts)
5. All transformations are observable via ResolutionReport
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from forgebreaker.models.canonical_card import (
    CanonicalCard,
    CardMetadata,
    InventoryCard,
    OwnedCard,
    ResolvedCard,
)
from forgebreaker.models.failure import FailureKind, KnownError

# =============================================================================
# REASON CODES (not prose)
# =============================================================================


class ResolutionReason(str, Enum):
    """Reason codes for resolution outcomes."""

    # Success reasons
    RESOLVED = "resolved"
    NORMALIZED = "normalized"
    ARENA_FLAGGED = "arena_flagged"

    # Failure reasons
    NOT_FOUND = "not_found"
    NO_ORACLE_ID = "no_oracle_id"
    INVALID_DATA = "invalid_data"


# =============================================================================
# RESOLUTION EVENTS (diagnostic artifacts)
# =============================================================================


@dataclass(frozen=True, slots=True)
class ResolutionEvent:
    """
    A single card resolution event.

    Diagnostic artifact describing what happened to one card.
    Not user-facing text - structured for inspection.
    """

    input_name: str
    input_set_code: str
    input_count: int
    reason: ResolutionReason
    output_oracle_id: str | None = None
    output_name: str | None = None
    arena_only: bool = False


@dataclass(frozen=True)
class ResolutionReport:
    """
    Diagnostic report for a resolution operation.

    INVARIANT: This is a structured diagnostic artifact.
    It is NOT user-facing prose - it uses reason codes.

    Contains:
    - resolved: Successfully resolved card events
    - normalized: Cards where name was normalized (none currently, for future)
    - arena_flagged: Cards from Arena-specific sets
    - rejected: Cards that failed resolution with reason codes
    """

    resolved: tuple[ResolutionEvent, ...] = field(default_factory=tuple)
    normalized: tuple[ResolutionEvent, ...] = field(default_factory=tuple)
    arena_flagged: tuple[ResolutionEvent, ...] = field(default_factory=tuple)
    rejected: tuple[ResolutionEvent, ...] = field(default_factory=tuple)

    @property
    def total_resolved(self) -> int:
        """Count of successfully resolved cards."""
        return len(self.resolved)

    @property
    def total_rejected(self) -> int:
        """Count of rejected cards."""
        return len(self.rejected)

    @property
    def total_arena_only(self) -> int:
        """Count of arena-only flagged cards."""
        return len(self.arena_flagged)

    @property
    def all_resolved(self) -> bool:
        """True if no cards were rejected."""
        return len(self.rejected) == 0

    def get_rejected_names(self, limit: int = 5) -> list[str]:
        """Get rejected card names (for error messages)."""
        return [e.input_name for e in self.rejected[:limit]]


# =============================================================================
# RESOLUTION RESULT (owned cards + report)
# =============================================================================


@dataclass(frozen=True)
class ResolutionResult:
    """
    Complete result of resolving inventory to canonical cards.

    Contains both:
    - owned_cards: The resolved cards for downstream use
    - report: Diagnostic artifact describing transformations
    """

    owned_cards: tuple[OwnedCard, ...]
    report: ResolutionReport

    @property
    def all_resolved(self) -> bool:
        """True if all inventory cards resolved successfully."""
        return self.report.all_resolved


# =============================================================================
# RESOLVER
# =============================================================================


class CanonicalCardResolver:
    """
    Resolves InventoryCard -> ResolvedCard using Scryfall data.

    SECURITY CONTRACT:
    - Input: Untrusted InventoryCard list
    - Output: Trusted OwnedCard list + ResolutionReport OR terminal KnownError
    - No partial results on failure
    """

    def __init__(self, card_db: dict[str, dict[str, Any]]) -> None:
        """
        Initialize resolver with Scryfall card database.

        Args:
            card_db: Scryfall card database {name: card_data}
        """
        self._card_db = card_db
        # Build set of all known Scryfall set codes for arena_only detection
        self._known_sets = self._build_known_sets()

    def _build_known_sets(self) -> set[str]:
        """Extract all unique set codes from Scryfall database."""
        sets: set[str] = set()
        for card_data in self._card_db.values():
            set_code = card_data.get("set")
            if set_code:
                sets.add(str(set_code).lower())
        return sets

    def resolve(self, inventory: list[InventoryCard]) -> ResolutionResult:
        """
        Resolve inventory cards to canonical cards.

        Consolidates multiple printings of the same card by SUMMING counts.

        Args:
            inventory: List of raw inventory cards from Arena CSV

        Returns:
            ResolutionResult with resolved cards and diagnostic report
        """
        # Group by canonical name (consolidation)
        consolidated: dict[str, list[InventoryCard]] = {}
        for inv_card in inventory:
            if inv_card.name not in consolidated:
                consolidated[inv_card.name] = []
            consolidated[inv_card.name].append(inv_card)

        owned_cards: list[OwnedCard] = []
        resolved_events: list[ResolutionEvent] = []
        arena_flagged_events: list[ResolutionEvent] = []
        rejected_events: list[ResolutionEvent] = []

        for name, inv_cards in consolidated.items():
            # Try to resolve the canonical card
            result = self._resolve_single(name, inv_cards)

            if isinstance(result, tuple):
                owned_card, event = result
                owned_cards.append(owned_card)
                resolved_events.append(event)

                if owned_card.card.arena_only:
                    arena_flagged_events.append(event)
            else:
                # result is ResolutionEvent with failure reason
                rejected_events.append(result)

        report = ResolutionReport(
            resolved=tuple(resolved_events),
            normalized=(),  # No normalization currently
            arena_flagged=tuple(arena_flagged_events),
            rejected=tuple(rejected_events),
        )

        return ResolutionResult(
            owned_cards=tuple(owned_cards),
            report=report,
        )

    def _resolve_single(
        self,
        name: str,
        inv_cards: list[InventoryCard],
    ) -> tuple[OwnedCard, ResolutionEvent] | ResolutionEvent:
        """
        Resolve a single card name to a ResolvedCard.

        Returns (OwnedCard, ResolutionEvent) on success,
        or ResolutionEvent with failure reason on failure.
        """
        # Sum counts across all printings
        total_count = sum(inv.count for inv in inv_cards)
        # Use first card's set_code for reporting
        first_inv = inv_cards[0]

        card_data = self._card_db.get(name)
        if card_data is None:
            return ResolutionEvent(
                input_name=name,
                input_set_code=first_inv.set_code,
                input_count=total_count,
                reason=ResolutionReason.NOT_FOUND,
            )

        # Extract oracle_id
        oracle_id = card_data.get("oracle_id")
        if not oracle_id:
            return ResolutionEvent(
                input_name=name,
                input_set_code=first_inv.set_code,
                input_count=total_count,
                reason=ResolutionReason.NO_ORACLE_ID,
            )

        # Check if any set code is Arena-only (not in Scryfall)
        arena_only = False
        for inv_card in inv_cards:
            set_code = inv_card.set_code.lower() if inv_card.set_code else ""
            if set_code and set_code not in self._known_sets:
                arena_only = True
                break

        # Build identity
        identity = CanonicalCard(
            oracle_id=str(oracle_id),
            name=name,
        )

        # Build metadata
        metadata = CardMetadata(
            type_line=str(card_data.get("type_line", "")),
            colors=tuple(card_data.get("colors", [])),
            legalities=dict(card_data.get("legalities", {})),
        )

        # Build resolved card
        resolved = ResolvedCard(
            identity=identity,
            metadata=metadata,
            arena_only=arena_only,
        )

        owned = OwnedCard(card=resolved, count=total_count)

        event = ResolutionEvent(
            input_name=name,
            input_set_code=first_inv.set_code,
            input_count=total_count,
            reason=ResolutionReason.ARENA_FLAGGED if arena_only else ResolutionReason.RESOLVED,
            output_oracle_id=identity.oracle_id,
            output_name=identity.name,
            arena_only=arena_only,
        )

        return (owned, event)

    def resolve_or_fail(self, inventory: list[InventoryCard]) -> list[OwnedCard]:
        """
        Resolve inventory cards, raising terminal error on ANY failure.

        This is the primary entry point for collection import.

        Args:
            inventory: List of raw inventory cards

        Returns:
            List of owned cards (all successfully resolved)

        Raises:
            KnownError: If any card fails resolution (terminal, zero LLM calls)
        """
        result = self.resolve(inventory)

        if not result.all_resolved:
            # Build detailed failure message using reason codes
            failed_names = result.report.get_rejected_names(5)
            detail = f"Failed cards: {', '.join(failed_names)}"
            if result.report.total_rejected > 5:
                detail += f" (and {result.report.total_rejected - 5} more)"

            raise KnownError(
                kind=FailureKind.VALIDATION_FAILED,
                message="Collection import failed: some cards could not be resolved.",
                detail=detail,
                suggestion="Check that card names match exactly. Re-export from Arena if needed.",
                status_code=400,
            )

        return list(result.owned_cards)

    def resolve_with_report(
        self, inventory: list[InventoryCard]
    ) -> tuple[list[OwnedCard], ResolutionReport]:
        """
        Resolve inventory cards, returning both cards and diagnostic report.

        Terminal failure on any unresolved card.

        Args:
            inventory: List of raw inventory cards

        Returns:
            Tuple of (owned_cards, report)

        Raises:
            KnownError: If any card fails resolution (terminal)
        """
        result = self.resolve(inventory)

        if not result.all_resolved:
            failed_names = result.report.get_rejected_names(5)
            detail = f"Failed cards: {', '.join(failed_names)}"
            if result.report.total_rejected > 5:
                detail += f" (and {result.report.total_rejected - 5} more)"

            raise KnownError(
                kind=FailureKind.VALIDATION_FAILED,
                message="Collection import failed: some cards could not be resolved.",
                detail=detail,
                suggestion="Check that card names match exactly. Re-export from Arena if needed.",
                status_code=400,
            )

        return list(result.owned_cards), result.report
