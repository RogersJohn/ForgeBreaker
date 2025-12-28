"""
Deck assumption surfacing.

This module surfaces observable characteristics of a decklist to help
players articulate their beliefs about how the deck should function.

IMPORTANT: This does NOT infer player intent or predict performance.
It provides starting points for players to examine and may use wrong.
The "typical ranges" are conventional baselines, not prescriptions.
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

# Conventional baselines for comparison (NOT prescriptions)
# These represent common patterns, not requirements.
# Deviating from these may be intentional and correct.

TYPICAL_CMC_BY_ARCHETYPE: dict[str, tuple[float, float]] = {
    "aggro": (1.5, 2.3),
    "midrange": (2.5, 3.5),
    "control": (3.0, 4.0),
    "combo": (2.0, 3.5),
}

TYPICAL_LANDS_BY_ARCHETYPE: dict[str, tuple[int, int]] = {
    "aggro": (20, 23),
    "midrange": (23, 26),
    "control": (25, 28),
    "combo": (22, 26),
}

TYPICAL_DRAW_DENSITY_BY_ARCHETYPE: dict[str, tuple[int, int]] = {
    "aggro": (0, 4),
    "midrange": (2, 6),
    "control": (4, 10),
    "combo": (4, 10),
}

# Disclaimer text for assumptions
BASELINE_DISCLAIMER = (
    "Typical ranges are based on common patterns for this archetype. "
    "Your deck may intentionally differ. This is not a recommendation."
)


def surface_assumptions(
    deck: MetaDeck,
    card_db: dict[str, dict[str, Any]],
) -> DeckAssumptionSet:
    """
    Surface observable characteristics of a deck for player examination.

    This does NOT infer what the player believes or predict how the deck
    will perform. It provides starting points for the player to examine
    their own assumptions about the deck.

    Args:
        deck: The deck to examine
        card_db: Scryfall card database for card properties

    Returns:
        DeckAssumptionSet with observable characteristics and conventional baselines
    """
    # Default to midrange if archetype unknown (this default is visible to the user)
    archetype = deck.archetype.lower() if deck.archetype else "midrange"
    if archetype not in ARCHETYPE_CURVES:
        archetype = "midrange"

    assumptions: list[DeckAssumption] = []

    # Surface each category of characteristics
    assumptions.extend(_surface_mana_curve_beliefs(deck, card_db, archetype))
    assumptions.extend(_surface_draw_consistency_beliefs(deck, card_db, archetype))
    assumptions.extend(_surface_key_card_beliefs(deck, card_db))
    assumptions.extend(_surface_interaction_beliefs(deck, card_db, archetype))

    # Calculate deviation from convention (NOT quality or likelihood of success)
    deviation, deviation_explanation = _calculate_deviation(assumptions, archetype)

    return DeckAssumptionSet(
        deck_name=deck.name,
        archetype=archetype,
        assumptions=assumptions,
        overall_fragility=deviation,
        fragility_explanation=deviation_explanation,
    )


# Keep old name as alias for backwards compatibility
extract_assumptions = surface_assumptions


def _surface_mana_curve_beliefs(
    deck: MetaDeck,
    card_db: dict[str, dict[str, Any]],
    archetype: str,
) -> list[DeckAssumption]:
    """Surface mana curve characteristics for player examination."""
    assumptions: list[DeckAssumption] = []

    # Observe the decklist
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

    # Compare to conventional baseline (not prescription)
    typical_cmc = TYPICAL_CMC_BY_ARCHETYPE.get(archetype, (2.0, 3.5))
    comparison = _compare_to_baseline(avg_cmc, typical_cmc[0], typical_cmc[1])

    assumptions.append(
        DeckAssumption(
            name="Mana Curve Belief",
            category=AssumptionCategory.MANA_CURVE,
            description=(
                f"This deck's average mana value is {avg_cmc:.2f}. "
                f"You believe this curve will function for your game plan."
            ),
            observed_value=round(avg_cmc, 2),
            typical_range=typical_cmc,
            health=comparison,
            explanation=_explain_cmc_belief(avg_cmc, typical_cmc, archetype),
            adjustable=True,
        )
    )

    # Land count observation
    typical_lands = TYPICAL_LANDS_BY_ARCHETYPE.get(archetype, (23, 26))
    land_comparison = _compare_to_baseline(land_count, typical_lands[0], typical_lands[1])

    assumptions.append(
        DeckAssumption(
            name="Land Count Belief",
            category=AssumptionCategory.MANA_CURVE,
            description=(
                f"This deck runs {land_count} lands. "
                f"You believe this is enough to cast your spells on curve."
            ),
            observed_value=land_count,
            typical_range=(float(typical_lands[0]), float(typical_lands[1])),
            health=land_comparison,
            explanation=_explain_land_belief(land_count, typical_lands, archetype),
            adjustable=True,
        )
    )

    # Early game density for aggro
    if archetype == "aggro":
        low_curve = curve.get(1, 0) + curve.get(2, 0)
        typical_low = (18, 24)
        low_comparison = _compare_to_baseline(low_curve, typical_low[0], typical_low[1])

        assumptions.append(
            DeckAssumption(
                name="Early Pressure Belief",
                category=AssumptionCategory.MANA_CURVE,
                description=(
                    f"This deck has {low_curve} cards at 1-2 mana. "
                    f"You believe this provides enough early pressure."
                ),
                observed_value=low_curve,
                typical_range=(float(typical_low[0]), float(typical_low[1])),
                health=low_comparison,
                explanation=(
                    f"Aggro decks often run 18-24 cards at 1-2 mana. "
                    f"This deck has {low_curve}. Whether this is enough depends on "
                    f"your game plan and meta expectations."
                ),
                adjustable=False,
            )
        )

    return assumptions


def _surface_draw_consistency_beliefs(
    deck: MetaDeck,
    card_db: dict[str, dict[str, Any]],
    archetype: str,
) -> list[DeckAssumption]:
    """Surface card draw characteristics for player examination."""
    assumptions: list[DeckAssumption] = []

    draw_keywords = ["draw a card", "draw two", "draw three", "scry", "look at the top", "surveil"]
    draw_count = 0

    for card_name, qty in deck.cards.items():
        card_data = card_db.get(card_name, {})
        oracle = card_data.get("oracle_text", "").lower()

        if any(kw in oracle for kw in draw_keywords):
            draw_count += qty

    typical_draw = TYPICAL_DRAW_DENSITY_BY_ARCHETYPE.get(archetype, (2, 6))
    comparison = _compare_to_baseline(draw_count, typical_draw[0], typical_draw[1])

    assumptions.append(
        DeckAssumption(
            name="Card Flow Belief",
            category=AssumptionCategory.DRAW_CONSISTENCY,
            description=(
                f"This deck has {draw_count} cards with draw/selection effects. "
                f"You believe this provides adequate card flow for your game plan."
            ),
            observed_value=draw_count,
            typical_range=(float(typical_draw[0]), float(typical_draw[1])),
            health=comparison,
            explanation=_explain_draw_belief(draw_count, typical_draw, archetype),
            adjustable=True,
        )
    )

    return assumptions


def _surface_key_card_beliefs(
    deck: MetaDeck,
    card_db: dict[str, dict[str, Any]],
) -> list[DeckAssumption]:
    """Surface key card dependencies for player examination."""
    assumptions: list[DeckAssumption] = []

    # Find 4x cards (player has chosen to maximize these)
    four_ofs = [name for name, qty in deck.cards.items() if qty == 4]

    # Filter to non-lands
    key_cards = []
    for card_name in four_ofs:
        card_data = card_db.get(card_name, {})
        if "Land" not in card_data.get("type_line", ""):
            key_cards.append(card_name)

    key_card_count = len(key_cards)

    # This is player choice, not optimization
    typical_range = (4.0, 10.0)
    comparison = AssumptionHealth.HEALTHY
    if key_card_count > 12 or key_card_count < 3:
        comparison = AssumptionHealth.WARNING

    assumptions.append(
        DeckAssumption(
            name="Key Card Dependency",
            category=AssumptionCategory.KEY_CARDS,
            description=(
                f"You're running {key_card_count} cards as 4x copies. "
                f"You believe these are essential to your strategy."
            ),
            observed_value=key_card_count,
            typical_range=typical_range,
            health=comparison,
            explanation=(
                f"Cards run as 4x are typically cards you want to draw every game. "
                f"This deck maximizes {key_card_count} cards: "
                f"{', '.join(key_cards[:5])}{'...' if len(key_cards) > 5 else ''}. "
                f"If these underperform, the deck's effectiveness may suffer."
            ),
            adjustable=False,
        )
    )

    if key_cards:
        assumptions.append(
            DeckAssumption(
                name="Must-Draw Belief",
                category=AssumptionCategory.KEY_CARDS,
                description=("These are cards you believe the deck needs to draw to function."),
                observed_value=key_cards[:5],
                typical_range=(0.0, 0.0),  # Not a numeric comparison
                health=AssumptionHealth.HEALTHY,
                explanation=(
                    "You've identified these as key cards by running 4 copies. "
                    "Consider: What happens if you don't draw them? "
                    "What happens if they're answered immediately?"
                ),
                adjustable=True,
            )
        )

    return assumptions


def _surface_interaction_beliefs(
    deck: MetaDeck,
    card_db: dict[str, dict[str, Any]],
    archetype: str,
) -> list[DeckAssumption]:
    """Surface interaction characteristics for player examination."""
    assumptions: list[DeckAssumption] = []

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

    typical_removal = ARCHETYPE_ROLE_TARGETS.get(archetype, {}).get("removal", 6)
    comparison = _compare_to_baseline(removal_count, typical_removal - 2, typical_removal + 4)

    assumptions.append(
        DeckAssumption(
            name="Interaction Belief",
            category=AssumptionCategory.INTERACTION_TIMING,
            description=(
                f"This deck has {removal_count} interaction spells. "
                f"You believe this is enough to handle opposing threats."
            ),
            observed_value=removal_count,
            typical_range=(float(max(0, typical_removal - 2)), float(typical_removal + 4)),
            health=comparison,
            explanation=_explain_interaction_belief(removal_count, typical_removal, archetype),
            adjustable=True,
        )
    )

    if removal_count > 0:
        instant_ratio = instant_removal / removal_count
        ratio_comparison = AssumptionHealth.HEALTHY
        if archetype == "control" and instant_ratio < 0.5:
            ratio_comparison = AssumptionHealth.WARNING

        assumptions.append(
            DeckAssumption(
                name="Response Timing Belief",
                category=AssumptionCategory.INTERACTION_TIMING,
                description=(
                    f"{instant_removal} of {removal_count} interaction spells are instant-speed. "
                    f"You believe this timing is sufficient for your game plan."
                ),
                observed_value=round(instant_ratio, 2),
                typical_range=(0.3, 1.0),
                health=ratio_comparison,
                explanation=(
                    f"Instant-speed interaction lets you respond on your opponent's turn. "
                    f"{int(instant_ratio * 100)}% of your interaction is instant-speed. "
                    f"Whether this is enough depends on the threats you expect to face."
                ),
                adjustable=False,
            )
        )

    return assumptions


def _compare_to_baseline(value: float, min_typical: float, max_typical: float) -> AssumptionHealth:
    """
    Compare a value to conventional baseline.

    This is NOT a quality judgment. It indicates deviation from convention.
    Deviation may be intentional and correct.
    """
    if min_typical <= value <= max_typical:
        return AssumptionHealth.HEALTHY

    if value < min_typical:
        deviation = (
            (min_typical - value) / min_typical if min_typical > 0 else abs(min_typical - value)
        )
    else:
        deviation = (
            (value - max_typical) / max_typical if max_typical > 0 else abs(value - max_typical)
        )

    if deviation > 0.25:
        return AssumptionHealth.CRITICAL
    return AssumptionHealth.WARNING


# Keep old name as alias
_calculate_health = _compare_to_baseline


def _calculate_deviation(
    assumptions: list[DeckAssumption],
    archetype: str,
) -> tuple[float, str]:
    """
    Calculate how much the deck deviates from conventional patterns.

    This is NOT a prediction of failure. It measures unconventionality.
    Unconventional decks may perform excellently.
    """
    if not assumptions:
        return 0.0, "No assumptions to examine."

    warnings = sum(1 for a in assumptions if a.health == AssumptionHealth.WARNING)
    criticals = sum(1 for a in assumptions if a.health == AssumptionHealth.CRITICAL)

    deviation = min(1.0, (warnings * 0.15) + (criticals * 0.3))

    if deviation < 0.2:
        explanation = (
            f"This {archetype} deck's characteristics match conventional patterns. "
            f"This doesn't guarantee success—it means the deck isn't unusual for its archetype."
        )
    elif deviation < 0.5:
        explanation = (
            f"This {archetype} deck differs from convention in {warnings} area(s). "
            f"This may be intentional. Consider whether these differences serve your game plan."
        )
    else:
        explanation = (
            f"This {archetype} deck differs significantly from typical builds "
            f"({criticals} major difference(s), {warnings} minor). "
            f"This isn't necessarily wrong—but you should understand why you're diverging."
        )

    return deviation, explanation


# Keep old name as alias
_calculate_fragility = _calculate_deviation


def _explain_cmc_belief(actual: float, typical: tuple[float, float], archetype: str) -> str:
    """Explain mana curve observation."""
    range_str = f"{typical[0]:.1f}-{typical[1]:.1f}"
    if typical[0] <= actual <= typical[1]:
        return (
            f"This matches the typical range ({range_str}) for {archetype} decks. "
            f"Whether this is correct for your specific game plan is for you to decide."
        )

    if actual < typical[0]:
        return (
            f"This is below the typical range ({range_str}) for {archetype}. "
            f"You believe the deck can function on a lower curve. "
            f"Consider: Will you run out of cards before closing the game?"
        )
    return (
        f"This is above the typical range ({range_str}) for {archetype}. "
        f"You believe the deck can afford a higher curve. "
        f"Consider: Can you survive long enough to cast your expensive spells?"
    )


def _explain_land_belief(actual: int, typical: tuple[int, int], archetype: str) -> str:
    """Explain land count observation."""
    if typical[0] <= actual <= typical[1]:
        return (
            f"This matches the typical range ({typical[0]}-{typical[1]}) for {archetype}. "
            f"Whether this is correct depends on your curve and mana requirements."
        )

    if actual < typical[0]:
        return (
            f"This is below typical ({typical[0]}-{typical[1]}) for {archetype}. "
            f"You believe the deck functions on fewer lands. "
            f"Consider: How often will you miss land drops that matter?"
        )
    return (
        f"This is above typical ({typical[0]}-{typical[1]}) for {archetype}. "
        f"You believe the extra lands are worth the flood risk. "
        f"Consider: Will you draw too many lands in long games?"
    )


def _explain_draw_belief(actual: int, typical: tuple[int, int], archetype: str) -> str:
    """Explain card draw observation."""
    if typical[0] <= actual <= typical[1]:
        return (
            f"This is typical for {archetype} decks. "
            f"Whether it's right for your game plan depends on how you expect games to go."
        )

    if actual < typical[0]:
        return (
            f"This is below typical ({typical[0]}-{typical[1]}) for {archetype}. "
            f"You believe your opening hand and topdecks will be sufficient. "
            f"Consider: What happens when you need to find a specific answer?"
        )
    return (
        f"This is above typical ({typical[0]}-{typical[1]}) for {archetype}. "
        f"You're investing in card flow. "
        f"Consider: Are you giving up early tempo for late-game consistency?"
    )


def _explain_interaction_belief(actual: int, typical: int, archetype: str) -> str:
    """Explain interaction observation."""
    base = (
        f"Convention suggests ~{typical} interaction spells for {archetype}. "
        f"This deck has {actual}. "
    )
    if actual < typical:
        base += (
            "You believe you can race or ignore opposing threats. "
            "Consider: What happens when you can't?"
        )
    else:
        base += (
            "You believe you need to answer opposing threats. "
            "Consider: Is this taking slots from your own game plan?"
        )
    return base
