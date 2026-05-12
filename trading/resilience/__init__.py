"""
Resilience Package

Error recovery and fault tolerance for trading system.
"""

from trading.resilience.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerManager,
    CircuitState,
    get_circuit_breaker,
    get_circuit_breaker_manager
)

from trading.resilience.checkpoints import (
    Checkpoint,
    load_checkpoint,
    persist_checkpoint,
    stable_payload_hash,
)

from trading.resilience.state_recovery import (
    StateRecovery,
    SystemState,
    get_state_recovery,
    graceful_shutdown_handler
)

__all__ = [
    'CircuitBreaker',
    'CircuitBreakerConfig',
    'CircuitBreakerManager',
    'CircuitState',
    'Checkpoint',
    'StateRecovery',
    'SystemState',
    'get_circuit_breaker',
    'get_circuit_breaker_manager',
    'get_state_recovery',
    'graceful_shutdown_handler',
    'load_checkpoint',
    'persist_checkpoint',
    'stable_payload_hash',
]
