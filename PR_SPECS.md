# ForgeBreaker - PR Specifications

Complete specifications for each PR. Claude should implement exactly what's specified.

---

## Phase 1: Foundation

---

### PR #1: project-setup

**Branch:** `feature/01-project-setup`

**Files to Create:**

```
forgebreaker/__init__.py
forgebreaker/main.py
forgebreaker/config.py
tests/__init__.py
tests/conftest.py
pyproject.toml
.gitignore
.github/workflows/ci.yml
README.md
```

**pyproject.toml:**

```toml
[build-system]
requires = ["setuptools>=61.0"]
build-backend = "setuptools.build_meta"

[project]
name = "forgebreaker"
version = "0.1.0"
description = "MTG Arena collection manager and deck advisor"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.109.0",
    "uvicorn[standard]>=0.27.0",
    "pydantic>=2.5.0",
    "pydantic-settings>=2.1.0",
    "httpx>=0.26.0",
    "sqlalchemy[asyncio]>=2.0.25",
    "asyncpg>=0.29.0",
    "alembic>=1.13.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.4.0",
    "pytest-asyncio>=0.23.0",
    "pytest-cov>=4.1.0",
    "ruff>=0.1.14",
    "mypy>=1.8.0",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
addopts = "-v --cov=forgebreaker --cov-report=term-missing"

[tool.ruff]
target-version = "py311"
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "I", "N", "W", "UP", "B", "C4", "SIM", "ARG"]

[tool.mypy]
python_version = "3.11"
strict = true
plugins = ["pydantic.mypy"]
```

**forgebreaker/config.py:**

```python
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment."""
    
    app_name: str = "ForgeBreaker"
    debug: bool = False
    
    database_url: str = "postgresql+asyncpg://localhost:5432/forgebreaker"
    
    mlforge_url: str = "https://backend-production-b2b8.up.railway.app"
    
    anthropic_api_key: str = ""
    
    class Config:
        env_file = ".env"


settings = Settings()
```

**forgebreaker/main.py:**

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from forgebreaker.config import settings

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Tighten in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "healthy"}


@app.get("/ready")
async def ready() -> dict[str, str]:
    return {"status": "ready"}
```

**.github/workflows/ci.yml:**

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      
      - name: Install dependencies
        run: |
          pip install -e ".[dev]"
      
      - name: Lint
        run: |
          ruff check .
          ruff format --check .
      
      - name: Type check
        run: mypy forgebreaker
      
      - name: Test
        run: pytest
```

**tests/conftest.py:**

```python
import pytest


@pytest.fixture
def sample_arena_export() -> str:
    """Sample Arena deck export for testing."""
    return """Deck
4 Lightning Bolt (LEB) 163
4 Monastery Swiftspear (BRO) 144
20 Mountain (NEO) 290

Sideboard
2 Abrade (VOW) 139"""
```

**Acceptance Criteria:**
- [ ] `pip install -e ".[dev]"` succeeds
- [ ] `ruff check .` passes
- [ ] `mypy forgebreaker` passes
- [ ] `pytest` runs (0 tests is OK for this PR)
- [ ] `uvicorn forgebreaker.main:app` starts
- [ ] GET /health returns 200

---

### PR #2: models-core

**Branch:** `feature/02-models-core`

**Files to Create:**

```
forgebreaker/models/__init__.py
forgebreaker/models/card.py
forgebreaker/models/collection.py
forgebreaker/models/deck.py
tests/test_models.py
```

**forgebreaker/models/card.py:**

```python
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Card:
    """
    A card instance with quantity.
    
    Attributes:
        name: Card name exactly as it appears in Arena
        quantity: Number of copies (1-4 for most cards, unlimited for basic lands)
        set_code: Three-letter set code (e.g., "LEB", "DMU")
        collector_number: Collector number within set
        arena_id: Arena's internal card ID (for log parsing)
    """
    name: str
    quantity: int
    set_code: str | None = None
    collector_number: str | None = None
    arena_id: int | None = None
```

**forgebreaker/models/collection.py:**

```python
from dataclasses import dataclass, field


@dataclass
class Collection:
    """
    A user's card collection.
    
    Cards are stored by name with max quantity owned.
    For most cards, max is 4. Basic lands can exceed 4.
    """
    cards: dict[str, int] = field(default_factory=dict)
    
    def owns(self, card_name: str, quantity: int = 1) -> bool:
        """Check if collection contains at least `quantity` of a card."""
        return self.cards.get(card_name, 0) >= quantity
    
    def get_quantity(self, card_name: str) -> int:
        """Get quantity owned of a specific card."""
        return self.cards.get(card_name, 0)
    
    def add_card(self, card_name: str, quantity: int = 1) -> None:
        """Add cards to collection."""
        self.cards[card_name] = self.cards.get(card_name, 0) + quantity
    
    def total_cards(self) -> int:
        """Total number of cards in collection."""
        return sum(self.cards.values())
    
    def unique_cards(self) -> int:
        """Number of unique cards in collection."""
        return len(self.cards)
```

**forgebreaker/models/deck.py:**

```python
from dataclasses import dataclass, field


@dataclass
class MetaDeck:
    """
    A competitive deck from the metagame.
    
    Attributes:
        name: Deck archetype name (e.g., "Mono-Red Aggro")
        archetype: Play style category
        format: Arena format (standard, historic, explorer, timeless)
        cards: Maindeck cards {name: quantity}
        sideboard: Sideboard cards {name: quantity}
        win_rate: Estimated win rate from meta source (0.0-1.0)
        meta_share: Percentage of meta this deck represents
        source_url: Where this deck list came from
    """
    name: str
    archetype: str  # aggro, midrange, control, combo
    format: str
    cards: dict[str, int] = field(default_factory=dict)
    sideboard: dict[str, int] = field(default_factory=dict)
    win_rate: float | None = None
    meta_share: float | None = None
    source_url: str | None = None
    
    def maindeck_count(self) -> int:
        """Total cards in maindeck."""
        return sum(self.cards.values())
    
    def all_cards(self) -> set[str]:
        """All unique card names in deck including sideboard."""
        return set(self.cards.keys()) | set(self.sideboard.keys())


@dataclass
class WildcardCost:
    """Wildcards needed to complete a deck."""
    common: int = 0
    uncommon: int = 0
    rare: int = 0
    mythic: int = 0
    
    def total(self) -> int:
        """Total wildcards needed."""
        return self.common + self.uncommon + self.rare + self.mythic
    
    def weighted_cost(self) -> float:
        """
        Weighted cost reflecting wildcard scarcity.
        
        Weights based on approximate acquisition difficulty:
        - Common: 0.1 (very easy to get)
        - Uncommon: 0.25
        - Rare: 1.0 (baseline)
        - Mythic: 4.0 (4x harder than rare)
        """
        return (
            self.common * 0.1
            + self.uncommon * 0.25
            + self.rare * 1.0
            + self.mythic * 4.0
        )


@dataclass
class DeckDistance:
    """How far a collection is from completing a deck."""
    deck: MetaDeck
    owned_cards: int
    missing_cards: int
    completion_percentage: float
    wildcard_cost: WildcardCost
    missing_card_list: list[tuple[str, int, str]]  # (name, qty_needed, rarity)
    
    @property
    def is_complete(self) -> bool:
        """True if user owns all cards needed."""
        return self.missing_cards == 0


@dataclass
class RankedDeck:
    """A deck with its ranking score for recommendations."""
    deck: MetaDeck
    distance: DeckDistance
    score: float
    can_build_now: bool
    within_budget: bool
    recommendation_reason: str
```

**tests/test_models.py:**

```python
import pytest
from forgebreaker.models.card import Card
from forgebreaker.models.collection import Collection
from forgebreaker.models.deck import MetaDeck, WildcardCost, DeckDistance


class TestCard:
    def test_card_creation(self):
        card = Card(name="Lightning Bolt", quantity=4, set_code="LEB")
        assert card.name == "Lightning Bolt"
        assert card.quantity == 4
        assert card.set_code == "LEB"
    
    def test_card_immutable(self):
        card = Card(name="Lightning Bolt", quantity=4)
        with pytest.raises(AttributeError):
            card.quantity = 3  # type: ignore
    
    def test_card_optional_fields(self):
        card = Card(name="Mountain", quantity=20)
        assert card.set_code is None
        assert card.collector_number is None
        assert card.arena_id is None


class TestCollection:
    def test_empty_collection(self):
        collection = Collection()
        assert collection.total_cards() == 0
        assert collection.unique_cards() == 0
    
    def test_add_card(self):
        collection = Collection()
        collection.add_card("Lightning Bolt", 4)
        assert collection.get_quantity("Lightning Bolt") == 4
    
    def test_add_card_stacks(self):
        collection = Collection()
        collection.add_card("Lightning Bolt", 2)
        collection.add_card("Lightning Bolt", 2)
        assert collection.get_quantity("Lightning Bolt") == 4
    
    def test_owns_card(self):
        collection = Collection(cards={"Lightning Bolt": 4})
        assert collection.owns("Lightning Bolt", 4) is True
        assert collection.owns("Lightning Bolt", 5) is False
        assert collection.owns("Counterspell", 1) is False
    
    def test_get_quantity_missing_card(self):
        collection = Collection()
        assert collection.get_quantity("Nonexistent Card") == 0


class TestMetaDeck:
    def test_maindeck_count(self):
        deck = MetaDeck(
            name="Test Deck",
            archetype="aggro",
            format="standard",
            cards={"Lightning Bolt": 4, "Mountain": 20},
        )
        assert deck.maindeck_count() == 24
    
    def test_all_cards_includes_sideboard(self):
        deck = MetaDeck(
            name="Test Deck",
            archetype="aggro",
            format="standard",
            cards={"Lightning Bolt": 4},
            sideboard={"Abrade": 2},
        )
        assert deck.all_cards() == {"Lightning Bolt", "Abrade"}


class TestWildcardCost:
    def test_total(self):
        cost = WildcardCost(common=4, uncommon=8, rare=12, mythic=2)
        assert cost.total() == 26
    
    def test_weighted_cost(self):
        # 4 mythics = 16.0 weighted
        # 4 rares = 4.0 weighted
        # Total = 20.0
        cost = WildcardCost(rare=4, mythic=4)
        assert cost.weighted_cost() == 20.0
    
    def test_weighted_cost_empty(self):
        cost = WildcardCost()
        assert cost.weighted_cost() == 0.0


class TestDeckDistance:
    def test_is_complete(self):
        deck = MetaDeck(name="Test", archetype="aggro", format="standard")
        
        complete = DeckDistance(
            deck=deck,
            owned_cards=60,
            missing_cards=0,
            completion_percentage=1.0,
            wildcard_cost=WildcardCost(),
            missing_card_list=[],
        )
        assert complete.is_complete is True
        
        incomplete = DeckDistance(
            deck=deck,
            owned_cards=56,
            missing_cards=4,
            completion_percentage=0.93,
            wildcard_cost=WildcardCost(rare=4),
            missing_card_list=[("Sheoldred", 4, "mythic")],
        )
        assert incomplete.is_complete is False
```

**Acceptance Criteria:**
- [ ] All model classes importable from `forgebreaker.models`
- [ ] All tests pass
- [ ] mypy passes with strict mode
- [ ] ruff check passes

---

### PR #3: parser-arena-export

**Branch:** `feature/03-parser-arena-export`

**Files to Create:**

```
forgebreaker/parsers/__init__.py
forgebreaker/parsers/arena_export.py
tests/test_parsers.py
tests/fixtures/sample_collection.txt
```

**forgebreaker/parsers/arena_export.py:**

```python
"""
Parser for MTG Arena deck/collection export format.

Arena export format:
    <quantity> <card name> (<set_code>) <collector_number>
    
Example:
    4 Lightning Bolt (LEB) 163
    4 Monastery Swiftspear (BRO) 144
    
Sections are separated by headers: Deck, Sideboard, Commander, Companion
"""

import re
from forgebreaker.models.card import Card
from forgebreaker.models.collection import Collection


# Pattern: "4 Lightning Bolt (LEB) 163"
# Groups: (quantity, card_name, set_code, collector_number)
ARENA_FULL_PATTERN = re.compile(
    r"^(\d+)\s+(.+?)\s+\(([A-Z0-9]+)\)\s+(\d+)$"
)

# Pattern: "4 Lightning Bolt" (no set info)
# Groups: (quantity, card_name)
ARENA_SIMPLE_PATTERN = re.compile(
    r"^(\d+)\s+(.+)$"
)

# Section headers in Arena exports
SECTION_HEADERS = frozenset({"deck", "sideboard", "commander", "companion"})


def parse_arena_export(text: str) -> list[Card]:
    """
    Parse Arena deck/collection export text into Card objects.
    
    Args:
        text: Raw text from Arena export (clipboard paste)
        
    Returns:
        List of Card objects. Empty list if input is empty/whitespace.
        
    Handles:
        - Full format: "4 Card Name (SET) 123"
        - Simple format: "4 Card Name"
        - Split cards: "4 Fire // Ice (MH2) 290"
        - Section headers (Deck, Sideboard, etc.)
        - Empty lines between sections
    """
    if not text or not text.strip():
        return []
    
    cards: list[Card] = []
    
    for line in text.strip().split("\n"):
        line = line.strip()
        
        # Skip empty lines
        if not line:
            continue
        
        # Skip section headers
        if line.lower() in SECTION_HEADERS:
            continue
        
        # Try full pattern first (with set code)
        match = ARENA_FULL_PATTERN.match(line)
        if match:
            quantity, name, set_code, collector_num = match.groups()
            cards.append(Card(
                name=name,
                quantity=int(quantity),
                set_code=set_code,
                collector_number=collector_num,
            ))
            continue
        
        # Try simple pattern (no set code)
        match = ARENA_SIMPLE_PATTERN.match(line)
        if match:
            quantity, name = match.groups()
            cards.append(Card(
                name=name,
                quantity=int(quantity),
            ))
            continue
        
        # Line didn't match any pattern - skip silently
        # This handles comments or malformed lines gracefully
    
    return cards


def cards_to_collection(cards: list[Card]) -> Collection:
    """
    Aggregate a list of Cards into a Collection.
    
    Combines quantities for duplicate card names.
    
    Args:
        cards: List of Card objects (possibly with duplicates)
        
    Returns:
        Collection with aggregated quantities
    """
    collection = Collection()
    
    for card in cards:
        collection.add_card(card.name, card.quantity)
    
    return collection


def parse_arena_to_collection(text: str) -> Collection:
    """
    Convenience function: parse Arena export directly to Collection.
    
    Args:
        text: Raw Arena export text
        
    Returns:
        Collection with all cards from export
    """
    cards = parse_arena_export(text)
    return cards_to_collection(cards)
```

**tests/fixtures/sample_collection.txt:**

```
Deck
4 Lightning Bolt (LEB) 163
4 Monastery Swiftspear (BRO) 144
2 Sheoldred, the Apocalypse (DMU) 107
4 Fire // Ice (MH2) 290
20 Mountain (NEO) 290

Sideboard
2 Abrade (VOW) 139
3 Roiling Vortex (ZNR) 156
```

**tests/test_parsers.py:**

```python
import pytest
from pathlib import Path
from forgebreaker.parsers.arena_export import (
    parse_arena_export,
    cards_to_collection,
    parse_arena_to_collection,
)
from forgebreaker.models.card import Card


class TestParseArenaExport:
    def test_parse_full_format(self):
        text = "4 Lightning Bolt (LEB) 163"
        result = parse_arena_export(text)
        
        assert len(result) == 1
        assert result[0].name == "Lightning Bolt"
        assert result[0].quantity == 4
        assert result[0].set_code == "LEB"
        assert result[0].collector_number == "163"
    
    def test_parse_simple_format(self):
        text = "4 Lightning Bolt"
        result = parse_arena_export(text)
        
        assert len(result) == 1
        assert result[0].name == "Lightning Bolt"
        assert result[0].quantity == 4
        assert result[0].set_code is None
    
    def test_parse_split_card(self):
        """Split cards have // in the name."""
        text = "4 Fire // Ice (MH2) 290"
        result = parse_arena_export(text)
        
        assert len(result) == 1
        assert result[0].name == "Fire // Ice"
    
    def test_parse_empty_input(self):
        assert parse_arena_export("") == []
        assert parse_arena_export("   ") == []
        assert parse_arena_export("\n\n\n") == []
    
    def test_parse_with_section_headers(self):
        text = """Deck
4 Lightning Bolt (LEB) 163

Sideboard
2 Abrade (VOW) 139"""
        result = parse_arena_export(text)
        
        assert len(result) == 2
        assert result[0].name == "Lightning Bolt"
        assert result[1].name == "Abrade"
    
    def test_parse_ignores_malformed_lines(self):
        text = """4 Lightning Bolt (LEB) 163
This is not a valid card line
Another invalid line
2 Mountain (NEO) 290"""
        result = parse_arena_export(text)
        
        assert len(result) == 2
        assert result[0].name == "Lightning Bolt"
        assert result[1].name == "Mountain"
    
    def test_parse_card_with_comma_in_name(self):
        text = "2 Sheoldred, the Apocalypse (DMU) 107"
        result = parse_arena_export(text)
        
        assert len(result) == 1
        assert result[0].name == "Sheoldred, the Apocalypse"
    
    def test_parse_basic_land_high_quantity(self):
        """Basic lands can have more than 4 copies."""
        text = "24 Mountain (NEO) 290"
        result = parse_arena_export(text)
        
        assert len(result) == 1
        assert result[0].quantity == 24
    
    def test_parse_fixture_file(self):
        """Test parsing the fixture file."""
        fixture_path = Path(__file__).parent / "fixtures" / "sample_collection.txt"
        text = fixture_path.read_text()
        result = parse_arena_export(text)
        
        assert len(result) == 7
        names = [c.name for c in result]
        assert "Lightning Bolt" in names
        assert "Fire // Ice" in names
        assert "Sheoldred, the Apocalypse" in names


class TestCardsToCollection:
    def test_aggregates_duplicates(self):
        cards = [
            Card(name="Lightning Bolt", quantity=2),
            Card(name="Lightning Bolt", quantity=2),
        ]
        collection = cards_to_collection(cards)
        
        assert collection.get_quantity("Lightning Bolt") == 4
    
    def test_preserves_unique_cards(self):
        cards = [
            Card(name="Lightning Bolt", quantity=4),
            Card(name="Mountain", quantity=20),
        ]
        collection = cards_to_collection(cards)
        
        assert collection.unique_cards() == 2
        assert collection.total_cards() == 24


class TestParseArenaToCollection:
    def test_convenience_function(self):
        text = """4 Lightning Bolt (LEB) 163
4 Mountain (NEO) 290"""
        collection = parse_arena_to_collection(text)
        
        assert collection.owns("Lightning Bolt", 4)
        assert collection.owns("Mountain", 4)
```

**Acceptance Criteria:**
- [ ] All tests pass
- [ ] Handles all edge cases listed
- [ ] mypy passes
- [ ] ruff check passes

---

### PR #4: parser-scryfall

**Branch:** `feature/04-parser-scryfall`

**Files to Create:**

```
forgebreaker/parsers/scryfall.py
tests/test_scryfall.py
tests/fixtures/scryfall_sample.json
```

**forgebreaker/parsers/scryfall.py:**

```python
"""
Scryfall bulk data loader.

Downloads and parses Scryfall's bulk card data to build lookup tables
for arena_id -> card_name mapping and card rarities.

Bulk data: https://scryfall.com/docs/api/bulk-data
"""

import json
from pathlib import Path
from typing import TypedDict
import httpx


SCRYFALL_BULK_API = "https://api.scryfall.com/bulk-data"


class CardData(TypedDict):
    """Minimal card data we need from Scryfall."""
    name: str
    arena_id: int | None
    rarity: str  # common, uncommon, rare, mythic


def get_bulk_data_url() -> str:
    """
    Fetch the download URL for Scryfall's default-cards bulk data.
    
    Returns:
        URL to download the bulk JSON file
        
    Raises:
        httpx.HTTPError: If API request fails
    """
    response = httpx.get(
        SCRYFALL_BULK_API,
        headers={"User-Agent": "ForgeBreaker/1.0"},
    )
    response.raise_for_status()
    
    data = response.json()
    
    # Find the "default_cards" entry
    for entry in data["data"]:
        if entry["type"] == "default_cards":
            return entry["download_uri"]
    
    raise ValueError("Could not find default_cards bulk data URL")


def download_bulk_data(output_path: Path) -> None:
    """
    Download Scryfall bulk data to a file.
    
    Args:
        output_path: Where to save the JSON file
        
    Note:
        File is ~80MB, download may take a minute.
    """
    url = get_bulk_data_url()
    
    # Stream download due to file size
    with httpx.stream(
        "GET",
        url,
        headers={"User-Agent": "ForgeBreaker/1.0"},
        follow_redirects=True,
    ) as response:
        response.raise_for_status()
        with open(output_path, "wb") as f:
            for chunk in response.iter_bytes(chunk_size=8192):
                f.write(chunk)


def load_arena_id_mapping(bulk_data_path: Path) -> dict[int, str]:
    """
    Build arena_id -> card_name mapping from bulk data.
    
    Args:
        bulk_data_path: Path to downloaded Scryfall bulk JSON
        
    Returns:
        Dict mapping Arena card IDs to card names
    """
    mapping: dict[int, str] = {}
    
    with open(bulk_data_path, "r", encoding="utf-8") as f:
        cards = json.load(f)
    
    for card in cards:
        arena_id = card.get("arena_id")
        if arena_id is not None:
            mapping[arena_id] = card["name"]
    
    return mapping


def load_rarity_mapping(bulk_data_path: Path) -> dict[str, str]:
    """
    Build card_name -> rarity mapping from bulk data.
    
    Args:
        bulk_data_path: Path to downloaded Scryfall bulk JSON
        
    Returns:
        Dict mapping card names to rarities (common, uncommon, rare, mythic)
        
    Note:
        For cards printed at multiple rarities, uses the most recent printing.
    """
    mapping: dict[str, str] = {}
    
    with open(bulk_data_path, "r", encoding="utf-8") as f:
        cards = json.load(f)
    
    for card in cards:
        name = card["name"]
        rarity = card.get("rarity", "common")
        
        # Normalize rarity names
        if rarity == "mythic":
            rarity = "mythic"
        elif rarity == "rare":
            rarity = "rare"
        elif rarity == "uncommon":
            rarity = "uncommon"
        else:
            rarity = "common"
        
        # Later entries overwrite earlier (more recent printings)
        mapping[name] = rarity
    
    return mapping


def load_card_data(bulk_data_path: Path) -> dict[str, CardData]:
    """
    Load complete card data keyed by name.
    
    Args:
        bulk_data_path: Path to downloaded Scryfall bulk JSON
        
    Returns:
        Dict mapping card names to CardData
    """
    data: dict[str, CardData] = {}
    
    with open(bulk_data_path, "r", encoding="utf-8") as f:
        cards = json.load(f)
    
    for card in cards:
        name = card["name"]
        data[name] = CardData(
            name=name,
            arena_id=card.get("arena_id"),
            rarity=card.get("rarity", "common"),
        )
    
    return data
```

**tests/fixtures/scryfall_sample.json:**

```json
[
  {
    "name": "Lightning Bolt",
    "arena_id": 12345,
    "rarity": "common",
    "set": "leb"
  },
  {
    "name": "Sheoldred, the Apocalypse",
    "arena_id": 82377,
    "rarity": "mythic",
    "set": "dmu"
  },
  {
    "name": "Monastery Swiftspear",
    "arena_id": 54321,
    "rarity": "uncommon",
    "set": "bro"
  },
  {
    "name": "Card Without Arena ID",
    "rarity": "rare",
    "set": "leg"
  }
]
```

**tests/test_scryfall.py:**

```python
import pytest
from pathlib import Path
from forgebreaker.parsers.scryfall import (
    load_arena_id_mapping,
    load_rarity_mapping,
    load_card_data,
)


@pytest.fixture
def sample_bulk_path() -> Path:
    return Path(__file__).parent / "fixtures" / "scryfall_sample.json"


class TestLoadArenaIdMapping:
    def test_loads_arena_ids(self, sample_bulk_path: Path):
        mapping = load_arena_id_mapping(sample_bulk_path)
        
        assert mapping[12345] == "Lightning Bolt"
        assert mapping[82377] == "Sheoldred, the Apocalypse"
    
    def test_skips_cards_without_arena_id(self, sample_bulk_path: Path):
        mapping = load_arena_id_mapping(sample_bulk_path)
        
        # Should only have 3 entries (one card has no arena_id)
        assert len(mapping) == 3


class TestLoadRarityMapping:
    def test_loads_rarities(self, sample_bulk_path: Path):
        mapping = load_rarity_mapping(sample_bulk_path)
        
        assert mapping["Lightning Bolt"] == "common"
        assert mapping["Sheoldred, the Apocalypse"] == "mythic"
        assert mapping["Monastery Swiftspear"] == "uncommon"
        assert mapping["Card Without Arena ID"] == "rare"


class TestLoadCardData:
    def test_loads_complete_data(self, sample_bulk_path: Path):
        data = load_card_data(sample_bulk_path)
        
        bolt = data["Lightning Bolt"]
        assert bolt["name"] == "Lightning Bolt"
        assert bolt["arena_id"] == 12345
        assert bolt["rarity"] == "common"
    
    def test_handles_missing_arena_id(self, sample_bulk_path: Path):
        data = load_card_data(sample_bulk_path)
        
        card = data["Card Without Arena ID"]
        assert card["arena_id"] is None
```

**Acceptance Criteria:**
- [ ] All tests pass
- [ ] Can parse sample fixture
- [ ] mypy passes
- [ ] ruff check passes

---

## Phase 2: Core Logic

---

### PR #5: analysis-distance

**Branch:** `feature/05-analysis-distance`

**Files to Create:**

```
forgebreaker/analysis/__init__.py
forgebreaker/analysis/distance.py
tests/test_analysis.py
```

**forgebreaker/analysis/distance.py:**

```python
"""
Deck distance calculation.

Calculates how "far" a user's collection is from being able to build
a specific deck, measured in missing cards and wildcard cost.
"""

from forgebreaker.models.collection import Collection
from forgebreaker.models.deck import MetaDeck, WildcardCost, DeckDistance


def get_card_rarity(card_name: str, rarity_db: dict[str, str]) -> str:
    """
    Look up card rarity from database.
    
    Args:
        card_name: Name of the card
        rarity_db: Mapping of card names to rarities
        
    Returns:
        Rarity string. Defaults to "rare" if not found (conservative estimate).
    """
    return rarity_db.get(card_name, "rare")


def calculate_deck_distance(
    collection: Collection,
    deck: MetaDeck,
    rarity_db: dict[str, str],
) -> DeckDistance:
    """
    Calculate how far a collection is from completing a deck.
    
    Args:
        collection: User's card collection
        deck: Target deck to build
        rarity_db: Card name -> rarity mapping
        
    Returns:
        DeckDistance with ownership stats, wildcard costs, and missing cards
    """
    owned = 0
    missing = 0
    missing_list: list[tuple[str, int, str]] = []
    wildcards = WildcardCost()
    
    # Check each card in the deck's maindeck
    for card_name, required_qty in deck.cards.items():
        owned_qty = collection.get_quantity(card_name)
        
        if owned_qty >= required_qty:
            # User owns enough copies
            owned += required_qty
        else:
            # User is short some copies
            owned += owned_qty
            needed = required_qty - owned_qty
            missing += needed
            
            rarity = get_card_rarity(card_name, rarity_db)
            missing_list.append((card_name, needed, rarity))
            
            # Add to appropriate wildcard bucket
            if rarity == "common":
                wildcards.common += needed
            elif rarity == "uncommon":
                wildcards.uncommon += needed
            elif rarity == "rare":
                wildcards.rare += needed
            elif rarity == "mythic":
                wildcards.mythic += needed
    
    total_cards = deck.maindeck_count()
    completion = owned / total_cards if total_cards > 0 else 0.0
    
    return DeckDistance(
        deck=deck,
        owned_cards=owned,
        missing_cards=missing,
        completion_percentage=completion,
        wildcard_cost=wildcards,
        missing_card_list=missing_list,
    )
```

**tests/test_analysis.py:**

```python
import pytest
from forgebreaker.models.collection import Collection
from forgebreaker.models.deck import MetaDeck
from forgebreaker.analysis.distance import calculate_deck_distance


@pytest.fixture
def rarity_db() -> dict[str, str]:
    return {
        "Lightning Bolt": "common",
        "Monastery Swiftspear": "uncommon",
        "Sheoldred, the Apocalypse": "mythic",
        "Mountain": "common",
        "Den of the Bugbear": "rare",
    }


@pytest.fixture
def sample_deck() -> MetaDeck:
    return MetaDeck(
        name="Mono-Red Aggro",
        archetype="aggro",
        format="standard",
        cards={
            "Lightning Bolt": 4,
            "Monastery Swiftspear": 4,
            "Mountain": 20,
        },
    )


class TestCalculateDeckDistance:
    def test_complete_deck(self, sample_deck: MetaDeck, rarity_db: dict[str, str]):
        """User owns all cards needed."""
        collection = Collection(cards={
            "Lightning Bolt": 4,
            "Monastery Swiftspear": 4,
            "Mountain": 20,
        })
        
        distance = calculate_deck_distance(collection, sample_deck, rarity_db)
        
        assert distance.is_complete
        assert distance.owned_cards == 28
        assert distance.missing_cards == 0
        assert distance.completion_percentage == 1.0
        assert distance.wildcard_cost.total() == 0
    
    def test_partial_ownership(self, sample_deck: MetaDeck, rarity_db: dict[str, str]):
        """User owns some but not all cards."""
        collection = Collection(cards={
            "Lightning Bolt": 4,
            "Monastery Swiftspear": 2,  # Missing 2
            "Mountain": 20,
        })
        
        distance = calculate_deck_distance(collection, sample_deck, rarity_db)
        
        assert not distance.is_complete
        assert distance.owned_cards == 26
        assert distance.missing_cards == 2
        assert distance.wildcard_cost.uncommon == 2
    
    def test_empty_collection(self, sample_deck: MetaDeck, rarity_db: dict[str, str]):
        """User owns nothing."""
        collection = Collection()
        
        distance = calculate_deck_distance(collection, sample_deck, rarity_db)
        
        assert distance.owned_cards == 0
        assert distance.missing_cards == 28
        assert distance.completion_percentage == 0.0
    
    def test_missing_card_list(self, rarity_db: dict[str, str]):
        """Verify missing card list contains correct data."""
        deck = MetaDeck(
            name="Test",
            archetype="control",
            format="standard",
            cards={
                "Sheoldred, the Apocalypse": 4,
                "Den of the Bugbear": 2,
            },
        )
        collection = Collection(cards={
            "Sheoldred, the Apocalypse": 2,  # Missing 2
            # Missing all Den of the Bugbear
        })
        
        distance = calculate_deck_distance(collection, deck, rarity_db)
        
        assert len(distance.missing_card_list) == 2
        
        # Check mythic
        sheoldred = next(c for c in distance.missing_card_list if c[0] == "Sheoldred, the Apocalypse")
        assert sheoldred[1] == 2  # need 2
        assert sheoldred[2] == "mythic"
        
        # Check rare
        den = next(c for c in distance.missing_card_list if c[0] == "Den of the Bugbear")
        assert den[1] == 2
        assert den[2] == "rare"
    
    def test_unknown_rarity_defaults_to_rare(self, sample_deck: MetaDeck):
        """Cards not in rarity_db should default to rare."""
        collection = Collection()
        rarity_db: dict[str, str] = {}  # Empty - no rarities known
        
        distance = calculate_deck_distance(collection, sample_deck, rarity_db)
        
        # All cards should be counted as rare
        assert distance.wildcard_cost.rare == 28
        assert distance.wildcard_cost.common == 0
```

**Acceptance Criteria:**
- [ ] All tests pass
- [ ] Correctly calculates ownership
- [ ] Correctly categorizes wildcards by rarity
- [ ] mypy passes
- [ ] ruff check passes

---

*[Document continues with PRs #6-25 in same format...]*

---

## Quick Reference: All PRs

| PR | Branch | Component | Est. Lines |
|----|--------|-----------|------------|
| 1 | feature/01-project-setup | Project scaffolding | 150 |
| 2 | feature/02-models-core | Data models | 200 |
| 3 | feature/03-parser-arena-export | Arena text parser | 150 |
| 4 | feature/04-parser-scryfall | Scryfall loader | 150 |
| 5 | feature/05-analysis-distance | Distance calculation | 100 |
| 6 | feature/06-analysis-ranker | Deck ranking | 150 |
| 7 | feature/07-scraper-mtggoldfish | Meta deck scraper | 150 |
| 8 | feature/08-db-models | SQLAlchemy models | 150 |
| 9 | feature/09-db-operations | CRUD operations | 150 |
| 10 | feature/10-api-collection | Collection endpoints | 150 |
| 11 | feature/11-api-decks | Deck endpoints | 150 |
| 12 | feature/12-api-distance | Distance endpoint | 100 |
| 13 | feature/13-api-health | Health endpoints | 50 |
| 14 | feature/14-ml-features | Feature engineering | 100 |
| 15 | feature/15-ml-inference | MLForge client | 100 |
| 16 | feature/16-mcp-tools | MCP tool definitions | 150 |
| 17 | feature/17-api-chat | Chat endpoint | 150 |
| 18 | feature/18-frontend-setup | Vite + React + Tailwind | 200 |
| 19 | feature/19-frontend-collection | Collection import | 200 |
| 20 | feature/20-frontend-deck-browser | Deck list | 200 |
| 21 | feature/21-frontend-deck-detail | Deck detail view | 200 |
| 22 | feature/22-frontend-chat | Chat interface | 200 |
| 23 | feature/23-jobs-meta-update | Scheduled refresh | 100 |
| 24 | feature/24-deployment | Railway config | 100 |
| 25 | feature/25-docs | Documentation | 150 |
