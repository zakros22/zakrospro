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
#  نظام تبادل المفاتيح
# ══════════════════════════════════════════════════════════════════════════════

class QuotaExhaustedError(Exception):
    pass


# ══════════════════════════════════════════════════════════════════════════════
#  اكتشاف نوع المادة
# ══════════════════════════════════════════════════════════════════════════════

def _detect_subject(text: str) -> str:
    text_lower = text.lower()
    subjects = {
        "medicine": ["طب", "مرض", "علاج", "طبيب", "مريض", "جراحة", "medicine", "disease", "treatment", "doctor"],
        "physics": ["فيزياء", "قوة", "حركة", "طاقة", "كهرباء", "physics", "force", "energy"],
        "chemistry": ["كيمياء", "تفاعل", "عنصر", "مركب", "chemistry", "reaction"],
        "math": ["رياضيات", "معادلة", "حساب", "جبر", "math", "equation", "algebra"],
        "engineering": ["هندسة", "بناء", "تصميم", "engineering", "design"],
        "computer": ["برمجة", "حاسوب", "خوارزمية", "computer", "programming"],
        "history": ["تاريخ", "حرب", "حضارة", "history", "war"],
        "literature": ["أدب", "شعر", "رواية", "literature", "poetry"],
        "business": ["إدارة", "اقتصاد", "تسويق", "business", "management"],
        "science": ["علوم", "أحياء", "نبات", "science", "biology"],
    }
    for subject, keywords in subjects.items():
        if any(kw in text_lower for kw in keywords):
            return subject
    return "other"


# ══════════════════════════════════════════════════════════════════════════════
#  دوال التوليد
# ══════════════════════════════════════════════════════════════════════════════

async def _generate_with_deepseek(prompt: str) -> str:
    if not DEEPSEEK_API_KEYS:
        raise QuotaExhaustedError("لا توجد مفاتيح")
    for key in DEEPSEEK_API_KEYS:
        try:
            headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
            payload = {"model": "deepseek-chat", "messages": [{"role": "user", "content": prompt}], "max_tokens": 6000, "temperature": 0.5}
            async with aiohttp.ClientSession() as session:
                async with session.post("https://api.deepseek.com/v1/chat/completions", headers=headers, json=payload, timeout=120) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data["choices"][0]["message"]["content"].strip()
        except:
            continue
    raise QuotaExhaustedError("DeepSeek فشل")


async def _generate_with_gemini(prompt: str) -> str:
    if not GEMINI_API_KEYS:
        raise QuotaExhaustedError("لا توجد مفاتيح")
    for key in GEMINI_API_KEYS:
        try:
            client = genai.Client(api_key=key)
            response = await asyncio.to_thread(client.models.generate_content, model="gemini-2.0-flash", contents=prompt, config=genai_types.GenerateContentConfig(temperature=0.5, max_output_tokens=6000))
            return response.text.strip()
        except:
            continue
    raise QuotaExhaustedError("Gemini فشل")


async def _generate_with_openrouter(prompt: str) -> str:
    if not OPENROUTER_API_KEYS:
        raise QuotaExhaustedError("لا توجد مفاتيح")
    for key in OPENROUTER_API_KEYS:
        try:
            headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json", "HTTP-Referer": "https://lecture-bot.com"}
            payload = {"model": "google/gemini-2.0-flash-exp:free", "messages": [{"role": "user", "content": prompt}], "max_tokens": 6000}
            async with aiohttp.ClientSession() as session:
                async with session.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload, timeout=120) as resp:
                    if resp.status == 200:
                        return await resp.json()["choices"][0]["message"]["content"].strip()
        except:
            continue
    raise QuotaExhaustedError("OpenRouter فشل")


async def _generate_with_groq(prompt: str) -> str:
    if not GROQ_API_KEYS:
        raise QuotaExhaustedError("لا توجد مفاتيح")
    for key in GROQ_API_KEYS:
        try:
            headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
            payload = {"model": "llama-3.3-70b-versatile", "messages": [{"role": "user", "content": prompt}], "max_tokens": 6000}
            async with aiohttp.ClientSession() as session:
                async with session.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload, timeout=90) as resp:
                    if resp.status == 200:
                        return await resp.json()["choices"][0]["message"]["content"].strip()
        except:
            continue
    raise QuotaExhaustedError("Groq فشل")


async def _generate_with_rotation(prompt: str) -> str:
    for func in [_generate_with_deepseek, _generate_with_gemini, _generate_with_openrouter, _generate_with_groq]:
        try:
            return await func(prompt)
        except:
            continue
    raise QuotaExhaustedError("جميع المزودين فشلوا")


# ══════════════════════════════════════════════════════════════════════════════
#  تحليل محلي احتياطي (سريع ومضمون)
# ══════════════════════════════════════════════════════════════════════════════

def _local_analyze(text: str, dialect: str) -> dict:
    """تحليل محلي يضمن نتيجة دائماً."""
    is_english = dialect in ("english", "british")
    subject = _detect_subject(text)
    
    # تنظيف النص وتقسيمه
    text = re.sub(r'\s+', ' ', text).strip()
    
    # تقسيم إلى فقرات
    paragraphs = []
    for p in text.split('\n'):
        p = p.strip()
        if len(p) > 100:
            paragraphs.append(p)
    
    if len(paragraphs) < 3:
        words = text.split()
        chunk_size = max(250, len(words) // 4)
        for i in range(0, len(words), chunk_size):
            chunk = ' '.join(words[i:i+chunk_size])
            if len(chunk) > 50:
                paragraphs.append(chunk)
    
    # أخذ أول 4 فقرات كأقسام
    sections = []
    for i, para in enumerate(paragraphs[:4]):
        # استخراج عنوان من أول جملة
        first_sent = para.split('.')[0].split('؟')[0].split('!')[0][:50]
        
        if is_english:
            title = f"Section {i+1}: {first_sent}"
            narration = para[:600]
        else:
            title = f"القسم {i+1}: {first_sent}"
            narration = para[:600]
        
        sections.append({
            "title": title,
            "narration": narration,
            "duration_estimate": max(30, len(narration) // 15)
        })
    
    if not sections:
        if is_english:
            sections = [{"title": "Main Content", "narration": text[:600], "duration_estimate": 45}]
        else:
            sections = [{"title": "المحتوى الرئيسي", "narration": text[:600], "duration_estimate": 45}]
    
    return {
        "lecture_type": subject,
        "title": "Lecture Summary" if is_english else "ملخص المحاضرة",
        "sections": sections,
        "summary": text[:300],
        "total_sections": len(sections)
    }


# ══════════════════════════════════════════════════════════════════════════════
#  تحليل المحاضرة الرئيسي
# ══════════════════════════════════════════════════════════════════════════════

async def analyze_lecture(text: str, dialect: str = "msa") -> dict:
    """تحليل المحاضرة - كل قسم له عنوان ونص شرح."""
    
    is_english_output = dialect in ("english", "british")
    subject = _detect_subject(text)
    
    # عدد الأقسام حسب طول النص (بحد أقصى 5 أقسام)
    word_count = len(text.split())
    if word_count < 400:
        num_sections = 2
    elif word_count < 800:
        num_sections = 3
    elif word_count < 1500:
        num_sections = 4
    else:
        num_sections = 5
    
    text_limit = min(len(text), 4000)
    
    # لهجة الشرح
    dialect_names = {
        "iraq": "العراقية", "egypt": "المصرية", "syria": "الشامية",
        "gulf": "الخليجية", "msa": "الفصحى"
    }
    dialect_name = dialect_names.get(dialect, "الفصحى")
    
    if is_english_output:
        prompt = f"""Analyze this text and create a structured lecture with exactly {num_sections} sections.

For each section provide:
1. A clear section title
2. A simplified narration in English (explain like a teacher to students, mention key terms with simple definitions)

Text:
{text[:text_limit]}

Return ONLY valid JSON:
{{
  "title": "Lecture title",
  "sections": [
    {{"title": "Section 1 title", "narration": "Simplified explanation..."}},
    {{"title": "Section 2 title", "narration": "Simplified explanation..."}}
  ]
}}"""
    else:
        prompt = f"""حلل هذا النص وأنشئ محاضرة تعليمية مكونة من {num_sections} أقسام بالضبط.

المطلوب لكل قسم:
1. عنوان واضح للقسم
2. شرح مبسط باللهجة {dialect_name}. اشرح كمعلم لطلابه. اذكر المصطلحات المهمة مع شرحها.

النص:
{text[:text_limit]}

أرجع JSON فقط:
{{
  "title": "عنوان المحاضرة",
  "sections": [
    {{"title": "عنوان القسم الأول", "narration": "الشرح المبسط باللهجة المطلوبة..."}},
    {{"title": "عنوان القسم الثاني", "narration": "الشرح المبسط..."}}
  ]
}}"""

    try:
        content = await _generate_with_rotation(prompt)
        content = re.sub(r'^```json\s*', '', content.strip())
        content = re.sub(r'\s*```$', '', content)
        
        result = json.loads(content)
        result["lecture_type"] = subject
        
        # إضافة مدة تقديرية لكل قسم
        for section in result["sections"]:
            narration_len = len(section.get("narration", ""))
            section["duration_estimate"] = max(25, narration_len // 12)
        
        print(f"✅ تم التحليل: {len(result['sections'])} أقسام")
        return result
        
    except Exception as e:
        print(f"⚠️ استخدام التحليل المحلي: {e}")
        return _local_analyze(text, dialect)


# ══════════════════════════════════════════════════════════════════════════════
#  استخراج النص من PDF
# ══════════════════════════════════════════════════════════════════════════════

async def extract_full_text_from_pdf(pdf_bytes: bytes) -> str:
    try:
        import PyPDF2
        reader = PyPDF2.PdfReader(io.BytesIO(pdf_bytes))
        pages = [page.extract_text() or "" for page in reader.pages]
        text = "\n\n".join(pages)
        if len(text.strip()) < 50:
            raise ValueError("النص قصير جداً")
        return text
    except Exception as e:
        raise ValueError(f"فشل قراءة PDF: {e}")


# ══════════════════════════════════════════════════════════════════════════════
#  توليد صورة كرتونية خرافية واحدة لكل قسم
# ══════════════════════════════════════════════════════════════════════════════

def _build_section_image_prompt(section_title: str, lecture_type: str, is_arabic: bool) -> str:
    """بناء وصف لصورة كرتونية خرافية تلخص القسم بأكمله."""
    
    style = {
        "medicine": "cute medical fantasy, magical healing, whimsical doctor and patient",
        "science": "magical laboratory, fairy tale science, glowing potions",
        "math": "floating magical numbers, fairy tale geometry, cute math wizard",
        "physics": "cosmic magic, fairy tale physics, magical forces",
        "chemistry": "magical potions, colorful smoke, cute chemistry set",
        "engineering": "fairy tale construction, magical bridge, whimsical machine",
        "computer": "magical circuit, cute robot, fairy tale coding",
        "history": "fairy tale ancient scene, magical history, whimsical past",
        "literature": "magical book, fairy tale story, whimsical words",
        "business": "magical marketplace, fairy tale merchant, cute coins",
        "other": "fairy tale classroom, magical learning, whimsical education"
    }.get(lecture_type, "fairy tale education, magical learning, cute cartoon")
    
    # استخدام عنوان القسم لوصف الصورة
    clean_title = section_title[:60].replace('"', '').replace("'", "")
    
    if is_arabic:
        # للعربية نستخدم وصف إنجليزي بسيط
        prompt = f"cute fantasy cartoon illustration about {clean_title}, {style}, whimsical storybook style, bright magical colors, simple clean design, no text no words"
    else:
        prompt = f"cute fantasy cartoon illustration about {clean_title}, {style}, whimsical storybook style, bright magical colors, simple clean design, no text no words"
    
    return prompt


async def _generate_cartoon_image(prompt: str) -> bytes | None:
    """توليد صورة كرتونية."""
    import urllib.parse
    seed = random.randint(1, 99999)
    encoded = urllib.parse.quote(prompt[:300])
    url = f"https://image.pollinations.ai/prompt/{encoded}?width=854&height=480&nologo=true&seed={seed}&model=flux"
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                if resp.status == 200:
                    raw = await resp.read()
                    if len(raw) > 5000:
                        img = PILImage.open(io.BytesIO(raw)).convert("RGB")
                        img = img.resize((854, 480), PILImage.LANCZOS)
                        buf = io.BytesIO()
                        img.save(buf, "JPEG", quality=90)
                        print(f"✅ صورة كرتونية: {len(buf.getvalue())//1024}KB")
                        return buf.getvalue()
    except:
        pass
    return None


def _create_placeholder_image(title: str, lecture_type: str, is_arabic: bool) -> bytes:
    """صورة احتياطية جميلة."""
    colors = {
        "medicine": ((180, 30, 80), (220, 100, 150), (255, 220, 100)),
        "science": ((30, 100, 150), (100, 180, 220), (200, 255, 150)),
        "math": ((80, 30, 150), (150, 100, 220), (255, 200, 100)),
        "physics": ((20, 50, 120), (80, 150, 250), (255, 150, 200)),
        "chemistry": ((100, 20, 100), (200, 80, 180), (150, 255, 200)),
        "other": ((40, 40, 120), (100, 100, 200), (255, 200, 100)),
    }
    bg1, bg2, accent = colors.get(lecture_type, colors["other"])
    
    W, H = 854, 480
    img = PILImage.new("RGB", (W, H), bg1)
    draw = ImageDraw.Draw(img)
    
    # تدرج
    for y in range(H):
        t = y / H
        r = int(bg1[0] * (1-t) + bg2[0] * t)
        g = int(bg1[1] * (1-t) + bg2[1] * t)
        b = int(bg1[2] * (1-t) + bg2[2] * t)
        draw.line([(0, y), (W, y)], fill=(r, g, b))
    
    # نجوم
    for _ in range(20):
        x, y = random.randint(20, W-20), random.randint(20, H-20)
        s = random.randint(3, 8)
        draw.ellipse([x-s, y-s, x+s, y+s], fill=(255, 255, 200))
    
    # عنوان مبسط
    short_title = title[:30]
    if is_arabic:
        try:
            import arabic_reshaper
            from bidi.algorithm import get_display
            short_title = get_display(arabic_reshaper.reshape(short_title))
        except:
            pass
    
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 35)
    except:
        font = ImageFont.load_default()
    
    bbox = draw.textbbox((0, 0), short_title, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(((W-tw)//2, (H-th)//2), short_title, fill=(255, 255, 255), font=font)
    
    draw.rectangle([15, 15, W-15, H-15], outline=accent, width=4)
    
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=90)
    return buf.getvalue()


async def fetch_image_for_keyword(
    keyword: str,
    section_title: str,
    lecture_type: str,
    image_search_en: str = "",
) -> bytes:
    """جلب صورة كرتونية واحدة للقسم بأكمله."""
    
    # نستخدم عنوان القسم كاملاً لوصف الصورة
    title_to_use = section_title if section_title else keyword
    is_arabic = any('\u0600' <= c <= '\u06ff' for c in title_to_use)
    
    prompt = _build_section_image_prompt(title_to_use, lecture_type, is_arabic)
    
    # محاولة التوليد
    img = await _generate_cartoon_image(prompt)
    if img:
        return img
    
    # صورة احتياطية
    return _create_placeholder_image(title_to_use, lecture_type, is_arabic)
