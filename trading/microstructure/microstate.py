"""
microstate.py - Microstructure state container.

Defines dataclasses for unified microstructure state that combines
tick-level flow data with ICT geometry for the complete market picture.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
from datetime import datetime
import numpy as np


@dataclass
class MicroStructure:
    """
    Pure microstructure fields from tick data.
    """
    # Core tick fields
    timestamp: float
    bid: float
    ask: float
    mid: float
    spread: float
    
    # Flow fields
    ofi: float = 0.0  # Order Flow Imbalance
    cumulative_ofi: float = 0.0
    normalized_ofi: float = 0.0
    microprice: float = 0.0
    
    # Dynamics
    velocity: float = 0.0
    acceleration: float = 0.0
    spread_velocity: float = 0.0
    
    # Derived signals
    buying_pressure: bool = False
    selling_pressure: bool = False
    flow_bias: str = 'neutral'  # 'buying' | 'selling' | 'neutral'
    
    @property
    def pressure_strength(self) -> float:
        """Strength of buying/selling pressure (0 to 1)"""
        return abs(self.normalized_ofi)


@dataclass
class ICTGeometry:
    """
    ICT/SMC geometry structure.
    """
    # Liquidity
    liquidity_zones: List[Dict] = field(default_factory=list)
    equal_highs: List[float] = field(default_factory=list)
    equal_lows: List[float] = field(default_factory=list)
    
    # Fair Value Gaps
    fvgs: List[Dict] = field(default_factory=list)
    
    # Market Structure
    bos_points: List[Dict] = field(default_factory=list)  # Break of Structure
    choch_points: List[Dict] = field(default_factory=list)  # Change of Character
    
    # Session/Time
    current_session: str = ''  # 'London', 'NY', 'Asia', etc.
    kill_zone: bool = False
    htf_bias: str = 'neutral'  # 'bullish' | 'bearish' | 'neutral'


@dataclass
class MicroState:
    """
    Unified microstructure state.
    
    Combines tick-level microstructure with ICT geometry
    for complete market picture used in path generation.
    """
    # Identity
    symbol: str
    timestamp: float
    
    # Microstructure (tick-level)
    microstructure: MicroStructure
    
    # Geometry (ICT structure)
    ict_geometry: ICTGeometry
    
    # Flow field (computed forces)
    flow_forces: Dict[str, float] = field(default_factory=dict)
    
    # Metadata
    source: str = ''  # 'MT5', 'Deriv', 'TradingView'
    timeframe: str = 'M1'
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            'symbol': self.symbol,
            'timestamp': self.timestamp,
            'microstructure': {
                'bid': self.microstructure.bid,
                'ask': self.microstructure.ask,
                'mid': self.microstructure.mid,
                'spread': self.microstructure.spread,
                'ofi': self.microstructure.ofi,
                'microprice': self.microstructure.microprice,
                'velocity': self.microstructure.velocity,
                'acceleration': self.microstructure.acceleration,
                'flow_bias': self.microstructure.flow_bias,
                'pressure_strength': self.microstructure.pressure_strength,
            },
            'ict_geometry': {
                'liquidity_zones': len(self.ict_geometry.liquidity_zones),
                'fvgs': len(self.ict_geometry.fvgs),
                'session': self.ict_geometry.current_session,
                'htf_bias': self.ict_geometry.htf_bias,
            },
            'flow_forces': self.flow_forces,
        }
    
    @classmethod
    def from_market_data(cls, 
                         symbol: str,
                         micro_data: Dict,
                         ict_data: Dict,
                         timestamp: Optional[float] = None) -> 'MicroState':
        """
        Create MicroState from processed market data.
        
        Args:
            symbol: Trading symbol
            micro_data: Output from TickProcessor
            ict_data: ICT geometry data
            timestamp: Optional timestamp override
        """
        ts = timestamp or datetime.now().timestamp()
        
        # Create microstructure
        micro = MicroStructure(
            timestamp=micro_data.get('timestamp', ts),
            bid=micro_data.get('bid', 0.0),
            ask=micro_data.get('ask', 0.0),
            mid=micro_data.get('mid', 0.0),
            spread=micro_data.get('spread', 0.0),
            ofi=micro_data.get('ofi', 0.0),
            cumulative_ofi=micro_data.get('cumulative_ofi', 0.0),
            normalized_ofi=micro_data.get('normalized_ofi', 0.0),
            microprice=micro_data.get('microprice', 0.0),
            velocity=micro_data.get('velocity', 0.0),
            acceleration=micro_data.get('acceleration', 0.0),
            spread_velocity=micro_data.get('spread_velocity', 0.0),
            buying_pressure=micro_data.get('buying_pressure', False),
            selling_pressure=micro_data.get('selling_pressure', False),
            flow_bias=micro_data.get('ofi_signal', 'neutral'),
        )
        
        # Create ICT geometry
        ict = ICTGeometry(
            liquidity_zones=ict_data.get('liquidity_zones', []),
            equal_highs=ict_data.get('equal_highs', []),
            equal_lows=ict_data.get('equal_lows', []),
            fvgs=ict_data.get('fvgs', []),
            bos_points=ict_data.get('bos_points', []),
            choch_points=ict_data.get('choch_points', []),
            current_session=ict_data.get('current_session', ''),
            kill_zone=ict_data.get('kill_zone', False),
            htf_bias=ict_data.get('htf_bias', 'neutral'),
        )
        
        return cls(
            symbol=symbol,
            timestamp=ts,
            microstructure=micro,
            ict_geometry=ict,
        )
    
    def get_action_inputs(self) -> Dict[str, float]:
        """
        Get inputs for action functional computation.
        
        Returns dict with all fields needed for S_L, S_T, S_E, S_R.
        """
        return {
            # For S_L (Liquidity)
            'ofi': self.microstructure.ofi,
            'microprice': self.microstructure.microprice,
            'pressure_strength': self.microstructure.pressure_strength,
            'liquidity_count': len(self.ict_geometry.liquidity_zones),
            'fvg_count': len(self.ict_geometry.fvgs),
            
            # For S_T (Time)
            'session': self.ict_geometry.current_session,
            'kill_zone': 1.0 if self.ict_geometry.kill_zone else 0.0,
            
            # For S_E (Entry)
            'velocity': self.microstructure.velocity,
            'spread': self.microstructure.spread,
            
            # For S_R (Risk)
            'acceleration': self.microstructure.acceleration,
            'spread_velocity': self.microstructure.spread_velocity,
        }
