"""Canonical evidence and audit-chain namespace."""

from trading.evidence.evidence_chain import EvidenceBundle, EvidenceEmitter, MerkleTree
from .audit_log import (
    ValidationReport,
    append_execution_evidence,
    iter_execution_evidence,
    verify_execution_evidence_chain,
)

META = {
    "tier": "rootfile",
    "layer": "tachyonic_chain",
    "operator_type": "evidence_adapter",
}

__all__ = [
    "EvidenceBundle",
    "EvidenceEmitter",
    "MerkleTree",
    "ValidationReport",
    "append_execution_evidence",
    "iter_execution_evidence",
    "verify_execution_evidence_chain",
]
