import os
import sys


def _load_dotenv():
    """
    تحميل ملف .env إذا كان موجوداً.
    هذا يسمح لك بوضع المفاتيح السرية في ملف محلي بدلاً من متغيرات البيئة.
    """
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


# تحميل الملف فوراً عند استيراد الموديول
_load_dotenv()


# ============================================================
# 1. إعدادات تيليجرام الأساسية
# ============================================================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TELEGRAM_BOT_TOKEN:
    print("❌ خطأ: TELEGRAM_BOT_TOKEN غير موجود في متغيرات البيئة!", file=sys.stderr)
    sys.exit(1)

OWNER_ID = int(os.getenv("OWNER_ID", "7021542402"))
OWNER_USERNAME = os.getenv("OWNER_USERNAME", "@zakros22bot")

# ============================================================
# 2. قاعدة البيانات
# ============================================================
DATABASE_URL = os.getenv("DATABASE_URL", "")
if not DATABASE_URL:
    print("⚠️ تحذير: DATABASE_URL غير موجود. سيتم استخدام قاعدة بيانات محلية مؤقتة.", file=sys.stderr)

# ============================================================
# 3. مفاتيح APIs للذكاء الاصطناعي (نظام تبادل المفاتيح)
# ============================================================

# --- Google Gemini API (الأساسي) ---
# يدعم صيغ متعددة:
# - GOOGLE_API_KEY (مفتاح واحد)
# - GOOGLE_API_KEYS (مفاتيح متعددة مفصولة بفواصل)
# - GOOGLE_API_KEY_1, GOOGLE_API_KEY_2, ... GOOGLE_API_KEY_9
_raw_google = os.getenv("GOOGLE_API_KEYS", "") or os.getenv("GOOGLE_API_KEY", "")
_g_from_comma: list[str] = [k.strip() for k in _raw_google.split(",") if k.strip()]
_g_from_numbered: list[str] = [
    v for i in range(1, 10)
    if (v := os.getenv(f"GOOGLE_API_KEY_{i}", "")).strip()
]
# دمج جميع المفاتيح مع إزالة التكرار
_g_all = _g_from_comma + [k for k in _g_from_numbered if k not in _g_from_comma]
GOOGLE_API_KEYS: list[str] = _g_all
GOOGLE_API_KEY = GOOGLE_API_KEYS[0] if GOOGLE_API_KEYS else ""

if not GOOGLE_API_KEY:
    print("⚠️ تحذير: لا يوجد أي مفتاح Google API. التحليل قد لا يعمل.", file=sys.stderr)
else:
    print(f"✅ تم تحميل {len(GOOGLE_API_KEYS)} مفتاح Google API", file=sys.stderr)

# --- Groq API (بديل مجاني سريع) ---
_raw_groq = os.getenv("GROQ_API_KEYS", "") or os.getenv("GROQ_API_KEY", "")
_groq_from_comma: list[str] = [k.strip() for k in _raw_groq.split(",") if k.strip()]
_groq_from_numbered: list[str] = [
    v for i in range(1, 10)
    if (v := os.getenv(f"GROQ_API_KEY_{i}", "")).strip()
]
_groq_all = _groq_from_comma + [k for k in _groq_from_numbered if k not in _groq_from_comma]
GROQ_API_KEYS: list[str] = _groq_all
GROQ_API_KEY = GROQ_API_KEYS[0] if GROQ_API_KEYS else ""

if GROQ_API_KEYS:
    print(f"✅ تم تحميل {len(GROQ_API_KEYS)} مفتاح Groq API (بديل احتياطي)", file=sys.stderr)

# --- OpenRouter API (بديل ثاني - نماذج مجانية) ---
_raw_or = os.getenv("OPENROUTER_API_KEYS", "") or os.getenv("OPENROUTER_API_KEY", "")
_or_from_comma: list[str] = [k.strip() for k in _raw_or.split(",") if k.strip()]
_or_from_numbered: list[str] = [
    v for i in range(1, 10)
    if (v := os.getenv(f"OPENROUTER_API_KEY_{i}", "")).strip()
]
_or_all = _or_from_comma + [k for k in _or_from_numbered if k not in _or_from_comma]
OPENROUTER_API_KEYS: list[str] = _or_all
OPENROUTER_API_KEY = OPENROUTER_API_KEYS[0] if OPENROUTER_API_KEYS else ""

if OPENROUTER_API_KEYS:
    print(f"✅ تم تحميل {len(OPENROUTER_API_KEYS)} مفتاح OpenRouter API (بديل احتياطي ثاني)", file=sys.stderr)

# --- OpenAI API (لتوليد الصور DALL-E) ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
if OPENAI_API_KEY:
    print("✅ تم تحميل مفتاح OpenAI API (لتوليد الصور)", file=sys.stderr)

# --- ElevenLabs API (للصوت الاحترافي - اختياري) ---
_raw_el = os.getenv("ELEVENLABS_API_KEYS", "") or os.getenv("ELEVENLABS_API_KEY", "")
_el_from_comma: list[str] = [k.strip() for k in _raw_el.split(",") if k.strip()]
_el_from_numbered: list[str] = [
    v for i in range(1, 10)
    if (v := os.getenv(f"ELEVENLABS_API_KEY_{i}", "")).strip()
]
_el_all = _el_from_comma + [k for k in _el_from_numbered if k not in _el_from_comma]
ELEVENLABS_API_KEYS: list[str] = _el_all
ELEVENLABS_API_KEY = ELEVENLABS_API_KEYS[0] if ELEVENLABS_API_KEYS else ""

if ELEVENLABS_API_KEYS:
    print(f"✅ تم تحميل {len(ELEVENLABS_API_KEYS)} مفتاح ElevenLabs API (صوت احترافي)", file=sys.stderr)
else:
    print("ℹ️ لا توجد مفاتيح ElevenLabs. سيتم استخدام gTTS المجاني للصوت.", file=sys.stderr)

# --- Pexels و Pixabay (صور احتياطية مجانية) ---
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "")
PIXABAY_API_KEY = os.getenv("PIXABAY_API_KEY", "")

# ============================================================
# 4. إعدادات النظام والحدود
# ============================================================
FREE_ATTEMPTS = 1          # عدد المحاولات المجانية لكل مستخدم جديد
PAID_ATTEMPTS = 7          # عدد المحاولات المضافة عند الدفع

# نظام الإحالة
REFERRAL_POINTS_PER_INVITE = 0.1   # نقاط لكل شخص يدخل عبر الرابط
REFERRAL_POINTS_PER_ATTEMPT = 1.0  # نقاط مطلوبة للحصول على محاولة مجانية

# ============================================================
# 5. إعدادات الدفع
# ============================================================
MASTERCARD_NUMBER = os.getenv("MASTERCARD_NUMBER", "4272128655")
MASTERCARD_PRICE = 4
TON_WALLET = os.getenv("TON_WALLET", "UQBpVo1V-ZhWpJi5YzoyQeX5fWuVwNq8KgcxXJWPq1ideEeD")
TRC20_WALLET = os.getenv("TRC20_WALLET", "TNbYTFmtoAr2CH3YYgxhCMZ3YNXNm9QLcq")
TELEGRAM_STARS_PRICE = 50

# ============================================================
# 6. إعدادات الفيديو والعلامة المائية
# ============================================================
WATERMARK_TEXT = "@zakros_probot"
TEMP_DIR = "/tmp/telegram_bot"
os.makedirs(TEMP_DIR, exist_ok=True)

# ============================================================
# 7. إعدادات اللهجات والأصوات
# ============================================================
VOICES = {
    "iraq": {
        "name": "🇮🇶 عراقي",
        "voice_id": "TX3LPaxmHKxFdv7VOQHJ",
        "description": "لهجة عراقية أصيلة - صوت ذكوري دافئ"
    },
    "egypt": {
        "name": "🇪🇬 مصري",
        "voice_id": "AZnzlk1XvdvUeBnXmlld",
        "description": "لهجة مصرية مميزة - صوت واضح ومحبوب"
    },
    "syria": {
        "name": "🇸🇾 شامي",
        "voice_id": "21m00Tcm4TlvDq8ikWAM",
        "description": "لهجة شامية جميلة - صوت هادئ ورصين"
    },
    "gulf": {
        "name": "🇸🇦 خليجي",
        "voice_id": "EXAVITQu4vr4xnSDxMaL",
        "description": "لهجة خليجية راقية - صوت قوي ومؤثر"
    },
    "msa": {
        "name": "📚 فصحى",
        "voice_id": "pNInz6obpgDQGcFmaJgB",
        "description": "عربي فصيح - صوت أكاديمي محترف"
    },
    "english": {
        "name": "🇺🇸 English",
        "voice_id": "9BWtsMINqrJLrRacOk9x",
        "description": "Professional American English - Clear and engaging"
    },
    "british": {
        "name": "🇬🇧 British",
        "voice_id": "CwhRBWXzGAHq8TQ4Fs17",
        "description": "British English - Sophisticated and articulate"
    }
}

# ============================================================
# 8. أنواع المحاضرات المدعومة (للتخصص الدقيق)
# ============================================================
LECTURE_TYPES = {
    # الطب
    "medicine": "🩺 طب عام",
    "surgery": "🔪 جراحة",
    "pediatrics": "👶 طب أطفال",
    "dentistry": "🦷 طب أسنان",
    "pharmacy": "💊 صيدلة",
    "cardiology": "❤️ قلب",
    "neurology": "🧠 أعصاب",
    "dermatology": "🔬 جلدية",
    "ophthalmology": "👁️ عيون",
    "orthopedics": "🦴 عظام",
    
    # الهندسة
    "engineering": "⚙️ هندسة عامة",
    "civil": "🏗️ هندسة مدنية",
    "electrical": "⚡ هندسة كهربائية",
    "mechanical": "🔧 هندسة ميكانيكية",
    "aerospace": "🚀 هندسة فضاء",
    "software": "💻 هندسة برمجيات",
    "chemical": "🧪 هندسة كيميائية",
    "industrial": "🏭 هندسة صناعية",
    
    # العلوم
    "science": "🔬 علوم عامة",
    "physics": "⚛️ فيزياء",
    "chemistry": "🧪 كيمياء",
    "biology": "🧬 أحياء",
    "astronomy": "🌌 فلك",
    "geology": "🪨 جيولوجيا",
    "mathematics": "📐 رياضيات",
    
    # العلوم الإنسانية
    "literature": "📖 أدب",
    "history": "🏛️ تاريخ",
    "geography": "🌍 جغرافيا",
    "philosophy": "🤔 فلسفة",
    "psychology": "🧠 علم نفس",
    "sociology": "👥 علم اجتماع",
    "economics": "📊 اقتصاد",
    "law": "⚖️ قانون",
    "politics": "🏛️ سياسة",
    
    # العلوم الإسلامية
    "islamic": "🕌 علوم إسلامية",
    "quran": "📖 قرآن كريم",
    "hadith": "📜 حديث شريف",
    "fiqh": "📚 فقه",
    "aqeedah": "🕋 عقيدة",
    "tafseer": "📝 تفسير",
    "seerah": "🌟 سيرة",
    
    # المراحل الدراسية
    "primary": "🎒 ابتدائي",
    "middle": "📚 متوسط",
    "high": "🎓 إعدادي/ثانوي",
    "university": "🏛️ جامعي",
    
    # افتراضي
    "other": "📚 تعليمي عام"
}

# ============================================================
# 9. إعدادات الشخصية الكرتونية (الأفاتار)
# ============================================================
AVATAR_SETTINGS = {
    "medicine": {"gender": "male", "age": "adult", "style": "professional"},
    "surgery": {"gender": "male", "age": "adult", "style": "serious"},
    "pediatrics": {"gender": "female", "age": "adult", "style": "friendly"},
    "dentistry": {"gender": "male", "age": "adult", "style": "professional"},
    "engineering": {"gender": "male", "age": "adult", "style": "technical"},
    "science": {"gender": "female", "age": "adult", "style": "curious"},
    "math": {"gender": "male", "age": "adult", "style": "analytical"},
    "literature": {"gender": "female", "age": "adult", "style": "elegant"},
    "history": {"gender": "male", "age": "senior", "style": "wise"},
    "islamic": {"gender": "male", "age": "senior", "style": "scholarly"},
    "quran": {"gender": "male", "age": "senior", "style": "spiritual"},
    "primary": {"gender": "female", "age": "young", "style": "cheerful"},
    "middle": {"gender": "male", "age": "adult", "style": "encouraging"},
    "high": {"gender": "male", "age": "adult", "style": "academic"},
    "default": {"gender": "male", "age": "adult", "style": "neutral"}
}

# ============================================================
# 10. ألوان الفيديو حسب نوع المادة
# ============================================================
SUBJECT_COLORS = {
    # الطب - درجات الأخضر والأزرق
    "medicine": (21, 128, 61),
    "surgery": (185, 28, 28),
    "pediatrics": (255, 159, 67),
    "dentistry": (13, 71, 161),
    "pharmacy": (46, 125, 50),
    "cardiology": (220, 20, 60),
    "neurology": (75, 0, 130),
    
    # الهندسة - درجات البرتقالي والرمادي
    "engineering": (230, 126, 34),
    "civil": (121, 85, 72),
    "electrical": (255, 193, 7),
    "mechanical": (96, 125, 139),
    "aerospace": (33, 33, 33),
    "software": (41, 98, 255),
    "chemical": (0, 150, 136),
    
    # العلوم - درجات البنفسجي والأخضر
    "science": (46, 204, 113),
    "physics": (155, 89, 182),
    "chemistry": (231, 76, 60),
    "biology": (241, 196, 15),
    "astronomy": (26, 35, 126),
    "mathematics": (52, 73, 94),
    
    # العلوم الإنسانية - درجات دافئة
    "literature": (192, 57, 43),
    "history": (230, 126, 34),
    "geography": (39, 174, 96),
    "philosophy": (93, 64, 55),
    "psychology": (156, 39, 176),
    "economics": (0, 150, 136),
    
    # العلوم الإسلامية - درجات الأزرق والأخضر
    "islamic": (21, 101, 192),
    "quran": (46, 134, 222),
    "hadith": (41, 128, 185),
    "fiqh": (142, 68, 173),
    "aqeedah": (2, 119, 189),
    "tafseer": (26, 83, 92),
    "seerah": (183, 28, 28),
    
    # المراحل الدراسية - ألوان مبهجة
    "primary": (255, 107, 107),
    "middle": (78, 205, 196),
    "high": (255, 209, 102),
    "university": (52, 73, 94),
    
    # افتراضي
    "other": (100, 116, 139)
    }
