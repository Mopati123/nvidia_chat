"""
ApexQuantumICT Trading Bot - Web Server Wrapper
Provides health check endpoint for deployment platforms
"""

import os
import threading
from flask import Flask, jsonify

# Import the bot
import telegram_bot_full as bot

app = Flask(__name__)

@app.route('/')
def health_check():
    """Health check endpoint for monitoring"""
    return jsonify({
        "status": "running",
        "bot": "ApexQuantumICT Trading Bot",
        "trading_enabled": bot.TRADING_AVAILABLE,
        "system": "𝔖 = (X, g, Φ, Π, ℳ, Λ, ℛ, ℰ)",
        "operators": 18,
        "version": "1.0.0"
    })

@app.route('/status')
def detailed_status():
    """Detailed system status"""
    if bot.TRADING_AVAILABLE and bot.trading_system:
        report = bot.trading_system.get_shadow_report()
        return jsonify({
            "status": "active",
            "executions": report['performance']['total_executions'],
            "scheduler": "sovereign",
            "refusal_first": True,
            "deterministic": True
        })
    return jsonify({"status": "ai_chat_only", "trading": "not_initialized"})

def run_bot():
    """Run the Telegram bot in a separate thread"""
    try:
        bot.main()
    except Exception as e:
        print(f"Bot error: {e}")

if __name__ == "__main__":
    # Start bot in background thread
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    
    # Start web server for health checks
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
