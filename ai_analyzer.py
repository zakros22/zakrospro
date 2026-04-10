import json
import re
import io
import asyncio
import aiohttp
import random
import os
from PIL import Image as PILImage, ImageDraw, ImageFont
from google import genai
from google.genai import types as genai_types

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

print(f"🔑 Loaded {len(_google_keys)} Google API key(s)")

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
                print(f"✅ Google success with {model}")
                return response.text.strip()
            except Exception as e:
                err = str(e)
                if "429" in err or "RESOURCE_EXHAUSTED" in err or "quota" in err.lower():
                    print(f"⚠️ Google key exhausted")
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
                        print(f"✅ Groq success with {model}")
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
# استخراج الكلمات المفتاحية
# ──────────────────────────────────────────────────────────────────────────────

def _extract_keywords_from_text(text: str, max_words: int = 20) -> list:
    stop_words = {'و', 'في', 'من', 'على', 'إلى', 'أن', 'هو', 'هي', 'هذا', 'هذه', 'كان', 
                  'كانت', 'مع', 'ما', 'لا', 'عن', 'إذا', 'لم', 'لن', 'قد', 'ثم', 'أو', 
                  'أم', 'لكن', 'حتى', 'بل', 'كل', 'بعض', 'أي', 'تلك', 'ذلك', 'هؤلاء', 
                  'الذي', 'التي', 'الذين', 'ماذا', 'كيف', 'أين', 'متى', 'نحن', 'هم',
                  'the', 'a', 'an', 'is', 'are', 'was', 'were', 'of', 'to', 'in',
                  'that', 'it', 'be', 'for', 'on', 'with', 'as', 'at', 'by', 'this',
                  'and', 'or', 'but'}
    
    words = re.findall(r'[\u0600-\u06FF]{4,}|[a-zA-Z]{4,}', text)
    word_freq = {}
    for w in words:
        w_lower = w.lower()
        if w_lower not in stop_words:
            word_freq[w] = word_freq.get(w, 0) + 1
    
    sorted_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)
    return [w[0] for w in sorted_words[:max_words]]


def _detect_lecture_type(text: str) -> str:
    text_lower = text.lower()
    
    medical = ['مرض', 'علاج', 'طبيب', 'جراحة', 'دواء', 'تشخيص', 'مريض', 'عرض', 'قلب', 'دم', 'خلية', 'ورم', 'سرطان', 'endometriosis', 'cyst', 'inflammation', 'pain', 'bleeding', 'menstrual', 'pelvic']
    math = ['معادلة', 'دالة', 'تفاضل', 'تكامل', 'جبر', 'هندسة', 'عدد', 'متغير', 'رياضيات', 'equation', 'function', 'calculus', 'algebra']
    physics = ['قوة', 'طاقة', 'حركة', 'سرعة', 'تسارع', 'جاذبية', 'كهرباء', 'مغناطيس', 'فيزياء', 'force', 'energy', 'motion']
    chemistry = ['تفاعل', 'عنصر', 'مركب', 'جزيء', 'ذرة', 'حمض', 'قاعدة', 'كيمياء', 'reaction', 'element', 'compound']
    history = ['تاريخ', 'حرب', 'معركة', 'حضارة', 'إمبراطورية', 'ملك', 'ثورة', 'قرن', 'history', 'war', 'battle']
    biology = ['نبات', 'حيوان', 'بيئة', 'وراثة', 'حمض نووي', 'تطور', 'خلية', 'biology', 'plant', 'animal', 'cell']
    
    scores = {
        'medicine': sum(1 for kw in medical if kw in text_lower),
        'math': sum(1 for kw in math if kw in text_lower),
        'physics': sum(1 for kw in physics if kw in text_lower),
        'chemistry': sum(1 for kw in chemistry if kw in text_lower),
        'history': sum(1 for kw in history if kw in text_lower),
        'biology': sum(1 for kw in biology if kw in text_lower),
    }
    
    best_type = max(scores, key=scores.get)
    if scores[best_type] > 1:
        return best_type
    return 'other'


async def analyze_lecture(text: str, dialect: str = "msa") -> dict:
    """تحليل المحاضرة مع شرح مفصل"""
    
    extracted_keywords = _extract_keywords_from_text(text, 20)
    lecture_type = _detect_lecture_type(text)
    
    word_count = len(text.split())
    if word_count < 300:
        num_sections = 3
    elif word_count < 600:
        num_sections = 4
    elif word_count < 1000:
        num_sections = 5
    else:
        num_sections = 6
    
    text_limit = min(len(text), 4000)
    
    dialect_instructions = {
        "iraq": "باللهجة العراقية. اشرح كمعلم عراقي: استخدم (هواية، گلت، يعني، هسا، چي، شلون، أكو).",
        "egypt": "باللهجة المصرية. اشرح كمعلم مصري: استخدم (أوي، معلش، يعني، كده، عايز، النهارده).",
        "syria": "باللهجة الشامية. اشرح كمعلم سوري: استخدم (هلق، شو، كتير، منيح، هيك، عم).",
        "gulf": "باللهجة الخليجية. اشرح كمعلم خليجي: استخدم (زين، وايد، عاد، هاذي، أبشر).",
        "msa": "بالعربية الفصحى البسيطة والواضحة."
    }
    
    dialect_inst = dialect_instructions.get(dialect, dialect_instructions["msa"])

    prompt = f"""أنت معلم خبير ومتخصص في تبسيط المعلومات. مهمتك شرح المحاضرة التالية بشكل مفصل جداً.

**تعليمات مهمة:**
- {dialect_inst}
- اشرح كل مفهوم بالتفصيل (15-20 جملة لكل قسم)
- فسر المصطلحات العلمية بلغة بسيطة
- أعطِ أمثلة واقعية
- اربط بين المفاهيم

**المحاضرة:**
---
{text[:text_limit]}
---

**الكلمات المفتاحية المستخرجة:** {', '.join(extracted_keywords[:12])}

**المطلوب - {num_sections} أقسام:**

أرجع JSON فقط:

{{
  "lecture_type": "{lecture_type}",
  "title": "عنوان المحاضرة",
  "sections": [
    {{
      "title": "عنوان القسم",
      "keywords": ["كلمة1", "كلمة2", "كلمة3", "كلمة4"],
      "narration": "نص الشرح الصوتي الكامل والمفصل (15-20 جملة). اشرح هنا بالتفصيل. استخدم اللهجة المطلوبة.",
      "duration_estimate": 90
    }}
  ],
  "summary": "ملخص شامل (5-7 جمل)",
  "key_points": ["نقطة1", "نقطة2", "نقطة3", "نقطة4", "نقطة5"]
}}

**تنبيهات:**
- keywords: 4 كلمات مفتاحية لكل قسم.
- narration: اكتب شرحاً طويلاً ومفصلاً (15-20 جملة على الأقل).
- أرجع JSON فقط.
"""

    try:
        content = await _generate_with_rotation(prompt, max_output_tokens=8192)
        content = content.strip()
        content = re.sub(r'^```json\s*', '', content)
        content = re.sub(r'\s*```$', '', content)
        
        result = json.loads(content)
        
        if "title" not in result or not result["title"]:
            result["title"] = extracted_keywords[0] if extracted_keywords else "المحاضرة التعليمية"
        
        if "summary" not in result or not result["summary"]:
            result["summary"] = f"شرحنا في هذه المحاضرة: {', '.join(extracted_keywords[:5])}"
        
        if "key_points" not in result or not result["key_points"]:
            result["key_points"] = extracted_keywords[:5]
        
        if "lecture_type" not in result:
            result["lecture_type"] = lecture_type
        
        for i, section in enumerate(result.get("sections", [])):
            if "keywords" not in section or not section["keywords"] or len(section["keywords"]) < 4:
                start_idx = (i * 4) % len(extracted_keywords)
                section["keywords"] = []
                for j in range(4):
                    idx = (start_idx + j) % len(extracted_keywords)
                    if extracted_keywords[idx] not in section["keywords"]:
                        section["keywords"].append(extracted_keywords[idx])
            
            if "title" not in section or not section["title"]:
                section["title"] = section["keywords"][0] if section["keywords"] else f"القسم {i+1}"
            
            if "narration" not in section or not section["narration"]:
                kw_str = ', '.join(section.get('keywords', ['المفاهيم'])[:3])
                section["narration"] = f"في هذا القسم سنتعرف على {kw_str}. " * 12
            
            if "duration_estimate" not in section:
                section["duration_estimate"] = 90
            
            section["_keyword_images"] = [None] * 4
            section["_image_bytes"] = None
        
        print(f"✅ Analysis complete: {len(result.get('sections', []))} sections")
        return result
        
    except Exception as e:
        print(f"Analysis error: {e}, using fallback")
        
        sections = []
        for i in range(num_sections):
            start_idx = (i * 4) % len(extracted_keywords)
            kw = []
            for j in range(4):
                idx = (start_idx + j) % len(extracted_keywords)
                if extracted_keywords[idx] not in kw:
                    kw.append(extracted_keywords[idx])
            
            narration = f"في هذا القسم سنتعرف على {kw[0] if kw else 'المفاهيم الأساسية'}. " * 12
            
            sections.append({
                "title": kw[0] if kw else f"القسم {i+1}",
                "keywords": kw if kw else ["مفهوم", "تعريف", "شرح", "تحليل"],
                "narration": narration,
                "duration_estimate": 90,
                "_keyword_images": [None] * 4,
                "_image_bytes": None
            })
        
        return {
            "lecture_type": lecture_type,
            "title": extracted_keywords[0] if extracted_keywords else "المحاضرة التعليمية",
            "sections": sections,
            "summary": f"شرحنا في هذه المحاضرة: {', '.join(extracted_keywords[:5])}",
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
# توليد الصور - Picsum + صورة ملونة احتياطية
# ──────────────────────────────────────────────────────────────────────────────

async def _pollinations_generate(prompt: str) -> bytes | None:
    import urllib.parse
    clean_prompt = prompt[:200].replace("\n", " ")
    encoded = urllib.parse.quote(clean_prompt)
    url = f"https://image.pollinations.ai/prompt/{encoded}?width=400&height=300&nologo=true"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    raw = await resp.read()
                    if len(raw) > 5000:
                        return raw
    except Exception:
        pass
    return None


async def _picsum_generate() -> bytes | None:
    """موقع Picsum - صور عشوائية مجانية"""
    try:
        url = f"https://picsum.photos/400/300?random={random.randint(1, 1000)}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    return await resp.read()
    except Exception:
        pass
    return None


def _make_colored_image(keyword: str, lecture_type: str = "other") -> bytes:
    """صورة ملونة مكتوب عليها الكلمة المفتاحية"""
    W, H = 400, 300
    
    colors = {
        'medicine': (231, 76, 126),
        'math': (52, 152, 219),
        'physics': (52, 152, 219),
        'chemistry': (46, 204, 113),
        'history': (230, 126, 34),
        'biology': (46, 204, 113),
        'other': (155, 89, 182)
    }
    accent = colors.get(lecture_type, (231, 76, 126))
    
    img = PILImage.new("RGB", (W, H), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    
    # خلفية متدرجة بسيطة
    for y in range(H):
        t = y / H
        r = int(255 * (1 - t) + accent[0] * t * 0.3)
        g = int(255 * (1 - t) + accent[1] * t * 0.3)
        b = int(255 * (1 - t) + accent[2] * t * 0.3)
        draw.line([(0, y), (W, y)], fill=(r, g, b))
    
    # إطار
    draw.rounded_rectangle([(10, 10), (W-10, H-10)], radius=10, outline=accent, width=4)
    
    # دائرة في المنتصف
    draw.ellipse([(W//2-50, H//2-50), (W//2+50, H//2+50)], fill=(*accent, 30))
    
    try:
        font_path = os.path.join(os.path.dirname(__file__), "fonts", "Amiri-Bold.ttf")
        if os.path.exists(font_path):
            font = ImageFont.truetype(font_path, 28)
        else:
            font = ImageFont.load_default()
    except Exception:
        font = ImageFont.load_default()
    
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
        keyword_disp = get_display(arabic_reshaper.reshape(keyword[:20]))
    except Exception:
        keyword_disp = keyword[:20]
    
    # تقسيم النص الطويل
    words = keyword_disp.split()
    lines = []
    current = []
    for w in words:
        current.append(w)
        line = ' '.join(current)
        try:
            bbox = draw.textbbox((0, 0), line, font=font)
            if bbox[2] - bbox[0] > W - 40:
                current.pop()
                lines.append(' '.join(current))
                current = [w]
        except Exception:
            pass
    if current:
        lines.append(' '.join(current))
    
    y = H//2 - (len(lines) * 20)
    for line in lines:
        try:
            bbox = draw.textbbox((0, 0), line, font=font)
            tw = bbox[2] - bbox[0]
        except Exception:
            tw = len(line) * 15
        x = (W - tw) // 2
        draw.text((x+2, y+2), line, fill=(200, 200, 200), font=font)
        draw.text((x, y), line, fill=accent, font=font)
        y += 35
    
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=90)
    return buf.getvalue()


async def fetch_image_for_keyword(
    keyword: str,
    section_title: str,
    lecture_type: str,
    image_search_en: str = "",
) -> bytes:
    """جلب صورة للكلمة المفتاحية"""
    
    print(f"🖼️ Fetching image for: {keyword}")
    
    # 1. محاولة Pollinations
    prompt = f"simple educational illustration of {keyword}, clean style"
    img_bytes = await _pollinations_generate(prompt)
    if img_bytes:
        print(f"✅ Pollinations success for {keyword}")
        return img_bytes
    
    # 2. محاولة Picsum
    img_bytes = await _picsum_generate()
    if img_bytes:
        print(f"✅ Picsum fallback for {keyword}")
        return img_bytes
    
    # 3. صورة ملونة
    print(f"⚠️ Using colored placeholder for {keyword}")
    return _make_colored_image(keyword, lecture_type)
