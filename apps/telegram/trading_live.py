"""
trading_live.py — Live trading with real market data and broker integration

Demo and Live account support for MT5 and Deriv
"""

import os
import logging
from typing import Optional, Dict, Literal
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler

from trading.brokers.market_data import market_feed, MarketDataFeed
from trading.brokers.mt5_broker import mt5_broker, MT5Broker, MT5Order
from trading.brokers.deriv_broker import deriv_broker, DerivBroker, DerivOrder
from trading.shadow.shadow_trading_loop import ShadowTradingLoop

logger = logging.getLogger(__name__)


class LiveTradingSystem:
    """
    Complete live trading system with:
    - Real market data (yfinance)
    - MT5 integration (forex, stocks)
    - Deriv integration (synthetics, options)
    - Demo account testing
    - Risk management
    """
    
    def __init__(self):
        self.data_feed = MarketDataFeed()
        self.mt5 = MT5Broker()
        self.deriv = DerivBroker()
        self.shadow = ShadowTradingLoop()
        
        # Mode: demo or live
        self.mode: Literal["shadow", "demo", "live"] = "shadow"
        self.active_broker: Optional[str] = None
        
        # Risk limits
        self.max_daily_loss = float(os.getenv("MAX_DAILY_LOSS", 100))
        self.max_position_size = float(os.getenv("MAX_POSITION_SIZE", 0.1))
        self.daily_pnl = 0.0
        
    def set_mode(self, mode: Literal["shadow", "demo", "live"]) -> bool:
        """
        Set trading mode:
        - shadow: Simulation only (no real capital)
        - demo: Practice account (fake money)
        - live: Real account (real money)
        """
        if mode not in ["shadow", "demo", "live"]:
            return False
        
        self.mode = mode
        logger.info(f"Trading mode set to: {mode}")
        return True
    
    def connect_broker(self, broker: str, **kwargs) -> bool:
        """
        Connect to broker:
        - 'mt5': MetaTrader 5 (requires running terminal)
        - 'deriv': Deriv.com (requires API token)
        """
        if broker == "mt5":
            # Check if MT5 is available (Windows only typically)
            try:
                import MetaTrader5
                account = kwargs.get('account')
                password = kwargs.get('password')
                server = kwargs.get('server')
                
                self.mt5 = MT5Broker(account, password, server)
                if self.mt5.connect():
                    # Verify demo account if in demo mode
                    if self.mode == "demo" and not self.mt5.is_demo():
                        logger.warning("MT5 is not a demo account! Switching to shadow.")
                        self.mode = "shadow"
                        return False
                    
                    self.active_broker = "mt5"
                    info = self.mt5.get_account_info()
                    logger.info(f"MT5 connected: {info}")
                    return True
                return False
            except ImportError:
                logger.error("MetaTrader5 not installed (Windows only)")
                return False
                
        elif broker == "deriv":
            api_token = kwargs.get('api_token') or os.getenv("DERIV_API_TOKEN")
            if not api_token:
                logger.error("No Deriv API token provided")
                return False
            
            self.deriv = DerivBroker(api_token)
            if self.deriv.connect():
                if self.deriv.authorize(api_token):
                    # Check if demo
                    info = self.deriv.get_account_info()
                    if info and info.get('demo'):
                        logger.info("Connected to Deriv DEMO account")
                    else:
                        if self.mode == "demo":
                            logger.warning("Not a Deriv demo account! Switching to shadow.")
                            self.mode = "shadow"
                            return False
                        logger.info("Connected to Deriv LIVE account")
                    
                    self.active_broker = "deriv"
                    return True
            return False
        
        return False
    
    def execute_trade(self, 
                     symbol: str, 
                     direction: Literal["buy", "sell"],
                     volume: float = 0.01,
                     sl: Optional[float] = None,
                     tp: Optional[float] = None) -> Optional[Dict]:
        """
        Execute trade through active broker
        
        Args:
            symbol: Trading pair (EURUSD, BTCUSD, etc.)
            direction: buy or sell
            volume: Position size (lots for MT5, stake for Deriv)
            sl: Stop loss price
            tp: Take profit price
        
        Returns:
            Trade result dict or None if failed
        """
        # Risk checks
        if self.daily_pnl <= -self.max_daily_loss:
            logger.warning("Max daily loss reached - trade blocked")
            return {"error": "Max daily loss reached", "blocked": True}
        
        if volume > self.max_position_size:
            logger.warning(f"Position size {volume} exceeds max {self.max_position_size}")
            return {"error": "Position size too large", "blocked": True}
        
        # Shadow mode: simulate only
        if self.mode == "shadow" or not self.active_broker:
            return self._execute_shadow_trade(symbol, direction, volume)
        
        # Real trading via broker
        if self.active_broker == "mt5":
            return self._execute_mt5_trade(symbol, direction, volume, sl, tp)
        
        elif self.active_broker == "deriv":
            return self._execute_deriv_trade(symbol, direction, volume)
        
        return None
    
    def _execute_shadow_trade(self, symbol, direction, volume) -> Dict:
        """Execute shadow trade (simulation)"""
        ohlcv = self.data_feed.fetch_ohlcv(symbol, period="1d", interval="1h")
        if not ohlcv:
            return {"error": "No market data"}
        
        execution = self.shadow.execute_shadow(
            symbol, ohlcv, direction, "auto"
        )
        
        return {
            "mode": "shadow",
            "symbol": symbol,
            "direction": direction,
            "volume": volume,
            "outcome": execution.outcome.value,
            "pnl_prediction": execution.pnl_prediction,
            "evidence_hash": execution.evidence_hash,
            "execution_time_ms": execution.execution_time_ms
        }
    
    def _execute_mt5_trade(self, symbol, direction, volume, sl, tp) -> Optional[Dict]:
        """Execute via MT5"""
        order = MT5Order(
            symbol=symbol,
            order_type=direction,
            volume=volume,
            sl=sl,
            tp=tp,
            comment="ApexQuantumICT"
        )
        
        result = self.mt5.place_order(order)
        if result:
            # Track PnL for risk management
            self.daily_pnl += result.get('profit', 0)
        
        return result
    
    def _execute_deriv_trade(self, symbol, direction, stake) -> Optional[Dict]:
        """Execute via Deriv"""
        # Normalize symbol for Deriv
        if not symbol.startswith("frx") and not symbol.startswith("R_") and not symbol.startswith("cry"):
            if symbol == "BTCUSD":
                symbol = "cryBTCUSD"
            elif symbol == "ETHUSD":
                symbol = "cryETHUSD"
            else:
                symbol = f"frx{symbol}"
        
        # Determine contract type
        contract_type = "CALL" if direction == "buy" else "PUT"
        
        order = DerivOrder(
            symbol=symbol,
            contract_type=contract_type,
            amount=stake,
            duration=5,  # 5 minutes
            duration_unit="m"
        )
        
        result = self.deriv.place_contract(order)
        if result:
            # Track (simplified)
            pass
        
        return result
    
    def get_account_info(self) -> Optional[Dict]:
        """Get account information from active broker"""
        if self.active_broker == "mt5":
            return self.mt5.get_account_info()
        elif self.active_broker == "deriv":
            return self.deriv.get_account_info()
        return {"mode": self.mode, "broker": "none"}
    
    def get_positions(self) -> list:
        """Get open positions"""
        if self.active_broker == "mt5":
            positions = self.mt5.get_positions()
            return [
                {
                    "ticket": p.ticket,
                    "symbol": p.symbol,
                    "type": "buy" if p.type == 0 else "sell",
                    "volume": p.volume,
                    "profit": p.profit,
                    "open_time": p.open_time.isoformat()
                }
                for p in positions
            ]
        elif self.active_broker == "deriv":
            return self.deriv.get_active_contracts()
        return []
    
    def close_position(self, identifier) -> bool:
        """Close position by ID"""
        if self.active_broker == "mt5":
            return self.mt5.close_position(identifier)
        elif self.active_broker == "deriv":
            # Get current price
            price = self.deriv.get_current_price(identifier)
            return self.deriv.sell_contract(identifier, price or 0)
        return False


# Singleton
live_trading = LiveTradingSystem()


# ============== TELEGRAM COMMAND HANDLERS ==============

async def trade_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /trade <symbol> <buy|sell> [volume] — Execute live trade
    
    Examples:
    /trade EURUSD buy 0.01
    /trade BTCUSD sell 50
    """
    args = context.args
    if len(args) < 2:
        await update.message.reply_text(
            "Usage: `/trade EURUSD buy [volume]`\n"
            "Modes: shadow (default) | demo | live\n"
            "Brokers: MT5 | Deriv\n"
            "Use `/mode` to check/set mode"
        )
        return
    
    symbol = args[0].upper()
    direction = args[1].lower()
    volume = float(args[2]) if len(args) > 2 else 0.01
    
    await update.message.chat.send_action(action="typing")
    
    try:
        result = live_trading.execute_trade(symbol, direction, volume)
        
        if result is None:
            await update.message.reply_text("❌ Trade failed (check logs)")
            return
        
        if result.get("blocked"):
            await update.message.reply_text(f"🚫 Trade blocked: {result.get('error')}")
            return
        
        # Format response
        mode = result.get("mode", live_trading.mode)
        
        if mode == "shadow":
            text = f"""🔬 **Shadow Trade Executed**

**Symbol:** `{symbol}` | **Direction:** {direction}
**Volume:** `{volume}`

**Result:**
• Outcome: {result.get('outcome', 'unknown')}
• PnL Prediction: `{result.get('pnl_prediction', 0):.4f}`
• Evidence: `{result.get('evidence_hash', '')[:16]}...`

*No real capital at risk*"""
        else:
            text = f"""✅ **Live Trade Executed ({mode.upper()})**

**Symbol:** `{symbol}` | **Direction:** {direction}
**Volume:** `{volume}`

**Order:**
• Ticket: `{result.get('ticket', result.get('contract_id', 'N/A'))}`
• Price: `{result.get('price', result.get('buy_price', 'N/A'))}`

*Real trade executed - monitor with /positions*"""
        
        await update.message.reply_text(text, parse_mode="Markdown")
        
    except Exception as e:
        logger.error(f"Trade error: {e}")
        await update.message.reply_text(f"❌ Error: {str(e)[:200]}")


async def mode_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /mode [shadow|demo|live] — Check or set trading mode
    
    shadow: Simulation only
    demo: Practice account (fake money)
    live: Real account (real money)
    """
    args = context.args
    
    if args:
        new_mode = args[0].lower()
        if live_trading.set_mode(new_mode):
            await update.message.reply_text(
                f"✅ Trading mode set to: **{new_mode.upper()}**\n\n"
                f"Use `/connect` to link broker account"
            )
        else:
            await update.message.reply_text(
                "❌ Invalid mode. Use: `shadow`, `demo`, or `live`"
            )
        return
    
    # Show current mode
    info = live_trading.get_account_info() or {}
    
    text = f"""⚙️ **Trading Mode Settings**

**Current Mode:** `{live_trading.mode.upper()}`
**Active Broker:** `{live_trading.active_broker or 'none'}`

**Risk Limits:**
• Max Daily Loss: `${live_trading.max_daily_loss}`
• Max Position: `{live_trading.max_position_size}` lots
• Daily PnL: `${live_trading.daily_pnl:.2f}`

**Account Info:**
```
{info}
```

**Commands:**
• `/mode shadow` — Simulation only
• `/mode demo` — Practice account
• `/mode live` — Real money ⚠️
• `/connect mt5` or `/connect deriv`"""
    
    await update.message.reply_text(text, parse_mode="Markdown")


async def connect_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /connect <broker> — Connect to trading broker
    
    /connect mt5
    /connect deriv
    """
    args = context.args
    if not args:
        await update.message.reply_text(
            "Usage: `/connect mt5` or `/connect deriv`\n\n"
            "**MT5:** Requires running MT5 terminal\n"
            "**Deriv:** Requires DERIV_API_TOKEN env variable"
        )
        return
    
    broker = args[0].lower()
    await update.message.chat.send_action(action="typing")
    
    try:
        if broker == "mt5":
            # Try to connect (will use saved credentials or prompt)
            if live_trading.connect_broker("mt5"):
                info = live_trading.get_account_info()
                await update.message.reply_text(
                    f"✅ **MT5 Connected**\n\n"
                    f"Account: `{info.get('login', 'N/A')}`\n"
                    f"Server: `{info.get('server', 'N/A')}`\n"
                    f"Balance: `{info.get('balance', 0)} {info.get('currency', '')}`\n"
                    f"Mode: `{info.get('trade_mode', 'unknown')}`\n\n"
                    f"Ready to trade with `/trade`"
                )
            else:
                await update.message.reply_text(
                    "❌ **MT5 Connection Failed**\n\n"
                    "Requirements:\n"
                    "• MT5 terminal running\n"
                    "• Windows OS (or Wine on Mac/Linux)\n"
                    "• `pip install MetaTrader5`"
                )
                
        elif broker == "deriv":
            token = os.getenv("DERIV_API_TOKEN")
            if not token:
                await update.message.reply_text(
                    "❌ **No DERIV_API_TOKEN found**\n\n"
                    "1. Get token: https://app.deriv.com/account/api-token\n"
                    "2. Set env: `export DERIV_API_TOKEN=your_token`"
                )
                return
            
            if live_trading.connect_broker("deriv", api_token=token):
                info = live_trading.get_account_info()
                demo_status = "✅ DEMO" if info.get('demo') else "⚠️ LIVE"
                await update.message.reply_text(
                    f"✅ **Deriv Connected**\n\n"
                    f"Account: `{info.get('loginid', 'N/A')}`\n"
                    f"Balance: `{info.get('balance', 0)} {info.get('currency', '')}`\n"
                    f"Mode: {demo_status}\n\n"
                    f"Ready to trade with `/trade`"
                )
            else:
                await update.message.reply_text("❌ Deriv connection failed")
        else:
            await update.message.reply_text("❌ Unknown broker. Use: mt5 or deriv")
            
    except Exception as e:
        logger.error(f"Connect error: {e}")
        await update.message.reply_text(f"❌ Connection error: {str(e)[:200]}")


async def positions_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/positions — Show open positions"""
    positions = live_trading.get_positions()
    
    if not positions:
        await update.message.reply_text("📭 No open positions")
        return
    
    lines = [f"**📊 Open Positions ({len(positions)})**\n"]
    
    for p in positions[:10]:  # Limit to 10
        symbol = p.get('symbol', p.get('underlying', 'N/A'))
        ticket = p.get('ticket', p.get('contract_id', 'N/A'))
        ptype = p.get('type', p.get('contract_type', 'N/A'))
        profit = p.get('profit', p.get('profit_loss', 0))
        volume = p.get('volume', p.get('buy_price', 0))
        
        lines.append(
            f"• `{symbol}` {ptype} | "
            f"Vol: {volume} | "
            f"PnL: `{profit:.2f}` | "
            f"ID: `{ticket}`"
        )
    
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


def add_live_trading_handlers(application):
    """Add live trading commands to bot"""
    handlers = [
        CommandHandler("trade", trade_command),
        CommandHandler("mode", mode_command),
        CommandHandler("connect", connect_command),
        CommandHandler("positions", positions_command),
    ]
    
    for handler in handlers:
        application.add_handler(handler)
    
    logger.info("✅ Live trading handlers added")
