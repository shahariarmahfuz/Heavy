import os
import asyncio
import queue
import logging
import requests
import html
import random
import string
import re

from telegram import Update
from telegram.constants import ParseMode, ChatAction
from telegram.ext import Application, MessageHandler, CommandHandler, filters, ContextTypes

# ==========================================
# ⚙️ কনফিগারেশন
# ==========================================
TOKEN = os.getenv("AI_BOT_TOKEN")
API_BASE = "https://ai.xneko.xyz"

# লগের লেভেল সেট করা
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# ইউজারদের সেশন বা চ্যাট আইডি স্টোর করার জন্য ডিকশনারি
# Structure: { telegram_user_id: "SESSION_ID" }
user_sessions = {}

# ==========================================
# 🛠️ ইউটিলিটি ফাংশন (আইডি জেনারেশন)
# ==========================================
def generate_session_id():
    """
    RANDO-RANDO-RANDO ফরম্যাটে আইডি জেনারেট করে।
    উদাহরণ: SJHD-JSJE-KWJS
    """
    def get_chunk():
        return ''.join(random.choices(string.ascii_uppercase, k=4))
    
    return f"{get_chunk()}-{get_chunk()}-{get_chunk()}"

def get_current_uid(user_id):
    """ইউজারের বর্তমান সেশন আইডি রিটার্ন করে, না থাকলে টেলিগ্রাম আইডি দেয়"""
    return user_sessions.get(user_id, str(user_id))

# ==========================================
# 🛠️ ইউটিলিটি ফাংশন (টাইপিং এবং ফরম্যাটিং)
# ==========================================
async def keep_sending_action(bot, chat_id, action):
    """রেসপন্স না আসা পর্যন্ত টাইপিং স্ট্যাটাস দেখাবে"""
    try:
        while True:
            await bot.send_chat_action(chat_id=chat_id, action=action)
            await asyncio.sleep(4)
    except asyncio.CancelledError:
        pass

def parse_and_format_content(text):
    """
    AI এর মার্কডাউন রেসপন্সকে টেলিগ্রাম সাপোর্টেড HTML এ কনভার্ট করে।
    এটি কোড ব্লকগুলো (```code```) কে <pre><code>...</code></pre> এ রূপান্তর করে।
    """
    parts = re.split(r'(```.*?```)', text, flags=re.DOTALL)
    formatted_parts = []

    for part in parts:
        if part.startswith('```') and part.endswith('```'):
            # এটি একটি কোড ব্লক
            content = part[3:-3].strip()
            # ল্যাঙ্গুয়েজ ডিটেকশন (যদি থাকে, যেমন ```python)
            first_line_break = content.find('\n')
            lang = ""
            if first_line_break > -1:
                possible_lang = content[:first_line_break].strip()
                # সাধারণ ল্যাঙ্গুয়েজ নাম চেক (স্পেস বা স্পেশাল ক্যারেক্টার বাদে)
                if possible_lang and possible_lang.isalnum() and len(possible_lang) < 15:
                    lang = f' class="language-{possible_lang}"'
                    content = content[first_line_break+1:]
            
            # কোডের ভেতরের স্পেশাল ক্যারেক্টার এস্কেপ করা (যেমন <, >, &)
            escaped_content = html.escape(content)
            formatted_parts.append(f'<pre><code{lang}>{escaped_content}</code></pre>')
        else:
            # এটি সাধারণ টেক্সট, এখানেও এস্কেপ করতে হবে
            if part.strip():
                # বোল্ড টেক্সট হ্যান্ডেল করা (**text** -> <b>text</b>)
                part = html.escape(part)
                part = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', part)
                formatted_parts.append(part)

    return "".join(formatted_parts)

async def send_smart_split_message(chat_id, text, bot):
    """
    বড় মেসেজগুলো এমনভাবে ভাগ করে পাঠায় যেন HTML ট্যাগ বা কোড ব্লক ভেঙে না যায়।
    """
    # প্রথমে পুরো টেক্সটকে HTML এ ফরম্যাট করে নিই
    formatted_text = parse_and_format_content(text)
    
    max_len = 4000
    if len(formatted_text) <= max_len:
        await bot.send_message(chat_id=chat_id, text=formatted_text, parse_mode=ParseMode.HTML)
        return

    # যদি মেসেজ বড় হয়, তবে লাইন বাই লাইন স্প্লিট লজিক
    lines = formatted_text.split('\n')
    chunk = ""
    in_code_block = False
    code_lang = ""

    for line in lines:
        # বর্তমান লাইন যোগ করলে যদি লিমিট পার হয়ে যায়
        if len(chunk) + len(line) + 1 > max_len:
            # যদি কোড ব্লকের ভেতরে থাকি, তাহলে ট্যাগ ক্লোজ করে পাঠাতে হবে
            if in_code_block:
                chunk += "</code></pre>"
            
            # মেসেজ পাঠানো
            try:
                await bot.send_message(chat_id=chat_id, text=chunk, parse_mode=ParseMode.HTML)
            except Exception as e:
                # ফলব্যাক: যদি পার্সিং এরর হয়, প্লেইন টেক্সট হিসেবে পাঠানো
                await bot.send_message(chat_id=chat_id, text=chunk.replace('<', ''), parse_mode=None)

            # নতুন চাঙ্ক শুরু
            chunk = ""
            # যদি কোড ব্লক আগে ওপেন ছিল, পরের মেসেজে আবার ওপেন করতে হবে
            if in_code_block:
                chunk += f'<pre><code{code_lang}>'
        
        # কোড ব্লক ডিটেকশন (ম্যানুয়ালি ট্যাগ দেখে)
        if '<pre><code' in line:
            in_code_block = True
            # ল্যাঙ্গুয়েজ ক্লাস সেভ করে রাখা
            match = re.search(r'<code( class="[^"]*")?>', line)
            if match and match.group(1):
                code_lang = match.group(1)
            else:
                code_lang = ""
        
        if '</code></pre>' in line:
            in_code_block = False

        chunk += line + "\n"

    # বাকি অংশ পাঠানো
    if chunk:
        try:
            await bot.send_message(chat_id=chat_id, text=chunk, parse_mode=ParseMode.HTML)
        except Exception:
            await bot.send_message(chat_id=chat_id, text=chunk.replace('<', ''), parse_mode=None)

# ==========================================
# 🤖 কমান্ড হ্যান্ডলার (/newchat)
# ==========================================
async def new_chat_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    new_session_id = generate_session_id()
    
    # সেশন সেভ করা
    user_sessions[user_id] = new_session_id
    
    await update.message.reply_text(
        f"✅ <b>New Chat Started!</b>\n\n"
        f"👤 Your new Identity ID: <code>{new_session_id}</code>\n"
        f"Previous context has been cleared.",
        parse_mode=ParseMode.HTML
    )
    logging.info(f"User {user_id} switched to new session: {new_session_id}")

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Hello! I am ready. Send me a message or photo.\n"
        "Use /newchat to reset the conversation context."
    )

# ==========================================
# 🤖 মেইন মেসেজ হ্যান্ডলার
# ==========================================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg: return
    
    chat_id = msg.chat_id
    user_id = msg.from_user.id
    has_photo = bool(msg.photo)
    text = msg.caption if has_photo else msg.text
    
    if not text and not has_photo: return

    # সেশন আইডি বের করা (যদি /newchat দিয়ে সেট করা থাকে, নাহলে ডিফল্ট আইডি)
    current_uid = get_current_uid(user_id)
    
    # অ্যাকশন
    action = ChatAction.UPLOAD_PHOTO if has_photo else ChatAction.TYPING
    typing_task = asyncio.create_task(keep_sending_action(context.bot, chat_id, action))

    try:
        response_data = None
        should_use_post = has_photo or (text and len(text) > 600)
        loop = asyncio.get_running_loop()

        if should_use_post:
            logging.info(f"[{current_uid}] Sending POST request (Image: {has_photo})")
            data = {'uid': current_uid}
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
            logging.info(f"[{current_uid}] Sending GET request")
            params = {'q': text, 'uid': current_uid}
            
            resp = await loop.run_in_executor(
                None,
                lambda: requests.get(f"{API_BASE}/ask", params=params)
            )

        try: 
            response_data = resp.json()
        except: 
            response_data = {"status": "success", "text": resp.text}

        typing_task.cancel()

        if not response_data:
            await context.bot.send_message(chat_id, "❌ Empty response from API")
            return

        final_response = response_data.get("text") or response_data.get("output") or "No response text"
        
        # ফরম্যাটেড মেসেজ পাঠানো
        await send_smart_split_message(chat_id, final_response, context.bot)

    except Exception as e:
        logging.error(f"Handler Error: {e}")
        typing_task.cancel()
        await context.bot.send_message(chat_id, f"❌ Error: {str(e)}")

# ==========================================
# 🔄 রানার ফাংশন
# ==========================================
async def bot_loop(application, local_queue):
    logging.info("🤖 AI Bot Process Started...")
    await application.initialize()
    await application.start()

    while True:
        try:
            # কিউ থেকে আপডেট নেওয়া (যদি মাল্টিপ্রসেসিং ব্যবহার করেন)
            # সাধারণ চালানোর জন্য এটি ব্লকিং হতে পারে, তাই timeout ব্যবহার করা হলো
            update_data = local_queue.get(timeout=1)
            if update_data:
                update = Update.de_json(update_data, application.bot)
                await application.process_update(update)
        except queue.Empty:
            # কিউ খালি থাকলে লুপ কন্টিনিউ করবে (CPU idle রাখার জন্য সামান্য স্লিপ দেওয়া যেতে পারে)
            await asyncio.sleep(0.1) 
            continue
        except Exception as e:
            logging.error(f"AI Bot Loop Error: {e}")

def run_bot(input_queue):
    if not TOKEN:
        print("❌ AI Bot Token Missing!")
        return

    # ইভেন্ট লুপ সেটআপ
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    app = Application.builder().token(TOKEN).build()
    
    # হ্যান্ডলার রেজিস্ট্রেশন
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("newchat", new_chat_command)) # নতুন ফিচার
    app.add_handler(MessageHandler(filters.TEXT | filters.PHOTO, handle_message))

    loop.run_until_complete(bot_loop(app, input_queue))
