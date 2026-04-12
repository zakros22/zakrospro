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
    if not text:
        return ""
    text = str(text).replace('\x00', '').replace('\0', '')
    text = re.sub(r'[\x01-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


async def extract_full_text_from_pdf(pdf_bytes: bytes) -> str:
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
    text = await asyncio.wait_for(loop.run_in_executor(None, _extract), timeout=90.0)
    return clean_text(text)


# ═══════════════════════════════════════════════════════════════════════════════
# API Keys
# ═══════════════════════════════════════════════════════════════════════════════

_google_keys = [k.strip() for k in os.getenv("GOOGLE_API_KEYS", "").split(",") if k.strip()]
_current_google_idx = 0
_exhausted_google = set()

_groq_keys = [k.strip() for k in os.getenv("GROQ_API_KEYS", "").split(",") if k.strip()]
_current_groq_idx = 0
_exhausted_groq = set()

_openrouter_keys = [k.strip() for k in os.getenv("OPENROUTER_API_KEYS", "").split(",") if k.strip()]
_current_or_idx = 0
_exhausted_or = set()

print(f"[AI] Google: {len(_google_keys)}, Groq: {len(_groq_keys)}, OpenRouter: {len(_openrouter_keys)}")


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


def _mark_google_exhausted(k):
    global _current_google_idx
    _exhausted_google.add(k)
    _current_google_idx += 1


def _next_groq_key():
    global _current_groq_idx
    if not _groq_keys:
        return None
    for _ in range(len(_groq_keys)):
        k = _groq_keys[_current_groq_idx % len(_groq_keys)]
        if k not in _exhausted_groq:
            return k
        _current_groq_idx += 1
    return None


def _mark_groq_exhausted(k):
    global _current_groq_idx
    _exhausted_groq.add(k)
    _current_groq_idx += 1


def _next_or_key():
    global _current_or_idx
    if not _openrouter_keys:
        return None
    for _ in range(len(_openrouter_keys)):
        k = _openrouter_keys[_current_or_idx % len(_openrouter_keys)]
        if k not in _exhausted_or:
            return k
        _current_or_idx += 1
    return None


def _mark_or_exhausted(k):
    global _current_or_idx
    _exhausted_or.add(k)
    _current_or_idx += 1


# ═══════════════════════════════════════════════════════════════════════════════
# دوال AI
# ═══════════════════════════════════════════════════════════════════════════════

async def _google_generate(prompt: str, max_tokens: int = 8192) -> str:
    models = ["gemini-2.0-flash", "gemini-2.0-flash-lite"]
    
    for _ in range(len(_google_keys) + 1):
        key = _next_google_key()
        if not key:
            break
        
        client = genai.Client(api_key=key)
        
        for model in models:
            try:
                response = await asyncio.to_thread(
                    client.models.generate_content,
                    model=model,
                    contents=prompt,
                    config=genai_types.GenerateContentConfig(temperature=0.9, max_output_tokens=max_tokens)
                )
                print(f"[AI] Google success: {model}")
                return response.text.strip()
            except Exception as e:
                err = str(e)
                if "429" in err or "RESOURCE_EXHAUSTED" in err or "quota" in err.lower():
                    _mark_google_exhausted(key)
                    print("[AI] Google key exhausted")
                    break
                else:
                    continue
    
    raise Exception("All Google keys exhausted")


async def _groq_generate(prompt: str, max_tokens: int = 8192) -> str:
    models = ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "gemma2-9b-it"]
    
    for _ in range(len(_groq_keys) + 1):
        key = _next_groq_key()
        if not key:
            break
        
        for model in models:
            try:
                headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
                payload = {
                    "model": model,
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
                            print(f"[AI] Groq success: {model}")
                            return data["choices"][0]["message"]["content"].strip()
                        elif resp.status == 429:
                            _mark_groq_exhausted(key)
                            print("[AI] Groq key exhausted")
                            break
            except:
                continue
    
    raise Exception("All Groq keys exhausted")


async def _openrouter_generate(prompt: str, max_tokens: int = 8192) -> str:
    models = [
        "google/gemini-2.0-flash-exp:free",
        "google/gemini-2.0-flash-lite-preview-02-05:free",
        "nvidia/llama-3.1-nemotron-70b-instruct:free",
        "meta-llama/llama-3.2-3b-instruct:free"
    ]
    
    for _ in range(len(_openrouter_keys) + 1):
        key = _next_or_key()
        if not key:
            break
        
        for model in models:
            try:
                headers = {
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://replit.com",
                    "X-Title": "Lecture Video Bot"
                }
                payload = {
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": min(max_tokens, 8192),
                    "temperature": 0.9
                }
                async with aiohttp.ClientSession() as s:
                    async with s.post(
                        "https://openrouter.ai/api/v1/chat/completions",
                        headers=headers, json=payload, timeout=aiohttp.ClientTimeout(90)
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            content = data["choices"][0]["message"]["content"]
                            if content and content.strip():
                                print(f"[AI] OpenRouter success: {model}")
                                return content.strip()
                        elif resp.status == 429:
                            _mark_or_exhausted(key)
                            print("[AI] OpenRouter key exhausted")
                            break
            except:
                continue
    
    raise Exception("All OpenRouter keys exhausted")


async def _ai_generate(prompt: str, max_tokens: int = 8192) -> str:
    if _google_keys:
        try:
            return await _google_generate(prompt, max_tokens)
        except Exception as e:
            print(f"[AI] Google failed: {e}")
    
    if _groq_keys:
        try:
            return await _groq_generate(prompt, max_tokens)
        except Exception as e:
            print(f"[AI] Groq failed: {e}")
    
    if _openrouter_keys:
        try:
            return await _openrouter_generate(prompt, max_tokens)
        except Exception as e:
            print(f"[AI] OpenRouter failed: {e}")
    
    raise Exception("All AI services failed")


# ═══════════════════════════════════════════════════════════════════════════════
# استخراج الكلمات وتحديد النوع
# ═══════════════════════════════════════════════════════════════════════════════

def _extract_keywords(text: str, max_words: int = 30) -> list:
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
    text = clean_text(text).lower()
    medical = ['مرض', 'علاج', 'طبيب', 'جراحة', 'دواء', 'تشخيص', 'مريض', 'قلب', 'دم', 'خلية', 'ورم', 'سرطان', 'endometriosis', 'cyst', 'inflammation']
    math = ['معادلة', 'دالة', 'تفاضل', 'تكامل', 'جبر', 'هندسة', 'رياضيات', 'equation', 'function', 'calculus', 'derivative', 'integral', 'matrix']
    physics = ['قوة', 'طاقة', 'حركة', 'سرعة', 'جاذبية', 'كهرباء', 'مغناطيس', 'فيزياء', 'force', 'energy', 'motion', 'velocity']
    chemistry = ['تفاعل', 'عنصر', 'مركب', 'جزيء', 'ذرة', 'حمض', 'قاعدة', 'كيمياء', 'reaction', 'element', 'compound', 'molecule']
    history = ['تاريخ', 'حرب', 'معركة', 'حضارة', 'إمبراطورية', 'ملك', 'ثورة', 'history', 'war', 'battle']
    biology = ['نبات', 'حيوان', 'بيئة', 'وراثة', 'تطور', 'خلية', 'biology', 'plant', 'animal', 'cell']
    
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


def _detect_has_equations(text: str) -> bool:
    """الكشف عن وجود معادلات رياضية"""
    patterns = [r'[=+\-*/^()]', r'\d+', r'[xyzXYZ]', r'\[.*\]', r'\(.*\)']
    for p in patterns:
        if re.search(p, text):
            return True
    return False


# ═══════════════════════════════════════════════════════════════════════════════
# توليد الأسئلة التفاعلية
# ═══════════════════════════════════════════════════════════════════════════════

def _generate_question(keywords: list, lecture_type: str, section_title: str) -> tuple:
    """توليد سؤال وجواب لكل قسم"""
    kw = keywords[0] if keywords else "المفهوم"
    
    questions = {
        'medicine': (
            f"❓ سؤال: ما هو تعريف {kw}؟ وما هي أبرز أعراضه؟",
            f"✅ الإجابة: {kw} هو ... (يتم شرحه في القسم). من أبرز أعراضه: ..."
        ),
        'math': (
            f"❓ سؤال: كيف يمكننا حل معادلة {kw}؟",
            f"✅ الإجابة: لحل معادلة {kw}، نتبع الخطوات التالية: ..."
        ),
        'physics': (
            f"❓ سؤال: ما هو القانون الفيزيائي المرتبط بـ {kw}؟",
            f"✅ الإجابة: القانون هو ... وينص على أن ..."
        ),
        'chemistry': (
            f"❓ سؤال: ما هي معادلة تفاعل {kw}؟ وما شروطه؟",
            f"✅ الإجابة: معادلة التفاعل هي ... وتحتاج إلى درجة حرارة ..."
        ),
        'history': (
            f"❓ سؤال: متى وقعت أحداث {kw}؟ ومن هي الشخصيات الرئيسية؟",
            f"✅ الإجابة: وقعت في عام ... وأهم شخصياتها: ..."
        ),
        'biology': (
            f"❓ سؤال: ما هو تركيب {kw}؟ وما وظيفته؟",
            f"✅ الإجابة: يتكون {kw} من ... ووظيفته الأساسية هي ..."
        ),
        'other': (
            f"❓ سؤال: ما هو {kw}؟ وما أهميته؟",
            f"✅ الإجابة: {kw} هو ... وتكمن أهميته في ..."
        )
    }
    
    return questions.get(lecture_type, questions['other'])


# ═══════════════════════════════════════════════════════════════════════════════
# الدالة الرئيسية - تحليل ذكي مع أسئلة تفاعلية
# ═══════════════════════════════════════════════════════════════════════════════

async def analyze_lecture(text: str, dialect: str = "msa") -> dict:
    text = clean_text(text)
    if not text:
        raise ValueError("النص فارغ")
    
    keywords = _extract_keywords(text, 40)
    ltype = _detect_type(text)
    has_equations = _detect_has_equations(text)
    
    print(f"[AI] Type: {ltype}, Has equations: {has_equations}")
    
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
        'medicine': 'طبيب استشاري', 'math': 'أستاذ رياضيات', 'physics': 'فيزيائي',
        'chemistry': 'كيميائي', 'history': 'مؤرخ', 'biology': 'عالم أحياء', 'other': 'معلم خبير'
    }
    teacher = teacher_map.get(ltype, 'معلم خبير')
    
    dial_map = {"iraq": "بالعراقي", "egypt": "بالمصري", "syria": "بالشامي", "gulf": "بالخليجي", "msa": "بالفصحى"}
    dial = dial_map.get(dialect, "بالفصحى")
    
    # تخصيص prompt حسب نوع المحاضرة
    if ltype == 'math' or has_equations:
        style_instruction = """
- اشرح المعادلات خطوة بخطوة.
- اكتب المعادلة كاملة ثم حللها.
- اشرح كل متغير وماذا يمثل.
- أعط مثالاً عددياً محلولاً.
"""
    elif ltype == 'medicine':
        style_instruction = """
- اشرح pathophysiology (الآلية المرضية).
- اذكر الأعراض والعلامات.
- اشرح طرق التشخيص.
- اذكر خيارات العلاج.
"""
    elif ltype == 'physics' or ltype == 'chemistry':
        style_instruction = """
- اذكر القانون أو المعادلة أولاً.
- اشرح كل رمز في المعادلة.
- أعط مثالاً تطبيقياً.
- اشرح الوحدات المستخدمة.
"""
    else:
        style_instruction = """
- اشرح المفاهيم بلغة واضحة.
- أعط أمثلة واقعية.
- اربط بين الأفكار.
"""
    
    prompt = f"""أنت {teacher} تشرح لطلابك. اشرح {dial}.

**تعليمات الشرح:**
{style_instruction}
- اكتب شرحاً كاملاً (20-25 جملة).
- لا تكرر الجمل.
- استخدم أسلوب المعلم: "دعونا نفهم..."، "لاحظوا معي...".

**النص:**
---
{preview}
---

**الكلمات:** {', '.join(keywords[:15])}

**المطلوب - {ns} أقسام:**
أرجع JSON:
{{
  "title": "عنوان المحاضرة",
  "sections": [
    {{
      "title": "عنوان القسم",
      "keywords": ["كلمة1", "كلمة2", "كلمة3", "كلمة4"],
      "narration": "نص الشرح (20-25 جملة)"
    }}
  ],
  "summary": "ملخص (6-8 جمل)"
}}"""
    
    ai_success = False
    title = keywords[0] if keywords else "محاضرة"
    ai_secs = []
    summary = f"شرحنا: {', '.join(keywords[:8])}"
    
    try:
        content = await _ai_generate(prompt, 8192)
        content = re.sub(r'^```json\s*', '', content.strip())
        content = re.sub(r'\s*```$', '', content)
        res = json.loads(content)
        title = clean_text(res.get("title", title))
        ai_secs = res.get("sections", [])
        summary = clean_text(res.get("summary", summary))
        ai_success = True
        print(f"[AI] AI generation successful")
    except Exception as e:
        print(f"[AI] AI failed, using fallback: {e}")
    
    sections = []
    for i in range(ns):
        if ai_success and i < len(ai_secs) and ai_secs[i].get("narration"):
            s = ai_secs[i]
            kw = [clean_text(k) for k in s.get("keywords", [])[:4]]
            st = clean_text(s.get("title", f"قسم {i+1}"))
            nar = clean_text(s.get("narration", ""))
        else:
            idx = (i * 4) % len(keywords)
            kw = [keywords[(idx + j) % len(keywords)] for j in range(4)]
            st = kw[0] if kw else f"قسم {i+1}"
            nar = _generate_fallback_narration(kw, ltype, text, i, ns)
        
        while len(kw) < 4:
            kw.append("مفهوم")
        
        # توليد سؤال تفاعلي للقسم
        question, answer = _generate_question(kw, ltype, st)
        
        sections.append({
            "title": st,
            "keywords": kw[:4],
            "narration": nar,
            "question": question,
            "answer": answer,
            "duration_estimate": max(45, len(nar.split()) // 3),
            "_image_bytes": None,
            "_has_equations": has_equations
        })
    
    for s in sections:
        q = " ".join(s["keywords"][:4])
        s["_image_bytes"] = await fetch_image_for_keyword(q, s["title"], ltype)
    
    return {
        "lecture_type": ltype,
        "title": title,
        "sections": sections,
        "summary": summary,
        "all_keywords": keywords,
        "has_equations": has_equations
    }


def _generate_fallback_narration(keywords: list, lecture_type: str, original_text: str, section_idx: int, total_sections: int) -> str:
    """خطة احتياطية ذكية حسب نوع المحاضرة"""
    kw_str = '، '.join(keywords[:3])
    
    if lecture_type == 'medicine':
        return f"نتحدث عن {kw_str}. تعريف {keywords[0]} هو الأساس. الأعراض تشمل {keywords[1]}. التشخيص يتم عبر {keywords[2]}. العلاج يشمل أدوية وجراحة. المضاعفات قد تكون خطيرة. الوقاية مهمة جداً. " * 8
    elif lecture_type == 'math':
        return f"لحل معادلة {kw_str}، نتبع خطوات محددة. أولاً، نحدد المتغيرات. ثانياً، نكتب المعادلة. ثالثاً، نبسط الطرفين. رابعاً، نعزل المتغير. خامساً، نتحقق من الحل. مثال: إذا كانت x + 2 = 5، فإن x = 3. " * 6
    elif lecture_type == 'physics':
        return f"قانون {kw_str} ينص على أن القوة تساوي الكتلة مضروبة في التسارع (F = ma). هذا يعني أنه كلما زادت الكتلة، زادت القوة المطلوبة. تطبيقات هذا القانون كثيرة في حياتنا اليومية. " * 7
    elif lecture_type == 'chemistry':
        return f"تفاعل {kw_str} يتم وفق معادلة كيميائية موزونة. المواد المتفاعلة هي {keywords[0]}، والنواتج هي {keywords[1]}. شروط التفاعل تشمل درجة حرارة وضغط محددين. " * 7
    elif lecture_type == 'history':
        return f"أحداث {kw_str} وقعت في فترة مهمة من التاريخ. الأسباب كانت متعددة. النتائج غيرت مجرى التاريخ. الشخصيات الرئيسية لعبت أدواراً حاسمة. " * 8
    else:
        sentences = re.split(r'(?<=[.!?؟])\s+', original_text)
        selected = []
        for s in sentences:
            if any(kw in s for kw in keywords[:3]):
                selected.append(s)
            if len(selected) >= 15:
                break
        if len(selected) < 5:
            selected = sentences[:20]
        return " ".join(selected) if selected else f"شرح مفصل عن {kw_str}. " * 15


# ═══════════════════════════════════════════════════════════════════════════════
# الصور
# ═══════════════════════════════════════════════════════════════════════════════

_TYPE_COLORS = {
    'medicine': (231, 76, 126), 'math': (52, 152, 219), 'physics': (52, 152, 219),
    'chemistry': (46, 204, 113), 'history': (230, 126, 34), 'biology': (46, 204, 113),
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


def _make_colored_image(keywords: str, color: tuple) -> bytes:
    keywords = clean_text(keywords) or "مفهوم"
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
    draw.rounded_rectangle([(15, 15), (W-15, H-15)], radius=15, outline=(*color, 100), width=2)
    draw.ellipse([(W//2-70, H//2-70), (W//2+70, H//2+70)], fill=(*color, 30))
    draw.ellipse([(W//2-50, H//2-50), (W//2+50, H//2+50)], outline=color, width=3)
    
    font = _get_font(32)
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
            url = f"https://image.pollinations.ai/prompt/{urllib.parse.quote(prompt[:200])}?width=500&height=350&nologo=true&model=flux"
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


async def fetch_image_for_keyword(keyword: str, section_title: str = "", lecture_type: str = "other", image_search_en: str = "") -> bytes:
    keyword = clean_text(keyword) or "مفهوم"
    color = _TYPE_COLORS.get(lecture_type, _TYPE_COLORS['other'])
    
    # تخصيص وصف الصورة حسب نوع المحاضرة
    if lecture_type == 'medicine':
        prompt = f"medical illustration of {keyword}, anatomy style, clean"
    elif lecture_type == 'math':
        prompt = f"math equation illustration of {keyword}, whiteboard style"
    elif lecture_type == 'physics':
        prompt = f"physics diagram of {keyword}, scientific illustration"
    elif lecture_type == 'chemistry':
        prompt = f"chemistry molecular structure of {keyword}"
    else:
        prompt = f"educational illustration of {keyword}, cartoon style"
    
    img = await _pollinations_generate(prompt)
    if img:
        return img
    img = await _unsplash_generate(keyword)
    if img:
        return img
    img = await _picsum_generate()
    if img:
        return img
    return _make_colored_image(keyword, color)
