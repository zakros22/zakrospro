import json
import re
import io
import asyncio
import aiohttp
import os
import random
import base64
import urllib.parse
from PIL import Image as PILImage, ImageDraw, ImageFont
from google import genai
from google.genai import types as genai_types
from config import (
    GOOGLE_API_KEY, GOOGLE_API_KEYS, GROQ_API_KEYS, OPENROUTER_API_KEYS,
    OPENAI_API_KEY, PEXELS_API_KEY, PIXABAY_API_KEY, UNSPLASH_ACCESS_KEY
)

# ═════════════════════════════════════════════════════════════════════════════
# 🔑 نظام المفاتيح المتعدد
# ═════════════════════════════════════════════════════════════════════════════
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
                                return content.strip()
            except:
                continue
    raise QuotaExhaustedError("نفدت حصة OpenRouter")


async def _generate_with_rotation(prompt: str, max_output_tokens: int = 8192) -> str:
    global _current_key_idx
    gemini_models = ["gemini-2.0-flash", "gemini-2.0-flash-lite", "gemini-1.5-flash"]
    
    # تجربة Gemini
    for i in range(len(_key_pool)):
        key_idx = (_current_key_idx + i) % len(_key_pool)
        key = _key_pool[key_idx]
        client = _get_client(key)
        for model in gemini_models:
            try:
                response = await asyncio.to_thread(
                    client.models.generate_content, model=model, contents=prompt,
                    config=genai_types.GenerateContentConfig(temperature=0.3, max_output_tokens=max_output_tokens)
                )
                _current_key_idx = key_idx
                print(f"✅ Gemini: {model}")
                return response.text.strip()
            except Exception as e:
                if "429" in str(e) or "quota" in str(e).lower():
                    continue
                else:
                    continue
    
    # تجربة Groq
    if _groq_pool:
        print("🔄 Trying Groq...")
        try:
            return await _generate_with_groq(prompt, max_output_tokens)
        except:
            pass
    
    # تجربة OpenRouter
    if _or_pool:
        print("🔄 Trying OpenRouter...")
        try:
            return await _generate_with_openrouter(prompt, max_output_tokens)
        except:
            pass
    
    raise QuotaExhaustedError("جميع المفاتيح منتهية")


def _compute_lecture_scale(text: str) -> tuple:
    """حساب عدد الأقسام بناءً على طول النص"""
    word_count = len(text.split())
    if word_count < 300:
        return 3, "6-8", 3000
    elif word_count < 800:
        return 4, "8-10", 5000
    elif word_count < 1500:
        return 5, "10-12", 6000
    elif word_count < 3000:
        return 6, "12-15", 7000
    else:
        return 7, "15-18", 8000


async def analyze_lecture(text: str, dialect: str = "msa") -> dict:
    dialect_instructions = {
        "iraq": "استخدم اللهجة العراقية في الشرح، مع كلمات عراقية أصيلة مثل (هواية، گلت، يعني، بس، هسا، چان، عگب)",
        "egypt": "استخدم اللهجة المصرية في الشرح، مع كلمات مصرية مثل (أوي، معلش، يعني، بس، كده، إيه، مش)",
        "syria": "استخدم اللهجة الشامية في الشرح، مع كلمات شامية مثل (هلق، شو، كتير، منيح، هيك، شي، عنجد)",
        "gulf": "استخدم اللهجة الخليجية في الشرح، مع كلمات خليجية مثل (زين، وايد، عاد، هاذي، أبشر، يمعود)",
        "msa": "استخدم العربية الفصحى الواضحة والمبسطة",
        "english": "Use clear, simple English. Explain like a teacher to students.",
        "british": "Use British English with a professional, clear academic tone."
    }

    instruction = dialect_instructions.get(dialect, dialect_instructions["msa"])
    num_sections, narration_sentences, max_tokens = _compute_lecture_scale(text)
    text_limit = min(len(text), 5000)
    is_english = dialect in ("english", "british")

    if is_english:
        summary_hint = "A clear, concise summary (4-5 sentences)"
        key_points_hint = '["Key point 1", "Key point 2", "Key point 3", "Key point 4"]'
        title_hint = "Lecture title"
        section_title_hint = "Section title"
        content_hint = f"Simplified section content ({narration_sentences} sentences)"
        keywords_hint = '["keyword1", "keyword2", "keyword3", "keyword4"]'
        narration_hint = f"Full narration ({narration_sentences} sentences)"
        lang_note = "Write ALL text in English."
    else:
        summary_hint = "ملخص المحاضرة بأسلوب مبسط (4-5 جمل)"
        key_points_hint = '["نقطة رئيسية 1", "نقطة رئيسية 2", "نقطة رئيسية 3", "نقطة رئيسية 4"]'
        title_hint = "عنوان المحاضرة"
        section_title_hint = "عنوان القسم"
        content_hint = f"محتوى القسم المبسط بأسلوب ممتع وسهل الفهم ({narration_sentences} جمل)"
        keywords_hint = '["مصطلح 1", "مصطلح 2", "مصطلح 3", "مصطلح 4"]'
        narration_hint = f"نص الشرح الكامل باللهجة المطلوبة ({narration_sentences} جمل)"
        lang_note = "النص يجب أن يكون باللهجة المطلوبة"

    prompt = f"""أنت معلم خبير في تبسيط المحاضرات.

{instruction}

المحاضرة:
---
{text[:text_limit]}
---

أرجع JSON فقط بالتنسيق التالي. {num_sections} أقسام بالضبط:

{{
  "lecture_type": "medicine/science/math/literature/history/computer/business/other",
  "title": "{title_hint}",
  "sections": [
    {{
      "title": "{section_title_hint}",
      "content": "{content_hint}",
      "keywords": {keywords_hint},
      "keyword_images": [
        "cartoon illustration description for keyword1 - 3-5 English words",
        "cartoon illustration description for keyword2 - 3-5 English words",
        "cartoon illustration description for keyword3 - 3-5 English words",
        "cartoon illustration description for keyword4 - 3-5 English words"
      ],
      "narration": "{narration_hint}",
      "duration_estimate": 45
    }}
  ],
  "summary": "{summary_hint}",
  "key_points": {key_points_hint}
}}

مهم جداً:
- {lang_note}
- {num_sections} أقسام بالضبط
- keywords: 4 مصطلحات
- keyword_images: وصف إنجليزي لصورة كرتونية (3-5 كلمات)
- أرجع JSON فقط بدون أي نص إضافي أو ```json
"""

    content = await _generate_with_rotation(prompt, max_output_tokens=max_tokens)
    content = content.strip()
    content = re.sub(r'^```json\s*', '', content)
    content = re.sub(r'\s*```$', '', content)
    content = content.strip()

    try:
        result = json.loads(content)
        if len(result.get("sections", [])) != num_sections:
            sections = result.get("sections", [])
            if len(sections) > num_sections:
                result["sections"] = sections[:num_sections]
        return result
    except json.JSONDecodeError:
        json_match = re.search(r'\{[\s\S]*\}', content)
        if json_match:
            return json.loads(json_match.group())
        raise ValueError(f"Failed to parse JSON: {content[:300]}")


# ═════════════════════════════════════════════════════════════════════════════
# 🖼️ نظام الصور الخرافي - 5 بدائل مجانية
# ═════════════════════════════════════════════════════════════════════════════

async def _fetch_pexels(query: str) -> bytes | None:
    """Pexels API - صور حقيقية عالية الجودة"""
    if not PEXELS_API_KEY:
        return None
    try:
        headers = {"Authorization": PEXELS_API_KEY}
        url = f"https://api.pexels.com/v1/search?query={urllib.parse.quote(query)}&per_page=3&orientation=landscape"
        async with aiohttp.ClientSession() as s:
            async with s.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as r:
                if r.status == 200:
                    data = await r.json()
                    for photo in data.get("photos", []):
                        img_url = photo["src"].get("large")
                        if img_url:
                            async with s.get(img_url, timeout=15) as ir:
                                if ir.status == 200:
                                    print(f"✅ Pexels: {query[:30]}")
                                    return await ir.read()
    except Exception as e:
        print(f"Pexels error: {e}")
    return None


async def _fetch_pixabay(query: str) -> bytes | None:
    """Pixabay API - صور تعليمية"""
    if not PIXABAY_API_KEY:
        return None
    try:
        url = f"https://pixabay.com/api/?key={PIXABAY_API_KEY}&q={urllib.parse.quote(query)}&per_page=3&orientation=horizontal"
        async with aiohttp.ClientSession() as s:
            async with s.get(url, timeout=aiohttp.ClientTimeout(total=10)) as r:
                if r.status == 200:
                    data = await r.json()
                    for hit in data.get("hits", []):
                        img_url = hit.get("largeImageURL")
                        if img_url:
                            async with s.get(img_url, timeout=15) as ir:
                                if ir.status == 200:
                                    print(f"✅ Pixabay: {query[:30]}")
                                    return await ir.read()
    except Exception as e:
        print(f"Pixabay error: {e}")
    return None


async def _fetch_unsplash(query: str) -> bytes | None:
    """Unsplash API - صور احترافية"""
    if not UNSPLASH_ACCESS_KEY:
        return None
    try:
        headers = {"Authorization": f"Client-ID {UNSPLASH_ACCESS_KEY}"}
        url = f"https://api.unsplash.com/search/photos?query={urllib.parse.quote(query)}&per_page=3&orientation=landscape"
        async with aiohttp.ClientSession() as s:
            async with s.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as r:
                if r.status == 200:
                    data = await r.json()
                    for photo in data.get("results", []):
                        img_url = photo["urls"].get("regular")
                        if img_url:
                            async with s.get(img_url, timeout=15) as ir:
                                if ir.status == 200:
                                    print(f"✅ Unsplash: {query[:30]}")
                                    return await ir.read()
    except Exception as e:
        print(f"Unsplash error: {e}")
    return None


async def _fetch_pollinations(query: str) -> bytes | None:
    """Pollinations.ai - ذكاء اصطناعي مجاني"""
    try:
        prompt = f"educational cartoon illustration, {query}, simple colorful style, clear background"
        encoded = urllib.parse.quote(prompt[:200])
        url = f"https://image.pollinations.ai/prompt/{encoded}?width=1280&height=720&seed={random.randint(1,99999)}&model=flux"
        async with aiohttp.ClientSession() as s:
            async with s.get(url, timeout=aiohttp.ClientTimeout(total=12)) as r:
                if r.status == 200:
                    data = await r.read()
                    if len(data) > 5000:
                        print(f"✅ Pollinations: {query[:30]}")
                        return data
    except Exception as e:
        print(f"Pollinations error: {e}")
    return None


async def _fetch_dalle(query: str) -> bytes | None:
    """DALL-E 3 - OpenAI"""
    if not OPENAI_API_KEY:
        return None
    try:
        payload = {
            "model": "dall-e-3",
            "prompt": f"cartoon educational illustration, {query}, simple style, white background",
            "size": "1024x1024",
            "n": 1,
            "response_format": "b64_json"
        }
        headers = {"Authorization": f"Bearer {OPENAI_API_KEY}"}
        async with aiohttp.ClientSession() as s:
            async with s.post("https://api.openai.com/v1/images/generations", json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as r:
                if r.status == 200:
                    data = await r.json()
                    b64 = data["data"][0].get("b64_json", "")
                    if b64:
                        print(f"✅ DALL-E: {query[:30]}")
                        return base64.b64decode(b64)
    except Exception as e:
        print(f"DALL-E error: {e}")
    return None


def _create_cartoon_placeholder(keyword: str, section_title: str, lecture_type: str) -> bytes:
    """إنشاء صورة كرتونية بديلة احترافية"""
    W, H = 1280, 720
    colors = {
        "medicine": (41, 128, 185), "science": (39, 174, 96), "math": (230, 126, 34),
        "physics": (155, 89, 182), "chemistry": (231, 76, 60), "biology": (52, 152, 219),
        "history": (241, 196, 15), "computer": (142, 68, 173), "business": (26, 188, 156),
        "literature": (192, 57, 43), "other": (149, 165, 166),
    }
    color = colors.get(lecture_type, colors["other"])
    
    img = PILImage.new("RGB", (W, H), (245, 248, 250))
    draw = ImageDraw.Draw(img)
    
    # خلفية متدرجة
    for y in range(H):
        t = y / H
        r = int(255 * (1 - t) + color[0] * 0.2 * t)
        g = int(255 * (1 - t) + color[1] * 0.2 * t)
        b = int(255 * (1 - t) + color[2] * 0.2 * t)
        draw.line([(0, y), (W, y)], fill=(r, g, b))
    
    # إطار
    draw.rounded_rectangle([(20, 20), (W-20, H-20)], radius=30, outline=color, width=6)
    
    # أيقونة
    icons = {"medicine": "🩺", "science": "🔬", "math": "📐", "physics": "⚡",
             "chemistry": "🧪", "biology": "🧬", "history": "🏛️", "computer": "💻",
             "business": "💼", "literature": "📖", "other": "📚"}
    icon = icons.get(lecture_type, "📚")
    
    # تحميل الخط
    try:
        font = ImageFont.truetype("/app/fonts/Amiri-Bold.ttf", 80)
    except:
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 80)
        except:
            font = ImageFont.load_default()
    
    bbox = draw.textbbox((0, 0), icon, font=font)
    iw = bbox[2] - bbox[0]
    draw.text(((W - iw)//2, 150), icon, fill=color, font=font)
    
    # الكلمة المفتاحية
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
        kw = get_display(arabic_reshaper.reshape(keyword[:30]))
    except:
        kw = keyword[:30]
    
    try:
        font_kw = ImageFont.truetype("/app/fonts/Amiri-Bold.ttf", 48)
    except:
        try:
            font_kw = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 48)
        except:
            font_kw = ImageFont.load_default()
    
    bbox = draw.textbbox((0, 0), kw, font=font_kw)
    kw_w = bbox[2] - bbox[0]
    draw.text(((W - kw_w)//2 + 3, 300), kw, fill=(0, 0, 0, 100), font=font_kw)
    draw.text(((W - kw_w)//2, 297), kw, fill=(40, 45, 60), font=font_kw)
    
    # نص توضيحي
    hint = "🎨 صورة تعليمية"
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
        hint = get_display(arabic_reshaper.reshape(hint))
    except:
        pass
    
    try:
        font_hint = ImageFont.truetype("/app/fonts/Amiri-Regular.ttf", 24)
    except:
        try:
            font_hint = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 24)
        except:
            font_hint = ImageFont.load_default()
    
    bbox = draw.textbbox((0, 0), hint, font=font_hint)
    hw = bbox[2] - bbox[0]
    draw.text(((W - hw)//2, 450), hint, fill=(120, 120, 140), font=font_hint)
    
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=90)
    return buf.getvalue()


async def fetch_image_for_keyword(
    keyword: str,
    section_title: str,
    lecture_type: str,
    image_search_en: str = "",
) -> bytes:
    """جلب صورة للكلمة المفتاحية - 5 بدائل مجانية"""
    subject = (image_search_en or keyword).strip()
    
    # 1. Pollinations.ai (ذكاء اصطناعي مجاني)
    img = await _fetch_pollinations(subject)
    if img:
        return img
    
    # 2. Pexels (صور حقيقية)
    img = await _fetch_pexels(f"{subject} education")
    if img:
        return img
    
    # 3. Pixabay (صور تعليمية)
    img = await _fetch_pixabay(subject)
    if img:
        return img
    
    # 4. Unsplash (صور احترافية)
    img = await _fetch_unsplash(subject)
    if img:
        return img
    
    # 5. DALL-E (إذا وجد مفتاح)
    img = await _fetch_dalle(subject)
    if img:
        return img
    
    # 6. صورة كرتونية بديلة
    print(f"🎨 Creating cartoon placeholder for: {subject[:30]}")
    return _create_cartoon_placeholder(keyword, section_title, lecture_type)


# ═════════════════════════════════════════════════════════════════════════════
# 📄 استخراج النص من PDF
# ═════════════════════════════════════════════════════════════════════════════

async def extract_full_text_from_pdf(pdf_bytes: bytes) -> str:
    import PyPDF2
    
    def _extract():
        reader = PyPDF2.PdfReader(io.BytesIO(pdf_bytes))
        texts = []
        for page in reader.pages[:100]:
            try:
                txt = page.extract_text()
                if txt and txt.strip():
                    texts.append(txt.strip())
            except:
                pass
        return "\n\n".join(texts)
    
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _extract)


async def extract_full_text_from_pdf_path(pdf_path: str) -> str:
    import PyPDF2
    
    def _extract():
        try:
            reader = PyPDF2.PdfReader(pdf_path)
            texts = []
            for page in reader.pages[:100]:
                try:
                    txt = page.extract_text()
                    if txt and txt.strip():
                        texts.append(txt.strip())
                except:
                    pass
            return "\n\n".join(texts)
        except Exception as e:
            print(f"PDF extraction error: {e}")
            return ""
    
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _extract)


async def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    return await extract_full_text_from_pdf(pdf_bytes)


def _is_safe_url(url: str) -> bool:
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        return parsed.scheme in ('http', 'https')
    except:
        return False


async def extract_text_from_url(url: str) -> str:
    if not _is_safe_url(url):
        return ""
    try:
        from bs4 import BeautifulSoup
        headers = {'User-Agent': 'Mozilla/5.0'}
        async with aiohttp.ClientSession() as s:
            async with s.get(url, headers=headers, timeout=15) as r:
                if r.status == 200:
                    html = await r.text()
                    soup = BeautifulSoup(html, 'html.parser')
                    for tag in soup(['script', 'style', 'nav', 'footer', 'header']):
                        tag.decompose()
                    text = soup.get_text(separator='\n', strip=True)
                    return '\n'.join([l.strip() for l in text.split('\n') if len(l.strip()) > 20][:200])
    except:
        pass
    return ""


async def translate_full_text(text: str, dialect: str) -> str:
    return text


async def generate_educational_image(prompt: str, lecture_type: str, keywords: list = None, image_search: str = None, image_search_fallbacks: list = None) -> bytes:
    kw = keywords[0] if keywords else prompt[:30]
    return await fetch_image_for_keyword(kw, "", lecture_type, image_search or prompt)


def _make_placeholder_image(keywords: list, lecture_type: str = "other") -> bytes:
    return _create_cartoon_placeholder(keywords[0] if keywords else "مصطلح", "", lecture_type)
