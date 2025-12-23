"""
Health check endpoints.

Provides liveness and readiness probes with database connectivity checks.
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from forgebreaker.db.database import get_session

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    database: str | None = None


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """
    Liveness probe.

    Returns healthy if the service is running.
    Does not check dependencies.
    """
    return HealthResponse(status="healthy")


@router.get(
    "/ready",
    response_model=HealthResponse,
    responses={503: {"model": HealthResponse}},
)
async def ready(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> HealthResponse:
    """
    Readiness probe.

    Returns ready if the service can handle requests.
    Checks database connectivity.
    """
    try:
        await session.execute(text("SELECT 1"))
        return HealthResponse(status="ready", database="connected")
    except Exception:
        return HealthResponse(status="not ready", database="disconnected")
