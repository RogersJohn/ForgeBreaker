from importlib.metadata import version as pkg_version

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from forgebreaker.api import collection_router, decks_router, distance_router, health_router
from forgebreaker.config import settings

app = FastAPI(
    title=settings.app_name,
    version=pkg_version("forgebreaker"),
)

app.include_router(collection_router)
app.include_router(decks_router)
app.include_router(distance_router)
app.include_router(health_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Tighten in production
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
