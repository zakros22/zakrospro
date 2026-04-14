import os
import sys

# =============================================================================
# 1. تحميل .env (اختياري للتطوير المحلي)
# =============================================================================
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

# =============================================================================
# 2. تيليجرام
# =============================================================================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TELEGRAM_BOT_TOKEN:
    print("❌ خطأ: TELEGRAM_BOT_TOKEN غير مضبوط في متغيرات البيئة", file=sys.stderr)
    sys.exit(1)

# =============================================================================
# 3. قاعدة البيانات
# =============================================================================
DATABASE_URL = os.getenv("DATABASE_URL", "")
if not DATABASE_URL:
    print("❌ خطأ: DATABASE_URL غير مضبوط في متغيرات البيئة", file=sys.stderr)
    sys.exit(1)

# =============================================================================
# 4. لوحة التحكم والإعدادات العامة
# =============================================================================
OWNER_ID = int(os.getenv("OWNER_ID", "7021542402"))
OWNER_USERNAME = os.getenv("OWNER_USERNAME", "@zakros22bot")

FREE_ATTEMPTS = int(os.getenv("FREE_ATTEMPTS", "1"))
PAID_ATTEMPTS = int(os.getenv("PAID_ATTEMPTS", "7"))

MASTERCARD_NUMBER = os.getenv("MASTERCARD_NUMBER", "4272128655")
MASTERCARD_PRICE = int(os.getenv("MASTERCARD_PRICE", "4"))
TON_WALLET = os.getenv("TON_WALLET", "UQBpVo1V-ZhWpJi5YzoyQeX5fWuVwNq8KgcxXJWPq1ideEeD")
TRC20_WALLET = os.getenv("TRC20_WALLET", "TNbYTFmtoAr2CH3YYgxhCMZ3YNXNm9QLcq")
TELEGRAM_STARS_PRICE = int(os.getenv("TELEGRAM_STARS_PRICE", "50"))

REFERRAL_POINTS_PER_INVITE = float(os.getenv("REFERRAL_POINTS_PER_INVITE", "0.1"))
REFERRAL_POINTS_PER_ATTEMPT = float(os.getenv("REFERRAL_POINTS_PER_ATTEMPT", "1.0"))

WATERMARK_TEXT = os.getenv("WATERMARK_TEXT", "@zakros_probot")

# =============================================================================
# 5. تجميع المفاتيح (يدعم: مفتاح واحد، قائمة مفصولة بفواصل، مفاتيح مرقمة _1.._9)
# =============================================================================
def _collect_keys(env_names: list[str]) -> list[str]:
    """جمع المفاتيح من متغيرات البيئة وإرجاع قائمة بدون تكرار."""
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

# --- DeepSeek API Keys (الأولوية الأولى للتحليل) ---
_raw_deepseek = _collect_keys(["DEEPSEEK_API_KEY", "DEEPSEEK_API_KEYS"])
for i in range(1, 10):
    k = os.getenv(f"DEEPSEEK_API_KEY_{i}", "").strip()
    if k and k not in _raw_deepseek:
        _raw_deepseek.append(k)
DEEPSEEK_API_KEYS = _raw_deepseek

# --- Gemini API Keys (الأولوية الثانية للتحليل) ---
_raw_gemini = _collect_keys(["GOOGLE_API_KEY", "GOOGLE_API_KEYS", "GEMINI_API_KEY", "GEMINI_API_KEYS"])
for i in range(1, 10):
    k = os.getenv(f"GOOGLE_API_KEY_{i}", "") or os.getenv(f"GEMINI_API_KEY_{i}", "")
    if k.strip() and k.strip() not in _raw_gemini:
        _raw_gemini.append(k.strip())
GEMINI_API_KEYS = _raw_gemini
GOOGLE_API_KEY = GEMINI_API_KEYS[0] if GEMINI_API_KEYS else ""   # للتوافق مع الأكواد القديمة

# --- OpenRouter API Keys (الأولوية الثالثة للتحليل) ---
_raw_openrouter = _collect_keys(["OPENROUTER_API_KEY", "OPENROUTER_API_KEYS"])
for i in range(1, 10):
    k = os.getenv(f"OPENROUTER_API_KEY_{i}", "").strip()
    if k and k not in _raw_openrouter:
        _raw_openrouter.append(k)
OPENROUTER_API_KEYS = _raw_openrouter

# --- Groq API Keys (احتياطي أخير للتحليل) ---
_raw_groq = _collect_keys(["GROQ_API_KEY", "GROQ_API_KEYS"])
for i in range(1, 10):
    k = os.getenv(f"GROQ_API_KEY_{i}", "").strip()
    if k and k not in _raw_groq:
        _raw_groq.append(k)
GROQ_API_KEYS = _raw_groq

# --- ElevenLabs API Keys (توليد الصوت) ---
_raw_elevenlabs = _collect_keys(["ELEVENLABS_API_KEY", "ELEVENLABS_API_KEYS"])
for i in range(1, 10):
    k = os.getenv(f"ELEVENLABS_API_KEY_{i}", "").strip()
    if k and k not in _raw_elevenlabs:
        _raw_elevenlabs.append(k)
ELEVENLABS_API_KEYS = _raw_elevenlabs

# --- OpenAI API Key (لتوليد الصور DALL-E) ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()

# =============================================================================
# 6. التحقق من المفاتيح وعرض تحذيرات
# =============================================================================
print("=" * 60)
print("📋 حالة المفاتيح:")
print(f"   🔷 DeepSeek: {len(DEEPSEEK_API_KEYS)} مفتاح")
print(f"   🔶 Gemini: {len(GEMINI_API_KEYS)} مفتاح")
print(f"   🌐 OpenRouter: {len(OPENROUTER_API_KEYS)} مفتاح")
print(f"   ⚡ Groq: {len(GROQ_API_KEYS)} مفتاح")
print(f"   🔊 ElevenLabs: {len(ELEVENLABS_API_KEYS)} مفتاح")
print(f"   🎨 OpenAI (DALL-E): {'✅ موجود' if OPENAI_API_KEY else '❌ غير مضبوط'}")
if not DEEPSEEK_API_KEYS and not GEMINI_API_KEYS and not OPENROUTER_API_KEYS:
    print("⚠️  تحذير: لا توجد أي مفاتيح للتحليل (DeepSeek/Gemini/OpenRouter). البوت لن يعمل!")
print("=" * 60)

# =============================================================================
# 7. إعدادات الأصوات (Voice IDs)
# =============================================================================
VOICES = {
    "iraq":   {"name": "🇮🇶 عراقي", "voice_id": "TX3LPaxmHKxFdv7VOQHJ"},
    "egypt":  {"name": "🇪🇬 مصري", "voice_id": "AZnzlk1XvdvUeBnXmlld"},
    "syria":  {"name": "🇸🇾 سوري", "voice_id": "21m00Tcm4TlvDq8ikWAM"},
    "gulf":   {"name": "🇸🇦 خليجي", "voice_id": "EXAVITQu4vr4xnSDxMaL"},
    "msa":    {"name": "📚 فصحى", "voice_id": "pNInz6obpgDQGcFmaJgB"},
    "english":{"name": "🇺🇸 English", "voice_id": "9BWtsMINqrJLrRacOk9x"},
    "british":{"name": "🇬🇧 British", "voice_id": "CwhRBWXzGAHq8TQ4Fs17"},
}

# =============================================================================
# 8. المجلدات المؤقتة
# =============================================================================
TEMP_DIR = "/tmp/telegram_bot"
os.makedirs(TEMP_DIR, exist_ok=True)
