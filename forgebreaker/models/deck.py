from dataclasses import dataclass, field


@dataclass
class MetaDeck:
    """
    A competitive deck from the metagame.

    Attributes:
        name: Deck archetype name (e.g., "Mono-Red Aggro")
        archetype: Play style category
        format: Arena format (standard, historic, explorer, timeless)
        cards: Maindeck cards {name: quantity}
        sideboard: Sideboard cards {name: quantity}
        win_rate: Estimated win rate from meta source (0.0-1.0)
        meta_share: Percentage of meta this deck represents
        source_url: Where this deck list came from
    """

    name: str
    archetype: str  # aggro, midrange, control, combo
    format: str
    cards: dict[str, int] = field(default_factory=dict)
    sideboard: dict[str, int] = field(default_factory=dict)
    win_rate: float | None = None
    meta_share: float | None = None
    source_url: str | None = None

    def maindeck_count(self) -> int:
        """Total cards in maindeck."""
        return sum(self.cards.values())

    def all_cards(self) -> set[str]:
        """All unique card names in deck including sideboard."""
        return set(self.cards.keys()) | set(self.sideboard.keys())


@dataclass
class WildcardCost:
    """Wildcards needed to complete a deck."""

    common: int = 0
    uncommon: int = 0
    rare: int = 0
    mythic: int = 0

    def total(self) -> int:
        """Total wildcards needed."""
        return self.common + self.uncommon + self.rare + self.mythic

    def weighted_cost(self) -> float:
        """
        Weighted cost reflecting wildcard scarcity.

        Weights based on approximate acquisition difficulty:
        - Common: 0.1 (very easy to get)
        - Uncommon: 0.25
        - Rare: 1.0 (baseline)
        - Mythic: 4.0 (4x harder than rare)
        """
        return self.common * 0.1 + self.uncommon * 0.25 + self.rare * 1.0 + self.mythic * 4.0


@dataclass
class DeckDistance:
    """How far a collection is from completing a deck."""

    deck: MetaDeck
    owned_cards: int
    missing_cards: int
    completion_percentage: float
    wildcard_cost: WildcardCost
    missing_card_list: list[tuple[str, int, str]]  # (name, qty_needed, rarity)

    @property
    def is_complete(self) -> bool:
        """True if user owns all cards needed."""
        return self.missing_cards == 0


@dataclass
class RankedDeck:
    """A deck with its ranking score for recommendations."""

    deck: MetaDeck
    distance: DeckDistance
    score: float
    can_build_now: bool
    within_budget: bool
    recommendation_reason: str
