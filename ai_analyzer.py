import json
import re
import io
import asyncio
import aiohttp
from PIL import Image as PILImage
from google import genai
from google.genai import types as genai_types
from config import (
    DEEPSEEK_API_KEYS, GOOGLE_API_KEYS, GROQ_API_KEYS, 
    OPENROUTER_API_KEYS, STABILITY_API_KEYS, REPLICATE_API_TOKEN
)

# ══════════════════════════════════════════════════════════════════════════════
# 🔑 KEY POOLS & ROTATION — لكل خدمة مؤشر خاص
# ══════════════════════════════════════════════════════════════════════════════

# DeepSeek
_deepseek_pool = list(DEEPSEEK_API_KEYS)
_deepseek_idx = 0
_deepseek_exhausted = set()

# Gemini
_gemini_pool = list(GOOGLE_API_KEYS)
_gemini_idx = 0
_gemini_exhausted = set()
_gemini_clients = {}

# Groq
_groq_pool = list(GROQ_API_KEYS)
_groq_idx = 0
_groq_exhausted = set()

# OpenRouter
_or_pool = list(OPENROUTER_API_KEYS)
_or_idx = 0
_or_exhausted = set()

# Stability AI (للصور)
_stability_pool = list(STABILITY_API_KEYS)
_stability_idx = 0
_stability_exhausted = set()


class QuotaExhaustedError(Exception):
    """تستخدم عندما تنفد كل المفاتيح من جميع الخدمات"""
    pass


# ══════════════════════════════════════════════════════════════════════════════
# 1️⃣ DEEPSEEK — الواجهة الأولى
# ══════════════════════════════════════════════════════════════════════════════

DEEPSEEK_MODELS = ["deepseek-chat", "deepseek-reasoner"]

async def _generate_with_deepseek(prompt: str, max_tokens: int = 8192) -> str:
    """استدعاء DeepSeek API (OpenAI-compatible)"""
    global _deepseek_idx, _deepseek_exhausted
    
    if not _deepseek_pool:
        raise QuotaExhaustedError("No DeepSeek keys configured")
    
    # تدوير المفاتيح
    for _ in range(len(_deepseek_pool)):
        key_idx = _deepseek_idx % len(_deepseek_pool)
        key = _deepseek_pool[key_idx]
        _deepseek_idx += 1
        
        if key in _deepseek_exhausted:
            continue
            
        for model in DEEPSEEK_MODELS:
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
                        "https://api.deepseek.com/v1/chat/completions",
                        headers=headers,
                        json=payload,
                        timeout=aiohttp.ClientTimeout(total=90),
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            text = data["choices"][0]["message"]["content"].strip()
                            print(f"✅ DeepSeek success: {model}")
                            return text
                        elif resp.status in (429, 402, 403):
                            body = await resp.text()
                            if "quota" in body.lower() or "insufficient" in body.lower():
                                print(f"⚠️ DeepSeek key exhausted: {key[:12]}...")
                                _deepseek_exhausted.add(key)
                                break  # جرب المفتاح التالي
                            continue
                        else:
                            body = await resp.text()
                            print(f"⚠️ DeepSeek {model} {resp.status}: {body[:80]}")
                            continue
            except Exception as e:
                print(f"⚠️ DeepSeek {model} error: {e!s:.80}")
                continue
                
    raise QuotaExhaustedError("All DeepSeek keys exhausted")


# ══════════════════════════════════════════════════════════════════════════════
# 2️⃣ GEMINI — الواجهة الثانية
# ══════════════════════════════════════════════════════════════════════════════

def _get_gemini_client(key: str):
    if key not in _gemini_clients:
        _gemini_clients[key] = genai.Client(api_key=key)
    return _gemini_clients[key]


async def _generate_with_gemini(prompt: str, max_tokens: int = 8192) -> str:
    """استدعاء Gemini API مع تدوير المفاتيح"""
    global _gemini_idx, _gemini_exhausted
    
    if not _gemini_pool:
        raise QuotaExhaustedError("No Gemini keys configured")
    
    gemini_models = ["gemini-2.0-flash", "gemini-2.0-flash-lite", "gemini-1.5-flash"]
    
    for _ in range(len(_gemini_pool)):
        key_idx = _gemini_idx % len(_gemini_pool)
        key = _gemini_pool[key_idx]
        _gemini_idx += 1
        
        if key in _gemini_exhausted:
            continue
            
        client = _get_gemini_client(key)
        
        for model in gemini_models:
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
                print(f"✅ Gemini success: {model}")
                return response.text.strip()
            except Exception as e:
                err = str(e)
                if "quota" in err.lower() or "exhausted" in err.lower() or "429" in err:
                    print(f"⚠️ Gemini key exhausted: {key[:12]}...")
                    _gemini_exhausted.add(key)
                    break
                print(f"⚠️ Gemini {model} error: {err[:80]}")
                continue
                
    raise QuotaExhaustedError("All Gemini keys exhausted")


# ══════════════════════════════════════════════════════════════════════════════
# 3️⃣ GROQ — الواجهة الثالثة
# ══════════════════════════════════════════════════════════════════════════════

GROQ_MODELS = ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "gemma2-9b-it", "mixtral-8x7b-32768"]

async def _generate_with_groq(prompt: str, max_tokens: int = 8192) -> str:
    """استدعاء Groq API مع تدوير المفاتيح"""
    global _groq_idx, _groq_exhausted
    
    if not _groq_pool:
        raise QuotaExhaustedError("No Groq keys configured")
    
    for _ in range(len(_groq_pool)):
        key_idx = _groq_idx % len(_groq_pool)
        key = _groq_pool[key_idx]
        _groq_idx += 1
        
        if key in _groq_exhausted:
            continue
            
        for model in GROQ_MODELS:
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
                        timeout=aiohttp.ClientTimeout(total=90),
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            text = data["choices"][0]["message"]["content"].strip()
                            print(f"✅ Groq success: {model}")
                            return text
                        elif resp.status in (429, 403):
                            body = await resp.text()
                            if "quota" in body.lower() or "limit" in body.lower():
                                print(f"⚠️ Groq key exhausted: {key[:12]}...")
                                _groq_exhausted.add(key)
                                break
                            continue
                        else:
                            body = await resp.text()
                            print(f"⚠️ Groq {model} {resp.status}: {body[:80]}")
                            continue
            except Exception as e:
                print(f"⚠️ Groq {model} error: {e!s:.80}")
                continue
                
    raise QuotaExhaustedError("All Groq keys exhausted")


# ══════════════════════════════════════════════════════════════════════════════
# 4️⃣ OPENROUTER — الواجهة الرابعة (نماذج مجانية)
# ══════════════════════════════════════════════════════════════════════════════

OR_MODELS = [
    "deepseek/deepseek-chat:free",
    "google/gemini-2.0-flash-exp:free",
    "meta-llama/llama-3.3-70b-instruct:free",
    "qwen/qwen2.5-72b-instruct:free",
    "mistralai/mistral-7b-instruct:free",
]

async def _generate_with_openrouter(prompt: str, max_tokens: int = 8192) -> str:
    """استدعاء OpenRouter مع تدوير المفاتيح"""
    global _or_idx, _or_exhausted
    
    if not _or_pool:
        raise QuotaExhaustedError("No OpenRouter keys configured")
    
    for _ in range(len(_or_pool)):
        key_idx = _or_idx % len(_or_pool)
        key = _or_pool[key_idx]
        _or_idx += 1
        
        if key in _or_exhausted:
            continue
            
        for model in OR_MODELS:
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
                        timeout=aiohttp.ClientTimeout(total=120),
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            content = data["choices"][0]["message"]["content"]
                            if content and content.strip():
                                print(f"✅ OpenRouter success: {model}")
                                return content.strip()
                        elif resp.status in (429, 402, 403):
                            body = await resp.text()
                            if "quota" in body.lower() or "credits" in body.lower():
                                print(f"⚠️ OpenRouter key exhausted: {key[:12]}...")
                                _or_exhausted.add(key)
                                break
                            continue
                        else:
                            body = await resp.text()
                            print(f"⚠️ OpenRouter {model} {resp.status}: {body[:100]}")
                            continue
            except Exception as e:
                print(f"⚠️ OpenRouter {model} error: {e!s:.80}")
                continue
                
    raise QuotaExhaustedError("All OpenRouter keys exhausted")


# ══════════════════════════════════════════════════════════════════════════════
# 🔄 دالة التوليد الرئيسية — تجرب كل الخدمات بالترتيب
# ══════════════════════════════════════════════════════════════════════════════

async def _generate_with_rotation(prompt: str, max_tokens: int = 8192) -> str:
    """
    تجرب الخدمات بالترتيب:
    1. DeepSeek (مع تدوير 9 مفاتيح)
    2. Gemini (مع تدوير 9 مفاتيح)
    3. Groq (مع تدوير 9 مفاتيح)
    4. OpenRouter (مع تدوير 9 مفاتيح + نماذج مجانية)
    """
    errors = []
    
    # 1️⃣ DeepSeek
    if _deepseek_pool:
        try:
            return await _generate_with_deepseek(prompt, max_tokens)
        except QuotaExhaustedError as e:
            errors.append(f"DeepSeek: {e}")
            print("🔄 DeepSeek exhausted — switching to Gemini...")
    
    # 2️⃣ Gemini
    if _gemini_pool:
        try:
            return await _generate_with_gemini(prompt, max_tokens)
        except QuotaExhaustedError as e:
            errors.append(f"Gemini: {e}")
            print("🔄 Gemini exhausted — switching to Groq...")
    
    # 3️⃣ Groq
    if _groq_pool:
        try:
            return await _generate_with_groq(prompt, max_tokens)
        except QuotaExhaustedError as e:
            errors.append(f"Groq: {e}")
            print("🔄 Groq exhausted — switching to OpenRouter...")
    
    # 4️⃣ OpenRouter
    if _or_pool:
        try:
            return await _generate_with_openrouter(prompt, max_tokens)
        except QuotaExhaustedError as e:
            errors.append(f"OpenRouter: {e}")
    
    # كل شيء فشل
    raise QuotaExhaustedError(f"All services exhausted: {' | '.join(errors)}")


# ══════════════════════════════════════════════════════════════════════════════
# 📊 تحليل المحاضرة
# ══════════════════════════════════════════════════════════════════════════════

def _compute_lecture_scale(text: str) -> tuple:
    """تحديد عدد الأقسام بناءً على طول النص"""
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
        return 7, "15-18", 8192


async def analyze_lecture(text: str, dialect: str = "msa") -> dict:
    """تحليل المحاضرة واستخراج الأقسام والكلمات المفتاحية"""
    
    dialect_instructions = {
        "iraq": "استخدم اللهجة العراقية في الشرح، مع كلمات عراقية أصيلة مثل (هواية، گلت، يعني، بس، هسا، چي، شلون، وين، أكو، ماكو)",
        "egypt": "استخدم اللهجة المصرية في الشرح، مع كلمات مصرية مثل (أوي، معلش، إيه، مش، كده، بتاع، عايز، فين، ازيك، أهو)",
        "syria": "استخدم اللهجة الشامية في الشرح، مع كلمات شامية مثل (هلق، شو، كتير، منيح، هيك، لهلق، قديش، عم، هون، كيفك)",
        "gulf": "استخدم اللهجة الخليجية في الشرح، مع كلمات خليجية مثل (زين، وايد، عاد، هاذي، أبشر، شفيك، ليش، كيفك، إيه)",
        "msa": "استخدم العربية الفصحى الواضحة والمبسطة",
        "english": "Use clear, simple English. Explain like a teacher to students.",
        "british": "Use British English with a professional, clear academic tone."
    }

    instruction = dialect_instructions.get(dialect, dialect_instructions["msa"])
    num_sections, narration_sentences, _ = _compute_lecture_scale(text)
    text_limit = min(len(text), 5000 + num_sections * 2000)

    is_english = dialect in ("english", "british")

    if is_english:
        summary_hint = "A clear, concise summary of the lecture in English (4-5 sentences)"
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

    prompt = f"""أنت معلم خبير ومتخصص في تبسيط المحاضرات العلمية. مهمتك تحليل هذه المحاضرة وإنتاج محتوى تعليمي احترافي.

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
        "simple cartoon visual for keyword1 — 3-5 English words",
        "simple cartoon visual for keyword2 — 3-5 English words",
        "simple cartoon visual for keyword3 — 3-5 English words",
        "simple cartoon visual for keyword4 — 3-5 English words"
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
- يجب أن تكون {num_sections} أقسام بالضبط لا أكثر ولا أقل
- اجعل الشرح (narration) طبيعياً وطويلاً كأن معلم خبير يشرح أمام الطلاب مباشرة
- كل قسم يجب أن يكون شرحاً وافياً ({narration_sentences} جمل)
- keywords: 4 مصطلحات أساسية تمثل أجزاء الشرح
- keyword_images: وصف إنجليزي لصورة كرتونية بسيطة لكل كلمة مفتاحية (3-5 كلمات)
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


# ══════════════════════════════════════════════════════════════════════════════
# 📄 استخراج النص من PDF
# ══════════════════════════════════════════════════════════════════════════════

async def extract_full_text_from_pdf(pdf_bytes: bytes) -> str:
    """استخراج النص الكامل من PDF"""
    import PyPDF2

    reader = PyPDF2.PdfReader(io.BytesIO(pdf_bytes))
    pages = []
    for page in reader.pages:
        page_text = page.extract_text() or ""
        if page_text.strip():
            pages.append(page_text)
    return "\n\n".join(pages)


# ══════════════════════════════════════════════════════════════════════════════
# 🖼️ توليد الصور — طرق متعددة مجانية
# ══════════════════════════════════════════════════════════════════════════════

async def _pollinations_generate(prompt: str) -> bytes | None:
    """Pollinations.ai — مجاني بالكامل"""
    import urllib.parse
    import random
    
    clean_prompt = prompt[:380].replace("\n", " ")
    seed = random.randint(1, 99999)
    encoded = urllib.parse.quote(clean_prompt)
    url = f"https://image.pollinations.ai/prompt/{encoded}?width=854&height=480&nologo=true&seed={seed}"
    
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
                        print(f"✅ Pollinations image OK")
                        return buf.getvalue()
    except Exception as e:
        print(f"⚠️ Pollinations error: {e}")
    return None


async def _stability_generate(prompt: str) -> bytes | None:
    """Stability AI — جودة عالية مع تدوير مفاتيح"""
    global _stability_idx, _stability_exhausted
    
    if not _stability_pool:
        return None
        
    for _ in range(len(_stability_pool)):
        key_idx = _stability_idx % len(_stability_pool)
        key = _stability_pool[key_idx]
        _stability_idx += 1
        
        if key in _stability_exhausted:
            continue
            
        try:
            headers = {
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            }
            payload = {
                "text_prompts": [{"text": f"educational cartoon illustration, {prompt}"}],
                "cfg_scale": 7,
                "height": 512,
                "width": 896,
                "samples": 1,
                "steps": 30,
            }
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://api.stability.ai/v1/generation/stable-diffusion-xl-1024-v1-0/text-to-image",
                    headers=headers,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        import base64
                        b64 = data["artifacts"][0]["base64"]
                        raw = base64.b64decode(b64)
                        pil_img = PILImage.open(io.BytesIO(raw)).convert("RGB")
                        pil_img = pil_img.resize((854, 480), PILImage.LANCZOS)
                        buf = io.BytesIO()
                        pil_img.save(buf, "JPEG", quality=90)
                        print(f"✅ Stability AI image OK")
                        return buf.getvalue()
                    elif resp.status in (429, 403, 401):
                        print(f"⚠️ Stability key exhausted: {key[:12]}...")
                        _stability_exhausted.add(key)
                        continue
        except Exception as e:
            print(f"⚠️ Stability error: {e}")
            continue
    return None


async def _replicate_generate(prompt: str) -> bytes | None:
    """Replicate — Flux model (جودة خرافية)"""
    if not REPLICATE_API_TOKEN:
        return None
        
    try:
        headers = {
            "Authorization": f"Token {REPLICATE_API_TOKEN}",
            "Content-Type": "application/json",
        }
        payload = {
            "version": "black-forest-labs/flux-schnell",
            "input": {
                "prompt": f"educational cartoon illustration, clean style, {prompt}",
                "width": 896,
                "height": 512,
                "num_outputs": 1,
            }
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.replicate.com/v1/predictions",
                headers=headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=60),
            ) as resp:
                if resp.status == 201:
                    data = await resp.json()
                    pred_id = data["id"]
                    
                    # انتظار النتيجة
                    for _ in range(20):
                        await asyncio.sleep(3)
                        async with session.get(
                            f"https://api.replicate.com/v1/predictions/{pred_id}",
                            headers=headers,
                        ) as check:
                            if check.status == 200:
                                result = await check.json()
                                if result["status"] == "succeeded":
                                    img_url = result["output"][0]
                                    async with session.get(img_url) as img_resp:
                                        if img_resp.status == 200:
                                            raw = await img_resp.read()
                                            pil_img = PILImage.open(io.BytesIO(raw)).convert("RGB")
                                            pil_img = pil_img.resize((854, 480), PILImage.LANCZOS)
                                            buf = io.BytesIO()
                                            pil_img.save(buf, "JPEG", quality=90)
                                            print(f"✅ Replicate Flux image OK")
                                            return buf.getvalue()
                                elif result["status"] == "failed":
                                    break
    except Exception as e:
        print(f"⚠️ Replicate error: {e}")
    return None


def _make_placeholder_image(keywords: list, lecture_type: str = "other") -> bytes:
    """صورة احتياطية احترافية"""
    from PIL import ImageDraw, ImageFont
    import os

    PALETTES = {
        "medicine": ((20, 78, 140), (6, 147, 227), (255, 200, 0)),
        "science": ((11, 110, 79), (28, 200, 135), (255, 220, 50)),
        "math": ((58, 12, 163), (100, 60, 220), (255, 180, 0)),
        "history": ((150, 60, 10), (220, 110, 40), (255, 230, 100)),
        "computer": ((0, 80, 120), (0, 160, 200), (255, 200, 50)),
        "business": ((0, 80, 40), (0, 160, 80), (255, 220, 0)),
        "other": ((30, 30, 80), (70, 60, 160), (255, 200, 50)),
    }
    bg1, bg2, accent = PALETTES.get(lecture_type, PALETTES["other"])

    W, H = 854, 480
    img = PILImage.new("RGB", (W, H), bg1)
    draw = ImageDraw.Draw(img)

    for x in range(W):
        t = x / W
        r = int(bg1[0] * (1 - t) + bg2[0] * t)
        g = int(bg1[1] * (1 - t) + bg2[1] * t)
        b = int(bg1[2] * (1 - t) + bg2[2] * t)
        draw.line([(x, 0), (x, H)], fill=(r, g, b))

    keyword = (keywords[0] if keywords else "").strip()
    
    try:
        font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        font = ImageFont.truetype(font_path, 48)
    except:
        font = ImageFont.load_default()

    # ظل
    draw.text((W//2 + 3, H//2 + 3), keyword, fill=(0, 0, 0, 100), font=font, anchor="mm")
    # نص رئيسي
    draw.text((W//2, H//2), keyword, fill=(255, 255, 255), font=font, anchor="mm")
    
    # خط تحت الكلمة
    draw.rectangle([W//2 - 150, H//2 + 50, W//2 + 150, H//2 + 56], fill=accent)

    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=92)
    return buf.getvalue()


async def fetch_image_for_keyword(
    keyword: str,
    section_title: str,
    lecture_type: str,
    image_search_en: str = "",
) -> bytes:
    """جلب صورة للكلمة المفتاحية — تجربة عدة طرق مجانية"""
    
    prompt = image_search_en or keyword
    full_prompt = f"educational cartoon illustration, simple clean style, {prompt}, {lecture_type}"
    
    # 1. Pollinations (مجاني)
    img = await _pollinations_generate(full_prompt)
    if img:
        return img
        
    # 2. Stability AI (إذا وجدت مفاتيح)
    img = await _stability_generate(full_prompt)
    if img:
        return img
        
    # 3. Replicate Flux (جودة عالية)
    img = await _replicate_generate(full_prompt)
    if img:
        return img
        
    # 4. صورة احتياطية
    return _make_placeholder_image([keyword, section_title], lecture_type)


# ══════════════════════════════════════════════════════════════════════════════
# 🎨 توليد صورة تعليمية (متوافقة مع الواجهة القديمة)
# ══════════════════════════════════════════════════════════════════════════════

async def generate_educational_image(
    prompt: str,
    lecture_type: str,
    keywords: list = None,
    image_search: str = None,
    image_search_fallbacks: list = None,
) -> bytes:
    """توليد صورة تعليمية"""
    kws = (keywords or [])[:4]
    subject = (image_search or (kws[0] if kws else prompt[:40])).strip()
    return await fetch_image_for_keyword(subject, "", lecture_type, subject)
