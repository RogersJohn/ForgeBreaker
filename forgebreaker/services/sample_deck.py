"""
Sample deck for demo mode.

Provides a real tournament-winning Standard deck that demonstrates
ForgeBreaker's assumption surfacing, fragility analysis, and stress
testing capabilities.

Source: Ken Yukuhiro's 1st place deck from Pro Tour Final Fantasy
(June 20, 2025), with a 9-1 record.

DESIGN PRINCIPLE: Sample data is intentionally minimal. Full card datasets
are not bundled with the application. Large datasets like Scryfall's bulk
card data (~100MB) are downloaded on-demand when needed for specific
operations. The demo flow works entirely with this curated deck, which
exercises all code paths (parsing, analysis, ML, MCP) without requiring
external data.
"""

from forgebreaker.models.deck import MetaDeck

# Ken Yukuhiro's Pro Tour Final Fantasy winning Mono-Red Aggro
# Source: https://www.mtggoldfish.com/deck/7186307
SAMPLE_DECK = MetaDeck(
    name="Mono-Red Aggro (Pro Tour Final Fantasy 1st)",
    archetype="aggro",
    format="standard",
    cards={
        # Creatures (24)
        "Heartfire Hero": 4,
        "Manifold Mouse": 4,
        "Emberheart Challenger": 4,
        "Hired Claw": 4,
        "Magebane Lizard": 3,
        "Twinmaw Stormbrood": 4,
        "Tersa Lightshatter": 1,
        # Spells (13)
        "Burst Lightning": 4,
        "Monstrous Rage": 4,
        "Lightning Strike": 1,
        "Self-Destruct": 1,
        "Screaming Nemesis": 3,
        # Lands (23)
        "Mountain": 17,
        "Rockface Village": 4,
        "Soulstone Sanctuary": 2,
    },
    sideboard={
        "Soul-Guide Lantern": 2,
        "Suplex": 2,
        "Torch the Tower": 3,
        "Lithomantic Barrage": 2,
        "Magebane Lizard": 1,
        "Case of the Crimson Pulse": 2,
        "Sunspine Lynx": 3,
    },
    win_rate=0.90,
    meta_share=0.102,
    source_url="https://www.mtggoldfish.com/deck/7186307",
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
