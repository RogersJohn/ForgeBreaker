"""Model training pipeline for deck win rate prediction.

Trains an XGBoost classifier on 17Lands game data.
Exports to ONNX format for deployment to MLForge.
"""

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd  # type: ignore[import-untyped]
from sklearn.metrics import accuracy_score, roc_auc_score  # type: ignore[import-untyped]
from xgboost import XGBClassifier

# Model hyperparameters
MODEL_CONFIG = {
    "n_estimators": 100,
    "max_depth": 6,
    "learning_rate": 0.1,
    "random_state": 42,
}

# Data split ratios
TRAIN_RATIO = 0.7
VAL_RATIO = 0.15
TEST_RATIO = 0.15


def split_by_draft_id(
    df: pd.DataFrame,
    train_ratio: float = TRAIN_RATIO,
    val_ratio: float = VAL_RATIO,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Split data by draft_id to prevent data leakage.

    Games from the same draft should not appear in different splits.

    Args:
        df: DataFrame with draft_id column
        train_ratio: Fraction of drafts for training
        val_ratio: Fraction of drafts for validation

    Returns:
        Tuple of (train, val, test) DataFrames
    """
    # Get unique draft IDs and shuffle
    draft_ids = df["draft_id"].unique()
    np.random.seed(MODEL_CONFIG["random_state"])
    np.random.shuffle(draft_ids)

    # Calculate split points
    n_drafts = len(draft_ids)
    train_end = int(n_drafts * train_ratio)
    val_end = train_end + int(n_drafts * val_ratio)

    train_ids = set(draft_ids[:train_end])
    val_ids = set(draft_ids[train_end:val_end])
    test_ids = set(draft_ids[val_end:])

    train = df[df["draft_id"].isin(train_ids)].copy()
    val = df[df["draft_id"].isin(val_ids)].copy()
    test = df[df["draft_id"].isin(test_ids)].copy()

    return train, val, test


def train_model(
    X_train: pd.DataFrame,  # noqa: N803
    y_train: pd.Series,
    X_val: pd.DataFrame,  # noqa: N803
    y_val: pd.Series,
) -> XGBClassifier:
    """Train XGBoost classifier.

    Args:
        X_train: Training features
        y_train: Training labels
        X_val: Validation features
        y_val: Validation labels

    Returns:
        Trained XGBoost model
    """
    model = XGBClassifier(
        n_estimators=MODEL_CONFIG["n_estimators"],
        max_depth=MODEL_CONFIG["max_depth"],
        learning_rate=MODEL_CONFIG["learning_rate"],
        random_state=MODEL_CONFIG["random_state"],
        eval_metric="logloss",
        early_stopping_rounds=10,
    )

    model.fit(
        X_train,
        y_train,
        eval_set=[(X_val, y_val)],
        verbose=False,
    )

    return model


def evaluate_model(
    model: XGBClassifier,
    X_test: pd.DataFrame,  # noqa: N803
    y_test: pd.Series,
) -> dict[str, float]:
    """Evaluate model on test set.

    Args:
        model: Trained model
        X_test: Test features
        y_test: Test labels

    Returns:
        Dict with accuracy and AUC metrics
    """
    y_pred = model.predict(X_test)
    y_prob = model.predict_proba(X_test)[:, 1]

    return {
        "accuracy": accuracy_score(y_test, y_pred),
        "auc": roc_auc_score(y_test, y_prob),
    }


def export_to_onnx(
    model: XGBClassifier,
    feature_names: list[str],
    output_path: Path,
) -> dict[str, str]:
    """Export model to ONNX format.

    Renames features to f0, f1, f2... format required by onnxmltools.
    Returns mapping from f-names to original names for metadata.

    Args:
        model: Trained XGBoost model
        feature_names: List of original feature names
        output_path: Path to save ONNX model

    Returns:
        Mapping from f-names (f0, f1, ...) to original feature names

    Raises:
        ImportError: If onnxmltools not available
    """
    try:
        from onnxmltools import convert_xgboost  # type: ignore
        from onnxmltools.convert.common.data_types import FloatTensorType  # type: ignore
    except ImportError as e:
        raise ImportError(
            "onnxmltools required for ONNX export. Install with: pip install onnxmltools"
        ) from e

    # Create f-name mapping (onnxmltools requires f0, f1, f2... format)
    f_names = [f"f{i}" for i in range(len(feature_names))]
    feature_mapping = dict(zip(f_names, feature_names, strict=True))

    # Temporarily update model's feature names for conversion
    booster = model.get_booster()
    original_names = booster.feature_names
    booster.feature_names = f_names

    try:
        # Define input type
        initial_type = [("input", FloatTensorType([None, len(feature_names)]))]

        # Convert to ONNX using onnxmltools (has XGBoost support)
        onnx_model = convert_xgboost(
            model,
            initial_types=initial_type,
            target_opset=12,
        )

        # Save model
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "wb") as f:
            f.write(onnx_model.SerializeToString())
    finally:
        # Restore original feature names
        booster.feature_names = original_names

    return feature_mapping


def save_metadata(
    feature_names: list[str],
    metrics: dict[str, float],
    output_path: Path,
) -> None:
    """Save model metadata to JSON.

    Args:
        feature_names: List of feature names
        metrics: Model evaluation metrics
        output_path: Path to save metadata
    """
    metadata: dict[str, Any] = {
        "feature_names": feature_names,
        "metrics": metrics,
        "model_config": MODEL_CONFIG,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(metadata, f, indent=2)


def generate_model_card(
    metrics: dict[str, float],
    output_path: Path,
) -> None:
    """Generate MODEL_CARD.md documentation.

    Args:
        metrics: Model evaluation metrics
        output_path: Path to save model card
    """
    content = f"""# Deck Win Rate Predictor

## Model Description
XGBoost classifier that predicts deck win probability based on deck composition and game context.

## Training Data
- Source: 17Lands public game data
- Features: Deck composition, mana curve, colors, game context

## Performance Metrics
- Accuracy: {metrics.get("accuracy", 0):.4f}
- AUC-ROC: {metrics.get("auc", 0):.4f}

## Model Configuration
```json
{json.dumps(MODEL_CONFIG, indent=2)}
```

## Limitations
- Trained on limited format data (Premier Draft, Traditional Draft, Quick Draft, Sealed)
- Performance may vary across different sets and formats
- Does not account for individual card power levels

## Intended Use
- Deck building assistance in MTG Arena
- Win rate estimation for draft decks
"""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        f.write(content)
