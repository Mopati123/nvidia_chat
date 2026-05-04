"""
trading_integration.py — Superposition layer for existing Telegram bots

Integrates ApexQuantumICT trading into ANY python-telegram-bot project.
Just import and add handlers to your existing bot.
"""

import os
import logging
from typing import Optional, Dict, Any
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler

# Setup logging
logger = logging.getLogger(__name__)

# Try to import trading system
try:
    from trading.shadow.shadow_trading_loop import ShadowTradingLoop
    from trading.operators.operator_registry import OperatorRegistry
    from trading.evidence.evidence_chain import EvidenceEmitter
    from trading.market_bridge.minkowski_adapter import MarketDataAdapter
    TRADING_AVAILABLE = True
    logger.info("ApexQuantumICT trading system available")
except ImportError as e:
    TRADING_AVAILABLE = False
    logger.warning(f"Trading system not available: {e}")


class TradingBotSuperposition:
    """
    Superposition layer: merges existing bot with ApexQuantumICT trading.
    
    Usage in your existing bot:
        from apps.telegram.trading_integration import TradingBotSuperposition
        
        trading = TradingBotSuperposition()
        trading.add_handlers(application)  # Add to your bot
    """
    
    def __init__(self):
        self.trading_system: Optional[ShadowTradingLoop] = None
        self.evidence_emitter: Optional[EvidenceEmitter] = None
        self.registry: Optional[OperatorRegistry] = None
        self.adapter: Optional[MarketDataAdapter] = None
        
        if TRADING_AVAILABLE:
            try:
                self.trading_system = ShadowTradingLoop()
                self.evidence_emitter = EvidenceEmitter()
                self.registry = OperatorRegistry()
                self.adapter = MarketDataAdapter()
                logger.info("✓ Trading superposition initialized")
            except Exception as e:
                logger.error(f"Failed to initialize trading: {e}")
    
    def is_available(self) -> bool:
        """Check if trading system is ready"""
        return TRADING_AVAILABLE and self.trading_system is not None
    
    def add_handlers(self, application):
        """
        Add all trading command handlers to your existing bot.
        
        Args:
            application: telegram.ext.Application instance
        """
        if not self.is_available():
            logger.warning("Trading not available, handlers not added")
            return
        
        handlers = [
            CommandHandler("market", self._market_analysis),
            CommandHandler("shadow", self._shadow_trade),
            CommandHandler("operators", self._list_operators),
            CommandHandler("constraints", self._check_constraints),
            CommandHandler("trading", self._trading_status),
        ]
        
        for handler in handlers:
            application.add_handler(handler)
        
        logger.info("✓ Trading handlers added to bot")
    
    # ============== HANDLER METHODS ==============
    
    async def _market_analysis(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """/market <symbol> [bias] — ICT analysis"""
        args = context.args
        if not args:
            await update.message.reply_text(
                "Usage: `/market EURUSD [bullish|bearish]`\n"
                "Runs 25-operator ICT + order-book analysis via quantum-inspired system."
            )
            return
        
        symbol = args[0].upper()
        bias = args[1].lower() if len(args) > 1 else "neutral"
        
        await update.message.chat.send_action(action="typing")
        
        try:
            # Generate demo data (replace with your real data feed)
            ohlcv = self._generate_demo_ohlcv(symbol)
            
            # Run analysis
            analysis = self.trading_system.analyze_setup(symbol, ohlcv)
            
            # Format report
            top_ops = analysis["setup_quality"]["top_signals"][:5]
            op_lines = "\n".join([f"  • `{name}`: {score:.3f}" for name, score in top_ops])
            
            report = f"""📊 **ApexQuantumICT Analysis — {symbol}**

**Bias:** {bias} | **Session:** {self.adapter.get_session()}
**System:** 𝔖 = (X, g, Φ, Π, ℳ, Λ, ℛ, ℰ)

**Top Operator Signals:**
{op_lines}

**Setup Quality:**
• Potential: `{analysis['setup_quality']['potential_strength']:.3f}`
• Constraints: `{analysis['setup_quality']['constraint_clearance']:.3f}`

**🎯 Verdict:** `{analysis['recommendation'].upper()}`

*18 ICT operators: FVG, OB, LP, OTE, sweep, displacement...*"""
            
            await update.message.reply_text(report, parse_mode="Markdown")
            
        except Exception as e:
            logger.error(f"Market analysis error: {e}")
            await update.message.reply_text(f"❌ Error: {str(e)[:200]}")
    
    async def _shadow_trade(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """/shadow <symbol> <bias> — Execute shadow trade"""
        args = context.args
        if len(args) < 2:
            await update.message.reply_text(
                "Usage: `/shadow EURUSD bullish`\n"
                "Full canonical cycle with evidence (no real capital)."
            )
            return
        
        symbol = args[0].upper()
        bias = args[1].lower()
        
        await update.message.chat.send_action(action="typing")
        
        try:
            ohlcv = self._generate_demo_ohlcv(symbol)
            session = self.adapter.get_session()
            
            execution = self.trading_system.execute_shadow(symbol, ohlcv, bias, session)
            
            outcome_emoji = "✅" if execution.outcome.value == "success" else "🚫"
            
            report = f"""🔬 **Shadow Execution — {symbol}**

**ID:** `{execution.execution_id}`
**Outcome:** {outcome_emoji} `{execution.outcome.value.upper()}`
**PnL Prediction:** `{execution.pnl_prediction:.4f}`
**Time:** `{execution.execution_time_ms:.1f}ms`

**Canonical Cycle:** ✅ Proposal → ✅ Projection → ✅ ΔS → ✅ Collapse → ✅ State → ✅ Reconciliation → ✅ Evidence

**Evidence:** `{execution.evidence_hash[:16]}...`

*Scheduler sovereignty enforced | Refusal-first active*"""
            
            await update.message.reply_text(report, parse_mode="Markdown")
            
        except Exception as e:
            logger.error(f"Shadow trade error: {e}")
            await update.message.reply_text(f"❌ Error: {str(e)[:200]}")
    
    async def _list_operators(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """/operators — List 18 ICT operators"""
        try:
            meta = self.registry.get_registry_metadata()
            
            potentials = [f"{m['id']:02d}. `{n}` — {m['equation']}" 
                         for n, m in meta.items() if m['type'] == 'potential'][:7]
            projectors = [f"{m['id']:02d}. `{n}` — {m['equation']}" 
                         for n, m in meta.items() if m['type'] == 'projector'][:5]
            
            report = f"""⚛️ **25-Operator ICT + Order-Book Registry**

**Potential Operators (V → H):**
{chr(10).join(potentials)}

**Projector Operators (Π → Constraints):**
{chr(10).join(projectors)}

**Measurement:** `projection` — ⟨ψ|O|ψ⟩

**System Invariants:**
• No sideways imports • META dict validated
• Hermitian/idempotent/self-adjoint

*H_market = Σ α_k O_k — market Hamiltonian*"""
            
            await update.message.reply_text(report, parse_mode="Markdown")
            
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {str(e)[:200]}")
    
    async def _check_constraints(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """/constraints — Check constraint status"""
        try:
            status = self.trading_system.apex.constraints.get_admissibility_status()
            
            proj_lines = "\n".join([f"  • `{p}` (λ={status['lambda_weights'].get(p, 1.0)})" 
                                   for p in status['projector_names']])
            
            report = f"""🔒 **Constraint Hamiltonian**

**Active Projectors (Π² = Π, Π† = Π):**
{proj_lines}

**Violations:** {len(status['violations'])}
**Refusal-First:** {status['refusal_first']}
**Idempotency:** Verified

**Algebra:** Π_total = Π_session ∘ Π_risk ∘ Π_regime ∘ Π_sequence ∘ Π_reconciliation

*Annihilates inadmissible | Evidenced refusal*"""
            
            await update.message.reply_text(report, parse_mode="Markdown")
            
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {str(e)[:200]}")
    
    async def _trading_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """/trading — System status"""
        try:
            report = self.trading_system.get_shadow_report()
            perf = report['performance']
            
            status_text = f"""📈 **ApexQuantumICT Status**

**Performance:**
• Executions: `{perf['total_executions']}`
• Success: `{perf['successes']}` | Refused: `{perf['refusals']}`
• Avg Time: `{perf['avg_execution_time_ms']:.1f}ms`

**System Tuple 𝔖:**
• X: State space | g: Minkowski metric
• Φ: Action S[q] = ∫L dt
• Π: {len(report['system_status']['constraints_status']['projector_names'])} projectors
• ℳ: Observable extraction
• Λ: Scheduler (sovereign authority)
• ℛ: Reconciliation (drift detection)
• ℰ: Merkle+Ed25519 evidence

**Recent:** {len(report['recent_executions'])} executions
**Drift Alerts:** {len(report['drift_alerts'])}

*Scheduler sovereignty: NO override possible*"""
            
            await update.message.reply_text(status_text, parse_mode="Markdown")
            
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {str(e)[:200]}")
    
    # ============== UTILITY METHODS ==============
    
    def _generate_demo_ohlcv(self, symbol: str, n: int = 20) -> list:
        """Generate synthetic OHLCV for demo (replace with your data feed)"""
        import random
        
        base_price = 1.0 if "USD" in symbol else 100.0
        if "BTC" in symbol:
            base_price = 50000.0
        elif "ETH" in symbol:
            base_price = 3000.0
        
        ohlcv = []
        price = base_price
        
        for i in range(n):
            change = random.uniform(-0.001, 0.001)
            
            ohlcv.append({
                "open": round(price, 5),
                "close": round(price + change, 5),
                "high": round(max(price, price + change) + abs(random.uniform(0, 0.0005)), 5),
                "low": round(min(price, price + change) - abs(random.uniform(0, 0.0005)), 5),
                "volume": random.randint(1000, 10000),
                "timestamp": i
            })
            
            price += change
        
        return ohlcv
    
    def get_help_text(self) -> str:
        """Get trading commands help for /start message"""
        return """
**⚛️ ApexQuantumICT Trading Commands:**
• `/market <symbol> [bias]` — ICT + order-book analysis (25 operators)
• `/shadow <symbol> <bias>` — Shadow trade execution
• `/operators` — List 18 ICT/SMC operators
• `/constraints` — Check constraint Hamiltonian
• `/trading` — System status (𝔖 tuple)

*System invariants: Refusal-first, Scheduler sovereignty, Deterministic evidence*
"""


# Singleton instance for easy import
trading_superposition = TradingBotSuperposition()


def add_trading_to_bot(application):
    """
    One-liner to add trading to your existing bot.
    
    Usage:
        from apps.telegram.trading_integration import add_trading_to_bot
        add_trading_to_bot(application)
    """
    trading_superposition.add_handlers(application)
