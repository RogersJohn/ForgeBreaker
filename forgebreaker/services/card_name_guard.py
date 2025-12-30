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

import re
from dataclasses import dataclass

from forgebreaker.models.validated_deck import ValidatedDeck


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

    # Check for non-card endings
    name_lower = name.lower()
    return all(not name_lower.endswith(ending) for ending in _NON_CARD_ENDINGS)


def extract_potential_card_names(text: str) -> set[str]:
    """
    Extract all potential MTG card names from a text string.

    This is intentionally broad — it extracts anything that MIGHT
    be a card name. The guard will then validate each against the deck.

    Args:
        text: Text to scan for card names

    Returns:
        Set of potential card name strings
    """
    potential_names: set[str] = set()

    for pattern in _CARD_REFERENCE_PATTERNS:
        for match in pattern.finditer(text):
            # Get the card name group (varies by pattern)
            groups = match.groups()
            # Last group is typically the card name
            name = groups[-1] if groups else match.group(0)
            name = name.strip()

            if _is_likely_card_name(name):
                potential_names.add(name)

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

    leaked: list[str] = []
    for name in potential_names:
        if name not in allowed:
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
    result = validate_output_card_names(output, validated_deck, additional_allowed)

    if not result.valid:
        # Take the first leaked name for the error
        leaked = result.leaked_names[0]
        raise CardNameLeakageError(
            leaked_name=leaked,
            output_context=output,
            validated_deck=validated_deck,
        )

    return output


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
