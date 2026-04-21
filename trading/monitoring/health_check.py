"""
Health Check Service
Monitors system health, broker connectivity, API rate limits, TAEP consistency
"""

import os
import time
import logging
import threading
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

from trading.brokers.deriv_broker import DerivBroker
from trading.brokers.mt5_broker import MT5Broker
from trading.brokers.tradingview_connector import TradingViewConnector
from trading.risk.risk_manager import get_risk_manager

logger = logging.getLogger(__name__)


class HealthStatus(Enum):
    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


@dataclass
class ComponentHealth:
    """Health status of a system component"""
    name: str
    status: HealthStatus
    last_check: float
    latency_ms: float
    message: str
    metrics: Dict


class HealthCheckService:
    """
    Comprehensive health monitoring system
    
    Monitors:
    - Broker connectivity (Deriv, MT5)
    - TradingView connector
    - API rate limits
    - TAEP state consistency
    - Risk manager status
    - System resources
    """
    
    def __init__(
        self,
        check_interval: int = 60,  # seconds
        warning_threshold: float = 1000.0,  # ms
        critical_threshold: float = 5000.0  # ms
    ):
        self.check_interval = check_interval
        self.warning_threshold = warning_threshold
        self.critical_threshold = critical_threshold
        
        # Components to monitor
        self.deriv: Optional[DerivBroker] = None
        self.mt5: Optional[MT5Broker] = None
        self.tv_connector: Optional[TradingViewConnector] = None
        
        # State
        self.running = False
        self.check_thread: Optional[threading.Thread] = None
        self.stop_event = threading.Event()
        
        # Health storage
        self.health_history: List[Dict] = []
        self.max_history = 1000
        self.current_health: Dict[str, ComponentHealth] = {}
        
        # Callbacks
        self.alert_handlers: List[Callable[[ComponentHealth], None]] = []
        
        # Statistics
        self.checks_performed = 0
        self.alerts_triggered = 0
        
        logger.info("HealthCheckService initialized")
    
    def register_brokers(
        self,
        deriv: Optional[DerivBroker] = None,
        mt5: Optional[MT5Broker] = None,
        tv_connector: Optional[TradingViewConnector] = None
    ):
        """Register brokers to monitor"""
        self.deriv = deriv
        self.mt5 = mt5
        self.tv_connector = tv_connector
        logger.info("Brokers registered for health monitoring")
    
    def register_alert_handler(self, handler: Callable[[ComponentHealth], None]):
        """Register callback for health alerts"""
        self.alert_handlers.append(handler)
    
    def _check_deriv(self) -> ComponentHealth:
        """Check Deriv broker health"""
        if not self.deriv:
            return ComponentHealth(
                name="deriv",
                status=HealthStatus.UNKNOWN,
                last_check=time.time(),
                latency_ms=0,
                message="Not configured",
                metrics={}
            )
        
        start = time.time()
        try:
            # Test connection
            account_info = self.deriv.get_account_info()
            latency = (time.time() - start) * 1000
            
            if account_info:
                status = HealthStatus.HEALTHY
                message = "Connected"
                metrics = {
                    'balance': account_info.get('balance', 0),
                    'account_id': account_info.get('login', 'unknown')
                }
            else:
                status = HealthStatus.WARNING
                message = "Connected but no account info"
                metrics = {}
            
            # Check latency
            if latency > self.critical_threshold:
                status = HealthStatus.CRITICAL
                message = f"High latency: {latency:.0f}ms"
            elif latency > self.warning_threshold:
                status = HealthStatus.WARNING
                message = f"Elevated latency: {latency:.0f}ms"
            
        except Exception as e:
            latency = (time.time() - start) * 1000
            status = HealthStatus.CRITICAL
            message = f"Connection failed: {str(e)}"
            metrics = {}
        
        return ComponentHealth(
            name="deriv",
            status=status,
            last_check=time.time(),
            latency_ms=latency,
            message=message,
            metrics=metrics
        )
    
    def _check_mt5(self) -> ComponentHealth:
        """Check MT5 broker health"""
        if not self.mt5:
            return ComponentHealth(
                name="mt5",
                status=HealthStatus.UNKNOWN,
                last_check=time.time(),
                latency_ms=0,
                message="Not configured",
                metrics={}
            )
        
        start = time.time()
        try:
            account_info = self.mt5.get_account_info()
            latency = (time.time() - start) * 1000
            
            if account_info:
                status = HealthStatus.HEALTHY
                message = "Connected"
                metrics = {
                    'balance': account_info.get('balance', 0),
                    'account_id': account_info.get('login', 'unknown')
                }
            else:
                status = HealthStatus.WARNING
                message = "Connected but no account info"
                metrics = {}
            
            if latency > self.critical_threshold:
                status = HealthStatus.CRITICAL
                message = f"High latency: {latency:.0f}ms"
            elif latency > self.warning_threshold:
                status = HealthStatus.WARNING
                message = f"Elevated latency: {latency:.0f}ms"
            
        except Exception as e:
            latency = (time.time() - start) * 1000
            status = HealthStatus.CRITICAL
            message = f"Connection failed: {str(e)}"
            metrics = {}
        
        return ComponentHealth(
            name="mt5",
            status=status,
            last_check=time.time(),
            latency_ms=latency,
            message=message,
            metrics=metrics
        )
    
    def _check_tradingview(self) -> ComponentHealth:
        """Check TradingView connector health"""
        if not self.tv_connector:
            return ComponentHealth(
                name="tradingview",
                status=HealthStatus.UNKNOWN,
                last_check=time.time(),
                latency_ms=0,
                message="Not configured",
                metrics={}
            )
        
        try:
            stats = self.tv_connector.stats
            queue_size = len(self.tv_connector.signal_queue)
            
            # Determine status
            if queue_size > 90:  # 90% of max queue
                status = HealthStatus.CRITICAL
                message = f"Queue nearly full: {queue_size}"
            elif stats.get('auth_failed', 0) > 10:
                status = HealthStatus.WARNING
                message = "Multiple auth failures"
            else:
                status = HealthStatus.HEALTHY
                message = "Operating normally"
            
            metrics = {
                'signals_received': stats.get('signals_received', 0),
                'queue_size': queue_size,
                'auth_failures': stats.get('auth_failed', 0),
                'rate_limited': stats.get('rate_limited', 0)
            }
            
        except Exception as e:
            status = HealthStatus.CRITICAL
            message = f"Error: {str(e)}"
            metrics = {}
        
        return ComponentHealth(
            name="tradingview",
            status=status,
            last_check=time.time(),
            latency_ms=0,
            message=message,
            metrics=metrics
        )
    
    def _check_risk_manager(self) -> ComponentHealth:
        """Check risk manager status"""
        try:
            rm = get_risk_manager()
            status_info = rm.get_status()
            
            # Determine status
            if status_info['kill_switch']:
                status = HealthStatus.CRITICAL
                message = "KILL SWITCH ACTIVE"
            elif status_info['level'] == 'red':
                status = HealthStatus.CRITICAL
                message = "Daily loss limit nearly breached"
            elif status_info['level'] == 'yellow':
                status = HealthStatus.WARNING
                message = "Approaching risk limits"
            else:
                status = HealthStatus.HEALTHY
                message = "Risk within limits"
            
            metrics = {
                'daily_pnl': status_info.get('daily_pnl', 0),
                'remaining_limit': status_info.get('remaining_limit', 0),
                'open_positions': status_info.get('open_positions', 0),
                'kill_switch': status_info.get('kill_switch', False)
            }
            
        except Exception as e:
            status = HealthStatus.CRITICAL
            message = f"Risk manager error: {str(e)}"
            metrics = {}
        
        return ComponentHealth(
            name="risk_manager",
            status=status,
            last_check=time.time(),
            latency_ms=0,
            message=message,
            metrics=metrics
        )
    
    def _check_system_resources(self) -> ComponentHealth:
        """Check system resources"""
        try:
            import psutil
            
            # CPU and memory
            cpu_percent = psutil.cpu_percent(interval=0.1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            
            # Determine status
            if cpu_percent > 90 or memory.percent > 90:
                status = HealthStatus.CRITICAL
                message = f"High resource usage: CPU {cpu_percent:.0f}%, Mem {memory.percent:.0f}%"
            elif cpu_percent > 70 or memory.percent > 80:
                status = HealthStatus.WARNING
                message = f"Elevated resource usage: CPU {cpu_percent:.0f}%, Mem {memory.percent:.0f}%"
            else:
                status = HealthStatus.HEALTHY
                message = f"Resources normal: CPU {cpu_percent:.0f}%, Mem {memory.percent:.0f}%"
            
            metrics = {
                'cpu_percent': cpu_percent,
                'memory_percent': memory.percent,
                'memory_available_mb': memory.available / (1024 * 1024),
                'disk_free_gb': disk.free / (1024 * 1024 * 1024)
            }
            
        except ImportError:
            status = HealthStatus.UNKNOWN
            message = "psutil not available"
            metrics = {}
        except Exception as e:
            status = HealthStatus.CRITICAL
            message = f"Resource check failed: {str(e)}"
            metrics = {}
        
        return ComponentHealth(
            name="system_resources",
            status=status,
            last_check=time.time(),
            latency_ms=0,
            message=message,
            metrics=metrics
        )
    
    def _perform_checks(self) -> Dict[str, ComponentHealth]:
        """Perform all health checks"""
        checks = {
            'deriv': self._check_deriv(),
            'mt5': self._check_mt5(),
            'tradingview': self._check_tradingview(),
            'risk_manager': self._check_risk_manager(),
            'system': self._check_system_resources()
        }
        
        self.current_health = checks
        self.checks_performed += 1
        
        # Store history
        health_record = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'components': {
                name: {
                    'status': comp.status.value,
                    'message': comp.message,
                    'latency_ms': comp.latency_ms
                }
                for name, comp in checks.items()
            }
        }
        self.health_history.append(health_record)
        
        # Trim history
        if len(self.health_history) > self.max_history:
            self.health_history = self.health_history[-self.max_history:]
        
        # Check for alerts
        for name, comp in checks.items():
            if comp.status in [HealthStatus.WARNING, HealthStatus.CRITICAL]:
                self._trigger_alert(comp)
        
        return checks
    
    def _trigger_alert(self, component: ComponentHealth):
        """Trigger alert for component"""
        self.alerts_triggered += 1
        logger.warning(f"Health alert: {component.name} - {component.message}")
        
        for handler in self.alert_handlers:
            try:
                handler(component)
            except Exception as e:
                logger.error(f"Alert handler error: {e}")
    
    def _check_loop(self):
        """Background health check loop"""
        while not self.stop_event.is_set():
            self._perform_checks()
            self.stop_event.wait(self.check_interval)
    
    def start(self):
        """Start health monitoring"""
        if self.running:
            logger.warning("Health monitoring already running")
            return
        
        self.running = True
        self.stop_event.clear()
        self.check_thread = threading.Thread(target=self._check_loop, daemon=True)
        self.check_thread.start()
        logger.info("Health monitoring started")
    
    def stop(self):
        """Stop health monitoring"""
        self.running = False
        self.stop_event.set()
        if self.check_thread:
            self.check_thread.join(timeout=5.0)
        logger.info("Health monitoring stopped")
    
    def get_current_health(self) -> Dict[str, ComponentHealth]:
        """Get current health status of all components"""
        if not self.current_health:
            self._perform_checks()
        return self.current_health
    
    def get_overall_status(self) -> HealthStatus:
        """Get overall system health"""
        health = self.get_current_health()
        
        statuses = [comp.status for comp in health.values()]
        
        if HealthStatus.CRITICAL in statuses:
            return HealthStatus.CRITICAL
        elif HealthStatus.WARNING in statuses:
            return HealthStatus.WARNING
        elif all(s == HealthStatus.HEALTHY for s in statuses):
            return HealthStatus.HEALTHY
        else:
            return HealthStatus.UNKNOWN
    
    def get_health_report(self) -> str:
        """Generate formatted health report"""
        health = self.get_current_health()
        overall = self.get_overall_status()
        
        emoji_map = {
            HealthStatus.HEALTHY: "✅",
            HealthStatus.WARNING: "⚠️",
            HealthStatus.CRITICAL: "🚨",
            HealthStatus.UNKNOWN: "❓"
        }
        
        lines = [
            "╔══════════════════════════════════════════════════════════╗",
            f"║           HEALTH CHECK REPORT - {overall.value.upper():<15}       ║",
            "╠══════════════════════════════════════════════════════════╣"
        ]
        
        for name, comp in health.items():
            emoji = emoji_map.get(comp.status, "❓")
            status_str = f"{emoji} {name.upper():<12} {comp.status.value:<10}"
            lines.append(f"║  {status_str:<54}║")
            lines.append(f"║     {comp.message[:50]:<50}║")
            if comp.latency_ms > 0:
                lines.append(f"║     Latency: {comp.latency_ms:.1f}ms{'':<38}║")
            lines.append("║                                                          ║")
        
        lines.append("╚══════════════════════════════════════════════════════════╝")
        
        return "\n".join(lines)
    
    def get_status(self) -> Dict:
        """Get service status"""
        return {
            'running': self.running,
            'checks_performed': self.checks_performed,
            'alerts_triggered': self.alerts_triggered,
            'overall_health': self.get_overall_status().value,
            'current_health': {
                name: {
                    'status': comp.status.value,
                    'message': comp.message
                }
                for name, comp in self.get_current_health().items()
            }
        }


# Global instance
health_service: Optional[HealthCheckService] = None


def get_health_service(
    check_interval: int = 60
) -> HealthCheckService:
    """Get or create global health service"""
    global health_service
    if health_service is None:
        health_service = HealthCheckService(check_interval)
    return health_service


# Example usage
if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    
    # Create service
    service = get_health_service()
    
    # Perform one check
    health = service.get_current_health()
    
    for name, comp in health.items():
        print(f"{name}: {comp.status.value} - {comp.message}")
    
    print(f"\nOverall: {service.get_overall_status().value}")
    print(service.get_health_report())
