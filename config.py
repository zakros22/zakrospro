import os

def _load_env():
    env_path = os.path.join(os.path.dirname(__file__), '.env')
    try:
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, v = line.split('=', 1)
                    if k.strip() and v.strip():
                        os.environ[k.strip()] = v.strip()
    except:
        pass

_load_env()

# ── Telegram ──────────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID", "7021542402"))
OWNER_USERNAME = os.getenv("OWNER_USERNAME", "@zakros22bot")

# ── Database ──────────────────────────────────────────────────────────────────
DATABASE_URL = os.getenv("DATABASE_URL", "")

# ── API Keys ──────────────────────────────────────────────────────────────────
GOOGLE_API_KEYS = [k.strip() for k in os.getenv("GOOGLE_API_KEYS", "").split(",") if k.strip()]
GOOGLE_API_KEY = GOOGLE_API_KEYS[0] if GOOGLE_API_KEYS else ""

GROQ_API_KEYS = [k.strip() for k in os.getenv("GROQ_API_KEYS", "").split(",") if k.strip()]
GROQ_API_KEY = GROQ_API_KEYS[0] if GROQ_API_KEYS else ""

OPENROUTER_API_KEYS = [k.strip() for k in os.getenv("OPENROUTER_API_KEYS", "").split(",") if k.strip()]
OPENROUTER_API_KEY = OPENROUTER_API_KEYS[0] if OPENROUTER_API_KEYS else ""

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# ElevenLabs (اختياري - نستخدم gTTS المجاني)
ELEVENLABS_API_KEYS = [k.strip() for k in os.getenv("ELEVENLABS_API_KEYS", "").split(",") if k.strip()]
ELEVENLABS_API_KEY = ELEVENLABS_API_KEYS[0] if ELEVENLABS_API_KEYS else ""

# ── Pexels & Pixabay (للصور الاحتياطية) ───────────────────────────────────────
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "")
PIXABAY_API_KEY = os.getenv("PIXABAY_API_KEY", "")

# ── System Settings ───────────────────────────────────────────────────────────
FREE_ATTEMPTS = 1
PAID_ATTEMPTS = 7

# ⭐ المتغيرات المفقودة - أضفها هنا ⭐
REFERRAL_POINTS_PER_INVITE = 0.1   # نقاط لكل شخص يدخل عبر الرابط
REFERRAL_POINTS_PER_ATTEMPT = 1.0  # نقاط مطلوبة للحصول على محاولة مجانية

# ── Payment Settings ──────────────────────────────────────────────────────────
MASTERCARD_NUMBER = os.getenv("MASTERCARD_NUMBER", "4272128655")
MASTERCARD_PRICE = 4
TON_WALLET = os.getenv("TON_WALLET", "UQBpVo1V-ZhWpJi5YzoyQeX5fWuVwNq8KgcxXJWPq1ideEeD")
TRC20_WALLET = os.getenv("TRC20_WALLET", "TNbYTFmtoAr2CH3YYgxhCMZ3YNXNm9QLcq")
TELEGRAM_STARS_PRICE = 50

# ── Watermark & Temp ──────────────────────────────────────────────────────────
WATERMARK_TEXT = "@zakros_probot"
TEMP_DIR = "/tmp/telegram_bot"
os.makedirs(TEMP_DIR, exist_ok=True)

# ── Voice Settings (gTTS) ─────────────────────────────────────────────────────
VOICES = {
    "iraq": {"name": "🇮🇶 عراقي", "voice_id": "iraq", "description": "لهجة عراقية"},
    "egypt": {"name": "🇪🇬 مصري", "voice_id": "egypt", "description": "لهجة مصرية"},
    "syria": {"name": "🇸🇾 شامي", "voice_id": "syria", "description": "لهجة شامية"},
    "gulf": {"name": "🇸🇦 خليجي", "voice_id": "gulf", "description": "لهجة خليجية"},
    "msa": {"name": "📚 فصحى", "voice_id": "msa", "description": "عربي فصيح"},
    "english": {"name": "🇺🇸 English", "voice_id": "english", "description": "English"},
    "british": {"name": "🇬🇧 British", "voice_id": "british", "description": "British English"},
}
