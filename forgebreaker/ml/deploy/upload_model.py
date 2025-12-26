"""Upload trained models to MLForge.

CLI script to deploy ONNX models to the MLForge inference platform.

Usage:
    python -m forgebreaker.ml.deploy.upload_model \\
        --model models/deck_winrate_predictor.onnx \\
        --metadata models/model_metadata.json \\
        --url https://mlforge.example.com
"""

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

import httpx


class UploadError(Exception):
    """Raised when model upload fails."""


async def upload_model(
    model_path: Path,
    mlforge_url: str,
    *,
    timeout: float = 120.0,
) -> dict[str, Any]:
    """Upload ONNX model file to MLForge.

    Args:
        model_path: Path to ONNX model file
        mlforge_url: Base URL of MLForge API
        timeout: Request timeout in seconds

    Returns:
        Response from MLForge API with model_id

    Raises:
        UploadError: If upload fails (network, HTTP, or file errors)
    """
    url = f"{mlforge_url}/api/v1/models/upload"

    try:
        model_bytes = model_path.read_bytes()
    except (FileNotFoundError, PermissionError, OSError) as exc:
        raise UploadError(f"Failed to read model file '{model_path}': {exc}") from exc

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            files = {"model": (model_path.name, model_bytes, "application/octet-stream")}
            response = await client.post(url, files=files)
    except httpx.RequestError as exc:
        raise UploadError(f"Network error uploading model: {exc}") from exc

    if not response.is_success:
        raise UploadError(f"Failed to upload model: HTTP {response.status_code} - {response.text}")

    try:
        result: dict[str, Any] = response.json()
    except json.JSONDecodeError as exc:
        raise UploadError(f"Invalid JSON response: {response.text}") from exc

    return result


async def register_model(
    model_id: str,
    metadata_path: Path,
    mlforge_url: str,
    *,
    timeout: float = 30.0,
) -> dict[str, Any]:
    """Register model metadata with MLForge.

    Args:
        model_id: Model ID from upload response
        metadata_path: Path to metadata JSON file
        mlforge_url: Base URL of MLForge API
        timeout: Request timeout in seconds

    Returns:
        Response from MLForge API

    Raises:
        UploadError: If registration fails (network, HTTP, or file errors)
    """
    url = f"{mlforge_url}/api/v1/models/{model_id}/register"

    try:
        with open(metadata_path) as f:
            metadata = json.load(f)
    except (FileNotFoundError, PermissionError, OSError) as exc:
        raise UploadError(f"Failed to read metadata file '{metadata_path}': {exc}") from exc
    except json.JSONDecodeError as exc:
        raise UploadError(f"Invalid JSON in metadata file '{metadata_path}': {exc}") from exc

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, json=metadata)
    except httpx.RequestError as exc:
        raise UploadError(f"Network error registering model: {exc}") from exc

    if not response.is_success:
        raise UploadError(
            f"Failed to register model: HTTP {response.status_code} - {response.text}"
        )

    try:
        result: dict[str, Any] = response.json()
    except json.JSONDecodeError as exc:
        raise UploadError(f"Invalid JSON response: {response.text}") from exc

    return result


async def deploy_model(
    model_path: Path,
    metadata_path: Path,
    mlforge_url: str,
) -> dict[str, Any]:
    """Upload and register a model with MLForge.

    Args:
        model_path: Path to ONNX model file
        metadata_path: Path to metadata JSON file
        mlforge_url: Base URL of MLForge API

    Returns:
        Combined response with model_id and registration status

    Raises:
        UploadError: If upload or registration fails
    """
    # Upload model file
    upload_response = await upload_model(model_path, mlforge_url)
    model_id = upload_response["model_id"]

    # Register metadata
    register_response = await register_model(model_id, metadata_path, mlforge_url)

    return {
        "model_id": model_id,
        "upload": upload_response,
        "register": register_response,
    }


def main() -> None:
    """CLI entrypoint for model upload."""
    parser = argparse.ArgumentParser(description="Upload model to MLForge")
    parser.add_argument(
        "--model",
        type=Path,
        required=True,
        help="Path to ONNX model file",
    )
    parser.add_argument(
        "--metadata",
        type=Path,
        help="Path to metadata JSON file",
    )
    parser.add_argument(
        "--url",
        required=True,
        help="MLForge API base URL",
    )

    args = parser.parse_args()

    if not args.model.exists():
        print(f"Error: Model file not found: {args.model}")
        return

    result = asyncio.run(upload_model(args.model, args.url))
    print(f"Uploaded model: {result['model_id']}")

    if args.metadata:
        if not args.metadata.exists():
            print(f"Warning: Metadata file not found: {args.metadata}")
        else:
            model_id = result["model_id"]
            register_result = asyncio.run(register_model(model_id, args.metadata, args.url))
            print(f"Registered metadata: {register_result}")


if __name__ == "__main__":
    main()
