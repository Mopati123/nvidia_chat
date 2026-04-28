"""Canonical evidence and audit-chain namespace."""

from trading.evidence.evidence_chain import EvidenceBundle, EvidenceEmitter, MerkleTree

META = {
    "tier": "rootfile",
    "layer": "tachyonic_chain",
    "operator_type": "evidence_adapter",
}

__all__ = ["EvidenceBundle", "EvidenceEmitter", "MerkleTree"]

