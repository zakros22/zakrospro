import json
import re
import io
import asyncio
import aiohttp
import random
from PIL import Image as PILImage, ImageDraw, ImageFont
from google import genai
from google.genai import types as genai_types
import os

# ──────────────────────────────────────────────────────────────────────────────
# تحميل مفاتيح Google
# ──────────────────────────────────────────────────────────────────────────────

def _load_google_keys():
    keys = []
    raw_keys = os.getenv("GOOGLE_API_KEYS", "")
    if raw_keys:
        keys.extend([k.strip() for k in raw_keys.split(",") if k.strip()])
    for i in range(1, 10):
        key = os.getenv(f"GOOGLE_API_KEY_{i}", "")
        if key and key not in keys:
            keys.append(key.strip())
    single_key = os.getenv("GOOGLE_API_KEY", "")
    if single_key and single_key not in keys:
        keys.append(single_key.strip())
    return keys

_google_keys = _load_google_keys()
_current_google_idx = 0
_exhausted_google_keys = set()

def _get_next_google_key():
    global _current_google_idx
    if not _google_keys:
        return None
    for _ in range(len(_google_keys)):
        key = _google_keys[_current_google_idx % len(_google_keys)]
        if key not in _exhausted_google_keys:
            return key
        _current_google_idx += 1
    return None

def _mark_google_exhausted(key: str):
    global _current_google_idx
    _exhausted_google_keys.add(key)
    _current_google_idx += 1

# ──────────────────────────────────────────────────────────────────────────────
# تحميل مفاتيح Groq
# ──────────────────────────────────────────────────────────────────────────────

def _load_groq_keys():
    keys = []
    raw_keys = os.getenv("GROQ_API_KEYS", "")
    if raw_keys:
        keys.extend([k.strip() for k in raw_keys.split(",") if k.strip()])
    single_key = os.getenv("GROQ_API_KEY", "")
    if single_key and single_key not in keys:
        keys.append(single_key.strip())
    return keys

_groq_keys = _load_groq_keys()
_current_groq_idx = 0

def _get_next_groq_key():
    global _current_groq_idx
    if not _groq_keys:
        return None
    key = _groq_keys[_current_groq_idx % len(_groq_keys)]
    _current_groq_idx += 1
    return key

_GROQ_MODELS = ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "gemma2-9b-it"]

# ──────────────────────────────────────────────────────────────────────────────
# دوال التوليد
# ──────────────────────────────────────────────────────────────────────────────

async def _generate_with_google(prompt: str, max_tokens: int = 8192) -> str:
    models = ["gemini-2.0-flash", "gemini-2.0-flash-lite"]
    
    for _ in range(len(_google_keys) * 2):
        key = _get_next_google_key()
        if not key:
            break
        
        client = genai.Client(api_key=key)
        
        for model in models:
            try:
                response = await asyncio.to_thread(
                    client.models.generate_content,
                    model=model,
                    contents=prompt,
                    config=genai_types.GenerateContentConfig(
                        temperature=0.3,
                        max_output_tokens=max_tokens,
                    ),
                )
                return response.text.strip()
            except Exception as e:
                err = str(e)
                if "429" in err or "RESOURCE_EXHAUSTED" in err or "quota" in err.lower():
                    _mark_google_exhausted(key)
                    break
                else:
                    continue
    
    raise Exception("All Google keys exhausted")


async def _generate_with_groq(prompt: str, max_tokens: int = 8192) -> str:
    if not _groq_keys:
        raise Exception("No Groq keys")
    
    key = _get_next_groq_key()
    if not key:
        raise Exception("No Groq keys available")
    
    for model in _GROQ_MODELS:
        try:
            headers = {
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": min(max_tokens, 8192),
                "temperature": 0.3,
            }
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=60),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data["choices"][0]["message"]["content"].strip()
        except Exception:
            continue
    
    raise Exception("Groq failed")


async def _generate_with_rotation(prompt: str, max_output_tokens: int = 8192) -> str:
    if _google_keys:
        try:
            return await _generate_with_google(prompt, max_output_tokens)
        except Exception as e:
            print(f"Google failed: {e}")
    
    if _groq_keys:
        try:
            return await _generate_with_groq(prompt, max_output_tokens)
        except Exception as e:
            print(f"Groq failed: {e}")
    
    raise Exception("All AI services failed")


# ──────────────────────────────────────────────────────────────────────────────
# تحليل المحاضرة
# ──────────────────────────────────────────────────────────────────────────────

def _extract_keywords_from_text(text: str, max_words: int = 4) -> list:
    """استخراج الكلمات المفتاحية من النص العربي"""
    stop_words = {'و', 'في', 'من', 'على', 'إلى', 'أن', 'هو', 'هي', 'هذا', 'هذه', 'كان', 'كانت', 'مع', 'ما', 'لا', 'عن', 'إذا', 'لم', 'لن', 'قد', 'ثم', 'أو', 'أم', 'لكن', 'حتى', 'بل', 'كل', 'بعض', 'أي', 'تلك', 'ذلك', 'هؤلاء', 'الذي', 'التي', 'الذين', 'ما', 'ماذا', 'كيف', 'أين', 'متى'}
    
    words = re.findall(r'[\u0600-\u06FF]{4,}', text)
    word_freq = {}
    for w in words:
        if w not in stop_words:
            word_freq[w] = word_freq.get(w, 0) + 1
    
    sorted_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)
    return [w[0] for w in sorted_words[:max_words]]


async def analyze_lecture(text: str, dialect: str = "msa") -> dict:
    # استخراج الكلمات المفتاحية من النص الأصلي
    extracted_keywords = _extract_keywords_from_text(text, 6)
    
    dialect_instructions = {
        "iraq": "استخدم اللهجة العراقية في الشرح، مع كلمات عراقية أصيلة مثل (هواية، گلت، يعني، بس، هسا)",
        "egypt": "استخدم اللهجة المصرية في الشرح، مع كلمات مصرية مثل (أوي، معلش، يعني، بس، كده)",
        "syria": "استخدم اللهجة الشامية في الشرح، مع كلمات شامية مثل (هلق، شو، كتير، منيح، هيك)",
        "gulf": "استخدم اللهجة الخليجية في الشرح، مع كلمات خليجية مثل (زين، وايد، عاد، هاذي، أبشر)",
        "msa": "استخدم العربية الفصحى الواضحة والمبسطة",
    }

    instruction = dialect_instructions.get(dialect, dialect_instructions["msa"])
    
    # تحديد عدد الأقسام
    word_count = len(text.split())
    if word_count < 300:
        num_sections = 3
    elif word_count < 800:
        num_sections = 4
    elif word_count < 1500:
        num_sections = 5
    else:
        num_sections = 6
    
    text_limit = min(len(text), 4000)

    prompt = f"""أنت معلم خبير ومتخصص في تبسيط المحاضرات العلمية.

{instruction}

المحاضرة:
---
{text[:text_limit]}
---

الكلمات المفتاحية المستخرجة: {', '.join(extracted_keywords[:6])}

قم بتحليل المحاضرة وأرجع JSON فقط بالتنسيق التالي. يجب أن يحتوي على بالضبط {num_sections} أقسام:

{{
  "lecture_type": "medicine",
  "title": "عنوان المحاضرة",
  "sections": [
    {{
      "title": "عنوان القسم",
      "content": "محتوى القسم المبسط",
      "keywords": ["كلمة1", "كلمة2", "كلمة3", "كلمة4"],
      "narration": "نص الشرح الكامل باللهجة المطلوبة (8-10 جمل)",
      "duration_estimate": 45
    }}
  ],
  "summary": "ملخص المحاضرة بأسلوب مبسط (4-5 جمل)",
  "key_points": ["نقطة1", "نقطة2", "نقطة3", "نقطة4"]
}}

مهم جداً:
- يجب أن تكون {num_sections} أقسام بالضبط
- كل قسم يجب أن يحتوي على 4 كلمات مفتاحية من القائمة المستخرجة
- اكتب النصوص باللهجة المطلوبة
- أرجع JSON فقط بدون أي نص إضافي
"""

    try:
        content = await _generate_with_rotation(prompt, max_output_tokens=8192)
        content = content.strip()
        content = re.sub(r'^```json\s*', '', content)
        content = re.sub(r'\s*```$', '', content)
        
        result = json.loads(content)
        
        # التأكد من وجود كل الحقول
        if "title" not in result or not result["title"]:
            result["title"] = "المحاضرة التعليمية"
        if "summary" not in result or not result["summary"]:
            result["summary"] = "تم شرح المفاهيم الأساسية في هذه المحاضرة."
        if "key_points" not in result or not result["key_points"]:
            result["key_points"] = extracted_keywords[:4]
        
        # التأكد من وجود كلمات مفتاحية في كل قسم
        for i, section in enumerate(result.get("sections", [])):
            if "keywords" not in section or not section["keywords"]:
                # استخدام الكلمات المستخرجة
                start_idx = (i * 4) % len(extracted_keywords)
                section["keywords"] = []
                for j in range(4):
                    idx = (start_idx + j) % len(extracted_keywords)
                    if extracted_keywords[idx] not in section["keywords"]:
                        section["keywords"].append(extracted_keywords[idx])
            
            if "narration" not in section or not section["narration"]:
                section["narration"] = section.get("content", "شرح القسم")
            
            if "title" not in section or not section["title"]:
                section["title"] = f"القسم {i+1}"
        
        return result
        
    except Exception as e:
        print(f"Analysis error: {e}")
        
        # إنشاء بيانات افتراضية
        sections = []
        chunk_size = max(1, len(extracted_keywords) // num_sections)
        
        for i in range(num_sections):
            start_idx = (i * chunk_size) % len(extracted_keywords)
            kw = []
            for j in range(4):
                idx = (start_idx + j) % len(extracted_keywords)
                if extracted_keywords[idx] not in kw:
                    kw.append(extracted_keywords[idx])
            
            sections.append({
                "title": f"القسم {i+1}: {kw[0] if kw else 'مقدمة'}",
                "content": f"شرح مفصل عن {', '.join(kw[:2]) if kw else 'المفاهيم الأساسية'}",
                "keywords": kw if kw else ["مفهوم", "تعريف", "شرح", "تحليل"],
                "narration": f"في هذا القسم سنتعرف على {', '.join(kw[:3]) if kw else 'المفاهيم الأساسية'}. " * 3,
                "duration_estimate": 45
            })
        
        return {
            "lecture_type": "other",
            "title": "المحاضرة التعليمية",
            "sections": sections,
            "summary": "تم شرح المفاهيم الأساسية في هذه المحاضرة.",
            "key_points": extracted_keywords[:4] if extracted_keywords else ["نقطة1", "نقطة2", "نقطة3", "نقطة4"]
        }


async def extract_full_text_from_pdf(pdf_bytes: bytes) -> str:
    import PyPDF2
    reader = PyPDF2.PdfReader(io.BytesIO(pdf_bytes))
    pages = []
    for page in reader.pages:
        page_text = page.extract_text() or ""
        if page_text.strip():
            pages.append(page_text)
    return "\n\n".join(pages)


# ──────────────────────────────────────────────────────────────────────────────
# توليد الصور - مواقع متعددة للاحتياط
# ──────────────────────────────────────────────────────────────────────────────

async def _pollinations_generate(prompt: str) -> bytes | None:
    """الموقع الأول: Pollinations.ai"""
    import urllib.parse
    clean_prompt = prompt[:200].replace("\n", " ")
    encoded = urllib.parse.quote(clean_prompt)
    url = f"https://image.pollinations.ai/prompt/{encoded}?width=854&height=480&nologo=true&model=flux"

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
                        print(f"✅ Pollinations image generated")
                        return buf.getvalue()
    except Exception as e:
        print(f"Pollinations error: {e}")
    return None


async def _picsum_generate() -> bytes | None:
    """الموقع الاحتياطي: Lorem Picsum (صور عشوائية مجانية)"""
    try:
        url = f"https://picsum.photos/854/480?random={random.randint(1, 1000)}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    raw = await resp.read()
                    if len(raw) > 5000:
                        print(f"✅ Picsum fallback image used")
                        return raw
    except Exception as e:
        print(f"Picsum error: {e}")
    return None


def _make_placeholder_image(keyword: str, section_title: str = "") -> bytes:
    """صورة احتياطية مكتوب عليها الكلمة المفتاحية"""
    W, H = 854, 480
    # خلفية متدرجة
    img = PILImage.new("RGB", (W, H), (30, 40, 70))
    draw = ImageDraw.Draw(img)
    
    # تدرج لوني
    for y in range(H):
        t = y / H
        r = int(30 * (1 - t) + 60 * t)
        g = int(40 * (1 - t) + 80 * t)
        b = int(70 * (1 - t) + 120 * t)
        draw.line([(0, y), (W, y)], fill=(r, g, b))
    
    # إطار
    draw.rectangle([(20, 20), (W-20, H-20)], outline=(255, 200, 50), width=3)
    
    try:
        font_path = os.path.join(os.path.dirname(__file__), "fonts", "Amiri-Bold.ttf")
        if os.path.exists(font_path):
            font = ImageFont.truetype(font_path, 50)
            font_small = ImageFont.truetype(font_path, 24)
        else:
            font = ImageFont.load_default()
            font_small = font
    except Exception:
        font = ImageFont.load_default()
        font_small = font
    
    # إعادة تشكيل النص العربي
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
        keyword_disp = get_display(arabic_reshaper.reshape(keyword))
        section_disp = get_display(arabic_reshaper.reshape(section_title[:30]))
    except Exception:
        keyword_disp = keyword
        section_disp = section_title[:30]
    
    # رسم الكلمة المفتاحية
    try:
        bbox = draw.textbbox((0, 0), keyword_disp, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    except Exception:
        tw, th = len(keyword_disp) * 30, 50
    
    x = (W - tw) // 2
    y = (H - th) // 2 - 30
    
    # ظل
    draw.text((x+3, y+3), keyword_disp, fill=(0, 0, 0), font=font)
    draw.text((x, y), keyword_disp, fill=(255, 220, 50), font=font)
    
    # عنوان القسم
    if section_title:
        try:
            bbox = draw.textbbox((0, 0), section_disp, font=font_small)
            sw, sh = bbox[2] - bbox[0], bbox[3] - bbox[1]
        except Exception:
            sw, sh = len(section_disp) * 15, 24
        
        sx = (W - sw) // 2
        sy = y + th + 20
        draw.text((sx+2, sy+2), section_disp, fill=(0, 0, 0), font=font_small)
        draw.text((sx, sy), section_disp, fill=(200, 200, 220), font=font_small)
    
    # علامة مائية
    watermark = "@zakros_probot"
    try:
        bbox = draw.textbbox((0, 0), watermark, font=font_small)
        ww, wh = bbox[2] - bbox[0], bbox[3] - bbox[1]
    except Exception:
        ww, wh = len(watermark) * 10, 20
    
    wx = (W - ww) // 2
    wy = H - wh - 20
    draw.text((wx, wy), watermark, fill=(120, 130, 150), font=font_small)
    
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=90)
    return buf.getvalue()


async def fetch_image_for_keyword(
    keyword: str,
    section_title: str,
    lecture_type: str,
    image_search_en: str = "",
) -> bytes:
    """جلب صورة للكلمة المفتاحية - يجرب Pollinations ثم Picsum ثم صورة نصية"""
    
    # تحضير وصف الصورة
    subject = keyword.strip()
    
    # وصف بالعربي للصورة
    prompt_ar = f"رسم توضيحي تعليمي بسيط عن {subject}، خلفية فاتحة، أسلوب كرتوني نظيف"
    
    # وصف بالإنجليزي للصورة
    prompt_en = f"educational cartoon illustration about {subject}, simple clean style, light background"
    
    # 1. محاولة Pollinations مع وصف عربي
    try:
        img_bytes = await _pollinations_generate(prompt_ar)
        if img_bytes:
            return img_bytes
    except Exception:
        pass
    
    # 2. محاولة Pollinations مع وصف إنجليزي
    try:
        img_bytes = await _pollinations_generate(prompt_en)
        if img_bytes:
            return img_bytes
    except Exception:
        pass
    
    # 3. محاولة Picsum (صور عشوائية)
    try:
        img_bytes = await _picsum_generate()
        if img_bytes:
            return img_bytes
    except Exception:
        pass
    
    # 4. صورة احتياطية مكتوب عليها الكلمة المفتاحية
    return _make_placeholder_image(keyword, section_title)
