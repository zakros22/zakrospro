#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
تحليل المحاضرات باستخدام الذكاء الاصطناعي
يدعم: DeepSeek, Gemini, OpenRouter, Groq, DuckDuckGo
مع تحليل محلي احتياطي
"""

import json
import re
import io
import asyncio
import aiohttp
import logging
from google import genai
from google.genai import types as genai_types
from config import (
    DEEPSEEK_API_KEYS, GEMINI_API_KEYS, OPENROUTER_API_KEYS, GROQ_API_KEYS
)

logger = logging.getLogger(__name__)


class QuotaExhaustedError(Exception):
    """يُرفع عند نفاد جميع المفاتيح من جميع المزودين."""
    pass


# ══════════════════════════════════════════════════════════════════════════════
#  أنماط الشرح حسب المادة الدراسية
# ══════════════════════════════════════════════════════════════════════════════
TEACHING_STYLES_AR = {
    "medicine": """
أنت طبيب استشاري خبير تشرح لطلاب الطب. أسلوبك:
- ابدأ بحالة سريرية واقعية: "تخيل معي مريضاً جاء للعيادة يشكو من..."
- اشرح الآلية بتشبيهات حياتية: "تخيل أن الخلية مثل قلعة والهرمون مثل المفتاح..."
- اذكر المصطلحات الطبية مع شرحها بالعامية
- اختتم بـ "الخلاصة السريرية" في 3 نقاط ذهبية
""",
    "science": """
أنت عالم تشرح العلوم بأسلوب تجريبي ممتع:
- ابدأ بتجربة ذهنية: "لو كنت في مختبر ورأيت..."
- اشرح الظاهرة بتشبيه من الحياة اليومية
- اذكر تطبيقات عملية من الواقع
- اختتم بـ "سر التجربة" - معلومة تثير الفضول
""",
    "math": """
أنت أستاذ رياضيات عبقري تشرح بالألغاز والتحديات:
- ابدأ بـ "تحدي اليوم": مسألة بسيطة تقود للمفهوم
- اشرح القاعدة كأنها "سر من أسرار الأرقام"
- استخدم رسوماً ذهنية: "تخيل الأعداد كأنها قطع ليغو..."
- اختتم بـ "خدعة رياضية" يمكن للطالب استخدامها
""",
    "physics": """
أنت فيزيائي عبقري تشرح قوانين الكون بأسلوب سحري:
- ابدأ بـ "ظاهرة غامضة": لماذا يحدث كذا؟
- اشرح القانون كأنه "تعويذة سحرية" تتحكم بالطبيعة
- استخدم تشبيهات من عالم الخيال والأفلام
- اختتم بـ "تطبيق خارق" يذهل الطالب
""",
    "chemistry": """
أنت كيميائي ساحر تشرح التفاعلات كأنها وصفات سحرية:
- ابدأ بـ "جرعة اليوم": تفاعل كيميائي مذهل
- اشرح التفاعل كأنه "رقصة بين الذرات"
- استخدم ألواناً وروائح في الوصف
- اختتم بـ "سر المختبر" - معلومة خطيرة لكن مفيدة
""",
    "engineering": """
أنت مهندس عبقري تشرح كيفية بناء الأشياء العظيمة:
- ابدأ بـ "تحدي البناء": كيف نبني جسراً/برجاً/طائرة؟
- اشرح المبدأ الهندسي بقصة من التاريخ الهندسي
- اذكر أخطاء شهيرة وكيف تم تجنبها
- اختتم بـ "نصيحة المهندس الذهبية"
""",
    "computer": """
أنت خبير برمجة وذكاء اصطناعي تشرح بأسلوب الـ "هاكر" الأخلاقي:
- ابدأ بـ "مشكلة تقنية" تحتاج حلاً ذكياً
- اشرح الخوارزمية كأنها "وصفة طبخ برمجية"
- استخدم تشبيهات من عالم الإنترنت والتطبيقات
- اختتم بـ "خدعة برمجية" تدهش المستخدم
""",
    "history": """
أنت راوي قصص تاريخي محترف تجعل الماضي حياً:
- ابدأ بـ "تخيل أنك في عام..." وانقل الطالب للزمن الماضي
- اروي الأحداث كأنها فيلم سينمائي بشخصيات وأبطال
- اربط الماضي بالحاضر: "وهذا ما نراه اليوم في..."
- اختتم بـ "درس التاريخ" - ماذا نتعلم من هذه القصة؟
""",
    "literature": """
أنت أديب وناقد فني تشرح جماليات النصوص:
- ابدأ بـ "لوحة فنية" من النص الأدبي
- حلل الأسلوب كأنك تكشف أسرار السحر في الكلمات
- اربط النص بمشاعر إنسانية عميقة
- اختتم بـ "اقتباس من ذهب" يلخص الدرس
""",
    "business": """
أنت رجل أعمال ناجح ومستشار إداري خبير:
- ابدأ بـ "قصة نجاح/فشل" من عالم الشركات الحقيقي
- اشرح المفهوم الإداري كأنه "لعبة استراتيجية"
- استخدم أرقاماً وإحصائيات واقعية
- اختتم بـ "نصيحة المليونير" - خطوة عملية للنجاح
""",
    "other": """
أنت معلم مبدع تشرح بأسلوب القصص والتشبيهات:
- ابدأ بقصة أو موقف يثير الفضول
- اشرح المفهوم بتشبيه من الحياة اليومية
- اذكر تطبيقات عملية وأمثلة واقعية
- اختتم بخلاصة في 3 نقاط سهلة التذكر
""",
}

TEACHING_STYLES_EN = {
    "medicine": "You are an expert medical consultant. Start with a patient case, explain with analogies, end with clinical pearls.",
    "science": "You are a passionate scientist. Start with a thought experiment, explain with everyday analogies, end with a science secret.",
    "math": "You are a math wizard. Start with a puzzle, explain as secrets of numbers, end with a math trick.",
    "physics": "You are a physicist explaining the universe's magic. Use fantasy analogies.",
    "chemistry": "You are a chemistry wizard with magical potions. Explain reactions as dances of atoms.",
    "engineering": "You are a master builder. Explain through engineering stories.",
    "computer": "You are a coding wizard. Explain algorithms as cooking recipes.",
    "history": "You are a time-traveling storyteller. Bring the past to life.",
    "literature": "You are a literary critic revealing the art of words.",
    "business": "You are a successful entrepreneur sharing business wisdom.",
    "other": "You are a creative teacher using stories and analogies.",
}


# ══════════════════════════════════════════════════════════════════════════════
#  اكتشاف نوع المادة
# ══════════════════════════════════════════════════════════════════════════════
def detect_subject(text: str) -> str:
    """اكتشاف نوع المادة من النص."""
    text_lower = text.lower()
    
    subjects = {
        "medicine": ["طب", "مرض", "علاج", "طبيب", "مريض", "جراحة", "ولادة", "قيصرية", "تشريح", "دواء", "مستشفى", "medicine", "disease", "treatment", "doctor", "patient", "surgery"],
        "physics": ["فيزياء", "قوة", "حركة", "طاقة", "كهرباء", "مغناطيس", "جاذبية", "نيوتن", "physics", "force", "motion", "energy", "electricity", "gravity"],
        "chemistry": ["كيمياء", "تفاعل", "عنصر", "مركب", "حمض", "قاعدة", "جزيء", "ذرة", "chemistry", "reaction", "element", "compound", "acid", "base"],
        "math": ["رياضيات", "معادلة", "حساب", "جبر", "هندسة", "تكامل", "تفاضل", "إحصاء", "math", "equation", "algebra", "calculus", "geometry"],
        "engineering": ["هندسة", "بناء", "جسر", "تصميم", "إنشاء", "ميكانيكا", "كهرباء", "engineering", "construction", "design", "bridge", "mechanical"],
        "computer": ["برمجة", "حاسوب", "خوارزمية", "برنامج", "كود", "بايثون", "جافا", "computer", "programming", "algorithm", "code", "python", "java"],
        "history": ["تاريخ", "حرب", "معركة", "حضارة", "إمبراطورية", "خلافة", "قديم", "history", "war", "battle", "civilization", "empire", "ancient"],
        "literature": ["أدب", "شعر", "رواية", "قصة", "كاتب", "شاعر", "نثر", "بلاغة", "literature", "poetry", "novel", "story", "writer", "poet"],
        "business": ["إدارة", "اقتصاد", "تسويق", "شركة", "استثمار", "أسهم", "تمويل", "business", "management", "marketing", "company", "investment", "finance"],
        "science": ["علوم", "أحياء", "نبات", "حيوان", "خلية", "وراثة", "بيئة", "science", "biology", "plant", "animal", "cell", "genetics", "environment"],
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
#  دوال التوليد حسب المزود
# ══════════════════════════════════════════════════════════════════════════════
async def _generate_deepseek(prompt: str, max_tokens: int = 6000) -> str:
    """توليد باستخدام DeepSeek."""
    if not DEEPSEEK_API_KEYS:
        raise QuotaExhaustedError("لا توجد مفاتيح DeepSeek")
    
    for key in DEEPSEEK_API_KEYS:
        try:
            headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
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
                        logger.info("✅ DeepSeek نجاح")
                        return data["choices"][0]["message"]["content"].strip()
                    elif resp.status == 402:
                        logger.warning(f"⚠️ DeepSeek رصيد منتهي للمفتاح {key[:15]}...")
                        continue
                    else:
                        body = await resp.text()
                        logger.warning(f"⚠️ DeepSeek {resp.status}: {body[:100]}")
                        continue
        except Exception as e:
            logger.warning(f"⚠️ DeepSeek خطأ: {str(e)[:80]}")
            continue
    
    raise QuotaExhaustedError("جميع مفاتيح DeepSeek منتهية")


async def _generate_gemini(prompt: str, max_tokens: int = 6000) -> str:
    """توليد باستخدام Gemini."""
    if not GEMINI_API_KEYS:
        raise QuotaExhaustedError("لا توجد مفاتيح Gemini")
    
    for key in GEMINI_API_KEYS:
        try:
            client = genai.Client(api_key=key)
            response = await asyncio.to_thread(
                client.models.generate_content,
                model="gemini-2.0-flash",
                contents=prompt,
                config=genai_types.GenerateContentConfig(
                    temperature=0.5,
                    max_output_tokens=max_tokens
                )
            )
            logger.info("✅ Gemini نجاح")
            return response.text.strip()
        except Exception as e:
            err = str(e)
            if "quota" in err.lower() or "429" in err:
                logger.warning(f"⚠️ Gemini حصة منتهية للمفتاح {key[:15]}...")
                continue
            else:
                logger.warning(f"⚠️ Gemini خطأ: {err[:80]}")
                continue
    
    raise QuotaExhaustedError("جميع مفاتيح Gemini منتهية")


async def _generate_openrouter(prompt: str, max_tokens: int = 6000) -> str:
    """توليد باستخدام OpenRouter."""
    if not OPENROUTER_API_KEYS:
        raise QuotaExhaustedError("لا توجد مفاتيح OpenRouter")
    
    models = [
        "deepseek/deepseek-chat:free",
        "google/gemini-2.0-flash-exp:free",
        "meta-llama/llama-3.3-70b-instruct:free",
        "qwen/qwen-2.5-72b-instruct:free",
    ]
    
    for key in OPENROUTER_API_KEYS:
        for model in models:
            try:
                headers = {
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://lecture-bot.com",
                    "X-Title": "Lecture Video Bot",
                }
                payload = {
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": max_tokens,
                    "temperature": 0.5,
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
                            content = data["choices"][0]["message"]["content"]
                            if content and content.strip():
                                logger.info(f"✅ OpenRouter نجاح: {model}")
                                return content.strip()
                        elif resp.status == 402:
                            logger.warning(f"⚠️ OpenRouter رصيد منتهي للمفتاح {key[:15]}...")
                            break
                        else:
                            continue
            except Exception as e:
                logger.warning(f"⚠️ OpenRouter خطأ: {str(e)[:80]}")
                continue
    
    raise QuotaExhaustedError("جميع مفاتيح OpenRouter منتهية")


async def _generate_groq(prompt: str, max_tokens: int = 6000) -> str:
    """توليد باستخدام Groq."""
    if not GROQ_API_KEYS:
        raise QuotaExhaustedError("لا توجد مفاتيح Groq")
    
    models = ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "gemma2-9b-it"]
    
    for key in GROQ_API_KEYS:
        for model in models:
            try:
                headers = {
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                }
                payload = {
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": max_tokens,
                    "temperature": 0.5,
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
                        elif resp.status == 429:
                            logger.warning(f"⚠️ Groq حد الطلبات للمفتاح {key[:15]}...")
                            continue
                        else:
                            continue
            except Exception as e:
                logger.warning(f"⚠️ Groq خطأ: {str(e)[:80]}")
                continue
    
    raise QuotaExhaustedError("جميع مفاتيح Groq منتهية")


async def _generate_duckduckgo(prompt: str, max_tokens: int = 6000) -> str:
    """توليد باستخدام DuckDuckGo AI (مجاني)."""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Content-Type": "application/json",
            "Origin": "https://duckduckgo.com",
            "Referer": "https://duckduckgo.com/",
        }
        
        payload = {
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": prompt[:4000]}],
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://duckduckgo.com/duckchat/v1/chat",
                headers=headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=90)
            ) as resp:
                if resp.status == 200:
                    full_response = ""
                    async for line in resp.content:
                        if line:
                            try:
                                line_text = line.decode('utf-8').strip()
                                if line_text.startswith('data: '):
                                    data = json.loads(line_text[6:])
                                    if data.get("message"):
                                        full_response += data["message"]
                            except:
                                pass
                    
                    if full_response.strip():
                        logger.info("✅ DuckDuckGo نجاح")
                        return full_response.strip()
        
        raise Exception("DuckDuckGo failed")
    except Exception as e:
        raise QuotaExhaustedError(f"DuckDuckGo: {e}")


async def call_ai(prompt: str, max_tokens: int = 6000) -> str:
    """
    استدعاء AI مع تناوب تلقائي بين المزودين.
    الأولوية: DeepSeek → Gemini → OpenRouter → Groq → DuckDuckGo
    """
    providers = [
        ("DeepSeek", lambda: _generate_deepseek(prompt, max_tokens)),
        ("Gemini", lambda: _generate_gemini(prompt, max_tokens)),
        ("OpenRouter", lambda: _generate_openrouter(prompt, max_tokens)),
        ("Groq", lambda: _generate_groq(prompt, max_tokens)),
        ("DuckDuckGo", lambda: _generate_duckduckgo(prompt, max_tokens)),
    ]
    
    for name, func in providers:
        logger.info(f"🔄 تجربة {name}...")
        try:
            return await func()
        except QuotaExhaustedError as e:
            logger.warning(f"⚠️ {name} فشل: {e}")
            continue
    
    raise QuotaExhaustedError("جميع المزودين فشلوا")


# ══════════════════════════════════════════════════════════════════════════════
#  تحليل محلي احتياطي
# ══════════════════════════════════════════════════════════════════════════════
def local_analyze(text: str, dialect: str) -> dict:
    """تحليل محلي احتياطي يضمن دائماً نتيجة."""
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
#  الدالة الرئيسية للتحليل
# ══════════════════════════════════════════════════════════════════════════════
def _compute_lecture_scale(text: str) -> tuple:
    """حساب عدد الأقسام المناسب."""
    word_count = len(text.split())
    if word_count < 400:
        return 2, "6-8", 3000
    elif word_count < 800:
        return 3, "8-10", 5000
    elif word_count < 1500:
        return 4, "10-12", 6000
    else:
        return 5, "12-15", 8000


async def analyze_lecture(text: str, dialect: str = "msa") -> dict:
    """
    تحليل المحاضرة إلى أقسام مع كلمات مفتاحية وشرح.
    
    Args:
        text: نص المحاضرة
        dialect: اللهجة المطلوبة
    
    Returns:
        dict: بيانات المحاضرة المحللة
    """
    is_arabic = dialect not in ("english", "british")
    subject = detect_subject(text)
    
    # اختيار أسلوب الشرح
    if is_arabic:
        teaching_style = TEACHING_STYLES_AR.get(subject, TEACHING_STYLES_AR["other"])
        dialect_names = {
            "iraq": "العراقية", "egypt": "المصرية", "syria": "الشامية",
            "gulf": "الخليجية", "msa": "الفصحى"
        }
        dialect_name = dialect_names.get(dialect, "الفصحى")
        dialect_instruction = f"استخدم اللهجة {dialect_name} في الشرح."
    else:
        teaching_style = TEACHING_STYLES_EN.get(subject, TEACHING_STYLES_EN["other"])
        dialect_instruction = "Use clear professional English."
    
    num_sections, narration_sentences, max_tokens = _compute_lecture_scale(text)
    text_limit = min(len(text), 4000 + num_sections * 500)
    
    # بناء prompt
    if is_arabic:
        prompt = f"""{teaching_style}

{dialect_instruction}

النص:
---
{text[:text_limit]}
---

حلل النص إلى {num_sections} أقسام تعليمية. لكل قسم قدم:
1. title: عنوان واضح وجذاب للقسم
2. keywords: 3-5 كلمات مفتاحية (مصطلحات مهمة في هذا القسم)
3. narration: شرح مبسط وممتع ({narration_sentences} جمل) باللهجة المطلوبة

أرجع JSON فقط:
{{"title": "عنوان المحاضرة", "sections": [{{"title": "عنوان القسم", "keywords": ["مصطلح1", "مصطلح2", "مصطلح3"], "narration": "الشرح..."}}], "summary": "ملخص عام (3-4 جمل)"}}"""
    else:
        prompt = f"""{teaching_style}

{dialect_instruction}

Text:
{text[:text_limit]}

Analyze into {num_sections} sections. For each section provide:
1. title: Clear section title
2. keywords: 3-5 key terms
3. narration: Simplified explanation ({narration_sentences} sentences)

Return ONLY JSON:
{{"title": "Lecture Title", "sections": [{{"title": "Section", "keywords": ["term1", "term2"], "narration": "explanation..."}}], "summary": "Overall summary"}}"""

    try:
        # محاولة استخدام AI
        response = await call_ai(prompt, max_tokens)
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
            raise ValueError("النص المستخرج قصير جداً - تأكد من أن الملف يحتوي على نص")
        
        return text
    except Exception as e:
        raise ValueError(f"فشل استخراج النص من PDF: {e}")


# تصدير QuotaExhaustedError
__all__ = ['analyze_lecture', 'extract_full_text_from_pdf', 'QuotaExhaustedError']
