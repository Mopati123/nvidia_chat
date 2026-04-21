"""
Three-Body Hamiltonian (H_3B)

Chaotic entropy engine via gravitational three-body dynamics.
"""

import numpy as np
from typing import Optional


class ThreeBodyHamiltonian:
    """
    Three-body chaotic Hamiltonian.
    
    H_3B generates entropy through:
    - Gravitational coupling
    - Nonlinear dynamics
    - Sensitive dependence
    """
    
    def __init__(
        self,
        masses: Optional[np.ndarray] = None,
        G: float = 1.0,
        dimension: int = 3
    ):
        self.masses = masses if masses is not None else np.array([1.0, 1.0, 1.0])
        self.G = G
        self.dimension = dimension
    
    def compute(self, state_vec: np.ndarray) -> np.ndarray:
        """
        Compute three-body Hamiltonian matrix.
        
        Args:
            state_vec: State vector encoding positions and momenta
        
        Returns:
            H: Hamiltonian matrix
        """
        # Extract positions (first 9 elements for 3 bodies in 3D)
        n = len(state_vec)
        H = np.zeros((n, n), dtype=complex)
        
        # Add chaotic coupling terms (off-diagonal)
        # This creates the mixing essential for chaos
        coupling = 0.01
        for i in range(min(9, n)):
            for j in range(i+1, min(9, n)):
                if abs(i - j) <= 3:  # Local coupling
                    H[i, j] = coupling
                    H[j, i] = coupling
        
        # Diagonal: kinetic terms
        for i in range(n):
            H[i, i] = 0.1 * (i + 1)  # Energy scale
        
        return H
    
    def compute_energy(
        self,
        positions: np.ndarray,
        velocities: np.ndarray
    ) -> float:
        """
        Compute total energy of three-body system.
        
        E = T + V = Σ ½mᵢvᵢ² - G Σ_{i<j} mᵢmⱼ/|rᵢ-rⱼ|
        """
        # Kinetic energy
        kinetic = 0.5 * np.sum(
            self.masses[:, np.newaxis] * velocities**2
        )
        
        # Potential energy
        potential = 0.0
        n = len(positions)
        for i in range(n):
            for j in range(i+1, n):
                r_ij = positions[j] - positions[i]
                distance = np.linalg.norm(r_ij)
                potential -= self.G * self.masses[i] * self.masses[j] / distance
        
        return kinetic + potential
    
    def get_coupling_matrix(self, n: int) -> np.ndarray:
        """Get chaotic coupling matrix."""
        coupling = np.zeros((n, n))
        
        for i in range(n):
            for j in range(i+1, n):
                # Coupling decreases with distance in state space
                strength = 0.1 / (abs(i - j) + 1)
                coupling[i, j] = strength
                coupling[j, i] = strength
        
        return coupling
