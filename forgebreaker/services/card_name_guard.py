"""
Card Name Guard — Final Output Barrier for Named Cards.

This module enforces the core invariant:

    No user-visible string may contain a card name unless that name
    is present in a ValidatedDeck object.

The guard scans output strings for potential MTG card name patterns
and validates each against the authoritative ValidatedDeck.

FAILURE MODE: If an unvalidated card name is detected, the guard
raises CardNameLeakageError. Failure is better than a lie.
"""

import logging
import re
import time
from dataclasses import dataclass

from forgebreaker.models.validated_deck import ValidatedDeck

logger = logging.getLogger(__name__)

# =============================================================================
# INSTRUMENTATION FOR PRODUCTION DEBUGGING
# =============================================================================
# These counters help diagnose performance and failure patterns.
# They are reset on module reload and are purely diagnostic.

_guard_invocation_count: int = 0
_guard_total_time_ms: float = 0.0
_guard_leak_count: int = 0


class CardNameLeakageError(Exception):
    """
    Raised when an unvalidated card name is detected in output.

    This is a SYSTEM INVARIANT failure — a card name appeared in
    user-visible output that was NOT in the ValidatedDeck.

    This error must never be silenced or downgraded to a warning.
    """

    def __init__(
        self,
        leaked_name: str,
        output_context: str,
        validated_deck: ValidatedDeck | None,
    ):
        self.leaked_name = leaked_name
        self.output_context = output_context[:200]  # Truncate for logging
        self.validated_deck = validated_deck
        deck_size = len(validated_deck) if validated_deck else 0
        super().__init__(
            f"INVARIANT VIOLATION: Card name '{leaked_name}' found in output "
            f"but not in validated deck ({deck_size} cards). "
            f"Context: {self.output_context}..."
        )


@dataclass(frozen=True)
class GuardResult:
    """Result of card name guard validation."""

    valid: bool
    leaked_names: tuple[str, ...]
    checked_count: int


# Pattern to detect MTG-style card references in output text.
# Matches patterns like:
# - "4x Lightning Bolt" or "4 Lightning Bolt"
# - "**Card Name**" (markdown bold)
# - "[Card Name]" (markdown link text or oracle reference)
# - "Replace X with Y" where X and Y are card names
#
# This is intentionally broad — we validate ALL potential card names.
_CARD_REFERENCE_PATTERNS = [
    # Quantity prefix: "4x Card Name" or "4 Card Name"
    re.compile(r"\b(\d+)x?\s+([A-Z][A-Za-z'\-,\s]+?)(?=\s*(?:\(|$|\n|,|\.|:))", re.MULTILINE),
    # Markdown bold: "**Card Name**"
    re.compile(r"\*\*([A-Z][A-Za-z'\-,\s]+?)\*\*"),
    # Bracket reference: "[Card Name]" or "[Card Name]:"
    re.compile(r"\[([A-Z][A-Za-z'\-,\s]+?)\]"),
]

# Common MTG card name patterns for validation
# Card names typically:
# - Start with capital letter
# - May contain apostrophes, commas, hyphens
# - Are 2-6 words typically
# - Don't end with common non-card words
_NON_CARD_ENDINGS = frozenset(
    [
        "analysis",
        "deck",
        "cards",
        "lands",
        "spells",
        "creatures",
        "colors",
        "curve",
        "tips",
        "warnings",
        "issues",
        "notes",
        "reference",
        "upgrades",
        "section",
        "breakdown",
        "count",
    ]
)

# MTG terminology that looks like card names but isn't
# These are exact matches (case-insensitive)
_NON_CARD_EXACT = frozenset(
    [
        "summon",  # Old type line word: "Summon - Dragon"
        "instant",
        "sorcery",
        "enchantment",
        "artifact",
        "creature",
        "planeswalker",
        "tribal",
        "legendary",
    ]
)


def canonical_card_key(name: str) -> str:
    """
    Return the canonical comparison key for a card name.

    - Strips subtitle after the first comma
    - Normalizes internal whitespace
    - Case-folds for comparison

    NOTE:
    This enforces existence-level validation, not identity resolution.
    Ambiguous base names (e.g. "Jace") are intentionally allowed.
    """
    # Strip after first comma
    base = name.split(",", 1)[0]
    # Normalize whitespace and case-fold
    return " ".join(base.split()).casefold()


def _is_likely_card_name(name: str) -> bool:
    """
    Check if a string is likely an MTG card name.

    Conservative: returns True if it MIGHT be a card name.
    We'd rather over-validate than miss a leak.
    """
    name = name.strip()

    # Too short or too long
    if len(name) < 3 or len(name) > 50:
        return False

    # Must start with capital
    if not name[0].isupper():
        return False

    name_lower = name.lower()

    # Check for exact non-card terms (MTG terminology)
    if name_lower in _NON_CARD_EXACT:
        return False

    # Check for non-card endings
    return all(not name_lower.endswith(ending) for ending in _NON_CARD_ENDINGS)


def extract_potential_card_names(text: str, log_matches: bool = False) -> set[str]:
    """
    Extract all potential MTG card names from a text string.

    This is intentionally broad — it extracts anything that MIGHT
    be a card name. The guard will then validate each against the deck.

    Args:
        text: Text to scan for card names
        log_matches: If True, log each pattern match for debugging

    Returns:
        Set of potential card name strings
    """
    potential_names: set[str] = set()

    pattern_names = ["quantity_prefix", "markdown_bold", "bracket_reference"]

    for i, pattern in enumerate(_CARD_REFERENCE_PATTERNS):
        for match in pattern.finditer(text):
            # Get the card name group (varies by pattern)
            groups = match.groups()
            # Last group is typically the card name
            name = groups[-1] if groups else match.group(0)
            name = name.strip()

            if _is_likely_card_name(name):
                potential_names.add(name)
                if log_matches:
                    logger.debug(
                        "GUARD_MATCH: pattern=%s, matched='%s', context='%s'",
                        pattern_names[i] if i < len(pattern_names) else f"pattern_{i}",
                        name,
                        match.group(0)[:50],
                    )

    return potential_names


def validate_output_card_names(
    output: str,
    validated_deck: ValidatedDeck,
    additional_allowed: frozenset[str] | None = None,
) -> GuardResult:
    """
    Validate that all card names in output are in the validated deck.

    This is the FINAL check before returning output to the user.
    Any unvalidated card name is a system invariant violation.

    Args:
        output: The output string to validate
        validated_deck: The authoritative source of allowed card names
        additional_allowed: Extra allowed names (e.g., from user's full collection)

    Returns:
        GuardResult with validation status and any leaked names
    """
    potential_names = extract_potential_card_names(output)

    if not potential_names:
        return GuardResult(valid=True, leaked_names=(), checked_count=0)

    allowed = validated_deck.cards
    if additional_allowed:
        allowed = allowed | additional_allowed

    # Build canonical key set for comparison (once per invocation)
    allowed_canonical = frozenset(canonical_card_key(name) for name in allowed)

    leaked: list[str] = []
    for name in potential_names:
        if canonical_card_key(name) not in allowed_canonical:
            leaked.append(name)

    return GuardResult(
        valid=len(leaked) == 0,
        leaked_names=tuple(leaked),
        checked_count=len(potential_names),
    )


def guard_output(
    output: str,
    validated_deck: ValidatedDeck,
    additional_allowed: frozenset[str] | None = None,
) -> str:
    """
    Guard output text against card name leakage.

    This function MUST be called before returning ANY user-visible
    response that may contain card names.

    Args:
        output: The output string to guard
        validated_deck: The authoritative source of allowed card names
        additional_allowed: Extra allowed names (e.g., collection cards)

    Returns:
        The output string (unchanged if valid)

    Raises:
        CardNameLeakageError: If any unvalidated card name is detected
    """
    global _guard_invocation_count, _guard_total_time_ms, _guard_leak_count

    _guard_invocation_count += 1
    invocation_id = _guard_invocation_count
    start_time = time.perf_counter()

    # Log invocation context
    deck_size = len(validated_deck)
    additional_size = len(additional_allowed) if additional_allowed else 0
    output_len = len(output)

    logger.info(
        "GUARD_INVOKE #%d: output_len=%d, deck_cards=%d, additional=%d",
        invocation_id,
        output_len,
        deck_size,
        additional_size,
    )

    # Log validated deck contents (truncated for large decks)
    deck_cards_preview = list(validated_deck.cards)[:10]
    logger.debug(
        "GUARD_DECK #%d: cards=%s%s",
        invocation_id,
        deck_cards_preview,
        "..." if deck_size > 10 else "",
    )

    result = validate_output_card_names(output, validated_deck, additional_allowed)

    elapsed_ms = (time.perf_counter() - start_time) * 1000
    _guard_total_time_ms += elapsed_ms

    # Log extracted names
    if result.checked_count > 0:
        logger.info(
            "GUARD_EXTRACT #%d: found %d potential card names in output",
            invocation_id,
            result.checked_count,
        )

    if not result.valid:
        _guard_leak_count += 1
        # Log ALL leaked names, not just the first
        logger.warning(
            "GUARD_LEAK #%d: leaked_names=%s, output_preview='%s'",
            invocation_id,
            result.leaked_names,
            output[:200].replace("\n", "\\n"),
        )
        logger.info(
            "GUARD_STATS: total_invocations=%d, total_time_ms=%.2f, total_leaks=%d",
            _guard_invocation_count,
            _guard_total_time_ms,
            _guard_leak_count,
        )
        # Take the first leaked name for the error
        leaked = result.leaked_names[0]
        raise CardNameLeakageError(
            leaked_name=leaked,
            output_context=output,
            validated_deck=validated_deck,
        )

    logger.info(
        "GUARD_PASS #%d: elapsed_ms=%.2f, checked=%d names",
        invocation_id,
        elapsed_ms,
        result.checked_count,
    )

    return output


def get_guard_stats() -> dict[str, int | float]:
    """
    Get instrumentation statistics for the guard.

    Returns:
        Dict with invocation count, total time, and leak count
    """
    return {
        "invocation_count": _guard_invocation_count,
        "total_time_ms": round(_guard_total_time_ms, 2),
        "leak_count": _guard_leak_count,
        "avg_time_ms": (
            round(_guard_total_time_ms / _guard_invocation_count, 2)
            if _guard_invocation_count > 0
            else 0.0
        ),
    }


def reset_guard_stats() -> None:
    """Reset instrumentation counters (for testing)."""
    global _guard_invocation_count, _guard_total_time_ms, _guard_leak_count
    _guard_invocation_count = 0
    _guard_total_time_ms = 0.0
    _guard_leak_count = 0


def create_refusal_response(error: CardNameLeakageError) -> dict[str, str | bool]:
    """
    Create a refusal response for a card name leakage error.

    This is the correct response when the system detects it would
    have produced invalid output. Refusal is better than a lie.

    Args:
        error: The leakage error that was caught

    Returns:
        Dict with refusal message suitable for user display
    """
    return {
        "success": False,
        "error": "card_name_invariant_violation",
        "message": (
            "The system attempted to produce an invalid card reference. "
            "This request has been refused to maintain output integrity. "
            "Please try a different request."
        ),
        "detail": f"Detected unvalidated card: '{error.leaked_name}'",
    }
