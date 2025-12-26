"""Tests for 17Lands data downloader."""

from pathlib import Path

import httpx
import pytest
import respx

from forgebreaker.ml.data.download_17lands import (
    VALID_EVENT_TYPES,
    DownloadError,
    construct_17lands_url,
    download_file,
    download_multiple_sets,
    generate_file_path,
)


class TestUrlConstruction:
    """Tests for URL construction."""

    def test_constructs_premier_draft_url(self) -> None:
        """URL follows 17Lands S3 pattern for PremierDraft."""
        url = construct_17lands_url("BLB", "PremierDraft")
        expected = (
            "https://17lands-public.s3.amazonaws.com/analysis_data/"
            "game_data/game_data_public.BLB.PremierDraft.csv.gz"
        )
        assert url == expected

    def test_set_code_is_uppercased(self) -> None:
        """Set codes are normalized to uppercase."""
        url = construct_17lands_url("blb", "PremierDraft")
        assert ".BLB." in url

    def test_invalid_event_type_raises(self) -> None:
        """Only valid event types are accepted."""
        with pytest.raises(ValueError, match="Invalid event type"):
            construct_17lands_url("BLB", "InvalidEvent")

    def test_all_valid_event_types(self) -> None:
        """All valid event types produce valid URLs."""
        for event_type in VALID_EVENT_TYPES:
            url = construct_17lands_url("BLB", event_type)
            assert event_type in url


class TestFilePaths:
    """Tests for file path generation."""

    def test_generates_path_in_data_directory(self, tmp_path: Path) -> None:
        """File path is within the specified data directory."""
        path = generate_file_path("BLB", "PremierDraft", tmp_path)
        assert path.parent == tmp_path

    def test_filename_includes_set_and_event(self, tmp_path: Path) -> None:
        """Filename contains set code and event type."""
        path = generate_file_path("BLB", "PremierDraft", tmp_path)
        assert "BLB" in path.name
        assert "PremierDraft" in path.name
        assert path.suffix == ".gz"


class TestDownloadBehavior:
    """Tests for download functionality (mocked HTTP)."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_downloads_to_correct_path(self, tmp_path: Path) -> None:
        """Downloaded content is written to the correct file."""
        url = construct_17lands_url("BLB", "PremierDraft")
        respx.get(url).mock(return_value=httpx.Response(200, content=b"test,data\n1,2\n"))

        result_path = await download_file("BLB", "PremierDraft", tmp_path)

        assert result_path.exists()
        assert result_path.read_bytes() == b"test,data\n1,2\n"

    @pytest.mark.asyncio
    async def test_skips_download_if_file_exists(self, tmp_path: Path) -> None:
        """Existing files are not re-downloaded."""
        # Create existing file
        existing_path = generate_file_path("BLB", "PremierDraft", tmp_path)
        existing_path.write_bytes(b"existing content")

        # No mock needed - should not make HTTP call
        result_path = await download_file("BLB", "PremierDraft", tmp_path)

        assert result_path == existing_path
        assert result_path.read_bytes() == b"existing content"

    @pytest.mark.asyncio
    @respx.mock
    async def test_raises_on_http_error(self, tmp_path: Path) -> None:
        """HTTP errors are wrapped in DownloadError."""
        url = construct_17lands_url("BLB", "PremierDraft")
        respx.get(url).mock(return_value=httpx.Response(404))

        with pytest.raises(DownloadError, match="Failed to download"):
            await download_file("BLB", "PremierDraft", tmp_path)


class TestBatchOperations:
    """Tests for batch download operations."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_downloads_multiple_sets(self, tmp_path: Path) -> None:
        """Multiple sets can be downloaded in one call."""
        for set_code in ["BLB", "OTJ", "MKM"]:
            url = construct_17lands_url(set_code, "PremierDraft")
            respx.get(url).mock(return_value=httpx.Response(200, content=b"data"))

        results = await download_multiple_sets(
            ["BLB", "OTJ", "MKM"],
            "PremierDraft",
            tmp_path,
        )

        assert len(results["success"]) == 3
        assert len(results["failed"]) == 0

    @pytest.mark.asyncio
    @respx.mock
    async def test_continues_on_single_failure(self, tmp_path: Path) -> None:
        """Batch continues even if one download fails."""
        # BLB and MKM succeed, OTJ fails
        respx.get(construct_17lands_url("BLB", "PremierDraft")).mock(
            return_value=httpx.Response(200, content=b"data")
        )
        respx.get(construct_17lands_url("OTJ", "PremierDraft")).mock(
            return_value=httpx.Response(404)
        )
        respx.get(construct_17lands_url("MKM", "PremierDraft")).mock(
            return_value=httpx.Response(200, content=b"data")
        )

        results = await download_multiple_sets(
            ["BLB", "OTJ", "MKM"],
            "PremierDraft",
            tmp_path,
        )

        assert len(results["success"]) == 2
        assert len(results["failed"]) == 1
        assert "OTJ" in results["failed"]
