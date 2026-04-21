"""
Master Equation - Lindbladian state evolution

dρ/dt = -i[H, ρ] + Σ(LρL† - ½{L†L, ρ})

Where:
- H: Total Hamiltonian (unitary evolution)
- L_k: Lindblad operators (non-unitary/constraint terms)
- [A,B]: Commutator AB - BA
- {A,B}: Anticommutator AB + BA
"""

import numpy as np
from typing import List, Optional, Callable


def evolve_master_equation(
    rho: np.ndarray,
    H_total: np.ndarray,
    lindblad_ops: List[np.ndarray],
    dt: float,
    backend: str = 'numpy'
) -> np.ndarray:
    """
    Evolve density matrix through master equation.
    
    Args:
        rho: Density matrix (state representation, Hermitian positive semi-definite)
        H_total: Total Hamiltonian (Hermitian)
        lindblad_ops: List of Lindblad operators (constraints, measurements)
        dt: Time step
        backend: 'numpy' or optimized backend
    
    Returns:
        Evolved density matrix
    
    Raises:
        ValueError: If rho or H is not Hermitian
    """
    # Validate inputs
    if not _is_hermitian(rho, tol=1e-10):
        raise ValueError("Density matrix rho must be Hermitian")
    
    if not _is_hermitian(H_total, tol=1e-10):
        raise ValueError("Hamiltonian H must be Hermitian")
    
    # Unitary part: -i[H, ρ] = -i(Hρ - ρH)
    commutator = -1j * (H_total @ rho - rho @ H_total)
    
    # Lindblad part: Σ(LρL† - ½{L†L, ρ})
    lindblad_sum = np.zeros_like(rho, dtype=complex)
    
    for L in lindblad_ops:
        # LρL†
        term1 = L @ rho @ L.conj().T
        
        # ½{L†L, ρ} = ½(L†Lρ + ρL†L)
        Ldagger_L = L.conj().T @ L
        term2 = 0.5 * (Ldagger_L @ rho + rho @ Ldagger_L)
        
        lindblad_sum += term1 - term2
    
    # Total evolution
    drho = commutator + lindblad_sum
    
    # Update
    rho_new = rho + dt * drho
    
    # Ensure physicality (numerical drift correction)
    rho_new = _ensure_physical(rho_new)
    
    return rho_new


def _is_hermitian(matrix: np.ndarray, tol: float = 1e-10) -> bool:
    """Check if matrix is Hermitian (A = A†)."""
    if matrix.shape[0] != matrix.shape[1]:
        return False
    return np.allclose(matrix, matrix.conj().T, atol=tol)


def _ensure_physical(rho: np.ndarray) -> np.ndarray:
    """
    Ensure density matrix is physical (Hermitian, positive semi-definite, trace=1).
    
    Applies numerical corrections for drift.
    """
    # Make Hermitian (average with conjugate transpose)
    rho = 0.5 * (rho + rho.conj().T)
    
    # Ensure positive semi-definite (clip negative eigenvalues)
    eigenvalues, eigenvectors = np.linalg.eigh(rho)
    eigenvalues = np.maximum(eigenvalues, 0)  # Clip to non-negative
    
    # Reconstruct
    rho = eigenvectors @ np.diag(eigenvalues) @ eigenvectors.conj().T
    
    # Normalize trace to 1
    trace = np.trace(rho)
    if trace > 0:
        rho = rho / trace
    
    return rho


def compute_hamiltonian_total(
    state_vec: np.ndarray,
    hamiltonians: List[Callable[[np.ndarray], np.ndarray]]
) -> np.ndarray:
    """
    Compute total Hamiltonian H_total = Σ H_i.
    
    Args:
        state_vec: State vector
        hamiltonians: List of Hamiltonian functions
    
    Returns:
        Total Hamiltonian matrix
    """
    H_total = np.zeros((len(state_vec), len(state_vec)), dtype=complex)
    
    for H_func in hamiltonians:
        H_i = H_func(state_vec)
        H_total += H_i
    
    return H_total


def create_lindblad_measurement(observable: np.ndarray) -> np.ndarray:
    """
    Create Lindblad operator for projective measurement.
    
    L = |ψ⟩⟨ψ| for measurement eigenstate.
    
    Args:
        observable: Observable to measure
    
    Returns:
        Lindblad operator L
    """
    # Get eigenstate of observable
    eigenvalues, eigenvectors = np.linalg.eigh(observable)
    
    # Use ground state as measurement projector
    ground_state = eigenvectors[:, 0]
    
    # L = |0⟩⟨0|
    L = np.outer(ground_state, ground_state.conj())
    
    return L


def create_lindblad_damping(damping_rate: float, dimension: int) -> np.ndarray:
    """
    Create amplitude damping Lindblad operator.
    
    L = √γ σ₋ (lowering operator with rate γ)
    
    Args:
        damping_rate: Damping rate γ
        dimension: Hilbert space dimension
    
    Returns:
        Lindblad operator
    """
    # Create lowering operator σ₋
    lowering = np.zeros((dimension, dimension), dtype=complex)
    for i in range(dimension - 1):
        lowering[i, i + 1] = np.sqrt(i + 1)
    
    L = np.sqrt(damping_rate) * lowering
    
    return L


def create_lindblad_dephasing(dephasing_rate: float, dimension: int) -> np.ndarray:
    """
    Create pure dephasing Lindblad operator.
    
    L = √γ σ_z (dephasing with rate γ)
    
    Args:
        dephasing_rate: Dephasing rate γ
        dimension: Hilbert space dimension
    
    Returns:
        Lindblad operator
    """
    # Create σ_z operator
    sigma_z = np.diag([1 if i % 2 == 0 else -1 for i in range(dimension)])
    
    L = np.sqrt(dephasing_rate) * sigma_z
    
    return L
