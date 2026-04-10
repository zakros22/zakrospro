import json
import re
import io
import asyncio
import aiohttp
from PIL import Image as PILImage
from google import genai
from google.genai import types as genai_types
from config import GOOGLE_API_KEY, GOOGLE_API_KEYS, GROQ_API_KEYS, OPENROUTER_API_KEYS, OPENAI_API_KEY

# ── Google API key pool ────────────────────────────────────────────────────────
_key_pool: list[str] = list(GOOGLE_API_KEYS) if GOOGLE_API_KEYS else (
    [GOOGLE_API_KEY] if GOOGLE_API_KEY else []
)

# ── Groq key pool (free fallback) ─────────────────────────────────────────────
_groq_pool: list[str] = list(GROQ_API_KEYS)
_key_clients: dict[str, object] = {}
_current_key_idx: int = 0


def _get_client(key: str | None = None):
    """Return a genai Client for the given key (or the current pool key)."""
    if not _key_pool:
        raise RuntimeError(
            "GOOGLE_API_KEY غير مضبوط. احصل على مفتاح مجاني من https://aistudio.google.com/"
        )
    use_key = key or _key_pool[_current_key_idx % len(_key_pool)]
    if use_key not in _key_clients:
        _key_clients[use_key] = genai.Client(api_key=use_key)
    return _key_clients[use_key]


class QuotaExhaustedError(Exception):
    pass


# ── Groq fallback (free, fast, generous limits) ───────────────────────────────
_GROQ_MODELS = [
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "gemma2-9b-it",
]

# ── OpenRouter fallback (free models, no daily quota) ─────────────────────────
_OR_MODELS = [
    "openai/gpt-oss-120b:free",
    "nvidia/nemotron-3-super-120b-a12b:free",
    "openai/gpt-oss-20b:free",
    "liquid/lfm-2.5-1.2b-instruct:free",
]
_or_pool: list[str] = list(OPENROUTER_API_KEYS)

async def _generate_with_groq(prompt: str, max_tokens: int = 8192) -> str:
    """Call Groq API (OpenAI-compatible) as fallback when Gemini quota is exhausted."""
    if not _groq_pool:
        raise QuotaExhaustedError("لا يوجد GROQ_API_KEY — أضفه من console.groq.com")

    for groq_key in _groq_pool:
        for model in _GROQ_MODELS:
            try:
                headers = {
                    "Authorization": f"Bearer {groq_key}",
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
                            body = await resp.text()
                            print(f"⚠️ Groq {model} 429: {body[:80]}")
                            continue
                        else:
                            body = await resp.text()
                            print(f"⚠️ Groq {model} {resp.status}: {body[:80]}")
                            continue
            except Exception as e:
                print(f"⚠️ Groq {model} error: {e!s:.80}")
                continue

    raise QuotaExhaustedError(
        "⚠️ نفدت حصة Groq. سيتم التحويل لـ OpenRouter..."
    )


async def _generate_with_openrouter(prompt: str, max_tokens: int = 8192) -> str:
    """Call OpenRouter free models as second fallback — no daily quota."""
    if not _or_pool:
        raise QuotaExhaustedError("لا يوجد OPENROUTER_API_KEY")

    for or_key in _or_pool:
        for model in _OR_MODELS:
            try:
                headers = {
                    "Authorization": f"Bearer {or_key}",
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
                                print(f"⚠️ OpenRouter {model} returned empty response")
                                continue
                        else:
                            body = await resp.text()
                            print(f"⚠️ OpenRouter {model} {resp.status}: {body[:100]}")
                            continue
            except Exception as e:
                print(f"⚠️ OpenRouter {model} error: {e!s:.80}")
                continue

    raise QuotaExhaustedError(
        "⚠️ نفدت حصة OpenRouter أيضاً."
    )


async def _generate_with_rotation(prompt: str, max_output_tokens: int = 8192) -> str:
    """
    1) Try every Gemini key × model (no waiting on 429 — move on immediately).
    2) If all Gemini attempts fail → try Groq (free, fast, generous limits).
    3) If Groq fails → try OpenRouter free models (no daily quota).
    4) If all fail → raise QuotaExhaustedError with helpful message.
    """
    global _current_key_idx

    # Only models confirmed working in v1beta API
    gemini_models = ["gemini-2.0-flash", "gemini-2.0-flash-lite"]
    gemini_errors: list[str] = []

    # ── Phase 1: Try Gemini ────────────────────────────────────────────────────
    for i in range(len(_key_pool)):
        key_idx = (_current_key_idx + i) % len(_key_pool)
        key     = _key_pool[key_idx]
        client  = _get_client(key)

        for model in gemini_models:
            try:
                response = await asyncio.to_thread(
                    client.models.generate_content,
                    model=model,
                    contents=prompt,
                    config=genai_types.GenerateContentConfig(
                        temperature=0.3,
                        max_output_tokens=max_output_tokens,
                    ),
                )
                _current_key_idx = key_idx
                print(f"✅ Gemini success: {model}")
                return response.text.strip()
            except Exception as e:
                err = str(e)
                print(f"⚠️ Gemini {model} failed: {err[:100]}")
                gemini_errors.append(f"Gemini/{model}: {err[:60]}")
                continue  # always try next model/key without waiting

    # ── Phase 2: Gemini exhausted — try Groq immediately ──────────────────────
    if _groq_pool:
        print("🔄 Gemini exhausted — switching to Groq...")
        try:
            return await _generate_with_groq(prompt, max_tokens=max_output_tokens)
        except QuotaExhaustedError as groq_err:
            gemini_errors.append(f"Groq: {groq_err!s:.80}")

    # ── Phase 3: Groq failed — try OpenRouter free models ─────────────────────
    if _or_pool:
        print("🔄 Groq failed — switching to OpenRouter free models...")
        try:
            return await _generate_with_openrouter(prompt, max_tokens=max_output_tokens)
        except QuotaExhaustedError as or_err:
            gemini_errors.append(f"OpenRouter: {or_err!s:.80}")

    # ── Phase 4: Everything failed ─────────────────────────────────────────────
    errors_summary = " | ".join(gemini_errors[-4:]) if gemini_errors else "unknown"
    raise QuotaExhaustedError(
        f"QUOTA_EXHAUSTED:{errors_summary}"
    )


def _compute_lecture_scale(text: str) -> tuple:
    """Return (num_sections, narration_sentences, max_tokens) based on word count."""
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
        key_points_hint = '["Key point 1 in English", "Key point 2", "Key point 3", "Key point 4"]'
        title_hint = "Lecture title in English"
        section_title_hint = "Section title in English"
        content_hint = f"Simplified section content in English ({narration_sentences} sentences)"
        keywords_hint = '["keyword1", "keyword2", "keyword3", "keyword4"]'
        narration_hint = f"Full narration in English as a teacher explaining to students ({narration_sentences} sentences)"
        lang_note = "IMPORTANT: Write ALL text fields (title, section titles, content, narration, summary, key_points, keywords) in English."
    else:
        summary_hint = "ملخص المحاضرة بأسلوب مبسط (4-5 جمل)"
        key_points_hint = '["نقطة رئيسية 1", "نقطة رئيسية 2", "نقطة رئيسية 3", "نقطة رئيسية 4"]'
        title_hint = "عنوان المحاضرة"
        section_title_hint = "عنوان القسم"
        content_hint = f"محتوى القسم المبسط بأسلوب ممتع وسهل الفهم ({narration_sentences} جمل)"
        keywords_hint = '["مصطلح رئيسي 1", "مصطلح رئيسي 2", "مصطلح رئيسي 3", "مصطلح رئيسي 4"]'
        narration_hint = f"نص الشرح الكامل بالنص الطبيعي للمحاضر مع اللهجة المطلوبة، اجعله ممتعاً وشيقاً ({narration_sentences} جمل)"
        lang_note = "النص يجب أن يكون باللهجة المطلوبة بالكامل مع الحفاظ على الأسلوب التعليمي"

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
        "cartoon visual 1 — 3-5 English words describing a simple cartoon that shows exactly what the narration says about keyword1 (e.g. 'uterus contracting cartoon', 'prostaglandin molecule simple')",
        "cartoon visual 2 — matches what narration says about keyword2",
        "cartoon visual 3 — matches what narration says about keyword3",
        "cartoon visual 4 — matches what narration says about keyword4"
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
- اجعل الشرح (narration) طبيعياً وطويلاً كأن معلم خبير يشرح أمام الطلاب مباشرة — فصّل كل فكرة، أعطِ أمثلة، ووضّح الربط بين المفاهيم
- كل قسم يجب أن يكون شرحاً وافياً ({narration_sentences} جملة) بحيث مدة الصوت بين 60-120 ثانية لكل قسم
- لا تختصر، المطلوب شرح موسّع وتفصيلي
- keywords: 4 مصطلحات/كلمات مفتاحية أساسية تمثل أجزاء الشرح الأربعة في هذا القسم — الكلمة الأولى للجزء الأول من الشرح، والثانية للجزء الثاني، وهكذا
- keyword_images: مصفوفة من 4 عناصر — لكل كلمة مفتاحية وصف إنجليزي لصورة كرتونية بسيطة تمثل بالضبط ما يُشرح في ذلك الجزء من narration. أمثلة: 'uterus contracting simple cartoon', 'prostaglandin molecule cartoon', 'pain receptor cartoon person', 'ibuprofen pill cartoon'. كل وصف 3-5 كلمات إنجليزية فقط — فكرة واحدة واضحة وبسيطة قابلة للرسم
- الصورة والكلمة المفتاحية يجب أن يعكسا ما يُقال بالصوت في تلك اللحظة بالضبط
- duration_estimate: تقدير ثواني الشرح الصوتي بناءً على طول narration (60-120 ثانية لكل قسم)
- أرجع JSON فقط بدون أي نص إضافي أو ```json
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
        raise ValueError(f"Failed to parse Gemini response as JSON: {content[:500]}")


def _is_safe_url(url: str) -> bool:
    """Block SSRF attempts - disallow private/internal IPs and non-HTTP schemes."""
    import ipaddress
    from urllib.parse import urlparse

    try:
        parsed = urlparse(url)
        if parsed.scheme not in ('http', 'https'):
            return False

        hostname = parsed.hostname or ''
        if not hostname:
            return False

        blocked_hosts = {
            'localhost', '127.0.0.1', '0.0.0.0', '::1',
            'metadata.google.internal', '169.254.169.254'
        }
        if hostname.lower() in blocked_hosts:
            return False

        try:
            ip = ipaddress.ip_address(hostname)
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                return False
        except ValueError:
            pass

        return True
    except Exception:
        return False


async def extract_text_from_url(url: str) -> str:
    from bs4 import BeautifulSoup

    if not _is_safe_url(url):
        raise ValueError("URL is not allowed. Only public HTTP/HTTPS URLs are accepted.")

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }

    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status != 200:
                raise ValueError(f"Failed to fetch URL: HTTP {resp.status}")
            content_type = resp.headers.get('Content-Type', '')
            if 'text' not in content_type and 'html' not in content_type:
                raise ValueError("URL does not return HTML/text content")
            html = await resp.text()

    soup = BeautifulSoup(html, 'html.parser')
    for tag in soup(['script', 'style', 'nav', 'footer', 'header']):
        tag.decompose()

    text = soup.get_text(separator='\n', strip=True)
    lines = [line.strip() for line in text.split('\n') if line.strip() and len(line.strip()) > 20]
    return '\n'.join(lines[:200])


async def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    import PyPDF2

    reader = PyPDF2.PdfReader(io.BytesIO(pdf_bytes))
    text = ""
    for page in reader.pages:
        text += page.extract_text() + "\n"
    return text[:15000]


async def extract_full_text_from_pdf(pdf_bytes: bytes) -> str:
    """Extract all text from a PDF without truncation."""
    import PyPDF2

    reader = PyPDF2.PdfReader(io.BytesIO(pdf_bytes))
    pages = []
    for page in reader.pages:
        page_text = page.extract_text() or ""
        if page_text.strip():
            pages.append(page_text)
    return "\n\n".join(pages)


async def translate_full_text(text: str, dialect: str) -> str:
    """Translate the full text to the specified Arabic dialect, preserving structure."""
    dialect_instructions = {
        "iraq": (
            "ترجم النص التالي بالكامل إلى اللهجة العراقية. "
            "استخدم الكلمات والتعابير العراقية الأصيلة مثل (هواية، گلت، يعني، بس، هسا، چي، شلون، وين، أكو، ماكو). "
            "حافظ على كل المعنى والتفاصيل والبنية الأصلية للنص تماماً."
        ),
        "egypt": (
            "ترجم النص التالي بالكامل إلى اللهجة المصرية. "
            "استخدم الكلمات والتعابير المصرية مثل (أوي، معلش، إيه، مش، كده، بتاع، عايز، فين، ازيك، أهو). "
            "حافظ على كل المعنى والتفاصيل والبنية الأصلية للنص تماماً."
        ),
        "syria": (
            "ترجم النص التالي بالكامل إلى اللهجة الشامية السورية. "
            "استخدم الكلمات والتعابير الشامية مثل (هلق، شو، كتير، منيح، هيك، لهلق، قديش، عم، هون، كيفك). "
            "حافظ على كل المعنى والتفاصيل والبنية الأصلية للنص تماماً."
        ),
        "gulf": (
            "ترجم النص التالي بالكامل إلى اللهجة الخليجية. "
            "استخدم الكلمات والتعابير الخليجية مثل (زين، وايد، عاد، هاذي، أبشر، شفيك، ليش، كيفك، إيه، واللي). "
            "حافظ على كل المعنى والتفاصيل والبنية الأصلية للنص تماماً."
        ),
        "msa": (
            "حوّل النص التالي بالكامل إلى العربية الفصحى السليمة والواضحة. "
            "صحح أي كلمات عامية أو لهجوية واستبدلها بالفصحى المناسبة. "
            "حافظ على كل المعنى والتفاصيل والبنية الأصلية للنص تماماً."
        ),
    }

    instruction = dialect_instructions.get(dialect, dialect_instructions["msa"])

    MAX_CHUNK = 12000
    if len(text) <= MAX_CHUNK:
        chunks = [text]
    else:
        paragraphs = text.split("\n")
        chunks = []
        current: list[str] = []
        current_len = 0
        for para in paragraphs:
            if current_len + len(para) + 1 > MAX_CHUNK and current:
                chunks.append("\n".join(current))
                current = [para]
                current_len = len(para)
            else:
                current.append(para)
                current_len += len(para) + 1
        if current:
            chunks.append("\n".join(current))

    translated_parts: list[str] = []
    for idx, chunk in enumerate(chunks):
        prompt = (
            f"{instruction}\n\n"
            f"النص:\n---\n{chunk}\n---\n\n"
            f"قدّم الترجمة فقط بدون أي شرح أو تعليق إضافي. "
            f"حافظ على التنسيق والفقرات كما هي."
        )
        result = await _generate_with_rotation(prompt)
        translated_parts.append(result)

    return "\n\n".join(translated_parts)


def _make_placeholder_image(keywords: list, lecture_type: str = "other") -> bytes:
    """
    Generate a professional educational card with gradient background,
    decorative shapes, and the keyword text (Arabic-aware).
    Used as fallback when Pollinations is unavailable.
    """
    from PIL import ImageDraw, ImageFont
    import os

    # ── Color palettes per lecture type (bg1, bg2, accent) ──────────────────
    PALETTES = {
        "طب":      ((20, 78, 140), (6, 147, 227), (255, 200, 0)),
        "medicine":((20, 78, 140), (6, 147, 227), (255, 200, 0)),
        "علوم":    ((11, 110, 79), (28, 200, 135), (255, 220, 50)),
        "science": ((11, 110, 79), (28, 200, 135), (255, 220, 50)),
        "رياضيات": ((58, 12, 163), (100, 60, 220), (255, 180, 0)),
        "math":    ((58, 12, 163), (100, 60, 220), (255, 180, 0)),
        "تاريخ":   ((150, 60, 10), (220, 110, 40), (255, 230, 100)),
        "history": ((150, 60, 10), (220, 110, 40), (255, 230, 100)),
        "فيزياء":  ((10, 50, 120), (30, 120, 210), (0, 230, 210)),
        "physics": ((10, 50, 120), (30, 120, 210), (0, 230, 210)),
        "كيمياء":  ((100, 0, 100), (180, 0, 200), (0, 220, 180)),
        "chemistry":((100,0,100), (180, 0, 200), (0, 220, 180)),
        "هندسة":   ((20, 70, 60), (40, 140, 120), (255, 200, 0)),
        "engineering":((20,70,60),(40,140,120),(255,200,0)),
        "اقتصاد":  ((0, 80, 40), (0, 160, 80), (255, 220, 0)),
        "economics":((0,80,40), (0,160,80), (255,220,0)),
    }
    bg1, bg2, accent = PALETTES.get(lecture_type, ((30, 30, 80), (70, 60, 160), (255, 200, 50)))

    W, H = 1280, 720
    img = PILImage.new("RGB", (W, H), bg1)
    draw = ImageDraw.Draw(img)

    # ── Gradient background (horizontal blend) ───────────────────────────────
    for x in range(W):
        t = x / W
        r = int(bg1[0] * (1 - t) + bg2[0] * t)
        g = int(bg1[1] * (1 - t) + bg2[1] * t)
        b = int(bg1[2] * (1 - t) + bg2[2] * t)
        draw.line([(x, 0), (x, H)], fill=(r, g, b))

    # ── Decorative circles ───────────────────────────────────────────────────
    def draw_circle(cx, cy, r, fill, alpha=80):
        mask = PILImage.new("RGBA", (W, H), (0, 0, 0, 0))
        mdraw = ImageDraw.Draw(mask)
        mdraw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(*fill, alpha))
        img.paste(PILImage.new("RGB", (W, H), fill), mask=mask.split()[3])

    draw_circle(-60, -60, 260, accent, 40)
    draw_circle(W + 60, H + 60, 300, accent, 30)
    draw_circle(W // 2, H // 2, 200, bg2, 25)
    draw_circle(80, H - 80, 120, accent, 35)

    # ── Thin accent border ───────────────────────────────────────────────────
    border = 8
    draw.rectangle([border, border, W - border, H - border],
                   outline=accent, width=border)

    # ── Fonts ────────────────────────────────────────────────────────────────
    FONTS_DIR = os.path.join(os.path.dirname(__file__), "fonts")
    ARABIC_BOLD = os.path.join(FONTS_DIR, "NotoNaskhArabic-Bold.ttf")
    LATIN_BOLD  = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

    def load_font(path, size):
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            return ImageFont.load_default()

    # ── Keyword text ─────────────────────────────────────────────────────────
    keyword_raw = (keywords[0] if keywords else "").strip()

    def _ar(text: str) -> str:
        try:
            import arabic_reshaper
            from bidi.algorithm import get_display
            return get_display(arabic_reshaper.reshape(text))
        except Exception:
            return text

    # detect Arabic
    has_arabic = any("\u0600" <= c <= "\u06ff" for c in keyword_raw)
    if has_arabic:
        display_text = _ar(keyword_raw)
        font_kw = load_font(ARABIC_BOLD, 80)
    else:
        display_text = keyword_raw
        font_kw = load_font(LATIN_BOLD, 80)

    # wrap long text
    MAX_CHARS = 30
    if len(display_text) > MAX_CHARS:
        mid = len(display_text) // 2
        display_text = display_text[:mid] + "\n" + display_text[mid:]

    # shadow
    draw.text((W // 2 + 3, H // 2 + 3), display_text,
              fill=(0, 0, 0, 120), font=font_kw, anchor="mm", align="center")
    # main text
    draw.text((W // 2, H // 2), display_text,
              fill=(255, 255, 255), font=font_kw, anchor="mm", align="center")

    # ── Accent underline ─────────────────────────────────────────────────────
    uw = min(500, len(display_text) * 28)
    uy = H // 2 + 70
    draw.rectangle([W // 2 - uw // 2, uy, W // 2 + uw // 2, uy + 6],
                   fill=accent)

    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=92)
    return buf.getvalue()


async def _fetch_image_from_url(img_url: str) -> bytes | None:
    """Download image from URL and return as JPEG bytes, resized to 1280x720."""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "image/*",
        }
        async with aiohttp.ClientSession() as session:
            async with session.get(img_url, headers=headers, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                if resp.status != 200:
                    return None
                content_type = resp.headers.get("Content-Type", "")
                if "image" not in content_type:
                    return None
                raw = await resp.read()

        pil_img = PILImage.open(io.BytesIO(raw)).convert("RGB")
        target_w, target_h = 1280, 720
        src_w, src_h = pil_img.size
        src_ratio = src_w / src_h
        target_ratio = target_w / target_h

        if src_ratio > target_ratio:
            new_h = target_h
            new_w = int(src_ratio * target_h)
        else:
            new_w = target_w
            new_h = int(target_w / src_ratio)

        pil_img = pil_img.resize((new_w, new_h), PILImage.LANCZOS)

        left = (new_w - target_w) // 2
        top = (new_h - target_h) // 2
        pil_img = pil_img.crop((left, top, left + target_w, top + target_h))

        buf = io.BytesIO()
        pil_img.save(buf, "JPEG", quality=90)
        return buf.getvalue()
    except Exception:
        return None


# ---------------------------------------------------------------------------
# DALL-E 3 — OpenAI image generation (highest quality AI cartoon images)
# ---------------------------------------------------------------------------
async def _dalle_generate(prompt: str) -> bytes | None:
    """
    Generate a cartoon educational image via DALL-E 3 (OpenAI).
    Returns JPEG bytes resized to 1280×720, or None on failure.
    """
    import base64
    if not OPENAI_API_KEY:
        return None
    payload = {
        "model": "dall-e-3",
        "prompt": prompt,
        "size": "1792x1024",
        "quality": "standard",
        "n": 1,
        "response_format": "b64_json",
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {OPENAI_API_KEY}",
    }
    try:
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.post(
                "https://api.openai.com/v1/images/generations",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=40),
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    print(f"DALL-E error {resp.status}: {body[:120]}")
                    return None
                data = await resp.json()
                imgs = data.get("data", [])
                if not imgs:
                    return None
                b64 = imgs[0].get("b64_json", "")
                raw = base64.b64decode(b64)
                # resize to 1280×720
                pil_img = PILImage.open(io.BytesIO(raw)).convert("RGB")
                pil_img = pil_img.resize((1280, 720), PILImage.LANCZOS)
                buf = io.BytesIO()
                pil_img.save(buf, "JPEG", quality=92)
                kb = len(buf.getvalue()) // 1024
                print(f"DALL-E 3 OK: {kb}KB")
                return buf.getvalue()
    except Exception as e:
        print(f"DALL-E exception: {e}")
        return None


def _build_dalle_prompt(subject: str, lecture_type: str) -> str:
    """
    Build a prompt for a hand-drawn Osmosis-style medical sketch illustration.
    Osmosis style: thin pink/red pencil outline on pure white, simple anatomy sketch.
    """
    # Type-specific style hint
    style: dict[str, str] = {
        "medicine":    "medical anatomy sketch, thin pink outline drawing",
        "science":     "science diagram sketch, thin line drawing",
        "math":        "math concept sketch, clean line drawing",
        "physics":     "physics diagram sketch, simple line illustration",
        "chemistry":   "chemistry molecule sketch, simple line drawing",
        "biology":     "biology cell sketch, thin outline illustration",
        "history":     "history scene sketch, simple pencil illustration",
        "computer":    "tech diagram sketch, simple line drawing",
        "business":    "business concept sketch, simple line illustration",
        "engineering": "engineering diagram sketch, simple line drawing",
        "literature":  "literary scene sketch, simple pencil illustration",
        "other":       "educational sketch, simple line drawing",
    }
    s = style.get(lecture_type, style["other"])

    return (
        f"{s}, {subject}, "
        "Osmosis.org style medical education illustration, "
        "hand-drawn pencil sketch, thin clean outline, "
        "pure white background, minimal soft pink and red colors only, "
        "single concept, simple anatomy diagram, "
        "no photorealism, no 3D, no shading, no background elements, "
        "no text, no watermark, clean educational medical sketch"
    )


# ---------------------------------------------------------------------------
# Pollinations.ai — fast free AI image generation (no key needed, ~5s)
# ---------------------------------------------------------------------------
async def _pollinations_generate(prompt: str, lecture_type: str = "other") -> bytes | None:
    """Generate image via Pollinations.ai — free, no API key, ~5s response."""
    import urllib.parse, random

    # flux-anime → clean flat style closest to Osmosis hand-drawn look
    model = "flux-anime"

    clean_prompt = prompt[:380].replace("\n", " ")
    seed = random.randint(1, 99999)
    encoded = urllib.parse.quote(clean_prompt)
    url = (
        f"https://image.pollinations.ai/prompt/{encoded}"
        f"?width=854&height=480&nologo=true&enhance=false&seed={seed}&model={model}"
    )
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
                        print(f"Pollinations OK: {len(buf.getvalue())//1024}KB")
                        return buf.getvalue()
    except Exception as e:
        print(f"Pollinations error: {e}")
    return None


# ---------------------------------------------------------------------------
# Stable Horde — kept as last-resort only (very slow, skipped by default)
# ---------------------------------------------------------------------------
_HORDE_KEY = "0000000000"   # anonymous free tier
_HORDE_BASE = "https://aihorde.net/api/v2"


async def _stable_horde_generate(prompt: str, max_wait: float = 25.0) -> bytes | None:
    """
    Generate an AI cartoon image via Stable Horde (free, distributed).
    Submits a job and polls for up to `max_wait` seconds.
    Returns JPEG bytes resized to 1280×720, or None on failure/timeout.
    """
    import base64

    headers = {
        "Content-Type": "application/json",
        "apikey": _HORDE_KEY,
        "Client-Agent": "TelegramLectureBot:2.0:anonymous",
    }

    submit_payload = {
        "prompt": prompt,
        "params": {
            "width": 576,      # must be multiple of 64
            "height": 320,     # must be multiple of 64 (≈16:9)
            "steps": 15,
            "cfg_scale": 7,
            "sampler_name": "k_euler",
            "n": 1,
        },
        "nsfw": False,
        "trusted_workers": False,
        "slow_workers": True,   # include slow community workers → faster queues
        "r2": False,            # return base64 inline (no R2 storage link)
        "models": ["Dreamshaper 8"],
    }

    try:
        async with aiohttp.ClientSession(headers=headers) as session:
            # 1. Submit job
            async with session.post(
                f"{_HORDE_BASE}/generate/async",
                json=submit_payload,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status not in (200, 202):
                    body = await resp.text()
                    print(f"Horde submit failed {resp.status}: {body[:100]}")
                    return None
                job = await resp.json()
                job_id = job.get("id")
                if not job_id:
                    return None
                print(f"Horde job submitted: {job_id}")

            # 2. Poll until done or timeout
            t0 = asyncio.get_event_loop().time()
            poll_interval = 3.0
            while True:
                elapsed = asyncio.get_event_loop().time() - t0
                if elapsed >= max_wait:
                    print(f"Horde timeout after {elapsed:.0f}s for: '{prompt[:40]}'")
                    return None

                await asyncio.sleep(poll_interval)
                async with session.get(
                    f"{_HORDE_BASE}/generate/check/{job_id}",
                    timeout=aiohttp.ClientTimeout(total=8),
                ) as check:
                    if check.status != 200:
                        continue
                    status = await check.json()
                    wait_time = status.get("wait_time", 0)
                    done = status.get("done", False)
                    print(f"  Horde: done={done} wait={wait_time}s elapsed={elapsed:.0f}s")

                    # if queue is very long and we still have time for OpenVerse, abort
                    if not done and wait_time > (max_wait - elapsed - 2):
                        print(f"Horde queue too long ({wait_time}s), switching to OpenVerse")
                        return None

                    if not done:
                        continue

                # 3. Fetch result
                async with session.get(
                    f"{_HORDE_BASE}/generate/status/{job_id}",
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as result:
                    if result.status != 200:
                        return None
                    result_data = await result.json()
                    generations = result_data.get("generations", [])
                    if not generations:
                        return None
                    b64 = generations[0].get("img", "")
                    if not b64:
                        return None
                    raw = base64.b64decode(b64)
                    elapsed_total = asyncio.get_event_loop().time() - t0
                    print(f"Horde image OK: {len(raw)//1024}KB in {elapsed_total:.1f}s")

                    # resize to 1280x720
                    pil_img = PILImage.open(io.BytesIO(raw)).convert("RGB")
                    pil_img = pil_img.resize((1280, 720), PILImage.LANCZOS)
                    buf = io.BytesIO()
                    pil_img.save(buf, "JPEG", quality=88)
                    return buf.getvalue()
    except Exception as e:
        print(f"Horde error: {e}")
        return None


def _build_horde_prompt(subject: str, lecture_type: str) -> str:
    """Build a Stable Diffusion prompt for a clear educational illustration."""
    ctx = _build_dalle_prompt(subject, lecture_type)
    return ctx


# ---------------------------------------------------------------------------
# OpenVerse — Creative Commons image search (fast fallback)
# ---------------------------------------------------------------------------
async def _openverse_search_image(queries: list[str]) -> str | None:
    """Search OpenVerse for a CC-licensed image. Returns a direct URL or None."""
    import urllib.parse
    base = "https://api.openverse.org/v1/images/"
    headers = {"User-Agent": "TelegramLectureBot/2.0", "Accept": "application/json"}
    async with aiohttp.ClientSession(headers=headers) as session:
        for q in queries:
            if not q:
                continue
            params = urllib.parse.urlencode({"q": q, "page_size": 5})
            try:
                async with session.get(
                    f"{base}?{params}", timeout=aiohttp.ClientTimeout(total=8)
                ) as resp:
                    if resp.status != 200:
                        continue
                    data = await resp.json()
                    for r in data.get("results", []):
                        img_url = r.get("url", "")
                        if img_url and img_url.startswith("http"):
                            ext = img_url.split("?")[0].lower().split(".")[-1]
                            if ext not in ("svg", "gif", "webp"):
                                print(f"OpenVerse found: '{q[:40]}' → {img_url[:60]}")
                                return img_url
            except Exception as e:
                print(f"OpenVerse error for '{q[:40]}': {e}")
    return None


async def _openverse_fetch(queries: list[str]) -> bytes | None:
    """Search OpenVerse and download the image as resized JPEG bytes."""
    url = await _openverse_search_image(queries)
    if not url:
        return None
    img_bytes = await _fetch_image_from_url(url)
    if img_bytes:
        print(f"OpenVerse image OK ({len(img_bytes)//1024}KB): '{queries[0][:50]}'")
    return img_bytes


# ---------------------------------------------------------------------------
# Main public API
# ---------------------------------------------------------------------------
async def generate_educational_image(
    prompt: str,
    lecture_type: str,
    keywords: list = None,
    image_search: str = None,
    image_search_fallbacks: list = None,
) -> bytes:
    """Generate/fetch an educational image. Pollinations → DALL-E → OpenVerse → PIL card."""
    kws = (keywords or [])[:4]
    subject = (image_search or (kws[0] if kws else prompt[:40])).strip()

    # 1. Pollinations.ai — fast free AI image (primary, ~5s)
    pol_prompt = _build_dalle_prompt(subject, lecture_type)
    try:
        img_bytes = await asyncio.wait_for(
            _pollinations_generate(pol_prompt, lecture_type), timeout=15.0
        )
        if img_bytes:
            return img_bytes
    except (asyncio.TimeoutError, Exception) as e:
        print(f"Pollinations fallback: {e}")

    # 2. DALL-E 3 — only if OpenAI key is set
    if OPENAI_API_KEY:
        dalle_prompt = _build_dalle_prompt(subject, lecture_type)
        try:
            img_bytes = await asyncio.wait_for(_dalle_generate(dalle_prompt), timeout=30.0)
            if img_bytes:
                return img_bytes
        except (asyncio.TimeoutError, Exception) as e:
            print(f"DALL-E fallback: {e}")

    # 3. OpenVerse — real educational photos (fast, CC-licensed)
    queries = [f"{subject} educational", f"{subject} diagram", f"{subject} science"]
    for kw in kws[:2]:
        if kw and kw != subject:
            queries.append(f"{kw} educational diagram")
    try:
        img_bytes = await asyncio.wait_for(_openverse_fetch(queries), timeout=10.0)
        if img_bytes:
            return img_bytes
    except (asyncio.TimeoutError, Exception):
        pass

    # 4. PIL placeholder (instant)
    return _make_placeholder_image(kws, lecture_type)


async def fetch_image_for_keyword(
    keyword: str,
    section_title: str,
    lecture_type: str,
    image_search_en: str = "",
) -> bytes:
    """
    Fetch a cartoon AI image for the keyword.
    Pipeline: DALL-E 3 → Stable Horde → OpenVerse → PIL educational card.
    Always returns bytes — never None.
    """
    subject = (image_search_en or keyword).strip()

    # 1. Pollinations.ai — fast free AI image (primary, ~5s)
    pol_prompt = _build_dalle_prompt(subject, lecture_type)
    try:
        img_bytes = await asyncio.wait_for(
            _pollinations_generate(pol_prompt, lecture_type), timeout=15.0
        )
        if img_bytes:
            return img_bytes
    except (asyncio.TimeoutError, Exception) as e:
        print(f"Pollinations fallback for keyword '{subject[:30]}': {e}")

    # 2. DALL-E 3 — only if OpenAI key is set
    if OPENAI_API_KEY:
        dalle_prompt = _build_dalle_prompt(subject, lecture_type)
        try:
            img_bytes = await asyncio.wait_for(_dalle_generate(dalle_prompt), timeout=30.0)
            if img_bytes:
                return img_bytes
        except Exception as e:
            print(f"DALL-E error: {e}")

    # 3. OpenVerse — real educational photos
    ov_queries = [f"{subject} educational", f"{subject} diagram", f"{section_title} educational"]
    seen: set[str] = set()
    ov_clean = [q for q in ov_queries if q and not (q in seen or seen.add(q))]
    try:
        img_bytes = await asyncio.wait_for(_openverse_fetch(ov_clean), timeout=10.0)
        if img_bytes:
            return img_bytes
    except (asyncio.TimeoutError, Exception) as e:
        print(f"OpenVerse error: {e}")

    # 4. PIL placeholder (instant)
    return _make_placeholder_image([keyword, section_title], lecture_type)
