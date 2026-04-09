from openai import OpenAI
import os
import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# NVIDIA API setup
api_key = os.environ.get("NVAPI_KEY")
if not api_key:
    raise ValueError("Set NVAPI_KEY environment variable with your NVIDIA API key")

client = OpenAI(
    base_url="https://integrate.api.nvidia.com/v1",
    api_key=api_key
)

# Telegram bot token from environment
bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
if not bot_token:
    raise ValueError("Set TELEGRAM_BOT_TOKEN environment variable")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 NVIDIA Falcon 3 Bot ready!\n\nSend me any message and I'll respond using tiiuae/falcon3-7b-instruct."
    )


async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_message = update.message.text
    
    # Show "typing" indicator
    await update.message.chat.send_action(action="typing")
    
    try:
        completion = client.chat.completions.create(
            model="tiiuae/falcon3-7b-instruct",
            messages=[{"content": user_message, "role": "user"}],
            temperature=0.2,
            top_p=0.7,
            max_tokens=1024,
            stream=False  # Non-streaming for simpler bot response
        )
        
        response = completion.choices[0].message.content
        await update.message.reply_text(response)
        
    except Exception as e:
        await update.message.reply_text(f"Error: {str(e)}")


def main():
    application = Application.builder().token(bot_token).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat))
    
    print("Bot is running... Press Ctrl+C to stop")
    application.run_polling()


if __name__ == "__main__":
    main()
