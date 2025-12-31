"""
Canonical Card Resolution Service.

Resolves raw inventory cards to oracle-backed canonical cards.
This is the trust boundary for collection import.

INVARIANTS:
1. Resolution uses Scryfall data ONLY (no network)
2. Resolution failures are TERMINAL (KnownError)
3. Arena-only cards are FLAGGED, not excluded
4. Multiple printings consolidate to ONE canonical card (SUM counts)
"""

from dataclasses import dataclass
from typing import Any

from forgebreaker.models.canonical_card import CanonicalCard, InventoryCard, OwnedCard
from forgebreaker.models.failure import FailureKind, KnownError


@dataclass
class ResolutionResult:
    """Result of resolving inventory to canonical cards."""

    owned_cards: list[OwnedCard]
    """Successfully resolved cards with summed counts."""

    unresolved: list[tuple[InventoryCard, str]]
    """Cards that failed resolution with reason."""

    arena_only_count: int
    """Count of cards flagged as arena-only."""

    @property
    def all_resolved(self) -> bool:
        """True if all inventory cards resolved successfully."""
        return len(self.unresolved) == 0


class CanonicalCardResolver:
    """
    Resolves InventoryCard -> CanonicalCard using Scryfall data.

    SECURITY CONTRACT:
    - Input: Untrusted InventoryCard list
    - Output: Trusted OwnedCard list OR terminal KnownError
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

        Consolidates by ORACLE_ID (not name) - handles split cards, adventures,
        MDFCs, and rebalanced cards correctly.

        Args:
            inventory: List of raw inventory cards from Arena CSV

        Returns:
            ResolutionResult with resolved cards and any failures
        """
        # Phase 1: Resolve each inventory card individually
        resolved_by_oracle: dict[str, tuple[CanonicalCard, int, bool]] = {}
        unresolved: list[tuple[InventoryCard, str]] = []

        for inv_card in inventory:
            result = self._resolve_single_card(inv_card)

            if isinstance(result, tuple):
                canonical, arena_only_flag = result
                oracle_id = canonical.oracle_id

                # Consolidate by oracle_id (SUM counts)
                if oracle_id in resolved_by_oracle:
                    existing_card, existing_count, existing_arena = resolved_by_oracle[oracle_id]
                    resolved_by_oracle[oracle_id] = (
                        existing_card,
                        existing_count + inv_card.count,
                        existing_arena or arena_only_flag,
                    )
                else:
                    resolved_by_oracle[oracle_id] = (
                        canonical,
                        inv_card.count,
                        arena_only_flag,
                    )
            else:
                # result is error reason string
                unresolved.append((inv_card, result))

        # Phase 2: Build owned cards with arena_only flag applied
        owned_cards: list[OwnedCard] = []
        arena_only_count = 0

        for canonical, count, arena_only in resolved_by_oracle.values():
            # Apply arena_only flag if any printing was arena-only
            if arena_only and not canonical.arena_only:
                canonical = CanonicalCard(
                    oracle_id=canonical.oracle_id,
                    name=canonical.name,
                    type_line=canonical.type_line,
                    colors=canonical.colors,
                    legalities=canonical.legalities,
                    arena_only=True,
                )
            owned_cards.append(OwnedCard(card=canonical, count=count))
            if canonical.arena_only:
                arena_only_count += 1

        return ResolutionResult(
            owned_cards=owned_cards,
            unresolved=unresolved,
            arena_only_count=arena_only_count,
        )

    def _resolve_single_card(
        self,
        inv_card: InventoryCard,
    ) -> tuple[CanonicalCard, bool] | str:
        """
        Resolve a single InventoryCard to a CanonicalCard.

        Returns (CanonicalCard, arena_only_flag) on success, error string on failure.
        """
        card_data = self._card_db.get(inv_card.name)
        if card_data is None:
            return "Card not found in Scryfall database"

        # Extract oracle_id - this is the identity key
        oracle_id = card_data.get("oracle_id")
        if not oracle_id:
            return "No oracle_id in Scryfall data"

        # Check if this specific printing is Arena-only
        set_code = inv_card.set_code.lower() if inv_card.set_code else ""
        arena_only = bool(set_code and set_code not in self._known_sets)

        # Build canonical card (arena_only=False initially, applied in consolidation)
        canonical = CanonicalCard(
            oracle_id=str(oracle_id),
            name=inv_card.name,
            type_line=str(card_data.get("type_line", "")),
            colors=tuple(card_data.get("colors", [])),
            legalities=dict(card_data.get("legalities", {})),
            arena_only=False,
        )

        return (canonical, arena_only)

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
            # Build detailed failure message
            failed_names = [inv.name for inv, _ in result.unresolved[:5]]
            detail = f"Failed cards: {', '.join(failed_names)}"
            if len(result.unresolved) > 5:
                detail += f" (and {len(result.unresolved) - 5} more)"

            raise KnownError(
                kind=FailureKind.VALIDATION_FAILED,
                message="Collection import failed: some cards could not be resolved.",
                detail=detail,
                suggestion="Check that card names match exactly. Re-export from Arena if needed.",
                status_code=400,
            )

        return result.owned_cards
