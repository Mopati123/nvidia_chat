"""Deterministic offline refusal/risk baseline trainer."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np

from .evidence_dataset import read_refusal_risk_dataset

META = {
    "tier": "rootfile",
    "layer": "data_core.ml",
    "operator_type": "cp_map",
}


NUMERIC_FEATURES = (
    "hour_utc",
    "day_of_week",
    "volume",
    "amount",
    "pnl_prediction",
    "retcode",
)
CATEGORICAL_FEATURES = (
    "operation",
    "symbol_bucket",
    "broker",
    "direction",
    "mode",
)


@dataclass
class TrainingReport:
    """Summary returned after offline refusal/risk training."""

    rows: int
    features: int
    output_path: str
    metrics: Dict[str, Any]
    feature_weights: Dict[str, float] = field(default_factory=dict)


def _clean_category(value: Any) -> str:
    text = str(value or "missing").strip().lower()
    return text or "missing"


def _prepare_matrix(rows: List[Dict[str, Any]]) -> Tuple[np.ndarray, np.ndarray, Dict[str, Any]]:
    if not rows:
        raise ValueError("Cannot train refusal/risk model from an empty dataset")

    y = np.array([int(row["risk_label"]) for row in rows], dtype=float)

    numeric = np.array([
        [float(row.get(feature) or 0.0) for feature in NUMERIC_FEATURES]
        for row in rows
    ], dtype=float)
    means = numeric.mean(axis=0)
    stds = numeric.std(axis=0)
    stds[stds == 0] = 1.0
    numeric_scaled = (numeric - means) / stds

    categories = {
        feature: sorted({_clean_category(row.get(feature)) for row in rows})
        for feature in CATEGORICAL_FEATURES
    }
    categorical_columns: List[np.ndarray] = []
    categorical_names: List[str] = []
    for feature, values in categories.items():
        observed = [_clean_category(row.get(feature)) for row in rows]
        for value in values:
            categorical_columns.append(np.array([1.0 if item == value else 0.0 for item in observed]))
            categorical_names.append(f"{feature}={value}")

    categorical = (
        np.vstack(categorical_columns).T
        if categorical_columns
        else np.zeros((len(rows), 0), dtype=float)
    )
    x = np.hstack([numeric_scaled, categorical])
    metadata = {
        "numeric_features": list(NUMERIC_FEATURES),
        "categorical_features": categories,
        "feature_names": list(NUMERIC_FEATURES) + categorical_names,
        "numeric_means": {name: float(value) for name, value in zip(NUMERIC_FEATURES, means)},
        "numeric_stds": {name: float(value) for name, value in zip(NUMERIC_FEATURES, stds)},
    }
    return x, y, metadata


def _sigmoid(values: np.ndarray) -> np.ndarray:
    clipped = np.clip(values, -60.0, 60.0)
    return 1.0 / (1.0 + np.exp(-clipped))


def _metrics(y_true: np.ndarray, y_pred: np.ndarray) -> Dict[str, Any]:
    tp = int(np.sum((y_true == 1) & (y_pred == 1)))
    tn = int(np.sum((y_true == 0) & (y_pred == 0)))
    fp = int(np.sum((y_true == 0) & (y_pred == 1)))
    fn = int(np.sum((y_true == 1) & (y_pred == 0)))
    accuracy = float((tp + tn) / max(len(y_true), 1))
    precision = float(tp / max(tp + fp, 1))
    recall = float(tp / max(tp + fn, 1))
    return {
        "accuracy": accuracy,
        "precision": precision,
        "recall": recall,
        "confusion_matrix": {
            "tp": tp,
            "tn": tn,
            "fp": fp,
            "fn": fn,
        },
    }


def train_refusal_risk_model(
    dataset_path: str | Path,
    output_path: str | Path,
    *,
    seed: int = 12345,
    epochs: int = 250,
    learning_rate: float = 0.15,
    l2: float = 0.001,
) -> TrainingReport:
    """Train a deterministic offline logistic baseline from a Parquet dataset."""
    np.random.default_rng(seed)  # locks future extension points to a stable seed
    rows = [row for row in read_refusal_risk_dataset(dataset_path) if row.get("risk_label") in {0, 1}]
    x, y, metadata = _prepare_matrix(rows)

    x_bias = np.hstack([np.ones((x.shape[0], 1), dtype=float), x])
    weights = np.zeros(x_bias.shape[1], dtype=float)
    regularization = np.ones_like(weights)
    regularization[0] = 0.0

    for _ in range(epochs):
        probabilities = _sigmoid(x_bias @ weights)
        gradient = (x_bias.T @ (probabilities - y)) / len(y)
        gradient += l2 * regularization * weights
        weights -= learning_rate * gradient

    probabilities = _sigmoid(x_bias @ weights)
    predictions = (probabilities >= 0.5).astype(int)
    metrics = _metrics(y.astype(int), predictions)

    feature_names = ["bias"] + metadata["feature_names"]
    feature_weights = {
        name: float(weight)
        for name, weight in zip(feature_names, weights)
    }
    artifact = {
        "model_type": "offline_refusal_risk_logistic_baseline",
        "artifact_schema_version": 1,
        "seed": seed,
        "epochs": epochs,
        "learning_rate": learning_rate,
        "l2": l2,
        "rows": len(rows),
        "features": len(feature_names),
        "metadata": metadata,
        "weights": feature_weights,
        "metrics": metrics,
        "runtime_integration": "offline_only",
    }

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8")

    return TrainingReport(
        rows=len(rows),
        features=len(feature_names),
        output_path=str(output_path),
        metrics=metrics,
        feature_weights=feature_weights,
    )
