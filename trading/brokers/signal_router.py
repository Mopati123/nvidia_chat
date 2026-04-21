"""
Signal Router
Routes TradingView signals to appropriate broker (Deriv or MT5)
Handles symbol mapping, timeframe validation, and best execution
"""

import logging
import time
from typing import Dict, Optional, List, Callable
from dataclasses import dataclass
from enum import Enum

from trading.brokers.tradingview_connector import TradingViewSignal, get_tradingview_connector
from trading.brokers.deriv_broker import DerivBroker, deriv_broker
from trading.brokers.mt5_broker import MT5Broker, mt5_broker

logger = logging.getLogger(__name__)


class BrokerType(Enum):
    DERIV = "deriv"
    MT5 = "mt5"
    NONE = "none"


@dataclass
class RoutedOrder:
    """Order after routing"""
    signal: TradingViewSignal
    broker: BrokerType
    symbol: str
    direction: str
    size: float
    price: float
    metadata: Dict


class SymbolMapper:
    """
    Maps TradingView symbols to broker-specific symbols
    """
    
    # TradingView to Deriv mapping
    TV_TO_DERIV = {
        'EURUSD': 'frxEURUSD',
        'GBPUSD': 'frxGBPUSD',
        'USDJPY': 'frxUSDJPY',
        'USDCHF': 'frxUSDCHF',
        'AUDUSD': 'frxAUDUSD',
        'USDCAD': 'frxUSDCAD',
        'NZDUSD': 'frxNZDUSD',
        'EURGBP': 'frxEURGBP',
        'XAUUSD': 'frxXAUUSD',
        'XAGUSD': 'frxXAGUSD',
        'BTCUSD': 'cryBTCUSD',
        'ETHUSD': 'cryETHUSD',
        'R_10': 'R_10',
        'R_25': 'R_25',
        'R_50': 'R_50',
        'R_75': 'R_75',
        'R_100': 'R_100',
    }
    
    # TradingView to MT5 mapping (usually same, but allows customization)
    TV_TO_MT5 = {
        'EURUSD': 'EURUSD',
        'GBPUSD': 'GBPUSD',
        'USDJPY': 'USDJPY',
        'XAUUSD': 'XAUUSD',
        'BTCUSD': 'BTCUSD',
    }
    
    @classmethod
    def to_deriv(cls, tv_symbol: str) -> Optional[str]:
        """Convert TradingView symbol to Deriv symbol"""
        # Try exact match first
        if tv_symbol in cls.TV_TO_DERIV:
            return cls.TV_TO_DERIV[tv_symbol]
        
        # Try without prefix
        if tv_symbol.startswith('TV_'):
            tv_symbol = tv_symbol[3:]
        
        return cls.TV_TO_DERIV.get(tv_symbol)
    
    @classmethod
    def to_mt5(cls, tv_symbol: str) -> Optional[str]:
        """Convert TradingView symbol to MT5 symbol"""
        if tv_symbol in cls.TV_TO_MT5:
            return cls.TV_TO_MT5[tv_symbol]
        return tv_symbol  # Usually same
    
    @classmethod
    def is_synthetic(cls, tv_symbol: str) -> bool:
        """Check if symbol is synthetic (Deriv only)"""
        return tv_symbol.startswith('R_') or tv_symbol in ['R_10', 'R_25', 'R_50', 'R_75', 'R_100']


class SignalRouter:
    """
    Routes TradingView signals to best broker
    
    Routing logic:
    1. Synthetic indices → Deriv only
    2. Forex majors → Both (best spread)
    3. Crypto → Both (best spread)
    4. Timeframe compatibility check
    """
    
    def __init__(
        self,
        prefer_deriv: bool = True,
        enable_mt5: bool = True,
        timeframe_whitelist: Optional[List[str]] = None
    ):
        self.prefer_deriv = prefer_deriv
        self.enable_mt5 = enable_mt5
        self.timeframe_whitelist = timeframe_whitelist or ['1m', '5m', '15m', '1h', '4h']
        
        # Broker instances
        self.deriv: Optional[DerivBroker] = None
        self.mt5: Optional[MT5Broker] = None
        
        # Routing stats
        self.stats = {
            'routed_deriv': 0,
            'routed_mt5': 0,
            'rejected_timeframe': 0,
            'rejected_symbol': 0,
            'rejected_no_broker': 0,
            'last_route': None
        }
        
        # Callbacks
        self.pre_route_handlers: List[Callable] = []
        self.post_route_handlers: List[Callable] = []
        
        self._initialize_brokers()
    
    def _initialize_brokers(self):
        """Initialize broker connections"""
        try:
            self.deriv = deriv_broker
            if self.deriv.connect():
                logger.info("Deriv broker connected")
            else:
                logger.warning("Deriv broker failed to connect")
                self.deriv = None
        except Exception as e:
            logger.warning(f"Deriv not available: {e}")
            self.deriv = None
        
        if self.enable_mt5:
            try:
                self.mt5 = mt5_broker
                if self.mt5.connect():
                    logger.info("MT5 broker connected")
                else:
                    logger.warning("MT5 broker failed to connect")
                    self.mt5 = None
            except Exception as e:
                logger.warning(f"MT5 not available: {e}")
                self.mt5 = None
    
    def register_pre_route(self, handler: Callable[[TradingViewSignal], Optional[TradingViewSignal]]):
        """Register handler called before routing (can modify signal)"""
        self.pre_route_handlers.append(handler)
    
    def register_post_route(self, handler: Callable[[RoutedOrder], None]):
        """Register handler called after routing"""
        self.post_route_handlers.append(handler)
    
    def validate_timeframe(self, timeframe: str) -> bool:
        """Check if timeframe is supported"""
        return timeframe in self.timeframe_whitelist
    
    def select_broker(self, signal: TradingViewSignal) -> BrokerType:
        """
        Select best broker for signal
        
        Rules:
        1. Synthetics → Deriv only
        2. If only one broker available → use that
        3. Prefer based on setting
        4. Check symbol availability
        """
        symbol = signal.symbol
        
        # Synthetic indices are Deriv only
        if SymbolMapper.is_synthetic(symbol):
            if self.deriv:
                return BrokerType.DERIV
            logger.warning(f"Synthetic {symbol} but Deriv not available")
            return BrokerType.NONE
        
        # Check available brokers
        deriv_available = self.deriv is not None and SymbolMapper.to_deriv(symbol)
        mt5_available = self.mt5 is not None and SymbolMapper.to_mt5(symbol)
        
        if deriv_available and mt5_available:
            # Both available - use preference
            return BrokerType.DERIV if self.prefer_deriv else BrokerType.MT5
        elif deriv_available:
            return BrokerType.DERIV
        elif mt5_available:
            return BrokerType.MT5
        else:
            return BrokerType.NONE
    
    def route_signal(self, signal: TradingViewSignal) -> Optional[RoutedOrder]:
        """
        Route a TradingView signal to appropriate broker
        
        Returns RoutedOrder or None if rejected
        """
        # Pre-route handlers
        for handler in self.pre_route_handlers:
            try:
                modified = handler(signal)
                if modified is None:
                    logger.info(f"Signal {signal.symbol} rejected by pre-route handler")
                    return None
                signal = modified
            except Exception as e:
                logger.error(f"Pre-route handler error: {e}")
        
        # Validate timeframe
        if not self.validate_timeframe(signal.timeframe):
            self.stats['rejected_timeframe'] += 1
            logger.warning(f"Timeframe {signal.timeframe} not in whitelist")
            return None
        
        # Select broker
        broker = self.select_broker(signal)
        
        if broker == BrokerType.NONE:
            self.stats['rejected_no_broker'] += 1
            logger.warning(f"No broker available for {signal.symbol}")
            return None
        
        # Map symbol
        if broker == BrokerType.DERIV:
            broker_symbol = SymbolMapper.to_deriv(signal.symbol)
        else:
            broker_symbol = SymbolMapper.to_mt5(signal.symbol)
        
        if not broker_symbol:
            self.stats['rejected_symbol'] += 1
            logger.warning(f"Symbol mapping failed for {signal.symbol}")
            return None
        
        # Create routed order
        order = RoutedOrder(
            signal=signal,
            broker=broker,
            symbol=broker_symbol,
            direction=signal.signal.lower(),  # buy/sell
            size=0.01,  # Minimum size, will be adjusted by position sizer
            price=signal.price,
            metadata={
                'routed_at': time.time(),
                'tv_symbol': signal.symbol,
                'tv_timeframe': signal.timeframe,
                'rsi': signal.rsi,
                'ofi': signal.ofi,
                'in_killzone': signal.in_killzone
            }
        )
        
        # Update stats
        if broker == BrokerType.DERIV:
            self.stats['routed_deriv'] += 1
        else:
            self.stats['routed_mt5'] += 1
        
        self.stats['last_route'] = f"{signal.symbol} → {broker.value}:{broker_symbol}"
        logger.info(f"Routed: {self.stats['last_route']}")
        
        # Post-route handlers
        for handler in self.post_route_handlers:
            try:
                handler(order)
            except Exception as e:
                logger.error(f"Post-route handler error: {e}")
        
        return order
    
    def connect_to_tradingview(self):
        """Auto-connect to TradingView connector"""
        tv = get_tradingview_connector()
        tv.register_handler(self.route_signal)
        logger.info("SignalRouter connected to TradingView connector")
    
    def get_stats(self) -> Dict:
        """Get routing statistics"""
        return {
            **self.stats,
            'deriv_connected': self.deriv is not None,
            'mt5_connected': self.mt5 is not None,
            'timeframes_whitelisted': self.timeframe_whitelist
        }


# Global router instance
signal_router: Optional[SignalRouter] = None


def get_signal_router(
    prefer_deriv: bool = True,
    enable_mt5: bool = True
) -> SignalRouter:
    """Get or create global signal router"""
    global signal_router
    if signal_router is None:
        signal_router = SignalRouter(prefer_deriv, enable_mt5)
    return signal_router


# Example usage
if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    
    # Create router
    router = get_signal_router()
    
    # Create test signal
    test_signal = TradingViewSignal(
        symbol='EURUSD',
        timeframe='1h',
        price=1.0850,
        signal='BUY',
        rsi=35.0,
        ofi=100.0,
        microprice=1.0851,
        in_killzone=True,
        timestamp=time.time(),
        raw_data={}
    )
    
    # Route it
    order = router.route_signal(test_signal)
    if order:
        print(f"Routed to {order.broker.value}: {order.symbol}")
    else:
        print("Signal rejected")
    
    print(f"Stats: {router.get_stats()}")
