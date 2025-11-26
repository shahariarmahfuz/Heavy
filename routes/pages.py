from flask import Blueprint, render_template, request
from bot.bot import update_queue, TOKEN  # bot ফোল্ডার থেকে ইমপোর্ট

# ব্লুপ্রিন্ট তৈরি (নাম দেওয়া হলো 'pages')
# এই ভেরিয়েবলটির নামই (pages_bp) আমরা app.py তে ইমপোর্ট করছি
pages_bp = Blueprint('pages', __name__)

# --- ওয়েবসাইট পেজগুলো ---

@pages_bp.route('/')
def home():
    # templates ফোল্ডারে home.html থাকতে হবে
    return render_template('home.html')

@pages_bp.route('/about')
def about():
    return render_template('about.html')

@pages_bp.route('/contact')
def contact():
    return render_template('contact.html')

# --- টেলিগ্রাম ওয়েব হুক রিসিভার ---
# TOKEN আমরা bot.py থেকে ইমপোর্ট করেছি
@pages_bp.route(f'/{TOKEN}', methods=['POST'])
def telegram_webhook():
    """
    মেসেজ রিসিভ করে bot.py এর কিউ-তে পাঠিয়ে দিবে।
    লজিক সব bot.py তেই থাকবে, এটি শুধু পিয়ন হিসেবে কাজ করবে।
    """
    try:
        # JSON ডেটা নেওয়া
        json_update = request.get_json(force=True)
        
        # মেসেজটি bot.py এর প্রসেসিং লাইনে (Queue) পাঠিয়ে দেওয়া হলো
        update_queue.put(json_update)
        
        # সাথে সাথে টেলিগ্রামকে OK বলা (টাইমআউট এড়াতে)
        return "OK", 200
    except Exception as e:
        print(f"Webhook Error: {e}")
        return "Error", 500
