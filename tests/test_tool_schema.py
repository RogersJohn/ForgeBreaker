"""
Tests for Tool Schema Invariants (PR 7).

These tests verify:
1. Tool names are unchanged
2. Required parameters are unchanged
3. Removed parameters (user_id) are server-injected
4. Schema structure remains valid JSON Schema
"""

import pytest

from forgebreaker.mcp.tools import TOOL_DEFINITIONS, execute_tool

# =============================================================================
# EXPECTED TOOL NAMES (AUTHORITATIVE - DO NOT CHANGE)
# =============================================================================

EXPECTED_TOOL_NAMES = [
    "get_deck_recommendations",
    "calculate_deck_distance",
    "get_collection_stats",
    "list_meta_decks",
    "search_collection",
    "build_deck",
    "find_synergies",
    "export_to_arena",
    "improve_deck",
    "get_deck_assumptions",
    "stress_deck_assumption",
    "find_deck_breaking_point",
]


# =============================================================================
# EXPECTED REQUIRED PARAMETERS (AUTHORITATIVE - DO NOT CHANGE)
# These are the MODEL-FACING required parameters, not server-injected ones.
# =============================================================================

EXPECTED_REQUIRED_PARAMS = {
    "get_deck_recommendations": ["format"],
    "calculate_deck_distance": ["format", "deck_name"],
    "get_collection_stats": [],
    "list_meta_decks": ["format"],
    "search_collection": [],
    "build_deck": ["theme"],
    "find_synergies": ["card_name"],
    "export_to_arena": ["cards", "lands"],
    "improve_deck": ["deck_text"],
    "get_deck_assumptions": ["format", "deck_name"],
    "stress_deck_assumption": ["format", "deck_name", "stress_type", "target"],
    "find_deck_breaking_point": ["format", "deck_name"],
}


# =============================================================================
# SERVER-INJECTED PARAMETERS (REMOVED FROM SCHEMA)
# =============================================================================

SERVER_INJECTED_PARAMS = ["user_id"]


# =============================================================================
# TOOL NAME TESTS
# =============================================================================


class TestToolNames:
    """Tests that tool names are unchanged."""

    def test_tool_count_unchanged(self) -> None:
        """Number of tools matches expected."""
        assert len(TOOL_DEFINITIONS) == len(EXPECTED_TOOL_NAMES)

    def test_all_expected_tools_present(self) -> None:
        """All expected tool names are present."""
        actual_names = [t.name for t in TOOL_DEFINITIONS]
        for expected_name in EXPECTED_TOOL_NAMES:
            assert expected_name in actual_names, f"Missing tool: {expected_name}"

    def test_no_unexpected_tools(self) -> None:
        """No unexpected tools were added."""
        actual_names = [t.name for t in TOOL_DEFINITIONS]
        for actual_name in actual_names:
            assert actual_name in EXPECTED_TOOL_NAMES, f"Unexpected tool: {actual_name}"

    def test_tool_order_preserved(self) -> None:
        """Tool order matches expected order."""
        actual_names = [t.name for t in TOOL_DEFINITIONS]
        assert actual_names == EXPECTED_TOOL_NAMES


# =============================================================================
# REQUIRED PARAMETER TESTS
# =============================================================================


class TestRequiredParameters:
    """Tests that required parameters are unchanged."""

    @pytest.mark.parametrize("tool_name", EXPECTED_TOOL_NAMES)
    def test_required_params_match(self, tool_name: str) -> None:
        """Required parameters match expected for each tool."""
        tool = next(t for t in TOOL_DEFINITIONS if t.name == tool_name)
        actual_required = tool.parameters.get("required", [])
        expected_required = EXPECTED_REQUIRED_PARAMS[tool_name]

        assert set(actual_required) == set(expected_required), (
            f"Tool '{tool_name}' required params mismatch. "
            f"Expected: {expected_required}, Got: {actual_required}"
        )


# =============================================================================
# SERVER-INJECTED PARAMETER TESTS
# =============================================================================


class TestServerInjectedParams:
    """Tests that server-injected params are removed from schemas."""

    @pytest.mark.parametrize("tool_name", EXPECTED_TOOL_NAMES)
    def test_user_id_not_in_schema(self, tool_name: str) -> None:
        """user_id is not in any tool's schema properties."""
        tool = next(t for t in TOOL_DEFINITIONS if t.name == tool_name)
        properties = tool.parameters.get("properties", {})

        for server_param in SERVER_INJECTED_PARAMS:
            assert server_param not in properties, (
                f"Tool '{tool_name}' should not have '{server_param}' in schema. "
                "This is a server-injected parameter."
            )

    @pytest.mark.parametrize("tool_name", EXPECTED_TOOL_NAMES)
    def test_user_id_not_required(self, tool_name: str) -> None:
        """user_id is not in any tool's required list."""
        tool = next(t for t in TOOL_DEFINITIONS if t.name == tool_name)
        required = tool.parameters.get("required", [])

        for server_param in SERVER_INJECTED_PARAMS:
            assert server_param not in required, (
                f"Tool '{tool_name}' should not require '{server_param}'. "
                "This is a server-injected parameter."
            )


# =============================================================================
# SCHEMA STRUCTURE TESTS
# =============================================================================


class TestSchemaStructure:
    """Tests that schemas are valid JSON Schema."""

    @pytest.mark.parametrize("tool_name", EXPECTED_TOOL_NAMES)
    def test_has_type_object(self, tool_name: str) -> None:
        """Each tool schema has type: object."""
        tool = next(t for t in TOOL_DEFINITIONS if t.name == tool_name)
        assert tool.parameters.get("type") == "object"

    @pytest.mark.parametrize("tool_name", EXPECTED_TOOL_NAMES)
    def test_has_properties(self, tool_name: str) -> None:
        """Each tool schema has a properties field."""
        tool = next(t for t in TOOL_DEFINITIONS if t.name == tool_name)
        assert "properties" in tool.parameters

    @pytest.mark.parametrize("tool_name", EXPECTED_TOOL_NAMES)
    def test_has_required(self, tool_name: str) -> None:
        """Each tool schema has a required field."""
        tool = next(t for t in TOOL_DEFINITIONS if t.name == tool_name)
        assert "required" in tool.parameters

    @pytest.mark.parametrize("tool_name", EXPECTED_TOOL_NAMES)
    def test_description_is_concise(self, tool_name: str) -> None:
        """Tool descriptions are concise (single sentence, < 100 chars)."""
        tool = next(t for t in TOOL_DEFINITIONS if t.name == tool_name)
        description = tool.description

        # Should be a single sentence (one period at end)
        assert description.endswith("."), f"Tool '{tool_name}' description should end with period"
        # Remove the final period and check there are no others
        inner = description[:-1]
        assert inner.count(".") == 0, (
            f"Tool '{tool_name}' description should be single sentence: {description}"
        )
        # Should be reasonably short
        assert len(description) < 100, (
            f"Tool '{tool_name}' description too long ({len(description)} chars): {description}"
        )


# =============================================================================
# PARAMETER DESCRIPTION TESTS
# =============================================================================


class TestParameterDescriptions:
    """Tests that parameter descriptions are concise."""

    @pytest.mark.parametrize("tool_name", EXPECTED_TOOL_NAMES)
    def test_param_descriptions_concise(self, tool_name: str) -> None:
        """Parameter descriptions are <= 8 words."""
        tool = next(t for t in TOOL_DEFINITIONS if t.name == tool_name)
        properties = tool.parameters.get("properties", {})

        for param_name, param_def in properties.items():
            description = param_def.get("description", "")
            word_count = len(description.split())
            assert word_count <= 8, (
                f"Tool '{tool_name}' param '{param_name}' description too long "
                f"({word_count} words): '{description}'"
            )


# =============================================================================
# EXECUTE_TOOL DISPATCH TESTS
# =============================================================================


class TestExecuteToolDispatch:
    """Tests that execute_tool handles all tools."""

    def test_unknown_tool_raises(self) -> None:
        """Unknown tool name raises ValueError."""
        import asyncio

        async def test():
            from unittest.mock import MagicMock

            mock_session = MagicMock()
            with pytest.raises(ValueError, match="Unknown tool"):
                await execute_tool(mock_session, "nonexistent_tool", {})

        asyncio.run(test())

    def test_all_tools_have_handler(self) -> None:
        """All defined tools have a handler in execute_tool."""
        import inspect

        from forgebreaker.mcp import tools as tools_module

        # Get the source of execute_tool
        source = inspect.getsource(tools_module.execute_tool)

        for tool_name in EXPECTED_TOOL_NAMES:
            # Check that the tool name appears in the dispatch logic
            assert f'"{tool_name}"' in source or f"'{tool_name}'" in source, (
                f"Tool '{tool_name}' not handled in execute_tool"
            )
