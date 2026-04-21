"""
flow_field.py - Liquidity potential and flow field computation.

Defines liquidity zones as potential wells and computes flow-driven
forces that guide path generation in the action functional.
"""

import numpy as np
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass


@dataclass
class LiquidityZone:
    """
    Liquidity zone definition.
    
    Represents equal highs/lows or resting liquidity.
    """
    level: float  # Price level
    zone_type: str  # 'high' | 'low' | 'internal' | 'external'
    strength: float  # Number of touches/volume
    volume: float  # Resting volume estimate
    
    def distance_to(self, price: float) -> float:
        """Distance from price to this liquidity zone"""
        return abs(price - self.level)


@dataclass
class FVGZone:
    """
    Fair Value Gap (imbalance zone).
    
    Represents low-resistance regions.
    """
    top: float
    bottom: float
    midpoint: float
    zone_type: str  # 'bullish' | 'bearish'
    
    def contains(self, price: float) -> bool:
        """Check if price is inside FVG"""
        return self.bottom <= price <= self.top
    
    def distance_to_midpoint(self, price: float) -> float:
        """Distance to FVG midpoint (entry anchor)"""
        return abs(price - self.midpoint)


class LiquidityPotentialField:
    """
    Liquidity potential field Φ_L.
    
    Computes potential energy landscape where:
    - Liquidity zones are potential wells (low cost to reach)
    - Flow (OFI) modifies the cost to reach each zone
    - FVG zones create low-resistance paths
    
    The potential is used in S_L (liquidity cost) component of action.
    """
    
    def __init__(self):
        self.liquidity_zones: List[LiquidityZone] = []
        self.fvg_zones: List[FVGZone] = []
        self.current_price: float = 0.0
        
    def set_liquidity_zones(self, zones: List[Dict]):
        """
        Set liquidity zones from ICT geometry analysis.
        
        Args:
            zones: List of dicts with 'level', 'type', 'strength', 'volume'
        """
        self.liquidity_zones = [
            LiquidityZone(
                level=z['level'],
                zone_type=z.get('type', 'internal'),
                strength=z.get('strength', 1.0),
                volume=z.get('volume', 0.0)
            )
            for z in zones
        ]
    
    def set_fvg_zones(self, fvgs: List[Dict]):
        """
        Set FVG zones from ICT analysis.
        
        Args:
            fvgs: List of dicts with 'top', 'bottom', 'type'
        """
        self.fvg_zones = [
            FVGZone(
                top=f['top'],
                bottom=f['bottom'],
                midpoint=(f['top'] + f['bottom']) / 2,
                zone_type=f.get('type', 'bullish')
            )
            for f in fvgs
        ]
    
    def compute_potential(self, price: float, ofi: float) -> float:
        """
        Compute liquidity potential at given price with flow.
        
        Φ_L(x) = distance_to_liquidity * (1 - tanh(OFI))
        
        Strong buying (OFI > 0) reduces cost toward upside liquidity.
        Strong selling (OFI < 0) reduces cost toward downside liquidity.
        
        Args:
            price: Current price point
            ofi: Order Flow Imbalance
        
        Returns:
            Potential value (lower = more favorable)
        """
        if not self.liquidity_zones:
            return 0.0
        
        # Find nearest liquidity zone
        distances = [zone.distance_to(price) for zone in self.liquidity_zones]
        min_distance = min(distances)
        nearest_zone = self.liquidity_zones[distances.index(min_distance)]
        
        # Determine flow alignment
        # OFI > 0 (buying) should favor upside liquidity (highs)
        # OFI < 0 (selling) should favor downside liquidity (lows)
        is_upside = price > nearest_zone.level if nearest_zone.zone_type == 'low' else price < nearest_zone.level
        
        # Flow factor: tanh(OFI) maps to [-1, 1]
        # (1 - tanh(OFI)) creates flow-weighted potential
        flow_factor = 1 - np.tanh(ofi)
        
        # If flow aligns with direction to liquidity, reduce cost
        if (ofi > 0 and is_upside) or (ofi < 0 and not is_upside):
            flow_factor *= 0.5  # Flow-aligned = lower cost
        else:
            flow_factor *= 1.5  # Flow-opposed = higher cost
        
        # Base potential
        potential = min_distance * flow_factor
        
        return potential
    
    def compute_fvg_bonus(self, price: float) -> float:
        """
        Compute FVG bonus factor.
        
        Inside FVG = low resistance (bonus < 1.0)
        Outside FVG = high resistance (bonus > 1.0)
        
        Returns:
            Bonus factor (0.5 inside FVG, 1.5 outside)
        """
        for fvg in self.fvg_zones:
            if fvg.contains(price):
                return 0.5  # Low resistance inside FVG
        
        return 1.5  # Higher resistance outside FVG
    
    def compute_liquidity_cost_for_path(self, path: List[Dict]) -> float:
        """
        Compute total liquidity cost for a path.
        
        Used in S_L component of action functional.
        
        Args:
            path: List of path steps, each with 'price' and 'ofi'
        
        Returns:
            Average liquidity cost along path
        """
        if not path:
            return 0.0
        
        costs = []
        for step in path:
            price = step.get('price', 0.0)
            ofi = step.get('ofi', 0.0)
            
            # Base liquidity cost
            d_liq = self.compute_potential(price, ofi)
            
            # FVG alignment bonus
            fvg_bonus = self.compute_fvg_bonus(price)
            
            # Total cost for this step
            cost = d_liq * fvg_bonus
            costs.append(cost)
        
        # Return average cost
        return np.mean(costs) if costs else 0.0


class FlowField:
    """
    Complete flow field combining all microstructure forces.
    
    Integrates:
    - Liquidity potential (Φ_L)
    - Order Flow Imbalance (OFI)
    - Velocity and acceleration
    - Spread dynamics
    """
    
    def __init__(self):
        self.liquidity_field = LiquidityPotentialField()
        self.current_ofi = 0.0
        self.current_velocity = 0.0
        self.current_acceleration = 0.0
        self.current_spread = 0.0
        
    def update_from_microstructure(self, micro_data: Dict):
        """
        Update flow field from microstructure data.
        
        Args:
            micro_data: Output from TickProcessor
        """
        self.current_ofi = micro_data.get('ofi', 0.0)
        self.current_velocity = micro_data.get('velocity', 0.0)
        self.current_acceleration = micro_data.get('acceleration', 0.0)
        self.current_spread = micro_data.get('spread', 0.0)
    
    def compute_force_vector(self, price: float, target_liquidity: float) -> float:
        """
        Compute force toward target liquidity.
        
        Force considers:
        - Distance to target
        - Flow alignment (OFI)
        - Momentum (velocity)
        
        Returns:
            Force magnitude (positive = toward target)
        """
        distance = target_liquidity - price
        
        # Flow alignment
        flow_alignment = np.tanh(self.current_ofi)
        
        # Momentum contribution
        momentum = np.sign(self.current_velocity) * min(abs(self.current_velocity) * 10, 1.0)
        
        # Combined force
        force = (
            0.5 * np.sign(distance) +  # Direction to target
            0.3 * flow_alignment +     # Flow push
            0.2 * momentum             # Momentum
        )
        
        return force
    
    def get_flow_state(self) -> Dict:
        """
        Get current flow state summary.
        """
        return {
            'ofi': self.current_ofi,
            'velocity': self.current_velocity,
            'acceleration': self.current_acceleration,
            'spread': self.current_spread,
            'buying_pressure': self.current_ofi > 0.1,
            'selling_pressure': self.current_ofi < -0.1,
            'high_volatility': self.current_spread > 0.0005,  # 5 pips
            'trending': abs(self.current_velocity) > 0.001,
        }
