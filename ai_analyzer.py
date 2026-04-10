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
# استخراج الكلمات المفتاحية من النص
# ──────────────────────────────────────────────────────────────────────────────

def _extract_keywords_from_text(text: str, max_words: int = 8) -> list:
    """استخراج الكلمات المفتاحية من النص العربي"""
    stop_words = {'و', 'في', 'من', 'على', 'إلى', 'أن', 'هو', 'هي', 'هذا', 'هذه', 'كان', 
                  'كانت', 'مع', 'ما', 'لا', 'عن', 'إذا', 'لم', 'لن', 'قد', 'ثم', 'أو', 
                  'أم', 'لكن', 'حتى', 'بل', 'كل', 'بعض', 'أي', 'تلك', 'ذلك', 'هؤلاء', 
                  'الذي', 'التي', 'الذين', 'ماذا', 'كيف', 'أين', 'متى', 'نحن', 'هم'}
    
    words = re.findall(r'[\u0600-\u06FF]{4,}', text)
    word_freq = {}
    for w in words:
        if w not in stop_words:
            word_freq[w] = word_freq.get(w, 0) + 1
    
    sorted_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)
    return [w[0] for w in sorted_words[:max_words]]


# ──────────────────────────────────────────────────────────────────────────────
# التحليل العميق للمحاضرة
# ──────────────────────────────────────────────────────────────────────────────

async def analyze_lecture(text: str, dialect: str = "msa") -> dict:
    """تحليل عميق للمحاضرة مع شرح مفصل للمفاهيم والمعادلات"""
    
    # استخراج الكلمات المفتاحية
    extracted_keywords = _extract_keywords_from_text(text, 10)
    
    # تحديد عدد الأقسام حسب طول النص
    word_count = len(text.split())
    if word_count < 400:
        num_sections = 3
    elif word_count < 800:
        num_sections = 4
    elif word_count < 1500:
        num_sections = 5
    elif word_count < 2500:
        num_sections = 6
    else:
        num_sections = 7
    
    dialect_instructions = {
        "iraq": "استخدم اللهجة العراقية الأصيلة. اشرح بطريقة المعلم العراقي: (هواية، گلت، يعني، بس، هسا، چي، شلون، وين، أكو، ماكو). خلي الشرح وافي ومفصل.",
        "egypt": "استخدم اللهجة المصرية. اشرح بطريقة المعلم المصري: (أوي، معلش، يعني، كده، عايز، بتاع، النهارده، بكره). خلي الشرح وافي ومفصل.",
        "syria": "استخدم اللهجة الشامية. اشرح بطريقة المعلم السوري: (هلق، شو، كتير، منيح، هيك، عم، فيكن). خلي الشرح وافي ومفصل.",
        "gulf": "استخدم اللهجة الخليجية. اشرح بطريقة المعلم الخليجي: (زين، وايد، عاد، هاذي، أبشر، شفيك، ليش). خلي الشرح وافي ومفصل.",
        "msa": "استخدم العربية الفصحى البسيطة والواضحة. اشرح كمعلم متمكن يبسط المعلومات للطلاب.",
    }
    
    instruction = dialect_instructions.get(dialect, dialect_instructions["msa"])
    
    text_limit = min(len(text), 5000)

    prompt = f"""أنت معلم خبير ومتخصص في تبسيط العلوم والرياضيات. مهمتك شرح المحاضرة التالية بشكل مفصل وعميق جداً.

{instruction}

**المحاضرة:**
---
{text[:text_limit]}
---

**الكلمات المفتاحية المستخرجة:** {', '.join(extracted_keywords[:8])}

**تعليمات مهمة جداً:**

1. **حلل النص بعمق**: اقرأ المحاضرة جيداً وافهم كل مفهوم.
2. **اشرح المعادلات الرياضية**: إذا وجدت معادلات، اشرحها خطوة بخطوة. فسر كل رمز وماذا يعني.
3. **فسر المصطلحات العلمية**: كل مصطلح معقد، اشرحه بلغة بسيطة مع مثال.
4. **اربط الأفكار**: وضح كيف ترتبط المفاهيم ببعضها.
5. **أعطِ أمثلة واقعية**: لكل مفهوم، أعطِ مثالاً من الحياة اليومية.
6. **الشرح يجب أن يكون طويلاً ووافياً**: لا تختصر! اشرح كل جزئية بالتفصيل.
7. **استخدم أسلوب المعلم**: كأنك تشرح لطلاب أمامك في الفصل.

**المطلوب:**
أنشئ {num_sections} أقسام تعليمية. كل قسم يجب أن يحتوي على شرح مفصل جداً (15-20 جملة).

أرجع JSON فقط بالتنسيق التالي:

{{
  "lecture_type": "medicine/science/math/physics/chemistry/biology/engineering/computer/business/literature/history/other",
  "title": "عنوان المحاضرة (عنوان جذاب وواضح)",
  "sections": [
    {{
      "title": "عنوان القسم",
      "content": "ملخص مختصر للقسم (3-4 جمل)",
      "keywords": ["كلمة1", "كلمة2", "كلمة3", "كلمة4"],
      "keyword_images": [
        "وصف إنجليزي لصورة كرتونية تعبر عن الكلمة الأولى (3-5 كلمات)",
        "وصف إنجليزي لصورة كرتونية تعبر عن الكلمة الثانية (3-5 كلمات)",
        "وصف إنجليزي لصورة كرتونية تعبر عن الكلمة الثالثة (3-5 كلمات)",
        "وصف إنجليزي لصورة كرتونية تعبر عن الكلمة الرابعة (3-5 كلمات)"
      ],
      "narration": "نص الشرح الكامل والمفصل (15-20 جملة). اشرح كل مفهوم، فسر المعادلات، أعطِ أمثلة، اربط الأفكار. استخدم اللهجة المطلوبة.",
      "duration_estimate": 90
    }}
  ],
  "summary": "ملخص شامل للمحاضرة (6-8 جمل) يذكر أهم النقاط التي تم شرحها",
  "key_points": ["النقطة الرئيسية الأولى", "النقطة الرئيسية الثانية", "النقطة الرئيسية الثالثة", "النقطة الرئيسية الرابعة", "النقطة الرئيسية الخامسة"]
}}

**تنبيهات:**
- اكتب نصوصاً طويلة ومفصلة في narration (15-20 جملة على الأقل لكل قسم).
- اشرح المعادلات الرياضية خطوة بخطوة.
- فسر كل المصطلحات العلمية.
- استخدم الكلمات المفتاحية من القائمة أعلاه.
- أرجع JSON فقط بدون أي نص إضافي.
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
            result["summary"] = "تم شرح المفاهيم الأساسية في هذه المحاضرة بشكل مفصل."
        if "key_points" not in result or not result["key_points"]:
            result["key_points"] = extracted_keywords[:5]
        
        # التأكد من وجود كلمات مفتاحية وشرح في كل قسم
        for i, section in enumerate(result.get("sections", [])):
            if "keywords" not in section or not section["keywords"]:
                start_idx = (i * 4) % len(extracted_keywords)
                section["keywords"] = []
                for j in range(4):
                    idx = (start_idx + j) % len(extracted_keywords)
                    if extracted_keywords[idx] not in section["keywords"]:
                        section["keywords"].append(extracted_keywords[idx])
            
            if "narration" not in section or not section["narration"]:
                section["narration"] = section.get("content", "شرح مفصل للقسم") * 5
            
            if "keyword_images" not in section or not section["keyword_images"]:
                section["keyword_images"] = [
                    f"educational illustration of {kw}" for kw in section.get("keywords", ["concept"])[:4]
                ]
            
            if "title" not in section or not section["title"]:
                section["title"] = f"القسم {i+1}: {section.get('keywords', [''])[0]}"
        
        return result
        
    except Exception as e:
        print(f"Analysis error: {e}")
        
        # إنشاء بيانات افتراضية مفصلة
        sections = []
        for i in range(num_sections):
            start_idx = (i * 4) % len(extracted_keywords)
            kw = []
            for j in range(4):
                idx = (start_idx + j) % len(extracted_keywords)
                if extracted_keywords[idx] not in kw:
                    kw.append(extracted_keywords[idx])
            
            # نص شرح افتراضي طويل
            if kw:
                narration = (
                    f"في هذا القسم سنتعرف على {kw[0]}. "
                    f"{kw[0]} هو مفهوم مهم جداً في مجالنا. "
                    f"لنفهم {kw[0]} بشكل أفضل، دعونا ننظر إلى تعريفه أولاً. "
                    f"ثم ننتقل إلى {kw[1]} الذي يرتبط ارتباطاً وثيقاً بـ {kw[0]}. "
                    f"العلاقة بين {kw[0]} و {kw[1]} هي علاقة تكاملية. "
                    f"بعد ذلك، سنتناول {kw[2]} ونرى كيف يؤثر على النتائج. "
                    f"وأخيراً، سنختتم بـ {kw[3]} الذي يوضح التطبيق العملي. "
                ) * 3
            else:
                narration = "شرح مفصل للمفاهيم الأساسية في هذا القسم. " * 8
            
            sections.append({
                "title": f"القسم {i+1}: {kw[0] if kw else 'المفاهيم الأساسية'}",
                "content": f"شرح مفصل عن {', '.join(kw[:2]) if kw else 'المفاهيم'}",
                "keywords": kw if kw else ["مفهوم", "تعريف", "شرح", "تحليل"],
                "keyword_images": [f"educational illustration of {k}" for k in (kw if kw else ["concept"])[:4]],
                "narration": narration,
                "duration_estimate": 90
            })
        
        return {
            "lecture_type": "other",
            "title": extracted_keywords[0] if extracted_keywords else "المحاضرة التعليمية",
            "sections": sections,
            "summary": "شرحنا في هذه المحاضرة " + "، ".join(extracted_keywords[:5]) if extracted_keywords else "المفاهيم الأساسية",
            "key_points": extracted_keywords[:5] if extracted_keywords else ["نقطة1", "نقطة2", "نقطة3", "نقطة4", "نقطة5"]
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
# توليد الصور
# ──────────────────────────────────────────────────────────────────────────────

async def _pollinations_generate(prompt: str) -> bytes | None:
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
                        return buf.getvalue()
    except Exception:
        pass
    return None


async def _picsum_generate() -> bytes | None:
    try:
        url = f"https://picsum.photos/854/480?random={random.randint(1, 1000)}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    return await resp.read()
    except Exception:
        pass
    return None


def _make_placeholder_image(keyword: str, section_title: str = "") -> bytes:
    W, H = 854, 480
    img = PILImage.new("RGB", (W, H), (30, 40, 70))
    draw = ImageDraw.Draw(img)
    
    for y in range(H):
        t = y / H
        r = int(30 * (1 - t) + 60 * t)
        g = int(40 * (1 - t) + 80 * t)
        b = int(70 * (1 - t) + 120 * t)
        draw.line([(0, y), (W, y)], fill=(r, g, b))
    
    draw.rectangle([(20, 20), (W-20, H-20)], outline=(255, 200, 50), width=3)
    
    try:
        font_path = os.path.join(os.path.dirname(__file__), "fonts", "Amiri-Bold.ttf")
        if os.path.exists(font_path):
            font = ImageFont.truetype(font_path, 50)
        else:
            font = ImageFont.load_default()
    except Exception:
        font = ImageFont.load_default()
    
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
        keyword_disp = get_display(arabic_reshaper.reshape(keyword))
    except Exception:
        keyword_disp = keyword
    
    try:
        bbox = draw.textbbox((0, 0), keyword_disp, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    except Exception:
        tw, th = len(keyword_disp) * 30, 50
    
    x = (W - tw) // 2
    y = (H - th) // 2 - 30
    
    draw.text((x+3, y+3), keyword_disp, fill=(0, 0, 0), font=font)
    draw.text((x, y), keyword_disp, fill=(255, 220, 50), font=font)
    
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=90)
    return buf.getvalue()


async def fetch_image_for_keyword(
    keyword: str,
    section_title: str,
    lecture_type: str,
    image_search_en: str = "",
) -> bytes:
    subject = image_search_en if image_search_en else keyword.strip()
    
    prompt_en = f"educational cartoon illustration of {subject}, simple clean style, white background"
    prompt_ar = f"رسم توضيحي تعليمي بسيط عن {keyword}، خلفية بيضاء، أسلوب كرتوني نظيف"
    
    # محاولة Pollinations مع وصف عربي
    img_bytes = await _pollinations_generate(prompt_ar)
    if img_bytes:
        return img_bytes
    
    # محاولة Pollinations مع وصف إنجليزي
    img_bytes = await _pollinations_generate(prompt_en)
    if img_bytes:
        return img_bytes
    
    # محاولة Picsum
    img_bytes = await _picsum_generate()
    if img_bytes:
        return img_bytes
    
    # صورة احتياطية
    return _make_placeholder_image(keyword, section_title)
