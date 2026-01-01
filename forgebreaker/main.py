import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from importlib.metadata import version as pkg_version

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from forgebreaker.api import (
    assumptions_router,
    chat_router,
    collection_router,
    decks_router,
    distance_router,
    health_router,
    stress_router,
)
from forgebreaker.config import settings
from forgebreaker.db.database import init_db
from forgebreaker.models.failure import (
    FailureKind,
    KnownError,
    RefusalError,
    create_refusal,
    create_unknown_failure,
    finalize_response,
)
from forgebreaker.services.card_name_guard import CardNameLeakageError, get_guard_stats
from forgebreaker.services.cost_controls import (
    DailyBudgetExceededError,
    LLMDisabledError,
    RateLimitExceededError,
    get_usage_tracker,
)

logger = logging.getLogger(__name__)


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
app.include_router(stress_router)

# CORS: Open access is intentional for this demo project.
# See README "Security Model" section for context.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =============================================================================
# FAILURE AUTHORITY BOUNDARY — Exception Handlers
# =============================================================================
#
# All exception handlers pass through the authority boundary via finalize_response()
# or the create_* factory functions which finalize automatically.
#
# =============================================================================


@app.exception_handler(KnownError)
async def known_error_handler(_request: Request, exc: KnownError) -> JSONResponse:
    """Handle known, explainable errors through the authority boundary."""
    response = finalize_response(exc.to_response())
    return JSONResponse(
        status_code=exc.status_code,
        content=response.model_dump(),
    )


@app.exception_handler(RefusalError)
async def refusal_error_handler(_request: Request, exc: RefusalError) -> JSONResponse:
    """Handle constraint-based refusals through the authority boundary."""
    response = finalize_response(exc.to_response())
    return JSONResponse(
        status_code=422,  # Unprocessable Entity
        content=response.model_dump(),
    )


@app.exception_handler(CardNameLeakageError)
async def card_name_leakage_handler(_request: Request, exc: CardNameLeakageError) -> JSONResponse:
    """Handle card name invariant violations through the authority boundary."""
    # Use create_refusal which finalizes automatically
    response = create_refusal(
        kind=FailureKind.CARD_NAME_LEAKAGE,
        constraint=f"card_name_output_barrier (leaked: {exc.leaked_name})",
    )
    return JSONResponse(
        status_code=422,
        content=response.model_dump(),
    )


# =============================================================================
# COST CONTROL EXCEPTION HANDLERS
# =============================================================================


@app.exception_handler(RateLimitExceededError)
async def rate_limit_handler(_request: Request, exc: RateLimitExceededError) -> JSONResponse:
    """Handle per-IP rate limit exceeded (HTTP 429)."""
    logger.warning(
        "RATE_LIMIT_RESPONSE",
        extra={"ip_hash": exc.ip_hash, "limit": exc.limit},
    )
    response = finalize_response(exc.to_response())
    return JSONResponse(
        status_code=exc.status_code,
        content=response.model_dump(),
    )


@app.exception_handler(DailyBudgetExceededError)
async def daily_budget_handler(_request: Request, exc: DailyBudgetExceededError) -> JSONResponse:
    """Handle global daily budget exceeded (HTTP 503)."""
    logger.warning(
        "DAILY_BUDGET_RESPONSE",
        extra={"limit_type": exc.limit_type, "used": exc.used, "limit": exc.limit},
    )
    response = finalize_response(exc.to_response())
    return JSONResponse(
        status_code=exc.status_code,
        content=response.model_dump(),
    )


@app.exception_handler(LLMDisabledError)
async def llm_disabled_handler(_request: Request, exc: LLMDisabledError) -> JSONResponse:
    """Handle LLM kill switch (HTTP 503)."""
    logger.warning("LLM_DISABLED_RESPONSE")
    response = finalize_response(exc.to_response())
    return JSONResponse(
        status_code=exc.status_code,
        content=response.model_dump(),
    )


@app.exception_handler(Exception)
async def unknown_exception_handler(_request: Request, exc: Exception) -> JSONResponse:
    """
    Handle all unexpected exceptions through the authority boundary.

    This is the catch-all that ensures no raw 500 reaches the frontend.
    Uses create_unknown_failure which finalizes automatically.
    """
    logger.exception("Unexpected error: %s", exc)
    # create_unknown_failure uses the STANDARD unknown message — fixed and boring
    response = create_unknown_failure(exc)
    return JSONResponse(
        status_code=500,
        content=response.model_dump(),
    )


# =============================================================================
# DIAGNOSTICS ENDPOINT — Guard Stats for Production Monitoring
# =============================================================================


@app.get("/diagnostics/guard-stats")
async def get_guard_diagnostics() -> dict[str, int | float]:
    """
    Get card name guard instrumentation statistics.

    Returns:
        Dict with invocation count, total time, leak count, and average time.
        This is useful for monitoring guard performance in production.
    """
    return get_guard_stats()


@app.get("/diagnostics/usage-stats")
async def get_usage_diagnostics() -> dict[str, int | str]:
    """
    Get current usage statistics and remaining budget.

    Returns:
        Dict with:
        - date: Current date (UTC)
        - unique_ips_today: Number of unique IP addresses seen today
        - llm_calls_today: LLM calls made today (global)
        - llm_calls_remaining: Remaining LLM calls before daily limit
        - tokens_today: Tokens used today (global)
        - tokens_remaining: Remaining tokens before daily limit
        - requests_per_ip_limit: Per-IP daily request limit
        - llm_calls_limit: Global daily LLM call limit
        - tokens_limit: Global daily token limit

    This endpoint is useful for monitoring usage and remaining budget.
    """
    return get_usage_tracker().get_diagnostics()
