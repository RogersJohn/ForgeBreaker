"""
Stress testing analysis for decks.

Applies stress scenarios to deck assumptions and measures the impact
on deck fragility and performance expectations.
"""

from typing import Any

from forgebreaker.analysis.assumptions import extract_assumptions
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
    Apply a stress scenario to a deck and measure the impact.

    Args:
        deck: The deck to stress
        card_db: Scryfall card database
        scenario: The stress scenario to apply

    Returns:
        StressResult with before/after comparison and explanations
    """
    # Get baseline assumptions
    baseline = extract_assumptions(deck, card_db)

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
        explanation="Unknown stress type - no changes applied.",
    )


def find_breaking_point(
    deck: MetaDeck,
    card_db: dict[str, dict[str, Any]],
) -> BreakingPointAnalysis:
    """
    Find the weakest point in a deck by testing multiple stress scenarios.

    Args:
        deck: The deck to analyze
        card_db: Scryfall card database

    Returns:
        BreakingPointAnalysis identifying the most vulnerable assumption
    """
    baseline = extract_assumptions(deck, card_db)

    # Test each assumption category with increasing intensity
    worst_result: StressResult | None = None
    lowest_intensity_break = 1.1  # Start higher than max

    # Test key card stress
    key_cards_assumptions = baseline.get_by_category(AssumptionCategory.KEY_CARDS)
    for assumption in key_cards_assumptions:
        if isinstance(assumption.current_value, list) and assumption.current_value:
            # Test removing key cards
            for card in assumption.current_value[:3]:  # Test top 3 key cards
                for intensity in [0.25, 0.5, 0.75, 1.0]:
                    scenario = StressScenario(
                        stress_type=StressType.MISSING,
                        target=card,
                        intensity=intensity,
                        description=f"Remove copies of {card}",
                    )
                    result = apply_stress(deck, card_db, scenario)
                    if result.breaking_point and intensity < lowest_intensity_break:
                        lowest_intensity_break = intensity
                        worst_result = result

    # Test mana curve stress
    for intensity in [0.25, 0.5, 0.75, 1.0]:
        scenario = StressScenario(
            stress_type=StressType.DELAYED,
            target="mana_curve",
            intensity=intensity,
            description="Delay mana development",
        )
        result = apply_stress(deck, card_db, scenario)
        if result.breaking_point and intensity < lowest_intensity_break:
            lowest_intensity_break = intensity
            worst_result = result

    # Test hostile meta
    for intensity in [0.25, 0.5, 0.75, 1.0]:
        scenario = StressScenario(
            stress_type=StressType.HOSTILE_META,
            target="interaction",
            intensity=intensity,
            description="Face more interaction",
        )
        result = apply_stress(deck, card_db, scenario)
        if result.breaking_point and intensity < lowest_intensity_break:
            lowest_intensity_break = intensity
            worst_result = result

    # Calculate resilience (inverse of how easily it breaks)
    # Early break = low resilience, never broke = max resilience
    resilience = lowest_intensity_break if lowest_intensity_break <= 1.0 else 1.0

    if worst_result:
        weakest = (
            worst_result.affected_assumptions[0].name
            if worst_result.affected_assumptions
            else "Unknown"
        )
        explanation = (
            f"The deck's weakest point is '{weakest}'. "
            f"At {int(lowest_intensity_break * 100)}% stress intensity, "
            f"the deck's fragility increases significantly. "
            f"{worst_result.explanation}"
        )
        return BreakingPointAnalysis(
            deck_name=deck.name,
            weakest_assumption=weakest,
            breaking_intensity=lowest_intensity_break,
            breaking_scenario=worst_result.scenario,
            resilience_score=resilience,
            explanation=explanation,
        )

    return BreakingPointAnalysis(
        deck_name=deck.name,
        weakest_assumption="None found",
        breaking_intensity=1.0,
        breaking_scenario=None,
        resilience_score=1.0,
        explanation=(
            "This deck showed no clear breaking points under stress testing. "
            "It appears resilient to the tested scenarios."
        ),
    )


def _apply_underperform_stress(
    deck: MetaDeck,
    card_db: dict[str, dict[str, Any]],  # noqa: ARG001  Required by factory interface
    baseline: DeckAssumptionSet,
    scenario: StressScenario,
) -> StressResult:
    """
    Simulate key cards underperforming (drawing less frequently).

    This stress type reduces the effective copy count of targeted cards,
    simulating games where you don't draw your key pieces.
    """
    affected: list[StressedAssumption] = []

    # Find key card assumptions
    key_assumption = next(
        (a for a in baseline.assumptions if a.name == "Key Card Dependency"),
        None,
    )

    if key_assumption and isinstance(key_assumption.current_value, int):
        # Reduce effective key card count based on intensity
        reduction = int(key_assumption.current_value * scenario.intensity * 0.5)
        new_value = max(0, key_assumption.current_value - reduction)

        new_health = _recalculate_health(
            new_value, key_assumption.expected_range[0], key_assumption.expected_range[1]
        )

        affected.append(
            StressedAssumption(
                name=key_assumption.name,
                original_value=key_assumption.current_value,
                stressed_value=new_value,
                original_health=key_assumption.health.value,
                stressed_health=new_health.value,
                change_explanation=(
                    f"With key cards underperforming, effective 4x cards "
                    f"drops from {key_assumption.current_value} to {new_value}."
                ),
            )
        )

    # Calculate new fragility
    original_fragility = baseline.overall_fragility
    stressed_fragility = _calculate_stressed_fragility(baseline, affected, scenario.intensity)
    breaking_point = stressed_fragility > 0.7

    recommendations = _generate_underperform_recommendations(baseline, scenario)

    return StressResult(
        deck_name=deck.name,
        scenario=scenario,
        original_fragility=original_fragility,
        stressed_fragility=stressed_fragility,
        affected_assumptions=affected,
        breaking_point=breaking_point,
        explanation=_generate_stress_explanation(
            "underperformance", scenario.target,
            original_fragility, stressed_fragility, breaking_point
        ),
        recommendations=recommendations,
    )


def _apply_missing_stress(
    deck: MetaDeck,
    card_db: dict[str, dict[str, Any]],  # noqa: ARG001  Required by factory interface
    baseline: DeckAssumptionSet,
    scenario: StressScenario,
) -> StressResult:
    """
    Simulate missing copies of a card (can't draw or removed).

    This tests what happens if a key card isn't in your deck or
    you never draw it.
    """
    affected: list[StressedAssumption] = []

    target_card = scenario.target
    copies_to_remove = int(4 * scenario.intensity)  # At 100%, remove all 4 copies

    # Check if target is a key card
    must_draw = next(
        (a for a in baseline.assumptions if a.name == "Must-Draw Cards"),
        None,
    )

    is_key_card = (
        must_draw
        and isinstance(must_draw.current_value, list)
        and target_card in must_draw.current_value
    )

    if is_key_card and must_draw:
        new_value = [c for c in must_draw.current_value if c != target_card]
        affected.append(
            StressedAssumption(
                name="Must-Draw Cards",
                original_value=must_draw.current_value,
                stressed_value=new_value,
                original_health=must_draw.health.value,
                stressed_health=(
                    "warning" if len(new_value) < len(must_draw.current_value)
                    else "healthy"
                ),
                change_explanation=(
                    f"Removing {copies_to_remove} copies of {target_card} "
                    f"eliminates it from must-draw cards."
                ),
            )
        )

    # Also affect key card dependency count
    key_dep = next(
        (a for a in baseline.assumptions if a.name == "Key Card Dependency"),
        None,
    )

    if key_dep and isinstance(key_dep.current_value, int):
        new_count = max(0, key_dep.current_value - 1) if is_key_card else key_dep.current_value
        if new_count != key_dep.current_value:
            new_health = _recalculate_health(
                new_count, key_dep.expected_range[0], key_dep.expected_range[1]
            )
            affected.append(
                StressedAssumption(
                    name=key_dep.name,
                    original_value=key_dep.current_value,
                    stressed_value=new_count,
                    original_health=key_dep.health.value,
                    stressed_health=new_health.value,
                    change_explanation=(
                        f"Losing {target_card} reduces 4x card count from "
                        f"{key_dep.current_value} to {new_count}."
                    ),
                )
            )

    original_fragility = baseline.overall_fragility
    stressed_fragility = _calculate_stressed_fragility(
        baseline, affected, scenario.intensity, is_key_card
    )
    breaking_point = stressed_fragility > 0.7 or (is_key_card and scenario.intensity >= 0.75)

    return StressResult(
        deck_name=deck.name,
        scenario=scenario,
        original_fragility=original_fragility,
        stressed_fragility=stressed_fragility,
        affected_assumptions=affected,
        breaking_point=breaking_point,
        explanation=_generate_stress_explanation(
            "card removal", target_card, original_fragility, stressed_fragility, breaking_point
        ),
        recommendations=_generate_missing_recommendations(target_card, is_key_card),
    )


def _apply_delayed_stress(
    deck: MetaDeck,
    card_db: dict[str, dict[str, Any]],  # noqa: ARG001  Required by factory interface
    baseline: DeckAssumptionSet,
    scenario: StressScenario,
) -> StressResult:
    """
    Simulate delayed mana development (mana screw, missing land drops).

    This tests what happens when the deck's curve is effectively shifted up.
    """
    affected: list[StressedAssumption] = []

    # Find mana curve assumptions
    cmc_assumption = next(
        (a for a in baseline.assumptions if a.name == "Average Mana Value"),
        None,
    )

    if cmc_assumption and isinstance(cmc_assumption.current_value, int | float):
        # Increase effective CMC (simulating delayed development)
        cmc_increase = cmc_assumption.current_value * scenario.intensity * 0.3
        new_cmc = cmc_assumption.current_value + cmc_increase

        new_health = _recalculate_health(
            new_cmc, cmc_assumption.expected_range[0], cmc_assumption.expected_range[1]
        )

        affected.append(
            StressedAssumption(
                name=cmc_assumption.name,
                original_value=round(cmc_assumption.current_value, 2),
                stressed_value=round(new_cmc, 2),
                original_health=cmc_assumption.health.value,
                stressed_health=new_health.value,
                change_explanation=(
                    f"Delayed development increases effective mana value "
                    f"from {cmc_assumption.current_value:.2f} to {new_cmc:.2f}."
                ),
            )
        )

    # Also affect land count perception
    land_assumption = next(
        (a for a in baseline.assumptions if a.name == "Land Count"),
        None,
    )

    if land_assumption and isinstance(land_assumption.current_value, int | float):
        # Effectively fewer lands (simulating screw)
        land_reduction = int(land_assumption.current_value * scenario.intensity * 0.2)
        new_lands = land_assumption.current_value - land_reduction

        new_health = _recalculate_health(
            new_lands, land_assumption.expected_range[0], land_assumption.expected_range[1]
        )

        affected.append(
            StressedAssumption(
                name=land_assumption.name,
                original_value=land_assumption.current_value,
                stressed_value=new_lands,
                original_health=land_assumption.health.value,
                stressed_health=new_health.value,
                change_explanation=(
                    f"Mana problems reduce effective lands "
                    f"from {land_assumption.current_value} to {new_lands}."
                ),
            )
        )

    original_fragility = baseline.overall_fragility
    stressed_fragility = _calculate_stressed_fragility(baseline, affected, scenario.intensity)
    breaking_point = stressed_fragility > 0.7

    return StressResult(
        deck_name=deck.name,
        scenario=scenario,
        original_fragility=original_fragility,
        stressed_fragility=stressed_fragility,
        affected_assumptions=affected,
        breaking_point=breaking_point,
        explanation=_generate_stress_explanation(
            "mana delays", "mana development",
            original_fragility, stressed_fragility, breaking_point
        ),
        recommendations=_generate_delayed_recommendations(baseline),
    )


def _apply_hostile_meta_stress(
    deck: MetaDeck,
    card_db: dict[str, dict[str, Any]],  # noqa: ARG001  Required by factory interface
    baseline: DeckAssumptionSet,
    scenario: StressScenario,
) -> StressResult:
    """
    Simulate facing more interaction than expected.

    This tests what happens when opponents have more answers.
    """
    affected: list[StressedAssumption] = []

    # Find interaction timing assumptions
    removal_assumption = next(
        (a for a in baseline.assumptions if a.name == "Removal Density"),
        None,
    )

    # In a hostile meta, your interaction matters more but may be outpaced
    if removal_assumption and isinstance(removal_assumption.current_value, int | float):
        # Hostile meta means you need MORE interaction
        needed_increase = int(removal_assumption.current_value * scenario.intensity * 0.5)
        effective_shortfall = needed_increase  # You're this many short

        new_health = (
            AssumptionHealth.WARNING if effective_shortfall > 2
            else AssumptionHealth.CRITICAL if effective_shortfall > 4
            else removal_assumption.health
        )

        affected.append(
            StressedAssumption(
                name=removal_assumption.name,
                original_value=removal_assumption.current_value,
                stressed_value=removal_assumption.current_value,  # Value same, context changed
                original_health=removal_assumption.health.value,
                stressed_health=new_health.value,
                change_explanation=(
                    f"In a hostile meta, you may need {needed_increase} more "
                    f"interaction spells than the current {removal_assumption.current_value}."
                ),
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

        affected.append(
            StressedAssumption(
                name=key_assumption.name,
                original_value=key_assumption.current_value,
                stressed_value=key_assumption.current_value,
                original_health=original_health.value,
                stressed_health=stressed_health.value,
                change_explanation=(
                    "Reliance on key cards becomes riskier when opponents "
                    "have more answers available."
                ),
            )
        )

    original_fragility = baseline.overall_fragility
    stressed_fragility = _calculate_stressed_fragility(baseline, affected, scenario.intensity)
    breaking_point = stressed_fragility > 0.7

    return StressResult(
        deck_name=deck.name,
        scenario=scenario,
        original_fragility=original_fragility,
        stressed_fragility=stressed_fragility,
        affected_assumptions=affected,
        breaking_point=breaking_point,
        explanation=_generate_stress_explanation(
            "hostile meta", "opponent interaction",
            original_fragility, stressed_fragility, breaking_point
        ),
        recommendations=_generate_hostile_meta_recommendations(baseline),
    )


def _recalculate_health(
    value: float, min_expected: float, max_expected: float
) -> AssumptionHealth:
    """Recalculate health for a new value."""
    if min_expected <= value <= max_expected:
        return AssumptionHealth.HEALTHY

    if value < min_expected:
        deviation = (
            (min_expected - value) / min_expected if min_expected > 0
            else abs(min_expected - value)
        )
    else:
        deviation = (
            (value - max_expected) / max_expected if max_expected > 0
            else abs(value - max_expected)
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
    degradations = sum(
        1 for a in affected
        if a.stressed_health != a.original_health
    )

    critical_count = sum(
        1 for a in affected if a.stressed_health == "critical"
    )

    # Fragility increases based on degradations and intensity
    increase = (degradations * 0.1 + critical_count * 0.15) * intensity

    # Key card removal has extra impact
    if key_card_affected:
        increase += 0.15 * intensity

    return min(1.0, base_fragility + increase)


def _generate_stress_explanation(
    stress_name: str,
    target: str,
    original: float,
    stressed: float,
    breaking: bool,
) -> str:
    """Generate human-readable stress explanation."""
    change = stressed - original
    direction = "increased" if change > 0 else "decreased"

    if breaking:
        return (
            f"Stress testing {stress_name} on {target} caused significant fragility. "
            f"Fragility {direction} from {original:.0%} to {stressed:.0%}. "
            f"This represents a breaking point - the deck may struggle to function."
        )

    if abs(change) < 0.05:
        return (
            f"Stress testing {stress_name} on {target} had minimal impact. "
            f"Fragility stayed near {original:.0%}. The deck is resilient to this stress."
        )

    return (
        f"Stress testing {stress_name} on {target} {direction} fragility "
        f"from {original:.0%} to {stressed:.0%}. "
        f"The deck shows moderate vulnerability to this scenario."
    )


def _generate_underperform_recommendations(
    baseline: DeckAssumptionSet, scenario: StressScenario
) -> list[str]:
    """Generate recommendations for underperformance stress."""
    recommendations = []

    if scenario.intensity > 0.5:
        recommendations.append(
            "Consider adding redundancy - backup cards that serve similar roles."
        )

    draw_assumption = next(
        (a for a in baseline.assumptions if a.name == "Card Selection Density"),
        None,
    )
    if draw_assumption and draw_assumption.health != AssumptionHealth.HEALTHY:
        recommendations.append(
            "More card draw/selection helps find key pieces more consistently."
        )

    recommendations.append(
        "Test which key cards the deck can function without, and which are critical."
    )

    return recommendations


def _generate_missing_recommendations(target_card: str, is_key_card: bool) -> list[str]:
    """Generate recommendations for missing card stress."""
    recommendations = []

    if is_key_card:
        recommendations.append(
            f"'{target_card}' is critical. Consider backup options or protection."
        )
        recommendations.append(
            "Evaluate if there are functional replacements in the format."
        )
    else:
        recommendations.append(
            f"'{target_card}' removal has limited impact - the slot may be flexible."
        )

    return recommendations


def _generate_delayed_recommendations(baseline: DeckAssumptionSet) -> list[str]:
    """Generate recommendations for mana delay stress."""
    recommendations = []

    land_assumption = next(
        (a for a in baseline.assumptions if a.name == "Land Count"),
        None,
    )

    if land_assumption and isinstance(land_assumption.current_value, int | float):
        if land_assumption.current_value < land_assumption.expected_range[0]:
            recommendations.append(
                "Consider adding more lands to reduce mana screw frequency."
            )
        recommendations.append(
            "Evaluate your mana curve - can you reduce average mana value?"
        )

    recommendations.append(
        "Test mulliganing more aggressively for land-heavy hands."
    )

    return recommendations


def _generate_hostile_meta_recommendations(baseline: DeckAssumptionSet) -> list[str]:
    """Generate recommendations for hostile meta stress."""
    recommendations = []

    removal_assumption = next(
        (a for a in baseline.assumptions if a.name == "Removal Density"),
        None,
    )

    if (
        removal_assumption
        and isinstance(removal_assumption.current_value, int | float)
        and removal_assumption.current_value < 6
    ):
        recommendations.append(
            "Consider more interaction in the maindeck or sideboard."
        )

    recommendations.append(
        "Evaluate threats with built-in protection (hexproof, ward, etc.)."
    )
    recommendations.append(
        "Consider faster gameplans to get under interaction-heavy decks."
    )

    return recommendations
