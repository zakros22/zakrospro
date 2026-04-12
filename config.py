# -*- coding: utf-8 -*-
import os
import sys

def _load_dotenv():
    """تحميل متغيرات البيئة من ملف .env"""
    env_path = os.path.join(os.path.dirname(__file__), '.env')
    try:
        with open(env_path, 'r', encoding='utf-8') as f:
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

# ═══════════════════════════════════════════════════════════════════════════════
# البوت
# ═══════════════════════════════════════════════════════════════════════════════

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# ═══════════════════════════════════════════════════════════════════════════════
# مفاتيح الذكاء الاصطناعي
# ═══════════════════════════════════════════════════════════════════════════════

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_API_KEYS = os.getenv("DEEPSEEK_API_KEYS", "")

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
GOOGLE_API_KEYS = os.getenv("GOOGLE_API_KEYS", "")

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_API_KEYS = os.getenv("GROQ_API_KEYS", "")

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_API_KEYS = os.getenv("OPENROUTER_API_KEYS", "")

def get_all_keys(env_name, single_env):
    """استخراج جميع المفاتيح من متغيرات البيئة"""
    keys = []
    raw = os.getenv(env_name, "")
    if raw:
        for k in raw.split(","):
            k = k.strip()
            if k and k not in keys:
                keys.append(k)
    single = os.getenv(single_env, "").strip()
    if single and single not in keys:
        keys.append(single)
    return [k for k in keys if k]

# ═══════════════════════════════════════════════════════════════════════════════
# قاعدة البيانات
# ═══════════════════════════════════════════════════════════════════════════════

DATABASE_URL = os.getenv("DATABASE_URL", "")

# ═══════════════════════════════════════════════════════════════════════════════
# Webhook
# ═══════════════════════════════════════════════════════════════════════════════

WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")

# ═══════════════════════════════════════════════════════════════════════════════
# إعدادات المالك
# ═══════════════════════════════════════════════════════════════════════════════

OWNER_ID = int(os.getenv("OWNER_ID", "7021542402"))
OWNER_USERNAME = os.getenv("OWNER_USERNAME", "@zakros22bot")

# ═══════════════════════════════════════════════════════════════════════════════
# المحاولات
# ═══════════════════════════════════════════════════════════════════════════════

FREE_ATTEMPTS = int(os.getenv("FREE_ATTEMPTS", "3"))
PAID_ATTEMPTS = int(os.getenv("PAID_ATTEMPTS", "10"))

# ═══════════════════════════════════════════════════════════════════════════════
# الإحالات
# ═══════════════════════════════════════════════════════════════════════════════

REFERRAL_POINTS_PER_INVITE = 0.1
REFERRAL_POINTS_PER_ATTEMPT = 1.0

# ═══════════════════════════════════════════════════════════════════════════════
# الدفع
# ═══════════════════════════════════════════════════════════════════════════════

MASTERCARD_NUMBER = os.getenv("MASTERCARD_NUMBER", "")
MASTERCARD_PRICE = int(os.getenv("MASTERCARD_PRICE", "4"))
TON_WALLET = os.getenv("TON_WALLET", "")
TRC20_WALLET = os.getenv("TRC20_WALLET", "")
TELEGRAM_STARS_PRICE = int(os.getenv("TELEGRAM_STARS_PRICE", "50"))

# ═══════════════════════════════════════════════════════════════════════════════
# العلامة المائية والمجلدات
# ═══════════════════════════════════════════════════════════════════════════════

WATERMARK_TEXT = "@zakros_probot"
TEMP_DIR = "/tmp/telegram_bot"
os.makedirs(TEMP_DIR, exist_ok=True)

# ═══════════════════════════════════════════════════════════════════════════════
# تحذير
# ═══════════════════════════════════════════════════════════════════════════════

if not TELEGRAM_BOT_TOKEN:
    print("⚠️ TELEGRAM_BOT_TOKEN غير موجود", file=sys.stderr)
