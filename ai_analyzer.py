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
                        temperature=0.7,  # زيادة الإبداع لمنع التكرار
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
                    "temperature": 0.7,
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


def _extract_keywords_from_text(text: str, max_words: int = 20) -> list:
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
    """تحليل المحاضرة مع شرح متنوع غير مكرر"""
    
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
    
    text_limit = min(len(text), 5000)
    
    teacher_styles = {
        'medicine': 'أنت طبيب استشاري تشرح لطلاب الطب. استخدم لغة طبية دقيقة. اشرح الأعراض، الأسباب، التشخيص، والعلاج. أعط أمثلة واقعية.',
        'math': 'أنت أستاذ رياضيات. اشرح المعادلات خطوة بخطوة مع أمثلة عددية. فسر كل متغير.',
        'physics': 'أنت فيزيائي. اشرح القوانين وطبقها على أمثلة من الحياة اليومية.',
        'chemistry': 'أنت كيميائي. اشرح التفاعلات والمعادلات الكيميائية وظروفها.',
        'history': 'أنت مؤرخ. اسرد الأحداث التاريخية بتسلسل زمني مع تحليل الأسباب والنتائج.',
        'biology': 'أنت عالم أحياء. اشرح التركيب والوظيفة والعمليات الحيوية.',
        'other': 'أنت معلم خبير. بسط المفاهيم المعقدة وأعط أمثلة من الحياة.'
    }
    
    teacher_style = teacher_styles.get(lecture_type, teacher_styles['other'])
    
    dialect_instructions = {
        "iraq": "باللهجة العراقية: استخدم (هواية، گلت، هسا، چي، شلون، أكو، ماكو).",
        "egypt": "باللهجة المصرية: استخدم (أوي، معلش، كده، عايز، النهارده، يا جماعة).",
        "syria": "باللهجة الشامية: استخدم (هلق، شو، كتير، منيح، هيك، عم، فيكن).",
        "gulf": "باللهجة الخليجية: استخدم (زين، وايد، عاد، هاذي، أبشر، يالحبيب).",
        "msa": "بالعربية الفصحى البسيطة والواضحة."
    }
    
    dialect_inst = dialect_instructions.get(dialect, dialect_instructions["msa"])

    prompt = f"""{teacher_style}

**تعليمات صارمة للشرح:**
- {dialect_inst}
- اكتب شرحاً كاملاً ومتنوعاً. كل جملة يجب أن تضيف معلومة جديدة.
- لا تكرر نفس الجملة أبداً. لا تستخدم "يعني يعني" أو "هو هو".
- فسر المصطلحات العلمية. أعط أمثلة واقعية.
- اربط بين المفاهيم بشكل منطقي.

**المحاضرة:**
---
{text[:text_limit]}
---

**الكلمات المفتاحية:** {', '.join(extracted_keywords[:12])}

**المطلوب - {num_sections} أقسام:**

أرجع JSON فقط:

{{
  "title": "عنوان المحاضرة",
  "sections": [
    {{
      "title": "عنوان القسم",
      "keywords": ["كلمة1", "كلمة2", "كلمة3", "كلمة4"],
      "terms_en": ["term1", "term2", "term3", "term4"],
      "narration": "نص الشرح الصوتي الكامل (15-20 جملة متنوعة). لا تكرر الجمل."
    }}
  ],
  "summary": "ملخص شامل (5-7 جمل)"
}}

- keywords: 4 كلمات مفتاحية عربية.
- terms_en: المصطلحات الإنجليزية المقابلة (إن وجدت).
- narration: شرح كامل ومتنوع.
- أرجع JSON فقط.
"""

    try:
        content = await _generate_with_rotation(prompt, max_output_tokens=8192)
        content = content.strip()
        content = re.sub(r'^```json\s*', '', content)
        content = re.sub(r'\s*```$', '', content)
        
        result = json.loads(content)
        
        if "title" not in result:
            result["title"] = extracted_keywords[0] if extracted_keywords else "المحاضرة التعليمية"
        
        if "summary" not in result:
            result["summary"] = f"شرحنا: {', '.join(extracted_keywords[:5])}"
        
        for i, section in enumerate(result.get("sections", [])):
            if "keywords" not in section or not section["keywords"]:
                start_idx = (i * 4) % len(extracted_keywords)
                section["keywords"] = []
                for j in range(4):
                    idx = (start_idx + j) % len(extracted_keywords)
                    if extracted_keywords[idx] not in section["keywords"]:
                        section["keywords"].append(extracted_keywords[idx])
            
            if "terms_en" not in section:
                section["terms_en"] = []
            
            if "title" not in section:
                section["title"] = section["keywords"][0] if section["keywords"] else f"القسم {i+1}"
            
            if "narration" not in section or len(section["narration"]) < 100:
                kw_str = ', '.join(section.get('keywords', ['المفاهيم'])[:3])
                section["narration"] = f"دعونا نتعرف على {kw_str}. " * 12
        
        return result
        
    except Exception as e:
        print(f"Analysis error: {e}")
        
        sections = []
        for i in range(num_sections):
            start_idx = (i * 4) % len(extracted_keywords)
            kw = []
            for j in range(4):
                idx = (start_idx + j) % len(extracted_keywords)
                if extracted_keywords[idx] not in kw:
                    kw.append(extracted_keywords[idx])
            
            sections.append({
                "title": kw[0] if kw else f"القسم {i+1}",
                "keywords": kw if kw else ["مفهوم", "تعريف", "شرح", "تحليل"],
                "terms_en": [],
                "narration": f"دعونا نتعرف على {kw[0] if kw else 'المفاهيم'}. " * 12
            })
        
        return {
            "title": extracted_keywords[0] if extracted_keywords else "المحاضرة التعليمية",
            "sections": sections,
            "summary": f"شرحنا: {', '.join(extracted_keywords[:5])}"
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
# توليد الصور - صور ملونة مضمونة
# ─────────────────────────────────────────────────────────────────────────────

def _make_keyword_image(keyword: str, color: tuple, term_en: str = "") -> bytes:
    """إنشاء صورة تعليمية ملونة تحمل الكلمة المفتاحية"""
    W, H = 400, 300
    
    img = PILImage.new("RGB", (W, H), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    
    # خلفية متدرجة
    for y in range(H):
        t = y / H
        r = int(255 * (1 - t) + color[0] * t * 0.2)
        g = int(255 * (1 - t) + color[1] * t * 0.2)
        b = int(255 * (1 - t) + color[2] * t * 0.2)
        draw.line([(0, y), (W, y)], fill=(r, g, b))
    
    # إطار
    draw.rounded_rectangle([(8, 8), (W-8, H-8)], radius=12, outline=color, width=5)
    
    # دائرة
    draw.ellipse([(W//2-55, H//2-55), (W//2+55, H//2+55)], fill=(*color, 30))
    
    try:
        font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        if os.path.exists(font_path):
            font = ImageFont.truetype(font_path, 32)
        else:
            font = ImageFont.load_default()
    except:
        font = ImageFont.load_default()
    
    # تحضير النص العربي
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
        keyword_disp = get_display(arabic_reshaper.reshape(keyword[:20]))
    except:
        keyword_disp = keyword[:20]
    
    # تقسيم النص
    words = keyword_disp.split()
    lines = []
    current = []
    for w in words:
        current.append(w)
        line = ' '.join(current)
        try:
            bbox = font.getbbox(line)
            if bbox[2] - bbox[0] > W - 40:
                current.pop()
                lines.append(' '.join(current))
                current = [w]
        except:
            pass
    if current:
        lines.append(' '.join(current))
    
    y = H//2 - (len(lines) * 35)//2 - 10
    for line in lines:
        try:
            bbox = font.getbbox(line)
            tw = bbox[2] - bbox[0]
        except:
            tw = len(line) * 18
        x = (W - tw) // 2
        draw.text((x+2, y+2), line, fill=(200, 200, 200), font=font)
        draw.text((x, y), line, fill=color, font=font)
        y += 40
    
    # المصطلح الإنجليزي
    if term_en:
        try:
            font_en = ImageFont.truetype(font_path, 18) if os.path.exists(font_path) else ImageFont.load_default()
        except:
            font_en = font
        term_disp = term_en[:30]
        try:
            bbox = font_en.getbbox(term_disp)
            tw = bbox[2] - bbox[0]
        except:
            tw = len(term_disp) * 10
        x = (W - tw) // 2
        draw.text((x, y + 15), term_disp, fill=(100, 100, 100), font=font_en)
    
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=90)
    return buf.getvalue()


async def fetch_image_for_keyword(
    keyword: str,
    section_title: str,
    lecture_type: str,
    image_search_en: str = "",
) -> bytes:
    """إرجاع صورة ملونة تحمل الكلمة المفتاحية (مضمونة 100%)"""
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
    return _make_keyword_image(keyword, color, image_search_en)
