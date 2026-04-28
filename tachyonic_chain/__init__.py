"""Canonical evidence and audit-chain namespace."""

from trading.evidence.evidence_chain import EvidenceBundle, EvidenceEmitter, MerkleTree
from .audit_log import append_execution_evidence

META = {
    "tier": "rootfile",
    "layer": "tachyonic_chain",
    "operator_type": "evidence_adapter",
}

__all__ = ["EvidenceBundle", "EvidenceEmitter", "MerkleTree", "append_execution_evidence"]
