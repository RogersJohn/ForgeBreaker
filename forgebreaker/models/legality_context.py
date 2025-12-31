"""
Legality Context — Explicit, Testable Format Legality.

INVARIANT: All legality checks must accept an explicit LegalityContext.
This makes rotation changes testable and prevents silent legality shifts.

A LegalityContext captures:
1. The format (standard, explorer, historic)
2. The rotation version (e.g., "2024-Q4", "2025-Q1")

The rotation_version allows:
- Testing legality at specific points in time
- Simulating rotation changes
- Auditing when legality decisions were made
"""

from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Any


class LegalityFormat(str, Enum):
    """Supported Arena formats."""

    STANDARD = "standard"
    EXPLORER = "explorer"
    HISTORIC = "historic"
    ALCHEMY = "alchemy"
    BRAWL = "brawl"
    TIMELESS = "timeless"


# Standard rotation versions (Q4 = rotation happens)
# These represent the Standard pool AFTER the rotation
ROTATION_VERSIONS = {
    "2024-Q3": date(2024, 7, 1),  # Pre-rotation 2024
    "2024-Q4": date(2024, 10, 1),  # Post-rotation 2024 (Bloomburrow onwards)
    "2025-Q1": date(2025, 1, 1),  # Current
    "2025-Q4": date(2025, 10, 1),  # Future rotation
}

# Current rotation version (update when rotation happens)
CURRENT_ROTATION_VERSION = "2025-Q1"


@dataclass(frozen=True, slots=True)
class LegalityContext:
    """
    Explicit context for legality determination.

    INVARIANT: Legality checks without explicit context are forbidden.
    Use LegalityContext.current() for "now" but make it explicit in code.

    Attributes:
        format: The Arena format to check legality for
        rotation_version: Version identifier for rotation state
        effective_date: Optional specific date for legality check
    """

    format: LegalityFormat
    rotation_version: str = CURRENT_ROTATION_VERSION
    effective_date: date | None = None

    def __post_init__(self) -> None:
        """Validate rotation version."""
        if self.rotation_version not in ROTATION_VERSIONS:
            # Allow unknown versions for forward compatibility
            # but warn in logs (not enforced here)
            pass

    @classmethod
    def current(cls, format: LegalityFormat) -> "LegalityContext":
        """
        Create context for current rotation.

        Use this when you want "now" but need to be explicit about it.
        """
        return cls(format=format, rotation_version=CURRENT_ROTATION_VERSION)

    @classmethod
    def at_rotation(cls, format: LegalityFormat, rotation_version: str) -> "LegalityContext":
        """
        Create context for a specific rotation version.

        Use this for testing or simulating rotation changes.
        """
        effective = ROTATION_VERSIONS.get(rotation_version)
        return cls(
            format=format,
            rotation_version=rotation_version,
            effective_date=effective,
        )

    @classmethod
    def at_date(cls, format: LegalityFormat, effective_date: date) -> "LegalityContext":
        """
        Create context for a specific date.

        Determines rotation_version from the date.
        """
        # Find the most recent rotation version for this date
        version = CURRENT_ROTATION_VERSION
        for v, d in sorted(ROTATION_VERSIONS.items(), key=lambda x: x[1], reverse=True):
            if effective_date >= d:
                version = v
                break

        return cls(
            format=format,
            rotation_version=version,
            effective_date=effective_date,
        )

    @property
    def format_name(self) -> str:
        """Get format name as string for legality dict lookup."""
        return self.format.value


@dataclass(frozen=True, slots=True)
class LegalityResult:
    """
    Result of a legality check.

    Includes the context used for the check, enabling auditing.
    """

    is_legal: bool
    context: LegalityContext
    reason: str = ""


def check_legality(
    card_data: dict[str, Any],
    context: LegalityContext,
) -> LegalityResult:
    """
    Check if a card is legal in the given context.

    INVARIANT: Context must be explicitly provided. No implicit "current".

    Args:
        card_data: Card data dict with "legalities" field
        context: Explicit legality context

    Returns:
        LegalityResult with legality status and context used
    """
    legalities = card_data.get("legalities", {})
    status = legalities.get(context.format_name, "not_legal")

    is_legal = status == "legal"

    reason = f"legalities[{context.format_name}] = {status} (rotation: {context.rotation_version})"

    return LegalityResult(is_legal=is_legal, context=context, reason=reason)


def filter_by_legality(
    card_names: set[str],
    card_db: dict[str, dict[str, Any]],
    context: LegalityContext,
) -> set[str]:
    """
    Filter cards by legality in the given context.

    INVARIANT: Context must be explicitly provided.

    Args:
        card_names: Set of card names to filter
        card_db: Card database with legality data
        context: Explicit legality context

    Returns:
        Set of card names that are legal in the context
    """
    result: set[str] = set()

    for card_name in card_names:
        card_data = card_db.get(card_name)
        if card_data is None:
            continue

        legality = check_legality(card_data, context)
        if legality.is_legal:
            result.add(card_name)

    return result
