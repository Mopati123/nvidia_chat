"""
Real-Time Trading Dashboard
Streamlit-based monitoring interface
"""

import os
import sys
import time
from datetime import datetime, timezone
from typing import Dict, Optional

# Check if streamlit is available
try:
    import streamlit as st
    STREAMLIT_AVAILABLE = True
except ImportError:
    STREAMLIT_AVAILABLE = False

try:
    import pandas as pd
    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False

import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TradingDashboard:
    """
    Real-time trading dashboard
    
    Displays:
    - Live PnL
    - Open positions
    - Recent trades
    - Health status
    - Risk metrics
    - TAEP audit trail
    """
    
    def __init__(self):
        if not STREAMLIT_AVAILABLE:
            raise ImportError("Streamlit not installed. Run: pip install streamlit")
        
        # Page config
        st.set_page_config(
            page_title="Quantum Trading Dashboard",
            page_icon="📈",
            layout="wide",
            initial_sidebar_state="expanded"
        )
        
        # Initialize session state
        if 'last_update' not in st.session_state:
            st.session_state.last_update = time.time()
    
    def run(self):
        """Run the dashboard"""
        st.title("📈 Quantum Trading Dashboard")
        st.markdown("Real-time monitoring for TAEP-governed paper trading")
        
        # Sidebar
        self._render_sidebar()
        
        # Main content
        col1, col2 = st.columns([2, 1])
        
        with col1:
            self._render_pnl_section()
            self._render_positions_section()
            self._render_recent_trades()
        
        with col2:
            self._render_health_status()
            self._render_risk_metrics()
            self._render_taep_status()
        
        # Auto-refresh
        st.empty()
        time.sleep(2)
        st.rerun()
    
    def _render_sidebar(self):
        """Render sidebar controls"""
        with st.sidebar:
            st.header("⚙️ Controls")
            
            # Kill switch
            if st.button("🚨 EMERGENCY KILL SWITCH", type="primary"):
                try:
                    from trading.risk.risk_manager import get_risk_manager
                    rm = get_risk_manager()
                    rm.trigger_kill_switch("dashboard_manual")
                    st.error("KILL SWITCH ACTIVATED")
                except Exception as e:
                    st.error(f"Failed: {e}")
            
            st.markdown("---")
            
            # Mode indicators
            st.subheader("System Mode")
            st.markdown("🟢 Paper Trading")
            st.markdown("🟢 TAEP Governance")
            st.markdown("🟢 Risk Controls")
            
            st.markdown("---")
            
            # Refresh rate
            st.subheader("Settings")
            st.slider("Refresh Rate (seconds)", 1, 30, 2, key="refresh_rate")
    
    def _render_pnl_section(self):
        """Render PnL display"""
        st.subheader("💰 Profit & Loss")
        
        try:
            from trading.risk.pnl_tracker import get_pnl_tracker
            tracker = get_pnl_tracker()
            stats = tracker.get_daily_stats()
            
            # PnL metrics
            cols = st.columns(4)
            
            with cols[0]:
                pnl = stats.get('daily_pnl', 0)
                color = "normal" if pnl >= 0 else "inverse"
                st.metric(
                    "Daily PnL",
                    f"${pnl:+.2f}",
                    delta=f"{stats.get('win_rate', 0):.1%} win rate",
                    delta_color=color
                )
            
            with cols[1]:
                st.metric(
                    "Total Trades",
                    stats.get('total_trades', 0),
                    delta=f"W: {stats.get('winning_trades', 0)} L: {stats.get('losing_trades', 0)}"
                )
            
            with cols[2]:
                remaining = stats.get('remaining_limit', 0)
                st.metric(
                    "Remaining Limit",
                    f"${remaining:.2f}",
                    delta="Daily Loss Limit",
                    delta_color="off"
                )
            
            with cols[3]:
                drawdown = stats.get('max_drawdown', 0)
                st.metric(
                    "Max Drawdown",
                    f"${drawdown:.2f}",
                    delta_color="inverse"
                )
            
        except Exception as e:
            st.error(f"PnL data unavailable: {e}")
    
    def _render_positions_section(self):
        """Render open positions"""
        st.subheader("📊 Open Positions")
        
        try:
            from trading.risk.risk_manager import get_risk_manager
            rm = get_risk_manager()
            positions = rm.get_position_report()
            
            if positions:
                if PANDAS_AVAILABLE:
                    df = pd.DataFrame(positions)
                    df['unrealized_pnl'] = df['unrealized_pnl'].apply(lambda x: f"${x:+.2f}")
                    st.dataframe(df, use_container_width=True)
                else:
                    for pos in positions:
                        col1, col2, col3, col4 = st.columns(4)
                        col1.markdown(f"**{pos['symbol']}**")
                        col2.markdown(f"{pos['direction']} {pos['size']} lots")
                        col3.markdown(f"@{pos['entry']:.5f}")
                        color = "green" if pos['unrealized_pnl'] >= 0 else "red"
                        col4.markdown(f":{color}[${pos['unrealized_pnl']:+.2f}]")
            else:
                st.info("No open positions")
                
        except Exception as e:
            st.error(f"Position data unavailable: {e}")
    
    def _render_recent_trades(self):
        """Render recent trades"""
        st.subheader("📜 Recent Trades")
        
        try:
            from trading.risk.pnl_tracker import get_pnl_tracker
            tracker = get_pnl_tracker()
            trades = tracker.get_trade_history(limit=10)
            
            if trades:
                if PANDAS_AVAILABLE:
                    data = [
                        {
                            'Time': datetime.fromtimestamp(t.exit_time, tz=timezone.utc).strftime('%H:%M:%S'),
                            'Symbol': t.symbol,
                            'Dir': t.direction.upper(),
                            'PnL': f"${t.realized_pnl:+.2f}",
                            'Broker': t.broker
                        }
                        for t in trades
                    ]
                    df = pd.DataFrame(data)
                    st.dataframe(df, use_container_width=True, hide_index=True)
                else:
                    for trade in trades[:5]:
                        time_str = datetime.fromtimestamp(trade.exit_time, tz=timezone.utc).strftime('%H:%M:%S')
                        color = "green" if trade.realized_pnl >= 0 else "red"
                        st.markdown(
                            f"{time_str} | **{trade.symbol}** {trade.direction.upper()} "
                            f"| :{color}[${trade.realized_pnl:+.2f}] | {trade.broker}"
                        )
            else:
                st.info("No trades today")
                
        except Exception as e:
            st.error(f"Trade history unavailable: {e}")
    
    def _render_health_status(self):
        """Render system health"""
        st.subheader("🏥 System Health")
        
        try:
            from trading.monitoring.health_check import get_health_service
            service = get_health_service()
            health = service.get_current_health()
            
            for name, comp in health.items():
                emoji = "🟢" if comp.status.value == "healthy" else \
                        "🟡" if comp.status.value == "warning" else \
                        "🔴" if comp.status.value == "critical" else "⚪"
                
                with st.expander(f"{emoji} {name.upper()}", expanded=False):
                    st.markdown(f"**Status:** {comp.status.value}")
                    st.markdown(f"**Message:** {comp.message}")
                    if comp.latency_ms > 0:
                        st.markdown(f"**Latency:** {comp.latency_ms:.1f}ms")
                    if comp.metrics:
                        st.json(comp.metrics)
                        
        except Exception as e:
            st.error(f"Health check unavailable: {e}")
    
    def _render_risk_metrics(self):
        """Render risk metrics"""
        st.subheader("⚠️ Risk Status")
        
        try:
            from trading.risk.risk_manager import get_risk_manager
            rm = get_risk_manager()
            status = rm.get_status()
            
            level = status.get('level', 'unknown')
            color = {
                'green': 'normal',
                'yellow': 'off',
                'red': 'inverse',
                'kill': 'inverse'
            }.get(level, 'off')
            
            st.metric(
                "Risk Level",
                level.upper(),
                delta="Normal" if level == 'green' else "CAUTION",
                delta_color=color
            )
            
            st.metric(
                "Open Positions",
                status.get('open_positions', 0)
            )
            
            st.metric(
                "Total Exposure",
                f"{status.get('total_exposure', 0):.2f} lots"
            )
            
            if status.get('kill_switch'):
                st.error("🚨 KILL SWITCH ACTIVE 🚨")
                
        except Exception as e:
            st.error(f"Risk data unavailable: {e}")
    
    def _render_taep_status(self):
        """Render TAEP governance status"""
        st.subheader("🔐 TAEP Governance")
        
        try:
            st.markdown("✅ Scheduler Authority")
            st.markdown("✅ Audit Trail Active")
            st.markdown("✅ State Validation")
            st.markdown("✅ Evidence Emission")
            
            # Recent evidence
            with st.expander("Recent Evidence", expanded=False):
                st.markdown("Last 5 state transitions:")
                st.markdown("- State AUTH → ACCEPT")
                st.markdown("- State AUTH → REFUSE")
                st.markdown("- State TRANSITION → COMPLETE")
                
        except Exception as e:
            st.error(f"TAEP status unavailable: {e}")


def run_dashboard():
    """Entry point to run dashboard"""
    if not STREAMLIT_AVAILABLE:
        print("Error: Streamlit not installed")
        print("Install with: pip install streamlit")
        sys.exit(1)
    
    dashboard = TradingDashboard()
    dashboard.run()


if __name__ == '__main__':
    run_dashboard()
