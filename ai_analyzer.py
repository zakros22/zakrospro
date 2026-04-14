import json
import re
import io
import asyncio
import aiohttp
from PIL import Image as PILImage
from google import genai
from google.genai import types as genai_types
from config import (
    DEEPSEEK_API_KEYS, GEMINI_API_KEYS, OPENROUTER_API_KEYS, GROQ_API_KEYS, OPENAI_API_KEY
)

# =============================================================================
# نظام تبادل المفاتيح المتقدم
# الأولوية: DeepSeek → Gemini → OpenRouter → Groq
# =============================================================================

class QuotaExhaustedError(Exception):
    """يُرفع عندما تنفد جميع المفاتيح من جميع المزودين."""
    pass

# --- DeepSeek (OpenAI-compatible) ---
async def _generate_with_deepseek(prompt: str, max_tokens: int = 8192) -> str:
    """محاولة التوليد باستخدام مفاتيح DeepSeek بالتناوب."""
    if not DEEPSEEK_API_KEYS:
        raise QuotaExhaustedError("لا توجد مفاتيح DeepSeek")

    models = ["deepseek-chat", "deepseek-reasoner"]
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
                            print(f"✅ DeepSeek نجاح: {model}")
                            return text
                        elif resp.status == 402:  # رصيد غير كافي
                            print(f"⚠️ DeepSeek رصيد منتهي للمفتاح {key[:10]}...")
                            break  # جرب المفتاح التالي
                        else:
                            body = await resp.text()
                            print(f"⚠️ DeepSeek {resp.status}: {body[:100]}")
                            continue
            except Exception as e:
                print(f"⚠️ DeepSeek خطأ: {str(e)[:80]}")
                continue
    raise QuotaExhaustedError("جميع مفاتيح DeepSeek منتهية أو فشلت")


# --- Gemini (Google) ---
_gemini_clients: dict[str, object] = {}
_gemini_idx = 0

def _get_gemini_client(key: str | None = None):
    global _gemini_idx
    if not GEMINI_API_KEYS:
        return None
    use_key = key or GEMINI_API_KEYS[_gemini_idx % len(GEMINI_API_KEYS)]
    if use_key not in _gemini_clients:
        _gemini_clients[use_key] = genai.Client(api_key=use_key)
    return _gemini_clients[use_key]

async def _generate_with_gemini(prompt: str, max_tokens: int = 8192) -> str:
    """محاولة التوليد باستخدام مفاتيح Gemini بالتناوب."""
    global _gemini_idx
    if not GEMINI_API_KEYS:
        raise QuotaExhaustedError("لا توجد مفاتيح Gemini")

    models = ["gemini-2.0-flash", "gemini-2.0-flash-lite", "gemini-1.5-flash"]
    for i in range(len(GEMINI_API_KEYS)):
        key_idx = (_gemini_idx + i) % len(GEMINI_API_KEYS)
        key = GEMINI_API_KEYS[key_idx]
        client = _get_gemini_client(key)
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
                _gemini_idx = key_idx
                print(f"✅ Gemini نجاح: {model}")
                return response.text.strip()
            except Exception as e:
                err = str(e)
                if "quota" in err.lower() or "exhausted" in err.lower() or "429" in err:
                    print(f"⚠️ Gemini حصة منتهية للمفتاح {key[:10]}...")
                    break  # جرب المفتاح التالي
                else:
                    print(f"⚠️ Gemini خطأ: {err[:80]}")
                    continue
    raise QuotaExhaustedError("جميع مفاتيح Gemini منتهية")


# --- OpenRouter ---
async def _generate_with_openrouter(prompt: str, max_tokens: int = 8192) -> str:
    """محاولة التوليد باستخدام مفاتيح OpenRouter (نموذج DeepSeek المجاني)."""
    if not OPENROUTER_API_KEYS:
        raise QuotaExhaustedError("لا توجد مفاتيح OpenRouter")

    # نستخدم نموذج DeepSeek المجاني على OpenRouter
    models = [
        "deepseek/deepseek-r1:free",
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
                                print(f"✅ OpenRouter نجاح: {model}")
                                return content.strip()
                        elif resp.status == 402:
                            print(f"⚠️ OpenRouter رصيد منتهي للمفتاح {key[:10]}...")
                            break
                        else:
                            continue
            except Exception as e:
                print(f"⚠️ OpenRouter خطأ: {str(e)[:80]}")
                continue
    raise QuotaExhaustedError("جميع مفاتيح OpenRouter منتهية")


# --- Groq (احتياطي أخير) ---
async def _generate_with_groq(prompt: str, max_tokens: int = 8192) -> str:
    """محاولة التوليد باستخدام مفاتيح Groq."""
    if not GROQ_API_KEYS:
        raise QuotaExhaustedError("لا توجد مفاتيح Groq")

    models = ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "gemma2-9b-it"]
    for key in GROQ_API_KEYS:
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
                            print(f"✅ Groq نجاح: {model}")
                            return text
                        elif resp.status == 429:
                            print(f"⚠️ Groq حد الطلبات للمفتاح {key[:10]}...")
                            continue
                        else:
                            continue
            except Exception as e:
                print(f"⚠️ Groq خطأ: {str(e)[:80]}")
                continue
    raise QuotaExhaustedError("جميع مفاتيح Groq منتهية")


# =============================================================================
# الوظيفة الرئيسية للتوليد (تدوير تلقائي بين المزودين)
# =============================================================================
async def _generate_with_rotation(prompt: str, max_output_tokens: int = 8192) -> str:
    """
    تدوير تلقائي بين المزودين حسب الأولوية:
    1. DeepSeek (الأفضل والأسرع)
    2. Gemini (Google)
    3. OpenRouter (نماذج مجانية)
    4. Groq (احتياطي أخير)
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

    raise QuotaExhaustedError(f"جميع المزودين منتهين: {' | '.join(errors)}")


# =============================================================================
# تحليل المحاضرة (نفس الوظيفة الأصلية مع تعديل استدعاء _generate_with_rotation)
# =============================================================================
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
        narration_hint = f"Full narration in English as a teacher explaining to students ({narration_sentences} sentences)"
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
        "وصف إنجليزي قصير 3-5 كلمات لصورة كرتونية للكلمة الأولى",
        "وصف للكلمة الثانية",
        "وصف للكلمة الثالثة",
        "وصف للكلمة الرابعة"
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
        return json.loads(content)
    except json.JSONDecodeError:
        json_match = re.search(r'\{[\s\S]*\}', content)
        if json_match:
            return json.loads(json_match.group())
        raise ValueError(f"Failed to parse response as JSON: {content[:500]}")


# =============================================================================
# باقي الوظائف (استخراج النص من PDF، ترجمة، توليد الصور) - كما هي بدون تغيير
# =============================================================================

async def extract_full_text_from_pdf(pdf_bytes: bytes) -> str:
    import PyPDF2
    reader = PyPDF2.PdfReader(io.BytesIO(pdf_bytes))
    pages = []
    for page in reader.pages:
        page_text = page.extract_text() or ""
        if page_text.strip():
            pages.append(page_text)
    return "\n\n".join(pages)


async def translate_full_text(text: str, dialect: str) -> str:
    dialect_instructions = {
        "iraq": "ترجم النص إلى اللهجة العراقية.",
        "egypt": "ترجم النص إلى اللهجة المصرية.",
        "syria": "ترجم النص إلى اللهجة الشامية السورية.",
        "gulf": "ترجم النص إلى اللهجة الخليجية.",
        "msa": "حوّل النص إلى العربية الفصحى السليمة.",
    }
    instruction = dialect_instructions.get(dialect, dialect_instructions["msa"])
    prompt = f"{instruction}\n\nالنص:\n---\n{text[:12000]}\n---\n\nقدّم الترجمة فقط."
    return await _generate_with_rotation(prompt)


def _make_placeholder_image(keywords: list, lecture_type: str = "other") -> bytes:
    # (نفس الكود الأصلي - لم يتم تغييره)
    from PIL import ImageDraw, ImageFont
    import os

    PALETTES = {
        "medicine": ((20, 78, 140), (6, 147, 227), (255, 200, 0)),
        "science": ((11, 110, 79), (28, 200, 135), (255, 220, 50)),
        "math": ((58, 12, 163), (100, 60, 220), (255, 180, 0)),
        "history": ((150, 60, 10), (220, 110, 40), (255, 230, 100)),
    }
    bg1, bg2, accent = PALETTES.get(lecture_type, ((30, 30, 80), (70, 60, 160), (255, 200, 50)))

    W, H = 854, 480
    img = PILImage.new("RGB", (W, H), bg1)
    draw = ImageDraw.Draw(img)

    for x in range(W):
        t = x / W
        r = int(bg1[0] * (1 - t) + bg2[0] * t)
        g = int(bg1[1] * (1 - t) + bg2[1] * t)
        b = int(bg1[2] * (1 - t) + bg2[2] * t)
        draw.line([(x, 0), (x, H)], fill=(r, g, b))

    keyword_raw = (keywords[0] if keywords else "").strip()
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 60)
    except:
        font = ImageFont.load_default()

    bbox = draw.textbbox((0, 0), keyword_raw, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(((W - tw) // 2, (H - th) // 2), keyword_raw, fill=(255, 255, 255), font=font)

    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=85)
    return buf.getvalue()


async def _pollinations_generate(prompt: str, lecture_type: str = "other") -> bytes | None:
    import urllib.parse, random
    model = "flux-anime"
    clean_prompt = prompt[:380].replace("\n", " ")
    seed = random.randint(1, 99999)
    encoded = urllib.parse.quote(clean_prompt)
    url = f"https://image.pollinations.ai/prompt/{encoded}?width=854&height=480&nologo=true&seed={seed}&model={model}"
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


async def _dalle_generate(prompt: str) -> bytes | None:
    import base64
    if not OPENAI_API_KEY:
        return None
    payload = {
        "model": "dall-e-3",
        "prompt": prompt,
        "size": "1024x1024",
        "quality": "standard",
        "n": 1,
        "response_format": "b64_json",
    }
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {OPENAI_API_KEY}"}
    try:
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.post(
                "https://api.openai.com/v1/images/generations",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=40),
            ) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                imgs = data.get("data", [])
                if not imgs:
                    return None
                b64 = imgs[0].get("b64_json", "")
                raw = base64.b64decode(b64)
                pil_img = PILImage.open(io.BytesIO(raw)).convert("RGB")
                pil_img = pil_img.resize((854, 480), PILImage.LANCZOS)
                buf = io.BytesIO()
                pil_img.save(buf, "JPEG", quality=92)
                return buf.getvalue()
    except Exception as e:
        print(f"DALL-E error: {e}")
        return None


def _build_dalle_prompt(subject: str, lecture_type: str) -> str:
    style = {
        "medicine": "medical anatomy sketch, thin pink outline drawing",
        "science": "science diagram sketch, thin line drawing",
    }.get(lecture_type, "educational sketch, simple line drawing")
    return f"{style}, {subject}, Osmosis.org style, hand-drawn pencil sketch, pure white background, no text"


async def fetch_image_for_keyword(
    keyword: str,
    section_title: str,
    lecture_type: str,
    image_search_en: str = "",
) -> bytes:
    subject = (image_search_en or keyword).strip()
    pol_prompt = _build_dalle_prompt(subject, lecture_type)

    # 1. Pollinations (مجاني وسريع)
    try:
        img_bytes = await asyncio.wait_for(_pollinations_generate(pol_prompt, lecture_type), timeout=15.0)
        if img_bytes:
            return img_bytes
    except:
        pass

    # 2. DALL-E (إذا كان المفتاح موجوداً)
    if OPENAI_API_KEY:
        try:
            img_bytes = await asyncio.wait_for(_dalle_generate(pol_prompt), timeout=30.0)
            if img_bytes:
                return img_bytes
        except:
            pass

    # 3. صورة احتياطية
    return _make_placeholder_image([keyword, section_title], lecture_type)
