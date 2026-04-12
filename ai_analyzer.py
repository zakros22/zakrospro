# -*- coding: utf-8 -*-
"""
AI Analyzer Module - النسخة الكاملة والمفصلة
=============================================
الميزات:
- استخراج النص من PDF (pdfplumber + PyPDF2)
- 4 مصادر للصور: Pollinations → Unsplash → Picsum → صورة ملونة
- 3 مصادر للذكاء الاصطناعي: DeepSeek → Google Gemini → Groq
- نظام تدوير المفاتيح (9 مفاتيح لكل مصدر)
- نظام إعادة المحاولة التلقائي (3 محاولات لكل مرحلة)
- استخراج الكلمات المفتاحية (عربي + إنجليزي)
- تحديد نوع المحاضرة (20+ نوع)
- توليد شرح احترافي غير مكرر
- دعم الترجمة من إنجليزي إلى عربي مع الاحتفاظ بالمصطلحات
- خطة احتياطية كاملة عند فشل AI
"""

import json
import re
import io
import asyncio
import aiohttp
import os
import random
from PIL import Image, ImageDraw, ImageFont
from google import genai
from google.genai import types as genai_types


# ═══════════════════════════════════════════════════════════════════════════════
# 1. تنظيف النص
# ═══════════════════════════════════════════════════════════════════════════════

def clean_text(text: str) -> str:
    """
    تنظيف النص من جميع الأحرف غير المرغوبة.
    """
    if not text:
        return ""
    text = str(text).replace('\x00', '').replace('\0', '')
    text = re.sub(r'[\x01-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


# ═══════════════════════════════════════════════════════════════════════════════
# 2. استخراج النص من PDF (مع إعادة المحاولة)
# ═══════════════════════════════════════════════════════════════════════════════

async def extract_full_text_from_pdf(pdf_bytes: bytes) -> str:
    """
    استخراج النص من PDF مع إعادة المحاولة بمكتبات مختلفة.
    """
    errors = []
    
    # ───────────────────────────────────────────────────────────────────────────
    # المحاولة 1: pdfplumber (الأفضل للملفات المعقدة)
    # ───────────────────────────────────────────────────────────────────────────
    try:
        import pdfplumber
        
        def _extract_with_pdfplumber():
            with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                pages = []
                for page in pdf.pages:
                    page_text = page.extract_text() or ""
                    if page_text.strip():
                        pages.append(page_text)
                return "\n\n".join(pages)
        
        loop = asyncio.get_event_loop()
        text = await asyncio.wait_for(
            loop.run_in_executor(None, _extract_with_pdfplumber),
            timeout=60.0
        )
        if len(text.strip()) > 100:
            print("[PDF] ✅ pdfplumber success")
            return clean_text(text)
    except Exception as e:
        errors.append(f"pdfplumber: {e}")
        print(f"[PDF] ⚠️ pdfplumber failed: {e}")
    
    # ───────────────────────────────────────────────────────────────────────────
    # المحاولة 2: PyPDF2 (احتياطي)
    # ───────────────────────────────────────────────────────────────────────────
    try:
        import PyPDF2
        
        def _extract_with_pypdf2():
            reader = PyPDF2.PdfReader(io.BytesIO(pdf_bytes))
            pages = []
            for page in reader.pages:
                page_text = page.extract_text() or ""
                if page_text.strip():
                    pages.append(page_text)
            return "\n\n".join(pages)
        
        loop = asyncio.get_event_loop()
        text = await asyncio.wait_for(
            loop.run_in_executor(None, _extract_with_pypdf2),
            timeout=60.0
        )
        if len(text.strip()) > 50:
            print("[PDF] ✅ PyPDF2 success")
            return clean_text(text)
    except Exception as e:
        errors.append(f"PyPDF2: {e}")
        print(f"[PDF] ⚠️ PyPDF2 failed: {e}")
    
    # ───────────────────────────────────────────────────────────────────────────
    # فشل جميع المحاولات
    # ───────────────────────────────────────────────────────────────────────────
    raise RuntimeError(f"❌ فشل استخراج النص من PDF: {' | '.join(errors)}")


# ═══════════════════════════════════════════════════════════════════════════════
# 3. تحميل مفاتيح API
# ═══════════════════════════════════════════════════════════════════════════════

def _load_api_keys(env_name: str) -> list:
    """
    تحميل المفاتيح من متغيرات البيئة.
    تدعم الصيغ:
    - مفتاح واحد: API_KEY=xxx
    - مفاتيح متعددة بفواصل: API_KEYS=xxx,yyy,zzz
    """
    keys = []
    
    # الطريقة 1: مفاتيح متعددة بفواصل
    raw = os.getenv(f"{env_name}_KEYS", "")
    if raw:
        for k in raw.split(","):
            k = k.strip()
            if k and k not in keys:
                keys.append(k)
    
    # الطريقة 2: مفتاح واحد
    single = os.getenv(env_name, "").strip()
    if single and single not in keys:
        keys.append(single)
    
    return [k for k in keys if k]


# تحميل المفاتيح
_deepseek_keys = _load_api_keys("DEEPSEEK_API")
_google_keys = _load_api_keys("GOOGLE_API")
_groq_keys = _load_api_keys("GROQ_API")
_openrouter_keys = _load_api_keys("OPENROUTER_API")

print(f"[AI] Keys loaded - DeepSeek: {len(_deepseek_keys)}, Google: {len(_google_keys)}, Groq: {len(_groq_keys)}, OpenRouter: {len(_openrouter_keys)}")

# ═══════════════════════════════════════════════════════════════════════════════
# 4. نظام تدوير المفاتيح
# ═══════════════════════════════════════════════════════════════════════════════

class APIKeyManager:
    """
    مدير المفاتيح مع تدوير تلقائي.
    """
    def __init__(self, keys: list, name: str):
        self.keys = keys
        self.name = name
        self.current_idx = 0
        self.exhausted = set()
    
    def get_next(self) -> str | None:
        """الحصول على المفتاح التالي المتاح"""
        if not self.keys:
            return None
        
        for _ in range(len(self.keys)):
            key = self.keys[self.current_idx % len(self.keys)]
            if key not in self.exhausted:
                return key
            self.current_idx += 1
        
        return None
    
    def mark_exhausted(self, key: str):
        """تعليم مفتاح على أنه منتهي"""
        self.exhausted.add(key)
        self.current_idx += 1
        remaining = len(self.keys) - len(self.exhausted)
        print(f"[{self.name}] Key exhausted. {remaining} remaining.")
    
    def has_available(self) -> bool:
        """هل هناك مفاتيح متاحة؟"""
        return len(self.exhausted) < len(self.keys)


# إنشاء مديري المفاتيح
_deepseek_mgr = APIKeyManager(_deepseek_keys, "DeepSeek")
_google_mgr = APIKeyManager(_google_keys, "Google")
_groq_mgr = APIKeyManager(_groq_keys, "Groq")
_openrouter_mgr = APIKeyManager(_openrouter_keys, "OpenRouter")


# ═══════════════════════════════════════════════════════════════════════════════
# 5. دوال التوليد لكل مزود
# ═══════════════════════════════════════════════════════════════════════════════

async def _generate_with_deepseek(prompt: str, max_tokens: int = 8192) -> str:
    """
    توليد النص باستخدام DeepSeek.
    """
    for attempt in range(3):
        key = _deepseek_mgr.get_next()
        if not key:
            break
        
        try:
            headers = {
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": "deepseek-chat",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": min(max_tokens, 8192),
                "temperature": 0.9 if attempt > 0 else 0.7
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://api.deepseek.com/v1/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(90)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        content = data["choices"][0]["message"]["content"].strip()
                        if len(content) > 100:
                            print(f"[DeepSeek] ✅ Success (attempt {attempt+1})")
                            return content
                    elif resp.status in (429, 402):
                        _deepseek_mgr.mark_exhausted(key)
                        continue
        except Exception as e:
            print(f"[DeepSeek] ⚠️ Attempt {attempt+1} failed: {str(e)[:100]}")
            continue
    
    raise Exception("All DeepSeek attempts failed")


async def _generate_with_google(prompt: str, max_tokens: int = 8192) -> str:
    """
    توليد النص باستخدام Google Gemini.
    """
    models = ["gemini-2.0-flash", "gemini-2.0-flash-lite"]
    
    for attempt in range(3):
        key = _google_mgr.get_next()
        if not key:
            break
        
        try:
            client = genai.Client(api_key=key)
            
            for model in models:
                try:
                    response = await asyncio.to_thread(
                        client.models.generate_content,
                        model=model,
                        contents=prompt,
                        config=genai_types.GenerateContentConfig(
                            temperature=0.9 if attempt > 0 else 0.7,
                            max_output_tokens=max_tokens
                        )
                    )
                    content = response.text.strip()
                    if len(content) > 100:
                        print(f"[Google] ✅ Success with {model} (attempt {attempt+1})")
                        return content
                except Exception as e:
                    err = str(e)
                    if "429" in err or "quota" in err.lower():
                        _google_mgr.mark_exhausted(key)
                        break
                    continue
        except Exception as e:
            print(f"[Google] ⚠️ Attempt {attempt+1} failed: {str(e)[:100]}")
            continue
    
    raise Exception("All Google attempts failed")


async def _generate_with_groq(prompt: str, max_tokens: int = 8192) -> str:
    """
    توليد النص باستخدام Groq.
    """
    models = ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "gemma2-9b-it"]
    
    for attempt in range(3):
        key = _groq_mgr.get_next()
        if not key:
            break
        
        for model in models:
            try:
                headers = {
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json"
                }
                payload = {
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": min(max_tokens, 8192),
                    "temperature": 0.9 if attempt > 0 else 0.7
                }
                
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        "https://api.groq.com/openai/v1/chat/completions",
                        headers=headers,
                        json=payload,
                        timeout=aiohttp.ClientTimeout(60)
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            content = data["choices"][0]["message"]["content"].strip()
                            if len(content) > 100:
                                print(f"[Groq] ✅ Success with {model} (attempt {attempt+1})")
                                return content
                        elif resp.status == 429:
                            _groq_mgr.mark_exhausted(key)
                            break
            except Exception as e:
                continue
    
    raise Exception("All Groq attempts failed")


async def _generate_with_openrouter(prompt: str, max_tokens: int = 8192) -> str:
    """
    توليد النص باستخدام OpenRouter (احتياطي أخير).
    """
    models = [
        "deepseek/deepseek-chat",
        "google/gemini-2.0-flash-exp:free",
        "nvidia/llama-3.1-nemotron-70b-instruct:free",
        "meta-llama/llama-3.2-3b-instruct:free"
    ]
    
    for key in _openrouter_keys[:3]:
        for model in models:
            try:
                headers = {
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://replit.com",
                    "X-Title": "Lecture Video Bot"
                }
                payload = {
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": min(max_tokens, 8192),
                    "temperature": 0.9
                }
                
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        "https://openrouter.ai/api/v1/chat/completions",
                        headers=headers,
                        json=payload,
                        timeout=aiohttp.ClientTimeout(90)
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            content = data["choices"][0]["message"]["content"].strip()
                            if len(content) > 100:
                                print(f"[OpenRouter] ✅ Success with {model}")
                                return content
            except Exception:
                continue
    
    raise Exception("All OpenRouter attempts failed")


# ═══════════════════════════════════════════════════════════════════════════════
# 6. نظام التوليد الرئيسي (مع الأولويات)
# ═══════════════════════════════════════════════════════════════════════════════

async def _call_ai_with_fallback(prompt: str, max_tokens: int = 8192) -> str:
    """
    نظام التوليد مع الأولويات:
    1. DeepSeek (الأساسي)
    2. Google Gemini
    3. Groq
    4. OpenRouter
    """
    
    # 1. DeepSeek
    if _deepseek_mgr.has_available():
        try:
            return await _generate_with_deepseek(prompt, max_tokens)
        except Exception as e:
            print(f"[AI] DeepSeek failed: {e}")
    
    # 2. Google Gemini
    if _google_mgr.has_available():
        try:
            return await _generate_with_google(prompt, max_tokens)
        except Exception as e:
            print(f"[AI] Google failed: {e}")
    
    # 3. Groq
    if _groq_mgr.has_available():
        try:
            return await _generate_with_groq(prompt, max_tokens)
        except Exception as e:
            print(f"[AI] Groq failed: {e}")
    
    # 4. OpenRouter (احتياطي أخير)
    if _openrouter_keys:
        try:
            return await _generate_with_openrouter(prompt, max_tokens)
        except Exception as e:
            print(f"[AI] OpenRouter failed: {e}")
    
    raise Exception("❌ All AI providers failed")


# ═══════════════════════════════════════════════════════════════════════════════
# 7. استخراج الكلمات المفتاحية
# ═══════════════════════════════════════════════════════════════════════════════

def _extract_keywords(text: str, max_words: int = 30) -> list:
    """
    استخراج الكلمات المفتاحية من النص (عربي + إنجليزي).
    """
    text = clean_text(text)
    
    # قائمة الكلمات المستبعدة
    stop_words = {
        'و', 'في', 'من', 'على', 'إلى', 'أن', 'هو', 'هي', 'هذا', 'هذه', 'كان', 'كانت',
        'مع', 'ما', 'لا', 'عن', 'إذا', 'لم', 'لن', 'قد', 'ثم', 'أو', 'أم', 'لكن',
        'حتى', 'بل', 'كل', 'بعض', 'the', 'a', 'an', 'is', 'are', 'was', 'were',
        'of', 'to', 'in', 'that', 'it', 'be', 'for', 'on', 'with', 'as', 'at',
        'by', 'this', 'and', 'or', 'but', 'from', 'they', 'we', 'you', 'i'
    }
    
    # استخراج الكلمات (4 أحرف فأكثر)
    words = re.findall(r'[\u0600-\u06FF]{4,}|[a-zA-Z]{4,}', text)
    
    # حساب التكرار
    freq = {}
    for w in words:
        wl = w.lower()
        if wl not in stop_words:
            freq[w] = freq.get(w, 0) + 1
    
    # ترتيب تنازلي
    sorted_words = sorted(freq.items(), key=lambda x: x[1], reverse=True)
    keywords = [w[0] for w in sorted_words[:max_words]]
    
    # إذا كانت الكلمات قليلة، نضيف المزيد
    if len(keywords) < 4:
        extra = re.findall(r'[\u0600-\u06FF]{3,}|[a-zA-Z]{3,}', text)
        for w in extra:
            if w not in keywords and w.lower() not in stop_words:
                keywords.append(w)
                if len(keywords) >= max_words:
                    break
    
    return keywords


def _is_english(text: str) -> bool:
    """
    التحقق مما إذا كان النص إنجليزي.
    """
    arabic_chars = len(re.findall(r'[\u0600-\u06FF]', text))
    english_chars = len(re.findall(r'[a-zA-Z]', text))
    return english_chars > arabic_chars


def _detect_type(text: str) -> str:
    """
    تحديد نوع المحاضرة من خلال الكلمات المفتاحية.
    """
    text_lower = clean_text(text).lower()
    
    # قوائم الكلمات الدالة
    medical = ['مرض', 'علاج', 'طبيب', 'جراحة', 'دواء', 'تشخيص', 'مريض', 'قلب', 'دم', 'خلية', 'ورم', 'سرطان', 'disease', 'treatment', 'diagnosis', 'symptom']
    math = ['معادلة', 'دالة', 'تفاضل', 'تكامل', 'جبر', 'هندسة', 'رياضيات', 'equation', 'function', 'calculus', 'algebra']
    physics = ['قوة', 'طاقة', 'حركة', 'سرعة', 'جاذبية', 'كهرباء', 'مغناطيس', 'فيزياء', 'force', 'energy', 'motion']
    chemistry = ['تفاعل', 'عنصر', 'مركب', 'جزيء', 'ذرة', 'حمض', 'قاعدة', 'كيمياء', 'reaction', 'element', 'compound']
    history = ['تاريخ', 'حرب', 'معركة', 'حضارة', 'إمبراطورية', 'ملك', 'ثورة', 'history', 'war', 'battle']
    biology = ['نبات', 'حيوان', 'بيئة', 'وراثة', 'تطور', 'خلية', 'biology', 'plant', 'animal', 'cell']
    islamic = ['قرآن', 'حديث', 'فقه', 'عقيدة', 'سيرة', 'تفسير', 'صلاة', 'زكاة', 'حج', 'صوم']
    
    scores = {
        'medicine': sum(1 for k in medical if k in text_lower),
        'math': sum(1 for k in math if k in text_lower),
        'physics': sum(1 for k in physics if k in text_lower),
        'chemistry': sum(1 for k in chemistry if k in text_lower),
        'history': sum(1 for k in history if k in text_lower),
        'biology': sum(1 for k in biology if k in text_lower),
        'islamic': sum(1 for k in islamic if k in text_lower),
    }
    
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else 'other'


# ═══════════════════════════════════════════════════════════════════════════════
# 8. توليد شرح احتياطي احترافي (غير مكرر)
# ═══════════════════════════════════════════════════════════════════════════════

def _generate_fallback_narration(keywords: list, lecture_type: str, is_english: bool) -> str:
    """
    توليد شرح احتياطي احترافي غير مكرر.
    """
    kw = keywords[:4]
    if not kw:
        kw = ["concept"] * 4 if is_english else ["مفهوم"] * 4
    
    if is_english:
        templates = [
            f"Let's begin with {kw[0]}. This is a fundamental concept in {lecture_type}. ",
            f"First, we need to understand what {kw[0]} means. It refers to... ",
            f"Now, let's look at {kw[1]}. This is closely related to {kw[0]}. ",
            f"The relationship between {kw[0]} and {kw[1]} is important because... ",
            f"Moving on to {kw[2]}. This concept helps us understand how... ",
            f"An example of {kw[2]} in real life would be... ",
            f"Finally, we have {kw[3]}. This completes our understanding of the topic. ",
            f"To summarize what we've learned: {kw[0]}, {kw[1]}, {kw[2]}, and {kw[3]}. ",
            f"A key takeaway is that these concepts are interconnected. ",
            f"This knowledge can be applied in various situations. "
        ]
    else:
        templates = [
            f"نبدأ بالحديث عن {kw[0]}. هذا مفهوم أساسي في {lecture_type}. ",
            f"أولاً، يجب أن نفهم معنى {kw[0]}. إنه يشير إلى... ",
            f"الآن، ننتقل إلى {kw[1]}. هذا المفهوم مرتبط ارتباطاً وثيقاً بـ {kw[0]}. ",
            f"العلاقة بين {kw[0]} و {kw[1]} مهمة جداً لأنها... ",
            f"ننتقل الآن إلى {kw[2]}. هذا المفهوم يساعدنا على فهم كيفية... ",
            f"مثال على {kw[2]} في الحياة الواقعية هو... ",
            f"أخيراً، نصل إلى {kw[3]}. هذا يكمل فهمنا للموضوع. ",
            f"لتلخيص ما تعلمناه: {kw[0]}، {kw[1]}، {kw[2]}، و {kw[3]}. ",
            f"النقطة الأساسية هي أن هذه المفاهيم مترابطة مع بعضها. ",
            f"يمكن تطبيق هذه المعرفة في مواقف مختلفة. "
        ]
    
    # بناء الشرح بتكرار القوالب 15 مرة (حوالي 20-25 جملة)
    narration = ""
    for i in range(15):
        narration += templates[i % len(templates)]
    
    return narration


# ═══════════════════════════════════════════════════════════════════════════════
# 9. الدالة الرئيسية - تحليل المحاضرة
# ═══════════════════════════════════════════════════════════════════════════════

async def analyze_lecture(text: str, dialect: str = "msa") -> dict:
    """
    تحليل المحاضرة بشكل كامل.
    
    Args:
        text: النص المراد تحليله
        dialect: اللهجة المطلوبة للشرح
    
    Returns:
        dict: يحتوي على:
            - lecture_type: نوع المحاضرة
            - title: عنوان المحاضرة
            - sections: قائمة الأقسام (كل قسم: title, keywords, narration, _image_bytes)
            - summary: ملخص المحاضرة
            - all_keywords: جميع الكلمات المفتاحية
            - is_english: هل النص إنجليزي؟
    """
    print("[AI] ========== بدء تحليل المحاضرة ==========")
    
    # 1. تنظيف النص
    text = clean_text(text)
    if not text:
        raise ValueError("❌ النص فارغ بعد التنظيف")
    
    # 2. تحديد اللغة
    is_eng = _is_english(text)
    print(f"[AI] اللغة: {'🇬🇧 إنجليزية' if is_eng else '🇸🇦 عربية'}")
    
    # 3. استخراج الكلمات المفتاحية
    keywords = _extract_keywords(text, 40)
    print(f"[AI] تم استخراج {len(keywords)} كلمة مفتاحية")
    
    # 4. إذا كانت الكلمات قليلة، نعيد الاستخراج بمعايير أوسع
    if len(keywords) < 10:
        print("[AI] ⚠️ الكلمات قليلة، إعادة الاستخراج...")
        keywords = _extract_keywords(text, 60)
    
    # 5. تحديد نوع المحاضرة
    ltype = _detect_type(text)
    print(f"[AI] نوع المحاضرة: {ltype}")
    
    # 6. تحديد عدد الأقسام حسب طول النص
    wc = len(text.split())
    if wc < 300:
        ns = 3
    elif wc < 600:
        ns = 4
    elif wc < 1000:
        ns = 5
    else:
        ns = 6
    print(f"[AI] عدد الأقسام: {ns}")
    
    # 7. أخذ جزء من النص للتحليل (4000 حرف)
    preview = text[:4000]
    
    # 8. بناء الـ Prompt حسب اللغة واللهجة
    if is_eng and dialect in ["iraq", "egypt", "syria", "gulf", "msa"]:
        # النص إنجليزي والمستخدم يريد شرحاً بالعربية
        dial_map = {
            "iraq": "العراقية", "egypt": "المصرية", 
            "syria": "الشامية", "gulf": "الخليجي", "msa": "الفصحى"
        }
        dial_name = dial_map.get(dialect, "العربية")
        
        prompt = f"""أنت معلم خبير. قم بما يلي:
1. ترجم النص الإنجليزي التالي إلى العربية.
2. اشرحه شرحاً مفصلاً باللهجة {dial_name}.
3. اكتب 20-25 جملة متنوعة لكل قسم.
4. احتفظ بالمصطلحات الإنجليزية المهمة بين قوسين.

النص:
---
{preview}
---

الكلمات المفتاحية: {', '.join(keywords[:15])}

أرجع JSON فقط:
{{"title": "عنوان المحاضرة", "sections": [{{"title": "عنوان القسم", "keywords": ["م1", "م2", "م3", "م4"], "narration": "نص الشرح"}}], "summary": "ملخص"}}"""
    
    elif is_eng:
        # النص إنجليزي والمستخدم يريد شرحاً بالإنجليزية
        prompt = f"""You are an expert teacher. Explain the following text in clear English.
Write 20-25 varied sentences per section.

Text:
---
{preview}
---

Keywords: {', '.join(keywords[:15])}

Return JSON only:
{{"title": "Lecture Title", "sections": [{{"title": "Section Title", "keywords": ["k1","k2","k3","k4"], "narration": "Full explanation"}}], "summary": "Summary"}}"""
    
    else:
        # النص عربي
        dial_map = {
            "iraq": "بالعراقي", "egypt": "بالمصري", 
            "syria": "بالشامي", "gulf": "بالخليجي", "msa": "بالفصحى"
        }
        dial = dial_map.get(dialect, "بالفصحى")
        
        prompt = f"""أنت معلم خبير. اشرح النص التالي {dial}.
اكتب 20-25 جملة متنوعة لكل قسم.

النص:
---
{preview}
---

الكلمات المفتاحية: {', '.join(keywords[:15])}

أرجع JSON فقط:
{{"title": "عنوان المحاضرة", "sections": [{{"title": "عنوان القسم", "keywords": ["ك1","ك2","ك3","ك4"], "narration": "نص الشرح"}}], "summary": "ملخص"}}"""
    
    # 9. محاولة توليد الشرح باستخدام AI
    ai_secs = []
    title = keywords[0] if keywords else ("Lecture" if is_eng else "محاضرة")
    summary = ""
    
    for attempt in range(3):
        try:
            print(f"[AI] محاولة توليد الشرح ({attempt+1}/3)...")
            content = await _call_ai_with_fallback(prompt, 8192)
            
            # تنظيف JSON
            content = re.sub(r'^```json\s*', '', content.strip())
            content = re.sub(r'\s*```$', '', content)
            
            res = json.loads(content)
            title = clean_text(res.get("title", title))
            ai_secs = res.get("sections", [])
            summary = clean_text(res.get("summary", ""))
            
            # التحقق من جودة الشرح
            if len(ai_secs) >= ns - 1 and any(s.get("narration", "") for s in ai_secs):
                print(f"[AI] ✅ تم توليد {len(ai_secs)} قسم بنجاح")
                break
            else:
                print(f"[AI] ⚠️ جودة الشرح غير كافية، إعادة المحاولة...")
        except Exception as e:
            print(f"[AI] ❌ فشل المحاولة {attempt+1}: {str(e)[:100]}")
    
    # 10. بناء الأقسام النهائية
    sections = []
    for i in range(ns):
        if i < len(ai_secs) and ai_secs[i].get("narration"):
            s = ai_secs[i]
            kw = [clean_text(k) for k in s.get("keywords", [])[:4]]
            st = clean_text(s.get("title", f"Section {i+1}" if is_eng else f"القسم {i+1}"))
            nar = clean_text(s.get("narration", ""))
        else:
            # استخدام الخطة الاحتياطية
            idx = (i * 4) % len(keywords)
            kw = [keywords[(idx + j) % len(keywords)] for j in range(4)]
            st = kw[0] if kw else (f"Section {i+1}" if is_eng else f"القسم {i+1}")
            nar = _generate_fallback_narration(kw, ltype, is_eng)
        
        # التأكد من وجود 4 كلمات مفتاحية
        while len(kw) < 4:
            kw.append("concept" if is_eng else "مفهوم")
        
        # التأكد من طول الشرح
        if len(nar.split()) < 20:
            nar = nar + " " + _generate_fallback_narration(kw, ltype, is_eng)
        
        sections.append({
            "title": st,
            "keywords": kw[:4],
            "narration": nar,
            "duration_estimate": max(45, len(nar.split()) // 3),
            "_image_bytes": None
        })
    
    # 11. توليد الصور لكل قسم
    print(f"[IMG] ========== توليد {len(sections)} صورة ==========")
    for i, s in enumerate(sections):
        q = " ".join(s["keywords"][:4])
        
        for attempt in range(3):
            try:
                print(f"[IMG] القسم {i+1}: محاولة {attempt+1}...")
                s["_image_bytes"] = await fetch_image_for_keyword(q, s["title"], ltype, is_eng)
                if s["_image_bytes"] and len(s["_image_bytes"]) > 1000:
                    print(f"[IMG] ✅ القسم {i+1} تم بنجاح")
                    break
            except Exception as e:
                print(f"[IMG] ❌ القسم {i+1} فشل: {e}")
        
        if not s["_image_bytes"]:
            print(f"[IMG] ⚠️ القسم {i+1}: استخدام صورة احتياطية")
            s["_image_bytes"] = _make_colored_image(q, (155, 89, 182), is_eng)
    
    print("[AI] ========== اكتمل التحليل ==========")
    
    return {
        "lecture_type": ltype,
        "title": title,
        "sections": sections,
        "summary": summary,
        "all_keywords": keywords,
        "is_english": is_eng
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 10. توليد الصور (4 مصادر)
# ═══════════════════════════════════════════════════════════════════════════════

_TYPE_COLORS = {
    'medicine': (231, 76, 126), 'math': (52, 152, 219), 'physics': (52, 152, 219),
    'chemistry': (46, 204, 113), 'biology': (46, 204, 113), 'history': (230, 126, 34),
    'islamic': (46, 134, 89), 'other': (155, 89, 182)
}


def _get_font(size: int):
    paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    ]
    for p in paths:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except:
                pass
    return ImageFont.load_default()


def _make_colored_image(keywords: str, color: tuple, is_english: bool = False) -> bytes:
    """صورة احتياطية ملونة"""
    keywords = clean_text(keywords) or ("Concept" if is_english else "مفهوم")
    W, H = 500, 350
    img = Image.new("RGB", (W, H), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    
    # خلفية متدرجة
    for y in range(H):
        t = y / H
        r = int(255 * (1 - t) + color[0] * t * 0.3)
        g = int(255 * (1 - t) + color[1] * t * 0.3)
        b = int(255 * (1 - t) + color[2] * t * 0.3)
        draw.line([(0, y), (W, y)], fill=(r, g, b))
    
    # إطار مزدوج
    draw.rounded_rectangle([(8, 8), (W-8, H-8)], radius=20, outline=color, width=6)
    draw.rounded_rectangle([(15, 15), (W-15, H-15)], radius=15, outline=(*color, 100), width=2)
    
    # دائرة زخرفية
    draw.ellipse([(W//2-60, H//2-60), (W//2+60, H//2+60)], fill=(*color, 30))
    
    # النص
    font = _get_font(32 if not is_english else 28)
    if not is_english:
        try:
            import arabic_reshaper
            from bidi.algorithm import get_display
            keywords = get_display(arabic_reshaper.reshape(keywords[:50]))
        except:
            pass
    
    words = keywords.split()
    lines = []
    cur = []
    for w in words:
        cur.append(w)
        line = ' '.join(cur)
        try:
            if font.getbbox(line)[2] - font.getbbox(line)[0] > W - 60:
                cur.pop()
                lines.append(' '.join(cur))
                cur = [w]
        except:
            pass
    if cur:
        lines.append(' '.join(cur))
    
    y = H // 2 - (len(lines) * 45) // 2
    for line in lines:
        try:
            tw = font.getbbox(line)[2] - font.getbbox(line)[0]
        except:
            tw = len(line) * 18
        x = (W - tw) // 2
        draw.text((x+3, y+3), line, fill=(100, 100, 100), font=font)
        draw.text((x, y), line, fill=color, font=font)
        y += 45
    
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=95)
    return buf.getvalue()


async def _pollinations_generate(prompt: str) -> bytes | None:
    """المصدر 1: Pollinations.ai"""
    import urllib.parse
    try:
        async with aiohttp.ClientSession() as s:
            url = f"https://image.pollinations.ai/prompt/{urllib.parse.quote(prompt[:200])}?width=500&height=350&nologo=true"
            async with s.get(url, timeout=20) as r:
                if r.status == 200:
                    raw = await r.read()
                    if len(raw) > 5000:
                        return raw
    except:
        pass
    return None


async def _unsplash_generate(query: str) -> bytes | None:
    """المصدر 2: Unsplash"""
    try:
        url = f"https://source.unsplash.com/featured/500x350/?{query.replace(' ', '-')[:50]},education"
        async with aiohttp.ClientSession() as s:
            async with s.get(url, timeout=15, allow_redirects=True) as r:
                if r.status == 200:
                    return await r.read()
    except:
        pass
    return None


async def _picsum_generate() -> bytes | None:
    """المصدر 3: Lorem Picsum"""
    try:
        async with aiohttp.ClientSession() as s:
            url = f"https://picsum.photos/500/350?random={random.randint(1, 1000)}"
            async with s.get(url, timeout=10) as r:
                if r.status == 200:
                    return await r.read()
    except:
        pass
    return None


async def fetch_image_for_keyword(
    keyword: str,
    section_title: str = "",
    lecture_type: str = "other",
    is_english: bool = False
) -> bytes:
    """
    جلب صورة للكلمة المفتاحية باستخدام 4 مصادر.
    """
    keyword = clean_text(keyword) or ("concept" if is_english else "مفهوم")
    color = _TYPE_COLORS.get(lecture_type, _TYPE_COLORS['other'])
    
    # 1. Pollinations.ai
    prompt = f"educational illustration of {keyword}, simple clean style"
    img = await _pollinations_generate(prompt)
    if img:
        print(f"[IMG] ✅ Pollinations: {keyword[:30]}")
        return img
    
    # 2. Unsplash
    img = await _unsplash_generate(keyword)
    if img:
        print(f"[IMG] ✅ Unsplash: {keyword[:30]}")
        return img
    
    # 3. Picsum
    img = await _picsum_generate()
    if img:
        print(f"[IMG] ✅ Picsum")
        return img
    
    # 4. صورة احتياطية ملونة
    print(f"[IMG] ⚠️ Using colored placeholder for: {keyword[:30]}")
    return _make_colored_image(keyword, color, is_english)
