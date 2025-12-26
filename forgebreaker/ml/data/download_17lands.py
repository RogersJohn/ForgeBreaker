"""Download 17Lands public datasets from S3.

17Lands provides game-level data for MTG Arena draft formats.
Files are gzipped CSVs stored in a public S3 bucket.

Usage:
    python -m forgebreaker.ml.data.download_17lands --sets BLB OTJ MKM
"""

import argparse
import asyncio
from pathlib import Path
from typing import TypedDict

import httpx


class DownloadError(Exception):
    """Raised when a download fails."""

    pass


# Valid event types per 17Lands data
VALID_EVENT_TYPES = frozenset(["PremierDraft", "TradDraft", "QuickDraft", "Sealed"])

# S3 bucket URL pattern
# Format: game_data_public.{SET}.{EVENT}.csv.gz
_BASE_URL = "https://17lands-public.s3.amazonaws.com/analysis_data/game_data"


def construct_17lands_url(set_code: str, event_type: str) -> str:
    """Construct the S3 URL for a 17Lands dataset.

    Args:
        set_code: MTG set code (e.g., "BLB", "OTJ")
        event_type: Event type (PremierDraft, TradDraft, QuickDraft, Sealed)

    Returns:
        Full S3 URL for the dataset

    Raises:
        ValueError: If event_type is not valid
    """
    if event_type not in VALID_EVENT_TYPES:
        raise ValueError(
            f"Invalid event type: {event_type}. Must be one of: {sorted(VALID_EVENT_TYPES)}"
        )

    set_code = set_code.upper()
    return f"{_BASE_URL}/game_data_public.{set_code}.{event_type}.csv.gz"


def generate_file_path(set_code: str, event_type: str, data_dir: Path) -> Path:
    """Generate the local file path for a downloaded dataset.

    Args:
        set_code: MTG set code
        event_type: Event type
        data_dir: Directory to store files

    Returns:
        Path where the file should be saved
    """
    set_code = set_code.upper()
    filename = f"17lands_{set_code}_{event_type}.csv.gz"
    return data_dir / filename


async def download_file(
    set_code: str,
    event_type: str,
    data_dir: Path,
    *,
    force: bool = False,
) -> Path:
    """Download a single 17Lands dataset.

    Args:
        set_code: MTG set code
        event_type: Event type
        data_dir: Directory to store files
        force: If True, re-download even if file exists

    Returns:
        Path to the downloaded file

    Raises:
        DownloadError: If download fails
    """
    data_dir.mkdir(parents=True, exist_ok=True)
    file_path = generate_file_path(set_code, event_type, data_dir)

    # Skip if already downloaded
    if file_path.exists() and not force:
        return file_path

    url = construct_17lands_url(set_code, event_type)

    try:
        async with (
            httpx.AsyncClient(timeout=300.0) as client,
            client.stream("GET", url) as response,
        ):
            response.raise_for_status()
            with open(file_path, "wb") as f:
                async for chunk in response.aiter_bytes():
                    f.write(chunk)
    except httpx.HTTPStatusError as e:
        raise DownloadError(
            f"Failed to download {set_code} {event_type}: HTTP {e.response.status_code}"
        ) from e
    except httpx.RequestError as e:
        raise DownloadError(f"Failed to download {set_code} {event_type}: {e}") from e

    return file_path


class BatchResult(TypedDict):
    """Result of batch download operation."""

    success: list[Path]
    failed: dict[str, str]


async def download_multiple_sets(
    set_codes: list[str],
    event_type: str,
    data_dir: Path,
    *,
    force: bool = False,
) -> BatchResult:
    """Download datasets for multiple sets.

    Continues on individual failures.

    Args:
        set_codes: List of MTG set codes
        event_type: Event type
        data_dir: Directory to store files
        force: If True, re-download even if files exist

    Returns:
        Dict with 'success' (list of paths) and 'failed' (dict of set -> error)
    """
    success: list[Path] = []
    failed: dict[str, str] = {}

    for set_code in set_codes:
        try:
            path = await download_file(set_code, event_type, data_dir, force=force)
            success.append(path)
        except DownloadError as e:
            failed[set_code] = str(e)

    return {"success": success, "failed": failed}


def main() -> None:
    """CLI entrypoint for downloading 17Lands data."""
    parser = argparse.ArgumentParser(description="Download 17Lands game data")
    parser.add_argument(
        "--sets",
        nargs="+",
        required=True,
        help="Set codes to download (e.g., BLB OTJ MKM)",
    )
    parser.add_argument(
        "--event-type",
        default="PremierDraft",
        choices=sorted(VALID_EVENT_TYPES),
        help="Event type (default: PremierDraft)",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("data/raw"),
        help="Directory to store files (default: data/raw)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-download even if files exist",
    )

    args = parser.parse_args()

    results = asyncio.run(
        download_multiple_sets(
            args.sets,
            args.event_type,
            args.data_dir,
            force=args.force,
        )
    )

    print(f"Downloaded {len(results['success'])} files:")
    for path in results["success"]:
        print(f"  {path}")

    if results["failed"]:
        print(f"\nFailed {len(results['failed'])} downloads:")
        for set_code, error in results["failed"].items():
            print(f"  {set_code}: {error}")


if __name__ == "__main__":
    main()
