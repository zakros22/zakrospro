#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys

# ══════════════════════════════════════════════════════════════════════════════
#  تحميل .env
# ══════════════════════════════════════════════════════════════════════════════
def _load_dotenv():
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

# ══════════════════════════════════════════════════════════════════════════════
#  تيليجرام
# ══════════════════════════════════════════════════════════════════════════════
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
if not TELEGRAM_BOT_TOKEN:
    print("❌ خطأ: TELEGRAM_BOT_TOKEN غير مضبوط")
    sys.exit(1)

# ══════════════════════════════════════════════════════════════════════════════
#  المالك
# ══════════════════════════════════════════════════════════════════════════════
OWNER_ID = int(os.getenv("OWNER_ID", "7021542402"))
OWNER_USERNAME = os.getenv("OWNER_USERNAME", "@zakros22bot")

# ══════════════════════════════════════════════════════════════════════════════
#  مفاتيح API
# ══════════════════════════════════════════════════════════════════════════════
def _parse_keys(env_var):
    val = os.getenv(env_var, "")
    if not val:
        return []
    return [k.strip() for k in val.split(",") if k.strip()]

DEEPSEEK_API_KEYS = _parse_keys("DEEPSEEK_API_KEYS")
GEMINI_API_KEYS = _parse_keys("GOOGLE_API_KEYS")
ELEVENLABS_API_KEYS = _parse_keys("ELEVENLABS_API_KEYS")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()

# ══════════════════════════════════════════════════════════════════════════════
#  إعدادات الدفع
# ══════════════════════════════════════════════════════════════════════════════
FREE_ATTEMPTS = int(os.getenv("FREE_ATTEMPTS", "1"))
PAID_ATTEMPTS = int(os.getenv("PAID_ATTEMPTS", "7"))

MASTERCARD_NUMBER = os.getenv("MASTERCARD_NUMBER", "4272128655")
MASTERCARD_PRICE = int(os.getenv("MASTERCARD_PRICE", "4"))
TON_WALLET = os.getenv("TON_WALLET", "")
TRC20_WALLET = os.getenv("TRC20_WALLET", "")
TELEGRAM_STARS_PRICE = int(os.getenv("TELEGRAM_STARS_PRICE", "50"))

REFERRAL_POINTS_PER_INVITE = float(os.getenv("REFERRAL_POINTS_PER_INVITE", "0.1"))
REFERRAL_POINTS_PER_ATTEMPT = float(os.getenv("REFERRAL_POINTS_PER_ATTEMPT", "1.0"))

WATERMARK_TEXT = os.getenv("WATERMARK_TEXT", "@zakros_probot")

# ══════════════════════════════════════════════════════════════════════════════
#  المجلدات المؤقتة
# ══════════════════════════════════════════════════════════════════════════════
TEMP_DIR = "/tmp/telegram_bot"
os.makedirs(TEMP_DIR, exist_ok=True)

# ══════════════════════════════════════════════════════════════════════════════
#  عرض حالة المفاتيح
# ══════════════════════════════════════════════════════════════════════════════
print("=" * 50)
print("📋 حالة المفاتيح:")
print(f"   🔷 DeepSeek: {len(DEEPSEEK_API_KEYS)} مفتاح")
print(f"   🔶 Gemini: {len(GEMINI_API_KEYS)} مفتاح")
print(f"   🔊 ElevenLabs: {len(ELEVENLABS_API_KEYS)} مفتاح")
print("=" * 50)
