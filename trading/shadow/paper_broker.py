"""
Paper Broker - Simulated Trading for Backtesting

Simulates trade execution with realistic market conditions:
- Slippage modeling
- Commission/spread costs
- Fill probability
- Virtual balance tracking
"""

import numpy as np
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class OrderSide(Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"


@dataclass
class Order:
    """Order specification"""
    symbol: str
    side: OrderSide
    size: float
    order_type: OrderType = OrderType.MARKET
    price: Optional[float] = None  # For limit/stop orders
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: Dict = field(default_factory=dict)


@dataclass
class ExecutionResult:
    """Result of order execution"""
    filled: bool
    symbol: str
    side: OrderSide
    size: float
    fill_price: float
    commission: float
    slippage: float
    timestamp: str
    order_id: str
    pnl: Optional[float] = None  # Realized PnL if closing position
    metadata: Dict = field(default_factory=dict)
    
    @property
    def total_cost(self) -> float:
        """Total cost including commission and slippage"""
        return self.fill_price * self.size + self.commission + self.slippage


@dataclass
class Position:
    """Current position state"""
    symbol: str
    side: OrderSide
    size: float
    entry_price: float
    entry_time: str
    unrealized_pnl: float = 0.0
    
    def update_unrealized_pnl(self, current_price: float):
        """Update unrealized PnL based on current price"""
        if self.side == OrderSide.BUY:
            self.unrealized_pnl = (current_price - self.entry_price) * self.size
        else:
            self.unrealized_pnl = (self.entry_price - current_price) * self.size


class PaperBroker:
    """
    Simulated broker for paper trading.
    
    Provides realistic trade simulation without real money risk.
    """
    
    def __init__(
        self,
        initial_balance: float = 10000.0,
        base_currency: str = "USD",
        slippage_model: str = "realistic",
        commission_rate: float = 0.0001,  # 1 pip = 0.01%
        spread_model: str = "variable"
    ):
        self.initial_balance = initial_balance
        self.balance = initial_balance
        self.base_currency = base_currency
        self.slippage_model = slippage_model
        self.commission_rate = commission_rate
        self.spread_model = spread_model
        
        # State tracking
        self.positions: Dict[str, Position] = {}
        self.trade_history: List[ExecutionResult] = []
        self.equity_curve: List[Dict] = []
        
        # Performance tracking
        self.total_trades = 0
        self.winning_trades = 0
        self.total_commission = 0.0
        
        logger.info(
            f"PaperBroker initialized: balance={initial_balance:.2f}, "
            f"commission={commission_rate:.4%}"
        )
    
    def execute_market_order(
        self,
        order: Order,
        current_price: float,
        market_depth: Optional[Dict] = None
    ) -> ExecutionResult:
        """
        Execute a market order with simulated slippage.
        
        Args:
            order: Order specification
            current_price: Current market price
            market_depth: Optional depth data for slippage calculation
        
        Returns:
            ExecutionResult with fill details
        """
        # Calculate slippage
        slippage = self._calculate_slippage(order, current_price, market_depth)
        
        # Apply slippage to fill price
        if order.side == OrderSide.BUY:
            fill_price = current_price * (1 + slippage)
        else:
            fill_price = current_price * (1 - slippage)
        
        # Calculate commission
        notional = fill_price * order.size
        commission = notional * self.commission_rate
        
        # Check if we have enough balance
        total_cost = notional + commission
        if order.side == OrderSide.BUY and total_cost > self.balance:
            logger.warning(f"Insufficient balance: {self.balance:.2f} < {total_cost:.2f}")
            return ExecutionResult(
                filled=False,
                symbol=order.symbol,
                side=order.side,
                size=0,
                fill_price=0,
                commission=0,
                slippage=0,
                timestamp=datetime.now().isoformat(),
                order_id=self._generate_order_id()
            )
        
        # Calculate realized PnL if closing position
        realized_pnl = None
        if order.symbol in self.positions:
            existing_pos = self.positions[order.symbol]
            if existing_pos.side != order.side:
                # Closing or reducing position
                close_size = min(order.size, existing_pos.size)
                if order.side == OrderSide.BUY:  # Closing short
                    realized_pnl = (existing_pos.entry_price - fill_price) * close_size
                else:  # Closing long
                    realized_pnl = (fill_price - existing_pos.entry_price) * close_size
        
        # Update balance
        if order.side == OrderSide.BUY:
            self.balance -= total_cost
        else:
            self.balance += notional - commission
        
        # Update or create position
        self._update_position(order, fill_price)
        
        # Track commission
        self.total_commission += commission
        self.total_trades += 1
        if realized_pnl is not None and realized_pnl > 0:
            self.winning_trades += 1
        
        # Create result
        result = ExecutionResult(
            filled=True,
            symbol=order.symbol,
            side=order.side,
            size=order.size,
            fill_price=fill_price,
            commission=commission,
            slippage=slippage * fill_price * order.size,  # Slippage cost in currency
            timestamp=datetime.now().isoformat(),
            order_id=self._generate_order_id(),
            pnl=realized_pnl
        )
        
        self.trade_history.append(result)
        
        # Update equity curve
        self._update_equity_curve()
        
        logger.debug(
            f"Executed {order.side.value} {order.size} {order.symbol} @ {fill_price:.5f} "
            f"(slippage={slippage:.4%}, commission={commission:.2f})"
        )
        
        return result
    
    def _calculate_slippage(
        self,
        order: Order,
        current_price: float,
        market_depth: Optional[Dict]
    ) -> float:
        """
        Calculate realistic slippage.
        
        Models:
        - 'realistic': Variable based on order size and volatility
        - 'fixed': Constant slippage (e.g., 0.01%)
        - 'none': No slippage (for testing)
        """
        if self.slippage_model == "none":
            return 0.0
        
        if self.slippage_model == "fixed":
            return 0.0001  # 1 pip
        
        # Realistic model: slippage increases with order size
        base_slippage = 0.00005  # 0.5 pip base
        
        # Scale with order size (larger orders = more slippage)
        size_factor = min(order.size / 100, 0.001)  # Cap at 10 pips
        
        # Add random component (market volatility)
        random_component = np.random.normal(0, 0.0001)
        
        slippage = base_slippage + size_factor + random_component
        return max(0, slippage)  # Slippage always against us
    
    def _update_position(self, order: Order, fill_price: float):
        """Update position tracking"""
        symbol = order.symbol
        
        if symbol not in self.positions:
            # New position
            self.positions[symbol] = Position(
                symbol=symbol,
                side=order.side,
                size=order.size,
                entry_price=fill_price,
                entry_time=datetime.now().isoformat()
            )
        else:
            existing = self.positions[symbol]
            
            if existing.side == order.side:
                # Adding to position (pyramiding)
                # Average entry price
                total_size = existing.size + order.size
                avg_price = (existing.entry_price * existing.size + fill_price * order.size) / total_size
                existing.size = total_size
                existing.entry_price = avg_price
            else:
                # Reducing or flipping position
                if order.size >= existing.size:
                    # Full close + reverse
                    remaining = order.size - existing.size
                    if remaining > 0:
                        self.positions[symbol] = Position(
                            symbol=symbol,
                            side=order.side,
                            size=remaining,
                            entry_price=fill_price,
                            entry_time=datetime.now().isoformat()
                        )
                    else:
                        del self.positions[symbol]
                else:
                    # Partial close
                    existing.size -= order.size
    
    def _update_equity_curve(self):
        """Update equity curve with current state"""
        # Calculate unrealized PnL
        unrealized = sum(pos.unrealized_pnl for pos in self.positions.values())
        
        equity = self.balance + unrealized
        
        self.equity_curve.append({
            'timestamp': datetime.now().isoformat(),
            'balance': self.balance,
            'unrealized_pnl': unrealized,
            'equity': equity,
            'total_positions': len(self.positions)
        })
    
    def _generate_order_id(self) -> str:
        """Generate unique order ID"""
        import hashlib
        import time
        data = f"{time.time()}{self.total_trades}"
        return hashlib.md5(data.encode()).hexdigest()[:12]
    
    def close_all_positions(self, current_prices: Dict[str, float]) -> List[ExecutionResult]:
        """Close all open positions"""
        results = []
        
        for symbol, position in list(self.positions.items()):
            current_price = current_prices.get(symbol, position.entry_price)
            
            # Create closing order
            close_side = OrderSide.SELL if position.side == OrderSide.BUY else OrderSide.BUY
            order = Order(
                symbol=symbol,
                side=close_side,
                size=position.size,
                order_type=OrderType.MARKET
            )
            
            result = self.execute_market_order(order, current_price)
            results.append(result)
        
        return results
    
    def get_position(self, symbol: str) -> Optional[Position]:
        """Get position for symbol"""
        return self.positions.get(symbol)
    
    def get_all_positions(self) -> Dict[str, Position]:
        """Get all positions"""
        return self.positions.copy()
    
    def get_performance_metrics(self) -> Dict:
        """
        Calculate comprehensive performance metrics.
        
        Returns dict with:
        - total_pnl: Total realized PnL
        - win_rate: Percentage of winning trades
        - sharpe_ratio: Risk-adjusted return
        - max_drawdown: Maximum equity drawdown
        - profit_factor: Gross profit / gross loss
        - avg_trade: Average PnL per trade
        - avg_winner: Average winning trade
        - avg_loser: Average losing trade
        """
        if not self.trade_history:
            return {
                'total_pnl': 0,
                'win_rate': 0,
                'sharpe_ratio': 0,
                'max_drawdown': 0,
                'profit_factor': 0,
                'avg_trade': 0,
                'avg_winner': 0,
                'avg_loser': 0
            }
        
        # Realized PnL from closed trades
        realized_pnls = [t.pnl for t in self.trade_history if t.pnl is not None]
        total_pnl = sum(realized_pnls) if realized_pnls else 0
        
        # Win rate
        winning_trades = [pnl for pnl in realized_pnls if pnl > 0]
        losing_trades = [pnl for pnl in realized_pnls if pnl < 0]
        win_rate = len(winning_trades) / len(realized_pnls) if realized_pnls else 0
        
        # Profit factor
        gross_profit = sum(winning_trades) if winning_trades else 0
        gross_loss = abs(sum(losing_trades)) if losing_trades else 1
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0
        
        # Average trade
        avg_trade = np.mean(realized_pnls) if realized_pnls else 0
        avg_winner = np.mean(winning_trades) if winning_trades else 0
        avg_loser = np.mean(losing_trades) if losing_trades else 0
        
        # Max drawdown from equity curve
        max_dd = self._calculate_max_drawdown()
        
        # Sharpe ratio (simplified, assuming daily returns)
        if len(self.equity_curve) > 1:
            returns = []
            for i in range(1, len(self.equity_curve)):
                prev_equity = self.equity_curve[i-1]['equity']
                curr_equity = self.equity_curve[i]['equity']
                if prev_equity > 0:
                    returns.append((curr_equity - prev_equity) / prev_equity)
            
            if returns and np.std(returns) > 0:
                sharpe = np.mean(returns) / np.std(returns) * np.sqrt(252)  # Annualized
            else:
                sharpe = 0
        else:
            sharpe = 0
        
        return {
            'total_pnl': total_pnl,
            'win_rate': win_rate,
            'sharpe_ratio': sharpe,
            'max_drawdown': max_dd,
            'profit_factor': profit_factor,
            'avg_trade': avg_trade,
            'avg_winner': avg_winner,
            'avg_loser': avg_loser,
            'total_trades': self.total_trades,
            'total_commission': self.total_commission,
            'current_balance': self.balance,
            'open_positions': len(self.positions)
        }
    
    def _calculate_max_drawdown(self) -> float:
        """Calculate maximum drawdown from equity curve"""
        if not self.equity_curve:
            return 0
        
        peak = self.equity_curve[0]['equity']
        max_dd = 0
        
        for point in self.equity_curve:
            equity = point['equity']
            if equity > peak:
                peak = equity
            dd = (peak - equity) / peak if peak > 0 else 0
            max_dd = max(max_dd, dd)
        
        return max_dd
    
    def get_trade_report(self) -> str:
        """Generate human-readable trade report"""
        metrics = self.get_performance_metrics()
        
        report = f"""
═══════════════════════════════════════════════════════════
              PAPER TRADING PERFORMANCE REPORT
═══════════════════════════════════════════════════════════

Balance: {metrics['current_balance']:.2f} (Initial: {self.initial_balance:.2f})
Total PnL: {metrics['total_pnl']:.2f} ({metrics['total_pnl']/self.initial_balance:.2%})

Trade Statistics:
  Total Trades: {metrics['total_trades']}
  Win Rate: {metrics['win_rate']:.2%}
  Profit Factor: {metrics['profit_factor']:.2f}
  Sharpe Ratio: {metrics['sharpe_ratio']:.2f}
  Max Drawdown: {metrics['max_drawdown']:.2%}

Trade Details:
  Average Trade: {metrics['avg_trade']:.2f}
  Average Winner: {metrics['avg_winner']:.2f}
  Average Loser: {metrics['avg_loser']:.2f}
  Total Commission: {metrics['total_commission']:.2f}

Open Positions: {metrics['open_positions']}
═══════════════════════════════════════════════════════════
"""
        return report
