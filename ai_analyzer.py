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

# ═══════════════════════════════════════════════════════════════════════════════
# تنظيف النص
# ═══════════════════════════════════════════════════════════════════════════════

def clean_text(text: str) -> str:
    if not text:
        return ""
    text = str(text).replace('\x00', '').replace('\0', '')
    text = re.sub(r'[\x01-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


# ═══════════════════════════════════════════════════════════════════════════════
# استخراج النص من PDF - الحل الجذري (Thread + Timeout)
# ═══════════════════════════════════════════════════════════════════════════════

async def extract_full_text_from_pdf(pdf_bytes: bytes) -> str:
    """
    استخراج النص من PDF بشكل غير متزامن حقيقي.
    يستخدم pypdf (أسرع من PyPDF2) ويعمل في Thread منفصل مع Timeout.
    """
    from pypdf import PdfReader
    
    def _extract():
        reader = PdfReader(io.BytesIO(pdf_bytes))
        pages = []
        for page in reader.pages:
            page_text = page.extract_text() or ""
            if page_text.strip():
                pages.append(page_text)
        return "\n\n".join(pages)
    
    loop = asyncio.get_event_loop()
    
    try:
        # تشغيل الاستخراج في Thread منفصل مع timeout 60 ثانية
        text = await asyncio.wait_for(
            loop.run_in_executor(None, _extract),
            timeout=60.0
        )
        return clean_text(text)
    except asyncio.TimeoutError:
        raise RuntimeError("استخراج النص من PDF استغرق وقتاً طويلاً. الملف كبير جداً.")
    except Exception as e:
        raise RuntimeError(f"فشل استخراج النص من PDF: {str(e)}")


# ═══════════════════════════════════════════════════════════════════════════════
# مفاتيح API
# ═══════════════════════════════════════════════════════════════════════════════

def _load_google_keys():
    keys = []
    raw = os.getenv("GOOGLE_API_KEYS", "")
    if raw:
        for k in raw.split(","):
            k = k.strip()
            if k and k not in keys:
                keys.append(k)
    for i in range(1, 10):
        k = os.getenv(f"GOOGLE_API_KEY_{i}", "").strip()
        if k and k not in keys:
            keys.append(k)
    single = os.getenv("GOOGLE_API_KEY", "").strip()
    if single and single not in keys:
        keys.append(single)
    return keys

_google_keys = _load_google_keys()
_current_google_idx = 0
_exhausted_google = set()

def _load_groq_keys():
    keys = []
    raw = os.getenv("GROQ_API_KEYS", "")
    if raw:
        for k in raw.split(","):
            k = k.strip()
            if k and k not in keys:
                keys.append(k)
    single = os.getenv("GROQ_API_KEY", "").strip()
    if single and single not in keys:
        keys.append(single)
    return keys

_groq_keys = _load_groq_keys()
_GROQ_MODELS = ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"]

def _next_google_key():
    global _current_google_idx
    if not _google_keys:
        return None
    for _ in range(len(_google_keys)):
        k = _google_keys[_current_google_idx % len(_google_keys)]
        if k not in _exhausted_google:
            return k
        _current_google_idx += 1
    return None

def _mark_exhausted(k):
    global _current_google_idx
    _exhausted_google.add(k)
    _current_google_idx += 1


# ═══════════════════════════════════════════════════════════════════════════════
# دوال AI
# ═══════════════════════════════════════════════════════════════════════════════

async def _google_generate(prompt: str, max_tokens: int = 8192) -> str:
    models = ["gemini-2.0-flash", "gemini-2.0-flash-lite"]
    for _ in range(len(_google_keys) * 2):
        key = _next_google_key()
        if not key:
            break
        client = genai.Client(api_key=key)
        for model in models:
            try:
                resp = await asyncio.to_thread(
                    client.models.generate_content,
                    model=model,
                    contents=prompt,
                    config=genai_types.GenerateContentConfig(
                        temperature=0.7,
                        max_output_tokens=max_tokens
                    )
                )
                return resp.text.strip()
            except Exception as e:
                if "429" in str(e) or "quota" in str(e).lower():
                    _mark_exhausted(key)
                    break
    raise Exception("Google failed")


async def _groq_generate(prompt: str, max_tokens: int = 8192) -> str:
    if not _groq_keys:
        raise Exception("No Groq keys")
    for key in _groq_keys:
        for model in _GROQ_MODELS:
            try:
                headers = {
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json"
                }
                payload = {
                    "model": model,
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
            except:
                continue
    raise Exception("Groq failed")


async def _ai_generate(prompt: str, max_tokens: int = 8192) -> str:
    if _google_keys:
        try:
            return await _google_generate(prompt, max_tokens)
        except:
            pass
    if _groq_keys:
        try:
            return await _groq_generate(prompt, max_tokens)
        except:
            pass
    raise Exception("All AI failed")


# ═══════════════════════════════════════════════════════════════════════════════
# تحليل النص
# ═══════════════════════════════════════════════════════════════════════════════

def _extract_keywords(text: str, max_words: int = 30) -> list:
    text = clean_text(text)
    stop = {
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
        if wl not in stop:
            freq[w] = freq.get(w, 0) + 1
    sorted_words = sorted(freq.items(), key=lambda x: x[1], reverse=True)
    return [w[0] for w in sorted_words[:max_words]]


def _detect_type(text: str) -> str:
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
    text = clean_text(text)
    if not text:
        raise ValueError("Empty")
    
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
        'medicine': 'طبيب', 'math': 'أستاذ رياضيات', 'physics': 'فيزيائي',
        'chemistry': 'كيميائي', 'history': 'مؤرخ', 'biology': 'عالم أحياء',
        'other': 'معلم'
    }
    teacher = teacher_map.get(ltype, 'معلم')
    
    dial_map = {
        "iraq": "بالعراقي", "egypt": "بالمصري", "syria": "بالشامي",
        "gulf": "بالخليجي", "msa": "بالفصحى"
    }
    dial = dial_map.get(dialect, "بالفصحى")
    
    prompt = (
        f"أنت {teacher}. اشرح {dial}. اكتب 15-20 جملة متنوعة لكل قسم. "
        f"النص: {preview}. الكلمات: {', '.join(keywords[:15])}. "
        f"أرجع JSON: {{'title': 'عنوان', 'sections': [{{'title': '', 'keywords': ['','','',''], 'narration': ''}}]}}"
    )
    
    try:
        content = await _ai_generate(prompt, 8192)
        content = re.sub(r'^```json\s*', '', content.strip())
        content = re.sub(r'\s*```$', '', content)
        res = json.loads(content)
        title = clean_text(res.get("title", keywords[0] if keywords else "محاضرة"))
        ai_secs = res.get("sections", [])
    except:
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
            nar = f"نتعرف على {', '.join(kw[:3])}. " * 15
        
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
        "summary": f"شرحنا: {', '.join(keywords[:8])}",
        "all_keywords": keywords
    }


# ═══════════════════════════════════════════════════════════════════════════════
# الصور
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


def _get_font(sz):
    paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    ]
    for p in paths:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, sz)
            except:
                pass
    return ImageFont.load_default()


def _make_image(kw: str, col: tuple) -> bytes:
    kw = clean_text(kw) or "مفهوم"
    W, H = 500, 350
    img = Image.new("RGB", (W, H), (255, 255, 255))
    d = ImageDraw.Draw(img)
    
    for y in range(H):
        t = y / H
        r = int(255 * (1 - t) + col[0] * t * 0.2)
        g = int(255 * (1 - t) + col[1] * t * 0.2)
        b = int(255 * (1 - t) + col[2] * t * 0.2)
        d.line([(0, y), (W, y)], fill=(r, g, b))
    
    d.rounded_rectangle([(10, 10), (W-10, H-10)], radius=20, outline=col, width=8)
    d.ellipse([(W//2-60, H//2-60), (W//2+60, H//2+60)], fill=(*col, 25))
    
    f = _get_font(32)
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
        kw = get_display(arabic_reshaper.reshape(kw[:30]))
    except:
        pass
    
    lines = []
    cur = []
    for w in kw.split():
        cur.append(w)
        line = ' '.join(cur)
        try:
            if f.getbbox(line)[2] - f.getbbox(line)[0] > W - 60:
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
            tw = f.getbbox(line)[2] - f.getbbox(line)[0]
        except:
            tw = len(line) * 18
        x = (W - tw) // 2
        d.text((x+3, y+3), line, fill=(200, 200, 200), font=f)
        d.text((x, y), line, fill=col, font=f)
        y += 45
    
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=90)
    return buf.getvalue()


async def _pollinations(prompt: str) -> bytes | None:
    import urllib.parse
    try:
        async with aiohttp.ClientSession() as s:
            url = f"https://image.pollinations.ai/prompt/{urllib.parse.quote(prompt[:200])}?width=500&height=350&nologo=true"
            async with s.get(url, timeout=15) as r:
                if r.status == 200:
                    return await r.read()
    except:
        pass
    return None


async def _picsum() -> bytes | None:
    try:
        async with aiohttp.ClientSession() as s:
            url = f"https://picsum.photos/500/350?random={random.randint(1, 1000)}"
            async with s.get(url, timeout=10) as r:
                if r.status == 200:
                    return await r.read()
    except:
        pass
    return None


async def fetch_image_for_keyword(keyword: str, section_title: str = "", lecture_type: str = "other", image_search_en: str = "") -> bytes:
    keyword = clean_text(keyword) or "مفهوم"
    col = _TYPE_COLORS.get(lecture_type, _TYPE_COLORS['other'])
    
    img = await _pollinations(f"educational illustration of {keyword}")
    if img:
        return img
    
    img = await _picsum()
    if img:
        return img
    
    return _make_image(keyword, col)
