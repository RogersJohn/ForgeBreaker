"""
Deck assumption extraction and analysis.

Analyzes a deck to identify the implicit assumptions it relies on,
making them explicit and inspectable for players.
"""

from typing import Any

from forgebreaker.models.assumptions import (
    AssumptionCategory,
    AssumptionHealth,
    DeckAssumption,
    DeckAssumptionSet,
)
from forgebreaker.models.deck import MetaDeck
from forgebreaker.services.deck_builder import ARCHETYPE_CURVES, ARCHETYPE_ROLE_TARGETS

# Expected mana curve distributions by archetype (average CMC)
ARCHETYPE_EXPECTED_CMC: dict[str, tuple[float, float]] = {
    "aggro": (1.5, 2.3),
    "midrange": (2.5, 3.5),
    "control": (3.0, 4.0),
    "combo": (2.0, 3.5),
}

# Expected land counts by archetype
ARCHETYPE_EXPECTED_LANDS: dict[str, tuple[int, int]] = {
    "aggro": (20, 23),
    "midrange": (23, 26),
    "control": (25, 28),
    "combo": (22, 26),
}

# Draw/selection density expectations (cards per 60)
ARCHETYPE_DRAW_DENSITY: dict[str, tuple[int, int]] = {
    "aggro": (0, 4),
    "midrange": (2, 6),
    "control": (4, 10),
    "combo": (4, 10),
}


def extract_assumptions(
    deck: MetaDeck,
    card_db: dict[str, dict[str, Any]],
) -> DeckAssumptionSet:
    """
    Extract all assumptions from a deck.

    Args:
        deck: The deck to analyze
        card_db: Scryfall card database for card properties

    Returns:
        DeckAssumptionSet with all identified assumptions
    """
    archetype = deck.archetype.lower() if deck.archetype else "midrange"
    if archetype not in ARCHETYPE_CURVES:
        archetype = "midrange"

    assumptions: list[DeckAssumption] = []

    # Extract each category of assumptions
    assumptions.extend(_extract_mana_curve_assumptions(deck, card_db, archetype))
    assumptions.extend(_extract_draw_consistency_assumptions(deck, card_db, archetype))
    assumptions.extend(_extract_key_card_assumptions(deck, card_db))
    assumptions.extend(_extract_interaction_timing_assumptions(deck, card_db, archetype))

    # Calculate overall fragility
    fragility, fragility_explanation = _calculate_fragility(assumptions, archetype)

    return DeckAssumptionSet(
        deck_name=deck.name,
        archetype=archetype,
        assumptions=assumptions,
        overall_fragility=fragility,
        fragility_explanation=fragility_explanation,
    )


def _extract_mana_curve_assumptions(
    deck: MetaDeck,
    card_db: dict[str, dict[str, Any]],
    archetype: str,
) -> list[DeckAssumption]:
    """Extract mana curve related assumptions."""
    assumptions: list[DeckAssumption] = []

    # Calculate actual mana curve
    curve: dict[int, int] = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0}
    total_cmc = 0.0
    nonland_count = 0
    land_count = 0

    for card_name, qty in deck.cards.items():
        card_data = card_db.get(card_name, {})
        type_line = card_data.get("type_line", "")

        if "Land" in type_line:
            land_count += qty
            continue

        cmc = card_data.get("cmc", 2)
        bucket = min(6, max(1, int(cmc))) if cmc > 0 else 1
        curve[bucket] += qty
        total_cmc += cmc * qty
        nonland_count += qty

    avg_cmc = total_cmc / nonland_count if nonland_count > 0 else 2.5

    # Mana curve assumption
    expected_cmc = ARCHETYPE_EXPECTED_CMC.get(archetype, (2.0, 3.5))
    cmc_health = _calculate_health(avg_cmc, expected_cmc[0], expected_cmc[1])

    assumptions.append(
        DeckAssumption(
            name="Average Mana Value",
            category=AssumptionCategory.MANA_CURVE,
            description=f"This deck's average mana value is {avg_cmc:.2f}",
            current_value=round(avg_cmc, 2),
            expected_range=expected_cmc,
            health=cmc_health,
            explanation=_explain_cmc(avg_cmc, expected_cmc, archetype),
            adjustable=True,
        )
    )

    # Land count assumption
    expected_lands = ARCHETYPE_EXPECTED_LANDS.get(archetype, (23, 26))
    land_health = _calculate_health(land_count, expected_lands[0], expected_lands[1])

    assumptions.append(
        DeckAssumption(
            name="Land Count",
            category=AssumptionCategory.MANA_CURVE,
            description=f"This deck runs {land_count} lands",
            current_value=land_count,
            expected_range=(float(expected_lands[0]), float(expected_lands[1])),
            health=land_health,
            explanation=_explain_lands(land_count, expected_lands, archetype),
            adjustable=True,
        )
    )

    # Low curve density (1-2 drops for aggro)
    if archetype == "aggro":
        low_curve = curve.get(1, 0) + curve.get(2, 0)
        expected_low = (18, 24)  # Aggro needs lots of cheap threats
        low_health = _calculate_health(low_curve, expected_low[0], expected_low[1])

        assumptions.append(
            DeckAssumption(
                name="Early Game Density",
                category=AssumptionCategory.MANA_CURVE,
                description=f"This deck has {low_curve} cards at 1-2 mana",
                current_value=low_curve,
                expected_range=(float(expected_low[0]), float(expected_low[1])),
                health=low_health,
                explanation=(
                    "Aggro decks typically need 18-24 cards at 1-2 mana "
                    f"to establish early pressure. This deck has {low_curve}."
                ),
                adjustable=False,
            )
        )

    return assumptions


def _extract_draw_consistency_assumptions(
    deck: MetaDeck,
    card_db: dict[str, dict[str, Any]],
    archetype: str,
) -> list[DeckAssumption]:
    """Extract card draw and selection assumptions."""
    assumptions: list[DeckAssumption] = []

    # Count draw/selection effects
    draw_keywords = ["draw a card", "draw two", "draw three", "scry", "look at the top", "surveil"]
    draw_count = 0

    for card_name, qty in deck.cards.items():
        card_data = card_db.get(card_name, {})
        oracle = card_data.get("oracle_text", "").lower()

        if any(kw in oracle for kw in draw_keywords):
            draw_count += qty

    expected_draw = ARCHETYPE_DRAW_DENSITY.get(archetype, (2, 6))
    draw_health = _calculate_health(draw_count, expected_draw[0], expected_draw[1])

    assumptions.append(
        DeckAssumption(
            name="Card Selection Density",
            category=AssumptionCategory.DRAW_CONSISTENCY,
            description=f"This deck has {draw_count} cards with draw/selection effects",
            current_value=draw_count,
            expected_range=(float(expected_draw[0]), float(expected_draw[1])),
            health=draw_health,
            explanation=_explain_draw(draw_count, expected_draw, archetype),
            adjustable=True,
        )
    )

    return assumptions


def _extract_key_card_assumptions(
    deck: MetaDeck,
    card_db: dict[str, dict[str, Any]],
) -> list[DeckAssumption]:
    """Extract key card dependency assumptions."""
    assumptions: list[DeckAssumption] = []

    # Find 4x cards (likely key cards)
    four_ofs = [name for name, qty in deck.cards.items() if qty == 4]

    # Filter to non-lands
    key_cards = []
    for card_name in four_ofs:
        card_data = card_db.get(card_name, {})
        if "Land" not in card_data.get("type_line", ""):
            key_cards.append(card_name)

    key_card_count = len(key_cards)

    # Having many 4x cards means high dependency on specific cards
    expected_range = (4.0, 10.0)  # 4-10 four-ofs is typical
    dependency_health = AssumptionHealth.HEALTHY
    if key_card_count > 12 or key_card_count < 3:
        dependency_health = AssumptionHealth.WARNING

    assumptions.append(
        DeckAssumption(
            name="Key Card Dependency",
            category=AssumptionCategory.KEY_CARDS,
            description=f"This deck has {key_card_count} cards that appear as 4x copies",
            current_value=key_card_count,
            expected_range=expected_range,
            health=dependency_health,
            explanation=(
                f"Cards run as 4x are typically essential to your strategy. "
                f"This deck depends on {key_card_count} such cards: "
                f"{', '.join(key_cards[:5])}{'...' if len(key_cards) > 5 else ''}."
            ),
            adjustable=False,
        )
    )

    # Check for unique effects (cards that do something no other card in the deck does)
    if key_cards:
        assumptions.append(
            DeckAssumption(
                name="Must-Draw Cards",
                category=AssumptionCategory.KEY_CARDS,
                description="These are the cards your deck most needs to function",
                current_value=key_cards[:5],  # Top 5 key cards
                expected_range=(0.0, 0.0),  # Not a numeric comparison
                health=AssumptionHealth.HEALTHY,
                explanation=(
                    "If any of these cards underperform or are removed, "
                    "your deck's effectiveness may drop significantly."
                ),
                adjustable=True,
            )
        )

    return assumptions


def _extract_interaction_timing_assumptions(
    deck: MetaDeck,
    card_db: dict[str, dict[str, Any]],
    archetype: str,
) -> list[DeckAssumption]:
    """Extract interaction timing assumptions."""
    assumptions: list[DeckAssumption] = []

    # Count removal and interaction
    removal_count = 0
    instant_removal = 0

    removal_keywords = [
        "destroy target",
        "exile target",
        "damage to any",
        "damage to target",
        "-X/-X",
    ]
    counter_keywords = ["counter target", "counter that"]

    for card_name, qty in deck.cards.items():
        card_data = card_db.get(card_name, {})
        oracle = card_data.get("oracle_text", "").lower()
        type_line = card_data.get("type_line", "").lower()

        is_removal = any(kw in oracle for kw in removal_keywords)
        is_counter = any(kw in oracle for kw in counter_keywords)

        if is_removal or is_counter:
            removal_count += qty
            if "instant" in type_line:
                instant_removal += qty

    # Expected removal by archetype
    expected_removal = ARCHETYPE_ROLE_TARGETS.get(archetype, {}).get("removal", 6)
    removal_health = _calculate_health(removal_count, expected_removal - 2, expected_removal + 4)

    assumptions.append(
        DeckAssumption(
            name="Removal Density",
            category=AssumptionCategory.INTERACTION_TIMING,
            description=f"This deck has {removal_count} removal/interaction spells",
            current_value=removal_count,
            expected_range=(float(max(0, expected_removal - 2)), float(expected_removal + 4)),
            health=removal_health,
            explanation=_explain_removal(removal_count, expected_removal, archetype),
            adjustable=True,
        )
    )

    # Instant-speed interaction ratio
    if removal_count > 0:
        instant_ratio = instant_removal / removal_count
        ratio_health = AssumptionHealth.HEALTHY
        if archetype == "control" and instant_ratio < 0.5:
            ratio_health = AssumptionHealth.WARNING

        assumptions.append(
            DeckAssumption(
                name="Instant-Speed Interaction",
                category=AssumptionCategory.INTERACTION_TIMING,
                description=(
                    f"{instant_removal} of {removal_count} interaction spells are instant-speed"
                ),
                current_value=round(instant_ratio, 2),
                expected_range=(0.3, 1.0),
                health=ratio_health,
                explanation=(
                    "Instant-speed removal lets you respond to threats on your opponent's turn. "
                    f"This deck has {int(instant_ratio * 100)}% instant-speed interaction."
                ),
                adjustable=False,
            )
        )

    return assumptions


def _calculate_health(value: float, min_expected: float, max_expected: float) -> AssumptionHealth:
    """Calculate health status based on expected range."""
    if min_expected <= value <= max_expected:
        return AssumptionHealth.HEALTHY

    # How far outside the range?
    if value < min_expected:
        deviation = (
            (min_expected - value) / min_expected if min_expected > 0 else abs(min_expected - value)
        )
    else:
        deviation = (
            (value - max_expected) / max_expected if max_expected > 0 else abs(value - max_expected)
        )

    if deviation > 0.25:
        return AssumptionHealth.CRITICAL
    return AssumptionHealth.WARNING


def _calculate_fragility(
    assumptions: list[DeckAssumption],
    archetype: str,
) -> tuple[float, str]:
    """Calculate overall deck fragility from assumptions."""
    if not assumptions:
        return 0.0, "No assumptions analyzed."

    warnings = sum(1 for a in assumptions if a.health == AssumptionHealth.WARNING)
    criticals = sum(1 for a in assumptions if a.health == AssumptionHealth.CRITICAL)

    # Fragility score: 0-1
    fragility = min(1.0, (warnings * 0.15) + (criticals * 0.3))

    if fragility < 0.2:
        explanation = (
            f"This {archetype} deck's assumptions are well within expected ranges. "
            "It should perform consistently under normal conditions."
        )
    elif fragility < 0.5:
        explanation = (
            f"This {archetype} deck has some assumptions outside typical ranges. "
            f"There are {warnings} warning(s) that may affect consistency."
        )
    else:
        explanation = (
            f"This {archetype} deck relies on assumptions that deviate "
            f"significantly from typical builds. "
            f"There are {criticals} critical issue(s) and {warnings} warning(s). "
            "Consider stress-testing to understand how this affects performance."
        )

    return fragility, explanation


def _explain_cmc(actual: float, expected: tuple[float, float], archetype: str) -> str:
    """Explain average CMC assumption."""
    range_str = f"{expected[0]:.1f}-{expected[1]:.1f}"
    if expected[0] <= actual <= expected[1]:
        return f"This is within the typical range ({range_str}) for {archetype} decks."

    if actual < expected[0]:
        return (
            f"This is below the typical range ({range_str}) for {archetype}. "
            "The deck may run out of gas quickly without card advantage."
        )
    return (
        f"This is above the typical range ({range_str}) for {archetype}. "
        "The deck may struggle with early game pressure."
    )


def _explain_lands(actual: int, expected: tuple[int, int], archetype: str) -> str:
    """Explain land count assumption."""
    if expected[0] <= actual <= expected[1]:
        return (
            f"This is within the typical range ({expected[0]}-{expected[1]}) for {archetype} decks."
        )

    if actual < expected[0]:
        return (
            f"This is below typical ({expected[0]}-{expected[1]}) for {archetype}. "
            "The deck assumes it will function on fewer lands, which increases mana screw risk."
        )
    return (
        f"This is above typical ({expected[0]}-{expected[1]}) for {archetype}. "
        "This reduces mana screw but may lead to flooding in longer games."
    )


def _explain_draw(actual: int, expected: tuple[int, int], archetype: str) -> str:
    """Explain card draw assumption."""
    if expected[0] <= actual <= expected[1]:
        return f"This is typical for {archetype} decks, providing adequate card flow."

    if actual < expected[0]:
        return (
            f"This is below typical ({expected[0]}-{expected[1]}) for {archetype}. "
            "The deck assumes its opening hand and topdecks will be sufficient."
        )
    return (
        f"This is above typical ({expected[0]}-{expected[1]}) for {archetype}. "
        "Strong card selection, but may trade early tempo for late-game consistency."
    )


def _explain_removal(actual: int, expected: int, archetype: str) -> str:
    """Explain removal density assumption."""
    base = f"For a {archetype} deck, {expected} interaction spells is typical. "
    base += f"This deck has {actual}. "
    if actual < expected:
        base += "Fewer spells means relying on racing opponents."
    return base
