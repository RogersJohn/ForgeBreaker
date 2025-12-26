"""Tests for MLForge model upload."""

from pathlib import Path

import httpx
import pytest
import respx

from forgebreaker.ml.deploy.upload_model import (
    upload_model,
    register_model,
    UploadError,
)


@pytest.fixture
def sample_model_file(tmp_path: Path) -> Path:
    """Create a sample ONNX file."""
    model_path = tmp_path / "model.onnx"
    model_path.write_bytes(b"fake onnx content")
    return model_path


@pytest.fixture
def sample_metadata(tmp_path: Path) -> Path:
    """Create a sample metadata file."""
    import json

    metadata_path = tmp_path / "metadata.json"
    metadata = {
        "feature_names": ["f1", "f2", "f3"],
        "metrics": {"accuracy": 0.55, "auc": 0.58},
    }
    with open(metadata_path, "w") as f:
        json.dump(metadata, f)
    return metadata_path


class TestUploadModel:
    """Tests for uploading ONNX model."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_uploads_onnx_file(self, sample_model_file: Path) -> None:
        """Successfully uploads ONNX file to MLForge."""
        mlforge_url = "https://mlforge.example.com"
        respx.post(f"{mlforge_url}/api/v1/models/upload").mock(
            return_value=httpx.Response(200, json={"model_id": "model-123"})
        )

        result = await upload_model(sample_model_file, mlforge_url)

        assert result["model_id"] == "model-123"

    @pytest.mark.asyncio
    @respx.mock
    async def test_handles_upload_failure(self, sample_model_file: Path) -> None:
        """Raises UploadError on HTTP failure."""
        mlforge_url = "https://mlforge.example.com"
        respx.post(f"{mlforge_url}/api/v1/models/upload").mock(
            return_value=httpx.Response(500, json={"error": "Server error"})
        )

        with pytest.raises(UploadError, match="Failed to upload"):
            await upload_model(sample_model_file, mlforge_url)


class TestRegisterModel:
    """Tests for registering model metadata."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_registers_model_metadata(self, sample_metadata: Path) -> None:
        """Registers model metadata with MLForge."""
        mlforge_url = "https://mlforge.example.com"
        model_id = "model-123"

        respx.post(f"{mlforge_url}/api/v1/models/{model_id}/register").mock(
            return_value=httpx.Response(200, json={"status": "registered"})
        )

        result = await register_model(model_id, sample_metadata, mlforge_url)

        assert result["status"] == "registered"

    @pytest.mark.asyncio
    @respx.mock
    async def test_handles_registration_failure(self, sample_metadata: Path) -> None:
        """Raises UploadError on registration failure."""
        mlforge_url = "https://mlforge.example.com"
        model_id = "model-123"

        respx.post(f"{mlforge_url}/api/v1/models/{model_id}/register").mock(
            return_value=httpx.Response(400, json={"error": "Bad request"})
        )

        with pytest.raises(UploadError, match="Failed to register"):
            await register_model(model_id, sample_metadata, mlforge_url)
