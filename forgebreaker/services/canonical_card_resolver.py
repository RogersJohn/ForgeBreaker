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

        Consolidates multiple printings of the same card by SUMMING counts.

        Args:
            inventory: List of raw inventory cards from Arena CSV

        Returns:
            ResolutionResult with resolved cards and any failures
        """
        # Group by canonical name (consolidation)
        consolidated: dict[str, list[InventoryCard]] = {}
        for inv_card in inventory:
            if inv_card.name not in consolidated:
                consolidated[inv_card.name] = []
            consolidated[inv_card.name].append(inv_card)

        owned_cards: list[OwnedCard] = []
        unresolved: list[tuple[InventoryCard, str]] = []
        arena_only_count = 0

        for name, inv_cards in consolidated.items():
            # Try to resolve the canonical card
            result = self._resolve_single(name, inv_cards)

            if isinstance(result, OwnedCard):
                owned_cards.append(result)
                if result.card.arena_only:
                    arena_only_count += 1
            else:
                # result is error reason string
                for inv_card in inv_cards:
                    unresolved.append((inv_card, result))

        return ResolutionResult(
            owned_cards=owned_cards,
            unresolved=unresolved,
            arena_only_count=arena_only_count,
        )

    def _resolve_single(
        self,
        name: str,
        inv_cards: list[InventoryCard],
    ) -> OwnedCard | str:
        """
        Resolve a single card name to a CanonicalCard.

        Returns OwnedCard on success, error reason string on failure.
        """
        card_data = self._card_db.get(name)
        if card_data is None:
            return "Card not found in Scryfall database"

        # Extract oracle_id
        oracle_id = card_data.get("oracle_id")
        if not oracle_id:
            return "No oracle_id in Scryfall data"

        # Check if any set code is Arena-only (not in Scryfall)
        arena_only = False
        for inv_card in inv_cards:
            set_code = inv_card.set_code.lower() if inv_card.set_code else ""
            if set_code and set_code not in self._known_sets:
                arena_only = True
                break

        # Build canonical card
        canonical = CanonicalCard(
            oracle_id=str(oracle_id),
            name=name,
            type_line=str(card_data.get("type_line", "")),
            colors=tuple(card_data.get("colors", [])),
            legalities=dict(card_data.get("legalities", {})),
            arena_only=arena_only,
        )

        # SUM counts across all printings (behavior change from MAX)
        total_count = sum(inv.count for inv in inv_cards)

        return OwnedCard(card=canonical, count=total_count)

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
