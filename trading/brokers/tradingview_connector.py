"""
TradingView Webhook Connector
Receives signals from TradingView Pine Script via webhooks
"""

import os
import json
import time
import hmac
import hashlib
import uuid
import logging
from typing import Dict, Optional, Callable
from dataclasses import dataclass
from datetime import datetime
from collections import deque
from threading import Lock

try:
    from flask import Flask, request, jsonify
    FLASK_AVAILABLE = True
except ImportError:
    FLASK_AVAILABLE = False

logger = logging.getLogger(__name__)


@dataclass
class TradingViewSignal:
    """Structured TradingView signal"""
    symbol: str
    timeframe: str
    price: float
    signal: str  # BUY, SELL, NONE
    rsi: float
    ofi: float
    microprice: float
    in_killzone: bool
    timestamp: float
    raw_data: Dict
    
    @classmethod
    def from_webhook(cls, data: Dict) -> 'TradingViewSignal':
        """Parse webhook data into structured signal"""
        return cls(
            symbol=data.get('symbol', 'UNKNOWN'),
            timeframe=data.get('timeframe', '1h'),
            price=float(data.get('price', 0)),
            signal=data.get('signal', 'NONE'),
            rsi=float(data.get('rsi', 50)),
            ofi=float(data.get('ofi', 0)),
            microprice=float(data.get('microprice', 0)),
            in_killzone=data.get('in_killzone', False),
            timestamp=float(data.get('timestamp', time.time())),
            raw_data=data
        )
    
    def is_valid(self) -> bool:
        """Check if signal is valid"""
        if self.signal not in ['BUY', 'SELL']:
            return False
        if self.price <= 0:
            return False
        if time.time() - self.timestamp > 300:  # 5 min staleness
            return False
        return True
    
    def __str__(self) -> str:
        return f"TV[{self.symbol}] {self.signal} @ {self.price:.5f} (RSI:{self.rsi:.1f})"


class TradingViewConnector:
    """
    TradingView Webhook Connector
    
    Receives and validates TradingView signals
    Implements rate limiting and HMAC authentication
    """
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        webhook_port: int = 8080,
        rate_limit: float = 5.0,  # seconds between signals
        max_queue_size: int = 100,
        allow_unsigned_webhooks: bool = False
    ):
        self.api_key = api_key or os.getenv('TV_API_KEY', '')
        self.allow_unsigned_webhooks = allow_unsigned_webhooks
        self.webhook_port = webhook_port
        self.rate_limit = rate_limit
        self.signal_queue: deque = deque(maxlen=max_queue_size)
        self.last_signal_time: Dict[str, float] = {}
        self.lock = Lock()
        self.handlers: list[Callable] = []
        self.app: Optional['Flask'] = None
        self.running = False
        
        # Statistics
        self.stats = {
            'signals_received': 0,
            'signals_valid': 0,
            'signals_dropped': 0,
            'rate_limited': 0,
            'auth_failed': 0,
            'last_signal': None
        }
        
        self._setup_flask()
    
    def _setup_flask(self):
        """Setup Flask app if available"""
        if not FLASK_AVAILABLE:
            logger.warning("Flask not available, webhook server disabled")
            return
            
        self.app = Flask(__name__)
        
        @self.app.route('/webhook', methods=['POST'])
        def webhook():
            return self._handle_webhook()
        
        @self.app.route('/health', methods=['GET'])
        def health():
            return jsonify({
                'status': 'ok',
                'queue_size': len(self.signal_queue),
                'stats': self.stats
            })
        
        @self.app.route('/stats', methods=['GET'])
        def get_stats():
            return jsonify(self.stats)
    
    def _verify_signature(self, data: str, signature: Optional[str]) -> bool:
        """Verify HMAC signature"""
        # #region agent log
        try:
            with open("logs/debug-3c812d.log", "a", encoding="utf-8") as _dbg:
                _dbg.write(json.dumps({
                    "sessionId": "3c812d",
                    "runId": "pre-fix",
                    "hypothesisId": "H1",
                    "id": f"log_{uuid.uuid4().hex}",
                    "location": "trading/brokers/tradingview_connector.py:_verify_signature",
                    "message": "verify_signature_entry",
                    "data": {
                        "has_api_key": bool(self.api_key),
                        "has_signature": bool(signature)
                    },
                    "timestamp": int(time.time() * 1000)
                }) + "\n")
        except Exception:
            pass
        # #endregion
        if not self.api_key:
            # #region agent log
            try:
                with open("logs/debug-3c812d.log", "a", encoding="utf-8") as _dbg:
                    _dbg.write(json.dumps({
                        "sessionId": "3c812d",
                        "runId": "pre-fix",
                        "hypothesisId": "H1",
                        "id": f"log_{uuid.uuid4().hex}",
                        "location": "trading/brokers/tradingview_connector.py:_verify_signature",
                        "message": "missing_api_key_branch",
                        "data": {"allow_unsigned_webhooks": self.allow_unsigned_webhooks},
                        "timestamp": int(time.time() * 1000)
                    }) + "\n")
            except Exception:
                pass
            # #endregion
            return self.allow_unsigned_webhooks
        if not signature:
            return False
        
        expected = hmac.new(
            self.api_key.encode(),
            data.encode(),
            hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected, signature)
    
    def _handle_webhook(self):
        """Handle incoming webhook from TradingView"""
        try:
            # Get request data
            if request.is_json:
                data = request.get_json()
            else:
                data = json.loads(request.data.decode('utf-8'))
            
            self.stats['signals_received'] += 1
            
            # Verify signature
            signature = request.headers.get('X-TV-Signature')
            if not self._verify_signature(json.dumps(data, sort_keys=True), signature):
                self.stats['auth_failed'] += 1
                logger.warning("Webhook authentication failed")
                return jsonify({'error': 'Invalid signature'}), 401
            
            # Parse signal
            signal = TradingViewSignal.from_webhook(data)
            
            # Rate limiting
            symbol = signal.symbol
            now = time.time()
            last_time = self.last_signal_time.get(symbol, 0)
            if now - last_time < self.rate_limit:
                self.stats['rate_limited'] += 1
                logger.info(f"Rate limited: {symbol}")
                return jsonify({'status': 'rate_limited'}), 429
            
            # Validate signal
            if not signal.is_valid():
                self.stats['signals_dropped'] += 1
                logger.warning(f"Invalid signal: {signal}")
                return jsonify({'error': 'Invalid signal'}), 400
            
            # Add to queue
            with self.lock:
                self.signal_queue.append(signal)
                self.last_signal_time[symbol] = now
            
            self.stats['signals_valid'] += 1
            self.stats['last_signal'] = str(signal)
            
            # Notify handlers
            for handler in self.handlers:
                try:
                    handler(signal)
                except Exception as e:
                    logger.error(f"Handler error: {e}")
            
            logger.info(f"Signal accepted: {signal}")
            return jsonify({'status': 'ok', 'signal': signal.signal})
            
        except Exception as e:
            logger.error(f"Webhook error: {e}")
            return jsonify({'error': str(e)}), 500
    
    def register_handler(self, handler: Callable[[TradingViewSignal], None]):
        """Register a signal handler callback"""
        self.handlers.append(handler)
    
    def get_next_signal(self, timeout: Optional[float] = None) -> Optional[TradingViewSignal]:
        """Get next signal from queue (blocking)"""
        start = time.time()
        while timeout is None or time.time() - start < timeout:
            with self.lock:
                if self.signal_queue:
                    return self.signal_queue.popleft()
            time.sleep(0.1)
        return None
    
    def peek_signals(self, count: int = 10) -> list:
        """Peek at pending signals without removing"""
        with self.lock:
            return list(self.signal_queue)[:count]
    
    def start_server(self, blocking: bool = False):
        """Start webhook server"""
        if not self.app:
            logger.error("Flask not available, cannot start server")
            return False
        
        self.running = True
        logger.info(f"Starting TradingView webhook server on port {self.webhook_port}")
        
        if blocking:
            self.app.run(host='0.0.0.0', port=self.webhook_port, debug=False)
        else:
            import threading
            self.server_thread = threading.Thread(
                target=self.app.run,
                kwargs={'host': '0.0.0.0', 'port': self.webhook_port, 'debug': False},
                daemon=True
            )
            self.server_thread.start()
        
        return True
    
    def stop_server(self):
        """Stop webhook server"""
        self.running = False
        logger.info("TradingView webhook server stopped")


# Global connector instance
tv_connector: Optional[TradingViewConnector] = None


def get_tradingview_connector(
    api_key: Optional[str] = None,
    webhook_port: int = 8080
) -> TradingViewConnector:
    """Get or create global TradingView connector"""
    global tv_connector
    if tv_connector is None:
        tv_connector = TradingViewConnector(api_key, webhook_port)
    return tv_connector


# Example usage
if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    
    # Create connector
    connector = get_tradingview_connector(webhook_port=8080)
    
    # Register handler
    def on_signal(signal: TradingViewSignal):
        print(f"Received: {signal}")
    
    connector.register_handler(on_signal)
    
    # Start server
    connector.start_server(blocking=True)
