"""ML adapters for model-backed state preparation."""

from .evidence_dataset import (
    DatasetBuildReport,
    audit_record_to_refusal_example,
    build_refusal_risk_dataset,
    sanitize_audit_record,
)
from .refusal_risk_trainer import TrainingReport, train_refusal_risk_model

META = {
    "tier": "rootfile",
    "layer": "data_core.ml",
    "operator_type": "cp_map",
}

__all__ = [
    "DatasetBuildReport",
    "TrainingReport",
    "audit_record_to_refusal_example",
    "build_refusal_risk_dataset",
    "sanitize_audit_record",
    "train_refusal_risk_model",
]
