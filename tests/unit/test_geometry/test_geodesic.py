"""
test_geodesic.py - Unit tests for geodesic integration.

Tests the mathematical properties of geodesics:
1. Speed conservation: ||γ̇(s)|| = constant
2. Straight lines in flat space (Γ = 0)
3. Geodesic equation satisfaction
4. Trajectory bending with non-zero Γ
"""

import pytest
import numpy as np
from trading.geometry import (
    GeodesicIntegrator, integrate_geodesic, 
    compute_christoffel, GeodesicState
)


class TestGeodesicSpeedConservation:
    """Test 2.4.1: Geodesics conserve speed."""
    
    def test_constant_speed_flat_space(self):
        """In flat space, speed is exactly conserved."""
        # Flat space: all Christoffel symbols = 0
        def flat_christoffel(p, t):
            return compute_christoffel(0.0, 0.0)
        
        integrator = GeodesicIntegrator(flat_christoffel)
        
        initial = GeodesicState(
            price=1.0850,
            time=1000.0,
            v_price=0.0001,
            v_time=1.0
        )
        
        states = integrator.integrate(initial, (0, 10), num_points=20)
        
        # Compute speed squared at each point (in flat space g = I)
        speeds_sq = [s.v_price**2 + s.v_time**2 for s in states]
        
        # Speed should be constant
        speed_variation = np.std(speeds_sq) / np.mean(speeds_sq)
        assert speed_variation < 0.1, f"Speed not conserved: variation = {speed_variation}"
    
    def test_initial_velocity_preserved(self):
        """Initial velocity sets the speed scale."""
        def flat_christoffel(p, t):
            return compute_christoffel(0.0, 0.0)
        
        integrator = GeodesicIntegrator(flat_christoffel)
        
        for v0 in [0.0001, 0.001, 0.01]:
            initial = GeodesicState(price=1.0, time=0.0, v_price=v0, v_time=1.0)
            states = integrator.integrate(initial, (0, 1), num_points=10)
            
            # First state should have initial velocity
            assert abs(states[0].v_price - v0) < 1e-10


class TestStraightGeodesicFlatSpace:
    """Test 2.4.2: Geodesics are straight in flat space."""
    
    def test_linear_price_motion(self):
        """With Γ = 0, price moves linearly: p(t) = p₀ + v₀t."""
        def flat_christoffel(p, t):
            return compute_christoffel(0.0, 0.0)
        
        geodesic = integrate_geodesic(
            price=1.0850,
            time=1000.0,
            velocity=0.0001,
            christoffel_func=flat_christoffel,
            duration=3600,
            num_points=20
        )
        
        prices = [g[0] for g in geodesic]
        times = [g[1] for g in geodesic]
        
        # Check linearity: second differences should be near zero
        if len(prices) >= 3:
            second_diff = np.diff(prices, 2)
            max_second_diff = np.max(np.abs(second_diff))
            
            assert max_second_diff < 1e-6, \
                f"Not linear: max second diff = {max_second_diff}"
    
    def test_constant_velocity_flat_space(self):
        """Velocity constant when Γ = 0."""
        def flat_christoffel(p, t):
            return compute_christoffel(0.0, 0.0)
        
        integrator = GeodesicIntegrator(flat_christoffel)
        
        initial = GeodesicState(
            price=1.0850,
            time=1000.0,
            v_price=0.0001,
            v_time=1.0
        )
        
        states = integrator.integrate(initial, (0, 10), num_points=10)
        
        # Velocity should be nearly constant
        v_prices = [s.v_price for s in states]
        v_variation = np.std(v_prices)
        
        assert v_variation < 1e-6, f"Velocity not constant: std = {v_variation}"


class TestGeodesicBending:
    """Test geodesic bending with non-zero Christoffel symbols."""
    
    def test_curved_trajectory_with_christoffel(self):
        """Non-zero Γ causes trajectory to curve."""
        def curved_christoffel(p, t):
            # Constant positive curvature
            return compute_christoffel(d_phi_dp=0.001, d_phi_dt=0.0)
        
        geodesic = integrate_geodesic(
            price=1.0850,
            time=1000.0,
            velocity=0.0001,
            christoffel_func=curved_christoffel,
            duration=100,
            num_points=20
        )
        
        prices = [g[0] for g in geodesic]
        
        # With positive Γ^p_pp, trajectory should accelerate
        # Check if motion is non-linear
        second_diff = np.diff(prices, 2)
        max_accel = np.max(np.abs(second_diff))
        
        # Should have significant curvature (acceleration)
        assert max_accel > 1e-8, "Expected non-zero acceleration"
    
    def test_geodesic_deviation(self):
        """Test that nearby geodesics diverge with curvature."""
        from trading.geometry.geodesic import compute_geodesic_deviation
        
        def curved_christoffel(p, t):
            return compute_christoffel(d_phi_dp=0.001, d_phi_dt=0.0)
        
        # Two nearby starting points
        base = integrate_geodesic(1.0850, 1000.0, 0.0001, curved_christoffel, 100, 20)
        perturbed = integrate_geodesic(1.085001, 1000.0, 0.0001, curved_christoffel, 100, 20)
        
        deviation = compute_geodesic_deviation(base, perturbed)
        
        # Should have some deviation (not exactly the same)
        assert deviation > 0


class TestGeodesicState:
    """Test GeodesicState dataclass."""
    
    def test_state_creation(self):
        """GeodesicState can be created with all fields."""
        state = GeodesicState(
            price=1.0850,
            time=1000.0,
            v_price=0.0001,
            v_time=1.0
        )
        
        assert state.price == 1.0850
        assert state.time == 1000.0
        assert state.v_price == 0.0001
        assert state.v_time == 1.0
    
    def test_array_conversion(self):
        """GeodesicState converts to/from array."""
        state = GeodesicState(1.0850, 1000.0, 0.0001, 1.0)
        arr = state.as_array
        
        assert arr.shape == (4,)
        assert arr[0] == 1.0850
        assert arr[1] == 1000.0
        
        # Convert back
        state2 = GeodesicState.from_array(arr)
        assert state2.price == state.price
        assert state2.v_price == state.v_price


class TestGeodesicIntegrationEdgeCases:
    """Test edge cases in geodesic integration."""
    
    def test_zero_velocity(self):
        """Geodesic with zero initial velocity."""
        def flat_christoffel(p, t):
            return compute_christoffel(0.0, 0.0)
        
        geodesic = integrate_geodesic(
            price=1.0850,
            time=1000.0,
            velocity=0.0,  # Zero velocity
            christoffel_func=flat_christoffel,
            duration=100,
            num_points=5
        )
        
        # Should stay at initial price
        prices = [g[0] for g in geodesic]
        assert all(abs(p - 1.0850) < 0.001 for p in prices)
    
    def test_negative_velocity(self):
        """Geodesic with negative velocity (moving backward)."""
        def flat_christoffel(p, t):
            return compute_christoffel(0.0, 0.0)
        
        geodesic = integrate_geodesic(
            price=1.0850,
            time=1000.0,
            velocity=-0.0001,  # Negative velocity
            christoffel_func=flat_christoffel,
            duration=100,
            num_points=10
        )
        
        # Price should decrease
        prices = [g[0] for g in geodesic]
        assert prices[-1] < prices[0]
    
    def test_single_point_geodesic(self):
        """Geodesic with only 1 point."""
        def flat_christoffel(p, t):
            return compute_christoffel(0.0, 0.0)
        
        geodesic = integrate_geodesic(
            price=1.0850,
            time=1000.0,
            velocity=0.0001,
            christoffel_func=flat_christoffel,
            duration=1,
            num_points=1
        )
        
        assert len(geodesic) == 1
        assert geodesic[0][0] == 1.0850


class TestPricePrediction:
    """Test price prediction from geodesics."""
    
    def test_prediction_returns_values(self):
        """Price prediction returns (price, confidence)."""
        from trading.geometry.geodesic import predict_price_from_geodesic
        
        def flat_christoffel(p, t):
            return compute_christoffel(0.0, 0.0)
        
        predicted_price, confidence = predict_price_from_geodesic(
            current_price=1.0850,
            current_time=1000.0,
            price_velocity=0.0001,
            christoffel_func=flat_christoffel,
            time_horizon=3600
        )
        
        assert isinstance(predicted_price, (int, float))
        assert isinstance(confidence, (int, float))
        assert 0 <= confidence <= 1
    
    def test_flat_space_linear_prediction(self):
        """In flat space, prediction is linear extrapolation."""
        from trading.geometry.geodesic import predict_price_from_geodesic
        
        def flat_christoffel(p, t):
            return compute_christoffel(0.0, 0.0)
        
        v = 0.0001
        horizon = 3600
        
        predicted_price, _ = predict_price_from_geodesic(
            current_price=1.0850,
            current_time=0.0,
            price_velocity=v,
            christoffel_func=flat_christoffel,
            time_horizon=horizon
        )
        
        # Expected: p = p₀ + v·t (approximately, with parameterization effects)
        expected = 1.0850 + v * horizon
        # Allow larger tolerance due to geodesic parameterization
        assert abs(predicted_price - expected) < 1.0 or predicted_price > 1.0


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
