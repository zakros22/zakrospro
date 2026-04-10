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

# ── قاعدة البيانات ───────────────────────────────────────────────────────────
DATABASE_URL = os.getenv("DATABASE_URL", "")

# ── Webhook ───────────────────────────────────────────────────────────────────
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")
WEBHOOK_ENABLED = bool(WEBHOOK_URL)

# ── Google Gemini ─────────────────────────────────────────────────────────────
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
GOOGLE_API_KEYS = os.getenv("GOOGLE_API_KEYS", "")

# ── Groq ──────────────────────────────────────────────────────────────────────
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_API_KEYS = os.getenv("GROQ_API_KEYS", "")

# ── OpenRouter ────────────────────────────────────────────────────────────────
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_API_KEYS = os.getenv("OPENROUTER_API_KEYS", "")

# ── ElevenLabs (اختياري) ──────────────────────────────────────────────────────
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
ELEVENLABS_API_KEYS = os.getenv("ELEVENLABS_API_KEYS", "")

# ── إعدادات المالك ───────────────────────────────────────────────────────────
OWNER_ID = int(os.getenv("OWNER_ID", "7021542402"))
OWNER_USERNAME = os.getenv("OWNER_USERNAME", "@zakros22bot")

# ── المحاولات ─────────────────────────────────────────────────────────────────
FREE_ATTEMPTS = int(os.getenv("FREE_ATTEMPTS", "3"))
PAID_ATTEMPTS = int(os.getenv("PAID_ATTEMPTS", "10"))

# ── الإحالات ──────────────────────────────────────────────────────────────────
REFERRAL_POINTS_PER_INVITE = 0.1
REFERRAL_POINTS_PER_ATTEMPT = 1.0

# ── ألوان Osmosis ─────────────────────────────────────────────────────────────
OSMOSIS_PINK = (231, 76, 126)      # وردي
OSMOSIS_BLUE = (52, 152, 219)      # أزرق
OSMOSIS_GREEN = (46, 204, 113)     # أخضر
OSMOSIS_RED = (231, 76, 60)        # أحمر
OSMOSIS_PURPLE = (155, 89, 182)    # بنفسجي
OSMOSIS_ORANGE = (230, 126, 34)    # برتقالي
OSMOSIS_DARK = (44, 62, 80)        # أزرق داكن
OSMOSIS_GRAY = (127, 140, 141)     # رمادي
OSMOSIS_WHITE = (255, 255, 255)    # أبيض

# ── العلامة المائية ───────────────────────────────────────────────────────────
WATERMARK_TEXT = "@zakros_probot"

# ── المجلدات المؤقتة ─────────────────────────────────────────────────────────
TEMP_DIR = "/tmp/telegram_bot"
os.makedirs(TEMP_DIR, exist_ok=True)

# ── تحذيرات ───────────────────────────────────────────────────────────────────
if not TELEGRAM_BOT_TOKEN:
    print("⚠️ WARNING: TELEGRAM_BOT_TOKEN not set", file=sys.stderr)
if not GOOGLE_API_KEY and not GOOGLE_API_KEYS:
    print("⚠️ WARNING: No Google API keys configured", file=sys.stderr)
