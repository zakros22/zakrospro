import json
import re
import io
import asyncio
import aiohttp
import random
from PIL import Image as PILImage, ImageDraw, ImageFont
from google import genai
from google.genai import types as genai_types
from config import GOOGLE_API_KEY
import os

# ── Google Gemini Client ──────────────────────────────────────────────────────
if not GOOGLE_API_KEY:
    raise RuntimeError("GOOGLE_API_KEY غير موجود. احصل على مفتاح مجاني من https://aistudio.google.com/")

_client = genai.Client(api_key=GOOGLE_API_KEY)


async def _generate_with_gemini(prompt: str, max_output_tokens: int = 8192) -> str:
    """توليد النص باستخدام Google Gemini المجاني"""
    try:
        response = await asyncio.to_thread(
            _client.models.generate_content,
            model="gemini-2.0-flash",
            contents=prompt,
            config=genai_types.GenerateContentConfig(
                temperature=0.3,
                max_output_tokens=max_output_tokens,
            ),
        )
        return response.text.strip()
    except Exception as e:
        raise Exception(f"Gemini error: {e}")


def _compute_lecture_scale(text: str) -> tuple:
    """حساب عدد الأقسام وحجم المخرجات"""
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
    """تحليل المحاضرة واستخراج الأقسام"""
    dialect_instructions = {
        "iraq": "استخدم اللهجة العراقية في الشرح، مع كلمات عراقية أصيلة مثل (هواية، گلت، يعني، بس، هسا)",
        "egypt": "استخدم اللهجة المصرية في الشرح، مع كلمات مصرية مثل (أوي، معلش، يعني، بس، كده)",
        "syria": "استخدم اللهجة الشامية في الشرح، مع كلمات شامية مثل (هلق، شو، كتير، منيح، هيك)",
        "gulf": "استخدم اللهجة الخليجية في الشرح، مع كلمات خليجية مثل (زين، وايد، عاد، هاذي، أبشر)",
        "msa": "استخدم العربية الفصحى الواضحة والمبسطة",
        "english": "Use clear, simple English. Explain like a teacher to students.",
        "british": "Use British English with a professional, clear academic tone."
    }

    instruction = dialect_instructions.get(dialect, dialect_instructions["msa"])
    num_sections, narration_sentences, _ = _compute_lecture_scale(text)
    text_limit = min(len(text), 4000 + num_sections * 1500)

    is_english = dialect in ("english", "british")

    if is_english:
        summary_hint = "A clear, concise summary of the lecture in English (4-5 sentences)."
        key_points_hint = '["Key point 1", "Key point 2", "Key point 3", "Key point 4"]'
        title_hint = "Lecture title in English"
        section_title_hint = "Section title in English"
        content_hint = f"Simplified section content in English ({narration_sentences} sentences)"
        keywords_hint = '["keyword1", "keyword2", "keyword3", "keyword4"]'
        narration_hint = f"Full narration in English as a teacher ({narration_sentences} sentences)"
        lang_note = "IMPORTANT: Write ALL text fields in English."
    else:
        summary_hint = "ملخص المحاضرة بأسلوب مبسط (4-5 جمل)"
        key_points_hint = '["نقطة رئيسية 1", "نقطة رئيسية 2", "نقطة رئيسية 3", "نقطة رئيسية 4"]'
        title_hint = "عنوان المحاضرة"
        section_title_hint = "عنوان القسم"
        content_hint = f"محتوى القسم المبسط بأسلوب ممتع وسهل الفهم ({narration_sentences} جمل)"
        keywords_hint = '["مصطلح رئيسي 1", "مصطلح رئيسي 2", "مصطلح رئيسي 3", "مصطلح رئيسي 4"]'
        narration_hint = f"نص الشرح الكامل باللهجة المطلوبة ({narration_sentences} جمل)"
        lang_note = "النص يجب أن يكون باللهجة المطلوبة بالكامل"

    prompt = f"""أنت معلم خبير ومتخصص في تبسيط المحاضرات العلمية.

{instruction}

المحاضرة:
---
{text[:text_limit]}
---

قم بتحليل المحاضرة وأرجع JSON فقط بالتنسيق التالي. يجب أن يحتوي على بالضبط {num_sections} أقسام:

{{
  "lecture_type": "one of: medicine/science/math/literature/history/computer/business/other",
  "title": "{title_hint}",
  "sections": [
    {{
      "title": "{section_title_hint}",
      "content": "{content_hint}",
      "keywords": {keywords_hint},
      "keyword_images": [
        "cartoon visual 1 - simple description in English",
        "cartoon visual 2 - simple description in English",
        "cartoon visual 3 - simple description in English",
        "cartoon visual 4 - simple description in English"
      ],
      "narration": "{narration_hint}",
      "duration_estimate": 45
    }}
  ],
  "summary": "{summary_hint}",
  "key_points": {key_points_hint},
  "total_sections": {num_sections}
}}

مهم جداً:
- {lang_note}
- يجب أن تكون {num_sections} أقسام بالضبط
- أرجع JSON فقط بدون أي نص إضافي
"""

    content = await _generate_with_gemini(prompt, max_output_tokens=8192)
    content = content.strip()
    content = re.sub(r'^```json\s*', '', content)
    content = re.sub(r'\s*```$', '', content)
    content = content.strip()

    try:
        result = json.loads(content)
        return result
    except json.JSONDecodeError:
        json_match = re.search(r'\{[\s\S]*\}', content)
        if json_match:
            return json.loads(json_match.group())
        raise ValueError(f"Failed to parse Gemini response as JSON: {content[:500]}")


async def extract_full_text_from_pdf(pdf_bytes: bytes) -> str:
    """استخراج النص من ملف PDF"""
    import PyPDF2

    reader = PyPDF2.PdfReader(io.BytesIO(pdf_bytes))
    pages = []
    for page in reader.pages:
        page_text = page.extract_text() or ""
        if page_text.strip():
            pages.append(page_text)
    return "\n\n".join(pages)


# ── توليد الصور المجاني باستخدام Pollinations.ai ──────────────────────────────

async def _pollinations_generate(prompt: str) -> bytes | None:
    """توليد صورة باستخدام Pollinations.ai المجاني"""
    import urllib.parse

    clean_prompt = prompt[:380].replace("\n", " ")
    seed = random.randint(1, 99999)
    encoded = urllib.parse.quote(clean_prompt)
    url = f"https://image.pollinations.ai/prompt/{encoded}?width=854&height=480&nologo=true&seed={seed}&model=flux"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status == 200:
                    raw = await resp.read()
                    if len(raw) > 5000:
                        pil_img = PILImage.open(io.BytesIO(raw)).convert("RGB")
                        pil_img = pil_img.resize((854, 480), PILImage.LANCZOS)
                        buf = io.BytesIO()
                        pil_img.save(buf, "JPEG", quality=85)
                        return buf.getvalue()
    except Exception as e:
        print(f"Pollinations error: {e}")
    return None


def _make_placeholder_image(keywords: list, lecture_type: str = "other") -> bytes:
    """إنشاء صورة احتياطية بسيطة"""
    W, H = 854, 480
    img = PILImage.new("RGB", (W, H), (30, 30, 80))
    draw = ImageDraw.Draw(img)

    keyword = keywords[0] if keywords else "Educational"

    try:
        font_path = os.path.join(os.path.dirname(__file__), "fonts", "Amiri-Bold.ttf")
        font = ImageFont.truetype(font_path, 60)
    except Exception:
        font = ImageFont.load_default()

    # مركز النص
    bbox = draw.textbbox((0, 0), keyword, font=font)
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x, y = (W - w) // 2, (H - h) // 2

    draw.text((x, y), keyword, fill=(255, 255, 255), font=font)

    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=90)
    return buf.getvalue()


async def fetch_image_for_keyword(
    keyword: str,
    section_title: str,
    lecture_type: str,
    image_search_en: str = "",
) -> bytes:
    """جلب صورة للكلمة المفتاحية - Pollinations مجاني"""
    subject = (image_search_en or keyword).strip()

    prompt = f"educational cartoon illustration, {subject}, simple clean style, white background, no text"

    try:
        img_bytes = await _pollinations_generate(prompt)
        if img_bytes:
            return img_bytes
    except Exception as e:
        print(f"Pollinations failed for '{subject}': {e}")

    return _make_placeholder_image([keyword, section_title], lecture_type)
