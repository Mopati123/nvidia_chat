"""
broker_manager.py — Multi-broker orchestration and market data aggregation

Manages multiple broker connections, aggregates data sources, provides unified interface.
"""

import logging
import asyncio
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from collections import defaultdict
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class PriceFeed:
    """Unified price feed from any broker"""
    symbol: str
    price: float
    timestamp: datetime
    broker: str  # Source broker
    bid: Optional[float] = None
    ask: Optional[float] = None
    spread: Optional[float] = None
    
    
@dataclass
class AggregatedOHLCV:
    """Aggregated OHLCV data from multiple sources"""
    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int
    sources: List[str] = field(default_factory=list)  # Which brokers provided data
    price_variance: float = 0.0  # Variance between sources (for validation)


class BrokerManager:
    """
    Manages multiple broker connections and aggregates market data
    """
    
    # Symbol mappings: unified_symbol -> {broker: broker_specific_symbol}
    SYMBOL_MAP = {
        'EURUSD': {
            'deriv': 'frxEURUSD',
            'mt5': 'EURUSD',
            'yahoo': 'EURUSD=X'
        },
        'GBPUSD': {
            'deriv': 'frxGBPUSD',
            'mt5': 'GBPUSD',
            'yahoo': 'GBPUSD=X'
        },
        'USDJPY': {
            'deriv': 'frxUSDJPY',
            'mt5': 'USDJPY',
            'yahoo': 'USDJPY=X'
        },
        'BTCUSD': {
            'deriv': 'cryBTCUSD',
            'mt5': 'BTCUSD',
            'yahoo': 'BTC-USD'
        },
        'ETHUSD': {
            'deriv': 'cryETHUSD',
            'mt5': 'ETHUSD',
            'yahoo': 'ETH-USD'
        },
        'XAUUSD': {
            'deriv': 'frxXAUUSD',
            'mt5': 'XAUUSD',
            'yahoo': 'GC=F'
        },
        'US30': {
            'deriv': 'OTC_US30',
            'mt5': 'US30',
            'yahoo': '^DJI'
        },
        'VIX10': {
            'deriv': 'R_10',
            'mt5': 'Volatility 10 Index'
        },
        'VIX25': {
            'deriv': 'R_25',
            'mt5': 'Volatility 25 Index'
        },
        'VIX50': {
            'deriv': 'R_50',
            'mt5': 'Volatility 50 Index'
        },
    }
    
    def __init__(self):
        self.brokers: Dict[str, Any] = {}
        self.connected: Dict[str, bool] = {}
        self.credentials: Dict[str, Dict] = {}
        self.price_cache: Dict[str, List[PriceFeed]] = defaultdict(list)
        self.ohlcv_cache: Dict[str, List[AggregatedOHLCV]] = defaultdict(list)
        self.cache_ttl = timedelta(minutes=5)
        
    def register_broker(self, name: str, broker_instance: Any, credentials: Dict) -> bool:
        """
        Register a broker instance
        
        Args:
            name: Unique broker identifier (e.g., 'deriv_demo', 'mt5_icmarkets')
            broker_instance: Initialized broker object (DerivBroker, MT5Broker)
            credentials: Dict with connection info (for reconnection)
        """
        self.brokers[name] = broker_instance
        self.credentials[name] = credentials
        self.connected[name] = False
        logger.info(f"Registered broker: {name}")
        return True
    
    def connect_all(self) -> Dict[str, bool]:
        """Connect to all registered brokers, returns connection status"""
        results = {}
        for name, broker in self.brokers.items():
            try:
                if hasattr(broker, 'connect'):
                    success = broker.connect()
                    self.connected[name] = success
                    results[name] = success
                    logger.info(f"Broker '{name}': {'✓ connected' if success else '✗ failed'}")
                else:
                    logger.warning(f"Broker '{name}' has no connect method")
                    results[name] = False
            except Exception as e:
                logger.error(f"Failed to connect '{name}': {e}")
                self.connected[name] = False
                results[name] = False
        return results
    
    def disconnect_all(self):
        """Disconnect all brokers"""
        for name, broker in self.brokers.items():
            try:
                if hasattr(broker, 'disconnect'):
                    broker.disconnect()
                    logger.info(f"Disconnected broker: {name}")
            except Exception as e:
                logger.error(f"Error disconnecting '{name}': {e}")
            self.connected[name] = False
    
    def get_broker_symbol(self, unified_symbol: str, broker_name: str) -> Optional[str]:
        """Convert unified symbol to broker-specific symbol"""
        if unified_symbol in self.SYMBOL_MAP:
            return self.SYMBOL_MAP[unified_symbol].get(broker_name)
        
        # Try reverse lookup (if user passed broker-specific symbol)
        for uni, mappings in self.SYMBOL_MAP.items():
            if mappings.get(broker_name) == unified_symbol:
                return unified_symbol  # Already broker-specific
        
        return unified_symbol  # Return as-is if no mapping found
    
    def get_ohlcv(
        self,
        symbol: str,
        timeframe: str = '1h',
        count: int = 100,
        prefer_broker: Optional[str] = None
    ) -> List[AggregatedOHLCV]:
        """
        Fetch OHLCV data from available brokers with aggregation
        
        Priority: prefer_broker > MT5 > Deriv > Yahoo Finance
        """
        results = []
        errors = []
        
        # Determine broker order
        broker_order = list(self.brokers.keys())
        if prefer_broker and prefer_broker in broker_order:
            broker_order.remove(prefer_broker)
            broker_order.insert(0, prefer_broker)
        
        # Try each broker in priority order
        for broker_name in broker_order:
            if not self.connected.get(broker_name, False):
                continue
                
            broker = self.brokers[broker_name]
            broker_symbol = self.get_broker_symbol(symbol, broker_name.split('_')[0])
            
            try:
                # Handle different broker APIs
                if 'deriv' in broker_name.lower():
                    granularity = self._timeframe_to_deriv_granularity(timeframe)
                    data = broker.get_ohlcv(broker_symbol, granularity, count)
                elif 'mt5' in broker_name.lower():
                    tf_code = self._timeframe_to_mt5(timeframe)
                    data = broker.get_ohlcv(broker_symbol, tf_code, count)
                else:
                    continue
                
                if data:
                    # Convert to AggregatedOHLCV
                    for candle in data:
                        agg = AggregatedOHLCV(
                            symbol=symbol,
                            timestamp=datetime.fromisoformat(candle['timestamp']),
                            open=candle['open'],
                            high=candle['high'],
                            low=candle['low'],
                            close=candle['close'],
                            volume=candle.get('volume', 0),
                            sources=[broker_name]
                        )
                        results.append(agg)
                    
                    logger.info(f"Fetched {len(data)} candles from {broker_name} for {symbol}")
                    return results  # Return first successful source
                    
            except Exception as e:
                errors.append(f"{broker_name}: {e}")
                continue
        
        # Fallback to Yahoo Finance via market_data.py
        if not results:
            try:
                from .market_data import market_feed
                yahoo_symbol = self.SYMBOL_MAP.get(symbol, {}).get('yahoo', symbol)
                df = market_feed.fetch_ohlcv(yahoo_symbol, period='1mo', interval=timeframe)
                
                if df is not None and len(df) > 0:
                    # Convert Polars DataFrame to AggregatedOHLCV
                    for row in df.to_dicts():
                        agg = AggregatedOHLCV(
                            symbol=symbol,
                            timestamp=row.get('Date', datetime.now()),
                            open=row['Open'],
                            high=row['High'],
                            low=row['Low'],
                            close=row['Close'],
                            volume=int(row.get('Volume', 0)),
                            sources=['yahoo']
                        )
                        results.append(agg)
                    
                    logger.info(f"Fetched {len(results)} candles from Yahoo Finance for {symbol}")
                    
            except Exception as e:
                errors.append(f"yahoo: {e}")
        
        if not results:
            logger.error(f"Failed to fetch {symbol} from all sources: {errors}")
        
        return results
    
    def get_current_price(self, symbol: str) -> Optional[PriceFeed]:
        """Get current price from best available source"""
        broker_order = ['mt5', 'deriv']  # Priority order
        
        for broker_type in broker_order:
            # Find connected broker of this type
            for name, connected in self.connected.items():
                if not connected:
                    continue
                if not name.lower().startswith(broker_type):
                    continue
                
                broker = self.brokers[name]
                broker_symbol = self.get_broker_symbol(symbol, broker_type)
                
                try:
                    if broker_type == 'mt5':
                        import MetaTrader5 as mt5
                        tick = mt5.symbol_info_tick(broker_symbol)
                        if tick:
                            return PriceFeed(
                                symbol=symbol,
                                price=(tick.bid + tick.ask) / 2,
                                timestamp=datetime.now(),
                                broker=name,
                                bid=tick.bid,
                                ask=tick.ask,
                                spread=tick.ask - tick.bid
                            )
                    
                    elif broker_type == 'deriv':
                        price = broker.get_current_price(broker_symbol)
                        if price:
                            return PriceFeed(
                                symbol=symbol,
                                price=price,
                                timestamp=datetime.now(),
                                broker=name
                            )
                            
                except Exception as e:
                    logger.debug(f"Price fetch failed from {name}: {e}")
                    continue
        
        # Fallback to Yahoo
        try:
            from .market_data import market_feed
            yahoo_symbol = self.SYMBOL_MAP.get(symbol, {}).get('yahoo', symbol)
            price = market_feed.get_last_price(yahoo_symbol)
            if price:
                return PriceFeed(
                    symbol=symbol,
                    price=price,
                    timestamp=datetime.now(),
                    broker='yahoo'
                )
        except Exception as e:
            logger.debug(f"Yahoo fallback failed: {e}")
        
        return None
    
    def get_available_symbols(self) -> Dict[str, List[str]]:
        """
        Get symbols available on each connected broker
        Returns: {broker_name: [symbols]}
        """
        available = {}
        
        for name, broker in self.brokers.items():
            if not self.connected.get(name, False):
                continue
            
            try:
                # Check if broker has symbol discovery method
                if hasattr(broker, 'get_available_symbols'):
                    symbols = broker.get_available_symbols()
                    available[name] = symbols
                else:
                    # Use predefined mappings
                    broker_type = name.split('_')[0]
                    available[name] = [
                        sym for sym, mappings in self.SYMBOL_MAP.items()
                        if broker_type in mappings
                    ]
            except Exception as e:
                logger.error(f"Failed to get symbols from {name}: {e}")
                available[name] = []
        
        return available
    
    def compare_prices(self, symbol: str) -> Dict[str, Any]:
        """
        Get price from all sources and compare
        Useful for detecting arbitrage or data quality issues
        """
        prices = {}
        
        for name, broker in self.brokers.items():
            if not self.connected.get(name, False):
                continue
            
            broker_type = name.split('_')[0]
            broker_symbol = self.get_broker_symbol(symbol, broker_type)
            
            try:
                if broker_type == 'mt5':
                    import MetaTrader5 as mt5
                    tick = mt5.symbol_info_tick(broker_symbol)
                    if tick:
                        prices[name] = {
                            'bid': tick.bid,
                            'ask': tick.ask,
                            'mid': (tick.bid + tick.ask) / 2,
                            'spread': tick.ask - tick.bid
                        }
                
                elif broker_type == 'deriv':
                    price = broker.get_current_price(broker_symbol)
                    if price:
                        prices[name] = {'price': price}
                        
            except Exception as e:
                logger.debug(f"Price compare failed for {name}: {e}")
        
        # Calculate statistics
        if prices:
            all_prices = [p.get('mid', p.get('price', 0)) for p in prices.values()]
            return {
                'symbol': symbol,
                'sources': prices,
                'min_price': min(all_prices),
                'max_price': max(all_prices),
                'spread_pct': ((max(all_prices) - min(all_prices)) / np.mean(all_prices) * 100
                    if all_prices and np.mean(all_prices) > 0 else 0),
                'price_count': len(all_prices)
            }
        
        return {'symbol': symbol, 'sources': {}, 'error': 'No price data available'}
    
    def _timeframe_to_deriv_granularity(self, timeframe: str) -> int:
        """Convert timeframe string to Deriv granularity code"""
        mapping = {
            '1m': 60,
            '5m': 300,
            '15m': 900,
            '30m': 1800,
            '1h': 3600,
            '4h': 14400,
            '1d': 86400
        }
        return mapping.get(timeframe, 3600)
    
    def _timeframe_to_mt5(self, timeframe: str) -> int:
        """Convert timeframe string to MT5 constant"""
        try:
            import MetaTrader5 as mt5
            mapping = {
                '1m': mt5.TIMEFRAME_M1,
                '5m': mt5.TIMEFRAME_M5,
                '15m': mt5.TIMEFRAME_M15,
                '30m': mt5.TIMEFRAME_M30,
                '1h': mt5.TIMEFRAME_H1,
                '4h': mt5.TIMEFRAME_H4,
                '1d': mt5.TIMEFRAME_D1
            }
            return mapping.get(timeframe, mt5.TIMEFRAME_H1)
        except ImportError:
            # Fallback to numeric values
            mapping = {
                '1m': 1, '5m': 5, '15m': 15, '30m': 30,
                '1h': 16385, '4h': 16388, '1d': 16408
            }
            return mapping.get(timeframe, 16385)


# Global broker manager instance
broker_manager: Optional[BrokerManager] = None


def get_broker_manager() -> BrokerManager:
    """Get or create global broker manager instance"""
    global broker_manager
    if broker_manager is None:
        broker_manager = BrokerManager()
    return broker_manager
