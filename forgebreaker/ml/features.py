"""
Feature engineering for ML-based deck recommendations.

Extracts numerical features from collections and decks for use with
the MLForge recommendation model.
"""

from dataclasses import dataclass, field

from forgebreaker.models.collection import Collection
from forgebreaker.models.deck import DeckDistance, MetaDeck


@dataclass
class CollectionFeatures:
    """Feature vector representing a user's collection."""

    total_cards: int = 0
    unique_cards: int = 0
    common_count: int = 0
    uncommon_count: int = 0
    rare_count: int = 0
    mythic_count: int = 0

    def to_dict(self) -> dict[str, int]:
        """Convert to dictionary for API calls."""
        return {
            "total_cards": self.total_cards,
            "unique_cards": self.unique_cards,
            "common_count": self.common_count,
            "uncommon_count": self.uncommon_count,
            "rare_count": self.rare_count,
            "mythic_count": self.mythic_count,
        }


@dataclass
class DeckFeatures:
    """Feature vector representing a deck and its distance from collection."""

    # Deck metadata
    deck_name: str = ""
    archetype: str = ""
    format: str = ""

    # Deck composition
    maindeck_size: int = 0
    sideboard_size: int = 0
    unique_cards: int = 0

    # Meta stats
    win_rate: float = 0.0
    meta_share: float = 0.0

    # Distance features
    owned_cards: int = 0
    missing_cards: int = 0
    completion_percentage: float = 0.0

    # Wildcard costs
    common_needed: int = 0
    uncommon_needed: int = 0
    rare_needed: int = 0
    mythic_needed: int = 0
    total_wildcards: int = 0
    weighted_cost: float = 0.0

    # Derived features
    can_build: bool = False
    archetype_encoded: list[float] = field(default_factory=list)

    def to_dict(self) -> dict[str, float | int | str | bool | list[float]]:
        """Convert to dictionary for API calls."""
        return {
            "deck_name": self.deck_name,
            "archetype": self.archetype,
            "format": self.format,
            "maindeck_size": self.maindeck_size,
            "sideboard_size": self.sideboard_size,
            "unique_cards": self.unique_cards,
            "win_rate": self.win_rate,
            "meta_share": self.meta_share,
            "owned_cards": self.owned_cards,
            "missing_cards": self.missing_cards,
            "completion_percentage": self.completion_percentage,
            "common_needed": self.common_needed,
            "uncommon_needed": self.uncommon_needed,
            "rare_needed": self.rare_needed,
            "mythic_needed": self.mythic_needed,
            "total_wildcards": self.total_wildcards,
            "weighted_cost": self.weighted_cost,
            "can_build": self.can_build,
            "archetype_encoded": self.archetype_encoded,
        }


# Archetype encoding order for one-hot encoding
ARCHETYPES = ["aggro", "midrange", "control", "combo"]


def encode_archetype(archetype: str) -> list[float]:
    """
    One-hot encode archetype for ML model.

    Args:
        archetype: Deck archetype (aggro, midrange, control, combo)

    Returns:
        One-hot encoded vector [aggro, midrange, control, combo]
    """
    archetype_lower = archetype.lower()
    return [1.0 if a == archetype_lower else 0.0 for a in ARCHETYPES]


def extract_collection_features(
    collection: Collection,
    rarity_map: dict[str, str],
) -> CollectionFeatures:
    """
    Extract ML features from a collection.

    Args:
        collection: User's card collection
        rarity_map: Card name -> rarity mapping

    Returns:
        CollectionFeatures with computed values
    """
    features = CollectionFeatures(
        total_cards=collection.total_cards(),
        unique_cards=collection.unique_cards(),
    )

    # Count cards by rarity
    for card_name, quantity in collection.cards.items():
        rarity = rarity_map.get(card_name, "common").lower()
        if rarity == "common":
            features.common_count += quantity
        elif rarity == "uncommon":
            features.uncommon_count += quantity
        elif rarity == "rare":
            features.rare_count += quantity
        elif rarity == "mythic":
            features.mythic_count += quantity
        else:
            # Fallback: treat unexpected rarity as common
            features.common_count += quantity

    return features


def extract_deck_features(
    deck: MetaDeck,
    distance: DeckDistance,
) -> DeckFeatures:
    """
    Extract ML features from a deck and its distance from collection.

    Args:
        deck: Target meta deck
        distance: Computed distance from user's collection

    Returns:
        DeckFeatures with computed values
    """
    sideboard_size = sum(deck.sideboard.values()) if deck.sideboard else 0

    return DeckFeatures(
        deck_name=deck.name,
        archetype=deck.archetype,
        format=deck.format,
        maindeck_size=deck.maindeck_count(),
        sideboard_size=sideboard_size,
        unique_cards=len(deck.all_cards()),
        win_rate=deck.win_rate or 0.0,
        meta_share=deck.meta_share or 0.0,
        owned_cards=distance.owned_cards,
        missing_cards=distance.missing_cards,
        completion_percentage=distance.completion_percentage,
        common_needed=distance.wildcard_cost.common,
        uncommon_needed=distance.wildcard_cost.uncommon,
        rare_needed=distance.wildcard_cost.rare,
        mythic_needed=distance.wildcard_cost.mythic,
        total_wildcards=distance.wildcard_cost.total(),
        weighted_cost=distance.wildcard_cost.weighted_cost(),
        can_build=distance.is_complete,
        archetype_encoded=encode_archetype(deck.archetype),
    )
