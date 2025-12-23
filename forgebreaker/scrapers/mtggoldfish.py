"""
MTGGoldfish meta deck scraper.

Fetches competitive deck data from MTGGoldfish metagame pages.
Parses deck lists, win rates, and meta share percentages.

Note: Web scraping is inherently fragile. Page structure may change.
"""

import re
from dataclasses import dataclass

import httpx

from forgebreaker.models.deck import MetaDeck

MTGGOLDFISH_BASE = "https://www.mtggoldfish.com"
USER_AGENT = "ForgeBreaker/1.0 (MTG Arena Collection Manager)"

# Valid Arena formats on MTGGoldfish (excludes Brawl - singleton format with no sideboard)
VALID_FORMATS = frozenset({"standard", "historic", "explorer", "timeless"})


@dataclass
class DeckSummary:
    """Summary of a meta deck from the metagame page."""

    name: str
    url: str
    meta_share: float
    format: str


def fetch_metagame_page(format_name: str, client: httpx.Client | None = None) -> str:
    """
    Fetch the metagame page HTML for a format.

    Args:
        format_name: Arena format (standard, historic, explorer, timeless)
        client: Optional httpx client for connection reuse

    Returns:
        Raw HTML content

    Raises:
        ValueError: If format is not valid
        httpx.HTTPError: If request fails
    """
    if format_name not in VALID_FORMATS:
        raise ValueError(f"Invalid format: {format_name}. Must be one of {VALID_FORMATS}")

    url = f"{MTGGOLDFISH_BASE}/metagame/{format_name}"

    if client:
        response = client.get(url)
    else:
        response = httpx.get(url, headers={"User-Agent": USER_AGENT}, follow_redirects=True)

    response.raise_for_status()
    return response.text


def parse_metagame_page(html: str, format_name: str) -> list[DeckSummary]:
    """
    Parse deck summaries from a metagame page.

    Args:
        html: Raw HTML content from metagame page
        format_name: The format being parsed

    Returns:
        List of DeckSummary objects
    """
    summaries: list[DeckSummary] = []

    # Pattern matches deck tiles with meta share percentage
    # Example: <a href="/archetype/mono-red-aggro#paper">Mono Red Aggro</a>
    # followed by meta percentage like "12.5%"
    # Matches: href="/archetype/..." followed by deck name, then percentage
    deck_pattern = re.compile(
        r'href="(/archetype/[^"#]+)[^"]*"[^>]*>\s*'  # href with archetype URL
        r"([^<]+?)\s*</a>"  # deck name
        r".*?"  # anything between
        r"(\d+\.?\d*)%",  # meta share percentage
        re.DOTALL,
    )

    for match in deck_pattern.finditer(html):
        url_path, name, meta_pct = match.groups()
        summaries.append(
            DeckSummary(
                name=name.strip(),
                url=f"{MTGGOLDFISH_BASE}{url_path}",
                meta_share=float(meta_pct) / 100.0,
                format=format_name,
            )
        )

    return summaries


def fetch_deck_page(url: str, client: httpx.Client | None = None) -> str:
    """
    Fetch a deck page HTML.

    Args:
        url: Full URL to deck page
        client: Optional httpx client for connection reuse

    Returns:
        Raw HTML content
    """
    if client:
        response = client.get(url)
    else:
        response = httpx.get(url, headers={"User-Agent": USER_AGENT}, follow_redirects=True)

    response.raise_for_status()
    return response.text


def parse_deck_page(html: str, summary: DeckSummary) -> MetaDeck:
    """
    Parse a full deck list from a deck page.

    Args:
        html: Raw HTML content from deck page
        summary: DeckSummary with metadata

    Returns:
        MetaDeck with full card list
    """
    cards: dict[str, int] = {}
    sideboard: dict[str, int] = {}

    # HTML structure we're matching (simplified):
    #   <td class="deck-col-qty">4</td>
    #   ... (other <td> / markup) ...
    #   <a data-card-id="12345" ...>Card Name</a>
    #
    # Group 1: numeric quantity from "deck-col-qty" cell
    # Group 2: card name text inside the <a> tag
    # DOTALL needed because content between quantity and card link spans multiple lines
    card_pattern = re.compile(
        r'deck-col-qty">\s*(\d+)\s*</td>\s*'  # group 1: quantity in deck-col-qty cell
        r".*?"  # non-greedy skip over intervening HTML (other <td>, whitespace)
        r'data-card-id="[^"]*"[^>]*>\s*'  # card link anchor with data-card-id
        r"([^<]+?)\s*</a>",  # group 2: card name text up to closing </a>
        re.DOTALL,
    )

    # Find sideboard section marker (-1 if not found)
    sideboard_marker = html.find("Sideboard")
    main_section = html[:sideboard_marker] if sideboard_marker != -1 else html
    side_section = html[sideboard_marker:] if sideboard_marker != -1 else ""

    # Parse main deck
    for match in card_pattern.finditer(main_section):
        qty, name = match.groups()
        name = name.strip()
        cards[name] = cards.get(name, 0) + int(qty)

    # Parse sideboard
    for match in card_pattern.finditer(side_section):
        qty, name = match.groups()
        name = name.strip()
        sideboard[name] = sideboard.get(name, 0) + int(qty)

    return MetaDeck(
        name=summary.name,
        archetype=_infer_archetype(summary.name),
        format=summary.format,
        cards=cards,
        sideboard=sideboard,
        meta_share=summary.meta_share,
        source_url=summary.url,
    )


def _infer_archetype(deck_name: str) -> str:
    """Infer archetype from deck name."""
    name_lower = deck_name.lower()

    if any(word in name_lower for word in ["aggro", "burn", "red deck", "sligh"]):
        return "aggro"
    if any(word in name_lower for word in ["control", "blue", "esper", "azorius"]):
        return "control"
    if any(word in name_lower for word in ["combo", "storm", "ramp"]):
        return "combo"

    return "midrange"  # Default


def fetch_meta_decks(
    format_name: str,
    limit: int = 10,
    client: httpx.Client | None = None,
) -> list[MetaDeck]:
    """
    Fetch top meta decks for a format.

    Args:
        format_name: Arena format (standard, historic, explorer, timeless)
        limit: Maximum number of decks to fetch
        client: Optional httpx client for connection reuse

    Returns:
        List of MetaDeck with full card lists

    Raises:
        ValueError: If format is not valid
        httpx.HTTPError: If any request fails
    """
    metagame_html = fetch_metagame_page(format_name, client)
    summaries = parse_metagame_page(metagame_html, format_name)

    decks: list[MetaDeck] = []
    for summary in summaries[:limit]:
        deck_html = fetch_deck_page(summary.url, client)
        deck = parse_deck_page(deck_html, summary)
        decks.append(deck)

    return decks
