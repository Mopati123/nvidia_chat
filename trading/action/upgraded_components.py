"""
upgraded_components.py - Microstructure-aware action components.

Upgrades the four action functional components to use tick-level
microstructure fields:

    S_L: Liquidity cost with flow-weighted potential
    S_T: Time cost with phase-locked session alignment  
    S_E: Entry precision with OFI trigger bonus
    S_R: Risk as path integral drawdown

These replace the basic action components in the path integral
evaluation, creating a force-driven rather than signal-driven system.
"""

import numpy as np
from typing import List, Dict, Optional
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


# Session phase mapping (0 to π)
SESSION_PHASES = {
    'asia': 0.0,           # 0
    'london_open': np.pi/4,   # π/4
    'london': np.pi/4,
    'ny_open': np.pi/2,       # π/2  
    'ny': np.pi/2,
    'ny_close': 3*np.pi/4,    # 3π/4
    'close': np.pi,           # π
}


@dataclass
class ActionConfig:
    """Configuration for action component computation"""
    # S_L (Liquidity) weights
    liquidity_flow_coupling: float = 1.0  # How much OFI affects liquidity cost
    fvg_bonus_inside: float = 0.5         # Cost multiplier inside FVG
    fvg_bonus_outside: float = 1.5        # Cost multiplier outside FVG
    
    # S_T (Time) weights
    session_alignment_weight: float = 1.0
    kill_zone_bonus: float = 0.7          # Reduced cost in kill zones
    
    # S_E (Entry) weights
    fvg_precision_weight: float = 0.6
    fib_precision_weight: float = 0.4
    ofi_trigger_threshold: float = 0.2    # OFI flip magnitude for bonus
    ofi_trigger_bonus: float = 0.3        # Cost reduction on OFI trigger
    
    # S_R (Risk) weights
    drawdown_weight: float = 1.0
    spread_volatility_weight: float = 0.5
    acceleration_penalty: float = 0.3

    # S_HFT (Order book) weights
    hft_action_weight: float = 0.2
    hft_depth_weight: float = 1.0
    hft_pressure_weight: float = 0.7
    hft_microprice_weight: float = 0.5
    hft_layering_weight: float = 0.4
    hft_iceberg_weight: float = 0.5
    hft_inversion_penalty: float = 1_000_000.0


class UpgradedActionComponents:
    """
    Microstructure-aware action functional components.
    
    Computes S_L, S_T, S_E, S_R using tick-level fields:
    - OFI (Order Flow Imbalance)
    - Microprice
    - Velocity/Acceleration
    - Spread dynamics
    - Liquidity potential Φ
    """
    
    def __init__(self, config: Optional[ActionConfig] = None):
        self.config = config or ActionConfig()
    
    def compute_s_liquidity(self,
                           path: List[Dict],
                           liquidity_zones: List[Dict],
                           fvgs: List[Dict]) -> float:
        """
        Compute upgraded liquidity cost S_L.
        
        S_L = Σ [distance_to_liquidity × (1 - tanh(OFI)) × FVG_bonus] / N
        
        Args:
            path: List of path steps with 'price', 'ofi', 'timestamp'
            liquidity_zones: ICT liquidity zones with 'level', 'type'
            fvgs: FVG zones with 'top', 'bottom', 'midpoint'
        
        Returns:
            Average liquidity cost along path (lower = better)
        """
        if not path or not liquidity_zones:
            return 0.0
        
        costs = []
        
        for step in path:
            price = step.get('price', 0.0)
            ofi = step.get('ofi', 0.0)
            
            # Find nearest liquidity zone
            min_distance = float('inf')
            nearest_zone = None
            
            for zone in liquidity_zones:
                distance = abs(price - zone.get('level', price))
                if distance < min_distance:
                    min_distance = distance
                    nearest_zone = zone
            
            if nearest_zone is None:
                continue
            
            # Determine if target liquidity is above or below current price
            is_upside = nearest_zone.get('level', price) > price
            
            # Flow factor: (1 - tanh(OFI))
            # Positive OFI (buying) reduces cost toward upside liquidity
            # Negative OFI (selling) reduces cost toward downside liquidity
            flow_alignment = np.tanh(ofi)
            
            if (ofi > 0 and is_upside) or (ofi < 0 and not is_upside):
                # Flow aligns with direction to liquidity
                flow_factor = 1 - 0.5 * abs(flow_alignment)
            else:
                # Flow opposes direction to liquidity
                flow_factor = 1 + 0.5 * abs(flow_alignment)
            
            # FVG bonus: low resistance inside FVG
            fvg_bonus = self._compute_fvg_bonus(price, fvgs)
            
            # Total cost for this step
            cost = min_distance * flow_factor * fvg_bonus
            costs.append(cost)
        
        # Return average cost
        return np.mean(costs) if costs else 0.0
    
    def compute_s_time(self,
                      path: List[Dict],
                      current_session: str,
                      target_session: str = 'ny_open',
                      in_kill_zone: bool = False) -> float:
        """
        Compute upgraded time cost S_T with phase-locked timing.
        
        S_T = |phase_expected - phase_actual|
        
        Phase values:
            London open: π/4
            NY open: π/2
            NY close: 3π/4
        
        Args:
            path: Path steps with 'timestamp'
            current_session: Current market session
            target_session: Optimal session for this trade type
            in_kill_zone: Whether currently in kill zone
        
        Returns:
            Time cost (lower = better timing)
        """
        if in_kill_zone:
            # Kill zones have reduced time cost (optimal timing)
            return self.config.kill_zone_bonus
        
        # Get phase values
        current_phase = SESSION_PHASES.get(current_session.lower(), np.pi/2)
        target_phase = SESSION_PHASES.get(target_session.lower(), np.pi/2)
        
        # Phase difference (circular distance)
        phase_diff = abs(target_phase - current_phase)
        
        # Normalize to [0, 1]
        max_diff = np.pi
        normalized_diff = phase_diff / max_diff
        
        # Time cost
        s_time = normalized_diff * self.config.session_alignment_weight
        
        return s_time
    
    def compute_s_entry(self,
                       entry_price: float,
                       fvg_midpoint: float,
                       fib_level: float,
                       ofi_at_entry: float,
                       ofi_before: float) -> float:
        """
        Compute upgraded entry precision cost S_E.
        
        S_E = |entry - FVG_mid| + |entry - fib_level| - OFI_trigger_bonus
        
        OFI trigger: If OFI flips sign at entry, reduce cost
        (indicates flow confirmation at entry point)
        
        Args:
            entry_price: Proposed entry price
            fvg_midpoint: FVG zone midpoint (ideal entry)
            fib_level: Nearest Fibonacci level
            ofi_at_entry: OFI value at entry time
            ofi_before: OFI value just before entry
        
        Returns:
            Entry cost (lower = more precise entry)
        """
        # Distance to FVG midpoint
        fvg_distance = abs(entry_price - fvg_midpoint)
        
        # Distance to Fibonacci level
        fib_distance = abs(entry_price - fib_level)
        
        # Weighted combination
        base_cost = (
            self.config.fvg_precision_weight * fvg_distance +
            self.config.fib_precision_weight * fib_distance
        )
        
        # OFI trigger bonus
        ofi_trigger = self._detect_ofi_trigger(ofi_before, ofi_at_entry)
        
        if ofi_trigger:
            # Flow confirmation at entry reduces cost
            cost = base_cost * (1 - self.config.ofi_trigger_bonus)
        else:
            cost = base_cost
        
        return cost
    
    def compute_s_risk(self, path: List[Dict]) -> float:
        """
        Compute upgraded risk cost S_R as path integral drawdown.
        
        S_R = ∫ drawdown(t) dt ≈ Σ drawdown(step)
        
        Also considers:
        - Spread volatility
        - Price acceleration (jerkiness)
        
        Args:
            path: Path steps with 'price', 'drawdown', 'spread', 'acceleration'
        
        Returns:
            Risk cost (lower = less risky path)
        """
        if not path:
            return 0.0
        
        risk_components = []
        
        for step in path:
            # Base drawdown component
            drawdown = step.get('drawdown', 0.0)
            
            # Spread volatility penalty
            spread = step.get('spread', 0.0)
            spread_penalty = spread * self.config.spread_volatility_weight
            
            # Acceleration penalty (high acceleration = instability)
            acceleration = step.get('acceleration', 0.0)
            accel_penalty = abs(acceleration) * self.config.acceleration_penalty
            
            # Combined risk for this step
            step_risk = (
                drawdown * self.config.drawdown_weight +
                spread_penalty +
                accel_penalty
            )
            
            risk_components.append(step_risk)
        
        # Total path risk (integral approximation)
        total_risk = sum(risk_components)
        
        # Average per step
        avg_risk = total_risk / len(path) if path else 0.0
        
        return avg_risk

    def compute_s_hft(self, path: List[Dict], hft_signals: Dict[str, float]) -> float:
        """
        Compute optional order-book cost S_HFT.

        Lower cost means the depth book agrees with the path direction. Book
        inversion is treated as a circuit-breaker-sized penalty, not alpha.
        """
        if not path or not hft_signals:
            return 0.0

        first_price = float(path[0].get('price', 0.0) or 0.0)
        last_price = float(path[-1].get('price', first_price) or first_price)
        if first_price <= 0:
            trajectory_signal = 0.0
        else:
            trajectory_signal = float(np.tanh((last_price - first_price) / first_price * 10_000.0))

        depth_signal = float(hft_signals.get('depth_imbalance', 0.0))
        pressure_ratio = float(hft_signals.get('pressure_ratio', 1.0) or 1.0)
        pressure_signal = float(np.tanh(np.log(max(pressure_ratio, 1e-9))))

        microprice = float(hft_signals.get('enhanced_microprice', first_price) or first_price)
        microprice_signal = 0.0
        if first_price > 0:
            microprice_signal = float(np.tanh((microprice - first_price) / first_price * 10_000.0))

        layering = abs(float(hft_signals.get('layering_score', 0.0)))
        iceberg = max(0.0, float(hft_signals.get('iceberg_probability', 0.0)))
        inversion = max(0.0, float(hft_signals.get('book_inversion', 0.0)))

        cfg = self.config
        directional_cost = (
            cfg.hft_depth_weight * abs(depth_signal - trajectory_signal) +
            cfg.hft_pressure_weight * abs(pressure_signal - trajectory_signal) +
            cfg.hft_microprice_weight * abs(microprice_signal - trajectory_signal)
        )
        risk_cost = (
            cfg.hft_layering_weight * layering +
            cfg.hft_iceberg_weight * iceberg +
            cfg.hft_inversion_penalty * inversion
        )
        return float(directional_cost + risk_cost)
    
    def compute_full_action(self,
                           path: List[Dict],
                           microstate: Dict,
                           weights: Dict[str, float]) -> Dict[str, float]:
        """
        Compute complete action functional S[γ] with all components.
        
        S[γ] = w_L·S_L + w_T·S_T + w_E·S_E + w_R·S_R
        
        Args:
            path: Path steps with microstructure fields
            microstate: Current MicroState dict
            weights: Component weights {'L': 0.5, 'T': 0.3, 'E': 0.1, 'R': 0.1}
        
        Returns:
            Dict with individual components and total action
        """
        # Extract data from microstate
        liquidity_zones = microstate.get('ict_geometry', {}).get('liquidity_zones', [])
        fvgs = microstate.get('ict_geometry', {}).get('fvgs', [])
        current_session = microstate.get('ict_geometry', {}).get('current_session', 'ny')
        in_kill_zone = microstate.get('ict_geometry', {}).get('kill_zone', False)
        
        # Compute individual components
        s_l = self.compute_s_liquidity(path, liquidity_zones, fvgs)
        s_t = self.compute_s_time(path, current_session, in_kill_zone=in_kill_zone)
        
        # For entry cost, we need entry point data
        if path:
            entry_step = path[0]
            entry_price = entry_step.get('price', 0.0)
            fvg_mid = entry_step.get('fvg_midpoint', entry_price)
            fib_level = entry_step.get('fib_level', entry_price)
            ofi_at = entry_step.get('ofi', 0.0)
            ofi_prev = path[0].get('ofi', 0.0) if len(path) > 0 else ofi_at
            
            s_e = self.compute_s_entry(entry_price, fvg_mid, fib_level, ofi_at, ofi_prev)
        else:
            s_e = 0.0
        
        s_r = self.compute_s_risk(path)
        hft_signals = microstate.get('hft_signals') or microstate.get('market_state', {}).get('hft_signals', {})
        has_hft = bool(hft_signals)
        s_hft = self.compute_s_hft(path, hft_signals) if has_hft else 0.0
        
        # Weighted total
        w_l = weights.get('L', 0.5)
        w_t = weights.get('T', 0.3)
        w_e = weights.get('E', 0.1)
        w_r = weights.get('R', 0.1)
        w_hft = weights.get('HFT', self.config.hft_action_weight)
        
        total_action = (
            w_l * s_l +
            w_t * s_t +
            w_e * s_e +
            w_r * s_r
        )
        if has_hft:
            total_action += w_hft * s_hft
        
        result = {
            'S_L': s_l,
            'S_T': s_t,
            'S_E': s_e,
            'S_R': s_r,
            'total_action': total_action,
            'weights': weights,
        }
        if has_hft:
            result['S_HFT'] = s_hft
            result['w_HFT'] = w_hft
        return result
    
    def _compute_fvg_bonus(self, price: float, fvgs: List[Dict]) -> float:
        """
        Compute FVG bonus factor for a price point.
        
        Inside FVG = low resistance (bonus < 1.0)
        Outside FVG = high resistance (bonus > 1.0)
        """
        for fvg in fvgs:
            top = fvg.get('top', float('inf'))
            bottom = fvg.get('bottom', float('-inf'))
            
            if bottom <= price <= top:
                return self.config.fvg_bonus_inside
        
        return self.config.fvg_bonus_outside
    
    def _detect_ofi_trigger(self, ofi_before: float, ofi_at: float) -> bool:
        """
        Detect OFI sign flip (flow confirmation) at entry.
        
        Returns True if OFI changed sign or crossed threshold.
        """
        threshold = self.config.ofi_trigger_threshold
        
        # Sign flip detection
        if ofi_before * ofi_at < 0:
            # Sign changed
            return abs(ofi_at) > threshold
        
        # Strong momentum in same direction
        if abs(ofi_at) > threshold and abs(ofi_at) > abs(ofi_before):
            return True
        
        return False
