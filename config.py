#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ملف الإعدادات والمتغيرات البيئية
يدعم تحميل المفاتيح من .env ومن متغيرات النظام
"""

import os
import sys

# ══════════════════════════════════════════════════════════════════════════════
#  تحميل ملف .env
# ══════════════════════════════════════════════════════════════════════════════
def _load_dotenv():
    """تحميل المتغيرات من ملف .env إذا وجد."""
    env_path = os.path.join(os.path.dirname(__file__), '.env')
    if os.path.exists(env_path):
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, val = line.split('=', 1)
                    key = key.strip()
                    val = val.strip()
                    if key and val:
                        # لا نعيد كتابة المتغيرات الموجودة
                        if key not in os.environ:
                            os.environ[key] = val

_load_dotenv()


# ══════════════════════════════════════════════════════════════════════════════
#  دالة جمع المفاتيح
# ══════════════════════════════════════════════════════════════════════════════
def _collect_keys(env_names: list) -> list:
    """جمع المفاتيح من متغيرات البيئة."""
    keys = []
    for name in env_names:
        val = os.getenv(name, "").strip()
        if val:
            if "," in val:
                keys.extend([k.strip() for k in val.split(",") if k.strip()])
            else:
                keys.append(val)
    
    # إزالة التكرار مع الحفاظ على الترتيب
    seen = set()
    unique = []
    for k in keys:
        if k not in seen:
            seen.add(k)
            unique.append(k)
    return unique


# ══════════════════════════════════════════════════════════════════════════════
#  تيليجرام
# ══════════════════════════════════════════════════════════════════════════════
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
if not TELEGRAM_BOT_TOKEN:
    print("❌ خطأ: TELEGRAM_BOT_TOKEN غير مضبوط في متغيرات البيئة")
    sys.exit(1)

# ══════════════════════════════════════════════════════════════════════════════
#  المالك
# ══════════════════════════════════════════════════════════════════════════════
OWNER_ID = int(os.getenv("OWNER_ID", "7021542402"))
OWNER_USERNAME = os.getenv("OWNER_USERNAME", "@zakros22bot")

# ══════════════════════════════════════════════════════════════════════════════
#  مفاتيح الذكاء الاصطناعي
# ══════════════════════════════════════════════════════════════════════════════
DEEPSEEK_API_KEYS = _collect_keys(["DEEPSEEK_API_KEY", "DEEPSEEK_API_KEYS"])
for i in range(1, 10):
    k = os.getenv(f"DEEPSEEK_API_KEY_{i}", "").strip()
    if k and k not in DEEPSEEK_API_KEYS:
        DEEPSEEK_API_KEYS.append(k)

GEMINI_API_KEYS = _collect_keys(["GOOGLE_API_KEY", "GOOGLE_API_KEYS", "GEMINI_API_KEY", "GEMINI_API_KEYS"])
for i in range(1, 10):
    k = os.getenv(f"GOOGLE_API_KEY_{i}", "") or os.getenv(f"GEMINI_API_KEY_{i}", "")
    if k.strip() and k.strip() not in GEMINI_API_KEYS:
        GEMINI_API_KEYS.append(k.strip())

OPENROUTER_API_KEYS = _collect_keys(["OPENROUTER_API_KEY", "OPENROUTER_API_KEYS"])
GROQ_API_KEYS = _collect_keys(["GROQ_API_KEY", "GROQ_API_KEYS"])

# ══════════════════════════════════════════════════════════════════════════════
#  مفاتيح الصوت والصور
# ══════════════════════════════════════════════════════════════════════════════
ELEVENLABS_API_KEYS = _collect_keys(["ELEVENLABS_API_KEY", "ELEVENLABS_API_KEYS"])
for i in range(1, 10):
    k = os.getenv(f"ELEVENLABS_API_KEY_{i}", "").strip()
    if k and k not in ELEVENLABS_API_KEYS:
        ELEVENLABS_API_KEYS.append(k)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()

# ══════════════════════════════════════════════════════════════════════════════
#  إعدادات الدفع
# ══════════════════════════════════════════════════════════════════════════════
FREE_ATTEMPTS = int(os.getenv("FREE_ATTEMPTS", "1"))
PAID_ATTEMPTS = int(os.getenv("PAID_ATTEMPTS", "7"))

MASTERCARD_NUMBER = os.getenv("MASTERCARD_NUMBER", "")
MASTERCARD_PRICE = int(os.getenv("MASTERCARD_PRICE", "4"))
TON_WALLET = os.getenv("TON_WALLET", "")
TRC20_WALLET = os.getenv("TRC20_WALLET", "")
TELEGRAM_STARS_PRICE = int(os.getenv("TELEGRAM_STARS_PRICE", "50"))

# ══════════════════════════════════════════════════════════════════════════════
#  إعدادات الإحالة
# ══════════════════════════════════════════════════════════════════════════════
REFERRAL_POINTS_PER_INVITE = float(os.getenv("REFERRAL_POINTS_PER_INVITE", "0.1"))
REFERRAL_POINTS_PER_ATTEMPT = float(os.getenv("REFERRAL_POINTS_PER_ATTEMPT", "1.0"))

# ══════════════════════════════════════════════════════════════════════════════
#  إعدادات عامة
# ══════════════════════════════════════════════════════════════════════════════
WATERMARK_TEXT = os.getenv("WATERMARK_TEXT", "@zakros_probot")
TEMP_DIR = "/tmp/telegram_bot"
os.makedirs(TEMP_DIR, exist_ok=True)

# ══════════════════════════════════════════════════════════════════════════════
#  إعدادات الأصوات (ElevenLabs Voice IDs)
# ══════════════════════════════════════════════════════════════════════════════
VOICES = {
    "iraq":   {"name": "🇮🇶 عراقي", "voice_id": "TX3LPaxmHKxFdv7VOQHJ"},
    "egypt":  {"name": "🇪🇬 مصري", "voice_id": "AZnzlk1XvdvUeBnXmlld"},
    "syria":  {"name": "🇸🇾 سوري", "voice_id": "21m00Tcm4TlvDq8ikWAM"},
    "gulf":   {"name": "🇸🇦 خليجي", "voice_id": "EXAVITQu4vr4xnSDxMaL"},
    "msa":    {"name": "📚 فصحى", "voice_id": "pNInz6obpgDQGcFmaJgB"},
    "english": {"name": "🇺🇸 English", "voice_id": "9BWtsMINqrJLrRacOk9x"},
    "british": {"name": "🇬🇧 British", "voice_id": "CwhRBWXzGAHq8TQ4Fs17"},
}

# ══════════════════════════════════════════════════════════════════════════════
#  عرض حالة المفاتيح
# ══════════════════════════════════════════════════════════════════════════════
print("=" * 60)
print("📋 حالة المفاتيح:")
print(f"   🤖 DeepSeek: {len(DEEPSEEK_API_KEYS)} مفتاح")
print(f"   🧠 Gemini: {len(GEMINI_API_KEYS)} مفتاح")
print(f"   🌐 OpenRouter: {len(OPENROUTER_API_KEYS)} مفتاح")
print(f"   ⚡ Groq: {len(GROQ_API_KEYS)} مفتاح")
print(f"   🔊 ElevenLabs: {len(ELEVENLABS_API_KEYS)} مفتاح")
print(f"   🎨 OpenAI: {'✅ موجود' if OPENAI_API_KEY else '❌ غير مضبوط'}")
print("=" * 60)
