"""
Scheduled job to refresh meta deck data.

Fetches current meta decks from MTGGoldfish and syncs to database.
Can be run as a standalone script or called from a scheduler.
"""

import asyncio
import logging

import httpx

from forgebreaker.db.database import async_session_factory
from forgebreaker.db.operations import sync_meta_decks
from forgebreaker.scrapers.mtggoldfish import VALID_FORMATS, fetch_meta_decks

logger = logging.getLogger(__name__)

DEFAULT_DECKS_PER_FORMAT = 15


async def update_format(format_name: str, limit: int, client: httpx.Client) -> int:
    """
    Update meta decks for a single format.

    Args:
        format_name: Format to update (standard, historic, etc.)
        limit: Max number of decks to fetch
        client: HTTP client for requests

    Returns:
        Number of decks synced
    """
    logger.info("Fetching meta decks for %s...", format_name)

    try:
        decks = fetch_meta_decks(format_name, limit=limit, client=client)
        logger.info("Fetched %d decks for %s", len(decks), format_name)

        async with async_session_factory() as session:
            count = await sync_meta_decks(session, format_name, decks)
            await session.commit()

        logger.info("Synced %d decks for %s", count, format_name)
        return count

    except httpx.HTTPError as e:
        logger.error("HTTP error fetching %s: %s", format_name, e)
        return 0
    except Exception as e:
        logger.error("Error updating %s: %s", format_name, e)
        return 0


async def run_meta_update(
    formats: list[str] | None = None,
    limit: int = DEFAULT_DECKS_PER_FORMAT,
) -> dict[str, int]:
    """
    Run meta deck update for all or specified formats.

    Args:
        formats: List of formats to update. If None, updates all valid formats.
        limit: Max number of decks per format

    Returns:
        Dict mapping format name to number of decks synced
    """
    if formats is None:
        formats = list(VALID_FORMATS)

    results: dict[str, int] = {}

    with httpx.Client(
        headers={"User-Agent": "ForgeBreaker/1.0"},
        follow_redirects=True,
        timeout=30.0,
    ) as client:
        for format_name in formats:
            if format_name not in VALID_FORMATS:
                logger.warning("Skipping invalid format: %s", format_name)
                continue

            results[format_name] = await update_format(format_name, limit, client)

    total = sum(results.values())
    logger.info("Meta update complete. Total decks synced: %d", total)
    return results


def main() -> None:
    """CLI entry point for running meta update."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    asyncio.run(run_meta_update())


if __name__ == "__main__":
    main()
