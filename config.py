import os
import sys

def _load_dotenv():
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

# ── البوت ─────────────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# ── Google Gemini (مجاني) ─────────────────────────────────────────────────────
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
if not GOOGLE_API_KEY:
    print("⚠️ GOOGLE_API_KEY غير موجود - احصل على مفتاح مجاني من https://aistudio.google.com")

# ── قاعدة البيانات ───────────────────────────────────────────────────────────
DATABASE_URL = os.getenv("DATABASE_URL", "")

# ── إعدادات المالك ───────────────────────────────────────────────────────────
OWNER_ID = int(os.getenv("OWNER_ID", "7021542402"))
OWNER_USERNAME = os.getenv("OWNER_USERNAME", "@zakros22bot")

# ── المحاولات ─────────────────────────────────────────────────────────────────
FREE_ATTEMPTS = 3
PAID_ATTEMPTS = 10

# ── الإحالات ──────────────────────────────────────────────────────────────────
REFERRAL_POINTS_PER_INVITE = 0.1
REFERRAL_POINTS_PER_ATTEMPT = 1.0

# ── الدفع (اختياري) ───────────────────────────────────────────────────────────
MASTERCARD_NUMBER = os.getenv("MASTERCARD_NUMBER", "4272128655")
MASTERCARD_PRICE = 4
TON_WALLET = os.getenv("TON_WALLET", "UQBpVo1V-ZhWpJi5YzoyQeX5fWuVwNq8KgcxXJWPq1ideEeD")
TRC20_WALLET = os.getenv("TRC20_WALLET", "TNbYTFmtoAr2CH3YYgxhCMZ3YNXNm9QLcq")
TELEGRAM_STARS_PRICE = 50

# ── العلامة المائية ───────────────────────────────────────────────────────────
WATERMARK_TEXT = "@zakros_probot"

# ── المجلدات المؤقتة ─────────────────────────────────────────────────────────
TEMP_DIR = "/tmp/telegram_bot"
os.makedirs(TEMP_DIR, exist_ok=True)
