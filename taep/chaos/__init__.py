"""
TAEP Chaos Engine - Three-body dynamics for entropy generation
"""

from .three_body import ThreeBodyEngine, compute_three_body_forces
from .integrator import SymplecticIntegrator, lyapunov_exponent

__all__ = ['ThreeBodyEngine', 'compute_three_body_forces', 'SymplecticIntegrator', 'lyapunov_exponent']
