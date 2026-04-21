"""
telegram_handlers.py — Telegram bot commands for broker management

Commands:
    /brokers - List connected brokers and status
    /broker_add - Add new broker credentials (interactive)
    /broker_remove - Remove broker credentials
    /markets - List available markets across all brokers
    /price <symbol> - Get current price from all brokers
    /positions - Show open positions across all brokers
"""

import os
import logging
from typing import Dict, Optional, List
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes, ConversationHandler,
    CommandHandler, CallbackQueryHandler,
    MessageHandler, filters
)

logger = logging.getLogger(__name__)

# Conversation states for credential input
BROKER_TYPE, CREDENTIAL_NAME, CREDENTIAL_INPUT, CONFIRM = range(4)


class BrokerTelegramHandlers:
    """Telegram bot handlers for broker management"""
    
    def __init__(self):
        self.temp_credentials: Dict[int, Dict] = {}  # User ID -> pending credentials
    
    # ============================================================
    # /brokers - List all connected brokers
    # ============================================================
    async def cmd_brokers(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """List all brokers and their connection status"""
        from .broker_manager import get_broker_manager
        from .credentials import get_credential_manager
        
        manager = get_broker_manager()
        cred_manager = get_credential_manager()
        
        lines = ["📊 *Connected Brokers*", ""]
        
        if not manager.brokers:
            lines.append("No brokers configured.")
            lines.append("Use /broker_add to add a broker.")
        else:
            for name, connected in manager.connected.items():
                status = "🟢 Connected" if connected else "🔴 Disconnected"
                broker_type = name.split('_')[0].upper()
                lines.append(f"*{name}* ({broker_type})")
                lines.append(f"  Status: {status}")
                
                # Get account info if connected
                if connected and name in manager.brokers:
                    try:
                        broker = manager.brokers[name]
                        if hasattr(broker, 'get_account_info'):
                            info = broker.get_account_info()
                            if info:
                                balance = info.get('balance', 'N/A')
                                currency = info.get('currency', 'USD')
                                mode = '🧪 DEMO' if info.get('demo') or info.get('trade_mode') == 'demo' else '💰 LIVE'
                                lines.append(f"  Balance: {balance} {currency} {mode}")
                    except Exception as e:
                        logger.debug(f"Could not get account info: {e}")
                
                lines.append("")
        
        # List stored credentials not yet connected
        stored = cred_manager.list_stored_accounts()
        if stored:
            lines.append("📁 *Stored Credentials (not connected):*")
            for bt, name in stored:
                lines.append(f"  • {bt.upper()}: {name}")
        
        await update.message.reply_text(
            "\n".join(lines),
            parse_mode='Markdown'
        )
    
    # ============================================================
    # /broker_add - Interactive broker setup
    # ============================================================
    async def cmd_broker_add(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start interactive broker credential setup"""
        keyboard = [
            [InlineKeyboardButton("Deriv.com", callback_data='deriv')],
            [InlineKeyboardButton("MetaTrader 5", callback_data='mt5')],
            [InlineKeyboardButton("Cancel", callback_data='cancel')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "🏦 *Add New Broker*\n\nSelect broker type:",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
        return BROKER_TYPE
    
    async def broker_type_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle broker type selection"""
        query = update.callback_query
        await query.answer()
        
        broker_type = query.data
        if broker_type == 'cancel':
            await query.edit_message_text("❌ Cancelled.")
            return ConversationHandler.END
        
        user_id = update.effective_user.id
        self.temp_credentials[user_id] = {'type': broker_type}
        
        if broker_type == 'deriv':
            instructions = (
                "🔗 *Adding Deriv.com Account*\n\n"
                "Please enter your API token.\n\n"
                "_Get your token from:_\n"
                "app.deriv.com/account/api-token\n\n"
                "Enter a name for these credentials:"
            )
        else:  # mt5
            instructions = (
                "🔗 *Adding MetaTrader 5 Account*\n\n"
                "Please enter a name for these credentials\n"
                "(e.g., 'icmarkets', 'xm'):"
            )
        
        await query.edit_message_text(
            instructions,
            parse_mode='Markdown'
        )
        return CREDENTIAL_NAME
    
    async def credential_name_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle credential name input"""
        user_id = update.effective_user.id
        name = update.message.text.strip()
        
        self.temp_credentials[user_id]['name'] = name
        broker_type = self.temp_credentials[user_id]['type']
        
        if broker_type == 'deriv':
            await update.message.reply_text(
                "🔑 Now send your Deriv API token:\n\n"
                "_(It will be stored securely)_"
            )
        else:  # mt5
            await update.message.reply_text(
                "🔢 Send your MT5 Account ID (login number):"
            )
        
        return CREDENTIAL_INPUT
    
    async def credential_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle credential value input"""
        user_id = update.effective_user.id
        data = self.temp_credentials.get(user_id, {})
        broker_type = data.get('type')
        
        if broker_type == 'deriv':
            # First input is the token
            if 'token' not in data:
                data['token'] = update.message.text.strip()
                await update.message.reply_text(
                    "🧪 Is this a demo account? (Reply 'yes' or 'no')"
                )
                return CONFIRM
        
        elif broker_type == 'mt5':
            # Sequence: account -> password -> server -> demo?
            if 'account_id' not in data:
                data['account_id'] = update.message.text.strip()
                await update.message.reply_text("🔑 Send your MT5 password:")
                return CREDENTIAL_INPUT
            
            elif 'password' not in data:
                data['password'] = update.message.text.strip()
                await update.message.reply_text(
                    "🌐 Send your MT5 server name:\n"
                    "_(e.g., ICMarketsSC-Demo, MetaQuotes-Demo)_"
                )
                return CREDENTIAL_INPUT
            
            elif 'server' not in data:
                data['server'] = update.message.text.strip()
                await update.message.reply_text(
                    "🧪 Is this a demo account? (Reply 'yes' or 'no')"
                )
                return CONFIRM
        
        return CREDENTIAL_INPUT
    
    async def confirm_setup(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Confirm and save credentials"""
        user_id = update.effective_user.id
        data = self.temp_credentials.get(user_id, {})
        
        is_demo = update.message.text.strip().lower() in ['yes', 'y', 'true', 'demo']
        
        # Store credentials
        from .credentials import get_credential_manager
        manager = get_credential_manager()
        
        broker_type = data.get('type')
        name = data.get('name', 'default')
        
        try:
            if broker_type == 'deriv':
                success = manager.store_credential(
                    broker_type='deriv',
                    name=name,
                    credentials={'token': data.get('token')},
                    is_demo=is_demo
                )
            else:  # mt5
                success = manager.store_credential(
                    broker_type='mt5',
                    name=name,
                    account_id=data.get('account_id'),
                    credentials={
                        'password': data.get('password'),
                        'server': data.get('server')
                    },
                    is_demo=is_demo
                )
            
            if success:
                mode = "🧪 DEMO" if is_demo else "💰 LIVE"
                await update.message.reply_text(
                    f"✅ *Credentials Saved*\n\n"
                    f"Broker: {broker_type.upper()}\n"
                    f"Name: {name}\n"
                    f"Mode: {mode}\n\n"
                    f"Use /brokers to see status\n"
                    f"Use /markets to see available symbols",
                    parse_mode='Markdown'
                )
            else:
                await update.message.reply_text("❌ Failed to save credentials.")
        
        except Exception as e:
            logger.error(f"Credential save error: {e}")
            await update.message.reply_text(f"❌ Error: {str(e)}")
        
        finally:
            # Cleanup
            self.temp_credentials.pop(user_id, None)
        
        return ConversationHandler.END
    
    # ============================================================
    # /broker_remove - Remove broker credentials
    # ============================================================
    async def cmd_broker_remove(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Remove stored broker credentials"""
        from .credentials import get_credential_manager
        
        args = context.args
        if len(args) < 2:
            await update.message.reply_text(
                "Usage: `/broker_remove <broker_type> <name>`\n\n"
                "Example: `/broker_remove deriv demo`\n"
                "Example: `/broker_remove mt5 icmarkets`",
                parse_mode='Markdown'
            )
            return
        
        broker_type, name = args[0], args[1]
        
        manager = get_credential_manager()
        
        # Confirm
        keyboard = [
            [
                InlineKeyboardButton("Yes, Delete", callback_data=f'delete_{broker_type}_{name}'),
                InlineKeyboardButton("Cancel", callback_data='cancel_delete')
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"⚠️ *Delete Credentials?*\n\n"
            f"Broker: {broker_type.upper()}\n"
            f"Name: {name}\n\n"
            f"This cannot be undone!",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
    
    async def delete_confirm_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle delete confirmation"""
        query = update.callback_query
        await query.answer()
        
        data = query.data
        if data == 'cancel_delete':
            await query.edit_message_text("❌ Cancelled.")
            return
        
        if data.startswith('delete_'):
            parts = data.split('_', 2)
            if len(parts) == 3:
                broker_type, name = parts[1], parts[2]
                
                from .credentials import get_credential_manager
                manager = get_credential_manager()
                
                if manager.delete_credential(broker_type, name):
                    await query.edit_message_text(
                        f"✅ Deleted {broker_type.upper()} credentials '{name}'"
                    )
                else:
                    await query.edit_message_text("❌ Failed to delete credentials.")
    
    # ============================================================
    # /markets - List available markets
    # ============================================================
    async def cmd_markets(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """List available markets across all brokers"""
        from .broker_manager import get_broker_manager
        
        manager = get_broker_manager()
        available = manager.get_available_symbols()
        
        lines = ["📈 *Available Markets*", ""]
        
        if not available:
            lines.append("No brokers connected.")
            lines.append("Use /broker_add to add credentials.")
        else:
            for broker_name, symbols in available.items():
                lines.append(f"*{broker_name}* ({len(symbols)} symbols)")
                # Show first 10 symbols
                display_symbols = symbols[:10]
                lines.append(", ".join(display_symbols))
                if len(symbols) > 10:
                    lines.append(f"_... and {len(symbols) - 10} more_")
                lines.append("")
        
        lines.append("\n💡 *Common symbols:* EURUSD, GBPUSD, BTCUSD, XAUUSD")
        
        await update.message.reply_text(
            "\n".join(lines),
            parse_mode='Markdown'
        )
    
    # ============================================================
    # /price <symbol> - Get current price
    # ============================================================
    async def cmd_price(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Get current price for a symbol from all sources"""
        from .broker_manager import get_broker_manager
        
        args = context.args
        if not args:
            await update.message.reply_text(
                "Usage: `/price <symbol>`\n\n"
                "Examples:\n"
                "`/price EURUSD`\n"
                "`/price BTCUSD`",
                parse_mode='Markdown'
            )
            return
        
        symbol = args[0].upper()
        manager = get_broker_manager()
        
        # Get price comparison from all sources
        comparison = manager.compare_prices(symbol)
        
        if 'error' in comparison:
            await update.message.reply_text(f"❌ {comparison['error']}")
            return
        
        lines = [f"💵 *{symbol} Price*", ""]
        
        # Show prices from each source
        sources = comparison.get('sources', {})
        for source, data in sources.items():
            if 'mid' in data:
                lines.append(f"*{source}:* {data['mid']:.5f}")
                if 'spread' in data:
                    lines.append(f"  Spread: {data['spread']:.5f}")
            elif 'price' in data:
                lines.append(f"*{source}:* {data['price']:.5f}")
        
        # Show price spread across sources
        spread_pct = comparison.get('spread_pct', 0)
        if spread_pct > 0.01:  # > 0.01% difference
            lines.append(f"\n⚠️ Price variance: {spread_pct:.3f}%")
        
        lines.append(f"\n_Sources: {len(sources)}_")
        
        await update.message.reply_text(
            "\n".join(lines),
            parse_mode='Markdown'
        )
    
    # ============================================================
    # /positions - Show open positions
    # ============================================================
    async def cmd_positions(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show open positions across all brokers"""
        from .broker_manager import get_broker_manager
        
        manager = get_broker_manager()
        
        lines = ["📊 *Open Positions*", ""]
        has_positions = False
        
        for name, broker in manager.brokers.items():
            if not manager.connected.get(name, False):
                continue
            
            try:
                if hasattr(broker, 'get_positions'):
                    positions = broker.get_positions()
                    if positions:
                        has_positions = True
                        lines.append(f"*{name}* ({len(positions)} positions)")
                        
                        for pos in positions[:5]:  # Show first 5
                            profit = pos.profit if hasattr(pos, 'profit') else 0
                            emoji = "🟢" if profit >= 0 else "🔴"
                            
                            lines.append(
                                f"  {emoji} {pos.symbol} "
                                f"{'BUY' if pos.type == 0 else 'SELL'} "
                                f"{pos.volume} lots @ {pos.open_price:.5f} "
                                f"(P&L: {profit:+.2f})"
                            )
                        
                        if len(positions) > 5:
                            lines.append(f"  ... and {len(positions) - 5} more")
                        
                        lines.append("")
                
                elif hasattr(broker, 'get_active_contracts'):
                    # Deriv style
                    contracts = broker.get_active_contracts()
                    if contracts:
                        has_positions = True
                        lines.append(f"*{name}* ({len(contracts)} contracts)")
                        
                        for contract in contracts[:5]:
                            buy_price = contract.get('buy_price', 0)
                            current = contract.get('current_spot', buy_price)
                            pnl = current - buy_price if contract.get('contract_type') == 'CALL' else buy_price - current
                            emoji = "🟢" if pnl >= 0 else "🔴"
                            
                            lines.append(
                                f"  {emoji} {contract.get('underlying', 'N/A')} "
                                f"{contract.get('contract_type')} "
                                f"(P&L: {pnl:+.2f})"
                            )
                        
                        lines.append("")
            
            except Exception as e:
                logger.error(f"Error getting positions from {name}: {e}")
                lines.append(f"*{name}*: Error fetching positions")
        
        if not has_positions:
            lines.append("No open positions.")
        
        await update.message.reply_text(
            "\n".join(lines),
            parse_mode='Markdown'
        )


# Create singleton instance
broker_handlers = BrokerTelegramHandlers()


def get_broker_handlers() -> BrokerTelegramHandlers:
    """Get broker handlers instance"""
    return broker_handlers
