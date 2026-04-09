"""
minkowski_adapter.py — Minkowski market bridge

4-object market theorem: S_market = (M, g, H, Π)
- M = bulk manifold (price-time)
- g = lawful transport/connection (metric)
- H = boundary projector (Hamiltonian)
- Π = witness surface (measurement interface)

Transforms raw OHLCV → operator space
"""

import numpy as np
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from datetime import datetime


@dataclass
class MarketTuple:
    """4-object market theorem: S_market = (M, g, H, Π)"""
    M: Dict  # Bulk manifold
    g: Dict  # Metric tensor
    H: Dict  # Hamiltonian boundary
    Pi: Dict  # Witness surface Π
    
    def to_dict(self) -> Dict:
        return {
            "M": self.M,
            "g": self.g,
            "H": self.H,
            "Pi": self.Pi
        }


class MinkowskiAdapter:
    """
    Minkowski market bridge: OHLCV → (M, g, H, Π)
    
    Minkowski metric in 2D (price, time):
    ds² = -c²dt² + dx²
    where c = characteristic price velocity
    """
    
    def __init__(self, light_speed: float = 1.0):
        self.c = light_speed  # Characteristic price velocity
        
    def transform(self, ohlcv_data: List[Dict]) -> MarketTuple:
        """
        Transform raw OHLCV to 4-object market tuple
        
        Args:
            ohlcv_data: List of {open, high, low, close, volume, timestamp}
        
        Returns:
            MarketTuple: (M, g, H, Π)
        """
        if not ohlcv_data:
            return self._empty_tuple()
        
        # M: Bulk manifold - price-time embedding
        M = self._compute_bulk_manifold(ohlcv_data)
        
        # g: Metric tensor - Minkowski metric on manifold
        g = self._compute_metric(ohlcv_data)
        
        # H: Hamiltonian boundary - energy landscape
        H = self._compute_hamiltonian_boundary(ohlcv_data)
        
        # Π: Witness surface - measurement interface
        Pi = self._compute_witness_surface(ohlcv_data)
        
        return MarketTuple(M=M, g=g, H=H, Pi=Pi)
    
    def _compute_bulk_manifold(self, data: List[Dict]) -> Dict:
        """M: Bulk manifold - price-time coordinates"""
        prices = [d["close"] for d in data]
        times = [d.get("timestamp", i) for i, d in enumerate(data)]
        volumes = [d.get("volume", 0) for d in data]
        
        # Proper time along worldline
        proper_times = []
        for i in range(1, len(times)):
            dt = times[i] - times[i-1]
            dx = prices[i] - prices[i-1]
            # Minkowski interval: ds² = c²dt² - dx²
            ds_squared = (self.c * dt)**2 - dx**2
            proper_times.append(np.sqrt(abs(ds_squared)))
        
        return {
            "coordinates": list(zip(times, prices)),
            "prices": prices,
            "volumes": volumes,
            "proper_times": proper_times,
            "dimension": 2,
            "topology": "price_time_cylinder"
        }
    
    def _compute_metric(self, data: List[Dict]) -> Dict:
        """g: Minkowski metric tensor components"""
        prices = [d["close"] for d in data]
        
        # Compute metric components
        if len(prices) < 2:
            return {"g_tt": -1, "g_xx": 1, "g_tx": 0}
        
        # Price velocity (characteristic)
        velocities = [abs(prices[i] - prices[i-1]) for i in range(1, len(prices))]
        avg_velocity = np.mean(velocities) if velocities else 0.001
        
        # Minkowski metric: diag(-c², 1)
        g_tt = -(self.c ** 2)  # Time-time component
        g_xx = 1.0              # Price-price component
        g_tx = 0.0              # Off-diagonal (assume orthogonal)
        
        # Connection coefficients (Christoffel symbols)
        # Γᵗ_tx = 0, Γˣ_tt = 0 for flat Minkowski
        
        return {
            "g_tt": g_tt,
            "g_xx": g_xx,
            "g_tx": g_tx,
            "signature": (-1, 1),  # Lorentzian signature
            "curvature": 0.0,        # Flat space
            "connection": {
                "gamma_t_tx": 0.0,
                "gamma_x_tt": 0.0
            },
            "characteristic_velocity": avg_velocity
        }
    
    def _compute_hamiltonian_boundary(self, data: List[Dict]) -> Dict:
        """H: Hamiltonian boundary - energy constraints"""
        highs = [d["high"] for d in data]
        lows = [d["low"] for d in data]
        closes = [d["close"] for d in data]
        volumes = [d.get("volume", 0) for d in data]
        
        # Volatility as energy
        ranges = [h - l for h, l in zip(highs, lows)]
        avg_range = np.mean(ranges) if ranges else 0
        
        # Volume-weighted price
        if sum(volumes) > 0:
            vwap = sum(c * v for c, v in zip(closes, volumes)) / sum(volumes)
        else:
            vwap = np.mean(closes) if closes else 0
        
        # Momentum (kinetic energy)
        if len(closes) >= 2:
            momentum = abs(closes[-1] - closes[0]) / len(closes)
        else:
            momentum = 0
        
        return {
            "total_energy": avg_range + momentum,
            "kinetic": momentum,
            "potential": avg_range,
            "vwap": vwap,
            "support": min(lows) if lows else 0,
            "resistance": max(highs) if highs else 0,
            "volume_energy": sum(volumes) if volumes else 0
        }
    
    def _compute_witness_surface(self, data: List[Dict]) -> Dict:
        """Π: Witness surface - measurement/observation interface"""
        closes = [d["close"] for d in data]
        
        # Observable properties
        observable = {
            "current_price": closes[-1] if closes else 0,
            "price_change": (closes[-1] - closes[0]) / closes[0] if closes and closes[0] != 0 else 0,
            "volatility": np.std(closes) if len(closes) > 1 else 0,
            "trend_direction": "up" if closes[-1] > closes[0] else "down" if closes else "neutral"
        }
        
        # Measurement projectors (simplified)
        projectors = {
            "price_level": {
                "current": closes[-1] if closes else 0,
                "resolution": observable["volatility"] * 0.1
            },
            "momentum": {
                "value": observable["price_change"],
                "confidence": 1.0 - min(abs(observable["price_change"]), 1.0)
            }
        }
        
        return {
            "observable": observable,
            "projectors": projectors,
            "measurement_basis": "price_momentum",
            "uncertainty": observable["volatility"]
        }
    
    def _empty_tuple(self) -> MarketTuple:
        """Return empty market tuple"""
        return MarketTuple(
            M={"dimension": 0},
            g={"signature": (0, 0)},
            H={"total_energy": 0},
            Pi={"observable": {}}
        )
    
    def get_market_state(self, market_tuple: MarketTuple) -> Dict:
        """Extract flat market state from tuple for operator consumption"""
        return {
            "prices": market_tuple.M.get("prices", []),
            "highs": [market_tuple.H.get("resistance", 0)] * len(market_tuple.M.get("prices", [])),
            "lows": [market_tuple.H.get("support", 0)] * len(market_tuple.M.get("prices", [])),
            "close": market_tuple.Pi.get("observable", {}).get("current_price", 0),
            "volume": market_tuple.M.get("volumes", []),
            "vwap": market_tuple.H.get("vwap", 0),
            "volatility": market_tuple.Pi.get("uncertainty", 0),
            "regime": market_tuple.Pi.get("observable", {}).get("trend_direction", "neutral")
        }


class MarketDataAdapter:
    """
    High-level adapter: raw OHLCV → market state for operators
    """
    
    def __init__(self):
        self.minkowski = MinkowskiAdapter()
        
    def adapt(self, ohlcv_data: List[Dict]) -> Dict:
        """
        Full adaptation pipeline:
        OHLCV → Minkowski tuple → Flat market state
        """
        # Transform to 4-object tuple
        market_tuple = self.minkowski.transform(ohlcv_data)
        
        # Extract flat state
        market_state = self.minkowski.get_market_state(market_tuple)
        
        # Add tuple metadata
        market_state["_tuple"] = market_tuple.to_dict()
        market_state["_timestamp"] = datetime.now().isoformat()
        
        return market_state
    
    def get_session(self, timestamp: Optional[datetime] = None) -> str:
        """Determine trading session from timestamp"""
        if timestamp is None:
            timestamp = datetime.now()
        
        hour = timestamp.hour
        
        # Simplified session detection (UTC)
        if 7 <= hour < 11:
            return "london"
        elif 12 <= hour < 16:
            return "ny_am"
        elif 16 <= hour < 20:
            return "ny_pm"
        elif 0 <= hour < 4:
            return "asia"
        else:
            return "neutral"
