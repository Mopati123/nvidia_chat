"""
Demo Account Orchestrator
Manages paper trading on Deriv and MT5 demo accounts
Automatic demo account selection, balance verification, cross-broker reconciliation
"""

import os
import time
import logging
from typing import Dict, Optional, List, Tuple
from dataclasses import dataclass
from enum import Enum
from threading import Lock

from trading.brokers.deriv_broker import DerivBroker
from trading.brokers.mt5_broker import MT5Broker

logger = logging.getLogger(__name__)


class DemoStatus(Enum):
    AVAILABLE = "available"
    BUSY = "busy"
    NO_FUNDS = "no_funds"
    DISCONNECTED = "disconnected"
    ERROR = "error"


@dataclass
class DemoAccount:
    """Demo account information"""
    broker: str  # 'deriv' or 'mt5'
    name: str
    account_id: str
    balance: float
    currency: str
    status: DemoStatus
    last_check: float
    error_message: Optional[str] = None


class DemoOrchestrator:
    """
    Orchestrates demo/paper trading across multiple brokers
    
    Features:
    - Automatic demo account discovery
    - Balance monitoring and low-fund alerts
    - Smart account selection (round-robin with balance check)
    - Cross-broker position reconciliation
    - Paper trading mode enforcement
    """
    
    def __init__(
        self,
        min_balance_threshold: float = 100.0,
        balance_check_interval: int = 300,  # 5 minutes
        paper_mode_enforced: bool = True
    ):
        self.min_balance_threshold = min_balance_threshold
        self.balance_check_interval = balance_check_interval
        self.paper_mode_enforced = paper_mode_enforced
        
        self.lock = Lock()
        self.accounts: Dict[str, DemoAccount] = {}  # account_key -> DemoAccount
        self.active_account: Optional[str] = None
        self.account_rotation_index = 0
        
        # Broker instances
        self.deriv: Optional[DerivBroker] = None
        self.mt5: Optional[MT5Broker] = None
        
        # Stats
        self.trades_executed = 0
        self.failed_trades = 0
        self.last_reconciliation = 0
        
        # Paper mode safety
        if paper_mode_enforced:
            os.environ['TRADING_MODE'] = 'paper'
            logger.info("PAPER MODE ENFORCED - No live trading possible")
        
        self._initialize_brokers()
        self._discover_accounts()
    
    def _initialize_brokers(self):
        """Initialize broker connections"""
        # Deriv
        try:
            self.deriv = DerivBroker()
            if self.deriv.connect():
                # Verify it's demo
                if hasattr(self.deriv, 'is_demo') and not self.deriv.is_demo():
                    logger.error("Deriv account is LIVE - refusing to use")
                    self.deriv = None
            else:
                logger.warning("Deriv connection failed")
                self.deriv = None
        except Exception as e:
            logger.warning(f"Deriv not available: {e}")
            self.deriv = None
        
        # MT5
        try:
            self.mt5 = MT5Broker()
            if self.mt5.connect():
                # Verify it's demo
                if hasattr(self.mt5, 'is_demo') and not self.mt5.is_demo():
                    logger.error("MT5 account is LIVE - refusing to use")
                    self.mt5 = None
            else:
                logger.warning("MT5 connection failed")
                self.mt5 = None
        except Exception as e:
            logger.warning(f"MT5 not available: {e}")
            self.mt5 = None
    
    def _discover_accounts(self):
        """Discover and catalog all available demo accounts"""
        now = time.time()
        
        # Deriv accounts
        if self.deriv:
            try:
                account_info = self.deriv.get_account_info()
                if account_info:
                    key = "deriv_demo"
                    self.accounts[key] = DemoAccount(
                        broker='deriv',
                        name='Deriv Demo',
                        account_id=str(account_info.get('login', 'unknown')),
                        balance=float(account_info.get('balance', 0)),
                        currency=account_info.get('currency', 'USD'),
                        status=DemoStatus.AVAILABLE,
                        last_check=now
                    )
                    logger.info(f"Discovered Deriv demo: ${self.accounts[key].balance:.2f}")
            except Exception as e:
                logger.error(f"Failed to discover Deriv account: {e}")
        
        # MT5 accounts
        if self.mt5:
            try:
                account_info = self.mt5.get_account_info()
                if account_info:
                    key = "mt5_demo"
                    self.accounts[key] = DemoAccount(
                        broker='mt5',
                        name='MT5 Demo',
                        account_id=str(account_info.get('login', 'unknown')),
                        balance=float(account_info.get('balance', 0)),
                        currency=account_info.get('currency', 'USD'),
                        status=DemoStatus.AVAILABLE,
                        last_check=now
                    )
                    logger.info(f"Discovered MT5 demo: ${self.accounts[key].balance:.2f}")
            except Exception as e:
                logger.error(f"Failed to discover MT5 account: {e}")
    
    def refresh_account_balances(self):
        """Refresh all account balances"""
        now = time.time()
        
        for key, account in self.accounts.items():
            # Skip if checked recently
            if now - account.last_check < self.balance_check_interval:
                continue
            
            try:
                if account.broker == 'deriv' and self.deriv:
                    info = self.deriv.get_account_info()
                    if info:
                        account.balance = float(info.get('balance', 0))
                        account.status = DemoStatus.AVAILABLE
                        account.error_message = None
                
                elif account.broker == 'mt5' and self.mt5:
                    info = self.mt5.get_account_info()
                    if info:
                        account.balance = float(info.get('balance', 0))
                        account.status = DemoStatus.AVAILABLE
                        account.error_message = None
                
                account.last_check = now
                
                # Check low balance
                if account.balance < self.min_balance_threshold:
                    account.status = DemoStatus.NO_FUNDS
                    logger.warning(f"Low balance on {key}: ${account.balance:.2f}")
                
            except Exception as e:
                account.status = DemoStatus.ERROR
                account.error_message = str(e)
                logger.error(f"Balance check failed for {key}: {e}")
    
    def select_account(self, symbol: str, preference: Optional[str] = None) -> Optional[DemoAccount]:
        """
        Select best demo account for trading
        
        Selection logic:
        1. Synthetics → Deriv only
        2. Preference honored if valid
        3. Round-robin with balance check
        4. Skip accounts with errors or low funds
        """
        self.refresh_account_balances()
        
        # Synthetics = Deriv only
        if symbol.startswith('R_') or symbol.startswith('frxR_'):
            if 'deriv_demo' in self.accounts:
                acc = self.accounts['deriv_demo']
                if acc.status == DemoStatus.AVAILABLE:
                    self.active_account = 'deriv_demo'
                    return acc
            logger.warning(f"No Deriv account for synthetic {symbol}")
            return None
        
        # Build candidate list
        available = [
            key for key, acc in self.accounts.items()
            if acc.status == DemoStatus.AVAILABLE
        ]
        
        if not available:
            logger.error("No available demo accounts")
            return None
        
        # Preference honored if available
        if preference:
            pref_key = f"{preference}_demo"
            if pref_key in available:
                self.active_account = pref_key
                return self.accounts[pref_key]
        
        # Round-robin selection
        with self.lock:
            n = len(available)
            for i in range(n):
                idx = (self.account_rotation_index + i) % n
                key = available[idx]
                self.account_rotation_index = (idx + 1) % n
                self.active_account = key
                return self.accounts[key]
        
        return None
    
    def get_broker_for_symbol(self, symbol: str, account_key: str) -> Optional[object]:
        """Get broker instance for account"""
        if account_key not in self.accounts:
            return None
        
        account = self.accounts[account_key]
        
        if account.broker == 'deriv':
            return self.deriv
        elif account.broker == 'mt5':
            return self.mt5
        
        return None
    
    def reconcile_positions(self) -> Dict:
        """
        Reconcile positions across all brokers
        
        Returns discrepancy report
        """
        self.last_reconciliation = time.time()
        
        positions_by_broker = {}
        
        # Get positions from each broker
        if self.deriv:
            try:
                positions_by_broker['deriv'] = self.deriv.get_positions()
            except Exception as e:
                logger.error(f"Failed to get Deriv positions: {e}")
                positions_by_broker['deriv'] = []
        
        if self.mt5:
            try:
                positions_by_broker['mt5'] = self.mt5.get_positions()
            except Exception as e:
                logger.error(f"Failed to get MT5 positions: {e}")
                positions_by_broker['mt5'] = []
        
        # Check for discrepancies
        all_symbols = set()
        for positions in positions_by_broker.values():
            for pos in positions:
                all_symbols.add(pos.get('symbol', ''))
        
        discrepancies = []
        for symbol in all_symbols:
            brokers_with_position = [
                b for b, positions in positions_by_broker.items()
                if any(p.get('symbol') == symbol for p in positions)
            ]
            
            if len(brokers_with_position) > 1:
                # Same symbol on multiple brokers = potential issue
                discrepancies.append({
                    'symbol': symbol,
                    'brokers': brokers_with_position,
                    'type': 'duplicate_symbol'
                })
        
        return {
            'timestamp': self.last_reconciliation,
            'positions_by_broker': positions_by_broker,
            'total_positions': sum(len(p) for p in positions_by_broker.values()),
            'discrepancies': discrepancies,
            'clean': len(discrepancies) == 0
        }
    
    def verify_paper_mode(self) -> bool:
        """
        Verify all connected accounts are demo/paper
        
        Returns True if safe to trade
        """
        if not self.paper_mode_enforced:
            return True  # No enforcement
        
        for key, account in self.accounts.items():
            if account.broker == 'deriv' and self.deriv:
                if hasattr(self.deriv, 'is_demo') and not self.deriv.is_demo():
                    logger.critical(f"LIVE ACCOUNT DETECTED: {key}")
                    return False
            
            if account.broker == 'mt5' and self.mt5:
                if hasattr(self.mt5, 'is_demo') and not self.mt5.is_demo():
                    logger.critical(f"LIVE ACCOUNT DETECTED: {key}")
                    return False
        
        return True
    
    def get_status(self) -> Dict:
        """Get orchestrator status"""
        self.refresh_account_balances()
        
        return {
            'paper_mode_enforced': self.paper_mode_enforced,
            'paper_mode_verified': self.verify_paper_mode(),
            'accounts': {
                key: {
                    'broker': acc.broker,
                    'balance': acc.balance,
                    'currency': acc.currency,
                    'status': acc.status.value,
                    'error': acc.error_message
                }
                for key, acc in self.accounts.items()
            },
            'active_account': self.active_account,
            'trades_executed': self.trades_executed,
            'failed_trades': self.failed_trades,
            'last_reconciliation': self.last_reconciliation
        }
    
    def reset_all_accounts(self):
        """Reset/clear all positions on demo accounts (emergency)"""
        logger.critical("RESETTING ALL DEMO ACCOUNTS")
        
        if self.deriv:
            try:
                positions = self.deriv.get_positions()
                for pos in positions:
                    self.deriv.close_position(pos.get('id'))
                logger.info("Deriv positions closed")
            except Exception as e:
                logger.error(f"Failed to reset Deriv: {e}")
        
        if self.mt5:
            try:
                positions = self.mt5.get_positions()
                for pos in positions:
                    self.mt5.close_position(pos.get('ticket'))
                logger.info("MT5 positions closed")
            except Exception as e:
                logger.error(f"Failed to reset MT5: {e}")


# Global instance
demo_orchestrator: Optional[DemoOrchestrator] = None


def get_demo_orchestrator(
    min_balance_threshold: float = 100.0,
    paper_mode_enforced: bool = True
) -> DemoOrchestrator:
    """Get or create global demo orchestrator"""
    global demo_orchestrator
    if demo_orchestrator is None:
        demo_orchestrator = DemoOrchestrator(
            min_balance_threshold=min_balance_threshold,
            paper_mode_enforced=paper_mode_enforced
        )
    return demo_orchestrator


# Example usage
if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    
    # Create orchestrator
    orch = get_demo_orchestrator()
    
    # Check status
    print(f"Status: {orch.get_status()}")
    
    # Select account for EURUSD
    account = orch.select_account('EURUSD')
    if account:
        print(f"Selected: {account.name} with ${account.balance:.2f}")
    else:
        print("No account available")
    
    # Reconcile
    recon = orch.reconcile_positions()
    print(f"Reconciliation: {recon}")
