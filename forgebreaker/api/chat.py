"""
Chat API endpoint for Claude integration.

Provides a chat endpoint that uses Claude to answer questions about
deck recommendations and collection management.
"""

import json
import logging
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

logger = logging.getLogger(__name__)


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
) -> list[ToolResultBlockParam]:
    """Execute tool calls and return results."""
    results: list[ToolResultBlockParam] = []
    for tool_call in tool_calls:
        try:
            # Inject user_id server-side for security
            tool_input = cast(dict[str, Any], tool_call.input)
            tool_input["user_id"] = user_id

            result = await execute_tool(
                session,
                tool_call.name,
                tool_input,
            )
            results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": tool_call.id,
                    "content": json.dumps(result),
                }
            )
        except Exception as e:
            logger.exception("Tool execution error for %s", tool_call.name)
            results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": tool_call.id,
                    "content": json.dumps({"error": str(e)}),
                    "is_error": True,
                }
            )
    return results


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
    """
    if not settings.anthropic_api_key:
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

    # Loop to handle tool calls
    max_iterations = 5
    for _ in range(max_iterations):
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            tools=tools,
            messages=messages,
        )

        # Record token usage metrics (PR 4)
        if response.usage:
            _record_token_usage(
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
                feature_flag_enabled=settings.use_filtered_candidate_pool,
            )

        # Check if Claude wants to use tools
        tool_use_blocks = [block for block in response.content if isinstance(block, ToolUseBlock)]

        if not tool_use_blocks:
            # No tool calls, extract text response
            text_content = ""
            for block in response.content:
                if isinstance(block, TextBlock):
                    text_content += block.text

            return ChatResponse(
                message=ChatMessage(role="assistant", content=text_content),
                tool_calls=tool_calls_made,
            )

        # Process tool calls with server-injected user_id
        tool_results = await _process_tool_calls(session, tool_use_blocks, request.user_id)

        # Record tool calls for response
        for block in tool_use_blocks:
            tool_calls_made.append(
                {
                    "name": block.name,
                    "input": cast(dict[str, Any], block.input),
                }
            )

        # Add assistant response and tool results to messages
        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user", "content": tool_results})

    # Max iterations reached
    return ChatResponse(
        message=ChatMessage(
            role="assistant",
            content="I apologize, but I'm having trouble completing this request.",
        ),
        tool_calls=tool_calls_made,
    )
