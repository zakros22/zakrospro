import json
import re
import io
import asyncio
import aiohttp
from PIL import Image as PILImage
from google import genai
from google.genai import types as genai_types
from config import (
    DEEPSEEK_API_KEYS, GOOGLE_API_KEYS, GROQ_API_KEYS, OPENROUTER_API_KEYS
)
from image_generator import fetch_image_for_keyword, generate_educational_image

# ══════════════════════════════════════════════════════════════════════════════
# 🔑 KEY POOLS & ROTATION
# ══════════════════════════════════════════════════════════════════════════════
_deepseek_pool = list(DEEPSEEK_API_KEYS)
_deepseek_idx = 0
_deepseek_exhausted = set()

_gemini_pool = list(GOOGLE_API_KEYS)
_gemini_idx = 0
_gemini_exhausted = set()
_gemini_clients = {}

_groq_pool = list(GROQ_API_KEYS)
_groq_idx = 0
_groq_exhausted = set()

_or_pool = list(OPENROUTER_API_KEYS)
_or_idx = 0
_or_exhausted = set()


class QuotaExhaustedError(Exception):
    pass


# ══════════════════════════════════════════════════════════════════════════════
# 1️⃣ DEEPSEEK
# ══════════════════════════════════════════════════════════════════════════════
DEEPSEEK_MODELS = ["deepseek-chat", "deepseek-reasoner"]

async def _generate_with_deepseek(prompt: str, max_tokens: int = 8192) -> str:
    global _deepseek_idx, _deepseek_exhausted
    
    if not _deepseek_pool:
        raise QuotaExhaustedError("No DeepSeek keys")
    
    for _ in range(len(_deepseek_pool)):
        key_idx = _deepseek_idx % len(_deepseek_pool)
        key = _deepseek_pool[key_idx]
        _deepseek_idx += 1
        
        if key in _deepseek_exhausted:
            continue
            
        for model in DEEPSEEK_MODELS:
            try:
                headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
                payload = {
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": min(max_tokens, 8192),
                    "temperature": 0.3,
                }
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        "https://api.deepseek.com/v1/chat/completions",
                        headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=90)
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            print(f"✅ DeepSeek success: {model}")
                            return data["choices"][0]["message"]["content"].strip()
                        elif resp.status in (429, 402, 403):
                            _deepseek_exhausted.add(key)
                            break
            except Exception as e:
                print(f"⚠️ DeepSeek error: {e}")
                continue
    raise QuotaExhaustedError("All DeepSeek keys exhausted")


# ══════════════════════════════════════════════════════════════════════════════
# 2️⃣ GEMINI
# ══════════════════════════════════════════════════════════════════════════════
def _get_gemini_client(key: str):
    if key not in _gemini_clients:
        _gemini_clients[key] = genai.Client(api_key=key)
    return _gemini_clients[key]


async def _generate_with_gemini(prompt: str, max_tokens: int = 8192) -> str:
    global _gemini_idx, _gemini_exhausted
    
    if not _gemini_pool:
        raise QuotaExhaustedError("No Gemini keys")
    
    models = ["gemini-2.0-flash", "gemini-2.0-flash-lite", "gemini-1.5-flash"]
    
    for _ in range(len(_gemini_pool)):
        key_idx = _gemini_idx % len(_gemini_pool)
        key = _gemini_pool[key_idx]
        _gemini_idx += 1
        
        if key in _gemini_exhausted:
            continue
            
        client = _get_gemini_client(key)
        
        for model in models:
            try:
                response = await asyncio.to_thread(
                    client.models.generate_content,
                    model=model, contents=prompt,
                    config=genai_types.GenerateContentConfig(temperature=0.3, max_output_tokens=max_tokens),
                )
                print(f"✅ Gemini success: {model}")
                return response.text.strip()
            except Exception as e:
                err = str(e)
                if "quota" in err.lower() or "429" in err:
                    _gemini_exhausted.add(key)
                    break
                continue
    raise QuotaExhaustedError("All Gemini keys exhausted")


# ══════════════════════════════════════════════════════════════════════════════
# 3️⃣ GROQ
# ══════════════════════════════════════════════════════════════════════════════
GROQ_MODELS = ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "gemma2-9b-it", "mixtral-8x7b-32768"]

async def _generate_with_groq(prompt: str, max_tokens: int = 8192) -> str:
    global _groq_idx, _groq_exhausted
    
    if not _groq_pool:
        raise QuotaExhaustedError("No Groq keys")
    
    for _ in range(len(_groq_pool)):
        key_idx = _groq_idx % len(_groq_pool)
        key = _groq_pool[key_idx]
        _groq_idx += 1
        
        if key in _groq_exhausted:
            continue
            
        for model in GROQ_MODELS:
            try:
                headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
                payload = {
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": min(max_tokens, 8192),
                    "temperature": 0.3,
                }
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        "https://api.groq.com/openai/v1/chat/completions",
                        headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=90)
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            print(f"✅ Groq success: {model}")
                            return data["choices"][0]["message"]["content"].strip()
                        elif resp.status in (429, 403):
                            _groq_exhausted.add(key)
                            break
            except Exception as e:
                continue
    raise QuotaExhaustedError("All Groq keys exhausted")


# ══════════════════════════════════════════════════════════════════════════════
# 4️⃣ OPENROUTER
# ══════════════════════════════════════════════════════════════════════════════
OR_MODELS = [
    "deepseek/deepseek-chat:free",
    "google/gemini-2.0-flash-exp:free",
    "meta-llama/llama-3.3-70b-instruct:free",
    "qwen/qwen2.5-72b-instruct:free",
]

async def _generate_with_openrouter(prompt: str, max_tokens: int = 8192) -> str:
    global _or_idx, _or_exhausted
    
    if not _or_pool:
        raise QuotaExhaustedError("No OpenRouter keys")
    
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
                    "X-Title": "Lecture Bot",
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
                        headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=120)
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            content = data["choices"][0]["message"]["content"]
                            if content:
                                print(f"✅ OpenRouter success: {model}")
                                return content.strip()
                        elif resp.status in (429, 402, 403):
                            _or_exhausted.add(key)
                            break
            except Exception:
                continue
    raise QuotaExhaustedError("All OpenRouter keys exhausted")


# ══════════════════════════════════════════════════════════════════════════════
# 🔄 دالة التوليد الرئيسية
# ══════════════════════════════════════════════════════════════════════════════
async def _generate_with_rotation(prompt: str, max_tokens: int = 8192) -> str:
    """
    تجرب الخدمات بالترتيب:
    1. DeepSeek
    2. Gemini
    3. Groq
    4. OpenRouter
    """
    errors = []
    
    # 1️⃣ DeepSeek
    if _deepseek_pool:
        try:
            return await _generate_with_deepseek(prompt, max_tokens)
        except QuotaExhaustedError as e:
            errors.append(f"DeepSeek: {e}")
            print("🔄 Switching to Gemini...")
    
    # 2️⃣ Gemini
    if _gemini_pool:
        try:
            return await _generate_with_gemini(prompt, max_tokens)
        except QuotaExhaustedError as e:
            errors.append(f"Gemini: {e}")
            print("🔄 Switching to Groq...")
    
    # 3️⃣ Groq
    if _groq_pool:
        try:
            return await _generate_with_groq(prompt, max_tokens)
        except QuotaExhaustedError as e:
            errors.append(f"Groq: {e}")
            print("🔄 Switching to OpenRouter...")
    
    # 4️⃣ OpenRouter
    if _or_pool:
        try:
            return await _generate_with_openrouter(prompt, max_tokens)
        except QuotaExhaustedError as e:
            errors.append(f"OpenRouter: {e}")
    
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
        narration_hint = f"Full narration in English as a teacher explaining to students ({narration_sentences} sentences)"
        lang_note = "IMPORTANT: Write ALL text fields in English."
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
        "cartoon visual 1 — 3-5 English words describing a simple cartoon that shows exactly what the narration says about keyword1",
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
- اجعل الشرح (narration) طبيعياً وطويلاً كأن معلم خبير يشرح أمام الطلاب مباشرة
- كل قسم يجب أن يكون شرحاً وافياً ({narration_sentences} جمل)
- keywords: 4 مصطلحات/كلمات مفتاحية أساسية
- keyword_images: مصفوفة من 4 عناصر - وصف إنجليزي لصورة كرتونية بسيطة (3-5 كلمات)
- أرجع JSON فقط بدون أي نص إضافي
"""

    content = await _generate_with_rotation(prompt, max_tokens=8192)
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
# 🌐 استخراج النص من رابط URL
# ══════════════════════════════════════════════════════════════════════════════

def _is_safe_url(url: str) -> bool:
    """التحقق من أن الرابط آمن (يمنع SSRF)"""
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
    """استخراج النص من رابط مقال أو صفحة ويب"""
    from bs4 import BeautifulSoup

    if not _is_safe_url(url):
        raise ValueError("الرابط غير مسموح به. فقط روابط HTTP/HTTPS العامة مسموحة.")

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status != 200:
                    raise ValueError(f"فشل في جلب الرابط: HTTP {resp.status}")
                
                content_type = resp.headers.get('Content-Type', '')
                if 'text' not in content_type and 'html' not in content_type:
                    raise ValueError("الرابط لا يحتوي على نص أو HTML")
                
                html = await resp.text()

        soup = BeautifulSoup(html, 'html.parser')
        
        for tag in soup(['script', 'style', 'nav', 'footer', 'header', 'aside', 'noscript', 'meta', 'link']):
            tag.decompose()

        text = soup.get_text(separator='\n', strip=True)
        lines = [line.strip() for line in text.split('\n') if line.strip() and len(line.strip()) > 20]
        
        if not lines:
            raise ValueError("لم يتم العثور على نص كافٍ في الرابط")
        
        result = '\n'.join(lines[:200])
        
        if len(result) < 100:
            raise ValueError("النص المستخرج قصير جداً")
        
        return result
        
    except aiohttp.ClientError as e:
        raise ValueError(f"خطأ في الاتصال بالرابط: {e}")
    except Exception as e:
        raise ValueError(f"خطأ في استخراج النص: {e}")
