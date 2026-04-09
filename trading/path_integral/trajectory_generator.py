"""
trajectory_generator.py — Feynman path integral & least action

Euler-Lagrange + RK4 integration
ε calibration: ℏ = 0.015 with ESS-targeting bisection
"""

import numpy as np
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass


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
            
        actions = [t.action for t in trajectories]
        weights = [np.exp(-a / epsilon) for a in actions]
        
        if sum(weights) == 0:
            return 0.0
            
        normalized = [w / sum(weights) for w in weights]
        # ESS = 1 / Σ w_i²
        ess = 1.0 / sum(w**2 for w in normalized)
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
    """
    
    def __init__(self, 
                 n_trajectories: int = 5,
                 n_steps: int = 20,
                 time_horizon: float = 1.0):
        self.n_trajectories = n_trajectories
        self.n_steps = n_steps
        self.dt = time_horizon / n_steps
        
    def generate_trajectories(self,
                            initial_state: Dict,
                            market_hamiltonian: Dict[str, float],
                            operator_registry) -> List[Trajectory]:
        """
        Generate candidate trajectory family via RK4 integration.
        Multiple initial velocity perturbations.
        """
        price = initial_state.get("price", 100.0)
        time = 0.0
        
        # Velocity perturbations for trajectory family
        base_velocity = initial_state.get("velocity", 0.0)
        perturbations = np.linspace(-0.02, 0.02, self.n_trajectories)
        
        trajectories = []
        for i, pert in enumerate(perturbations):
            velocity = base_velocity + pert
            path = self._rk4_integrate(price, velocity, time, market_hamiltonian)
            
            # Compute operator scores for this path
            op_scores = self._compute_operator_scores(path, operator_registry)
            
            # Compute action
            action = self._compute_path_action(path, market_hamiltonian)
            
            # Predicted PnL (simplified)
            predicted_pnl = (path[-1][1] - path[0][1]) / path[0][1] if path else 0
            
            traj = Trajectory(
                id=f"traj_{i}_{hash(str(path)) % 10000}",
                path=path,
                energy=self._compute_energy(path, market_hamiltonian),
                action=action,
                operator_scores=op_scores,
                action_score=-action,  # Lower action = higher score
                predicted_pnl=predicted_pnl
            )
            
            trajectories.append(traj)
        
        return trajectories
    
    def _rk4_integrate(self,
                      initial_price: float,
                      initial_velocity: float,
                      start_time: float,
                      hamiltonian: Dict[str, float]) -> List[Tuple[float, float]]:
        """
        RK4 integration of equations of motion.
        d²x/dt² = -∂V/∂x (from H = T + V)
        """
        path = [(start_time, initial_price)]
        
        price = initial_price
        velocity = initial_velocity
        time = start_time
        
        # Force from potential gradient (simplified)
        potential_force = -sum(hamiltonian.values()) * 0.01
        
        for step in range(self.n_steps):
            # RK4 steps
            k1_v = potential_force * self.dt
            k1_x = velocity * self.dt
            
            k2_v = potential_force * self.dt
            k2_x = (velocity + 0.5 * k1_v) * self.dt
            
            k3_v = potential_force * self.dt
            k3_x = (velocity + 0.5 * k2_v) * self.dt
            
            k4_v = potential_force * self.dt
            k4_x = (velocity + k3_v) * self.dt
            
            # Update
            velocity += (k1_v + 2*k2_v + 2*k3_v + k4_v) / 6
            price += (k1_x + 2*k2_x + 2*k3_x + k4_x) / 6
            time += self.dt
            
            # Add noise for realism
            price += np.random.normal(0, abs(0.001 * price))
            
            path.append((time, price))
        
        return path
    
    def _compute_operator_scores(self,
                               path: List[Tuple[float, float]],
                               operator_registry) -> Dict[str, float]:
        """Compute ICT operator scores for trajectory"""
        # Create synthetic market data from path
        prices = [p for _, p in path]
        
        market_data = {
            "prices": prices,
            "highs": prices,
            "lows": prices,
            "close": prices[-1] if prices else 0
        }
        
        return operator_registry.get_all_scores(market_data, {})
    
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


class PathIntegralEngine:
    """Complete path integral engine: generation + weighting + selection"""
    
    def __init__(self):
        self.generator = LeastActionGenerator()
        self.integral = PathIntegralOperator()
        self.calibrator = EpsilonCalibrator()
        
    def execute_path_integral(self,
                             initial_state: Dict,
                             hamiltonian: Dict[str, float],
                             operator_registry) -> Dict:
        """
        Full path integral execution:
        1. Generate trajectories
        2. Compute actions
        3. Calibrate ℏ
        4. Weight trajectories
        5. Return results
        """
        # Generate trajectory family
        trajectories = self.generator.generate_trajectories(
            initial_state, hamiltonian, operator_registry
        )
        
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
            "hamiltonian": hamiltonian
        }
