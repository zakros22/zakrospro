# -*- coding: utf-8 -*-
import json
import re
import io
import asyncio
import aiohttp
import os
import random
from PIL import Image as PILImage, ImageDraw, ImageFont
from google import genai
from google.genai import types as genai_types

# ═══════════════════════════════════════════════════════════════════════════════
# دالة تنظيف النص من null bytes والأحرف غير المرغوبة
# ═══════════════════════════════════════════════════════════════════════════════

def _clean_text(text: str) -> str:
    """تنظيف النص من جميع الأحرف غير المرغوبة"""
    if not text:
        return ""
    text = text.replace('\x00', '').replace('\0', '')
    text = re.sub(r'[\x01-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


# ═══════════════════════════════════════════════════════════════════════════════
# 1. تحميل مفاتيح Google Gemini
# ═══════════════════════════════════════════════════════════════════════════════

def _load_google_keys():
    keys = []
    raw_keys = os.getenv("GOOGLE_API_KEYS", "")
    if raw_keys:
        for k in raw_keys.split(","):
            k = k.strip()
            if k and k not in keys:
                keys.append(k)
    
    for i in range(1, 10):
        key = os.getenv(f"GOOGLE_API_KEY_{i}", "").strip()
        if key and key not in keys:
            keys.append(key)
    
    single_key = os.getenv("GOOGLE_API_KEY", "").strip()
    if single_key and single_key not in keys:
        keys.append(single_key)
    
    return keys

_google_keys = _load_google_keys()
_current_google_idx = 0
_exhausted_google_keys = set()

print(f"[INFO] Loaded {len(_google_keys)} Google API key(s)")

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
    remaining = len(_google_keys) - len(_exhausted_google_keys)
    print(f"[WARN] Google key exhausted. {remaining} remaining.")

# ═══════════════════════════════════════════════════════════════════════════════
# 2. تحميل مفاتيح Groq (احتياطي)
# ═══════════════════════════════════════════════════════════════════════════════

def _load_groq_keys():
    keys = []
    raw_keys = os.getenv("GROQ_API_KEYS", "")
    if raw_keys:
        for k in raw_keys.split(","):
            k = k.strip()
            if k and k not in keys:
                keys.append(k)
    
    single_key = os.getenv("GROQ_API_KEY", "").strip()
    if single_key and single_key not in keys:
        keys.append(single_key)
    
    return keys

_groq_keys = _load_groq_keys()
print(f"[INFO] Loaded {len(_groq_keys)} Groq API key(s)")

_GROQ_MODELS = [
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "gemma2-9b-it",
]

# ═══════════════════════════════════════════════════════════════════════════════
# 3. دوال الاتصال بالـ APIs
# ═══════════════════════════════════════════════════════════════════════════════

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
                        temperature=0.7,
                        max_output_tokens=max_tokens,
                    ),
                )
                print(f"[OK] Google success with {model}")
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
                            print(f"[OK] Groq success with {model}")
                            return data["choices"][0]["message"]["content"].strip()
            except:
                continue
    
    raise Exception("Groq failed")


async def _generate_with_rotation(prompt: str, max_output_tokens: int = 8192) -> str:
    if _google_keys:
        try:
            return await _generate_with_google(prompt, max_output_tokens)
        except Exception as e:
            print(f"[WARN] Google failed: {e}")
    
    if _groq_keys:
        try:
            return await _generate_with_groq(prompt, max_output_tokens)
        except Exception as e:
            print(f"[WARN] Groq failed: {e}")
    
    raise Exception("All AI services failed")


# ═══════════════════════════════════════════════════════════════════════════════
# 4. استخراج الكلمات المفتاحية
# ═══════════════════════════════════════════════════════════════════════════════

def _extract_keywords(text: str, max_words: int = 30) -> list:
    text = _clean_text(text)
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
    text = _clean_text(text)
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


def _generate_fallback_narration(keywords: list, lecture_type: str) -> str:
    kw_str = '، '.join(keywords[:3])
    
    narrations = {
        'medicine': f"دعونا نتحدث عن {kw_str}. هذا الموضوع مهم جداً في المجال الطبي. أولاً، يجب أن نفهم تعريف كل مصطلح. ثانياً، نناقش الأعراض والعلامات المرتبطة. ثالثاً، نستعرض طرق التشخيص المتاحة. رابعاً، نتعرف على خيارات العلاج الحديثة. خامساً، نتحدث عن المضاعفات المحتملة. سادساً، نناقش طرق الوقاية. سابعاً، نستعرض أحدث الأبحاث في هذا المجال. ثامناً، نذكر بعض الحالات السريرية. تاسعاً، نجيب على الأسئلة الشائعة. وأخيراً، نلخص أهم النقاط التي يجب تذكرها.",
        'math': f"الآن سنشرح {kw_str} بالتفصيل. لنبدأ بتعريف كل مفهوم. ثم نكتب المعادلة الرياضية ونحللها خطوة بخطوة. بعد ذلك، نعطي مثالاً عددياً لتوضيح الفكرة. ثم نتحقق من صحة الحل. ننتقل إلى تطبيقات هذه المعادلة في الحياة العملية. نناقش أيضاً الحالات الخاصة والشروط اللازمة. نختم ببعض التمارين للتأكد من الفهم. تذكروا دائماً أن التدريب هو مفتاح إتقان الرياضيات.",
        'physics': f"في هذا القسم ندرس {kw_str}. الفيزياء علم جميل يفسر الظواهر من حولنا. نبدأ بشرح القانون الفيزيائي الأساسي. ثم نعرض تجربة عملية توضح هذا القانون. نحلل النتائج ونستنتج العلاقات بين المتغيرات. نربط هذه المفاهيم بحياتنا اليومية. مثلاً، نرى تطبيقات هذا القانون في حركة السيارات أو سقوط الأجسام. نناقش أيضاً حدود تطبيق هذا القانون والحالات التي لا ينطبق فيها. أخيراً، نلخص أهم ما تعلمناه.",
        'chemistry': f"نتعرف الآن على {kw_str} في الكيمياء. نبدأ بكتابة المعادلة الكيميائية الموزونة. نحدد المواد المتفاعلة والناتجة. نشرح شروط التفاعل مثل درجة الحرارة والضغط والمواد الحفازة. نحسب كمية المواد المتفاعلة والناتجة باستخدام الحسابات الكيميائية. نذكر تطبيقات هذا التفاعل في الصناعة. نناقش أيضاً المخاطر المحتملة وطرق التعامل الآمن مع المواد الكيميائية. نختم بمراجعة سريعة لأهم النقاط.",
        'history': f"اليوم سنسافر عبر الزمن لنتعرف على {kw_str}. التاريخ يعلمنا دروساً قيمة من الماضي. نبدأ بذكر التاريخ والمكان الذي وقعت فيه الأحداث. نتعرف على الشخصيات الرئيسية وأدوارها. نسرد الأحداث بتسلسل زمني واضح. نحلل الأسباب التي أدت إلى هذه الأحداث. نناقش النتائج والآثار التي ترتبت عليها. نستخلص الدروس والعبر المستفادة. نختم بربط هذه الأحداث بالواقع المعاصر.",
        'biology': f"في علم الأحياء، ندرس {kw_str}. الحياة مليئة بالأسرار الرائعة. نبدأ بشرح التركيب الأساسي. ثم ننتقل إلى الوظائف الحيوية التي يؤديها. نستخدم التشبيهات لتقريب المفاهيم. مثلاً، نشبه الخلية بالمصنع الصغير. نناقش أيضاً أهمية هذه العمليات للحفاظ على الحياة. نذكر بعض الأمراض المرتبطة بخلل هذه الوظائف. نختم بمراجعة سريعة وتلخيص لأهم المعلومات.",
        'other': f"مرحباً بكم في هذا القسم الذي سنتعرف فيه على {kw_str}. هذا الموضوع مهم جداً ويستحق التركيز. نبدأ بتعريف المصطلحات الأساسية. ثم نستعرض المعلومات بالتفصيل مع أمثلة توضيحية. نربط هذه المعلومات بالواقع العملي. نجيب على الأسئلة الشائعة حول هذا الموضوع. نذكر بعض النصائح والإرشادات المفيدة. أخيراً، نلخص أهم ما تم شرحه في هذا القسم."
    }
    
    return narrations.get(lecture_type, narrations['other'])


# ═══════════════════════════════════════════════════════════════════════════════
# 5. الدالة الرئيسية: تحليل المحاضرة
# ═══════════════════════════════════════════════════════════════════════════════

async def analyze_lecture(text: str, dialect: str = "msa") -> dict:
    print("[INFO] Starting lecture analysis...")
    
    text = _clean_text(text)
    
    if not text:
        raise ValueError("النص فارغ بعد التنظيف")
    
    all_keywords = _extract_keywords(text, 40)
    lecture_type = _detect_lecture_type(text)
    
    word_count = len(text.split())
    if word_count < 300:
        num_sections = 3
    elif word_count < 600:
        num_sections = 4
    elif word_count < 1000:
        num_sections = 5
    elif word_count < 1500:
        num_sections = 6
    else:
        num_sections = 7
    
    text_preview = text[:4000]
    
    teacher_styles = {
        'medicine': 'أنت طبيب استشاري تشرح لطلاب الطب. اشرح بشكل مفصل: التعريف، الأعراض، الأسباب، التشخيص، العلاج، المضاعفات، الوقاية.',
        'math': 'أنت أستاذ رياضيات. اشرح: تعريف المفاهيم، المعادلات، خطوات الحل، أمثلة عددية، تطبيقات، تمارين.',
        'physics': 'أنت فيزيائي. اشرح: القانون، التجربة، التحليل، التطبيقات الحياتية، العلاقات بين المتغيرات.',
        'chemistry': 'أنت كيميائي. اشرح: المعادلة، المواد، شروط التفاعل، الحسابات، التطبيقات الصناعية، احتياطات الأمان.',
        'history': 'أنت مؤرخ. اشرح: الزمان والمكان، الشخصيات، تسلسل الأحداث، الأسباب، النتائج، الدروس المستفادة.',
        'biology': 'أنت عالم أحياء. اشرح: التركيب، الوظيفة، العمليات الحيوية، الأهمية، الأمراض المرتبطة.',
        'other': 'أنت معلم خبير. اشرح: التعريف، التفاصيل، الأمثلة، التطبيقات، الأسئلة الشائعة، الخلاصة.'
    }
    
    teacher_style = teacher_styles.get(lecture_type, teacher_styles['other'])
    
    dialect_instructions = {
        "iraq": "باللهجة العراقية. استخدم: هواية، گلت، هسا، چي، شلون، أكو، ماكو.",
        "egypt": "باللهجة المصرية. استخدم: أوي، معلش، كده، عايز، النهارده، يا جماعة.",
        "syria": "باللهجة الشامية. استخدم: هلق، شو، كتير، منيح، هيك، عم، فيكن.",
        "gulf": "باللهجة الخليجية. استخدم: زين، وايد، عاد، هاذي، أبشر، يالحبيب.",
        "msa": "بالعربية الفصحى البسيطة والواضحة."
    }
    
    dialect_inst = dialect_instructions.get(dialect, dialect_instructions["msa"])

    prompt = f"""{teacher_style}
{dialect_inst}

**تعليمات صارمة:**
- اكتب شرحاً كاملاً ومتنوعاً (15-20 جملة كاملة).
- لا تكرر نفس الجملة أبداً.
- لا تستخدم "يعني يعني" أو "هو هو".
- كل جملة يجب أن تضيف معلومة جديدة.
- اشرح بأسلوب المعلم الذي يتحدث لطلابه.

**النص الأصلي:**
---
{text_preview}
---

**الكلمات المفتاحية:** {', '.join(all_keywords[:15])}

**المطلوب - {num_sections} أقسام:**

أرجع JSON فقط:
{{
  "title": "عنوان المحاضرة",
  "sections": [
    {{
      "title": "عنوان القسم",
      "keywords": ["ك1", "ك2", "ك3", "ك4"],
      "narration": "نص الشرح الكامل (15-20 جملة متنوعة)"
    }}
  ],
  "summary": "ملخص شامل للمحاضرة (5-7 جمل)"
}}
"""

    try:
        content = await _generate_with_rotation(prompt, max_output_tokens=8192)
        content = content.strip()
        content = re.sub(r'^```json\s*', '', content)
        content = re.sub(r'\s*```$', '', content)
        
        result = json.loads(content)
        title = _clean_text(result.get("title", all_keywords[0] if all_keywords else "المحاضرة التعليمية"))
        ai_sections = result.get("sections", [])
        summary = _clean_text(result.get("summary", f"شرحنا في هذه المحاضرة: {', '.join(all_keywords[:8])}"))
        print(f"[OK] AI generated {len(ai_sections)} sections")
        
    except Exception as e:
        print(f"[WARN] AI failed: {e}. Using fallback narration.")
        title = all_keywords[0] if all_keywords else "المحاضرة التعليمية"
        ai_sections = []
        summary = f"شرحنا في هذه المحاضرة: {', '.join(all_keywords[:8])}"

    final_sections = []
    for i in range(num_sections):
        if i < len(ai_sections) and ai_sections[i].get("narration"):
            section = ai_sections[i]
            keywords = [_clean_text(k) for k in section.get("keywords", [])[:4]]
            section_title = _clean_text(section.get("title", f"القسم {i+1}"))
            narration = _clean_text(section.get("narration", ""))
        else:
            start_idx = (i * 4) % len(all_keywords)
            keywords = []
            for j in range(4):
                idx = (start_idx + j) % len(all_keywords)
                kw = _clean_text(all_keywords[idx])
                if kw and kw not in keywords:
                    keywords.append(kw)
            section_title = keywords[0] if keywords else f"القسم {i+1}"
            narration = _generate_fallback_narration(keywords, lecture_type)
        
        while len(keywords) < 4:
            keywords.append("مفهوم")
        
        final_sections.append({
            "title": section_title,
            "keywords": keywords[:4],
            "narration": narration,
            "duration_estimate": max(45, len(narration.split()) // 3),
            "_keyword_images": [None] * 4,
            "_image_bytes": None
        })
    
    # توليد صورة واحدة لكل قسم
    print("[INFO] Generating section images...")
    for section in final_sections:
        section_keywords = section["keywords"]
        search_query = " ".join(section_keywords[:3])
        search_query = _clean_text(search_query)
        
        if not search_query:
            search_query = "educational concept"
        
        try:
            section["_image_bytes"] = await fetch_image_for_keyword(
                keyword=search_query,
                section_title=section["title"],
                lecture_type=lecture_type,
                image_search_en=search_query
            )
            print(f"[OK] Generated image for section: {section['title']}")
        except Exception as e:
            print(f"[WARN] Failed to generate section image: {e}")
            section["_image_bytes"] = None
    
    return {
        "lecture_type": lecture_type,
        "title": title,
        "sections": final_sections,
        "summary": summary,
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
    text = "\n\n".join(pages)
    text = _clean_text(text)
    return text


# ═══════════════════════════════════════════════════════════════════════════════
# 7. توليد الصور
# ═══════════════════════════════════════════════════════════════════════════════

_TYPE_COLORS = {
    'medicine': (231, 76, 126),
    'math': (52, 152, 219),
    'physics': (52, 152, 219),
    'chemistry': (46, 204, 113),
    'history': (230, 126, 34),
    'biology': (46, 204, 113),
    'other': (155, 89, 182),
}

def _get_font(size: int) -> ImageFont.FreeTypeFont:
    paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for p in paths:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except:
                pass
    return ImageFont.load_default()


def _make_colored_image(keyword: str, color: tuple) -> bytes:
    keyword = _clean_text(keyword)
    if not keyword:
        keyword = "مفهوم"
    
    W, H = 500, 350
    img = PILImage.new("RGB", (W, H), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    
    for y in range(H):
        t = y / H
        r = int(255 * (1 - t) + color[0] * t * 0.2)
        g = int(255 * (1 - t) + color[1] * t * 0.2)
        b = int(255 * (1 - t) + color[2] * t * 0.2)
        draw.line([(0, y), (W, y)], fill=(r, g, b))
    
    draw.rounded_rectangle([(10, 10), (W-10, H-10)], radius=20, outline=color, width=8)
    draw.ellipse([(W//2-60, H//2-60), (W//2+60, H//2+60)], fill=(*color, 25))
    
    font = _get_font(32)
    
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
        keyword = get_display(arabic_reshaper.reshape(keyword[:30]))
    except:
        pass
    
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
            tw = len(line) * 18
        x = (W - tw) // 2
        draw.text((x+3, y+3), line, fill=(200, 200, 200), font=font)
        draw.text((x, y), line, fill=color, font=font)
        y += 45
    
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=90)
    return buf.getvalue()


async def _pollinations_generate(prompt: str) -> bytes | None:
    prompt = _clean_text(prompt)
    if not prompt:
        return None
    
    import urllib.parse
    encoded = urllib.parse.quote(prompt[:200])
    url = f"https://image.pollinations.ai/prompt/{encoded}?width=500&height=350&nologo=true"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status == 200:
                    raw = await resp.read()
                    if len(raw) > 5000:
                        print(f"[OK] Pollinations image generated")
                        return raw
    except Exception as e:
        print(f"[WARN] Pollinations failed: {e}")
    return None


async def _picsum_generate() -> bytes | None:
    try:
        url = f"https://picsum.photos/500/350?random={random.randint(1, 1000)}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    print(f"[OK] Picsum fallback image used")
                    return await resp.read()
    except:
        pass
    return None


async def fetch_image_for_keyword(
    keyword: str,
    section_title: str = "",
    lecture_type: str = "other",
    image_search_en: str = "",
) -> bytes:
    # تنظيف جميع المدخلات
    keyword = _clean_text(keyword)
    section_title = _clean_text(section_title)
    image_search_en = _clean_text(image_search_en)
    
    if not keyword:
        keyword = "educational concept"
    
    print(f"[INFO] Fetching image for: {keyword[:50]}")
    color = _TYPE_COLORS.get(lecture_type, _TYPE_COLORS['other'])
    
    prompt = f"educational illustration of {keyword}"
    prompt = _clean_text(prompt)
    
    img_bytes = await _pollinations_generate(prompt)
    if img_bytes:
        return img_bytes
    
    img_bytes = await _picsum_generate()
    if img_bytes:
        return img_bytes
    
    print(f"[INFO] Using colored placeholder")
    return _make_colored_image(keyword, color)
