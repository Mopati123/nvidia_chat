"""
broker_logger.py — Comprehensive logging and audit trail for broker operations

Logs: Connections, data fetches, trades, errors
Formats: Human-readable + Structured JSON
Security: Credential masking, tamper-evident audit trail
"""

import os
import json
import hashlib
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, asdict
from enum import Enum

logger = logging.getLogger(__name__)


class BrokerOperation(Enum):
    CONNECT = "connect"
    DISCONNECT = "disconnect"
    FETCH_DATA = "fetch_data"
    PLACE_ORDER = "place_order"
    CLOSE_POSITION = "close_position"
    GET_POSITIONS = "get_positions"
    ERROR = "error"


@dataclass
class BrokerAuditRecord:
    """Single audit record for broker operation"""
    timestamp: str
    broker: str
    operation: str
    symbol: Optional[str]
    request_hash: str  # Hashed request for integrity
    response_hash: str  # Hashed response for integrity
    success: bool
    duration_ms: float
    metadata: Dict[str, Any]
    error_message: Optional[str] = None
    
    def to_dict(self) -> Dict:
        return asdict(self)
    
    def to_json(self) -> str:
        return json.dumps(self.to_dict(), default=str)


class BrokerLogger:
    """
    Comprehensive logging system for broker operations
    """
    
    def __init__(self, log_dir: Optional[str] = None):
        self.log_dir = Path(log_dir) if log_dir else Path("./logs/brokers")
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        self.audit_file = self.log_dir / f"audit_{datetime.now().strftime('%Y-%m')}.log"
        self.json_log_file = self.log_dir / f"broker_{datetime.now().strftime('%Y-%m-%d')}.jsonl"
        
        # Setup file loggers
        self._setup_loggers()
        
        # In-memory recent operations cache
        self.recent_operations: List[BrokerAuditRecord] = []
        self.max_cache_size = 1000
        
    def _setup_loggers(self):
        """Setup file-based loggers"""
        # Text log for humans
        self.text_logger = logging.getLogger('broker_text')
        self.text_logger.setLevel(logging.INFO)
        
        text_handler = logging.FileHandler(self.log_dir / f"broker_{datetime.now().strftime('%Y-%m-%d')}.log")
        text_handler.setFormatter(logging.Formatter(
            '%(asctime)s | %(levelname)-8s | %(message)s'
        ))
        self.text_logger.addHandler(text_handler)
        
        # JSON log for machines
        self.json_logger = logging.getLogger('broker_json')
        self.json_logger.setLevel(logging.INFO)
        
        json_handler = logging.FileHandler(self.json_log_file)
        json_handler.setFormatter(logging.Formatter('%(message)s'))
        self.json_logger.addHandler(json_handler)
    
    def _mask_sensitive(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Mask sensitive fields in logged data"""
        masked = {}
        sensitive_fields = ['token', 'password', 'api_key', 'secret', 'auth']
        
        for key, value in data.items():
            if any(s in key.lower() for s in sensitive_fields):
                masked[key] = '***MASKED***'
            elif isinstance(value, dict):
                masked[key] = self._mask_sensitive(value)
            else:
                masked[key] = value
        
        return masked
    
    def _hash_data(self, data: Any) -> str:
        """Create hash of data for integrity verification"""
        content = json.dumps(data, sort_keys=True, default=str).encode()
        return hashlib.sha256(content).hexdigest()[:16]
    
    def log_connection(self, broker: str, success: bool, duration_ms: float, 
                       error: Optional[str] = None, metadata: Optional[Dict] = None):
        """Log broker connection attempt"""
        operation = BrokerOperation.CONNECT if success else BrokerOperation.ERROR
        
        if success:
            self.text_logger.info(f"[{broker}] Connected ({duration_ms:.1f}ms)")
        else:
            self.text_logger.error(f"[{broker}] Connection failed: {error}")
        
        record = BrokerAuditRecord(
            timestamp=datetime.now().isoformat(),
            broker=broker,
            operation=operation.value,
            symbol=None,
            request_hash=self._hash_data({"action": "connect"}),
            response_hash=self._hash_data({"success": success}),
            success=success,
            duration_ms=duration_ms,
            metadata=metadata or {},
            error_message=error
        )
        
        self._write_record(record)
    
    def log_data_fetch(self, broker: str, symbol: str, success: bool,
                       duration_ms: float, count: int,
                       error: Optional[str] = None):
        """Log market data fetch operation"""
        if success:
            self.text_logger.info(
                f"[{broker}] Fetched {count} candles for {symbol} ({duration_ms:.1f}ms)"
            )
        else:
            self.text_logger.error(
                f"[{broker}] Data fetch failed for {symbol}: {error}"
            )
        
        record = BrokerAuditRecord(
            timestamp=datetime.now().isoformat(),
            broker=broker,
            operation=BrokerOperation.FETCH_DATA.value,
            symbol=symbol,
            request_hash=self._hash_data({"symbol": symbol}),
            response_hash=self._hash_data({"count": count}),
            success=success,
            duration_ms=duration_ms,
            metadata={"candle_count": count}
        )
        
        self._write_record(record)
    
    def log_trade(self, broker: str, symbol: str, operation: str,
                  success: bool, volume: float, price: float,
                  duration_ms: float, order_details: Dict,
                  error: Optional[str] = None):
        """Log trade execution"""
        # Mask sensitive data
        safe_details = self._mask_sensitive(order_details)
        
        if success:
            self.text_logger.info(
                f"[{broker}] {operation.upper()} {volume} {symbol} @ {price} "
                f"({duration_ms:.1f}ms)"
            )
        else:
            self.text_logger.error(
                f"[{broker}] {operation.upper()} failed for {symbol}: {error}"
            )
        
        record = BrokerAuditRecord(
            timestamp=datetime.now().isoformat(),
            broker=broker,
            operation=operation,
            symbol=symbol,
            request_hash=self._hash_data(safe_details),
            response_hash=self._hash_data({"success": success, "price": price}),
            success=success,
            duration_ms=duration_ms,
            metadata={
                "volume": volume,
                "price": price,
                "order_details": safe_details
            },
            error_message=error
        )
        
        self._write_record(record)
    
    def log_error(self, broker: str, operation: str, error: str,
                  symbol: Optional[str] = None, context: Optional[Dict] = None):
        """Log error with context"""
        safe_context = self._mask_sensitive(context or {})
        
        self.text_logger.error(
            f"[{broker}] Error in {operation}: {error}"
        )
        
        record = BrokerAuditRecord(
            timestamp=datetime.now().isoformat(),
            broker=broker,
            operation=BrokerOperation.ERROR.value,
            symbol=symbol,
            request_hash=self._hash_data(safe_context),
            response_hash="ERROR",
            success=False,
            duration_ms=0.0,
            metadata=safe_context,
            error_message=error
        )
        
        self._write_record(record)
    
    def _write_record(self, record: BrokerAuditRecord):
        """Write record to all log destinations"""
        # Add to cache
        self.recent_operations.append(record)
        if len(self.recent_operations) > self.max_cache_size:
            self.recent_operations.pop(0)
        
        # Write to JSON log
        self.json_logger.info(record.to_json())
        
        # Append to audit trail (tamper-evident)
        self._append_audit_trail(record)
    
    def _append_audit_trail(self, record: BrokerAuditRecord):
        """Append to tamper-evident audit log"""
        # Calculate chain hash (previous record's hash + current data)
        prev_hash = "0" * 16
        
        if self.audit_file.exists():
            try:
                with open(self.audit_file, 'r') as f:
                    lines = f.readlines()
                    if lines:
                        last_line = lines[-1]
                        # Extract hash from last line (format: HASH|JSON_DATA)
                        prev_hash = last_line.split('|')[0]
            except:
                pass
        
        # Create chain hash
        chain_input = f"{prev_hash}{record.to_json()}"
        chain_hash = hashlib.sha256(chain_input.encode()).hexdigest()[:16]
        
        # Write to audit file
        with open(self.audit_file, 'a') as f:
            f.write(f"{chain_hash}|{record.to_json()}\n")
    
    def get_recent_operations(self, broker: Optional[str] = None,
                              operation: Optional[str] = None,
                              limit: int = 100) -> List[BrokerAuditRecord]:
        """Get recent operations from cache"""
        filtered = self.recent_operations
        
        if broker:
            filtered = [r for r in filtered if r.broker == broker]
        
        if operation:
            filtered = [r for r in filtered if r.operation == operation]
        
        return filtered[-limit:]
    
    def get_stats(self, broker: Optional[str] = None,
                  hours: int = 24) -> Dict[str, Any]:
        """Get operation statistics"""
        cutoff = datetime.now() - __import__('datetime').timedelta(hours=hours)
        
        relevant = [
            r for r in self.recent_operations
            if datetime.fromisoformat(r.timestamp) > cutoff
            and (broker is None or r.broker == broker)
        ]
        
        if not relevant:
            return {"total": 0}
        
        total = len(relevant)
        successful = sum(1 for r in relevant if r.success)
        failed = total - successful
        
        by_operation = {}
        for r in relevant:
            by_operation[r.operation] = by_operation.get(r.operation, 0) + 1
        
        avg_duration = sum(r.duration_ms for r in relevant) / total
        
        return {
            "total": total,
            "successful": successful,
            "failed": failed,
            "success_rate": successful / total,
            "by_operation": by_operation,
            "avg_duration_ms": avg_duration,
            "period_hours": hours
        }
    
    def verify_audit_integrity(self) -> bool:
        """
        Verify tamper-evident audit trail integrity
        Returns True if intact, False if tampered
        """
        if not self.audit_file.exists():
            return True
        
        try:
            with open(self.audit_file, 'r') as f:
                lines = f.readlines()
            
            prev_hash = "0" * 16
            
            for i, line in enumerate(lines):
                parts = line.strip().split('|', 1)
                if len(parts) != 2:
                    logger.error(f"Audit line {i+1} corrupted: malformed")
                    return False
                
                stored_hash, json_data = parts
                
                # Verify chain
                chain_input = f"{prev_hash}{json_data}"
                computed_hash = hashlib.sha256(chain_input.encode()).hexdigest()[:16]
                
                if stored_hash != computed_hash:
                    logger.error(f"Audit line {i+1} tampered! Chain broken.")
                    return False
                
                prev_hash = stored_hash
            
            logger.info(f"Audit trail verified: {len(lines)} records intact")
            return True
            
        except Exception as e:
            logger.error(f"Audit verification failed: {e}")
            return False


# Global broker logger instance
broker_logger: Optional[BrokerLogger] = None


def get_broker_logger(log_dir: Optional[str] = None) -> BrokerLogger:
    """Get or create global broker logger"""
    global broker_logger
    if broker_logger is None:
        # Use environment variable if set
        if log_dir is None:
            log_dir = os.environ.get('BROKER_LOG_PATH', './logs/brokers')
        broker_logger = BrokerLogger(log_dir)
    return broker_logger
