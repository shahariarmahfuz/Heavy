import os
import threading
import requests
from flask import Flask, request, render_template

# ================================================================
# 🟢 আপনার বটগুলোকে এখানে ইমপোর্ট করুন
# ================================================================
import bots.ai_bot as ai_bot
import bots.test_bot as test_bot
import bots.info_bot as info_bot  # <--- ১. নতুন বট ইমপোর্ট করলাম

# ২. এবং এই লিস্টে যোগ করে দিন
ACTIVE_BOT_MODULES = [
    ai_bot,
    test_bot,
    info_bot  # <--- এখানে নাম যোগ করলাম
]

# আপনার সার্ভার লিংক
MY_SERVER_URL = "https://heavy-ztum.onrender.com"
# ================================================================

app = Flask(__name__)

# এই ডিকশনারিটি অটোমেটিক টোকেন এবং কিউ ম্যাপ করবে
TOKEN_TO_QUEUE_MAP = {}

def setup_all_bots():
    """সব বট অটোমেটিক সেটআপ করার ফাংশন"""
    print(f"🚀 Setting up {len(ACTIVE_BOT_MODULES)} bots...")

    for bot_module in ACTIVE_BOT_MODULES:
        try:
            # ১. মডিউল থেকে টোকেন এবং কিউ বের করা
            # (প্রতিটি বটের ফাইলে TOKEN এবং bot_queue থাকতেই হবে)
            token = bot_module.TOKEN
            queue = bot_module.bot_queue

            # ২. ম্যাপে রাখা
            TOKEN_TO_QUEUE_MAP[token] = queue

            # ৩. বটের রানার ফাংশন আলাদা থ্রেডে চালু করা
            # (প্রতিটি বটের ফাইলে run_bot() ফাংশন থাকতেই হবে)
            t = threading.Thread(target=bot_module.run_bot, daemon=True)
            t.start()

            # ৪. ওয়েব হুক সেট করা
            if MY_SERVER_URL and "http" in MY_SERVER_URL:
                webhook_url = f"{MY_SERVER_URL}/{token}"
                requests.get(f"https://api.telegram.org/bot{token}/setWebhook?url={webhook_url}")
                print(f"✅ Live: Bot ...{token[-5:]}")

        except Exception as e:
            print(f"❌ Error setting up a bot: {e}")
            print("Tip: Ensure the bot file has 'TOKEN', 'bot_queue', and 'run_bot()'")

# --- ডাইনামিক ওয়েব হুক রাউট ---
# টেলিগ্রাম যখনই কোনো টোকেন লিংকে হিট করবে, এটি অটোমেটিক চিনে নেবে
@app.route('/<token>', methods=['POST'])
def global_webhook(token):
    if token in TOKEN_TO_QUEUE_MAP:
        try:
            json_update = request.get_json(force=True)
            target_queue = TOKEN_TO_QUEUE_MAP[token]
            target_queue.put(json_update)
            return "OK", 200
        except Exception as e:
            print(f"Webhook Error: {e}")
            return "Error", 500
    else:
        return "Unknown Bot Token", 404

# --- ওয়েবসাইট পেজ ---
@app.route('/')
def home():
    return render_template('home.html')

if __name__ == "__main__":
    # সব বট চালু করুন
    setup_all_bots()

    # সার্ভার রান করুন
    PORT = int(os.environ.get("PORT", "8080"))
    app.run(host="0.0.0.0", port=PORT)
