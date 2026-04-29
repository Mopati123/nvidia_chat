"""Collapse authority leases for scheduler-owned execution control.

The scheduler already mints the cryptographic ExecutionToken used by the
engine.  This module adds a smaller internal primitive: a lease that limits
how many collapses may be active and how much collapse budget may be reserved
at once.  Leases are released after execution or at epoch cleanup.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from threading import Lock
from typing import Dict, Optional


@dataclass
class AuthorityLease:
    """Short-lived internal lease that reserves collapse capacity and budget."""

    lease_id: str
    budget_allocated: float
    budget_remaining: float
    issued_at: float
    released: bool = False

    def consume(self, amount: float) -> bool:
        """Consume part of the reserved budget if enough remains."""
        if amount < 0:
            return False
        if amount > self.budget_remaining:
            return False
        self.budget_remaining -= amount
        return True


class TokenAuthority:
    """Thread-safe authority for active collapse leases.

    This is deliberately separate from the public scheduler ExecutionToken.
    It acts like a bounded semaphore plus budget pool: the scheduler must
    acquire a lease before minting an execution token, and release it when the
    engine is done with the authorized collapse.
    """

    def __init__(
        self,
        max_active_tokens: int = 1,
        default_budget: float = 1.0,
        total_budget: Optional[float] = None,
    ) -> None:
        if max_active_tokens < 1:
            raise ValueError("max_active_tokens must be at least 1")
        if default_budget < 0:
            raise ValueError("default_budget must be non-negative")

        self.max_active_tokens = int(max_active_tokens)
        self.default_budget = float(default_budget)
        self.total_budget = (
            float(total_budget)
            if total_budget is not None
            else self.default_budget * self.max_active_tokens
        )
        if self.total_budget < 0:
            raise ValueError("total_budget must be non-negative")

        self._lock = Lock()
        self._active_leases: Dict[str, AuthorityLease] = {}
        self._budget_available = self.total_budget

    @property
    def active_count(self) -> int:
        """Number of active, unreleased leases."""
        with self._lock:
            return len(self._active_leases)

    @property
    def budget_available(self) -> float:
        """Currently unreserved budget in the authority pool."""
        with self._lock:
            return self._budget_available

    def acquire_lease(self, budget: Optional[float] = None) -> Optional[AuthorityLease]:
        """Reserve collapse capacity and budget, or return None on refusal."""
        requested = self.default_budget if budget is None else float(budget)
        if requested < 0:
            return None

        with self._lock:
            if len(self._active_leases) >= self.max_active_tokens:
                return None
            if requested > self.default_budget:
                return None
            if requested > self._budget_available:
                return None

            lease = AuthorityLease(
                lease_id=str(uuid.uuid4()),
                budget_allocated=requested,
                budget_remaining=requested,
                issued_at=time.time(),
            )
            self._active_leases[lease.lease_id] = lease
            self._budget_available -= requested
            return lease

    def get_lease(self, lease_id: str) -> Optional[AuthorityLease]:
        """Look up an active lease by ID."""
        with self._lock:
            return self._active_leases.get(lease_id)

    def release_lease(self, lease: AuthorityLease) -> bool:
        """Release a lease and return unused budget to the authority pool."""
        with self._lock:
            active = self._active_leases.pop(lease.lease_id, None)
            if active is None:
                return False
            active.released = True
            self._budget_available = min(
                self.total_budget,
                self._budget_available + active.budget_remaining,
            )
            return True

    def release_all(self) -> int:
        """Release every active lease and reset available budget."""
        with self._lock:
            released = len(self._active_leases)
            for lease in self._active_leases.values():
                lease.released = True
            self._active_leases.clear()
            self._budget_available = self.total_budget
            return released

