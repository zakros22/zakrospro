# -*- coding: utf-8 -*-
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

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL", "")
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
GOOGLE_API_KEYS = os.getenv("GOOGLE_API_KEYS", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_API_KEYS = os.getenv("GROQ_API_KEYS", "")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
ELEVENLABS_API_KEYS = os.getenv("ELEVENLABS_API_KEYS", "")

OWNER_ID = int(os.getenv("OWNER_ID", "7021542402"))
OWNER_USERNAME = os.getenv("OWNER_USERNAME", "@zakros22bot")

FREE_ATTEMPTS = int(os.getenv("FREE_ATTEMPTS", "3"))
PAID_ATTEMPTS = int(os.getenv("PAID_ATTEMPTS", "10"))

REFERRAL_POINTS_PER_INVITE = 0.1
REFERRAL_POINTS_PER_ATTEMPT = 1.0

MASTERCARD_NUMBER = os.getenv("MASTERCARD_NUMBER", "")
MASTERCARD_PRICE = int(os.getenv("MASTERCARD_PRICE", "4"))
TON_WALLET = os.getenv("TON_WALLET", "")
TRC20_WALLET = os.getenv("TRC20_WALLET", "")
TELEGRAM_STARS_PRICE = int(os.getenv("TELEGRAM_STARS_PRICE", "50"))

WATERMARK_TEXT = "@zakros_probot"
TEMP_DIR = "/tmp/telegram_bot"
os.makedirs(TEMP_DIR, exist_ok=True)

if not TELEGRAM_BOT_TOKEN:
    print("WARNING: TELEGRAM_BOT_TOKEN not set", file=sys.stderr)
