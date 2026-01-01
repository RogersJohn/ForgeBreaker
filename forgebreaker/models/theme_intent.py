"""
Theme intent model for normalized tribal/deck theme semantics.

INVARIANT: Raw theme strings must never be used directly for card matching.
All theme matching must go through ThemeIntent normalization first.
"""

import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Known creature subtypes from MTG (lowercase for matching)
# This is a subset of common tribes - extensible as needed
KNOWN_TRIBES: frozenset[str] = frozenset(
    {
        "goblin",
        "elf",
        "human",
        "zombie",
        "vampire",
        "merfolk",
        "dragon",
        "angel",
        "demon",
        "wizard",
        "warrior",
        "knight",
        "soldier",
        "cleric",
        "rogue",
        "shaman",
        "druid",
        "elemental",
        "beast",
        "bird",
        "cat",
        "dog",
        "dinosaur",
        "spirit",
        "horror",
        "skeleton",
        "rat",
        "snake",
        "spider",
        "wolf",
        "bear",
        "giant",
        "troll",
        "ogre",
        "orc",
        "dwarf",
        "faerie",
        "pirate",
        "artifact",
        "enchantment",
        "sliver",
        "phyrexian",
        "eldrazi",
        "fungus",
        "saproling",
        "treefolk",
        "hydra",
        "sphinx",
        "kraken",
        "leviathan",
        "wurm",
        "golem",
        "construct",
        "myr",
        "thopter",
        "servo",
    }
)

# Words to strip from theme strings (noise words)
NOISE_WORDS: frozenset[str] = frozenset(
    {
        "tribal",
        "deck",
        "build",
        "me",
        "a",
        "the",
        "with",
        "around",
        "themed",
        "theme",
        "based",
        "type",
        "creature",
        "creatures",
    }
)


@dataclass(frozen=True, slots=True)
class ThemeIntent:
    """
    Normalized theme intent extracted from raw user input.

    This is the ONLY structure that should be used for card matching.
    Raw theme strings must be normalized through `normalize_theme()` first.

    Attributes:
        tribe: Extracted creature subtype (e.g., "goblin"), or None if not tribal
        raw_theme: Original theme string for fallback/logging
    """

    tribe: str | None
    raw_theme: str

    def has_tribe(self) -> bool:
        """Check if a tribe was successfully extracted."""
        return self.tribe is not None

    def __str__(self) -> str:
        if self.tribe:
            return f"ThemeIntent(tribe={self.tribe})"
        return f"ThemeIntent(raw={self.raw_theme})"


def normalize_theme(raw_theme: str) -> ThemeIntent:
    """
    Normalize a raw theme string into structured ThemeIntent.

    This function extracts tribe information from user phrases like:
    - "goblin tribal" -> ThemeIntent(tribe="goblin")
    - "goblin deck" -> ThemeIntent(tribe="goblin")
    - "tribal goblins" -> ThemeIntent(tribe="goblin")
    - "goblins" -> ThemeIntent(tribe="goblin")

    The normalization is DETERMINISTIC:
    - No embeddings
    - No fuzzy matching
    - No LLM involvement

    Args:
        raw_theme: Raw theme string from user input

    Returns:
        ThemeIntent with extracted tribe (if found) and original raw theme
    """
    if not raw_theme:
        return ThemeIntent(tribe=None, raw_theme=raw_theme)

    # Lowercase and tokenize
    theme_lower = raw_theme.lower().strip()
    tokens = re.split(r"[\s,;:]+", theme_lower)

    # Remove noise words
    meaningful_tokens = [t for t in tokens if t and t not in NOISE_WORDS]

    # Look for known tribes in tokens
    for token in meaningful_tokens:
        # Handle plurals (simple -s suffix)
        singular = token.rstrip("s") if token.endswith("s") and len(token) > 2 else token

        if token in KNOWN_TRIBES:
            logger.info(
                "THEME_NORMALIZED",
                extra={
                    "raw_theme": raw_theme,
                    "extracted_tribe": token,
                    "method": "exact_match",
                },
            )
            return ThemeIntent(tribe=token, raw_theme=raw_theme)

        if singular in KNOWN_TRIBES:
            logger.info(
                "THEME_NORMALIZED",
                extra={
                    "raw_theme": raw_theme,
                    "extracted_tribe": singular,
                    "method": "singular_match",
                },
            )
            return ThemeIntent(tribe=singular, raw_theme=raw_theme)

    # No tribe found - return with raw theme for fallback matching
    logger.info(
        "THEME_NORMALIZED",
        extra={
            "raw_theme": raw_theme,
            "extracted_tribe": None,
            "method": "no_tribe_found",
        },
    )
    return ThemeIntent(tribe=None, raw_theme=raw_theme)


def card_matches_tribe(
    card_name: str,
    card_data: dict,
    tribe: str,
) -> bool:
    """
    Check if a card matches a tribe using oracle data.

    Matching is done against:
    1. Oracle creature subtypes (primary) - e.g., "Creature — Goblin Rogue"
    2. Card name tokens (secondary) - e.g., "Goblin Maskmaker"

    This is DETERMINISTIC matching - no fuzzy logic.

    Args:
        card_name: Name of the card
        card_data: Scryfall card data with type_line
        tribe: Normalized tribe string (lowercase)

    Returns:
        True if card matches the tribe
    """
    tribe_lower = tribe.lower()

    # Primary: Check type line for creature subtype
    type_line = card_data.get("type_line", "").lower()

    # Parse subtypes from type line (after the "—" or "-")
    if "—" in type_line:
        subtypes_part = type_line.split("—")[1].strip()
        subtypes = subtypes_part.split()
        if tribe_lower in subtypes:
            return True
    elif "-" in type_line:
        # Some cards use regular hyphen
        subtypes_part = type_line.split("-")[1].strip()
        subtypes = subtypes_part.split()
        if tribe_lower in subtypes:
            return True

    # Secondary: Check if tribe appears in card name as a token
    name_lower = card_name.lower()
    name_tokens = re.split(r"[\s,\-']+", name_lower)
    return tribe_lower in name_tokens
