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
# Google API Key Pool - يدعم 9+ مفاتيح
# ──────────────────────────────────────────────────────────────────────────────

def _load_google_keys():
    """تحميل جميع مفاتيح Google من متغيرات البيئة"""
    keys = []
    
    # الطريقة 1: متغير واحد بفواصل GOOGLE_API_KEYS
    raw_keys = os.getenv("GOOGLE_API_KEYS", "")
    if raw_keys:
        keys.extend([k.strip() for k in raw_keys.split(",") if k.strip()])
    
    # الطريقة 2: متغيرات منفصلة GOOGLE_API_KEY_1 إلى GOOGLE_API_KEY_9
    for i in range(1, 10):
        key = os.getenv(f"GOOGLE_API_KEY_{i}", "")
        if key and key not in keys:
            keys.append(key.strip())
    
    # الطريقة 3: مفتاح واحد GOOGLE_API_KEY
    single_key = os.getenv("GOOGLE_API_KEY", "")
    if single_key and single_key not in keys:
        keys.append(single_key.strip())
    
    return keys

_google_keys = _load_google_keys()
_current_google_idx = 0
_exhausted_google_keys = set()

print(f"🔑 Loaded {len(_google_keys)} Google API key(s)")

def _get_next_google_key():
    """الحصول على المفتاح التالي غير المنتهي"""
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
    """تعليم مفتاح Google كمنتهي"""
    global _current_google_idx
    _exhausted_google_keys.add(key)
    _current_google_idx += 1
    remaining = len(_google_keys) - len(_exhausted_google_keys)
    print(f"⚠️ Google key exhausted. {remaining}/{len(_google_keys)} remaining")

# ──────────────────────────────────────────────────────────────────────────────
# Groq API Key Pool (احتياطي أول)
# ──────────────────────────────────────────────────────────────────────────────

def _load_groq_keys():
    keys = []
    raw_keys = os.getenv("GROQ_API_KEYS", "")
    if raw_keys:
        keys.extend([k.strip() for k in raw_keys.split(",") if k.strip()])
    for i in range(1, 10):
        key = os.getenv(f"GROQ_API_KEY_{i}", "")
        if key and key not in keys:
            keys.append(key.strip())
    single_key = os.getenv("GROQ_API_KEY", "")
    if single_key and single_key not in keys:
        keys.append(single_key.strip())
    return keys

_groq_keys = _load_groq_keys()
_current_groq_idx = 0
_exhausted_groq_keys = set()

print(f"🔑 Loaded {len(_groq_keys)} Groq API key(s)")

def _get_next_groq_key():
    global _current_groq_idx
    if not _groq_keys:
        return None
    for _ in range(len(_groq_keys)):
        key = _groq_keys[_current_groq_idx % len(_groq_keys)]
        if key not in _exhausted_groq_keys:
            return key
        _current_groq_idx += 1
    return None

def _mark_groq_exhausted(key: str):
    global _current_groq_idx
    _exhausted_groq_keys.add(key)
    _current_groq_idx += 1
    print(f"⚠️ Groq key exhausted")

# ──────────────────────────────────────────────────────────────────────────────
# OpenRouter API Key Pool (احتياطي ثاني)
# ──────────────────────────────────────────────────────────────────────────────

def _load_openrouter_keys():
    keys = []
    raw_keys = os.getenv("OPENROUTER_API_KEYS", "")
    if raw_keys:
        keys.extend([k.strip() for k in raw_keys.split(",") if k.strip()])
    for i in range(1, 10):
        key = os.getenv(f"OPENROUTER_API_KEY_{i}", "")
        if key and key not in keys:
            keys.append(key.strip())
    single_key = os.getenv("OPENROUTER_API_KEY", "")
    if single_key and single_key not in keys:
        keys.append(single_key.strip())
    return keys

_openrouter_keys = _load_openrouter_keys()
_current_or_idx = 0
_exhausted_or_keys = set()

print(f"🔑 Loaded {len(_openrouter_keys)} OpenRouter API key(s)")

# ──────────────────────────────────────────────────────────────────────────────
# نماذج Groq المجانية
# ──────────────────────────────────────────────────────────────────────────────
_GROQ_MODELS = [
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "gemma2-9b-it",
    "mixtral-8x7b-32768",
]

# نماذج OpenRouter المجانية
_OR_MODELS = [
    "google/gemini-2.0-flash-exp:free",
    "google/gemini-2.0-flash-lite-preview-02-05:free",
    "google/gemini-2.0-flash-thinking-exp:free",
    "nvidia/llama-3.1-nemotron-70b-instruct:free",
    "meta-llama/llama-3.2-3b-instruct:free",
]

# ──────────────────────────────────────────────────────────────────────────────
# دوال التوليد
# ──────────────────────────────────────────────────────────────────────────────

async def _generate_with_google(prompt: str, max_tokens: int = 8192) -> str:
    """محاولة التوليد باستخدام Google Gemini مع تدوير المفاتيح"""
    models = ["gemini-2.0-flash", "gemini-2.0-flash-lite"]
    
    while True:
        key = _get_next_google_key()
        if not key:
            raise Exception("All Google keys exhausted")
        
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
                print(f"✅ Google success: {model} with key {key[:15]}...")
                return response.text.strip()
            except Exception as e:
                err = str(e)
                if "429" in err or "RESOURCE_EXHAUSTED" in err or "quota" in err.lower():
                    print(f"⚠️ Google key {key[:15]}... quota exhausted")
                    _mark_google_exhausted(key)
                    break  # نجرب مفتاح آخر
                else:
                    print(f"⚠️ Google error: {err[:100]}")
                    continue  # نجرب نموذج آخر بنفس المفتاح
        
        # إذا وصلنا هنا، معناه كل النماذج فشلت بهذا المفتاح
        _mark_google_exhausted(key)


async def _generate_with_groq(prompt: str, max_tokens: int = 8192) -> str:
    """محاولة التوليد باستخدام Groq مع تدوير المفاتيح"""
    if not _groq_keys:
        raise Exception("No Groq keys configured")
    
    while True:
        key = _get_next_groq_key()
        if not key:
            raise Exception("All Groq keys exhausted")
        
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
                            text = data["choices"][0]["message"]["content"].strip()
                            print(f"✅ Groq success: {model}")
                            return text
                        elif resp.status == 429:
                            print(f"⚠️ Groq key {key[:15]}... rate limited")
                            _mark_groq_exhausted(key)
                            break
                        else:
                            body = await resp.text()
                            print(f"⚠️ Groq {resp.status}: {body[:80]}")
                            continue
            except Exception as e:
                print(f"⚠️ Groq error: {e!s:.80}")
                continue
        
        _mark_groq_exhausted(key)


async def _generate_with_openrouter(prompt: str, max_tokens: int = 8192) -> str:
    """محاولة التوليد باستخدام OpenRouter مع تدوير المفاتيح"""
    if not _openrouter_keys:
        raise Exception("No OpenRouter keys configured")
    
    for key in _openrouter_keys:
        for model in _OR_MODELS:
            try:
                headers = {
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://replit.com",
                    "X-Title": "Lecture Video Bot",
                }
                payload = {
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": min(max_tokens, 8192),
                    "temperature": 0.3,
                }
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        "https://openrouter.ai/api/v1/chat/completions",
                        headers=headers,
                        json=payload,
                        timeout=aiohttp.ClientTimeout(total=90),
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            content = data["choices"][0]["message"]["content"]
                            if content and content.strip():
                                print(f"✅ OpenRouter success: {model}")
                                return content.strip()
                        else:
                            body = await resp.text()
                            print(f"⚠️ OpenRouter {resp.status}: {body[:80]}")
                            continue
            except Exception as e:
                print(f"⚠️ OpenRouter error: {e!s:.80}")
                continue
    
    raise Exception("All OpenRouter attempts failed")


async def _generate_with_rotation(prompt: str, max_output_tokens: int = 8192) -> str:
    """
    نظام التدوير الكامل:
    1. Google Gemini (كل المفاتيح بالدور)
    2. Groq (إذا فشل Google)
    3. OpenRouter (إذا فشل Groq)
    """
    errors = []
    
    # 1. Google Gemini
    if _google_keys:
        try:
            return await _generate_with_google(prompt, max_output_tokens)
        except Exception as e:
            errors.append(f"Google: {e}")
            print("🔄 Google failed, switching to Groq...")
    
    # 2. Groq
    if _groq_keys:
        try:
            return await _generate_with_groq(prompt, max_output_tokens)
        except Exception as e:
            errors.append(f"Groq: {e}")
            print("🔄 Groq failed, switching to OpenRouter...")
    
    # 3. OpenRouter
    if _openrouter_keys:
        try:
            return await _generate_with_openrouter(prompt, max_output_tokens)
        except Exception as e:
            errors.append(f"OpenRouter: {e}")
    
    raise Exception(f"All AI services failed: {' | '.join(errors)}")


# ──────────────────────────────────────────────────────────────────────────────
# تحليل المحاضرة
# ──────────────────────────────────────────────────────────────────────────────

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

    content = await _generate_with_rotation(prompt, max_output_tokens=8192)
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
        raise ValueError(f"Failed to parse response as JSON: {content[:500]}")


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
# توليد الصور (Pollinations.ai مجاني)
# ──────────────────────────────────────────────────────────────────────────────

async def _pollinations_generate(prompt: str) -> bytes | None:
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
    W, H = 854, 480
    img = PILImage.new("RGB", (W, H), (30, 30, 80))
    draw = ImageDraw.Draw(img)

    keyword = keywords[0] if keywords else "Educational"

    try:
        font_path = os.path.join(os.path.dirname(__file__), "fonts", "Amiri-Bold.ttf")
        font = ImageFont.truetype(font_path, 60)
    except Exception:
        font = ImageFont.load_default()

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
    subject = (image_search_en or keyword).strip()
    prompt = f"educational cartoon illustration, {subject}, simple clean style, white background, no text"

    try:
        img_bytes = await _pollinations_generate(prompt)
        if img_bytes:
            return img_bytes
    except Exception as e:
        print(f"Pollinations failed for '{subject}': {e}")

    return _make_placeholder_image([keyword, section_title], lecture_type)
