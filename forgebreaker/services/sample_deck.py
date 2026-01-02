"""
Sample deck for demo mode.

Provides a realistic Standard deck that demonstrates ForgeBreaker's
assumption surfacing, fragility analysis, and stress testing capabilities.

The deck is chosen to have interesting assumptions to explore:
- Mana curve assumptions (enough 1-2 drops for aggro)
- Key card dependencies (what if Swiftspear is always answered?)
- Interaction timing (can we deal with early blockers?)
"""

from forgebreaker.models.deck import MetaDeck

# Mono-Red Aggro - a classic archetype with clear assumptions
# This deck has interesting fragility points:
# - Heavily reliant on early creatures connecting
# - Needs to close games quickly before stabilization
# - Burn spells do double duty (removal + reach)
SAMPLE_DECK = MetaDeck(
    name="Sample: Mono-Red Aggro",
    archetype="aggro",
    format="standard",
    cards={
        # Creatures (20)
        "Monastery Swiftspear": 4,
        "Slickshot Show-Off": 4,
        "Heartfire Hero": 4,
        "Cacophony Scamp": 4,
        "Phoenix Chick": 4,
        # Spells (20)
        "Play with Fire": 4,
        "Monstrous Rage": 4,
        "Lightning Strike": 4,
        "Kumano Faces Kakkazan": 4,
        "Searing Spear": 4,
        # Lands (20)
        "Mountain": 20,
    },
    sideboard={
        "Rending Flame": 3,
        "Nahiri's Warcrafting": 2,
        "Obliterating Bolt": 2,
        "End the Festivities": 4,
        "Urabrask's Forge": 2,
        "Screaming Nemesis": 2,
    },
    win_rate=0.52,
    meta_share=0.08,
    source_url="https://github.com/RogersJohn/ForgeBreaker",
)


def get_sample_deck() -> MetaDeck:
    """
    Get the sample deck for demo mode.

    Returns a copy to prevent modification of the template.
    """
    return MetaDeck(
        name=SAMPLE_DECK.name,
        archetype=SAMPLE_DECK.archetype,
        format=SAMPLE_DECK.format,
        cards=SAMPLE_DECK.cards.copy(),
        sideboard=SAMPLE_DECK.sideboard.copy(),
        win_rate=SAMPLE_DECK.win_rate,
        meta_share=SAMPLE_DECK.meta_share,
        source_url=SAMPLE_DECK.source_url,
    )
