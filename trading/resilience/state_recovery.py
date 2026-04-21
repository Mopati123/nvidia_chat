"""
State Recovery
Save/restore TAEP state on crash, position reconciliation on restart, graceful shutdown
"""

import os
import json
import time
import signal
import logging
from typing import Dict, Optional, Any, Callable, List
from pathlib import Path
from dataclasses import dataclass, asdict
from threading import Lock

from taep.core.state import TAEPState
from trading.risk.risk_manager import get_risk_manager
from trading.paper_trading_loop import get_paper_trading_loop

logger = logging.getLogger(__name__)


@dataclass
class SystemState:
    """Complete system state snapshot"""
    timestamp: float
    version: str = "1.0"
    
    # TAEP state
    taep_states: Dict[str, Any] = None
    
    # Risk manager state
    daily_pnl: float = 0.0
    open_positions: Dict = None
    
    # Paper trading state
    active_trades: Dict = None
    daily_stats: Dict = None
    
    # Metadata
    shutdown_reason: str = ""
    shutdown_clean: bool = False


class StateRecovery:
    """
    System state recovery and persistence
    
    Features:
    - Periodic state snapshots
    - Crash recovery
    - Position reconciliation on restart
    - Graceful shutdown handling
    """
    
    def __init__(
        self,
        data_dir: str = "trading_data/state",
        save_interval: int = 30,  # seconds
        max_snapshots: int = 10
    ):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.save_interval = save_interval
        self.max_snapshots = max_snapshots
        
        # State file paths
        self.current_state_file = self.data_dir / "current_state.json"
        self.snapshot_dir = self.data_dir / "snapshots"
        self.snapshot_dir.mkdir(exist_ok=True)
        
        # State tracking
        self.last_save = 0
        self.lock = Lock()
        self.running = False
        
        # Shutdown handling
        self.shutdown_handlers: List[Callable] = []
        self._setup_signal_handlers()
        
        # Statistics
        self.saves_performed = 0
        self.restores_performed = 0
        
        logger.info(f"StateRecovery initialized: dir={data_dir}")
    
    def _setup_signal_handlers(self):
        """Setup graceful shutdown handlers"""
        def handle_signal(signum, frame):
            logger.info(f"Received signal {signum}, initiating graceful shutdown...")
            self.graceful_shutdown(signal_name=signal.Signals(signum).name)
        
        # Register for common termination signals (cross-platform)
        signals_to_handle = [signal.SIGTERM, signal.SIGINT]
        if hasattr(signal, 'SIGHUP'):
            signals_to_handle.append(signal.SIGHUP)
        
        for sig in signals_to_handle:
            try:
                signal.signal(sig, handle_signal)
            except (ValueError, AttributeError):
                # Signal not available on this platform
                pass
        
        # Windows specific
        if hasattr(signal, 'SIGBREAK'):
            try:
                signal.signal(signal.SIGBREAK, handle_signal)
            except (ValueError, AttributeError):
                pass
    
    def register_shutdown_handler(self, handler: Callable):
        """Register callback for graceful shutdown"""
        self.shutdown_handlers.append(handler)
    
    def save_state(self, reason: str = "periodic", clean: bool = False):
        """
        Save current system state
        
        Args:
            reason: Why state is being saved
            clean: Whether this is a clean shutdown
        """
        with self.lock:
            try:
                state = self._capture_state()
                state.shutdown_reason = reason
                state.shutdown_clean = clean
                
                # Save current state
                with open(self.current_state_file, 'w') as f:
                    json.dump(self._state_to_dict(state), f, indent=2)
                
                # Create snapshot (keep last N)
                snapshot_file = self.snapshot_dir / f"snapshot_{int(time.time())}.json"
                with open(snapshot_file, 'w') as f:
                    json.dump(self._state_to_dict(state), f, indent=2)
                
                self._cleanup_old_snapshots()
                
                self.saves_performed += 1
                self.last_save = time.time()
                
                logger.info(f"State saved: {reason}")
                
            except Exception as e:
                logger.error(f"Failed to save state: {e}")
    
    def _capture_state(self) -> SystemState:
        """Capture current system state"""
        state = SystemState(
            timestamp=time.time(),
            taep_states={},
            open_positions={},
            active_trades={},
            daily_stats={}
        )
        
        try:
            # Capture risk manager state
            rm = get_risk_manager()
            rm_state = rm.get_status()
            state.daily_pnl = rm_state.get('daily_pnl', 0.0)
            state.open_positions = rm.get_position_report()
        except Exception as e:
            logger.warning(f"Failed to capture risk manager state: {e}")
        
        try:
            # Capture paper trading state
            ptl = get_paper_trading_loop()
            ptl_status = ptl.get_status()
            state.active_trades = ptl_status.get('active_trades', {})
            state.daily_stats = {
                'trades_executed': ptl_status.get('stats', {}).get('trades_executed', 0),
                'signals_received': ptl_status.get('stats', {}).get('signals_received', 0)
            }
        except Exception as e:
            logger.warning(f"Failed to capture paper trading state: {e}")
        
        return state
    
    def _state_to_dict(self, state: SystemState) -> Dict:
        """Convert state to dictionary"""
        return asdict(state)
    
    def _cleanup_old_snapshots(self):
        """Remove old snapshots, keeping only the most recent"""
        try:
            snapshots = sorted(
                self.snapshot_dir.glob("snapshot_*.json"),
                key=lambda p: p.stat().st_mtime,
                reverse=True
            )
            
            for old_snapshot in snapshots[self.max_snapshots:]:
                old_snapshot.unlink()
                logger.debug(f"Removed old snapshot: {old_snapshot.name}")
                
        except Exception as e:
            logger.warning(f"Failed to cleanup snapshots: {e}")
    
    def restore_state(self) -> Optional[SystemState]:
        """
        Restore system state from disk
        
        Returns restored state or None if no state found
        """
        with self.lock:
            try:
                if not self.current_state_file.exists():
                    logger.info("No previous state found")
                    return None
                
                with open(self.current_state_file, 'r') as f:
                    data = json.load(f)
                
                state = SystemState(**data)
                
                self.restores_performed += 1
                
                if state.shutdown_clean:
                    logger.info("Previous shutdown was clean")
                else:
                    logger.warning(f"Previous shutdown was NOT clean: {state.shutdown_reason}")
                
                return state
                
            except Exception as e:
                logger.error(f"Failed to restore state: {e}")
                return None
    
    def reconcile_positions(self, restored_state: Optional[SystemState] = None):
        """
        Reconcile positions with brokers on restart
        
        Compares saved positions with actual broker positions
        """
        if restored_state is None:
            restored_state = self.restore_state()
        
        if not restored_state or not restored_state.open_positions:
            logger.info("No previous positions to reconcile")
            return
        
        logger.info(f"Reconciling {len(restored_state.open_positions)} saved positions...")
        
        discrepancies = []
        
        # Get current broker positions
        try:
            from trading.brokers.demo_orchestrator import get_demo_orchestrator
            orchestrator = get_demo_orchestrator()
            recon = orchestrator.reconcile_positions()
            
            current_positions = []
            for broker, positions in recon.get('positions_by_broker', {}).items():
                for pos in positions:
                    current_positions.append({
                        'symbol': pos.get('symbol'),
                        'broker': broker,
                        'size': pos.get('size', 0),
                        'direction': 'buy' if pos.get('type') == 0 else 'sell'
                    })
            
            # Compare
            saved_symbols = {p['symbol'] for p in restored_state.open_positions}
            current_symbols = {p['symbol'] for p in current_positions}
            
            missing_in_broker = saved_symbols - current_symbols
            extra_in_broker = current_symbols - saved_symbols
            
            if missing_in_broker:
                discrepancies.append(f"Missing in broker: {missing_in_broker}")
            
            if extra_in_broker:
                discrepancies.append(f"Extra in broker: {extra_in_broker}")
            
            if discrepancies:
                logger.warning(f"Position discrepancies found: {discrepancies}")
            else:
                logger.info("Position reconciliation: OK")
                
        except Exception as e:
            logger.error(f"Position reconciliation failed: {e}")
    
    def graceful_shutdown(self, signal_name: str = "unknown"):
        """
        Perform graceful shutdown
        
        1. Call all registered shutdown handlers
        2. Save final state
        3. Exit
        """
        logger.info(f"Graceful shutdown initiated (signal: {signal_name})")
        
        # Call shutdown handlers
        for handler in self.shutdown_handlers:
            try:
                handler()
            except Exception as e:
                logger.error(f"Shutdown handler error: {e}")
        
        # Save final state
        self.save_state(reason=f"shutdown_{signal_name}", clean=True)
        
        logger.info("Graceful shutdown complete")
    
    def periodic_save(self):
        """Call this periodically to save state"""
        if time.time() - self.last_save >= self.save_interval:
            self.save_state(reason="periodic")
    
    def get_status(self) -> Dict:
        """Get recovery system status"""
        return {
            'data_dir': str(self.data_dir),
            'current_state_exists': self.current_state_file.exists(),
            'last_save': self.last_save,
            'saves_performed': self.saves_performed,
            'restores_performed': self.restores_performed,
            'snapshot_count': len(list(self.snapshot_dir.glob("snapshot_*.json")))
        }


# Global instance
_state_recovery: Optional[StateRecovery] = None


def get_state_recovery(
    data_dir: str = "trading_data/state",
    save_interval: int = 30
) -> StateRecovery:
    """Get or create global state recovery"""
    global _state_recovery
    if _state_recovery is None:
        _state_recovery = StateRecovery(data_dir, save_interval)
    return _state_recovery


def graceful_shutdown_handler(signum=None, frame=None):
    """Global graceful shutdown handler"""
    recovery = get_state_recovery()
    signal_name = signal.Signals(signum).name if signum else "manual"
    recovery.graceful_shutdown(signal_name)
    
    # Exit cleanly
    import sys
    sys.exit(0)


# Register atexit handler
import atexit
atexit.register(lambda: graceful_shutdown_handler())


# Example usage
if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    
    # Create recovery
    recovery = get_state_recovery()
    
    # Test save
    recovery.save_state(reason="test")
    
    # Test restore
    state = recovery.restore_state()
    if state:
        print(f"Restored state from: {datetime.fromtimestamp(state.timestamp)}")
    
    # Status
    print(f"Status: {recovery.get_status()}")
