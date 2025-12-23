from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Card:
    """
    A card instance with quantity.

    Attributes:
        name: Card name exactly as it appears in Arena
        quantity: Number of copies (1-4 for most cards, unlimited for basic lands)
        set_code: Three-letter set code (e.g., "LEB", "DMU")
        collector_number: Collector number within set
        arena_id: Arena's internal card ID (for log parsing)
    """

    name: str
    quantity: int
    set_code: str | None = None
    collector_number: str | None = None
    arena_id: int | None = None
