"""
Production Risk Manager
Implements all critical risk controls for live trading
- Daily loss limits
- Position sizing limits
- Hard stops
- Correlated exposure
- Kill switch
"""

import os
import time
import logging
from typing import Dict, Optional, List, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import Lock
from enum import Enum

logger = logging.getLogger(__name__)


class RiskLevel(Enum):
    GREEN = "green"      # Normal
    YELLOW = "yellow"    # Warning
    RED = "red"          # Critical - block new trades
    KILL = "kill"        # Emergency stop all


@dataclass
class RiskCheck:
    """Result of a risk check"""
    passed: bool
    level: RiskLevel
    message: str
    metric: str
    value: float
    limit: float


@dataclass 
class Position:
    """Open position tracking"""
    symbol: str
    direction: str  # buy/sell
    size: float
    entry_price: float
    current_price: float
    unrealized_pnl: float = 0.0
    entry_time: float = field(default_factory=time.time)
    broker: str = "unknown"
    
    def update_price(self, price: float):
        """Update current price and PnL"""
        self.current_price = price
        if self.direction == 'buy':
            self.unrealized_pnl = (price - self.entry_price) * self.size
        else:
            self.unrealized_pnl = (self.entry_price - price) * self.size


class ProductionRiskManager:
    """
    Production-grade risk management system
    
    Enforces:
    - Daily loss limit (hard stop)
    - Position size limits
    - Max positions per symbol
    - Correlated exposure limits
    - Kill switch (emergency stop)
    """
    
    def __init__(
        self,
        daily_loss_limit: Optional[float] = None,
        max_position_size: Optional[float] = None,
        max_positions_per_symbol: int = 1,
        max_correlated_exposure: float = 0.3,
        kill_switch_on: bool = False
    ):
        # Configuration (with env overrides)
        self.daily_loss_limit = daily_loss_limit or float(os.getenv('MAX_DAILY_LOSS', 100.0))
        self.max_position_size = max_position_size or float(os.getenv('MAX_POSITION_SIZE', 0.1))
        self.max_positions_per_symbol = max_positions_per_symbol
        self.max_correlated_exposure = max_correlated_exposure
        
        # Kill switch
        self.kill_switch_on = kill_switch_on
        self.manual_kill_switch = False
        
        # State
        self.lock = Lock()
        self.positions: Dict[str, Position] = {}  # position_id -> Position
        self.daily_pnl = 0.0
        self.peak_daily_pnl = 0.0
        self.max_drawdown = 0.0
        self.trades_today = 0
        self.last_reset_date = datetime.now(timezone.utc).date()
        
        # Correlation groups
        self.correlation_groups = {
            'USD': ['EURUSD', 'GBPUSD', 'AUDUSD', 'NZDUSD', 'XAUUSD'],
            'EUR': ['EURUSD', 'EURGBP'],
            'GBP': ['GBPUSD', 'EURGBP'],
            'JPY': ['USDJPY'],
            'SYNTH': ['R_10', 'R_25', 'R_50', 'R_75', 'R_100']
        }
        
        # Callbacks
        self.on_breach_callbacks: List[Callable] = []
        self.on_kill_switch_callbacks: List[Callable] = []
        
        # Statistics
        self.total_checks = 0
        self.passed_checks = 0
        self.breaches = 0
        
        logger.info(f"RiskManager initialized: daily_loss_limit=${self.daily_loss_limit}, "
                   f"max_size={self.max_position_size} lots")
    
    def register_breach_callback(self, callback: Callable[[RiskCheck], None]):
        """Register callback when risk limit breached"""
        self.on_breach_callbacks.append(callback)
    
    def register_kill_callback(self, callback: Callable[[], None]):
        """Register callback when kill switch triggered"""
        self.on_kill_switch_callbacks.append(callback)
    
    def _check_daily_reset(self):
        """Reset daily stats at midnight UTC"""
        current_date = datetime.now(timezone.utc).date()
        if current_date != self.last_reset_date:
            with self.lock:
                self.daily_pnl = 0.0
                self.peak_daily_pnl = 0.0
                self.max_drawdown = 0.0
                self.trades_today = 0
                self.last_reset_date = current_date
                logger.info(f"Daily stats reset for {current_date}")
    
    def check_all_limits(
        self,
        symbol: str,
        direction: str,
        size: float,
        price: float
    ) -> RiskCheck:
        """
        Comprehensive risk check before trade
        
        Returns RiskCheck with passed=True if all limits ok
        """
        self._check_daily_reset()
        
        self.total_checks += 1
        
        # 1. Kill switch check (highest priority)
        if self.kill_switch_on or self.manual_kill_switch:
            return RiskCheck(
                passed=False,
                level=RiskLevel.KILL,
                message="KILL SWITCH ACTIVE - All trading halted",
                metric="kill_switch",
                value=1.0,
                limit=0.0
            )
        
        # 2. Daily loss limit check
        unrealized_total = sum(p.unrealized_pnl for p in self.positions.values())
        total_pnl = self.daily_pnl + unrealized_total
        
        if total_pnl <= -self.daily_loss_limit:
            return RiskCheck(
                passed=False,
                level=RiskLevel.RED,
                message=f"Daily loss limit BREACHED: ${total_pnl:.2f} / ${self.daily_loss_limit:.2f}",
                metric="daily_loss",
                value=abs(total_pnl),
                limit=self.daily_loss_limit
            )
        
        # 3. Position size check
        if size > self.max_position_size:
            return RiskCheck(
                passed=False,
                level=RiskLevel.RED,
                message=f"Position size {size} exceeds max {self.max_position_size}",
                metric="position_size",
                value=size,
                limit=self.max_position_size
            )
        
        # 4. Max positions per symbol
        symbol_positions = [p for p in self.positions.values() if p.symbol == symbol]
        if len(symbol_positions) >= self.max_positions_per_symbol:
            return RiskCheck(
                passed=False,
                level=RiskLevel.YELLOW,
                message=f"Max positions ({self.max_positions_per_symbol}) reached for {symbol}",
                metric="positions_per_symbol",
                value=len(symbol_positions),
                limit=self.max_positions_per_symbol
            )
        
        # 5. Correlated exposure check
        exposure = self._calculate_correlated_exposure(symbol, size)
        if exposure > self.max_correlated_exposure:
            return RiskCheck(
                passed=False,
                level=RiskLevel.YELLOW,
                message=f"Correlated exposure {exposure:.1%} exceeds limit {self.max_correlated_exposure:.1%}",
                metric="correlated_exposure",
                value=exposure,
                limit=self.max_correlated_exposure
            )
        
        # All checks passed
        self.passed_checks += 1
        return RiskCheck(
            passed=True,
            level=RiskLevel.GREEN,
            message="All risk checks passed",
            metric="all",
            value=0.0,
            limit=0.0
        )
    
    def _calculate_correlated_exposure(self, new_symbol: str, new_size: float) -> float:
        """Calculate correlated exposure for a symbol"""
        # Find which correlation group
        group = None
        for g_name, symbols in self.correlation_groups.items():
            if any(s in new_symbol for s in symbols):
                group = g_name
                break
        
        if not group:
            return 0.0  # No correlation data
        
        # Sum sizes in same group
        total_exposure = new_size
        for pos in self.positions.values():
            if any(s in pos.symbol for s in self.correlation_groups[group]):
                total_exposure += pos.size
        
        return total_exposure
    
    def add_position(self, position: Position) -> RiskCheck:
        """
        Add new position after risk check
        
        Returns RiskCheck - if failed, position not added
        """
        # Pre-check
        check = self.check_all_limits(
            position.symbol,
            position.direction,
            position.size,
            position.entry_price
        )
        
        if not check.passed:
            self.breaches += 1
            for callback in self.on_breach_callbacks:
                try:
                    callback(check)
                except Exception as e:
                    logger.error(f"Breach callback error: {e}")
            return check
        
        # Add position
        position_id = f"{position.symbol}_{int(time.time()*1000)}"
        with self.lock:
            self.positions[position_id] = position
            self.trades_today += 1
        
        logger.info(f"Position added: {position.symbol} {position.direction} {position.size} lots")
        return check
    
    def close_position(self, position_id: str, exit_price: float) -> Optional[float]:
        """Close position and update PnL"""
        with self.lock:
            position = self.positions.pop(position_id, None)
            if not position:
                return None
            
            # Calculate realized PnL
            if position.direction == 'buy':
                realized_pnl = (exit_price - position.entry_price) * position.size
            else:
                realized_pnl = (position.entry_price - exit_price) * position.size
            
            self.daily_pnl += realized_pnl
            
            # Update peak and drawdown
            if self.daily_pnl > self.peak_daily_pnl:
                self.peak_daily_pnl = self.daily_pnl
            
            current_dd = self.peak_daily_pnl - self.daily_pnl
            if current_dd > self.max_drawdown:
                self.max_drawdown = current_dd
            
            logger.info(f"Position closed: {position_id} PnL=${realized_pnl:.2f}")
            return realized_pnl
    
    def update_position_prices(self, prices: Dict[str, float]):
        """Update all position prices and unrealized PnL"""
        with self.lock:
            for pos_id, position in self.positions.items():
                if position.symbol in prices:
                    position.update_price(prices[position.symbol])
    
    def trigger_kill_switch(self, reason: str = "manual"):
        """Emergency kill switch - halt all trading"""
        self.manual_kill_switch = True
        logger.critical(f"KILL SWITCH TRIGGERED: {reason}")
        
        for callback in self.on_kill_switch_callbacks:
            try:
                callback()
            except Exception as e:
                logger.error(f"Kill switch callback error: {e}")
    
    def release_kill_switch(self):
        """Release kill switch after review"""
        self.manual_kill_switch = False
        logger.critical("KILL SWITCH RELEASED - Trading resumed")
    
    def get_status(self) -> Dict:
        """Get current risk status"""
        self._check_daily_reset()
        
        unrealized = sum(p.unrealized_pnl for p in self.positions.values())
        total_pnl = self.daily_pnl + unrealized
        
        # Determine risk level
        if self.kill_switch_on or self.manual_kill_switch:
            level = RiskLevel.KILL
        elif total_pnl <= -self.daily_loss_limit * 0.8:
            level = RiskLevel.RED
        elif total_pnl <= -self.daily_loss_limit * 0.5:
            level = RiskLevel.YELLOW
        else:
            level = RiskLevel.GREEN
        
        return {
            'level': level.value,
            'daily_pnl': total_pnl,
            'daily_loss_limit': self.daily_loss_limit,
            'remaining_limit': self.daily_loss_limit - abs(total_pnl) if total_pnl < 0 else self.daily_loss_limit,
            'open_positions': len(self.positions),
            'total_exposure': sum(p.size for p in self.positions.values()),
            'max_drawdown': self.max_drawdown,
            'trades_today': self.trades_today,
            'kill_switch': self.manual_kill_switch,
            'check_pass_rate': self.passed_checks / max(1, self.total_checks)
        }
    
    def get_position_report(self) -> List[Dict]:
        """Get report of all open positions"""
        return [
            {
                'symbol': p.symbol,
                'direction': p.direction,
                'size': p.size,
                'entry': p.entry_price,
                'current': p.current_price,
                'unrealized_pnl': p.unrealized_pnl,
                'broker': p.broker
            }
            for p in self.positions.values()
        ]


# Global instance
risk_manager: Optional[ProductionRiskManager] = None


def get_risk_manager(
    daily_loss_limit: Optional[float] = None,
    max_position_size: Optional[float] = None
) -> ProductionRiskManager:
    """Get or create global risk manager"""
    global risk_manager
    if risk_manager is None:
        risk_manager = ProductionRiskManager(daily_loss_limit, max_position_size)
    return risk_manager


# Example usage
if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    
    # Create manager
    rm = get_risk_manager(daily_loss_limit=100.0, max_position_size=0.1)
    
    # Test risk check
    check = rm.check_all_limits('EURUSD', 'buy', 0.05, 1.0850)
    print(f"Risk check: {check.passed} - {check.message}")
    
    # Add position
    pos = Position('EURUSD', 'buy', 0.05, 1.0850, 1.0850, broker='deriv')
    result = rm.add_position(pos)
    print(f"Add position: {result.passed}")
    
    # Get status
    status = rm.get_status()
    print(f"Status: {status}")
