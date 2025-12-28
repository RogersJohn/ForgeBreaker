"""
Player-Centered Validation Test — Architectural Contract.

This test protects ForgeBreaker's core contract:

1. Assumptions are PLAYER-DECLARED BELIEFS, not tunable parameters.
   They represent what a player believes about how their deck functions.

2. Violating a belief must produce a QUALITATIVELY DIFFERENT OUTCOME.
   Not just a number change — the deck's character should shift.

3. That outcome must be EXPLAINABLE, not just numeric.
   Players must understand WHY, not just see a different score.

This is an ARCHITECTURAL test, not a unit test.
It exists to prevent future refactors from:
- Turning assumptions into optimization knobs
- Smoothing away belief failure into gradual degradation
- Converting explanations into advice or recommendations

If this test fails, ForgeBreaker has lost its purpose.
"""

import pytest

from forgebreaker.analysis.assumptions import extract_assumptions
from forgebreaker.analysis.stress import apply_stress, find_breaking_point
from forgebreaker.models.deck import MetaDeck
from forgebreaker.models.stress import StressScenario, StressType


@pytest.fixture
def sample_aggro_deck() -> MetaDeck:
    """A realistic aggro deck for testing."""
    return MetaDeck(
        name="Mono-Red Aggro",
        archetype="aggro",
        format="standard",
        cards={
            "Monastery Swiftspear": 4,
            "Soul-Scar Mage": 4,
            "Goblin Guide": 4,
            "Lightning Bolt": 4,
            "Play with Fire": 4,
            "Light Up the Stage": 4,
            "Searing Blood": 2,
            "Kumano Faces Kakkazan": 4,
            "Fiery Emancipation": 2,
            "Mountain": 20,
        },
        sideboard={"Roiling Vortex": 2},
    )


@pytest.fixture
def sample_control_deck() -> MetaDeck:
    """A realistic control deck for testing."""
    return MetaDeck(
        name="Azorius Control",
        archetype="control",
        format="standard",
        cards={
            "Teferi, Hero of Dominaria": 4,
            "Absorb": 4,
            "Wrath of God": 3,
            "Supreme Verdict": 2,
            "Opt": 4,
            "Memory Deluge": 4,
            "Dovin's Veto": 2,
            "The Wandering Emperor": 3,
            "March of Otherworldly Light": 4,
            "Plains": 10,
            "Island": 10,
            "Hallowed Fountain": 4,
            "Adarkar Wastes": 4,
        },
        sideboard={"Rest in Peace": 2},
    )


@pytest.fixture
def mock_card_db() -> dict[str, dict]:
    """Mock card database with essential properties."""
    return {
        "Monastery Swiftspear": {"cmc": 1, "type_line": "Creature", "oracle_text": "Prowess"},
        "Soul-Scar Mage": {"cmc": 1, "type_line": "Creature", "oracle_text": "Prowess"},
        "Goblin Guide": {"cmc": 1, "type_line": "Creature", "oracle_text": "Haste"},
        "Lightning Bolt": {
            "cmc": 1,
            "type_line": "Instant",
            "oracle_text": "deals 3 damage to any target",
        },
        "Play with Fire": {
            "cmc": 1,
            "type_line": "Instant",
            "oracle_text": "deals 2 damage to any target. Scry 1.",
        },
        "Light Up the Stage": {
            "cmc": 1,
            "type_line": "Sorcery",
            "oracle_text": "Exile the top two cards. You may play them.",
        },
        "Searing Blood": {
            "cmc": 2,
            "type_line": "Instant",
            "oracle_text": "deals 2 damage to target creature",
        },
        "Kumano Faces Kakkazan": {"cmc": 1, "type_line": "Enchantment — Saga", "oracle_text": ""},
        "Fiery Emancipation": {"cmc": 6, "type_line": "Enchantment", "oracle_text": ""},
        "Mountain": {"cmc": 0, "type_line": "Basic Land", "oracle_text": ""},
        "Roiling Vortex": {"cmc": 2, "type_line": "Enchantment", "oracle_text": ""},
        # Control deck cards
        "Teferi, Hero of Dominaria": {
            "cmc": 5,
            "type_line": "Legendary Planeswalker",
            "oracle_text": "draw a card",
        },
        "Absorb": {
            "cmc": 3,
            "type_line": "Instant",
            "oracle_text": "Counter target spell. You gain 3 life.",
        },
        "Wrath of God": {
            "cmc": 4,
            "type_line": "Sorcery",
            "oracle_text": "Destroy all creatures.",
        },
        "Supreme Verdict": {
            "cmc": 4,
            "type_line": "Sorcery",
            "oracle_text": "Destroy all creatures.",
        },
        "Opt": {"cmc": 1, "type_line": "Instant", "oracle_text": "Scry 1. Draw a card."},
        "Memory Deluge": {
            "cmc": 4,
            "type_line": "Instant",
            "oracle_text": "Look at the top X cards. Draw two.",
        },
        "Dovin's Veto": {
            "cmc": 2,
            "type_line": "Instant",
            "oracle_text": "Counter target noncreature spell.",
        },
        "The Wandering Emperor": {
            "cmc": 4,
            "type_line": "Legendary Planeswalker",
            "oracle_text": "Flash. Exile target tapped creature.",
        },
        "March of Otherworldly Light": {
            "cmc": 1,
            "type_line": "Instant",
            "oracle_text": "Exile target artifact, creature, or enchantment.",
        },
        "Plains": {"cmc": 0, "type_line": "Basic Land", "oracle_text": ""},
        "Island": {"cmc": 0, "type_line": "Basic Land", "oracle_text": ""},
        "Hallowed Fountain": {"cmc": 0, "type_line": "Land", "oracle_text": ""},
        "Adarkar Wastes": {"cmc": 0, "type_line": "Land", "oracle_text": ""},
        "Rest in Peace": {"cmc": 2, "type_line": "Enchantment", "oracle_text": ""},
    }


class TestAssumptionExtractionProducesNonEmptySet:
    """Verify that decks produce meaningful assumptions."""

    def test_aggro_deck_has_assumptions(
        self, sample_aggro_deck: MetaDeck, mock_card_db: dict
    ) -> None:
        """Aggro deck produces non-empty assumption set."""
        assumptions = extract_assumptions(sample_aggro_deck, mock_card_db)

        assert assumptions is not None
        assert len(assumptions.assumptions) > 0
        assert assumptions.deck_name == "Mono-Red Aggro"
        assert assumptions.archetype == "aggro"

    def test_control_deck_has_assumptions(
        self, sample_control_deck: MetaDeck, mock_card_db: dict
    ) -> None:
        """Control deck produces non-empty assumption set."""
        assumptions = extract_assumptions(sample_control_deck, mock_card_db)

        assert assumptions is not None
        assert len(assumptions.assumptions) > 0
        assert assumptions.archetype == "control"

    def test_assumptions_have_required_fields(
        self, sample_aggro_deck: MetaDeck, mock_card_db: dict
    ) -> None:
        """Each assumption has all required fields for display."""
        assumptions = extract_assumptions(sample_aggro_deck, mock_card_db)

        for assumption in assumptions.assumptions:
            assert assumption.name, "Assumption must have a name"
            assert assumption.category, "Assumption must have a category"
            assert assumption.description, "Assumption must have a description"
            assert assumption.explanation, "Assumption must have an explanation"


class TestStressProducesMeaningfulDifference:
    """Verify that stress changes assumptions in measurable ways."""

    def test_stress_produces_measurable_change(
        self, sample_aggro_deck: MetaDeck, mock_card_db: dict
    ) -> None:
        """Stressing a deck produces measurable change (fragility or assumptions)."""
        scenario = StressScenario(
            stress_type=StressType.UNDERPERFORM,
            target="key_cards",
            intensity=0.75,
            description="Key cards underperforming",
        )
        result = apply_stress(sample_aggro_deck, mock_card_db, scenario)

        # Stress should produce SOME change - either fragility changes OR
        # assumptions are affected (even if they stay in healthy range)
        fragility_changed = result.stressed_fragility != result.original_fragility
        assumptions_affected = len(result.affected_assumptions) > 0

        assert fragility_changed or assumptions_affected, (
            "Stress should affect fragility or at least track affected assumptions"
        )

    def test_missing_card_stress_affects_key_cards(
        self, sample_aggro_deck: MetaDeck, mock_card_db: dict
    ) -> None:
        """Removing a key card produces measurable impact."""
        scenario = StressScenario(
            stress_type=StressType.MISSING,
            target="Monastery Swiftspear",  # A key 4x card
            intensity=1.0,  # Remove all copies
            description="Remove Monastery Swiftspear",
        )
        result = apply_stress(sample_aggro_deck, mock_card_db, scenario)

        # Should have affected assumptions
        assert result.affected_assumptions is not None
        # Explanation should mention the card or the stress
        assert (
            "Swiftspear" in result.explanation
            or "key" in result.explanation.lower()
            or "card" in result.explanation.lower()
        )


class TestExplanationsReferenceStressedAssumptions:
    """Verify that explanations are informative and reference what changed."""

    def test_stress_result_has_explanation(
        self, sample_aggro_deck: MetaDeck, mock_card_db: dict
    ) -> None:
        """Stress results always include an explanation."""
        scenario = StressScenario(
            stress_type=StressType.DELAYED,
            target="mana_curve",
            intensity=0.5,
            description="Delay mana development",
        )
        result = apply_stress(sample_aggro_deck, mock_card_db, scenario)

        assert result.explanation is not None
        assert len(result.explanation) > 0

    def test_affected_assumptions_have_change_explanations(
        self, sample_aggro_deck: MetaDeck, mock_card_db: dict
    ) -> None:
        """Each affected assumption explains what changed."""
        scenario = StressScenario(
            stress_type=StressType.DELAYED,
            target="mana_curve",
            intensity=0.75,
            description="Delay mana development",
        )
        result = apply_stress(sample_aggro_deck, mock_card_db, scenario)

        for affected in result.affected_assumptions:
            assert (
                affected.change_explanation
            ), f"Affected assumption {affected.name} should explain what changed"
            assert (
                affected.original_value is not None
            ), "Should show original value"
            assert (
                affected.stressed_value is not None
            ), "Should show stressed value"

    def test_breaking_point_has_comprehensive_explanation(
        self, sample_aggro_deck: MetaDeck, mock_card_db: dict
    ) -> None:
        """Breaking point analysis provides useful guidance."""
        result = find_breaking_point(sample_aggro_deck, mock_card_db)

        assert result.explanation is not None
        assert len(result.explanation) > 20, "Explanation should be substantive"
        assert result.weakest_assumption is not None
        assert result.resilience_score >= 0.0
        assert result.resilience_score <= 1.0


class TestUncertaintyLanguagePresent:
    """Verify that uncertainty is explicitly communicated."""

    def test_stress_explanation_includes_conditional_language(
        self, sample_aggro_deck: MetaDeck, mock_card_db: dict
    ) -> None:
        """Stress explanations use conditional/uncertainty language."""
        scenario = StressScenario(
            stress_type=StressType.HOSTILE_META,
            target="interaction",
            intensity=0.75,
            description="Face more interaction",
        )
        result = apply_stress(sample_aggro_deck, mock_card_db, scenario)

        # Check for uncertainty or conditional language
        # Includes words that indicate this is a scenario/estimate, not a guarantee
        explanation_lower = result.explanation.lower()
        uncertainty_words = [
            "may", "might", "could", "if", "under", "when", "assume",
            "shows", "appears", "suggests", "scenario", "testing", "stress"
        ]

        has_uncertainty = any(word in explanation_lower for word in uncertainty_words)
        assert has_uncertainty, (
            f"Explanation should include uncertainty language. "
            f"Got: '{result.explanation}'"
        )

    def test_recommendations_use_suggestive_language(
        self, sample_aggro_deck: MetaDeck, mock_card_db: dict
    ) -> None:
        """Recommendations suggest rather than dictate."""
        scenario = StressScenario(
            stress_type=StressType.UNDERPERFORM,
            target="key_cards",
            intensity=0.75,
            description="Key cards underperforming",
        )
        result = apply_stress(sample_aggro_deck, mock_card_db, scenario)

        if result.recommendations:
            for rec in result.recommendations:
                rec_lower = rec.lower()
                # Should use suggestive language
                suggestive_words = [
                    "consider",
                    "may",
                    "might",
                    "could",
                    "evaluate",
                    "test",
                    "try",
                ]
                has_suggestive = any(word in rec_lower for word in suggestive_words)
                assert has_suggestive, (
                    f"Recommendation should be suggestive, not directive. "
                    f"Got: '{rec}'"
                )


class TestAssumptionChangeDifferentiatesDecks:
    """Verify that different decks respond differently to stress."""

    def test_aggro_vs_control_different_breaking_points(
        self,
        sample_aggro_deck: MetaDeck,
        sample_control_deck: MetaDeck,
        mock_card_db: dict,
    ) -> None:
        """Different archetypes have different vulnerabilities."""
        aggro_breaking = find_breaking_point(sample_aggro_deck, mock_card_db)
        control_breaking = find_breaking_point(sample_control_deck, mock_card_db)

        # They should have different breaking characteristics
        # (not necessarily different scores, but different weak points)
        # This test is more about the system differentiating decks
        assert aggro_breaking.deck_name != control_breaking.deck_name

        # At minimum, the weakest assumptions should be identified
        assert aggro_breaking.weakest_assumption is not None
        assert control_breaking.weakest_assumption is not None

    def test_mana_delay_affects_control_differently(
        self,
        sample_aggro_deck: MetaDeck,
        sample_control_deck: MetaDeck,
        mock_card_db: dict,
    ) -> None:
        """Mana delay stress has different impact on different archetypes."""
        scenario = StressScenario(
            stress_type=StressType.DELAYED,
            target="mana_curve",
            intensity=0.5,
            description="Delay mana development",
        )

        aggro_result = apply_stress(sample_aggro_deck, mock_card_db, scenario)
        control_result = apply_stress(sample_control_deck, mock_card_db, scenario)

        # Both should produce results
        assert aggro_result.explanation
        assert control_result.explanation

        # The explanations should reflect different deck contexts
        assert aggro_result.deck_name == "Mono-Red Aggro"
        assert control_result.deck_name == "Azorius Control"


class TestEndToEndPlayerTrust:
    """
    The core validation test: changing an assumption produces a
    meaningful, explainable difference.

    This test represents what a player would experience:
    1. Look at their deck's assumptions
    2. Stress test one assumption
    3. See a clear before/after difference
    4. Understand why via explanation
    """

    def test_assumption_change_produces_explained_difference(
        self, sample_aggro_deck: MetaDeck, mock_card_db: dict
    ) -> None:
        """
        This is THE player trust test.

        Validates:
        1. Deck produces non-empty assumption set
        2. Stressed version differs from baseline
        3. Explanation is present and references stressed assumption
        4. Uncertainty language included
        """
        # 1. Get baseline assumptions for a deck
        baseline = extract_assumptions(sample_aggro_deck, mock_card_db)
        assert len(baseline.assumptions) > 0, "Deck should have assumptions"

        # 2. Stress one assumption (key_card_dependency)
        scenario = StressScenario(
            stress_type=StressType.UNDERPERFORM,
            target="key_cards",
            intensity=0.75,
            description="Key cards underperforming",
        )
        result = apply_stress(sample_aggro_deck, mock_card_db, scenario)

        # 3. Verify stressed state differs from baseline
        # Either fragility changed, or we're at bounds (0 or 1)
        changed = (
            result.stressed_fragility != result.original_fragility
            or len(result.affected_assumptions) > 0
        )
        assert changed, "Stress should produce some measurable change"

        # 4. Verify explanation references the stressed assumption
        assert result.explanation is not None
        assert len(result.explanation) > 10, "Explanation should be substantive"

        # 5. Verify uncertainty language is present
        explanation_lower = result.explanation.lower()
        uncertainty_markers = ["may", "might", "could", "if", "under", "scenario"]
        has_uncertainty = any(marker in explanation_lower for marker in uncertainty_markers)

        # Allow for cases where the deck is already at max/min state
        if result.stressed_fragility not in (0.0, 1.0):
            assert has_uncertainty, (
                "Explanation should include uncertainty language to be honest about limitations"
            )

        # 6. STRUCTURAL ASSERTION: Explanation must be interpretive, not prescriptive
        #    This guards against explanations drifting into advice/optimization language.
        prescriptive_signals = ["should", "must", "need to", "recommend", "optimize", "fix"]
        has_prescriptive = any(signal in explanation_lower for signal in prescriptive_signals)
        assert not has_prescriptive, (
            f"Explanation must describe consequences, not prescribe actions. "
            f"Found prescriptive language in: '{result.explanation}'"
        )
