#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import re
import io
import asyncio
import aiohttp
import random
from PIL import Image as PILImage, ImageDraw, ImageFont
from google import genai
from google.genai import types as genai_types
from config import (
    DEEPSEEK_API_KEYS, GEMINI_API_KEYS, OPENROUTER_API_KEYS, GROQ_API_KEYS, OPENAI_API_KEY
)

# ══════════════════════════════════════════════════════════════════════════════
#  نظام تبادل المفاتيح المتقدم
#  الأولوية: DeepSeek → Gemini → OpenRouter → Groq → DuckDuckGo → Blackbox
# ══════════════════════════════════════════════════════════════════════════════

class QuotaExhaustedError(Exception):
    """يُرفع عندما تنفد جميع المفاتيح من جميع المزودين."""
    pass


# ══════════════════════════════════════════════════════════════════════════════
#  مزود 1: DeepSeek (OpenAI-compatible)
# ══════════════════════════════════════════════════════════════════════════════
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
                        elif resp.status == 402:
                            print(f"⚠️ DeepSeek رصيد منتهي للمفتاح {key[:15]}...")
                            break
                        else:
                            body = await resp.text()
                            print(f"⚠️ DeepSeek {resp.status}: {body[:100]}")
                            continue
            except Exception as e:
                print(f"⚠️ DeepSeek خطأ: {str(e)[:80]}")
                continue
    raise QuotaExhaustedError("جميع مفاتيح DeepSeek منتهية")


# ══════════════════════════════════════════════════════════════════════════════
#  مزود 2: Gemini (Google)
# ══════════════════════════════════════════════════════════════════════════════
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
                    print(f"⚠️ Gemini حصة منتهية للمفتاح {key[:15]}...")
                    break
                else:
                    print(f"⚠️ Gemini خطأ: {err[:80]}")
                    continue
    raise QuotaExhaustedError("جميع مفاتيح Gemini منتهية")


# ══════════════════════════════════════════════════════════════════════════════
#  مزود 3: OpenRouter
# ══════════════════════════════════════════════════════════════════════════════
async def _generate_with_openrouter(prompt: str, max_tokens: int = 8192) -> str:
    """محاولة التوليد باستخدام مفاتيح OpenRouter."""
    if not OPENROUTER_API_KEYS:
        raise QuotaExhaustedError("لا توجد مفاتيح OpenRouter")

    models = [
        "deepseek/deepseek-r1:free",
        "deepseek/deepseek-chat:free",
        "google/gemini-2.0-flash-exp:free",
        "meta-llama/llama-3.3-70b-instruct:free",
        "qwen/qwen-2.5-72b-instruct:free",
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
                            print(f"⚠️ OpenRouter رصيد منتهي للمفتاح {key[:15]}...")
                            break
                        else:
                            continue
            except Exception as e:
                print(f"⚠️ OpenRouter خطأ: {str(e)[:80]}")
                continue
    raise QuotaExhaustedError("جميع مفاتيح OpenRouter منتهية")


# ══════════════════════════════════════════════════════════════════════════════
#  مزود 4: Groq
# ══════════════════════════════════════════════════════════════════════════════
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
                            print(f"⚠️ Groq حد الطلبات للمفتاح {key[:15]}...")
                            continue
                        else:
                            continue
            except Exception as e:
                print(f"⚠️ Groq خطأ: {str(e)[:80]}")
                continue
    raise QuotaExhaustedError("جميع مفاتيح Groq منتهية")


# ══════════════════════════════════════════════════════════════════════════════
#  مزود 5: DuckDuckGo AI Chat (مجاني تماماً - بدون مفتاح)
# ══════════════════════════════════════════════════════════════════════════════
async def _generate_with_duckduckgo(prompt: str, max_tokens: int = 8192) -> str:
    """
    استخدام DuckDuckGo AI Chat - مجاني تماماً وبدون مفتاح.
    يدعم نماذج متعددة: gpt-4o-mini, claude-3-haiku, llama-3.3-70b, mixtral-8x7b
    """
    models = ["gpt-4o-mini", "claude-3-haiku", "llama-3.3-70b", "mixtral-8x7b"]
    
    for model in models:
        try:
            # DuckDuckGo AI Chat API
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Content-Type": "application/json",
                "Origin": "https://duckduckgo.com",
                "Referer": "https://duckduckgo.com/",
            }
            
            # الحصول على VQD token
            async with aiohttp.ClientSession() as session:
                # الخطوة 1: الحصول على status
                async with session.get(
                    "https://duckduckgo.com/duckchat/v1/status",
                    headers={"User-Agent": headers["User-Agent"]},
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status != 200:
                        continue
                
                # الخطوة 2: إنشاء محادثة جديدة
                chat_payload = {
                    "model": model,
                    "messages": [{"role": "user", "content": prompt[:4000]}],
                }
                
                async with session.post(
                    "https://duckduckgo.com/duckchat/v1/chat",
                    headers=headers,
                    json=chat_payload,
                    timeout=aiohttp.ClientTimeout(total=60),
                ) as resp:
                    if resp.status == 200:
                        # قراءة الاستجابة المتدفقة
                        full_response = ""
                        async for line in resp.content:
                            if line:
                                try:
                                    line_text = line.decode('utf-8').strip()
                                    if line_text.startswith('data: '):
                                        data = json.loads(line_text[6:])
                                        if data.get("message"):
                                            full_response += data["message"]
                                except:
                                    pass
                        
                        if full_response.strip():
                            print(f"✅ DuckDuckGo نجاح: {model}")
                            return full_response.strip()
                    else:
                        print(f"⚠️ DuckDuckGo {model} فشل: {resp.status}")
                        continue
                        
        except Exception as e:
            print(f"⚠️ DuckDuckGo {model} خطأ: {str(e)[:80]}")
            continue
    
    raise QuotaExhaustedError("DuckDuckGo AI Chat فشل")


# ══════════════════════════════════════════════════════════════════════════════
#  مزود 6: Blackbox AI (مجاني - بدون مفتاح)
# ══════════════════════════════════════════════════════════════════════════════
async def _generate_with_blackbox(prompt: str, max_tokens: int = 8192) -> str:
    """استخدام Blackbox AI - مجاني وبدون مفتاح."""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Content-Type": "application/json",
            "Origin": "https://www.blackbox.ai",
            "Referer": "https://www.blackbox.ai/",
        }
        
        payload = {
            "messages": [{"role": "user", "content": prompt[:4000]}],
            "model": "blackboxai",
            "max_tokens": min(max_tokens, 4096),
            "temperature": 0.3,
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://www.blackbox.ai/api/chat",
                headers=headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=60),
            ) as resp:
                if resp.status == 200:
                    text = await resp.text()
                    if text and len(text) > 50:
                        print(f"✅ Blackbox AI نجاح")
                        return text.strip()
                else:
                    print(f"⚠️ Blackbox AI فشل: {resp.status}")
                    
    except Exception as e:
        print(f"⚠️ Blackbox AI خطأ: {str(e)[:80]}")
    
    raise QuotaExhaustedError("Blackbox AI فشل")


# ══════════════════════════════════════════════════════════════════════════════
#  مزود 7: Hugging Face Inference API (مجاني - نماذج متعددة)
# ══════════════════════════════════════════════════════════════════════════════
async def _generate_with_huggingface(prompt: str, max_tokens: int = 8192) -> str:
    """استخدام Hugging Face Inference API - بعض النماذج مجانية."""
    
    # نماذج مجانية على Hugging Face
    free_models = [
        "mistralai/Mistral-7B-Instruct-v0.2",
        "microsoft/Phi-3-mini-4k-instruct",
        "google/gemma-2b-it",
    ]
    
    for model in free_models:
        try:
            headers = {"Content-Type": "application/json"}
            payload = {
                "inputs": prompt[:2000],
                "parameters": {
                    "max_new_tokens": min(max_tokens, 2048),
                    "temperature": 0.3,
                    "return_full_text": False,
                }
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"https://api-inference.huggingface.co/models/{model}",
                    headers=headers,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=60),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if isinstance(data, list) and data:
                            text = data[0].get("generated_text", "")
                            if text.strip():
                                print(f"✅ HuggingFace نجاح: {model}")
                                return text.strip()
                    else:
                        print(f"⚠️ HuggingFace {model} فشل: {resp.status}")
                        continue
                        
        except Exception as e:
            print(f"⚠️ HuggingFace {model} خطأ: {str(e)[:80]}")
            continue
    
    raise QuotaExhaustedError("HuggingFace فشل")


# ══════════════════════════════════════════════════════════════════════════════
#  الدالة الرئيسية للتوليد (تدوير تلقائي بين جميع المزودين)
# ══════════════════════════════════════════════════════════════════════════════
async def _generate_with_rotation(prompt: str, max_output_tokens: int = 8192) -> str:
    """
    تدوير تلقائي بين المزودين حسب الأولوية:
    1. DeepSeek
    2. Gemini
    3. OpenRouter
    4. Groq
    5. DuckDuckGo (مجاني - بدون مفتاح)
    6. Blackbox AI (مجاني - بدون مفتاح)
    7. HuggingFace (مجاني)
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

    # 5. DuckDuckGo AI (مجاني - بدون مفتاح)
    print("🔄 تجربة DuckDuckGo AI (مجاني)...")
    try:
        return await _generate_with_duckduckgo(prompt, max_output_tokens)
    except QuotaExhaustedError as e:
        errors.append(f"DuckDuckGo: {e}")

    # 6. Blackbox AI (مجاني - بدون مفتاح)
    print("🔄 تجربة Blackbox AI (مجاني)...")
    try:
        return await _generate_with_blackbox(prompt, max_output_tokens)
    except QuotaExhaustedError as e:
        errors.append(f"Blackbox: {e}")

    # 7. HuggingFace (مجاني)
    print("🔄 تجربة HuggingFace (مجاني)...")
    try:
        return await _generate_with_huggingface(prompt, max_output_tokens)
    except QuotaExhaustedError as e:
        errors.append(f"HuggingFace: {e}")

    raise QuotaExhaustedError(f"جميع المزودين منتهين: {' | '.join(errors)}")


# ══════════════════════════════════════════════════════════════════════════════
#  تحليل المحاضرة
# ══════════════════════════════════════════════════════════════════════════════
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
- keyword_images: مصفوفة من 4 عناصر - لكل كلمة مفتاحية وصف إنجليزي قصير (3-5 كلمات) لصورة كرتونية بسيطة
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


# ══════════════════════════════════════════════════════════════════════════════
#  استخراج النص من PDF
# ══════════════════════════════════════════════════════════════════════════════
async def extract_full_text_from_pdf(pdf_bytes: bytes) -> str:
    import PyPDF2
    reader = PyPDF2.PdfReader(io.BytesIO(pdf_bytes))
    pages = []
    for page in reader.pages:
        page_text = page.extract_text() or ""
        if page_text.strip():
            pages.append(page_text)
    return "\n\n".join(pages)


# ══════════════════════════════════════════════════════════════════════════════
#  توليد الصور - Pollinations.ai (مجاني وسريع)
# ══════════════════════════════════════════════════════════════════════════════
async def _pollinations_generate(prompt: str) -> bytes | None:
    """توليد صورة باستخدام Pollinations.ai - مجاني وسريع."""
    import urllib.parse
    
    clean_prompt = prompt[:380].replace("\n", " ")
    seed = random.randint(1, 99999)
    encoded = urllib.parse.quote(clean_prompt)
    
    # استخدام نموذج flux للحصول على صور كرتونية تعليمية
    url = f"https://image.pollinations.ai/prompt/{encoded}?width=854&height=480&nologo=true&seed={seed}&model=flux"
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                if resp.status == 200:
                    raw = await resp.read()
                    if len(raw) > 5000:
                        pil_img = PILImage.open(io.BytesIO(raw)).convert("RGB")
                        pil_img = pil_img.resize((854, 480), PILImage.LANCZOS)
                        buf = io.BytesIO()
                        pil_img.save(buf, "JPEG", quality=85)
                        print(f"✅ Pollinations صورة: {len(buf.getvalue())//1024}KB")
                        return buf.getvalue()
    except Exception as e:
        print(f"⚠️ Pollinations خطأ: {str(e)[:60]}")
    
    return None


# ══════════════════════════════════════════════════════════════════════════════
#  توليد الصور - Picsum (صور توضيحية احتياطية)
# ══════════════════════════════════════════════════════════════════════════════
async def _picsum_generate(keyword: str) -> bytes | None:
    """صور توضيحية من Picsum - مجاني."""
    try:
        # استخدام seed مستقر لكل كلمة
        seed = sum(ord(c) for c in keyword) % 1000
        url = f"https://picsum.photos/seed/{seed}/854/480"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status == 200:
                    raw = await resp.read()
                    if len(raw) > 5000:
                        print(f"✅ Picsum صورة احتياطية لـ: {keyword[:20]}")
                        return raw
    except Exception as e:
        print(f"⚠️ Picsum خطأ: {str(e)[:60]}")
    
    return None


# ══════════════════════════════════════════════════════════════════════════════
#  توليد صورة احتياطية (كرت تعليمي)
# ══════════════════════════════════════════════════════════════════════════════
def _make_placeholder_image(keywords: list, lecture_type: str = "other") -> bytes:
    """إنشاء كرت تعليمي احتياطي."""
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

    # تدرج لوني
    for x in range(W):
        t = x / W
        r = int(bg1[0] * (1 - t) + bg2[0] * t)
        g = int(bg1[1] * (1 - t) + bg2[1] * t)
        b = int(bg1[2] * (1 - t) + bg2[2] * t)
        draw.line([(x, 0), (x, H)], fill=(r, g, b))

    # النص الرئيسي
    keyword_raw = (keywords[0] if keywords else "").strip()
    
    try:
        # محاولة استخدام خط عربي
        font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        font = ImageFont.truetype(font_path, 50)
    except:
        font = ImageFont.load_default()

    # رسم النص
    bbox = draw.textbbox((0, 0), keyword_raw, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(((W - tw) // 2, (H - th) // 2), keyword_raw, fill=(255, 255, 255), font=font)
    
    # إطار
    draw.rectangle([(10, 10), (W-10, H-10)], outline=accent, width=3)

    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=85)
    return buf.getvalue()


# ══════════════════════════════════════════════════════════════════════════════
#  الدالة الرئيسية لجلب صورة لكلمة مفتاحية
# ══════════════════════════════════════════════════════════════════════════════
async def fetch_image_for_keyword(
    keyword: str,
    section_title: str,
    lecture_type: str,
    image_search_en: str = "",
) -> bytes:
    """
    جلب صورة تعليمية للكلمة المفتاحية.
    
    Pipeline:
    1. Pollinations.ai (مجاني - AI)
    2. Picsum (صور توضيحية احتياطية)
    3. كرت تعليمي (صورة مولدة محلياً)
    """
    subject = (image_search_en or keyword).strip()
    
    # بناء prompt للصورة
    prompt = f"educational cartoon illustration of {subject}, simple clean style, white background, no text"
    
    # 1. محاولة Pollinations.ai
    img_bytes = await _pollinations_generate(prompt)
    if img_bytes:
        return img_bytes
    
    # 2. محاولة Picsum
    img_bytes = await _picsum_generate(keyword)
    if img_bytes:
        return img_bytes
    
    # 3. كرت تعليمي احتياطي
    return _make_placeholder_image([keyword, section_title], lecture_type)
