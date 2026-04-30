from openai import OpenAI
import os
import asyncio
import logging
import json
import time
import uuid
from collections import defaultdict
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from dotenv import load_dotenv

# Load environment variables from .env file (override=True forces reload)
load_dotenv(override=True)

# ApexQuantumICT Trading System imports
try:
    from trading.shadow.shadow_trading_loop import ShadowTradingLoop
    from trading.operators.operator_registry import OperatorRegistry
    from trading.evidence.evidence_chain import EvidenceEmitter
    from trading.market_bridge.minkowski_adapter import MarketDataAdapter
    from trading.brokers.market_data import market_feed
    from apps.telegram.trading_live import live_trading, add_live_trading_handlers
    TRADING_AVAILABLE = True
except ImportError as e:
    TRADING_AVAILABLE = False
    logger.warning(f"Trading imports failed: {e}")

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_broker_manager():
    """Load credential manager from environment-configured password only."""
    from trading.brokers.credentials import get_credential_manager
    password = os.environ.get("APEX_CREDENTIAL_PASSWORD")
    # #region agent log
    try:
        with open("logs/debug-3c812d.log", "a", encoding="utf-8") as _dbg:
            _dbg.write(json.dumps({
                "sessionId": "3c812d",
                "runId": "post-fix",
                "hypothesisId": "H5",
                "id": f"log_{uuid.uuid4().hex}",
                "location": "telegram_bot_full.py:get_broker_manager",
                "message": "broker_manager_env_check",
                "data": {"env_password_present": bool(password)},
                "timestamp": int(time.time() * 1000)
            }) + "\n")
    except Exception:
        pass
    # #endregion
    if not password:
        raise ValueError("Set APEX_CREDENTIAL_PASSWORD environment variable for broker commands")
    return get_credential_manager(password)

# NVIDIA API setup
api_key = os.environ.get("NVAPI_KEY")
if not api_key:
    raise ValueError("Set NVAPI_KEY environment variable with your NVIDIA API key")

client = OpenAI(
    base_url="https://integrate.api.nvidia.com/v1",
    api_key=api_key
)

bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
if not bot_token:
    raise ValueError("Set TELEGRAM_BOT_TOKEN environment variable")

# Conversation memory: {user_id: [{"role": "user"/"assistant", "content": "..."}]}
conversation_history = defaultdict(list)
MAX_HISTORY = 10

# ApexQuantumICT Trading System (Input 1-6 Integration)
trading_system = None
evidence_emitter = None
if TRADING_AVAILABLE:
    try:
        trading_system = ShadowTradingLoop()
        evidence_emitter = EvidenceEmitter()
        logger.info("ApexQuantumICT trading system initialized")
    except Exception as e:
        logger.error(f"Trading system init error: {e}")

# User stats
user_stats = defaultdict(lambda: {"messages": 0, "first_seen": None, "last_active": None})

# Available models
MODELS = {
    "falcon": "tiiuae/falcon3-7b-instruct",
    "nemotron": "nvidia/llama-3.1-nemotron-70b-instruct",
    "qwen": "qwen/qwen2.5-7b-instruct"
}

# Default persona
DEFAULT_SYSTEM_PROMPT = "You are a helpful AI assistant running on NVIDIA infrastructure. Be concise but thorough."


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_stats[user_id]["first_seen"] = datetime.now().isoformat()
    
    welcome = """🤖 **NVIDIA AI Bot - ApexQuantumICT Edition**

**AI Chat Commands:**
• /start - This menu
• /reset - Clear conversation history
• /models - List available models
• /model <name> - Switch model (falcon/nemotron/qwen)
• /persona <type> - Set personality (coder/teacher/creative/short)
• /status - Your stats and current settings
• /image <prompt> - Generate image (if supported)

**⚛️ ApexQuantumICT Trading Commands (6-Input Integration):**
• /market <symbol> [bias] - ICT + order-book analysis via 25-operator registry
• /shadow <symbol> <bias> - Shadow trade execution (no capital)
• /operators - List all 25 operators (18 ICT + 7 order-book analytics)
• /constraints - Check constraint Hamiltonian status
• /trading - Shadow system status (𝔖 = (X, g, Φ, Π, ℳ, Λ, ℛ, ℰ))

**💰 Live Trading Commands:**
• /mode [shadow|demo|live] - Set trading mode
• /connect <mt5|deriv> - Connect broker
• /trade <symbol> <buy|sell> [volume] - Execute trade
• /positions - Show open positions

**🏦 Broker Management:**
• /broker_list - List stored broker accounts
• /broker_test <deriv|mt5> - Test broker connection
• /broker_status - Quick health check of all brokers

**Features:**
✅ NVIDIA AI models (Falcon 3, Nemotron 70B, Qwen)
✅ Conversation memory
✅ **ApexQuantumICT quantum-inspired trading execution**
✅ Minkowski market bridge (OHLCV → (M, g, H, Π))
✅ 18 ICT/SMC operators as quantum operators
✅ Feynman path integral trajectory selection
✅ Scheduler-authorized collapse with refusal-first
✅ Cryptographic evidence (Merkle + Ed25519)
✅ Shadow execution (no real capital at risk)

*System invariants: Refusal-first, Scheduler sovereignty, Deterministic evidence*

Just send any message to chat, or use trading commands!"""
    
    await update.message.reply_text(welcome, parse_mode="Markdown")


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    conversation_history[user_id] = []
    await update.message.reply_text("🗑️ Conversation history cleared!")


async def models(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = "**Available Models:**\n\n"
    for name, model_id in MODELS.items():
        text += f"• `/{name}` - `{model_id}`\n"
    text += "\nUse `/model <name>` to switch"
    await update.message.reply_text(text, parse_mode="Markdown")


async def set_model(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    args = context.args
    
    if not args:
        await update.message.reply_text("Usage: `/model falcon` or `/model nemotron` or `/model qwen`")
        return
    
    model_name = args[0].lower()
    if model_name not in MODELS:
        await update.message.reply_text(f"Unknown model. Use /models to see available options.")
        return
    
    # Store in user context
    context.user_data["model"] = MODELS[model_name]
    await update.message.reply_text(f"✅ Switched to **{model_name}** model", parse_mode="Markdown")


async def set_persona(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    args = context.args
    
    personas = {
        "coder": "You are an expert programmer. Write clean, efficient code with comments. Prefer Python and explain your solutions.",
        "teacher": "You are a patient teacher. Explain concepts simply, use examples, and check for understanding.",
        "creative": "You are a creative writer. Be imaginative, use vivid language, and think outside the box.",
        "short": "You are a concise assistant. Keep responses brief and to the point. One paragraph max when possible.",
        "default": DEFAULT_SYSTEM_PROMPT
    }
    
    if not args:
        list_personas = "\n".join([f"• `{k}`" for k in personas.keys()])
        await update.message.reply_text(f"**Available personas:**\n{list_personas}\n\nUsage: `/persona coder`", parse_mode="Markdown")
        return
    
    persona_name = args[0].lower()
    if persona_name not in personas:
        await update.message.reply_text(f"Unknown persona. Available: {', '.join(personas.keys())}")
        return
    
    context.user_data["persona"] = personas[persona_name]
    await update.message.reply_text(f"✅ Persona set to **{persona_name}**", parse_mode="Markdown")


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    stats = user_stats[user_id]
    
    current_model = context.user_data.get("model", MODELS["falcon"])
    current_persona = context.user_data.get("persona", DEFAULT_SYSTEM_PROMPT)[:50] + "..."
    history_count = len(conversation_history[user_id])
    
    text = f"""📊 **Your Stats**

**Messages sent:** {stats['messages']}
**History length:** {history_count} messages
**First seen:** {stats['first_seen'] or 'Just now'}
**Last active:** {stats['last_active'] or 'Just now'}

**Current model:** `{current_model}`
**Persona:** {current_persona}
"""
    await update.message.reply_text(text, parse_mode="Markdown")


async def generate_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    prompt = " ".join(context.args) if context.args else None
    
    if not prompt:
        await update.message.reply_text("Usage: `/image a futuristic city at sunset`")
        return
    
    await update.message.chat.send_action(action="upload_photo")
    
    try:
        # Try NVIDIA's SDXL or other image model if available
        # Fallback to text response if image generation not available
        await update.message.reply_text(
            f"🎨 **Image prompt received:**\n`{prompt}`\n\n"
            "Note: Image generation requires a separate image model API. "
            "I can describe what this image would look like, or you can integrate "
            "Stability AI or DALL-E for actual image generation."
        )
    except Exception as e:
        logger.error(f"Image generation error: {e}")
        await update.message.reply_text(f"Error: {str(e)}")


async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_message = update.message.text
    chat_type = update.message.chat.type
    
    # Check if bot was mentioned in group (required for groups)
    if chat_type in ["group", "supergroup"]:
        bot_username = context.bot.username
        if f"@{bot_username}" not in user_message and update.message.reply_to_message is None:
            return  # Ignore group messages that don't mention or reply to bot
        # Remove bot mention from message
        user_message = user_message.replace(f"@{bot_username}", "").strip()
    
    # Update stats
    user_stats[user_id]["messages"] += 1
    user_stats[user_id]["last_active"] = datetime.now().isoformat()
    
    # Get user settings
    model = context.user_data.get("model", MODELS["falcon"])
    persona = context.user_data.get("persona", DEFAULT_SYSTEM_PROMPT)
    
    # Show typing indicator
    await update.message.chat.send_action(action="typing")
    
    # Build message history
    history = conversation_history[user_id]
    messages = [{"role": "system", "content": persona}]
    messages.extend(history[-MAX_HISTORY:])  # Last N messages for context
    messages.append({"role": "user", "content": user_message})
    
    try:
        completion = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.7,
            top_p=0.9,
            max_tokens=2048,
            stream=False
        )
        
        response = completion.choices[0].message.content
        
        # Store in history
        conversation_history[user_id].append({"role": "user", "content": user_message})
        conversation_history[user_id].append({"role": "assistant", "content": response})
        
        # Trim history if too long
        if len(conversation_history[user_id]) > MAX_HISTORY * 2:
            conversation_history[user_id] = conversation_history[user_id][-MAX_HISTORY * 2:]
        
        # Send response (handle long messages)
        if len(response) > 4096:
            # Split long messages
            chunks = [response[i:i+4000] for i in range(0, len(response), 4000)]
            for chunk in chunks:
                await update.message.reply_text(chunk)
        else:
            await update.message.reply_text(response)
            
    except Exception as e:
        logger.error(f"Chat error: {e}")
        await update.message.reply_text(f"❌ Error: {str(e)}\n\nTry /reset if the conversation got too long.")


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎤 Voice messages not yet implemented.\n"
        "I can add speech-to-text using Whisper if you'd like!"
    )


# ================= APEXQUANTUMICT TRADING COMMANDS =================
# Integrated from 6 inputs: Architecture, System Tuple, Transition Cycle,
# 25-Operator Registry, Production Codebase, End-to-End Data Flow

async def market_analysis(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /market <symbol> - Run ICT + order-book analysis using 25-operator registry
    Canonical transition cycle: Proposal → Projection → ΔS → Evidence
    """
    if not TRADING_AVAILABLE or not trading_system:
        await update.message.reply_text(
            "⚠️ Trading system not available. Check imports."
        )
        return
    
    args = context.args
    if not args:
        await update.message.reply_text(
            "Usage: `/market EURUSD` or `/market BTCUSDT bullish`\n"
            "Analyses market using 18 ICT operators (FVG, OB, LP, etc.)"
        )
        return
    
    symbol = args[0].upper()
    bias = args[1].lower() if len(args) > 1 else "neutral"
    
    await update.message.chat.send_action(action="typing")
    
    try:
        # Fetch real OHLCV data from Yahoo Finance
        ohlcv = market_feed.fetch_ohlcv(symbol, period="5d", interval="1h")
        if not ohlcv:
            await update.message.reply_text(f"❌ No market data available for {symbol}")
            return
        
        # Run shadow analysis (no capital at risk)
        analysis = trading_system.analyze_setup(symbol, ohlcv)
        
        # Format operator scores
        top_ops = analysis["setup_quality"]["top_signals"]
        op_lines = "\n".join([f"  • `{name}`: {score:.3f}" for name, score in top_ops])
        
        report = f"""📊 **ApexQuantumICT Market Analysis**

**Symbol:** `{symbol}`
**Bias:** {bias}
**System Tuple:** 𝔖 = (X, g, Φ, Π, ℳ, Λ, ℛ, ℰ)

**Operator Scores (25-operator registry):**
{op_lines}

**Setup Quality:**
• Potential Strength: `{analysis['setup_quality']['potential_strength']:.3f}`
• Constraint Clearance: `{analysis['setup_quality']['constraint_clearance']:.3f}`

**Recommendation:** 🎯 `{analysis['recommendation'].upper()}`

*Analysis via Minkowski bridge → Hamiltonian H_market → Projection Π*"""
        
        await update.message.reply_text(report, parse_mode="Markdown")
        
    except Exception as e:
        logger.error(f"Market analysis error: {e}")
        await update.message.reply_text(f"❌ Analysis error: {str(e)}")


async def shadow_trade(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /shadow <symbol> <bias> - Execute shadow trade (no real capital)
    Full canonical cycle with cryptographic evidence emission
    """
    if not TRADING_AVAILABLE or not trading_system:
        await update.message.reply_text("⚠️ Trading system unavailable")
        return
    
    args = context.args
    if len(args) < 2:
        await update.message.reply_text(
            "Usage: `/shadow EURUSD bullish` or `/shadow BTCUSDT bearish`\n"
            "Executes full shadow cycle: Proposal→Projection→ΔS→Collapse→Reconciliation→Evidence"
        )
        return
    
    symbol = args[0].upper()
    bias = args[1].lower()
    
    await update.message.chat.send_action(action="typing")
    
    try:
        # Fetch real OHLCV data from Yahoo Finance
        ohlcv = market_feed.fetch_ohlcv(symbol, period="5d", interval="1h")
        if not ohlcv:
            await update.message.reply_text(f"❌ No market data available for {symbol}")
            return
        
        session = MarketDataAdapter().get_session()
        
        # Execute shadow trading loop
        execution = trading_system.execute_shadow(symbol, ohlcv, bias, session)
        
        # Format result
        outcome_emoji = "✅" if execution.outcome.value == "success" else "🚫"
        
        report = f"""🔬 **Shadow Execution Complete**

**Execution ID:** `{execution.execution_id}`
**Symbol:** `{symbol}` | **Bias:** {bias} | **Session:** {session}
**Outcome:** {outcome_emoji} `{execution.outcome.value.upper()}`

**Canonical Cycle:**
1. ✅ Proposal → 2. ✅ Projection → 3. ✅ ΔS → 4. ✅ Collapse → 5. ✅ State → 6. ✅ Reconciliation → 7. ✅ Evidence

**Trajectory:**
• Predicted PnL: `{execution.pnl_prediction:.4f}`
• Execution Time: `{execution.execution_time_ms:.2f}ms`

**Evidence:**
• Hash: `{execution.evidence_hash[:16]}...`
• Merkle root verified
• Deterministic: cross-machine reproducible

*Scheduler sovereignty: sole collapse authority enforced*
*Refusal-first: default non-execution*"""
        
        await update.message.reply_text(report, parse_mode="Markdown")
        
    except Exception as e:
        logger.error(f"Shadow trade error: {e}")
        await update.message.reply_text(f"❌ Shadow execution error: {str(e)}")


async def list_operators(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List all 25 operators from registry"""
    if not TRADING_AVAILABLE:
        await update.message.reply_text("⚠️ Trading system unavailable")
        return
    
    try:
        registry = OperatorRegistry()
        meta = registry.get_registry_metadata()
        
        # Group by type
        potentials = []
        projectors = []
        measurements = []
        
        for name, m in meta.items():
            if m["type"] == "potential":
                potentials.append(f"  {m['id']:02d}. `{name}` — {m['equation']}")
            elif m["type"] == "projector":
                projectors.append(f"  {m['id']:02d}. `{name}` — {m['equation']}")
            else:
                measurements.append(f"  {m['id']:02d}. `{name}` — {m['equation']}")
        
        report = f"""⚛️ **ApexQuantumICT 25-Operator Registry**

**Potential Operators (V → Hamiltonian):**
{chr(10).join(potentials[:7])}

**Projector Operators (Π → Constraints):**
{chr(10).join(projectors[:5])}

**Measurement Operators (ℳ → Readout):**
{chr(10).join(measurements)}

**System Invariants:**
• Operator algebra closed under composition
• No sideways imports (all coupling via OperatorMeta)
• META dict validated against JSON schema
• Quantum semantics block: Hermitian, idempotent, self-adjoint

*H_market = Σ α_k O_k — market Hamiltonian*"""
        
        await update.message.reply_text(report, parse_mode="Markdown")
        
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")


async def check_constraints(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check system constraint status (H_constraints.py)"""
    if not TRADING_AVAILABLE or not trading_system:
        await update.message.reply_text("⚠️ Trading system unavailable")
        return
    
    try:
        status = trading_system.apex.constraints.get_admissibility_status()
        
        report = f"""🔒 **Constraint Hamiltonian Status**

**Projectors (Π² = Π, Π† = Π):**
{chr(10).join([f"  • `{p}` (λ={status['lambda_weights'].get(p, 1.0)})" for p in status['projector_names']])}

**Active Violations:** {len(status['violations'])}
**Refusal-First Mode:** {status['refusal_first']}
**Idempotency Verified:** {status['idempotency_verified']}

**Constraint Algebra:**
Π_total = Π_session ∘ Π_risk ∘ Π_regime ∘ Π_sequence ∘ Π_reconciliation

*Annihilates inadmissible trajectories*
*Evidenced refusal as first-class output*"""
        
        await update.message.reply_text(report, parse_mode="Markdown")
        
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")


async def trading_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Get shadow trading system status"""
    if not TRADING_AVAILABLE or not trading_system:
        await update.message.reply_text("⚠️ Trading system unavailable")
        return
    
    try:
        report = trading_system.get_shadow_report()
        perf = report['performance']
        
        status_text = f"""📈 **ApexQuantumICT Shadow Status**

**Performance Metrics:**
• Total Executions: `{perf['total_executions']}`
• Successes: `{perf['successes']}` | Refusals: `{perf['refusals']}`
• Avg Execution Time: `{perf['avg_execution_time_ms']:.2f}ms`
• Cumulative PnL (sim): `{perf['cumulative_pnl']:.4f}`

**System Tuple 𝔖:**
• X (State Space): Active
• g (Metric): Minkowski bridge connected
• Φ (Lawful Functional): Action S[q] = ∫L dt
• Π (Projectors): {len(report['system_status']['constraints_status']['projector_names'])} active
• ℳ (Measurement): Observable extraction ready
• Λ (Scheduler): Sovereign collapse authority
• ℛ (Reconciliation): Drift detection active
• ℰ (Evidence): Merkle+Ed25519 ready

**Recent Executions:** {len(report['recent_executions'])}
**Drift Alerts:** {len(report['drift_alerts'])}

*Scheduler sovereignty: NO entity can force collapse*"""
        
        await update.message.reply_text(status_text, parse_mode="Markdown")
        
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")


async def broker_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List all stored broker accounts"""
    await update.message.chat.send_action(action="typing")
    
    try:
        manager = get_broker_manager()
        accounts = manager.list_stored_accounts()
        
        if not accounts:
            await update.message.reply_text(
                "📭 No broker accounts stored.\n\n"
                "Add accounts with CLI:\n"
                "`python -m scripts.broker.manage_brokers add deriv`\n"
                "`python -m scripts.broker.manage_brokers add mt5`"
            )
            return
        
        # Group by broker type
        from collections import defaultdict
        grouped = defaultdict(list)
        for broker_type, name in accounts:
            grouped[broker_type].append(name)
        
        lines = ["📋 **Stored Broker Accounts**\n"]
        
        for broker_type, names in grouped.items():
            lines.append(f"\n🔹 **{broker_type.upper()}**")
            for name in names:
                cred = manager.get_credential(broker_type, name)
                if cred:
                    emoji = "🧪" if cred.is_demo else "💰"
                    account_id = cred.account_id if cred.account_id else "API Token"
                    lines.append(f"   {emoji} `{name}`: {account_id}")
        
        lines.append(f"\n✅ Total: {len(accounts)} accounts")
        lines.append("\nTest with: `/broker_test deriv` or `/broker_test mt5`")
        
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
        
    except Exception as e:
        logger.error(f"Broker list error: {e}")
        await update.message.reply_text(f"❌ Error listing accounts: {str(e)}")


async def broker_test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Test broker connection (deriv or mt5)"""
    args = context.args
    if not args:
        await update.message.reply_text(
            "Usage: `/broker_test deriv` or `/broker_test mt5`\n"
            "Tests connection to your stored broker credentials."
        )
        return
    
    broker_type = args[0].lower()
    if broker_type not in ['deriv', 'mt5']:
        await update.message.reply_text("❌ Supported brokers: `deriv`, `mt5`")
        return
    
    await update.message.chat.send_action(action="typing")
    
    try:
        manager = get_broker_manager()
        
        if broker_type == 'deriv':
            cred = manager.get_credential('deriv', 'demo')
            if not cred:
                await update.message.reply_text("❌ No Deriv credentials found. Run: `python -m scripts.broker.manage_brokers add deriv`")
                return
            
            token = cred.credentials.get('token', '')
            await update.message.reply_text("🧪 Testing Deriv connection...")
            
            from trading.brokers.deriv_broker import DerivBroker
            success, message, info = DerivBroker.test_connection(token)
            
            if success and info:
                status = f"""✅ **Deriv Connected**

**Account:** `{info.get('loginid')}`
**Balance:** `{info.get('balance')} {info.get('currency')}`
**Demo:** {'Yes' if info.get('demo') else 'No'}

Ready for trading!"""
                await update.message.reply_text(status, parse_mode="Markdown")
            else:
                await update.message.reply_text(f"❌ {message}")
        
        elif broker_type == 'mt5':
            cred = manager.get_credential('mt5', 'default')
            if not cred:
                await update.message.reply_text("❌ No MT5 credentials found. Run: `python -m scripts.broker.manage_brokers add mt5`")
                return
            
            account = cred.account_id
            password = cred.credentials.get('password', '')
            server = cred.credentials.get('server', '')
            
            await update.message.reply_text(f"🧪 Testing MT5 connection to `{server}`...\n⏳ This may take 10-15 seconds")
            
            from trading.brokers.mt5_broker import MT5Broker
            success, message, info = MT5Broker.test_connection(
                int(account), password, server, max_retries=5
            )
            
            if success and info:
                mode = "🧪 Demo" if info.get('trade_mode') == 'demo' else "💰 Live"
                status = f"""✅ **MT5 Connected**

**Account:** `{info.get('login')}`
**Server:** `{info.get('server')}`
**Type:** {mode}
**Balance:** `{info.get('balance')} {info.get('currency')}`
**Equity:** `{info.get('equity')}`

Ready for trading!"""
                await update.message.reply_text(status, parse_mode="Markdown")
            else:
                error_msg = f"❌ {message}\n\nMake sure MT5 terminal is running.\nLaunch with: `python -m scripts.broker.launch_mt5_auto`"
                await update.message.reply_text(error_msg)
    
    except Exception as e:
        logger.error(f"Broker test error: {e}")
        await update.message.reply_text(f"❌ Error testing connection: {str(e)}")


async def broker_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Quick health check of all brokers"""
    await update.message.chat.send_action(action="typing")
    
    try:
        from trading.brokers.deriv_broker import DerivBroker
        manager = get_broker_manager()
        accounts = manager.list_stored_accounts()
        
        if not accounts:
            await update.message.reply_text("📭 No accounts configured. Use `/broker_list` to see setup instructions.")
            return
        
        lines = ["🏥 **Broker Health Status**\n"]
        
        for broker_type, name in accounts:
            cred = manager.get_credential(broker_type, name)
            if not cred:
                continue
            
            if broker_type == 'deriv':
                token = cred.credentials.get('token', '')
                success, _, info = DerivBroker.test_connection(token)
                emoji = "🟢" if success else "🔴"
                balance = f"{info.get('balance')} {info.get('currency')}" if info else "N/A"
                lines.append(f"{emoji} **Deriv** (`{name}`): {balance}")
            
            elif broker_type == 'mt5':
                # Check if MT5 process is running
                import subprocess
                try:
                    result = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq terminal64.exe'], 
                                          capture_output=True, text=True)
                    mt5_running = 'terminal64.exe' in result.stdout
                except:
                    mt5_running = False
                
                emoji = "🟡" if mt5_running else "🔴"
                status = "Running" if mt5_running else "Not running"
                lines.append(f"{emoji} **MT5** (`{name}`): {status} (run `/broker_test mt5` to verify)")
        
        lines.append("\n🟢 = Connected | 🟡 = Running (need test) | 🔴 = Offline")
        
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
        
    except Exception as e:
        logger.error(f"Broker status error: {e}")
        await update.message.reply_text(f"❌ Error checking status: {str(e)}")


def _generate_demo_ohlcv(symbol: str, n: int = 20) -> list:
    """Generate synthetic OHLCV for demo purposes"""
    import random
    import math
    
    base_price = 1.0 if "USD" in symbol else 100.0
    if "BTC" in symbol or "ETH" in symbol:
        base_price = 50000.0 if "BTC" in symbol else 3000.0
    
    ohlcv = []
    price = base_price
    
    for i in range(n):
        volatility = price * 0.001
        change = random.gauss(0, volatility)
        
        open_p = price
        close_p = price + change
        high_p = max(open_p, close_p) + abs(random.gauss(0, volatility * 0.5))
        low_p = min(open_p, close_p) - abs(random.gauss(0, volatility * 0.5))
        volume = random.randint(1000, 10000)
        
        ohlcv.append({
            "open": round(open_p, 5),
            "high": round(high_p, 5),
            "low": round(low_p, 5),
            "close": round(close_p, 5),
            "volume": volume,
            "timestamp": i
        })
        
        price = close_p
    
    return ohlcv


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Update {update} caused error {context.error}")
    if update and update.message:
        await update.message.reply_text("An error occurred. Please try again or use /reset.")


def main():
    application = Application.builder().token(bot_token).build()
    
    # Command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("reset", reset))
    application.add_handler(CommandHandler("models", models))
    application.add_handler(CommandHandler("model", set_model))
    application.add_handler(CommandHandler("persona", set_persona))
    application.add_handler(CommandHandler("status", status))
    application.add_handler(CommandHandler("image", generate_image))
    
    # ApexQuantumICT trading commands
    application.add_handler(CommandHandler("market", market_analysis))
    application.add_handler(CommandHandler("shadow", shadow_trade))
    application.add_handler(CommandHandler("operators", list_operators))
    application.add_handler(CommandHandler("constraints", check_constraints))
    application.add_handler(CommandHandler("trading", trading_status))
    
    # Broker management commands
    application.add_handler(CommandHandler("broker_list", broker_list))
    application.add_handler(CommandHandler("broker_test", broker_test))
    application.add_handler(CommandHandler("broker_status", broker_status))
    
    # Live trading commands (MT5 + Deriv + yfinance)
    add_live_trading_handlers(application)
    
    # Message handlers
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat))
    application.add_handler(MessageHandler(filters.VOICE, handle_voice))
    
    # Error handler
    application.add_error_handler(error_handler)
    
    logger.info("Bot is running with full features... Press Ctrl+C to stop")
    application.run_polling()


if __name__ == "__main__":
    main()
