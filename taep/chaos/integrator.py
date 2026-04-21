"""
Symplectic Integrator for Hamiltonian Systems

Preserves:
- Energy (approximately)
- Phase space volume
- Symplectic structure

Better than standard integrators for long-term chaotic dynamics.
"""

import numpy as np
from typing import Callable, Tuple


class SymplecticIntegrator:
    """
    Verlet-style symplectic integrator.
    
    Time-reversible, good energy conservation for Hamiltonian systems.
    """
    
    def __init__(self, dt: float = 0.001):
        """
        Initialize integrator.
        
        Args:
            dt: Time step size
        """
        self.dt = dt
    
    def step_velocity_verlet(
        self,
        q: np.ndarray,
        p: np.ndarray,
        force_func: Callable[[np.ndarray], np.ndarray],
        mass: float = 1.0
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Single Velocity Verlet step.
        
        Algorithm:
        1. p(t+dt/2) = p(t) + (dt/2) F(q(t))
        2. q(t+dt) = q(t) + dt p(t+dt/2)/m
        3. p(t+dt) = p(t+dt/2) + (dt/2) F(q(t+dt))
        
        Args:
            q: Positions
            p: Momenta
            force_func: Function computing F(q)
            mass: Mass (assumed equal for all)
        
        Returns:
            (q_new, p_new): Updated positions and momenta
        """
        # Half-step momentum
        F = force_func(q)
        p_half = p + 0.5 * self.dt * F
        
        # Full-step position
        q_new = q + self.dt * p_half / mass
        
        # Half-step momentum (finish)
        F_new = force_func(q_new)
        p_new = p_half + 0.5 * self.dt * F_new
        
        return q_new, p_new
    
    def integrate(
        self,
        q0: np.ndarray,
        p0: np.ndarray,
        force_func: Callable[[np.ndarray], np.ndarray],
        steps: int,
        mass: float = 1.0
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Integrate over multiple steps.
        
        Args:
            q0: Initial positions
            p0: Initial momenta
            force_func: Force computation function
            steps: Number of integration steps
            mass: Mass
        
        Returns:
            (q_final, p_final): Final state
        """
        q, p = q0.copy(), p0.copy()
        
        for _ in range(steps):
            q, p = self.step_velocity_verlet(q, p, force_func, mass)
        
        return q, p


def lyapunov_exponent(
    q0: np.ndarray,
    p0: np.ndarray,
    force_func: Callable[[np.ndarray], np.ndarray],
    dt: float = 0.001,
    steps: int = 1000,
    perturbation: float = 1e-10,
    mass: float = 1.0
) -> float:
    """
    Compute largest Lyapunov exponent.
    
    Measures exponential divergence of nearby trajectories:
    d(t) ≈ d₀ exp(λt)
    
    λ > 0: Chaotic (exponential divergence)
    λ = 0: Marginally stable
    λ < 0: Dissipative (convergence)
    
    Args:
        q0: Initial position
        p0: Initial momentum
        force_func: Force function
        dt: Time step
        steps: Integration steps
        perturbation: Initial separation
        mass: Mass
    
    Returns:
        lyapunov: Largest Lyapunov exponent λ
    """
    integrator = SymplecticIntegrator(dt)
    
    # Original trajectory
    q_orig, p_orig = q0.copy(), p0.copy()
    
    # Perturbed trajectory
    q_pert = q0 + perturbation * np.random.randn(*q0.shape)
    p_pert = p0 + perturbation * np.random.randn(*p0.shape)
    
    # Evolve and track divergence
    log_divergence = []
    
    for step in range(steps):
        # Evolve original
        q_orig, p_orig = integrator.step_velocity_verlet(
            q_orig, p_orig, force_func, mass
        )
        
        # Evolve perturbed
        q_pert, p_pert = integrator.step_velocity_verlet(
            q_pert, p_pert, force_func, mass
        )
        
        # Measure separation
        sep_q = np.linalg.norm(q_orig - q_pert)
        sep_p = np.linalg.norm(p_orig - p_pert)
        separation = np.sqrt(sep_q**2 + sep_p**2)
        
        # Normalize to avoid overflow (Gram-Schmidt style)
        if separation > 1e6 * perturbation:
            scale = perturbation / separation
            q_pert = q_orig + scale * (q_pert - q_orig)
            p_pert = p_orig + scale * (p_pert - p_orig)
            separation = perturbation
        
        log_divergence.append(np.log(separation + 1e-300))
    
    # Fit log(d) = log(d₀) + λt
    times = np.arange(len(log_divergence)) * dt
    
    # Linear regression for slope
    if len(times) > 10:
        # Use last 80% to avoid transients
        start_idx = len(times) // 5
        slope = np.polyfit(times[start_idx:], log_divergence[start_idx:], 1)[0]
        return slope
    
    return 0.0


def compute_energy(
    q: np.ndarray,
    p: np.ndarray,
    potential_func: Callable[[np.ndarray], float],
    mass: float = 1.0
) -> float:
    """
    Compute total energy H = T + V.
    
    Args:
        q: Positions
        p: Momenta
        potential_func: V(q) potential energy
        mass: Mass
    
    Returns:
        energy: Total energy
    """
    # Kinetic energy: T = p²/(2m)
    kinetic = 0.5 * np.sum(p**2) / mass
    
    # Potential energy
    potential = potential_func(q)
    
    return kinetic + potential


def check_energy_drift(
    q0: np.ndarray,
    p0: np.ndarray,
    force_func: Callable[[np.ndarray], np.ndarray],
    potential_func: Callable[[np.ndarray], float],
    dt: float = 0.001,
    steps: int = 1000,
    mass: float = 1.0
) -> float:
    """
    Check energy conservation over integration.
    
    Good symplectic integrator should have small drift.
    
    Args:
        q0, p0: Initial state
        force_func: F(q) force
        potential_func: V(q) potential
        dt, steps: Integration parameters
        mass: Mass
    
    Returns:
        relative_drift: |E_final - E_initial| / |E_initial|
    """
    integrator = SymplecticIntegrator(dt)
    
    # Initial energy
    E0 = compute_energy(q0, p0, potential_func, mass)
    
    # Integrate
    q, p = integrator.integrate(q0, p0, force_func, steps, mass)
    
    # Final energy
    E_final = compute_energy(q, p, potential_func, mass)
    
    # Relative drift
    if abs(E0) > 1e-10:
        relative_drift = abs(E_final - E0) / abs(E0)
    else:
        relative_drift = abs(E_final - E0)
    
    return relative_drift
