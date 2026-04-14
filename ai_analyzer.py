#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import re
import io
import asyncio
import aiohttp
import random
import os
from PIL import Image as PILImage, ImageDraw, ImageFont
from google import genai
from google.genai import types as genai_types
from config import (
    DEEPSEEK_API_KEYS, GEMINI_API_KEYS, OPENROUTER_API_KEYS, GROQ_API_KEYS, OPENAI_API_KEY
)

# ══════════════════════════════════════════════════════════════════════════════
#  نظام تبادل المفاتيح المتقدم
# ══════════════════════════════════════════════════════════════════════════════

class QuotaExhaustedError(Exception):
    """يُرفع عندما تنفد جميع المفاتيح من جميع المزودين."""
    pass


# ══════════════════════════════════════════════════════════════════════════════
#  أنماط الشرح حسب المادة
# ══════════════════════════════════════════════════════════════════════════════

SUBJECT_TEACHING_STYLES_AR = {
    "medicine": "أنت طبيب استشاري خبير تشرح لطلاب الطب. ابدأ بقصة مريض واقعية، اشرح الآلية بتشبيهات حياتية، واختم بخلاصة سريرية.",
    "science": "أنت عالم تشرح العلوم بأسلوب تجريبي ممتع. ابدأ بتجربة ذهنية، اشرح الظاهرة بتشبيه من الحياة، واذكر تطبيقات عملية.",
    "math": "أنت أستاذ رياضيات تشرح بالألغاز والتحديات. ابدأ بمسألة بسيطة، اشرح القاعدة كسر من أسرار الأرقام، واختم بخدعة رياضية.",
    "physics": "أنت فيزيائي تشرح قوانين الكون بأسلوب سحري. ابدأ بظاهرة غامضة، اشرح القانون كتعويذة سحرية، واستخدم تشبيهات من الخيال.",
    "chemistry": "أنت كيميائي تشرح التفاعلات كوصفات سحرية. ابدأ بتفاعل مذهل، اشرحه كرقصة بين الذرات، واختم بسر المختبر.",
    "engineering": "أنت مهندس تشرح كيفية بناء الأشياء العظيمة. ابدأ بتحدي بناء، اشرح المبدأ بقصة هندسية، واختم بنصيحة ذهبية.",
    "computer": "أنت خبير برمجة تشرح بأسلوب الهاكر الأخلاقي. ابدأ بمشكلة تقنية، اشرح الخوارزمية كوصفة طبخ، واختم بخدعة برمجية.",
    "history": "أنت راوي قصص تاريخي تجعل الماضي حياً. انقل الطالب للزمن الماضي، اروي الأحداث كفيلم سينمائي، واربط الماضي بالحاضر.",
    "literature": "أنت أديب وناقد تشرح جماليات النصوص. ابدأ بلوحة فنية من النص، حلل الأسلوب كأسرار السحر، واختم باقتباس من ذهب.",
    "business": "أنت رجل أعمال ناجح تشارك حكمة الأعمال. ابدأ بقصة نجاح أو فشل حقيقية، اشرح المفهوم كلعبة استراتيجية، واختم بنصيحة المليونير.",
    "other": "أنت معلم مبدع تشرح بأسلوب القصص والتشبيهات. ابدأ بقصة تثير الفضول، اشرح بتشبيه من الحياة، واختم بخلاصة في 3 نقاط.",
}

SUBJECT_TEACHING_STYLES_EN = {
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
#  اكتشاف المادة من النص
# ══════════════════════════════════════════════════════════════════════════════

def _detect_subject(text: str) -> str:
    """اكتشاف نوع المادة من النص."""
    text_lower = text.lower()
    
    subjects_keywords = {
        "medicine": ["طب", "مرض", "علاج", "طبيب", "مريض", "جراحة", "دوائي", "تشخيص", "medicine", "disease", "treatment", "doctor", "patient", "surgery"],
        "physics": ["فيزياء", "قوة", "حركة", "طاقة", "كهرباء", "مغناطيس", "جاذبية", "physics", "force", "motion", "energy", "electricity", "gravity"],
        "chemistry": ["كيمياء", "تفاعل", "عنصر", "مركب", "حمض", "قاعدة", "chemistry", "reaction", "element", "compound", "acid"],
        "math": ["رياضيات", "معادلة", "حساب", "جبر", "هندسة", "تكامل", "تفاضل", "math", "equation", "algebra", "calculus", "geometry"],
        "engineering": ["هندسة", "بناء", "جسر", "تصميم", "إنشاء", "engineering", "construction", "design", "bridge"],
        "computer": ["برمجة", "حاسوب", "خوارزمية", "برنامج", "كمبيوتر", "computer", "programming", "algorithm", "code", "software"],
        "history": ["تاريخ", "حرب", "معركة", "حضارة", "إمبراطورية", "history", "war", "battle", "civilization", "empire"],
        "literature": ["أدب", "شعر", "رواية", "قصة", "كاتب", "literature", "poetry", "novel", "writer"],
        "business": ["إدارة", "اقتصاد", "تسويق", "شركة", "business", "management", "marketing", "economy", "company"],
        "science": ["علوم", "أحياء", "نبات", "حيوان", "خلية", "science", "biology", "cell", "plant", "animal"],
    }
    
    scores = {}
    for subject, keywords in subjects_keywords.items():
        score = sum(1 for kw in keywords if kw in text_lower)
        if score > 0:
            scores[subject] = score
    
    if scores:
        return max(scores, key=scores.get)
    return "other"


# ══════════════════════════════════════════════════════════════════════════════
#  دوال التوليد - DeepSeek
# ══════════════════════════════════════════════════════════════════════════════

async def _generate_with_deepseek(prompt: str, max_tokens: int = 8192) -> str:
    """محاولة التوليد باستخدام مفاتيح DeepSeek."""
    if not DEEPSEEK_API_KEYS:
        raise QuotaExhaustedError("لا توجد مفاتيح DeepSeek")

    for key in DEEPSEEK_API_KEYS:
        try:
            headers = {
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": "deepseek-chat",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": min(max_tokens, 8192),
                "temperature": 0.4,
            }
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://api.deepseek.com/v1/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=120),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        text = data["choices"][0]["message"]["content"].strip()
                        print(f"✅ DeepSeek نجاح")
                        return text
                    else:
                        body = await resp.text()
                        print(f"⚠️ DeepSeek {resp.status}: {body[:100]}")
                        continue
        except Exception as e:
            print(f"⚠️ DeepSeek خطأ: {str(e)[:80]}")
            continue
    raise QuotaExhaustedError("DeepSeek فشل")


# ══════════════════════════════════════════════════════════════════════════════
#  دوال التوليد - Gemini
# ══════════════════════════════════════════════════════════════════════════════

async def _generate_with_gemini(prompt: str, max_tokens: int = 8192) -> str:
    """محاولة التوليد باستخدام مفاتيح Gemini."""
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
                    temperature=0.4,
                    max_output_tokens=max_tokens,
                ),
            )
            print(f"✅ Gemini نجاح")
            return response.text.strip()
        except Exception as e:
            err = str(e)
            if "quota" in err.lower() or "429" in err:
                print(f"⚠️ Gemini حصة منتهية")
                continue
            else:
                print(f"⚠️ Gemini خطأ: {err[:80]}")
                continue
    raise QuotaExhaustedError("Gemini فشل")


# ══════════════════════════════════════════════════════════════════════════════
#  دوال التوليد - OpenRouter
# ══════════════════════════════════════════════════════════════════════════════

async def _generate_with_openrouter(prompt: str, max_tokens: int = 8192) -> str:
    """محاولة التوليد باستخدام OpenRouter."""
    if not OPENROUTER_API_KEYS:
        raise QuotaExhaustedError("لا توجد مفاتيح OpenRouter")

    for key in OPENROUTER_API_KEYS:
        try:
            headers = {
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://lecture-bot.com",
                "X-Title": "Lecture Bot",
            }
            payload = {
                "model": "google/gemini-2.0-flash-exp:free",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": min(max_tokens, 8192),
                "temperature": 0.4,
            }
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=120),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        content = data["choices"][0]["message"]["content"]
                        if content and content.strip():
                            print(f"✅ OpenRouter نجاح")
                            return content.strip()
                    else:
                        continue
        except Exception:
            continue
    raise QuotaExhaustedError("OpenRouter فشل")


# ══════════════════════════════════════════════════════════════════════════════
#  دوال التوليد - Groq
# ══════════════════════════════════════════════════════════════════════════════

async def _generate_with_groq(prompt: str, max_tokens: int = 8192) -> str:
    """محاولة التوليد باستخدام Groq."""
    if not GROQ_API_KEYS:
        raise QuotaExhaustedError("لا توجد مفاتيح Groq")

    for key in GROQ_API_KEYS:
        try:
            headers = {
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": "llama-3.3-70b-versatile",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": min(max_tokens, 8192),
                "temperature": 0.4,
            }
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=90),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        text = data["choices"][0]["message"]["content"].strip()
                        print(f"✅ Groq نجاح")
                        return text
                    else:
                        continue
        except Exception:
            continue
    raise QuotaExhaustedError("Groq فشل")


# ══════════════════════════════════════════════════════════════════════════════
#  تحليل محلي بسيط (احتياطي أخير - لا يحتاج API)
# ══════════════════════════════════════════════════════════════════════════════

def _local_analyze(text: str, dialect: str = "msa") -> dict:
    """
    تحليل محلي بسيط للنص (بدون API) - احتياطي أخير.
    يضمن دائماً وجود نتيجة حتى لو فشلت جميع المزودين.
    """
    is_english = dialect in ("english", "british")
    subject = _detect_subject(text)
    
    # تقسيم النص إلى فقرات
    paragraphs = [p.strip() for p in text.split('\n') if p.strip() and len(p.strip()) > 50]
    
    if len(paragraphs) > 10:
        paragraphs = paragraphs[:10]
    elif len(paragraphs) < 3:
        # تقسيم النص الطويل إلى أقسام
        words = text.split()
        chunk_size = max(200, len(words) // 4)
        paragraphs = []
        for i in range(0, len(words), chunk_size):
            chunk = ' '.join(words[i:i+chunk_size])
            if len(chunk) > 50:
                paragraphs.append(chunk)
    
    # إنشاء الأقسام
    sections = []
    for i, para in enumerate(paragraphs[:6]):
        # استخراج كلمات مفتاحية بسيطة
        words_list = re.findall(r'\b[\w\u0600-\u06FF]{4,}\b', para)
        keywords = list(set(words_list))[:4]
        
        if is_english:
            section = {
                "title": f"Section {i+1}: {para[:30]}...",
                "content": para[:500],
                "keywords": keywords if keywords else ["concept", "topic", "idea", "point"],
                "keyword_images": [f"educational cartoon of {kw}" for kw in (keywords if keywords else ["learning"])],
                "narration": para[:1000],
                "duration_estimate": 30
            }
        else:
            section = {
                "title": f"القسم {i+1}: {para[:30]}...",
                "content": para[:500],
                "keywords": keywords if keywords else ["مفهوم", "موضوع", "فكرة", "نقطة"],
                "keyword_images": ["educational cartoon illustration" for _ in range(4)],
                "narration": para[:1000],
                "duration_estimate": 30
            }
        sections.append(section)
    
    if is_english:
        return {
            "lecture_type": subject,
            "title": "Lecture Summary",
            "sections": sections[:4] if sections else [{"title": "Main Content", "content": text[:500], "keywords": ["topic"], "keyword_images": ["cartoon"], "narration": text[:1000], "duration_estimate": 60}],
            "summary": text[:300] + "...",
            "key_points": ["Point 1", "Point 2", "Point 3", "Point 4"],
            "total_sections": len(sections[:4])
        }
    else:
        return {
            "lecture_type": subject,
            "title": "ملخص المحاضرة",
            "sections": sections[:4] if sections else [{"title": "المحتوى الرئيسي", "content": text[:500], "keywords": ["موضوع"], "keyword_images": ["cartoon"], "narration": text[:1000], "duration_estimate": 60}],
            "summary": text[:300] + "...",
            "key_points": ["النقطة الأولى", "النقطة الثانية", "النقطة الثالثة", "النقطة الرابعة"],
            "total_sections": len(sections[:4])
        }


# ══════════════════════════════════════════════════════════════════════════════
#  الدالة الرئيسية للتوليد مع تدوير المفاتيح
# ══════════════════════════════════════════════════════════════════════════════

async def _generate_with_rotation(prompt: str, max_output_tokens: int = 8192) -> str:
    """
    تدوير تلقائي بين المزودين.
    إذا فشل الجميع، نستخدم التحليل المحلي.
    """
    errors = []

    # 1. DeepSeek
    if DEEPSEEK_API_KEYS:
        print("🔄 تجربة DeepSeek...")
        try:
            return await _generate_with_deepseek(prompt, max_output_tokens)
        except QuotaExhaustedError as e:
            errors.append(f"DeepSeek: {e}")

    # 2. Gemini
    if GEMINI_API_KEYS:
        print("🔄 تجربة Gemini...")
        try:
            return await _generate_with_gemini(prompt, max_output_tokens)
        except QuotaExhaustedError as e:
            errors.append(f"Gemini: {e}")

    # 3. OpenRouter
    if OPENROUTER_API_KEYS:
        print("🔄 تجربة OpenRouter...")
        try:
            return await _generate_with_openrouter(prompt, max_output_tokens)
        except QuotaExhaustedError as e:
            errors.append(f"OpenRouter: {e}")

    # 4. Groq
    if GROQ_API_KEYS:
        print("🔄 تجربة Groq...")
        try:
            return await _generate_with_groq(prompt, max_output_tokens)
        except QuotaExhaustedError as e:
            errors.append(f"Groq: {e}")

    # إذا وصلنا هنا، جميع المزودين فشلوا
    raise QuotaExhaustedError(f"جميع المزودين منتهين: {' | '.join(errors)}")


# ══════════════════════════════════════════════════════════════════════════════
#  تحليل المحاضرة
# ══════════════════════════════════════════════════════════════════════════════

def _compute_lecture_scale(text: str) -> tuple:
    word_count = len(text.split())
    if word_count < 300:
        return 3, "6-8", 3000
    elif word_count < 800:
        return 4, "8-10", 5000
    elif word_count < 1500:
        return 5, "10-12", 6000
    else:
        return 6, "12-15", 8000


async def analyze_lecture(text: str, dialect: str = "msa") -> dict:
    """تحليل المحاضرة وإنتاج محتوى تعليمي احترافي."""
    
    is_english = dialect in ("english", "british")
    subject = _detect_subject(text)
    
    # اختيار أسلوب الشرح
    if is_english:
        teaching_style = SUBJECT_TEACHING_STYLES_EN.get(subject, SUBJECT_TEACHING_STYLES_EN["other"])
        lang_note = "Write ALL text in English."
        summary_hint = "A clear summary (4-5 sentences)"
        key_points_hint = '["Point 1", "Point 2", "Point 3", "Point 4"]'
        title_hint = "Lecture title"
        section_title_hint = "Section title"
        content_hint = "Simplified section content"
        keywords_hint = '["keyword1", "keyword2", "keyword3", "keyword4"]'
        narration_hint = "Full narration as a teacher"
        dialect_instruction = "Use clear professional English."
    else:
        teaching_style = SUBJECT_TEACHING_STYLES_AR.get(subject, SUBJECT_TEACHING_STYLES_AR["other"])
        lang_note = "اكتب كل النص بالعربية."
        summary_hint = "ملخص المحاضرة بأسلوب مبسط (4-5 جمل)"
        key_points_hint = '["النقطة 1", "النقطة 2", "النقطة 3", "النقطة 4"]'
        title_hint = "عنوان المحاضرة"
        section_title_hint = "عنوان القسم"
        content_hint = "محتوى القسم المبسط"
        keywords_hint = '["مصطلح1", "مصطلح2", "مصطلح3", "مصطلح4"]'
        narration_hint = "نص الشرح الكامل للمحاضر"
        
        dialect_instructions = {
            "iraq": "استخدم اللهجة العراقية الأصيلة (هواية، گلت، هسا، شلون، أكو)",
            "egypt": "استخدم اللهجة المصرية (أوي، يعني، كده، إيه، بتاع)",
            "syria": "استخدم اللهجة الشامية (هلق، شو، كتير، منيح، هيك)",
            "gulf": "استخدم اللهجة الخليجية (زين، وايد، عاد، أبشر)",
            "msa": "استخدم العربية الفصحى الواضحة والمبسطة",
        }
        dialect_instruction = dialect_instructions.get(dialect, dialect_instructions["msa"])

    num_sections, narration_sentences, _ = _compute_lecture_scale(text)
    text_limit = min(len(text), 4000 + num_sections * 1500)

    prompt = f"""أنت معلم خبير ومبدع. {teaching_style}

المادة: {subject}
{ dialect_instruction if not is_english else '' }

المحاضرة:
---
{text[:text_limit]}
---

حلل المحاضرة وأرجع JSON فقط:

{{
  "lecture_type": "{subject}",
  "title": "{title_hint}",
  "sections": [
    {{
      "title": "{section_title_hint}",
      "content": "{content_hint}",
      "keywords": {keywords_hint},
      "keyword_images": [
        "magical fantasy cartoon illustration of keyword1, cute whimsical style",
        "magical fantasy cartoon illustration of keyword2, cute whimsical style",
        "magical fantasy cartoon illustration of keyword3, cute whimsical style",
        "magical fantasy cartoon illustration of keyword4, cute whimsical style"
      ],
      "narration": "{narration_hint} ({narration_sentences} جمل)",
      "duration_estimate": 45
    }}
  ],
  "summary": "{summary_hint}",
  "key_points": {key_points_hint},
  "total_sections": {num_sections}
}}

مهم جداً:
- {lang_note}
- عدد الأقسام = {num_sections} بالضبط
- أرجع JSON فقط"""

    try:
        # محاولة استخدام API
        content = await _generate_with_rotation(prompt, max_output_tokens=8192)
        content = content.strip()
        content = re.sub(r'^```json\s*', '', content)
        content = re.sub(r'\s*```$', '', content)
        content = content.strip()

        try:
            result = json.loads(content)
            result["lecture_type"] = subject
            print(f"✅ تم التحليل بنجاح باستخدام API")
            return result
        except json.JSONDecodeError:
            json_match = re.search(r'\{[\s\S]*\}', content)
            if json_match:
                result = json.loads(json_match.group())
                result["lecture_type"] = subject
                print(f"✅ تم التحليل بنجاح (JSON مستخرج)")
                return result
            raise ValueError("Invalid JSON")
            
    except (QuotaExhaustedError, Exception) as e:
        print(f"⚠️ فشل التحليل عبر API: {e}")
        print("🔄 استخدام التحليل المحلي الاحتياطي...")
        # استخدام التحليل المحلي كاحتياطي
        return _local_analyze(text, dialect)


# ══════════════════════════════════════════════════════════════════════════════
#  استخراج النص من PDF
# ══════════════════════════════════════════════════════════════════════════════

async def extract_full_text_from_pdf(pdf_bytes: bytes) -> str:
    """استخراج النص الكامل من PDF."""
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


# ══════════════════════════════════════════════════════════════════════════════
#  توليد صور كرتونية خرافية
# ══════════════════════════════════════════════════════════════════════════════

def _build_fantasy_cartoon_prompt(subject: str, lecture_type: str) -> str:
    """بناء prompt لصورة كرتونية خرافية."""
    
    style_modifiers = {
        "medicine": "magical healing potion style, cute medical fantasy, whimsical doctor's tools, fairy tale",
        "science": "magical laboratory, glowing potions, fairy tale science, whimsical experiments",
        "math": "floating numbers, magical geometry, fairy tale mathematics, glowing equations",
        "physics": "cosmic magic, floating planets, fairy tale physics, magical forces",
        "chemistry": "bubbling magical potions, colorful smoke, fairy tale chemistry set",
        "engineering": "fairy tale castle construction, magical bridges, whimsical machines",
        "computer": "magical circuit board, glowing fairy code, whimsical robots",
        "history": "fairy tale ancient kingdom, magical historical scene, whimsical past",
        "literature": "magical book, fairy tale story coming alive, whimsical words",
        "business": "magical marketplace, fairy tale merchants, whimsical coins",
        "other": "fairy tale education, magical learning, whimsical classroom"
    }
    
    style = style_modifiers.get(lecture_type, style_modifiers["other"])
    
    return f"{subject}, {style}, fantasy cartoon illustration, cute whimsical style, bright magical colors, storybook art, no text, no words, no letters"


async def _pollinations_fantasy_generate(prompt: str) -> bytes | None:
    """توليد صورة كرتونية خرافية باستخدام Pollinations.ai."""
    import urllib.parse
    
    clean_prompt = prompt[:380].replace("\n", " ")
    seed = random.randint(1, 99999)
    encoded = urllib.parse.quote(clean_prompt)
    
    url = f"https://image.pollinations.ai/prompt/{encoded}?width=854&height=480&nologo=true&seed={seed}&model=flux"
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=25)) as resp:
                if resp.status == 200:
                    raw = await resp.read()
                    if len(raw) > 5000:
                        pil_img = PILImage.open(io.BytesIO(raw)).convert("RGB")
                        pil_img = pil_img.resize((854, 480), PILImage.LANCZOS)
                        buf = io.BytesIO()
                        pil_img.save(buf, "JPEG", quality=90)
                        print(f"✅ صورة كرتونية خرافية: {len(buf.getvalue())//1024}KB")
                        return buf.getvalue()
    except Exception as e:
        print(f"⚠️ Pollinations خطأ: {str(e)[:60]}")
    
    return None


def _make_fantasy_placeholder_image(keywords: list, lecture_type: str) -> bytes:
    """إنشاء صورة كرتونية خرافية احتياطية."""
    
    PALETTES = {
        "medicine": ((180, 30, 80), (220, 100, 150), (255, 220, 100)),
        "science": ((30, 100, 150), (100, 180, 220), (200, 255, 150)),
        "math": ((80, 30, 150), (150, 100, 220), (255, 200, 100)),
        "physics": ((20, 50, 120), (80, 150, 250), (255, 150, 200)),
        "chemistry": ((100, 20, 100), (200, 80, 180), (150, 255, 200)),
        "engineering": ((40, 80, 100), (100, 160, 180), (255, 220, 100)),
        "computer": ((20, 60, 100), (80, 140, 200), (200, 255, 150)),
        "history": ((120, 60, 30), (200, 140, 80), (255, 230, 150)),
        "literature": ((60, 30, 80), (140, 80, 160), (255, 200, 220)),
        "business": ((20, 80, 60), (80, 160, 120), (255, 220, 100)),
        "other": ((40, 40, 120), (100, 100, 200), (255, 200, 100)),
    }
    
    bg1, bg2, accent = PALETTES.get(lecture_type, PALETTES["other"])
    
    W, H = 854, 480
    img = PILImage.new("RGB", (W, H), bg1)
    draw = ImageDraw.Draw(img)
    
    for y in range(H):
        t = y / H
        r = int(bg1[0] * (1 - t) + bg2[0] * t)
        g = int(bg1[1] * (1 - t) + bg2[1] * t)
        b = int(bg1[2] * (1 - t) + bg2[2] * t)
        draw.line([(0, y), (W, y)], fill=(r, g, b))
    
    # نجوم وبريق
    for _ in range(30):
        x = random.randint(10, W-10)
        y = random.randint(10, H-10)
        size = random.randint(2, 6)
        star_color = (255, 255, 200) if random.random() > 0.5 else (255, 220, 150)
        draw.ellipse([x-size, y-size, x+size, y+size], fill=star_color)
    
    keyword_raw = (keywords[0] if keywords else "").strip()
    
    try:
        font_paths = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "fonts/Amiri-Bold.ttf",
        ]
        font = None
        for fp in font_paths:
            try:
                if os.path.exists(fp):
                    font = ImageFont.truetype(fp, 45)
                    break
            except:
                continue
        if font is None:
            font = ImageFont.load_default()
    except:
        font = ImageFont.load_default()
    
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
        display_text = get_display(arabic_reshaper.reshape(keyword_raw))
    except:
        display_text = keyword_raw
    
    bbox = draw.textbbox((0, 0), display_text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    
    draw.text(((W - tw) // 2 + 3, (H - th) // 2 + 3), display_text, fill=(0, 0, 0), font=font)
    draw.text(((W - tw) // 2, (H - th) // 2), display_text, fill=(255, 255, 255), font=font)
    
    draw.rectangle([15, 15, W-15, H-15], outline=accent, width=4)
    draw.rectangle([20, 20, W-20, H-20], outline=accent, width=1)
    
    for cx, cy in [(15, 15), (W-15, 15), (15, H-15), (W-15, H-15)]:
        draw.ellipse([cx-8, cy-8, cx+8, cy+8], fill=accent)
    
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=92)
    return buf.getvalue()


async def fetch_image_for_keyword(
    keyword: str,
    section_title: str,
    lecture_type: str,
    image_search_en: str = "",
) -> bytes:
    """جلب صورة كرتونية خرافية للكلمة المفتاحية."""
    subject = (image_search_en or keyword).strip()
    prompt = _build_fantasy_cartoon_prompt(subject, lecture_type)
    
    # محاولة Pollinations.ai
    img_bytes = await _pollinations_fantasy_generate(prompt)
    if img_bytes:
        return img_bytes
    
    # صورة خرافية احتياطية
    return _make_fantasy_placeholder_image([keyword, section_title], lecture_type)
