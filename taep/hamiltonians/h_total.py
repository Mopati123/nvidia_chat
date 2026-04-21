"""
Total Hamiltonian (H_total)

H_total = H_geo + H_3B + H_stat + H_game + H_q
"""

import numpy as np
from typing import List, Optional, Callable


class TotalHamiltonian:
    """
    Combines all Hamiltonian components.
    """
    
    def __init__(self, hamiltonians: Optional[List] = None):
        """
        Initialize with component Hamiltonians.
        
        Args:
            hamiltonians: List of Hamiltonian objects
        """
        self.hamiltonians = hamiltonians or []
        self.weights = [1.0] * len(self.hamiltonians)
    
    def add_hamiltonian(self, H, weight: float = 1.0):
        """Add a Hamiltonian component with weight."""
        self.hamiltonians.append(H)
        self.weights.append(weight)
    
    def compute(self, state_vec: np.ndarray) -> np.ndarray:
        """
        Compute total Hamiltonian.
        
        H_total = Σ w_i H_i
        """
        if not self.hamiltonians:
            # Default: identity scaled by state dimension
            n = len(state_vec)
            return np.eye(n, dtype=complex)
        
        # Sum weighted Hamiltonians
        H_total = np.zeros((len(state_vec), len(state_vec)), dtype=complex)
        
        for H, w in zip(self.hamiltonians, self.weights):
            if hasattr(H, 'compute'):
                H_i = H.compute(state_vec)
            elif callable(H):
                H_i = H(state_vec)
            else:
                continue
            
            H_total += w * H_i
        
        return H_total
    
    def get_component_energies(self, state) -> dict:
        """Get energy contribution from each component."""
        energies = {}
        
        for i, (H, w) in enumerate(zip(self.hamiltonians, self.weights)):
            name = getattr(H, '__class__.__name__', f'H_{i}')
            
            if hasattr(H, 'total_energy'):
                if hasattr(state, 'q') and hasattr(state, 'p'):
                    E = H.total_energy(state.q, state.p)
                else:
                    E = 0.0
            elif hasattr(H, 'compute_energy'):
                # For three-body
                if hasattr(H, 'compute_energy'):
                    # Try to extract positions/velocities
                    if hasattr(state, 'positions') and hasattr(state, 'velocities'):
                        E = H.compute_energy(state.positions, state.velocities)
                    else:
                        E = 0.0
            else:
                E = 0.0
            
            energies[name] = w * E
        
        return energies
    
    @staticmethod
    def create_default(state_dim: int = 9) -> 'TotalHamiltonian':
        """Create default Hamiltonian with geometric and three-body components."""
        from .h_geo import GeometricHamiltonian
        from .h_3body import ThreeBodyHamiltonian
        
        H = TotalHamiltonian()
        H.add_hamiltonian(GeometricHamiltonian(), weight=1.0)
        H.add_hamiltonian(ThreeBodyHamiltonian(), weight=0.5)
        
        return H
