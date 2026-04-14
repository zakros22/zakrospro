#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import re
import io
import asyncio
import aiohttp
import random
import base64
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
#  أنماط الشرح الاحترافية حسب المادة الدراسية
# ══════════════════════════════════════════════════════════════════════════════

SUBJECT_TEACHING_STYLES_AR = {
    "medicine": """
🎓 *أسلوب شرح الطب:*
أنت طبيب استشاري خبير تشرح لطلاب الطب بأسلوب قصصي ممتع.
- ابدأ بقصة مريض واقعية: "تخيل معي مريضاً جاء للعيادة يشكو من..."
- اشرح الآلية بطريقة تشبيهية: "تخيل أن الخلية مثل قلعة والهرمون مثل المفتاح..."
- استخدم مصطلحات طبية مع شرحها بالعامية بين قوسين
- اختتم بـ "الخلاصة السريرية" في 3 نقاط ذهبية
""",
    "science": """
🔬 *أسلوب شرح العلوم:*
أنت عالم فيزياء/كيمياء/أحياء تشرح للطلاب بأسلوب تجريبي ممتع.
- ابدأ بتجربة ذهنية: "لو كنت في مختبر ورأيت..."
- اشرح الظاهرة بتشبيه من الحياة اليومية
- اذكر تطبيقات عملية من الواقع
- اختتم بـ "سر التجربة" - معلومة تثير الفضول
""",
    "math": """
📐 *أسلوب شرح الرياضيات:*
أنت أستاذ رياضيات عبقري تشرح للطلاب بأسلوب الألغاز والتحديات.
- ابدأ بـ "تحدي اليوم": مسألة بسيطة تقود للمفهوم
- اشرح القاعدة كأنها "سر من أسرار الأرقام"
- استخدم رسوماً ذهنية: "تخيل الأعداد كأنها قطع ليغو..."
- اختتم بـ "خدعة رياضية" يمكن للطالب استخدامها مع أصدقائه
""",
    "physics": """
⚡ *أسلوب شرح الفيزياء:*
أنت فيزيائي عبقري تشرح قوانين الكون بأسلوب سحري.
- ابدأ بـ "ظاهرة غامضة": لماذا يحدث كذا؟
- اشرح القانون كأنه "تعويذة سحرية" تتحكم بالطبيعة
- استخدم تشبيهات من عالم الخيال والأفلام
- اختتم بـ "تطبيق خارق" يذهل الطالب
""",
    "chemistry": """
🧪 *أسلوب شرح الكيمياء:*
أنت كيميائي ساحر تشرح التفاعلات كأنها وصفات سحرية.
- ابدأ بـ "جرعة اليوم": تفاعل كيميائي مذهل
- اشرح التفاعل كأنه "رقصة بين الذرات"
- استخدم ألواناً وروائح في الوصف
- اختتم بـ "سر المختبر" - معلومة خطيرة لكن مفيدة
""",
    "engineering": """
🏗️ *أسلوب شرح الهندسة:*
أنت مهندس عبقري تشرح كيفية بناء الأشياء العظيمة.
- ابدأ بـ "تحدي البناء": كيف نبني جسراً/برجاً/طائرة؟
- اشرح المبدأ الهندسي بقصة من التاريخ الهندسي
- اذكر أخطاء شهيرة وكيف تم تجنبها
- اختتم بـ "نصيحة المهندس الذهبية"
""",
    "computer": """
💻 *أسلوب شرح الحاسوب:*
أنت خبير برمجة وذكاء اصطناعي تشرح بأسلوب الـ "هاكر" الأخلاقي.
- ابدأ بـ "مشكلة تقنية" تحتاج حلاً ذكياً
- اشرح الخوارزمية كأنها "وصفة طبخ برمجية"
- استخدم تشبيهات من عالم الإنترنت والتطبيقات
- اختتم بـ "خدعة برمجية" تدهش المستخدم
""",
    "history": """
📜 *أسلوب شرح التاريخ:*
أنت راوي قصص تاريخي محترف تجعل الماضي حياً.
- ابدأ بـ "تخيل أنك في عام..." وانقل الطالب للزمن الماضي
- اروي الأحداث كأنها فيلم سينمائي بشخصيات وأبطال
- اربط الماضي بالحاضر: "وهذا ما نراه اليوم في..."
- اختتم بـ "درس التاريخ" - ماذا نتعلم من هذه القصة؟
""",
    "literature": """
📖 *أسلوب شرح الأدب:*
أنت أديب وناقد فني تشرح جماليات النصوص.
- ابدأ بـ "لوحة فنية" من النص الأدبي
- حلل الأسلوب كأنك تكشف أسرار السحر في الكلمات
- اربط النص بمشاعر إنسانية عميقة
- اختتم بـ "اقتباس من ذهب" يلخص الدرس
""",
    "business": """
💼 *أسلوب شرح إدارة الأعمال:*
أنت رجل أعمال ناجح ومستشار إداري خبير.
- ابدأ بـ "قصة نجاح/فشل" من عالم الشركات الحقيقي
- اشرح المفهوم الإداري كأنه "لعبة استراتيجية"
- استخدم أرقاماً وإحصائيات واقعية
- اختتم بـ "نصيحة المليونير" - خطوة عملية للنجاح
""",
    "other": """
📚 *أسلوب شرح تعليمي ممتع:*
أنت معلم مبدع تشرح بأسلوب القصص والتشبيهات.
- ابدأ بقصة أو موقف يثير الفضول
- اشرح المفهوم بتشبيه من الحياة اليومية
- اذكر تطبيقات عملية وأمثلة واقعية
- اختتم بخلاصة في 3 نقاط سهلة التذكر
""",
}

SUBJECT_TEACHING_STYLES_EN = {
    "medicine": """
You are an expert medical consultant teaching with storytelling:
- Start with a real patient case: "Imagine a patient walks into your clinic..."
- Explain mechanisms with analogies: "Think of the cell as a castle..."
- End with "Clinical Pearls" - 3 golden takeaways
""",
    "science": """
You are a passionate scientist making science magical:
- Start with a thought experiment
- Explain phenomena with everyday analogies
- End with a "Science Secret" that sparks curiosity
""",
    "math": """
You are a math wizard revealing the magic of numbers:
- Start with "Today's Challenge" - a simple puzzle
- Explain rules as "Secrets of Numbers"
- End with a "Math Trick" students can use
""",
    "physics": """
You are a physicist explaining the universe's magic:
- Start with a mysterious phenomenon
- Explain laws as "Nature's Spells"
- Use analogies from movies and fantasy
""",
    "chemistry": """
You are a chemistry wizard with magical potions:
- Start with an amazing chemical reaction
- Explain as a "Dance of Atoms"
- End with a "Lab Secret"
""",
    "engineering": """
You are a master builder explaining great constructions:
- Start with a building challenge
- Explain principles through engineering history
- End with "Engineer's Golden Tip"
""",
    "computer": """
You are a coding wizard teaching programming magic:
- Start with a tech problem needing clever solution
- Explain algorithms as "Cooking Recipes for Code"
- End with a "Pro Hacker Tip"
""",
    "history": """
You are a time-traveling storyteller bringing past to life:
- Transport student to the historical era
- Tell events like a movie with characters
- Connect past to present
""",
    "literature": """
You are a literary critic revealing the art of words:
- Present a beautiful text excerpt
- Analyze style like revealing magic spells
- End with a "Golden Quote"
""",
    "business": """
You are a successful entrepreneur sharing business wisdom:
- Share real company success/failure stories
- Explain concepts as strategy games
- End with "Millionaire's Advice"
""",
    "other": """
You are a creative teacher using stories and analogies:
- Start with curiosity-sparking story
- Explain with everyday analogies
- End with 3 easy takeaways
""",
}


# ══════════════════════════════════════════════════════════════════════════════
#  دوال التوليد حسب المزودين
# ══════════════════════════════════════════════════════════════════════════════

async def _generate_with_deepseek(prompt: str, max_tokens: int = 8192) -> str:
    """محاولة التوليد باستخدام مفاتيح DeepSeek بالتناوب."""
    if not DEEPSEEK_API_KEYS:
        raise QuotaExhaustedError("لا توجد مفاتيح DeepSeek")

    models = ["deepseek-chat"]
    for key in DEEPSEEK_API_KEYS:
        for model in models:
            try:
                headers = {
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                }
                payload = {
                    "model": model,
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


async def _generate_with_gemini(prompt: str, max_tokens: int = 8192) -> str:
    """محاولة التوليد باستخدام مفاتيح Gemini بالتناوب."""
    if not GEMINI_API_KEYS:
        raise QuotaExhaustedError("لا توجد مفاتيح Gemini")

    models = ["gemini-2.0-flash", "gemini-1.5-flash"]
    for i, key in enumerate(GEMINI_API_KEYS):
        for model in models:
            try:
                client = genai.Client(api_key=key)
                response = await asyncio.to_thread(
                    client.models.generate_content,
                    model=model,
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
                    print(f"⚠️ Gemini حصة منتهية للمفتاح {i+1}")
                    break
                else:
                    print(f"⚠️ Gemini خطأ: {err[:80]}")
                    continue
    raise QuotaExhaustedError("Gemini فشل")


async def _generate_with_openrouter(prompt: str, max_tokens: int = 8192) -> str:
    """محاولة التوليد باستخدام OpenRouter (نماذج مجانية)."""
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
                    "X-Title": "Lecture Bot",
                }
                payload = {
                    "model": model,
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


async def _generate_with_duckduckgo(prompt: str, max_tokens: int = 8192) -> str:
    """استخدام DuckDuckGo AI Chat - مجاني تماماً."""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Content-Type": "application/json",
            "Origin": "https://duckduckgo.com",
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
                timeout=aiohttp.ClientTimeout(total=90),
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
                        print(f"✅ DuckDuckGo نجاح")
                        return full_response.strip()
                        
        raise Exception("DuckDuckGo failed")
    except Exception as e:
        raise QuotaExhaustedError(f"DuckDuckGo: {e}")


async def _generate_with_rotation(prompt: str, max_output_tokens: int = 8192) -> str:
    """
    تدوير تلقائي بين المزودين:
    1. DeepSeek
    2. Gemini
    3. OpenRouter
    4. DuckDuckGo (مجاني)
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

    # 4. DuckDuckGo (مجاني - بدون مفتاح)
    print("🔄 تجربة DuckDuckGo (مجاني)...")
    try:
        return await _generate_with_duckduckgo(prompt, max_output_tokens)
    except QuotaExhaustedError as e:
        errors.append(f"DuckDuckGo: {e}")

    raise QuotaExhaustedError(f"جميع المزودين منتهين: {' | '.join(errors)}")


# ══════════════════════════════════════════════════════════════════════════════
#  تحليل المحاضرة مع أسلوب شرح حسب المادة
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


async def analyze_lecture(text: str, dialect: str = "msa") -> dict:
    """تحليل المحاضرة وإنتاج محتوى تعليمي احترافي."""
    
    is_english = dialect in ("english", "british")
    subject = _detect_subject(text)
    
    # اختيار أسلوب الشرح المناسب
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
        key_points_hint = '["نقطة 1", "نقطة 2", "نقطة 3", "نقطة 4"]'
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
        "وصف إنجليزي 3-5 كلمات لصورة كرتونية خرافية للكلمة الأولى - استخدم كلمات مثل: magical, fantasy, cartoon, cute, whimsical",
        "وصف للكلمة الثانية بنفس الأسلوب",
        "وصف للكلمة الثالثة بنفس الأسلوب",
        "وصف للكلمة الرابعة بنفس الأسلوب"
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
- keyword_images: أوصاف إنجليزية لصور كرتونية خرافية (fantasy cartoon style)
- استخدم كلمات مثل: magical, fantasy, cartoon, cute, whimsical, fairy tale
- أرجع JSON فقط"""

    content = await _generate_with_rotation(prompt, max_output_tokens=8192)
    content = content.strip()
    content = re.sub(r'^```json\s*', '', content)
    content = re.sub(r'\s*```$', '', content)
    content = content.strip()

    try:
        result = json.loads(content)
        # التأكد من أن lecture_type صحيح
        result["lecture_type"] = subject
        return result
    except json.JSONDecodeError:
        json_match = re.search(r'\{[\s\S]*\}', content)
        if json_match:
            result = json.loads(json_match.group())
            result["lecture_type"] = subject
            return result
        raise ValueError(f"Failed to parse JSON: {content[:500]}")


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
#  توليد صور كرتونية خرافية - Fantasy Cartoon Style
# ══════════════════════════════════════════════════════════════════════════════

def _build_fantasy_cartoon_prompt(subject: str, lecture_type: str) -> str:
    """بناء prompt لصورة كرتونية خرافية."""
    
    # أنماط مختلفة حسب المادة
    style_modifiers = {
        "medicine": "magical healing potion style, cute medical fantasy, whimsical doctor's tools",
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
    
    return f"{subject}, {style}, fantasy cartoon illustration, cute whimsical style, bright colors, magical atmosphere, storybook art, soft lighting, child-friendly, no text, no words"


async def _pollinations_fantasy_generate(prompt: str) -> bytes | None:
    """توليد صورة كرتونية خرافية باستخدام Pollinations.ai."""
    import urllib.parse
    
    clean_prompt = prompt[:380].replace("\n", " ")
    seed = random.randint(1, 99999)
    encoded = urllib.parse.quote(clean_prompt)
    
    # استخدام نموذج flux للحصول على صور كرتونية عالية الجودة
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


async def _prodia_fantasy_generate(prompt: str) -> bytes | None:
    """توليد صورة باستخدام Prodia (بديل مجاني)."""
    try:
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0",
        }
        
        payload = {
            "prompt": prompt,
            "negative_prompt": "text, words, letters, watermark, realistic, photo, ugly, blurry",
            "model": "dreamshaperXL_alpha2.safetensors",
            "steps": 20,
            "cfg_scale": 7,
            "width": 854,
            "height": 480,
            "sampler": "DPM++ 2M Karras",
        }
        
        async with aiohttp.ClientSession() as session:
            # إنشاء مهمة
            async with session.post(
                "https://api.prodia.com/v1/job",
                headers=headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                job_id = data.get("job")
                if not job_id:
                    return None
            
            # انتظار النتيجة
            for _ in range(15):
                await asyncio.sleep(1.5)
                async with session.get(
                    f"https://api.prodia.com/v1/job/{job_id}",
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        status = data.get("status")
                        if status == "succeeded":
                            image_url = data.get("imageUrl")
                            if image_url:
                                async with session.get(image_url, timeout=15) as img_resp:
                                    if img_resp.status == 200:
                                        raw = await img_resp.read()
                                        pil_img = PILImage.open(io.BytesIO(raw)).convert("RGB")
                                        pil_img = pil_img.resize((854, 480), PILImage.LANCZOS)
                                        buf = io.BytesIO()
                                        pil_img.save(buf, "JPEG", quality=90)
                                        print(f"✅ Prodia صورة كرتونية")
                                        return buf.getvalue()
                        elif status == "failed":
                            break
    except Exception:
        pass
    
    return None


def _make_fantasy_placeholder_image(keywords: list, lecture_type: str) -> bytes:
    """إنشاء صورة كرتونية خرافية احتياطية."""
    
    # ألوان خرافية حسب المادة
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
    
    # تدرج لوني سحري
    for y in range(H):
        t = y / H
        r = int(bg1[0] * (1 - t) + bg2[0] * t)
        g = int(bg1[1] * (1 - t) + bg2[1] * t)
        b = int(bg1[2] * (1 - t) + bg2[2] * t)
        draw.line([(0, y), (W, y)], fill=(r, g, b))
    
    # إضافة نجوم وبريق
    for _ in range(30):
        x = random.randint(10, W-10)
        y = random.randint(10, H-10)
        size = random.randint(2, 6)
        star_color = (255, 255, 200) if random.random() > 0.5 else (255, 220, 150)
        draw.ellipse([x-size, y-size, x+size, y+size], fill=star_color)
    
    # النص الرئيسي
    keyword_raw = (keywords[0] if keywords else "").strip()
    
    try:
        # محاولة استخدام خط عربي
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
    
    # تحضير النص العربي
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
        display_text = get_display(arabic_reshaper.reshape(keyword_raw))
    except:
        display_text = keyword_raw
    
    # رسم النص مع ظل
    bbox = draw.textbbox((0, 0), display_text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    
    # ظل
    draw.text(((W - tw) // 2 + 3, (H - th) // 2 + 3), display_text, fill=(0, 0, 0, 100), font=font)
    # نص رئيسي
    draw.text(((W - tw) // 2, (H - th) // 2), display_text, fill=(255, 255, 255), font=font)
    
    # إطار سحري
    draw.rectangle([15, 15, W-15, H-15], outline=accent, width=4)
    draw.rectangle([20, 20, W-20, H-20], outline=accent, width=1)
    
    # زخارف زوايا
    corner_size = 30
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
    """
    جلب صورة كرتونية خرافية للكلمة المفتاحية.
    
    Pipeline:
    1. Pollinations.ai (صور AI كرتونية خرافية)
    2. Prodia (بديل مجاني)
    3. صورة خرافية احتياطية مولدة محلياً
    """
    subject = (image_search_en or keyword).strip()
    
    # بناء prompt للصورة الكرتونية الخرافية
    prompt = _build_fantasy_cartoon_prompt(subject, lecture_type)
    
    # 1. محاولة Pollinations.ai
    img_bytes = await _pollinations_fantasy_generate(prompt)
    if img_bytes:
        return img_bytes
    
    # 2. محاولة Prodia
    img_bytes = await _prodia_fantasy_generate(prompt)
    if img_bytes:
        return img_bytes
    
    # 3. صورة خرافية احتياطية
    return _make_fantasy_placeholder_image([keyword, section_title], lecture_type)


# استيراد os للمسارات
import os
