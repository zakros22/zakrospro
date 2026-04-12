# -*- coding: utf-8 -*-
"""
AI Analyzer Module - النسخة الخرافية الكاملة
- 4 مصادر للصور: Pollinations → Unsplash → Picsum → صورة ملونة
- 3 مصادر للذكاء الاصطناعي: DeepSeek → Google → Groq
- نظام إعادة المحاولة التلقائي
- استخراج الكلمات المفتاحية (عربي + إنجليزي)
- توليد شرح احترافي غير مكرر
"""

import json
import re
import io
import asyncio
import aiohttp
import os
import random
from PIL import Image, ImageDraw, ImageFont


def clean_text(text: str) -> str:
    if not text:
        return ""
    text = str(text).replace('\x00', '').replace('\0', '')
    text = re.sub(r'[\x01-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


async def extract_full_text_from_pdf(pdf_bytes: bytes) -> str:
    """استخراج النص من PDF مع إعادة المحاولة"""
    errors = []
    
    # محاولة 1: pdfplumber
    try:
        import pdfplumber
        def _extract():
            with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                pages = []
                for page in pdf.pages:
                    page_text = page.extract_text() or ""
                    if page_text.strip():
                        pages.append(page_text)
                return "\n\n".join(pages)
        loop = asyncio.get_event_loop()
        text = await asyncio.wait_for(loop.run_in_executor(None, _extract), timeout=60.0)
        if len(text.strip()) > 100:
            print("[PDF] pdfplumber success")
            return clean_text(text)
    except Exception as e:
        errors.append(f"pdfplumber: {e}")
    
    # محاولة 2: PyPDF2
    try:
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
        text = await asyncio.wait_for(loop.run_in_executor(None, _extract), timeout=60.0)
        if len(text.strip()) > 50:
            print("[PDF] PyPDF2 success")
            return clean_text(text)
    except Exception as e:
        errors.append(f"PyPDF2: {e}")
    
    raise RuntimeError(f"فشل استخراج النص: {' | '.join(errors)}")


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

_deepseek_keys = _load_keys("DEEPSEEK_API_KEYS") or [os.getenv("DEEPSEEK_API_KEY", "").strip()]
_google_keys = _load_keys("GOOGLE_API_KEYS") or [os.getenv("GOOGLE_API_KEY", "").strip()]
_groq_keys = _load_keys("GROQ_API_KEYS") or [os.getenv("GROQ_API_KEY", "").strip()]

_deepseek_keys = [k for k in _deepseek_keys if k]
_google_keys = [k for k in _google_keys if k]
_groq_keys = [k for k in _groq_keys if k]

print(f"[AI] DeepSeek: {len(_deepseek_keys)}, Google: {len(_google_keys)}, Groq: {len(_groq_keys)}")


# ═══════════════════════════════════════════════════════════════════════════════
# نظام التوليد مع إعادة المحاولة
# ═══════════════════════════════════════════════════════════════════════════════

async def _try_ai_providers(prompt: str, max_tokens: int = 8192, max_retries: int = 3) -> str:
    """تجربة جميع مزودي AI مع إعادة المحاولة"""
    
    # DeepSeek
    for key in _deepseek_keys[:3]:
        for attempt in range(max_retries):
            try:
                headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
                payload = {
                    "model": "deepseek-chat",
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": min(max_tokens, 8192),
                    "temperature": 0.9 if attempt > 0 else 0.7
                }
                async with aiohttp.ClientSession() as s:
                    async with s.post(
                        "https://api.deepseek.com/v1/chat/completions",
                        headers=headers, json=payload, timeout=aiohttp.ClientTimeout(90)
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            content = data["choices"][0]["message"]["content"].strip()
                            if len(content) > 100:
                                print(f"[DeepSeek] Success (attempt {attempt+1})")
                                return content
            except:
                continue
    
    # Google
    for key in _google_keys[:3]:
        for attempt in range(max_retries):
            try:
                from google import genai
                from google.genai import types as genai_types
                client = genai.Client(api_key=key)
                response = await asyncio.to_thread(
                    client.models.generate_content,
                    model="gemini-2.0-flash",
                    contents=prompt,
                    config=genai_types.GenerateContentConfig(
                        temperature=0.9 if attempt > 0 else 0.7,
                        max_output_tokens=max_tokens
                    )
                )
                content = response.text.strip()
                if len(content) > 100:
                    print(f"[Google] Success (attempt {attempt+1})")
                    return content
            except:
                continue
    
    # Groq
    for key in _groq_keys[:3]:
        for attempt in range(max_retries):
            try:
                headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
                payload = {
                    "model": "llama-3.3-70b-versatile",
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": min(max_tokens, 8192),
                    "temperature": 0.9 if attempt > 0 else 0.7
                }
                async with aiohttp.ClientSession() as s:
                    async with s.post(
                        "https://api.groq.com/openai/v1/chat/completions",
                        headers=headers, json=payload, timeout=aiohttp.ClientTimeout(60)
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            content = data["choices"][0]["message"]["content"].strip()
                            if len(content) > 100:
                                print(f"[Groq] Success (attempt {attempt+1})")
                                return content
            except:
                continue
    
    raise Exception("All AI providers failed")


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
    
    sorted_words = sorted(freq.items(), key=lambda x: x[1], reverse=True)
    keywords = [w[0] for w in sorted_words[:max_words]]
    
    if len(keywords) < 4:
        extra = re.findall(r'[\u0600-\u06FF]{3,}|[a-zA-Z]{3,}', text)
        for w in extra:
            if w not in keywords and w.lower() not in stop_words:
                keywords.append(w)
                if len(keywords) >= max_words:
                    break
    
    return keywords


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
# توليد شرح احتياطي احترافي (غير مكرر)
# ═══════════════════════════════════════════════════════════════════════════════

def _generate_fallback_narration(keywords: list, lecture_type: str, is_english: bool) -> str:
    kw = keywords[:4]
    
    if is_english:
        templates = [
            f"Let's begin with {kw[0]}. This is a fundamental concept. ",
            f"First, we need to understand what {kw[0]} means. ",
            f"Now, let's look at {kw[1]}. This is closely related to {kw[0]}. ",
            f"The relationship between {kw[0]} and {kw[1]} is important. ",
            f"Moving on to {kw[2]}. This concept helps us understand. ",
            f"An example of {kw[2]} in real life would be... ",
            f"Finally, we have {kw[3]}. This completes our understanding. ",
            f"To summarize: {kw[0]}, {kw[1]}, {kw[2]}, and {kw[3]}. ",
            f"A key takeaway is that these concepts are interconnected. ",
            f"This knowledge can be applied in various situations. "
        ]
    else:
        templates = [
            f"نبدأ بالحديث عن {kw[0]}. هذا مفهوم أساسي. ",
            f"أولاً، يجب أن نفهم معنى {kw[0]}. ",
            f"الآن، ننتقل إلى {kw[1]}. هذا مرتبط بـ {kw[0]}. ",
            f"العلاقة بين {kw[0]} و {kw[1]} مهمة جداً. ",
            f"ننتقل الآن إلى {kw[2]}. هذا يساعدنا على الفهم. ",
            f"مثال على {kw[2]} في الحياة الواقعية... ",
            f"أخيراً، نصل إلى {kw[3]}. هذا يكمل فهمنا. ",
            f"لتلخيص: {kw[0]}، {kw[1]}، {kw[2]}، و {kw[3]}. ",
            f"النقطة الأساسية أن هذه المفاهيم مترابطة. ",
            f"يمكن تطبيق هذه المعرفة في مواقف مختلفة. "
        ]
    
    narration = ""
    for i in range(15):
        narration += templates[i % len(templates)]
    
    return narration


# ═══════════════════════════════════════════════════════════════════════════════
# الدالة الرئيسية
# ═══════════════════════════════════════════════════════════════════════════════

async def analyze_lecture(text: str, dialect: str = "msa") -> dict:
    text = clean_text(text)
    if not text:
        raise ValueError("النص فارغ")
    
    is_eng = _is_english(text)
    print(f"[AI] اللغة: {'إنجليزية' if is_eng else 'عربية'}")
    
    keywords = _extract_keywords(text, 40)
    print(f"[AI] تم استخراج {len(keywords)} كلمة مفتاحية")
    
    if len(keywords) < 10:
        keywords = _extract_keywords(text, 50)
    
    ltype = _detect_type(text)
    print(f"[AI] نوع المحاضرة: {ltype}")
    
    wc = len(text.split())
    if wc < 300:
        ns = 3
    elif wc < 600:
        ns = 4
    elif wc < 1000:
        ns = 5
    else:
        ns = 6
    print(f"[AI] عدد الأقسام: {ns}")
    
    preview = text[:4000]
    
    # بناء prompt حسب اللغة واللهجة
    if is_eng and dialect in ["iraq", "egypt", "syria", "gulf", "msa"]:
        dial_map = {"iraq": "العراقية", "egypt": "المصرية", "syria": "الشامية", "gulf": "الخليجية", "msa": "الفصحى"}
        dial_name = dial_map.get(dialect, "العربية")
        prompt = f"""أنت معلم خبير. ترجم النص التالي إلى العربية واشرحه شرحاً مفصلاً باللهجة {dial_name}.
اكتب 20-25 جملة متنوعة لكل قسم. احتفظ بالمصطلحات الإنجليزية المهمة بين قوسين.

النص:
---
{preview}
---

أرجع JSON:
{{"title": "عنوان المحاضرة", "sections": [{{"title": "عنوان القسم", "keywords": ["م1", "م2", "م3", "م4"], "narration": "نص الشرح"}}], "summary": "ملخص"}}"""
    elif is_eng:
        prompt = f"""You are an expert teacher. Explain the following text in clear English.
Write 20-25 varied sentences per section.

Text:
---
{preview}
---

Return JSON:
{{"title": "Title", "sections": [{{"title": "Section", "keywords": ["k1","k2","k3","k4"], "narration": "Explanation"}}], "summary": "Summary"}}"""
    else:
        dial_map = {"iraq": "بالعراقي", "egypt": "بالمصري", "syria": "بالشامي", "gulf": "بالخليجي", "msa": "بالفصحى"}
        dial = dial_map.get(dialect, "بالفصحى")
        prompt = f"""أنت معلم خبير. اشرح النص التالي {dial}.
اكتب 20-25 جملة متنوعة لكل قسم.

النص:
---
{preview}
---

أرجع JSON:
{{"title": "عنوان المحاضرة", "sections": [{{"title": "عنوان القسم", "keywords": ["ك1","ك2","ك3","ك4"], "narration": "نص الشرح"}}], "summary": "ملخص"}}"""
    
    ai_secs = []
    title = keywords[0] if keywords else "محاضرة"
    summary = ""
    
    for attempt in range(3):
        try:
            print(f"[AI] محاولة توليد الشرح ({attempt+1}/3)...")
            content = await _try_ai_providers(prompt, 8192)
            content = re.sub(r'^```json\s*', '', content.strip())
            content = re.sub(r'\s*```$', '', content)
            res = json.loads(content)
            
            title = clean_text(res.get("title", title))
            ai_secs = res.get("sections", [])
            summary = clean_text(res.get("summary", ""))
            
            if len(ai_secs) >= ns - 1 and any(s.get("narration", "") for s in ai_secs):
                print(f"[AI] ✅ تم توليد {len(ai_secs)} قسم بنجاح")
                break
        except Exception as e:
            print(f"[AI] ❌ فشل المحاولة {attempt+1}: {e}")
    
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
            nar = _generate_fallback_narration(kw, ltype, is_eng)
        
        while len(kw) < 4:
            kw.append("concept" if is_eng else "مفهوم")
        
        if len(nar.split()) < 20:
            nar = nar + " " + _generate_fallback_narration(kw, ltype, is_eng)
        
        sections.append({
            "title": st,
            "keywords": kw[:4],
            "narration": nar,
            "duration_estimate": max(45, len(nar.split()) // 3),
            "_image_bytes": None
        })
    
    print(f"[IMG] ========== توليد {len(sections)} صورة ==========")
    for i, s in enumerate(sections):
        q = " ".join(s["keywords"][:4])
        
        for attempt in range(3):
            try:
                print(f"[IMG] القسم {i+1}: محاولة {attempt+1}...")
                s["_image_bytes"] = await fetch_image_for_keyword(q, s["title"], ltype, is_eng)
                if s["_image_bytes"] and len(s["_image_bytes"]) > 1000:
                    print(f"[IMG] ✅ القسم {i+1} تم بنجاح")
                    break
            except Exception as e:
                print(f"[IMG] ❌ القسم {i+1} فشل: {e}")
        
        if not s["_image_bytes"]:
            s["_image_bytes"] = _make_colored_image(q, (155, 89, 182), is_eng)
    
    return {
        "lecture_type": ltype,
        "title": title,
        "sections": sections,
        "summary": summary,
        "all_keywords": keywords,
        "is_english": is_eng
    }


# ═══════════════════════════════════════════════════════════════════════════════
# الصور - 4 مصادر مع إعادة المحاولة
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
            async with s.get(url, timeout=20) as r:
                if r.status == 200:
                    raw = await r.read()
                    if len(raw) > 5000:
                        return raw
    except:
        pass
    return None


async def _unsplash_generate(query: str) -> bytes | None:
    try:
        url = f"https://source.unsplash.com/featured/500x350/?{query.replace(' ', '-')[:50]},education"
        async with aiohttp.ClientSession() as s:
            async with s.get(url, timeout=15, allow_redirects=True) as r:
                if r.status == 200:
                    return await r.read()
    except:
        pass
    return None


async def _picsum_generate() -> bytes | None:
    try:
        async with aiohttp.ClientSession() as s:
            url = f"https://picsum.photos/500/350?random={random.randint(1, 1000)}"
            async with s.get(url, timeout=10) as r:
                if r.status == 200:
                    return await r.read()
    except:
        pass
    return None


async def fetch_image_for_keyword(keyword: str, section_title: str = "", lecture_type: str = "other", is_english: bool = False) -> bytes:
    keyword = clean_text(keyword) or ("concept" if is_english else "مفهوم")
    color = _TYPE_COLORS.get(lecture_type, _TYPE_COLORS['other'])
    
    # محاولة 1: Pollinations مع وصف مفصل
    prompt = f"educational illustration of {keyword}, simple clean style"
    img = await _pollinations_generate(prompt)
    if img:
        return img
    
    # محاولة 2: Pollinations مع وصف مختلف
    prompt2 = f"cartoon illustration of {keyword}, educational"
    img = await _pollinations_generate(prompt2)
    if img:
        return img
    
    # محاولة 3: Unsplash
    img = await _unsplash_generate(keyword)
    if img:
        return img
    
    # محاولة 4: Picsum
    img = await _picsum_generate()
    if img:
        return img
    
    # صورة احتياطية
    return _make_colored_image(keyword, color, is_english)
