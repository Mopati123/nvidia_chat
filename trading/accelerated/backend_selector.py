"""
backend_selector.py — Tiered acceleration backend selector

Automatically selects fastest available backend:
1. Mojo (100-1000x) — AI-native, fastest
2. Cython (10-100x) — Compiled C extensions
3. Numba (2-10x) — JIT compilation (optional fallback)
4. NumPy (baseline) — Standard vectorized operations

Usage:
    from trading.accelerated.backend_selector import get_backend
    
    backend = get_backend()
    result = backend.rk4_integrate(...)
"""

import logging
import numpy as np
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Backend availability flags
_backend_status = {
    'mojo': False,
    'cython_path_integral': False,
    'cython_operators': False,
    'numba': False,
    'numpy': True,  # Always available
}

# Import Mojo bridge
try:
    from .mojo_bridge import mojo_bridge, MOJO_AVAILABLE
    _backend_status['mojo'] = MOJO_AVAILABLE
except ImportError:
    pass

# Import Cython modules
try:
    from . import _path_integral as cy_path
    _backend_status['cython_path_integral'] = True
    logger.info("✓ Cython path integral loaded")
except ImportError:
    cy_path = None

try:
    from . import _operators as cy_ops
    _backend_status['cython_operators'] = True
    logger.info("✓ Cython operators loaded")
except ImportError:
    cy_ops = None

# Numba (optional JIT fallback)
try:
    from numba import jit, njit, prange
    _backend_status['numba'] = True
    logger.info("✓ Numba JIT available")
    
    @njit(cache=True, fastmath=True)
    def numba_rk4_integrate(initial_price, velocity, dt, n_steps, force, noise):
        """Numba-compiled RK4 for fallback"""
        path = np.zeros(n_steps)
        price = initial_price
        vel = velocity
        
        for i in range(n_steps):
            # RK4 steps
            k1_v = force * dt
            k1_x = vel * dt
            
            k2_v = force * dt
            k2_x = (vel + 0.5 * k1_v) * dt
            
            k3_v = force * dt
            k3_x = (vel + 0.5 * k2_v) * dt
            
            k4_v = force * dt
            k4_x = (vel + k3_v) * dt
            
            vel += (k1_v + 2*k2_v + 2*k3_v + k4_v) / 6
            price += (k1_x + 2*k2_x + 2*k3_x + k4_x) / 6
            
            if noise > 0:
                price += np.random.normal(0, noise * price)
            
            path[i] = price
        
        return path
    
except ImportError:
    numba_rk4_integrate = None


@dataclass
class BackendCapabilities:
    """Describes what a backend can do"""
    name: str
    speedup: float
    supports_trajectories: bool
    supports_operators: bool
    supports_parallel: bool
    available: bool


def get_backend_status() -> Dict[str, bool]:
    """Get availability of all backends"""
    return _backend_status.copy()


def get_best_backend() -> str:
    """Return name of best available backend"""
    if _backend_status['mojo']:
        return 'mojo'
    elif _backend_status['cython_path_integral']:
        return 'cython'
    elif _backend_status['numba']:
        return 'numba'
    else:
        return 'numpy'


def get_backend_capabilities() -> List[BackendCapabilities]:
    """Get detailed capabilities of each backend"""
    return [
        BackendCapabilities(
            name='mojo',
            speedup=1000.0,
            supports_trajectories=True,
            supports_operators=True,
            supports_parallel=True,
            available=_backend_status['mojo']
        ),
        BackendCapabilities(
            name='cython',
            speedup=100.0,
            supports_trajectories=True,
            supports_operators=True,
            supports_parallel=False,
            available=_backend_status['cython_path_integral']
        ),
        BackendCapabilities(
            name='numba',
            speedup=10.0,
            supports_trajectories=True,
            supports_operators=False,
            supports_parallel=True,
            available=_backend_status['numba']
        ),
        BackendCapabilities(
            name='numpy',
            speedup=1.0,
            supports_trajectories=True,
            supports_operators=True,
            supports_parallel=False,
            available=True
        ),
    ]


class AcceleratedBackend:
    """
    Unified interface to all acceleration backends.
    
    Automatically selects best available backend for each operation.
    """
    
    def __init__(self, preferred: Optional[str] = None):
        self.preferred = preferred or get_best_backend()
        self.logger = logging.getLogger(__name__)
        
    def _log_backend(self, operation: str, backend: str):
        """Log which backend is being used"""
        self.logger.debug(f"Using {backend} backend for {operation}")
    
    def rk4_integrate(
        self,
        initial_price: float,
        initial_velocity: float,
        dt: float,
        n_steps: int,
        potential_force: float,
        noise_scale: float = 0.0
    ) -> np.ndarray:
        """
        RK4 integration with automatic backend selection.
        
        Returns: np.ndarray of price path
        """
        # Try backends in order of preference
        if self.preferred == 'mojo' and _backend_status['mojo']:
            result = mojo_bridge.generate_trajectories(
                initial_price, initial_velocity, potential_force,
                n_trajectories=1, n_steps=n_steps
            )
            if result:
                self._log_backend('rk4', 'mojo')
                return np.array(result.get('path', []))
        
        if self.preferred == 'cython' and cy_path is not None:
            self._log_backend('rk4', 'cython')
            return cy_path.rk4_integrate_1d(
                initial_price, initial_velocity, dt, n_steps,
                potential_force, noise_scale
            )
        
        if _backend_status['numba'] and numba_rk4_integrate is not None:
            self._log_backend('rk4', 'numba')
            return numba_rk4_integrate(
                initial_price, initial_velocity, dt, n_steps,
                potential_force, noise_scale
            )
        
        # NumPy fallback
        self._log_backend('rk4', 'numpy')
        return self._rk4_numpy(
            initial_price, initial_velocity, dt, n_steps,
            potential_force, noise_scale
        )
    
    def _rk4_numpy(
        self, price, velocity, dt, n_steps, force, noise
    ) -> np.ndarray:
        """NumPy fallback RK4 implementation"""
        path = np.zeros(n_steps)
        
        for i in range(n_steps):
            k1_v = force * dt
            k1_x = velocity * dt
            
            k2_v = force * dt
            k2_x = (velocity + 0.5 * k1_v) * dt
            
            k3_v = force * dt
            k3_x = (velocity + 0.5 * k2_v) * dt
            
            k4_v = force * dt
            k4_x = (velocity + k3_v) * dt
            
            velocity += (k1_v + 2*k2_v + 2*k3_v + k4_v) / 6
            price += (k1_x + 2*k2_x + 2*k3_x + k4_x) / 6
            
            if noise > 0:
                price += np.random.normal(0, noise * abs(price))
            
            path[i] = price
        
        return path
    
    def compute_action_batch(
        self,
        paths: np.ndarray,
        hamiltonian_values: np.ndarray,
        epsilon: float
    ) -> np.ndarray:
        """
        Compute action for multiple paths.
        
        Returns: np.ndarray of action values
        """
        if cy_path is not None:
            self._log_backend('action_batch', 'cython')
            return cy_path.compute_action_batch(paths, hamiltonian_values, epsilon)
        
        # NumPy fallback
        self._log_backend('action_batch', 'numpy')
        return self._action_numpy(paths, hamiltonian_values)
    
    def _action_numpy(
        self, paths: np.ndarray, hamiltonian: np.ndarray
    ) -> np.ndarray:
        """NumPy action computation"""
        n_paths, n_steps = paths.shape
        actions = np.zeros(n_paths)
        
        for i in range(n_paths):
            action = 0.0
            for j in range(n_steps - 1):
                dt = 1.0
                dx = paths[i, j+1] - paths[i, j]
                kinetic = 0.5 * dx * dx / (dt * dt)
                potential = hamiltonian[i]
                lagrangian = kinetic - potential
                action += lagrangian * dt
            actions[i] = action
        
        return actions
    
    def compute_ess(self, actions: np.ndarray, epsilon: float) -> float:
        """
        Compute Effective Sample Size.
        
        Returns: ESS value [0, 1]
        """
        if cy_path is not None:
            self._log_backend('ess', 'cython')
            return cy_path.compute_ess(actions, epsilon)
        
        # NumPy fallback
        self._log_backend('ess', 'numpy')
        weights = np.exp(-actions / epsilon)
        total = weights.sum()
        if total == 0:
            return 0.0
        normalized = weights / total
        ess = 1.0 / (normalized ** 2).sum()
        return ess / len(actions)
    
    def compute_hamiltonian_fast(
        self,
        prices: np.ndarray,
        highs: np.ndarray,
        lows: np.ndarray,
        opens: np.ndarray,
        closes: np.ndarray,
        volumes: np.ndarray,
        weights: Optional[np.ndarray] = None
    ) -> float:
        """
        Compute market Hamiltonian H = Σ α_k * O_k.
        
        Returns: Total Hamiltonian energy
        """
        if weights is None:
            weights = np.ones(18) / 18
        
        if cy_ops is not None:
            self._log_backend('hamiltonian', 'cython')
            return cy_ops.compute_hamiltonian_fast(
                prices, highs, lows, opens, closes,
                volumes.astype(np.int32), weights
            )
        
        # NumPy fallback (simplified)
        self._log_backend('hamiltonian', 'numpy')
        kinetic = 0.5 * np.diff(prices) ** 2
        return weights[0] * kinetic.mean() if len(kinetic) > 0 else 0.0
    
    def calibrate_epsilon(
        self,
        actions: np.ndarray,
        target_ess: float = 0.5,
        min_epsilon: float = 0.001,
        max_epsilon: float = 0.1,
        max_iterations: int = 10
    ) -> float:
        """
        Calibrate epsilon using bisection.
        
        Returns: Calibrated epsilon value
        """
        if cy_path is not None:
            self._log_backend('calibrate', 'cython')
            return cy_path.calibrate_epsilon(
                actions, target_ess, min_epsilon, max_epsilon, max_iterations
            )
        
        # NumPy fallback
        self._log_backend('calibrate', 'numpy')
        low, high = min_epsilon, max_epsilon
        
        for _ in range(max_iterations):
            mid = (low + high) / 2
            ess = self.compute_ess(actions, mid)
            if ess < target_ess:
                low = mid
            else:
                high = mid
        
        return (low + high) / 2


# Singleton instance
backend = AcceleratedBackend()


def get_backend(preferred: Optional[str] = None) -> AcceleratedBackend:
    """Get backend instance (singleton)"""
    global backend
    if preferred and preferred != backend.preferred:
        backend = AcceleratedBackend(preferred)
    return backend


def benchmark_backends() -> Dict[str, float]:
    """
    Benchmark all available backends.
    
    Returns: Dict of backend name -> speedup factor
    """
    import time
    
    # Test parameters
    initial_price = 1.0850
    velocity = 0.0
    dt = 0.1
    n_steps = 100
    force = 0.01
    noise = 0.001
    
    results = {}
    
    # Test each backend
    for backend_name in ['cython', 'numba', 'numpy']:
        try:
            b = AcceleratedBackend(backend_name)
            
            # Warmup
            for _ in range(5):
                b.rk4_integrate(initial_price, velocity, dt, 10, force, noise)
            
            # Benchmark
            start = time.perf_counter()
            for _ in range(100):
                b.rk4_integrate(initial_price, velocity, dt, n_steps, force, noise)
            elapsed = time.perf_counter() - start
            
            results[backend_name] = elapsed
            
        except Exception as e:
            results[backend_name] = float('inf')
            logger.warning(f"{backend_name} benchmark failed: {e}")
    
    # Calculate speedups relative to numpy
    baseline = results.get('numpy', 1.0)
    speedups = {
        name: baseline / time if time > 0 else 0
        for name, time in results.items()
    }
    
    return speedups
