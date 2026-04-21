"""
liquidity_field.py - Liquidity resistance field ϕ(p,t).

Computes the scalar liquidity field from ICT structures:

    ϕ(p,t) = a₁·ρ_OB + a₂·ρ_pool - a₃·ρ_FVG + a₄·σ + a₅·m(t)

Where:
    ρ_OB   = order block density (raises resistance)
    ρ_pool = liquidity pool density (raises resistance)
    ρ_FVG  = FVG strength (reduces resistance, negative term)
    σ      = spread/volatility (uncertainty)
    m(t)   = session misalignment penalty

This field defines the metric, connection, and curvature of the market manifold.
"""

import numpy as np
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass


@dataclass
class LiquidityFieldConfig:
    """Configuration for liquidity field computation"""
    a_ob: float = 0.3       # Order block weight (resistance)
    a_pool: float = 0.2     # Liquidity pool weight (resistance)
    a_fvg: float = -0.4     # FVG weight (negative = reduces resistance)
    a_sigma: float = 0.1    # Spread/volatility weight (uncertainty)
    a_session: float = 0.2  # Session misalignment weight
    epsilon: float = 1e-8     # Numerical stabilizer


class LiquidityField:
    """
    Liquidity resistance field ϕ(p,t).
    
    Represents how difficult it is for price to move through different
    regions of the market. High ϕ = high resistance (slow, constrained motion).
    Low ϕ = low resistance (fast, easy flow).
    
    The field is computed from ICT geometry and microstructure:
    - Order blocks: Barriers that raise resistance
    - Liquidity pools: Dense regions that constrain motion
    - FVGs: Low-resistance corridors that facilitate flow
    - Spread: Uncertainty that increases effective resistance
    - Session timing: Phase misalignment that raises costs
    """
    
    def __init__(self, config: Optional[LiquidityFieldConfig] = None):
        self.config = config or LiquidityFieldConfig()
        
    def compute(self,
                price: float,
                timestamp: float,
                ict_structures: Dict,
                microstructure: Optional[Dict] = None) -> float:
        """
        Compute liquidity field ϕ at point (p,t).
        
        Args:
            price: Current price p
            timestamp: Current time t
            ict_structures: Dict with 'order_blocks', 'liquidity_pools', 'fvgs'
            microstructure: Optional dict with 'spread', 'session', etc.
        
        Returns:
            Scalar liquidity field value ϕ(p,t)
        """
        # Extract densities
        rho_ob = self._compute_order_block_density(price, ict_structures.get('order_blocks', []))
        rho_pool = self._compute_liquidity_pool_density(price, ict_structures.get('liquidity_pools', []))
        rho_fvg = self._compute_fvg_strength(price, ict_structures.get('fvgs', []))
        
        # Spread/volatility contribution
        sigma = microstructure.get('spread', 0.0) if microstructure else 0.0
        
        # Session misalignment
        m_t = self._compute_session_misalignment(timestamp, microstructure)
        
        # Compute field
        cfg = self.config
        phi = (
            cfg.a_ob * rho_ob +
            cfg.a_pool * rho_pool +
            cfg.a_fvg * rho_fvg +
            cfg.a_sigma * sigma +
            cfg.a_session * m_t
        )
        
        return phi
    
    def compute_gradient(self,
                        price: float,
                        timestamp: float,
                        ict_structures: Dict,
                        microstructure: Optional[Dict] = None,
                        dp: float = 0.0001) -> Tuple[float, float]:
        """
        Compute gradient ∇ϕ = (∂_p ϕ, ∂_t ϕ) numerically.
        
        Args:
            price: Price point
            timestamp: Time point
            ict_structures: ICT geometry
            microstructure: Microstructure data
            dp: Price step for numerical derivative
        
        Returns:
            Tuple (d_phi_dp, d_phi_dt) - gradient components
        """
        # Compute ϕ at current point
        phi_center = self.compute(price, timestamp, ict_structures, microstructure)
        
        # Compute ∂_p ϕ (price derivative)
        phi_plus_dp = self.compute(price + dp, timestamp, ict_structures, microstructure)
        phi_minus_dp = self.compute(price - dp, timestamp, ict_structures, microstructure)
        d_phi_dp = (phi_plus_dp - phi_minus_dp) / (2 * dp)
        
        # Compute ∂_t ϕ (time derivative) - use small time step
        dt = 60  # 1 minute in seconds
        phi_plus_dt = self.compute(price, timestamp + dt, ict_structures, microstructure)
        phi_minus_dt = self.compute(price, timestamp - dt, ict_structures, microstructure)
        d_phi_dt = (phi_plus_dt - phi_minus_dt) / (2 * dt)
        
        return d_phi_dp, d_phi_dt
    
    def compute_laplacian(self,
                         price: float,
                         timestamp: float,
                         ict_structures: Dict,
                         microstructure: Optional[Dict] = None,
                         dp: float = 0.0001) -> float:
        """
        Compute Laplacian Δϕ = ∂²_p ϕ + ∂²_t ϕ numerically.
        
        The Laplacian is needed for Gaussian curvature computation.
        
        Returns:
            Scalar Laplacian value Δϕ
        """
        # Compute ϕ at center
        phi_center = self.compute(price, timestamp, ict_structures, microstructure)
        
        # Second derivative in price (∂²_p ϕ)
        phi_plus_p = self.compute(price + dp, timestamp, ict_structures, microstructure)
        phi_minus_p = self.compute(price - dp, timestamp, ict_structures, microstructure)
        d2_phi_dp2 = (phi_plus_p - 2 * phi_center + phi_minus_p) / (dp ** 2)
        
        # Second derivative in time (∂²_t ϕ)
        dt = 60  # 1 minute
        phi_plus_t = self.compute(price, timestamp + dt, ict_structures, microstructure)
        phi_minus_t = self.compute(price, timestamp - dt, ict_structures, microstructure)
        d2_phi_dt2 = (phi_plus_t - 2 * phi_center + phi_minus_t) / (dt ** 2)
        
        return d2_phi_dp2 + d2_phi_dt2
    
    def _compute_order_block_density(self, price: float, order_blocks: List[Dict]) -> float:
        """
        Compute order block density ρ_OB at price.
        
        Order blocks raise resistance. Density is computed as sum of
        block strengths weighted by inverse distance.
        """
        if not order_blocks:
            return 0.0
        
        density = 0.0
        for ob in order_blocks:
            level = ob.get('level', price)
            strength = ob.get('strength', 1.0)
            width = ob.get('width', 0.0010)  # 10 pips default
            
            # Distance from price to order block
            distance = abs(price - level)
            
            # Contribution falls off with distance
            if distance < width * 2:  # Within influence zone
                contrib = strength * np.exp(-distance / width)
                density += contrib
        
        return min(density, 5.0)  # Cap at 5.0
    
    def _compute_liquidity_pool_density(self, price: float, pools: List[Dict]) -> float:
        """
        Compute liquidity pool density ρ_pool at price.
        
        Liquidity pools are dense regions that constrain motion.
        """
        if not pools:
            return 0.0
        
        density = 0.0
        for pool in pools:
            level = pool.get('level', price)
            volume = pool.get('volume', 1.0)
            radius = pool.get('radius', 0.0020)  # 20 pips
            
            distance = abs(price - level)
            
            if distance < radius * 2:
                # Higher volume = denser pool
                contrib = (volume / 100.0) * np.exp(-distance / radius)
                density += contrib
        
        return min(density, 5.0)
    
    def _compute_fvg_strength(self, price: float, fvgs: List[Dict]) -> float:
        """
        Compute FVG strength ρ_FVG at price.
        
        FVGs are negative contributions (reduce resistance).
        Stronger when price is inside the gap.
        """
        if not fvgs:
            return 0.0
        
        strength = 0.0
        for fvg in fvgs:
            top = fvg.get('top', price + 0.0010)
            bottom = fvg.get('bottom', price - 0.0010)
            gap_strength = fvg.get('strength', 1.0)
            
            # Check if price is inside FVG
            if bottom <= price <= top:
                # Inside gap - maximum reduction
                # Contribution increases toward center
                center = (top + bottom) / 2
                distance_from_center = abs(price - center)
                half_width = (top - bottom) / 2
                
                # Normalize to [0,1] - 0 at edges, 1 at center
                normalized = 1.0 - (distance_from_center / (half_width + 1e-8))
                contrib = gap_strength * normalized
                strength += contrib
            else:
                # Near gap - partial effect
                distance_to_gap = min(abs(price - top), abs(price - bottom))
                if distance_to_gap < 0.0010:  # Within 10 pips
                    decay = np.exp(-distance_to_gap / 0.0005)
                    contrib = gap_strength * decay * 0.5
                    strength += contrib
        
        return min(strength, 3.0)
    
    def _compute_session_misalignment(self, timestamp: float, microstructure: Optional[Dict]) -> float:
        """
        Compute session misalignment penalty m(t).
        
        Higher during dead zones, lower during aligned sessions.
        """
        if not microstructure:
            return 0.5  # Neutral
        
        session = microstructure.get('session', '').lower()
        kill_zone = microstructure.get('kill_zone', False)
        
        # Aligned sessions have low misalignment
        if session in ['london', 'ny', 'london_open', 'ny_open']:
            if kill_zone:
                return 0.0  # Perfect alignment
            return 0.2
        
        # Dead zones have high misalignment
        if session in ['asia', 'close']:
            return 1.0
        
        return 0.5  # Default


def compute_liquidity_field(price: float,
                           timestamp: float,
                           ict_structures: Dict,
                           microstructure: Optional[Dict] = None,
                           config: Optional[LiquidityFieldConfig] = None) -> float:
    """
    Convenience function to compute liquidity field ϕ(p,t).
    
    Args:
        price: Price coordinate
        timestamp: Time coordinate
        ict_structures: Dict with 'order_blocks', 'liquidity_pools', 'fvgs'
        microstructure: Optional microstructure data
        config: Optional configuration
    
    Returns:
        Scalar liquidity field value
    """
    field = LiquidityField(config)
    return field.compute(price, timestamp, ict_structures, microstructure)
