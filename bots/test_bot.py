import os # os ইমপোর্ট
import asyncio
import queue
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# ==========================================
# ⚙️ কনফিগারেশন (সিক্রেট থেকে নেওয়া)
# ==========================================
TOKEN = os.getenv("TEST_BOT_TOKEN")

if not TOKEN:
    print("⚠️ Warning: TEST_BOT_TOKEN not found in Secrets!")

bot_queue = queue.Queue()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("আমি টেস্ট বট! সিক্রেট টোকেন দিয়ে চলছি! 🕵️‍♂️")

async def bot_loop(application):
    print("🧪 Test Bot Started...")
    await application.initialize()
    await application.start()
    while True:
        try:
            update_data = bot_queue.get(timeout=1)
            if update_data:
                update = Update.de_json(update_data, application.bot)
                await application.process_update(update)
        except queue.Empty: continue
        except Exception as e: print(f"Test Bot Error: {e}")

def run_bot():
    if not TOKEN: return
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    loop.run_until_complete(bot_loop(app))
