"""
Canonical Card Models.

This module defines the trust boundary between raw Arena CSV data
and oracle-backed canonical Magic cards.

INVARIANTS:
- InventoryCard is UNTRUSTED raw import data
- CanonicalCard represents IDENTITY only (oracle_id, name)
- CardMetadata holds semantic/playability data
- ResolvedCard combines identity + metadata for downstream use
- All models are frozen (immutable after construction)

DESIGN:
- CanonicalCard = identity (stable across printings)
- CardMetadata = semantic data (may change per format/context)
- ResolvedCard = identity + metadata (result of resolution)
- OwnedCard = resolved card + count (for collections)
"""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class InventoryCard:
    """
    Raw card entry from Arena CSV import.

    This is UNTRUSTED data directly from user input.
    No assumptions about validity - must be resolved to canonical form.

    Attributes:
        name: Card name as it appears in Arena export
        set_code: Three-letter set code from Arena (e.g., "DMU", "Y24")
        count: Number of copies in this specific printing
        collector_number: Collector number within set (optional)
    """

    name: str
    set_code: str
    count: int
    collector_number: str | None = None


@dataclass(frozen=True, slots=True)
class CanonicalCard:
    """
    Oracle-backed card IDENTITY from Scryfall.

    This is TRUSTED identity data backed by the Scryfall oracle.
    Contains ONLY identity fields - no semantic/playability data.
    Use ResolvedCard for semantic operations.

    Attributes:
        oracle_id: Scryfall oracle ID (stable across printings)
        name: Canonical card name from Scryfall
    """

    oracle_id: str
    name: str


@dataclass(frozen=True, slots=True)
class CardMetadata:
    """
    Semantic/playability data for a card.

    Separated from identity to clarify that:
    - Identity is stable (oracle_id, name)
    - Metadata may vary by context (legalities change, types are contextual)

    Attributes:
        type_line: Full type line (e.g., "Creature - Human Wizard")
        colors: Tuple of color letters (W, U, B, R, G) - immutable
        legalities: Dict of format -> legality status
    """

    type_line: str
    colors: tuple[str, ...]
    legalities: dict[str, str]


@dataclass(frozen=True, slots=True)
class ResolvedCard:
    """
    A canonical card with its metadata and resolution context.

    This is the result of successful resolution: identity + metadata.
    arena_only is a resolution-time flag, not part of card identity.

    Attributes:
        identity: The canonical card identity
        metadata: Semantic data from oracle
        arena_only: True if imported from Arena-specific set
    """

    identity: CanonicalCard
    metadata: CardMetadata
    arena_only: bool = False

    @property
    def oracle_id(self) -> str:
        """Convenience accessor for oracle_id."""
        return self.identity.oracle_id

    @property
    def name(self) -> str:
        """Convenience accessor for name."""
        return self.identity.name

    @property
    def type_line(self) -> str:
        """Convenience accessor for type_line."""
        return self.metadata.type_line

    @property
    def colors(self) -> tuple[str, ...]:
        """Convenience accessor for colors."""
        return self.metadata.colors

    @property
    def legalities(self) -> dict[str, str]:
        """Convenience accessor for legalities."""
        return self.metadata.legalities


@dataclass(frozen=True, slots=True)
class OwnedCard:
    """
    A resolved card paired with owned count.

    Represents a resolved, owned card in a collection.
    Count is the SUM across all printings (consolidated).

    Attributes:
        card: The resolved card (identity + metadata)
        count: Total owned across all printings
    """

    card: ResolvedCard
    count: int
