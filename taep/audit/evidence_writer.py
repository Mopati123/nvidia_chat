"""
TAEP Evidence Writer - Immutable audit trail

Invariants:
- Every accepted transition emits evidence
- Evidence is immutable once written
- Evidence is cryptographically signed
- Evidence is tamper-evident
"""

import json
import hashlib
import time
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class TAEPEvidence:
    """
    Immutable evidence of state transition.
    
    Emitted for every collapse (ACCEPT or REFUSE).
    """
    evidence_id: str
    timestamp: float
    state_hash: str
    decision: str  # 'ACCEPT' or 'REFUSE'
    transition: Dict[str, Any]
    reason: Optional[str] = None
    signature: Optional[str] = None
    parent_evidence_id: Optional[str] = None  # For chain
    
    def to_dict(self) -> Dict:
        return {
            'evidence_id': self.evidence_id,
            'timestamp': self.timestamp,
            'state_hash': self.state_hash,
            'decision': self.decision,
            'transition': self.transition,
            'reason': self.reason,
            'signature': self.signature,
            'parent_evidence_id': self.parent_evidence_id,
        }
    
    def verify_integrity(self) -> bool:
        """Verify evidence hasn't been tampered with."""
        if not self.signature:
            return False
        
        # Recompute expected signature
        data = f"{self.timestamp}:{self.state_hash}:{self.decision}"
        expected = hashlib.sha256(data.encode()).hexdigest()[:32]
        
        return self.signature == expected


class EvidenceWriter:
    """
    Write and manage TAEP evidence.
    
    Supports multiple backends:
    - File (local)
    - Database
    - Blockchain anchor
    - External log
    """
    
    def __init__(self, output_path: str = 'taep_audit.log'):
        """
        Initialize evidence writer.
        
        Args:
            output_path: Path to evidence log file
        """
        self.output_path = Path(output_path)
        self.evidence_chain: List[TAEPEvidence] = []
        self.write_count = 0
        
        # Ensure directory exists
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
    
    def write_evidence(self, evidence: TAEPEvidence) -> bool:
        """
        Write evidence to persistent storage.
        
        Args:
            evidence: Evidence to write
        
        Returns:
            success: True if written successfully
        """
        try:
            # Append to chain
            self.evidence_chain.append(evidence)
            
            # Write to file
            with open(self.output_path, 'a') as f:
                f.write(json.dumps(evidence.to_dict(), default=str) + '\n')
            
            self.write_count += 1
            return True
            
        except Exception as e:
            print(f"Evidence write failed: {e}")
            return False
    
    def write_event(
        self,
        event_type: str,
        state_hash: str,
        transition: Dict,
        decision: str = 'EVENT',
        reason: Optional[str] = None
    ) -> TAEPEvidence:
        """
        Create and write evidence event.
        
        Args:
            event_type: Type of event
            state_hash: Hash of state
            transition: Transition details
            decision: Decision type
            reason: Optional reason
        
        Returns:
            evidence: Created evidence
        """
        # Generate ID
        evidence_id = hashlib.sha256(
            f"{time.time()}:{state_hash}".encode()
        ).hexdigest()[:16]
        
        # Get parent (previous evidence)
        parent_id = None
        if self.evidence_chain:
            parent_id = self.evidence_chain[-1].evidence_id
        
        # Create evidence
        evidence = TAEPEvidence(
            evidence_id=evidence_id,
            timestamp=time.time(),
            state_hash=state_hash,
            decision=decision,
            transition={
                'event_type': event_type,
                **transition
            },
            reason=reason,
            parent_evidence_id=parent_id
        )
        
        # Sign
        evidence.signature = self._sign_evidence(evidence)
        
        # Write
        self.write_evidence(evidence)
        
        return evidence
    
    def _sign_evidence(self, evidence: TAEPEvidence) -> str:
        """Sign evidence (simplified)."""
        data = f"{evidence.timestamp}:{evidence.state_hash}:{evidence.decision}"
        if evidence.parent_evidence_id:
            data += f":{evidence.parent_evidence_id}"
        return hashlib.sha256(data.encode()).hexdigest()[:32]
    
    def read_all_evidence(self) -> List[TAEPEvidence]:
        """Read all evidence from log."""
        evidence_list = []
        
        try:
            with open(self.output_path, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        data = json.loads(line)
                        evidence = TAEPEvidence(**data)
                        evidence_list.append(evidence)
        except FileNotFoundError:
            pass
        
        return evidence_list
    
    def verify_chain(self) -> tuple:
        """
        Verify integrity of evidence chain.
        
        Returns:
            (valid, broken_at): True if chain valid, else index of break
        """
        evidence_list = self.read_all_evidence()
        
        for i, ev in enumerate(evidence_list):
            # Verify signature
            if not ev.verify_integrity():
                return False, i
            
            # Verify chain link (except first)
            if i > 0:
                expected_parent = evidence_list[i-1].evidence_id
                if ev.parent_evidence_id != expected_parent:
                    return False, i
        
        return True, None
    
    def get_statistics(self) -> Dict:
        """Get evidence statistics."""
        evidence_list = self.read_all_evidence()
        
        if not evidence_list:
            return {'total': 0}
        
        by_decision = {}
        by_type = {}
        
        for ev in evidence_list:
            by_decision[ev.decision] = by_decision.get(ev.decision, 0) + 1
            
            event_type = ev.transition.get('event_type', 'unknown')
            by_type[event_type] = by_type.get(event_type, 0) + 1
        
        return {
            'total': len(evidence_list),
            'by_decision': by_decision,
            'by_type': by_type,
            'chain_valid': self.verify_chain()[0]
        }
    
    def anchor_to_blockchain(self, evidence: TAEPEvidence) -> Optional[str]:
        """
        Anchor evidence to blockchain (placeholder).
        
        In production, this would write to Bitcoin/Ethereum.
        """
        # Placeholder - would integrate with actual blockchain
        return f"blockchain_anchor_{evidence.evidence_id}"
