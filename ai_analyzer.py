import json
import re
import io
import asyncio
import aiohttp
import os
from PIL import Image as PILImage, ImageDraw, ImageFont
from google import genai
from google.genai import types as genai_types
from config import GOOGLE_API_KEY, GOOGLE_API_KEYS, GROQ_API_KEYS, OPENROUTER_API_KEYS, OPENAI_API_KEY

# ── Google API key pool ────────────────────────────────────────────────────────
_key_pool: list[str] = list(GOOGLE_API_KEYS) if GOOGLE_API_KEYS else ([GOOGLE_API_KEY] if GOOGLE_API_KEY else [])
_groq_pool: list[str] = list(GROQ_API_KEYS) if GROQ_API_KEYS else []
_or_pool: list[str] = list(OPENROUTER_API_KEYS) if OPENROUTER_API_KEYS else []
_key_clients: dict[str, object] = {}
_current_key_idx: int = 0


def _get_client(key: str | None = None):
    if not _key_pool:
        raise RuntimeError("GOOGLE_API_KEY غير مضبوط")
    use_key = key or _key_pool[_current_key_idx % len(_key_pool)]
    if use_key not in _key_clients:
        _key_clients[use_key] = genai.Client(api_key=use_key)
    return _key_clients[use_key]


class QuotaExhaustedError(Exception):
    pass


_GROQ_MODELS = ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "gemma2-9b-it"]
_OR_MODELS = ["openai/gpt-oss-120b:free", "nvidia/nemotron-3-super-120b-a12b:free", "openai/gpt-oss-20b:free"]


async def _generate_with_groq(prompt: str, max_tokens: int = 8192) -> str:
    if not _groq_pool:
        raise QuotaExhaustedError("لا يوجد GROQ_API_KEY")
    for groq_key in _groq_pool:
        for model in _GROQ_MODELS:
            try:
                headers = {"Authorization": f"Bearer {groq_key}", "Content-Type": "application/json"}
                payload = {"model": model, "messages": [{"role": "user", "content": prompt}], "max_tokens": min(max_tokens, 8192), "temperature": 0.3}
                async with aiohttp.ClientSession() as s:
                    async with s.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=60)) as r:
                        if r.status == 200:
                            data = await r.json()
                            print(f"✅ Groq: {model}")
                            return data["choices"][0]["message"]["content"].strip()
            except:
                continue
    raise QuotaExhaustedError("نفدت حصة Groq")


async def _generate_with_openrouter(prompt: str, max_tokens: int = 8192) -> str:
    if not _or_pool:
        raise QuotaExhaustedError("لا يوجد OPENROUTER_API_KEY")
    for or_key in _or_pool:
        for model in _OR_MODELS:
            try:
                headers = {"Authorization": f"Bearer {or_key}", "Content-Type": "application/json", "HTTP-Referer": "https://replit.com", "X-Title": "Lecture Bot"}
                payload = {"model": model, "messages": [{"role": "user", "content": prompt}], "max_tokens": min(max_tokens, 8192), "temperature": 0.3}
                async with aiohttp.ClientSession() as s:
                    async with s.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=90)) as r:
                        if r.status == 200:
                            data = await r.json()
                            content = data["choices"][0]["message"]["content"]
                            if content:
                                print(f"✅ OpenRouter: {model}")
                                return content.strip()
            except:
                continue
    raise QuotaExhaustedError("نفدت حصة OpenRouter")


async def _generate_with_rotation(prompt: str, max_output_tokens: int = 8192) -> str:
    global _current_key_idx
    gemini_models = ["gemini-2.0-flash", "gemini-2.0-flash-lite"]
    
    for i in range(len(_key_pool)):
        key_idx = (_current_key_idx + i) % len(_key_pool)
        key = _key_pool[key_idx]
        client = _get_client(key)
        for model in gemini_models:
            try:
                response = await asyncio.to_thread(
                    client.models.generate_content, model=model, contents=prompt,
                    config=genai_types.GenerateContentConfig(temperature=0.3, max_output_tokens=max_output_tokens),
                )
                _current_key_idx = key_idx
                print(f"✅ Gemini: {model}")
                return response.text.strip()
            except:
                continue
    
    if _groq_pool:
        try:
            return await _generate_with_groq(prompt, max_output_tokens)
        except:
            pass
    
    if _or_pool:
        try:
            return await _generate_with_openrouter(prompt, max_output_tokens)
        except:
            pass
    
    raise QuotaExhaustedError("QUOTA_EXHAUSTED")


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
        narration_hint = f"Full narration in English ({narration_sentences} sentences)"
        lang_note = "IMPORTANT: Write ALL text fields in English."
    else:
        summary_hint = "ملخص المحاضرة بأسلوب مبسط (4-5 جمل)"
        key_points_hint = '["نقطة رئيسية 1", "نقطة رئيسية 2", "نقطة رئيسية 3", "نقطة رئيسية 4"]'
        title_hint = "عنوان المحاضرة"
        section_title_hint = "عنوان القسم"
        content_hint = f"محتوى القسم المبسط بأسلوب ممتع وسهل الفهم ({narration_sentences} جمل)"
        keywords_hint = '["مصطلح رئيسي 1", "مصطلح رئيسي 2", "مصطلح رئيسي 3", "مصطلح رئيسي 4"]'
        narration_hint = f"نص الشرح الكامل بالنص الطبيعي للمحاضر مع اللهجة المطلوبة ({narration_sentences} جمل)"
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
        "cartoon educational illustration description for keyword1 - 3-5 English words",
        "cartoon educational illustration description for keyword2 - 3-5 English words",
        "cartoon educational illustration description for keyword3 - 3-5 English words",
        "cartoon educational illustration description for keyword4 - 3-5 English words"
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
- keywords: 4 مصطلحات أساسية
- keyword_images: وصف إنجليزي لصورة كرتونية تعليمية (3-5 كلمات)
- أرجع JSON فقط بدون أي نص إضافي
"""

    content = await _generate_with_rotation(prompt, max_output_tokens=8192)
    content = content.strip()
    content = re.sub(r'^```json\s*', '', content)
    content = re.sub(r'\s*```$', '', content)
    content = content.strip()

    try:
        return json.loads(content)
    except json.JSONDecodeError:
        json_match = re.search(r'\{[\s\S]*\}', content)
        if json_match:
            return json.loads(json_match.group())
        raise ValueError(f"Failed to parse JSON: {content[:500]}")


# ── استخراج النص من PDF بسرعة ────────────────────────────────────────────────
async def extract_full_text_from_pdf(pdf_bytes: bytes) -> str:
    """استخراج النص من PDF بسرعة وفعالية"""
    import PyPDF2
    
    def _extract():
        reader = PyPDF2.PdfReader(io.BytesIO(pdf_bytes))
        texts = []
        total_pages = len(reader.pages)
        # حد أقصى 100 صفحة للسرعة
        for page in reader.pages[:100]:
            try:
                txt = page.extract_text()
                if txt and txt.strip():
                    texts.append(txt.strip())
            except Exception:
                pass
        return "\n\n".join(texts)
    
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _extract)


# ── إنشاء صورة كرتونية بديلة ─────────────────────────────────────────────────
def _create_cartoon_placeholder(keyword: str, section_title: str, lecture_type: str) -> bytes:
    """إنشاء صورة كرتونية بديلة احترافية"""
    W, H = 800, 500
    colors = {
        "medicine": (255, 107, 107),
        "science": (78, 205, 196),
        "math": (255, 209, 102),
        "physics": (100, 180, 255),
        "chemistry": (170, 120, 255),
        "biology": (100, 220, 150),
        "history": (255, 180, 80),
        "computer": (80, 200, 220),
        "business": (255, 200, 100),
        "literature": (220, 120, 200),
        "other": (150, 150, 220),
    }
    color = colors.get(lecture_type, colors["other"])
    
    img = PILImage.new("RGB", (W, H), (250, 252, 255))
    draw = ImageDraw.Draw(img)
    
    # خلفية متدرجة
    for y in range(H):
        t = y / H
        r = int(255 * (1 - t) + color[0] * 0.15 * t)
        g = int(255 * (1 - t) + color[1] * 0.15 * t)
        b = int(255 * (1 - t) + color[2] * 0.15 * t)
        draw.line([(0, y), (W, y)], fill=(r, g, b))
    
    # إطار
    draw.rounded_rectangle([(15, 15), (W-15, H-15)], radius=20, outline=color, width=4)
    
    # أيقونة
    icons = {"medicine": "🩺", "science": "🔬", "math": "📐", "physics": "⚡", "chemistry": "🧪", "biology": "🧬", "history": "🏛️", "computer": "💻", "business": "💼", "literature": "📖", "other": "📚"}
    icon = icons.get(lecture_type, "📚")
    
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 60)
    except:
        font = ImageFont.load_default()
    bbox = draw.textbbox((0, 0), icon, font=font)
    iw = bbox[2] - bbox[0]
    draw.text(((W - iw)//2, 80), icon, fill=color, font=font)
    
    # الكلمة المفتاحية
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
        kw = get_display(arabic_reshaper.reshape(keyword[:25]))
    except:
        kw = keyword[:25]
    
    try:
        font_kw = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 32)
    except:
        font_kw = ImageFont.load_default()
    
    bbox = draw.textbbox((0, 0), kw, font=font_kw)
    kw_w = bbox[2] - bbox[0]
    draw.text(((W - kw_w)//2 + 2, 180), kw, fill=(0, 0, 0, 100), font=font_kw)
    draw.text(((W - kw_w)//2, 178), kw, fill=(40, 45, 60), font=font_kw)
    
    # عنوان القسم
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
        st = get_display(arabic_reshaper.reshape(section_title[:35]))
    except:
        st = section_title[:35]
    
    try:
        font_st = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 16)
    except:
        font_st = ImageFont.load_default()
    
    bbox = draw.textbbox((0, 0), st, font=font_st)
    sw = bbox[2] - bbox[0]
    draw.text(((W - sw)//2, 260), st, fill=(100, 100, 120), font=font_st)
    
    # خط زخرفي
    draw.rectangle([(W//4, 300), (W*3//4, 304)], fill=color)
    
    # نص "صورة تعليمية"
    hint = "🎨 صورة تعليمية"
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
        hint = get_display(arabic_reshaper.reshape(hint))
    except:
        pass
    
    bbox = draw.textbbox((0, 0), hint, font=font_st)
    hw = bbox[2] - bbox[0]
    draw.text(((W - hw)//2, 350), hint, fill=(150, 150, 170), font=font_st)
    
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=90)
    return buf.getvalue()


# ── جلب الصورة مع نظام بدائل متعدد ───────────────────────────────────────────
async def fetch_image_for_keyword(
    keyword: str,
    section_title: str,
    lecture_type: str,
    image_search_en: str = "",
) -> bytes:
    """جلب صورة للكلمة المفتاحية - مع نظام بدائل متعدد"""
    
    subject = (image_search_en or keyword).strip()
    
    # 1. Pollinations.ai
    try:
        import urllib.parse, random
        prompt = f"educational cartoon illustration, {subject}, simple colorful style, clear"
        encoded = urllib.parse.quote(prompt[:200])
        url = f"https://image.pollinations.ai/prompt/{encoded}?width=800&height=500&seed={random.randint(1,99999)}&model=flux"
        
        async with aiohttp.ClientSession() as s:
            async with s.get(url, timeout=aiohttp.ClientTimeout(total=10)) as r:
                if r.status == 200:
                    data = await r.read()
                    if len(data) > 5000:
                        print(f"✅ Pollinations: {subject[:30]}")
                        return data
    except Exception as e:
        print(f"Pollinations failed: {e}")
    
    # 2. DALL-E
    if OPENAI_API_KEY:
        try:
            import base64
            prompt = f"cartoon educational illustration, {subject}, simple colorful style, white background"
            payload = {"model": "dall-e-3", "prompt": prompt, "size": "1024x1024", "n": 1, "response_format": "b64_json"}
            headers = {"Authorization": f"Bearer {OPENAI_API_KEY}"}
            
            async with aiohttp.ClientSession() as s:
                async with s.post("https://api.openai.com/v1/images/generations", json=payload, headers=headers, timeout=30) as r:
                    if r.status == 200:
                        data = await r.json()
                        b64 = data["data"][0].get("b64_json", "")
                        if b64:
                            print(f"✅ DALL-E: {subject[:30]}")
                            return base64.b64decode(b64)
        except Exception as e:
            print(f"DALL-E failed: {e}")
    
    # 3. Pexels
    pexels_key = os.getenv("PEXELS_API_KEY", "")
    if pexels_key:
        try:
            import urllib.parse
            q = urllib.parse.quote(f"{subject} education")
            headers = {"Authorization": pexels_key}
            async with aiohttp.ClientSession() as s:
                async with s.get(f"https://api.pexels.com/v1/search?query={q}&per_page=3", headers=headers, timeout=10) as r:
                    if r.status == 200:
                        data = await r.json()
                        for photo in data.get("photos", []):
                            img_url = photo["src"].get("large")
                            if img_url:
                                async with s.get(img_url, timeout=15) as ir:
                                    if ir.status == 200:
                                        print(f"✅ Pexels: {subject[:30]}")
                                        return await ir.read()
        except Exception as e:
            print(f"Pexels failed: {e}")
    
    # 4. Pixabay
    pixabay_key = os.getenv("PIXABAY_API_KEY", "")
    if pixabay_key:
        try:
            import urllib.parse
            q = urllib.parse.quote(f"{subject} cartoon")
            async with aiohttp.ClientSession() as s:
                async with s.get(f"https://pixabay.com/api/?key={pixabay_key}&q={q}&per_page=3", timeout=10) as r:
                    if r.status == 200:
                        data = await r.json()
                        for hit in data.get("hits", []):
                            img_url = hit.get("largeImageURL")
                            if img_url:
                                async with s.get(img_url, timeout=15) as ir:
                                    if ir.status == 200:
                                        print(f"✅ Pixabay: {subject[:30]}")
                                        return await ir.read()
        except Exception as e:
            print(f"Pixabay failed: {e}")
    
    # 5. صورة كرتونية بديلة
    print(f"🎨 Creating cartoon placeholder for: {subject[:30]}")
    return _create_cartoon_placeholder(keyword, section_title, lecture_type)


async def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """نسخة مختصرة للتوافق"""
    return await extract_full_text_from_pdf(pdf_bytes)
