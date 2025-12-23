from pathlib import Path

import pytest

from forgebreaker.scrapers.mtggoldfish import (
    DeckSummary,
    _infer_archetype,
    parse_deck_page,
    parse_metagame_page,
)


@pytest.fixture
def metagame_html() -> str:
    fixture_path = Path(__file__).parent / "fixtures" / "mtggoldfish_metagame.html"
    return fixture_path.read_text()


@pytest.fixture
def deck_html() -> str:
    fixture_path = Path(__file__).parent / "fixtures" / "mtggoldfish_deck.html"
    return fixture_path.read_text()


@pytest.fixture
def sample_summary() -> DeckSummary:
    return DeckSummary(
        name="Mono Red Aggro",
        url="https://www.mtggoldfish.com/archetype/mono-red-aggro",
        meta_share=0.125,
        format="standard",
    )


class TestParseMetagamePage:
    def test_parses_deck_summaries(self, metagame_html: str) -> None:
        """Extracts deck summaries from metagame page."""
        summaries = parse_metagame_page(metagame_html, "standard")

        assert len(summaries) == 3

    def test_extracts_deck_names(self, metagame_html: str) -> None:
        """Deck names are correctly extracted."""
        summaries = parse_metagame_page(metagame_html, "standard")
        names = [s.name for s in summaries]

        assert "Mono Red Aggro" in names
        assert "Azorius Control" in names
        assert "Golgari Midrange" in names

    def test_extracts_meta_shares(self, metagame_html: str) -> None:
        """Meta share percentages are correctly parsed."""
        summaries = parse_metagame_page(metagame_html, "standard")

        mono_red = next(s for s in summaries if s.name == "Mono Red Aggro")
        assert mono_red.meta_share == pytest.approx(0.125)

        azorius = next(s for s in summaries if s.name == "Azorius Control")
        assert azorius.meta_share == pytest.approx(0.098)

    def test_builds_correct_urls(self, metagame_html: str) -> None:
        """URLs are correctly constructed."""
        summaries = parse_metagame_page(metagame_html, "standard")

        mono_red = next(s for s in summaries if s.name == "Mono Red Aggro")
        assert "mtggoldfish.com/archetype/mono-red-aggro" in mono_red.url

    def test_sets_format(self, metagame_html: str) -> None:
        """Format is passed through to summaries."""
        summaries = parse_metagame_page(metagame_html, "historic")

        for summary in summaries:
            assert summary.format == "historic"

    def test_empty_page_returns_empty_list(self) -> None:
        """Empty HTML returns empty list."""
        summaries = parse_metagame_page("<html></html>", "standard")

        assert summaries == []


class TestParseDeckPage:
    def test_parses_main_deck(self, deck_html: str, sample_summary: DeckSummary) -> None:
        """Main deck cards are correctly parsed."""
        deck = parse_deck_page(deck_html, sample_summary)

        assert deck.cards["Monastery Swiftspear"] == 4
        assert deck.cards["Lightning Bolt"] == 4
        assert deck.cards["Mountain"] == 20

    def test_parses_sideboard(self, deck_html: str, sample_summary: DeckSummary) -> None:
        """Sideboard cards are correctly parsed."""
        deck = parse_deck_page(deck_html, sample_summary)

        assert deck.sideboard["Smash to Smithereens"] == 3
        assert deck.sideboard["Roiling Vortex"] == 2

    def test_includes_metadata(self, deck_html: str, sample_summary: DeckSummary) -> None:
        """Deck includes metadata from summary."""
        deck = parse_deck_page(deck_html, sample_summary)

        assert deck.name == "Mono Red Aggro"
        assert deck.format == "standard"
        assert deck.meta_share == 0.125
        assert deck.source_url == sample_summary.url

    def test_infers_archetype(self, deck_html: str, sample_summary: DeckSummary) -> None:
        """Archetype is inferred from deck name."""
        deck = parse_deck_page(deck_html, sample_summary)

        assert deck.archetype == "aggro"

    def test_counts_total_cards(self, deck_html: str, sample_summary: DeckSummary) -> None:
        """Total maindeck count is correct."""
        deck = parse_deck_page(deck_html, sample_summary)

        # 16 creatures + 12 instants + 20 lands = 48
        # But our fixture has specific quantities
        assert deck.maindeck_count() == 48


class TestInferArchetype:
    def test_aggro_detection(self) -> None:
        """Aggro decks are detected."""
        assert _infer_archetype("Mono Red Aggro") == "aggro"
        assert _infer_archetype("Burn") == "aggro"
        assert _infer_archetype("Red Deck Wins") == "aggro"

    def test_control_detection(self) -> None:
        """Control decks are detected."""
        assert _infer_archetype("Azorius Control") == "control"
        assert _infer_archetype("Esper Control") == "control"
        assert _infer_archetype("Blue Moon") == "control"

    def test_combo_detection(self) -> None:
        """Combo decks are detected."""
        assert _infer_archetype("Storm Combo") == "combo"
        assert _infer_archetype("Ramp") == "combo"

    def test_defaults_to_midrange(self) -> None:
        """Unknown archetypes default to midrange."""
        assert _infer_archetype("Golgari Midrange") == "midrange"
        assert _infer_archetype("Jund") == "midrange"
        assert _infer_archetype("Some Random Deck") == "midrange"
