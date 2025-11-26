import os  # os ইমপোর্ট করা হলো
import asyncio
import queue
import logging
import requests
import html
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, MessageHandler, filters, ContextTypes

# ==========================================
# ⚙️ কনফিগারেশন (সিক্রেট থেকে নেওয়া)
# ==========================================
# এখানে সরাসরি টোকেন না দিয়ে এনভায়রনমেন্ট ভেরিয়েবল নাম দেওয়া হলো
TOKEN = os.getenv("AI_BOT_TOKEN")

if not TOKEN:
    print("⚠️ Warning: AI_BOT_TOKEN not found in Secrets!")

API_BASE = "https://ai.xneko.xyz"

bot_queue = queue.Queue()
logging.basicConfig(level=logging.INFO)

# ==========================================
# 🛠️ ইউটিলিটি ফাংশন
# ==========================================

def smart_split(text, max_len=4000):
    if len(text) <= max_len: return [text]
    chunks = []
    while text:
        if len(text) <= max_len:
            chunks.append(text)
            break
        split_at = text.rfind('\n', 0, max_len)
        if split_at == -1: split_at = text.rfind(' ', 0, max_len)
        if split_at == -1: split_at = max_len
        chunk = text[:split_at]
        remaining = text[split_at:]
        if chunk.count('<pre>') > chunk.count('</pre>'):
            chunk += "</pre>"; remaining = "<pre>" + remaining
        elif chunk.count('<code>') > chunk.count('</code>'):
            chunk += "</code>"; remaining = "<code>" + remaining
        chunks.append(chunk)
        text = remaining
    return chunks

async def send_html_safe_message(chat_id, text, bot):
    clean_text = text.replace("```", "")
    chunks = smart_split(clean_text)
    for chunk in chunks:
        try:
            await bot.send_message(chat_id, chunk, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
        except Exception as e:
            print(f"HTML Error: {e}. Falling back.")
            await bot.send_message(chat_id, chunk.replace("<", "").replace(">", ""))

# ==========================================
# 🤖 মেইন লজিক হ্যান্ডলার
# ==========================================

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg: return
    chat_id = msg.chat_id
    uid = msg.from_user.id
    has_photo = bool(msg.photo)
    text = msg.caption if has_photo else msg.text
    if not text and not has_photo: return

    action = 'upload_photo' if has_photo else 'typing'
    await context.bot.send_chat_action(chat_id=chat_id, action=action)

    try:
        response_data = None
        should_use_post = has_photo or (text and len(text) > 600)
        if should_use_post:
            data = {'uid': str(uid)}; files = {}
            if text: data['q'] = text
            if has_photo:
                photo_file = await msg.photo[-1].get_file()
                image_bytes = await photo_file.download_as_bytearray()
                files['image'] = ('image.jpg', image_bytes, 'image/jpeg')
            resp = requests.post(f"{API_BASE}/ask", data=data, files=files if files else None)
            try: response_data = resp.json()
            except: response_data = {"status": "success", "text": resp.text}
        else:
            params = {'q': text, 'uid': uid}
            resp = requests.get(f"{API_BASE}/ask", params=params)
            try: response_data = resp.json()
            except: response_data = {"status": "success", "text": resp.text}

        final_resp = response_data.get("text") or response_data.get("output") or "No response"
        await send_html_safe_message(chat_id, final_resp, context.bot)

    except Exception as e:
        print(f"Handler Error: {e}")
        await context.bot.send_message(chat_id, f"❌ Error: {str(e)}")

# ==========================================
# 🔄 রানার
# ==========================================

async def bot_loop(application):
    print("🤖 AI Bot Worker Started...")
    await application.initialize()
    await application.start()
    while True:
        try:
            update_data = bot_queue.get(timeout=1)
            if update_data:
                update = Update.de_json(update_data, application.bot)
                await application.process_update(update)
        except queue.Empty: continue
        except Exception as e: print(f"AI Bot Loop Error: {e}")

def run_bot():
    if not TOKEN: return # টোকেন না থাকলে রান করবে না
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    app = Application.builder().token(TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT | filters.PHOTO, handle_message))
    loop.run_until_complete(bot_loop(app))
