"""
Three-Body Chaos Engine - Entropy generation via chaotic dynamics

The three-body problem provides:
- Sensitive dependence on initial conditions
- Nonlinear coupling
- Long-run divergence
- Rich phase structure

Used for cryptographic key evolution and entropy generation.
"""

import numpy as np
from typing import Tuple, Optional, List
from dataclasses import dataclass


@dataclass
class ThreeBodyState:
    """State of three-body system."""
    positions: np.ndarray  # Shape (3, 3) - 3 bodies, 3D positions
    velocities: np.ndarray  # Shape (3, 3) - 3 bodies, 3D velocities
    masses: np.ndarray  # Shape (3,) - masses of 3 bodies
    
    def __post_init__(self):
        self.positions = np.array(self.positions, dtype=np.float64)
        self.velocities = np.array(self.velocities, dtype=np.float64)
        self.masses = np.array(self.masses, dtype=np.float64)


def compute_three_body_forces(
    positions: np.ndarray,
    masses: np.ndarray,
    G: float = 1.0,
    softening: float = 1e-9
) -> np.ndarray:
    """
    Compute gravitational forces in three-body system.
    
    F_i = -G Σ_{j≠i} m_j (r_i - r_j) / |r_i - r_j|³
    
    Args:
        positions: (3, 3) array - positions of 3 bodies in 3D
        masses: (3,) array - masses of 3 bodies
        G: Gravitational constant
        softening: Softening parameter to avoid singularities
    
    Returns:
        forces: (3, 3) array - forces on each body
    """
    n_bodies = len(positions)
    forces = np.zeros_like(positions)
    
    for i in range(n_bodies):
        for j in range(n_bodies):
            if i != j:
                r_ij = positions[j] - positions[i]
                distance = np.linalg.norm(r_ij)
                
                # Gravitational force with softening
                force_magnitude = G * masses[j] / (distance**3 + softening)
                forces[i] += force_magnitude * r_ij
    
    return forces


class ThreeBodyEngine:
    """
    Chaotic entropy generator via three-body dynamics.
    
    H_3B generates entropy through sensitive dependence on initial conditions.
    """
    
    def __init__(
        self,
        masses: Optional[np.ndarray] = None,
        G: float = 1.0,
        dimension: int = 3
    ):
        """
        Initialize three-body engine.
        
        Args:
            masses: Masses of 3 bodies (default: equal masses [1, 1, 1])
            G: Gravitational constant
            dimension: Spatial dimension (2 or 3)
        """
        self.masses = masses if masses is not None else np.array([1.0, 1.0, 1.0])
        self.G = G
        self.dimension = dimension
        
        # Initialize with random initial conditions
        self.state = self._initialize_random_state()
        
        # Lyapunov tracking
        self.lyapunov_history = []
    
    def _initialize_random_state(self) -> ThreeBodyState:
        """Initialize with random initial conditions."""
        # Random positions in unit cube
        positions = np.random.randn(3, self.dimension)
        
        # Random velocities (ensure center of mass at rest)
        velocities = np.random.randn(3, self.dimension)
        velocities -= np.mean(velocities, axis=0)  # Zero center-of-mass velocity
        
        return ThreeBodyState(
            positions=positions,
            velocities=velocities,
            masses=self.masses
        )
    
    def evolve(self, dt: float, steps: int = 1) -> np.ndarray:
        """
        Evolve three-body system using symplectic integration.
        
        Args:
            dt: Time step
            steps: Number of integration steps
        
        Returns:
            positions: Final positions of 3 bodies
        """
        for _ in range(steps):
            # Symplectic Euler (Verlet-like)
            # Update velocities first (kick)
            forces = compute_three_body_forces(
                self.state.positions, self.state.masses, self.G
            )
            
            # F = ma -> a = F/m
            accelerations = forces / self.state.masses[:, np.newaxis]
            self.state.velocities += accelerations * dt
            
            # Update positions (drift)
            self.state.positions += self.state.velocities * dt
        
        return self.state.positions.copy()
    
    def generate_key_seed(self, geometric_state: np.ndarray, momentum: np.ndarray) -> np.ndarray:
        """
        Generate cryptographic key seed from chaotic dynamics.
        
        Maps trading state to initial conditions, evolves three-body system,
        extracts entropy from final configuration.
        
        Args:
            geometric_state: q vector (trading geometric state)
            momentum: p vector (trading momentum)
        
        Returns:
            key_seed: Entropy-rich array for key derivation
        """
        # Map trading state to initial conditions
        # Use geometric state to seed positions
        seed_value = np.sum(geometric_state) + np.sum(momentum)
        np.random.seed(int(seed_value * 1e6) % 2**32)
        
        # Re-initialize with seeded random state
        self.state = self._initialize_random_state()
        
        # Evolve for chaos generation
        self.evolve(dt=0.01, steps=100)
        
        # Extract key seed from final positions
        # Use fractional parts for entropy
        key_seed = np.modf(self.state.positions.flatten())[0]
        
        # Ensure positive
        key_seed = np.abs(key_seed)
        
        return key_seed
    
    def compute_lyapunov_exponent(
        self,
        dt: float = 0.01,
        steps: int = 1000,
        perturbation: float = 1e-10
    ) -> float:
        """
        Compute largest Lyapunov exponent to quantify chaos.
        
        λ > 0 indicates chaos (exponential divergence of nearby trajectories)
        
        Args:
            dt: Time step
            steps: Number of steps
            perturbation: Initial perturbation size
        
        Returns:
            lyapunov_exponent: λ (positive = chaotic)
        """
        # Save original state
        original_pos = self.state.positions.copy()
        original_vel = self.state.velocities.copy()
        
        # Create perturbed state
        perturbed_pos = original_pos + perturbation * np.random.randn(*original_pos.shape)
        perturbed_vel = original_vel + perturbation * np.random.randn(*original_vel.shape)
        
        # Evolve both
        divergence_history = []
        
        for _ in range(steps):
            # Evolve original
            forces = compute_three_body_forces(original_pos, self.state.masses, self.G)
            accelerations = forces / self.state.masses[:, np.newaxis]
            original_vel += accelerations * dt
            original_pos += original_vel * dt
            
            # Evolve perturbed
            forces_p = compute_three_body_forces(perturbed_pos, self.state.masses, self.G)
            acc_p = forces_p / self.state.masses[:, np.newaxis]
            perturbed_vel += acc_p * dt
            perturbed_pos += perturbed_vel * dt
            
            # Compute divergence
            divergence = np.linalg.norm(original_pos - perturbed_pos)
            divergence_history.append(divergence)
        
        # Fit exponential: d(t) = d₀ exp(λt)
        # log(d) = log(d₀) + λt
        if len(divergence_history) > 10:
            times = np.arange(len(divergence_history)) * dt
            log_divergence = np.log(divergence_history + 1e-300)  # Avoid log(0)
            
            # Linear fit
            slope = np.polyfit(times, log_divergence, 1)[0]
            lyapunov = slope
        else:
            lyapunov = 0.0
        
        self.lyapunov_history.append(lyapunov)
        
        return lyapunov
    
    def get_entropy_measure(self) -> float:
        """
        Get current entropy measure from system state.
        
        Returns:
            entropy: Measure of disorder (higher = more chaotic)
        """
        # Use velocity dispersion as entropy proxy
        velocity_std = np.std(self.state.velocities)
        position_dispersion = np.std(self.state.positions)
        
        # Combined entropy measure
        entropy = velocity_std * position_dispersion
        
        return entropy


def create_figure8_initial_conditions() -> ThreeBodyState:
    """
    Create initial conditions for figure-8 periodic orbit.
    
    The figure-8 is a stable periodic solution to the three-body problem.
    Useful for testing and demonstration.
    
    Returns:
        state: ThreeBodyState with figure-8 initial conditions
    """
    # Figure-8 initial conditions (Chenciner & Montgomery 2000)
    # Masses: m1 = m2 = m3 = 1
    # Initial positions
    positions = np.array([
        [0.97000436, -0.24308753, 0.0],
        [-0.97000436, 0.24308753, 0.0],
        [0.0, 0.0, 0.0]
    ])
    
    # Initial velocities
    velocities = np.array([
        [0.46620368, 0.43236573, 0.0],
        [0.46620368, 0.43236573, 0.0],
        [-0.93240737, -0.86473146, 0.0]
    ])
    
    masses = np.array([1.0, 1.0, 1.0])
    
    return ThreeBodyState(positions=positions, velocities=velocities, masses=masses)
