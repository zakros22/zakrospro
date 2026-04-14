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
from google import genai
from google.genai import types as genai_types
from config import (
    DEEPSEEK_API_KEYS, GEMINI_API_KEYS, OPENROUTER_API_KEYS, GROQ_API_KEYS
)


class QuotaExhaustedError(Exception):
    """يُرفع عند نفاد جميع المفاتيح."""
    pass


# ══════════════════════════════════════════════════════════════════════════════
#  أنماط الشرح حسب المادة
# ══════════════════════════════════════════════════════════════════════════════
TEACHING_STYLES = {
    "medicine": """
أنت طبيب استشاري تشرح لطلاب الطب. أسلوبك:
- ابدأ بحالة سريرية واقعية: "مريض جاء يشكو من..."
- اشرح الآلية بتشبيهات حياتية
- اذكر المصطلحات الطبية مع شرحها
- اختم بخلاصة سريرية في 3 نقاط
""",
    "science": """
أنت عالم تشرح العلوم بأسلوب تجريبي ممتع:
- ابدأ بتجربة ذهنية: "تخيل أنك في مختبر..."
- اشرح الظاهرة بتشبيه من الحياة اليومية
- اذكر تطبيقات عملية
- اختم بسر علمي يثير الفضول
""",
    "math": """
أنت أستاذ رياضيات تشرح بالألغاز:
- ابدأ بتحدي: "هل تستطيع حل هذه المسألة؟"
- اشرح القاعدة كسر من أسرار الأرقام
- استخدم رسوماً ذهنية
- اختم بخدعة رياضية
""",
    "physics": """
أنت فيزيائي تشرح قوانين الكون:
- ابدأ بظاهرة غامضة
- اشرح القانون كتعويذة سحرية
- استخدم تشبيهات من الخيال
- اختم بتطبيق مذهل
""",
    "chemistry": """
أنت كيميائي تشرح التفاعلات كوصفات سحرية:
- ابدأ بتفاعل مذهل
- اشرحه كرقصة بين الذرات
- استخدم الألوان والروائح في الوصف
- اختم بسر المختبر
""",
    "engineering": """
أنت مهندس تشرح كيفية بناء الأشياء:
- ابدأ بتحدي بناء
- اشرح المبدأ بقصة هندسية
- اذكر أخطاء شهيرة وتجنبها
- اختم بنصيحة المهندس الذهبية
""",
    "computer": """
أنت خبير برمجة تشرح بأسلوب الهاكر:
- ابدأ بمشكلة تقنية
- اشرح الخوارزمية كوصفة طبخ
- استخدم تشبيهات تقنية
- اختم بخدعة برمجية
""",
    "history": """
أنت راوي قصص تاريخي:
- انقل المستمع للزمن الماضي
- اروي الأحداث كفيلم سينمائي
- اربط الماضي بالحاضر
- اختم بدرس مستفاد
""",
    "literature": """
أنت أديب وناقد:
- ابدأ بلوحة فنية من النص
- حلل الأسلوب كأسرار السحر
- اربط بمشاعر إنسانية
- اختم باقتباس من ذهب
""",
    "business": """
أنت خبير إدارة أعمال:
- ابدأ بقصة نجاح أو فشل حقيقية
- اشرح المفهوم كلعبة استراتيجية
- استخدم أرقاماً واقعية
- اختم بنصيحة المليونير
""",
    "other": """
أنت معلم مبدع:
- ابدأ بقصة تثير الفضول
- اشرح بتشبيه من الحياة
- اذكر تطبيقات عملية
- اختم بخلاصة في 3 نقاط
"""
}


# ══════════════════════════════════════════════════════════════════════════════
#  اكتشاف نوع المادة
# ══════════════════════════════════════════════════════════════════════════════
def detect_subject(text: str) -> str:
    """اكتشاف نوع المادة من النص."""
    text_lower = text.lower()
    
    subjects = {
        "medicine": ["طب", "مرض", "علاج", "طبيب", "مريض", "جراحة", "ولادة", "قيصرية", "تشريح", "دوائي"],
        "physics": ["فيزياء", "قوة", "حركة", "طاقة", "كهرباء", "مغناطيس", "جاذبية", "نيوتن", "اينشتاين"],
        "chemistry": ["كيمياء", "تفاعل", "عنصر", "مركب", "حمض", "قاعدة", "جزيء", "ذرة"],
        "math": ["رياضيات", "معادلة", "حساب", "جبر", "هندسة", "تكامل", "تفاضل", "إحصاء"],
        "engineering": ["هندسة", "بناء", "جسر", "تصميم", "إنشاء", "ميكانيكا", "كهرباء"],
        "computer": ["برمجة", "حاسوب", "خوارزمية", "برنامج", "كود", "بايثون", "جافا"],
        "history": ["تاريخ", "حرب", "معركة", "حضارة", "إمبراطورية", "خلافة", "قديم"],
        "literature": ["أدب", "شعر", "رواية", "قصة", "كاتب", "شاعر", "نثر", "بلاغة"],
        "business": ["إدارة", "اقتصاد", "تسويق", "شركة", "استثمار", "أسهم", "تمويل"],
        "science": ["علوم", "أحياء", "نبات", "حيوان", "خلية", "وراثة", "بيئة"],
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
#  دوال التوليد
# ══════════════════════════════════════════════════════════════════════════════
async def _generate_deepseek(prompt: str) -> str:
    if not DEEPSEEK_API_KEYS:
        raise QuotaExhaustedError("لا توجد مفاتيح DeepSeek")
    
    for key in DEEPSEEK_API_KEYS:
        try:
            headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
            payload = {"model": "deepseek-chat", "messages": [{"role": "user", "content": prompt}], "max_tokens": 6000, "temperature": 0.5}
            async with aiohttp.ClientSession() as s:
                async with s.post("https://api.deepseek.com/v1/chat/completions", headers=headers, json=payload, timeout=120) as r:
                    if r.status == 200:
                        d = await r.json()
                        return d["choices"][0]["message"]["content"].strip()
        except:
            continue
    raise QuotaExhaustedError("DeepSeek فشل")


async def _generate_gemini(prompt: str) -> str:
    if not GEMINI_API_KEYS:
        raise QuotaExhaustedError("لا توجد مفاتيح Gemini")
    
    for key in GEMINI_API_KEYS:
        try:
            client = genai.Client(api_key=key)
            response = await asyncio.to_thread(
                client.models.generate_content,
                model="gemini-2.0-flash",
                contents=prompt,
                config=genai_types.GenerateContentConfig(temperature=0.5, max_output_tokens=6000)
            )
            return response.text.strip()
        except:
            continue
    raise QuotaExhaustedError("Gemini فشل")


async def _generate_openrouter(prompt: str) -> str:
    if not OPENROUTER_API_KEYS:
        raise QuotaExhaustedError("لا توجد مفاتيح OpenRouter")
    
    for key in OPENROUTER_API_KEYS:
        try:
            headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json", "HTTP-Referer": "https://lecture-bot.com"}
            payload = {"model": "google/gemini-2.0-flash-exp:free", "messages": [{"role": "user", "content": prompt}], "max_tokens": 6000}
            async with aiohttp.ClientSession() as s:
                async with s.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload, timeout=120) as r:
                    if r.status == 200:
                        d = await r.json()
                        return d["choices"][0]["message"]["content"].strip()
        except:
            continue
    raise QuotaExhaustedError("OpenRouter فشل")


async def _generate_groq(prompt: str) -> str:
    if not GROQ_API_KEYS:
        raise QuotaExhaustedError("لا توجد مفاتيح Groq")
    
    for key in GROQ_API_KEYS:
        try:
            headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
            payload = {"model": "llama-3.3-70b-versatile", "messages": [{"role": "user", "content": prompt}], "max_tokens": 6000}
            async with aiohttp.ClientSession() as s:
                async with s.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload, timeout=90) as r:
                    if r.status == 200:
                        d = await r.json()
                        return d["choices"][0]["message"]["content"].strip()
        except:
            continue
    raise QuotaExhaustedError("Groq فشل")


async def call_ai(prompt: str) -> str:
    """استدعاء AI مع تناوب المزودين."""
    for func in [_generate_deepseek, _generate_gemini, _generate_openrouter, _generate_groq]:
        try:
            return await func(prompt)
        except QuotaExhaustedError:
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
            keywords = ["مصطلح 1", "مصطلح 2", "مصطلح 3"] if is_arabic else ["term1", "term2", "term3"]
        
        sections.append({
            "title": title,
            "keywords": keywords,
            "narration": para[:800],
            "duration_estimate": max(30, len(para) // 12)
        })
    
    if not sections:
        sections = [{
            "title": "المحتوى الرئيسي" if is_arabic else "Main Content",
            "keywords": ["مصطلح 1", "مصطلح 2"] if is_arabic else ["term1", "term2"],
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
async def analyze_lecture(text: str, dialect: str = "msa") -> dict:
    """تحليل المحاضرة إلى أقسام مع كلمات مفتاحية وشرح."""
    is_arabic = dialect not in ("english", "british")
    subject = detect_subject(text)
    style = TEACHING_STYLES.get(subject, TEACHING_STYLES["other"])
    
    # تحديد عدد الأقسام
    word_count = len(text.split())
    if word_count < 400:
        num_sections = 2
    elif word_count < 800:
        num_sections = 3
    elif word_count < 1500:
        num_sections = 4
    else:
        num_sections = 5
    
    text_sample = text[:4000]
    
    # لهجة الشرح
    dialect_names = {
        "iraq": "العراقية", "egypt": "المصرية", "syria": "الشامية",
        "gulf": "الخليجية", "msa": "الفصحى"
    }
    dialect_name = dialect_names.get(dialect, "الفصحى")
    
    if is_arabic:
        prompt = f"""{style}

حلل النص التالي إلى {num_sections} أقسام تعليمية.

النص:
{text_sample}

لكل قسم، قدم:
1. title: عنوان واضح وجذاب للقسم
2. keywords: 3-5 كلمات مفتاحية (مصطلحات مهمة في هذا القسم)
3. narration: شرح مبسط وممتع (250-400 كلمة) باللهجة {dialect_name}. اشرح كمعلم لطلابه.

أرجع JSON فقط بالتنسيق التالي:
{{"title": "عنوان المحاضرة", "sections": [{{"title": "عنوان القسم", "keywords": ["مصطلح1", "مصطلح2", "مصطلح3"], "narration": "الشرح..."}}], "summary": "ملخص عام للمحاضرة (3-4 جمل)"}}"""
    else:
        prompt = f"""{style}

Analyze this text into {num_sections} sections.

Text: {text_sample}

For each section provide:
1. title: Clear section title
2. keywords: 3-5 key terms
3. narration: Simplified explanation in English

Return ONLY JSON:
{{"title": "Lecture Title", "sections": [{{"title": "Section", "keywords": ["term1", "term2"], "narration": "explanation..."}}], "summary": "Overall summary"}}"""

    try:
        response = await call_ai(prompt)
        response = re.sub(r'```json\s*', '', response.strip())
        response = re.sub(r'\s*```', '', response)
        
        data = json.loads(response)
        data["lecture_type"] = subject
        
        # إضافة مدد تقديرية
        for sec in data["sections"]:
            narration_len = len(sec.get("narration", ""))
            sec["duration_estimate"] = max(25, narration_len // 12)
        
        return data
    except Exception as e:
        print(f"⚠️ استخدام التحليل المحلي: {e}")
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
        raise ValueError(f"فشل قراءة PDF: {e}")
