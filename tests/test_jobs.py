"""Tests for scheduled jobs."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from forgebreaker.jobs.update_meta import run_meta_update, update_format
from forgebreaker.models.deck import MetaDeck


@pytest.fixture
def sample_meta_deck() -> MetaDeck:
    return MetaDeck(
        name="Mono-Red Aggro",
        archetype="aggro",
        format="standard",
        cards={"Lightning Bolt": 4, "Mountain": 20},
        sideboard={},
        meta_share=0.12,
        source_url="https://example.com",
    )


class TestUpdateFormat:
    @pytest.mark.asyncio
    async def test_update_format_success(self, sample_meta_deck: MetaDeck):
        """Test successful format update."""
        mock_client = MagicMock()
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session.commit = AsyncMock()

        with (
            patch(
                "forgebreaker.jobs.update_meta.fetch_meta_decks",
                return_value=[sample_meta_deck],
            ),
            patch(
                "forgebreaker.jobs.update_meta.async_session_factory",
                return_value=mock_session,
            ),
            patch(
                "forgebreaker.jobs.update_meta.sync_meta_decks",
                new_callable=AsyncMock,
                return_value=1,
            ),
        ):
            result = await update_format("standard", limit=10, client=mock_client)
            assert result == 1

    @pytest.mark.asyncio
    async def test_update_format_http_error(self):
        """Test format update handles HTTP errors."""
        import httpx

        mock_client = MagicMock()

        with patch(
            "forgebreaker.jobs.update_meta.fetch_meta_decks",
            side_effect=httpx.HTTPError("Network error"),
        ):
            result = await update_format("standard", limit=10, client=mock_client)
            assert result == 0


class TestRunMetaUpdate:
    @pytest.mark.asyncio
    async def test_run_meta_update_all_formats(self, sample_meta_deck: MetaDeck):
        """Test updating all formats."""
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session.commit = AsyncMock()

        with (
            patch(
                "forgebreaker.jobs.update_meta.fetch_meta_decks",
                return_value=[sample_meta_deck],
            ),
            patch(
                "forgebreaker.jobs.update_meta.async_session_factory",
                return_value=mock_session,
            ),
            patch(
                "forgebreaker.jobs.update_meta.sync_meta_decks",
                new_callable=AsyncMock,
                return_value=1,
            ),
        ):
            results = await run_meta_update()

            # All valid formats should be updated
            assert "standard" in results
            assert "historic" in results
            assert "explorer" in results
            assert "timeless" in results

    @pytest.mark.asyncio
    async def test_run_meta_update_specific_formats(self, sample_meta_deck: MetaDeck):
        """Test updating specific formats only."""
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session.commit = AsyncMock()

        with (
            patch(
                "forgebreaker.jobs.update_meta.fetch_meta_decks",
                return_value=[sample_meta_deck],
            ),
            patch(
                "forgebreaker.jobs.update_meta.async_session_factory",
                return_value=mock_session,
            ),
            patch(
                "forgebreaker.jobs.update_meta.sync_meta_decks",
                new_callable=AsyncMock,
                return_value=1,
            ),
        ):
            results = await run_meta_update(formats=["standard"])

            assert "standard" in results
            assert "historic" not in results

    @pytest.mark.asyncio
    async def test_run_meta_update_skips_invalid_format(self):
        """Test that invalid formats are skipped."""
        results = await run_meta_update(formats=["invalid_format"])
        assert "invalid_format" not in results
