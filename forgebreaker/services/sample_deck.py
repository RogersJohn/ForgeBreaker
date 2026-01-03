"""
Sample deck for demo mode.

This sample deck is intentionally human-curated to provide a clear,
representative example for first-time users. Demo decks prioritize
clarity and analysis value over historical performance.

DESIGN PRINCIPLE: Sample data is intentionally minimal. Full card datasets
are not bundled with the application. Large datasets like Scryfall's bulk
card data (~100MB) are downloaded on-demand when needed for specific
operations. The demo flow works entirely with this curated deck, which
exercises all code paths (parsing, analysis, ML, MCP) without requiring
external data.
"""

from forgebreaker.models.deck import MetaDeck

# Curated Gruul sample deck for demo purposes
SAMPLE_DECK = MetaDeck(
    name="Sample Deck",
    archetype="midrange",
    format="standard",
    cards={
        # Creatures
        "Badgermole Cub": 2,
        "Bristly Bill, Spine Sower": 2,
        "Mossborn Hydra": 4,
        "Earth Kingdom General": 4,
        "Haru, Hidden Talent": 3,
        "The Boulder, Ready to Rumble": 1,
        # Spells
        "Shock": 4,
        "Burst Lightning": 4,
        "Explosive Derailment": 4,
        "Ride the Shoopuf": 2,
        "Earthbender Ascension": 2,
        "Sazh's Chocobo": 1,
        "The Legend of Kyoshi": 3,
        # Lands
        "Forest": 14,
        "Mountain": 10,
    },
    sideboard={},
    win_rate=None,
    meta_share=None,
    source_url=None,
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
        sideboard=SAMPLE_DECK.sideboard.copy() if SAMPLE_DECK.sideboard else {},
        win_rate=SAMPLE_DECK.win_rate,
        meta_share=SAMPLE_DECK.meta_share,
        source_url=SAMPLE_DECK.source_url,
    )
