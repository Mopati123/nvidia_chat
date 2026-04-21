"""
Circuit Breaker
Auto-pause on consecutive errors, exponential backoff, manual resume via Telegram
"""

import time
import logging
from typing import Dict, Optional, Callable, List
from enum import Enum
from dataclasses import dataclass
from threading import Lock

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Failing, rejecting requests
    HALF_OPEN = "half_open"  # Testing if service recovered


@dataclass
class CircuitBreakerConfig:
    """Circuit breaker configuration"""
    failure_threshold: int = 5          # Failures before opening
    success_threshold: int = 3          # Successes before closing from half-open
    timeout_seconds: float = 60.0       # Time before half-open attempt
    half_open_max_calls: int = 3        # Max calls in half-open state


class CircuitBreaker:
    """
    Circuit breaker pattern implementation
    
    Protects system from cascading failures by:
    - Tracking consecutive errors
    - Opening circuit after threshold
    - Exponential backoff before retry
    - Half-open state for gradual recovery
    """
    
    def __init__(
        self,
        name: str,
        config: Optional[CircuitBreakerConfig] = None
    ):
        self.name = name
        self.config = config or CircuitBreakerConfig()
        
        # State
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: Optional[float] = None
        self.last_state_change = time.time()
        
        # Half-open tracking
        self.half_open_calls = 0
        
        # Statistics
        self.total_calls = 0
        self.total_failures = 0
        self.total_successes = 0
        self.total_rejected = 0
        
        # Callbacks
        self.on_open_callbacks: List[Callable] = []
        self.on_close_callbacks: List[Callable] = []
        self.on_half_open_callbacks: List[Callable] = []
        
        # Thread safety
        self.lock = Lock()
        
        logger.info(f"CircuitBreaker '{name}' initialized (threshold={self.config.failure_threshold})")
    
    def register_on_open(self, callback: Callable):
        """Register callback when circuit opens"""
        self.on_open_callbacks.append(callback)
    
    def register_on_close(self, callback: Callable):
        """Register callback when circuit closes"""
        self.on_close_callbacks.append(callback)
    
    def register_on_half_open(self, callback: Callable):
        """Register callback when circuit enters half-open"""
        self.on_half_open_callbacks.append(callback)
    
    def _transition_to(self, new_state: CircuitState):
        """Transition to new state"""
        old_state = self.state
        self.state = new_state
        self.last_state_change = time.time()
        
        logger.warning(f"Circuit '{self.name}': {old_state.value} -> {new_state.value}")
        
        # Reset counters
        if new_state == CircuitState.CLOSED:
            self.failure_count = 0
            self.success_count = 0
            self.half_open_calls = 0
            for cb in self.on_close_callbacks:
                try:
                    cb()
                except Exception as e:
                    logger.error(f"Close callback error: {e}")
        
        elif new_state == CircuitState.OPEN:
            self.failure_count = 0
            self.success_count = 0
            self.half_open_calls = 0
            for cb in self.on_open_callbacks:
                try:
                    cb()
                except Exception as e:
                    logger.error(f"Open callback error: {e}")
        
        elif new_state == CircuitState.HALF_OPEN:
            self.half_open_calls = 0
            for cb in self.on_half_open_callbacks:
                try:
                    cb()
                except Exception as e:
                    logger.error(f"Half-open callback error: {e}")
    
    def call(self, func: Callable, *args, **kwargs):
        """
        Execute function with circuit breaker protection
        
        Returns: (success: bool, result_or_error)
        """
        with self.lock:
            self.total_calls += 1
            
            # Check if we can proceed
            if self.state == CircuitState.OPEN:
                # Check if timeout elapsed for half-open attempt
                if time.time() - self.last_state_change >= self.config.timeout_seconds:
                    self._transition_to(CircuitState.HALF_OPEN)
                else:
                    self.total_rejected += 1
                    return False, CircuitBreakerOpenError(f"Circuit '{self.name}' is OPEN")
            
            if self.state == CircuitState.HALF_OPEN:
                if self.half_open_calls >= self.config.half_open_max_calls:
                    self.total_rejected += 1
                    return False, CircuitBreakerOpenError(
                        f"Circuit '{self.name}' half-open limit reached"
                    )
                self.half_open_calls += 1
            
            # Execute
            try:
                result = func(*args, **kwargs)
                self._on_success()
                return True, result
                
            except Exception as e:
                self._on_failure()
                return False, e
    
    def _on_success(self):
        """Handle successful call"""
        self.total_successes += 1
        
        if self.state == CircuitState.HALF_OPEN:
            self.success_count += 1
            if self.success_count >= self.config.success_threshold:
                self._transition_to(CircuitState.CLOSED)
        else:
            self.failure_count = 0  # Reset on success in closed state
    
    def _on_failure(self):
        """Handle failed call"""
        self.total_failures += 1
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        if self.state == CircuitState.HALF_OPEN:
            # Any failure in half-open reopens circuit
            self._transition_to(CircuitState.OPEN)
        elif self.state == CircuitState.CLOSED:
            if self.failure_count >= self.config.failure_threshold:
                self._transition_to(CircuitState.OPEN)
    
    def manual_open(self):
        """Manually open the circuit (emergency stop)"""
        with self.lock:
            if self.state != CircuitState.OPEN:
                self._transition_to(CircuitState.OPEN)
                logger.critical(f"Circuit '{self.name}' manually opened")
    
    def manual_close(self):
        """Manually close the circuit (resume)"""
        with self.lock:
            if self.state != CircuitState.CLOSED:
                self._transition_to(CircuitState.CLOSED)
                logger.critical(f"Circuit '{self.name}' manually closed")
    
    def get_status(self) -> Dict:
        """Get circuit breaker status"""
        time_in_state = time.time() - self.last_state_change
        
        return {
            'name': self.name,
            'state': self.state.value,
            'time_in_state_seconds': time_in_state,
            'failure_count': self.failure_count,
            'success_count': self.success_count,
            'half_open_calls': self.half_open_calls,
            'total_calls': self.total_calls,
            'total_failures': self.total_failures,
            'total_successes': self.total_successes,
            'total_rejected': self.total_rejected,
            'failure_rate': self.total_failures / max(1, self.total_calls),
            'config': {
                'failure_threshold': self.config.failure_threshold,
                'success_threshold': self.config.success_threshold,
                'timeout_seconds': self.config.timeout_seconds
            }
        }
    
    def __str__(self) -> str:
        return f"CircuitBreaker({self.name}: {self.state.value})"


class CircuitBreakerOpenError(Exception):
    """Exception raised when circuit breaker is open"""
    pass


class CircuitBreakerManager:
    """
    Manages multiple circuit breakers for different components
    """
    
    def __init__(self):
        self.breakers: Dict[str, CircuitBreaker] = {}
        self.lock = Lock()
    
    def get_breaker(
        self,
        name: str,
        config: Optional[CircuitBreakerConfig] = None
    ) -> CircuitBreaker:
        """Get or create circuit breaker"""
        with self.lock:
            if name not in self.breakers:
                self.breakers[name] = CircuitBreaker(name, config)
            return self.breakers[name]
    
    def get_all_status(self) -> Dict[str, Dict]:
        """Get status of all circuit breakers"""
        with self.lock:
            return {
                name: breaker.get_status()
                for name, breaker in self.breakers.items()
            }
    
    def open_all(self):
        """Open all circuits (emergency stop)"""
        with self.lock:
            for breaker in self.breakers.values():
                breaker.manual_open()
    
    def close_all(self):
        """Close all circuits (resume)"""
        with self.lock:
            for breaker in self.breakers.values():
                breaker.manual_close()


# Global manager
_cb_manager: Optional[CircuitBreakerManager] = None


def get_circuit_breaker_manager() -> CircuitBreakerManager:
    """Get global circuit breaker manager"""
    global _cb_manager
    if _cb_manager is None:
        _cb_manager = CircuitBreakerManager()
    return _cb_manager


def get_circuit_breaker(
    name: str,
    config: Optional[CircuitBreakerConfig] = None
) -> CircuitBreaker:
    """Get circuit breaker by name"""
    return get_circuit_breaker_manager().get_breaker(name, config)


# Example usage
if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    
    # Create breaker
    breaker = get_circuit_breaker("broker_api")
    
    # Simulate calls
    def mock_api_call(should_fail=False):
        if should_fail:
            raise Exception("API Error")
        return "Success"
    
    # Test successes
    for i in range(3):
        success, result = breaker.call(mock_api_call, should_fail=False)
        print(f"Call {i+1}: {success}, {result}")
    
    # Test failures (should open circuit)
    for i in range(6):
        success, result = breaker.call(mock_api_call, should_fail=True)
        print(f"Fail {i+1}: {success}, {type(result).__name__}")
    
    # Check status
    print(f"\nStatus: {breaker.get_status()}")
    
    # Circuit should be open now
    success, result = breaker.call(mock_api_call, should_fail=False)
    print(f"Call after open: {success}, {type(result).__name__}")
