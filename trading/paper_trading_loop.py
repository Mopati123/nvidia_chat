"""
Paper Trading Loop
Event-driven execution with TAEP governance
Full audit trail and latency measurement
"""

import os
import time
import logging
from typing import Dict, Optional, List, Callable, Any
from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import Thread, Event, Lock
from queue import Queue, Empty

from taep.core.state import TAEPState, ExecutionToken
from taep.scheduler import TAEPScheduler, get_scheduler
from taep.audit.evidence_writer import TAEPEvidence, EvidenceWriter

from trading.risk.risk_manager import get_risk_manager, ProductionRiskManager, RiskCheck
from trading.risk.position_sizer import get_position_sizer, SizingParams
from trading.risk.pnl_tracker import get_pnl_tracker, TradeRecord
from trading.brokers.demo_orchestrator import get_demo_orchestrator, DemoOrchestrator
from trading.brokers.tradingview_connector import TradingViewSignal, get_tradingview_connector
from trading.brokers.signal_router import get_signal_router, SignalRouter, RoutedOrder

logger = logging.getLogger(__name__)


@dataclass
class PaperTradeContext:
    """Context for a paper trade"""
    signal: TradingViewSignal
    routed_order: RoutedOrder
    entry_price: float
    size: float
    taep_state: Optional[TAEPState] = None
    taep_evidence: Optional[TAEPEvidence] = None
    execution_time_ms: float = 0.0
    status: str = "pending"  # pending, executed, rejected, closed
    entry_time: float = field(default_factory=time.time)
    exit_time: Optional[float] = None
    realized_pnl: Optional[float] = None


class PaperTradingLoop:
    """
    Production paper trading loop
    
    Features:
    - Event-driven from TradingView signals
    - TAEP governance at every step
    - Full audit trail
    - Latency measurement
    - Risk management integration
    - Position sizing
    - Multi-broker execution
    """
    
    def __init__(
        self,
        max_queue_size: int = 1000,
        signal_timeout: float = 5.0,
        enable_taep: bool = True
    ):
        self.max_queue_size = max_queue_size
        self.signal_timeout = signal_timeout
        self.enable_taep = enable_taep
        
        # Components
        self.risk_manager = get_risk_manager()
        self.position_sizer = get_position_sizer()
        self.pnl_tracker = get_pnl_tracker()
        self.demo_orchestrator = get_demo_orchestrator()
        self.signal_router = get_signal_router()
        self.tv_connector = get_tradingview_connector()
        
        # TAEP components
        self.taep_scheduler: Optional[TAEPScheduler] = None
        self.evidence_writer: Optional[EvidenceWriter] = None
        if enable_taep:
            try:
                self.taep_scheduler = get_scheduler()
                self.evidence_writer = EvidenceWriter()
            except Exception as e:
                logger.warning(f"TAEP not available: {e}")
                self.enable_taep = False
        
        # State
        self.running = False
        self.stop_event = Event()
        self.signal_queue: Queue = Queue(maxsize=max_queue_size)
        self.active_trades: Dict[str, PaperTradeContext] = {}
        self.trade_lock = Lock()
        
        # Statistics
        self.stats = {
            'signals_received': 0,
            'signals_routed': 0,
            'trades_executed': 0,
            'trades_rejected_risk': 0,
            'trades_rejected_taep': 0,
            'trades_closed': 0,
            'total_latency_ms': 0.0,
            'avg_latency_ms': 0.0
        }
        
        # Handlers
        self.pre_trade_handlers: List[Callable] = []
        self.post_trade_handlers: List[Callable] = []
        
        # Connect to signal router
        self._connect_to_signals()
    
    def _connect_to_signals(self):
        """Connect to TradingView signal router"""
        self.signal_router.register_post_route(self._on_signal_routed)
        logger.info("Paper trading loop connected to signal router")
    
    def _on_signal_routed(self, order: RoutedOrder):
        """Handle routed signal from TradingView"""
        try:
            self.signal_queue.put(order, block=False)
            self.stats['signals_routed'] += 1
            logger.info(f"Signal queued: {order.signal.symbol} -> {order.broker.value}")
        except:
            logger.warning("Signal queue full, dropping signal")
    
    def _create_taep_state(self, signal: TradingViewSignal, order: RoutedOrder) -> Optional[TAEPState]:
        """Create TAEP state for trade authorization"""
        if not self.enable_taep:
            return None
        
        try:
            # Convert signal to TAEP state
            q = [signal.price, time.time(), signal.rsi / 100.0]  # position vector
            p = [signal.ofi / 1000.0, 0.0, 0.0]  # momentum
            k = [0.1, 0.1, 0.1]  # chaotic key
            
            token = ExecutionToken(
                operation='PAPER_TRADE',
                budget=order.size * signal.price * 100000,  # Notional value
                expiry=time.time() + 60
            )
            
            state = TAEPState(
                q=q,
                p=p,
                k=k,
                policy={'symbol': signal.symbol, 'max_position': 1.0},
                entropy=abs(signal.ofi) / 1000.0,
                token=token
            )
            
            return state
            
        except Exception as e:
            logger.error(f"Failed to create TAEP state: {e}")
            return None
    
    def _authorize_with_taep(self, state: TAEPState) -> tuple:
        """Get TAEP authorization for trade"""
        if not self.enable_taep or not self.taep_scheduler:
            return True, None
        
        try:
            proposal = {'action': 'execute_paper_trade', 'size': 0.01}
            authorized = self.taep_scheduler.authorize(state, proposal)
            evidence = self.taep_scheduler.collapse(state, authorized, proposal)
            
            return authorized, evidence
            
        except Exception as e:
            logger.error(f"TAEP authorization failed: {e}")
            return False, None
    
    def _execute_trade(self, order: RoutedOrder) -> Optional[PaperTradeContext]:
        """
        Execute a paper trade with full governance
        
        Returns PaperTradeContext or None if rejected
        """
        signal = order.signal
        start_time = time.time()
        
        # 1. Create trade context
        context = PaperTradeContext(
            signal=signal,
            routed_order=order,
            entry_price=order.price,
            size=order.size,
            status="pending"
        )
        
        # 2. Pre-trade handlers
        for handler in self.pre_trade_handlers:
            try:
                result = handler(context)
                if result is False:
                    logger.info(f"Trade rejected by pre-handler: {signal.symbol}")
                    return None
            except Exception as e:
                logger.error(f"Pre-trade handler error: {e}")
        
        # 3. Risk check
        risk_check = self.risk_manager.check_all_limits(
            symbol=order.symbol,
            direction=order.direction,
            size=order.size,
            price=order.price
        )
        
        if not risk_check.passed:
            self.stats['trades_rejected_risk'] += 1
            logger.warning(f"Trade rejected by risk manager: {risk_check.message}")
            context.status = "rejected"
            return context
        
        # 4. Position sizing (refine size)
        account = self.demo_orchestrator.select_account(order.symbol)
        if account:
            sized = self.position_sizer.quick_size(
                account_balance=account.balance,
                entry_price=order.price,
                confidence=0.7,
                volatility=0.01
            )
            context.size = min(order.size, sized)
        
        # 5. TAEP authorization
        if self.enable_taep:
            context.taep_state = self._create_taep_state(signal, order)
            authorized, evidence = self._authorize_with_taep(context.taep_state)
            context.taep_evidence = evidence
            
            if not authorized:
                self.stats['trades_rejected_taep'] += 1
                logger.warning(f"Trade rejected by TAEP: {signal.symbol}")
                context.status = "rejected"
                return context
        
        # 6. Execute on broker (paper mode)
        try:
            broker = self.demo_orchestrator.get_broker_for_symbol(
                order.symbol,
                f"{order.broker.value}_demo"
            )
            
            if broker:
                # Record position in risk manager
                from trading.risk.risk_manager import Position
                position = Position(
                    symbol=order.symbol,
                    direction=order.direction,
                    size=context.size,
                    entry_price=context.entry_price,
                    current_price=context.entry_price,
                    broker=order.broker.value
                )
                
                self.risk_manager.add_position(position)
                
                context.status = "executed"
                self.stats['trades_executed'] += 1
                
                # Store as active trade
                trade_id = f"{order.symbol}_{int(time.time()*1000)}"
                with self.trade_lock:
                    self.active_trades[trade_id] = context
                
                logger.info(f"Paper trade executed: {order.symbol} {order.direction} {context.size} lots")
                
            else:
                logger.error(f"No broker for {order.symbol}")
                context.status = "rejected"
                
        except Exception as e:
            logger.error(f"Trade execution failed: {e}")
            context.status = "rejected"
        
        # 7. Calculate latency
        context.execution_time_ms = (time.time() - start_time) * 1000
        self.stats['total_latency_ms'] += context.execution_time_ms
        self.stats['avg_latency_ms'] = (
            self.stats['total_latency_ms'] / self.stats['trades_executed']
            if self.stats['trades_executed'] > 0 else 0
        )
        
        # 8. Post-trade handlers
        for handler in self.post_trade_handlers:
            try:
                handler(context)
            except Exception as e:
                logger.error(f"Post-trade handler error: {e}")
        
        return context
    
    def _process_signals(self):
        """Main signal processing loop"""
        while not self.stop_event.is_set():
            try:
                # Get signal with timeout
                order = self.signal_queue.get(timeout=1.0)
                self.stats['signals_received'] += 1
                
                # Execute trade
                context = self._execute_trade(order)
                
                if context and context.status == "executed":
                    logger.info(f"Trade complete: {context.signal.symbol} "
                              f"(latency: {context.execution_time_ms:.1f}ms)")
                
            except Empty:
                continue
            except Exception as e:
                logger.error(f"Signal processing error: {e}")
    
    def start(self):
        """Start paper trading loop"""
        if self.running:
            logger.warning("Paper trading loop already running")
            return
        
        # Verify paper mode
        if not self.demo_orchestrator.verify_paper_mode():
            logger.critical("PAPER MODE VERIFICATION FAILED - NOT STARTING")
            return
        
        self.running = True
        self.stop_event.clear()
        
        # Start processing thread
        self.processing_thread = Thread(target=self._process_signals, daemon=True)
        self.processing_thread.start()
        
        logger.info("Paper trading loop started")
    
    def stop(self):
        """Stop paper trading loop"""
        self.running = False
        self.stop_event.set()
        
        if hasattr(self, 'processing_thread'):
            self.processing_thread.join(timeout=5.0)
        
        logger.info("Paper trading loop stopped")
    
    def close_position(self, trade_id: str, exit_price: float) -> Optional[float]:
        """Close an active paper trade"""
        with self.trade_lock:
            context = self.active_trades.pop(trade_id, None)
        
        if not context:
            return None
        
        # Calculate PnL
        if context.routed_order.direction == 'buy':
            pnl = (exit_price - context.entry_price) * context.size * 100000  # Pip value approx
        else:
            pnl = (context.entry_price - exit_price) * context.size * 100000
        
        context.realized_pnl = pnl
        context.exit_time = time.time()
        context.status = "closed"
        
        # Record in PnL tracker
        trade_record = TradeRecord(
            trade_id=trade_id,
            symbol=context.routed_order.symbol,
            direction=context.routed_order.direction,
            entry_price=context.entry_price,
            exit_price=exit_price,
            size=context.size,
            realized_pnl=pnl,
            entry_time=context.entry_time,
            exit_time=context.exit_time,
            broker=context.routed_order.broker.value
        )
        
        self.pnl_tracker.record_trade(trade_record)
        self.stats['trades_closed'] += 1
        
        logger.info(f"Position closed: {trade_id} PnL=${pnl:.2f}")
        return pnl
    
    def get_status(self) -> Dict:
        """Get trading loop status"""
        return {
            'running': self.running,
            'paper_mode_verified': self.demo_orchestrator.verify_paper_mode(),
            'queue_size': self.signal_queue.qsize(),
            'active_trades': len(self.active_trades),
            'stats': self.stats,
            'daily_pnl': self.pnl_tracker.get_current_pnl(),
            'risk_status': self.risk_manager.get_status()
        }


# Global instance
paper_trading_loop: Optional[PaperTradingLoop] = None


def get_paper_trading_loop(enable_taep: bool = True) -> PaperTradingLoop:
    """Get or create global paper trading loop"""
    global paper_trading_loop
    if paper_trading_loop is None:
        paper_trading_loop = PaperTradingLoop(enable_taep=enable_taep)
    return paper_trading_loop


# Example usage
if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    
    # Create loop
    loop = get_paper_trading_loop()
    
    # Check status
    print(f"Status: {loop.get_status()}")
    
    # Start
    loop.start()
    
    # Run for a bit
    time.sleep(10)
    
    # Stop
    loop.stop()
