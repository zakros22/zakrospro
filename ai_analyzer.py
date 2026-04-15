import json
import re
import io
import asyncio
import aiohttp
from PIL import Image as PILImage

# ══════════════════════════════════════════════════════════════════════════════
# استيراد المفاتيح من config
# ══════════════════════════════════════════════════════════════════════════════
try:
    from config import (
        DEEPSEEK_API_KEYS, GOOGLE_API_KEYS, GROQ_API_KEYS, OPENROUTER_API_KEYS
    )
except ImportError:
    DEEPSEEK_API_KEYS = []
    GOOGLE_API_KEYS = []
    GROQ_API_KEYS = []
    OPENROUTER_API_KEYS = []

# استيراد Google Gemini
try:
    from google import genai
    from google.genai import types as genai_types
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    genai = None
    genai_types = None

# استيراد دوال الصور
try:
    from image_generator import fetch_image_for_keyword, generate_educational_image
except ImportError:
    fetch_image_for_keyword = None
    generate_educational_image = None


# ══════════════════════════════════════════════════════════════════════════════
# 🔑 KEY POOLS & ROTATION - تدوير المفاتيح
# ══════════════════════════════════════════════════════════════════════════════

_deepseek_pool = list(DEEPSEEK_API_KEYS) if DEEPSEEK_API_KEYS else []
_deepseek_exhausted = set()

_gemini_pool = list(GOOGLE_API_KEYS) if GOOGLE_API_KEYS else []
_gemini_exhausted = set()
_gemini_clients = {}

_groq_pool = list(GROQ_API_KEYS) if GROQ_API_KEYS else []
_groq_exhausted = set()

_or_pool = list(OPENROUTER_API_KEYS) if OPENROUTER_API_KEYS else []
_or_exhausted = set()


class QuotaExhaustedError(Exception):
    """يتم رميها عندما تنفد جميع المفاتيح لخدمة معينة"""
    pass


# ══════════════════════════════════════════════════════════════════════════════
# 1️⃣ DEEPSEEK
# ══════════════════════════════════════════════════════════════════════════════
DEEPSEEK_MODELS = ["deepseek-chat", "deepseek-reasoner"]

async def _generate_with_deepseek(prompt: str, max_tokens: int = 8192) -> str:
    if not _deepseek_pool:
        raise QuotaExhaustedError("No DeepSeek keys")
    
    available_keys = [k for k in _deepseek_pool if k not in _deepseek_exhausted]
    if not available_keys:
        raise QuotaExhaustedError("All DeepSeek keys exhausted")
    
    for key in available_keys:
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
                            body = await resp.text()
                            if "quota" in body.lower() or "insufficient" in body.lower():
                                print(f"⚠️ DeepSeek key exhausted")
                                _deepseek_exhausted.add(key)
                                break
            except Exception as e:
                print(f"⚠️ DeepSeek error: {str(e)[:100]}")
                continue
    
    raise QuotaExhaustedError("All DeepSeek keys exhausted")


# ══════════════════════════════════════════════════════════════════════════════
# 2️⃣ GEMINI
# ══════════════════════════════════════════════════════════════════════════════
def _get_gemini_client(key: str):
    if not GEMINI_AVAILABLE:
        raise QuotaExhaustedError("Gemini not available")
    if key not in _gemini_clients:
        _gemini_clients[key] = genai.Client(api_key=key)
    return _gemini_clients[key]


async def _generate_with_gemini(prompt: str, max_tokens: int = 8192) -> str:
    if not GEMINI_AVAILABLE:
        raise QuotaExhaustedError("Gemini not installed")
    
    if not _gemini_pool:
        raise QuotaExhaustedError("No Gemini keys")
    
    models = ["gemini-2.0-flash", "gemini-2.0-flash-lite", "gemini-1.5-flash"]
    available_keys = [k for k in _gemini_pool if k not in _gemini_exhausted]
    
    if not available_keys:
        raise QuotaExhaustedError("All Gemini keys exhausted")
    
    for key in available_keys:
        client = _get_gemini_client(key)
        
        for model in models:
            try:
                response = await asyncio.to_thread(
                    client.models.generate_content,
                    model=model,
                    contents=prompt,
                    config=genai_types.GenerateContentConfig(
                        temperature=0.3,
                        max_output_tokens=max_tokens
                    ),
                )
                print(f"✅ Gemini success: {model}")
                return response.text.strip()
            except Exception as e:
                err = str(e)
                if "quota" in err.lower() or "exhausted" in err.lower() or "429" in err:
                    print(f"⚠️ Gemini key exhausted")
                    _gemini_exhausted.add(key)
                    break
                print(f"⚠️ Gemini error: {err[:100]}")
                continue
    
    raise QuotaExhaustedError("All Gemini keys exhausted")


# ══════════════════════════════════════════════════════════════════════════════
# 3️⃣ GROQ
# ══════════════════════════════════════════════════════════════════════════════
GROQ_MODELS = ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "gemma2-9b-it"]

async def _generate_with_groq(prompt: str, max_tokens: int = 8192) -> str:
    if not _groq_pool:
        raise QuotaExhaustedError("No Groq keys")
    
    available_keys = [k for k in _groq_pool if k not in _groq_exhausted]
    if not available_keys:
        raise QuotaExhaustedError("All Groq keys exhausted")
    
    for key in available_keys:
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
                            body = await resp.text()
                            if "quota" in body.lower() or "limit" in body.lower():
                                print(f"⚠️ Groq key exhausted")
                                _groq_exhausted.add(key)
                                break
            except Exception as e:
                print(f"⚠️ Groq error: {str(e)[:100]}")
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
    if not _or_pool:
        raise QuotaExhaustedError("No OpenRouter keys")
    
    available_keys = [k for k in _or_pool if k not in _or_exhausted]
    if not available_keys:
        raise QuotaExhaustedError("All OpenRouter keys exhausted")
    
    for key in available_keys:
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
                            body = await resp.text()
                            if "quota" in body.lower() or "credits" in body.lower():
                                print(f"⚠️ OpenRouter key exhausted")
                                _or_exhausted.add(key)
                                break
            except Exception as e:
                print(f"⚠️ OpenRouter error: {str(e)[:100]}")
                continue
    
    raise QuotaExhaustedError("All OpenRouter keys exhausted")


# ══════════════════════════════════════════════════════════════════════════════
# 5️⃣ بدائل مجانية
# ══════════════════════════════════════════════════════════════════════════════

async def _generate_with_duckduckgo(prompt: str) -> str:
    """DuckDuckGo AI Chat - مجاني"""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Content-Type": "application/json",
            "Origin": "https://duckduckgo.com",
            "Referer": "https://duckduckgo.com/",
        }
        payload = {
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": prompt[:4000]}],
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://duckduckgo.com/duckchat/v1/chat",
                headers=headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=60),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("message", "")
    except Exception as e:
        print(f"⚠️ DuckDuckGo error: {e}")
    raise Exception("DuckDuckGo failed")


async def _generate_with_blackbox(prompt: str) -> str:
    """Blackbox AI - مجاني"""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Content-Type": "application/json",
        }
        payload = {
            "messages": [{"role": "user", "content": prompt[:4000]}],
            "model": "blackboxai",
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://www.blackbox.ai/api/chat",
                headers=headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=60),
            ) as resp:
                if resp.status == 200:
                    return await resp.text()
    except Exception as e:
        print(f"⚠️ Blackbox error: {e}")
    raise Exception("Blackbox failed")


async def _generate_with_free_fallback(prompt: str) -> str:
    """تجربة البدائل المجانية"""
    print("🆓 Trying free alternatives...")
    
    try:
        result = await _generate_with_duckduckgo(prompt)
        if result and len(result) > 100:
            print("✅ DuckDuckGo success (free)")
            return result
    except Exception:
        pass
    
    try:
        result = await _generate_with_blackbox(prompt)
        if result and len(result) > 100:
            print("✅ Blackbox AI success (free)")
            return result
    except Exception:
        pass
    
    raise QuotaExhaustedError("All free alternatives failed")


# ══════════════════════════════════════════════════════════════════════════════
# 🔄 دالة التوليد الرئيسية
# ══════════════════════════════════════════════════════════════════════════════
async def _generate_with_rotation(prompt: str, max_tokens: int = 8192) -> str:
    """
    تجرب الخدمات بالترتيب:
    1. DeepSeek → 2. Gemini → 3. Groq → 4. OpenRouter → 5. Free alternatives
    """
    errors = []
    
    # 1️⃣ DeepSeek
    if _deepseek_pool:
        try:
            print("🔄 Trying DeepSeek...")
            return await _generate_with_deepseek(prompt, max_tokens)
        except QuotaExhaustedError as e:
            errors.append(f"DeepSeek: {e}")
            print("⚠️ DeepSeek exhausted — switching to Gemini...")
    
    # 2️⃣ Gemini
    if _gemini_pool and GEMINI_AVAILABLE:
        try:
            print("🔄 Trying Gemini...")
            return await _generate_with_gemini(prompt, max_tokens)
        except QuotaExhaustedError as e:
            errors.append(f"Gemini: {e}")
            print("⚠️ Gemini exhausted — switching to Groq...")
    
    # 3️⃣ Groq
    if _groq_pool:
        try:
            print("🔄 Trying Groq...")
            return await _generate_with_groq(prompt, max_tokens)
        except QuotaExhaustedError as e:
            errors.append(f"Groq: {e}")
            print("⚠️ Groq exhausted — switching to OpenRouter...")
    
    # 4️⃣ OpenRouter
    if _or_pool:
        try:
            print("🔄 Trying OpenRouter...")
            return await _generate_with_openrouter(prompt, max_tokens)
        except QuotaExhaustedError as e:
            errors.append(f"OpenRouter: {e}")
            print("⚠️ OpenRouter exhausted — switching to free alternatives...")
    
    # 5️⃣ Free alternatives
    print("🔄 Trying free alternatives...")
    try:
        return await _generate_with_free_fallback(prompt)
    except QuotaExhaustedError as e:
        errors.append(f"Free: {e}")
    
    raise QuotaExhaustedError(f"All services exhausted: {' | '.join(errors[-3:])}")


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


def _clean_json_response(content: str) -> str:
    """تنظيف استجابة JSON من أي نص إضافي"""
    content = content.strip()
    
    # إزالة علامات markdown
    content = re.sub(r'^```json\s*', '', content)
    content = re.sub(r'^```\s*', '', content)
    content = re.sub(r'\s*```$', '', content)
    
    # البحث عن أول { وآخر }
    start_idx = content.find('{')
    end_idx = content.rfind('}')
    
    if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
        content = content[start_idx:end_idx + 1]
    
    return content.strip()


def _extract_valid_json(content: str) -> dict:
    """استخراج JSON صالح من النص"""
    content = _clean_json_response(content)
    
    # المحاولة الأولى: تحليل مباشر
    try:
        return json.loads(content)
    except json.JSONDecodeError as e:
        print(f"⚠️ JSON parse error: {e}")
    
    # المحاولة الثانية: إصلاح المشاكل الشائعة
    try:
        # إصلاح الفواصل الزائدة
        fixed = re.sub(r',\s*}', '}', content)
        fixed = re.sub(r',\s*]', ']', fixed)
        # إصلاح علامات التنصيص
        fixed = fixed.replace('"', '"').replace('"', '"')
        fixed = fixed.replace(''', "'").replace(''', "'")
        return json.loads(fixed)
    except json.JSONDecodeError:
        pass
    
    # المحاولة الثالثة: استخدام regex لاستخراج الأجزاء الرئيسية
    try:
        # استخراج عنوان المحاضرة
        title_match = re.search(r'"title"\s*:\s*"([^"]*)"', content)
        title = title_match.group(1) if title_match else "محاضرة"
        
        # استخراج نوع المحاضرة
        type_match = re.search(r'"lecture_type"\s*:\s*"([^"]*)"', content)
        lecture_type = type_match.group(1) if type_match else "other"
        
        # استخراج الملخص
        summary_match = re.search(r'"summary"\s*:\s*"([^"]*)"', content)
        summary = summary_match.group(1) if summary_match else ""
        
        # استخراج النقاط الرئيسية
        key_points = []
        kp_match = re.search(r'"key_points"\s*:\s*\[(.*?)\]', content, re.DOTALL)
        if kp_match:
            kp_text = kp_match.group(1)
            kp_items = re.findall(r'"([^"]*)"', kp_text)
            key_points = kp_items[:4]
        
        # بناء JSON أساسي
        return {
            "lecture_type": lecture_type,
            "title": title,
            "sections": [
                {
                    "title": f"القسم {i+1}",
                    "content": "محتوى القسم",
                    "keywords": ["مصطلح 1", "مصطلح 2", "مصطلح 3", "مصطلح 4"],
                    "keyword_images": ["educational cartoon", "educational cartoon", "educational cartoon", "educational cartoon"],
                    "narration": "نص الشرح",
                    "duration_estimate": 45
                }
                for i in range(3)
            ],
            "summary": summary,
            "key_points": key_points or ["نقطة 1", "نقطة 2", "نقطة 3", "نقطة 4"],
            "total_sections": 3
        }
    except Exception:
        pass
    
    # فشل كل شيء - إرجاع JSON افتراضي
    raise ValueError(f"Failed to parse JSON: {content[:300]}")


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
        summary_hint = "A clear, concise summary (4-5 sentences)"
        key_points_hint = '["Key point 1", "Key point 2", "Key point 3", "Key point 4"]'
        title_hint = "Lecture title"
        section_title_hint = "Section title"
        content_hint = f"Simplified content ({narration_sentences} sentences)"
        keywords_hint = '["keyword1", "keyword2", "keyword3", "keyword4"]'
        narration_hint = f"Full narration ({narration_sentences} sentences)"
        lang_note = "Write ALL text in English."
    else:
        summary_hint = "ملخص المحاضرة بأسلوب مبسط (4-5 جمل)"
        key_points_hint = '["نقطة رئيسية 1", "نقطة رئيسية 2", "نقطة رئيسية 3", "نقطة رئيسية 4"]'
        title_hint = "عنوان المحاضرة"
        section_title_hint = "عنوان القسم"
        content_hint = f"محتوى القسم المبسط ({narration_sentences} جمل)"
        keywords_hint = '["مصطلح رئيسي 1", "مصطلح رئيسي 2", "مصطلح رئيسي 3", "مصطلح رئيسي 4"]'
        narration_hint = f"نص الشرح الكامل ({narration_sentences} جمل)"
        lang_note = "النص يجب أن يكون باللهجة المطلوبة"

    prompt = f"""أنت معلم خبير. حلل المحاضرة وأرجع JSON فقط.

{instruction}

المحاضرة:
---
{text[:text_limit]}
---

أرجع JSON فقط بالتنسيق التالي (بالضبط {num_sections} أقسام):

{{
  "lecture_type": "medicine/science/math/literature/history/computer/business/other",
  "title": "{title_hint}",
  "sections": [
    {{
      "title": "{section_title_hint}",
      "content": "{content_hint}",
      "keywords": {keywords_hint},
      "keyword_images": ["cartoon visual 1", "cartoon visual 2", "cartoon visual 3", "cartoon visual 4"],
      "narration": "{narration_hint}",
      "duration_estimate": 45
    }}
  ],
  "summary": "{summary_hint}",
  "key_points": {key_points_hint},
  "total_sections": {num_sections}
}}

مهم: {num_sections} أقسام بالضبط. {lang_note} أرجع JSON فقط بدون أي نص إضافي."""

    # محاولة التحليل حتى 3 مرات
    for attempt in range(3):
        try:
            content = await _generate_with_rotation(prompt, max_tokens=8192)
            result = _extract_valid_json(content)
            
            # التحقق من وجود الأقسام
            if not result.get("sections"):
                result["sections"] = [
                    {
                        "title": f"القسم {i+1}" if not is_english else f"Section {i+1}",
                        "content": "محتوى القسم",
                        "keywords": ["مصطلح 1", "مصطلح 2", "مصطلح 3", "مصطلح 4"],
                        "keyword_images": ["educational", "educational", "educational", "educational"],
                        "narration": "نص الشرح",
                        "duration_estimate": 45
                    }
                    for i in range(num_sections)
                ]
            
            # التأكد من عدد الأقسام
            while len(result["sections"]) < num_sections:
                result["sections"].append({
                    "title": f"القسم {len(result['sections'])+1}",
                    "content": "محتوى إضافي",
                    "keywords": ["مصطلح"],
                    "keyword_images": ["educational"],
                    "narration": "نص الشرح",
                    "duration_estimate": 45
                })
            
            result["sections"] = result["sections"][:num_sections]
            result["total_sections"] = num_sections
            
            return result
            
        except Exception as e:
            print(f"⚠️ Analysis attempt {attempt + 1} failed: {e}")
            if attempt == 2:
                # آخر محاولة - إرجاع JSON افتراضي
                return {
                    "lecture_type": "other",
                    "title": "المحاضرة" if not is_english else "Lecture",
                    "sections": [
                        {
                            "title": f"القسم {i+1}" if not is_english else f"Section {i+1}",
                            "content": "محتوى القسم",
                            "keywords": ["مصطلح 1", "مصطلح 2", "مصطلح 3", "مصطلح 4"],
                            "keyword_images": ["educational", "educational", "educational", "educational"],
                            "narration": "نص الشرح الكامل للقسم",
                            "duration_estimate": 45
                        }
                        for i in range(num_sections)
                    ],
                    "summary": "ملخص المحاضرة" if not is_english else "Lecture summary",
                    "key_points": ["نقطة 1", "نقطة 2", "نقطة 3", "نقطة 4"],
                    "total_sections": num_sections
                }
            await asyncio.sleep(2)


# ══════════════════════════════════════════════════════════════════════════════
# 📄 استخراج النص من PDF
# ══════════════════════════════════════════════════════════════════════════════

async def extract_full_text_from_pdf(pdf_bytes: bytes) -> str:
    """استخراج النص الكامل من PDF"""
    try:
        import PyPDF2
        reader = PyPDF2.PdfReader(io.BytesIO(pdf_bytes))
        pages = []
        for page in reader.pages:
            page_text = page.extract_text() or ""
            if page_text.strip():
                pages.append(page_text)
        result = "\n\n".join(pages)
        if len(result) < 50:
            raise ValueError("النص المستخرج قصير جداً")
        return result
    except ImportError:
        raise ImportError("PyPDF2 غير مثبت. قم بتثبيته: pip install PyPDF2")
    except Exception as e:
        raise ValueError(f"فشل في استخراج النص من PDF: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# 🌐 استخراج النص من رابط URL
# ══════════════════════════════════════════════════════════════════════════════

def _is_safe_url(url: str) -> bool:
    """التحقق من أن الرابط آمن"""
    import ipaddress
    from urllib.parse import urlparse

    try:
        parsed = urlparse(url)
        if parsed.scheme not in ('http', 'https'):
            return False

        hostname = parsed.hostname or ''
        if not hostname:
            return False

        blocked_hosts = {'localhost', '127.0.0.1', '0.0.0.0', '::1'}
        if hostname.lower() in blocked_hosts:
            return False

        try:
            ip = ipaddress.ip_address(hostname)
            if ip.is_private or ip.is_loopback:
                return False
        except ValueError:
            pass

        return True
    except Exception:
        return False


async def extract_text_from_url(url: str) -> str:
    """استخراج النص من رابط"""
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        raise ImportError("BeautifulSoup غير مثبت. pip install beautifulsoup4")

    if not _is_safe_url(url):
        raise ValueError("الرابط غير مسموح به")

    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status != 200:
                    raise ValueError(f"HTTP {resp.status}")
                html = await resp.text()

        soup = BeautifulSoup(html, 'html.parser')
        for tag in soup(['script', 'style', 'nav', 'footer', 'header']):
            tag.decompose()

        text = soup.get_text(separator='\n', strip=True)
        lines = [line.strip() for line in text.split('\n') if line.strip() and len(line.strip()) > 20]
        
        if not lines:
            raise ValueError("لم يتم العثور على نص")
        
        result = '\n'.join(lines[:200])
        if len(result) < 100:
            raise ValueError("النص قصير جداً")
        
        return result
        
    except Exception as e:
        raise ValueError(f"خطأ في استخراج النص: {e}")
