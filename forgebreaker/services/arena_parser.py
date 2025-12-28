"""
Arena Deck Parser.

THIS MODULE HANDLES SYNTAX ONLY.

=============================================================================
RESPONSIBILITY BOUNDARY
=============================================================================

This module ONLY extracts structure from raw Arena deck text.
It does NOT validate or sanitize.

Parser success does NOT imply the data is valid or safe.

The parser produces UNTRUSTED intermediate structures that MUST be
passed through the sanitizer before use.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# =============================================================================
# PARSED STRUCTURES (UNTRUSTED)
# =============================================================================


@dataclass
class ParsedCardEntry:
    """
    A card entry extracted from parsing. NOT YET VALIDATED.

    This is an UNTRUSTED intermediate structure.
    Do not use outside the parser/sanitizer boundary.
    """

    quantity_str: str  # Raw string, not yet validated as int
    card_name: str  # Raw string, not yet validated
    set_code: str | None  # May be None if format doesn't include it
    collector_number: str | None  # May be None if format doesn't include it
    line_number: int  # For error reporting


@dataclass
class ParsedSection:
    """
    A parsed section with its entries.

    Section names are stored as-parsed (not normalized).
    """

    name: str  # Section name as parsed (e.g., "Deck", "Sideboard")
    name_lower: str  # Lowercase for comparison
    entries: list[ParsedCardEntry]
    line_number: int  # Line where section header appeared


@dataclass
class ParsedDeckStructure:
    """
    Complete parsed deck structure. NOT YET VALIDATED.

    This is an UNTRUSTED intermediate structure.
    The sanitizer MUST validate this before use.
    """

    sections: list[ParsedSection]
    unparseable_lines: list[tuple[int, str]]  # (line_number, line_content)


# =============================================================================
# PARSER ERROR
# =============================================================================


class ArenaParseError(Exception):
    """
    Raised when parsing cannot extract ANY structure.

    This is distinct from validation errors - it means the input
    is so malformed that we cannot even extract structure from it.
    """

    def __init__(self, line_number: int, line_content: str, reason: str) -> None:
        self.line_number = line_number
        self.line_content = line_content
        self.reason = reason
        super().__init__(f"Parse error at line {line_number}: {reason}")


# =============================================================================
# PARSER
# =============================================================================


class ArenaParser:
    """
    Parser for Arena deck text.

    This extracts STRUCTURE ONLY. It does not validate values.
    The output is UNTRUSTED and must be sanitized.

    Usage:
        parser = ArenaParser()
        parsed = parser.parse(raw_text)
        # parsed is UNTRUSTED - must sanitize before use
    """

    # Pattern to match Arena format: "4 Card Name (SET) 123"
    _FULL_FORMAT_PATTERN = re.compile(r"^(\d+)\s+(.+?)\s+\(([A-Z0-9]+)\)\s+(\S+)$")

    # Pattern to match simple format: "4 Card Name" (no set info)
    _SIMPLE_FORMAT_PATTERN = re.compile(r"^(\d+)\s+(.+)$")

    # Known section headers (lowercase)
    KNOWN_SECTIONS: frozenset[str] = frozenset(
        {
            "deck",
            "sideboard",
            "commander",
            "companion",
        }
    )

    def parse(self, raw_input: str) -> ParsedDeckStructure:
        """
        Parse raw Arena deck text to intermediate structure.

        This extracts structure ONLY. It does not validate values.
        The returned structure is UNTRUSTED.

        Args:
            raw_input: Raw Arena deck text

        Returns:
            ParsedDeckStructure with extracted sections and entries
        """
        lines = raw_input.split("\n")

        sections: list[ParsedSection] = []
        unparseable_lines: list[tuple[int, str]] = []

        # Default section for cards before any header
        current_section: ParsedSection | None = None

        for line_num, line in enumerate(lines, 1):
            stripped = line.strip()

            # Skip empty lines
            if not stripped:
                continue

            # Check for section header
            stripped_lower = stripped.lower()
            if self._is_section_header(stripped, stripped_lower):
                # Start new section
                current_section = ParsedSection(
                    name=stripped,
                    name_lower=stripped_lower,
                    entries=[],
                    line_number=line_num,
                )
                sections.append(current_section)
                continue

            # Try to parse as card entry
            entry = self._parse_card_line(stripped, line_num)
            if entry is not None:
                # If no section yet, create implicit "deck" section
                if current_section is None:
                    current_section = ParsedSection(
                        name="Deck",
                        name_lower="deck",
                        entries=[],
                        line_number=0,  # Implicit section
                    )
                    sections.append(current_section)

                current_section.entries.append(entry)
            else:
                # Line could not be parsed
                unparseable_lines.append((line_num, stripped))

        return ParsedDeckStructure(
            sections=sections,
            unparseable_lines=unparseable_lines,
        )

    def _is_section_header(self, _line: str, line_lower: str) -> bool:
        """
        Check if a line is a section header.

        Returns True for known section names (case-insensitive).
        """
        # Known section names
        if line_lower in self.KNOWN_SECTIONS:
            return True

        # Also match with trailing colon (e.g., "Deck:")
        if line_lower.endswith(":"):
            base = line_lower[:-1]
            if base in self.KNOWN_SECTIONS:
                return True

        return False

    def _parse_card_line(self, line: str, line_num: int) -> ParsedCardEntry | None:
        """
        Parse a single card line.

        Returns None if line doesn't match any known format.
        This is PARSING ONLY - no validation of values.
        """
        # Try full Arena format first: "4 Card Name (SET) 123"
        match = self._FULL_FORMAT_PATTERN.match(line)
        if match:
            qty_str, name, set_code, collector_num = match.groups()
            return ParsedCardEntry(
                quantity_str=qty_str,
                card_name=name,
                set_code=set_code,
                collector_number=collector_num,
                line_number=line_num,
            )

        # Try simple format: "4 Card Name"
        match = self._SIMPLE_FORMAT_PATTERN.match(line)
        if match:
            qty_str, name = match.groups()
            return ParsedCardEntry(
                quantity_str=qty_str,
                card_name=name.strip(),
                set_code=None,
                collector_number=None,
                line_number=line_num,
            )

        return None


# =============================================================================
# PUBLIC API
# =============================================================================


def parse_arena_deck(raw_input: str) -> ParsedDeckStructure:
    """
    Parse raw Arena deck text.

    This is a convenience function that creates a parser and parses.

    Args:
        raw_input: Raw Arena deck text

    Returns:
        UNTRUSTED ParsedDeckStructure - must be sanitized before use
    """
    parser = ArenaParser()
    return parser.parse(raw_input)
