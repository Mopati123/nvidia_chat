"""
Multi-Broker Sync
Best execution across Deriv + MT5
Slippage comparison and fill rate tracking
"""

import time
import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from collections import defaultdict

from trading.brokers.deriv_broker import DerivBroker
from trading.brokers.mt5_broker import MT5Broker

logger = logging.getLogger(__name__)


@dataclass
class BrokerQuote:
    """Quote from a broker"""
    broker: str
    symbol: str
    bid: float
    ask: float
    spread: float
    timestamp: float
    latency_ms: float


@dataclass
class ExecutionResult:
    """Result of order execution"""
    broker: str
    symbol: str
    direction: str
    size: float
    requested_price: float
    executed_price: float
    slippage: float
    execution_time_ms: float
    success: bool
    error: Optional[str] = None


class MultiBrokerSync:
    """
    Synchronizes and optimizes across multiple brokers
    
    Features:
    - Best price selection (lowest spread)
    - Slippage tracking per broker
    - Fill rate monitoring
    - Failover execution
    - Quote aggregation
    """
    
    def __init__(
        self,
        deriv: Optional[DerivBroker] = None,
        mt5: Optional[MT5Broker] = None,
        prefer_best_price: bool = True,
        slippage_threshold: float = 0.0001  # 1 pip
    ):
        self.deriv = deriv
        self.mt5 = mt5
        self.prefer_best_price = prefer_best_price
        self.slippage_threshold = slippage_threshold
        
        # Statistics
        self.quotes_received = 0
        self.executions = 0
        self.slippage_events = 0
        self.failed_executions = 0
        
        # Performance tracking
        self.broker_stats = defaultdict(lambda: {
            'trades': 0,
            'total_slippage': 0.0,
            'avg_slippage': 0.0,
            'fills': 0,
            'failures': 0,
            'avg_latency_ms': 0.0
        })
        
        # Quote cache
        self.latest_quotes: Dict[str, BrokerQuote] = {}
        
        logger.info(f"MultiBrokerSync initialized: Deriv={deriv is not None}, MT5={mt5 is not None}")
    
    def get_quotes(self, symbol: str) -> List[BrokerQuote]:
        """
        Get quotes from all available brokers
        
        Returns list of BrokerQuote, sorted by spread (best first)
        """
        quotes = []
        
        # Get Deriv quote
        if self.deriv:
            start = time.time()
            try:
                tick = self.deriv.get_tick(symbol)
                if tick:
                    latency = (time.time() - start) * 1000
                    quote = BrokerQuote(
                        broker='deriv',
                        symbol=symbol,
                        bid=tick.get('bid', 0),
                        ask=tick.get('ask', 0),
                        spread=tick.get('ask', 0) - tick.get('bid', 0),
                        timestamp=time.time(),
                        latency_ms=latency
                    )
                    quotes.append(quote)
                    self.latest_quotes[f"deriv_{symbol}"] = quote
                    self.quotes_received += 1
            except Exception as e:
                logger.warning(f"Failed to get Deriv quote for {symbol}: {e}")
        
        # Get MT5 quote
        if self.mt5:
            start = time.time()
            try:
                tick = self.mt5.get_tick(symbol)
                if tick:
                    latency = (time.time() - start) * 1000
                    quote = BrokerQuote(
                        broker='mt5',
                        symbol=symbol,
                        bid=tick.get('bid', 0),
                        ask=tick.get('ask', 0),
                        spread=tick.get('ask', 0) - tick.get('bid', 0),
                        timestamp=time.time(),
                        latency_ms=latency
                    )
                    quotes.append(quote)
                    self.latest_quotes[f"mt5_{symbol}"] = quote
                    self.quotes_received += 1
            except Exception as e:
                logger.warning(f"Failed to get MT5 quote for {symbol}: {e}")
        
        # Sort by spread (ascending = best first)
        quotes.sort(key=lambda q: q.spread)
        
        return quotes
    
    def get_best_broker(
        self,
        symbol: str,
        direction: str,
        size: float
    ) -> Tuple[str, float]:
        """
        Determine best broker for execution
        
        Returns: (broker_name, expected_price)
        """
        quotes = self.get_quotes(symbol)
        
        if not quotes:
            logger.error(f"No quotes available for {symbol}")
            return ('none', 0.0)
        
        if len(quotes) == 1:
            # Only one broker available
            q = quotes[0]
            price = q.ask if direction == 'buy' else q.bid
            return (q.broker, price)
        
        # Compare brokers
        if self.prefer_best_price:
            # Select broker with best spread
            best = quotes[0]
            price = best.ask if direction == 'buy' else best.bid
            
            # Log comparison
            if len(quotes) > 1:
                spread_diff = quotes[1].spread - best.spread
                logger.debug(f"Best broker for {symbol}: {best.broker} "
                           f"(spread {best.spread:.5f}, saved {spread_diff:.5f})")
            
            return (best.broker, price)
        else:
            # Use historical performance (currently just use first available)
            q = quotes[0]
            price = q.ask if direction == 'buy' else q.bid
            return (q.broker, price)
    
    def execute_best(
        self,
        symbol: str,
        direction: str,
        size: float,
        order_type: str = 'market'
    ) -> ExecutionResult:
        """
        Execute on best available broker with failover
        
        Tries best broker first, falls back to others on failure
        """
        start_time = time.time()
        
        # Get broker priority
        quotes = self.get_quotes(symbol)
        
        if not quotes:
            self.failed_executions += 1
            return ExecutionResult(
                broker='none',
                symbol=symbol,
                direction=direction,
                size=size,
                requested_price=0,
                executed_price=0,
                slippage=0,
                execution_time_ms=0,
                success=False,
                error="No quotes available"
            )
        
        # Try each broker in order
        for quote in quotes:
            broker_name = quote.broker
            requested_price = quote.ask if direction == 'buy' else quote.bid
            
            try:
                # Execute
                if broker_name == 'deriv' and self.deriv:
                    result = self._execute_deriv(
                        symbol, direction, size, requested_price
                    )
                elif broker_name == 'mt5' and self.mt5:
                    result = self._execute_mt5(
                        symbol, direction, size, requested_price
                    )
                else:
                    continue
                
                # Success
                if result.success:
                    result.execution_time_ms = (time.time() - start_time) * 1000
                    self._update_stats(result)
                    return result
                
            except Exception as e:
                logger.warning(f"Execution failed on {broker_name}: {e}")
                continue
        
        # All brokers failed
        self.failed_executions += 1
        return ExecutionResult(
            broker='all_failed',
            symbol=symbol,
            direction=direction,
            size=size,
            requested_price=0,
            executed_price=0,
            slippage=0,
            execution_time_ms=(time.time() - start_time) * 1000,
            success=False,
            error="All brokers failed"
        )
    
    def _execute_deriv(
        self,
        symbol: str,
        direction: str,
        size: float,
        requested_price: float
    ) -> ExecutionResult:
        """Execute on Deriv"""
        if not self.deriv:
            return ExecutionResult(
                broker='deriv',
                symbol=symbol,
                direction=direction,
                size=size,
                requested_price=requested_price,
                executed_price=0,
                slippage=0,
                execution_time_ms=0,
                success=False,
                error="Deriv not available"
            )
        
        try:
            # Place order (paper mode - just simulate)
            # In real mode: order = self.deriv.place_order(...)
            executed_price = requested_price  # Simulated fill
            
            slippage = abs(executed_price - requested_price)
            
            return ExecutionResult(
                broker='deriv',
                symbol=symbol,
                direction=direction,
                size=size,
                requested_price=requested_price,
                executed_price=executed_price,
                slippage=slippage,
                execution_time_ms=0,
                success=True
            )
            
        except Exception as e:
            return ExecutionResult(
                broker='deriv',
                symbol=symbol,
                direction=direction,
                size=size,
                requested_price=requested_price,
                executed_price=0,
                slippage=0,
                execution_time_ms=0,
                success=False,
                error=str(e)
            )
    
    def _execute_mt5(
        self,
        symbol: str,
        direction: str,
        size: float,
        requested_price: float
    ) -> ExecutionResult:
        """Execute on MT5"""
        if not self.mt5:
            return ExecutionResult(
                broker='mt5',
                symbol=symbol,
                direction=direction,
                size=size,
                requested_price=requested_price,
                executed_price=0,
                slippage=0,
                execution_time_ms=0,
                success=False,
                error="MT5 not available"
            )
        
        try:
            # Place order (paper mode - just simulate)
            executed_price = requested_price  # Simulated fill
            
            slippage = abs(executed_price - requested_price)
            
            return ExecutionResult(
                broker='mt5',
                symbol=symbol,
                direction=direction,
                size=size,
                requested_price=requested_price,
                executed_price=executed_price,
                slippage=slippage,
                execution_time_ms=0,
                success=True
            )
            
        except Exception as e:
            return ExecutionResult(
                broker='mt5',
                symbol=symbol,
                direction=direction,
                size=size,
                requested_price=requested_price,
                executed_price=0,
                slippage=0,
                execution_time_ms=0,
                success=False,
                error=str(e)
            )
    
    def _update_stats(self, result: ExecutionResult):
        """Update broker statistics"""
        self.executions += 1
        
        stats = self.broker_stats[result.broker]
        stats['trades'] += 1
        stats['total_slippage'] += result.slippage
        stats['avg_slippage'] = stats['total_slippage'] / stats['trades']
        
        if result.slippage > self.slippage_threshold:
            self.slippage_events += 1
        
        if result.success:
            stats['fills'] += 1
        else:
            stats['failures'] += 1
        
        # Update average latency
        prev_latency = stats['avg_latency_ms']
        stats['avg_latency_ms'] = (
            (prev_latency * (stats['trades'] - 1) + result.execution_time_ms)
            / stats['trades']
        )
    
    def get_best_broker_report(self) -> Dict:
        """Generate broker performance comparison"""
        if not self.broker_stats:
            return {'message': 'No execution data yet'}
        
        # Calculate fill rates
        report = {}
        for broker, stats in self.broker_stats.items():
            fill_rate = stats['fills'] / max(1, stats['trades'])
            report[broker] = {
                'trades': stats['trades'],
                'fill_rate': fill_rate,
                'avg_slippage': stats['avg_slippage'],
                'avg_latency_ms': stats['avg_latency_ms'],
                'failures': stats['failures']
            }
        
        # Rank by composite score (lower is better)
        ranked = sorted(
            report.items(),
            key=lambda x: (
                -x[1]['fill_rate'],  # Higher fill rate better
                x[1]['avg_slippage'],  # Lower slippage better
                x[1]['avg_latency_ms']  # Lower latency better
            ),
            reverse=True
        )
        
        return {
            'rankings': [
                {'broker': b, 'rank': i+1, **data}
                for i, (b, data) in enumerate(ranked)
            ],
            'best_broker': ranked[0][0] if ranked else None,
            'slippage_events': self.slippage_events,
            'failed_executions': self.failed_executions,
            'total_executions': self.executions
        }
    
    def get_status(self) -> Dict:
        """Get sync status"""
        return {
            'deriv_connected': self.deriv is not None,
            'mt5_connected': self.mt5 is not None,
            'quotes_received': self.quotes_received,
            'executions': self.executions,
            'slippage_events': self.slippage_events,
            'failed_executions': self.failed_executions,
            'broker_performance': self.get_best_broker_report()
        }


# Example usage
if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    
    # Create sync (with mock brokers for demo)
    sync = MultiBrokerSync(deriv=None, mt5=None)
    
    print(f"Status: {sync.get_status()}")
