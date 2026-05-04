"""Thread-safe token ownership and concurrency control for scheduler collapse."""

from __future__ import annotations

import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from threading import Lock
from typing import Any, Dict, Iterator, Optional, Union


@dataclass
class AuthorityToken:
    """Authority lease that gates one scheduler-authorized operation."""

    token_id: str
    owner: str
    budget: float
    issued_at: float
    metadata: Dict[str, Any] = field(default_factory=dict)

    def consume(self, amount: float) -> bool:
        """Consume budget from this authority lease if sufficient budget exists."""
        amount = float(amount)
        if amount < 0:
            return False
        if amount > self.budget:
            return False
        self.budget -= amount
        return True


class TokenAuthority:
    """Central authority for active scheduler token ownership."""

    def __init__(self, max_active_tokens: int = 1, default_budget: float = 1.0) -> None:
        if max_active_tokens < 1:
            raise ValueError("max_active_tokens must be at least 1")
        self.max_active_tokens = int(max_active_tokens)
        self.default_budget = float(default_budget)
        self._lock = Lock()
        self._active_tokens: Dict[str, AuthorityToken] = {}

    @property
    def active_count(self) -> int:
        """Return the number of currently active authority leases."""
        with self._lock:
            return len(self._active_tokens)

    def active_tokens(self) -> Dict[str, AuthorityToken]:
        """Return a snapshot of active authority leases keyed by token id."""
        with self._lock:
            return dict(self._active_tokens)

    def issue_token(
        self,
        owner: str,
        budget: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[AuthorityToken]:
        """Issue an authority lease if concurrency capacity is available."""
        with self._lock:
            if len(self._active_tokens) >= self.max_active_tokens:
                return None
            token = AuthorityToken(
                token_id=uuid.uuid4().hex,
                owner=str(owner),
                budget=float(self.default_budget if budget is None else budget),
                issued_at=time.time(),
                metadata=dict(metadata or {}),
            )
            self._active_tokens[token.token_id] = token
            return token

    def get_token(self, token_id: str) -> Optional[AuthorityToken]:
        """Look up an active authority lease by token id."""
        with self._lock:
            return self._active_tokens.get(token_id)

    def release_token(self, token_or_id: Optional[Union[AuthorityToken, str]]) -> None:
        """Release a lease by token object or id. Missing tokens are ignored."""
        if token_or_id is None:
            return
        token_id = token_or_id if isinstance(token_or_id, str) else token_or_id.token_id
        with self._lock:
            self._active_tokens.pop(token_id, None)

    def release_all(self) -> None:
        """Release every active lease owned by this authority."""
        with self._lock:
            self._active_tokens.clear()

    @contextmanager
    def acquire_token(
        self,
        owner: str,
        budget: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Iterator[Optional[AuthorityToken]]:
        """Context manager that releases a token even when work raises."""
        token = self.issue_token(owner=owner, budget=budget, metadata=metadata)
        try:
            yield token
        finally:
            self.release_token(token)
