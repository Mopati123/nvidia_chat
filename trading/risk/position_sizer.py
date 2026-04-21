"""
Position Sizing Engine
Implements Kelly Criterion with TAEP constraints
Volatility-adjusted position sizing
"""

import logging
import numpy as np
from typing import Dict, Optional, Tuple
from dataclasses import dataclass

from trading.risk.risk_manager import get_risk_manager, ProductionRiskManager

logger = logging.getLogger(__name__)


@dataclass
class SizingParams:
    """Parameters for position sizing calculation"""
    account_balance: float
    win_rate: float  # Historical win rate (0-1)
    avg_win: float   # Average win amount
    avg_loss: float  # Average loss amount
    volatility: float  # Current volatility (ATR or std dev)
    confidence: float  # Signal confidence (0-1)
    risk_per_trade: float  # Risk percentage per trade (default 0.02 = 2%)


class PositionSizer:
    """
    Production position sizing engine
    
    Methods:
    1. Kelly Criterion (fractional for safety)
    2. Volatility-adjusted sizing
    3. TAEP constraint integration
    4. Account balance percentage
    """
    
    def __init__(
        self,
        kelly_fraction: float = 0.25,  # Use 1/4 Kelly for safety
        max_risk_per_trade: float = 0.02,  # 2% max
        min_position_size: float = 0.01,  # 0.01 lots minimum
        volatility_lookback: int = 20
    ):
        self.kelly_fraction = kelly_fraction
        self.max_risk_per_trade = max_risk_per_trade
        self.min_position_size = min_position_size
        self.volatility_lookback = volatility_lookback
        
        # Risk manager reference
        self.risk_manager = get_risk_manager()
        
        logger.info(f"PositionSizer: kelly_frac={kelly_fraction}, max_risk={max_risk_per_trade}")
    
    def kelly_criterion(
        self,
        win_rate: float,
        avg_win: float,
        avg_loss: float
    ) -> float:
        """
        Calculate Kelly Criterion fraction
        
        Kelly % = W - [(1 - W) / R]
        Where W = win rate, R = win/loss ratio
        
        Returns: Fraction of capital to risk (0-1)
        """
        if avg_loss == 0:
            return 0.0
        
        win_loss_ratio = avg_win / avg_loss
        
        if win_loss_ratio <= 0:
            return 0.0
        
        # Full Kelly
        kelly = win_rate - ((1 - win_rate) / win_loss_ratio)
        
        # Apply safety fraction (1/4 Kelly recommended)
        fractional_kelly = kelly * self.kelly_fraction
        
        # Clamp to reasonable bounds
        return max(0.0, min(fractional_kelly, 0.5))
    
    def volatility_adjusted_size(
        self,
        base_size: float,
        current_volatility: float,
        target_volatility: float = 0.01  # 1% daily vol target
    ) -> float:
        """
        Adjust position size based on volatility
        
        Higher volatility = smaller position
        """
        if current_volatility <= 0:
            return base_size
        
        # Volatility scaling factor
        vol_factor = target_volatility / current_volatility
        
        # Apply adjustment (bounded)
        adjusted_size = base_size * np.clip(vol_factor, 0.25, 2.0)
        
        return adjusted_size
    
    def calculate_position_size(
        self,
        params: SizingParams,
        entry_price: float,
        stop_loss: Optional[float] = None,
        symbol: str = ""
    ) -> Tuple[float, Dict]:
        """
        Calculate optimal position size
        
        Returns: (size_in_lots, metadata_dict)
        """
        metadata = {
            'method': 'composite',
            'kelly_pct': 0.0,
            'risk_pct': 0.0,
            'vol_adjustment': 1.0,
            'confidence_factor': params.confidence,
            'constraints_applied': []
        }
        
        # 1. Kelly-based sizing
        if params.win_rate > 0 and params.avg_win > 0 and params.avg_loss > 0:
            kelly_pct = self.kelly_criterion(params.win_rate, params.avg_win, params.avg_loss)
            kelly_size = params.account_balance * kelly_pct / entry_price
            metadata['kelly_pct'] = kelly_pct
        else:
            # Default to fixed fraction if no Kelly data
            kelly_size = params.account_balance * self.max_risk_per_trade / entry_price
            metadata['method'] = 'fixed_fraction'
        
        # 2. Risk-based sizing (if stop loss provided)
        if stop_loss and stop_loss != entry_price:
            risk_amount = params.account_balance * self.max_risk_per_trade
            price_risk = abs(entry_price - stop_loss)
            risk_size = risk_amount / price_risk if price_risk > 0 else 0
            metadata['risk_pct'] = self.max_risk_per_trade
        else:
            risk_size = kelly_size
        
        # Take minimum of Kelly and risk-based
        base_size = min(kelly_size, risk_size)
        
        # 3. Volatility adjustment
        if params.volatility > 0:
            base_size = self.volatility_adjusted_size(base_size, params.volatility)
            metadata['vol_adjustment'] = self.volatility_adjusted_size(1.0, params.volatility)
        
        # 4. Confidence scaling
        base_size *= params.confidence
        
        # 5. Apply TAEP/Risk Manager constraints
        max_size = self.risk_manager.max_position_size
        if base_size > max_size:
            base_size = max_size
            metadata['constraints_applied'].append('max_position_limit')
        
        # 6. Apply minimum size
        if base_size < self.min_position_size:
            base_size = 0.0  # Too small to trade
            metadata['constraints_applied'].append('below_minimum')
        
        # 7. Round to standard lot sizes
        # Forex: 0.01 lots minimum, 0.01 increments
        base_size = round(base_size * 100) / 100
        
        metadata['final_size'] = base_size
        metadata['account_pct'] = (base_size * entry_price) / params.account_balance
        
        logger.debug(f"Position size for {symbol}: {base_size} lots (meta: {metadata})")
        
        return base_size, metadata
    
    def quick_size(
        self,
        account_balance: float,
        entry_price: float,
        confidence: float = 0.5,
        volatility: float = 0.01
    ) -> float:
        """
        Quick position size calculation with defaults
        
        For rapid signal response
        """
        params = SizingParams(
            account_balance=account_balance,
            win_rate=0.5,  # Assume 50%
            avg_win=100,
            avg_loss=50,
            volatility=volatility,
            confidence=confidence,
            risk_per_trade=self.max_risk_per_trade
        )
        
        size, _ = self.calculate_position_size(params, entry_price)
        return size
    
    def get_default_params(
        self,
        account_balance: float,
        historical_trades: Optional[list] = None
    ) -> SizingParams:
        """
        Generate sizing params from historical data
        
        If no history provided, uses conservative defaults
        """
        if historical_trades and len(historical_trades) > 10:
            # Calculate from history
            wins = [t['pnl'] for t in historical_trades if t['pnl'] > 0]
            losses = [t['pnl'] for t in historical_trades if t['pnl'] < 0]
            
            win_rate = len(wins) / len(historical_trades)
            avg_win = np.mean(wins) if wins else 100
            avg_loss = abs(np.mean(losses)) if losses else 50
            
            # Calculate volatility from returns
            returns = [t['return_pct'] for t in historical_trades if 'return_pct' in t]
            volatility = np.std(returns) if returns else 0.01
        else:
            # Conservative defaults
            win_rate = 0.5
            avg_win = 100
            avg_loss = 50
            volatility = 0.01
        
        return SizingParams(
            account_balance=account_balance,
            win_rate=win_rate,
            avg_win=avg_win,
            avg_loss=avg_loss,
            volatility=volatility,
            confidence=0.7,  # Moderate confidence default
            risk_per_trade=self.max_risk_per_trade
        )


# Global instance
position_sizer: Optional[PositionSizer] = None


def get_position_sizer(
    kelly_fraction: float = 0.25,
    max_risk_per_trade: float = 0.02
) -> PositionSizer:
    """Get or create global position sizer"""
    global position_sizer
    if position_sizer is None:
        position_sizer = PositionSizer(kelly_fraction, max_risk_per_trade)
    return position_sizer


# Example usage
if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    
    # Create sizer
    sizer = get_position_sizer()
    
    # Test Kelly calculation
    kelly = sizer.kelly_criterion(win_rate=0.6, avg_win=150, avg_loss=100)
    print(f"Kelly fraction: {kelly:.2%}")
    
    # Test position sizing
    params = SizingParams(
        account_balance=10000.0,
        win_rate=0.55,
        avg_win=120,
        avg_loss=80,
        volatility=0.015,
        confidence=0.8,
        risk_per_trade=0.02
    )
    
    size, meta = sizer.calculate_position_size(
        params,
        entry_price=1.0850,
        stop_loss=1.0800,
        symbol='EURUSD'
    )
    
    print(f"Position size: {size} lots")
    print(f"Metadata: {meta}")
