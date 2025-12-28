"""
Arena Deck Formatter.

THIS MODULE HANDLES OUTPUT RENDERING ONLY.

=============================================================================
RESPONSIBILITY BOUNDARY
=============================================================================

This module ONLY formats validated deck data for output.
It accepts TRUSTED SanitizedDeck objects and produces Arena format strings.

This module does NOT validate - it trusts its input is already sanitized.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from forgebreaker.services.arena_sanitizer import SanitizedCard, SanitizedDeck


def format_deck_for_arena(deck: SanitizedDeck) -> str:
    """
    Format a sanitized deck as Arena import text.

    Args:
        deck: A TRUSTED SanitizedDeck (already validated)

    Returns:
        Arena format string ready for import
    """
    lines: list[str] = ["Deck"]

    for card in deck.cards:
        lines.append(_format_card_line(card))

    if deck.sideboard:
        lines.append("")
        lines.append("Sideboard")
        for card in deck.sideboard:
            lines.append(_format_card_line(card))

    return "\n".join(lines)


def _format_card_line(card: SanitizedCard) -> str:
    """Format a single card line in Arena format."""
    return f"{card.quantity} {card.name} ({card.set_code}) {card.collector_number}"
