import os
import requests
import multiprocessing # 🟢 থ্রেডিং বাদ দিয়ে মাল্টিপ্রসেসিং
from flask import Flask, request, render_template

# বটের রানার ফাংশন ইমপোর্ট
# নোট: আমরা শুধু রানার ফাংশন ইমপোর্ট করব, গ্লোবাল কিউ নয়
from bots.ai_bot import run_bot as run_ai_bot, TOKEN as AI_TOKEN
from bots.test_bot import run_bot as run_test_bot, TOKEN as TEST_TOKEN
from bots.info_bot import run_bot as run_info_bot, TOKEN as INFO_TOKEN

# সার্ভার কনফিগারেশন
MY_SERVER_URL = "https://heavy-ztum.onrender.com"

app = Flask(__name__)

# এই ডিকশনারিটি প্রসেসগুলোর কিউ (Queue) মনে রাখবে
PROCESS_QUEUES = {}

def set_webhook(token):
    """ওয়েব হুক সেট করার ফাংশন"""
    if MY_SERVER_URL and "http" in MY_SERVER_URL:
        url = f"{MY_SERVER_URL}/{token}"
        try:
            requests.get(f"https://api.telegram.org/bot{token}/setWebhook?url={url}")
            print(f"✅ Webhook set for: ...{token[-5:]}")
        except Exception as e:
            print(f"❌ Webhook failed: {e}")

# --- ডাইনামিক ওয়েব হুক রাউট ---
@app.route('/<token>', methods=['POST'])
def global_webhook(token):
    # চেক করি এই টোকেনটি আমাদের কোনো প্রসেসের সাথে যুক্ত কিনা
    if token in PROCESS_QUEUES:
        try:
            # খুব দ্রুত ডেটা রিসিভ করে কিউতে ফেলে দেওয়া হয়
            # Flask এখানে ১ মিলিসেকেন্ডও দেরি করবে না
            json_update = request.get_json(force=True)
            target_queue = PROCESS_QUEUES[token]
            target_queue.put(json_update)
            
            return "OK", 200
        except Exception as e:
            print(f"Webhook Error: {e}")
            return "Error", 500
    else:
        return "Unknown Bot Token", 404

@app.route('/')
def home():
    return render_template('home.html')

def start_process(target_func, token, name):
    """একটি সম্পূর্ণ আলাদা প্রসেস তৈরি করার ফাংশন"""
    # ১. এই প্রসেসের জন্য একটি আলাদা কিউ তৈরি
    queue = multiprocessing.Queue()
    
    # ২. গ্লোবাল ম্যাপে রাখা (যাতে Flask খুঁজে পায়)
    PROCESS_QUEUES[token] = queue
    
    # ৩. প্রসেস স্টার্ট করা (আর্গুমেন্ট হিসেবে কিউ পাঠানো হচ্ছে)
    p = multiprocessing.Process(target=target_func, args=(queue,), name=name)
    p.start()
    return p

if __name__ == "__main__":
    # Flask এর রিলোডার সমস্যা এড়াতে মেইন ব্লকে রাখা জরুরি
    PORT = int(os.environ.get("PORT", "8080"))

    print("🚀 Starting Multiprocess Bot System...")

    # ১. AI Bot প্রসেস চালু
    start_process(run_ai_bot, AI_TOKEN, "AI_Bot_Process")

    # ২. Test Bot প্রসেস চালু
    start_process(run_test_bot, TEST_TOKEN, "Test_Bot_Process")

    # ৩. Info Bot প্রসেস চালু
    start_process(run_info_bot, INFO_TOKEN, "Info_Bot_Process")

    # ৪. ওয়েব হুক সেট করা
    set_webhook(AI_TOKEN)
    set_webhook(TEST_TOKEN)
    set_webhook(INFO_TOKEN)

    # ৫. সার্ভার রান
    app.run(host="0.0.0.0", port=PORT)

