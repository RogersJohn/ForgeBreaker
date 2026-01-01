"""
Chat API endpoint for Claude integration.

Provides a chat endpoint that uses Claude to answer questions about
deck recommendations and collection management.

TERMINAL OUTCOME ENFORCEMENT:
- Tool errors are terminal — no retries
- KnownFailure exceptions are terminal — no retries
- Successful tool completion allows ONE final LLM call for formatting
- Budget exhaustion is terminal — already enforced

OBSERVABILITY:
- All logs are structured with request_id for correlation
- Lifecycle events: CHAT_REQUEST_START, CHAT_REQUEST_TERMINATED
- LLM events: LLM_CALL_START, LLM_CALL_END
- Tool events: TOOL_CALL_START, TOOL_CALL_SUCCESS, TOOL_CALL_FAILURE
- Terminal detection: TERMINAL_SUCCESS_DETECTED
"""

import json
import logging
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Annotated, Any, cast

import anthropic
from anthropic.types import (
    MessageParam,
    TextBlock,
    ToolParam,
    ToolResultBlockParam,
    ToolUseBlock,
)
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from forgebreaker.config import settings
from forgebreaker.db.database import get_session
from forgebreaker.mcp.tools import TOOL_DEFINITIONS, execute_tool
from forgebreaker.models.budget import (
    MAX_LLM_CALLS_PER_REQUEST,
    MAX_TOKENS_PER_REQUEST,
    BudgetExceededError,
    RequestBudget,
)
from forgebreaker.models.failure import FailureKind, KnownError, RefusalError

# =============================================================================
# TERMINAL OUTCOME CLASSIFICATION
# =============================================================================


class TerminalReason(str, Enum):
    """Classification of why execution terminated."""

    NONE = "none"  # Not terminal, continue
    SUCCESS = "success"  # Tool completed successfully with valid result
    TOOL_ERROR = "tool_error"  # Tool raised an exception
    TOOL_RETURNED_ERROR = "tool_returned_error"  # Tool returned error in result
    KNOWN_FAILURE = "known_failure"  # KnownError exception
    REFUSAL = "refusal"  # RefusalError exception
    BUDGET_EXHAUSTED = "budget_exhausted"  # Budget limit hit


# =============================================================================
# TERMINAL SUCCESS DETECTION
# =============================================================================

# Tools that produce terminal success when they return {"success": True}
# These tools complete the user's request fully - no follow-up LLM call needed
TERMINAL_SUCCESS_TOOLS = frozenset(
    {
        "build_deck",
        "find_synergies",
        "improve_deck",
        "search_collection",
        "get_deck_recommendations",
        "calculate_deck_distance",
        "list_meta_decks",
        "get_collection_stats",
        "export_to_arena",
    }
)


def _is_terminal_success(tool_name: str, result: Any) -> bool:
    """
    Determine if a tool result represents terminal success.

    A result is terminally successful if:
    1. The tool is in TERMINAL_SUCCESS_TOOLS
    2. The result is a dict with "success": True AND has actual content
    3. No error is present in the result
    4. The result is NOT empty/trivial

    This is a DETERMINISTIC check - no heuristics.

    IMPORTANT: Empty results (0 cards, no matches) are NOT terminal success.
    They should be returned to the LLM for explanation or retry.
    """
    if tool_name not in TERMINAL_SUCCESS_TOOLS:
        return False

    if not isinstance(result, dict):
        return False

    # Explicit error means not success
    if result.get("error"):
        return False

    # Check for warnings that indicate empty/failed results
    warnings = result.get("warnings", [])
    if warnings and any("no cards" in w.lower() or "not found" in w.lower() for w in warnings):
        return False

    # For build_deck: must have actual cards
    if tool_name == "build_deck":
        total_cards = result.get("total_cards", 0)
        if total_cards == 0:
            return False  # Empty deck is not a success
        return result.get("success") is True

    # For search_collection: must have results
    if tool_name == "search_collection":
        results = result.get("results", [])
        return bool(results)  # No results is not terminal success

    # For other tools with explicit success flag
    if result.get("success") is True:
        return True

    # For tools that return data without explicit success flag,
    # check for presence of expected data fields with actual content
    if "results" in result and result["results"]:
        return True

    return bool("cards" in result and result["cards"])


@dataclass
class ToolProcessingResult:
    """Result of processing tool calls with terminal outcome detection."""

    results: list[ToolResultBlockParam]
    is_terminal: bool
    terminal_reason: TerminalReason
    error_message: str | None = None
    # For terminal success, store the successful result for direct formatting
    success_tool_name: str | None = None
    success_result: dict[str, Any] | None = None


@dataclass
class RequestContext:
    """Request-scoped context for tracking terminal state and observability.

    INVARIANT: Once is_finalized is True, NO LLM calls may be made.
    This is enforced by guard_llm_call() which must be called before
    every client.messages.create() invocation.

    OBSERVABILITY: All logs include request_id and user_id for correlation.
    """

    request_id: str = ""
    user_id: str = ""
    is_finalized: bool = False
    terminal_reason: TerminalReason = TerminalReason.NONE
    terminal_message: str | None = None
    llm_call_count: int = 0
    tool_call_count: int = 0
    tools_invoked: list[str] = field(default_factory=list)

    def _log_extra(self) -> dict[str, Any]:
        """Base extra fields for all logs in this request."""
        return {"request_id": self.request_id, "user_id": self.user_id}

    def finalize(self, reason: TerminalReason, message: str) -> None:
        """Mark request as finalized. No further LLM calls allowed."""
        if self.is_finalized:
            return  # Already finalized
        self.is_finalized = True
        self.terminal_reason = reason
        self.terminal_message = message
        # Note: CHAT_REQUEST_TERMINATED is logged separately at request end

    def guard_llm_call(self) -> None:
        """Guard that MUST be called before every LLM invocation.

        Raises KnownError if request is finalized.
        This makes it structurally impossible to call LLM after terminal outcome.
        """
        if self.is_finalized:
            raise KnownError(
                kind=FailureKind.INVARIANT_VIOLATION,
                message=(
                    "Internal invariant violation: LLM call attempted after terminal outcome. "
                    "This is a bug."
                ),
                detail=f"Reason: {self.terminal_reason.value}, Message: {self.terminal_message}",
                status_code=500,
            )

    def record_llm_call(self) -> None:
        """Record that an LLM call was made."""
        self.llm_call_count += 1

    def record_tool_call(self, tool_name: str) -> None:
        """Record that a tool was invoked."""
        self.tool_call_count += 1
        self.tools_invoked.append(tool_name)


logger = logging.getLogger(__name__)


# =============================================================================
# REQUEST-SCOPED EXECUTION ID
# =============================================================================


def _generate_request_id() -> str:
    """Generate a short, unique request ID for log correlation."""
    return uuid.uuid4().hex[:12]


# =============================================================================
# TOKEN METRICS (PR 4)
# =============================================================================

_token_metrics: list[dict[str, Any]] = []


def get_token_metrics() -> list[dict[str, Any]]:
    """Get recorded token metrics."""
    return _token_metrics.copy()


def reset_token_metrics() -> None:
    """Reset token metrics (for testing)."""
    _token_metrics.clear()


def _record_token_usage(
    input_tokens: int,
    output_tokens: int,
    feature_flag_enabled: bool,
) -> None:
    """Record token usage metrics."""
    _token_metrics.append(
        {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
            "feature_flag_enabled": feature_flag_enabled,
        }
    )
    logger.info(
        "token_usage",
        extra={
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "feature_flag_enabled": feature_flag_enabled,
        },
    )


router = APIRouter(prefix="/chat", tags=["chat"])

# System prompt for Claude
SYSTEM_PROMPT = """You are ForgeBreaker, an MTG Arena deck building assistant.

You help users:
1. Understand what cards they own
2. Build decks from their collection
3. Find meta decks they can complete
4. Get strategic advice

## Available Tools

### search_collection
Use when users ask about their cards:
- "Do I have any goblins?"
- "What shrines do I own?"
- "Show me my red creatures"

### build_deck
Use when users want to create a deck:
- "Build me a shrine deck"
- "Make a goblin tribal deck"
- "Create something fun with dragons"

This builds a COMPLETE 60-card deck using ONLY cards they own. No wildcards needed.

### find_synergies
Use when users want to know what works together:
- "What pairs well with Sheoldred?"
- "Find synergies for my sacrifice deck"

### export_to_arena
Use AFTER building a deck to give the user importable text.
Takes the cards and lands from a previous build_deck call.

### improve_deck
Use when users paste an existing deck list and ask to improve or upgrade it:
- "Here's my deck: [deck list]. How can I make it better?"
- "Improve this deck with cards I own"
- "What upgrades can I make to this list?"

Analyzes the deck and suggests card swaps from their collection.

### get_deck_recommendations
Use when users want competitive meta decks:
- "What meta decks can I build?"
- "Show me Standard decks I'm close to"

### calculate_deck_distance
Use for details about a specific meta deck's completion:
- "How close am I to completing Mono Red Aggro?"
- "What cards do I need for Esper Control?"

### list_meta_decks
Use to show available meta decks for a format:
- "What are the top decks in Standard?"
- "Show me all Historic meta decks"

### get_collection_stats
Use to show collection overview (total cards, unique cards):
- "How many cards do I have?"
- "Show me my collection statistics"

## Important Guidelines

1. ALWAYS use tools - don't guess about the user's collection
2. When building casual decks, use build_deck - don't suggest meta decks
3. After building a deck, offer to export it for Arena
4. If a theme has no cards, say so clearly
5. Be encouraging about casual/fun decks - not everything needs to be competitive

## Example Interaction

User: "Build me a shrine deck"

1. Call build_deck(theme="shrine") to create the deck using only cards they own
2. Show the deck with explanations
3. Offer: "Would you like me to export this for Arena import?"

(Optional) If the user first wants to see what shrines they own, you MAY call
search_collection(name_contains="shrine") before building the deck.

Note: All tool calls are automatically scoped to the authenticated user's data.
You do not need to provide user_id in tool calls - it is injected by the server.
"""


class ChatMessage(BaseModel):
    """A single chat message."""

    role: str = Field(..., pattern="^(user|assistant)$")
    content: str


class ChatRequest(BaseModel):
    """Request body for chat endpoint."""

    user_id: str = Field(..., description="User ID for collection lookup")
    messages: list[ChatMessage] = Field(..., min_length=1)


class ChatResponse(BaseModel):
    """Response from chat endpoint."""

    message: ChatMessage
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)


def _create_terminal_response(
    ctx: RequestContext,
    tool_calls_made: list[dict[str, Any]],
) -> ChatResponse:
    """Create a response for terminal FAILURE outcomes without making an LLM call.

    This is used when we hit a terminal failure state and must return immediately.
    The response explains the failure to the user.
    """
    # Build user-friendly error message based on terminal reason
    reason = ctx.terminal_reason
    message = ctx.terminal_message or "An error occurred"

    if reason == TerminalReason.KNOWN_FAILURE:
        content = f"I encountered an issue: {message}"
    elif reason == TerminalReason.REFUSAL:
        content = f"I cannot complete this request: {message}"
    elif reason == TerminalReason.TOOL_ERROR:
        content = f"A technical error occurred: {message}"
    elif reason == TerminalReason.TOOL_RETURNED_ERROR:
        content = f"I encountered a problem: {message}"
    elif reason == TerminalReason.BUDGET_EXHAUSTED:
        content = f"Request limit reached: {message}"
    else:
        content = f"Request could not be completed: {message}"

    return ChatResponse(
        message=ChatMessage(role="assistant", content=content),
        tool_calls=tool_calls_made,
    )


def _format_terminal_success_response(
    tool_name: str,
    result: dict[str, Any],
    tool_calls_made: list[dict[str, Any]],
) -> ChatResponse:
    """
    Format a successful tool result into a user response.

    This is the TERMINAL SUCCESS path - no further LLM calls are made.
    The response is formatted deterministically from the tool result.

    INVARIANT: This function produces a complete response without LLM involvement.
    """
    # Format based on tool type
    if tool_name == "build_deck":
        deck_name = result.get("deck_name", "Your Deck")
        total_cards = result.get("total_cards", 60)
        colors = result.get("colors", [])
        theme_cards = result.get("theme_cards", 0)
        cards = result.get("cards", {})
        lands = result.get("lands", {})
        notes = result.get("notes", "")
        warnings = result.get("warnings", [])
        assumptions = result.get("assumptions", "")

        # Build deck list
        lines = [
            f"# {deck_name}",
            f"**{total_cards} cards** | Colors: {', '.join(colors) or 'Colorless'}",
            "",
        ]

        if assumptions:
            lines.append(assumptions)
            lines.append("")

        # Non-land cards
        if cards:
            lines.append("## Cards")
            for card_name, count in cards.items():
                lines.append(f"- {count}x {card_name}")
            lines.append("")

        # Lands
        if lands:
            lines.append("## Lands")
            for land_name, count in lands.items():
                lines.append(f"- {count}x {land_name}")
            lines.append("")

        if notes:
            lines.append(f"**Strategy:** {notes}")
            lines.append("")

        if warnings:
            lines.append("**Warnings:**")
            for w in warnings:
                lines.append(f"- {w}")
            lines.append("")

        lines.append(f"Found {theme_cards} theme cards in your collection.")
        lines.append("")
        lines.append("Would you like me to export this deck for Arena import?")

        content = "\n".join(lines)

    elif tool_name == "search_collection":
        results_list = result.get("results", [])
        total = result.get("total", len(results_list))
        query = result.get("query", "")

        if not results_list:
            content = f"I didn't find any cards matching '{query}' in your collection."
        else:
            lines = [f"Found {total} cards matching '{query}':", ""]
            for card in results_list[:20]:  # Limit display
                name = card.get("name", "Unknown")
                count = card.get("count", 1)
                lines.append(f"- {count}x {name}")
            if total > 20:
                lines.append(f"... and {total - 20} more")
            content = "\n".join(lines)

    elif tool_name == "find_synergies":
        synergies = result.get("synergies", [])
        card_name = result.get("card_name", "that card")

        if not synergies:
            content = f"I didn't find strong synergies for {card_name} in your collection."
        else:
            lines = [f"Cards that synergize with {card_name}:", ""]
            for syn in synergies[:15]:
                name = syn.get("name", "Unknown")
                reason = syn.get("reason", "")
                lines.append(f"- **{name}**: {reason}")
            content = "\n".join(lines)

    elif tool_name == "export_to_arena":
        arena_text = result.get("arena_export", result.get("export", ""))
        content = (
            f"Here's your deck ready for Arena import:\n\n```\n{arena_text}\n```\n\n"
            "Copy this text and paste it into MTG Arena's deck import."
        )

    elif tool_name == "improve_deck":
        suggestions = result.get("suggestions", [])
        analysis = result.get("analysis", "")

        lines = ["## Deck Improvement Suggestions", ""]
        if analysis:
            lines.append(analysis)
            lines.append("")
        for sug in suggestions[:10]:
            remove = sug.get("remove", "")
            add = sug.get("add", "")
            reason = sug.get("reason", "")
            lines.append(f"- Replace **{remove}** with **{add}**: {reason}")
        content = "\n".join(lines)

    elif tool_name == "get_collection_stats":
        total = result.get("total_cards", 0)
        unique = result.get("unique_cards", 0)
        content = f"Your collection has **{total:,} cards** ({unique:,} unique cards)."

    elif tool_name in ("get_deck_recommendations", "list_meta_decks"):
        decks = result.get("decks", result.get("recommendations", []))
        if not decks:
            content = "No meta decks found for this format."
        else:
            lines = ["## Available Meta Decks", ""]
            for deck in decks[:10]:
                name = deck.get("name", "Unknown")
                completion = deck.get("completion_percentage", deck.get("completion", 0))
                lines.append(f"- **{name}**: {completion:.0f}% complete")
            content = "\n".join(lines)

    elif tool_name == "calculate_deck_distance":
        deck_name = result.get("deck_name", "the deck")
        completion = result.get("completion_percentage", 0)
        missing = result.get("missing_cards", [])

        lines = [f"## {deck_name}", f"**{completion:.0f}% complete**", ""]
        if missing:
            lines.append("Missing cards:")
            for card in missing[:15]:
                name = card.get("name", "Unknown")
                count = card.get("count", 1)
                lines.append(f"- {count}x {name}")
        content = "\n".join(lines)

    else:
        # Generic fallback - just confirm success
        content = f"Done! The {tool_name.replace('_', ' ')} operation completed successfully."

    return ChatResponse(
        message=ChatMessage(role="assistant", content=content),
        tool_calls=tool_calls_made,
    )


def _get_anthropic_tools() -> list[ToolParam]:
    """Convert our tool definitions to Anthropic format."""
    tools: list[ToolParam] = []
    for tool in TOOL_DEFINITIONS:
        tools.append(
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.parameters,
            }
        )
    return tools


async def _process_tool_calls(
    session: AsyncSession,
    tool_calls: list[ToolUseBlock],
    user_id: str,
    ctx: RequestContext,
) -> ToolProcessingResult:
    """
    Execute tool calls and return results with terminal outcome detection.

    TERMINAL OUTCOMES (no further LLM calls allowed):
    - SUCCESS: Tool returned valid result → terminal (exit loop)
    - KnownError exception → terminal
    - RefusalError exception → terminal
    - Any other exception → terminal
    - Tool returns {"error": ...} → terminal

    Returns:
        ToolProcessingResult with is_terminal flag set appropriately
    """
    results: list[ToolResultBlockParam] = []
    is_terminal = False
    terminal_reason = TerminalReason.NONE
    error_message: str | None = None
    success_tool_name: str | None = None
    success_result: dict[str, Any] | None = None

    for tool_call in tool_calls:
        tool_name = tool_call.name
        ctx.record_tool_call(tool_name)

        # TOOL_CALL_START
        logger.info(
            "TOOL_CALL_START",
            extra={
                **ctx._log_extra(),
                "tool_name": tool_name,
                "tool_index": ctx.tool_call_count,
            },
        )

        try:
            # Inject user_id server-side for security
            tool_input = cast(dict[str, Any], tool_call.input)
            tool_input["user_id"] = user_id

            result = await execute_tool(
                session,
                tool_name,
                tool_input,
            )

            # Check if tool returned an error in its result
            if isinstance(result, dict) and result.get("error"):
                is_terminal = True
                terminal_reason = TerminalReason.TOOL_RETURNED_ERROR
                error_message = str(result.get("error"))
                # TOOL_CALL_FAILURE
                logger.warning(
                    "TOOL_CALL_FAILURE",
                    extra={
                        **ctx._log_extra(),
                        "tool_name": tool_name,
                        "failure_type": "returned_error",
                    },
                )
            # TERMINAL SUCCESS: Tool completed successfully with valid result
            elif _is_terminal_success(tool_name, result):
                is_terminal = True
                terminal_reason = TerminalReason.SUCCESS
                success_tool_name = tool_name
                success_result = result if isinstance(result, dict) else None

                # TOOL_CALL_SUCCESS
                logger.info(
                    "TOOL_CALL_SUCCESS",
                    extra={
                        **ctx._log_extra(),
                        "tool_name": tool_name,
                    },
                )

                # TERMINAL_SUCCESS_DETECTED
                logger.info(
                    "TERMINAL_SUCCESS_DETECTED",
                    extra={
                        **ctx._log_extra(),
                        "reason": "deck_built" if tool_name == "build_deck" else "tool_success",
                        "tool_name": tool_name,
                    },
                )
            else:
                # Tool succeeded but result is not terminal (e.g., empty results)
                # TOOL_CALL_SUCCESS
                logger.info(
                    "TOOL_CALL_SUCCESS",
                    extra={
                        **ctx._log_extra(),
                        "tool_name": tool_name,
                    },
                )

            results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": tool_call.id,
                    "content": json.dumps(result),
                }
            )

        except KnownError as e:
            # KnownError is TERMINAL — no retries
            is_terminal = True
            terminal_reason = TerminalReason.KNOWN_FAILURE
            error_message = e.message
            # TOOL_CALL_FAILURE
            logger.warning(
                "TOOL_CALL_FAILURE",
                extra={
                    **ctx._log_extra(),
                    "tool_name": tool_name,
                    "failure_type": "known_error",
                },
            )
            results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": tool_call.id,
                    "content": json.dumps({"error": e.message, "kind": e.kind.value}),
                    "is_error": True,
                }
            )

        except RefusalError as e:
            # RefusalError is TERMINAL — no retries
            is_terminal = True
            terminal_reason = TerminalReason.REFUSAL
            error_message = e.message
            # TOOL_CALL_FAILURE
            logger.warning(
                "TOOL_CALL_FAILURE",
                extra={
                    **ctx._log_extra(),
                    "tool_name": tool_name,
                    "failure_type": "refusal",
                },
            )
            results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": tool_call.id,
                    "content": json.dumps({"error": e.message, "kind": e.kind.value}),
                    "is_error": True,
                }
            )

        except Exception as e:
            # Any other exception is TERMINAL — no retries
            is_terminal = True
            terminal_reason = TerminalReason.TOOL_ERROR
            error_message = str(e)
            # TOOL_CALL_FAILURE
            logger.exception(
                "TOOL_CALL_FAILURE",
                extra={
                    **ctx._log_extra(),
                    "tool_name": tool_name,
                    "failure_type": "exception",
                },
            )
            results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": tool_call.id,
                    "content": json.dumps({"error": str(e)}),
                    "is_error": True,
                }
            )

    return ToolProcessingResult(
        results=results,
        is_terminal=is_terminal,
        terminal_reason=terminal_reason,
        error_message=error_message,
        success_tool_name=success_tool_name,
        success_result=success_result,
    )


@router.post("/", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ChatResponse:
    """
    Chat with Claude about deck recommendations.

    Sends messages to Claude with access to deck and collection tools.
    Claude can look up collection stats, meta decks, and calculate
    what cards are needed for specific decks.

    Budget enforcement (PR 5):
    - Max LLM calls: MAX_LLM_CALLS_PER_REQUEST (hard cap)
    - Max tokens: MAX_TOKENS_PER_REQUEST (hard cap)
    - Exceedance is terminal — no retries, no fallback

    Terminal outcome enforcement (CRITICAL INVARIANT):
    - Tool errors are TERMINAL — return immediately, NO further LLM calls
    - KnownFailure/RefusalError are TERMINAL — return immediately
    - RequestContext.is_finalized blocks ALL LLM calls after terminal
    - guard_llm_call() enforces this before every client.messages.create()

    Observability:
    - All logs include request_id for correlation
    - Lifecycle: CHAT_REQUEST_START, CHAT_REQUEST_TERMINATED
    - LLM calls: LLM_CALL_START, LLM_CALL_END
    - Tool calls: TOOL_CALL_START, TOOL_CALL_SUCCESS/FAILURE
    """
    # Generate request-scoped execution ID for log correlation
    request_id = _generate_request_id()

    # Request-scoped context for terminal state tracking and observability
    # INVARIANT: Once ctx.is_finalized is True, NO LLM calls allowed
    ctx = RequestContext(request_id=request_id, user_id=request.user_id)

    # CHAT_REQUEST_START
    logger.info(
        "CHAT_REQUEST_START",
        extra={
            **ctx._log_extra(),
        },
    )

    if not settings.anthropic_api_key:
        # CHAT_REQUEST_TERMINATED (config error)
        logger.error(
            "CHAT_REQUEST_TERMINATED",
            extra={
                **ctx._log_extra(),
                "outcome": "config_error",
                "llm_calls": 0,
                "tool_calls": 0,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Anthropic API key not configured",
        )

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    # Convert messages to Anthropic format
    messages: list[MessageParam] = []
    for msg in request.messages:
        messages.append({"role": cast(Any, msg.role), "content": msg.content})

    tools = _get_anthropic_tools()
    tool_calls_made: list[dict[str, Any]] = []

    # Initialize request budget (PR 5)
    budget = RequestBudget(
        max_llm_calls=MAX_LLM_CALLS_PER_REQUEST,
        max_tokens=MAX_TOKENS_PER_REQUEST,
    )

    # Helper to log termination (exactly once per request)
    def _log_terminated(outcome: str) -> None:
        logger.info(
            "CHAT_REQUEST_TERMINATED",
            extra={
                **ctx._log_extra(),
                "outcome": outcome,
                "llm_calls": ctx.llm_call_count,
                "tool_calls": ctx.tool_call_count,
                "tools_invoked": ctx.tools_invoked,
            },
        )

    # Loop to handle tool calls — budget enforced, terminal outcomes enforced
    try:
        while True:
            # BUDGET CHECK: Before each LLM call
            budget.check_call_budget()

            # TERMINAL GUARD: Block LLM call if request is finalized
            # This is the HARD INVARIANT - no LLM calls after terminal outcome
            ctx.guard_llm_call()

            call_index = ctx.llm_call_count + 1

            # LLM_CALL_START
            logger.info(
                "LLM_CALL_START",
                extra={
                    **ctx._log_extra(),
                    "call_index": call_index,
                },
            )

            # Make LLM call with tools
            response = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=2048,
                system=SYSTEM_PROMPT,
                tools=tools,
                messages=messages,
            )
            ctx.record_llm_call()

            # BUDGET RECORD: After each LLM call
            input_tokens = response.usage.input_tokens if response.usage else 0
            output_tokens = response.usage.output_tokens if response.usage else 0
            budget.record_call(input_tokens, output_tokens)

            # LLM_CALL_END
            logger.info(
                "LLM_CALL_END",
                extra={
                    **ctx._log_extra(),
                    "call_index": call_index,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                },
            )

            # Record token usage metrics (PR 4)
            if response.usage:
                _record_token_usage(
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    feature_flag_enabled=settings.use_filtered_candidate_pool,
                )

            # Check if Claude wants to use tools
            tool_use_blocks = [
                block for block in response.content if isinstance(block, ToolUseBlock)
            ]

            if not tool_use_blocks:
                # No tool calls, extract text response — this is the SUCCESS exit path
                text_content = ""
                for block in response.content:
                    if isinstance(block, TextBlock):
                        text_content += block.text

                # CHAT_REQUEST_TERMINATED (success - no tools)
                _log_terminated("success")

                return ChatResponse(
                    message=ChatMessage(role="assistant", content=text_content),
                    tool_calls=tool_calls_made,
                )

            # Process tool calls with server-injected user_id
            tool_result = await _process_tool_calls(session, tool_use_blocks, request.user_id, ctx)

            # Record tool calls for response
            for block in tool_use_blocks:
                tool_calls_made.append(
                    {
                        "name": block.name,
                        "input": cast(dict[str, Any], block.input),
                    }
                )

            # CHECK FOR TERMINAL OUTCOME — RETURN IMMEDIATELY
            # Do NOT continue loop, do NOT make another LLM call
            if tool_result.is_terminal:
                ctx.finalize(tool_result.terminal_reason, tool_result.error_message or "")

                # TERMINAL SUCCESS: Format result directly, skip LLM
                if (
                    tool_result.terminal_reason == TerminalReason.SUCCESS
                    and tool_result.success_tool_name
                    and tool_result.success_result
                ):
                    # CHAT_REQUEST_TERMINATED (success - terminal)
                    _log_terminated("success")

                    return _format_terminal_success_response(
                        tool_result.success_tool_name,
                        tool_result.success_result,
                        tool_calls_made,
                    )

                # TERMINAL FAILURE: Return error response
                # CHAT_REQUEST_TERMINATED (known_failure)
                _log_terminated("known_failure")

                return _create_terminal_response(ctx, tool_calls_made)

            # Add assistant response and tool results to messages for next iteration
            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_result.results})

    except BudgetExceededError as e:
        # Budget exceeded — terminal failure, finalize and return
        ctx.finalize(TerminalReason.BUDGET_EXHAUSTED, e.message)

        # CHAT_REQUEST_TERMINATED (budget_exceeded)
        _log_terminated("budget_exceeded")

        raise HTTPException(
            status_code=e.status_code,
            detail=e.message,
        ) from e
