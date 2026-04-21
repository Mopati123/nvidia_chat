"""
tick_processor.py - Tick-level microstructure computation.

Computes Order Flow Imbalance (OFI), microprice, spread dynamics,
tick velocity and acceleration from raw market tick data.
"""

import numpy as np
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from collections import deque


@dataclass
class Tick:
    """Single market tick"""
    timestamp: float
    bid: float
    ask: float
    bid_volume: float
    ask_volume: float
    price: Optional[float] = None  # Last trade price if available
    volume: Optional[float] = None  # Last trade volume
    
    @property
    def mid(self) -> float:
        """Mid price"""
        return (self.bid + self.ask) / 2
    
    @property
    def spread(self) -> float:
        """Bid-ask spread"""
        return self.ask - self.bid


class OFICalculator:
    """
    Order Flow Imbalance (OFI) calculator.
    
    OFI = Δ(bid_volume) - Δ(ask_volume)
    
    Positive OFI = buying pressure
    Negative OFI = selling pressure
    """
    
    def __init__(self, window_size: int = 10):
        self.window_size = window_size
        self.ticks: deque = deque(maxlen=window_size)
        self.ofi_history: deque = deque(maxlen=window_size)
        
    def process_tick(self, tick: Tick) -> float:
        """
        Process new tick and compute OFI.
        
        Returns:
            OFI value (positive = buying pressure)
        """
        if len(self.ticks) == 0:
            self.ticks.append(tick)
            return 0.0
        
        prev_tick = self.ticks[-1]
        
        # Compute volume changes
        delta_bid_vol = tick.bid_volume - prev_tick.bid_volume
        delta_ask_vol = tick.ask_volume - prev_tick.ask_volume
        
        # OFI calculation
        ofi = delta_bid_vol - delta_ask_vol
        
        # Store
        self.ticks.append(tick)
        self.ofi_history.append(ofi)
        
        return ofi
    
    @property
    def cumulative_ofi(self) -> float:
        """Cumulative OFI over window"""
        return sum(self.ofi_history) if self.ofi_history else 0.0
    
    @property
    def normalized_ofi(self) -> float:
        """OFI normalized by volume"""
        if not self.ofi_history:
            return 0.0
        total_vol = sum(t.bid_volume + t.ask_volume for t in self.ticks)
        return self.cumulative_ofi / (total_vol + 1e-8)


class TickProcessor:
    """
    Main tick processor that computes all microstructure fields.
    
    Fields computed:
    - OFI (Order Flow Imbalance)
    - Microprice (volume-weighted fair price)
    - Spread dynamics (spread and rate of change)
    - Tick velocity (price rate of change)
    - Tick acceleration (velocity rate of change)
    """
    
    def __init__(self, window_size: int = 20):
        self.window_size = window_size
        self.ticks: deque = deque(maxlen=window_size)
        self.ofi_calc = OFICalculator(window_size=window_size)
        
        # History for derivatives
        self.velocities: deque = deque(maxlen=window_size)
        self.spread_history: deque = deque(maxlen=window_size)
        
    def process_tick(self, tick_data: Dict) -> Dict:
        """
        Process raw tick data and compute all microstructure fields.
        
        Args:
            tick_data: Dict with keys 'timestamp', 'bid', 'ask', 
                      'bid_volume', 'ask_volume', optionally 'price', 'volume'
        
        Returns:
            Dict with computed microstructure fields
        """
        tick = Tick(
            timestamp=tick_data['timestamp'],
            bid=tick_data['bid'],
            ask=tick_data['ask'],
            bid_volume=tick_data.get('bid_volume', 0),
            ask_volume=tick_data.get('ask_volume', 0),
            price=tick_data.get('price'),
            volume=tick_data.get('volume')
        )
        
        # Compute OFI
        ofi = self.ofi_calc.process_tick(tick)
        
        # Compute microprice
        microprice = self._compute_microprice(tick)
        
        # Compute spread dynamics
        spread, spread_velocity = self._compute_spread_dynamics(tick)
        
        # Compute tick velocity and acceleration
        velocity, acceleration = self._compute_velocity_acceleration(tick)
        
        # Store tick
        self.ticks.append(tick)
        
        return {
            'timestamp': tick.timestamp,
            'bid': tick.bid,
            'ask': tick.ask,
            'mid': tick.mid,
            'spread': spread,
            'spread_velocity': spread_velocity,
            'microprice': microprice,
            'ofi': ofi,
            'cumulative_ofi': self.ofi_calc.cumulative_ofi,
            'normalized_ofi': self.ofi_calc.normalized_ofi,
            'velocity': velocity,
            'acceleration': acceleration,
            'buying_pressure': ofi > 0,
            'selling_pressure': ofi < 0,
        }
    
    def _compute_microprice(self, tick: Tick) -> float:
        """
        Compute volume-weighted microprice.
        
        Microprice = (bid * ask_vol + ask * bid_vol) / (bid_vol + ask_vol)
        
        This indicates where price 'wants' to go based on order book imbalance.
        """
        total_volume = tick.bid_volume + tick.ask_volume
        if total_volume == 0:
            return tick.mid
        
        return (tick.bid * tick.ask_volume + tick.ask * tick.bid_volume) / total_volume
    
    def _compute_spread_dynamics(self, tick: Tick) -> Tuple[float, float]:
        """
        Compute spread and its rate of change.
        
        Returns:
            (current_spread, spread_velocity)
        """
        current_spread = tick.spread
        
        # Compute spread velocity
        spread_velocity = 0.0
        if len(self.spread_history) > 0:
            prev_spread = self.spread_history[-1]
            dt = 1.0  # Assuming uniform time steps, can be adjusted
            spread_velocity = (current_spread - prev_spread) / dt
        
        self.spread_history.append(current_spread)
        
        return current_spread, spread_velocity
    
    def _compute_velocity_acceleration(self, tick: Tick) -> Tuple[float, float]:
        """
        Compute tick velocity and acceleration.
        
        v = Δprice / Δt
        a = Δv / Δt
        """
        velocity = 0.0
        acceleration = 0.0
        
        if len(self.ticks) > 0:
            prev_tick = self.ticks[-1]
            dt = tick.timestamp - prev_tick.timestamp
            
            if dt > 0:
                # Velocity
                price_change = tick.mid - prev_tick.mid
                velocity = price_change / dt
                self.velocities.append(velocity)
                
                # Acceleration
                if len(self.velocities) >= 2:
                    prev_velocity = list(self.velocities)[-2]
                    acceleration = (velocity - prev_velocity) / dt
        
        return velocity, acceleration
    
    def get_flow_bias(self) -> str:
        """
        Get overall flow bias based on OFI history.
        
        Returns:
            'buying' | 'selling' | 'neutral'
        """
        if not self.ofi_calc.ofi_history:
            return 'neutral'
        
        cum_ofi = self.ofi_calc.cumulative_ofi
        
        if cum_ofi > 0.5:
            return 'buying'
        elif cum_ofi < -0.5:
            return 'selling'
        else:
            return 'neutral'
    
    def get_microstructure_summary(self) -> Dict:
        """
        Get summary of current microstructure state.
        """
        if not self.ticks:
            return {}
        
        latest = self.ticks[-1]
        
        return {
            'last_price': latest.mid,
            'spread': latest.spread,
            'ofi_signal': self.get_flow_bias(),
            'cumulative_ofi': self.ofi_calc.cumulative_ofi,
            'pressure_strength': abs(self.ofi_calc.normalized_ofi),
            'tick_count': len(self.ticks),
        }
