import os
import sys


def _load_dotenv():
    """Load .env file — overrides any existing env var if .env has a non-empty value."""
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

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY     = os.getenv("OPENAI_API_KEY", "")

# ── Google API key pool ───────────────────────────────────────────────────────
# Supports: GOOGLE_API_KEY, GOOGLE_API_KEYS (comma), GOOGLE_API_KEY_1 … _9
_raw_google = os.getenv("GOOGLE_API_KEYS", "") or os.getenv("GOOGLE_API_KEY", "")
_g_from_comma: list[str] = [k.strip() for k in _raw_google.split(",") if k.strip()]
_g_from_numbered: list[str] = [
    v for i in range(1, 10)
    if (v := os.getenv(f"GOOGLE_API_KEY_{i}", "").strip())
]
_g_all = _g_from_comma + [k for k in _g_from_numbered if k not in _g_from_comma]
GOOGLE_API_KEYS: list[str] = _g_all
GOOGLE_API_KEY  = GOOGLE_API_KEYS[0] if GOOGLE_API_KEYS else ""

# ── Groq API key pool ─────────────────────────────────────────────────────────
# Supports: GROQ_API_KEY, GROQ_API_KEYS (comma), GROQ_API_KEY_1 … _9
_raw_groq = os.getenv("GROQ_API_KEYS", "") or os.getenv("GROQ_API_KEY", "")
_groq_from_comma: list[str] = [k.strip() for k in _raw_groq.split(",") if k.strip()]
_groq_from_numbered: list[str] = [
    v for i in range(1, 10)
    if (v := os.getenv(f"GROQ_API_KEY_{i}", "").strip())
]
_groq_all = _groq_from_comma + [k for k in _groq_from_numbered if k not in _groq_from_comma]
GROQ_API_KEYS: list[str] = _groq_all
GROQ_API_KEY  = GROQ_API_KEYS[0] if GROQ_API_KEYS else ""

# ── OpenRouter API key pool ───────────────────────────────────────────────────
# Supports: OPENROUTER_API_KEY, OPENROUTER_API_KEYS (comma), OPENROUTER_API_KEY_1 … _9
_raw_or = os.getenv("OPENROUTER_API_KEYS", "") or os.getenv("OPENROUTER_API_KEY", "")
_or_from_comma: list[str] = [k.strip() for k in _raw_or.split(",") if k.strip()]
_or_from_numbered: list[str] = [
    v for i in range(1, 10)
    if (v := os.getenv(f"OPENROUTER_API_KEY_{i}", "").strip())
]
_or_all = _or_from_comma + [k for k in _or_from_numbered if k not in _or_from_comma]
OPENROUTER_API_KEYS: list[str] = _or_all
OPENROUTER_API_KEY  = OPENROUTER_API_KEYS[0] if OPENROUTER_API_KEYS else ""

# ── ElevenLabs key pool (comma-separated OR individual _1.._9) ───────────────
_raw_keys = os.getenv("ELEVENLABS_API_KEYS", "") or os.getenv("ELEVENLABS_API_KEY", "")
_el_from_comma: list[str] = [k.strip() for k in _raw_keys.split(",") if k.strip()]
_el_from_numbered: list[str] = [
    v for i in range(1, 10)
    if (v := os.getenv(f"ELEVENLABS_API_KEY_{i}", "").strip())
]
_el_all = _el_from_comma + [k for k in _el_from_numbered if k not in _el_from_comma]
ELEVENLABS_API_KEYS: list[str] = _el_all
ELEVENLABS_API_KEY  = ELEVENLABS_API_KEYS[0] if ELEVENLABS_API_KEYS else ""

if not TELEGRAM_BOT_TOKEN:
    print("WARNING: TELEGRAM_BOT_TOKEN environment variable is not set", file=sys.stderr)
if not GOOGLE_API_KEY:
    print("WARNING: GOOGLE_API_KEY not set — get a free key from https://aistudio.google.com/", file=sys.stderr)
if not GROQ_API_KEY:
    print("INFO: GROQ_API_KEY not set — get a free key from https://console.groq.com/ for better reliability", file=sys.stderr)
if not ELEVENLABS_API_KEYS:
    print("WARNING: ELEVENLABS_API_KEYS not set — voice will use gTTS fallback", file=sys.stderr)


DATABASE_URL = os.getenv("DATABASE_URL", "")

OWNER_ID = 7021542402
FREE_ATTEMPTS = 1
PAID_ATTEMPTS = 7

# ⭐═════════════════════════════════════════════════════════════════════════════
# المتغيرات المضافة (هذه فقط التي كانت مفقودة)
# ⭐═════════════════════════════════════════════════════════════════════════════
REFERRAL_POINTS_PER_INVITE = 0.1   # نقاط لكل شخص يدخل عبر الرابط
REFERRAL_POINTS_PER_ATTEMPT = 1.0  # نقاط مطلوبة للحصول على محاولة واحدة

MASTERCARD_NUMBER = "4272128655"
OWNER_USERNAME = "@zakros22bot"
WATERMARK_TEXT = "@zakros_probot"
MASTERCARD_PRICE = 4
TON_WALLET = "UQBpVo1V-ZhWpJi5YzoyQeX5fWuVwNq8KgcxXJWPq1ideEeD"
TRC20_WALLET = "TNbYTFmtoAr2CH3YYgxhCMZ3YNXNm9QLcq"
TELEGRAM_STARS_PRICE = 50

VOICES = {
    "iraq": {
        "name": "🇮🇶 عراقي",
        "voice_id": "TX3LPaxmHKxFdv7VOQHJ",
        "description": "لهجة عراقية أصيلة"
    },
    "egypt": {
        "name": "🇪🇬 مصري",
        "voice_id": "AZnzlk1XvdvUeBnXmlld",
        "description": "لهجة مصرية مميزة"
    },
    "syria": {
        "name": "🇸🇾 سوري",
        "voice_id": "21m00Tcm4TlvDq8ikWAM",
        "description": "لهجة شامية جميلة"
    },
    "gulf": {
        "name": "🇸🇦 خليجي",
        "voice_id": "EXAVITQu4vr4xnSDxMaL",
        "description": "لهجة خليجية راقية"
    },
    "msa": {
        "name": "📚 فصحى",
        "voice_id": "pNInz6obpgDQGcFmaJgB",
        "description": "عربي فصيح"
    },
    "english": {
        "name": "🇺🇸 English",
        "voice_id": "9BWtsMINqrJLrRacOk9x",
        "description": "Professional English"
    },
    "british": {
        "name": "🇬🇧 British",
        "voice_id": "CwhRBWXzGAHq8TQ4Fs17",
        "description": "British English accent"
    }
}

TEMP_DIR = "/tmp/telegram_bot"
os.makedirs(TEMP_DIR, exist_ok=True)
