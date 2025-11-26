import os
import asyncio
import queue  # এটি queue.Empty এরর চেক করার জন্য লাগবে
import logging
import requests
import html
import random
import string
from telegram import Update
from telegram.constants import ParseMode, ChatAction
from telegram.ext import Application, MessageHandler, CommandHandler, filters, ContextTypes

# ==========================================
# ⚙️ কনফিগারেশন
# ==========================================
TOKEN = os.getenv("AI_BOT_TOKEN")
API_BASE = "https://ai.xneko.xyz"

logging.basicConfig(level=logging.INFO)

# ইউজারের সেশন ID মনে রাখার জন্য ডিকশনারি
user_sessions = {}

# ==========================================
# 🛠️ ইউটিলিটি ফাংশন
# ==========================================

def generate_session_id():
    """XXXX-XXXX-XXXX ফরম্যাটে র‍্যান্ডম ID জেনারেট করে"""
    part = lambda: ''.join(random.choices(string.ascii_uppercase, k=4))
    return f"{part()}-{part()}-{part()}"

async def keep_sending_action(bot, chat_id, action):
    """টাইপিং স্ট্যাটাস বজায় রাখে"""
    try:
        while True:
            await bot.send_chat_action(chat_id=chat_id, action=action)
            await asyncio.sleep(4)
    except asyncio.CancelledError:
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
            await bot.send_message(chat_id=chat_id, text=chunk, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
        except Exception as e:
            plain_text = chunk.replace("<", "").replace(">", "")
            await bot.send_message(chat_id=chat_id, text=plain_text)

# ==========================================
# 🎮 কমান্ড হ্যান্ডলার
# ==========================================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("স্বাগতম! আমি আপনার AI অ্যাসিস্ট্যান্ট। প্রশ্ন করা শুরু করুন।")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "🤖 **কমান্ড লিস্ট:**\n\n"
        "/newchat - নতুন চ্যাট শুরু করুন (হিস্ট্রি ক্লিয়ার হবে)\n"
        "/help - এই মেসেজটি দেখাবে\n"
        "যেকোনো টেক্সট বা ছবি পাঠান উত্তরের জন্য।"
    )
    await send_html_safe_message(update.effective_chat.id, help_text, context.bot)

async def newchat_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    real_uid = update.message.from_user.id
    new_id = generate_session_id()
    
    # নতুন ID সেট করা হচ্ছে
    user_sessions[real_uid] = new_id
    
    await update.message.reply_text(
        f"✅ <b>নতুন চ্যাট সেশন শুরু হয়েছে!</b>\n"
        f"আপনার নতুন সেশন ID: <code>{new_id}</code>",
        parse_mode=ParseMode.HTML
    )

# ==========================================
# 🤖 মেইন লজিক হ্যান্ডলার
# ==========================================

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg: return

    chat_id = msg.chat_id
    real_uid = msg.from_user.id # টেলিগ্রামের আসল ID
    
    # সেশন চেক করা: যদি নতুন চ্যাট ID থাকে সেটা ব্যবহার করবে, না হলে আসল ID
    api_uid = user_sessions.get(real_uid, real_uid)

    has_photo = bool(msg.photo)
    text = msg.caption if has_photo else msg.text

    if not text and not has_photo: return

    action = ChatAction.UPLOAD_PHOTO if has_photo else ChatAction.TYPING
    typing_task = asyncio.create_task(keep_sending_action(context.bot, chat_id, action))

    try:
        response_data = None
        should_use_post = has_photo or (text and len(text) > 600)
        loop = asyncio.get_running_loop()

        # এখানে api_uid ব্যবহার করা হচ্ছে (যেটি রেন্ডম হতে পারে)
        if should_use_post:
            print(f"[{api_uid}] Sending POST request (Image: {has_photo})")
            data = {'uid': str(api_uid)}
            if text: data['q'] = text
            
            files = {}
            if has_photo:
                photo_file = await msg.photo[-1].get_file()
                image_bytes = await photo_file.download_as_bytearray()
                files['image'] = ('image.jpg', image_bytes, 'image/jpeg')

            resp = await loop.run_in_executor(
                None, 
                lambda: requests.post(f"{API_BASE}/ask", data=data, files=files if files else None)
            )
        else:
            print(f"[{api_uid}] Sending GET request")
            params = {'q': text, 'uid': api_uid}
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
        typing_task.cancel()
        await send_html_safe_message(chat_id, final_response, context.bot)

    except Exception as e:
        print(f"Handler Error: {e}")
        typing_task.cancel()
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
    
    # নতুন কমান্ড হ্যান্ডলারগুলো যুক্ত করা হলো
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("newchat", newchat_command))
    
    # মেসেজ হ্যান্ডলার সবার শেষে থাকবে
    app.add_handler(MessageHandler(filters.TEXT | filters.PHOTO, handle_message))

    loop.run_until_complete(bot_loop(app, input_queue))
