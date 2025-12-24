"""
MTGGoldfish meta deck scraper.

Fetches competitive deck data from MTGGoldfish metagame pages.
Parses deck lists, win rates, and meta share percentages.

Note: Web scraping is inherently fragile. Page structure may change.
Uses download endpoint for deck lists (text format) since JS rendering is required for HTML.
"""

import re
from dataclasses import dataclass

import httpx

from forgebreaker.models.deck import MetaDeck

MTGGOLDFISH_BASE = "https://www.mtggoldfish.com"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

# Valid Arena formats on MTGGoldfish (excludes Brawl - singleton format with no sideboard)
VALID_FORMATS = frozenset({"standard", "historic", "explorer", "timeless"})


@dataclass
class DeckSummary:
    """Summary of a meta deck from the metagame page."""

    name: str
    url: str
    deck_id: str | None  # ID for fetching deck via download endpoint
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

    Extracts deck names, archetype URLs, and meta shares.
    Note: Deck IDs must be fetched from individual archetype pages.

    Args:
        html: Raw HTML content from metagame page
        format_name: The format being parsed

    Returns:
        List of DeckSummary objects
    """
    summaries: list[DeckSummary] = []
    seen_names: set[str] = set()  # Avoid duplicates

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
        name = name.strip()

        # Skip duplicates (same archetype can appear multiple times)
        if name in seen_names:
            continue
        seen_names.add(name)

        summaries.append(
            DeckSummary(
                name=name,
                url=f"{MTGGOLDFISH_BASE}{url_path}",
                deck_id=None,  # Will be fetched from archetype page
                meta_share=float(meta_pct) / 100.0,
                format=format_name,
            )
        )

    return summaries


def fetch_archetype_page(url: str, client: httpx.Client | None = None) -> str:
    """
    Fetch an archetype page HTML.

    Args:
        url: Full URL to archetype page
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


def extract_deck_id_from_archetype(html: str) -> str | None:
    """
    Extract the first deck ID from an archetype page.

    Args:
        html: Raw HTML content from archetype page

    Returns:
        Deck ID string or None if not found
    """
    # Pattern to find deck IDs (e.g. /deck/7496197)
    deck_id_pattern = re.compile(r"/deck/(\d+)")
    match = deck_id_pattern.search(html)
    return match.group(1) if match else None


def fetch_deck_download(deck_id: str, client: httpx.Client | None = None) -> str:
    """
    Fetch deck in text format via download endpoint.

    Args:
        deck_id: The deck ID number
        client: Optional httpx client for connection reuse

    Returns:
        Plain text deck list (simple format: qty CardName, one per line)
    """
    url = f"{MTGGOLDFISH_BASE}/deck/download/{deck_id}"

    if client:
        response = client.get(url)
    else:
        response = httpx.get(url, headers={"User-Agent": USER_AGENT}, follow_redirects=True)

    response.raise_for_status()
    return response.text


def parse_deck_download(text: str, summary: DeckSummary) -> MetaDeck:
    """
    Parse a deck list from the download text format.

    Format is simple: "qty CardName" per line, blank line separates sideboard.
    Example:
        4 Lightning Bolt
        4 Monastery Swiftspear

        2 Pyroblast
        1 Smash to Smithereens

    Args:
        text: Plain text deck list from download endpoint
        summary: DeckSummary with metadata

    Returns:
        MetaDeck with full card list
    """
    cards: dict[str, int] = {}
    sideboard: dict[str, int] = {}

    # Pattern: qty CardName (simple format)
    # Matches: "4 Lightning Bolt" -> (4, Lightning Bolt)
    card_pattern = re.compile(r"^(\d+)\s+(.+)$", re.MULTILINE)

    # Split by blank lines to separate main deck from sideboard
    sections = re.split(r"\n\s*\n", text.strip())

    # Main deck is first section
    if sections:
        for match in card_pattern.finditer(sections[0]):
            qty, name = match.groups()
            name = name.strip()
            cards[name] = cards.get(name, 0) + int(qty)

    # Sideboard is second section (if exists)
    if len(sections) > 1:
        for match in card_pattern.finditer(sections[1]):
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

    Workflow:
    1. Fetch metagame page for archetype list
    2. For each archetype, fetch its page to find a sample deck ID
    3. Download the deck in text format (avoids JS rendering)

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
        try:
            # Fetch archetype page to get a deck ID
            archetype_html = fetch_archetype_page(summary.url, client)
            deck_id = extract_deck_id_from_archetype(archetype_html)

            if not deck_id:
                continue

            # Download and parse the deck
            deck_text = fetch_deck_download(deck_id, client)
            deck = parse_deck_download(deck_text, summary)

            # Only add if we got cards (sanity check)
            if deck.cards:
                decks.append(deck)

        except httpx.HTTPError:
            # Skip decks that fail to download
            continue

    return decks
