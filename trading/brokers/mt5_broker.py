"""
mt5_broker.py — MetaTrader 5 integration

Real trading via MT5 terminal
Supports demo and live accounts
"""

import os
import MetaTrader5 as mt5
import logging
from typing import Dict, Optional, List, Tuple
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class MT5Order:
    """MT5 order structure"""
    symbol: str
    order_type: str  # buy/sell
    volume: float
    price: Optional[float] = None
    sl: Optional[float] = None  # Stop loss
    tp: Optional[float] = None  # Take profit
    deviation: int = 20  # Slippage in points
    magic: int = 0  # Expert advisor ID
    comment: str = "ApexQuantumICT"


@dataclass  
class MT5Position:
    """MT5 position info"""
    ticket: int
    symbol: str
    type: int  # 0=buy, 1=sell
    volume: float
    open_price: float
    current_price: float
    profit: float
    swap: float
    open_time: datetime


def _filling_mode(symbol_info) -> int:
    """Return the first filling mode supported by the symbol (FOK > IOC > RETURN)."""
    fm = getattr(symbol_info, "filling_mode", 0)
    if fm & 1:
        return mt5.ORDER_FILLING_FOK
    if fm & 2:
        return mt5.ORDER_FILLING_IOC
    return mt5.ORDER_FILLING_RETURN


class MT5Broker:
    """
    MetaTrader 5 broker integration
    
    Requires MT5 terminal running locally or via Wine on Linux/Mac
    """
    
    def __init__(self, account: Optional[int] = None,
                 password: Optional[str] = None,
                 server: Optional[str] = None):
        _env_acct = os.getenv("MT5_ACCOUNT_ID", "")
        self.account  = account  or (int(_env_acct) if _env_acct.isdigit() else None)
        self.password = password or os.getenv("MT5_PASSWORD")
        self.server   = server   or os.getenv("MT5_SERVER")
        self.connected = False
        
    def connect(self, max_retries: int = 5, retry_delay: float = 3.0) -> bool:
        """Initialize MT5 connection with retry logic"""
        import time
        
        for attempt in range(max_retries):
            try:
                # Initialize MT5
                if not mt5.initialize():
                    err_code, err_desc = mt5.last_error()
                    if err_code == -10005:  # IPC timeout - terminal still initializing
                        logger.warning(f"MT5 initializing... (attempt {attempt + 1}/{max_retries})")
                        time.sleep(retry_delay)
                        continue
                    else:
                        logger.error(f"MT5 initialize failed: {err_desc} ({err_code})")
                        return False
                
                # Login if credentials provided
                if self.account and self.password and self.server:
                    authorized = mt5.login(
                        self.account,
                        password=self.password,
                        server=self.server
                    )
                    if not authorized:
                        err_code, err_desc = mt5.last_error()
                        if err_code == -10005 and attempt < max_retries - 1:
                            logger.warning(f"MT5 login timeout, retrying... ({attempt + 1}/{max_retries})")
                            mt5.shutdown()
                            time.sleep(retry_delay)
                            continue
                        logger.error(f"MT5 login failed: {err_desc} ({err_code})")
                        return False
                
                self.connected = True
                account_info = mt5.account_info()
                if account_info:
                    logger.info(f"MT5 connected: {account_info.login} @ {account_info.server}")
                    logger.info(f"Balance: {account_info.balance}, Equity: {account_info.equity}")
                return True
                
            except Exception as e:
                logger.error(f"MT5 connection error (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                    continue
                return False
        
        return False
    
    def disconnect(self):
        """Shutdown MT5 connection"""
        mt5.shutdown()
        self.connected = False
        logger.info("MT5 disconnected")
    
    @staticmethod
    def test_connection(account: int, password: str, server: str, max_retries: int = 5) -> tuple[bool, str, Optional[Dict]]:
        """
        Test MT5 connection and authentication without keeping connection open.
        Includes retry logic for MT5 initialization delays.
        
        Args:
            account: MT5 account number
            password: MT5 password
            server: MT5 server name
            max_retries: Number of connection attempts (default 5)
        
        Returns:
            (success: bool, message: str, account_info: Optional[Dict])
        """
        import time
        
        broker = MT5Broker(account, password, server)
        
        for attempt in range(max_retries):
            try:
                # Try to connect with single retry (connect has its own retries)
                if broker.connect(max_retries=1, retry_delay=2.0):
                    # Get account info
                    info = broker.get_account_info()
                    broker.disconnect()
                    
                    if info:
                        mode_emoji = "🧪" if info.get('trade_mode') == 'demo' else "💰"
                        return True, f"✅ Connected! {mode_emoji} Account {info.get('login')} @ {info.get('server')}, Balance: {info.get('balance')} {info.get('currency')}", info
                    else:
                        return True, "✅ Connected but failed to get account details", None
                
                # Connection failed - check why
                err_code, err_desc = mt5.last_error()
                
                if err_code == -10005:  # IPC timeout
                    if attempt < max_retries - 1:
                        print(f"   ⏳ MT5 initializing... waiting 3s (attempt {attempt + 1}/{max_retries})")
                        time.sleep(3.0)
                        continue
                    else:
                        return False, f"❌ MT5 IPC timeout - terminal may be stuck initializing. Try restarting MT5.", None
                else:
                    return False, f"❌ MT5 error: {err_desc} (code {err_code})", None
                    
            except Exception as e:
                if attempt < max_retries - 1:
                    print(f"   ⏳ Retry {attempt + 1}/{max_retries} after error: {e}")
                    time.sleep(3.0)
                    continue
                return False, f"❌ Error: {str(e)}", None
        
        return False, "❌ Failed to connect after all retry attempts", None

    def get_account_info(self) -> Optional[Dict]:
        """Get account information"""
        if not self.connected:
            return None
            
        info = mt5.account_info()
        if info is None:
            return None
            
        return {
            'login': info.login,
            'server': info.server,
            'balance': info.balance,
            'equity': info.equity,
            'margin': info.margin,
            'margin_free': info.margin_free,
            'margin_level': info.margin_level,
            'currency': info.currency,
            'trade_allowed': info.trade_allowed,
            'trade_mode': 'demo' if info.trade_mode == 0 else 'real'
        }
    
    def get_ohlcv(self, symbol: str, timeframe: int = mt5.TIMEFRAME_H1, 
                  count: int = 100) -> List[Dict]:
        """
        Get OHLCV from MT5
        
        Timeframes: M1=1, M5=5, M15=15, M30=30, H1=16385, H4=16388, D1=16408
        """
        if not self.connected:
            return []
        
        try:
            rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, count)
            if rates is None:
                return []
            
            # Convert numpy array to list of dicts
            ohlcv = []
            for rate in rates:
                # rate is a tuple: (time, open, high, low, close, tick_volume, spread, real_volume)
                ohlcv.append({
                    'timestamp': datetime.fromtimestamp(rate[0]).isoformat(),
                    'open': round(float(rate[1]), 5),
                    'high': round(float(rate[2]), 5),
                    'low': round(float(rate[3]), 5),
                    'close': round(float(rate[4]), 5),
                    'volume': int(rate[5]),
                    'spread': int(rate[6])
                })
            
            return ohlcv
            
        except Exception as e:
            logger.error(f"MT5 OHLCV fetch failed: {e}")
            return []
    
    def place_order(self, order: MT5Order) -> Optional[Dict]:
        """
        Place market order via MT5
        
        Returns order result or None if failed
        """
        if not self.connected:
            logger.error("MT5 not connected")
            return None
        
        try:
            # Resolve broker-specific symbol suffix (e.g. EURUSD_r, EURUSDm, EURUSD.)
            resolved = order.symbol
            if mt5.symbol_info(resolved) is None:
                for suffix in ('_r', 'm', '.', '_micro', '_pro', '_ecn'):
                    candidate = order.symbol + suffix
                    if mt5.symbol_info(candidate) is not None:
                        logger.info("MT5 symbol resolved: %s → %s", order.symbol, candidate)
                        resolved = candidate
                        break
            order = MT5Order(
                symbol=resolved,
                order_type=order.order_type,
                volume=order.volume,
                price=order.price,
                sl=order.sl,
                tp=order.tp,
                deviation=order.deviation,
                magic=order.magic,
                comment=order.comment,
            )

            # Get symbol info
            symbol_info = mt5.symbol_info(order.symbol)
            if symbol_info is None:
                logger.error(f"Symbol {order.symbol} not found")
                return None
            
            if not symbol_info.visible:
                # Add to MarketWatch if not visible
                if not mt5.symbol_select(order.symbol, True):
                    logger.error(f"Failed to select {order.symbol}")
                    return None
            
            # Get current price
            tick = mt5.symbol_info_tick(order.symbol)
            if tick is None:
                logger.error(f"No tick data for {order.symbol}")
                return None
            
            # Determine order type and price
            if order.order_type.lower() == 'buy':
                order_type = mt5.ORDER_TYPE_BUY
                price = tick.ask
            else:  # sell
                order_type = mt5.ORDER_TYPE_SELL
                price = tick.bid
            
            # Build order request
            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": order.symbol,
                "volume": order.volume,
                "type": order_type,
                "price": price,
                "deviation": order.deviation,
                "magic": order.magic,
                "comment": order.comment,
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": _filling_mode(symbol_info),
            }

            # Add SL/TP if provided
            if order.sl:
                request["sl"] = order.sl
            if order.tp:
                request["tp"] = order.tp
            
            # Send order — retry once on transient failures (requote, price change, timeout)
            _TRANSIENT = {
                mt5.TRADE_RETCODE_REQUOTE,
                mt5.TRADE_RETCODE_PRICE_CHANGED,
                mt5.TRADE_RETCODE_TIMEOUT,
            }
            result = mt5.order_send(request)
            if result.retcode in _TRANSIENT:
                import time as _time
                logger.warning(
                    "MT5 transient retcode %d (%s) — single retry after 500ms",
                    result.retcode, order.symbol
                )
                _time.sleep(0.5)
                result = mt5.order_send(request)

            if result.retcode != mt5.TRADE_RETCODE_DONE:
                if result.retcode == 10027:
                    logger.error(
                        "MT5 AutoTrading DISABLED (retcode=10027) — "
                        "enable it in MetaTrader: Tools → Options → Expert Advisors "
                        "→ 'Allow automated trading', or click the AutoTrading toolbar button"
                    )
                else:
                    logger.error(
                        "MT5 order failed: retcode=%d symbol=%s volume=%.2f",
                        result.retcode, order.symbol, order.volume
                    )
                return None
            
            logger.info(f"Order executed: {order.symbol} {order.order_type} "
                       f"{order.volume} lots @ {result.price}")
            
            return {
                'ticket': result.order,
                'symbol': order.symbol,
                'volume': order.volume,
                'price': result.price,
                'bid': result.bid,
                'ask': result.ask,
                'comment': order.comment,
                'retcode': result.retcode
            }
            
        except Exception as e:
            logger.error(f"Order placement failed: {e}")
            return None
    
    def get_positions(self) -> List[MT5Position]:
        """Get all open positions"""
        if not self.connected:
            return []
        
        positions = mt5.positions_get()
        if positions is None:
            return []
        
        result = []
        for pos in positions:
            result.append(MT5Position(
                ticket=pos.ticket,
                symbol=pos.symbol,
                type=pos.type,
                volume=pos.volume,
                open_price=pos.price_open,
                current_price=pos.price_current,
                profit=pos.profit,
                swap=pos.swap,
                open_time=datetime.fromtimestamp(pos.time)
            ))
        
        return result
    
    def close_position(self, ticket: int) -> bool:
        """Close position by ticket number"""
        if not self.connected:
            return False
        
        try:
            position = mt5.positions_get(ticket=ticket)
            if position is None or len(position) == 0:
                return False
            
            pos = position[0]
            
            # Create close order (opposite direction)
            close_type = mt5.ORDER_TYPE_SELL if pos.type == 0 else mt5.ORDER_TYPE_BUY
            
            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": pos.symbol,
                "volume": pos.volume,
                "type": close_type,
                "position": ticket,
                "price": mt5.symbol_info_tick(pos.symbol).bid if close_type == mt5.ORDER_TYPE_SELL else mt5.symbol_info_tick(pos.symbol).ask,
                "deviation": 20,
                "magic": 0,
                "comment": "ApexQuantumICT close",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": _filling_mode(mt5.symbol_info(pos.symbol)),
            }

            result = mt5.order_send(request)
            return result.retcode == mt5.TRADE_RETCODE_DONE
            
        except Exception as e:
            logger.error(f"Close position failed: {e}")
            return False
    
    def is_demo(self) -> bool:
        """Check if account is demo"""
        info = self.get_account_info()
        if info:
            return info.get('trade_mode') == 'demo'
        return False
    
    def get_available_symbols(self, group: str = "*") -> List[str]:
        """
        Get list of available symbols from MT5
        
        Args:
            group: Symbol group pattern (e.g., "*USD*", "*", "Forex*")
        """
        if not self.connected:
            return []
        
        try:
            symbols = mt5.symbols_get(group=group)
            if symbols is None:
                return []
            
            return sorted([sym.name for sym in symbols])
            
        except Exception as e:
            logger.error(f"Failed to get symbols: {e}")
            return []
    
    def get_current_price(self, symbol: str) -> Optional[float]:
        """Return current bid price for symbol (used by AsyncTickLoop producer)."""
        if not self.connected:
            return None
        try:
            tick = mt5.symbol_info_tick(symbol)
            return float(tick.bid) if tick else None
        except Exception:
            return None

    def get_symbol_info(self, symbol: str) -> Optional[Dict]:
        """Get detailed symbol information from MT5"""
        if not self.connected:
            return None
        
        try:
            info = mt5.symbol_info(symbol)
            if info is None:
                return None
            
            return {
                'name': info.name,
                'description': info.description,
                'path': info.path,
                'currency_base': info.currency_base,
                'currency_profit': info.currency_profit,
                'currency_margin': info.currency_margin,
                'digits': info.digits,
                'spread': info.spread,
                'tick_size': info.point,
                'contract_size': info.trade_contract_size,
                'min_lot': info.volume_min,
                'max_lot': info.volume_max,
                'lot_step': info.volume_step,
                'trade_allowed': info.trade_mode == 0,
                'visible': info.visible
            }
            
        except Exception as e:
            logger.error(f"Failed to get symbol info: {e}")
            return None


# Singleton
mt5_broker = MT5Broker()
