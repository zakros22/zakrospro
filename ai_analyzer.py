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
# استخراج الكلمات المفتاحية
# ──────────────────────────────────────────────────────────────────────────────

def _extract_keywords_from_text(text: str, max_words: int = 12) -> list:
    """استخراج الكلمات المفتاحية من النص"""
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
    """تحديد نوع المحاضرة"""
    text_lower = text.lower()
    
    medical = ['مرض', 'علاج', 'طبيب', 'جراحة', 'دواء', 'تشخيص', 'مريض', 'عرض', 'قلب', 'دم', 'خلية', 'ورم', 'سرطان', 'endometriosis', 'cyst', 'inflammation', 'pain', 'bleeding', 'menstrual', 'pelvic', 'diagnosis', 'symptom', 'treatment', 'surgery', 'medicine', 'disease', 'heart', 'blood', 'cell', 'cancer', 'chronic', 'acute']
    math = ['معادلة', 'دالة', 'تفاضل', 'تكامل', 'جبر', 'هندسة', 'عدد', 'متغير', 'رياضيات', 'equation', 'function', 'calculus', 'algebra', 'geometry', 'variable', 'math', 'derivative', 'integral']
    physics = ['قوة', 'طاقة', 'حركة', 'سرعة', 'تسارع', 'جاذبية', 'كهرباء', 'مغناطيس', 'فيزياء', 'force', 'energy', 'motion', 'velocity', 'gravity', 'physics', 'quantum', 'wave', 'particle']
    chemistry = ['تفاعل', 'عنصر', 'مركب', 'جزيء', 'ذرة', 'حمض', 'قاعدة', 'كيمياء', 'reaction', 'element', 'compound', 'molecule', 'atom', 'chemistry', 'bond', 'acid', 'base']
    history = ['تاريخ', 'حرب', 'معركة', 'حضارة', 'إمبراطورية', 'ملك', 'ثورة', 'قرن', 'قديم', 'history', 'war', 'battle', 'civilization', 'empire', 'revolution', 'ancient', 'king', 'dynasty']
    biology = ['نبات', 'حيوان', 'بيئة', 'وراثة', 'حمض نووي', 'تطور', 'خلية', 'biology', 'plant', 'animal', 'evolution', 'dna', 'gene', 'species', 'cell', 'tissue', 'organ']
    
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


def _get_teacher_persona(lecture_type: str, dialect: str) -> str:
    """تحديد شخصية المعلم حسب نوع المحاضرة"""
    
    personas = {
        'medicine': {
            'name': 'دكتور/ة',
            'style': 'طبيب استشاري يشرح لطلاب الطب',
            'instructions': '''
اشرح بأسلوب طبي واضح ومبسط.
لكل قسم:
- اذكر المصطلح الطبي (بالعربي والإنجليزي)
- اشرح pathophysiology بشكل مبسط
- اذكر الأعراض والعلامات
- اشرح الأسباب والمضاعفات
استخدم جمل قصيرة وواضحة تصلح للعرض على السبورة.
            '''
        },
        'math': {
            'name': 'أستاذ/ة رياضيات',
            'style': 'معلم رياضيات يشرح على السبورة',
            'instructions': '''
اشرح المعادلات خطوة بخطوة.
لكل قسم:
- اكتب المعادلة بوضوح
- اشرح كل متغير
- أعطِ مثالاً عددياً
- اشرح التطبيق العملي
            '''
        },
        'physics': {
            'name': 'أستاذ/ة فيزياء',
            'style': 'فيزيائي يشرح القوانين الطبيعية',
            'instructions': '''
اشرح القوانين الفيزيائية.
لكل قسم:
- اذكر القانون
- اشرح الوحدات
- أعطِ مثالاً تطبيقياً
- اربط بالظواهر اليومية
            '''
        },
        'chemistry': {
            'name': 'أستاذ/ة كيمياء',
            'style': 'كيميائي يشرح التفاعلات',
            'instructions': '''
اشرح التفاعلات الكيميائية.
لكل قسم:
- اكتب المعادلة الكيميائية
- اشرح المواد المتفاعلة والناتجة
- اذكر شروط التفاعل
- اشرح التطبيقات
            '''
        },
        'history': {
            'name': 'أستاذ/ة تاريخ',
            'style': 'مؤرخ يسرد الأحداث',
            'instructions': '''
اسرد الأحداث التاريخية كقصة.
لكل قسم:
- اذكر الحدث الرئيسي
- اذكر الشخصيات المهمة
- اذكر التاريخ والمكان
- اشرح الأسباب والنتائج
            '''
        },
        'biology': {
            'name': 'أستاذ/ة أحياء',
            'style': 'عالم أحياء يشرح الكائنات الحية',
            'instructions': '''
اشرح المفاهيم البيولوجية.
لكل قسم:
- اذكر اسم الكائن/العملية
- اشرح التركيب والوظيفة
- اذكر الأهمية البيئية/الطبية
- استخدم التشبيهات
            '''
        },
        'other': {
            'name': 'أستاذ/ة',
            'style': 'معلم خبير',
            'instructions': '''
اشرح المفاهيم بوضوح.
لكل قسم:
- اذكر المفهوم الرئيسي
- اشرحه بلغة بسيطة
- أعطِ مثالاً
- اذكر التطبيقات
            '''
        }
    }
    
    dialect_style = {
        'iraq': 'باللهجة العراقية الدارجة. استخدم: هواية، گلت، يعني، هسا، چي، شلون، أكو.',
        'egypt': 'باللهجة المصرية. استخدم: أوي، معلش، يعني، كده، عايز، النهارده.',
        'syria': 'باللهجة الشامية. استخدم: هلق، شو، كتير، منيح، هيك، عم.',
        'gulf': 'باللهجة الخليجية. استخدم: زين، وايد، عاد، هاذي، أبشر.',
        'msa': 'بالعربية الفصحى البسيطة والواضحة.'
    }
    
    persona = personas.get(lecture_type, personas['other'])
    dialect_inst = dialect_style.get(dialect, dialect_style['msa'])
    
    return f"""
أنت {persona['name']} {persona['style']}.
{persona['instructions']}
تكلم {dialect_inst}
"""


async def analyze_lecture(text: str, dialect: str = "msa") -> dict:
    """تحليل المحاضرة بأسلوب Osmosis"""
    
    # استخراج الكلمات المفتاحية
    extracted_keywords = _extract_keywords_from_text(text, 16)
    
    # تحديد نوع المحاضرة
    lecture_type = _detect_lecture_type(text)
    
    # تحديد عدد الأقسام
    word_count = len(text.split())
    if word_count < 300:
        num_sections = 3
    elif word_count < 600:
        num_sections = 4
    elif word_count < 1000:
        num_sections = 5
    else:
        num_sections = 6
    
    teacher_persona = _get_teacher_persona(lecture_type, dialect)
    text_limit = min(len(text), 4000)

    prompt = f"""{teacher_persona}

**المحاضرة المطلوب شرحها:**
---
{text[:text_limit]}
---

**نوع المحاضرة:** {lecture_type}
**الكلمات المفتاحية المستخرجة:** {', '.join(extracted_keywords[:12])}

**المطلوب - أنشئ {num_sections} أقسام:**

أرجع JSON فقط:

{{
  "lecture_type": "{lecture_type}",
  "title": "عنوان المحاضرة (عنوان جذاب ومناسب)",
  "sections": [
    {{
      "title": "عنوان القسم (عنوان قصير وواضح)",
      "keywords": ["كلمة1", "كلمة2", "كلمة3", "كلمة4"],
      "osmosis_items": [
        {{
          "type": "text",
          "content": "النص العربي المراد عرضه على السبورة",
          "color": "pink/blue/green/purple/orange",
          "size": 24,
          "bold": true
        }},
        {{
          "type": "arrow",
          "from": "الكلمة السابقة",
          "to": "الكلمة التالية",
          "color": "pink"
        }}
      ],
      "narration": "نص الشرح الصوتي الكامل (10-15 جملة) - هذا ما سينطقه المعلم",
      "duration_estimate": 60
    }}
  ],
  "summary": "ملخص شامل (5-7 جمل)",
  "key_points": ["نقطة1", "نقطة2", "نقطة3", "نقطة4", "نقطة5"]
}}

**تعليمات مهمة:**
1. keywords: 4 كلمات مفتاحية لكل قسم من القائمة أعلاه.
2. narration: اكتب شرحاً صوتياً كاملاً باللهجة المطلوبة (10-15 جملة).
3. title: اجعله قصيراً وواضحاً.
4. أرجع JSON فقط.
"""

    try:
        content = await _generate_with_rotation(prompt, max_output_tokens=8192)
        content = content.strip()
        content = re.sub(r'^```json\s*', '', content)
        content = re.sub(r'\s*```$', '', content)
        
        result = json.loads(content)
        
        # التأكد من وجود الحقول الأساسية
        if "title" not in result or not result["title"]:
            result["title"] = extracted_keywords[0] if extracted_keywords else "المحاضرة التعليمية"
        
        if "summary" not in result or not result["summary"]:
            result["summary"] = f"شرحنا في هذه المحاضرة: {', '.join(extracted_keywords[:5])}"
        
        if "key_points" not in result or not result["key_points"]:
            result["key_points"] = extracted_keywords[:5]
        
        if "lecture_type" not in result:
            result["lecture_type"] = lecture_type
        
        # معالجة الأقسام
        for i, section in enumerate(result.get("sections", [])):
            # الكلمات المفتاحية
            if "keywords" not in section or not section["keywords"] or len(section["keywords"]) < 4:
                start_idx = (i * 4) % len(extracted_keywords)
                section["keywords"] = []
                for j in range(4):
                    idx = (start_idx + j) % len(extracted_keywords)
                    if extracted_keywords[idx] not in section["keywords"]:
                        section["keywords"].append(extracted_keywords[idx])
            
            # العنوان
            if "title" not in section or not section["title"]:
                section["title"] = section["keywords"][0] if section["keywords"] else f"القسم {i+1}"
            
            # الشرح الصوتي
            if "narration" not in section or not section["narration"]:
                kw_str = ', '.join(section.get('keywords', ['المفاهيم'])[:3])
                section["narration"] = f"في هذا القسم سنتعرف على {kw_str}. " * 8
            
            # مدة تقديرية
            if "duration_estimate" not in section:
                section["duration_estimate"] = 60
            
            # إعدادات الصور
            section["_keyword_images"] = [None] * 4
            section["_image_bytes"] = None
        
        return result
        
    except Exception as e:
        print(f"Analysis error: {e}")
        
        # إنشاء بيانات افتراضية
        sections = []
        for i in range(num_sections):
            start_idx = (i * 4) % len(extracted_keywords)
            kw = []
            for j in range(4):
                idx = (start_idx + j) % len(extracted_keywords)
                if extracted_keywords[idx] not in kw:
                    kw.append(extracted_keywords[idx])
            
            narration = f"في هذا القسم سنتعرف على {kw[0] if kw else 'المفاهيم الأساسية'}. " * 10
            
            sections.append({
                "title": kw[0] if kw else f"القسم {i+1}",
                "keywords": kw if kw else ["مفهوم", "تعريف", "شرح", "تحليل"],
                "narration": narration,
                "duration_estimate": 60,
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
# توليد الصور بأسلوب Osmosis
# ──────────────────────────────────────────────────────────────────────────────

async def _pollinations_generate(prompt: str) -> bytes | None:
    import urllib.parse
    clean_prompt = prompt[:200].replace("\n", " ")
    encoded = urllib.parse.quote(clean_prompt)
    url = f"https://image.pollinations.ai/prompt/{encoded}?width=400&height=300&nologo=true&model=flux"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status == 200:
                    raw = await resp.read()
                    if len(raw) > 5000:
                        pil_img = PILImage.open(io.BytesIO(raw)).convert("RGB")
                        buf = io.BytesIO()
                        pil_img.save(buf, "JPEG", quality=85)
                        return buf.getvalue()
    except Exception:
        pass
    return None


def _make_osmosis_style_image(keyword: str, lecture_type: str = "medicine") -> bytes:
    """صورة بأسلوب Osmosis البسيط"""
    W, H = 300, 200
    
    # ألوان Osmosis
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
    
    # إطار بسيط
    draw.rounded_rectangle([(5, 5), (W-5, H-5)], radius=8, outline=accent, width=3)
    
    # دائرة في الخلفية
    draw.ellipse([(W//2-40, H//2-40), (W//2+40, H//2+40)], fill=(*accent, 20))
    
    try:
        font_path = os.path.join(os.path.dirname(__file__), "fonts", "Amiri-Bold.ttf")
        if os.path.exists(font_path):
            font = ImageFont.truetype(font_path, 24)
        else:
            font = ImageFont.load_default()
    except Exception:
        font = ImageFont.load_default()
    
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
        keyword_disp = get_display(arabic_reshaper.reshape(keyword[:15]))
    except Exception:
        keyword_disp = keyword[:15]
    
    try:
        bbox = draw.textbbox((0, 0), keyword_disp, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    except Exception:
        tw, th = len(keyword_disp) * 15, 30
    
    x = (W - tw) // 2
    y = (H - th) // 2
    
    draw.text((x+1, y+1), keyword_disp, fill=(200, 200, 200), font=font)
    draw.text((x, y), keyword_disp, fill=accent, font=font)
    
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=90)
    return buf.getvalue()


async def fetch_image_for_keyword(
    keyword: str,
    section_title: str,
    lecture_type: str,
    image_search_en: str = "",
) -> bytes:
    """جلب صورة بأسلوب Osmosis"""
    
    # أوصاف حسب نوع المحاضرة
    prompts = {
        'medicine': f"simple medical illustration of {keyword}, osmosis style, clean white background, minimal colors",
        'math': f"simple math diagram of {keyword}, educational style, clean white background",
        'physics': f"simple physics diagram of {keyword}, educational illustration, clean white background",
        'chemistry': f"simple chemistry illustration of {keyword}, educational style, clean white background",
        'history': f"simple historical illustration of {keyword}, educational style, clean white background",
        'biology': f"simple biology diagram of {keyword}, osmosis style, clean white background",
        'other': f"simple educational illustration of {keyword}, clean white background, minimal style"
    }
    
    prompt = prompts.get(lecture_type, prompts['other'])
    
    # محاولة Pollinations
    img_bytes = await _pollinations_generate(prompt)
    if img_bytes:
        return img_bytes
    
    # محاولة ثانية بوصف أبسط
    simple_prompt = f"simple cartoon {keyword}, white background, minimal"
    img_bytes = await _pollinations_generate(simple_prompt)
    if img_bytes:
        return img_bytes
    
    # صورة احتياطية بأسلوب Osmosis
    return _make_osmosis_style_image(keyword, lecture_type)
