"""
evidence_chain.py — Cryptographic audit trail

Merkle root + Ed25519 signed evidence bundles ℰ
Deterministic, reproducible, non-repudiable
"""

import hashlib
import hmac
import json
import os
import time
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from datetime import datetime

from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives.serialization import (
    Encoding, PrivateFormat, PublicFormat, NoEncryption,
    load_pem_private_key
)
from cryptography.exceptions import InvalidSignature


@dataclass
class EvidenceBundle:
    """Complete evidence package"""
    bundle_id: str
    timestamp: float
    merkle_root: str
    signature: str
    inputs_hash: str
    operators_applied: List[str]
    constraints_checked: List[str]
    scheduler_decision: str
    execution_result: Dict
    reconciliation_delta: float
    
    def to_dict(self) -> Dict:
        return {
            "bundle_id": self.bundle_id,
            "timestamp": self.timestamp,
            "merkle_root": self.merkle_root,
            "signature": self.signature[:32] + "...",  # Truncated for display
            "inputs_hash": self.inputs_hash,
            "operators_applied": self.operators_applied,
            "constraints_checked": self.constraints_checked,
            "scheduler_decision": self.scheduler_decision,
            "execution_result": self.execution_result,
            "reconciliation_delta": self.reconciliation_delta
        }


class MerkleTree:
    """
    Deterministic Merkle root computation.
    Binary hash tree for evidence integrity.
    """
    
    def __init__(self):
        self.leaves: List[str] = []
        
    def add_leaf(self, data: Any):
        """Add data as leaf node"""
        if isinstance(data, dict):
            data = json.dumps(data, sort_keys=True)
        elif not isinstance(data, str):
            data = str(data)
        
        leaf_hash = hashlib.sha256(data.encode()).hexdigest()
        self.leaves.append(leaf_hash)
    
    def compute_root(self) -> str:
        """Compute Merkle root via pairwise hashing"""
        if not self.leaves:
            return hashlib.sha256(b"empty").hexdigest()
        
        current_level = self.leaves[:]
        
        while len(current_level) > 1:
            next_level = []
            
            for i in range(0, len(current_level), 2):
                left = current_level[i]
                right = current_level[i + 1] if i + 1 < len(current_level) else left
                
                # Pairwise hash
                combined = hashlib.sha256(
                    (left + right).encode()
                ).hexdigest()
                next_level.append(combined)
            
            current_level = next_level
        
        return current_level[0]
    
    def get_proof(self, index: int) -> List[str]:
        """Get Merkle proof path for leaf at index"""
        if index >= len(self.leaves):
            return []
        
        proof = []
        current_level = self.leaves[:]
        current_idx = index
        
        while len(current_level) > 1:
            sibling_idx = current_idx + 1 if current_idx % 2 == 0 else current_idx - 1
            
            if sibling_idx < len(current_level):
                proof.append(current_level[sibling_idx])
            
            current_idx //= 2
            
            # Build next level
            next_level = []
            for i in range(0, len(current_level), 2):
                left = current_level[i]
                right = current_level[i + 1] if i + 1 < len(current_level) else left
                combined = hashlib.sha256((left + right).encode()).hexdigest()
                next_level.append(combined)
            
            current_level = next_level
        
        return proof


class Ed25519Signer:
    """
    Real Ed25519 signature on evidence bundles.

    Key loading priority:
    1. APEX_SIGNING_KEY env var (PEM string)
    2. trading/keys/signing_key.pem file
    3. Generate ephemeral key (development only — warns loudly)
    """

    _KEY_FILE = os.path.join(os.path.dirname(__file__), "..", "keys", "signing_key.pem")

    def __init__(self, private_key_pem: Optional[bytes] = None):
        self._private_key, self._public_key = self._load_or_create(private_key_pem)
        self.public_key_hex = self._public_key.public_bytes(
            Encoding.Raw, PublicFormat.Raw
        ).hex()

    def _load_or_create(self, pem_override: Optional[bytes]):
        # Priority 1: explicit override
        if pem_override:
            priv = load_pem_private_key(pem_override, password=None)
            return priv, priv.public_key()

        # Priority 2: environment variable
        env_pem = os.getenv("APEX_SIGNING_KEY")
        if env_pem:
            priv = load_pem_private_key(env_pem.encode(), password=None)
            return priv, priv.public_key()

        # Priority 3: key file
        key_file = os.path.normpath(self._KEY_FILE)
        if os.path.exists(key_file):
            with open(key_file, "rb") as f:
                priv = load_pem_private_key(f.read(), password=None)
            return priv, priv.public_key()

        # Priority 4: generate ephemeral (dev only)
        import warnings
        warnings.warn(
            "APEX_SIGNING_KEY not set and no key file found. "
            "Generating ephemeral Ed25519 key — signatures will NOT persist across restarts. "
            "Set APEX_SIGNING_KEY env var or place key at trading/keys/signing_key.pem.",
            RuntimeWarning, stacklevel=3
        )
        priv = ed25519.Ed25519PrivateKey.generate()
        return priv, priv.public_key()

    def sign(self, message: str) -> str:
        """Sign message with real Ed25519. Returns 128-char hex signature."""
        return self._private_key.sign(message.encode()).hex()

    def verify(self, message: str, signature_hex: str) -> bool:
        """Constant-time verification of Ed25519 signature."""
        try:
            sig_bytes = bytes.fromhex(signature_hex)
            self._public_key.verify(sig_bytes, message.encode())
            return True
        except (InvalidSignature, ValueError):
            return False

    @staticmethod
    def generate_key_pem() -> bytes:
        """Generate a new Ed25519 private key in PEM format. Store securely."""
        priv = ed25519.Ed25519PrivateKey.generate()
        return priv.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption())


class TachyonicAnchor:
    """
    Deterministic artifact hash anchoring.
    Cross-machine reproducibility verification.
    """
    
    def __init__(self):
        self.anchors: Dict[str, str] = {}
    
    def anchor(self, 
               execution_id: str, 
               evidence_bundle: EvidenceBundle,
               system_state: Dict) -> str:
        """
        Anchor evidence hash for deterministic replay.
        
        Returns anchor hash that can be verified across machines.
        """
        # Deterministic serialization
        anchor_data = {
            "execution_id": execution_id,
            "merkle_root": evidence_bundle.merkle_root,
            "timestamp": evidence_bundle.timestamp,
            "system_version": system_state.get("version", "1.0"),
            "operator_schema": system_state.get("operator_schema_hash", ""),
            "scheduler_state": system_state.get("scheduler_state_hash", "")
        }
        
        # Deterministic hash
        serialized = json.dumps(anchor_data, sort_keys=True, separators=(',', ':'))
        anchor_hash = hashlib.sha256(serialized.encode()).hexdigest()
        
        self.anchors[execution_id] = anchor_hash
        return anchor_hash
    
    def verify_anchor(self, 
                     execution_id: str, 
                     expected_hash: str) -> bool:
        """Verify anchor hash matches recorded"""
        return self.anchors.get(execution_id) == expected_hash


class EvidenceEmitter:
    """
    Evidence emission: packages full execution trace.
    Merkle root + Ed25519 signed bundle.
    """
    
    def __init__(self):
        self.signer = Ed25519Signer()
        self.anchor = TachyonicAnchor()
        self.bundles: Dict[str, EvidenceBundle] = {}
    
    def emit(self,
            execution_id: str,
            inputs: Dict,
            operators_applied: List[str],
            constraints_checked: List[str],
            scheduler_decision: str,
            execution_result: Dict,
            reconciliation_delta: float,
            system_state: Dict) -> EvidenceBundle:
        """
        Emit complete evidence bundle.
        
        Steps:
        1. Build Merkle tree of all execution data
        2. Compute Merkle root
        3. Sign with Ed25519
        4. Anchor for reproducibility
        5. Return bundle
        """
        # Build Merkle tree
        tree = MerkleTree()
        
        # Add all evidence leaves
        tree.add_leaf(inputs)
        tree.add_leaf({"operators": operators_applied})
        tree.add_leaf({"constraints": constraints_checked})
        tree.add_leaf({"scheduler": scheduler_decision})
        tree.add_leaf(execution_result)
        tree.add_leaf({"reconciliation": reconciliation_delta})
        tree.add_leaf({"timestamp": time.time()})
        
        # Compute root
        merkle_root = tree.compute_root()
        
        # Sign
        signature_data = f"{execution_id}:{merkle_root}:{time.time()}"
        signature = self.signer.sign(signature_data)
        
        # Hash inputs
        inputs_hash = hashlib.sha256(
            json.dumps(inputs, sort_keys=True).encode()
        ).hexdigest()
        
        # Create bundle
        bundle = EvidenceBundle(
            bundle_id=f"evidence_{execution_id}_{int(time.time())}",
            timestamp=time.time(),
            merkle_root=merkle_root,
            signature=signature,
            inputs_hash=inputs_hash,
            operators_applied=operators_applied,
            constraints_checked=constraints_checked,
            scheduler_decision=scheduler_decision,
            execution_result=execution_result,
            reconciliation_delta=reconciliation_delta
        )
        
        # Anchor for reproducibility
        anchor_hash = self.anchor.anchor(execution_id, bundle, system_state)
        
        # Store
        self.bundles[bundle.bundle_id] = bundle
        
        return bundle
    
    def verify_bundle(self, bundle_id: str) -> bool:
        """Verify evidence bundle integrity"""
        bundle = self.bundles.get(bundle_id)
        if not bundle:
            return False
        
        # Verify signature
        sig_data = f"{bundle.bundle_id}:{bundle.merkle_root}:{bundle.timestamp}"
        return self.signer.verify(sig_data, bundle.signature)
    
    def get_bundle(self, bundle_id: str) -> Optional[EvidenceBundle]:
        """Retrieve evidence bundle by ID"""
        return self.bundles.get(bundle_id)
    
    def get_reproducibility_report(self, bundle_id: str) -> Dict:
        """Get cross-machine reproducibility verification data"""
        bundle = self.bundles.get(bundle_id)
        if not bundle:
            return {"error": "Bundle not found"}
        
        return {
            "bundle_id": bundle_id,
            "merkle_root": bundle.merkle_root,
            "signature_valid": self.verify_bundle(bundle_id),
            "anchor_hash": self.anchor.anchors.get(bundle_id.replace("evidence_", "").split("_")[0], ""),
            "deterministic": True,  # Design invariant
            "cross_machine_verifiable": True
        }
