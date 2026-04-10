# -*- coding: utf-8 -*-
"""
AI Analyzer Module - Complete Features
=======================================
الميزات الكاملة:
- تنظيف النص من null bytes والأحرف غير المرغوبة
- استخراج الكلمات المفتاحية من النص (عربي وإنجليزي)
- تحديد نوع المحاضرة (طبية، رياضيات، فيزياء، كيمياء، تاريخ، أحياء، أخرى)
- تقسيم النص إلى أقسام متساوية
- توليد شرح احترافي باستخدام Google Gemini (مع تدوير 9 مفاتيح)
- استخدام Groq كخدمة احتياطية (مع تدوير 9 مفاتيح)
- شرح احتياطي احترافي إذا فشل AI
- توليد صورة لكل قسم (صورة ملونة تحتوي على الكلمات المفتاحية)
- استخدام Pollinations.ai للصور (مع Picsum كاحتياطي)
- استخراج النص من ملفات PDF
"""

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
# 1. تنظيف النص
# ═══════════════════════════════════════════════════════════════════════════════

def clean_text(text: str) -> str:
    """تنظيف النص من null bytes والأحرف غير المرغوبة"""
    if not text:
        return ""
    text = str(text)
    text = text.replace('\x00', '').replace('\0', '')
    text = re.sub(r'[\x01-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


# ═══════════════════════════════════════════════════════════════════════════════
# 2. تحميل مفاتيح API
# ═══════════════════════════════════════════════════════════════════════════════

def _load_google_keys():
    """تحميل مفاتيح Google Gemini من متغيرات البيئة"""
    keys = []
    
    # الطريقة 1: مفاتيح مفصولة بفواصل
    raw_keys = os.getenv("GOOGLE_API_KEYS", "")
    if raw_keys:
        for k in raw_keys.split(","):
            k = k.strip()
            if k and k not in keys:
                keys.append(k)
    
    # الطريقة 2: مفاتيح مرقمة (GOOGLE_API_KEY_1 إلى _9)
    for i in range(1, 10):
        key = os.getenv(f"GOOGLE_API_KEY_{i}", "").strip()
        if key and key not in keys:
            keys.append(key)
    
    # الطريقة 3: مفتاح واحد
    single_key = os.getenv("GOOGLE_API_KEY", "").strip()
    if single_key and single_key not in keys:
        keys.append(single_key)
    
    return keys


def _load_groq_keys():
    """تحميل مفاتيح Groq من متغيرات البيئة"""
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


# تهيئة المفاتيح
_google_keys = _load_google_keys()
_current_google_idx = 0
_exhausted_google = set()

_groq_keys = _load_groq_keys()
_GROQ_MODELS = [
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "gemma2-9b-it",
]

print(f"[AI] Loaded {len(_google_keys)} Google API key(s)")
print(f"[AI] Loaded {len(_groq_keys)} Groq API key(s)")


def _next_google_key():
    """الحصول على مفتاح Google التالي المتاح"""
    global _current_google_idx
    if not _google_keys:
        return None
    for _ in range(len(_google_keys)):
        key = _google_keys[_current_google_idx % len(_google_keys)]
        if key not in _exhausted_google:
            return key
        _current_google_idx += 1
    return None


def _mark_google_exhausted(key: str):
    """تعليم مفتاح Google على أنه مستنفذ"""
    global _current_google_idx
    _exhausted_google.add(key)
    _current_google_idx += 1
    remaining = len(_google_keys) - len(_exhausted_google)
    print(f"[AI] Google key exhausted. {remaining} remaining.")


# ═══════════════════════════════════════════════════════════════════════════════
# 3. دوال الاتصال بالذكاء الاصطناعي
# ═══════════════════════════════════════════════════════════════════════════════

async def _google_generate(prompt: str, max_tokens: int = 8192) -> str:
    """توليد النص باستخدام Google Gemini"""
    models = ["gemini-2.0-flash", "gemini-2.0-flash-lite"]
    
    for _ in range(len(_google_keys) * 2):
        key = _next_google_key()
        if not key:
            break
        
        client = genai.Client(api_key=key)
        
        for model in models:
            try:
                response = await asyncio.to_thread(
                    client.models.generate_content,
                    model=model,
                    contents=prompt,
                    config=genai_types.GenerateContentConfig(
                        temperature=0.7,
                        max_output_tokens=max_tokens,
                    ),
                )
                print(f"[AI] Google success with {model}")
                return response.text.strip()
            except Exception as e:
                err = str(e)
                if "429" in err or "RESOURCE_EXHAUSTED" in err or "quota" in err.lower():
                    _mark_google_exhausted(key)
                    break
                else:
                    continue
    
    raise Exception("All Google keys exhausted")


async def _groq_generate(prompt: str, max_tokens: int = 8192) -> str:
    """توليد النص باستخدام Groq (احتياطي)"""
    if not _groq_keys:
        raise Exception("No Groq keys configured")
    
    for key in _groq_keys:
        for model in _GROQ_MODELS:
            try:
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
                            print(f"[AI] Groq success with {model}")
                            return data["choices"][0]["message"]["content"].strip()
            except Exception:
                continue
    
    raise Exception("All Groq attempts failed")


async def _ai_generate(prompt: str, max_tokens: int = 8192) -> str:
    """نظام التدوير: Google أولاً، ثم Groq"""
    # المرحلة 1: Google Gemini
    if _google_keys:
        try:
            return await _google_generate(prompt, max_tokens)
        except Exception as e:
            print(f"[AI] Google failed: {e}")
    
    # المرحلة 2: Groq
    if _groq_keys:
        try:
            return await _groq_generate(prompt, max_tokens)
        except Exception as e:
            print(f"[AI] Groq failed: {e}")
    
    raise Exception("All AI services failed")


# ═══════════════════════════════════════════════════════════════════════════════
# 4. استخراج الكلمات المفتاحية وتحديد نوع المحاضرة
# ═══════════════════════════════════════════════════════════════════════════════

def _extract_keywords(text: str, max_words: int = 30) -> list:
    """استخراج الكلمات المفتاحية من النص (عربي وإنجليزي)"""
    text = clean_text(text)
    
    stop_words = {
        'و', 'في', 'من', 'على', 'إلى', 'أن', 'هو', 'هي', 'هذا', 'هذه', 'كان', 'كانت',
        'مع', 'ما', 'لا', 'عن', 'إذا', 'لم', 'لن', 'قد', 'ثم', 'أو', 'أم', 'لكن',
        'حتى', 'بل', 'كل', 'بعض', 'the', 'a', 'an', 'is', 'are', 'was', 'were',
        'of', 'to', 'in', 'that', 'it', 'be', 'for', 'on', 'with', 'as', 'at',
        'by', 'this', 'and', 'or', 'but', 'from', 'they', 'we', 'you', 'i', 'he',
        'she', 'his', 'her', 'their', 'have', 'has', 'had'
    }
    
    words = re.findall(r'[\u0600-\u06FF]{4,}|[a-zA-Z]{4,}', text)
    word_freq = {}
    
    for w in words:
        w_lower = w.lower()
        if w_lower not in stop_words:
            word_freq[w] = word_freq.get(w, 0) + 1
    
    sorted_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)
    return [w[0] for w in sorted_words[:max_words]]


def _detect_lecture_type(text: str) -> str:
    """تحديد نوع المحاضرة من خلال الكلمات المفتاحية"""
    text_lower = clean_text(text).lower()
    
    medical_keywords = [
        'مرض', 'علاج', 'طبيب', 'جراحة', 'دواء', 'تشخيص', 'مريض', 'عرض', 'قلب', 'دم',
        'خلية', 'ورم', 'سرطان', 'endometriosis', 'cyst', 'inflammation', 'pain',
        'bleeding', 'menstrual', 'pelvic', 'diagnosis', 'treatment', 'surgery',
        'medicine', 'disease', 'heart', 'blood', 'cell', 'cancer'
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
    
    scores = {
        'medicine': sum(1 for kw in medical_keywords if kw in text_lower),
        'math': sum(1 for kw in math_keywords if kw in text_lower),
        'physics': sum(1 for kw in physics_keywords if kw in text_lower),
        'chemistry': sum(1 for kw in chemistry_keywords if kw in text_lower),
        'history': sum(1 for kw in history_keywords if kw in text_lower),
        'biology': sum(1 for kw in biology_keywords if kw in text_lower),
    }
    
    best_type = max(scores, key=scores.get)
    if scores[best_type] > 1:
        print(f"[AI] Detected lecture type: {best_type}")
        return best_type
    
    print("[AI] Detected lecture type: other")
    return 'other'


def _split_text_into_parts(text: str, num_parts: int) -> list:
    """تقسيم النص إلى أجزاء متساوية (للاستخدام كخطة احتياطية)"""
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
    while len(parts) < num_parts:
        parts.append("")
    
    if len(parts) > num_parts:
        while len(parts) > num_parts:
            parts[-2] = parts[-2] + " " + parts[-1]
            parts.pop()
    
    return parts


def _generate_fallback_narration(keywords: list, lecture_type: str) -> str:
    """توليد شرح احتياطي احترافي إذا فشل AI"""
    kw_str = '، '.join(keywords[:3])
    
    narrations = {
        'medicine': (
            f"دعونا نتحدث عن {kw_str}. هذا الموضوع مهم جداً في المجال الطبي. "
            f"أولاً، يجب أن نفهم تعريف {keywords[0]} بشكل دقيق. "
            f"ثانياً، نناقش الأعراض والعلامات المرتبطة بـ {keywords[1]}. "
            f"ثالثاً، نستعرض طرق التشخيص المتاحة لـ {keywords[2]}. "
            f"رابعاً، نتعرف على خيارات العلاج الحديثة. "
            f"خامساً، نتحدث عن المضاعفات المحتملة وكيفية تجنبها. "
            f"سادساً، نناقش طرق الوقاية وأهميتها. "
            f"سابعاً، نستعرض أحدث الأبحاث في هذا المجال. "
            f"ثامناً، نذكر بعض الحالات السريرية للتوضيح. "
            f"تاسعاً، نجيب على الأسئلة الشائعة حول {keywords[0]}. "
            f"وأخيراً، نلخص أهم النقاط التي يجب تذكرها."
        ),
        'math': (
            f"الآن سنشرح {kw_str} بالتفصيل. "
            f"لنبدأ بتعريف {keywords[0]} وفهم خصائصه الأساسية. "
            f"ثم نكتب المعادلة الرياضية الخاصة بـ {keywords[1]} ونحللها خطوة بخطوة. "
            f"بعد ذلك، نعطي مثالاً عددياً لتوضيح الفكرة بشكل عملي. "
            f"ثم نتحقق من صحة الحل ونتأكد من النتائج. "
            f"ننتقل إلى تطبيقات {keywords[2]} في الحياة العملية. "
            f"نناقش أيضاً الحالات الخاصة والشروط اللازمة لتطبيق هذه المعادلات. "
            f"نختم ببعض التمارين للتأكد من فهم الموضوع. "
            f"تذكروا دائماً أن التدريب هو مفتاح إتقان الرياضيات."
        ),
        'physics': (
            f"في هذا القسم ندرس {kw_str}. الفيزياء علم جميل يفسر الظواهر من حولنا. "
            f"نبدأ بشرح القانون الفيزيائي الأساسي المتعلق بـ {keywords[0]}. "
            f"ثم نعرض تجربة عملية توضح هذا القانون بشكل ملموس. "
            f"نحلل النتائج ونستنتج العلاقات بين المتغيرات المختلفة. "
            f"نربط هذه المفاهيم بحياتنا اليومية، مثل تطبيقات {keywords[1]}. "
            f"مثلاً، نرى تطبيقات هذا القانون في حركة السيارات أو سقوط الأجسام. "
            f"نناقش أيضاً حدود تطبيق هذا القانون والحالات التي لا ينطبق فيها. "
            f"أخيراً، نلخص أهم ما تعلمناه عن {keywords[2]}."
        ),
        'chemistry': (
            f"نتعرف الآن على {kw_str} في الكيمياء. "
            f"نبدأ بكتابة المعادلة الكيميائية الموزونة الخاصة بـ {keywords[0]}. "
            f"نحدد المواد المتفاعلة والناتجة ونشرح دور كل منها. "
            f"نشرح شروط التفاعل مثل درجة الحرارة والضغط والمواد الحفازة. "
            f"نحسب كمية المواد المتفاعلة والناتجة باستخدام الحسابات الكيميائية. "
            f"نذكر تطبيقات هذا التفاعل في الصناعة والحياة اليومية. "
            f"نناقش أيضاً المخاطر المحتملة وطرق التعامل الآمن مع {keywords[1]}. "
            f"نختم بمراجعة سريعة لأهم النقاط حول {keywords[2]}."
        ),
        'history': (
            f"اليوم سنسافر عبر الزمن لنتعرف على {kw_str}. التاريخ يعلمنا دروساً قيمة. "
            f"نبدأ بذكر التاريخ والمكان الذي وقعت فيه أحداث {keywords[0]}. "
            f"نتعرف على الشخصيات الرئيسية وأدوارها في هذه الأحداث. "
            f"نسرد الأحداث بتسلسل زمني واضح منذ البداية وحتى النهاية. "
            f"نحلل الأسباب التي أدت إلى {keywords[1]} وتطورها. "
            f"نناقش النتائج والآثار التي ترتبت على هذه الأحداث. "
            f"نستخلص الدروس والعبر المستفادة من {keywords[2]}. "
            f"نختم بربط هذه الأحداث بالواقع المعاصر وأهميتها اليوم."
        ),
        'biology': (
            f"في علم الأحياء، ندرس {kw_str}. الحياة مليئة بالأسرار الرائعة. "
            f"نبدأ بشرح التركيب الأساسي لـ {keywords[0]} ومكوناته. "
            f"ثم ننتقل إلى الوظائف الحيوية التي يؤديها {keywords[1]}. "
            f"نستخدم التشبيهات لتقريب المفاهيم، مثلاً نشبه الخلية بالمصنع الصغير. "
            f"نناقش أيضاً أهمية هذه العمليات للحفاظ على الحياة. "
            f"نذكر بعض الأمراض المرتبطة بخلل هذه الوظائف وكيفية علاجها. "
            f"نختم بمراجعة سريعة وتلخيص لأهم المعلومات عن {keywords[2]}."
        ),
        'other': (
            f"مرحباً بكم في هذا القسم الذي سنتعرف فيه على {kw_str}. "
            f"هذا الموضوع مهم جداً ويستحق التركيز والاهتمام. "
            f"نبدأ بتعريف {keywords[0]} وفهم معناه بدقة. "
            f"ثم نستعرض المعلومات المتعلقة بـ {keywords[1]} بالتفصيل مع أمثلة توضيحية. "
            f"نربط هذه المعلومات بالواقع العملي ونرى كيف تؤثر في حياتنا. "
            f"نجيب على الأسئلة الشائعة حول هذا الموضوع. "
            f"نذكر بعض النصائح والإرشادات المفيدة المتعلقة بـ {keywords[2]}. "
            f"أخيراً، نلخص أهم ما تم شرحه في هذا القسم."
        )
    }
    
    return narrations.get(lecture_type, narrations['other'])


# ═══════════════════════════════════════════════════════════════════════════════
# 5. الدالة الرئيسية: تحليل المحاضرة
# ═══════════════════════════════════════════════════════════════════════════════

async def analyze_lecture(text: str, dialect: str = "msa") -> dict:
    """تحليل المحاضرة بشكل كامل"""
    print("[AI] Starting lecture analysis...")
    
    # تنظيف النص
    text = clean_text(text)
    if not text:
        raise ValueError("النص فارغ بعد التنظيف")
    
    # استخراج الكلمات المفتاحية
    all_keywords = _extract_keywords(text, 40)
    print(f"[AI] Extracted {len(all_keywords)} keywords")
    
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
    
    print(f"[AI] Creating {num_sections} sections")
    
    # تجهيز النص للتحليل
    text_preview = text[:4000]
    
    # أسلوب المعلم حسب نوع المحاضرة
    teacher_styles = {
        'medicine': 'أنت طبيب استشاري تشرح لطلاب الطب. اشرح: التعريف، الأعراض، الأسباب، التشخيص، العلاج، المضاعفات، الوقاية.',
        'math': 'أنت أستاذ رياضيات. اشرح: تعريف المفاهيم، المعادلات، خطوات الحل، أمثلة عددية، تطبيقات، تمارين.',
        'physics': 'أنت فيزيائي. اشرح: القانون، التجربة، التحليل، التطبيقات الحياتية، العلاقات بين المتغيرات.',
        'chemistry': 'أنت كيميائي. اشرح: المعادلة، المواد، شروط التفاعل، الحسابات، التطبيقات الصناعية.',
        'history': 'أنت مؤرخ. اشرح: الزمان والمكان، الشخصيات، تسلسل الأحداث، الأسباب، النتائج، الدروس المستفادة.',
        'biology': 'أنت عالم أحياء. اشرح: التركيب، الوظيفة، العمليات الحيوية، الأهمية، الأمراض المرتبطة.',
        'other': 'أنت معلم خبير. اشرح: التعريف، التفاصيل، الأمثلة، التطبيقات، الأسئلة الشائعة، الخلاصة.'
    }
    
    teacher_style = teacher_styles.get(lecture_type, teacher_styles['other'])
    
    # أسلوب اللهجة
    dialect_instructions = {
        "iraq": "باللهجة العراقية. استخدم: هواية، گلت، هسا، چي، شلون، أكو، ماكو.",
        "egypt": "باللهجة المصرية. استخدم: أوي، معلش، كده، عايز، النهارده، يا جماعة.",
        "syria": "باللهجة الشامية. استخدم: هلق، شو، كتير، منيح، هيك، عم، فيكن.",
        "gulf": "باللهجة الخليجية. استخدم: زين، وايد، عاد، هاذي، أبشر، يالحبيب.",
        "msa": "بالعربية الفصحى البسيطة والواضحة."
    }
    
    dialect_inst = dialect_instructions.get(dialect, dialect_instructions["msa"])
    
    # بناء الـ Prompt
    prompt = f"""{teacher_style}
{dialect_inst}

**تعليمات صارمة للشرح:**
- اكتب شرحاً كاملاً ومتنوعاً (15-20 جملة) لكل قسم.
- لا تكرر نفس الجملة أبداً.
- لا تستخدم "يعني يعني" أو "هو هو هو".
- كل جملة يجب أن تضيف معلومة جديدة.
- فسر المصطلحات العلمية، أعط أمثلة واقعية، اربط الأفكار.
- استخدم أسلوب المعلم الذي يشرح لطلابه مباشرة.

**النص الأصلي:**
---
{text_preview}
---

**الكلمات المفتاحية المستخرجة:** {', '.join(all_keywords[:15])}

**المطلوب - {num_sections} أقسام:**

أرجع JSON فقط:
{{
  "title": "عنوان المحاضرة",
  "sections": [
    {{
      "title": "عنوان القسم",
      "keywords": ["كلمة1", "كلمة2", "كلمة3", "كلمة4"],
      "narration": "نص الشرح الكامل (15-20 جملة متنوعة)"
    }}
  ],
  "summary": "ملخص شامل للمحاضرة (5-7 جمل)"
}}
"""

    try:
        content = await _ai_generate(prompt, max_tokens=8192)
        content = content.strip()
        content = re.sub(r'^```json\s*', '', content)
        content = re.sub(r'\s*```$', '', content)
        
        result = json.loads(content)
        title = clean_text(result.get("title", all_keywords[0] if all_keywords else "المحاضرة التعليمية"))
        ai_sections = result.get("sections", [])
        summary = clean_text(result.get("summary", f"شرحنا في هذه المحاضرة: {', '.join(all_keywords[:8])}"))
        print(f"[AI] Successfully generated {len(ai_sections)} sections")
        
    except Exception as e:
        print(f"[AI] AI generation failed: {e}. Using fallback.")
        title = all_keywords[0] if all_keywords else "المحاضرة التعليمية"
        ai_sections = []
        summary = f"شرحنا في هذه المحاضرة: {', '.join(all_keywords[:8])}"
    
    # تقسيم النص الأصلي كخطة احتياطية
    original_parts = _split_text_into_parts(text, num_sections)
    
    # بناء الأقسام النهائية
    final_sections = []
    for i in range(num_sections):
        if i < len(ai_sections) and ai_sections[i].get("narration"):
            section = ai_sections[i]
            keywords = [clean_text(k) for k in section.get("keywords", [])[:4]]
            section_title = clean_text(section.get("title", f"القسم {i+1}"))
            narration = clean_text(section.get("narration", ""))
        else:
            # استخدام الكلمات المفتاحية المستخرجة
            start_idx = (i * 4) % len(all_keywords)
            keywords = []
            for j in range(4):
                idx = (start_idx + j) % len(all_keywords)
                if all_keywords[idx] not in keywords:
                    keywords.append(all_keywords[idx])
            section_title = keywords[0] if keywords else f"القسم {i+1}"
            # استخدام شرح احتياطي احترافي
            narration = _generate_fallback_narration(keywords, lecture_type)
        
        # التأكد من وجود 4 كلمات مفتاحية
        while len(keywords) < 4:
            keywords.append("مفهوم")
        
        final_sections.append({
            "title": section_title,
            "keywords": keywords[:4],
            "narration": narration,
            "duration_estimate": max(45, len(narration.split()) // 3),
            "_image_bytes": None
        })
    
    # توليد صورة لكل قسم
    print("[AI] Generating section images...")
    for section in final_sections:
        search_query = " ".join(section["keywords"][:3])
        try:
            section["_image_bytes"] = await fetch_image_for_keyword(
                keyword=search_query,
                section_title=section["title"],
                lecture_type=lecture_type,
                image_search_en=search_query
            )
            print(f"[AI] Generated image for: {section['title']}")
        except Exception as e:
            print(f"[AI] Image generation failed: {e}")
            section["_image_bytes"] = None
    
    return {
        "lecture_type": lecture_type,
        "title": title,
        "sections": final_sections,
        "summary": summary,
        "key_points": all_keywords[:5],
        "all_keywords": all_keywords
    }


async def extract_full_text_from_pdf(pdf_bytes: bytes) -> str:
    """استخراج النص الكامل من ملف PDF"""
    import PyPDF2
    reader = PyPDF2.PdfReader(io.BytesIO(pdf_bytes))
    pages = []
    for page in reader.pages:
        page_text = page.extract_text() or ""
        if page_text.strip():
            pages.append(page_text)
    text = "\n\n".join(pages)
    return clean_text(text)


# ═══════════════════════════════════════════════════════════════════════════════
# 6. توليد الصور
# ═══════════════════════════════════════════════════════════════════════════════

_TYPE_COLORS = {
    'medicine': (231, 76, 126),
    'math': (52, 152, 219),
    'physics': (52, 152, 219),
    'chemistry': (46, 204, 113),
    'history': (230, 126, 34),
    'biology': (46, 204, 113),
    'other': (155, 89, 182),
}


def _get_font(size: int) -> ImageFont.FreeTypeFont:
    """تحميل خط مناسب"""
    paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for p in paths:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except:
                pass
    return ImageFont.load_default()


def _make_colored_image(keyword: str, color: tuple) -> bytes:
    """إنشاء صورة ملونة تحتوي على الكلمة المفتاحية"""
    keyword = clean_text(keyword) or "مفهوم"
    W, H = 500, 350
    
    img = PILImage.new("RGB", (W, H), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    
    # خلفية متدرجة
    for y in range(H):
        t = y / H
        r = int(255 * (1 - t) + color[0] * t * 0.2)
        g = int(255 * (1 - t) + color[1] * t * 0.2)
        b = int(255 * (1 - t) + color[2] * t * 0.2)
        draw.line([(0, y), (W, y)], fill=(r, g, b))
    
    # إطار
    draw.rounded_rectangle([(10, 10), (W-10, H-10)], radius=20, outline=color, width=8)
    
    # دائرة زخرفية
    draw.ellipse([(W//2-60, H//2-60), (W//2+60, H//2+60)], fill=(*color, 25))
    
    # تحضير النص العربي
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
        keyword = get_display(arabic_reshaper.reshape(keyword[:30]))
    except:
        pass
    
    font = _get_font(32)
    
    # تقسيم النص إذا كان طويلاً
    words = keyword.split()
    lines = []
    current = []
    for w in words:
        current.append(w)
        line = ' '.join(current)
        try:
            if font.getbbox(line)[2] - font.getbbox(line)[0] > W - 60:
                current.pop()
                lines.append(' '.join(current))
                current = [w]
        except:
            pass
    if current:
        lines.append(' '.join(current))
    
    y = H//2 - (len(lines) * 40) // 2
    for line in lines:
        try:
            tw = font.getbbox(line)[2] - font.getbbox(line)[0]
        except:
            tw = len(line) * 18
        x = (W - tw) // 2
        draw.text((x+3, y+3), line, fill=(200, 200, 200), font=font)
        draw.text((x, y), line, fill=color, font=font)
        y += 45
    
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=90)
    return buf.getvalue()


async def _pollinations_generate(prompt: str) -> bytes | None:
    """محاولة توليد صورة باستخدام Pollinations.ai"""
    import urllib.parse
    encoded = urllib.parse.quote(prompt[:200])
    url = f"https://image.pollinations.ai/prompt/{encoded}?width=500&height=350&nologo=true"
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status == 200:
                    raw = await resp.read()
                    if len(raw) > 5000:
                        print(f"[AI] Pollinations image generated")
                        return raw
    except Exception as e:
        print(f"[AI] Pollinations failed: {e}")
    
    return None


async def _picsum_generate() -> bytes | None:
    """محاولة جلب صورة من Lorem Picsum"""
    try:
        url = f"https://picsum.photos/500/350?random={random.randint(1, 1000)}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    print(f"[AI] Picsum fallback image used")
                    return await resp.read()
    except:
        pass
    return None


async def fetch_image_for_keyword(
    keyword: str,
    section_title: str = "",
    lecture_type: str = "other",
    image_search_en: str = "",
) -> bytes:
    """جلب صورة للكلمة المفتاحية"""
    keyword = clean_text(keyword) or "مفهوم"
    color = _TYPE_COLORS.get(lecture_type, _TYPE_COLORS['other'])
    
    print(f"[AI] Fetching image for: {keyword[:50]}")
    
    # 1. محاولة Pollinations
    prompt = f"educational illustration of {keyword}, simple clean style"
    img_bytes = await _pollinations_generate(prompt)
    if img_bytes:
        return img_bytes
    
    # 2. محاولة Picsum
    img_bytes = await _picsum_generate()
    if img_bytes:
        return img_bytes
    
    # 3. صورة ملونة احتياطية
    print(f"[AI] Using colored placeholder")
    return _make_colored_image(keyword, color)
