"""
Test TAEPState and admissibility
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import pytest
import numpy as np
from taep.core.state import TAEPState, ExecutionToken


class TestTAEPState:
    """Test TAEPState creation and properties."""
    
    def test_state_creation(self):
        """Can create TAEPState with all components."""
        token = ExecutionToken(
            operation='test',
            budget=1000.0,
            expiry=9999999999.0
        )
        
        state = TAEPState(
            q=np.array([1.0, 2.0, 3.0]),
            p=np.array([0.1, 0.2, 0.3]),
            k=np.array([0.5]),
            policy={'max_position': 10.0},
            entropy=0.5,
            token=token
        )
        
        assert state is not None
        assert len(state.q) == 3
        assert state.token is not None
    
    def test_admissibility_positive_price(self):
        """State with positive price is admissible."""
        token = ExecutionToken('test', 1000.0, 9999999999.0)
        
        state = TAEPState(
            q=np.array([1.0850, 1000.0, 0.5]),  # price > 0
            p=np.array([0.0, 0.0, 0.0]),
            k=np.array([0.5]),
            policy={},
            entropy=0.5,
            token=token
        )
        
        assert state.is_admissible()
    
    def test_admissibility_negative_price_not_allowed(self):
        """State with negative price is not admissible."""
        token = ExecutionToken('test', 1000.0, 9999999999.0)
        
        state = TAEPState(
            q=np.array([-1.0, 1000.0, 0.5]),  # price < 0
            p=np.array([0.0, 0.0, 0.0]),
            k=np.array([0.5]),
            policy={},
            entropy=0.5,
            token=token
        )
        
        assert not state.is_admissible()
    
    def test_admissibility_expired_token(self):
        """State with expired token is not admissible."""
        token = ExecutionToken('test', 1000.0, 0.0)  # Already expired
        
        state = TAEPState(
            q=np.array([1.0850, 1000.0, 0.5]),
            p=np.array([0.0, 0.0, 0.0]),
            k=np.array([0.5]),
            policy={},
            entropy=0.5,
            token=token
        )
        
        assert not state.is_admissible()
    
    def test_state_hash_computed(self):
        """Can compute state hash."""
        token = ExecutionToken('test', 1000.0, 9999999999.0)
        
        state = TAEPState(
            q=np.array([1.0850, 1000.0, 0.5]),
            p=np.array([0.0, 0.0, 0.0]),
            k=np.array([0.5]),
            policy={},
            entropy=0.5,
            token=token
        )
        
        hash_val = state.compute_hash()
        assert hash_val is not None
        assert len(hash_val) == 64  # SHA-256 hex
    
    def test_serialization(self):
        """Can serialize and deserialize state."""
        token = ExecutionToken('test', 1000.0, 9999999999.0)
        
        state = TAEPState(
            q=np.array([1.0850, 1000.0, 0.5]),
            p=np.array([0.0, 0.0, 0.0]),
            k=np.array([0.5]),
            policy={'max_position': 10.0},
            entropy=0.5,
            token=token
        )
        
        # Serialize
        d = state.to_dict()
        assert 'q' in d
        assert 'policy' in d
        
        # Deserialize
        state2 = TAEPState.from_dict(d)
        assert np.allclose(state2.q, state.q)
        assert state2.policy == state.policy


class TestExecutionToken:
    """Test ExecutionToken functionality."""
    
    def test_token_creation(self):
        """Can create valid token."""
        token = ExecutionToken(
            operation='TRADE',
            budget=1000.0,
            expiry=9999999999.0
        )
        
        assert token.operation == 'TRADE'
        assert token.budget == 1000.0
        assert token.valid
    
    def test_token_not_expired(self):
        """Token not expired before expiry."""
        token = ExecutionToken(
            operation='test',
            budget=100.0,
            expiry=9999999999.0  # Far future
        )
        
        assert not token.expired()
    
    def test_token_expired(self):
        """Token expired after expiry."""
        token = ExecutionToken(
            operation='test',
            budget=100.0,
            expiry=0.0  # Already expired
        )
        
        assert token.expired()
    
    def test_token_revoke(self):
        """Can revoke token."""
        token = ExecutionToken('test', 100.0, 9999999999.0)
        assert token.valid
        
        token.revoke()
        assert not token.valid


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
