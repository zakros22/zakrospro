# -*- coding: utf-8 -*-
import json
import re
import io
import asyncio
import aiohttp
import os
import random
from PIL import Image as PILImage, ImageDraw, ImageFont
from google import genai
from google.genai import types as genai_types

# ═══════════════════════════════════════════════════════════════════════════════
# 1. تحميل مفاتيح Google Gemini من متغيرات البيئة
# ═══════════════════════════════════════════════════════════════════════════════

def _load_google_keys():
    """
    تحميل جميع مفاتيح Google Gemini من متغيرات البيئة.
    تدعم الصيغ التالية:
    - GOOGLE_API_KEY: مفتاح واحد
    - GOOGLE_API_KEYS: عدة مفاتيح مفصولة بفواصل
    - GOOGLE_API_KEY_1 إلى GOOGLE_API_KEY_9: مفاتيح منفصلة
    """
    keys = []
    
    # الطريقة الأولى: متغير واحد يحتوي على عدة مفاتيح مفصولة بفواصل
    raw_keys = os.getenv("GOOGLE_API_KEYS", "")
    if raw_keys:
        for k in raw_keys.split(","):
            k = k.strip()
            if k and k not in keys:
                keys.append(k)
    
    # الطريقة الثانية: مفاتيح مرقمة من 1 إلى 9
    for i in range(1, 10):
        key = os.getenv(f"GOOGLE_API_KEY_{i}", "")
        key = key.strip()
        if key and key not in keys:
            keys.append(key)
    
    # الطريقة الثالثة: مفتاح واحد فقط
    single_key = os.getenv("GOOGLE_API_KEY", "")
    single_key = single_key.strip()
    if single_key and single_key not in keys:
        keys.append(single_key)
    
    return keys

# تجهيز مجموعة المفاتيح
_google_keys = _load_google_keys()
_current_google_idx = 0
_exhausted_google_keys = set()

# طباعة عدد المفاتيح المحملة للتأكد
print(f"[INFO] Loaded {len(_google_keys)} Google API key(s)")

def _get_next_google_key():
    """
    الحصول على المفتاح التالي المتاح من Google.
    إذا كان المفتاح الحالي مستنفذ، ينتقل إلى المفتاح التالي تلقائياً.
    """
    global _current_google_idx
    if not _google_keys:
        return None
    
    # نجرب جميع المفاتيح
    for _ in range(len(_google_keys)):
        key = _google_keys[_current_google_idx % len(_google_keys)]
        if key not in _exhausted_google_keys:
            return key
        _current_google_idx += 1
    
    # كل المفاتيح مستنفذة
    return None

def _mark_google_exhausted(key: str):
    """
    تعليم مفتاح Google على أنه مستنفذ (انتهت حصته المجانية).
    """
    global _current_google_idx
    _exhausted_google_keys.add(key)
    _current_google_idx += 1
    remaining = len(_google_keys) - len(_exhausted_google_keys)
    print(f"[WARN] Google key exhausted. {remaining} key(s) remaining.")

# ═══════════════════════════════════════════════════════════════════════════════
# 2. تحميل مفاتيح Groq (خدمة احتياطية مجانية)
# ═══════════════════════════════════════════════════════════════════════════════

def _load_groq_keys():
    """
    تحميل مفاتيح Groq من متغيرات البيئة.
    تدعم GROQ_API_KEYS (بفواصل) أو GROQ_API_KEY (مفتاح واحد).
    """
    keys = []
    raw_keys = os.getenv("GROQ_API_KEYS", "")
    if raw_keys:
        for k in raw_keys.split(","):
            k = k.strip()
            if k and k not in keys:
                keys.append(k)
    
    single_key = os.getenv("GROQ_API_KEY", "").strip()
    if single_key and single_key not in keys:
        keys.append(single_key)
    
    return keys

_groq_keys = _load_groq_keys()
print(f"[INFO] Loaded {len(_groq_keys)} Groq API key(s)")

# قائمة النماذج المجانية في Groq
_GROQ_MODELS = [
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "gemma2-9b-it",
    "mixtral-8x7b-32768",
]

# ═══════════════════════════════════════════════════════════════════════════════
# 3. دوال الاتصال بـ Google Gemini
# ═══════════════════════════════════════════════════════════════════════════════

async def _generate_with_google(prompt: str, max_tokens: int = 8192) -> str:
    """
    محاولة توليد النص باستخدام Google Gemini.
    تجرب جميع المفاتيح المتاحة وجميع النماذج.
    """
    # النماذج المتاحة والمجانية
    models = ["gemini-2.0-flash", "gemini-2.0-flash-lite"]
    
    # نجرب كل المفاتيح
    for _ in range(len(_google_keys) * 2):
        key = _get_next_google_key()
        if not key:
            break
        
        # إنشاء عميل Gemini
        client = genai.Client(api_key=key)
        
        # نجرب كل نموذج
        for model in models:
            try:
                print(f"[INFO] Trying Google model: {model}")
                
                # استدعاء API بشكل غير متزامن
                response = await asyncio.to_thread(
                    client.models.generate_content,
                    model=model,
                    contents=prompt,
                    config=genai_types.GenerateContentConfig(
                        temperature=0.7,  # إبداع متوسط لمنع التكرار
                        max_output_tokens=max_tokens,
                    ),
                )
                
                print(f"[OK] Google success with {model}")
                return response.text.strip()
                
            except Exception as e:
                err = str(e)
                # التحقق من انتهاء الحصة
                if "429" in err or "RESOURCE_EXHAUSTED" in err or "quota" in err.lower():
                    print(f"[WARN] Google key quota exhausted")
                    _mark_google_exhausted(key)
                    break  # نجرب مفتاح آخر
                else:
                    print(f"[WARN] Google error: {err[:100]}")
                    continue  # نجرب نموذج آخر
    
    raise Exception("All Google keys exhausted")


# ═══════════════════════════════════════════════════════════════════════════════
# 4. دوال الاتصال بـ Groq (احتياطي)
# ═══════════════════════════════════════════════════════════════════════════════

async def _generate_with_groq(prompt: str, max_tokens: int = 8192) -> str:
    """
    محاولة توليد النص باستخدام Groq كخدمة احتياطية.
    """
    if not _groq_keys:
        raise Exception("No Groq keys configured")
    
    # نجرب كل المفاتيح
    for key in _groq_keys:
        # نجرب كل نموذج
        for model in _GROQ_MODELS:
            try:
                print(f"[INFO] Trying Groq model: {model}")
                
                headers = {
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                }
                payload = {
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": min(max_tokens, 8192),
                    "temperature": 0.7,
                }
                
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        "https://api.groq.com/openai/v1/chat/completions",
                        headers=headers,
                        json=payload,
                        timeout=aiohttp.ClientTimeout(total=60),
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            print(f"[OK] Groq success with {model}")
                            return data["choices"][0]["message"]["content"].strip()
                        else:
                            body = await resp.text()
                            print(f"[WARN] Groq {resp.status}: {body[:100]}")
                            continue
                            
            except Exception as e:
                print(f"[WARN] Groq error: {str(e)[:100]}")
                continue
    
    raise Exception("All Groq attempts failed")


# ═══════════════════════════════════════════════════════════════════════════════
# 5. دالة التدوير الرئيسية (Google أولاً، ثم Groq)
# ═══════════════════════════════════════════════════════════════════════════════

async def _generate_with_rotation(prompt: str, max_output_tokens: int = 8192) -> str:
    """
    نظام التدوير الذكي:
    1. يجرب Google Gemini أولاً (مع تدوير المفاتيح)
    2. إذا فشل، ينتقل إلى Groq
    """
    
    # المرحلة الأولى: Google Gemini
    if _google_keys:
        try:
            return await _generate_with_google(prompt, max_output_tokens)
        except Exception as e:
            print(f"[WARN] Google failed: {e}")
            print("[INFO] Switching to Groq fallback...")
    
    # المرحلة الثانية: Groq
    if _groq_keys:
        try:
            return await _generate_with_groq(prompt, max_output_tokens)
        except Exception as e:
            print(f"[WARN] Groq failed: {e}")
    
    # كل شيء فشل
    raise Exception("All AI services failed. Please try again later.")


# ═══════════════════════════════════════════════════════════════════════════════
# 6. استخراج الكلمات المفتاحية من النص
# ═══════════════════════════════════════════════════════════════════════════════

def _extract_keywords_from_text(text: str, max_words: int = 30) -> list:
    """
    استخراج الكلمات الأكثر تكراراً من النص.
    يستخدم للعربية والإنجليزية.
    """
    # قائمة الكلمات المستبعدة (stop words)
    stop_words = {
        # عربي
        'و', 'في', 'من', 'على', 'إلى', 'أن', 'هو', 'هي', 'هذا', 'هذه', 'كان', 'كانت',
        'مع', 'ما', 'لا', 'عن', 'إذا', 'لم', 'لن', 'قد', 'ثم', 'أو', 'أم', 'لكن',
        'حتى', 'بل', 'كل', 'بعض', 'أي', 'تلك', 'ذلك', 'هؤلاء', 'الذي', 'التي',
        'الذين', 'ماذا', 'كيف', 'أين', 'متى', 'نحن', 'هم',
        # إنجليزي
        'the', 'a', 'an', 'is', 'are', 'was', 'were', 'of', 'to', 'in', 'that',
        'it', 'be', 'for', 'on', 'with', 'as', 'at', 'by', 'this', 'and', 'or',
        'but', 'from', 'they', 'we', 'you', 'i', 'he', 'she', 'his', 'her', 'their'
    }
    
    # استخراج الكلمات العربية (4 أحرف فأكثر) والإنجليزية (4 أحرف فأكثر)
    words = re.findall(r'[\u0600-\u06FF]{4,}|[a-zA-Z]{4,}', text)
    
    # حساب التكرار
    word_freq = {}
    for w in words:
        w_lower = w.lower()
        if w_lower not in stop_words:
            word_freq[w] = word_freq.get(w, 0) + 1
    
    # ترتيب تنازلي
    sorted_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)
    return [w[0] for w in sorted_words[:max_words]]


# ═══════════════════════════════════════════════════════════════════════════════
# 7. تحديد نوع المحاضرة (طبية، رياضيات، تاريخ...)
# ═══════════════════════════════════════════════════════════════════════════════

def _detect_lecture_type(text: str) -> str:
    """
    تحديد نوع المحاضرة من خلال الكلمات المفتاحية الموجودة في النص.
    """
    text_lower = text.lower()
    
    # قوائم الكلمات الدالة على كل نوع
    medical_keywords = [
        'مرض', 'علاج', 'طبيب', 'جراحة', 'دواء', 'تشخيص', 'مريض', 'عرض', 'قلب', 'دم',
        'خلية', 'ورم', 'سرطان', 'endometriosis', 'cyst', 'inflammation', 'pain',
        'bleeding', 'menstrual', 'pelvic', 'diagnosis', 'treatment', 'surgery',
        'medicine', 'disease', 'heart', 'blood', 'cell', 'cancer', 'chronic', 'acute'
    ]
    
    math_keywords = [
        'معادلة', 'دالة', 'تفاضل', 'تكامل', 'جبر', 'هندسة', 'عدد', 'متغير', 'رياضيات',
        'equation', 'function', 'calculus', 'algebra', 'geometry', 'variable', 'math',
        'derivative', 'integral', 'matrix', 'vector'
    ]
    
    physics_keywords = [
        'قوة', 'طاقة', 'حركة', 'سرعة', 'تسارع', 'جاذبية', 'كهرباء', 'مغناطيس', 'فيزياء',
        'force', 'energy', 'motion', 'velocity', 'gravity', 'physics', 'quantum',
        'wave', 'particle', 'mass', 'acceleration'
    ]
    
    chemistry_keywords = [
        'تفاعل', 'عنصر', 'مركب', 'جزيء', 'ذرة', 'حمض', 'قاعدة', 'كيمياء',
        'reaction', 'element', 'compound', 'molecule', 'atom', 'chemistry',
        'bond', 'acid', 'base', 'solution'
    ]
    
    history_keywords = [
        'تاريخ', 'حرب', 'معركة', 'حضارة', 'إمبراطورية', 'ملك', 'ثورة', 'قرن', 'قديم',
        'history', 'war', 'battle', 'civilization', 'empire', 'revolution', 'ancient',
        'king', 'dynasty', 'century'
    ]
    
    biology_keywords = [
        'نبات', 'حيوان', 'بيئة', 'وراثة', 'حمض نووي', 'تطور', 'خلية',
        'biology', 'plant', 'animal', 'evolution', 'dna', 'gene', 'species',
        'cell', 'tissue', 'organ', 'ecosystem'
    ]
    
    # حساب النقاط لكل نوع
    scores = {
        'medicine': sum(1 for kw in medical_keywords if kw in text_lower),
        'math': sum(1 for kw in math_keywords if kw in text_lower),
        'physics': sum(1 for kw in physics_keywords if kw in text_lower),
        'chemistry': sum(1 for kw in chemistry_keywords if kw in text_lower),
        'history': sum(1 for kw in history_keywords if kw in text_lower),
        'biology': sum(1 for kw in biology_keywords if kw in text_lower),
    }
    
    # اختيار النوع الأعلى نقاط
    best_type = max(scores, key=scores.get)
    if scores[best_type] > 1:
        print(f"[INFO] Detected lecture type: {best_type}")
        return best_type
    
    print("[INFO] Detected lecture type: other")
    return 'other'


# ═══════════════════════════════════════════════════════════════════════════════
# 8. تقسيم النص الأصلي إلى أقسام (للاستخدام كخطة احتياطية)
# ═══════════════════════════════════════════════════════════════════════════════

def _split_text_into_parts(text: str, num_parts: int) -> list:
    """
    تقسيم النص الأصلي إلى أجزاء متساوية تقريباً.
    تستخدم كخطة احتياطية إذا فشل AI في توليد الأقسام.
    """
    words = text.split()
    total_words = len(words)
    
    if total_words == 0:
        return [""] * num_parts
    
    chunk_size = max(1, total_words // num_parts)
    parts = []
    
    for i in range(0, total_words, chunk_size):
        part = ' '.join(words[i:i+chunk_size])
        if part.strip():
            parts.append(part)
    
    # التأكد من العدد المطلوب
    if len(parts) > num_parts:
        # دمج الأجزاء الزائدة
        while len(parts) > num_parts:
            parts[-2] = parts[-2] + " " + parts[-1]
            parts.pop()
    elif len(parts) < num_parts:
        # إضافة أجزاء فارغة
        while len(parts) < num_parts:
            parts.append("")
    
    return parts


# ═══════════════════════════════════════════════════════════════════════════════
# 9. الدالة الرئيسية: تحليل المحاضرة
# ═══════════════════════════════════════════════════════════════════════════════

async def analyze_lecture(text: str, dialect: str = "msa") -> dict:
    """
    تحليل المحاضرة بشكل كامل:
    1. استخراج الكلمات المفتاحية
    2. تحديد نوع المحاضرة
    3. استخدام AI لتوليد عنوان وأقسام وشرح احترافي
    4. إذا فشل AI، استخدام تقسيم النص الأصلي
    """
    
    print("[INFO] Starting lecture analysis...")
    
    # استخراج الكلمات المفتاحية من النص كاملاً
    all_keywords = _extract_keywords_from_text(text, 40)
    print(f"[INFO] Extracted {len(all_keywords)} keywords")
    
    # تحديد نوع المحاضرة
    lecture_type = _detect_lecture_type(text)
    
    # تحديد عدد الأقسام حسب طول النص
    word_count = len(text.split())
    if word_count < 300:
        num_sections = 3
    elif word_count < 600:
        num_sections = 4
    elif word_count < 1000:
        num_sections = 5
    elif word_count < 1500:
        num_sections = 6
    else:
        num_sections = 7
    
    print(f"[INFO] Will create {num_sections} sections")
    
    # ───────────────────────────────────────────────────────────────────────────
    # تجهيز الـ Prompt للـ AI
    # ───────────────────────────────────────────────────────────────────────────
    
    # أسلوب المعلم حسب نوع المحاضرة
    teacher_styles = {
        'medicine': 'أنت طبيب استشاري تشرح لطلاب الطب. اشرح pathophysiology والأعراض والأسباب والتشخيص والعلاج. استخدم لغة طبية دقيقة ثم بسطها للطلاب.',
        'math': 'أنت أستاذ رياضيات تشرح على السبورة. اشرح المعادلات خطوة بخطوة. فسر كل متغير. أعط أمثلة عددية محلولة.',
        'physics': 'أنت فيزيائي تشرح القوانين الطبيعية. اشرح القانون ثم طبقه على مثال من الحياة اليومية. اشرح الوحدات والأبعاد.',
        'chemistry': 'أنت كيميائي تشرح التفاعلات. اشرح المعادلة الكيميائية وظروف التفاعل والتطبيقات. فسر الروابط والتراكيب.',
        'history': 'أنت مؤرخ تروي الأحداث. اسرد القصة التاريخية بتسلسل زمني. اذكر الشخصيات الرئيسية. حلل الأسباب والنتائج.',
        'biology': 'أنت عالم أحياء تشرح الكائنات الحية. اشرح التركيب والوظيفة والعمليات الحيوية. استخدم التشبيهات لتقريب المفاهيم.',
        'other': 'أنت معلم خبير تشرح المعلومات بوضوح. بسط المفاهيم المعقدة. أعط أمثلة من الحياة اليومية. اجعل الشرح ممتعاً وسهل الفهم.'
    }
    
    teacher_style = teacher_styles.get(lecture_type, teacher_styles['other'])
    
    # أسلوب اللهجة
    dialect_instructions = {
        "iraq": "باللهجة العراقية الأصيلة. تكلم كمعلم عراقي. استخدم كلمات مثل: هواية، گلت، يعني، هسا، چي، شلون، وين، أكو، ماكو.",
        "egypt": "باللهجة المصرية. تكلم كمعلم مصري. استخدم كلمات مثل: أوي، معلش، يعني، كده، عايز، بتاع، النهارده، بكره، يا جماعة.",
        "syria": "باللهجة الشامية. تكلم كمعلم سوري. استخدم كلمات مثل: هلق، شو، كتير، منيح، هيك، عم، فيكن، يا زلمة.",
        "gulf": "باللهجة الخليجية. تكلم كمعلم خليجي. استخدم كلمات مثل: زين، وايد، عاد، هاذي، أبشر، شفيك، ليش، يالحبيب.",
        "msa": "بالعربية الفصحى البسيطة والواضحة. تكلم كمعلم فصيح يبسط المعلومات للطلاب."
    }
    
    dialect_inst = dialect_instructions.get(dialect, dialect_instructions["msa"])
    
    # أخذ جزء من النص للتحليل (لتجنب تجاوز الحد الأقصى)
    text_preview = text[:4000]
    
    # بناء الـ Prompt
    prompt = f"""{teacher_style}

**تعليمات اللهجة:**
{dialect_inst}

**تعليمات صارمة للشرح:**
- اكتب شرحاً كاملاً ومتنوعاً. كل جملة يجب أن تضيف معلومة جديدة.
- لا تكرر نفس الجملة أبداً. لا تستخدم "يعني يعني" أو "هو هو هو".
- فسر المصطلحات العلمية بلغة بسيطة.
- أعط أمثلة واقعية من الحياة اليومية.
- اربط بين المفاهيم بشكل منطقي.
- استخدم أسلوب المعلم الذي يشرح لطلابه مباشرة.

**النص الأصلي للمحاضرة:**
---
{text_preview}
---

**الكلمات المفتاحية المستخرجة من النص:**
{', '.join(all_keywords[:15])}

**المطلوب بالضبط:**
قم بتحليل المحاضرة وإنشاء {num_sections} أقسام تعليمية.

أرجع JSON فقط بالتنسيق التالي:

{{
  "title": "عنوان المحاضرة (عنوان جذاب وواضح)",
  "sections": [
    {{
      "title": "عنوان القسم الأول",
      "keywords": ["كلمة1", "كلمة2", "كلمة3", "كلمة4"],
      "narration": "نص الشرح الصوتي الكامل والمفصل (15-20 جملة متنوعة). هذا هو النص الذي سينطقه المعلم. اشرح هنا بالتفصيل دون تكرار."
    }},
    {{
      "title": "عنوان القسم الثاني",
      "keywords": ["كلمة1", "كلمة2", "كلمة3", "كلمة4"],
      "narration": "نص الشرح الصوتي الكامل والمفصل (15-20 جملة متنوعة)."
    }}
  ],
  "summary": "ملخص شامل للمحاضرة (5-7 جمل)",
  "key_points": ["النقطة الرئيسية الأولى", "النقطة الثانية", "النقطة الثالثة", "النقطة الرابعة", "النقطة الخامسة"]
}}

**تنبيهات مهمة جداً:**
- keywords: يجب أن تكون 4 كلمات مفتاحية بالضبط لكل قسم.
- narration: اكتب 15-20 جملة متنوعة. لا تكرر الجمل. كل جملة معلومة جديدة.
- استخدم الكلمات المفتاحية من القائمة المستخرجة أعلاه.
- أرجع JSON فقط بدون أي نص إضافي.
"""

    # ───────────────────────────────────────────────────────────────────────────
    # محاولة التحليل باستخدام AI
    # ───────────────────────────────────────────────────────────────────────────
    
    ai_success = False
    title = all_keywords[0] if all_keywords else "المحاضرة التعليمية"
    ai_sections = []
    
    try:
        print("[INFO] Calling AI for analysis...")
        content = await _generate_with_rotation(prompt, max_output_tokens=8192)
        
        # تنظيف النص المستلم
        content = content.strip()
        content = re.sub(r'^```json\s*', '', content)
        content = re.sub(r'\s*```$', '', content)
        content = content.strip()
        
        # محاولة parse الـ JSON
        result = json.loads(content)
        
        title = result.get("title", title)
        ai_sections = result.get("sections", [])
        
        print(f"[OK] AI analysis successful. Title: {title}, Sections: {len(ai_sections)}")
        ai_success = True
        
    except Exception as e:
        print(f"[WARN] AI analysis failed: {e}")
        print("[INFO] Using fallback text splitting...")
    
    # ───────────────────────────────────────────────────────────────────────────
    # بناء الأقسام النهائية
    # ───────────────────────────────────────────────────────────────────────────
    
    # تقسيم النص الأصلي كاحتياط
    original_parts = _split_text_into_parts(text, num_sections)
    
    final_sections = []
    
    for i in range(num_sections):
        if ai_success and i < len(ai_sections):
            # استخدام بيانات AI
            section = ai_sections[i]
            section_keywords = section.get("keywords", [])[:4]
            section_title = section.get("title", f"القسم {i+1}")
            narration = section.get("narration", "")
        else:
            # استخدام البيانات المستخرجة تلقائياً
            start_idx = (i * 4) % len(all_keywords)
            section_keywords = []
            for j in range(4):
                idx = (start_idx + j) % len(all_keywords)
                if all_keywords[idx] not in section_keywords:
                    section_keywords.append(all_keywords[idx])
            section_title = section_keywords[0] if section_keywords else f"القسم {i+1}"
            narration = ""
        
        # التأكد من وجود 4 كلمات مفتاحية
        while len(section_keywords) < 4:
            if all_keywords:
                for kw in all_keywords:
                    if kw not in section_keywords:
                        section_keywords.append(kw)
                        break
            else:
                section_keywords.append("مفهوم")
        
        # إذا ماكو شرح كافي، نستخدم النص الأصلي
        if not narration or len(narration.split()) < 20:
            narration = original_parts[i] if i < len(original_parts) else ""
            if not narration:
                narration = f"في هذا القسم سنتعرف على {', '.join(section_keywords[:3])}. " * 10
        
        # تقدير المدة الزمنية (كل 3 كلمات = ثانية واحدة تقريباً)
        duration_estimate = max(45, len(narration.split()) // 3)
        
        final_sections.append({
            "title": section_title,
            "keywords": section_keywords[:4],
            "narration": narration,
            "duration_estimate": duration_estimate,
            "_keyword_images": [None] * 4,  # سيتم ملؤها لاحقاً
            "_image_bytes": None
        })
    
    # ───────────────────────────────────────────────────────────────────────────
    # تجهيز النتيجة النهائية
    # ───────────────────────────────────────────────────────────────────────────
    
    summary = f"شرحنا في هذه المحاضرة: {', '.join(all_keywords[:8])}"
    key_points = all_keywords[:5] if len(all_keywords) >= 5 else all_keywords + ["نقطة"] * (5 - len(all_keywords))
    
    return {
        "lecture_type": lecture_type,
        "title": title,
        "sections": final_sections,
        "summary": summary,
        "key_points": key_points,
        "all_keywords": all_keywords
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 10. استخراج النص من ملف PDF
# ═══════════════════════════════════════════════════════════════════════════════

async def extract_full_text_from_pdf(pdf_bytes: bytes) -> str:
    """
    استخراج النص الكامل من ملف PDF.
    """
    import PyPDF2
    
    try:
        reader = PyPDF2.PdfReader(io.BytesIO(pdf_bytes))
        pages = []
        
        for page in reader.pages:
            page_text = page.extract_text() or ""
            if page_text.strip():
                pages.append(page_text)
        
        full_text = "\n\n".join(pages)
        print(f"[INFO] Extracted {len(full_text)} characters from PDF")
        return full_text
        
    except Exception as e:
        print(f"[ERROR] Failed to extract text from PDF: {e}")
        raise


# ═══════════════════════════════════════════════════════════════════════════════
# 11. توليد الصور للكلمات المفتاحية
# ═══════════════════════════════════════════════════════════════════════════════

# ألوان متناسقة حسب نوع المحاضرة
_TYPE_COLORS = {
    'medicine': (231, 76, 126),   # وردي
    'math': (52, 152, 219),       # أزرق
    'physics': (52, 152, 219),    # أزرق
    'chemistry': (46, 204, 113),  # أخضر
    'history': (230, 126, 34),    # برتقالي
    'biology': (46, 204, 113),    # أخضر
    'other': (155, 89, 182),      # بنفسجي
}

def _get_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """
    تحميل خط مناسب للنصوص العربية والإنجليزية.
    """
    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/app/fonts/Amiri-Bold.ttf",
        "fonts/Amiri-Bold.ttf",
    ]
    
    for path in font_paths:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    
    # إذا ماكو أي خط، نستخدم الخط الافتراضي
    return ImageFont.load_default()


def _make_colored_image(keyword: str, color: tuple) -> bytes:
    """
    إنشاء صورة ملونة احترافية تحمل الكلمة المفتاحية.
    هذه الصورة مضمونة 100% ولا تعتمد على أي API خارجي.
    """
    W, H = 400, 300
    
    # إنشاء صورة بيضاء
    img = PILImage.new("RGB", (W, H), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    
    # خلفية متدرجة خفيفة
    for y in range(H):
        t = y / H
        r = int(255 * (1 - t) + color[0] * t * 0.2)
        g = int(255 * (1 - t) + color[1] * t * 0.2)
        b = int(255 * (1 - t) + color[2] * t * 0.2)
        draw.line([(0, y), (W, y)], fill=(r, g, b))
    
    # إطار ملون أنيق
    draw.rounded_rectangle([(8, 8), (W-8, H-8)], radius=15, outline=color, width=6)
    
    # دائرة زخرفية في المنتصف
    draw.ellipse([(W//2-50, H//2-50), (W//2+50, H//2+50)], fill=(*color, 25))
    
    # تحميل الخط
    font = _get_font(28, bold=True)
    
    # تقسيم الكلمة إلى أسطر إذا كانت طويلة
    words = keyword.split()
    lines = []
    current_line = []
    
    for word in words:
        current_line.append(word)
        line_text = ' '.join(current_line)
        try:
            bbox = font.getbbox(line_text)
            line_width = bbox[2] - bbox[0]
        except:
            line_width = len(line_text) * 16
        
        if line_width > W - 60:
            current_line.pop()
            if current_line:
                lines.append(' '.join(current_line))
            current_line = [word]
    
    if current_line:
        lines.append(' '.join(current_line))
    
    # رسم النص
    y = H//2 - (len(lines) * 40)//2
    for line in lines:
        try:
            bbox = font.getbbox(line)
            tw = bbox[2] - bbox[0]
        except:
            tw = len(line) * 16
        
        x = (W - tw) // 2
        
        # ظل
        draw.text((x+2, y+2), line, fill=(200, 200, 200), font=font)
        # النص الرئيسي
        draw.text((x, y), line, fill=color, font=font)
        
        y += 42
    
    # حفظ الصورة
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=90)
    return buf.getvalue()


async def _pollinations_generate(prompt: str) -> bytes | None:
    """
    محاولة توليد صورة باستخدام Pollinations.ai (مجاني).
    """
    import urllib.parse
    
    clean_prompt = prompt[:200].replace("\n", " ")
    encoded = urllib.parse.quote(clean_prompt)
    url = f"https://image.pollinations.ai/prompt/{encoded}?width=400&height=300&nologo=true&model=flux"
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    raw = await resp.read()
                    if len(raw) > 5000:
                        print(f"[OK] Pollinations image generated")
                        return raw
    except Exception as e:
        print(f"[WARN] Pollinations failed: {e}")
    
    return None


async def _picsum_generate() -> bytes | None:
    """
    محاولة جلب صورة من Lorem Picsum (صور عشوائية مجانية).
    """
    try:
        url = f"https://picsum.photos/400/300?random={random.randint(1, 1000)}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    print(f"[OK] Picsum fallback image used")
                    return await resp.read()
    except Exception as e:
        print(f"[WARN] Picsum failed: {e}")
    
    return None


async def fetch_image_for_keyword(
    keyword: str,
    section_title: str = "",
    lecture_type: str = "other",
    image_search_en: str = "",
) -> bytes:
    """
    جلب صورة للكلمة المفتاحية.
    يحاول أولاً Pollinations.ai، ثم Picsum، ثم صورة ملونة احتياطية.
    """
    print(f"[INFO] Fetching image for: {keyword}")
    
    # تحديد اللون المناسب
    color = _TYPE_COLORS.get(lecture_type, _TYPE_COLORS['other'])
    
    # 1. محاولة Pollinations.ai
    prompt = f"simple educational illustration of {keyword}, clean white background, minimal style"
    img_bytes = await _pollinations_generate(prompt)
    if img_bytes:
        return img_bytes
    
    # 2. محاولة Picsum
    img_bytes = await _picsum_generate()
    if img_bytes:
        return img_bytes
    
    # 3. صورة ملونة احتياطية (مضمونة 100%)
    print(f"[INFO] Using colored placeholder for: {keyword}")
    return _make_colored_image(keyword, color)
