"""
TAEP Scheduler - Sole collapse authority

Invariants:
1. No execution without scheduler authorization
2. No self-authorization
3. All accepted transitions emit evidence

The scheduler is the only component that can authorize state transitions.
"""

import time
import hashlib
from typing import Dict, Optional, Any, List, Callable
from dataclasses import dataclass, field


@dataclass
class TAEPEvidence:
    """
    Evidence of a state transition.
    
    Emitted for every collapse (ACCEPT or REFUSE).
    Immutable record for audit.
    """
    timestamp: float
    state_hash: str
    decision: str  # 'ACCEPT' or 'REFUSE'
    transition: Dict
    reason: Optional[str] = None
    signature: Optional[str] = None
    evidence_id: str = field(default_factory=lambda: 
        hashlib.sha256(str(time.time()).encode()).hexdigest()[:16]
    )
    
    def to_dict(self) -> Dict:
        return {
            'evidence_id': self.evidence_id,
            'timestamp': self.timestamp,
            'state_hash': self.state_hash,
            'decision': self.decision,
            'transition': self.transition,
            'reason': self.reason,
        }


@dataclass
class SchedulerDecision:
    """Complete decision with evidence."""
    authorized: bool
    evidence: TAEPEvidence
    token_valid: bool
    constraints_passed: bool
    budget_sufficient: bool


class TAEPScheduler:
    """
    TAEP collapse authority.
    
    Sole authority for:
    - Execution authorization
    - Budget enforcement
    - Policy compliance
    - Evidence emission
    
    No component may self-authorize execution.
    """
    
    def __init__(self, policy_engine=None):
        """
        Initialize scheduler.
        
        Args:
            policy_engine: Optional policy enforcement engine
        """
        self.policy_engine = policy_engine
        self.decision_history = []
        self.evidence_log = []
    
    def authorize(
        self,
        state,
        transition: Dict,
        context: Optional[Dict] = None
    ) -> bool:
        """
        Authorize state transition.
        
        Checks:
        1. Token validity (τ valid and not expired)
        2. State admissibility (x ∈ A(t))
        3. Budget constraints
        4. Policy compliance (π satisfied)
        
        Args:
            state: TAEPState or trading state
            transition: Proposed transition
            context: Additional context
        
        Returns:
            authorized: True if all checks pass
        """
        # Check 1: Token validity
        if not self._check_token(state):
            return False
        
        # Check 2: State admissibility
        if hasattr(state, 'is_admissible') and not state.is_admissible():
            return False
        
        # Check 3: Budget
        if not self._check_budget(state, transition):
            return False
        
        # Check 4: Policy
        if not self._check_policy(state, transition, context):
            return False
        
        return True
    
    def collapse(
        self,
        state,
        authorized: bool,
        transition: Optional[Dict] = None,
        reason: Optional[str] = None
    ) -> TAEPEvidence:
        """
        Collapse state - commit or refuse transition.
        
        Emits evidence regardless of outcome.
        This is the audit-first invariant.
        
        Args:
            state: Current state
            authorized: Whether transition was authorized
            transition: Transition details
            reason: Reason for refusal (if applicable)
        
        Returns:
            evidence: Immutable evidence record
        """
        # Compute state hash
        if hasattr(state, 'compute_hash'):
            state_hash = state.compute_hash()
        else:
            state_hash = self._compute_simple_hash(state)
        
        # Create evidence
        evidence = TAEPEvidence(
            timestamp=time.time(),
            state_hash=state_hash,
            decision='ACCEPT' if authorized else 'REFUSE',
            transition=transition or {},
            reason=reason
        )
        
        # Sign evidence (simplified)
        evidence.signature = self._sign_evidence(evidence)
        
        # Store
        self.evidence_log.append(evidence)
        
        return evidence
    
    def execute_stage(
        self,
        state,
        stage_func: callable,
        transition: Dict,
        context: Optional[Dict] = None
    ) -> tuple:
        """
        Execute a stage under TAEP governance.
        
        Flow:
        1. Authorize
        2. Execute (if authorized)
        3. Collapse (emit evidence)
        
        Args:
            state: Current state
            stage_func: Function to execute
            transition: Transition description
            context: Context
        
        Returns:
            (result, evidence): Execution result and evidence
        """
        # Authorize
        authorized = self.authorize(state, transition, context)
        
        reason = None
        result = None
        
        if authorized:
            try:
                result = stage_func(state)
            except Exception as e:
                authorized = False
                reason = f"Execution failed: {str(e)}"
        else:
            reason = "Authorization refused"
        
        # Collapse (always emit evidence)
        evidence = self.collapse(state, authorized, transition, reason)
        
        # Log decision
        self.decision_history.append({
            'timestamp': time.time(),
            'authorized': authorized,
            'evidence_id': evidence.evidence_id,
            'transition': transition,
        })
        
        return result, evidence
    
    def issue_token(
        self,
        operation: str,
        budget: float,
        expiry_duration: float = 300.0,
        constraints: Optional[Dict] = None
    ) -> 'ExecutionToken':
        """
        Issue execution token.
        
        Token grants temporary authority for specific operation.
        
        Args:
            operation: Operation type
            budget: Resource budget
            expiry_duration: Token validity duration (seconds)
            constraints: Additional constraints
        
        Returns:
            token: Execution token
        """
        from ..core.state import ExecutionToken
        
        token = ExecutionToken(
            operation=operation,
            budget=budget,
            expiry=time.time() + expiry_duration,
            valid=True
        )
        
        # Sign token (simplified)
        token.signature = self._sign_token(token)
        
        return token
    
    def revoke_token(self, token: 'ExecutionToken'):
        """Revoke a token."""
        token.revoke()
    
    def _check_token(self, state) -> bool:
        """Check token validity."""
        if not hasattr(state, 'token') or state.token is None:
            return False
        
        return state.token.valid and not state.token.expired()
    
    def _check_budget(self, state, transition: Dict) -> bool:
        """Check budget constraints."""
        if not hasattr(state, 'token') or state.token is None:
            return False
        
        required = transition.get('budget_required', 0.0)
        return state.token.budget >= required
    
    def _check_policy(self, state, transition: Dict, context: Optional[Dict]) -> bool:
        """Check policy compliance."""
        if self.policy_engine:
            return self.policy_engine.check(state, transition, context)
        
        # Default: allow
        return True
    
    def _compute_simple_hash(self, obj: Any) -> str:
        """Compute simple hash for non-TAEPState objects."""
        import json
        try:
            s = json.dumps(obj, sort_keys=True, default=str)
            return hashlib.sha256(s.encode()).hexdigest()
        except:
            return hashlib.sha256(str(obj).encode()).hexdigest()
    
    def _sign_evidence(self, evidence: TAEPEvidence) -> str:
        """Sign evidence (simplified - would use proper crypto in production)."""
        data = f"{evidence.timestamp}:{evidence.state_hash}:{evidence.decision}"
        return hashlib.sha256(data.encode()).hexdigest()[:32]
    
    def _sign_token(self, token: 'ExecutionToken') -> str:
        """Sign token (simplified)."""
        data = f"{token.operation}:{token.budget}:{token.expiry}"
        return hashlib.sha256(data.encode()).hexdigest()[:32]
    
    def get_audit_trail(self) -> list:
        """Get complete audit trail."""
        return [e.to_dict() for e in self.evidence_log]
    
    def verify_evidence(self, evidence: TAEPEvidence) -> bool:
        """Verify evidence integrity."""
        expected_sig = self._sign_evidence(evidence)
        return evidence.signature == expected_sig


# Global scheduler instance
_scheduler: Optional[TAEPScheduler] = None


def get_scheduler() -> TAEPScheduler:
    """Get or create global TAEP scheduler"""
    global _scheduler
    if _scheduler is None:
        _scheduler = TAEPScheduler()
    return _scheduler
