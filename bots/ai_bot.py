import os
import asyncio
import queue  # এটি queue.Empty এরর চেক করার জন্য লাগবে
import logging
import requests
import html
from telegram import Update
from telegram.constants import ParseMode, ChatAction
from telegram.ext import Application, MessageHandler, filters, ContextTypes

# ==========================================
# ⚙️ কনফিগারেশন
# ==========================================
TOKEN = os.getenv("AI_BOT_TOKEN")
API_BASE = "https://ai.xneko.xyz"

logging.basicConfig(level=logging.INFO)

# ==========================================
# 🛠️ ইউটিলিটি ফাংশন (টাইপিং এবং ফরম্যাটিং)
# ==========================================

async def keep_sending_action(bot, chat_id, action):
    """
    যতক্ষণ রেসপন্স না আসে, ততক্ষণ প্রতি ৪ সেকেন্ড পরপর টাইপিং স্ট্যাটাস পাঠাবে।
    """
    try:
        while True:
            await bot.send_chat_action(chat_id=chat_id, action=action)
            # টেলিগ্রাম অ্যাকশন ৫ সেকেন্ড থাকে, তাই আমরা ৪ সেকেন্ড পরপর রিনিউ করব
            await asyncio.sleep(4)
    except asyncio.CancelledError:
        # টাস্ক ক্যানসেল হলে লুপ বন্ধ হবে
        pass

def smart_split(text, max_len=4000):
    """মেসেজ ভেঙে ফেলার স্মার্ট ফাংশন"""
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
    """HTML ফরম্যাটে মেসেজ পাঠায়"""
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

    # অ্যাকশন নির্ধারণ (টাইপিং নাকি ফটো আপলোড)
    action = ChatAction.UPLOAD_PHOTO if has_photo else ChatAction.TYPING
    
    # 🟢 ১. টাইপিং বা আপলোডিং টাস্ক ব্যাকগ্রাউন্ডে চালু করা হলো
    typing_task = asyncio.create_task(keep_sending_action(context.bot, chat_id, action))

    try:
        response_data = None
        should_use_post = has_photo or (text and len(text) > 600)
        
        # বর্তমান ইভেন্ট লুপ নেওয়া (run_in_executor এর জন্য)
        loop = asyncio.get_running_loop()

        # 🟢 ২. API কলটিকে থ্রেডে পাঠানো হলো যাতে টাইপিং লুপটি ব্লক না হয়
        if should_use_post:
            print(f"[{uid}] Sending POST request (Image: {has_photo})")
            data = {'uid': str(uid)}
            if text: data['q'] = text
            
            files = {}
            if has_photo:
                photo_file = await msg.photo[-1].get_file()
                image_bytes = await photo_file.download_as_bytearray()
                files['image'] = ('image.jpg', image_bytes, 'image/jpeg')

            # requests.post কে থ্রেডে চালানো হচ্ছে
            resp = await loop.run_in_executor(
                None, 
                lambda: requests.post(f"{API_BASE}/ask", data=data, files=files if files else None)
            )
        else:
            print(f"[{uid}] Sending GET request")
            params = {'q': text, 'uid': uid}
            
            # requests.get কে থ্রেডে চালানো হচ্ছে
            resp = await loop.run_in_executor(
                None,
                lambda: requests.get(f"{API_BASE}/ask", params=params)
            )

        try: response_data = resp.json()
        except: response_data = {"status": "success", "text": resp.text}

        if not response_data:
            await context.bot.send_message(chat_id, "❌ Empty response from API")
            return

        final_response = response_data.get("text") or response_data.get("output") or "No response text"
        
        # 🟢 ৩. টাইপিং টাস্ক বন্ধ করা (কারণ রেসপন্স এসে গেছে)
        typing_task.cancel()
        
        await send_html_safe_message(chat_id, final_response, context.bot)

    except Exception as e:
        print(f"Handler Error: {e}")
        typing_task.cancel() # এরর হলেও টাইপিং বন্ধ করতে হবে
        await context.bot.send_message(chat_id, f"❌ Bot Error: {str(e)}")

# ==========================================
# 🔄 ব্যাকগ্রাউন্ড লুপ এবং রানার
# ==========================================

async def bot_loop(application, local_queue):
    print("🤖 AI Bot Process Started (Isolated)...")
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
            print(f"AI Bot Loop Error: {e}")

def run_bot(input_queue):
    if not TOKEN: 
        print("❌ AI Bot Token Missing!")
        return

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    app = Application.builder().token(TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT | filters.PHOTO, handle_message))

    loop.run_until_complete(bot_loop(app, input_queue))
