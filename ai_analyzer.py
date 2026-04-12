# -*- coding: utf-8 -*-
"""
AI Analyzer Module - مع DeepSeek كمصدر أساسي
=============================================
ترتيب الأولوية:
1. DeepSeek (9 مفاتيح مع تدوير)
2. Google Gemini (9 مفاتيح مع تدوير)
3. Groq (9 مفاتيح مع تدوير)
4. OpenRouter (9 مفاتيح مع تدوير)
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


def clean_text(text: str) -> str:
    if not text:
        return ""
    text = str(text).replace('\x00', '').replace('\0', '')
    text = re.sub(r'[\x01-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


async def extract_full_text_from_pdf(pdf_bytes: bytes) -> str:
    try:
        import pdfplumber
        
        def _extract():
            with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                pages = []
                for page in pdf.pages:
                    page_text = page.extract_text() or ""
                    if page_text.strip():
                        pages.append(page_text)
                return "\n\n".join(pages)
        
        loop = asyncio.get_event_loop()
        text = await asyncio.wait_for(loop.run_in_executor(None, _extract), timeout=60.0)
        if len(text.strip()) > 100:
            print(f"[PDF] pdfplumber success: {len(text)} chars")
            return clean_text(text)
    except Exception as e:
        print(f"[PDF] pdfplumber failed: {e}")
    
    try:
        import PyPDF2
        
        def _extract():
            reader = PyPDF2.PdfReader(io.BytesIO(pdf_bytes))
            pages = []
            for page in reader.pages:
                page_text = page.extract_text() or ""
                if page_text.strip():
                    pages.append(page_text)
            return "\n\n".join(pages)
        
        loop = asyncio.get_event_loop()
        text = await asyncio.wait_for(loop.run_in_executor(None, _extract), timeout=60.0)
        print(f"[PDF] PyPDF2 success: {len(text)} chars")
        return clean_text(text)
    except Exception as e:
        print(f"[PDF] PyPDF2 failed: {e}")
        raise RuntimeError(f"فشل استخراج النص من PDF: {str(e)}")


# ═══════════════════════════════════════════════════════════════════════════════
# تحميل مفاتيح API
# ═══════════════════════════════════════════════════════════════════════════════

def _load_keys(env_name):
    """تحميل المفاتيح من متغيرات البيئة (تدعم مفاتيح متعددة بفواصل)"""
    keys = []
    raw = os.getenv(env_name, "")
    if raw:
        for k in raw.split(","):
            k = k.strip()
            if k and k not in keys:
                keys.append(k)
    return keys


# DeepSeek Keys (الأولوية الأولى)
_deepseek_keys = _load_keys("DEEPSEEK_API_KEYS")
if not _deepseek_keys:
    single = os.getenv("DEEPSEEK_API_KEY", "").strip()
    if single:
        _deepseek_keys = [single]
_current_deepseek_idx = 0
_exhausted_deepseek = set()

# Google Keys (الأولوية الثانية)
_google_keys = _load_keys("GOOGLE_API_KEYS")
if not _google_keys:
    single = os.getenv("GOOGLE_API_KEY", "").strip()
    if single:
        _google_keys = [single]
_current_google_idx = 0
_exhausted_google = set()

# Groq Keys (الأولوية الثالثة)
_groq_keys = _load_keys("GROQ_API_KEYS")
if not _groq_keys:
    single = os.getenv("GROQ_API_KEY", "").strip()
    if single:
        _groq_keys = [single]
_current_groq_idx = 0
_exhausted_groq = set()

# OpenRouter Keys (الأولوية الرابعة)
_openrouter_keys = _load_keys("OPENROUTER_API_KEYS")
if not _openrouter_keys:
    single = os.getenv("OPENROUTER_API_KEY", "").strip()
    if single:
        _openrouter_keys = [single]
_current_or_idx = 0
_exhausted_or = set()

print(f"[AI] Keys - DeepSeek: {len(_deepseek_keys)}, Google: {len(_google_keys)}, Groq: {len(_groq_keys)}, OpenRouter: {len(_openrouter_keys)}")


# ═══════════════════════════════════════════════════════════════════════════════
# دوال التدوير لكل مزود
# ═══════════════════════════════════════════════════════════════════════════════

def _next_deepseek_key():
    global _current_deepseek_idx
    if not _deepseek_keys:
        return None
    for _ in range(len(_deepseek_keys)):
        k = _deepseek_keys[_current_deepseek_idx % len(_deepseek_keys)]
        if k not in _exhausted_deepseek:
            return k
        _current_deepseek_idx += 1
    return None


def _mark_deepseek_exhausted(k):
    global _current_deepseek_idx
    _exhausted_deepseek.add(k)
    _current_deepseek_idx += 1
    remaining = len(_deepseek_keys) - len(_exhausted_deepseek)
    print(f"[DeepSeek] Key exhausted. {remaining} remaining.")


def _next_google_key():
    global _current_google_idx
    if not _google_keys:
        return None
    for _ in range(len(_google_keys)):
        k = _google_keys[_current_google_idx % len(_google_keys)]
        if k not in _exhausted_google:
            return k
        _current_google_idx += 1
    return None


def _mark_google_exhausted(k):
    global _current_google_idx
    _exhausted_google.add(k)
    _current_google_idx += 1
    remaining = len(_google_keys) - len(_exhausted_google)
    print(f"[Google] Key exhausted. {remaining} remaining.")


def _next_groq_key():
    global _current_groq_idx
    if not _groq_keys:
        return None
    for _ in range(len(_groq_keys)):
        k = _groq_keys[_current_groq_idx % len(_groq_keys)]
        if k not in _exhausted_groq:
            return k
        _current_groq_idx += 1
    return None


def _mark_groq_exhausted(k):
    global _current_groq_idx
    _exhausted_groq.add(k)
    _current_groq_idx += 1
    remaining = len(_groq_keys) - len(_exhausted_groq)
    print(f"[Groq] Key exhausted. {remaining} remaining.")


def _next_or_key():
    global _current_or_idx
    if not _openrouter_keys:
        return None
    for _ in range(len(_openrouter_keys)):
        k = _openrouter_keys[_current_or_idx % len(_openrouter_keys)]
        if k not in _exhausted_or:
            return k
        _current_or_idx += 1
    return None


def _mark_or_exhausted(k):
    global _current_or_idx
    _exhausted_or.add(k)
    _current_or_idx += 1
    remaining = len(_openrouter_keys) - len(_exhausted_or)
    print(f"[OpenRouter] Key exhausted. {remaining} remaining.")


# ═══════════════════════════════════════════════════════════════════════════════
# دوال التوليد لكل مزود
# ═══════════════════════════════════════════════════════════════════════════════

async def _deepseek_generate(prompt: str, max_tokens: int = 8192) -> str:
    """توليد النص باستخدام DeepSeek - الأولوية الأولى"""
    if not _deepseek_keys:
        raise Exception("No DeepSeek keys configured")
    
    for _ in range(len(_deepseek_keys) + 1):
        key = _next_deepseek_key()
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
                "temperature": 0.9
            }
            async with aiohttp.ClientSession() as s:
                async with s.post(
                    "https://api.deepseek.com/v1/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(90)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        print(f"[DeepSeek] Success")
                        return data["choices"][0]["message"]["content"].strip()
                    elif resp.status == 429 or resp.status == 402:
                        _mark_deepseek_exhausted(key)
                        print(f"[DeepSeek] Key exhausted (rate limit/quota)")
                        continue
                    else:
                        body = await resp.text()
                        print(f"[DeepSeek] Error {resp.status}: {body[:100]}")
                        continue
        except Exception as e:
            print(f"[DeepSeek] Exception: {str(e)[:100]}")
            continue
    
    raise Exception("All DeepSeek keys exhausted")


async def _google_generate(prompt: str, max_tokens: int = 8192) -> str:
    """توليد النص باستخدام Google Gemini - الأولوية الثانية"""
    models = ["gemini-2.0-flash", "gemini-2.0-flash-lite"]
    
    for _ in range(len(_google_keys) + 1):
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
                    config=genai_types.GenerateContentConfig(temperature=0.9, max_output_tokens=max_tokens)
                )
                print(f"[Google] Success: {model}")
                return response.text.strip()
            except Exception as e:
                err = str(e)
                if "429" in err or "RESOURCE_EXHAUSTED" in err or "quota" in err.lower():
                    _mark_google_exhausted(key)
                    print(f"[Google] Key exhausted")
                    break
                else:
                    continue
    
    raise Exception("All Google keys exhausted")


async def _groq_generate(prompt: str, max_tokens: int = 8192) -> str:
    """توليد النص باستخدام Groq - الأولوية الثالثة"""
    models = ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "gemma2-9b-it"]
    
    for _ in range(len(_groq_keys) + 1):
        key = _next_groq_key()
        if not key:
            break
        
        for model in models:
            try:
                headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
                payload = {
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": min(max_tokens, 8192),
                    "temperature": 0.9
                }
                async with aiohttp.ClientSession() as s:
                    async with s.post(
                        "https://api.groq.com/openai/v1/chat/completions",
                        headers=headers, json=payload, timeout=aiohttp.ClientTimeout(60)
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            print(f"[Groq] Success: {model}")
                            return data["choices"][0]["message"]["content"].strip()
                        elif resp.status == 429:
                            _mark_groq_exhausted(key)
                            print(f"[Groq] Key exhausted")
                            break
            except:
                continue
    
    raise Exception("All Groq keys exhausted")


async def _openrouter_generate(prompt: str, max_tokens: int = 8192) -> str:
    """توليد النص باستخدام OpenRouter - الأولوية الرابعة"""
    models = [
        "deepseek/deepseek-chat",
        "google/gemini-2.0-flash-exp:free",
        "google/gemini-2.0-flash-lite-preview-02-05:free",
        "nvidia/llama-3.1-nemotron-70b-instruct:free",
        "meta-llama/llama-3.2-3b-instruct:free"
    ]
    
    for _ in range(len(_openrouter_keys) + 1):
        key = _next_or_key()
        if not key:
            break
        
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
                async with aiohttp.ClientSession() as s:
                    async with s.post(
                        "https://openrouter.ai/api/v1/chat/completions",
                        headers=headers, json=payload, timeout=aiohttp.ClientTimeout(90)
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            content = data["choices"][0]["message"]["content"]
                            if content and content.strip():
                                print(f"[OpenRouter] Success: {model}")
                                return content.strip()
                        elif resp.status == 429:
                            _mark_or_exhausted(key)
                            print(f"[OpenRouter] Key exhausted")
                            break
            except:
                continue
    
    raise Exception("All OpenRouter keys exhausted")


# ═══════════════════════════════════════════════════════════════════════════════
# نظام التوليد الرئيسي - بالأولوية المطلوبة
# ═══════════════════════════════════════════════════════════════════════════════

async def _ai_generate(prompt: str, max_tokens: int = 8192) -> str:
    """
    نظام التوليد حسب الأولوية:
    1. DeepSeek (المصدر الأساسي)
    2. Google Gemini
    3. Groq
    4. OpenRouter
    """
    
    # 1. DeepSeek (الأولوية الأولى)
    if _deepseek_keys:
        try:
            return await _deepseek_generate(prompt, max_tokens)
        except Exception as e:
            print(f"[AI] DeepSeek failed: {e}")
    
    # 2. Google Gemini (الأولوية الثانية)
    if _google_keys:
        try:
            return await _google_generate(prompt, max_tokens)
        except Exception as e:
            print(f"[AI] Google failed: {e}")
    
    # 3. Groq (الأولوية الثالثة)
    if _groq_keys:
        try:
            return await _groq_generate(prompt, max_tokens)
        except Exception as e:
            print(f"[AI] Groq failed: {e}")
    
    # 4. OpenRouter (الأولوية الرابعة)
    if _openrouter_keys:
        try:
            return await _openrouter_generate(prompt, max_tokens)
        except Exception as e:
            print(f"[AI] OpenRouter failed: {e}")
    
    raise Exception("All AI services failed")


# ═══════════════════════════════════════════════════════════════════════════════
# استخراج الكلمات المفتاحية
# ═══════════════════════════════════════════════════════════════════════════════

def _extract_keywords(text: str, max_words: int = 30) -> list:
    text = clean_text(text)
    stop_words = {
        'و', 'في', 'من', 'على', 'إلى', 'أن', 'هو', 'هي', 'هذا', 'هذه', 'كان', 'كانت',
        'مع', 'ما', 'لا', 'عن', 'إذا', 'لم', 'لن', 'قد', 'ثم', 'أو', 'أم', 'لكن',
        'حتى', 'بل', 'كل', 'بعض', 'the', 'a', 'an', 'is', 'are', 'was', 'were',
        'of', 'to', 'in', 'that', 'it', 'be', 'for', 'on', 'with', 'as', 'at',
        'by', 'this', 'and', 'or', 'but', 'from', 'they', 'we', 'you', 'i'
    }
    words = re.findall(r'[\u0600-\u06FF]{4,}|[a-zA-Z]{4,}', text)
    freq = {}
    for w in words:
        wl = w.lower()
        if wl not in stop_words:
            freq[w] = freq.get(w, 0) + 1
    sorted_words = sorted(freq.items(), key=lambda x: x[1], reverse=True)
    return [w[0] for w in sorted_words[:max_words]]


def _is_english(text: str) -> bool:
    arabic_chars = len(re.findall(r'[\u0600-\u06FF]', text))
    english_chars = len(re.findall(r'[a-zA-Z]', text))
    return english_chars > arabic_chars


# ═══════════════════════════════════════════════════════════════════════════════
# دالة متوافقة مع bot.py القديم
# ═══════════════════════════════════════════════════════════════════════════════

def _detect_type(text: str) -> str:
    """تحديد نوع المحاضرة - نسخة متوافقة مع bot.py"""
    text_lower = clean_text(text).lower()
    medical = ['مرض', 'علاج', 'طبيب', 'جراحة', 'دواء', 'تشخيص', 'مريض', 'قلب', 'دم', 'خلية', 'ورم', 'سرطان', 'disease', 'treatment', 'diagnosis', 'symptom']
    math = ['معادلة', 'دالة', 'تفاضل', 'تكامل', 'جبر', 'هندسة', 'رياضيات', 'equation', 'function', 'calculus', 'algebra']
    physics = ['قوة', 'طاقة', 'حركة', 'سرعة', 'جاذبية', 'كهرباء', 'مغناطيس', 'فيزياء', 'force', 'energy', 'motion']
    chemistry = ['تفاعل', 'عنصر', 'مركب', 'جزيء', 'ذرة', 'حمض', 'قاعدة', 'كيمياء', 'reaction', 'element', 'compound']
    history = ['تاريخ', 'حرب', 'معركة', 'حضارة', 'إمبراطورية', 'ملك', 'ثورة', 'history', 'war', 'battle']
    biology = ['نبات', 'حيوان', 'بيئة', 'وراثة', 'تطور', 'خلية', 'biology', 'plant', 'animal', 'cell']
    
    scores = {
        'medicine': sum(1 for k in medical if k in text_lower),
        'math': sum(1 for k in math if k in text_lower),
        'physics': sum(1 for k in physics if k in text_lower),
        'chemistry': sum(1 for k in chemistry if k in text_lower),
        'history': sum(1 for k in history if k in text_lower),
        'biology': sum(1 for k in biology if k in text_lower)
    }
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else 'other'


# ═══════════════════════════════════════════════════════════════════════════════
# التحليل الذكي - تحديد النوع والعنوان
# ═══════════════════════════════════════════════════════════════════════════════

async def _smart_detect_type_and_title(text: str) -> tuple:
    preview = text[:3000]
    keywords = _extract_keywords(text, 20)
    is_eng = _is_english(text)
    
    if is_eng:
        type_prompt = """Analyze the following text and return:
1. Lecture type (choose: medicine, math, physics, chemistry, biology, history, literature, philosophy, law, economics, engineering, computer_science, psychology, sociology, other)
2. Suitable title
3. Main sections (3-6 sections)

Return JSON only: {"type": "...", "title": "...", "main_sections": ["...", "..."]}"""
    else:
        type_prompt = """حلل النص التالي وأعطني:
1. نوع المحاضرة (اختر: medicine, math, physics, chemistry, biology, history, literature, philosophy, law, economics, engineering, computer_science, psychology, sociology, other)
2. عنوان مناسب
3. الأقسام الرئيسية (3-6 أقسام)

أرجع JSON فقط: {"type": "...", "title": "...", "main_sections": ["...", "..."]}"""
    
    prompt = f"""{type_prompt}

Text:
---
{preview}
---

Keywords: {', '.join(keywords[:15])}"""
    
    try:
        content = await _ai_generate(prompt, 4096)
        content = re.sub(r'^```json\s*', '', content.strip())
        content = re.sub(r'\s*```$', '', content)
        res = json.loads(content)
        return (
            res.get("type", "other"),
            res.get("title", keywords[0] if keywords else ("Lecture" if is_eng else "محاضرة")),
            res.get("main_sections", [])
        )
    except Exception as e:
        print(f"[AI] Smart detect failed: {e}")
        ltype = _detect_type(text)
        title = keywords[0] if keywords else ("Lecture" if is_eng else "محاضرة")
        return ltype, title, []


# ═══════════════════════════════════════════════════════════════════════════════
# توليد الأسئلة التفاعلية
# ═══════════════════════════════════════════════════════════════════════════════

def _generate_questions_by_type(keywords: list, lecture_type: str, is_english: bool) -> tuple:
    kw = keywords[0] if keywords else ("concept" if is_english else "المفهوم")
    kw2 = keywords[1] if len(keywords) > 1 else kw
    
    if is_english:
        questions_map = {
            'medicine': (
                f"❓ Question: What is {kw}? What are its main symptoms and diagnosis methods?",
                f"✅ Answer: {kw} is a medical condition characterized by... Diagnosis involves..."
            ),
            'math': (
                f"❓ Question: How do we solve an equation involving {kw}? Explain the steps.",
                f"✅ Answer: To solve an equation with {kw}: 1) Identify variables, 2) Write equation, 3) Simplify, 4) Isolate variable, 5) Verify."
            ),
            'physics': (
                f"❓ Question: What physical law relates to {kw}? Write its mathematical formula.",
                f"✅ Answer: The law states that... Formula: ..."
            ),
            'chemistry': (
                f"❓ Question: Write the reaction equation for {kw} with {kw2}. What are the conditions?",
                f"✅ Answer: Reaction: ... Conditions: temperature..., pressure..., catalyst..."
            ),
            'biology': (
                f"❓ Question: What is the structure of {kw}? What is its main function?",
                f"✅ Answer: {kw} consists of... Its primary function is..."
            ),
            'history': (
                f"❓ Question: When and where did the events of {kw} take place? Who were the key figures?",
                f"✅ Answer: It occurred in... at... Key figures include..."
            ),
            'other': (
                f"❓ Question: What is {kw}? Why is it important?",
                f"✅ Answer: {kw} is... Its importance lies in..."
            )
        }
    else:
        questions_map = {
            'medicine': (
                f"❓ سؤال: ما هو تعريف {kw}؟ وما هي أبرز أعراضه وطرق تشخيصه؟",
                f"✅ الإجابة: {kw} هو حالة طبية تتميز بـ ... يتم تشخيصه عبر ..."
            ),
            'math': (
                f"❓ سؤال: كيف نحل معادلة تتضمن {kw}؟ اشرح الخطوات.",
                f"✅ الإجابة: لحل معادلة {kw}، نتبع: 1) تحديد المتغيرات، 2) كتابة المعادلة، 3) تبسيط الطرفين، 4) عزل المتغير، 5) التحقق من الحل."
            ),
            'physics': (
                f"❓ سؤال: ما القانون الفيزيائي المرتبط بـ {kw}؟ اكتب صيغته الرياضية.",
                f"✅ الإجابة: القانون هو ... وصيغته: ..."
            ),
            'chemistry': (
                f"❓ سؤال: اكتب معادلة تفاعل {kw} مع {kw2}. وما شروط التفاعل؟",
                f"✅ الإجابة: معادلة التفاعل: ... الشروط: درجة حرارة ...، ضغط ...، عامل حفاز ..."
            ),
            'biology': (
                f"❓ سؤال: ما هو تركيب {kw}؟ وما وظيفته الرئيسية؟",
                f"✅ الإجابة: {kw} يتكون من ... ووظيفته الأساسية هي ..."
            ),
            'history': (
                f"❓ سؤال: متى وأين وقعت أحداث {kw}؟ ومن الشخصيات الرئيسية فيها؟",
                f"✅ الإجابة: وقعت في عام ... في ... وأهم شخصياتها: ..."
            ),
            'other': (
                f"❓ سؤال: ما هو {kw}؟ وما أهميته؟",
                f"✅ الإجابة: {kw} هو ... وتكمن أهميته في ..."
            )
        }
    
    return questions_map.get(lecture_type, questions_map['other'])


# ═══════════════════════════════════════════════════════════════════════════════
# شرح احتياطي
# ═══════════════════════════════════════════════════════════════════════════════

def _generate_fallback_narration(keywords: list, lecture_type: str, is_english: bool) -> str:
    kw_str = ', '.join(keywords[:3])
    
    if is_english:
        narrations = {
            'medicine': f"We discuss {kw_str}. Definition, symptoms, diagnosis, treatment... " * 8,
            'math': f"To solve {kw_str}: 1) Identify variables, 2) Write equation, 3) Simplify, 4) Isolate, 5) Verify. " * 6,
            'physics': f"The law of {kw_str} states that... Formula and applications... " * 7,
            'chemistry': f"Reaction of {kw_str}: equation, conditions, applications... " * 7,
            'biology': f"In biology, {kw_str} refers to structure and function... " * 7,
            'history': f"Events of {kw_str}: date, location, key figures, causes, consequences... " * 8,
            'other': f"Learning about {kw_str}: definition, examples, applications... " * 10
        }
    else:
        narrations = {
            'medicine': f"نتحدث عن {kw_str}. تعريف، أعراض، تشخيص، علاج... " * 8,
            'math': f"لحل {kw_str}: 1) تحديد المتغيرات، 2) كتابة المعادلة، 3) تبسيط، 4) عزل المتغير، 5) التحقق. " * 6,
            'physics': f"قانون {kw_str} ينص على... الصيغة والتطبيقات... " * 7,
            'chemistry': f"تفاعل {kw_str}: المعادلة، الشروط، التطبيقات... " * 7,
            'biology': f"في الأحياء، {kw_str}: التركيب والوظيفة... " * 7,
            'history': f"أحداث {kw_str}: التاريخ، المكان، الشخصيات، الأسباب، النتائج... " * 8,
            'other': f"نتعرف على {kw_str}: تعريف، أمثلة، تطبيقات... " * 10
        }
    
    return narrations.get(lecture_type, narrations['other'])


# ═══════════════════════════════════════════════════════════════════════════════
# الدالة الرئيسية
# ═══════════════════════════════════════════════════════════════════════════════

async def analyze_lecture(text: str, dialect: str = "msa") -> dict:
    text = clean_text(text)
    if not text:
        raise ValueError("النص فارغ")
    
    is_eng = _is_english(text)
    print(f"[AI] Language: {'English' if is_eng else 'Arabic'}")
    
    print("[AI] Phase 1: Smart detection...")
    ltype, title, main_sections = await _smart_detect_type_and_title(text)
    print(f"[AI] Type: {ltype}, Title: {title}")
    
    keywords = _extract_keywords(text, 40)
    
    if main_sections:
        ns = len(main_sections)
    else:
        wc = len(text.split())
        if wc < 300:
            ns = 3
        elif wc < 600:
            ns = 4
        elif wc < 1000:
            ns = 5
        else:
            ns = 6
    
    preview = text[:4000]
    
    teacher_map = {
        'medicine': 'Doctor' if is_eng else 'طبيب استشاري',
        'math': 'Math Professor' if is_eng else 'أستاذ رياضيات',
        'physics': 'Physicist' if is_eng else 'فيزيائي',
        'chemistry': 'Chemist' if is_eng else 'كيميائي',
        'biology': 'Biologist' if is_eng else 'عالم أحياء',
        'history': 'Historian' if is_eng else 'مؤرخ',
        'other': 'Expert Teacher' if is_eng else 'معلم خبير'
    }
    teacher = teacher_map.get(ltype, teacher_map['other'])
    
    if is_eng:
        dial = "in clear, simple English"
        prompt = f"""You are a {teacher} explaining to students. Explain {dial}.

**Instructions:**
- Write 20-25 complete, varied sentences.
- Do NOT repeat sentences.
- Explain concepts, give examples, connect ideas.

**Title:** {title}
**Type:** {ltype}

**Text:**
---
{preview}
---

**Keywords:** {', '.join(keywords[:15])}

**Required - {ns} sections:**
Return JSON:
{{"sections": [{{"title": "Section title", "keywords": ["word1", "word2", "word3", "word4"], "narration": "Full explanation (20-25 sentences)"}}], "summary": "Summary (6-8 sentences)"}}"""
    else:
        dial_map = {"iraq": "بالعراقي", "egypt": "بالمصري", "syria": "بالشامي", "gulf": "بالخليجي", "msa": "بالفصحى"}
        dial = dial_map.get(dialect, "بالفصحى")
        prompt = f"""أنت {teacher} تشرح لطلابك. اشرح {dial}.

**تعليمات:**
- اكتب 20-25 جملة كاملة ومتنوعة.
- لا تكرر الجمل.
- اشرح المفاهيم، أعط أمثلة، اربط الأفكار.

**العنوان:** {title}
**النوع:** {ltype}

**النص:**
---
{preview}
---

**الكلمات:** {', '.join(keywords[:15])}

**المطلوب - {ns} أقسام:**
أرجع JSON:
{{"sections": [{{"title": "عنوان القسم", "keywords": ["كلمة1", "كلمة2", "كلمة3", "كلمة4"], "narration": "نص الشرح (20-25 جملة)"}}], "summary": "ملخص (6-8 جمل)"}}"""
    
    try:
        content = await _ai_generate(prompt, 8192)
        content = re.sub(r'^```json\s*', '', content.strip())
        content = re.sub(r'\s*```$', '', content)
        res = json.loads(content)
        ai_secs = res.get("sections", [])
        summary = clean_text(res.get("summary", ""))
        print(f"[AI] AI generation successful: {len(ai_secs)} sections")
    except Exception as e:
        print(f"[AI] AI failed, using fallback: {e}")
        ai_secs = []
        summary = f"Summary: {', '.join(keywords[:8])}" if is_eng else f"ملخص: {', '.join(keywords[:8])}"
    
    sections = []
    for i in range(ns):
        if i < len(ai_secs) and ai_secs[i].get("narration"):
            s = ai_secs[i]
            kw = [clean_text(k) for k in s.get("keywords", [])[:4]]
            st = clean_text(s.get("title", f"Section {i+1}" if is_eng else f"القسم {i+1}"))
            nar = clean_text(s.get("narration", ""))
        else:
            idx = (i * 4) % len(keywords)
            kw = [keywords[(idx + j) % len(keywords)] for j in range(4)]
            st = kw[0] if kw else (f"Section {i+1}" if is_eng else f"القسم {i+1}")
            nar = _generate_fallback_narration(kw, ltype, is_eng)
        
        while len(kw) < 4:
            kw.append("concept" if is_eng else "مفهوم")
        
        question, answer = _generate_questions_by_type(kw, ltype, is_eng)
        
        sections.append({
            "title": st,
            "keywords": kw[:4],
            "narration": nar,
            "question": question,
            "answer": answer,
            "duration_estimate": max(45, len(nar.split()) // 3),
            "_image_bytes": None
        })
    
    for s in sections:
        q = " ".join(s["keywords"][:4])
        s["_image_bytes"] = await fetch_image_for_keyword(q, s["title"], ltype, is_eng)
    
    return {
        "lecture_type": ltype,
        "title": title,
        "sections": sections,
        "summary": summary,
        "all_keywords": keywords,
        "is_english": is_eng
    }


# ═══════════════════════════════════════════════════════════════════════════════
# الصور
# ═══════════════════════════════════════════════════════════════════════════════

_TYPE_COLORS = {
    'medicine': (231, 76, 126), 'math': (52, 152, 219), 'physics': (52, 152, 219),
    'chemistry': (46, 204, 113), 'biology': (46, 204, 113), 'history': (230, 126, 34),
    'other': (155, 89, 182)
}


def _get_font(size: int):
    paths = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]
    for p in paths:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except:
                pass
    return ImageFont.load_default()


def _make_colored_image(keywords: str, color: tuple, is_english: bool = False) -> bytes:
    keywords = clean_text(keywords) or ("Concept" if is_english else "مفهوم")
    W, H = 500, 350
    img = Image.new("RGB", (W, H), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    
    for y in range(H):
        t = y / H
        r = int(255 * (1 - t) + color[0] * t * 0.3)
        g = int(255 * (1 - t) + color[1] * t * 0.3)
        b = int(255 * (1 - t) + color[2] * t * 0.3)
        draw.line([(0, y), (W, y)], fill=(r, g, b))
    
    draw.rounded_rectangle([(8, 8), (W-8, H-8)], radius=20, outline=color, width=6)
    draw.rounded_rectangle([(15, 15), (W-15, H-15)], radius=15, outline=(*color, 100), width=2)
    draw.ellipse([(W//2-70, H//2-70), (W//2+70, H//2+70)], fill=(*color, 30))
    
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
    import urllib.parse
    try:
        async with aiohttp.ClientSession() as s:
            url = f"https://image.pollinations.ai/prompt/{urllib.parse.quote(prompt[:200])}?width=500&height=350&nologo=true&model=flux"
            async with s.get(url, timeout=20) as r:
                if r.status == 200:
                    raw = await r.read()
                    if len(raw) > 5000:
                        return raw
    except:
        pass
    return None


async def _unsplash_generate(query: str) -> bytes | None:
    try:
        url = f"https://source.unsplash.com/featured/500x350/?{query.replace(' ', '-')[:50]},education"
        async with aiohttp.ClientSession() as s:
            async with s.get(url, timeout=15, allow_redirects=True) as r:
                if r.status == 200:
                    return await r.read()
    except:
        pass
    return None


async def fetch_image_for_keyword(keyword: str, section_title: str = "", lecture_type: str = "other", is_english: bool = False) -> bytes:
    keyword = clean_text(keyword) or ("concept" if is_english else "مفهوم")
    color = _TYPE_COLORS.get(lecture_type, _TYPE_COLORS['other'])
    
    if lecture_type == 'medicine':
        prompt = f"medical illustration of {keyword}, anatomy style"
    elif lecture_type == 'math':
        prompt = f"math equation illustration of {keyword}, whiteboard style"
    elif lecture_type == 'physics':
        prompt = f"physics diagram of {keyword}, scientific"
    elif lecture_type == 'chemistry':
        prompt = f"chemistry molecular structure of {keyword}"
    elif lecture_type == 'biology':
        prompt = f"biology diagram of {keyword}, scientific"
    elif lecture_type == 'history':
        prompt = f"historical illustration of {keyword}, educational"
    else:
        prompt = f"educational illustration of {keyword}, cartoon style"
    
    img = await _pollinations_generate(prompt)
    if img:
        return img
    img = await _unsplash_generate(keyword)
    if img:
        return img
    return _make_colored_image(keyword, color, is_english)
