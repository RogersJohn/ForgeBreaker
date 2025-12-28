"""
Deck improvement service.

Analyzes an existing deck and suggests upgrades from the user's collection.
Uses synergy detection and tribal awareness for smarter suggestions.

IMPORTANT: All card suggestions MUST go through an AllowedCardSet.
This enforces the invariant that suggestions only come from cards
the player owns AND that are legal in the target format.
"""

from dataclasses import dataclass, field
from typing import Any

from forgebreaker.models.allowed_cards import (
    AllowedCardSet,
    build_allowed_set,
    validate_card_in_allowed_set,
)
from forgebreaker.models.collection import Collection
from forgebreaker.parsers.arena_export import parse_arena_export


@dataclass
class CardDetails:
    """Card information including oracle text."""

    name: str
    quantity: int
    type_line: str
    oracle_text: str
    mana_cost: str = ""


@dataclass
class CardSuggestion:
    """A suggested card swap."""

    remove_card: str
    remove_quantity: int
    add_card: str
    add_quantity: int
    reason: str
    # Include oracle text for both cards so AI can compare accurately
    remove_card_text: str = ""
    add_card_text: str = ""


@dataclass
class UpgradeCandidate:
    """Candidate for a card upgrade with scoring info."""

    card_name: str
    improvement_score: float
    reason: str
    card_data: dict[str, Any]


@dataclass
class DeckThemes:
    """Detected themes/strategies in a deck."""

    themes: set[str] = field(default_factory=set)
    tribal_types: dict[str, int] = field(default_factory=dict)  # subtype -> count
    keywords: set[str] = field(default_factory=set)


@dataclass
class DeckAnalysis:
    """Analysis of a deck with improvement suggestions."""

    original_cards: dict[str, int]
    total_cards: int
    colors: set[str]
    creature_count: int
    spell_count: int
    land_count: int
    detected_themes: list[str] = field(default_factory=list)
    primary_tribe: str | None = None
    suggestions: list[CardSuggestion] = field(default_factory=list)
    general_advice: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    # Include oracle text for key cards so AI can accurately describe them
    card_details: list[CardDetails] = field(default_factory=list)


# Theme detection patterns: theme_name -> (oracle_keywords, type_keywords)
THEME_PATTERNS: dict[str, tuple[list[str], list[str]]] = {
    "sacrifice": (
        ["sacrifice", "when this creature dies", "whenever a creature dies", "blood token"],
        [],
    ),
    "tokens": (
        [
            "create a",
            "token",
            "populate",
            "go wide",
            "whenever a creature enters",
            "when a creature enters",
        ],
        [],
    ),
    "graveyard": (
        ["from your graveyard", "mill", "flashback", "escape", "unearth", "dredge"],
        [],
    ),
    "counters": (
        ["+1/+1 counter", "proliferate", "evolve", "adapt", "modified"],
        [],
    ),
    "lifegain": (
        ["lifelink", "whenever you gain life", "soul warden", "gain life"],
        [],
    ),
    "spellslinger": (
        ["prowess", "magecraft", "whenever you cast an instant", "whenever you cast a sorcery"],
        [],
    ),
    "enchantments": (
        ["constellation", "enchantress", "whenever you cast an enchantment"],
        ["enchantment"],
    ),
    "artifacts": (
        ["affinity", "improvise", "metalcraft", "whenever an artifact"],
        ["artifact"],
    ),
    "aggro": (
        ["haste", "first strike", "double strike", "menace"],
        [],
    ),
    "control": (
        ["counter target", "destroy target", "exile target", "to its owner's hand"],
        [],
    ),
}

# Common tribal types to detect
TRIBAL_TYPES: set[str] = {
    "goblin",
    "elf",
    "vampire",
    "zombie",
    "merfolk",
    "dragon",
    "angel",
    "demon",
    "wizard",
    "warrior",
    "knight",
    "soldier",
    "cleric",
    "rogue",
    "shaman",
    "elemental",
    "spirit",
    "beast",
    "dinosaur",
    "cat",
    "dog",
    "rat",
    "human",
    "faerie",
    "giant",
    "troll",
    "ogre",
    "orc",
    "dwarf",
    "bird",
    "snake",
    "spider",
    "insect",
    "horror",
    "nightmare",
    "phyrexian",
    "sliver",
    "ally",
    "pirate",
    "sphinx",
    "hydra",
    "wurm",
    "drake",
    "phoenix",
    "shrine",
}


def _get_card_type_category(type_line: str) -> str:
    """Categorize a card by its type line."""
    type_lower = type_line.lower()
    if "land" in type_lower:
        return "land"
    if "creature" in type_lower:
        return "creature"
    if "instant" in type_lower or "sorcery" in type_lower:
        return "spell"
    if "enchantment" in type_lower:
        return "enchantment"
    if "artifact" in type_lower:
        return "artifact"
    if "planeswalker" in type_lower:
        return "planeswalker"
    return "other"


def _get_card_colors(card_data: dict[str, Any]) -> set[str]:
    """Extract colors from card data."""
    colors = card_data.get("colors", [])
    return set(colors) if colors else set()


def _extract_subtypes(type_line: str) -> set[str]:
    """Extract creature subtypes from a type line."""
    # Type line format: "Legendary Creature — Goblin Warrior"
    subtypes: set[str] = set()
    if "—" in type_line:
        subtype_part = type_line.split("—")[1].strip().lower()
        for word in subtype_part.split():
            if word in TRIBAL_TYPES:
                subtypes.add(word)
    return subtypes


def _detect_deck_themes(
    deck_cards: dict[str, int],
    card_db: dict[str, dict[str, Any]],
) -> DeckThemes:
    """Analyze deck to detect themes, tribal types, and key mechanics."""
    themes = DeckThemes()
    theme_scores: dict[str, int] = dict.fromkeys(THEME_PATTERNS, 0)
    theme_keywords: dict[str, set[str]] = {theme: set() for theme in THEME_PATTERNS}

    for card_name, quantity in deck_cards.items():
        card_data = card_db.get(card_name)
        if not card_data:
            continue

        oracle = card_data.get("oracle_text", "").lower()
        type_line = card_data.get("type_line", "").lower()

        # Count tribal types
        subtypes = _extract_subtypes(card_data.get("type_line", ""))
        for subtype in subtypes:
            themes.tribal_types[subtype] = themes.tribal_types.get(subtype, 0) + quantity

        # Score each theme based on keyword matches
        for theme_name, (oracle_keywords, type_keywords) in THEME_PATTERNS.items():
            for keyword in oracle_keywords:
                if keyword in oracle:
                    theme_scores[theme_name] += quantity
                    theme_keywords[theme_name].add(keyword)
            for keyword in type_keywords:
                if keyword in type_line:
                    theme_scores[theme_name] += quantity

    # Themes with significant presence (at least 4 cards matching)
    # Only add keywords for themes that pass the threshold
    for theme_name, score in theme_scores.items():
        if score >= 4:
            themes.themes.add(theme_name)
            themes.keywords.update(theme_keywords[theme_name])

    return themes


def _calculate_synergy_score(
    card_data: dict[str, Any],
    deck_themes: DeckThemes,
    deck_tribal: str | None,
) -> float:
    """
    Score how well a card fits the deck's themes and tribal identity.

    Returns 0-10 score where higher = better fit.
    """
    score = 0.0
    oracle = card_data.get("oracle_text", "").lower()
    type_line = card_data.get("type_line", "").lower()

    # Theme matching (up to 5 points)
    # Count each theme only once, even if both oracle and type keywords match
    theme_matches = 0
    for theme_name, (oracle_keywords, type_keywords) in THEME_PATTERNS.items():
        if theme_name not in deck_themes.themes:
            continue
        theme_matched = False
        for keyword in oracle_keywords:
            if keyword in oracle:
                theme_matched = True
                break
        if not theme_matched:
            for keyword in type_keywords:
                if keyword in type_line:
                    theme_matched = True
                    break
        if theme_matched:
            theme_matches += 1

    score += min(5.0, theme_matches * 2.0)

    # Tribal matching (up to 3 points)
    if deck_tribal:
        subtypes = _extract_subtypes(card_data.get("type_line", ""))
        if deck_tribal in subtypes:
            score += 3.0
        # Cards that care about the tribe also get points
        # e.g. "whenever a Goblin enters" for goblin deck
        elif deck_tribal in oracle:
            score += 2.0

    # Keyword synergy with deck's existing keywords (up to 2 points)
    keyword_matches = 0
    for keyword in deck_themes.keywords:
        if keyword in oracle:
            keyword_matches += 1
    score += min(2.0, keyword_matches * 0.5)

    return score


def _calculate_base_quality(card_data: dict[str, Any]) -> float:
    """
    Base card quality score (rarity + efficiency).

    Returns 0-4 score. This is secondary to synergy.
    """
    score = 0.0

    # Rarity gives a small bonus
    rarity = card_data.get("rarity", "common")
    rarity_scores = {"common": 0.0, "uncommon": 0.5, "rare": 1.0, "mythic": 1.5}
    score += rarity_scores.get(rarity, 0.0)

    # Efficient mana cost
    cmc = card_data.get("cmc", 3)
    if cmc <= 2:
        score += 0.5
    elif cmc <= 4:
        score += 0.25

    # Key evergreen abilities
    oracle = card_data.get("oracle_text", "").lower()
    evergreen = ["draw a card", "scry", "flying", "deathtouch", "trample"]
    for ability in evergreen:
        if ability in oracle:
            score += 0.25
            break

    return min(4.0, score)


def _find_synergy_upgrade(
    card_name: str,
    card_quantity: int,
    card_data: dict[str, Any] | None,
    allowed_set: AllowedCardSet,
    card_db: dict[str, dict[str, Any]],
    deck_cards: set[str],
    deck_colors: set[str],
    deck_themes: DeckThemes,
    deck_tribal: str | None,
) -> CardSuggestion | None:
    """
    Find a synergy-based upgrade for a specific card.

    IMPORTANT: Only cards in allowed_set can be suggested.
    This enforces the hard boundary that prevents suggesting
    cards the player doesn't own or that aren't format-legal.
    """
    if card_data is None:
        return None

    card_type = _get_card_type_category(card_data.get("type_line", ""))

    # Don't suggest replacing lands
    if card_type == "land":
        return None

    # Current card's scores
    current_synergy = _calculate_synergy_score(card_data, deck_themes, deck_tribal)
    current_quality = _calculate_base_quality(card_data)
    current_total = current_synergy + current_quality

    card_cmc = card_data.get("cmc", 0)

    best_upgrade: UpgradeCandidate | None = None

    # CRITICAL: Only iterate over allowed cards (owned AND format-legal)
    for owned_card, owned_qty in allowed_set.cards.items():
        if owned_card in deck_cards:
            continue
        if owned_qty < card_quantity:
            continue

        owned_data = card_db.get(owned_card)
        if owned_data is None:
            continue

        owned_type = _get_card_type_category(owned_data.get("type_line", ""))

        # Must be same general category
        if owned_type != card_type:
            continue

        owned_colors = _get_card_colors(owned_data)
        if owned_colors and not owned_colors.issubset(deck_colors):
            continue

        # CMC should be within reasonable range
        owned_cmc = owned_data.get("cmc", 0)
        if abs(owned_cmc - card_cmc) > 2:
            continue

        # Calculate upgrade's scores
        owned_synergy = _calculate_synergy_score(owned_data, deck_themes, deck_tribal)
        owned_quality = _calculate_base_quality(owned_data)
        owned_total = owned_synergy + owned_quality

        # Must be meaningfully better (at least 1 point improvement)
        improvement = owned_total - current_total
        if improvement < 1.0:
            continue

        # Build reason based on what makes it better
        reasons = []
        owned_subtypes = _extract_subtypes(owned_data.get("type_line", ""))

        # Synergy reasons
        if owned_synergy > current_synergy:
            if deck_tribal and deck_tribal in owned_subtypes:
                reasons.append(f"matches {deck_tribal} tribal theme")
            elif deck_themes.themes:
                matching_themes = []
                owned_oracle = owned_data.get("oracle_text", "").lower()
                for theme in deck_themes.themes:
                    keywords, _ = THEME_PATTERNS.get(theme, ([], []))
                    if any(kw in owned_oracle for kw in keywords):
                        matching_themes.append(theme)
                if matching_themes:
                    reasons.append(f"synergizes with {matching_themes[0]} strategy")

        # Quality reasons (only if no synergy reason found)
        if not reasons:
            owned_oracle = owned_data.get("oracle_text", "").lower()
            if "draw" in owned_oracle:
                reasons.append("provides card advantage")
            elif "destroy" in owned_oracle or "exile" in owned_oracle:
                reasons.append("better removal")
            elif owned_quality > current_quality:
                reasons.append("higher quality card")

        if not reasons:
            reasons.append("better overall fit")

        reason = ", ".join(reasons)

        if best_upgrade is None or improvement > best_upgrade.improvement_score:
            best_upgrade = UpgradeCandidate(
                card_name=owned_card,
                improvement_score=improvement,
                reason=reason,
                card_data=owned_data,
            )

    if best_upgrade:
        # HARD BOUNDARY: Validate suggestion before returning
        # This is a defensive check - should always pass if iteration was correct
        validate_card_in_allowed_set(
            best_upgrade.card_name,
            allowed_set,
            card_quantity,
        )

        return CardSuggestion(
            remove_card=card_name,
            remove_quantity=card_quantity,
            add_card=best_upgrade.card_name,
            add_quantity=card_quantity,
            reason=best_upgrade.reason,
            remove_card_text=card_data.get("oracle_text", ""),
            add_card_text=best_upgrade.card_data.get("oracle_text", ""),
        )

    return None


def analyze_and_improve_deck(
    deck_text: str,
    collection: Collection,
    card_db: dict[str, dict[str, Any]],
    format_name: str,
    format_legal_cards: set[str],
    max_suggestions: int = 5,
) -> DeckAnalysis:
    """
    Analyze a deck and suggest improvements from the user's collection.

    Uses synergy detection and tribal awareness for smarter suggestions.

    IMPORTANT: Only cards that are BOTH owned AND format-legal can be suggested.
    This is enforced via AllowedCardSet - a hard boundary that cannot be bypassed.

    Args:
        deck_text: Arena-format deck list
        collection: User's card collection
        card_db: Scryfall card database
        format_name: Target format (e.g., "standard", "historic")
        format_legal_cards: Set of cards legal in the target format
        max_suggestions: Maximum number of suggestions to return

    Returns:
        DeckAnalysis with suggestions and advice
    """
    # Build the allowed card set - the ONLY valid universe for suggestions
    allowed_set = build_allowed_set(
        collection_cards=collection.cards,
        format_legal_cards=format_legal_cards,
        format_name=format_name,
    )
    cards = parse_arena_export(deck_text)

    if not cards:
        return DeckAnalysis(
            original_cards={},
            total_cards=0,
            colors=set(),
            creature_count=0,
            spell_count=0,
            land_count=0,
            warnings=["Could not parse any cards from the deck list."],
        )

    # Build deck dictionary
    deck_cards: dict[str, int] = {}
    for card in cards:
        deck_cards[card.name] = deck_cards.get(card.name, 0) + card.quantity

    # Analyze deck composition
    colors: set[str] = set()
    creature_count = 0
    spell_count = 0
    land_count = 0

    for card_name in deck_cards:
        card_data = card_db.get(card_name)
        if card_data:
            colors.update(_get_card_colors(card_data))
            card_type = _get_card_type_category(card_data.get("type_line", ""))
            if card_type == "creature":
                creature_count += deck_cards[card_name]
            elif card_type == "spell":
                spell_count += deck_cards[card_name]
            elif card_type == "land":
                land_count += deck_cards[card_name]

    total_cards = sum(deck_cards.values())

    # Detect deck themes and tribal identity
    deck_themes = _detect_deck_themes(deck_cards, card_db)

    # Find primary tribe (if any type has 6+ creatures)
    primary_tribe: str | None = None
    if deck_themes.tribal_types:
        top_tribe = max(deck_themes.tribal_types.items(), key=lambda x: x[1])
        if top_tribe[1] >= 6:
            primary_tribe = top_tribe[0]

    # Find upgrade suggestions using synergy scoring
    suggestions: list[CardSuggestion] = []
    deck_card_set = set(deck_cards.keys())

    # Sort by quantity (suggest replacing 4-ofs first)
    sorted_cards = sorted(deck_cards.items(), key=lambda x: -x[1])

    for card_name, quantity in sorted_cards:
        if len(suggestions) >= max_suggestions:
            break

        card_data = card_db.get(card_name)
        suggestion = _find_synergy_upgrade(
            card_name,
            quantity,
            card_data,
            allowed_set,  # HARD BOUNDARY: Only suggest from allowed cards
            card_db,
            deck_card_set,
            colors if colors else {"W", "U", "B", "R", "G"},
            deck_themes,
            primary_tribe,
        )

        if suggestion:
            suggestions.append(suggestion)

    # Generate advice
    general_advice: list[str] = []
    warnings: list[str] = []

    if total_cards < 60:
        warnings.append(f"Deck has only {total_cards} cards. Standard decks need 60.")
    elif total_cards > 60:
        general_advice.append(f"Deck has {total_cards} cards. Consider cutting to exactly 60.")

    if land_count < 20:
        warnings.append(f"Only {land_count} lands may cause mana problems. Consider 22-26 lands.")
    elif land_count > 26:
        general_advice.append(f"{land_count} lands is high. Consider cutting 1-2.")

    if creature_count == 0 and spell_count > 0:
        general_advice.append("No creatures detected. Make sure you have win conditions.")

    if not suggestions:
        general_advice.append(
            "No synergy-based upgrades found. Your deck may already use your best cards!"
        )

    # Collect card details (oracle text) for all non-land cards
    card_details: list[CardDetails] = []
    for card_name, quantity in deck_cards.items():
        card_data = card_db.get(card_name)
        if card_data:
            card_type = _get_card_type_category(card_data.get("type_line", ""))
            # Skip basic lands - their text isn't useful
            if card_type == "land" and "basic" in card_data.get("type_line", "").lower():
                continue
            card_details.append(
                CardDetails(
                    name=card_name,
                    quantity=quantity,
                    type_line=card_data.get("type_line", ""),
                    oracle_text=card_data.get("oracle_text", ""),
                    mana_cost=card_data.get("mana_cost", ""),
                )
            )

    return DeckAnalysis(
        original_cards=deck_cards,
        total_cards=total_cards,
        colors=colors,
        creature_count=creature_count,
        spell_count=spell_count,
        land_count=land_count,
        detected_themes=list(deck_themes.themes),
        primary_tribe=primary_tribe,
        suggestions=suggestions,
        general_advice=general_advice,
        warnings=warnings,
        card_details=card_details,
    )


def format_deck_analysis(analysis: DeckAnalysis) -> str:
    """Format deck analysis for display."""
    lines: list[str] = []

    # Summary
    color_str = "".join(sorted(analysis.colors)) if analysis.colors else "Colorless"
    lines.append(f"**Deck Analysis** ({analysis.total_cards} cards, {color_str})")
    lines.append(
        f"- Creatures: {analysis.creature_count}, "
        f"Spells: {analysis.spell_count}, Lands: {analysis.land_count}"
    )

    # Detected themes
    if analysis.detected_themes or analysis.primary_tribe:
        theme_parts = []
        if analysis.primary_tribe:
            theme_parts.append(f"{analysis.primary_tribe.title()} tribal")
        theme_parts.extend(analysis.detected_themes)
        lines.append(f"- Detected strategy: {', '.join(theme_parts)}")

    lines.append("")

    # Warnings first
    if analysis.warnings:
        lines.append("**Issues:**")
        for warning in analysis.warnings:
            lines.append(f"- {warning}")
        lines.append("")

    # Suggestions with oracle text for accurate AI descriptions
    if analysis.suggestions:
        lines.append("**Suggested Upgrades:**")
        for i, suggestion in enumerate(analysis.suggestions, 1):
            lines.append(
                f"{i}. Replace {suggestion.remove_quantity}x {suggestion.remove_card} "
                f"with {suggestion.add_quantity}x {suggestion.add_card}"
            )
            lines.append(f"   Reason: {suggestion.reason}")
            # Include oracle text so AI can accurately describe the cards
            if suggestion.remove_card_text:
                lines.append(f"   [{suggestion.remove_card}]: {suggestion.remove_card_text}")
            if suggestion.add_card_text:
                lines.append(f"   [{suggestion.add_card}]: {suggestion.add_card_text}")
        lines.append("")

    # General advice
    if analysis.general_advice:
        lines.append("**Tips:**")
        for advice in analysis.general_advice:
            lines.append(f"- {advice}")
        lines.append("")

    # Card reference with oracle text for all cards in deck
    if analysis.card_details:
        lines.append("**Card Reference (oracle text):**")
        for card in sorted(analysis.card_details, key=lambda c: c.name):
            lines.append(f"- **{card.name}** ({card.type_line})")
            if card.oracle_text:
                lines.append(f"  {card.oracle_text}")

    return "\n".join(lines)
