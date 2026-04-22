"""
market_regime_detector.py — Dynamic market regime detection and model adaptation

Detects market regimes and adapts model parameters:
- High volatility → Conservative parameters, wider uncertainty bounds
- Low volatility → Aggressive parameters, tighter bounds
- Trending → Momentum bias in RL agent
- Ranging → Mean-reversion bias
- Crisis → Maximum caution, reduced position sizes

Integrates with:
- Path integral: Adjusts ℏ parameter
- RL agent: Modifies reward function
- Risk management: Adapts position sizing
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class MarketRegime(Enum):
    """Market regime classifications"""
    TRENDING_UP = "trending_up"
    TRENDING_DOWN = "trending_down"
    RANGING = "ranging"
    HIGH_VOLATILITY = "high_volatility"
    LOW_VOLATILITY = "low_volatility"
    CRISIS = "crisis"
    NORMAL = "normal"


@dataclass
class RegimeParameters:
    """Model parameters adapted per regime"""
    # Path integral parameters
    epsilon_scale: float = 1.0  # Scales ℏ parameter
    trajectory_count: int = 100  # Number of trajectories to generate

    # RL parameters
    risk_aversion: float = 1.0  # Higher = more conservative
    momentum_bias: float = 0.0  # Positive for trending, negative for ranging

    # Risk management
    max_position_size: float = 1.0  # Fraction of capital
    stop_loss_multiplier: float = 1.0  # Multiplier for stop distances

    # Geometry parameters
    curvature_weight: float = 1.0  # Weight for curvature in Hamiltonian
    liquidity_sensitivity: float = 1.0  # Sensitivity to liquidity field


class MarketRegimeDetector:
    """
    Detects market regime from price action and microstructure

    Uses multiple indicators:
    - ADX for trend strength
    - Bollinger Band width for volatility
    - RSI for momentum
    - Volume profile for liquidity
    - Order flow imbalance
    """

    def __init__(
        self,
        lookback_periods: int = 100,
        volatility_threshold: float = 0.02,
        trend_threshold: float = 25.0,  # ADX threshold
        crisis_threshold: float = 0.05  # Extreme volatility
    ):
        self.lookback = lookback_periods
        self.volatility_threshold = volatility_threshold
        self.trend_threshold = trend_threshold
        self.crisis_threshold = crisis_threshold

        # Regime parameter presets
        self.regime_params = self._initialize_regime_parameters()

        # State
        self.current_regime = MarketRegime.NORMAL
        self.regime_history: List[Tuple[MarketRegime, float]] = []
        self.confidence = 0.5

    def _initialize_regime_parameters(self) -> Dict[MarketRegime, RegimeParameters]:
        """Initialize parameter presets for each regime"""

        return {
            MarketRegime.TRENDING_UP: RegimeParameters(
                epsilon_scale=0.8,  # More deterministic trajectories
                trajectory_count=80,  # Fewer trajectories needed
                risk_aversion=0.7,  # Less conservative
                momentum_bias=0.3,  # Favor momentum
                max_position_size=1.2,  # Slightly larger positions
                stop_loss_multiplier=1.5,  # Wider stops for trends
                curvature_weight=0.8,  # Less sensitive to local curvature
                liquidity_sensitivity=0.9
            ),

            MarketRegime.TRENDING_DOWN: RegimeParameters(
                epsilon_scale=0.8,
                trajectory_count=80,
                risk_aversion=0.7,
                momentum_bias=-0.3,  # Negative momentum bias
                max_position_size=1.2,
                stop_loss_multiplier=1.5,
                curvature_weight=0.8,
                liquidity_sensitivity=0.9
            ),

            MarketRegime.RANGING: RegimeParameters(
                epsilon_scale=1.2,  # More diverse trajectories
                trajectory_count=120,  # More exploration
                risk_aversion=1.3,  # More conservative
                momentum_bias=-0.2,  # Slight mean-reversion bias
                max_position_size=0.8,  # Smaller positions
                stop_loss_multiplier=0.8,  # Tighter stops
                curvature_weight=1.4,  # More sensitive to basins/attractors
                liquidity_sensitivity=1.2
            ),

            MarketRegime.HIGH_VOLATILITY: RegimeParameters(
                epsilon_scale=1.5,  # Much more diverse
                trajectory_count=150,  # Extensive exploration
                risk_aversion=2.0,  # Very conservative
                momentum_bias=0.0,  # Neutral
                max_position_size=0.5,  # Much smaller positions
                stop_loss_multiplier=0.6,  # Tighter stops
                curvature_weight=1.2,
                liquidity_sensitivity=1.5  # More sensitive to liquidity
            ),

            MarketRegime.LOW_VOLATILITY: RegimeParameters(
                epsilon_scale=0.6,  # More deterministic
                trajectory_count=60,  # Fewer trajectories
                risk_aversion=0.8,  # Less conservative
                momentum_bias=0.1,  # Slight momentum bias
                max_position_size=1.5,  # Larger positions
                stop_loss_multiplier=2.0,  # Much wider stops
                curvature_weight=0.7,
                liquidity_sensitivity=0.7
            ),

            MarketRegime.CRISIS: RegimeParameters(
                epsilon_scale=2.0,  # Maximum exploration
                trajectory_count=200,  # Extensive sampling
                risk_aversion=5.0,  # Extremely conservative
                momentum_bias=0.0,  # Neutral
                max_position_size=0.2,  # Minimum positions
                stop_loss_multiplier=0.3,  # Very tight stops
                curvature_weight=2.0,  # Maximum curvature sensitivity
                liquidity_sensitivity=3.0  # Maximum liquidity sensitivity
            ),

            MarketRegime.NORMAL: RegimeParameters()  # Default parameters
        }

    def detect_regime(self, price_data: pd.DataFrame, microstructure: Optional[Dict] = None) -> MarketRegime:
        """
        Detect current market regime from price data

        Args:
            price_data: OHLCV DataFrame with at least 'high', 'low', 'close'
            microstructure: Optional microstructure data

        Returns:
            Detected market regime
        """

        if len(price_data) < self.lookback:
            return MarketRegime.NORMAL

        # Calculate indicators
        adx = self._calculate_adx(price_data)
        volatility = self._calculate_volatility(price_data)
        rsi = self._calculate_rsi(price_data)
        trend_direction = self._calculate_trend_direction(price_data)

        # Detect crisis (extreme volatility)
        if volatility > self.crisis_threshold:
            regime = MarketRegime.CRISIS
            confidence = min(1.0, volatility / (2 * self.crisis_threshold))

        # Detect high/low volatility
        elif volatility > self.volatility_threshold:
            regime = MarketRegime.HIGH_VOLATILITY
            confidence = min(1.0, volatility / (2 * self.volatility_threshold))

        elif volatility < self.volatility_threshold * 0.3:
            regime = MarketRegime.LOW_VOLATILITY
            confidence = min(1.0, (self.volatility_threshold * 0.3) / volatility)

        # Detect trending vs ranging
        elif adx > self.trend_threshold:
            if trend_direction > 0:
                regime = MarketRegime.TRENDING_UP
            else:
                regime = MarketRegime.TRENDING_DOWN
            confidence = min(1.0, adx / (self.trend_threshold * 1.5))

        else:
            regime = MarketRegime.RANGING
            confidence = min(1.0, (self.trend_threshold - adx) / self.trend_threshold)

        # Update state
        self.current_regime = regime
        self.confidence = confidence
        self.regime_history.append((regime, confidence))

        # Keep only recent history
        if len(self.regime_history) > 100:
            self.regime_history = self.regime_history[-100:]

        logger.info(f"Detected regime: {regime.value} (confidence: {confidence:.2f})")
        return regime

    def detect_regime_with_params(
        self,
        price_data: pd.DataFrame,
        microstructure: Optional[Dict] = None
    ) -> Tuple[MarketRegime, RegimeParameters]:
        """Detect regime AND return the adapted RegimeParameters in one call.

        This is the preferred entry point — callers no longer need to make two
        separate calls to detect_regime() then get_adapted_parameters().

        Returns:
            (regime, regime_params): current regime enum + fully adapted parameters
        """
        regime = self.detect_regime(price_data, microstructure)
        params = self.get_adapted_parameters()
        return regime, params

    def get_adapted_parameters(self, base_params: Optional[RegimeParameters] = None) -> RegimeParameters:
        """
        Get model parameters adapted for current regime

        Args:
            base_params: Base parameters to adapt from

        Returns:
            Adapted parameters for current regime
        """

        regime_params = self.regime_params[self.current_regime]

        if base_params is None:
            return regime_params

        # Interpolate between base and regime parameters based on confidence
        return self._interpolate_parameters(base_params, regime_params, self.confidence)

    def _interpolate_parameters(self, base: RegimeParameters, target: RegimeParameters, weight: float) -> RegimeParameters:
        """Interpolate between parameter sets"""

        return RegimeParameters(
            epsilon_scale=base.epsilon_scale * (1 - weight) + target.epsilon_scale * weight,
            trajectory_count=int(base.trajectory_count * (1 - weight) + target.trajectory_count * weight),
            risk_aversion=base.risk_aversion * (1 - weight) + target.risk_aversion * weight,
            momentum_bias=base.momentum_bias * (1 - weight) + target.momentum_bias * weight,
            max_position_size=base.max_position_size * (1 - weight) + target.max_position_size * weight,
            stop_loss_multiplier=base.stop_loss_multiplier * (1 - weight) + target.stop_loss_multiplier * weight,
            curvature_weight=base.curvature_weight * (1 - weight) + target.curvature_weight * weight,
            liquidity_sensitivity=base.liquidity_sensitivity * (1 - weight) + target.liquidity_sensitivity * weight
        )

    def _calculate_adx(self, data: pd.DataFrame, period: int = 14) -> float:
        """Calculate Average Directional Index"""
        high = data['high']
        low = data['low']
        close = data['close']

        # True Range
        tr = np.maximum(high - low,
                       np.maximum(abs(high - close.shift(1)),
                                abs(low - close.shift(1))))

        # Directional Movement
        dm_plus = np.where((high - high.shift(1)) > (low.shift(1) - low),
                          np.maximum(high - high.shift(1), 0), 0)
        dm_minus = np.where((low.shift(1) - low) > (high - high.shift(1)),
                           np.maximum(low.shift(1) - low, 0), 0)

        # Smoothed averages
        atr = tr.rolling(period).mean()
        di_plus = 100 * (pd.Series(dm_plus).rolling(period).mean() / atr)
        di_minus = 100 * (pd.Series(dm_minus).rolling(period).mean() / atr)

        # ADX
        dx = 100 * abs(di_plus - di_minus) / (di_plus + di_minus)
        adx = dx.rolling(period).mean()

        return adx.iloc[-1] if not adx.empty else 0.0

    def _calculate_volatility(self, data: pd.DataFrame) -> float:
        """Calculate recent volatility (standard deviation of returns)"""
        returns = data['close'].pct_change()
        return returns.std() * np.sqrt(252)  # Annualized

    def _calculate_rsi(self, data: pd.DataFrame, period: int = 14) -> float:
        """Calculate RSI"""
        delta = data['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi.iloc[-1] if not rsi.empty else 50.0

    def _calculate_trend_direction(self, data: pd.DataFrame, period: int = 20) -> float:
        """Calculate trend direction (-1 to 1)"""
        sma_short = data['close'].rolling(10).mean()
        sma_long = data['close'].rolling(period).mean()
        return np.sign((sma_short - sma_long).iloc[-1]) if not sma_long.empty else 0.0

    def get_regime_statistics(self) -> Dict:
        """Get statistics about regime detection"""
        if not self.regime_history:
            return {}

        regimes = [r for r, _ in self.regime_history]
        confidences = [c for _, c in self.regime_history]

        from collections import Counter
        regime_counts = Counter(regimes)

        return {
            'current_regime': self.current_regime.value,
            'confidence': self.confidence,
            'regime_distribution': {r.value: count for r, count in regime_counts.items()},
            'avg_confidence': np.mean(confidences),
            'regime_switches': len(set(regimes[-10:])) if len(regimes) >= 10 else len(set(regimes))
        }