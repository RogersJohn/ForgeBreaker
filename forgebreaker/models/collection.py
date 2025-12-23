from dataclasses import dataclass, field


@dataclass
class Collection:
    """
    A user's card collection.

    Cards are stored by name with max quantity owned.
    For most cards, max is 4. Basic lands can exceed 4.
    """

    cards: dict[str, int] = field(default_factory=dict)

    def owns(self, card_name: str, quantity: int = 1) -> bool:
        """Check if collection contains at least `quantity` of a card."""
        return self.cards.get(card_name, 0) >= quantity

    def get_quantity(self, card_name: str) -> int:
        """Get quantity owned of a specific card."""
        return self.cards.get(card_name, 0)

    def add_card(self, card_name: str, quantity: int = 1) -> None:
        """Add cards to collection."""
        self.cards[card_name] = self.cards.get(card_name, 0) + quantity

    def total_cards(self) -> int:
        """Total number of cards in collection."""
        return sum(self.cards.values())

    def unique_cards(self) -> int:
        """Number of unique cards in collection."""
        return len(self.cards)
