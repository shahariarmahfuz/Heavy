import os
import asyncio
import queue
import logging
import requests
import html
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, MessageHandler, filters, ContextTypes

# ==========================================
# ⚙️ কনফিগারেশন
# ==========================================
# নাম অবশ্যই TOKEN হতে হবে
TOKEN = os.getenv("AI_BOT_TOKEN")  
API_BASE = "https://ai.xneko.xyz"

# নাম অবশ্যই bot_queue হতে হবে
bot_queue = queue.Queue()

# লগিং
logging.basicConfig(level=logging.INFO)

# ==========================================
# 🛠️ ইউটিলিটি ফাংশন
# ==========================================

def smart_split(text, max_len=4000):
    if len(text) <= max_len:
        return [text]

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
            chunk += "</pre>"
            remaining = "<pre>" + remaining
        elif chunk.count('<code>') > chunk.count('</code>'):
            chunk += "</code>"
            remaining = "<code>" + remaining

        chunks.append(chunk)
        text = remaining
    return chunks

async def send_html_safe_message(chat_id, text, bot):
    clean_text = text.replace("```", "")
    chunks = smart_split(clean_text)

    for chunk in chunks:
        try:
            await bot.send_message(
                chat_id=chat_id, 
                text=chunk, 
                parse_mode=ParseMode.HTML, 
                disable_web_page_preview=True
            )
        except Exception as e:
            print(f"HTML Error: {e}. Falling back to plain text.")
            plain_text = chunk.replace("<", "").replace(">", "")
            await bot.send_message(chat_id=chat_id, text=plain_text)

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
            print(f"[{uid}] Sending POST request (Image: {has_photo})")
            data = {'uid': str(uid)}
            if text: data['q'] = text
            files = {}
            if has_photo:
                photo_file = await msg.photo[-1].get_file()
                image_bytes = await photo_file.download_as_bytearray()
                files['image'] = ('image.jpg', image_bytes, 'image/jpeg')

            resp = requests.post(f"{API_BASE}/ask", data=data, files=files if files else None)
            try: response_data = resp.json()
            except: response_data = {"status": "success", "text": resp.text}
        else:
            print(f"[{uid}] Sending GET request")
            params = {'q': text, 'uid': uid}
            resp = requests.get(f"{API_BASE}/ask", params=params)
            try: response_data = resp.json()
            except: response_data = {"status": "success", "text": resp.text}

        if not response_data:
            await context.bot.send_message(chat_id, "❌ Empty response from API")
            return

        final_response = response_data.get("text") or response_data.get("output") or "No response text"
        await send_html_safe_message(chat_id, final_response, context.bot)

    except Exception as e:
        print(f"Handler Error: {e}")
        await context.bot.send_message(chat_id, f"❌ Bot Error: {str(e)}")

# ==========================================
# 🔄 ব্যাকগ্রাউন্ড লুপ এবং রানার
# ==========================================

async def bot_loop(application):
    print("🤖 AI Bot Worker Started...")
    await application.initialize()
    await application.start()

    while True:
        try:
            # এখানে bot_queue ব্যবহার করা হচ্ছে
            update_data = bot_queue.get(timeout=1)
            if update_data:
                update = Update.de_json(update_data, application.bot)
                await application.process_update(update)
        except queue.Empty:
            continue
        except Exception as e:
            print(f"AI Bot Loop Error: {e}")

# ফাংশনের নাম অবশ্যই run_bot হতে হবে
def run_bot():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    # এখানে TOKEN ব্যবহার করা হচ্ছে
    app = Application.builder().token(TOKEN).build()

    app.add_handler(MessageHandler(filters.TEXT | filters.PHOTO, handle_message))

    loop.run_until_complete(bot_loop(app))
