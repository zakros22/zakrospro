import json
import sys
import json
import re
import io
import asyncio
import aiohttp
import os
from PIL import Image as PILImage, ImageDraw, ImageFont
from google import genai
from google.genai import types as genai_types
from config import (
    GOOGLE_API_KEY, GOOGLE_API_KEYS, GROQ_API_KEYS, 
    OPENROUTER_API_KEYS, OPENAI_API_KEY, SUBJECT_COLORS
)

# ============================================================
# API Key Pools
# ============================================================
_key_pool: list[str] = list(GOOGLE_API_KEYS) if GOOGLE_API_KEYS else ([GOOGLE_API_KEY] if GOOGLE_API_KEY else [])
_groq_pool: list[str] = list(GROQ_API_KEYS) if GROQ_API_KEYS else []
_or_pool: list[str] = list(OPENROUTER_API_KEYS) if OPENROUTER_API_KEYS else []

# ⭐═════════════════════════════════════════════════════════════════════════════
# DEEPSEEK API KEY POOL - الأولوية الأولى
# ⭐═════════════════════════════════════════════════════════════════════════════
_raw_ds = os.getenv("DEEPSEEK_API_KEYS", "") or os.getenv("DEEPSEEK_API_KEY", "")
_ds_from_comma: list[str] = [k.strip() for k in _raw_ds.split(",") if k.strip()]
_ds_from_numbered: list[str] = [
    v for i in range(1, 10)
    if (v := os.getenv(f"DEEPSEEK_API_KEY_{i}", "")).strip()
]
_deepseek_pool: list[str] = _ds_from_comma + [k for k in _ds_from_numbered if k not in _ds_from_comma]
DEEPSEEK_API_KEYS: list[str] = _deepseek_pool
DEEPSEEK_API_KEY = DEEPSEEK_API_KEYS[0] if DEEPSEEK_API_KEYS else ""

if DEEPSEEK_API_KEYS:
    print(f"✅ تم تحميل {len(DEEPSEEK_API_KEYS)} مفتاح DeepSeek API (الأولوية الأولى)", file=sys.stderr)
else:
    print("ℹ️ لا توجد مفاتيح DeepSeek. سيتم استخدام البدائل.", file=sys.stderr)

_key_clients: dict[str, object] = {}
_current_key_idx: int = 0
_current_ds_idx: int = 0  # مؤشر منفصل لـ DeepSeek


def _get_client(key: str | None = None):
    if not _key_pool:
        raise RuntimeError("GOOGLE_API_KEY غير مضبوط")
    use_key = key or _key_pool[_current_key_idx % len(_key_pool)]
    if use_key not in _key_clients:
        _key_clients[use_key] = genai.Client(api_key=use_key)
    return _key_clients[use_key]


class QuotaExhaustedError(Exception):
    pass


# ============================================================
# نماذج الذكاء الاصطناعي
# ============================================================
_DEEPSEEK_MODEL = "deepseek-chat"  # النموذج الرئيسي لـ DeepSeek
_GROQ_MODELS = ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "gemma2-9b-it"]
_OR_MODELS = [
    "openai/gpt-oss-120b:free",
    "nvidia/nemotron-3-super-120b-a12b:free",
    "openai/gpt-oss-20b:free",
    "liquid/lfm-2.5-1.2b-instruct:free",
    "deepseek/deepseek-chat:free",  # DeepSeek عبر OpenRouter كبديل إضافي
]


# ============================================================
# ⭐ DEEPSEEK - الأولوية الأولى ⭐
# ============================================================
async def _generate_with_deepseek(prompt: str, max_tokens: int = 8192) -> str:
    """
    استخدام DeepSeek API كأولوية أولى للتحليل والشرح.
    DeepSeek ممتاز في اللغة العربية والفهم العميق للنصوص.
    """
    global _current_ds_idx
    
    if not _deepseek_pool:
        raise QuotaExhaustedError("لا يوجد DEEPSEEK_API_KEY")
    
    for i in range(len(_deepseek_pool)):
        key_idx = (_current_ds_idx + i) % len(_deepseek_pool)
        key = _deepseek_pool[key_idx]
        
        try:
            headers = {
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "model": _DEEPSEEK_MODEL,
                "messages": [
                    {"role": "system", "content": "أنت معلم خبير ومتخصص في تبسيط المحاضرات التعليمية. تكتب بأسلوب واضح ومفصل مع دعم كامل للغة العربية."},
                    {"role": "user", "content": prompt}
                ],
                "max_tokens": min(max_tokens, 8192),
                "temperature": 0.3,
                "stream": False
            }
            
            async with aiohttp.ClientSession() as s:
                async with s.post(
                    "https://api.deepseek.com/v1/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=120)
                ) as r:
                    if r.status == 200:
                        data = await r.json()
                        _current_ds_idx = key_idx
                        content = data["choices"][0]["message"]["content"]
                        print(f"✅ DeepSeek success with key {key_idx+1}")
                        return content.strip()
                    elif r.status == 429:
                        print(f"⚠️ DeepSeek key {key_idx+1} rate limited")
                        continue
                    elif r.status == 401:
                        print(f"⚠️ DeepSeek key {key_idx+1} invalid")
                        continue
                    else:
                        body = await r.text()
                        print(f"⚠️ DeepSeek error {r.status}: {body[:100]}")
                        continue
                        
        except Exception as e:
            print(f"⚠️ DeepSeek key {key_idx+1} error: {str(e)[:50]}")
            continue
    
    raise QuotaExhaustedError("نفدت جميع مفاتيح DeepSeek")


# ============================================================
# Google Gemini - الأولوية الثانية
# ============================================================
async def _generate_with_gemini(prompt: str, max_tokens: int = 8192) -> str:
    """استخدام Google Gemini كأولوية ثانية"""
    global _current_key_idx
    gemini_models = ["gemini-2.0-flash", "gemini-2.0-flash-lite", "gemini-1.5-flash"]
    
    for i in range(len(_key_pool)):
        key_idx = (_current_key_idx + i) % len(_key_pool)
        key = _key_pool[key_idx]
        client = _get_client(key)
        
        for model in gemini_models:
            try:
                response = await asyncio.to_thread(
                    client.models.generate_content,
                    model=model,
                    contents=prompt,
                    config=genai_types.GenerateContentConfig(
                        temperature=0.3,
                        max_output_tokens=max_tokens
                    ),
                )
                _current_key_idx = key_idx
                print(f"✅ Gemini success: {model} with key {key_idx+1}")
                return response.text.strip()
            except Exception as e:
                err = str(e)
                if "429" in err or "quota" in err.lower() or "exhausted" in err.lower():
                    print(f"⚠️ Gemini key {key_idx+1} quota exhausted")
                    continue
                else:
                    print(f"⚠️ Gemini error: {err[:50]}")
                    continue
    
    raise QuotaExhaustedError("نفدت جميع مفاتيح Gemini")


# ============================================================
# Groq - الأولوية الثالثة
# ============================================================
async def _generate_with_groq(prompt: str, max_tokens: int = 8192) -> str:
    """استخدام Groq كأولوية ثالثة"""
    if not _groq_pool:
        raise QuotaExhaustedError("لا يوجد GROQ_API_KEY")
    
    for groq_key in _groq_pool:
        for model in _GROQ_MODELS:
            try:
                headers = {
                    "Authorization": f"Bearer {groq_key}",
                    "Content-Type": "application/json"
                }
                payload = {
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": min(max_tokens, 8192),
                    "temperature": 0.3
                }
                async with aiohttp.ClientSession() as s:
                    async with s.post(
                        "https://api.groq.com/openai/v1/chat/completions",
                        headers=headers,
                        json=payload,
                        timeout=aiohttp.ClientTimeout(total=60)
                    ) as r:
                        if r.status == 200:
                            data = await r.json()
                            print(f"✅ Groq success: {model}")
                            return data["choices"][0]["message"]["content"].strip()
            except Exception:
                continue
    
    raise QuotaExhaustedError("نفدت حصة Groq")


# ============================================================
# OpenRouter - الأولوية الرابعة (والأخيرة)
# ============================================================
async def _generate_with_openrouter(prompt: str, max_tokens: int = 8192) -> str:
    """استخدام OpenRouter كأولوية رابعة"""
    if not _or_pool:
        raise QuotaExhaustedError("لا يوجد OPENROUTER_API_KEY")
    
    for or_key in _or_pool:
        for model in _OR_MODELS:
            try:
                headers = {
                    "Authorization": f"Bearer {or_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://replit.com",
                    "X-Title": "ZAKROS PRO Lecture Bot"
                }
                payload = {
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": min(max_tokens, 8192),
                    "temperature": 0.3
                }
                async with aiohttp.ClientSession() as s:
                    async with s.post(
                        "https://openrouter.ai/api/v1/chat/completions",
                        headers=headers,
                        json=payload,
                        timeout=aiohttp.ClientTimeout(total=90)
                    ) as r:
                        if r.status == 200:
                            data = await r.json()
                            content = data["choices"][0]["message"]["content"]
                            if content and content.strip():
                                print(f"✅ OpenRouter success: {model}")
                                return content.strip()
            except Exception:
                continue
    
    raise QuotaExhaustedError("نفدت حصة OpenRouter")


# ============================================================
# نظام التوليد الذكي - DeepSeek أولاً
# ============================================================
async def _generate_with_rotation(prompt: str, max_output_tokens: int = 8192) -> str:
    """
    نظام تبادل المفاتيح الذكي:
    1. ⭐ DeepSeek (الأولوية الأولى - الأفضل للعربية والتحليل)
    2. Google Gemini (الأولوية الثانية)
    3. Groq (الأولوية الثالثة)
    4. OpenRouter (الأولوية الرابعة)
    """
    
    # ⭐ Phase 1: DeepSeek - الأولوية الأولى ⭐
    if _deepseek_pool:
        print("🔄 Trying DeepSeek (Priority 1)...")
        try:
            return await _generate_with_deepseek(prompt, max_output_tokens)
        except QuotaExhaustedError as e:
            print(f"⚠️ DeepSeek exhausted: {e}")
    
    # Phase 2: Google Gemini
    if _key_pool:
        print("🔄 Trying Google Gemini (Priority 2)...")
        try:
            return await _generate_with_gemini(prompt, max_output_tokens)
        except QuotaExhaustedError as e:
            print(f"⚠️ Gemini exhausted: {e}")
    
    # Phase 3: Groq
    if _groq_pool:
        print("🔄 Trying Groq (Priority 3)...")
        try:
            return await _generate_with_groq(prompt, max_output_tokens)
        except QuotaExhaustedError as e:
            print(f"⚠️ Groq exhausted: {e}")
    
    # Phase 4: OpenRouter
    if _or_pool:
        print("🔄 Trying OpenRouter (Priority 4)...")
        try:
            return await _generate_with_openrouter(prompt, max_output_tokens)
        except QuotaExhaustedError as e:
            print(f"⚠️ OpenRouter exhausted: {e}")
    
    raise QuotaExhaustedError("QUOTA_EXHAUSTED: جميع المفاتيح منتهية (DeepSeek, Gemini, Groq, OpenRouter)")


# ============================================================
# حساب حجم المحاضرة وعدد الأقسام
# ============================================================
def _compute_lecture_scale(text: str) -> tuple:
    """حساب عدد الأقسام بناءً على عدد الكلمات"""
    word_count = len(text.split())
    if word_count < 300:
        return 3, "6-8", 3000
    elif word_count < 800:
        return 4, "8-10", 5000
    elif word_count < 1500:
        return 5, "10-12", 6000
    elif word_count < 3000:
        return 6, "12-15", 7000
    else:
        return 7, "15-18", 8000


# ============================================================
# توجيهات التحليل حسب نوع المادة
# ============================================================
SUBJECT_INSTRUCTIONS = {
    # الطب
    "medicine": """
    - ركز على الجانب الطبي والتشريحي والوظائف الحيوية
    - استخدم مصطلحات طبية دقيقة
    - اشرح الأمراض والأعراض والعلاجات
    - اذكر آليات عمل الأدوية
    """,
    "surgery": """
    - ركز على الإجراءات الجراحية والتقنيات المستخدمة
    - اشرح خطوات العملية بالتفصيل
    - اذكر الأدوات الجراحية المستخدمة
    - نبه إلى المضاعفات المحتملة
    """,
    "pediatrics": """
    - استخدم أسلوباً لطيفاً مناسباً للأطفال
    - ركز على النمو والتطور
    - اشرح أمراض الأطفال الشائعة
    - اذكر التطعيمات وجداولها
    """,
    "dentistry": """
    - ركز على صحة الفم والأسنان
    - اشرح التركيبات السنية والإجراءات
    - اذكر أمراض اللثة والتسوس
    - تحدث عن العناية اليومية بالأسنان
    """,
    "pharmacy": """
    - ركز على الأدوية وتأثيراتها وآليات عملها
    - اشرح الجرعات والتفاعلات الدوائية
    - اذكر الآثار الجانبية والتحذيرات
    - تحدث عن طرق التخزين والاستخدام
    """,
    "cardiology": """
    - ركز على أمراض القلب والأوعية الدموية
    - اشرح وظائف القلب والدورة الدموية
    - اذكر أعراض أمراض القلب وعلاجاتها
    """,
    "neurology": """
    - ركز على الجهاز العصبي والدماغ
    - اشرح الأمراض العصبية الشائعة
    - اذكر أعراض السكتة الدماغية والصرع
    """,
    
    # الهندسة
    "engineering": """
    - ركز على الجانب الهندسي والتطبيقي
    - استخدم مصطلحات هندسية دقيقة
    - اشرح المبادئ الهندسية الأساسية
    - قدم أمثلة تطبيقية
    """,
    "civil": """
    - ركز على المنشآت والبنية التحتية
    - اشرح مواد البناء والتصميم الإنشائي
    - تحدث عن أساسات المباني والجسور
    - اذكر معايير السلامة
    """,
    "electrical": """
    - ركز على الدوائر الكهربائية والإلكترونية
    - اشرح التيار والجهد والمقاومة
    - تحدث عن المحولات والمحركات
    - اذكر أنظمة الطاقة
    """,
    "mechanical": """
    - ركز على الآلات والحركة والقوى
    - اشرح المبادئ الميكانيكية الأساسية
    - تحدث عن المحركات والتروس
    - اذكر الديناميكا الحرارية
    """,
    "aerospace": """
    - ركز على الطيران والفضاء
    - اشرح الديناميكا الهوائية والدفع
    - تحدث عن تصميم الطائرات والصواريخ
    - اذكر استكشاف الفضاء
    """,
    "software": """
    - ركز على البرمجة والخوارزميات
    - اشرح لغات البرمجة وهياكل البيانات
    - تحدث عن تطوير التطبيقات
    - اذكر أنظمة التشغيل وقواعد البيانات
    """,
    "chemical": """
    - ركز على العمليات الكيميائية الصناعية
    - اشرح تصميم المفاعلات والمعدات
    - تحدث عن تكرير النفط والبتروكيماويات
    """,
    
    # العلوم
    "science": """
    - ركز على المنهج العلمي والتجارب
    - استخدم مصطلحات علمية دقيقة
    - اشرح الظواهر الطبيعية
    - قدم أمثلة من الحياة اليومية
    """,
    "physics": """
    - ركز على القوانين الفيزيائية والظواهر الطبيعية
    - اشرح المعادلات الفيزيائية
    - تحدث عن الحركة والطاقة والقوى
    - اذكر النظريات الفيزيائية الحديثة
    """,
    "chemistry": """
    - ركز على التفاعلات الكيميائية والعناصر
    - اشرح المعادلات الكيميائية
    - تحدث عن الجدول الدوري والروابط
    - اذكر الكيمياء العضوية وغير العضوية
    """,
    "biology": """
    - ركز على الكائنات الحية والعمليات الحيوية
    - اشرح الخلايا والوراثة
    - تحدث عن التصنيف والتطور
    - اذكر علم البيئة والتوازن البيئي
    """,
    "astronomy": """
    - ركز على الأجرام السماوية والكون
    - اشرح حركة الكواكب والنجوم
    - تحدث عن المجرات والثقوب السوداء
    - اذكر استكشاف الفضاء
    """,
    "mathematics": """
    - ركز على المعادلات الرياضية والبراهين
    - اشرح الخطوات بالتفصيل
    - تحدث عن الجبر والهندسة والتفاضل
    - قدم أمثلة محلولة
    """,
    
    # العلوم الإنسانية
    "literature": """
    - ركز على النصوص الأدبية والتحليل
    - استخدم لغة أدبية جميلة
    - تحدث عن الأساليب الأدبية والبلاغة
    - اذكر الشعراء والأدباء المشهورين
    """,
    "history": """
    - ركز على الأحداث التاريخية والتسلسل الزمني
    - اشرح الأسباب والنتائج
    - تحدث عن الشخصيات التاريخية
    - اذكر الحضارات القديمة
    """,
    "geography": """
    - ركز على الظواهر الجغرافية والمواقع
    - اشرح الخرائط والتضاريس
    - تحدث عن المناخ والطقس
    - اذكر الدول والعواصم
    """,
    "philosophy": """
    - ركز على الأفكار الفلسفية والنظريات
    - اشرح المذاهب الفلسفية
    - تحدث عن الفلاسفة المشهورين
    - اذكر مفاهيم الوجود والمعرفة
    """,
    "psychology": """
    - ركز على السلوك البشري والعمليات العقلية
    - اشرح النظريات النفسية
    - تحدث عن الشخصية والاضطرابات
    - اذكر طرق العلاج النفسي
    """,
    "economics": """
    - ركز على النظريات الاقتصادية والأسواق
    - اشرح العرض والطلب
    - تحدث عن الناتج المحلي والتضخم
    - اذكر السياسات المالية والنقدية
    """,
    "law": """
    - ركز على القوانين والأنظمة القانونية
    - اشرح المواد القانونية
    - تحدث عن الحقوق والواجبات
    - اذكر أنواع المحاكم والقضايا
    """,
    
    # العلوم الإسلامية
    "islamic": """
    - ركز على التعاليم الإسلامية والأحكام الشرعية
    - استخدم أسلوباً وقوراً ومحترماً
    - استشهد بالآيات والأحاديث
    - اشرح المسائل الفقهية بوضوح
    """,
    "quran": """
    - ركز على تفسير الآيات وأسباب النزول
    - استخدم أسلوباً قرآنياً
    - اشرح معاني الكلمات والبلاغة القرآنية
    - اذكر القراءات والتجويد
    """,
    "hadith": """
    - ركز على شرح الأحاديث النبوية
    - اذكر الرواة والمصادر
    - اشرح درجة الحديث وصحته
    - استخلص الفوائد والأحكام
    """,
    "fiqh": """
    - ركز على الأحكام الفقهية وأدلتها
    - اشرح المسائل بتفصيل
    - اذكر آراء المذاهب الفقهية
    - بين الراجح من الأقوال
    """,
    "aqeedah": """
    - ركز على العقيدة الإسلامية وأركان الإيمان
    - اشرح مسائل التوحيد
    - رد على الشبهات
    - استشهد بالأدلة من الكتاب والسنة
    """,
    "tafseer": """
    - ركز على تفسير القرآن الكريم
    - اشرح معاني الآيات ودلالاتها
    - اذكر أسباب النزول والمناسبات
    - استخلص الهدايات القرآنية
    """,
    "seerah": """
    - ركز على سيرة النبي محمد ﷺ
    - اذكر الأحداث التاريخية والدروس المستفادة
    - تحدث عن غزواته وصفاته
    - استخلص العبر والمواعظ
    """,
    
    # المراحل الدراسية
    "primary": """
    - استخدم أسلوباً بسيطاً مناسباً للأطفال
    - كرر المعلومات الأساسية
    - استخدم أمثلة من الحياة اليومية
    - اجعل الشرح ممتعاً ومشوقاً
    """,
    "middle": """
    - استخدم أسلوباً متوسط الصعوبة
    - اشرح المفاهيم بوضوح
    - قدم أمثلة توضيحية
    - شجع على التفكير والاستنتاج
    """,
    "high": """
    - استخدم أسلوباً أكاديمياً متقدماً
    - تعمق في التفاصيل
    - اشرح النظريات والمفاهيم المعقدة
    - قدم أمثلة تطبيقية متقدمة
    """,
    "university": """
    - استخدم أسلوباً أكاديمياً عالي المستوى
    - تعمق في النظريات والأبحاث
    - استخدم المصطلحات المتخصصة
    - قدم تحليلات نقدية
    """,
    
    # افتراضي
    "other": """
    - استخدم أسلوباً تعليمياً واضحاً
    - اشرح المفاهيم الأساسية
    - قدم أمثلة توضيحية
    - لخص المعلومات المهمة
    """
}


# ============================================================
# تحليل المحاضرة الرئيسي
# ============================================================
async def analyze_lecture(text: str, dialect: str = "msa", subject_hint: str = "other") -> dict:
    """
    تحليل المحاضرة واستخراج الأقسام والمحتوى.
    يستخدم DeepSeek كأولوية أولى للتحليل.
    
    Args:
        text: نص المحاضرة
        dialect: اللهجة المطلوبة
        subject_hint: نوع المادة (لتوجيه التحليل)
    
    Returns:
        dict: بيانات المحاضرة المحللة
    """
    # إعدادات اللهجة
    dialect_instructions = {
        "iraq": "استخدم اللهجة العراقية في الشرح، مع كلمات عراقية أصيلة مثل (هواية، گلت، يعني، بس، هسا، چان، عگب)",
        "egypt": "استخدم اللهجة المصرية في الشرح، مع كلمات مصرية مثل (أوي، معلش، يعني، بس، كده، إيه، مش)",
        "syria": "استخدم اللهجة الشامية في الشرح، مع كلمات شامية مثل (هلق، شو، كتير، منيح، هيك، شي، عنجد)",
        "gulf": "استخدم اللهجة الخليجية في الشرح، مع كلمات خليجية مثل (زين، وايد، عاد، هاذي، أبشر، يمعود)",
        "msa": "استخدم العربية الفصحى الواضحة والمبسطة",
        "english": "Use clear, simple English. Explain like a teacher to students.",
        "british": "Use British English with a professional, clear academic tone."
    }
    
    instruction = dialect_instructions.get(dialect, dialect_instructions["msa"])
    subject_instruction = SUBJECT_INSTRUCTIONS.get(subject_hint, SUBJECT_INSTRUCTIONS["other"])
    
    # حساب عدد الأقسام
    num_sections, narration_sentences, max_tokens = _compute_lecture_scale(text)
    text_limit = min(len(text), 6000)  # زيادة الحد لـ DeepSeek
    is_english = dialect in ("english", "british")
    
    # إعدادات الإخراج حسب اللغة
    if is_english:
        summary_hint = "A clear, concise summary (4-5 sentences)"
        key_points_hint = '["Key point 1", "Key point 2", "Key point 3", "Key point 4"]'
        title_hint = "Lecture title"
        section_title_hint = "Section title"
        content_hint = f"Simplified section content ({narration_sentences} sentences)"
        keywords_hint = '["keyword1", "keyword2", "keyword3", "keyword4"]'
        narration_hint = f"Full narration ({narration_sentences} sentences)"
        lang_note = "Write ALL text in English."
    else:
        summary_hint = "ملخص المحاضرة بأسلوب مبسط (4-5 جمل)"
        key_points_hint = '["نقطة رئيسية 1", "نقطة رئيسية 2", "نقطة رئيسية 3", "نقطة رئيسية 4"]'
        title_hint = "عنوان المحاضرة"
        section_title_hint = "عنوان القسم"
        content_hint = f"محتوى القسم المبسط ({narration_sentences} جمل)"
        keywords_hint = '["مصطلح 1", "مصطلح 2", "مصطلح 3", "مصطلح 4"]'
        narration_hint = f"نص الشرح الكامل باللهجة المطلوبة ({narration_sentences} جمل)"
        lang_note = "النص يجب أن يكون باللهجة المطلوبة"
    
    # بناء الموجه (Prompt) - محسن لـ DeepSeek
    prompt = f"""أنت معلم خبير ومتخصص في تبسيط المحاضرات التعليمية. مهمتك تحليل المحاضرة التالية وإنتاج محتوى تعليمي احترافي.

{instruction}

{subject_instruction}

المحاضرة:
---
{text[:text_limit]}
---

قم بتحليل المحاضرة وأرجع JSON فقط بالتنسيق التالي. يجب أن يحتوي على {num_sections} أقسام بالضبط:

{{
  "lecture_type": "{subject_hint}",
  "title": "{title_hint}",
  "sections": [
    {{
      "title": "{section_title_hint}",
      "content": "{content_hint}",
      "keywords": {keywords_hint},
      "keyword_images": [
        "cartoon illustration description for keyword1 - 3-5 English words",
        "cartoon illustration description for keyword2 - 3-5 English words",
        "cartoon illustration description for keyword3 - 3-5 English words",
        "cartoon illustration description for keyword4 - 3-5 English words"
      ],
      "narration": "{narration_hint}",
      "duration_estimate": 45
    }}
  ],
  "summary": "{summary_hint}",
  "key_points": {key_points_hint}
}}

مهم جداً:
- {lang_note}
- يجب أن يكون عدد الأقسام {num_sections} بالضبط
- كل قسم يجب أن يحتوي على 4 كلمات مفتاحية
- keyword_images: وصف إنجليزي قصير (3-5 كلمات) لصورة كرتونية تعبر عن الكلمة
- narration: نص كامل للشرح الصوتي ({narration_sentences} جمل)
- أرجع JSON فقط بدون أي نص إضافي أو علامات ```json
"""
    
    # إرسال الطلب عبر نظام التوليد الذكي (DeepSeek أولاً)
    content = await _generate_with_rotation(prompt, max_output_tokens=max_tokens)
    content = content.strip()
    content = re.sub(r'^```json\s*', '', content)
    content = re.sub(r'\s*```$', '', content)
    content = content.strip()
    
    # محاولة تحليل JSON
    try:
        result = json.loads(content)
        
        # التأكد من عدد الأقسام
        sections = result.get("sections", [])
        if len(sections) != num_sections:
            if len(sections) > num_sections:
                result["sections"] = sections[:num_sections]
        
        return result
        
    except json.JSONDecodeError:
        # محاولة استخراج JSON من النص
        json_match = re.search(r'\{[\s\S]*\}', content)
        if json_match:
            try:
                return json.loads(json_match.group())
            except:
                pass
        raise ValueError(f"Failed to parse JSON: {content[:300]}")


# ============================================================
# استخراج النص من PDF
# ============================================================
async def extract_full_text_from_pdf(pdf_bytes: bytes) -> str:
    """استخراج النص من PDF (من الذاكرة)"""
    import PyPDF2
    
    def _extract():
        try:
            reader = PyPDF2.PdfReader(io.BytesIO(pdf_bytes))
            texts = []
            for page in reader.pages[:100]:
                try:
                    txt = page.extract_text()
                    if txt and txt.strip():
                        texts.append(txt.strip())
                except:
                    pass
            return "\n\n".join(texts)
        except Exception as e:
            print(f"PDF error: {e}")
            return ""
    
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _extract)


async def extract_full_text_from_pdf_path(pdf_path: str) -> str:
    """استخراج النص من PDF (من ملف) - أسرع وأفضل للذاكرة"""
    import PyPDF2
    
    def _extract():
        try:
            reader = PyPDF2.PdfReader(pdf_path)
            texts = []
            for page in reader.pages[:100]:
                try:
                    txt = page.extract_text()
                    if txt and txt.strip():
                        texts.append(txt.strip())
                except:
                    pass
            return "\n\n".join(texts)
        except Exception as e:
            print(f"PDF error: {e}")
            return ""
    
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _extract)


async def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """نسخة مختصرة للتوافق"""
    return await extract_full_text_from_pdf(pdf_bytes)


# ============================================================
# توليد الصور
# ============================================================
def _make_placeholder_image(keywords: list, lecture_type: str = "other") -> bytes:
    """إنشاء صورة بديلة احترافية"""
    W, H = 1280, 720
    
    # اختيار اللون حسب التخصص
    color = SUBJECT_COLORS.get(lecture_type, SUBJECT_COLORS.get("other", (100, 116, 139)))
    
    img = PILImage.new("RGB", (W, H), (245, 248, 250))
    draw = ImageDraw.Draw(img)
    
    # خلفية متدرجة
    for y in range(H):
        t = y / H
        r = int(255 * (1 - t) + color[0] * 0.2 * t)
        g = int(255 * (1 - t) + color[1] * 0.2 * t)
        b = int(255 * (1 - t) + color[2] * 0.2 * t)
        draw.line([(0, y), (W, y)], fill=(r, g, b))
    
    # إطار
    draw.rounded_rectangle([(20, 20), (W-20, H-20)], radius=30, outline=color, width=6)
    
    # أيقونة التخصص
    icons = {
        "medicine": "🩺", "surgery": "🔪", "pediatrics": "👶", "dentistry": "🦷",
        "engineering": "⚙️", "civil": "🏗️", "electrical": "⚡", "software": "💻",
        "science": "🔬", "physics": "⚛️", "chemistry": "🧪", "biology": "🧬",
        "math": "📐", "literature": "📖", "history": "🏛️", "geography": "🌍",
        "islamic": "🕌", "quran": "📖", "hadith": "📜", "fiqh": "📚",
        "primary": "🎒", "middle": "📚", "high": "🎓", "other": "📚"
    }
    icon = icons.get(lecture_type, "📚")
    
    try:
        font = ImageFont.truetype("/app/fonts/Amiri-Bold.ttf", 80)
    except:
        font = ImageFont.load_default()
    
    bbox = draw.textbbox((0, 0), icon, font=font)
    iw = bbox[2] - bbox[0]
    draw.text(((W - iw)//2, 150), icon, fill=color, font=font)
    
    # الكلمة المفتاحية
    if keywords:
        try:
            import arabic_reshaper
            from bidi.algorithm import get_display
            kw = get_display(arabic_reshaper.reshape(keywords[0][:30]))
        except:
            kw = keywords[0][:30]
        
        try:
            font_kw = ImageFont.truetype("/app/fonts/Amiri-Bold.ttf", 48)
        except:
            font_kw = ImageFont.load_default()
        
        bbox = draw.textbbox((0, 0), kw, font=font_kw)
        kw_w = bbox[2] - bbox[0]
        draw.text(((W - kw_w)//2 + 3, 300), kw, fill=(0, 0, 0, 100), font=font_kw)
        draw.text(((W - kw_w)//2, 297), kw, fill=(40, 45, 60), font=font_kw)
    
    # نص توضيحي
    hint = "🎨 صورة تعليمية"
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
        hint = get_display(arabic_reshaper.reshape(hint))
    except:
        pass
    
    try:
        font_hint = ImageFont.truetype("/app/fonts/Amiri-Regular.ttf", 24)
    except:
        font_hint = ImageFont.load_default()
    
    bbox = draw.textbbox((0, 0), hint, font=font_hint)
    hw = bbox[2] - bbox[0]
    draw.text(((W - hw)//2, 450), hint, fill=(120, 120, 140), font=font_hint)
    
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=90)
    return buf.getvalue()


async def _pollinations_generate(prompt: str) -> bytes | None:
    """توليد صورة باستخدام Pollinations.ai (مجاني)"""
    import urllib.parse
    import random
    
    try:
        encoded = urllib.parse.quote(prompt[:200])
        url = f"https://image.pollinations.ai/prompt/{encoded}?width=1280&height=720&seed={random.randint(1,99999)}&model=flux"
        
        async with aiohttp.ClientSession() as s:
            async with s.get(url, timeout=aiohttp.ClientTimeout(total=12)) as r:
                if r.status == 200:
                    data = await r.read()
                    if len(data) > 5000:
                        print(f"✅ Pollinations generated image")
                        return data
    except Exception as e:
        print(f"⚠️ Pollinations failed: {e}")
    
    return None


async def _dalle_generate(prompt: str) -> bytes | None:
    """توليد صورة باستخدام DALL-E (إذا توفر المفتاح)"""
    if not OPENAI_API_KEY:
        return None
    
    import base64
    
    try:
        payload = {
            "model": "dall-e-3",
            "prompt": f"educational cartoon illustration, {prompt[:200]}, simple colorful style, white background",
            "size": "1024x1024",
            "n": 1,
            "response_format": "b64_json"
        }
        headers = {"Authorization": f"Bearer {OPENAI_API_KEY}"}
        
        async with aiohttp.ClientSession() as s:
            async with s.post(
                "https://api.openai.com/v1/images/generations",
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as r:
                if r.status == 200:
                    data = await r.json()
                    b64 = data["data"][0].get("b64_json", "")
                    if b64:
                        print(f"✅ DALL-E generated image")
                        return base64.b64decode(b64)
    except Exception as e:
        print(f"⚠️ DALL-E failed: {e}")
    
    return None


async def _pexels_generate(keyword: str) -> bytes | None:
    """البحث عن صورة في Pexels"""
    pexels_key = os.getenv("PEXELS_API_KEY", "")
    if not pexels_key:
        return None
    
    import urllib.parse
    
    try:
        headers = {"Authorization": pexels_key}
        query = urllib.parse.quote(f"{keyword} education")
        
        async with aiohttp.ClientSession() as s:
            async with s.get(
                f"https://api.pexels.com/v1/search?query={query}&per_page=3",
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as r:
                if r.status == 200:
                    data = await r.json()
                    for photo in data.get("photos", []):
                        img_url = photo["src"].get("large")
                        if img_url:
                            async with s.get(img_url, timeout=15) as ir:
                                if ir.status == 200:
                                    print(f"✅ Pexels found image")
                                    return await ir.read()
    except Exception as e:
        print(f"⚠️ Pexels failed: {e}")
    
    return None


async def fetch_image_for_keyword(
    keyword: str,
    section_title: str,
    lecture_type: str,
    image_search_en: str = "",
) -> bytes:
    """
    جلب صورة للكلمة المفتاحية مع نظام بدائل متعدد.
    
    الترتيب:
    1. Pollinations.ai (مجاني وسريع)
    2. DALL-E (إذا توفر مفتاح OpenAI)
    3. Pexels (صور حقيقية مجانية)
    4. صورة بديلة محلية
    """
    subject = (image_search_en or keyword).strip()
    
    # 1. Pollinations
    prompt = f"educational cartoon illustration, {subject}, simple colorful style, clear background"
    img = await _pollinations_generate(prompt)
    if img:
        return img
    
    # 2. DALL-E
    img = await _dalle_generate(f"cartoon educational illustration, {subject}, simple style")
    if img:
        return img
    
    # 3. Pexels
    img = await _pexels_generate(subject)
    if img:
        return img
    
    # 4. صورة بديلة
    print(f"🎨 Creating placeholder for: {subject[:30]}")
    return _make_placeholder_image([keyword, section_title], lecture_type)


async def generate_educational_image(
    prompt: str,
    lecture_type: str,
    keywords: list = None,
    image_search: str = None,
    image_search_fallbacks: list = None,
) -> bytes:
    """دالة مساعدة للتوافق مع الكود القديم"""
    kw = keywords[0] if keywords else prompt[:30]
    return await fetch_image_for_keyword(kw, "", lecture_type, image_search or prompt)


# ============================================================
# دوال إضافية
# ============================================================
def _is_safe_url(url: str) -> bool:
    """التحقق من أمان الرابط"""
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        return parsed.scheme in ('http', 'https')
    except:
        return False


async def extract_text_from_url(url: str) -> str:
    """استخراج النص من رابط"""
    if not _is_safe_url(url):
        return ""
    
    try:
        from bs4 import BeautifulSoup
        headers = {'User-Agent': 'Mozilla/5.0'}
        
        async with aiohttp.ClientSession() as s:
            async with s.get(url, headers=headers, timeout=15) as r:
                if r.status == 200:
                    html = await r.text()
                    soup = BeautifulSoup(html, 'html.parser')
                    for tag in soup(['script', 'style', 'nav', 'footer', 'header']):
                        tag.decompose()
                    text = soup.get_text(separator='\n', strip=True)
                    return '\n'.join([l.strip() for l in text.split('\n') if len(l.strip()) > 20][:200])
    except:
        pass
    
    return ""


async def translate_full_text(text: str, dialect: str) -> str:
    """ترجمة النص إلى اللهجة المطلوبة"""
    return text
