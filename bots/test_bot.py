import os
import asyncio
import queue
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# ==========================================
# ⚙️ কনফিগারেশন
# ==========================================
TOKEN = os.getenv("TEST_BOT_TOKEN")

# ==========================================
# 🔄 ব্যাকগ্রাউন্ড লুপ (আইসোলেটেড)
# ==========================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("আমি টেস্ট বট! আলাদা প্রসেসরে চলছি! 🧪")

async def bot_loop(application, local_queue):
    """
    local_queue: app.py থেকে আসা মাল্টিপ্রসেসিং কিউ
    """
    print("🧪 Test Bot Process Started...")
    await application.initialize()
    await application.start()
    
    while True:
        try:
            # app.py থেকে পাঠানো কিউ চেক করা হচ্ছে
            update_data = local_queue.get(timeout=1)
            
            if update_data:
                update = Update.de_json(update_data, application.bot)
                await application.process_update(update)
                
        except queue.Empty:
            continue
        except Exception as e:
            print(f"Test Bot Error: {e}")

# ==========================================
# 🚀 রানার ফাংশন
# ==========================================

# ফাংশনটি এখন input_queue গ্রহণ করবে
def run_bot(input_queue):
    if not TOKEN:
        print("❌ Test Bot Token Missing!")
        return

    # প্রতিটি প্রসেসের জন্য নতুন ইভেন্ট লুপ
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    
    # লুপে ইনপুট কিউ পাস করা হলো
    loop.run_until_complete(bot_loop(app, input_queue))


