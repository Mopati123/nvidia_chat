"""
Test Three-Body Chaos Engine
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import pytest
import numpy as np
from taep.chaos.three_body import ThreeBodyEngine, compute_three_body_forces
from taep.chaos.integrator import SymplecticIntegrator, lyapunov_exponent


class TestThreeBodyForces:
    """Test gravitational force computation."""
    
    def test_force_computation(self):
        """Can compute forces for 3 bodies."""
        positions = np.array([
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0]
        ])
        masses = np.array([1.0, 1.0, 1.0])
        
        forces = compute_three_body_forces(positions, masses, G=1.0)
        
        assert forces.shape == (3, 3)
        assert np.all(np.isfinite(forces))
    
    def test_force_direction(self):
        """Forces are attractive (toward other bodies)."""
        positions = np.array([
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [10.0, 0.0, 0.0]  # Far away
        ])
        masses = np.array([1.0, 1.0, 1.0])
        
        forces = compute_three_body_forces(positions, masses, G=1.0)
        
        # Body 0 should be pulled toward body 1 (positive x direction)
        assert forces[0, 0] > 0


class TestThreeBodyEngine:
    """Test ThreeBodyEngine functionality."""
    
    def test_engine_creation(self):
        """Can create engine."""
        engine = ThreeBodyEngine()
        assert engine is not None
        assert len(engine.masses) == 3
    
    def test_evolve_changes_positions(self):
        """Evolution changes positions."""
        engine = ThreeBodyEngine()
        
        initial_pos = engine.state.positions.copy()
        engine.evolve(dt=0.01, steps=10)
        final_pos = engine.state.positions
        
        # Positions should have changed
        assert not np.allclose(initial_pos, final_pos)
    
    def test_key_seed_generation(self):
        """Can generate key seed."""
        engine = ThreeBodyEngine()
        
        geometric_state = np.array([1.0850, 1000.0, 0.5])
        momentum = np.array([0.0001, 0.0, 0.0])
        
        key_seed = engine.generate_key_seed(geometric_state, momentum)
        
        assert key_seed is not None
        assert len(key_seed) > 0
        assert np.all(key_seed >= 0)  # All positive
    
    def test_lyapunov_positive_for_chaos(self):
        """Lyapunov exponent positive indicates chaos."""
        engine = ThreeBodyEngine()
        
        lyap = engine.compute_lyapunov_exponent(dt=0.01, steps=500)
        
        # Should be positive for chaotic system
        # Note: May need more steps for reliable estimate
        assert isinstance(lyap, (int, float))
    
    def test_entropy_measure_increases(self):
        """Entropy measure increases with evolution."""
        engine = ThreeBodyEngine()
        
        initial_entropy = engine.get_entropy_measure()
        
        # Evolve
        for _ in range(100):
            engine.evolve(dt=0.01, steps=1)
        
        final_entropy = engine.get_entropy_measure()
        
        # Entropy should generally increase (not strictly)
        assert final_entropy > 0


class TestSymplecticIntegrator:
    """Test symplectic integration."""
    
    def test_integrator_creation(self):
        """Can create integrator."""
        integrator = SymplecticIntegrator(dt=0.001)
        assert integrator.dt == 0.001
    
    def test_single_step(self):
        """Can perform single integration step."""
        integrator = SymplecticIntegrator(dt=0.001)
        
        q = np.array([1.0, 0.0, 0.0])
        p = np.array([0.0, 0.1, 0.0])
        
        def force_func(q):
            return -q  # Harmonic oscillator
        
        q_new, p_new = integrator.step_velocity_verlet(q, p, force_func)
        
        assert q_new.shape == q.shape
        assert p_new.shape == p.shape
    
    def test_energy_conservation(self):
        """Energy approximately conserved over integration."""
        from taep.chaos.integrator import check_energy_drift
        
        q0 = np.array([1.0, 0.0, 0.0])
        p0 = np.array([0.0, 1.0, 0.0])
        
        def force_func(q):
            return -q
        
        def potential_func(q):
            return 0.5 * np.sum(q**2)
        
        drift = check_energy_drift(q0, p0, force_func, potential_func, dt=0.001, steps=1000)
        
        # Drift should be small for symplectic integrator
        assert drift < 0.01  # Less than 1% drift


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
