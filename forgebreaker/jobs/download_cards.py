"""
Download Scryfall card database.

Run this job to download the latest card data for collection search and deck building.
"""

import asyncio
import logging

from forgebreaker.services.card_database import download_card_database

logger = logging.getLogger(__name__)


async def run_download() -> None:
    """Download the Scryfall card database."""
    logger.info("Downloading Scryfall card database...")

    try:
        path = await download_card_database()
        logger.info("Downloaded card database to %s", path)
    except Exception as e:
        logger.error("Failed to download card database: %s", e)
        raise


def main() -> None:
    """CLI entry point."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    asyncio.run(run_download())


if __name__ == "__main__":
    main()
