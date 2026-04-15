#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
تحليل المحاضرات باستخدام الذكاء الاصطناعي
يدعم: DeepSeek, Gemini, OpenRouter, Groq
مع تحليل محلي احتياطي
"""

import json
import re
import io
import asyncio
import aiohttp
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════════════════
#  استيراد المفاتيح من config
# ══════════════════════════════════════════════════════════════════════════════
try:
    from config import (
        DEEPSEEK_API_KEYS, GEMINI_API_KEYS, 
        OPENROUTER_API_KEYS, GROQ_API_KEYS
    )
except ImportError:
    DEEPSEEK_API_KEYS = []
    GEMINI_API_KEYS = []
    OPENROUTER_API_KEYS = []
    GROQ_API_KEYS = []
    logger.warning("⚠️ لم يتم العثور على مفاتيح API في config.py")


class QuotaExhaustedError(Exception):
    """يُرفع عند نفاد جميع المفاتيح."""
    pass


# ══════════════════════════════════════════════════════════════════════════════
#  اكتشاف نوع المادة
# ══════════════════════════════════════════════════════════════════════════════
def detect_subject(text: str) -> str:
    """اكتشاف نوع المادة من النص."""
    text_lower = text.lower()
    
    subjects = {
        "medicine": ["طب", "مرض", "علاج", "طبيب", "مريض", "جراحة", "ولادة", "قيصرية", "تشريح", "دواء"],
        "physics": ["فيزياء", "قوة", "حركة", "طاقة", "كهرباء", "مغناطيس", "جاذبية"],
        "chemistry": ["كيمياء", "تفاعل", "عنصر", "مركب", "حمض", "قاعدة", "جزيء", "ذرة"],
        "math": ["رياضيات", "معادلة", "حساب", "جبر", "هندسة", "تكامل", "تفاضل"],
        "engineering": ["هندسة", "بناء", "جسر", "تصميم", "إنشاء", "ميكانيكا"],
        "computer": ["برمجة", "حاسوب", "خوارزمية", "برنامج", "كود", "بايثون"],
        "history": ["تاريخ", "حرب", "معركة", "حضارة", "إمبراطورية", "خلافة"],
        "literature": ["أدب", "شعر", "رواية", "قصة", "كاتب", "شاعر"],
        "business": ["إدارة", "اقتصاد", "تسويق", "شركة", "استثمار", "أسهم"],
        "science": ["علوم", "أحياء", "نبات", "حيوان", "خلية", "وراثة"],
    }
    
    scores = {}
    for subject, keywords in subjects.items():
        score = sum(1 for kw in keywords if kw in text_lower)
        if score > 0:
            scores[subject] = score
    
    if scores:
        return max(scores, key=scores.get)
    return "other"


# ══════════════════════════════════════════════════════════════════════════════
#  استدعاء DeepSeek
# ══════════════════════════════════════════════════════════════════════════════
async def call_deepseek(prompt: str, max_tokens: int = 4000) -> str:
    """استدعاء DeepSeek API."""
    if not DEEPSEEK_API_KEYS:
        raise QuotaExhaustedError("لا توجد مفاتيح DeepSeek")
    
    for key in DEEPSEEK_API_KEYS:
        try:
            headers = {
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": "deepseek-chat",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": max_tokens,
                "temperature": 0.5
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://api.deepseek.com/v1/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=120)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        logger.info(f"✅ DeepSeek نجاح")
                        return data["choices"][0]["message"]["content"].strip()
                    elif resp.status == 402:
                        logger.warning(f"⚠️ DeepSeek رصيد منتهي")
                        continue
                    else:
                        continue
        except Exception as e:
            logger.warning(f"⚠️ DeepSeek خطأ: {str(e)[:50]}")
            continue
    
    raise QuotaExhaustedError("جميع مفاتيح DeepSeek منتهية")


# ══════════════════════════════════════════════════════════════════════════════
#  استدعاء Gemini
# ══════════════════════════════════════════════════════════════════════════════
async def call_gemini(prompt: str, max_tokens: int = 4000) -> str:
    """استدعاء Gemini API."""
    if not GEMINI_API_KEYS:
        raise QuotaExhaustedError("لا توجد مفاتيح Gemini")
    
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        raise QuotaExhaustedError("مكتبة google-genai غير مثبتة")
    
    for key in GEMINI_API_KEYS:
        try:
            client = genai.Client(api_key=key)
            response = await asyncio.to_thread(
                client.models.generate_content,
                model="gemini-2.0-flash",
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.5,
                    max_output_tokens=max_tokens
                )
            )
            logger.info(f"✅ Gemini نجاح")
            return response.text.strip()
        except Exception as e:
            err = str(e)
            if "quota" in err.lower() or "429" in err:
                logger.warning(f"⚠️ Gemini حصة منتهية")
                continue
            else:
                logger.warning(f"⚠️ Gemini خطأ: {err[:50]}")
                continue
    
    raise QuotaExhaustedError("جميع مفاتيح Gemini منتهية")


# ══════════════════════════════════════════════════════════════════════════════
#  استدعاء OpenRouter
# ══════════════════════════════════════════════════════════════════════════════
async def call_openrouter(prompt: str, max_tokens: int = 4000) -> str:
    """استدعاء OpenRouter API."""
    if not OPENROUTER_API_KEYS:
        raise QuotaExhaustedError("لا توجد مفاتيح OpenRouter")
    
    models = [
        "deepseek/deepseek-chat:free",
        "google/gemini-2.0-flash-exp:free",
        "meta-llama/llama-3.3-70b-instruct:free",
    ]
    
    for key in OPENROUTER_API_KEYS:
        for model in models:
            try:
                headers = {
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://lecture-bot.com",
                    "X-Title": "Lecture Bot"
                }
                payload = {
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": max_tokens,
                    "temperature": 0.5
                }
                
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        "https://openrouter.ai/api/v1/chat/completions",
                        headers=headers,
                        json=payload,
                        timeout=aiohttp.ClientTimeout(total=120)
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            logger.info(f"✅ OpenRouter نجاح: {model}")
                            return data["choices"][0]["message"]["content"].strip()
                        else:
                            continue
            except Exception:
                continue
    
    raise QuotaExhaustedError("جميع مفاتيح OpenRouter منتهية")


# ══════════════════════════════════════════════════════════════════════════════
#  استدعاء Groq
# ══════════════════════════════════════════════════════════════════════════════
async def call_groq(prompt: str, max_tokens: int = 4000) -> str:
    """استدعاء Groq API."""
    if not GROQ_API_KEYS:
        raise QuotaExhaustedError("لا توجد مفاتيح Groq")
    
    models = ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"]
    
    for key in GROQ_API_KEYS:
        for model in models:
            try:
                headers = {
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json"
                }
                payload = {
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": max_tokens,
                    "temperature": 0.5
                }
                
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        "https://api.groq.com/openai/v1/chat/completions",
                        headers=headers,
                        json=payload,
                        timeout=aiohttp.ClientTimeout(total=90)
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            logger.info(f"✅ Groq نجاح: {model}")
                            return data["choices"][0]["message"]["content"].strip()
                        else:
                            continue
            except Exception:
                continue
    
    raise QuotaExhaustedError("جميع مفاتيح Groq منتهية")


# ══════════════════════════════════════════════════════════════════════════════
#  الدالة الرئيسية لاستدعاء AI مع تناوب المزودين
# ══════════════════════════════════════════════════════════════════════════════
async def call_ai(prompt: str, max_tokens: int = 4000) -> str:
    """
    استدعاء AI مع تناوب تلقائي بين المزودين.
    الأولوية: DeepSeek → Gemini → OpenRouter → Groq
    """
    providers = [
        ("DeepSeek", call_deepseek),
        ("Gemini", call_gemini),
        ("OpenRouter", call_openrouter),
        ("Groq", call_groq),
    ]
    
    for name, func in providers:
        logger.info(f"🔄 تجربة {name}...")
        try:
            return await func(prompt, max_tokens)
        except QuotaExhaustedError as e:
            logger.warning(f"⚠️ {name} فشل: {e}")
            continue
    
    raise QuotaExhaustedError("جميع المزودين فشلوا")


# ══════════════════════════════════════════════════════════════════════════════
#  تحليل محلي احتياطي (بدون API)
# ══════════════════════════════════════════════════════════════════════════════
def local_analyze(text: str, dialect: str = "msa") -> Dict:
    """
    تحليل محلي احتياطي يضمن دائماً نتيجة.
    يستخدم عندما تفشل جميع الـ APIs.
    """
    is_arabic = dialect not in ("english", "british")
    subject = detect_subject(text)
    
    # تنظيف النص
    text = re.sub(r'\s+', ' ', text).strip()
    
    # تقسيم إلى فقرات
    paragraphs = []
    for p in text.split('\n'):
        p = p.strip()
        if len(p) > 80:
            paragraphs.append(p)
    
    if len(paragraphs) < 3:
        words = text.split()
        chunk = max(200, len(words) // 4)
        for i in range(0, len(words), chunk):
            para = ' '.join(words[i:i+chunk])
            if len(para) > 50:
                paragraphs.append(para)
    
    # إنشاء الأقسام
    sections = []
    for i, para in enumerate(paragraphs[:5]):
        # استخراج عنوان
        first_sent = para.split('.')[0].split('؟')[0][:50]
        title = f"القسم {i+1}: {first_sent}" if is_arabic else f"Section {i+1}: {first_sent}"
        
        # استخراج كلمات مفتاحية
        words_list = re.findall(r'[\u0600-\u06FF]{4,}|[A-Za-z]{4,}', para)
        keywords = list(set(words_list))[:4]
        if not keywords:
            keywords = ["مصطلح 1", "مصطلح 2", "مصطلح 3"] if is_arabic else ["Term 1", "Term 2", "Term 3"]
        
        sections.append({
            "title": title,
            "keywords": keywords,
            "narration": para[:800],
            "duration_estimate": max(30, len(para) // 12)
        })
    
    if not sections:
        sections = [{
            "title": "المحتوى الرئيسي" if is_arabic else "Main Content",
            "keywords": ["مصطلح 1", "مصطلح 2"] if is_arabic else ["Term 1", "Term 2"],
            "narration": text[:800],
            "duration_estimate": 45
        }]
    
    return {
        "lecture_type": subject,
        "title": "ملخص المحاضرة" if is_arabic else "Lecture Summary",
        "sections": sections,
        "summary": text[:400]
    }


# ══════════════════════════════════════════════════════════════════════════════
#  حساب عدد الأقسام المناسب
# ══════════════════════════════════════════════════════════════════════════════
def compute_sections_count(text: str) -> tuple:
    """حساب عدد الأقسام المناسب حسب طول النص."""
    word_count = len(text.split())
    if word_count < 400:
        return 2, "6-8", 3000
    elif word_count < 800:
        return 3, "8-10", 4000
    elif word_count < 1500:
        return 4, "10-12", 5000
    else:
        return 5, "12-15", 6000


# ══════════════════════════════════════════════════════════════════════════════
#  الدالة الرئيسية لتحليل المحاضرة
# ══════════════════════════════════════════════════════════════════════════════
async def analyze_lecture(text: str, dialect: str = "msa") -> Dict:
    """
    تحليل المحاضرة إلى أقسام مع كلمات مفتاحية وشرح.
    
    Args:
        text: نص المحاضرة
        dialect: اللهجة المطلوبة (iraq, egypt, syria, gulf, msa, english)
    
    Returns:
        dict: بيانات المحاضرة المحللة
    """
    is_arabic = dialect not in ("english", "british")
    subject = detect_subject(text)
    num_sections, narration_sentences, max_tokens = compute_sections_count(text)
    
    # تحديد لهجة الشرح
    dialect_names = {
        "iraq": "العراقية", "egypt": "المصرية", "syria": "الشامية",
        "gulf": "الخليجية", "msa": "الفصحى"
    }
    dialect_name = dialect_names.get(dialect, "الفصحى")
    
    text_limit = min(len(text), 4000)
    
    # بناء prompt
    if is_arabic:
        prompt = f"""أنت معلم خبير في تبسيط المحاضرات.

حلل النص التالي إلى {num_sections} أقسام تعليمية.

النص:
---
{text[:text_limit]}
---

لكل قسم قدم:
1. title: عنوان واضح وجذاب للقسم
2. keywords: 3-5 كلمات مفتاحية (مصطلحات مهمة)
3. narration: شرح مبسط وممتع ({narration_sentences} جمل) باللهجة {dialect_name}

أرجع JSON فقط:
{{"title": "عنوان المحاضرة", "sections": [{{"title": "عنوان القسم", "keywords": ["مصطلح1", "مصطلح2"], "narration": "الشرح..."}}], "summary": "ملخص عام (3-4 جمل)"}}"""
    else:
        prompt = f"""You are an expert teacher.

Analyze this text into {num_sections} sections.

Text:
{text[:text_limit]}

For each section provide:
1. title: Clear section title
2. keywords: 3-5 key terms
3. narration: Simplified explanation ({narration_sentences} sentences)

Return ONLY JSON:
{{"title": "Lecture Title", "sections": [{{"title": "Section", "keywords": ["term1", "term2"], "narration": "explanation..."}}], "summary": "Overall summary"}}"""

    try:
        # محاولة استخدام AI
        response = await call_ai(prompt, max_tokens)
        
        # تنظيف الاستجابة
        response = re.sub(r'^```json\s*', '', response.strip())
        response = re.sub(r'\s*```$', '', response)
        
        data = json.loads(response)
        data["lecture_type"] = subject
        
        # إضافة مدد تقديرية
        for sec in data["sections"]:
            narration_len = len(sec.get("narration", ""))
            sec["duration_estimate"] = max(25, narration_len // 12)
        
        logger.info(f"✅ تم التحليل بنجاح: {len(data['sections'])} أقسام")
        return data
        
    except Exception as e:
        logger.warning(f"⚠️ استخدام التحليل المحلي: {e}")
        return local_analyze(text, dialect)


# ══════════════════════════════════════════════════════════════════════════════
#  استخراج النص من PDF
# ══════════════════════════════════════════════════════════════════════════════
async def extract_full_text_from_pdf(pdf_bytes: bytes) -> str:
    """استخراج النص الكامل من ملف PDF."""
    try:
        import PyPDF2
        reader = PyPDF2.PdfReader(io.BytesIO(pdf_bytes))
        pages = []
        for page in reader.pages:
            page_text = page.extract_text() or ""
            if page_text.strip():
                pages.append(page_text)
        
        text = "\n\n".join(pages)
        if len(text.strip()) < 50:
            raise ValueError("النص المستخرج قصير جداً")
        
        return text
    except Exception as e:
        raise ValueError(f"فشل استخراج النص من PDF: {e}")
