"""
Card synergy finder.

Identifies cards that work well together based on mechanics.
"""

from dataclasses import dataclass
from typing import Any

from forgebreaker.models.collection import Collection

# Synergy patterns: (trigger_keyword, synergy_keywords)
SYNERGY_PATTERNS: list[tuple[str, list[str]]] = [
    # Sacrifice synergies
    (
        "sacrifice",
        ["dies", "leaves the battlefield", "blood token", "food token", "treasure token"],
    ),
    # Graveyard synergies
    ("graveyard", ["mill", "dies", "flashback", "escape", "unearth"]),
    # Token synergies
    ("token", ["create", "populate", "convoke", "go wide"]),
    # Enchantment synergies
    ("enchantment", ["constellation", "enchantress", "aura"]),
    # Artifact synergies
    ("artifact", ["affinity", "improvise", "metalcraft"]),
    # +1/+1 counter synergies
    ("+1/+1 counter", ["proliferate", "evolve", "adapt", "modify"]),
    # Life gain synergies
    ("life", ["lifelink", "soul warden", "ajani's pridemate"]),
    # Spell synergies
    ("instant", ["prowess", "magecraft", "storm"]),
    ("sorcery", ["prowess", "magecraft", "storm"]),
]


@dataclass
class SynergyResult:
    """Cards that synergize with a given card."""

    source_card: str
    synergy_type: str
    synergistic_cards: list[tuple[str, int, str]]  # (name, qty, reason)


def find_synergies(
    card_name: str,
    collection: Collection,
    card_db: dict[str, dict[str, Any]],
    max_results: int = 20,
) -> SynergyResult | None:
    """
    Find cards in collection that synergize with a given card.

    Args:
        card_name: Card to find synergies for
        collection: User's collection
        card_db: Card database
        max_results: Maximum synergistic cards to return

    Returns:
        SynergyResult with synergistic cards, or None if card not found
    """
    card_data = card_db.get(card_name)
    if not card_data:
        return None

    oracle = card_data.get("oracle_text", "").lower()
    type_line = card_data.get("type_line", "").lower()

    # Determine what synergy patterns this card triggers
    synergy_keywords: set[str] = set()
    synergy_type = "general"

    for trigger, keywords in SYNERGY_PATTERNS:
        if trigger.lower() in oracle or trigger.lower() in type_line:
            synergy_keywords.update(kw.lower() for kw in keywords)
            synergy_type = trigger

    if not synergy_keywords:
        # No specific synergy found, look for type-based synergies.
        # Use only broad type keywords here; detailed mechanics are in SYNERGY_PATTERNS.
        if "creature" in type_line:
            synergy_keywords = {"creature", "tribal"}
            synergy_type = "creature"
        elif "enchantment" in type_line:
            synergy_keywords = {"enchantment"}
            synergy_type = "enchantment"
        elif "artifact" in type_line:
            synergy_keywords = {"artifact"}
            synergy_type = "artifact"

    # Find synergistic cards in collection
    synergistic: list[tuple[str, int, str]] = []

    for owned_name, qty in collection.cards.items():
        if owned_name == card_name:
            continue

        owned_data = card_db.get(owned_name)
        if not owned_data:
            continue

        owned_oracle = owned_data.get("oracle_text", "").lower()
        owned_type = owned_data.get("type_line", "").lower()

        for keyword in synergy_keywords:
            if keyword in owned_oracle or keyword in owned_type:
                reason = f"Has '{keyword}'"
                synergistic.append((owned_name, qty, reason))
                break

    # Sort by quantity and limit
    synergistic.sort(key=lambda x: -x[1])
    synergistic = synergistic[:max_results]

    return SynergyResult(
        source_card=card_name,
        synergy_type=synergy_type,
        synergistic_cards=synergistic,
    )


def format_synergy_results(result: SynergyResult) -> str:
    """Format synergy results for display."""
    if not result.synergistic_cards:
        return f"No synergistic cards found for {result.source_card} in your collection."

    lines = [
        f"## Cards that synergize with {result.source_card}",
        f"*Synergy type: {result.synergy_type}*\n",
    ]

    for name, qty, reason in result.synergistic_cards:
        lines.append(f"- {qty}x **{name}** - {reason}")

    return "\n".join(lines)
