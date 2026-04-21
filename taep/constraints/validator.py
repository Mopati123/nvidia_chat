"""
Constraint Validator - Comprehensive validation suite
"""

import numpy as np
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass


@dataclass
class ValidationResult:
    """Result of constraint validation."""
    valid: bool
    violations: List[str]
    details: Dict[str, Any]


class ConstraintValidator:
    """
    Comprehensive constraint validator.
    
    Validates:
    - State admissibility
    - Budget constraints
    - Policy compliance
    - Temporal constraints
    """
    
    def __init__(self):
        self.validators: List[Callable] = []
        self.validation_history: List[ValidationResult] = []
    
    def add_validator(self, validator: Callable):
        """Add custom validator function."""
        self.validators.append(validator)
    
    def validate(self, state, transition: Optional[Dict] = None) -> ValidationResult:
        """
        Run all validations on state and transition.
        
        Args:
            state: TAEPState or trading state
            transition: Proposed transition
        
        Returns:
            ValidationResult with validity and violations
        """
        violations = []
        details = {}
        
        # Built-in validations
        # 1. State bounds
        bounds_ok, bounds_details = self._validate_bounds(state)
        if not bounds_ok:
            violations.extend(bounds_details)
        details['bounds'] = bounds_ok
        
        # 2. Token validity
        token_ok, token_details = self._validate_token(state)
        if not token_ok:
            violations.extend(token_details)
        details['token'] = token_ok
        
        # 3. Budget
        budget_ok, budget_details = self._validate_budget(state, transition)
        if not budget_ok:
            violations.extend(budget_details)
        details['budget'] = budget_ok
        
        # 4. Custom validators
        for validator in self.validators:
            try:
                result = validator(state, transition)
                if isinstance(result, str):
                    violations.append(result)
                elif isinstance(result, list):
                    violations.extend(result)
                elif isinstance(result, tuple):
                    if not result[0]:
                        violations.append(result[1])
            except Exception as e:
                violations.append(f"Validator error: {str(e)}")
        
        result = ValidationResult(
            valid=len(violations) == 0,
            violations=violations,
            details=details
        )
        
        self.validation_history.append(result)
        return result
    
    def _validate_bounds(self, state) -> tuple:
        """Validate state is within bounds."""
        violations = []
        
        if hasattr(state, 'q'):
            if not np.all(np.isfinite(state.q)):
                violations.append("State contains non-finite values")
            
            # Check for NaN/Inf
            if np.any(np.isnan(state.q)):
                violations.append("State contains NaN values")
            
            # Check reasonable magnitude
            if np.any(np.abs(state.q) > 1e308):
                violations.append("State values unreasonably large")
        
        return len(violations) == 0, violations
    
    def _validate_token(self, state) -> tuple:
        """Validate execution token."""
        violations = []
        
        if not hasattr(state, 'token') or state.token is None:
            violations.append("No execution token")
            return False, violations
        
        if not state.token.valid:
            violations.append("Token is invalid")
        
        if state.token.expired():
            violations.append("Token has expired")
        
        return len(violations) == 0, violations
    
    def _validate_budget(self, state, transition: Optional[Dict]) -> tuple:
        """Validate budget constraints."""
        violations = []
        
        if not hasattr(state, 'token') or state.token is None:
            return True, []  # No token, no budget check
        
        available = state.token.budget
        
        if transition:
            required = transition.get('budget_required', 0.0)
            if required > available:
                violations.append(
                    f"Insufficient budget: required {required}, available {available}"
                )
        
        return len(violations) == 0, violations
    
    def get_stats(self) -> Dict:
        """Get validation statistics."""
        if not self.validation_history:
            return {'total': 0}
        
        total = len(self.validation_history)
        passed = sum(1 for r in self.validation_history if r.valid)
        failed = total - passed
        
        # Most common violations
        all_violations = []
        for r in self.validation_history:
            all_violations.extend(r.violations)
        
        from collections import Counter
        common = Counter(all_violations).most_common(5)
        
        return {
            'total': total,
            'passed': passed,
            'failed': failed,
            'pass_rate': passed / total if total > 0 else 0,
            'common_violations': common
        }
