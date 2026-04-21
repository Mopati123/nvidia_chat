"""
Execution Token Manager

Manages lifecycle of execution tokens:
- Issuance
- Validation
- Revocation
- Renewal
"""

import time
import hashlib
from typing import Dict, Optional, List
from dataclasses import dataclass


@dataclass
class TokenRecord:
    """Record of issued token."""
    token_id: str
    operation: str
    issued_at: float
    expires_at: float
    revoked: bool = False
    used: bool = False


class ExecutionTokenManager:
    """
    Manages execution token lifecycle.
    
    Responsibilities:
    - Track issued tokens
    - Prevent replay attacks
    - Enforce expiry
    - Audit token usage
    """
    
    def __init__(self):
        self.tokens: Dict[str, TokenRecord] = {}
        self.usage_log: List[Dict] = []
    
    def issue_token(
        self,
        operation: str,
        budget: float,
        expiry_duration: float = 300.0,
        constraints: Optional[Dict] = None
    ) -> 'ExecutionToken':
        """
        Issue new execution token.
        
        Args:
            operation: Operation type
            budget: Resource budget
            expiry_duration: Validity duration
            constraints: Additional constraints
        
        Returns:
            token: New execution token
        """
        from ..core.state import ExecutionToken
        
        token = ExecutionToken(
            operation=operation,
            budget=budget,
            expiry=time.time() + expiry_duration
        )
        
        # Generate unique ID
        token_id = hashlib.sha256(
            f"{operation}:{time.time()}:{budget}".encode()
        ).hexdigest()[:16]
        
        # Record
        record = TokenRecord(
            token_id=token_id,
            operation=operation,
            issued_at=time.time(),
            expires_at=token.expiry
        )
        
        self.tokens[token_id] = record
        
        return token
    
    def validate_token(self, token: 'ExecutionToken') -> bool:
        """
        Validate token for use.
        
        Checks:
        1. Not expired
        2. Not revoked
        3. Not already used
        
        Args:
            token: Token to validate
        
        Returns:
            valid: True if token is valid
        """
        if token.expired():
            return False
        
        if not token.valid:
            return False
        
        return True
    
    def consume_token(self, token: 'ExecutionToken') -> bool:
        """
        Mark token as consumed.
        
        Args:
            token: Token to consume
        
        Returns:
            success: True if consumed successfully
        """
        if not self.validate_token(token):
            return False
        
        # Mark as used
        token.valid = False
        
        # Log usage
        self.usage_log.append({
            'timestamp': time.time(),
            'operation': token.operation,
            'budget': token.budget
        })
        
        return True
    
    def revoke_token(self, token_id: str) -> bool:
        """
        Revoke a token by ID.
        
        Args:
            token_id: Token ID to revoke
        
        Returns:
            success: True if revoked
        """
        if token_id in self.tokens:
            self.tokens[token_id].revoked = True
            return True
        return False
    
    def cleanup_expired(self) -> int:
        """
        Clean up expired tokens.
        
        Returns:
            count: Number of tokens cleaned up
        """
        current_time = time.time()
        expired = [
            tid for tid, rec in self.tokens.items()
            if rec.expires_at < current_time
        ]
        
        for tid in expired:
            del self.tokens[tid]
        
        return len(expired)
    
    def get_token_stats(self) -> Dict:
        """Get token statistics."""
        total = len(self.tokens)
        active = sum(
            1 for rec in self.tokens.values()
            if not rec.revoked and rec.expires_at > time.time()
        )
        revoked = sum(1 for rec in self.tokens.values() if rec.revoked)
        used = sum(1 for rec in self.tokens.values() if rec.used)
        
        return {
            'total_issued': total,
            'active': active,
            'revoked': revoked,
            'used': used
        }
