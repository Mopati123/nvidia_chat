"""
deriv_broker.py — Deriv.com API integration

Direct API trading with Deriv (formerly Binary.com)
Supports forex, crypto, synthetic indices, volatility indices
"""

import asyncio
import json
import logging
import os
import websocket
import threading
from typing import Any, Dict, Optional, List, Callable
from dataclasses import dataclass
from datetime import datetime
import time

from core.authority.token_validator import validate_token
from tachyonic_chain.audit_log import append_execution_evidence

logger = logging.getLogger(__name__)


@dataclass
class DerivOrder:
    """Deriv order structure"""
    symbol: str  # e.g., "frxEURUSD", "R_10", "cryBTCUSD"
    contract_type: str  # CALL (buy/up) or PUT (sell/down)
    amount: float  # Stake amount
    duration: int  # Duration value
    duration_unit: str  # s (seconds), m (minutes), h (hours), d (days)
    basis: str = "stake"  # stake or payout


class DerivBroker:
    """
    Deriv.com WebSocket API integration
    
    Free API access at https://deriv.com/
    Get API token from: https://app.deriv.com/account/api-token
    """
    
    WEBSOCKET_URL = "wss://ws.binaryws.com/websockets/v3?app_id=1089"
    
    def __init__(self, api_token: Optional[str] = None):
        self.api_token = api_token or os.getenv("DERIV_API_TOKEN")
        self.ws = None
        self.connected = False
        self.authorized = False
        self.req_id = 0
        self.callbacks: Dict[str, Callable] = {}
        self.pending_responses: Dict[str, Dict] = {}
        
        # Market data cache
        self.price_cache: Dict[str, Dict] = {}
        
    def connect(self) -> bool:
        """Connect to Deriv WebSocket API"""
        try:
            self.ws = websocket.create_connection(self.WEBSOCKET_URL)
            self.connected = True
            
            # Start message handling thread
            self.msg_thread = threading.Thread(target=self._message_loop, daemon=True)
            self.msg_thread.start()
            
            logger.info("Deriv WebSocket connected")
            
            # Authorize if token provided
            if self.api_token:
                return self.authorize(self.api_token)
            
            return True
            
        except Exception as e:
            logger.error(f"Deriv connection failed: {e}")
            return False
    
    def disconnect(self):
        """Close WebSocket connection"""
        self.connected = False
        if self.ws:
            self.ws.close()
        logger.info("Deriv disconnected")
    
    def _message_loop(self):
        """Background thread for WebSocket messages"""
        while self.connected:
            try:
                if self.ws:
                    msg = self.ws.recv()
                    self._handle_message(json.loads(msg))
            except Exception as e:
                if self.connected:
                    logger.error(f"Message loop error: {e}")
                time.sleep(1)
    
    def _handle_message(self, msg: Dict):
        """Process incoming WebSocket messages"""
        # Handle responses
        if 'req_id' in msg:
            req_id = msg['req_id']
            self.pending_responses[req_id] = msg
        
        # Handle price ticks
        if 'tick' in msg:
            tick = msg['tick']
            self.price_cache[tick['symbol']] = {
                'price': tick['quote'],
                'epoch': tick['epoch'],
                'id': tick['id']
            }
        
        # Handle errors
        if 'error' in msg:
            logger.error(f"Deriv API error: {msg['error']}")
    
    def _send_request(self, request: Dict) -> Optional[Dict]:
        """Send request and wait for response"""
        if not self.connected or not self.ws:
            return None
        
        self.req_id += 1
        request['req_id'] = self.req_id
        
        # Clear previous response
        self.pending_responses.pop(self.req_id, None)
        
        # Send
        self.ws.send(json.dumps(request))
        
        # Wait for response (max 10 seconds)
        for _ in range(100):
            if self.req_id in self.pending_responses:
                return self.pending_responses.pop(self.req_id)
            time.sleep(0.1)
        
        return None
    
    def authorize(self, api_token: str) -> bool:
        """Authorize with API token"""
        response = self._send_request({
            "authorize": api_token
        })
        
        if response and 'authorize' in response:
            self.authorized = True
            self.api_token = api_token
            account = response['authorize']
            logger.info(f"Deriv authorized: {account.get('email')} "
                       f"({account.get('currency')} {account.get('balance')})")
            return True
        
        logger.error(f"Deriv authorization failed: {response}")
        return False
    
    def get_account_info(self) -> Optional[Dict]:
        """Get account information"""
        if not self.authorized:
            return None
        
        response = self._send_request({
            "balance": 1
        })
        
        if response and 'balance' in response:
            bal = response['balance']
            return {
                'balance': bal.get('balance'),
                'currency': bal.get('currency'),
                'loginid': bal.get('loginid'),
                'demo': 'VRTC' in bal.get('loginid', '') or bal.get('loginid', '').startswith('VRTC')
            }
        return None
    
    @staticmethod
    def test_connection(api_token: str) -> tuple[bool, str, Optional[Dict]]:
        """
        Test Deriv connection and authorization without keeping connection open.
        
        Returns:
            (success: bool, message: str, account_info: Optional[Dict])
        """
        broker = DerivBroker(api_token)
        try:
            if not broker.connect():
                return False, "Failed to connect to Deriv WebSocket", None
            
            if not broker.authorized:
                broker.disconnect()
                return False, "Connection succeeded but authorization failed (invalid token?)", None
            
            # Get account info
            info = broker.get_account_info()
            broker.disconnect()
            
            if info:
                return True, f"✅ Connected! Account: {info.get('loginid')}, Balance: {info.get('balance')} {info.get('currency')}", info
            else:
                return True, "✅ Connected but failed to get account details", None
                
        except Exception as e:
            return False, f"❌ Error: {str(e)}", None

    def get_ohlcv(self, symbol: str, granularity: int = 3600, 
                  count: int = 100) -> List[Dict]:
        """
        Get historical OHLCV data
        
        Granularity: 60 (1m), 300 (5m), 900 (15m), 1800 (30m), 
                     3600 (1h), 14400 (4h), 86400 (1d)
        """
        if not self.connected:
            return []
        
        response = self._send_request({
            "ticks_history": symbol,
            "adjust_start_time": 1,
            "count": count,
            "end": "latest",
            "granularity": granularity,
            "style": "candles"
        })
        
        if not response or 'candles' not in response:
            return []
        
        ohlcv = []
        for candle in response['candles']:
            ohlcv.append({
                'timestamp': datetime.fromtimestamp(candle['epoch']).isoformat(),
                'open': candle['open'],
                'high': candle['high'],
                'low': candle['low'],
                'close': candle['close'],
                'volume': 0  # Deriv doesn't provide volume in candles
            })
        
        return ohlcv
    
    def subscribe_ticks(self, symbol: str):
        """Subscribe to real-time ticks"""
        self._send_request({
            "ticks": symbol,
            "subscribe": 1
        })

    def get_latest_tick(self) -> Optional[Dict]:
        """Return the most recently received tick from any subscription."""
        if not self.price_cache:
            return None
        symbol = next(iter(self.price_cache))
        entry = self.price_cache[symbol]
        return {"symbol": symbol, "price": entry["price"], "epoch": entry.get("epoch")}

    def get_current_price(self, symbol: str) -> Optional[float]:
        """Get current price (requires subscription first)"""
        if symbol in self.price_cache:
            return self.price_cache[symbol]['price']
        
        # Fetch single tick
        response = self._send_request({
            "ticks": symbol
        })
        
        if response and 'tick' in response:
            return response['tick']['quote']
        
        return None
    
    def place_contract(self, order: DerivOrder, *, token: Optional[Any] = None) -> Optional[Dict]:
        """
        Place a contract (trade)
        
        Note: Deriv uses 'contracts' not traditional orders
        """
        validation = validate_token(token, operation="live_execution")
        if not validation.valid:
            logger.warning("Deriv contract blocked by token validator: %s", validation.reason)
            append_execution_evidence(
                event_type="broker_refusal",
                execution_id=f"deriv_refused_{order.symbol}_{int(time.time())}",
                operation="live_execution",
                symbol=order.symbol,
                outcome="refused",
                token_status=validation.reason,
                payload={
                    "broker": "deriv",
                    "contract_type": order.contract_type,
                    "amount": order.amount,
                },
            )
            return None

        if not self.authorized:
            logger.error("Not authorized")
            return None
        
        proposal = {
            "proposal": 1,
            "amount": order.amount,
            "basis": order.basis,
            "contract_type": order.contract_type,  # CALL or PUT
            "currency": "USD",
            "duration": order.duration,
            "duration_unit": order.duration_unit,
            "symbol": order.symbol
        }
        
        # Get proposal — retry once with 50% stake if first attempt fails
        response = self._send_request(proposal)
        if not response or 'proposal' not in response:
            reduced_amount = round(order.amount * 0.5, 2)
            if reduced_amount >= 1.0:
                logger.warning(
                    "Proposal failed for amount=%.2f — retrying with %.2f",
                    order.amount, reduced_amount
                )
                proposal['amount'] = reduced_amount
                order.amount = reduced_amount
                response = self._send_request(proposal)
            if not response or 'proposal' not in response:
                logger.error(f"Proposal failed after size reduction: {response}")
                append_execution_evidence(
                    event_type="broker_execution",
                    execution_id=f"deriv_failed_{order.symbol}_{int(time.time())}",
                    operation="live_execution",
                    symbol=order.symbol,
                    outcome="failed",
                    token_status="authorized",
                    payload={
                        "broker": "deriv",
                        "reason": "proposal_failed",
                        "contract_type": order.contract_type,
                        "amount": order.amount,
                    },
                )
                return None
        
        # Buy the contract
        proposal_id = response['proposal']['id']
        
        buy_response = self._send_request({
            "buy": proposal_id,
            "price": response['proposal']['ask_price']
        })
        
        if buy_response and 'buy' in buy_response:
            contract = buy_response['buy']
            logger.info(f"Contract bought: {order.symbol} {order.contract_type} "
                       f"${order.amount} for {order.duration}{order.duration_unit}")

            execution_result = {
                'contract_id': contract['contract_id'],
                'longcode': contract['longcode'],
                'transaction_id': contract['transaction_id'],
                'buy_price': contract['buy_price']
            }
            append_execution_evidence(
                event_type="broker_execution",
                execution_id=f"deriv_{execution_result['contract_id']}",
                operation="live_execution",
                symbol=order.symbol,
                outcome="success",
                token_status="authorized",
                payload={"broker": "deriv", **execution_result},
            )
            return execution_result
        
        logger.error(f"Buy failed: {buy_response}")
        append_execution_evidence(
            event_type="broker_execution",
            execution_id=f"deriv_failed_{order.symbol}_{int(time.time())}",
            operation="live_execution",
            symbol=order.symbol,
            outcome="failed",
            token_status="authorized",
            payload={
                "broker": "deriv",
                "reason": "buy_failed",
                "contract_type": order.contract_type,
                "amount": order.amount,
            },
        )
        return None
    
    def get_active_contracts(self) -> List[Dict]:
        """Get list of open positions/contracts"""
        if not self.authorized:
            return []
        
        response = self._send_request({
            "portfolio": 1
        })
        
        if response and 'portfolio' in response:
            return response['portfolio'].get('contracts', [])
        
        return []
    
    def sell_contract(self, contract_id: int, price: float, *, token: Optional[Any] = None) -> Optional[Dict]:
        """Sell/close a contract early"""
        validation = validate_token(token, operation="live_execution")
        if not validation.valid:
            logger.warning("Deriv sell blocked by token validator: %s", validation.reason)
            append_execution_evidence(
                event_type="broker_refusal",
                execution_id=f"deriv_sell_refused_{contract_id}_{int(time.time())}",
                operation="live_execution",
                outcome="refused",
                token_status=validation.reason,
                payload={"broker": "deriv", "contract_id": contract_id},
            )
            return None

        if not self.authorized:
            return None
        
        response = self._send_request({
            "sell": contract_id,
            "price": price
        })
        
        if response and 'sell' in response:
            append_execution_evidence(
                event_type="broker_execution",
                execution_id=f"deriv_sell_{contract_id}_{int(time.time())}",
                operation="live_execution",
                outcome="success",
                token_status="authorized",
                payload={"broker": "deriv", "contract_id": contract_id, "price": price},
            )
            return response['sell']
        
        return None
    
    def get_payout_currencies(self) -> List[str]:
        """Get list of supported currencies"""
        response = self._send_request({
            "payout_currencies": 1
        })
        
        if response and 'payout_currencies' in response:
            return response['payout_currencies']
        
        return []
    
    def get_trading_times(self, symbol: str) -> Optional[Dict]:
        """Get trading times for symbol"""
        response = self._send_request({
            "trading_times": symbol
        })
        
        if response and 'trading_times' in response:
            return response['trading_times']
        
        return None
    
    def get_available_symbols(self) -> List[str]:
        """Get list of active symbols from Deriv API"""
        if not self.connected:
            return []
        
        # Fetch active symbols
        response = self._send_request({
            "active_symbols": "brief",
            "product_type": "basic"
        })
        
        if not response or 'active_symbols' not in response:
            return []
        
        symbols = []
        for sym in response['active_symbols']:
            symbol = sym.get('symbol')
            if symbol:
                symbols.append(symbol)
        
        return sorted(symbols)
    
    def get_symbol_info(self, symbol: str) -> Optional[Dict]:
        """Get detailed symbol information"""
        if not self.connected:
            return None
        
        response = self._send_request({
            "active_symbols": "full",
            "product_type": "basic"
        })
        
        if not response or 'active_symbols' not in response:
            return None
        
        for sym in response['active_symbols']:
            if sym.get('symbol') == symbol:
                return {
                    'symbol': sym.get('symbol'),
                    'display_name': sym.get('display_name'),
                    'market': sym.get('market'),
                    'pip_size': sym.get('pip_size'),
                    'min_contract_duration': sym.get('min_contract_duration'),
                    'max_contract_duration': sym.get('max_contract_duration'),
                    'sentiment': sym.get('sentiment'),
                    'exchange_is_open': sym.get('exchange_is_open', 0) == 1
                }
        
        return None


# Singleton
deriv_broker = DerivBroker()
