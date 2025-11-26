# full bot with /newchat command to assign per-user random API UID tokens
import os
import asyncio
import queue
import logging
import requests
import re
import html
import json
import random
import string
from pathlib import Path
from telegram import Update
from telegram.constants import ParseMode, ChatAction
from telegram.ext import Application, MessageHandler, CommandHandler, filters, ContextTypes

# ==========================================
# Config
# ==========================================
TOKEN = os.getenv("AI_BOT_TOKEN")
API_BASE = "https://ai.xneko.xyz"
REQUEST_TIMEOUT = 30  # seconds
USER_TOKENS_FILE = Path("user_tokens.json")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ==========================================
# User token management (in-memory + persistent)
# ==========================================
_user_tokens = {}
_user_tokens_lock = asyncio.Lock()

def _load_tokens_from_disk():
    global _user_tokens
    if USER_TOKENS_FILE.exists():
        try:
            with USER_TOKENS_FILE.open("r", encoding="utf-8") as f:
                _user_tokens = json.load(f)
        except Exception as e:
            logger.exception("Failed to load user tokens file, starting fresh.")
            _user_tokens = {}
    else:
        _user_tokens = {}

def _save_tokens_to_disk():
    try:
        with USER_TOKENS_FILE.open("w", encoding="utf-8") as f:
            json.dump(_user_tokens, f)
    except Exception:
        logger.exception("Failed to save user tokens to disk")

def generate_random_token(parts=3, part_len=4):
    """Generate token like ABCD-EFGH-IJKL (uppercase letters+digits)"""
    alphabet = string.ascii_uppercase + string.digits
    parts_list = []
    for _ in range(parts):
        part = ''.join(random.choice(alphabet) for _ in range(part_len))
        parts_list.append(part)
    return '-'.join(parts_list)

async def get_user_token_for_api(user_id: int):
    """Return existing token or create a new one if not present."""
    uid_str = str(user_id)
    async with _user_tokens_lock:
        token = _user_tokens.get(uid_str)
        if not token:
            token = generate_random_token()
            _user_tokens[uid_str] = token
            _save_tokens_to_disk()
        return token

async def set_user_token_for_api(user_id: int, token: str):
    uid_str = str(user_id)
    async with _user_tokens_lock:
        _user_tokens[uid_str] = token
        _save_tokens_to_disk()

async def force_new_token_for_user(user_id: int):
    uid_str = str(user_id)
    new_token = generate_random_token()
    async with _user_tokens_lock:
        _user_tokens[uid_str] = new_token
        _save_tokens_to_disk()
    return new_token

# initialize tokens on startup
_load_tokens_from_disk()

# ==========================================
# Utilities for typing/action and HTML safety
# ==========================================
async def keep_sending_action(bot, chat_id, action):
    try:
        while True:
            await bot.send_chat_action(chat_id=chat_id, action=action)
            await asyncio.sleep(4)
    except asyncio.CancelledError:
        return

def smart_segment_split_for_chunks(segments, max_len=4000):
    chunks = []
    current = ""
    for seg in segments:
        if len(seg) > max_len:
            start = 0
            while start < len(seg):
                end = min(start + max_len, len(seg))
                if end < len(seg):
                    nl = seg.rfind('\n', start, end)
                    if nl > start:
                        end = nl + 1
                piece = seg[start:end]
                if current and len(current) + len(piece) > max_len:
                    chunks.append(current)
                    current = ""
                current += piece
                if len(current) >= max_len:
                    chunks.append(current)
                    current = ""
                start = end
            continue

        if len(current) + len(seg) <= max_len:
            current += seg
        else:
            chunks.append(current)
            current = seg
    if current:
        chunks.append(current)
    return chunks

def prepare_html_chunks(raw_text, max_len=4000):
    pre_re = re.compile(r'(?is)<pre(?:\s[^>]*)?>(.*?)</pre>')
    segments = []
    last_idx = 0

    for m in pre_re.finditer(raw_text):
        start, end = m.span()
        inner = m.group(1)
        if start > last_idx:
            outside = raw_text[last_idx:start]
            if outside:
                segments.append(html.escape(outside))

        escaped_inner = html.escape(inner)
        code_block = f"<pre><code>{escaped_inner}</code></pre>"
        segments.append(code_block)
        last_idx = end

    if last_idx < len(raw_text):
        tail = raw_text[last_idx:]
        if tail:
            segments.append(html.escape(tail))

    chunks = smart_segment_split_for_chunks(segments, max_len=max_len)
    return chunks

async def send_html_safe_message(chat_id, text, bot):
    chunks = prepare_html_chunks(text, max_len=4000)
    for chunk in chunks:
        try:
            await bot.send_message(
                chat_id=chat_id,
                text=chunk,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True
            )
        except Exception as e:
            logger.warning(f"HTML send failed: {e}. Falling back to plaintext for this chunk.")
            plain = re.sub(r'<[^>]+>', '', chunk)
            plain = html.unescape(plain)
            try:
                await bot.send_message(chat_id=chat_id, text=plain)
            except Exception as e2:
                logger.exception(f"Plain text fallback also failed: {e2}")

# ==========================================
# /newchat command handler
# ==========================================
async def newchat_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    When user sends /newchat, assign a new random token and inform them.
    That token will be used as uid in subsequent API requests.
    """
    msg = update.effective_message
    user = update.effective_user
    if not user:
        return

    new_token = await force_new_token_for_user(user.id)
    await msg.reply_text(
        f"✅ New chat token generated for you:\n`{new_token}`\n\n"
        "This token will be used for your subsequent requests.",
        parse_mode=ParseMode.MARKDOWN
    )

async def mytoken_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Optional: show current token for user."""
    msg = update.effective_message
    user = update.effective_user
    if not user:
        return
    token = await get_user_token_for_api(user.id)
    await msg.reply_text(f"Your current chat token: `{token}`", parse_mode=ParseMode.MARKDOWN)

# ==========================================
# Main message handler (uses per-user token)
# ==========================================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg:
        return

    chat_id = msg.chat_id
    user = msg.from_user
    if not user:
        return

    has_photo = bool(msg.photo)
    text = msg.caption if has_photo else msg.text

    if not text and not has_photo:
        return

    # get the per-user token (this will create one if not exist)
    api_uid = await get_user_token_for_api(user.id)

    action = ChatAction.UPLOAD_PHOTO if has_photo else ChatAction.TYPING
    typing_task = asyncio.create_task(keep_sending_action(context.bot, chat_id, action))

    try:
        response_data = None
        should_use_post = has_photo or (text and len(text) > 600)
        loop = asyncio.get_running_loop()

        if should_use_post:
            logger.info("[%s] Sending POST request (image: %s)", api_uid, has_photo)
            data = {'uid': str(api_uid)}
            if text:
                data['q'] = text

            files = None
            if has_photo:
                photo_file = await msg.photo[-1].get_file()
                image_bytes = await photo_file.download_as_bytearray()
                files = {'image': ('image.jpg', image_bytes, 'image/jpeg')}

            def do_post():
                try:
                    return requests.post(f"{API_BASE}/ask", data=data, files=files, timeout=REQUEST_TIMEOUT)
                finally:
                    pass

            resp = await loop.run_in_executor(None, do_post)
        else:
            logger.info("[%s] Sending GET request", api_uid)
            params = {'q': text, 'uid': api_uid}
            def do_get():
                return requests.get(f"{API_BASE}/ask", params=params, timeout=REQUEST_TIMEOUT)
            resp = await loop.run_in_executor(None, do_get)

        try:
            response_data = resp.json()
        except Exception:
            response_data = {"status": "success", "text": resp.text}

        if not response_data:
            await context.bot.send_message(chat_id, "❌ Empty response from API")
            return

        final_response = response_data.get("text") or response_data.get("output") or "No response text"

        typing_task.cancel()
        try:
            await asyncio.wait_for(typing_task, timeout=1.0)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            pass

        await send_html_safe_message(chat_id, final_response, context.bot)

    except Exception as e:
        logger.exception("Handler Error")
        typing_task.cancel()
        try:
            await asyncio.wait_for(typing_task, timeout=1.0)
        except Exception:
            pass
        await context.bot.send_message(chat_id, f"❌ Bot Error: {str(e)}")

# ==========================================
# Runner
# ==========================================
async def bot_loop(application, local_queue):
    logger.info("AI Bot Process Started (Isolated)...")
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
        except Exception:
            logger.exception("AI Bot Loop Error")

def run_bot(input_queue):
    if not TOKEN:
        print("❌ AI Bot Token Missing!")
        return

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    app = Application.builder().token(TOKEN).build()
    # add handlers
    app.add_handler(CommandHandler("newchat", newchat_command))
    app.add_handler(CommandHandler("mytoken", mytoken_command))  # optional
    app.add_handler(MessageHandler(filters.TEXT | filters.PHOTO, handle_message))

    loop.run_until_complete(bot_loop(app, input_queue))
