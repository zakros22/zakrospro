import os
import sys


def _load_dotenv():
    """Load .env file — overrides any existing env var if .env has a non-empty value."""
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

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# ══════════════════════════════════════════════════════════════════════════════
# 🔑 DEEPSEEK API KEYS — الأولوية الأولى (9 مفاتيح)
# ══════════════════════════════════════════════════════════════════════════════
DEEPSEEK_API_KEYS: list[str] = []
for i in range(1, 10):
    key = os.getenv(f"DEEPSEEK_API_KEY_{i}", "").strip()
    if key:
        DEEPSEEK_API_KEYS.append(key)
if not DEEPSEEK_API_KEYS:
    single = os.getenv("DEEPSEEK_API_KEY", "").strip()
    if single:
        DEEPSEEK_API_KEYS = [single]
DEEPSEEK_API_KEY = DEEPSEEK_API_KEYS[0] if DEEPSEEK_API_KEYS else ""

# ══════════════════════════════════════════════════════════════════════════════
# 🔑 GOOGLE API KEYS — Gemini (الأولوية الثانية - 9 مفاتيح)
# ══════════════════════════════════════════════════════════════════════════════
GOOGLE_API_KEYS: list[str] = []
for i in range(1, 10):
    key = os.getenv(f"GOOGLE_API_KEY_{i}", "").strip()
    if key:
        GOOGLE_API_KEYS.append(key)
if not GOOGLE_API_KEYS:
    single = os.getenv("GOOGLE_API_KEY", "").strip()
    if single:
        GOOGLE_API_KEYS = [single]
GOOGLE_API_KEY = GOOGLE_API_KEYS[0] if GOOGLE_API_KEYS else ""

# ══════════════════════════════════════════════════════════════════════════════
# 🚀 GROQ API KEYS — الأولوية الثالثة (9 مفاتيح)
# ══════════════════════════════════════════════════════════════════════════════
GROQ_API_KEYS: list[str] = []
for i in range(1, 10):
    key = os.getenv(f"GROQ_API_KEY_{i}", "").strip()
    if key:
        GROQ_API_KEYS.append(key)
if not GROQ_API_KEYS:
    single = os.getenv("GROQ_API_KEY", "").strip()
    if single:
        GROQ_API_KEYS = [single]
GROQ_API_KEY = GROQ_API_KEYS[0] if GROQ_API_KEYS else ""

# ══════════════════════════════════════════════════════════════════════════════
# 🌐 OPENROUTER API KEYS — الأولوية الرابعة (9 مفاتيح)
# ══════════════════════════════════════════════════════════════════════════════
OPENROUTER_API_KEYS: list[str] = []
for i in range(1, 10):
    key = os.getenv(f"OPENROUTER_API_KEY_{i}", "").strip()
    if key:
        OPENROUTER_API_KEYS.append(key)
if not OPENROUTER_API_KEYS:
    single = os.getenv("OPENROUTER_API_KEY", "").strip()
    if single:
        OPENROUTER_API_KEYS = [single]
OPENROUTER_API_KEY = OPENROUTER_API_KEYS[0] if OPENROUTER_API_KEYS else ""

# ══════════════════════════════════════════════════════════════════════════════
# 🎙️ ELEVENLABS API KEYS — Voice (9 مفاتيح)
# ══════════════════════════════════════════════════════════════════════════════
ELEVENLABS_API_KEYS: list[str] = []
for i in range(1, 10):
    key = os.getenv(f"ELEVENLABS_API_KEY_{i}", "").strip()
    if key:
        ELEVENLABS_API_KEYS.append(key)
if not ELEVENLABS_API_KEYS:
    single = os.getenv("ELEVENLABS_API_KEY", "").strip()
    if single:
        ELEVENLABS_API_KEYS = [single]
ELEVENLABS_API_KEY = ELEVENLABS_API_KEYS[0] if ELEVENLABS_API_KEYS else ""

# ══════════════════════════════════════════════════════════════════════════════
# 🖼️ STABILITY AI / REPLICATE — للصور المجانية
# ══════════════════════════════════════════════════════════════════════════════
STABILITY_API_KEYS: list[str] = []
for i in range(1, 10):
    key = os.getenv(f"STABILITY_API_KEY_{i}", "").strip()
    if key:
        STABILITY_API_KEYS.append(key)
if not STABILITY_API_KEYS:
    single = os.getenv("STABILITY_API_KEY", "").strip()
    if single:
        STABILITY_API_KEYS = [single]

REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN", "").strip()

# ══════════════════════════════════════════════════════════════════════════════
# تحذيرات
# ══════════════════════════════════════════════════════════════════════════════
if not TELEGRAM_BOT_TOKEN:
    print("⚠️ WARNING: TELEGRAM_BOT_TOKEN not set", file=sys.stderr)
if not DEEPSEEK_API_KEYS:
    print("⚠️ WARNING: No DeepSeek keys — get keys from platform.deepseek.com", file=sys.stderr)
if not GOOGLE_API_KEYS:
    print("⚠️ WARNING: No Google API keys — get free keys from aistudio.google.com", file=sys.stderr)
if not ELEVENLABS_API_KEYS:
    print("⚠️ WARNING: No ElevenLabs keys — voice will use gTTS fallback", file=sys.stderr)

DATABASE_URL = os.getenv("DATABASE_URL", "")

OWNER_ID = 7021542402
BOT_USERNAME = "@zakros_probot"
FREE_ATTEMPTS = 1
PAID_ATTEMPTS = 7
REFERRAL_POINTS_PER_INVITE = 0.1
REFERRAL_POINTS_PER_ATTEMPT = 1.0
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
