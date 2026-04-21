"""
Geometric Hamiltonian (H_geo)

Defines the substrate:
- Manifold structure
- Phase space
- Local curvature
"""

import numpy as np
from typing import Optional


class GeometricHamiltonian:
    """
    Geometric substrate Hamiltonian.
    
    H_geo = T + V where:
    T = kinetic energy (flat metric)
    V = potential from constraints
    """
    
    def __init__(self, dimension: int = 3):
        self.dimension = dimension
    
    def compute(self, q: np.ndarray, p: np.ndarray) -> np.ndarray:
        """
        Compute geometric Hamiltonian matrix.
        
        Args:
            q: Position vector
            p: Momentum vector
        
        Returns:
            H: Hamiltonian matrix (complex for Lindblad compatibility)
        """
        n = len(q)
        H = np.zeros((n, n), dtype=complex)
        
        # Kinetic: diagonal p²/(2m)
        for i in range(n):
            H[i, i] = 0.5 * p[i]**2 if i < len(p) else 0.0
        
        # Potential: constraint wells
        # Add small potential for numerical stability
        V = 1e-6 * np.sum(q**2)
        H += V * np.eye(n)
        
        return H
    
    def kinetic_energy(self, p: np.ndarray) -> float:
        """Compute kinetic energy T = p²/2."""
        return 0.5 * np.sum(p**2)
    
    def potential_energy(self, q: np.ndarray) -> float:
        """
        Compute potential energy V(q).
        
        For trading: potential from liquidity field.
        """
        # Harmonic-like potential from geometric state
        return 1e-6 * np.sum(q**2)
    
    def total_energy(self, q: np.ndarray, p: np.ndarray) -> float:
        """Total energy H = T + V."""
        return self.kinetic_energy(p) + self.potential_energy(q)
