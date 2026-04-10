# -*- coding: utf-8 -*-
import json
import re
import io
import asyncio
import aiohttp
import os
import random
from PIL import Image, ImageDraw, ImageFont
from google import genai
from google.genai import types as genai_types


def clean_text(text: str) -> str:
    """تنظيف النص من الأحرف غير المرغوبة"""
    if not text:
        return ""
    text = str(text).replace('\x00', '').replace('\0', '')
    text = re.sub(r'[\x01-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


async def extract_full_text_from_pdf(pdf_bytes: bytes) -> str:
    """استخراج النص من PDF"""
    import PyPDF2
    
    def _extract():
        reader = PyPDF2.PdfReader(io.BytesIO(pdf_bytes))
        pages = []
        for page in reader.pages:
            page_text = page.extract_text() or ""
            if page_text.strip():
                pages.append(page_text)
        return "\n\n".join(pages)
    
    loop = asyncio.get_event_loop()
    text = await loop.run_in_executor(None, _extract)
    return clean_text(text)


# ═══════════════════════════════════════════════════════════════════════════════
# مفاتيح API
# ═══════════════════════════════════════════════════════════════════════════════

_google_keys = [k.strip() for k in os.getenv("GOOGLE_API_KEYS", "").split(",") if k.strip()]
_current_google_idx = 0

_groq_key = os.getenv("GROQ_API_KEY", "").strip()


def _next_google_key():
    """الحصول على مفتاح Google التالي"""
    global _current_google_idx
    if not _google_keys:
        return None
    key = _google_keys[_current_google_idx % len(_google_keys)]
    _current_google_idx += 1
    return key


async def _ai_generate(prompt: str, max_tokens: int = 8192) -> str:
    """توليد النص باستخدام Google Gemini أو Groq"""
    
    # محاولة Google Gemini
    key = _next_google_key()
    if key:
        try:
            client = genai.Client(api_key=key)
            response = await asyncio.to_thread(
                client.models.generate_content,
                model="gemini-2.0-flash",
                contents=prompt,
                config=genai_types.GenerateContentConfig(
                    temperature=0.7,
                    max_output_tokens=max_tokens
                )
            )
            return response.text.strip()
        except Exception as e:
            print(f"[AI] Google failed: {e}")
    
    # محاولة Groq
    if _groq_key:
        try:
            headers = {
                "Authorization": f"Bearer {_groq_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": "llama-3.3-70b-versatile",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": min(max_tokens, 8192),
                "temperature": 0.7
            }
            async with aiohttp.ClientSession() as s:
                async with s.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(60)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data["choices"][0]["message"]["content"].strip()
        except Exception as e:
            print(f"[AI] Groq failed: {e}")
    
    raise Exception("All AI services failed")


# ═══════════════════════════════════════════════════════════════════════════════
# تحليل النص
# ═══════════════════════════════════════════════════════════════════════════════

def _extract_keywords(text: str, max_words: int = 30) -> list:
    """استخراج الكلمات المفتاحية"""
    text = clean_text(text)
    stop_words = {
        'و', 'في', 'من', 'على', 'إلى', 'أن', 'هو', 'هي', 'هذا', 'هذه', 'كان', 'كانت',
        'مع', 'ما', 'لا', 'عن', 'إذا', 'لم', 'لن', 'قد', 'ثم', 'أو', 'أم', 'لكن',
        'حتى', 'بل', 'كل', 'بعض', 'the', 'a', 'an', 'is', 'are', 'was', 'were',
        'of', 'to', 'in', 'that', 'it', 'be', 'for', 'on', 'with', 'as', 'at',
        'by', 'this', 'and', 'or', 'but'
    }
    words = re.findall(r'[\u0600-\u06FF]{4,}|[a-zA-Z]{4,}', text)
    freq = {}
    for w in words:
        wl = w.lower()
        if wl not in stop_words:
            freq[w] = freq.get(w, 0) + 1
    sorted_words = sorted(freq.items(), key=lambda x: x[1], reverse=True)
    return [w[0] for w in sorted_words[:max_words]]


def _detect_type(text: str) -> str:
    """تحديد نوع المحاضرة"""
    text = clean_text(text).lower()
    
    medical = ['مرض', 'علاج', 'طبيب', 'جراحة', 'دواء', 'تشخيص', 'مريض', 'قلب', 'دم', 'خلية', 'ورم', 'سرطان']
    math = ['معادلة', 'دالة', 'تفاضل', 'تكامل', 'جبر', 'هندسة', 'رياضيات', 'equation', 'function']
    physics = ['قوة', 'طاقة', 'حركة', 'سرعة', 'جاذبية', 'كهرباء', 'مغناطيس', 'فيزياء', 'force', 'energy']
    chemistry = ['تفاعل', 'عنصر', 'مركب', 'جزيء', 'ذرة', 'حمض', 'قاعدة', 'كيمياء', 'reaction']
    history = ['تاريخ', 'حرب', 'معركة', 'حضارة', 'إمبراطورية', 'ملك', 'ثورة', 'history', 'war']
    biology = ['نبات', 'حيوان', 'بيئة', 'وراثة', 'تطور', 'خلية', 'biology', 'plant', 'animal']
    
    scores = {
        'medicine': sum(1 for k in medical if k in text),
        'math': sum(1 for k in math if k in text),
        'physics': sum(1 for k in physics if k in text),
        'chemistry': sum(1 for k in chemistry if k in text),
        'history': sum(1 for k in history if k in text),
        'biology': sum(1 for k in biology if k in text)
    }
    best = max(scores, key=scores.get)
    return best if scores[best] > 1 else 'other'


async def analyze_lecture(text: str, dialect: str = "msa") -> dict:
    """تحليل المحاضرة بشكل كامل"""
    text = clean_text(text)
    if not text:
        raise ValueError("النص فارغ")
    
    keywords = _extract_keywords(text, 40)
    ltype = _detect_type(text)
    
    wc = len(text.split())
    if wc < 300:
        ns = 3
    elif wc < 600:
        ns = 4
    elif wc < 1000:
        ns = 5
    else:
        ns = 6
    
    preview = text[:4000]
    
    teacher_map = {
        'medicine': 'طبيب',
        'math': 'أستاذ رياضيات',
        'physics': 'فيزيائي',
        'chemistry': 'كيميائي',
        'history': 'مؤرخ',
        'biology': 'عالم أحياء',
        'other': 'معلم'
    }
    teacher = teacher_map.get(ltype, 'معلم')
    
    dial_map = {
        "iraq": "بالعراقي",
        "egypt": "بالمصري",
        "syria": "بالشامي",
        "gulf": "بالخليجي",
        "msa": "بالفصحى"
    }
    dial = dial_map.get(dialect, "بالفصحى")
    
    prompt = (
        f"أنت {teacher}. اشرح {dial}. اكتب 15-20 جملة متنوعة لكل قسم. "
        f"النص: {preview}. الكلمات المفتاحية: {', '.join(keywords[:15])}. "
        f"أرجع JSON فقط بالتنسيق التالي: "
        f'{{"title": "عنوان المحاضرة", "sections": [{{"title": "عنوان القسم", "keywords": ["ك1","ك2","ك3","ك4"], "narration": "نص الشرح"}}]}}'
    )
    
    try:
        content = await _ai_generate(prompt, 8192)
        content = re.sub(r'^```json\s*', '', content.strip())
        content = re.sub(r'\s*```$', '', content)
        res = json.loads(content)
        title = clean_text(res.get("title", keywords[0] if keywords else "محاضرة"))
        ai_secs = res.get("sections", [])
    except Exception as e:
        print(f"[AI] Parse failed: {e}")
        title = keywords[0] if keywords else "محاضرة"
        ai_secs = []
    
    sections = []
    for i in range(ns):
        if i < len(ai_secs) and ai_secs[i].get("narration"):
            s = ai_secs[i]
            kw = [clean_text(k) for k in s.get("keywords", [])[:4]]
            st = clean_text(s.get("title", f"قسم {i+1}"))
            nar = clean_text(s.get("narration", ""))
        else:
            idx = (i * 4) % len(keywords)
            kw = [keywords[(idx + j) % len(keywords)] for j in range(4)]
            st = kw[0] if kw else f"قسم {i+1}"
            nar = f"نتعرف في هذا القسم على {', '.join(kw[:3])}. " * 15
        
        while len(kw) < 4:
            kw.append("مفهوم")
        
        sections.append({
            "title": st,
            "keywords": kw[:4],
            "narration": nar,
            "duration_estimate": max(45, len(nar.split()) // 3),
            "_image_bytes": None
        })
    
    for s in sections:
        q = " ".join(s["keywords"][:3])
        s["_image_bytes"] = await fetch_image_for_keyword(q, s["title"], ltype)
    
    return {
        "lecture_type": ltype,
        "title": title,
        "sections": sections,
        "summary": f"شرحنا في هذه المحاضرة: {', '.join(keywords[:8])}",
        "all_keywords": keywords
    }


# ═══════════════════════════════════════════════════════════════════════════════
# توليد الصور
# ═══════════════════════════════════════════════════════════════════════════════

_TYPE_COLORS = {
    'medicine': (231, 76, 126),
    'math': (52, 152, 219),
    'physics': (52, 152, 219),
    'chemistry': (46, 204, 113),
    'history': (230, 126, 34),
    'biology': (46, 204, 113),
    'other': (155, 89, 182)
}


def _get_font(size: int):
    """تحميل خط مناسب"""
    paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    ]
    for p in paths:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except:
                pass
    return ImageFont.load_default()


def _make_colored_image(keyword: str, color: tuple) -> bytes:
    """إنشاء صورة ملونة تحتوي على الكلمة المفتاحية"""
    keyword = clean_text(keyword) or "مفهوم"
    W, H = 500, 350
    
    img = Image.new("RGB", (W, H), (255, 255, 255))
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
    
    lines = []
    cur = []
    for w in keyword.split():
        cur.append(w)
        line = ' '.join(cur)
        try:
            if font.getbbox(line)[2] - font.getbbox(line)[0] > W - 60:
                cur.pop()
                lines.append(' '.join(cur))
                cur = [w]
        except:
            pass
    if cur:
        lines.append(' '.join(cur))
    
    y = H // 2 - (len(lines) * 40) // 2
    for line in lines:
        try:
            tw = font.getbbox(line)[2] - font.getbbox(line)[0]
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
    """محاولة توليد صورة من Pollinations.ai"""
    import urllib.parse
    try:
        async with aiohttp.ClientSession() as s:
            encoded = urllib.parse.quote(prompt[:200])
            url = f"https://image.pollinations.ai/prompt/{encoded}?width=500&height=350&nologo=true"
            async with s.get(url, timeout=15) as r:
                if r.status == 200:
                    return await r.read()
    except:
        pass
    return None


async def _picsum_generate() -> bytes | None:
    """محاولة جلب صورة من Picsum"""
    try:
        async with aiohttp.ClientSession() as s:
            url = f"https://picsum.photos/500/350?random={random.randint(1, 1000)}"
            async with s.get(url, timeout=10) as r:
                if r.status == 200:
                    return await r.read()
    except:
        pass
    return None


async def fetch_image_for_keyword(
    keyword: str,
    section_title: str = "",
    lecture_type: str = "other",
    image_search_en: str = ""
) -> bytes:
    """جلب صورة للكلمة المفتاحية"""
    keyword = clean_text(keyword) or "مفهوم"
    color = _TYPE_COLORS.get(lecture_type, _TYPE_COLORS['other'])
    
    img = await _pollinations_generate(f"educational illustration of {keyword}")
    if img:
        return img
    
    img = await _picsum_generate()
    if img:
        return img
    
    return _make_colored_image(keyword, color)
