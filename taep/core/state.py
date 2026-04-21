"""
TAEP State - Complete state vector: x = (q, p, k, π, σ, τ)

q: Phase-space position (geometric)
p: Phase-space momentum (chaos)
k: Cryptographic key state
π: Policy/constraint state  
σ: Statistical entropy
τ: Execution token (scheduler authority)
"""

import numpy as np
import time
import hashlib
import json
from typing import Dict, Optional, Any
from dataclasses import dataclass, field


@dataclass
class ExecutionToken:
    """
    TAEP execution token - proof of scheduler authority.
    
    τ = (operation, budget, expiry, signature)
    """
    operation: str
    budget: float
    expiry: float
    issued_at: float = field(default_factory=time.time)
    valid: bool = True
    signature: Optional[str] = None
    
    def expired(self) -> bool:
        """Check if token has expired."""
        return time.time() > self.expiry
    
    def revoke(self):
        """Revoke token validity."""
        self.valid = False
    
    def to_dict(self) -> Dict:
        return {
            'operation': self.operation,
            'budget': self.budget,
            'expiry': self.expiry,
            'issued_at': self.issued_at,
            'valid': self.valid,
        }


@dataclass 
class TAEPState:
    """
    Complete TAEP state vector.
    
    State: x = (q, p, k, π, σ, τ)
    
    Components:
    - q: np.ndarray - Geometric position [price, time, liquidity_field]
    - p: np.ndarray - Momentum [velocity, acceleration, spread]
    - k: np.ndarray - Cryptographic key state
    - policy: Dict - Constraint/policy state (π)
    - entropy: float - Statistical entropy (σ)
    - token: ExecutionToken - Execution authority (τ)
    """
    q: np.ndarray  # Geometric position
    p: np.ndarray  # Momentum
    k: np.ndarray  # Key state
    policy: Dict   # π: Policy/constraints
    entropy: float # σ: Entropy
    token: ExecutionToken  # τ: Execution authority
    
    # Metadata
    timestamp: float = field(default_factory=time.time)
    state_id: str = field(default_factory=lambda: 
        hashlib.sha256(str(time.time()).encode()).hexdigest()[:16]
    )
    
    def __post_init__(self):
        """Ensure numpy arrays."""
        self.q = np.array(self.q, dtype=np.float64)
        self.p = np.array(self.p, dtype=np.float64)
        self.k = np.array(self.k, dtype=np.float64)
    
    def is_admissible(self) -> bool:
        """
        Check if state is in A(t) (admissible set).
        
        Validates:
        1. Geometric bounds (q finite)
        2. Momentum bounds (p finite)
        3. Entropy bounds (σ > 0)
        4. Token validity (τ valid and not expired)
        5. Policy compliance
        """
        return (
            self._check_geometric_bounds() and
            self._check_momentum_bounds() and
            self._check_entropy_bounds() and
            self._check_token_validity() and
            self._check_policy_compliance()
        )
    
    def _check_geometric_bounds(self) -> bool:
        """Check geometric state is finite and bounded."""
        if not np.all(np.isfinite(self.q)):
            return False
        
        # Check bounds (e.g., price > 0)
        if self.q[0] <= 0:  # Price must be positive
            return False
        
        return True
    
    def _check_momentum_bounds(self) -> bool:
        """Check momentum is finite."""
        return np.all(np.isfinite(self.p))
    
    def _check_entropy_bounds(self) -> bool:
        """Check entropy is positive and finite."""
        return np.isfinite(self.entropy) and self.entropy >= 0
    
    def _check_token_validity(self) -> bool:
        """Check execution token is valid and not expired."""
        if self.token is None:
            return False
        return self.token.valid and not self.token.expired()
    
    def _check_policy_compliance(self) -> bool:
        """Check policy constraints."""
        # Check max position if specified
        max_pos = self.policy.get('max_position')
        if max_pos is not None and abs(self.q[0]) > max_pos:
            return False
        
        # Check risk budget
        budget = self.policy.get('risk_budget')
        if budget is not None and budget <= 0:
            return False
        
        return True
    
    def compute_hash(self) -> str:
        """Compute SHA-256 hash of state for evidence."""
        state_str = json.dumps(self.to_dict(), sort_keys=True, default=str)
        return hashlib.sha256(state_str.encode()).hexdigest()
    
    def to_dict(self) -> Dict:
        """Serialize state to dictionary."""
        return {
            'q': self.q.tolist(),
            'p': self.p.tolist(),
            'k': self.k.tolist(),
            'policy': self.policy,
            'entropy': self.entropy,
            'token': self.token.to_dict() if self.token else None,
            'timestamp': self.timestamp,
            'state_id': self.state_id,
        }
    
    @classmethod
    def from_dict(cls, d: Dict) -> 'TAEPState':
        """Deserialize from dictionary."""
        token = ExecutionToken(**d['token']) if d.get('token') else None
        return cls(
            q=np.array(d['q']),
            p=np.array(d['p']),
            k=np.array(d['k']),
            policy=d['policy'],
            entropy=d['entropy'],
            token=token,
            timestamp=d.get('timestamp', time.time()),
            state_id=d.get('state_id', ''),
        )


class StateSpace:
    """
    Define admissible (A) and forbidden (F) regions of state space.
    """
    
    def __init__(self, bounds: Dict[str, tuple]):
        """
        Define state space bounds.
        
        Args:
            bounds: Dict mapping state components to (min, max) tuples
                   e.g., {'q[0]': (0, 1e6), 'entropy': (0, 100)}
        """
        self.bounds = bounds
    
    def is_admissible(self, state: TAEPState) -> bool:
        """Check if state is in admissible set A(t)."""
        # Check geometric bounds
        for i, (min_val, max_val) in self.bounds.get('q', {}).items():
            if not (min_val <= state.q[i] <= max_val):
                return False
        
        # Check entropy bounds
        if 'entropy' in self.bounds:
            min_e, max_e = self.bounds['entropy']
            if not (min_e <= state.entropy <= max_e):
                return False
        
        return True
    
    def project_to_admissible(self, state: TAEPState) -> TAEPState:
        """
        Project state onto admissible set (constraint enforcement).
        
        Returns state clipped to bounds.
        """
        new_state = TAEPState(
            q=np.clip(state.q, *self.bounds.get('q', [(0, np.inf)])[0]),
            p=state.p,  # Momentum can be unbounded
            k=state.k,
            policy=state.policy,
            entropy=np.clip(state.entropy, 0, 100),
            token=state.token,
        )
        return new_state
