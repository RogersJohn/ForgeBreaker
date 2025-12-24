# ForgeBreaker - Additional PR Specifications (Deck Building Tools)

These PRs add the missing deck building capabilities that transform ForgeBreaker from a "meta deck distance calculator" into an actual deck building assistant.

**Add this file to your repo as `PR_SPECS_PHASE2.md`**

---

## Overview

| PR | Branch | Component | Est. Lines | Priority |
|----|--------|-----------|------------|----------|
| 26 | feature/26-tool-search-collection | Collection search tool | 150 | High |
| 27 | feature/27-tool-build-deck | Deck building tool | 300 | High |
| 28 | feature/28-tool-find-synergies | Synergy finder tool | 150 | Medium |
| 29 | feature/29-tool-export-arena | Arena export tool | 50 | High |
| 30 | feature/30-card-database | Card database with Scryfall data | 200 | High |
| 31 | feature/31-integration-prompts | LLM prompt improvements | 100 | High |

**Total estimated effort: ~12 hours**

---

## PR #26: Collection Search Tool

**Branch:** `feature/26-tool-search-collection`

**Problem:** The LLM cannot search the user's collection for specific cards. When a user asks "do I have any shrine cards?", the LLM has no way to answer.

**Solution:** Add a `search_collection` MCP tool that filters the user's collection by name, type, color, set, and other criteria.

---

### Files to Create

```
forgebreaker/services/__init__.py
forgebreaker/services/collection_search.py
tests/test_collection_search.py
```

### Files to Modify

```
forgebreaker/mcp/tools.py  (add new tool definition)
forgebreaker/api/chat.py   (add tool handler)
```

---

### forgebreaker/services/collection_search.py

```python
"""
Collection search service.

Provides filtered search over a user's card collection.
"""

from dataclasses import dataclass
from forgebreaker.models.collection import Collection


@dataclass
class CardSearchResult:
    """A card matching search criteria."""
    name: str
    quantity: int
    set_code: str | None
    rarity: str
    colors: list[str]
    type_line: str
    mana_cost: str


def search_collection(
    collection: Collection,
    card_db: dict[str, dict],
    name_contains: str | None = None,
    card_type: str | None = None,
    colors: list[str] | None = None,
    set_code: str | None = None,
    rarity: str | None = None,
    min_quantity: int = 1,
    max_results: int = 50,
) -> list[CardSearchResult]:
    """
    Search user's collection for cards matching criteria.
    
    Args:
        collection: User's card collection
        card_db: Scryfall card database {name: card_data}
        name_contains: Filter cards with this text in name (case-insensitive)
        card_type: Filter by type line (e.g., "Creature", "Enchantment", "Shrine")
        colors: Filter by color identity (e.g., ["R", "W"])
        set_code: Filter by set (e.g., "DMU", "M21")
        rarity: Filter by rarity ("common", "uncommon", "rare", "mythic")
        min_quantity: Only return cards owned in at least this quantity
        max_results: Maximum results to return
        
    Returns:
        List of CardSearchResult matching all criteria
        
    Example:
        >>> search_collection(collection, card_db, name_contains="shrine")
        [CardSearchResult(name="Sanctum of Stone Fangs", quantity=4, ...)]
    """
    results: list[CardSearchResult] = []
    
    for card_name, quantity in collection.cards.items():
        # Skip if below minimum quantity
        if quantity < min_quantity:
            continue
        
        # Get card data from database
        card_data = card_db.get(card_name)
        if not card_data:
            # Card not in database, skip (might be a renamed card)
            continue
        
        # Apply name filter
        if name_contains:
            if name_contains.lower() not in card_name.lower():
                continue
        
        # Apply type filter
        if card_type:
            type_line = card_data.get("type_line", "")
            if card_type.lower() not in type_line.lower():
                continue
        
        # Apply color filter
        if colors:
            card_colors = set(card_data.get("colors", []))
            filter_colors = set(c.upper() for c in colors)
            # Card must have at least one matching color (or be colorless if [] passed)
            if filter_colors and not card_colors.intersection(filter_colors):
                continue
        
        # Apply set filter
        if set_code:
            if card_data.get("set", "").upper() != set_code.upper():
                continue
        
        # Apply rarity filter
        if rarity:
            if card_data.get("rarity", "").lower() != rarity.lower():
                continue
        
        # Card passed all filters
        results.append(CardSearchResult(
            name=card_name,
            quantity=quantity,
            set_code=card_data.get("set"),
            rarity=card_data.get("rarity", "common"),
            colors=card_data.get("colors", []),
            type_line=card_data.get("type_line", ""),
            mana_cost=card_data.get("mana_cost", ""),
        ))
        
        if len(results) >= max_results:
            break
    
    # Sort by quantity descending, then name
    results.sort(key=lambda x: (-x.quantity, x.name))
    
    return results


def format_search_results(results: list[CardSearchResult]) -> str:
    """
    Format search results for LLM response.
    
    Returns human-readable string listing cards found.
    """
    if not results:
        return "No cards found matching your criteria."
    
    lines = [f"Found {len(results)} cards:\n"]
    
    for card in results:
        colors_str = "".join(card.colors) if card.colors else "C"
        lines.append(
            f"- {card.quantity}x {card.name} ({colors_str}) - {card.type_line}"
        )
    
    return "\n".join(lines)
```

---

### MCP Tool Definition (add to forgebreaker/mcp/tools.py)

```python
SEARCH_COLLECTION_TOOL = {
    "name": "search_collection",
    "description": """Search the user's card collection for cards matching specific criteria.
    
Use this tool when the user asks about:
- What cards they own ("do I have any goblins?")
- Cards of a specific type ("show me my enchantments")
- Cards from a specific set ("what did I get from Foundations?")
- Cards for a theme ("find my shrine cards")

The tool returns a list of matching cards with quantities.""",
    "input_schema": {
        "type": "object",
        "properties": {
            "name_contains": {
                "type": "string",
                "description": "Find cards with this text in the name. Case-insensitive. Example: 'shrine', 'goblin', 'lightning'"
            },
            "card_type": {
                "type": "string",
                "description": "Filter by card type. Example: 'Creature', 'Enchantment', 'Instant', 'Sorcery', 'Land', 'Artifact', 'Planeswalker'"
            },
            "colors": {
                "type": "array",
                "items": {"type": "string", "enum": ["W", "U", "B", "R", "G"]},
                "description": "Filter by color identity. W=White, U=Blue, B=Black, R=Red, G=Green. Example: ['R', 'W'] for Boros cards"
            },
            "set_code": {
                "type": "string",
                "description": "Filter by set code. Example: 'DMU' for Dominaria United, 'ONE' for Phyrexia, 'FDN' for Foundations"
            },
            "rarity": {
                "type": "string",
                "enum": ["common", "uncommon", "rare", "mythic"],
                "description": "Filter by rarity"
            },
            "min_quantity": {
                "type": "integer",
                "description": "Only show cards owned in at least this quantity. Default: 1",
                "default": 1
            }
        }
    }
}
```

---

### tests/test_collection_search.py

```python
import pytest
from forgebreaker.models.collection import Collection
from forgebreaker.services.collection_search import (
    search_collection,
    format_search_results,
    CardSearchResult,
)


@pytest.fixture
def sample_card_db() -> dict[str, dict]:
    return {
        "Sanctum of Stone Fangs": {
            "type_line": "Legendary Enchantment — Shrine",
            "colors": ["B"],
            "set": "M21",
            "rarity": "uncommon",
            "mana_cost": "{1}{B}",
        },
        "Sanctum of Shattered Heights": {
            "type_line": "Legendary Enchantment — Shrine",
            "colors": ["R"],
            "set": "M21",
            "rarity": "uncommon",
            "mana_cost": "{2}{R}",
        },
        "Lightning Bolt": {
            "type_line": "Instant",
            "colors": ["R"],
            "set": "LEB",
            "rarity": "common",
            "mana_cost": "{R}",
        },
        "Sheoldred, the Apocalypse": {
            "type_line": "Legendary Creature — Phyrexian Praetor",
            "colors": ["B"],
            "set": "DMU",
            "rarity": "mythic",
            "mana_cost": "{2}{B}{B}",
        },
        "Forest": {
            "type_line": "Basic Land — Forest",
            "colors": [],
            "set": "FDN",
            "rarity": "common",
            "mana_cost": "",
        },
    }


@pytest.fixture
def sample_collection() -> Collection:
    return Collection(cards={
        "Sanctum of Stone Fangs": 4,
        "Sanctum of Shattered Heights": 3,
        "Lightning Bolt": 4,
        "Sheoldred, the Apocalypse": 2,
        "Forest": 20,
    })


class TestSearchCollection:
    def test_search_by_name(self, sample_collection, sample_card_db):
        results = search_collection(
            sample_collection, sample_card_db,
            name_contains="sanctum"
        )
        
        assert len(results) == 2
        names = [r.name for r in results]
        assert "Sanctum of Stone Fangs" in names
        assert "Sanctum of Shattered Heights" in names
    
    def test_search_by_type(self, sample_collection, sample_card_db):
        results = search_collection(
            sample_collection, sample_card_db,
            card_type="Shrine"
        )
        
        assert len(results) == 2
        for r in results:
            assert "Shrine" in r.type_line
    
    def test_search_by_color(self, sample_collection, sample_card_db):
        results = search_collection(
            sample_collection, sample_card_db,
            colors=["R"]
        )
        
        assert len(results) == 2
        names = [r.name for r in results]
        assert "Lightning Bolt" in names
        assert "Sanctum of Shattered Heights" in names
    
    def test_search_by_set(self, sample_collection, sample_card_db):
        results = search_collection(
            sample_collection, sample_card_db,
            set_code="M21"
        )
        
        assert len(results) == 2
        for r in results:
            assert r.set_code == "M21"
    
    def test_search_by_rarity(self, sample_collection, sample_card_db):
        results = search_collection(
            sample_collection, sample_card_db,
            rarity="mythic"
        )
        
        assert len(results) == 1
        assert results[0].name == "Sheoldred, the Apocalypse"
    
    def test_search_combined_filters(self, sample_collection, sample_card_db):
        """Multiple filters should AND together."""
        results = search_collection(
            sample_collection, sample_card_db,
            card_type="Enchantment",
            colors=["B"]
        )
        
        assert len(results) == 1
        assert results[0].name == "Sanctum of Stone Fangs"
    
    def test_search_no_results(self, sample_collection, sample_card_db):
        results = search_collection(
            sample_collection, sample_card_db,
            name_contains="nonexistent"
        )
        
        assert results == []
    
    def test_search_min_quantity(self, sample_collection, sample_card_db):
        results = search_collection(
            sample_collection, sample_card_db,
            min_quantity=4
        )
        
        # Only cards with 4+ copies
        names = [r.name for r in results]
        assert "Lightning Bolt" in names
        assert "Sanctum of Stone Fangs" in names
        assert "Forest" in names  # 20 copies
        assert "Sheoldred, the Apocalypse" not in names  # only 2


class TestFormatSearchResults:
    def test_format_empty(self):
        result = format_search_results([])
        assert "No cards found" in result
    
    def test_format_results(self, sample_card_db):
        results = [
            CardSearchResult(
                name="Lightning Bolt",
                quantity=4,
                set_code="LEB",
                rarity="common",
                colors=["R"],
                type_line="Instant",
                mana_cost="{R}",
            )
        ]
        
        formatted = format_search_results(results)
        assert "Found 1 cards" in formatted
        assert "4x Lightning Bolt" in formatted
        assert "(R)" in formatted  # Color
```

---

### Acceptance Criteria

- [ ] `search_collection` returns correct results for all filter types
- [ ] Filters combine with AND logic
- [ ] Results sorted by quantity (highest first)
- [ ] Empty results handled gracefully
- [ ] All tests pass
- [ ] MCP tool definition added
- [ ] Chat API handles the tool call

---

## PR #27: Deck Building Tool

**Branch:** `feature/27-tool-build-deck`

**Problem:** The LLM cannot build custom decks. When a user asks "build me a shrine deck", the LLM can only suggest pre-defined meta decks.

**Solution:** Add a `build_deck` MCP tool that constructs a 60-card deck from the user's collection around a theme.

---

### Files to Create

```
forgebreaker/services/deck_builder.py
tests/test_deck_builder.py
```

### Files to Modify

```
forgebreaker/mcp/tools.py
forgebreaker/api/chat.py
```

---

### forgebreaker/services/deck_builder.py

```python
"""
Deck building service.

Builds playable decks from user's collection around a theme.
"""

from dataclasses import dataclass, field
from forgebreaker.models.collection import Collection


@dataclass
class BuiltDeck:
    """A deck constructed from user's collection."""
    name: str
    cards: dict[str, int]  # card_name -> quantity
    total_cards: int
    colors: set[str]
    theme_cards: list[str]
    support_cards: list[str]
    lands: dict[str, int]
    notes: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class DeckBuildRequest:
    """Parameters for deck building."""
    theme: str  # Card name, type, or keyword to build around
    colors: list[str] | None = None  # Color restriction
    format: str = "standard"  # Format for legality checking
    include_cards: list[str] | None = None  # Must-include cards
    deck_size: int = 60  # Target deck size
    land_count: int = 24  # Target land count


def build_deck(
    request: DeckBuildRequest,
    collection: Collection,
    card_db: dict[str, dict],
    format_legality: dict[str, set[str]],  # format -> set of legal card names
) -> BuiltDeck:
    """
    Build a deck from user's collection around a theme.
    
    Strategy:
    1. Find all cards matching the theme that user owns
    2. Determine color identity from theme cards
    3. Add support cards (removal, card draw) in those colors
    4. Fill mana base from owned lands
    5. Validate deck size and provide warnings
    
    Args:
        request: Deck building parameters
        collection: User's card collection
        card_db: Scryfall card database
        format_legality: Legal cards per format
        
    Returns:
        BuiltDeck with cards, lands, and notes
    """
    notes: list[str] = []
    warnings: list[str] = []
    
    legal_cards = format_legality.get(request.format, set())
    
    # Step 1: Find theme cards
    theme_cards: list[tuple[str, int, dict]] = []
    
    for card_name, qty in collection.cards.items():
        if card_name not in legal_cards:
            continue
        
        card_data = card_db.get(card_name)
        if not card_data:
            continue
        
        # Check if card matches theme
        if _matches_theme(card_name, card_data, request.theme):
            theme_cards.append((card_name, qty, card_data))
    
    if not theme_cards:
        warnings.append(f"No cards matching theme '{request.theme}' found in your collection")
        return BuiltDeck(
            name=f"{request.theme} Deck",
            cards={},
            total_cards=0,
            colors=set(),
            theme_cards=[],
            support_cards=[],
            lands={},
            notes=notes,
            warnings=warnings,
        )
    
    notes.append(f"Found {len(theme_cards)} cards matching theme '{request.theme}'")
    
    # Step 2: Determine colors
    deck_colors: set[str] = set()
    for _, _, card_data in theme_cards:
        deck_colors.update(card_data.get("colors", []))
    
    if request.colors:
        deck_colors = deck_colors.intersection(set(c.upper() for c in request.colors))
    
    if not deck_colors:
        deck_colors = {"C"}  # Colorless
    
    notes.append(f"Deck colors: {', '.join(sorted(deck_colors))}")
    
    # Step 3: Build deck
    deck: dict[str, int] = {}
    nonland_target = request.deck_size - request.land_count
    
    # Add must-include cards first
    if request.include_cards:
        for card_name in request.include_cards:
            owned = collection.get_quantity(card_name)
            if owned > 0 and card_name in legal_cards:
                deck[card_name] = min(owned, 4)
            else:
                warnings.append(f"Cannot include {card_name} - not owned or not legal")
    
    # Add theme cards (prioritize)
    for card_name, qty, card_data in theme_cards:
        if card_name in deck:
            continue
        deck[card_name] = min(qty, 4)
    
    current_count = sum(deck.values())
    theme_card_names = [name for name, _, _ in theme_cards]
    
    # Step 4: Add support cards
    support_cards: list[str] = []
    
    if current_count < nonland_target:
        support = _find_support_cards(
            collection, card_db, legal_cards,
            deck_colors, set(deck.keys()),
            nonland_target - current_count
        )
        
        for card_name, qty in support:
            deck[card_name] = qty
            support_cards.append(card_name)
    
    current_count = sum(deck.values())
    
    if current_count < nonland_target:
        warnings.append(
            f"Could only find {current_count} nonland cards "
            f"(target: {nonland_target})"
        )
    
    # Step 5: Add lands
    lands = _build_mana_base(
        collection, card_db, legal_cards,
        deck_colors, request.land_count
    )
    
    total_lands = sum(lands.values())
    if total_lands < request.land_count:
        warnings.append(
            f"Could only find {total_lands} appropriate lands "
            f"(target: {request.land_count})"
        )
    
    total_cards = current_count + total_lands
    
    return BuiltDeck(
        name=f"{request.theme.title()} Deck",
        cards=deck,
        total_cards=total_cards,
        colors=deck_colors,
        theme_cards=theme_card_names,
        support_cards=support_cards,
        lands=lands,
        notes=notes,
        warnings=warnings,
    )


def _matches_theme(card_name: str, card_data: dict, theme: str) -> bool:
    """Check if a card matches the deck theme."""
    theme_lower = theme.lower()
    
    # Check name
    if theme_lower in card_name.lower():
        return True
    
    # Check type line
    type_line = card_data.get("type_line", "").lower()
    if theme_lower in type_line:
        return True
    
    # Check oracle text for keywords
    oracle = card_data.get("oracle_text", "").lower()
    if theme_lower in oracle:
        return True
    
    return False


def _find_support_cards(
    collection: Collection,
    card_db: dict[str, dict],
    legal_cards: set[str],
    colors: set[str],
    exclude: set[str],
    count_needed: int,
) -> list[tuple[str, int]]:
    """Find support cards (removal, draw, etc.) in the right colors."""
    support_keywords = [
        "destroy target",
        "exile target",
        "deals damage",
        "draw a card",
        "counter target",
        "return target",
    ]
    
    candidates: list[tuple[str, int, float]] = []  # (name, qty, cmc)
    
    for card_name, qty in collection.cards.items():
        if card_name in exclude:
            continue
        if card_name not in legal_cards:
            continue
        
        card_data = card_db.get(card_name)
        if not card_data:
            continue
        
        # Check color compatibility
        card_colors = set(card_data.get("colors", []))
        if card_colors and not card_colors.issubset(colors):
            continue
        
        # Skip lands
        if "Land" in card_data.get("type_line", ""):
            continue
        
        # Check if it's a support card
        oracle = card_data.get("oracle_text", "").lower()
        if any(kw in oracle for kw in support_keywords):
            cmc = card_data.get("cmc", 5)
            candidates.append((card_name, qty, cmc))
    
    # Sort by CMC (prefer cheaper cards)
    candidates.sort(key=lambda x: x[2])
    
    result: list[tuple[str, int]] = []
    added = 0
    
    for card_name, qty, _ in candidates:
        if added >= count_needed:
            break
        add_qty = min(qty, 4, count_needed - added)
        result.append((card_name, add_qty))
        added += add_qty
    
    return result


def _build_mana_base(
    collection: Collection,
    card_db: dict[str, dict],
    legal_cards: set[str],
    colors: set[str],
    land_count: int,
) -> dict[str, int]:
    """Build a mana base from owned lands."""
    lands: dict[str, int] = {}
    added = 0
    
    # Map colors to basic land types
    color_to_basic = {
        "W": "Plains",
        "U": "Island",
        "B": "Swamp",
        "R": "Mountain",
        "G": "Forest",
    }
    
    # First, add dual/utility lands
    for card_name, qty in collection.cards.items():
        if added >= land_count:
            break
        if card_name not in legal_cards:
            continue
        
        card_data = card_db.get(card_name)
        if not card_data:
            continue
        
        type_line = card_data.get("type_line", "")
        if "Land" not in type_line:
            continue
        
        # Skip basic lands for now (add at end)
        if "Basic" in type_line:
            continue
        
        # Check if land produces needed colors
        oracle = card_data.get("oracle_text", "").lower()
        produces_needed = False
        
        for color in colors:
            color_word = {
                "W": "white", "U": "blue", "B": "black",
                "R": "red", "G": "green"
            }.get(color, "")
            if color_word and color_word in oracle:
                produces_needed = True
                break
        
        if produces_needed or "any color" in oracle:
            add_qty = min(qty, 4, land_count - added)
            lands[card_name] = add_qty
            added += add_qty
    
    # Fill rest with basics
    if added < land_count and colors:
        basics_needed = land_count - added
        colors_list = sorted(colors - {"C"})
        
        if colors_list:
            per_color = basics_needed // len(colors_list)
            remainder = basics_needed % len(colors_list)
            
            for i, color in enumerate(colors_list):
                basic_name = color_to_basic.get(color)
                if basic_name:
                    count = per_color + (1 if i < remainder else 0)
                    if count > 0:
                        lands[basic_name] = count
                        added += count
    
    return lands


def format_built_deck(deck: BuiltDeck) -> str:
    """Format a built deck for display."""
    lines = [f"# {deck.name}\n"]
    
    if deck.notes:
        lines.append("**Notes:**")
        for note in deck.notes:
            lines.append(f"- {note}")
        lines.append("")
    
    if deck.warnings:
        lines.append("**Warnings:**")
        for warning in deck.warnings:
            lines.append(f"- ⚠️ {warning}")
        lines.append("")
    
    lines.append(f"**Colors:** {', '.join(sorted(deck.colors)) or 'Colorless'}")
    lines.append(f"**Total Cards:** {deck.total_cards}\n")
    
    # Theme cards
    if deck.theme_cards:
        lines.append("## Theme Cards")
        for name in deck.theme_cards:
            qty = deck.cards.get(name, 0)
            lines.append(f"- {qty}x {name}")
        lines.append("")
    
    # Support cards
    if deck.support_cards:
        lines.append("## Support Cards")
        for name in deck.support_cards:
            qty = deck.cards.get(name, 0)
            lines.append(f"- {qty}x {name}")
        lines.append("")
    
    # Lands
    if deck.lands:
        lines.append("## Lands")
        for name, qty in sorted(deck.lands.items()):
            lines.append(f"- {qty}x {name}")
        lines.append("")
    
    return "\n".join(lines)


def export_deck_to_arena(deck: BuiltDeck, card_db: dict[str, dict]) -> str:
    """Export deck to Arena import format."""
    lines = ["Deck"]
    
    # Non-land cards
    for card_name, qty in sorted(deck.cards.items()):
        card_data = card_db.get(card_name, {})
        set_code = card_data.get("set", "").upper()
        collector_num = card_data.get("collector_number", "1")
        lines.append(f"{qty} {card_name} ({set_code}) {collector_num}")
    
    # Lands
    for card_name, qty in sorted(deck.lands.items()):
        card_data = card_db.get(card_name, {})
        set_code = card_data.get("set", "FDN").upper()
        collector_num = card_data.get("collector_number", "1")
        lines.append(f"{qty} {card_name} ({set_code}) {collector_num}")
    
    return "\n".join(lines)
```

---

### MCP Tool Definition

```python
BUILD_DECK_TOOL = {
    "name": "build_deck",
    "description": """Build a custom deck from the user's collection around a theme.
    
Use this tool when the user asks to:
- Build a deck around a card type ("build me a shrine deck")
- Build a deck around a creature type ("make a goblin deck")
- Build a deck around a keyword ("build around graveyard synergies")
- Build a casual/fun deck ("make something fun with dragons")

The tool will:
1. Find all cards matching the theme in the user's collection
2. Add supporting cards (removal, card draw)
3. Add an appropriate mana base
4. Return a complete 60-card deck

This DOES NOT require wildcards - it only uses cards the user already owns.""",
    "input_schema": {
        "type": "object",
        "properties": {
            "theme": {
                "type": "string",
                "description": "Card name, type, or keyword to build around. Examples: 'Shrine', 'Goblin', 'sacrifice', 'graveyard', 'tokens'"
            },
            "colors": {
                "type": "array",
                "items": {"type": "string", "enum": ["W", "U", "B", "R", "G"]},
                "description": "Optional color restriction. If not specified, colors are determined from theme cards."
            },
            "format": {
                "type": "string",
                "enum": ["standard", "historic", "explorer", "timeless", "brawl"],
                "description": "Format for legality checking",
                "default": "standard"
            },
            "include_cards": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Specific cards that MUST be included in the deck"
            }
        },
        "required": ["theme"]
    }
}
```

---

### tests/test_deck_builder.py

```python
import pytest
from forgebreaker.models.collection import Collection
from forgebreaker.services.deck_builder import (
    build_deck,
    DeckBuildRequest,
    format_built_deck,
    export_deck_to_arena,
)


@pytest.fixture
def card_db() -> dict[str, dict]:
    return {
        "Sanctum of Stone Fangs": {
            "type_line": "Legendary Enchantment — Shrine",
            "colors": ["B"],
            "set": "M21",
            "collector_number": "120",
            "cmc": 2,
            "oracle_text": "At the beginning of your precombat main phase, each opponent loses 1 life for each Shrine you control.",
        },
        "Sanctum of Shattered Heights": {
            "type_line": "Legendary Enchantment — Shrine",
            "colors": ["R"],
            "set": "M21",
            "collector_number": "157",
            "cmc": 3,
            "oracle_text": "Sacrifice a Shrine: Deal damage equal to the number of Shrines you control.",
        },
        "Go for the Throat": {
            "type_line": "Instant",
            "colors": ["B"],
            "set": "MOM",
            "collector_number": "105",
            "cmc": 2,
            "oracle_text": "Destroy target nonartifact creature.",
        },
        "Lightning Bolt": {
            "type_line": "Instant",
            "colors": ["R"],
            "set": "STA",
            "collector_number": "42",
            "cmc": 1,
            "oracle_text": "Lightning Bolt deals 3 damage to any target.",
        },
        "Swamp": {
            "type_line": "Basic Land — Swamp",
            "colors": [],
            "set": "FDN",
            "collector_number": "280",
            "cmc": 0,
            "oracle_text": "",
        },
        "Mountain": {
            "type_line": "Basic Land — Mountain",
            "colors": [],
            "set": "FDN",
            "collector_number": "279",
            "cmc": 0,
            "oracle_text": "",
        },
        "Blood Crypt": {
            "type_line": "Land — Swamp Mountain",
            "colors": [],
            "set": "RNA",
            "collector_number": "245",
            "cmc": 0,
            "oracle_text": "({T}: Add {B} or {R}.) Blood Crypt enters tapped unless you pay 2 life.",
        },
    }


@pytest.fixture
def collection() -> Collection:
    return Collection(cards={
        "Sanctum of Stone Fangs": 4,
        "Sanctum of Shattered Heights": 4,
        "Go for the Throat": 4,
        "Lightning Bolt": 4,
        "Swamp": 20,
        "Mountain": 20,
        "Blood Crypt": 4,
    })


@pytest.fixture
def format_legality() -> dict[str, set[str]]:
    # All cards legal in historic for testing
    return {
        "historic": {
            "Sanctum of Stone Fangs",
            "Sanctum of Shattered Heights",
            "Go for the Throat",
            "Lightning Bolt",
            "Swamp",
            "Mountain",
            "Blood Crypt",
        }
    }


class TestBuildDeck:
    def test_build_shrine_deck(self, collection, card_db, format_legality):
        request = DeckBuildRequest(
            theme="Shrine",
            format="historic",
        )
        
        deck = build_deck(request, collection, card_db, format_legality)
        
        assert deck.name == "Shrine Deck"
        assert "Sanctum of Stone Fangs" in deck.theme_cards
        assert "Sanctum of Shattered Heights" in deck.theme_cards
        assert deck.colors == {"B", "R"}
    
    def test_build_includes_support(self, collection, card_db, format_legality):
        request = DeckBuildRequest(
            theme="Shrine",
            format="historic",
        )
        
        deck = build_deck(request, collection, card_db, format_legality)
        
        # Should include removal as support
        assert len(deck.support_cards) > 0
    
    def test_build_includes_lands(self, collection, card_db, format_legality):
        request = DeckBuildRequest(
            theme="Shrine",
            format="historic",
        )
        
        deck = build_deck(request, collection, card_db, format_legality)
        
        assert len(deck.lands) > 0
        assert sum(deck.lands.values()) > 0
    
    def test_build_no_theme_cards(self, collection, card_db, format_legality):
        request = DeckBuildRequest(
            theme="Dinosaur",  # Not in collection
            format="historic",
        )
        
        deck = build_deck(request, collection, card_db, format_legality)
        
        assert len(deck.warnings) > 0
        assert "No cards matching" in deck.warnings[0]
    
    def test_color_restriction(self, collection, card_db, format_legality):
        request = DeckBuildRequest(
            theme="Shrine",
            colors=["B"],  # Only black
            format="historic",
        )
        
        deck = build_deck(request, collection, card_db, format_legality)
        
        assert deck.colors == {"B"}


class TestExportToArena:
    def test_export_format(self, collection, card_db, format_legality):
        request = DeckBuildRequest(theme="Shrine", format="historic")
        deck = build_deck(request, collection, card_db, format_legality)
        
        export = export_deck_to_arena(deck, card_db)
        
        assert export.startswith("Deck")
        assert "Sanctum of Stone Fangs (M21)" in export
```

---

### Acceptance Criteria

- [ ] `build_deck` creates valid 60-card decks
- [ ] Theme cards correctly identified
- [ ] Support cards added in correct colors
- [ ] Mana base appropriate for deck colors
- [ ] Warnings generated for issues
- [ ] Arena export format correct
- [ ] All tests pass

---

## PR #28: Find Synergies Tool

**Branch:** `feature/28-tool-find-synergies`

**Problem:** Users can't discover what cards in their collection work well together.

**Solution:** Add a tool that finds cards with synergistic effects.

---

### Files to Create

```
forgebreaker/services/synergy_finder.py
tests/test_synergy_finder.py
```

---

### forgebreaker/services/synergy_finder.py

```python
"""
Card synergy finder.

Identifies cards that work well together based on mechanics.
"""

from dataclasses import dataclass
from forgebreaker.models.collection import Collection


# Synergy patterns: (trigger_keyword, synergy_keywords)
SYNERGY_PATTERNS = [
    # Sacrifice synergies
    ("sacrifice", ["dies", "leaves the battlefield", "blood token", "food token", "treasure token"]),
    # Graveyard synergies
    ("graveyard", ["mill", "dies", "flashback", "escape", "unearth"]),
    # Token synergies
    ("token", ["create", "populate", "convoke", "go wide"]),
    # Enchantment synergies
    ("enchantment", ["constellation", "enchantress", "aura"]),
    # Artifact synergies
    ("artifact", ["affinity", "improvise", "metalcraft"]),
    # +1/+1 counter synergies
    ("+1/+1 counter", ["proliferate", "evolve", "adapt", "modify"]),
    # Life gain synergies
    ("life", ["lifelink", "soul warden", "ajani's pridemate"]),
    # Spell synergies
    ("instant", ["prowess", "magecraft", "storm"]),
    ("sorcery", ["prowess", "magecraft", "storm"]),
]


@dataclass
class SynergyResult:
    """Cards that synergize with a given card."""
    source_card: str
    synergy_type: str
    synergistic_cards: list[tuple[str, int, str]]  # (name, qty, reason)


def find_synergies(
    card_name: str,
    collection: Collection,
    card_db: dict[str, dict],
    max_results: int = 20,
) -> SynergyResult | None:
    """
    Find cards in collection that synergize with a given card.
    
    Args:
        card_name: Card to find synergies for
        collection: User's collection
        card_db: Card database
        max_results: Maximum synergistic cards to return
        
    Returns:
        SynergyResult with synergistic cards, or None if card not found
    """
    card_data = card_db.get(card_name)
    if not card_data:
        return None
    
    oracle = card_data.get("oracle_text", "").lower()
    type_line = card_data.get("type_line", "").lower()
    
    # Determine what synergy patterns this card triggers
    synergy_keywords: set[str] = set()
    synergy_type = "general"
    
    for trigger, keywords in SYNERGY_PATTERNS:
        if trigger.lower() in oracle or trigger.lower() in type_line:
            synergy_keywords.update(kw.lower() for kw in keywords)
            synergy_type = trigger
    
    if not synergy_keywords:
        # No specific synergy found, look for type-based synergies
        if "creature" in type_line:
            synergy_keywords = {"creature", "tribal"}
        elif "enchantment" in type_line:
            synergy_keywords = {"enchantment", "constellation", "aura"}
        elif "artifact" in type_line:
            synergy_keywords = {"artifact", "affinity", "metalcraft"}
    
    # Find synergistic cards in collection
    synergistic: list[tuple[str, int, str]] = []
    
    for owned_name, qty in collection.cards.items():
        if owned_name == card_name:
            continue
        
        owned_data = card_db.get(owned_name)
        if not owned_data:
            continue
        
        owned_oracle = owned_data.get("oracle_text", "").lower()
        owned_type = owned_data.get("type_line", "").lower()
        
        for keyword in synergy_keywords:
            if keyword in owned_oracle or keyword in owned_type:
                reason = f"Has '{keyword}'"
                synergistic.append((owned_name, qty, reason))
                break
    
    # Sort by quantity and limit
    synergistic.sort(key=lambda x: -x[1])
    synergistic = synergistic[:max_results]
    
    return SynergyResult(
        source_card=card_name,
        synergy_type=synergy_type,
        synergistic_cards=synergistic,
    )


def format_synergy_results(result: SynergyResult) -> str:
    """Format synergy results for display."""
    if not result.synergistic_cards:
        return f"No synergistic cards found for {result.source_card} in your collection."
    
    lines = [
        f"## Cards that synergize with {result.source_card}",
        f"*Synergy type: {result.synergy_type}*\n",
    ]
    
    for name, qty, reason in result.synergistic_cards:
        lines.append(f"- {qty}x **{name}** - {reason}")
    
    return "\n".join(lines)
```

---

### MCP Tool Definition

```python
FIND_SYNERGIES_TOOL = {
    "name": "find_synergies",
    "description": """Find cards in the user's collection that synergize with a specific card.
    
Use this tool when the user asks:
- "What works well with [card]?"
- "Find synergies for [card]"
- "What should I pair with [card]?"
- "Build around [card]"

The tool identifies mechanical synergies like:
- Sacrifice payoffs for sacrifice enablers
- Token generators for token payoffs
- Graveyard fillers for graveyard payoffs""",
    "input_schema": {
        "type": "object",
        "properties": {
            "card_name": {
                "type": "string",
                "description": "Exact card name to find synergies for"
            }
        },
        "required": ["card_name"]
    }
}
```

---

### Acceptance Criteria

- [ ] Identifies common synergy patterns
- [ ] Returns owned cards that synergize
- [ ] Explains why each card synergizes
- [ ] All tests pass

---

## PR #29: Arena Export Tool

**Branch:** `feature/29-tool-export-arena`

**Problem:** After building a deck, users need to copy it into Arena.

**Solution:** Add a tool that formats decks for Arena import.

---

### MCP Tool Definition

```python
EXPORT_TO_ARENA_TOOL = {
    "name": "export_to_arena",
    "description": """Convert a deck to MTG Arena import format.
    
Use this AFTER building a deck with build_deck. Returns text that can be 
copy-pasted directly into Arena's import function.

Format:
Deck
4 Card Name (SET) 123
4 Another Card (SET) 456
...""",
    "input_schema": {
        "type": "object",
        "properties": {
            "deck_name": {
                "type": "string",
                "description": "Name of the deck to export (from a previous build_deck call)"
            }
        },
        "required": ["deck_name"]
    }
}
```

**Note:** The export function is already implemented in `deck_builder.py`. This PR just adds the MCP tool definition and wires it up.

---

## PR #30: Card Database with Format Legality

**Branch:** `feature/30-card-database`

**Problem:** The tools need access to full card data and format legality. Currently this data isn't properly loaded/cached.

**Solution:** Add a service that loads Scryfall data and provides format legality checking.

---

### Files to Create

```
forgebreaker/services/card_database.py
forgebreaker/data/.gitkeep
tests/test_card_database.py
```

---

### forgebreaker/services/card_database.py

```python
"""
Card database service.

Loads and caches Scryfall card data with format legality.
"""

import json
from pathlib import Path
from functools import lru_cache
import httpx


SCRYFALL_BULK_API = "https://api.scryfall.com/bulk-data"
DATA_DIR = Path(__file__).parent.parent / "data"


async def download_card_database(output_path: Path | None = None) -> Path:
    """
    Download latest Scryfall default-cards bulk data.
    
    Returns path to downloaded file.
    """
    if output_path is None:
        output_path = DATA_DIR / "default-cards.json"
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Get download URL
    async with httpx.AsyncClient() as client:
        response = await client.get(SCRYFALL_BULK_API)
        response.raise_for_status()
        data = response.json()
        
        download_url = None
        for item in data["data"]:
            if item["type"] == "default_cards":
                download_url = item["download_uri"]
                break
        
        if not download_url:
            raise ValueError("Could not find default_cards bulk data URL")
        
        # Stream download
        async with client.stream("GET", download_url) as response:
            response.raise_for_status()
            with open(output_path, "wb") as f:
                async for chunk in response.aiter_bytes(8192):
                    f.write(chunk)
    
    return output_path


@lru_cache(maxsize=1)
def load_card_database(path: Path | None = None) -> dict[str, dict]:
    """
    Load card database from file.
    
    Returns dict mapping card names to card data.
    Cached after first load.
    """
    if path is None:
        path = DATA_DIR / "default-cards.json"
    
    if not path.exists():
        raise FileNotFoundError(
            f"Card database not found at {path}. "
            "Run `python -m forgebreaker.jobs.download_cards` first."
        )
    
    with open(path, "r", encoding="utf-8") as f:
        cards = json.load(f)
    
    # Index by name
    db: dict[str, dict] = {}
    for card in cards:
        name = card.get("name")
        if name:
            db[name] = card
    
    return db


def get_format_legality(card_db: dict[str, dict]) -> dict[str, set[str]]:
    """
    Build format -> legal cards mapping.
    
    Returns dict like:
    {
        "standard": {"Lightning Bolt", "Shock", ...},
        "historic": {"Lightning Bolt", "Shock", "Brainstorm", ...},
        ...
    }
    """
    formats = ["standard", "historic", "explorer", "pioneer", "modern", "legacy", "vintage", "brawl", "timeless"]
    legality: dict[str, set[str]] = {f: set() for f in formats}
    
    for name, card in card_db.items():
        card_legalities = card.get("legalities", {})
        for fmt in formats:
            if card_legalities.get(fmt) == "legal":
                legality[fmt].add(name)
    
    return legality


def get_card_rarity(card_name: str, card_db: dict[str, dict]) -> str:
    """Get rarity for a card, defaulting to 'rare' if unknown."""
    card = card_db.get(card_name)
    if card:
        return card.get("rarity", "rare")
    return "rare"
```

---

### Acceptance Criteria

- [ ] Scryfall data downloads correctly
- [ ] Card database loads and caches
- [ ] Format legality correctly extracted
- [ ] All tests pass

---

## PR #31: LLM Prompt Improvements

**Branch:** `feature/31-integration-prompts`

**Problem:** The LLM doesn't know when to use the new tools.

**Solution:** Update the system prompt to guide tool usage.

---

### Files to Modify

```
forgebreaker/mcp/tools.py  (update SYSTEM_PROMPT)
forgebreaker/api/chat.py   (ensure all tools registered)
```

---

### Updated System Prompt

```python
SYSTEM_PROMPT = """You are ForgeBreaker, an MTG Arena deck building assistant.

You help users:
1. Understand what cards they own
2. Build decks from their collection
3. Find meta decks they can complete
4. Get strategic advice

## Available Tools

### search_collection
Use when users ask about their cards:
- "Do I have any goblins?"
- "What shrines do I own?"
- "Show me my red creatures"

### build_deck
Use when users want to create a deck:
- "Build me a shrine deck"
- "Make a goblin tribal deck"
- "Create something fun with dragons"

This builds a COMPLETE 60-card deck using ONLY cards they own. No wildcards needed.

### find_synergies
Use when users want to know what works together:
- "What pairs well with Sheoldred?"
- "Find synergies for my sacrifice deck"

### find_buildable_decks
Use when users want competitive meta decks:
- "What meta decks can I build?"
- "Show me Standard decks I'm close to"

### get_deck_details
Use for information about specific meta decks.

### export_to_arena
Use AFTER building a deck to give the user importable text.

## Important Guidelines

1. ALWAYS use tools - don't guess about the user's collection
2. When building casual decks, use build_deck - don't suggest meta decks
3. After building a deck, offer to export it for Arena
4. If a theme has no cards, say so clearly
5. Be encouraging about casual/fun decks - not everything needs to be competitive

## Example Interaction

User: "Build me a shrine deck"

1. Call search_collection(name_contains="shrine") to see what shrines they have
2. Call build_deck(theme="shrine") to create the deck
3. Show the deck with explanations
4. Offer: "Would you like me to export this for Arena import?"
"""
```

---

### Acceptance Criteria

- [ ] System prompt updated with new tools
- [ ] All tools registered in chat handler
- [ ] Tool calls work end-to-end
- [ ] LLM uses appropriate tools for different requests

---

## Testing the Complete Flow

After all PRs are merged, test with these prompts:

1. **"Do I have any shrine cards?"**
   - Should call `search_collection`
   - Should list owned shrines

2. **"Build me a shrine deck"**
   - Should call `search_collection` first
   - Should call `build_deck`
   - Should show complete 60-card deck
   - Should offer Arena export

3. **"What synergizes with Sheoldred?"**
   - Should call `find_synergies`
   - Should show cards with life/death triggers

4. **"Export that deck for Arena"**
   - Should call `export_to_arena`
   - Should return copy-pasteable text

5. **"What meta decks can I build in Standard?"**
   - Should call `find_buildable_decks`
   - Should show decks with completion percentages

---

## Summary

| PR | Tool/Feature | User Problem Solved |
|----|--------------|---------------------|
| 26 | search_collection | "What cards do I have?" |
| 27 | build_deck | "Build me a deck from my cards" |
| 28 | find_synergies | "What works well together?" |
| 29 | export_to_arena | "I want to use this deck in Arena" |
| 30 | card_database | Backend data for all tools |
| 31 | prompts | LLM knows when to use tools |

After these PRs, the conversation you showed would work correctly.
