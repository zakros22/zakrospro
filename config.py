# config.py
# -*- coding: utf-8 -*-
"""
ملف الإعدادات المركزي لبوت المحاضرات الطبية
يقوم بتحميل المتغيرات من ملف .env ومن بيئة النظام، ويوفر كائن Config موحد
"""

import os
import sys
import logging
from pathlib import Path
from typing import Dict, Optional

# محاولة تحميل مكتبة dotenv، إذا لم تكن موجودة نستمر بدونها
try:
    from dotenv import load_dotenv
    # تحميل المتغيرات من ملف .env إذا كان موجوداً
    env_path = Path(__file__).parent / '.env'
    if env_path.exists():
        load_dotenv(dotenv_path=env_path)
        print(f"✅ تم تحميل الإعدادات من: {env_path}")
    else:
        load_dotenv()  # يحاول تحميل .env من المسار الحالي
        print("ℹ️ لم يتم العثور على ملف .env، استخدام متغيرات بيئة النظام فقط")
except ImportError:
    print("⚠️ مكتبة python-dotenv غير مثبتة. يرجى تثبيتها: pip install python-dotenv")
    # نستمر بدون تحميل .env

class Config:
    """فئة تحوي جميع إعدادات البوت"""

    # ========== إعدادات البوت الأساسية ==========
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
    OWNER_ID: int = int(os.getenv("OWNER_ID", "7021542402"))  # معرف المالك

    # ========== مفاتيح الذكاء الاصطناعي ==========
    DEEPSEEK_API_KEY: str = os.getenv("DEEPSEEK_API_KEY", "")
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")

    # للتعامل مع مفاتيح متعددة مفصولة بفواصل (للاحتياط)
    DEEPSEEK_KEYS: list = [k.strip() for k in DEEPSEEK_API_KEY.split(",") if k.strip()]
    GEMINI_KEYS: list = [k.strip() for k in GEMINI_API_KEY.split(",") if k.strip()]
    GROQ_KEYS: list = [k.strip() for k in GROQ_API_KEY.split(",") if k.strip()]

    # ========== إعدادات قاعدة البيانات ==========
    DATABASE_URL: str = os.getenv("DATABASE_URL", "")
    # إذا كان الرابط يبدأ بـ postgres:// نستبدلها بـ postgresql:// ليتوافق مع بعض المكتبات
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

    # ========== إعدادات Webhook (لـ Heroku) ==========
    WEBHOOK_URL: str = os.getenv("WEBHOOK_URL", "")
    PORT: int = int(os.getenv("PORT", "5000"))
    WEBHOOK_PATH: str = f"/webhook/{BOT_TOKEN}" if BOT_TOKEN else "/webhook"

    # ========== حدود الاستخدام والخطط ==========
    FREE_ATTEMPTS: int = int(os.getenv("FREE_ATTEMPTS", "3"))
    REFERRAL_POINTS_REQUIRED: int = int(os.getenv("REFERRAL_POINTS_REQUIRED", "10"))
    REFERRAL_POINTS_PER_REFERRAL: int = int(os.getenv("REFERRAL_POINTS_PER_REFERRAL", "1"))

    # أسعار الاشتراكات (بالدولار)
    SUBSCRIPTION_PRICES: Dict[str, float] = {
        "1_month": float(os.getenv("PRICE_1M", "9.99")),
        "3_months": float(os.getenv("PRICE_3M", "24.99")),
        "12_months": float(os.getenv("PRICE_12M", "79.99")),
        "unlimited": float(os.getenv("PRICE_UNLIMITED", "149.99"))
    }

    # عدد المحاولات لكل خطة
    ATTEMPTS_PER_PLAN: Dict[str, int] = {
        "1_month": int(os.getenv("ATTEMPTS_1M", "30")),
        "3_months": int(os.getenv("ATTEMPTS_3M", "100")),
        "12_months": int(os.getenv("ATTEMPTS_12M", "500")),
        "unlimited": int(os.getenv("ATTEMPTS_UNLIMITED", "999999"))
    }

    # ========== معلومات الدفع ==========
    PAYMENT_METHODS: Dict[str, str] = {
        "mastercard": os.getenv("MASTERCARD_ACCOUNT", ""),
        "ton_usdt": os.getenv("TON_USDT_WALLET", ""),
        "btc": os.getenv("BTC_WALLET", ""),
    }

    # دعم نجوم تيليجرام
    TELEGRAM_STARS_ENABLED: bool = os.getenv("TELEGRAM_STARS_ENABLED", "true").lower() == "true"
    STARS_PRICE_1M: int = int(os.getenv("STARS_PRICE_1M", "100"))
    STARS_PRICE_3M: int = int(os.getenv("STARS_PRICE_3M", "250"))
    STARS_PRICE_12M: int = int(os.getenv("STARS_PRICE_12M", "800"))
    STARS_PRICE_UNLIMITED: int = int(os.getenv("STARS_PRICE_UNLIMITED", "1500"))

    # ========== العلامة المائية والإعدادات البصرية ==========
    WATERMARK_TEXT: str = os.getenv("WATERMARK_TEXT", "© Medical Lecture Bot - جميع الحقوق محفوظة")
    BOT_NAME: str = os.getenv("BOT_NAME", "Medical Lecture Bot")
    BOT_LOGO_URL: str = os.getenv("BOT_LOGO_URL", "")

    # ========== إعدادات الملفات المؤقتة ==========
    TMP_DIR: Path = Path("tmp/telegram_bot")
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    # مجلدات فرعية للتنظيم
    PDF_TMP: Path = TMP_DIR / "pdf"
    IMAGES_TMP: Path = TMP_DIR / "images"
    AUDIO_TMP: Path = TMP_DIR / "audio"
    VIDEO_TMP: Path = TMP_DIR / "video"
    for d in [PDF_TMP, IMAGES_TMP, AUDIO_TMP, VIDEO_TMP]:
        d.mkdir(parents=True, exist_ok=True)

    # ========== حدود المحتوى ==========
    MAX_TEXT_LENGTH: int = int(os.getenv("MAX_TEXT_LENGTH", "50000"))
    MIN_TEXT_LENGTH: int = int(os.getenv("MIN_TEXT_LENGTH", "100"))
    MAX_PDF_SIZE_MB: int = int(os.getenv("MAX_PDF_SIZE_MB", "20"))
    MAX_PDF_PAGES: int = int(os.getenv("MAX_PDF_PAGES", "100"))

    # ========== إعدادات الفيديو ==========
    VIDEO_WIDTH: int = int(os.getenv("VIDEO_WIDTH", "854"))
    VIDEO_HEIGHT: int = int(os.getenv("VIDEO_HEIGHT", "480"))
    VIDEO_FPS: int = int(os.getenv("VIDEO_FPS", "24"))
    VIDEO_BITRATE: str = os.getenv("VIDEO_BITRATE", "1000k")
    AUDIO_BITRATE: str = os.getenv("AUDIO_BITRATE", "128k")

    # مدة كل شريحة (بالثواني) - افتراضية وقابلة للتعديل
    WELCOME_DURATION: float = 3.5
    TITLE_DURATION: float = 4.0
    MAP_DURATION: float = 5.0
    SECTION_TITLE_DURATION: float = 3.0
    SUMMARY_DURATION: float = 6.0

    # ========== إعدادات اللغة واللهجات ==========
    SUPPORTED_LANGUAGES: list = ["ar", "en"]
    DEFAULT_LANGUAGE: str = "ar"
    DIALECTS: Dict[str, str] = {
        "iraqi": "اللهجة العراقية",
        "egyptian": "اللهجة المصرية",
        "levantine": "اللهجة الشامية",
        "gulf": "اللهجة الخليجية",
        "fusha": "العربية الفصحى"
    }
    DEFAULT_DIALECT: str = "fusha"

    # ========== التخصصات الطبية ==========
    MEDICAL_SPECIALTIES: Dict[str, str] = {
        "cardiology": "أمراض القلب",
        "pulmonology": "أمراض الصدر",
        "neurology": "الأعصاب",
        "gastroenterology": "الجهاز الهضمي",
        "nephrology": "الكلى",
        "endocrinology": "الغدد الصماء",
        "hematology": "أمراض الدم",
        "oncology": "الأورام",
        "rheumatology": "الروماتيزم",
        "dermatology": "الأمراض الجلدية",
        "ophthalmology": "طب العيون",
        "ent": "الأنف والأذن والحنجرة",
        "pediatrics": "طب الأطفال",
        "gynecology": "أمراض النساء والتوليد",
        "urology": "المسالك البولية",
        "orthopedics": "جراحة العظام",
        "psychiatry": "الطب النفسي",
        "emergency": "طب الطوارئ",
        "general": "طب عام",
        "anatomy": "علم التشريح",
        "physiology": "علم وظائف الأعضاء",
        "pathology": "علم الأمراض",
        "pharmacology": "علم الأدوية",
        "microbiology": "علم الأحياء الدقيقة",
    }

    # التخصصات الفرعية (يمكن توسيعها)
    SUB_SPECIALTIES: Dict[str, Dict[str, str]] = {
        "cardiology": {
            "interventional": "القسطرة التداخلية",
            "electrophysiology": "كهرباء القلب",
            "heart_failure": "فشل القلب",
            "preventive": "الوقاية",
        },
        "neurology": {
            "stroke": "الجلطات الدماغية",
            "epilepsy": "الصرع",
            "movement_disorders": "اضطرابات الحركة",
            "neuromuscular": "الأمراض العصبية العضلية",
        },
        # ... باقي التخصصات
    }

    # المراحل الدراسية
    EDUCATION_LEVELS: Dict[str, str] = {
        "undergraduate": "طالب بكالوريوس",
        "postgraduate": "طالب دراسات عليا",
        "resident": "طبيب مقيم",
        "specialist": "أخصائي",
        "consultant": "استشاري",
        "public": "تثقيف عام",
    }

    # ========== إعدادات الذكاء الاصطناعي ==========
    AI_TIMEOUT: int = int(os.getenv("AI_TIMEOUT", "60"))  # ثواني
    AI_MAX_RETRIES: int = int(os.getenv("AI_MAX_RETRIES", "3"))
    AI_TEMPERATURE: float = float(os.getenv("AI_TEMPERATURE", "0.7"))
    AI_MAX_TOKENS: int = int(os.getenv("AI_MAX_TOKENS", "4096"))

    # ========== إعدادات الصور ==========
    IMAGE_SOURCES: list = ["pollinations", "unsplash", "picsum", "generated"]
    UNSPLASH_ACCESS_KEY: str = os.getenv("UNSPLASH_ACCESS_KEY", "")
    PEXELS_API_KEY: str = os.getenv("PEXELS_API_KEY", "")

    # ========== إعدادات الصوت ==========
    GTTS_LANG_MAP: Dict[str, str] = {
        "iraqi": "ar",
        "egyptian": "ar",
        "levantine": "ar",
        "gulf": "ar",
        "fusha": "ar",
        "english": "en"
    }
    GTTS_TLD: str = "com"  # نطاق Google المستخدم

    # ========== إعدادات التخزين المؤقت والتنظيف ==========
    AUTO_CLEANUP_AFTER_HOURS: int = int(os.getenv("AUTO_CLEANUP_HOURS", "24"))
    MAX_CONCURRENT_VIDEO_TASKS: int = int(os.getenv("MAX_CONCURRENT_VIDEO", "2"))

    # ========== إعدادات التسجيل ==========
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    LOG_FILE: Path = TMP_DIR / "bot.log"

    # ========== دوال مساعدة ==========
    @classmethod
    def validate(cls) -> bool:
        """التحقق من وجود الإعدادات الضرورية"""
        errors = []
        warnings = []

        if not cls.BOT_TOKEN:
            errors.append("❌ BOT_TOKEN غير موجود! يجب تعيين توكن البوت.")
        if not cls.OWNER_ID:
            errors.append("❌ OWNER_ID غير موجود! يجب تعيين معرف المالك.")

        # تحذيرات للمفاتيح الاختيارية ولكنها مهمة
        if not cls.DEEPSEEK_API_KEY and not cls.GEMINI_API_KEY and not cls.GROQ_API_KEY:
            warnings.append("⚠️ لم يتم تعيين أي مفتاح AI. سيعمل البوت بوضع محدود (محتوى احتياطي فقط).")
        if not cls.DATABASE_URL:
            warnings.append("⚠️ DATABASE_URL غير موجود. لن يتم حفظ البيانات.")

        if errors:
            print("\n".join(errors))
            return False

        if warnings:
            print("\n".join(warnings))

        return True

    @classmethod
    def get_ai_keys(cls, provider: str) -> list:
        """إرجاع قائمة المفاتيح لمزود معين"""
        if provider.lower() == "deepseek":
            return cls.DEEPSEEK_KEYS
        elif provider.lower() == "gemini":
            return cls.GEMINI_KEYS
        elif provider.lower() == "groq":
            return cls.GROQ_KEYS
        return []

    @classmethod
    def get_subscription_price_stars(cls, plan: str) -> int:
        """إرجاع سعر الخطة بنجوم تيليجرام"""
        mapping = {
            "1_month": cls.STARS_PRICE_1M,
            "3_months": cls.STARS_PRICE_3M,
            "12_months": cls.STARS_PRICE_12M,
            "unlimited": cls.STARS_PRICE_UNLIMITED
        }
        return mapping.get(plan, 0)

    @classmethod
    def get_subscription_price_usd(cls, plan: str) -> float:
        """إرجاع سعر الخطة بالدولار"""
        return cls.SUBSCRIPTION_PRICES.get(plan, 0.0)


# ========== إعداد التسجيل (Logging) ==========
def setup_logging():
    """تهيئة نظام التسجيل"""
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    logging.basicConfig(
        level=getattr(logging, Config.LOG_LEVEL),
        format=log_format,
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(Config.LOG_FILE, encoding='utf-8')
        ]
    )
    # تقليل مستوى تسجيل المكتبات الخارجية
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("PIL").setLevel(logging.WARNING)


# تهيئة التسجيل
setup_logging()
logger = logging.getLogger(__name__)

# إنشاء نسخة من الإعدادات للاستخدام في باقي الملفات
config = Config()

# طباعة معلومات البدء
if __name__ == "__main__":
    print("=== إعدادات بوت المحاضرات الطبية ===")
    print(f"المالك ID: {config.OWNER_ID}")
    print(f"المحاولات المجانية: {config.FREE_ATTEMPTS}")
    print(f"عدد التخصصات المدعومة: {len(config.MEDICAL_SPECIALTIES)}")
    print(f"مجلد الملفات المؤقتة: {config.TMP_DIR}")
    valid = config.validate()
    print(f"حالة الإعدادات: {'✅ صالحة' if valid else '❌ تحتاج تصحيح'}")
