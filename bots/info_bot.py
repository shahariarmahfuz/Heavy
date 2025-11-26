import os
import asyncio
import queue
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ==========================================
# ⚙️ কনফিগারেশন
# ==========================================
TOKEN = os.getenv("INFO_BOT_TOKEN")

# ==========================================
# 🛠️ কমান্ড হ্যান্ডলারস
# ==========================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(
        f"হ্যালো {user.first_name}! 👋\nআমি ইনফো বট। আলাদা প্রসেস থেকে চলছি।"
    )

async def info_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    
    info_text = (
        f"👤 **আপনার তথ্য:**\n"
        f"🆔 ID: `{user.id}`\n"
        f"📛 Name: {user.full_name}\n"
        f"🏠 Chat ID: `{chat.id}`"
    )
    await update.message.reply_text(info_text, parse_mode="Markdown")

async def echo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("কিছু লিখুন। উদাহরন: `/echo হ্যালো`", parse_mode="Markdown")
        return
    text = ' '.join(context.args)
    await update.message.reply_text(f"📣 {text}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """সাধারণ মেসেজের উত্তর"""
    await update.message.reply_text(f"নোট করলাম: {update.message.text}")

# ==========================================
# 🔄 ব্যাকগ্রাউন্ড লুপ
# ==========================================

async def bot_loop(application, local_queue):
    print("ℹ️ Info Bot Process Started...")
    await application.initialize()
    await application.start()
    
    while True:
        try:
            update_data = local_queue.get(timeout=1)
            if update_data:
                update = Update.de_json(update_data, application.bot)
                await application.process_update(update)
        except queue.Empty:
            continue
        except Exception as e:
            print(f"Info Bot Error: {e}")

# ==========================================
# 🚀 রানার ফাংশন
# ==========================================

def run_bot(input_queue):
    if not TOKEN:
        print("❌ Info Bot Token Missing!")
        return

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    app = Application.builder().token(TOKEN).build()
    
    # হ্যান্ডলার যুক্ত করা
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("info", info_command))
    app.add_handler(CommandHandler("echo", echo_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    loop.run_until_complete(bot_loop(app, input_queue))


