"""
Admissibility Checker - Enforce A(t) (admissible region)

State must remain in admissible set:
x(t) in A(t) for all t

Forbidden set: F(t) = X \\ A(t)
"""

import numpy as np
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass


@dataclass
class ConstraintViolation:
    """Record of constraint violation."""
    constraint_type: str
    severity: str  # 'warning', 'critical', 'fatal'
    message: str
    value: Optional[float] = None
    threshold: Optional[float] = None


class StateSpace:
    """
    Define admissible (A) and forbidden (F) regions.
    """
    
    def __init__(self, bounds: Dict[str, tuple]):
        """
        Define state space bounds.
        
        Args:
            bounds: Dict mapping components to (min, max)
                   e.g., {'q[0]': (0, 1e6), 'entropy': (0, 100)}
        """
        self.bounds = bounds
    
    def is_admissible(self, state) -> bool:
        """Check if state is in A(t)."""
        return len(self.check_violations(state)) == 0
    
    def check_violations(self, state) -> List[ConstraintViolation]:
        """
        Check all constraints and return violations.
        
        Args:
            state: TAEPState or trading state
        
        Returns:
            violations: List of constraint violations
        """
        violations = []
        
        # Check geometric bounds
        if hasattr(state, 'q'):
            for i, (comp, (min_val, max_val)) in enumerate(
                self.bounds.get('q', {}).items()
            ):
                if i < len(state.q):
                    val = state.q[i]
                    if not (min_val <= val <= max_val):
                        violations.append(ConstraintViolation(
                            constraint_type='geometric_bound',
                            severity='critical',
                            message=f'q[{i}] = {val} outside [{min_val}, {max_val}]',
                            value=val,
                            threshold=max_val if val > max_val else min_val
                        ))
        
        # Check entropy bounds
        if hasattr(state, 'entropy'):
            if 'entropy' in self.bounds:
                min_e, max_e = self.bounds['entropy']
                if not (min_e <= state.entropy <= max_e):
                    violations.append(ConstraintViolation(
                        constraint_type='entropy_bound',
                        severity='warning',
                        message=f'entropy = {state.entropy} outside [{min_e}, {max_e}]',
                        value=state.entropy,
                        threshold=max_e if state.entropy > max_e else min_e
                    ))
        
        # Check token validity
        if hasattr(state, 'token'):
            if state.token is None:
                violations.append(ConstraintViolation(
                    constraint_type='token_missing',
                    severity='fatal',
                    message='Execution token missing'
                ))
            elif not state.token.valid:
                violations.append(ConstraintViolation(
                    constraint_type='token_invalid',
                    severity='fatal',
                    message='Execution token invalid'
                ))
            elif state.token.expired():
                violations.append(ConstraintViolation(
                    constraint_type='token_expired',
                    severity='fatal',
                    message='Execution token expired'
                ))
        
        return violations
    
    def project_to_admissible(self, state):
        """
        Project state onto admissible set.
        
        Returns state clipped to bounds.
        """
        if hasattr(state, 'q'):
            q_clipped = state.q.copy()
            for i, (min_val, max_val) in self.bounds.get('q', {}).items():
                if i < len(q_clipped):
                    q_clipped[i] = np.clip(q_clipped[i], min_val, max_val)
            
            # Create new state with clipped values
            from ..core.state import TAEPState
            new_state = TAEPState(
                q=q_clipped,
                p=state.p,
                k=state.k,
                policy=state.policy,
                entropy=np.clip(state.entropy, 0, 100) if hasattr(state, 'entropy') else 0.0,
                token=state.token
            )
            return new_state
        
        return state


class AdmissibilityChecker:
    """
    Comprehensive admissibility checker.
    
    Combines multiple constraint types:
    - Geometric bounds
    - Budget constraints
    - Policy constraints
    - Temporal constraints
    """
    
    def __init__(self, state_space: Optional[StateSpace] = None):
        self.state_space = state_space
        self.custom_constraints: List[Callable] = []
        self.violation_history: List[ConstraintViolation] = []
    
    def add_constraint(self, constraint_func: Callable):
        """Add custom constraint function."""
        self.custom_constraints.append(constraint_func)
    
    def check(self, state) -> tuple:
        """
        Full admissibility check.
        
        Returns:
            (is_admissible, violations)
        """
        all_violations = []
        
        # State space bounds
        if self.state_space:
            violations = self.state_space.check_violations(state)
            all_violations.extend(violations)
        
        # Custom constraints
        for constraint in self.custom_constraints:
            try:
                result = constraint(state)
                if result is not True:
                    if isinstance(result, str):
                        all_violations.append(ConstraintViolation(
                            constraint_type='custom',
                            severity='critical',
                            message=result
                        ))
                    elif isinstance(result, ConstraintViolation):
                        all_violations.append(result)
            except Exception as e:
                all_violations.append(ConstraintViolation(
                    constraint_type='custom_error',
                    severity='fatal',
                    message=f'Constraint error: {str(e)}'
                ))
        
        # Record violations
        self.violation_history.extend(all_violations)
        
        is_admissible = len(all_violations) == 0
        
        return is_admissible, all_violations
    
    def enforce(self, state, strict: bool = True):
        """
        Enforce admissibility by projection or refusal.
        
        Args:
            state: Current state
            strict: If True, refuse non-admissible states
                   If False, project to admissible region
        
        Returns:
            (state, violations)
        """
        is_admissible, violations = self.check(state)
        
        if is_admissible:
            return state, []
        
        if strict:
            # Refuse - return original with violations
            return state, violations
        else:
            # Project to admissible
            if self.state_space:
                projected = self.state_space.project_to_admissible(state)
                return projected, violations
            return state, violations
    
    def get_violation_stats(self) -> Dict:
        """Get violation statistics."""
        if not self.violation_history:
            return {'total': 0}
        
        by_type = {}
        by_severity = {}
        
        for v in self.violation_history:
            by_type[v.constraint_type] = by_type.get(v.constraint_type, 0) + 1
            by_severity[v.severity] = by_severity.get(v.severity, 0) + 1
        
        return {
            'total': len(self.violation_history),
            'by_type': by_type,
            'by_severity': by_severity
        }


def create_default_state_space() -> StateSpace:
    """Create default trading-focused state space bounds."""
    return StateSpace(bounds={
        'q': {
            0: (0.0001, 1e9),    # Price > 0
            1: (0, 2**50),       # Timestamp (reasonable range)
            2: (-100, 100),      # Liquidity field
        },
        'entropy': (0, 1000),
    })
