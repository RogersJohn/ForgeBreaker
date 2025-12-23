"""
Chat API endpoint for Claude integration.

Provides a chat endpoint that uses Claude to answer questions about
deck recommendations and collection management.
"""

import json
from typing import Annotated, Any, cast

import anthropic
from anthropic.types import MessageParam, ToolParam, ToolResultBlockParam, ToolUseBlock
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from forgebreaker.config import settings
from forgebreaker.db.database import get_session
from forgebreaker.mcp.tools import TOOL_DEFINITIONS, execute_tool

router = APIRouter(prefix="/chat", tags=["chat"])

# System prompt for Claude
SYSTEM_PROMPT = """You are ForgeBreaker, an MTG Arena deck advisor. You help users:
- Find decks they can build with their collection
- Calculate what cards they need for specific decks
- Understand their collection statistics
- Browse meta decks by format

Use the available tools to look up information. Be concise and helpful.
When recommending decks, explain why they're good choices based on completion percentage.
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
) -> list[ToolResultBlockParam]:
    """Execute tool calls and return results."""
    results: list[ToolResultBlockParam] = []
    for tool_call in tool_calls:
        try:
            result = await execute_tool(
                session,
                tool_call.name,
                cast(dict[str, Any], tool_call.input),
            )
            results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": tool_call.id,
                    "content": json.dumps(result),
                }
            )
        except ValueError as e:
            results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": tool_call.id,
                    "content": json.dumps({"error": str(e)}),
                    "is_error": True,
                }
            )
    return results


@router.post("", response_model=ChatResponse)
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
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            tools=tools,
            messages=messages,
        )

        # Check if Claude wants to use tools
        tool_use_blocks = [block for block in response.content if isinstance(block, ToolUseBlock)]

        if not tool_use_blocks:
            # No tool calls, extract text response
            text_content = ""
            for block in response.content:
                if hasattr(block, "text"):
                    text_content += block.text

            return ChatResponse(
                message=ChatMessage(role="assistant", content=text_content),
                tool_calls=tool_calls_made,
            )

        # Process tool calls
        tool_results = await _process_tool_calls(session, tool_use_blocks)

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
