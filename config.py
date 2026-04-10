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

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL", "")

# API Keys
GOOGLE_API_KEYS = [k.strip() for k in os.getenv("GOOGLE_API_KEYS", "").split(",") if k.strip()]
GROQ_API_KEYS = [k.strip() for k in os.getenv("GROQ_API_KEYS", "").split(",") if k.strip()]
OPENROUTER_API_KEYS = [k.strip() for k in os.getenv("OPENROUTER_API_KEYS", "").split(",") if k.strip()]
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

OWNER_ID = int(os.getenv("OWNER_ID", "7021542402"))
FREE_ATTEMPTS = 1
PAID_ATTEMPTS = 7

TEMP_DIR = "/tmp/telegram_bot"
os.makedirs(TEMP_DIR, exist_ok=True)

VOICES = {
    "iraq": {"name": "🇮🇶 عراقي", "voice_id": "iraq"},
    "egypt": {"name": "🇪🇬 مصري", "voice_id": "egypt"},
    "syria": {"name": "🇸🇾 شامي", "voice_id": "syria"},
    "gulf": {"name": "🇸🇦 خليجي", "voice_id": "gulf"},
    "msa": {"name": "📚 فصحى", "voice_id": "msa"},
    "english": {"name": "🇺🇸 English", "voice_id": "english"},
    "british": {"name": "🇬🇧 British", "voice_id": "british"},
}

WATERMARK = "@zakros_probot"
