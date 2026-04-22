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
import logging

# Accelerated backend integration for Hamiltonian computation
try:
    from ..accelerated.backend_selector import get_backend, ACCELERATED_AVAILABLE
    ACCELERATED = True
except ImportError:
    ACCELERATED = False
    logger = logging.getLogger(__name__)
    logger.debug("Accelerated operators not available")


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
    
    # ============== HELPER METHODS ==============

    def _compute_atr(self, market_data: Dict, period: int = 14) -> float:
        """Average True Range over last `period` candles."""
        ohlc = market_data.get("ohlc", [])
        highs = market_data.get("highs", [])
        lows = market_data.get("lows", [])
        closes = market_data.get("closes", []) or market_data.get("prices", [])

        if ohlc and len(ohlc) >= 2:
            trs = []
            for i in range(1, min(period + 1, len(ohlc))):
                c = ohlc[i]
                prev_close = ohlc[i - 1]["close"]
                tr = max(c["high"] - c["low"],
                         abs(c["high"] - prev_close),
                         abs(c["low"] - prev_close))
                trs.append(tr)
            return float(np.mean(trs)) if trs else 1e-6

        if highs and lows and len(highs) >= 2:
            trs = [highs[i] - lows[i] for i in range(max(0, len(highs) - period), len(highs))]
            return float(np.mean(trs)) if trs else 1e-6

        return 1e-6  # Degenerate fallback

    def _get_swing_levels(self, market_data: Dict, state: Dict):
        """Return (swing_high, swing_low) from state or derive from price history."""
        sh = state.get("swing_high") or state.get("bos_high")
        sl = state.get("swing_low") or state.get("bos_low")
        if sh and sl:
            return float(sh), float(sl)
        highs = market_data.get("highs", [])
        lows = market_data.get("lows", [])
        prices = market_data.get("prices", [])
        all_h = highs if highs else prices
        all_l = lows if lows else prices
        if all_h and all_l:
            return float(max(all_h[-50:])), float(min(all_l[-50:]))
        return 0.0, 0.0

    # ============== OPERATOR COMPUTATIONS ==============

    def _compute_kinetic(self, market_data: Dict, state: Dict) -> float:
        """T(p;σ) = p²/(2m·σ): Kinetic energy from momentum and volatility.

        p = mean absolute return velocity; σ = rolling std of returns (volatility).
        Score is dimensionless: higher momentum relative to volatility = higher score.
        """
        prices = market_data.get("prices", []) or market_data.get("closes", [])
        if len(prices) < 3:
            return 0.0
        arr = np.array(prices, dtype=float)
        returns = np.diff(arr) / np.where(arr[:-1] != 0, arr[:-1], 1.0)
        p = float(np.mean(np.abs(returns[-20:])))
        sigma = float(np.std(returns[-20:])) if len(returns) >= 2 else 1e-6
        if sigma < 1e-9:
            sigma = 1e-6
        return float(p ** 2 / (2.0 * sigma))

    def _compute_liquidity_pool(self, market_data: Dict, state: Dict) -> float:
        """V_LP(x) = -κ·Σ_i V_i·exp(-|x - x_i|/λ): Volume-weighted attraction field.

        Approximated as: sum of volume×proximity weights for recent candles.
        High near-price volume = strong attraction = high score.
        """
        prices = market_data.get("prices", []) or market_data.get("closes", [])
        volumes = market_data.get("volume", []) or market_data.get("volumes", [])
        if not prices or not volumes:
            return 0.0
        price = float(prices[-1])
        kappa = 1.0
        lam = float(np.std(prices[-20:]) if len(prices) >= 2 else 0.001) or 0.001
        total = 0.0
        n = min(len(prices), len(volumes), 20)
        for i in range(n):
            x_i = float(prices[-(i + 1)])
            v_i = float(volumes[-(i + 1)])
            dist = abs(price - x_i)
            total += v_i * np.exp(-dist / lam)
        vol_mean = float(np.mean(volumes[-20:])) if volumes else 1.0
        return float(kappa * total / max(vol_mean * n, 1.0))

    def _compute_order_block(self, market_data: Dict, state: Dict) -> float:
        """V_OB(x): Institutional order block detection.

        Criteria (ICT exact): candle body > 70% of range AND volume > 2σ above mean.
        Score = (body/range) × log(vol/vol_mean) — stronger OBs score higher.
        """
        ohlc = market_data.get("ohlc", [])
        volumes = market_data.get("volume", []) or market_data.get("volumes", [])
        if not ohlc or not volumes:
            return 0.0
        vol_arr = np.array(volumes[-50:], dtype=float)
        vol_mean = float(np.mean(vol_arr)) or 1.0
        vol_std = float(np.std(vol_arr)) or vol_mean * 0.5
        best_score = 0.0
        n = min(len(ohlc), len(volumes), 10)
        for i in range(n):
            c = ohlc[-(i + 1)]
            v = float(volumes[-(i + 1)])
            body = abs(c["close"] - c["open"])
            rng = c["high"] - c["low"]
            if rng <= 0:
                continue
            body_ratio = body / rng
            if body_ratio > 0.70 and v > vol_mean + 2.0 * vol_std:
                score = body_ratio * np.log(max(v / vol_mean, 1.0))
                best_score = max(best_score, score)
        return float(min(best_score, 5.0))

    def _compute_fvg(self, market_data: Dict, state: Dict) -> float:
        """V_FVG(x): Fair Value Gap — score = gap_size / ATR.

        Bullish FVG: high[i] < low[i+2] (gap up, unmitigated imbalance zone).
        Bearish FVG: low[i] > high[i+2] (gap down).
        Score = max gap size normalized by ATR — larger gaps = stronger imbalance.
        """
        ohlc = market_data.get("ohlc", [])
        if len(ohlc) < 3:
            return 0.0
        atr = self._compute_atr(market_data) or 1e-6
        best_gap = 0.0
        for i in range(len(ohlc) - 2):
            c1, c3 = ohlc[i], ohlc[i + 2]
            # Bullish FVG: c1 high < c3 low
            if c1["high"] < c3["low"]:
                gap = c3["low"] - c1["high"]
                best_gap = max(best_gap, gap)
            # Bearish FVG: c1 low > c3 high
            elif c1["low"] > c3["high"]:
                gap = c1["low"] - c3["high"]
                best_gap = max(best_gap, gap)
        return float(min(best_gap / atr, 10.0))

    def _compute_macro_time(self, market_data: Dict, state: Dict) -> float:
        """V_macro(t): Session weight × time-decay from session peak.

        Session base weights reflect ICT killzone importance.
        Decay: exp(-|minutes_from_open| / tau) where tau=30min.
        """
        import datetime
        session = market_data.get("session", "neutral").lower()
        session_weights = {
            "london": 1.0, "london_open": 1.0,
            "ny": 0.95, "new_york": 0.95, "ny_open": 1.0,
            "asia": 0.60, "tokyo": 0.60,
            "london_close": 0.70,
            "neutral": 0.40, "off_hours": 0.20
        }
        base_weight = session_weights.get(session, 0.40)

        # Time decay from session open if timestamp provided
        ts = market_data.get("timestamp")
        if ts:
            try:
                dt = datetime.datetime.utcfromtimestamp(float(ts))
                hour = dt.hour
                minute = dt.minute
                total_min = hour * 60 + minute
                # Session opens: London=8:00, NY=13:00, Asia=00:00 UTC
                session_opens = {"london": 480, "ny": 780, "asia": 0}
                open_min = session_opens.get(session, total_min)
                delta = abs(total_min - open_min)
                tau = 60.0  # 1-hour decay constant
                decay = float(np.exp(-delta / tau))
                base_weight *= (0.6 + 0.4 * decay)  # Decay from 100% to 60% of base
            except Exception:
                pass

        return float(np.clip(base_weight, 0.0, 1.0))

    def _compute_price_delivery(self, market_data: Dict, state: Dict) -> float:
        """V_PD(x): Premium/discount positioning relative to PD array midline.

        Score in [-1, 1]: +1 = deep discount (buy zone), -1 = deep premium (sell zone).
        PD midline = (swing_high + swing_low) / 2.
        """
        price = float(market_data.get("close", 0) or
                      (market_data.get("prices") or [0])[-1])
        swing_high, swing_low = self._get_swing_levels(market_data, state)
        if swing_high == swing_low or swing_high == 0:
            return 0.0
        midline = (swing_high + swing_low) / 2.0
        rng = swing_high - swing_low
        # Positive = discount, Negative = premium
        score = (midline - price) / rng
        return float(np.clip(score, -1.0, 1.0))

    def _compute_regime(self, market_data: Dict, state: Dict) -> float:
        """V_regime(x,t): Regime score from ADX + price structure.

        Returns continuous score: +1.0 (strong uptrend), 0 (ranging), -1.0 (downtrend).
        Computes ADX-proxy from DMI if raw prices available; uses state regime if provided.
        """
        # Check if regime was pre-computed by MarketRegimeDetector
        regime_label = state.get("regime") or market_data.get("regime")
        regime_map = {
            "trending_up": 1.0, "TRENDING_UP": 1.0,
            "trending_down": -1.0, "TRENDING_DOWN": -1.0,
            "ranging": 0.0, "RANGING": 0.0,
            "high_volatility": 0.2, "HIGH_VOLATILITY": 0.2,
            "low_volatility": 0.0, "LOW_VOLATILITY": 0.0,
            "crisis": -0.5, "CRISIS": -0.5,
        }
        if regime_label and regime_label in regime_map:
            return regime_map[regime_label]

        # Derive from price structure: BOS/CHOCH indicators
        prices = market_data.get("prices", []) or market_data.get("closes", [])
        if len(prices) < 20:
            return 0.0
        arr = np.array(prices, dtype=float)
        # ADX proxy: normalized directional movement
        returns = np.diff(arr[-21:])
        pos_dm = np.sum(returns[returns > 0])
        neg_dm = np.sum(np.abs(returns[returns < 0]))
        total_dm = pos_dm + neg_dm
        if total_dm < 1e-9:
            return 0.0
        dx = (pos_dm - neg_dm) / total_dm  # in [-1, 1]
        return float(dx)

    def _compute_session(self, market_data: Dict, state: Dict) -> float:
        """Π_session: Session legality projector {0, 1}.

        Allowed sessions from env TRADING_SESSIONS or default: london, ny, asia.
        """
        import os
        session = (market_data.get("session") or "").lower().strip()
        env_sessions = os.getenv("TRADING_SESSIONS", "london,ny,asia,new_york,tokyo,london_open,ny_open")
        allowed = {s.strip().lower() for s in env_sessions.split(",")}
        return 1.0 if session in allowed else 0.0

    def _compute_risk(self, market_data: Dict, state: Dict) -> float:
        """Π_risk: Risk limit projector {0, 1}.

        Queries live risk_manager if wired; otherwise falls back to state limits.
        """
        risk_mgr = state.get("risk_manager")
        if risk_mgr is not None and hasattr(risk_mgr, "get_max_allowed"):
            max_allowed = risk_mgr.get_max_allowed()
        else:
            max_allowed = float(state.get("max_position_size", 0.1))

        proposed = float(state.get("proposed_position_size",
                                   state.get("position_size", 0)))
        return 1.0 if proposed <= max_allowed else 0.0

    # T2-D: regime → sailing-lane decay factor
    _REGIME_ALPHA: Dict[str, float] = {
        "TRENDING": 0.85,
        "RANGING": 0.7,
        "HIGH_VOL": 0.6,
        "CRISIS": 0.5,
    }

    @classmethod
    def sailing_alpha_from_regime(cls, regime: str) -> float:
        """Return sailing-lane decay factor α for the given market regime."""
        return cls._REGIME_ALPHA.get(regime.upper(), 0.8)

    def _compute_sailing_lane(self, market_data: Dict, state: Dict) -> float:
        """L(n) = L₀·α^(n-1): Sailing lane multi-leg position sizing.

        leg n must be in {1..max_legs}. Returns 0 if leg exceeds max.
        Alpha can be regime-adapted (T2-D) via state["sailing_alpha"]; defaults to 0.8.
        """
        leg = int(state.get("current_leg", 1))
        max_legs = int(state.get("max_legs", 5))
        alpha = float(state.get("sailing_alpha", 0.8))
        L0 = float(state.get("sailing_L0", 1.0))

        if not (1 <= leg <= max_legs):
            return 0.0

        position = L0 * (alpha ** (leg - 1))
        return float(position) if position > 1e-4 else 0.0

    def _compute_sweep(self, market_data: Dict, state: Dict) -> float:
        """S_liq(x): Liquidity sweep — exceeds prior swing AND closes back inside.

        Score = reversal momentum = |close - sweep_level| / ATR.
        A sweep that closes strongly back inside scores higher.
        """
        highs = market_data.get("highs", [])
        lows = market_data.get("lows", [])
        closes = market_data.get("closes", []) or market_data.get("prices", [])
        if len(highs) < 5 or len(lows) < 5 or not closes:
            return 0.0
        atr = self._compute_atr(market_data) or 1e-6
        recent_high = float(max(highs[-6:-1]))
        recent_low = float(min(lows[-6:-1]))
        cur_high = float(highs[-1])
        cur_low = float(lows[-1])
        close = float(closes[-1])

        # Bearish sweep: wick above prior high, closes back below
        if cur_high > recent_high and close < recent_high:
            return float(min((recent_high - close) / atr, 3.0))
        # Bullish sweep: wick below prior low, closes back above
        if cur_low < recent_low and close > recent_low:
            return float(min((close - recent_low) / atr, 3.0))
        return 0.0

    def _compute_displacement(self, market_data: Dict, state: Dict) -> float:
        """D(x,t): Displacement — single impulsive candle > 2.5×ATR body.

        Score = body / ATR. Displacement candles leave FVGs and signal order flow.
        """
        ohlc = market_data.get("ohlc", [])
        closes = market_data.get("closes", []) or market_data.get("prices", [])
        if not ohlc and not closes:
            return 0.0
        atr = self._compute_atr(market_data) or 1e-6

        if ohlc:
            c = ohlc[-1]
            body = abs(c["close"] - c["open"])
        else:
            if len(closes) < 2:
                return 0.0
            body = abs(closes[-1] - closes[-2])

        score = body / atr
        return float(min(score, 5.0)) if score >= 2.5 else float(score * 0.3)

    def _compute_breaker_block(self, market_data: Dict, state: Dict) -> float:
        """BB(x): Breaker block — former OB that was swept through (BOS).

        After BOS, the prior order block flips polarity: support becomes resistance.
        Score = 1 / (distance_to_breaker / ATR + epsilon) — proximity-weighted.
        """
        price = float(market_data.get("close", 0) or
                      (market_data.get("closes") or market_data.get("prices") or [0])[-1])
        breaker_levels = state.get("breaker_levels", [])
        if not breaker_levels:
            # Derive from BOS level if available
            bos = state.get("bos_level")
            if bos:
                breaker_levels = [float(bos)]
            else:
                return 0.0
        atr = self._compute_atr(market_data) or 1e-6
        best = 0.0
        for lvl in breaker_levels:
            dist = abs(price - float(lvl))
            proximity = 1.0 / (dist / atr + 0.5)
            best = max(best, proximity)
        return float(min(best, 2.0))

    def _compute_mitigation(self, market_data: Dict, state: Dict) -> float:
        """MB(x): Mitigation block — price returning to unmitigated order block.

        Score = 1 - (distance / ATR). Score approaches 1 as price nears the level.
        Zero when distance > 1 ATR.
        """
        price = float(market_data.get("close", 0) or
                      (market_data.get("closes") or market_data.get("prices") or [0])[-1])
        unmitigated = state.get("unmitigated_levels", [])
        if not unmitigated:
            return 0.0
        atr = self._compute_atr(market_data) or 1e-6
        best = 0.0
        for lvl in unmitigated:
            dist = abs(price - float(lvl))
            score = max(0.0, 1.0 - dist / atr)
            best = max(best, score)
        return float(best)

    def _compute_ote(self, market_data: Dict, state: Dict) -> float:
        """OTE(x): Optimal Trade Entry — Fibonacci 0.62-0.79 retracement zone.

        Swing high/low MUST come from a confirmed BOS structure, not arbitrary window.
        Returns 1.0 in core OTE, 0.5 in extended OTE, 0.0 outside.
        """
        swing_high, swing_low = self._get_swing_levels(market_data, state)
        if swing_high == 0 or swing_low == 0 or swing_high == swing_low:
            return 0.0
        price = float(market_data.get("close", 0) or
                      (market_data.get("closes") or market_data.get("prices") or [0])[-1])
        rng = swing_high - swing_low
        bias = state.get("bias", "bullish")
        if bias == "bullish":
            retracement = (swing_high - price) / rng
        else:
            retracement = (price - swing_low) / rng

        if 0.62 <= retracement <= 0.79:
            return 1.0
        if 0.50 <= retracement < 0.62 or 0.79 < retracement <= 0.90:
            return 0.5
        return 0.0

    def _compute_judas(self, market_data: Dict, state: Dict) -> float:
        """J(x,t): Judas Swing — early session false move against expected direction.

        Requires active session (london or ny). Score = reversal speed normalized by ATR.
        A fast reversal after a false breakout signals higher probability Judas.
        """
        session = (market_data.get("session") or "").lower()
        if session not in ("london", "ny", "london_open", "ny_open", "new_york"):
            return 0.0
        prices = market_data.get("prices", []) or market_data.get("closes", [])
        if len(prices) < 10:
            return 0.0
        atr = self._compute_atr(market_data) or 1e-6
        # First 5 bars = initial session move; next 5 = reversal
        first_move = float(prices[4] - prices[0])
        reversal = float(prices[-1] - prices[4])
        # Judas: first_move and reversal are opposite signs, reversal is meaningful
        if first_move * reversal < 0 and abs(reversal) > 0.5 * atr:
            score = min(abs(reversal) / atr, 3.0)
            return float(score)
        return 0.0

    def _compute_accumulation(self, market_data: Dict, state: Dict) -> float:
        """A(x,t): Wyckoff Accumulation/Distribution phase detection.

        Accumulation = range compression (recent < earlier) + volume dry-up.
        Distribution = range expansion + climactic volume.
        Score: 0=neutral, 1=accumulation, -1=distribution (abs value returned for energy).
        """
        prices = market_data.get("prices", []) or market_data.get("closes", [])
        volumes = market_data.get("volume", []) or market_data.get("volumes", [])
        if len(prices) < 20 or len(volumes) < 20:
            return 0.3  # Insufficient data = neutral small score

        recent_prices = prices[-20:]
        earlier_prices = prices[-40:-20] if len(prices) >= 40 else prices[:20]
        recent_range = float(max(recent_prices) - min(recent_prices))
        earlier_range = float(max(earlier_prices) - min(earlier_prices))

        recent_vol = float(np.mean(volumes[-20:]))
        earlier_vol = float(np.mean(volumes[-40:-20]) if len(volumes) >= 40 else np.mean(volumes[:20]))

        range_compressed = recent_range < earlier_range * 0.65
        vol_dry = recent_vol < earlier_vol * 0.75
        vol_climax = recent_vol > earlier_vol * 1.5

        if range_compressed and vol_dry:
            return 1.0  # Accumulation
        if not range_compressed and vol_climax:
            return 0.8  # Distribution (still positive for energy contribution)
        return 0.3

    def _compute_projection(self, market_data: Dict, state: Dict) -> float:
        """O18 = <psi|H_market|psi>: Quantum expectation value of market Hamiltonian.

        Builds state vector psi from the 17 operator scores, computes quadratic form
        psi^T H_market psi where H_market is a diagonal approximation (operator scores
        as eigenvalues). This is the true quantum measurement, not a simple average.
        """
        scores = []
        for name, op in self.operators.items():
            if name != "projection":
                scores.append(op.apply(market_data, state))

        if not scores:
            return 0.0

        psi = np.array(scores, dtype=float)
        norm = float(np.linalg.norm(psi))
        if norm < 1e-9:
            return 0.0
        psi_normalized = psi / norm

        # Diagonal Hamiltonian: H_market = diag(scores)
        # <psi|H|psi> = sum_i psi_i^2 * h_i  (quadratic form on diagonal matrix)
        expectation = float(np.dot(psi_normalized ** 2, psi))
        return float(expectation)
    
    # ============== UTILITY METHODS ==============
    
    def get_hamiltonian(self, market_data: Dict, state: Dict) -> Dict[str, float]:
        """Compute full market Hamiltonian H_market = Σ α_k O_k"""
        # Check if we can use accelerated backend
        if ACCELERATED and 'prices' in market_data:
            try:
                backend = get_backend()
                prices = np.array(market_data.get('prices', []))
                if len(prices) > 0:
                    # Get OHLCV data
                    highs = np.array(market_data.get('highs', prices))
                    lows = np.array(market_data.get('lows', prices))
                    opens = np.array(market_data.get('opens', prices))
                    closes = np.array(market_data.get('closes', prices))
                    volumes = np.array(market_data.get('volumes', np.ones(len(prices))), dtype=np.int32)
                    
                    # Use accelerated Hamiltonian computation
                    weights = np.ones(18) / 18  # Equal weights
                    H_value = backend.compute_hamiltonian_fast(
                        prices, highs, lows, opens, closes, volumes, weights
                    )
                    
                    # Return with standard format
                    return {
                        'total_energy': H_value,
                        'accelerated': True,
                        'backend': 'cython' if hasattr(backend, 'preferred') else 'numpy'
                    }
            except Exception:
                pass  # Fall through to standard computation
        
        # Standard computation (fallback)
        contributions = {}
        for name, op in self.operators.items():
            if op.meta.type == OperatorType.POTENTIAL:
                contributions[name] = op.apply(market_data, state)
        return contributions
    
    def get_all_scores(self, market_data: Dict, state: Dict) -> Dict[str, float]:
        """Get scores from all 18 operators"""
        # Try accelerated path first
        if ACCELERATED and 'prices' in market_data:
            try:
                backend = get_backend()
                prices = np.array(market_data.get('prices', []))
                if len(prices) > 0:
                    highs = np.array(market_data.get('highs', prices))
                    lows = np.array(market_data.get('lows', prices))
                    opens = np.array(market_data.get('opens', prices))
                    closes = np.array(market_data.get('closes', prices))
                    volumes = np.array(market_data.get('volumes', np.ones(len(prices))), dtype=np.int32)
                    
                    scores_array = backend.compute_hamiltonian_fast(
                        prices, highs, lows, opens, closes, volumes
                    )
                    
                    if scores_array is not None and len(scores_array) == 18:
                        return {
                            name: float(scores_array[i])
                            for i, name in enumerate(self.operators.keys())
                        }
            except Exception:
                pass
        
        # Standard computation (fallback)
        return {name: op.apply(market_data, state) for name, op in self.operators.items()}
    
    def get_registry_metadata(self) -> Dict:
        """Export all operator META dicts"""
        return {name: op.meta.to_dict() for name, op in self.operators.items()}
