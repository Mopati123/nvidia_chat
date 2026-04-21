"""
geodesic.py - Geodesic equation integration for market trajectories.

Implements the geodesic equation:

    d²x^i/ds² + Γ^i_jk (dx^j/ds)(dx^k/ds) = 0

For price coordinate:
    p̈ + Γ^p_pp ṗ² + 2Γ^p_pt ṗ ṫ + Γ^p_tt ṫ² = 0

This defines how price moves through the liquidity manifold.
Geodesics are "straightest possible paths" in curved space.
"""

import numpy as np
from typing import List, Tuple, Optional, Callable
from dataclasses import dataclass
from scipy.integrate import odeint, solve_ivp


@dataclass
class GeodesicState:
    """State vector for geodesic integration: [p, t, v_p, v_t]"""
    price: float      # p
    time: float       # t
    v_price: float    # ṗ = dp/ds
    v_time: float     # ṫ = dt/ds
    
    @property
    def as_array(self) -> np.ndarray:
        return np.array([self.price, self.time, self.v_price, self.v_time])
    
    @classmethod
    def from_array(cls, arr: np.ndarray) -> 'GeodesicState':
        return cls(price=arr[0], time=arr[1], v_price=arr[2], v_time=arr[3])


class GeodesicIntegrator:
    """
    Integrator for geodesic equations through liquidity manifold.
    
    Given initial conditions (price, time, velocity), computes the
    trajectory that follows the geodesic equation.
    """
    
    def __init__(self, christoffel_func: Callable):
        """
        Initialize geodesic integrator.
        
        Args:
            christoffel_func: Function Γ(p,t) -> ChristoffelSymbols
        """
        self.christoffel_func = christoffel_func
    
    def _geodesic_equation(self, state: np.ndarray, s: float) -> np.ndarray:
        """
        Compute derivatives for geodesic equation.
        
        State: [p, t, v_p, v_t]
        Returns: [dp/ds, dt/ds, dv_p/ds, dv_t/ds]
        """
        p, t, v_p, v_t = state
        
        # Get Christoffel symbols at current point
        G = self.christoffel_func(p, t)
        
        # Geodesic equation for price:
        # dv_p/ds = -Γ^p_pp v_p² - 2Γ^p_pt v_p v_t - Γ^p_tt v_t²
        dv_p_ds = -(G.G_p_pp * v_p**2 + 
                   2 * G.G_p_pt * v_p * v_t + 
                   G.G_p_tt * v_t**2)
        
        # Geodesic equation for time:
        # dv_t/ds = -Γ^t_pp v_p² - 2Γ^t_pt v_p v_t - Γ^t_tt v_t²
        dv_t_ds = -(G.G_t_pp * v_p**2 + 
                   2 * G.G_t_pt * v_p * v_t + 
                   G.G_t_tt * v_t**2)
        
        return np.array([v_p, v_t, dv_p_ds, dv_t_ds])
    
    def integrate(self,
                  initial_state: GeodesicState,
                  s_span: Tuple[float, float],
                  num_points: int = 100) -> List[GeodesicState]:
        """
        Integrate geodesic from initial state.
        
        Args:
            initial_state: Starting [p, t, v_p, v_t]
            s_span: Integration range (s_start, s_end)
            num_points: Number of points to compute
        
        Returns:
            List of GeodesicState along the geodesic
        """
        s_values = np.linspace(s_span[0], s_span[1], num_points)
        
        # Use scipy's ODE solver
        solution = odeint(
            self._geodesic_equation,
            initial_state.as_array,
            s_values,
            tfirst=False
        )
        
        # Convert back to GeodesicState objects
        return [GeodesicState.from_array(sol) for sol in solution]
    
    def integrate_price_only(self,
                            initial_price: float,
                            initial_time: float,
                            initial_velocity: float,
                            duration: float,
                            num_points: int = 100) -> List[Tuple[float, float]]:
        """
        Simplified integration focusing on price evolution.
        
        Args:
            initial_price: Starting price p₀
            initial_time: Starting time t₀
            initial_velocity: Initial price velocity ṗ₀
            duration: Integration duration
            num_points: Number of points
        
        Returns:
            List of (price, time) tuples along geodesic
        """
        # Normalize initial velocity
        v_total = abs(initial_velocity)
        if v_total < 1e-10:
            v_total = 1.0
        
        # Initial state with normalized velocity
        initial_state = GeodesicState(
            price=initial_price,
            time=initial_time,
            v_price=initial_velocity / v_total,  # Normalized
            v_time=1.0 / v_total  # Time progresses steadily
        )
        
        # Integrate
        states = self.integrate(initial_state, (0, duration), num_points)
        
        # Return price-time pairs
        return [(s.price, s.time) for s in states]


def integrate_geodesic(
    price: float,
    time: float,
    velocity: float,
    christoffel_func: Callable,
    duration: float = 1.0,
    num_points: int = 50
) -> List[Tuple[float, float]]:
    """
    Convenience function to integrate a single geodesic.
    
    Args:
        price: Initial price
        time: Initial time
        velocity: Initial price velocity
        christoffel_func: Function providing Christoffel symbols
        duration: Integration duration
        num_points: Number of output points
    
    Returns:
        List of (price, time) points along geodesic
    """
    integrator = GeodesicIntegrator(christoffel_func)
    return integrator.integrate_price_only(
        price, time, velocity, duration, num_points
    )


def compute_geodesic_deviation(
    base_geodesic: List[Tuple[float, float]],
    perturbed_geodesic: List[Tuple[float, float]]
) -> float:
    """
    Compute deviation between two nearby geodesics.
    
    Used to detect instability (Lyapunov-like analysis).
    
    Args:
        base_geodesic: Reference geodesic
        perturbed_geodesic: Nearby geodesic with different initial conditions
    
    Returns:
        Maximum deviation
    """
    if len(base_geodesic) != len(perturbed_geodesic):
        min_len = min(len(base_geodesic), len(perturbed_geodesic))
        base_geodesic = base_geodesic[:min_len]
        perturbed_geodesic = perturbed_geodesic[:min_len]
    
    deviations = [
        abs(base_geodesic[i][0] - perturbed_geodesic[i][0])  # Price deviation
        for i in range(len(base_geodesic))
    ]
    
    return max(deviations) if deviations else 0.0


def analyze_geodesic_stability(
    price: float,
    time: float,
    christoffel_func: Callable,
    epsilon: float = 0.0001,
    duration: float = 1.0
) -> dict:
    """
    Analyze geodesic stability via deviation analysis.
    
    Args:
        price: Starting price
        time: Starting time
        christoffel_func: Christoffel symbols function
        epsilon: Perturbation size
        duration: Integration duration
    
    Returns:
        Dict with stability metrics
    """
    # Base geodesic
    base = integrate_geodesic(price, time, 0.0, christoffel_func, duration)
    
    # Perturbed geodesics
    perturbed_plus = integrate_geodesic(price + epsilon, time, 0.0, christoffel_func, duration)
    perturbed_minus = integrate_geodesic(price - epsilon, time, 0.0, christoffel_func, duration)
    
    # Compute deviations
    dev_plus = compute_geodesic_deviation(base, perturbed_plus)
    dev_minus = compute_geodesic_deviation(base, perturbed_minus)
    avg_deviation = (dev_plus + dev_minus) / 2
    
    # Stability metric
    stability = 1.0 / (1.0 + avg_deviation / epsilon)
    
    return {
        'base_geodesic': base,
        'avg_deviation': avg_deviation,
        'stability': stability,
        'is_stable': stability > 0.5,
    }


def predict_price_from_geodesic(
    current_price: float,
    current_time: float,
    price_velocity: float,
    christoffel_func: Callable,
    time_horizon: float = 3600  # 1 hour in seconds
) -> Tuple[float, float]:
    """
    Predict future price using geodesic integration.
    
    Args:
        current_price: Current price p₀
        current_time: Current time t₀
        price_velocity: Observed price velocity ṗ
        christoffel_func: Christoffel symbols function
        time_horizon: Prediction horizon in seconds
    
    Returns:
        Tuple (predicted_price, confidence)
    """
    # Integrate geodesic
    geodesic = integrate_geodesic(
        current_price, current_time, price_velocity,
        christoffel_func, duration=time_horizon, num_points=20
    )
    
    # Get final predicted price
    predicted_price = geodesic[-1][0]
    
    # Compute confidence from geodesic stability
    stability_analysis = analyze_geodesic_stability(
        current_price, current_time, christoffel_func, duration=time_horizon
    )
    confidence = stability_analysis['stability']
    
    return predicted_price, confidence
