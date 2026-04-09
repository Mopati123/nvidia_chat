"""
operator_registry.py — 18-operator registry (1:1 with equations)

Each operator declares:
- META dict (validated against schema)
- Domain/codomain
- Invariants
- Coupling interfaces
- Quantum semantics block

ICT/SMC Trading Concepts as Quantum Operators:
01-07: Potential operators (contribute to Hamiltonian)
08-17: Projector/constraint operators (Π)
18: Measurement operator (ℳ)
"""

import numpy as np
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass
from enum import Enum


class OperatorType(Enum):
    """Operator classification"""
    POTENTIAL = "potential"      # Contributes to H_market
    PROJECTOR = "projector"      # Constraint operator Π
    MEASUREMENT = "measurement"  # Observable extraction ℳ


@dataclass
class OperatorMeta:
    """Operator metadata contract"""
    id: int
    name: str
    equation: str
    type: OperatorType
    domain: str
    codomain: str
    invariants: List[str]
    interfaces: Dict[str, str]
    quantum_semantics: Dict[str, Any]
    
    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "name": self.name,
            "equation": self.equation,
            "type": self.type.value,
            "domain": self.domain,
            "codomain": self.codomain,
            "invariants": self.invariants,
            "interfaces": self.interfaces,
            "quantum_semantics": self.quantum_semantics
        }


class ICTOperator:
    """Base class for ICT/SMC trading operators"""
    
    def __init__(self, meta: OperatorMeta):
        self.meta = meta
        self._compute: Optional[Callable] = None
        
    def bind_compute(self, fn: Callable):
        """Bind the operator's computation function"""
        self._compute = fn
        
    def apply(self, market_data: Dict, state: Dict) -> float:
        """Apply operator to market state, return score"""
        if self._compute is None:
            return 0.0
        return self._compute(market_data, state)
    
    def get_contribution(self) -> Dict:
        """Get operator contribution to Hamiltonian"""
        return {
            "operator_id": self.meta.id,
            "name": self.meta.name,
            "equation": self.meta.equation,
            "weight": 1.0  # Default weight
        }


class OperatorRegistry:
    """
    18-operator registry for ICT/SMC trading analysis.
    Maps ICT concepts to quantum operators.
    """
    
    def __init__(self):
        self.operators: Dict[str, ICTOperator] = {}
        self._initialize_operators()
        
    def _initialize_operators(self):
        """Initialize all 18 operators with META declarations"""
        
        # 01: Kinetic - T(p;σ) - Momentum/velocity
        op01 = ICTOperator(OperatorMeta(
            id=1,
            name="kinetic",
            equation="T(p;σ)",
            type=OperatorType.POTENTIAL,
            domain="price_momentum",
            codomain="energy",
            invariants=["conservation", "differentiability"],
            interfaces={"input": "price_series", "output": "velocity_field"},
            quantum_semantics={"hermitian": True, "observable": True}
        ))
        op01.bind_compute(self._compute_kinetic)
        self.operators["kinetic"] = op01
        
        # 02: Liquidity Pool - V_LP(x) - Resting liquidity attraction
        op02 = ICTOperator(OperatorMeta(
            id=2,
            name="liquidity_pool",
            equation="V_LP(x)",
            type=OperatorType.POTENTIAL,
            domain="price_levels",
            codomain="potential_energy",
            invariants=["attractor", "volume_weighted"],
            interfaces={"input": "order_book", "output": "attraction_field"},
            quantum_semantics={"hermitian": True, "local": True}
        ))
        op02.bind_compute(self._compute_liquidity_pool)
        self.operators["liquidity_pool"] = op02
        
        # 03: Order Block - V_OB(x) - Institutional footprint
        op03 = ICTOperator(OperatorMeta(
            id=3,
            name="order_block",
            equation="V_OB(x)",
            type=OperatorType.POTENTIAL,
            domain="candle_structure",
            codomain="potential_energy",
            invariants=["imbalance", "mitigation"],
            interfaces={"input": "ohlcv", "output": "block_zones"},
            quantum_semantics={"hermitian": True, "non_local": False}
        ))
        op03.bind_compute(self._compute_order_block)
        self.operators["order_block"] = op03
        
        # 04: Fair Value Gap - V_FVG(x) - Imbalance/inefficiency
        op04 = ICTOperator(OperatorMeta(
            id=4,
            name="fvg",
            equation="V_FVG(x)",
            type=OperatorType.POTENTIAL,
            domain="price_gaps",
            codomain="potential_energy",
            invariants=["three_candle", "unmitigated"],
            interfaces={"input": "ohlcv", "output": "gap_zones"},
            quantum_semantics={"hermitian": True, "projection": True}
        ))
        op04.bind_compute(self._compute_fvg)
        self.operators["fvg"] = op04
        
        # 05: Macro Time - V_macro(t) - Session-dependent potential
        op05 = ICTOperator(OperatorMeta(
            id=5,
            name="macro_time",
            equation="V_macro(t)",
            type=OperatorType.POTENTIAL,
            domain="temporal",
            codomain="potential_energy",
            invariants=["session_cyclical", "killzones"],
            interfaces={"input": "timestamp", "output": "time_weight"},
            quantum_semantics={"hermitian": True, "time_dependent": True}
        ))
        op05.bind_compute(self._compute_macro_time)
        self.operators["macro_time"] = op05
        
        # 06: Price Delivery - V_PD(x) - Algorithmic delivery
        op06 = ICTOperator(OperatorMeta(
            id=6,
            name="price_delivery",
            equation="V_PD(x)",
            type=OperatorType.POTENTIAL,
            domain="price_trajectory",
            codomain="potential_energy",
            invariants=["draw_to_liquidity", "premium_discount"],
            interfaces={"input": "price_path", "output": "delivery_vector"},
            quantum_semantics={"hermitian": True, "path_dependent": True}
        ))
        op06.bind_compute(self._compute_price_delivery)
        self.operators["price_delivery"] = op06
        
        # 07: Regime - V_regime(x,t) - Trend/range/reversal
        op07 = ICTOperator(OperatorMeta(
            id=7,
            name="regime",
            equation="V_regime(x,t)",
            type=OperatorType.POTENTIAL,
            domain="market_structure",
            codomain="classification",
            invariants=["bos_choch", "trend_alignment"],
            interfaces={"input": "swings", "output": "regime_label"},
            quantum_semantics={"hermitian": False, "categorical": True}
        ))
        op07.bind_compute(self._compute_regime)
        self.operators["regime"] = op07
        
        # 08: Session - Π_session - Trading hours projector
        op08 = ICTOperator(OperatorMeta(
            id=8,
            name="session",
            equation="Π_session",
            type=OperatorType.PROJECTOR,
            domain="temporal",
            codomain="{0,1}",
            invariants=["idempotent", "self_adjoint"],
            interfaces={"input": "timestamp", "output": "legality"},
            quantum_semantics={"idempotent": True, "self_adjoint": True, "Π²": "Π"}
        ))
        op08.bind_compute(self._compute_session)
        self.operators["session"] = op08
        
        # 09: Risk - Π_risk - Exposure limit projector
        op09 = ICTOperator(OperatorMeta(
            id=9,
            name="risk",
            equation="Π_risk",
            type=OperatorType.PROJECTOR,
            domain="position_space",
            codomain="{0,1}",
            invariants=["idempotent", "self_adjoint", "position_sizing"],
            interfaces={"input": "proposed_position", "output": "admissibility"},
            quantum_semantics={"idempotent": True, "self_adjoint": True}
        ))
        op09.bind_compute(self._compute_risk)
        self.operators["risk"] = op09
        
        # 10: Sailing Lane - L(n) = L₀·α^(n-1) - Multi-leg execution
        op10 = ICTOperator(OperatorMeta(
            id=10,
            name="sailing_lane",
            equation="L(n) = L₀·α^(n-1)",
            type=OperatorType.PROJECTOR,
            domain="execution_sequence",
            codomain="leg_admissibility",
            invariants=["geometric_decay", "multiplicity_m", "max_legs"],
            interfaces={"input": "leg_number", "output": "lane_position"},
            quantum_semantics={"geometric": True, "recursive": True}
        ))
        op10.bind_compute(self._compute_sailing_lane)
        self.operators["sailing_lane"] = op10
        
        # 11: Sweep - S_liq(x) - Liquidity sweep detection
        op11 = ICTOperator(OperatorMeta(
            id=11,
            name="sweep",
            equation="S_liq(x)",
            type=OperatorType.POTENTIAL,
            domain="price_action",
            codomain="sweep_signal",
            invariants=[["stop_hunt", "inducement", "liquidity_grab"]],
            interfaces={"input": "candle_pattern", "output": "sweep_detected"},
            quantum_semantics={"impulsive": True, "transient": True}
        ))
        op11.bind_compute(self._compute_sweep)
        self.operators["sweep"] = op11
        
        # 12: Displacement - D(x,t) - Impulsive movement
        op12 = ICTOperator(OperatorMeta(
            id=12,
            name="displacement",
            equation="D(x,t)",
            type=OperatorType.POTENTIAL,
            domain="candle_structure",
            codomain="momentum_signal",
            invariants=[["large_body", "imbalance", "delivery"]],
            interfaces={"input": "candle", "output": "displacement_strength"},
            quantum_semantics={"impulsive": True, "irreversible": False}
        ))
        op12.bind_compute(self._compute_displacement)
        self.operators["displacement"] = op12
        
        # 13: Breaker Block - BB(x) - Failed order block
        op13 = ICTOperator(OperatorMeta(
            id=13,
            name="breaker_block",
            equation="BB(x)",
            type=OperatorType.POTENTIAL,
            domain="order_block_flip",
            codomain="reversal_zone",
            invariants=[["mitigation", "flip", "role_reversal"]],
            interfaces={"input": "ob_zone", "output": "breaker_signal"},
            quantum_semantics={"phase_transition": True, "hysteresis": True}
        ))
        op13.bind_compute(self._compute_breaker_block)
        self.operators["breaker_block"] = op13
        
        # 14: Mitigation - MB(x) - Return to unmitigated level
        op14 = ICTOperator(OperatorMeta(
            id=14,
            name="mitigation",
            equation="MB(x)",
            type=OperatorType.POTENTIAL,
            domain="price_return",
            codomain="reaction_zone",
            invariants=[["unmitigated", "balance", "rebalance"]],
            interfaces={"input": "price_level", "output": "mitigation_signal"},
            quantum_semantics={"restorative": True, "equilibrium_seeking": True}
        ))
        op14.bind_compute(self._compute_mitigation)
        self.operators["mitigation"] = op14
        
        # 15: Optimal Trade Entry - OTE(x) - Fibonacci confluence
        op15 = ICTOperator(OperatorMeta(
            id=15,
            name="ote",
            equation="OTE(x)",
            type=OperatorType.POTENTIAL,
            domain="fibonacci_retracement",
            codomain="entry_zone",
            invariants=[["0.62_0.79", "premium_discount", "confluence"]],
            interfaces={"input": "swing_range", "output": "ote_zone"},
            quantum_semantics={"interval_arithmetic": True, "nested": True}
        ))
        op15.bind_compute(self._compute_ote)
        self.operators["ote"] = op15
        
        # 16: Judas Swing - J(x,t) - False directional move
        op16 = ICTOperator(OperatorMeta(
            id=16,
            name="judas_swing",
            equation="J(x,t)",
            type=OperatorType.POTENTIAL,
            domain="session_open",
            codomain="trap_signal",
            invariants=["false_move", "liquidity_engineering", "reversal"],
            interfaces={"input": "session_price", "output": "judas_detected"},
            quantum_semantics=["deceptive", "contrarian", "transient"]
        ))
        op16.bind_compute(self._compute_judas)
        self.operators["judas_swing"] = op16
        
        # 17: Accumulation/Distribution - A(x,t) - Wyckoff phases
        op17 = ICTOperator(OperatorMeta(
            id=17,
            name="accumulation",
            equation="A(x,t)",
            type=OperatorType.POTENTIAL,
            domain="composite_volume",
            codomain="phase_classification",
            invariants=["schematic", "spring_upthrust", "volume_profile"],
            interfaces={"input": "price_volume", "output": "wyckoff_phase"},
            quantum_semantics=["composite", "volume_weighted", "slower"]
        ))
        op17.bind_compute(self._compute_accumulation)
        self.operators["accumulation"] = op17
        
        # 18: Projection - ⟨ψ|O|ψ⟩ - Observable readout
        op18 = ICTOperator(OperatorMeta(
            id=18,
            name="projection",
            equation="⟨ψ|O|ψ⟩",
            type=OperatorType.MEASUREMENT,
            domain="state_space",
            codomain="expectation_value",
            invariants=["linearity", "hermitian_observable", "real_eigenvalues"],
            interfaces={"input": "state_vector", "output": "measurement"},
            quantum_semantics=["measurement", "collapse", "expectation"]
        ))
        op18.bind_compute(self._compute_projection)
        self.operators["projection"] = op18
    
    # ============== OPERATOR COMPUTATIONS ==============
    
    def _compute_kinetic(self, market_data: Dict, state: Dict) -> float:
        """T(p;σ): Momentum/velocity operator"""
        prices = market_data.get("prices", [])
        if len(prices) < 2:
            return 0.0
        velocities = [prices[i] - prices[i-1] for i in range(1, len(prices))]
        return np.mean([abs(v) for v in velocities]) if velocities else 0.0
    
    def _compute_liquidity_pool(self, market_data: Dict, state: Dict) -> float:
        """V_LP(x): Resting liquidity attraction"""
        volume = market_data.get("volume", [])
        return np.mean(volume) if volume else 0.0
    
    def _compute_order_block(self, market_data: Dict, state: Dict) -> float:
        """V_OB(x): Institutional order block detection"""
        ohlc = market_data.get("ohlc", [])
        if not ohlc:
            return 0.0
        # Detect imbalance: strong close in one direction
        scores = []
        for candle in ohlc[-5:]:  # Last 5 candles
            body = abs(candle["close"] - candle["open"])
            range_ = candle["high"] - candle["low"]
            if range_ > 0:
                scores.append(body / range_)
        return np.mean(scores) if scores else 0.0
    
    def _compute_fvg(self, market_data: Dict, state: Dict) -> float:
        """V_FVG(x): Fair Value Gap detection"""
        ohlc = market_data.get("ohlc", [])
        if len(ohlc) < 3:
            return 0.0
        gaps = 0
        for i in range(len(ohlc) - 2):
            c1, c2, c3 = ohlc[i], ohlc[i+1], ohlc[i+2]
            # Bullish FVG: c2 low > c1 high and c3 low > c1 high
            if c2["low"] > c1["high"] and c3["low"] > c1["high"]:
                gaps += 1
            # Bearish FVG: c2 high < c1 low and c3 high < c1 low
            if c2["high"] < c1["low"] and c3["high"] < c1["low"]:
                gaps += 1
        return min(gaps * 0.3, 1.0)
    
    def _compute_macro_time(self, market_data: Dict, state: Dict) -> float:
        """V_macro(t): Session time weighting"""
        session = market_data.get("session", "neutral")
        weights = {"london": 1.0, "ny": 1.0, "asia": 0.7, "neutral": 0.5}
        return weights.get(session, 0.5)
    
    def _compute_price_delivery(self, market_data: Dict, state: Dict) -> float:
        """V_PD(x): Algorithmic price delivery"""
        highs = market_data.get("highs", [])
        lows = market_data.get("lows", [])
        if not highs or not lows:
            return 0.0
        range_ = max(highs) - min(lows)
        recent_range = max(highs[-5:]) - min(lows[-5:]) if len(highs) >= 5 else range_
        return recent_range / range_ if range_ > 0 else 0.0
    
    def _compute_regime(self, market_data: Dict, state: Dict) -> float:
        """V_regime(x,t): Market regime classification"""
        prices = market_data.get("prices", [])
        if len(prices) < 20:
            return 0.5  # Neutral
        
        # Simple trend detection
        short_ma = np.mean(prices[-5:])
        long_ma = np.mean(prices[-20:])
        
        if short_ma > long_ma * 1.02:
            return 1.0  # Trending up
        elif short_ma < long_ma * 0.98:
            return 0.0  # Trending down
        return 0.5  # Ranging
    
    def _compute_session(self, market_data: Dict, state: Dict) -> float:
        """Π_session: Session legality projector"""
        session = market_data.get("session", "")
        allowed = ["london", "ny", "asia"]
        return 1.0 if session in allowed else 0.0
    
    def _compute_risk(self, market_data: Dict, state: Dict) -> float:
        """Π_risk: Risk limit projector"""
        proposed_size = state.get("proposed_position_size", 0)
        max_size = state.get("max_position_size", 100)
        return 1.0 if proposed_size <= max_size else 0.0
    
    def _compute_sailing_lane(self, market_data: Dict, state: Dict) -> float:
        """L(n) = L₀·α^(n-1): Sailing lane multi-leg execution"""
        leg = state.get("current_leg", 1)
        max_legs = state.get("max_legs", 5)
        alpha = state.get("sailing_alpha", 0.8)
        L0 = state.get("sailing_L0", 1.0)
        
        if leg > max_legs:
            return 0.0
        
        position = L0 * (alpha ** (leg - 1))
        return position if position > 0.1 else 0.0
    
    def _compute_sweep(self, market_data: Dict, state: Dict) -> float:
        """S_liq(x): Liquidity sweep detection"""
        highs = market_data.get("highs", [])
        lows = market_data.get("lows", [])
        if len(highs) < 5 or len(lows) < 5:
            return 0.0
        
        # Check for sweep of recent high/low followed by reversal
        recent_high = max(highs[-5:-1])
        recent_low = min(lows[-5:-1])
        
        current_high = highs[-1]
        current_low = lows[-1]
        
        # High sweep + close back below
        if current_high > recent_high and market_data.get("close", 0) < recent_high:
            return 1.0
        # Low sweep + close back above
        if current_low < recent_low and market_data.get("close", 0) > recent_low:
            return 1.0
        return 0.0
    
    def _compute_displacement(self, market_data: Dict, state: Dict) -> float:
        """D(x,t): Displacement candle detection"""
        ohlc = market_data.get("ohlc", [])
        if not ohlc:
            return 0.0
        
        candle = ohlc[-1]
        body = abs(candle["close"] - candle["open"])
        range_ = candle["high"] - candle["low"]
        
        if range_ == 0:
            return 0.0
        
        body_ratio = body / range_
        # Large body = displacement
        return 1.0 if body_ratio > 0.7 else body_ratio
    
    def _compute_breaker_block(self, market_data: Dict, state: Dict) -> float:
        """BB(x): Breaker block (failed order block)"""
        ohlc = market_data.get("ohlc", [])
        if len(ohlc) < 3:
            return 0.0
        
        # Simplified: check for mitigation of previous structure
        c1, c2, c3 = ohlc[-3], ohlc[-2], ohlc[-1]
        
        # Bullish breaker: price takes out bearish OB low then reclaims
        if c1["close"] < c1["open"] and c2["low"] < c1["low"] and c3["close"] > c1["high"]:
            return 1.0
        # Bearish breaker
        if c1["close"] > c1["open"] and c2["high"] > c1["high"] and c3["close"] < c1["low"]:
            return 1.0
        return 0.0
    
    def _compute_mitigation(self, market_data: Dict, state: Dict) -> float:
        """MB(x): Mitigation block detection"""
        price = market_data.get("close", 0)
        unmitigated_levels = state.get("unmitigated_levels", [])
        
        for level in unmitigated_levels:
            if abs(price - level) / level < 0.005:  # Within 0.5%
                return 1.0
        return 0.0
    
    def _compute_ote(self, market_data: Dict, state: Dict) -> float:
        """OTE(x): Optimal Trade Entry (Fibonacci 0.62-0.79)"""
        swing_high = state.get("swing_high", 0)
        swing_low = state.get("swing_low", 0)
        price = market_data.get("close", 0)
        
        if swing_high == 0 or swing_low == 0:
            return 0.0
        
        range_ = swing_high - swing_low
        if range_ == 0:
            return 0.0
        
        # Calculate retracement
        if state.get("bias") == "bullish":
            retracement = (swing_high - price) / range_
        else:
            retracement = (price - swing_low) / range_
        
        # OTE zone: 0.62 - 0.79
        if 0.62 <= retracement <= 0.79:
            return 1.0
        elif 0.5 <= retracement <= 0.88:
            return 0.5
        return 0.0
    
    def _compute_judas(self, market_data: Dict, state: Dict) -> float:
        """J(x,t): Judas swing detection"""
        session = market_data.get("session", "")
        if session not in ["london", "ny"]:
            return 0.0
        
        # Simplified: check for initial false move at session open
        prices = market_data.get("prices", [])
        if len(prices) < 10:
            return 0.0
        
        first_5 = prices[:5]
        next_5 = prices[5:10]
        
        initial_move = np.mean(first_5)
        subsequent = np.mean(next_5)
        
        # Opposite move = Judas
        if abs(subsequent - initial_move) / initial_move > 0.003:
            return 1.0
        return 0.0
    
    def _compute_accumulation(self, market_data: Dict, state: Dict) -> float:
        """A(x,t): Wyckoff accumulation/distribution"""
        prices = market_data.get("prices", [])
        volumes = market_data.get("volume", [])
        
        if len(prices) < 20 or len(volumes) < 20:
            return 0.5
        
        # Check for range-bound with declining volume = accumulation
        recent_range = max(prices[-20:]) - min(prices[-20:])
        earlier_range = max(prices[-40:-20]) - min(prices[-40:-20]) if len(prices) >= 40 else recent_range
        
        recent_vol = np.mean(volumes[-20:])
        earlier_vol = np.mean(volumes[-40:-20]) if len(volumes) >= 40 else recent_vol
        
        if recent_range < earlier_range * 0.5 and recent_vol < earlier_vol * 0.7:
            return 1.0  # Accumulation
        return 0.5
    
    def _compute_projection(self, market_data: Dict, state: Dict) -> float:
        """⟨ψ|O|ψ⟩: Final measurement projection"""
        # Compute expectation value across all operators
        total = 0.0
        for name, op in self.operators.items():
            if name != "projection":
                total += op.apply(market_data, state)
        return total / max(len(self.operators) - 1, 1)
    
    # ============== UTILITY METHODS ==============
    
    def get_hamiltonian(self, market_data: Dict, state: Dict) -> Dict[str, float]:
        """Compute full market Hamiltonian H_market = Σ α_k O_k"""
        contributions = {}
        for name, op in self.operators.items():
            if op.meta.type == OperatorType.POTENTIAL:
                contributions[name] = op.apply(market_data, state)
        return contributions
    
    def get_all_scores(self, market_data: Dict, state: Dict) -> Dict[str, float]:
        """Get scores from all 18 operators"""
        return {name: op.apply(market_data, state) for name, op in self.operators.items()}
    
    def get_registry_metadata(self) -> Dict:
        """Export all operator META dicts"""
        return {name: op.meta.to_dict() for name, op in self.operators.items()}
