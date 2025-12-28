from forgebreaker.api.assumptions import router as assumptions_router
from forgebreaker.api.chat import router as chat_router
from forgebreaker.api.collection import router as collection_router
from forgebreaker.api.decks import router as decks_router
from forgebreaker.api.distance import router as distance_router
from forgebreaker.api.health import router as health_router

__all__ = [
    "assumptions_router",
    "chat_router",
    "collection_router",
    "decks_router",
    "distance_router",
    "health_router",
]
