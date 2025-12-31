"""
Canonical Card Models.

This module defines the trust boundary between raw Arena CSV data
and oracle-backed canonical Magic cards.

INVARIANTS:
- InventoryCard is UNTRUSTED raw import data
- CanonicalCard is TRUSTED oracle-backed data
- Construction of CanonicalCard implies successful resolution
- All models are frozen (immutable after construction)
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
    Oracle-backed canonical card from Scryfall.

    This is TRUSTED data backed by the Scryfall database.
    Construction implies successful resolution against oracle data.

    Attributes:
        oracle_id: Scryfall oracle ID (stable across printings)
        name: Canonical card name from Scryfall
        type_line: Full type line (e.g., "Creature - Human Wizard")
        colors: Tuple of color letters (W, U, B, R, G) - immutable
        legalities: Dict of format -> legality status
        arena_only: True if import set code is not in Scryfall print sets
    """

    oracle_id: str
    name: str
    type_line: str
    colors: tuple[str, ...]
    legalities: dict[str, str]
    arena_only: bool = False


@dataclass(frozen=True, slots=True)
class OwnedCard:
    """
    A canonical card paired with owned count.

    Represents a resolved, owned card in a collection.
    Count is the SUM across all printings (consolidated).

    Attributes:
        card: The canonical card data
        count: Total owned across all printings
    """

    card: CanonicalCard
    count: int
