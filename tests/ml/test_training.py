"""Tests for model training pipeline."""

import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from forgebreaker.ml.training.train import (
    MODEL_CONFIG,
    TEST_RATIO,
    TRAIN_RATIO,
    VAL_RATIO,
    evaluate_model,
    export_to_onnx,
    generate_model_card,
    save_metadata,
    split_by_draft_id,
    train_model,
)


@pytest.fixture
def sample_features() -> pd.DataFrame:
    """Sample feature DataFrame for training."""
    np.random.seed(42)
    n_samples = 100

    return pd.DataFrame(
        {
            "n_cards_in_deck": np.random.randint(35, 45, n_samples),
            "n_creatures": np.random.randint(10, 20, n_samples),
            "n_lands": np.random.randint(15, 18, n_samples),
            "n_noncreature_spells": np.random.randint(5, 15, n_samples),
            "avg_mana_value": np.random.uniform(2.0, 4.0, n_samples),
            "curve_1_drop": np.random.randint(2, 8, n_samples),
            "curve_2_drop": np.random.randint(4, 10, n_samples),
            "curve_3_drop": np.random.randint(3, 8, n_samples),
            "curve_4_drop": np.random.randint(1, 5, n_samples),
            "curve_5plus_drop": np.random.randint(0, 4, n_samples),
            "color_W": np.random.randint(0, 2, n_samples),
            "color_U": np.random.randint(0, 2, n_samples),
            "color_B": np.random.randint(0, 2, n_samples),
            "color_R": np.random.randint(0, 2, n_samples),
            "color_G": np.random.randint(0, 2, n_samples),
            "on_play": np.random.randint(0, 2, n_samples),
            "num_mulligans": np.random.randint(0, 3, n_samples),
            "user_skill_bucket": np.random.uniform(0.3, 0.7, n_samples),
            "won": np.random.randint(0, 2, n_samples),
            "draft_id": [f"draft_{i // 5}" for i in range(n_samples)],  # 20 unique drafts
        }
    )


class TestSplitByDraftId:
    """Tests for data splitting."""

    def test_splits_data_correctly(self, sample_features: pd.DataFrame) -> None:
        """Data is split into train/val/test with correct proportions."""
        train, val, test = split_by_draft_id(sample_features)

        total = len(train) + len(val) + len(test)
        assert total == len(sample_features)

        # Check approximate proportions (allow some variance due to grouping)
        assert len(train) / total >= TRAIN_RATIO - 0.05
        assert len(val) / total >= VAL_RATIO - 0.05
        assert len(test) / total >= TEST_RATIO - 0.05

    def test_no_draft_id_leakage(self, sample_features: pd.DataFrame) -> None:
        """No draft_id appears in multiple splits."""
        train, val, test = split_by_draft_id(sample_features)

        train_ids = set(train["draft_id"])
        val_ids = set(val["draft_id"])
        test_ids = set(test["draft_id"])

        assert train_ids.isdisjoint(val_ids)
        assert train_ids.isdisjoint(test_ids)
        assert val_ids.isdisjoint(test_ids)


class TestTrainModel:
    """Tests for model training."""

    def test_trains_xgboost_model(self, sample_features: pd.DataFrame) -> None:
        """Trains an XGBoost model successfully."""
        train, val, _ = split_by_draft_id(sample_features)
        feature_cols = [c for c in train.columns if c not in ["won", "draft_id"]]

        model = train_model(
            train[feature_cols],
            train["won"],
            val[feature_cols],
            val["won"],
        )

        assert model is not None
        # Model should have the configured parameters
        assert model.n_estimators == MODEL_CONFIG["n_estimators"]


class TestEvaluateModel:
    """Tests for model evaluation."""

    def test_evaluates_on_holdout(self, sample_features: pd.DataFrame) -> None:
        """Evaluates model and returns accuracy and AUC."""
        train, val, test = split_by_draft_id(sample_features)
        feature_cols = [c for c in train.columns if c not in ["won", "draft_id"]]

        model = train_model(
            train[feature_cols],
            train["won"],
            val[feature_cols],
            val["won"],
        )

        metrics = evaluate_model(model, test[feature_cols], test["won"])

        assert "accuracy" in metrics
        assert "auc" in metrics
        assert 0.0 <= metrics["accuracy"] <= 1.0
        assert 0.0 <= metrics["auc"] <= 1.0


# Check if ONNX dependencies are available
ONNX_AVAILABLE = (
    importlib.util.find_spec("onnxruntime") is not None
    and importlib.util.find_spec("onnxmltools") is not None
)


@pytest.mark.skipif(not ONNX_AVAILABLE, reason="ONNX dependencies not available")
class TestExportToOnnx:
    """Tests for ONNX export."""

    def test_exports_to_onnx(self, sample_features: pd.DataFrame, tmp_path: Path) -> None:
        """Exports model to ONNX format and returns feature name mapping."""
        train, val, _ = split_by_draft_id(sample_features)
        feature_cols = [c for c in train.columns if c not in ["won", "draft_id"]]

        model = train_model(
            train[feature_cols],
            train["won"],
            val[feature_cols],
            val["won"],
        )

        onnx_path = tmp_path / "model.onnx"
        feature_mapping = export_to_onnx(model, feature_cols, onnx_path)

        assert onnx_path.exists()
        assert onnx_path.stat().st_size > 0
        # Verify feature mapping
        assert len(feature_mapping) == len(feature_cols)
        assert feature_mapping["f0"] == feature_cols[0]
        assert feature_mapping[f"f{len(feature_cols) - 1}"] == feature_cols[-1]

    def test_onnx_produces_same_predictions(
        self, sample_features: pd.DataFrame, tmp_path: Path
    ) -> None:
        """ONNX model produces same predictions as original."""
        import onnxruntime as ort

        train, val, test = split_by_draft_id(sample_features)
        feature_cols = [c for c in train.columns if c not in ["won", "draft_id"]]

        model = train_model(
            train[feature_cols],
            train["won"],
            val[feature_cols],
            val["won"],
        )

        # Get XGBoost predictions
        xgb_probs = model.predict_proba(test[feature_cols])[:, 1]

        # Export and load ONNX
        onnx_path = tmp_path / "model.onnx"
        export_to_onnx(model, feature_cols, onnx_path)

        session = ort.InferenceSession(str(onnx_path))
        input_name = session.get_inputs()[0].name
        onnx_probs = session.run(None, {input_name: test[feature_cols].values.astype(np.float32)})[
            1
        ][:, 1]

        # Predictions should be very close
        np.testing.assert_allclose(xgb_probs, onnx_probs, rtol=1e-5, atol=1e-5)


class TestSaveMetadata:
    """Tests for metadata saving."""

    def test_saves_feature_names(self, sample_features: pd.DataFrame, tmp_path: Path) -> None:
        """Saves feature names to metadata file."""
        import json

        feature_cols = [c for c in sample_features.columns if c not in ["won", "draft_id"]]
        metrics = {"accuracy": 0.55, "auc": 0.58}

        metadata_path = tmp_path / "metadata.json"
        save_metadata(feature_cols, metrics, metadata_path)

        assert metadata_path.exists()

        with open(metadata_path) as f:
            metadata = json.load(f)

        assert "feature_names" in metadata
        assert metadata["feature_names"] == feature_cols
        assert "metrics" in metadata
        assert metadata["metrics"]["accuracy"] == 0.55


class TestGenerateModelCard:
    """Tests for model card generation."""

    def test_generates_model_card(self, tmp_path: Path) -> None:
        """Generates MODEL_CARD.md with correct content."""
        metrics = {"accuracy": 0.55, "auc": 0.58}

        card_path = tmp_path / "MODEL_CARD.md"
        generate_model_card(metrics, card_path)

        assert card_path.exists()

        content = card_path.read_text()
        assert "# Deck Win Rate Predictor" in content
        assert "0.5500" in content  # accuracy
        assert "0.5800" in content  # auc
        assert "XGBoost" in content
        assert "17Lands" in content
