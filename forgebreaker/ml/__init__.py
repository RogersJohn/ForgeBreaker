"""Machine learning components for deck recommendations."""

from forgebreaker.ml.features import (
    CollectionFeatures,
    DeckFeatures,
    encode_archetype,
    extract_collection_features,
    extract_deck_features,
)
from forgebreaker.ml.inference import (
    MLForgeClient,
    RecommendationScore,
    get_mlforge_client,
)

__all__ = [
    "CollectionFeatures",
    "DeckFeatures",
    "MLForgeClient",
    "RecommendationScore",
    "encode_archetype",
    "extract_collection_features",
    "extract_deck_features",
    "get_mlforge_client",
]
