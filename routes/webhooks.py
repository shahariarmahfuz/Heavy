# routes/webhooks.py
from flask import Blueprint, render_template, request

# দুটি বটের ফাইল থেকেই ইমপোর্ট করা হচ্ছে
from bots.ai_bot import ai_queue, AI_TOKEN
from bots.test_bot import test_queue, TEST_TOKEN

# ব্লুপ্রিন্ট
routes_bp = Blueprint('routes', __name__)

# --- ওয়েবসাইট ---
@routes_bp.route('/')
def home():
    return render_template('home.html')

# --- ১. AI বটের ওয়েব হুক ---
@routes_bp.route(f'/{AI_TOKEN}', methods=['POST'])
def ai_bot_webhook():
    try:
        json_update = request.get_json(force=True)
        # AI কিউ-তে পাঠানো হলো
        ai_queue.put(json_update)
        return "OK", 200
    except:
        return "Error", 500

# --- ২. Test বটের ওয়েব হুক ---
@routes_bp.route(f'/{TEST_TOKEN}', methods=['POST'])
def test_bot_webhook():
    try:
        json_update = request.get_json(force=True)
        # Test কিউ-তে পাঠানো হলো
        test_queue.put(json_update)
        return "OK", 200
    except:
        return "Error", 500
