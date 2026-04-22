"""
trajectory_generator.py — Feynman path integral & least action

Euler-Lagrange + RK4 integration
ε calibration: ℏ = 0.015 with ESS-targeting bisection

ACCELERATED: Uses Cython/Mojo backends when available (10-1000x speedup)
"""

import numpy as np
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
import logging

# Accelerated backend integration
try:
    from ..accelerated.backend_selector import get_backend, get_best_backend
    ACCELERATED_AVAILABLE = True
    logger = logging.getLogger(__name__)
    logger.info(f"✓ Accelerated backend: {get_best_backend()}")
except ImportError:
    ACCELERATED_AVAILABLE = False
    logger = logging.getLogger(__name__)
    logger.debug("Accelerated backends not available, using NumPy")


@dataclass
class Trajectory:
    """Candidate trajectory through market state space"""
    id: str
    path: List[Tuple[float, float]]  # (time, price) points
    energy: float
    action: float
    operator_scores: Dict[str, float]
    action_score: float = 0.0
    predicted_pnl: float = 0.0
    
    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "path": self.path,
            "energy": self.energy,
            "action": self.action,
            **self.operator_scores,
            "action_score": self.action_score,
            "predicted_pnl": self.predicted_pnl
        }


class EpsilonCalibrator:
    """
    ℏ calibration via bisection method
    Target: ESS (Effective Sample Size) with ε = 0.015
    """
    
    def __init__(self, target_ess: float = 0.5, epsilon_init: float = 0.015):
        self.target_ess = target_ess
        self.epsilon = epsilon_init
        self.min_epsilon = 0.001
        self.max_epsilon = 0.1
        
    def calibrate(self, trajectories: List[Trajectory]) -> float:
        """Bisection calibration of ℏ parameter"""
        if not trajectories:
            return self.epsilon
            
        low, high = self.min_epsilon, self.max_epsilon
        
        for _ in range(10):  # Max iterations
            mid = (low + high) / 2
            ess = self._compute_ess(trajectories, mid)
            
            if ess < self.target_ess:
                low = mid  # Need wider spread
            else:
                high = mid
                
        self.epsilon = (low + high) / 2
        return self.epsilon
    
    def _compute_ess(self, trajectories: List[Trajectory], epsilon: float) -> float:
        """Compute Effective Sample Size for given ℏ"""
        if not trajectories:
            return 0.0
        
        actions = np.array([t.action for t in trajectories])
        
        # Use accelerated backend if available
        if ACCELERATED_AVAILABLE:
            backend = get_backend()
            return backend.compute_ess(actions, epsilon)
        
        # NumPy fallback
        weights = np.exp(-actions / epsilon)
        
        if weights.sum() == 0:
            return 0.0
        
        normalized = weights / weights.sum()
        ess = 1.0 / (normalized ** 2).sum()
        return ess / len(trajectories)  # Normalize to [0,1]


class PathIntegralOperator:
    """
    Feynman path integral over trajectory families.
    S[q] = ∫L(q,q̇,t)dt — action functional
    """
    
    def __init__(self, calibrator: Optional[EpsilonCalibrator] = None):
        self.calibrator = calibrator or EpsilonCalibrator()
        self.epsilon = self.calibrator.epsilon
        
    def compute_action(self, 
                      path: List[Tuple[float, float]],
                      hamiltonian_values: Dict[str, float]) -> float:
        """
        Compute action S[q] = ∫L dt via discrete sum
        L = T - V (kinetic - potential)
        """
        if len(path) < 2:
            return 0.0
        
        action = 0.0
        dt = 1.0  # Discrete time step
        
        for i in range(1, len(path)):
            t_prev, p_prev = path[i-1]
            t_curr, p_curr = path[i]
            
            # Velocity (q̇)
            velocity = (p_curr - p_prev) / (t_curr - t_prev) if (t_curr - t_prev) > 0 else 0
            
            # Kinetic energy T = ½mv² (m=1)
            kinetic = 0.5 * velocity ** 2
            
            # Potential energy V from Hamiltonian contributions
            potential = sum(hamiltonian_values.values())
            
            # Lagrangian L = T - V
            lagrangian = kinetic - potential
            
            # Action integral
            action += lagrangian * dt
        
        return abs(action)  # Return absolute action
    
    def weight_trajectories(self, 
                           trajectories: List[Trajectory]) -> List[Tuple[Trajectory, float]]:
        """
        Weight trajectories by e^(iS/ℏ) → e^(-S/ℏ) for Wick rotation
        Returns (trajectory, weight) pairs
        """
        weighted = []
        
        for traj in trajectories:
            # Feynman weight: amplitude ∝ exp(iS/ℏ)
            # Euclidean (Wick rotation): exp(-S/ℏ)
            weight = np.exp(-traj.action / self.epsilon)
            weighted.append((traj, weight))
        
        return weighted
    
    def select_least_action(self, 
                           weighted_trajectories: List[Tuple[Trajectory, float]]) -> Optional[Trajectory]:
        """Select trajectory with minimum action (classical limit)"""
        if not weighted_trajectories:
            return None
        
        # Classical limit: highest weight = least action
        best = max(weighted_trajectories, key=lambda x: x[1])
        return best[0]


class LeastActionGenerator:
    """
    Euler-Lagrange equation solver with RK4 integration.
    Generates candidate trajectories from initial conditions.

    T2-A: When a christoffel_func is supplied, initial velocity seeds are
          adjusted using the local geodesic curvature at the starting point
          so trajectories follow geometrically natural directions.

    T2-B: When a christoffel_func is supplied, the RK4 force at each
          sub-step is computed from the live liquidity-field gradient
          (-∂_p ϕ = -Γ^p_pp) plus the geodesic curvature correction,
          replacing the original constant "force" placeholder.
    """

    def __init__(self,
                 n_trajectories: int = 5,
                 n_steps: int = 20,
                 time_horizon: float = 1.0,
                 epsilon: float = 0.015):
        self.n_trajectories = n_trajectories
        self.n_steps = n_steps
        self.dt = time_horizon / n_steps
        self.epsilon = epsilon

    def generate_trajectories(self,
                              initial_state: Dict,
                              market_hamiltonian: Dict[str, float],
                              operator_registry,
                              christoffel_func=None,
                              regime: Optional[str] = None) -> List[Trajectory]:
        """
        Generate candidate trajectory family via RK4 integration.

        Args:
            initial_state: {'price', 'velocity'} starting conditions
            market_hamiltonian: Hamiltonian values dict (used for action scoring)
            operator_registry: ICT operator scorer
            christoffel_func: Optional Γ(price, time) -> ChristoffelSymbols.
                When provided enables T2-A geodesic velocity seeds and
                T2-B time-varying gradient force.
        """
        price = initial_state.get("price", 100.0)
        t0 = 0.0
        base_velocity = initial_state.get("velocity", 0.0)

        # T2-A: geodesic-guided seeds vs uniform perturbations
        if christoffel_func is not None:
            perturbations = self._geodesic_velocity_seeds(
                price, t0, base_velocity, christoffel_func
            )
        else:
            perturbations = list(np.linspace(-0.02, 0.02, self.n_trajectories))

        trajectories = []
        for i, pert in enumerate(perturbations):
            velocity = base_velocity + pert
            state = {"price": price, "velocity": velocity, "time": t0}
            path = self._rk4_integrate(
                state, market_hamiltonian, christoffel_func=christoffel_func
            )

            op_scores = self._compute_operator_scores(path, operator_registry, regime=regime)
            action = self._compute_path_action(path, market_hamiltonian)
            predicted_pnl = (path[-1][1] - path[0][1]) / path[0][1] if path else 0

            traj = Trajectory(
                id=f"traj_{i}_{hash(str(path)) % 10000}",
                path=path,
                energy=self._compute_energy(path, market_hamiltonian),
                action=action,
                operator_scores=op_scores,
                action_score=-action,
                predicted_pnl=predicted_pnl,
            )
            trajectories.append(traj)

        return trajectories

    def _geodesic_velocity_seeds(
        self,
        price: float,
        time: float,
        base_velocity: float,
        christoffel_func,
    ) -> List[float]:
        """
        T2-A: Adjust N initial velocity perturbations using the local geodesic
        curvature tensor at the starting point.

        For each candidate velocity v the geodesic equation gives a
        first-order correction dv = -(Γ^p_pp v² + 2Γ^p_pt v + Γ^p_tt) dt.
        This shifts seeds toward the manifold's natural tangent directions.
        """
        base_perturbs = np.linspace(-0.02, 0.02, self.n_trajectories)
        try:
            G = christoffel_func(price, time)
            seeds = []
            for v_pert in base_perturbs:
                v = base_velocity + v_pert
                # First-order geodesic correction (v_t = 1, physical time param)
                dv = -(G.G_p_pp * v ** 2 + 2.0 * G.G_p_pt * v + G.G_p_tt) * self.dt
                seeds.append(v + dv)
            return seeds
        except Exception:
            return list(base_velocity + base_perturbs)

    def _rk4_integrate(self,
                       initial_state: Dict[str, float],
                       hamiltonian: Dict[str, float],
                       n_steps: int = 50,
                       christoffel_func=None) -> List[Tuple[float, float]]:
        """
        RK4 integration for trajectory generation.

        T2-B: When christoffel_func is provided the acceleration at each
        sub-step combines two physics terms evaluated at the sub-step price:
          1. Potential gradient force:  -Γ^p_pp  (= -∂_p ϕ)
          2. Geodesic curvature:        -(Γ^p_pp v² + 2Γ^p_pt v + Γ^p_tt)
        Together they implement the full geodesic equation with an external
        liquidity-field potential, replacing the constant "force" placeholder.

        Falls back to accelerated backend only when christoffel_func is None
        (backend requires a constant force parameter).
        """
        price = initial_state["price"]
        velocity = initial_state["velocity"]
        time = initial_state.get("time", 0.0)

        # Accelerated backend path — constant force only (no geodesic)
        if ACCELERATED_AVAILABLE and christoffel_func is None:
            backend = get_backend()
            potential_force = hamiltonian.get("force", 0.01)
            path_array = backend.rk4_integrate(
                price, velocity, self.dt, n_steps, potential_force, noise_scale=0.001
            )
            return [(i * self.dt, path_array[i]) for i in range(n_steps)]

        # NumPy path — constant force fallback
        if christoffel_func is None:
            potential_force = hamiltonian.get("force", 0.01)

        path = []
        dt = self.dt

        for _ in range(n_steps):
            if christoffel_func is not None:
                # T2-B: time-varying acceleration from Christoffel symbols.
                # Evaluated freshly at each of the 4 RK4 sub-steps.
                def accel(p: float, t: float, v: float) -> float:
                    G = christoffel_func(p, t)
                    grad_force = -G.G_p_pp                           # -∂_p ϕ
                    curvature = -(G.G_p_pp * v ** 2
                                  + 2.0 * G.G_p_pt * v
                                  + G.G_p_tt)                        # geodesic term
                    return grad_force + curvature

                a0 = accel(price, time, velocity)
                k1_v = a0 * dt
                k1_x = velocity * dt

                a1 = accel(price + 0.5 * k1_x, time + 0.5 * dt, velocity + 0.5 * k1_v)
                k2_v = a1 * dt
                k2_x = (velocity + 0.5 * k1_v) * dt

                a2 = accel(price + 0.5 * k2_x, time + 0.5 * dt, velocity + 0.5 * k2_v)
                k3_v = a2 * dt
                k3_x = (velocity + 0.5 * k2_v) * dt

                a3 = accel(price + k3_x, time + dt, velocity + k3_v)
                k4_v = a3 * dt
                k4_x = (velocity + k3_v) * dt
            else:
                # Original constant-force NumPy fallback
                k1_v = potential_force * dt
                k1_x = velocity * dt
                k2_v = potential_force * dt
                k2_x = (velocity + 0.5 * k1_v) * dt
                k3_v = potential_force * dt
                k3_x = (velocity + 0.5 * k2_v) * dt
                k4_v = potential_force * dt
                k4_x = (velocity + k3_v) * dt

            velocity += (k1_v + 2 * k2_v + 2 * k3_v + k4_v) / 6
            price += (k1_x + 2 * k2_x + 2 * k3_x + k4_x) / 6
            time += dt
            price += np.random.normal(0, abs(0.001 * price))

            path.append((time, price))

        return path
    
    def _compute_operator_scores(self,
                               path: List[Tuple[float, float]],
                               operator_registry,
                               regime: Optional[str] = None) -> Dict[str, float]:
        """Compute ICT operator scores for trajectory"""
        if operator_registry is None:
            return {}
        # Create synthetic market data from path
        prices = [p for _, p in path]
        if not prices:
            return operator_registry.get_all_scores({}, {})

        opens = [prices[0]] + prices[:-1]
        closes = prices[:]
        highs = [max(open_p, close_p) for open_p, close_p in zip(opens, closes)]
        lows = [min(open_p, close_p) for open_p, close_p in zip(opens, closes)]
        volumes = [1000] * len(prices)
        ohlc = [
            {
                "open": open_p,
                "high": high_p,
                "low": low_p,
                "close": close_p,
                "volume": volume,
            }
            for open_p, high_p, low_p, close_p, volume in zip(
                opens, highs, lows, closes, volumes
            )
        ]
        
        market_data = {
            "prices": prices,
            "highs": highs,
            "lows": lows,
            "opens": opens,
            "closes": closes,
            "close": closes[-1],
            "volumes": volumes,
            "volume": volumes,
            "ohlc": ohlc,
        }
        
        # T2-D: inject regime-based sailing-lane alpha
        op_state: Dict = {}
        if regime is not None:
            try:
                from ..operators.operator_registry import OperatorRegistry
                op_state["sailing_alpha"] = OperatorRegistry.sailing_alpha_from_regime(regime)
            except Exception:
                pass
        return operator_registry.get_all_scores(market_data, op_state)
    
    def _compute_path_action(self,
                           path: List[Tuple[float, float]],
                           hamiltonian: Dict[str, float]) -> float:
        """Compute action S = ∫L dt for path"""
        action = 0.0
        potential = sum(hamiltonian.values())
        
        for i in range(1, len(path)):
            dt = path[i][0] - path[i-1][0]
            dx = path[i][1] - path[i-1][1]
            velocity = dx / dt if dt > 0 else 0
            
            kinetic = 0.5 * velocity ** 2
            lagrangian = kinetic - potential
            action += lagrangian * dt
        
        return abs(action)
    
    def _compute_energy(self,
                       path: List[Tuple[float, float]],
                       hamiltonian: Dict[str, float]) -> float:
        """Compute total energy E = T + V along path"""
        if len(path) < 2:
            return sum(hamiltonian.values())
        
        energies = []
        potential = sum(hamiltonian.values())
        
        for i in range(1, len(path)):
            dt = path[i][0] - path[i-1][0]
            dx = path[i][1] - path[i-1][1]
            velocity = dx / dt if dt > 0 else 0
            kinetic = 0.5 * velocity ** 2
            energies.append(kinetic + abs(potential))
        
        return np.mean(energies) if energies else 0.0


class MemoryAugmentedGenerator:
    """
    Trajectory generator with pattern memory (RAG-style retrieval).
    
    Retrieves similar historical patterns to bias trajectory generation.
    """
    
    def __init__(self,
                 base_generator: Optional[LeastActionGenerator] = None,
                 embedder=None,
                 vector_store=None,
                 memory_bias_strength: float = 0.3):
        self.generator = base_generator or LeastActionGenerator()
        self.memory_bias_strength = memory_bias_strength
        
        # Lazy import to avoid circular dependencies
        self._embedder = embedder
        self._vector_store = vector_store
    
    @property
    def embedder(self):
        if self._embedder is None:
            from ..memory import get_embedder
            self._embedder = get_embedder()
        return self._embedder
    
    @property
    def vector_store(self):
        if self._vector_store is None:
            from ..memory import get_vector_store
            self._vector_store = get_vector_store()
        return self._vector_store
    
    def generate_trajectories(self,
                             initial_state: Dict,
                             market_hamiltonian: Dict[str, float],
                             operator_registry,
                             ohlcv_data: Optional[List[Dict]] = None,
                             symbol: str = "UNKNOWN",
                             timeframe: str = "1h") -> List[Trajectory]:
        """
        Generate trajectories with memory-augmented bias.
        
        Args:
            initial_state: Current market state
            market_hamiltonian: Hamiltonian values
            operator_registry: Operator scoring
            ohlcv_data: OHLCV for embedding (optional)
            symbol: Trading symbol
            timeframe: Candle timeframe
        
        Returns:
            List of Trajectory objects with memory_bias attribute
        """
        # Generate base trajectories
        trajectories = self.generator.generate_trajectories(
            initial_state, market_hamiltonian, operator_registry
        )
        
        # If no OHLCV data, return unmodified trajectories
        if not ohlcv_data:
            for traj in trajectories:
                traj.memory_bias = 1.0
                traj.similar_patterns = []
            return trajectories
        
        try:
            # Encode market state
            embedding = self.embedder.encode(ohlcv_data)
            
            # Query similar patterns
            similar = self.vector_store.query_similar(
                embedding,
                symbol=symbol,
                timeframe=timeframe,
                top_k=10,
                min_similarity=0.7
            )
            
            # Compute memory bias
            biases = self.vector_store.compute_memory_bias(
                trajectories,
                similar,
                bias_strength=self.memory_bias_strength
            )
            
            # Apply bias to trajectories
            for traj in trajectories:
                traj_id = traj.id
                bias = biases.get(traj_id, 1.0)
                traj.memory_bias = bias
                traj.similar_patterns = [
                    {
                        'pattern_id': m.pattern_id,
                        'similarity': m.market_summary.get('similarity', 0),
                        'best_pnl': m.best_pnl,
                        'win_rate': m.win_rate
                    }
                    for m in similar[:3]  # Top 3 for metadata
                ]
                
                # Modify action score by memory bias
                # Higher bias (from successful similar patterns) = better action score
                traj.action_score = traj.action_score * bias
            
            logger.debug(f"Applied memory bias to {len(trajectories)} trajectories "
                        f"(retrieved {len(similar)} similar patterns)")
            
        except Exception as e:
            logger.warning(f"Memory augmentation failed: {e}, using unmodified trajectories")
            for traj in trajectories:
                traj.memory_bias = 1.0
                traj.similar_patterns = []
        
        return trajectories
    
    def store_pattern_outcome(self,
                             ohlcv_data: List[Dict],
                             symbol: str,
                             timeframe: str,
                             trajectories: List[Trajectory],
                             evidence_hash: str = "") -> Optional[str]:
        """
        Store pattern with trajectory outcomes for future retrieval.
        
        Call this after scheduler collapse to store results.
        """
        try:
            embedding = self.embedder.encode(ohlcv_data)
            
            # Convert trajectories to storage format
            traj_outcomes = []
            for traj in trajectories:
                traj_outcomes.append({
                    'trajectory_id': traj.id,
                    'pnl': getattr(traj, 'realized_pnl', traj.predicted_pnl),
                    'success': getattr(traj, 'realized_pnl', 0) > 0,
                    'operators_used': list(traj.operator_scores.keys()),
                    'action': traj.action,
                    'memory_bias': getattr(traj, 'memory_bias', 1.0)
                })
            
            # Market summary
            closes = [c['close'] for c in ohlcv_data]
            market_summary = {
                'trend': (closes[-1] - closes[0]) / closes[0] if closes[0] != 0 else 0,
                'volatility': np.std(closes) / np.mean(closes) if closes else 0,
                'candle_count': len(ohlcv_data)
            }
            
            pattern_id = self.vector_store.store_pattern(
                embedding=embedding,
                symbol=symbol,
                timeframe=timeframe,
                trajectories=traj_outcomes,
                market_summary=market_summary,
                evidence_hash=evidence_hash
            )
            
            logger.debug(f"Stored pattern {pattern_id} for {symbol}")
            return pattern_id
            
        except Exception as e:
            logger.error(f"Failed to store pattern: {e}")
            return None


class PathIntegralEngine:
    """Complete path integral engine: generation + weighting + selection"""
    
    def __init__(self, use_memory: bool = False):
        self.generator = LeastActionGenerator()
        self.integral = PathIntegralOperator()
        self.calibrator = EpsilonCalibrator()
        
        # Optional memory augmentation
        self.use_memory = use_memory
        self.memory_generator = None
        if use_memory:
            self.memory_generator = MemoryAugmentedGenerator(
                base_generator=self.generator
            )
        
    def execute_path_integral(self,
                             initial_state: Dict,
                             hamiltonian: Dict[str, float],
                             operator_registry,
                             ohlcv_data: Optional[List[Dict]] = None,
                             symbol: str = "UNKNOWN",
                             timeframe: str = "1h") -> Dict:
        """
        Full path integral execution:
        1. Generate trajectories (with optional memory bias)
        2. Compute actions
        3. Calibrate ℏ
        4. Weight trajectories
        5. Return results
        
        Args:
            initial_state: Current market state
            hamiltonian: Hamiltonian values
            operator_registry: Operator scoring
            ohlcv_data: OHLCV for embedding (optional, required for memory)
            symbol: Trading symbol
            timeframe: Candle timeframe
        """
        # Generate trajectory family (with memory if enabled)
        if self.use_memory and self.memory_generator and ohlcv_data:
            trajectories = self.memory_generator.generate_trajectories(
                initial_state, hamiltonian, operator_registry,
                ohlcv_data=ohlcv_data, symbol=symbol, timeframe=timeframe
            )
        else:
            trajectories = self.generator.generate_trajectories(
                initial_state, hamiltonian, operator_registry
            )
            for traj in trajectories:
                traj.memory_bias = 1.0
                traj.similar_patterns = []
        
        # Calibrate ℏ
        epsilon = self.calibrator.calibrate(trajectories)
        self.integral.epsilon = epsilon
        
        # Weight trajectories
        weighted = self.integral.weight_trajectories(trajectories)
        
        # Select least action
        best = self.integral.select_least_action(weighted)
        
        return {
            "trajectories": [t.to_dict() for t in trajectories],
            "trajectory_count": len(trajectories),
            "epsilon": epsilon,
            "best_trajectory": best.to_dict() if best else None,
            "hamiltonian": hamiltonian,
            "memory_augmented": self.use_memory,
            "similar_patterns": getattr(best, 'similar_patterns', []) if best else []
        }
    
    def store_execution_outcome(self,
                               ohlcv_data: List[Dict],
                               symbol: str,
                               timeframe: str,
                               trajectories: List[Trajectory],
                               evidence_hash: str = "") -> Optional[str]:
        """
        Store pattern outcome after execution for memory learning.
        Call this after the scheduler collapse and trade execution.
        """
        if self.memory_generator:
            return self.memory_generator.store_pattern_outcome(
                ohlcv_data, symbol, timeframe, trajectories, evidence_hash
            )
        return None
