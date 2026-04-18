import os
import sys

def _load_dotenv():
    """تحميل ملف .env إذا كان موجوداً"""
    env_path = os.path.join(os.path.dirname(__file__), '.env')
    try:
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, _, val = line.partition('=')
                    key, val = key.strip(), val.strip()
                    if key and val:
                        os.environ[key] = val
    except FileNotFoundError:
        pass

_load_dotenv()

# المفتاح الوحيد المطلوب - من BotFather مجاناً
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

if not TELEGRAM_BOT_TOKEN:
    print("ERROR: TELEGRAM_BOT_TOKEN environment variable is required", file=sys.stderr)
    sys.exit(1)

# إعدادات قاعدة البيانات (PostgreSQL - مجاني على Railway/Supabase)
DATABASE_URL = os.getenv("DATABASE_URL", "")

# إعدادات المالك
OWNER_ID = int(os.getenv("OWNER_ID", "0"))
OWNER_USERNAME = os.getenv("OWNER_USERNAME", "@owner")

# نظام المحاولات
FREE_ATTEMPTS = 3  # 3 محاولات مجانية
PAID_ATTEMPTS = 5   # 5 محاولات إضافية عند الدفع

# نظام الإحالة
REFERRAL_POINTS_PER_INVITE = 0.1
REFERRAL_POINTS_PER_ATTEMPT = 1.0

# اللهجات المدعومة
VOICES = {
    "iraq": {"name": "🇮🇶 عراقي", "lang": "ar"},
    "egypt": {"name": "🇪🇬 مصري", "lang": "ar"},
    "syria": {"name": "🇸🇾 سوري", "lang": "ar"},
    "gulf": {"name": "🇸🇦 خليجي", "lang": "ar"},
    "msa": {"name": "📚 فصحى", "lang": "ar"},
    "english": {"name": "🇺🇸 English", "lang": "en"},
}

# مجلد الملفات المؤقتة
TEMP_DIR = "/tmp/telegram_bot"
os.makedirs(TEMP_DIR, exist_ok=True)

# إعدادات الدفع (اختياري)
PAYMENT_METHODS = {
    "stars": {"name": "⭐ نجوم تيليجرام", "price": 50},
    "manual": {"name": "💳 تحويل يدوي", "enabled": True}
  }
