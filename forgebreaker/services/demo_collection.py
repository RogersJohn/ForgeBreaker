"""
Demo collection loader service.

Provides read-only access to a sample MTG Arena collection for demo mode.
The demo collection is loaded from collection.csv at the repository root.
"""

import csv
from functools import lru_cache
from pathlib import Path

from forgebreaker.models.collection import Collection

# Path to the demo collection CSV file (repository root)
DEMO_COLLECTION_PATH = Path(__file__).parent.parent.parent / "collection.csv"


class DemoCollectionError(Exception):
    """Raised when demo collection cannot be loaded."""

    pass


@lru_cache(maxsize=1)
def _load_demo_cards() -> dict[str, int]:
    """
    Load demo collection from CSV file.

    Returns cards with Count > 0 as dict of card name -> quantity.
    Cached after first load (demo data is read-only).
    """
    if not DEMO_COLLECTION_PATH.exists():
        raise DemoCollectionError(f"Demo collection file not found: {DEMO_COLLECTION_PATH}")

    cards: dict[str, int] = {}

    with open(DEMO_COLLECTION_PATH, encoding="utf-8") as f:
        reader = csv.DictReader(f)

        for row in reader:
            try:
                name = row.get("Name", "").strip()
                count_str = row.get("Count", "0").strip()
                count = int(count_str) if count_str else 0

                if name and count > 0:
                    # Take max if duplicate card names exist
                    cards[name] = max(cards.get(name, 0), count)
            except (ValueError, KeyError):
                # Skip malformed rows silently
                continue

    if not cards:
        raise DemoCollectionError("Demo collection contains no cards with Count > 0")

    return cards


def get_demo_collection() -> Collection:
    """
    Get the demo collection as a Collection model.

    This is read-only sample data for users who haven't uploaded their own.
    """
    cards = _load_demo_cards()
    return Collection(cards=cards.copy())


def get_demo_cards() -> dict[str, int]:
    """
    Get the demo collection as a raw dictionary.

    Returns a copy to prevent mutation of cached data.
    """
    return _load_demo_cards().copy()


def demo_collection_available() -> bool:
    """Check if demo collection file exists and is loadable."""
    try:
        _load_demo_cards()
        return True
    except DemoCollectionError:
        return False
