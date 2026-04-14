#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys

# ══════════════════════════════════════════════════════════════════════════════
#  تحميل المتغيرات من .env
# ══════════════════════════════════════════════════════════════════════════════
def load_env():
    env_path = os.path.join(os.path.dirname(__file__), '.env')
    if os.path.exists(env_path):
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, val = line.split('=', 1)
                    os.environ[key.strip()] = val.strip()

load_env()

# ══════════════════════════════════════════════════════════════════════════════
#  تيليجرام
# ══════════════════════════════════════════════════════════════════════════════
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
if not TELEGRAM_BOT_TOKEN:
    print("خطأ: TELEGRAM_BOT_TOKEN غير موجود")
    sys.exit(1)

# ══════════════════════════════════════════════════════════════════════════════
#  المالك
# ══════════════════════════════════════════════════════════════════════════════
OWNER_ID = int(os.getenv("OWNER_ID", "7021542402"))

# ══════════════════════════════════════════════════════════════════════════════
#  مفاتيح API
# ══════════════════════════════════════════════════════════════════════════════
def get_keys(name):
    val = os.getenv(name, "")
    return [k.strip() for k in val.split(",") if k.strip()]

DEEPSEEK_API_KEYS = get_keys("DEEPSEEK_API_KEYS")
GEMINI_API_KEYS = get_keys("GOOGLE_API_KEYS")
ELEVENLABS_API_KEYS = get_keys("ELEVENLABS_API_KEYS")

# ══════════════════════════════════════════════════════════════════════════════
#  إعدادات البوت
# ══════════════════════════════════════════════════════════════════════════════
FREE_ATTEMPTS = int(os.getenv("FREE_ATTEMPTS", "1"))
PAID_ATTEMPTS = int(os.getenv("PAID_ATTEMPTS", "7"))
WATERMARK = os.getenv("WATERMARK_TEXT", "@zakros_probot")

# مجلد مؤقت
TEMP_DIR = "/tmp/telegram_bot"
os.makedirs(TEMP_DIR, exist_ok=True)

print(f"✅ DeepSeek: {len(DEEPSEEK_API_KEYS)} | Gemini: {len(GEMINI_API_KEYS)}")
