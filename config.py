#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import sys

def _load_dotenv():
    env_path = os.path.join(os.path.dirname(__file__), '.env')
    if os.path.exists(env_path):
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, val = line.split('=', 1)
                    os.environ[key.strip()] = val.strip()
_load_dotenv()

def _collect_keys(*names):
    keys = []
    for name in names:
        val = os.getenv(name, "").strip()
        if val:
            if "," in val: keys.extend([k.strip() for k in val.split(",") if k.strip()])
            else: keys.append(val)
    seen = set()
    return [k for k in keys if not (k in seen or seen.add(k))]

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
OWNER_ID = int(os.getenv("OWNER_ID", "7021542402"))
FREE_ATTEMPTS = int(os.getenv("FREE_ATTEMPTS", "1"))
PAID_ATTEMPTS = int(os.getenv("PAID_ATTEMPTS", "7"))
TEMP_DIR = "/tmp/telegram_bot"
os.makedirs(TEMP_DIR, exist_ok=True)

DEEPSEEK_API_KEYS = _collect_keys("DEEPSEEK_API_KEY", "DEEPSEEK_API_KEYS")
GEMINI_API_KEYS = _collect_keys("GOOGLE_API_KEY", "GOOGLE_API_KEYS", "GEMINI_API_KEY", "GEMINI_API_KEYS")
OPENROUTER_API_KEYS = _collect_keys("OPENROUTER_API_KEY", "OPENROUTER_API_KEYS")
GROQ_API_KEYS = _collect_keys("GROQ_API_KEY", "GROQ_API_KEYS")
ELEVENLABS_API_KEYS = _collect_keys("ELEVENLABS_API_KEY", "ELEVENLABS_API_KEYS")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()

VOICES = {
    "iraq": {"name": "🇮🇶 عراقي", "voice_id": "TX3LPaxmHKxFdv7VOQHJ"},
    "egypt": {"name": "🇪🇬 مصري", "voice_id": "AZnzlk1XvdvUeBnXmlld"},
    "syria": {"name": "🇸🇾 سوري", "voice_id": "21m00Tcm4TlvDq8ikWAM"},
    "gulf": {"name": "🇸🇦 خليجي", "voice_id": "EXAVITQu4vr4xnSDxMaL"},
    "msa": {"name": "📚 فصحى", "voice_id": "pNInz6obpgDQGcFmaJgB"},
    "english": {"name": "🇺🇸 English", "voice_id": "9BWtsMINqrJLrRacOk9x"},
}

print(f"✅ DeepSeek: {len(DEEPSEEK_API_KEYS)} | Gemini: {len(GEMINI_API_KEYS)} | ElevenLabs: {len(ELEVENLABS_API_KEYS)}")
