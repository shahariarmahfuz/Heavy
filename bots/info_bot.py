import os
import asyncio
import queue
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ==========================================
# ⚙️ কনফিগারেশন (সিক্রেট থেকে নেওয়া)
# ==========================================
TOKEN = os.getenv("INFO_BOT_TOKEN")

if not TOKEN:
    print("⚠️ Warning: INFO_BOT_TOKEN not found in Secrets!")

bot_queue = queue.Queue()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(f"হ্যালো {user.first_name}! আমি ইনফো বট।")

async def info_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(f"আপনার আইডি: `{user.id}`", parse_mode="Markdown")

async def bot_loop(application):
    print("ℹ️ Info Bot Started...")
    await application.initialize()
    await application.start()
    while True:
        try:
            update_data = bot_queue.get(timeout=1)
            if update_data:
                update = Update.de_json(update_data, application.bot)
                await application.process_update(update)
        except queue.Empty: continue
        except Exception as e: print(f"Info Bot Error: {e}")

def run_bot():
    if not TOKEN: return
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("info", info_command))
    loop.run_until_complete(bot_loop(app))

