"""
Stress testing analysis for decks.

Stress testing explores hypothetical scenarios to help players examine
their beliefs about what their deck needs to function.

A breaking point is NOT a numeric threshold. It occurs when a specific
player belief can no longer be reasonably held under the scenario.

This is exploration, not prediction.
"""

from typing import Any

from forgebreaker.analysis.assumptions import surface_assumptions
from forgebreaker.models.assumptions import (
    AssumptionCategory,
    AssumptionHealth,
    DeckAssumptionSet,
)
from forgebreaker.models.deck import MetaDeck
from forgebreaker.models.stress import (
    BreakingPointAnalysis,
    StressedAssumption,
    StressResult,
    StressScenario,
    StressType,
)


def apply_stress(
    deck: MetaDeck,
    card_db: dict[str, dict[str, Any]],
    scenario: StressScenario,
) -> StressResult:
    """
    Explore what happens to deck beliefs under a hypothetical scenario.

    This does NOT predict how the deck will perform. It helps players
    examine which of their beliefs might not hold under certain conditions.

    Args:
        deck: The deck to explore
        card_db: Scryfall card database
        scenario: The hypothetical scenario to explore

    Returns:
        StressResult with insight into how beliefs change under stress
    """
    # Get baseline assumptions
    baseline = surface_assumptions(deck, card_db)

    # Apply stress based on type
    if scenario.stress_type == StressType.UNDERPERFORM:
        return _apply_underperform_stress(deck, card_db, baseline, scenario)
    elif scenario.stress_type == StressType.MISSING:
        return _apply_missing_stress(deck, card_db, baseline, scenario)
    elif scenario.stress_type == StressType.DELAYED:
        return _apply_delayed_stress(deck, card_db, baseline, scenario)
    elif scenario.stress_type == StressType.HOSTILE_META:
        return _apply_hostile_meta_stress(deck, card_db, baseline, scenario)

    # Fallback for unknown stress types
    return StressResult(
        deck_name=deck.name,
        scenario=scenario,
        original_fragility=baseline.overall_fragility,
        stressed_fragility=baseline.overall_fragility,
        exploration_summary="Unknown stress type - no changes applied.",
    )


def find_breaking_point(
    deck: MetaDeck,
    card_db: dict[str, dict[str, Any]],
) -> BreakingPointAnalysis:
    """
    Identify which belief fails first under increasing stress.

    This explores which assumption is most sensitive to change—
    not a prediction of failure, but insight into deck dependencies.

    Args:
        deck: The deck to explore
        card_db: Scryfall card database

    Returns:
        BreakingPointAnalysis identifying the most vulnerable belief
    """
    baseline = surface_assumptions(deck, card_db)

    # Test each assumption category with increasing intensity
    first_violated_result: StressResult | None = None
    first_violation_intensity = 1.1  # Start higher than max

    # Test key card stress
    key_cards_assumptions = baseline.get_by_category(AssumptionCategory.KEY_CARDS)
    for assumption in key_cards_assumptions:
        if isinstance(assumption.observed_value, list) and assumption.observed_value:
            # Test removing key cards
            for card in assumption.observed_value[:3]:  # Test top 3 key cards
                for intensity in [0.25, 0.5, 0.75, 1.0]:
                    scenario = StressScenario(
                        stress_type=StressType.MISSING,
                        target=card,
                        intensity=intensity,
                        description=f"What if {card} is unavailable?",
                    )
                    result = apply_stress(deck, card_db, scenario)
                    if result.assumption_violated and intensity < first_violation_intensity:
                        first_violation_intensity = intensity
                        first_violated_result = result

    # Test mana curve stress
    for intensity in [0.25, 0.5, 0.75, 1.0]:
        scenario = StressScenario(
            stress_type=StressType.DELAYED,
            target="mana_curve",
            intensity=intensity,
            description="What if mana development is delayed?",
        )
        result = apply_stress(deck, card_db, scenario)
        if result.assumption_violated and intensity < first_violation_intensity:
            first_violation_intensity = intensity
            first_violated_result = result

    # Test hostile meta
    for intensity in [0.25, 0.5, 0.75, 1.0]:
        scenario = StressScenario(
            stress_type=StressType.HOSTILE_META,
            target="interaction",
            intensity=intensity,
            description="What if opponents have more answers?",
        )
        result = apply_stress(deck, card_db, scenario)
        if result.assumption_violated and intensity < first_violation_intensity:
            first_violation_intensity = intensity
            first_violated_result = result

    if first_violated_result:
        violated = first_violated_result.violated_belief or "Unknown"
        insight = (
            f"The belief '{violated}' is most sensitive to stress. "
            f"Given {first_violated_result.scenario.description.lower()}, "
            f"this belief may no longer hold. "
            f"{first_violated_result.violation_explanation}"
        )
        return BreakingPointAnalysis(
            deck_name=deck.name,
            most_vulnerable_belief=violated,
            stress_threshold=first_violation_intensity,
            failing_scenario=first_violated_result.scenario,
            exploration_insight=insight,
        )

    return BreakingPointAnalysis(
        deck_name=deck.name,
        most_vulnerable_belief="None identified",
        stress_threshold=1.0,
        failing_scenario=None,
        exploration_insight=(
            "No beliefs were clearly invalidated under the tested scenarios. "
            "This suggests the deck's assumptions may be robust to these "
            "specific stress types, though other scenarios may reveal vulnerabilities."
        ),
    )


def _apply_underperform_stress(
    deck: MetaDeck,
    card_db: dict[str, dict[str, Any]],  # noqa: ARG001
    baseline: DeckAssumptionSet,
    scenario: StressScenario,
) -> StressResult:
    """
    Explore what happens if key cards are drawn less frequently.

    This examines the belief that the deck will find its key pieces.
    """
    affected: list[StressedAssumption] = []
    violated_belief = ""
    violation_explanation = ""

    # Find key card assumptions
    key_assumption = next(
        (a for a in baseline.assumptions if a.name == "Key Card Dependency"),
        None,
    )

    if key_assumption and isinstance(key_assumption.observed_value, int):
        # Reduce effective key card count based on intensity
        reduction = int(key_assumption.observed_value * scenario.intensity * 0.5)
        new_value = max(0, key_assumption.observed_value - reduction)

        new_health = _recalculate_health(
            new_value, key_assumption.typical_range[0], key_assumption.typical_range[1]
        )

        # Determine if this violates the belief
        belief_violated = new_health == AssumptionHealth.CRITICAL
        violation_reason = ""
        if belief_violated:
            violation_reason = (
                f"The belief that the deck has enough redundant key cards "
                f"fails because effective 4x cards drops to {new_value}, "
                f"below what the archetype typically requires."
            )
            violated_belief = key_assumption.name
            violation_explanation = violation_reason

        affected.append(
            StressedAssumption(
                name=key_assumption.name,
                original_value=key_assumption.observed_value,
                stressed_value=new_value,
                original_health=key_assumption.health.value,
                stressed_health=new_health.value,
                change_explanation=(
                    f"If key cards underperform, effective 4x cards "
                    f"would drop from {key_assumption.observed_value} to {new_value}."
                ),
                belief_violated=belief_violated,
                violation_reason=violation_reason,
            )
        )

    # Calculate new fragility
    original_fragility = baseline.overall_fragility
    stressed_fragility = _calculate_stressed_fragility(baseline, affected, scenario.intensity)

    return StressResult(
        deck_name=deck.name,
        scenario=scenario,
        original_fragility=original_fragility,
        stressed_fragility=stressed_fragility,
        affected_assumptions=affected,
        assumption_violated=bool(violated_belief),
        violated_belief=violated_belief,
        violation_explanation=violation_explanation,
        exploration_summary=_generate_exploration_summary(
            "key card underperformance", scenario.target, affected, violated_belief
        ),
        considerations=_generate_underperform_considerations(baseline, scenario),
    )


def _apply_missing_stress(
    deck: MetaDeck,
    card_db: dict[str, dict[str, Any]],  # noqa: ARG001
    baseline: DeckAssumptionSet,
    scenario: StressScenario,
) -> StressResult:
    """
    Explore what happens if a card is unavailable.

    This examines the belief that specific cards will be in the deck
    and drawable.
    """
    affected: list[StressedAssumption] = []
    violated_belief = ""
    violation_explanation = ""

    target_card = scenario.target

    # Check if target is a key card
    must_draw = next(
        (a for a in baseline.assumptions if a.name == "Must-Draw Cards"),
        None,
    )

    is_key_card = bool(
        must_draw
        and isinstance(must_draw.observed_value, list)
        and target_card in must_draw.observed_value
    )

    if is_key_card and must_draw:
        new_value = [c for c in must_draw.observed_value if c != target_card]
        health_degraded = len(new_value) < len(must_draw.observed_value)

        # This belief is violated if the card was critical
        belief_violated = health_degraded and scenario.intensity >= 0.75
        violation_reason = ""
        if belief_violated:
            violation_reason = (
                f"The belief that '{target_card}' will be available fails. "
                f"This deck relies on drawing this card, and without it, "
                f"the deck's core strategy may not function as intended."
            )
            violated_belief = "Must-Draw Cards"
            violation_explanation = violation_reason

        affected.append(
            StressedAssumption(
                name="Must-Draw Cards",
                original_value=must_draw.observed_value,
                stressed_value=new_value,
                original_health=must_draw.health.value,
                stressed_health="warning" if health_degraded else "healthy",
                change_explanation=(
                    f"If '{target_card}' is unavailable, the deck loses "
                    f"a card it was built around finding."
                ),
                belief_violated=belief_violated,
                violation_reason=violation_reason,
            )
        )

    # Also examine key card dependency count
    key_dep = next(
        (a for a in baseline.assumptions if a.name == "Key Card Dependency"),
        None,
    )

    if key_dep and isinstance(key_dep.observed_value, int):
        new_count = max(0, key_dep.observed_value - 1) if is_key_card else key_dep.observed_value
        if new_count != key_dep.observed_value:
            new_health = _recalculate_health(
                new_count, key_dep.typical_range[0], key_dep.typical_range[1]
            )

            belief_violated_here = new_health == AssumptionHealth.CRITICAL
            violation_reason_here = ""
            if belief_violated_here and not violated_belief:
                violation_reason_here = (
                    f"The belief that the deck has enough key cards fails. "
                    f"Losing '{target_card}' reduces 4x card count to {new_count}, "
                    f"which may be insufficient for consistent draws."
                )
                violated_belief = key_dep.name
                violation_explanation = violation_reason_here

            affected.append(
                StressedAssumption(
                    name=key_dep.name,
                    original_value=key_dep.observed_value,
                    stressed_value=new_count,
                    original_health=key_dep.health.value,
                    stressed_health=new_health.value,
                    change_explanation=(
                        f"Without '{target_card}', 4x card count drops from "
                        f"{key_dep.observed_value} to {new_count}."
                    ),
                    belief_violated=belief_violated_here,
                    violation_reason=violation_reason_here,
                )
            )

    original_fragility = baseline.overall_fragility
    stressed_fragility = _calculate_stressed_fragility(
        baseline, affected, scenario.intensity, is_key_card
    )

    return StressResult(
        deck_name=deck.name,
        scenario=scenario,
        original_fragility=original_fragility,
        stressed_fragility=stressed_fragility,
        affected_assumptions=affected,
        assumption_violated=bool(violated_belief),
        violated_belief=violated_belief,
        violation_explanation=violation_explanation,
        exploration_summary=_generate_exploration_summary(
            f"'{target_card}' unavailability", target_card, affected, violated_belief
        ),
        considerations=_generate_missing_considerations(target_card, is_key_card),
    )


def _apply_delayed_stress(
    deck: MetaDeck,
    card_db: dict[str, dict[str, Any]],  # noqa: ARG001
    baseline: DeckAssumptionSet,
    scenario: StressScenario,
) -> StressResult:
    """
    Explore what happens if mana development is delayed.

    This examines beliefs about hitting land drops and casting spells on curve.
    """
    affected: list[StressedAssumption] = []
    violated_belief = ""
    violation_explanation = ""

    # Find mana curve assumptions
    cmc_assumption = next(
        (a for a in baseline.assumptions if a.name == "Average Mana Value"),
        None,
    )

    if cmc_assumption and isinstance(cmc_assumption.observed_value, int | float):
        # Increase effective CMC (simulating delayed development)
        cmc_increase = cmc_assumption.observed_value * scenario.intensity * 0.3
        new_cmc = cmc_assumption.observed_value + cmc_increase

        new_health = _recalculate_health(
            new_cmc, cmc_assumption.typical_range[0], cmc_assumption.typical_range[1]
        )

        belief_violated = new_health == AssumptionHealth.CRITICAL
        violation_reason = ""
        if belief_violated:
            violation_reason = (
                f"The belief that the deck can cast spells on curve fails. "
                f"With delayed mana, effective mana value rises to {new_cmc:.2f}, "
                f"meaning the deck cannot execute its game plan on time."
            )
            violated_belief = cmc_assumption.name
            violation_explanation = violation_reason

        affected.append(
            StressedAssumption(
                name=cmc_assumption.name,
                original_value=round(cmc_assumption.observed_value, 2),
                stressed_value=round(new_cmc, 2),
                original_health=cmc_assumption.health.value,
                stressed_health=new_health.value,
                change_explanation=(
                    f"If mana is delayed, effective mana value rises "
                    f"from {cmc_assumption.observed_value:.2f} to {new_cmc:.2f}."
                ),
                belief_violated=belief_violated,
                violation_reason=violation_reason,
            )
        )

    # Also examine land count perception
    land_assumption = next(
        (a for a in baseline.assumptions if a.name == "Land Count"),
        None,
    )

    if land_assumption and isinstance(land_assumption.observed_value, int | float):
        # Effectively fewer lands (simulating screw)
        land_reduction = int(land_assumption.observed_value * scenario.intensity * 0.2)
        new_lands = land_assumption.observed_value - land_reduction

        new_health = _recalculate_health(
            new_lands, land_assumption.typical_range[0], land_assumption.typical_range[1]
        )

        belief_violated_here = new_health == AssumptionHealth.CRITICAL
        violation_reason_here = ""
        if belief_violated_here and not violated_belief:
            violation_reason_here = (
                f"The belief that the deck has enough mana sources fails. "
                f"With effective lands dropping to {new_lands}, "
                f"the deck cannot reliably cast its spells."
            )
            violated_belief = land_assumption.name
            violation_explanation = violation_reason_here

        affected.append(
            StressedAssumption(
                name=land_assumption.name,
                original_value=land_assumption.observed_value,
                stressed_value=new_lands,
                original_health=land_assumption.health.value,
                stressed_health=new_health.value,
                change_explanation=(
                    f"If mana is problematic, effective lands drop "
                    f"from {land_assumption.observed_value} to {new_lands}."
                ),
                belief_violated=belief_violated_here,
                violation_reason=violation_reason_here,
            )
        )

    original_fragility = baseline.overall_fragility
    stressed_fragility = _calculate_stressed_fragility(baseline, affected, scenario.intensity)

    return StressResult(
        deck_name=deck.name,
        scenario=scenario,
        original_fragility=original_fragility,
        stressed_fragility=stressed_fragility,
        affected_assumptions=affected,
        assumption_violated=bool(violated_belief),
        violated_belief=violated_belief,
        violation_explanation=violation_explanation,
        exploration_summary=_generate_exploration_summary(
            "mana delays", "mana development", affected, violated_belief
        ),
        considerations=_generate_delayed_considerations(baseline),
    )


def _apply_hostile_meta_stress(
    deck: MetaDeck,
    card_db: dict[str, dict[str, Any]],  # noqa: ARG001
    baseline: DeckAssumptionSet,
    scenario: StressScenario,
) -> StressResult:
    """
    Explore what happens when facing more interaction than expected.

    This examines beliefs about threat resolution and protection.
    """
    affected: list[StressedAssumption] = []
    violated_belief = ""
    violation_explanation = ""

    # Find interaction timing assumptions
    removal_assumption = next(
        (a for a in baseline.assumptions if a.name == "Removal Density"),
        None,
    )

    # In a hostile meta, your interaction may be insufficient
    if removal_assumption and isinstance(removal_assumption.observed_value, int | float):
        # Hostile meta means you need MORE interaction
        needed_increase = int(removal_assumption.observed_value * scenario.intensity * 0.5)
        effective_shortfall = needed_increase

        new_health = (
            AssumptionHealth.CRITICAL
            if effective_shortfall > 4
            else AssumptionHealth.WARNING
            if effective_shortfall > 2
            else removal_assumption.health
        )

        belief_violated = new_health == AssumptionHealth.CRITICAL
        violation_reason = ""
        if belief_violated:
            violation_reason = (
                f"The belief that the deck has enough interaction fails. "
                f"Against a hostile meta with more threats to answer, "
                f"the current {removal_assumption.observed_value} removal spells "
                f"may be insufficient by {needed_increase} or more."
            )
            violated_belief = removal_assumption.name
            violation_explanation = violation_reason

        affected.append(
            StressedAssumption(
                name=removal_assumption.name,
                original_value=removal_assumption.observed_value,
                stressed_value=removal_assumption.observed_value,  # Value same, context changed
                original_health=removal_assumption.health.value,
                stressed_health=new_health.value,
                change_explanation=(
                    f"In a hostile meta, the deck may need {needed_increase} more "
                    f"interaction spells than the current {removal_assumption.observed_value}."
                ),
                belief_violated=belief_violated,
                violation_reason=violation_reason,
            )
        )

    # Key cards are more likely to be answered
    key_assumption = next(
        (a for a in baseline.assumptions if a.name == "Key Card Dependency"),
        None,
    )

    if key_assumption:
        original_health = key_assumption.health
        # High key card dependency becomes riskier in hostile meta
        stressed_health = (
            AssumptionHealth.WARNING
            if original_health == AssumptionHealth.HEALTHY
            else AssumptionHealth.CRITICAL
        )

        belief_violated_here = stressed_health == AssumptionHealth.CRITICAL
        violation_reason_here = ""
        if belief_violated_here and not violated_belief:
            violation_reason_here = (
                "The belief that key cards will resolve fails. "
                "In a hostile meta, opponents have more answers, "
                "and the deck's reliance on specific cards becomes a liability."
            )
            violated_belief = key_assumption.name
            violation_explanation = violation_reason_here

        affected.append(
            StressedAssumption(
                name=key_assumption.name,
                original_value=key_assumption.observed_value,
                stressed_value=key_assumption.observed_value,
                original_health=original_health.value,
                stressed_health=stressed_health.value,
                change_explanation=(
                    "In a hostile meta, relying on key cards becomes riskier "
                    "as opponents are more likely to have answers."
                ),
                belief_violated=belief_violated_here,
                violation_reason=violation_reason_here,
            )
        )

    original_fragility = baseline.overall_fragility
    stressed_fragility = _calculate_stressed_fragility(baseline, affected, scenario.intensity)

    return StressResult(
        deck_name=deck.name,
        scenario=scenario,
        original_fragility=original_fragility,
        stressed_fragility=stressed_fragility,
        affected_assumptions=affected,
        assumption_violated=bool(violated_belief),
        violated_belief=violated_belief,
        violation_explanation=violation_explanation,
        exploration_summary=_generate_exploration_summary(
            "hostile meta", "opponent interaction", affected, violated_belief
        ),
        considerations=_generate_hostile_meta_considerations(baseline),
    )


def _recalculate_health(value: float, min_typical: float, max_typical: float) -> AssumptionHealth:
    """Recalculate health for a new value against typical range."""
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


def _calculate_stressed_fragility(
    baseline: DeckAssumptionSet,
    affected: list[StressedAssumption],
    intensity: float,
    key_card_affected: bool = False,
) -> float:
    """Calculate new fragility score after stress."""
    base_fragility = baseline.overall_fragility

    # Count health degradations
    degradations = sum(1 for a in affected if a.stressed_health != a.original_health)

    critical_count = sum(1 for a in affected if a.stressed_health == "critical")

    # Fragility increases based on degradations and intensity
    increase = (degradations * 0.1 + critical_count * 0.15) * intensity

    # Key card removal has extra impact
    if key_card_affected:
        increase += 0.15 * intensity

    return min(1.0, base_fragility + increase)


def _generate_exploration_summary(
    stress_name: str,
    target: str,
    affected: list[StressedAssumption],
    violated_belief: str,
) -> str:
    """Generate human-readable exploration summary."""
    if violated_belief:
        return (
            f"Given {stress_name} affecting {target}, "
            f"the belief '{violated_belief}' can no longer be reasonably held. "
            f"This suggests the deck depends on this assumption more than others."
        )

    if affected:
        changes = [a.name for a in affected if a.stressed_health != a.original_health]
        if changes:
            return (
                f"Exploring {stress_name} on {target} reveals that "
                f"{', '.join(changes)} would be affected. "
                f"However, no beliefs are clearly invalidated under this scenario."
            )

    return (
        f"Exploring {stress_name} on {target} suggests minimal impact "
        f"on the deck's core assumptions under this scenario."
    )


def _generate_underperform_considerations(
    baseline: DeckAssumptionSet, scenario: StressScenario
) -> list[str]:
    """Generate considerations for underperformance exploration."""
    considerations = []

    if scenario.intensity > 0.5:
        considerations.append("Consider: Are there backup cards that could serve similar roles?")

    draw_assumption = next(
        (a for a in baseline.assumptions if a.name == "Card Selection Density"),
        None,
    )
    if draw_assumption and draw_assumption.health != AssumptionHealth.HEALTHY:
        considerations.append(
            "Consider: Would more card draw help find key pieces more consistently?"
        )

    considerations.append(
        "Consider: Which key cards could the deck function without, and which are critical?"
    )

    return considerations


def _generate_missing_considerations(target_card: str, is_key_card: bool) -> list[str]:
    """Generate considerations for missing card exploration."""
    considerations = []

    if is_key_card:
        considerations.append(
            f"Consider: Are there functional replacements for '{target_card}' in the format?"
        )
        considerations.append(
            "Consider: Could the deck be built to be less dependent on this specific card?"
        )
    else:
        considerations.append(
            f"'{target_card}' removal had limited impact - this slot may be flexible."
        )

    return considerations


def _generate_delayed_considerations(baseline: DeckAssumptionSet) -> list[str]:
    """Generate considerations for mana delay exploration."""
    considerations = []

    land_assumption = next(
        (a for a in baseline.assumptions if a.name == "Land Count"),
        None,
    )

    if land_assumption and isinstance(land_assumption.observed_value, int | float):
        if land_assumption.observed_value < land_assumption.typical_range[0]:
            considerations.append("Consider: Would adding more lands reduce mana screw frequency?")
        considerations.append(
            "Consider: Could the mana curve be lowered to reduce land dependency?"
        )

    considerations.append("Consider: How aggressively should you mulligan for land-heavy hands?")

    return considerations


def _generate_hostile_meta_considerations(baseline: DeckAssumptionSet) -> list[str]:
    """Generate considerations for hostile meta exploration."""
    considerations = []

    removal_assumption = next(
        (a for a in baseline.assumptions if a.name == "Removal Density"),
        None,
    )

    if (
        removal_assumption
        and isinstance(removal_assumption.observed_value, int | float)
        and removal_assumption.observed_value < 6
    ):
        considerations.append("Consider: Would more interaction in the maindeck or sideboard help?")

    considerations.append(
        "Consider: Are there threats with built-in protection (hexproof, ward, etc.)?"
    )
    considerations.append(
        "Consider: Could a faster game plan get under interaction-heavy opponents?"
    )

    return considerations
