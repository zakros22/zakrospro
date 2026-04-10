import json
import re
import io
import asyncio
import aiohttp
import os
from PIL import Image as PILImage, ImageDraw, ImageFont
from google import genai
from google.genai import types as genai_types

# ─────────────────────────────────────────────────────────────────────────────
# تحميل مفاتيح Google
# ─────────────────────────────────────────────────────────────────────────────

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

# ─────────────────────────────────────────────────────────────────────────────
# تحميل مفاتيح Groq
# ─────────────────────────────────────────────────────────────────────────────

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
                        temperature=0.4,
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
    
    for key in _groq_keys:
        for model in ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"]:
            try:
                headers = {
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                }
                payload = {
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": min(max_tokens, 8192),
                    "temperature": 0.4,
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
            except:
                continue
    
    raise Exception("Groq failed")


async def _generate_with_rotation(prompt: str, max_output_tokens: int = 8192) -> str:
    if _google_keys:
        try:
            return await _generate_with_google(prompt, max_output_tokens)
        except:
            pass
    
    if _groq_keys:
        try:
            return await _generate_with_groq(prompt, max_output_tokens)
        except:
            pass
    
    raise Exception("All AI services failed")


def _extract_keywords(text: str, max_words: int = 20) -> list:
    stop_words = {'و', 'في', 'من', 'على', 'إلى', 'أن', 'هو', 'هي', 'هذا', 'هذه', 'كان', 
                  'كانت', 'مع', 'ما', 'لا', 'عن', 'إذا', 'لم', 'لن', 'قد', 'ثم', 'أو', 
                  'أم', 'لكن', 'حتى', 'بل', 'كل', 'بعض', 'the', 'a', 'an', 'is', 'are',
                  'was', 'were', 'of', 'to', 'in', 'that', 'it', 'be', 'for', 'on',
                  'with', 'as', 'at', 'by', 'this', 'and', 'or', 'but'}
    
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
    
    medical = ['مرض', 'علاج', 'طبيب', 'جراحة', 'دواء', 'تشخيص', 'مريض', 'قلب', 'دم', 'خلية', 'ورم', 'سرطان', 'endometriosis', 'cyst', 'inflammation', 'pain', 'bleeding', 'menstrual']
    math = ['معادلة', 'دالة', 'تفاضل', 'تكامل', 'جبر', 'هندسة', 'رياضيات', 'equation', 'function', 'calculus', 'algebra']
    physics = ['قوة', 'طاقة', 'حركة', 'سرعة', 'جاذبية', 'كهرباء', 'مغناطيس', 'فيزياء', 'force', 'energy', 'motion']
    chemistry = ['تفاعل', 'عنصر', 'مركب', 'جزيء', 'ذرة', 'حمض', 'قاعدة', 'كيمياء', 'reaction', 'element', 'compound']
    history = ['تاريخ', 'حرب', 'معركة', 'حضارة', 'إمبراطورية', 'ملك', 'ثورة', 'history', 'war', 'battle']
    biology = ['نبات', 'حيوان', 'بيئة', 'وراثة', 'تطور', 'خلية', 'biology', 'plant', 'animal', 'cell']
    
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
    """تحليل المحاضرة وإنشاء شرح احترافي"""
    
    all_keywords = _extract_keywords(text, 30)
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
    
    text_preview = text[:4000]
    
    # شخصية المعلم حسب النوع
    teacher_styles = {
        'medicine': 'أنت طبيب استشاري تشرح لطلاب الطب. اشرح pathophysiology والأعراض والتشخيص والعلاج.',
        'math': 'أنت أستاذ رياضيات. اشرح المعادلات خطوة بخطوة مع أمثلة.',
        'physics': 'أنت فيزيائي. اشرح القوانين وطبقها على أمثلة واقعية.',
        'chemistry': 'أنت كيميائي. اشرح التفاعلات والمعادلات الكيميائية.',
        'history': 'أنت مؤرخ. اسرد الأحداث التاريخية وحلل الأسباب والنتائج.',
        'biology': 'أنت عالم أحياء. اشرح العمليات الحيوية والتركيب والوظيفة.',
        'other': 'أنت معلم خبير. بسط المفاهيم واشرحها بوضوح.'
    }
    
    teacher_style = teacher_styles.get(lecture_type, teacher_styles['other'])
    
    dialect_instructions = {
        "iraq": "باللهجة العراقية. استخدم: هواية، گلت، هسا، چي، شلون، أكو.",
        "egypt": "باللهجة المصرية. استخدم: أوي، معلش، كده، عايز، النهارده.",
        "syria": "باللهجة الشامية. استخدم: هلق، شو، كتير، منيح، هيك.",
        "gulf": "باللهجة الخليجية. استخدم: زين، وايد، عاد، هاذي، أبشر.",
        "msa": "بالعربية الفصحى البسيطة والواضحة."
    }
    
    dialect_inst = dialect_instructions.get(dialect, dialect_instructions["msa"])

    prompt = f"""{teacher_style}
تكلم {dialect_inst}

**النص الأصلي:**
---
{text_preview}
---

**الكلمات المفتاحية:** {', '.join(all_keywords[:15])}

**المطلوب:**
1. عنوان مناسب للمحاضرة
2. للأقسام الـ {num_sections}:
   - عنوان القسم
   - 4 كلمات مفتاحية
   - شرح كامل (15-20 جملة) - هذا أهم جزء!

أرجع JSON:
{{
  "title": "عنوان المحاضرة",
  "sections": [
    {{
      "title": "عنوان القسم",
      "keywords": ["ك1", "ك2", "ك3", "ك4"],
      "narration": "نص الشرح الكامل (15-20 جملة). اشرح هنا بالتفصيل. لا تكرر النص الأصلي - أضف شرحك الخاص."
    }}
  ]
}}

اكتب شرحاً احترافياً مفصلاً في narration. هذا هو الجزء الأهم!"""

    try:
        content = await _generate_with_rotation(prompt, max_output_tokens=8192)
        content = content.strip()
        content = re.sub(r'^```json\s*', '', content)
        content = re.sub(r'\s*```$', '', content)
        
        result = json.loads(content)
        title = result.get("title", all_keywords[0] if all_keywords else "المحاضرة التعليمية")
        ai_sections = result.get("sections", [])
        
    except Exception as e:
        print(f"AI analysis failed: {e}")
        title = all_keywords[0] if all_keywords else "المحاضرة التعليمية"
        ai_sections = []

    final_sections = []
    for i in range(num_sections):
        if i < len(ai_sections):
            section = ai_sections[i]
            keywords = section.get("keywords", [])[:4]
            section_title = section.get("title", f"القسم {i+1}")
            narration = section.get("narration", "")
        else:
            start_idx = (i * 4) % len(all_keywords)
            keywords = []
            for j in range(4):
                idx = (start_idx + j) % len(all_keywords)
                if all_keywords[idx] not in keywords:
                    keywords.append(all_keywords[idx])
            section_title = keywords[0] if keywords else f"القسم {i+1}"
            narration = ""
        
        # إذا ماكو شرح، ننشئ شرح افتراضي
        if not narration:
            kw_str = ', '.join(keywords[:3]) if keywords else 'المفاهيم'
            narration = f"في هذا القسم سنتعرف على {kw_str}. " * 12
        
        final_sections.append({
            "title": section_title,
            "keywords": keywords if keywords else ["مفهوم", "تعريف", "شرح", "تحليل"],
            "narration": narration,
            "duration_estimate": max(45, len(narration.split()) // 3),
            "_keyword_images": [None] * 4,
            "_image_bytes": None
        })
    
    return {
        "lecture_type": lecture_type,
        "title": title,
        "sections": final_sections,
        "summary": f"شرحنا في هذه المحاضرة: {', '.join(all_keywords[:8])}",
        "key_points": all_keywords[:5],
        "all_keywords": all_keywords
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


# ─────────────────────────────────────────────────────────────────────────────
# توليد الصور
# ─────────────────────────────────────────────────────────────────────────────

def _get_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ]
    for p in font_paths:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except:
                pass
    return ImageFont.load_default()


def _make_colored_image(keyword: str, color: tuple) -> bytes:
    W, H = 400, 300
    
    img = PILImage.new("RGB", (W, H), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    
    for y in range(H):
        t = y / H
        r = int(255 * (1 - t) + color[0] * t * 0.2)
        g = int(255 * (1 - t) + color[1] * t * 0.2)
        b = int(255 * (1 - t) + color[2] * t * 0.2)
        draw.line([(0, y), (W, y)], fill=(r, g, b))
    
    draw.rounded_rectangle([(8, 8), (W-8, H-8)], radius=15, outline=color, width=6)
    draw.ellipse([(W//2-50, H//2-50), (W//2+50, H//2+50)], fill=(*color, 30))
    
    font = _get_font(28, bold=True)
    
    words = keyword.split()
    lines = []
    current = []
    for w in words:
        current.append(w)
        line = ' '.join(current)
        try:
            bbox = font.getbbox(line)
            if bbox[2] - bbox[0] > W - 60:
                current.pop()
                lines.append(' '.join(current))
                current = [w]
        except:
            pass
    if current:
        lines.append(' '.join(current))
    
    y = H//2 - (len(lines) * 40)//2
    for line in lines:
        try:
            bbox = font.getbbox(line)
            tw = bbox[2] - bbox[0]
        except:
            tw = len(line) * 16
        x = (W - tw) // 2
        draw.text((x+2, y+2), line, fill=(200, 200, 200), font=font)
        draw.text((x, y), line, fill=color, font=font)
        y += 45
    
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=90)
    return buf.getvalue()


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
    except:
        pass
    return None


async def fetch_image_for_keyword(
    keyword: str,
    section_title: str,
    lecture_type: str,
    image_search_en: str = "",
) -> bytes:
    colors = {
        'medicine': (231, 76, 126),
        'math': (52, 152, 219),
        'physics': (52, 152, 219),
        'chemistry': (46, 204, 113),
        'history': (230, 126, 34),
        'biology': (46, 204, 113),
        'other': (155, 89, 182)
    }
    color = colors.get(lecture_type, (231, 76, 126))
    
    prompt = f"simple educational illustration of {keyword}, clean white background"
    img_bytes = await _pollinations_generate(prompt)
    if img_bytes:
        return img_bytes
    
    return _make_colored_image(keyword, color)
