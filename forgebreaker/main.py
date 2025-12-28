from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from importlib.metadata import version as pkg_version

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from forgebreaker.api import (
    assumptions_router,
    chat_router,
    collection_router,
    decks_router,
    distance_router,
    health_router,
)
from forgebreaker.config import settings
from forgebreaker.db.database import init_db


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan handler for startup/shutdown."""
    await init_db()
    yield


app = FastAPI(
    title=settings.app_name,
    version=pkg_version("forgebreaker"),
    lifespan=lifespan,
)

app.include_router(assumptions_router)
app.include_router(chat_router)
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
