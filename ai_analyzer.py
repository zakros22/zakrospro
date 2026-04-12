# -*- coding: utf-8 -*-
"""
AI Analyzer Module - مع ترجمة وشرح باللهجة المختارة
- إذا النص إنجليزي → يترجمه ويشرحه باللهجة المختارة
- يستخرج المصطلحات المهمة بالإنجليزي ويحتفظ بها
- يولد صورة لكل قسم (مضمون 100%)
"""

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
    if not text:
        return ""
    text = str(text).replace('\x00', '').replace('\0', '')
    text = re.sub(r'[\x01-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


async def extract_full_text_from_pdf(pdf_bytes: bytes) -> str:
    try:
        import pdfplumber
        def _extract():
            with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                return "\n\n".join([p.extract_text() or "" for p in pdf.pages])
        loop = asyncio.get_event_loop()
        return clean_text(await asyncio.wait_for(loop.run_in_executor(None, _extract), timeout=60.0))
    except:
        import PyPDF2
        def _extract():
            r = PyPDF2.PdfReader(io.BytesIO(pdf_bytes))
            return "\n\n".join([p.extract_text() or "" for p in r.pages])
        loop = asyncio.get_event_loop()
        return clean_text(await asyncio.wait_for(loop.run_in_executor(None, _extract), timeout=60.0))


# ═══════════════════════════════════════════════════════════════════════════════
# مفاتيح API
# ═══════════════════════════════════════════════════════════════════════════════

def _load_keys(env_name):
    keys = []
    raw = os.getenv(env_name, "")
    if raw:
        for k in raw.split(","):
            k = k.strip()
            if k and k not in keys:
                keys.append(k)
    return keys

_deepseek_keys = _load_keys("DEEPSEEK_API_KEYS")
if not _deepseek_keys:
    single = os.getenv("DEEPSEEK_API_KEY", "").strip()
    if single:
        _deepseek_keys = [single]
_current_deepseek_idx = 0
_exhausted_deepseek = set()

_google_keys = _load_keys("GOOGLE_API_KEYS")
if not _google_keys:
    single = os.getenv("GOOGLE_API_KEY", "").strip()
    if single:
        _google_keys = [single]

_groq_keys = _load_keys("GROQ_API_KEYS")
if not _groq_keys:
    single = os.getenv("GROQ_API_KEY", "").strip()
    if single:
        _groq_keys = [single]

print(f"[AI] DeepSeek: {len(_deepseek_keys)}, Google: {len(_google_keys)}, Groq: {len(_groq_keys)}")


def _next_deepseek_key():
    global _current_deepseek_idx
    if not _deepseek_keys:
        return None
    for _ in range(len(_deepseek_keys)):
        k = _deepseek_keys[_current_deepseek_idx % len(_deepseek_keys)]
        if k not in _exhausted_deepseek:
            return k
        _current_deepseek_idx += 1
    return None


def _mark_deepseek_exhausted(k):
    global _current_deepseek_idx
    _exhausted_deepseek.add(k)
    _current_deepseek_idx += 1


async def _deepseek_generate(prompt: str, max_tokens: int = 8192) -> str:
    if not _deepseek_keys:
        raise Exception("No DeepSeek keys")
    
    for _ in range(len(_deepseek_keys) + 1):
        key = _next_deepseek_key()
        if not key:
            break
        
        try:
            headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
            payload = {
                "model": "deepseek-chat",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": min(max_tokens, 8192),
                "temperature": 0.9
            }
            async with aiohttp.ClientSession() as s:
                async with s.post(
                    "https://api.deepseek.com/v1/chat/completions",
                    headers=headers, json=payload, timeout=aiohttp.ClientTimeout(90)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data["choices"][0]["message"]["content"].strip()
                    elif resp.status in (429, 402):
                        _mark_deepseek_exhausted(key)
                        continue
        except:
            continue
    
    # fallback to Google
    if _google_keys:
        try:
            key = _google_keys[0]
            client = genai.Client(api_key=key)
            response = await asyncio.to_thread(
                client.models.generate_content,
                model="gemini-2.0-flash",
                contents=prompt,
                config=genai_types.GenerateContentConfig(temperature=0.9, max_output_tokens=max_tokens)
            )
            return response.text.strip()
        except:
            pass
    
    # fallback to Groq
    if _groq_keys:
        try:
            key = _groq_keys[0]
            headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
            payload = {
                "model": "llama-3.3-70b-versatile",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": min(max_tokens, 8192),
                "temperature": 0.9
            }
            async with aiohttp.ClientSession() as s:
                async with s.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers=headers, json=payload, timeout=aiohttp.ClientTimeout(60)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data["choices"][0]["message"]["content"].strip()
        except:
            pass
    
    raise Exception("All AI services failed")


# ═══════════════════════════════════════════════════════════════════════════════
# استخراج الكلمات المفتاحية
# ═══════════════════════════════════════════════════════════════════════════════

def _extract_keywords(text: str, max_words: int = 30) -> list:
    text = clean_text(text)
    stop_words = {'و', 'في', 'من', 'على', 'إلى', 'أن', 'هو', 'هي', 'هذا', 'هذه', 'كان', 'كانت', 'مع', 'ما', 'لا', 'عن', 'إذا', 'لم', 'لن', 'قد', 'ثم', 'أو', 'أم', 'لكن', 'حتى', 'بل', 'كل', 'بعض', 'the', 'a', 'an', 'is', 'are', 'was', 'were', 'of', 'to', 'in', 'that', 'it', 'be', 'for', 'on', 'with', 'as', 'at', 'by', 'this', 'and', 'or', 'but'}
    words = re.findall(r'[\u0600-\u06FF]{4,}|[a-zA-Z]{4,}', text)
    freq = {}
    for w in words:
        wl = w.lower()
        if wl not in stop_words:
            freq[w] = freq.get(w, 0) + 1
    return [w[0] for w in sorted(freq.items(), key=lambda x: x[1], reverse=True)[:max_words]]


def _is_english(text: str) -> bool:
    arabic = len(re.findall(r'[\u0600-\u06FF]', text))
    english = len(re.findall(r'[a-zA-Z]', text))
    return english > arabic


def _detect_type(text: str) -> str:
    text_lower = clean_text(text).lower()
    if any(k in text_lower for k in ['مرض', 'علاج', 'طبيب', 'disease', 'treatment']):
        return 'medicine'
    elif any(k in text_lower for k in ['معادلة', 'دالة', 'تفاضل', 'equation', 'calculus']):
        return 'math'
    elif any(k in text_lower for k in ['قوة', 'طاقة', 'حركة', 'force', 'energy']):
        return 'physics'
    elif any(k in text_lower for k in ['تفاعل', 'عنصر', 'مركب', 'reaction', 'element']):
        return 'chemistry'
    elif any(k in text_lower for k in ['تاريخ', 'حرب', 'معركة', 'history', 'war']):
        return 'history'
    elif any(k in text_lower for k in ['نبات', 'حيوان', 'خلية', 'biology', 'cell']):
        return 'biology'
    return 'other'


# ═══════════════════════════════════════════════════════════════════════════════
# الدالة الرئيسية
# ═══════════════════════════════════════════════════════════════════════════════

async def analyze_lecture(text: str, dialect: str = "msa") -> dict:
    text = clean_text(text)
    if not text:
        raise ValueError("النص فارغ")
    
    is_eng = _is_english(text)
    print(f"[AI] Language: {'English' if is_eng else 'Arabic'}")
    
    # استخراج الكلمات المفتاحية (تحتفظ بالإنجليزي)
    keywords = _extract_keywords(text, 40)
    english_terms = [k for k in keywords if re.match(r'[a-zA-Z]', k)][:10]
    
    ltype = _detect_type(text)
    wc = len(text.split())
    ns = 3 if wc < 300 else 4 if wc < 600 else 5 if wc < 1000 else 6
    
    preview = text[:4000]
    
    # إذا النص إنجليزي والمستخدم اختار لهجة عربية → نترجم ونشرح باللهجة
    if is_eng and dialect in ["iraq", "egypt", "syria", "gulf", "msa"]:
        dial_map = {"iraq": "العراقية", "egypt": "المصرية", "syria": "الشامية", "gulf": "الخليجية", "msa": "الفصحى"}
        dial_name = dial_map.get(dialect, "العربية")
        
        prompt = f"""أنت معلم خبير. النص التالي باللغة الإنجليزية. قم بما يلي:
1. ترجم النص إلى العربية واشرحه شرحاً مفصلاً باللهجة {dial_name}.
2. احتفظ بالمصطلحات الإنجليزية المهمة كما هي بين قوسين.
3. اكتب 20-25 جملة متنوعة لكل قسم.

النص:
---
{preview}
---

المصطلحات الإنجليزية المهمة: {', '.join(english_terms[:10])}

أرجع JSON:
{{"title": "عنوان المحاضرة (بالعربية)", "sections": [{{"title": "عنوان القسم", "keywords": ["مصطلح1", "مصطلح2", "مصطلح3", "مصطلح4"], "narration": "نص الشرح باللهجة {dial_name} (20-25 جملة)"}}], "summary": "ملخص"}}"""
    elif is_eng:
        prompt = f"""You are an expert teacher. Explain the following text in clear English.
Write 20-25 varied sentences per section.

Text:
---
{preview}
---

Keywords: {', '.join(keywords[:15])}

Return JSON:
{{"title": "Lecture Title", "sections": [{{"title": "Section Title", "keywords": ["term1", "term2", "term3", "term4"], "narration": "Full explanation (20-25 sentences)"}}], "summary": "Summary"}}"""
    else:
        dial_map = {"iraq": "بالعراقي", "egypt": "بالمصري", "syria": "بالشامي", "gulf": "بالخليجي", "msa": "بالفصحى"}
        dial = dial_map.get(dialect, "بالفصحى")
        prompt = f"""أنت معلم خبير. اشرح النص التالي {dial}.
اكتب 20-25 جملة متنوعة لكل قسم.

النص:
---
{preview}
---

الكلمات: {', '.join(keywords[:15])}

أرجع JSON:
{{"title": "عنوان المحاضرة", "sections": [{{"title": "عنوان القسم", "keywords": ["كلمة1", "كلمة2", "كلمة3", "كلمة4"], "narration": "نص الشرح (20-25 جملة)"}}], "summary": "ملخص"}}"""
    
    try:
        content = await _deepseek_generate(prompt, 8192)
        content = re.sub(r'^```json\s*', '', content.strip())
        content = re.sub(r'\s*```$', '', content)
        res = json.loads(content)
        title = clean_text(res.get("title", keywords[0] if keywords else "محاضرة"))
        ai_secs = res.get("sections", [])
        summary = clean_text(res.get("summary", ""))
    except Exception as e:
        print(f"[AI] Failed: {e}")
        title = keywords[0] if keywords else "محاضرة"
        ai_secs = []
        summary = ""
    
    sections = []
    for i in range(ns):
        if i < len(ai_secs) and ai_secs[i].get("narration"):
            s = ai_secs[i]
            kw = [clean_text(k) for k in s.get("keywords", [])[:4]]
            st = clean_text(s.get("title", f"القسم {i+1}"))
            nar = clean_text(s.get("narration", ""))
        else:
            idx = (i * 4) % len(keywords)
            kw = [keywords[(idx + j) % len(keywords)] for j in range(4)]
            st = kw[0] if kw else f"القسم {i+1}"
            nar = f"شرح {', '.join(kw[:3])}. " * 15
        
        while len(kw) < 4:
            kw.append("مفهوم")
        
        sections.append({
            "title": st,
            "keywords": kw[:4],
            "narration": nar,
            "duration_estimate": max(45, len(nar.split()) // 3),
            "_image_bytes": None
        })
    
    # ✅ توليد صورة لكل قسم (مضمون 100%)
    print(f"[IMG] Generating images for {len(sections)} sections...")
    for i, s in enumerate(sections):
        q = " ".join(s["keywords"][:4])
        s["_image_bytes"] = await fetch_image_for_keyword(q, s["title"], ltype, is_eng)
        print(f"[IMG] Section {i+1}/{len(sections)} done")
    
    return {
        "lecture_type": ltype,
        "title": title,
        "sections": sections,
        "summary": summary,
        "all_keywords": keywords,
        "is_english": is_eng
    }


# ═══════════════════════════════════════════════════════════════════════════════
# الصور - مضمونة 100%
# ═══════════════════════════════════════════════════════════════════════════════

_TYPE_COLORS = {
    'medicine': (231, 76, 126), 'math': (52, 152, 219), 'physics': (52, 152, 219),
    'chemistry': (46, 204, 113), 'biology': (46, 204, 113), 'history': (230, 126, 34),
    'other': (155, 89, 182)
}


def _get_font(size: int):
    paths = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]
    for p in paths:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except:
                pass
    return ImageFont.load_default()


def _make_colored_image(keywords: str, color: tuple, is_english: bool = False) -> bytes:
    keywords = clean_text(keywords) or ("Concept" if is_english else "مفهوم")
    W, H = 500, 350
    img = Image.new("RGB", (W, H), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    
    for y in range(H):
        t = y / H
        r = int(255 * (1 - t) + color[0] * t * 0.3)
        g = int(255 * (1 - t) + color[1] * t * 0.3)
        b = int(255 * (1 - t) + color[2] * t * 0.3)
        draw.line([(0, y), (W, y)], fill=(r, g, b))
    
    draw.rounded_rectangle([(8, 8), (W-8, H-8)], radius=20, outline=color, width=6)
    draw.ellipse([(W//2-60, H//2-60), (W//2+60, H//2+60)], fill=(*color, 30))
    
    font = _get_font(32 if not is_english else 28)
    if not is_english:
        try:
            import arabic_reshaper
            from bidi.algorithm import get_display
            keywords = get_display(arabic_reshaper.reshape(keywords[:50]))
        except:
            pass
    
    words = keywords.split()
    lines = []
    cur = []
    for w in words:
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
    
    y = H // 2 - (len(lines) * 45) // 2
    for line in lines:
        try:
            tw = font.getbbox(line)[2] - font.getbbox(line)[0]
        except:
            tw = len(line) * 18
        x = (W - tw) // 2
        draw.text((x+3, y+3), line, fill=(100, 100, 100), font=font)
        draw.text((x, y), line, fill=color, font=font)
        y += 45
    
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=95)
    return buf.getvalue()


async def _pollinations_generate(prompt: str) -> bytes | None:
    import urllib.parse
    try:
        async with aiohttp.ClientSession() as s:
            url = f"https://image.pollinations.ai/prompt/{urllib.parse.quote(prompt[:200])}?width=500&height=350&nologo=true"
            async with s.get(url, timeout=15) as r:
                if r.status == 200:
                    raw = await r.read()
                    if len(raw) > 5000:
                        return raw
    except:
        pass
    return None


async def fetch_image_for_keyword(keyword: str, section_title: str = "", lecture_type: str = "other", is_english: bool = False) -> bytes:
    keyword = clean_text(keyword) or ("concept" if is_english else "مفهوم")
    color = _TYPE_COLORS.get(lecture_type, _TYPE_COLORS['other'])
    
    img = await _pollinations_generate(f"educational illustration of {keyword}")
    if img:
        return img
    
    return _make_colored_image(keyword, color, is_english)
