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
# API Keys - مع OpenRouter كمصدر ثالث
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
# استخراج الكلمات
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
    math = ['معادلة', 'دالة', 'تفاضل', 'تكامل', 'جبر', 'هندسة', 'رياضيات', 'equation', 'function', 'calculus']
    physics = ['قوة', 'طاقة', 'حركة', 'سرعة', 'جاذبية', 'كهرباء', 'مغناطيس', 'فيزياء', 'force', 'energy', 'motion']
    chemistry = ['تفاعل', 'عنصر', 'مركب', 'جزيء', 'ذرة', 'حمض', 'قاعدة', 'كيمياء', 'reaction', 'element', 'compound']
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


# ═══════════════════════════════════════════════════════════════════════════════
# خطة احتياطية خرافية - تولد شرحاً احترافياً محلياً
# ═══════════════════════════════════════════════════════════════════════════════

def _generate_fallback_narration(keywords: list, lecture_type: str, original_text: str, section_idx: int, total_sections: int) -> str:
    """
    توليد شرح احترافي محلياً إذا فشل AI.
    هذا يضمن أن الشرح دائماً احترافي ومناسب لنوع المحاضرة.
    """
    kw_str = '، '.join(keywords[:3])
    
    # مقدمات حسب نوع المحاضرة
    intros = {
        'medicine': f"دعونا نتحدث عن {kw_str}. هذا الموضوع مهم جداً في المجال الطبي. ",
        'math': f"الآن سنشرح {kw_str} بالتفصيل. الرياضيات لغة الكون. ",
        'physics': f"في هذا القسم ندرس {kw_str}. الفيزياء تفسر الظواهر من حولنا. ",
        'chemistry': f"نتعرف الآن على {kw_str} في الكيمياء. التفاعلات الكيميائية أساس حياتنا. ",
        'history': f"اليوم سنسافر عبر الزمن لنتعرف على {kw_str}. التاريخ يعلمنا دروساً قيمة. ",
        'biology': f"في علم الأحياء، ندرس {kw_str}. الحياة مليئة بالأسرار الرائعة. ",
        'other': f"مرحباً بكم في هذا القسم الذي سنتعرف فيه على {kw_str}. "
    }
    
    # تفاصيل حسب نوع المحاضرة
    details = {
        'medicine': [
            f"أولاً، يجب أن نفهم تعريف {keywords[0]} بشكل دقيق.",
            f"ثانياً، نناقش الأعراض والعلامات المرتبطة بـ {keywords[1]}.",
            f"ثالثاً، نستعرض طرق التشخيص المتاحة لـ {keywords[2]}.",
            f"رابعاً، نتعرف على خيارات العلاج الحديثة.",
            f"خامساً، نتحدث عن المضاعفات المحتملة وكيفية تجنبها.",
            f"سادساً، نناقش طرق الوقاية وأهميتها.",
            f"سابعاً، نستعرض أحدث الأبحاث في هذا المجال.",
            f"ثامناً، نذكر بعض الحالات السريرية للتوضيح.",
            f"تاسعاً، نجيب على الأسئلة الشائعة حول {keywords[0]}.",
            f"وأخيراً، نلخص أهم النقاط التي يجب تذكرها."
        ],
        'math': [
            f"لنبدأ بتعريف {keywords[0]} وفهم خصائصه الأساسية.",
            f"ثم نكتب المعادلة الرياضية الخاصة بـ {keywords[1]} ونحللها خطوة بخطوة.",
            f"بعد ذلك، نعطي مثالاً عددياً لتوضيح الفكرة بشكل عملي.",
            f"ثم نتحقق من صحة الحل ونتأكد من النتائج.",
            f"ننتقل إلى تطبيقات {keywords[2]} في الحياة العملية.",
            f"نناقش أيضاً الحالات الخاصة والشروط اللازمة لتطبيق هذه المعادلات.",
            f"نختم ببعض التمارين للتأكد من فهم الموضوع.",
            f"تذكروا دائماً أن التدريب هو مفتاح إتقان الرياضيات."
        ],
        'physics': [
            f"نبدأ بشرح القانون الفيزيائي الأساسي المتعلق بـ {keywords[0]}.",
            f"ثم نعرض تجربة عملية توضح هذا القانون بشكل ملموس.",
            f"نحلل النتائج ونستنتج العلاقات بين المتغيرات المختلفة.",
            f"نربط هذه المفاهيم بحياتنا اليومية، مثل تطبيقات {keywords[1]}.",
            f"نرى تطبيقات هذا القانون في حركة السيارات أو سقوط الأجسام.",
            f"نناقش أيضاً حدود تطبيق هذا القانون والحالات التي لا ينطبق فيها.",
            f"أخيراً، نلخص أهم ما تعلمناه عن {keywords[2]}."
        ],
        'chemistry': [
            f"نبدأ بكتابة المعادلة الكيميائية الموزونة الخاصة بـ {keywords[0]}.",
            f"نحدد المواد المتفاعلة والناتجة ونشرح دور كل منها.",
            f"نشرح شروط التفاعل مثل درجة الحرارة والضغط والمواد الحفازة.",
            f"نحسب كمية المواد المتفاعلة والناتجة باستخدام الحسابات الكيميائية.",
            f"نذكر تطبيقات هذا التفاعل في الصناعة والحياة اليومية.",
            f"نناقش المخاطر المحتملة وطرق التعامل الآمن مع {keywords[1]}.",
            f"نختم بمراجعة سريعة لأهم النقاط حول {keywords[2]}."
        ],
        'history': [
            f"نبدأ بذكر التاريخ والمكان الذي وقعت فيه أحداث {keywords[0]}.",
            f"نتعرف على الشخصيات الرئيسية وأدوارها في هذه الأحداث.",
            f"نسرد الأحداث بتسلسل زمني واضح منذ البداية وحتى النهاية.",
            f"نحلل الأسباب التي أدت إلى {keywords[1]} وتطورها.",
            f"نناقش النتائج والآثار التي ترتبت على هذه الأحداث.",
            f"نستخلص الدروس والعبر المستفادة من {keywords[2]}.",
            f"نختم بربط هذه الأحداث بالواقع المعاصر وأهميتها اليوم."
        ],
        'biology': [
            f"نبدأ بشرح التركيب الأساسي لـ {keywords[0]} ومكوناته.",
            f"ثم ننتقل إلى الوظائف الحيوية التي يؤديها {keywords[1]}.",
            f"نستخدم التشبيهات لتقريب المفاهيم، مثلاً نشبه الخلية بالمصنع الصغير.",
            f"نناقش أهمية هذه العمليات للحفاظ على الحياة.",
            f"نذكر بعض الأمراض المرتبطة بخلل هذه الوظائف وكيفية علاجها.",
            f"نختم بمراجعة سريعة وتلخيص لأهم المعلومات عن {keywords[2]}."
        ],
        'other': [
            f"نبدأ بتعريف {keywords[0]} وفهم معناه بدقة.",
            f"ثم نستعرض المعلومات المتعلقة بـ {keywords[1]} بالتفصيل مع أمثلة توضيحية.",
            f"نربط هذه المعلومات بالواقع العملي ونرى كيف تؤثر في حياتنا.",
            f"نجيب على الأسئلة الشائعة حول هذا الموضوع.",
            f"نذكر بعض النصائح والإرشادات المفيدة المتعلقة بـ {keywords[2]}.",
            f"أخيراً، نلخص أهم ما تم شرحه في هذا القسم."
        ]
    }
    
    intro = intros.get(lecture_type, intros['other'])
    detail_list = details.get(lecture_type, details['other'])
    
    # بناء الشرح
    narration = intro
    for sentence in detail_list:
        narration += sentence + " "
    
    # إضافة جمل إضافية من النص الأصلي إذا كانت متاحة
    sentences = re.split(r'(?<=[.!?؟])\s+', original_text)
    added = 0
    for s in sentences:
        if any(kw in s for kw in keywords[:3]) and s not in narration:
            narration += s + " "
            added += 1
            if added >= 5:
                break
    
    # تكرار إذا كان الشرح قصيراً
    if len(narration.split()) < 50:
        narration = (narration + " ") * 3
    
    return narration.strip()


# ═══════════════════════════════════════════════════════════════════════════════
# الدالة الرئيسية
# ═══════════════════════════════════════════════════════════════════════════════

async def analyze_lecture(text: str, dialect: str = "msa") -> dict:
    text = clean_text(text)
    if not text:
        raise ValueError("النص فارغ")
    
    keywords = _extract_keywords(text, 40)
    ltype = _detect_type(text)
    print(f"[AI] Detected type: {ltype}")
    
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
    
    prompt = f"""أنت {teacher} تشرح لطلابك. اشرح {dial}.

**تعليمات صارمة:**
- اكتب شرحاً كاملاً ومتنوعاً (20-25 جملة) لكل قسم.
- لا تكرر نفس الجملة أبداً.
- فسر المصطلحات، أعط أمثلة واقعية، اربط الأفكار.
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
            # ✅ استخدام الخطة الاحتياطية الخرافية
            nar = _generate_fallback_narration(kw, ltype, text, i, ns)
        
        while len(kw) < 4:
            kw.append("مفهوم")
        
        sections.append({
            "title": st, "keywords": kw[:4], "narration": nar,
            "duration_estimate": max(45, len(nar.split()) // 3), "_image_bytes": None
        })
    
    for s in sections:
        q = " ".join(s["keywords"][:4])
        s["_image_bytes"] = await fetch_image_for_keyword(q, s["title"], ltype)
    
    return {"lecture_type": ltype, "title": title, "sections": sections, "summary": summary, "all_keywords": keywords}


# ═══════════════════════════════════════════════════════════════════════════════
# الصور الخرافية
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
    
    img = await _pollinations_generate(f"professional educational illustration of {keyword}, high quality, cartoon style")
    if img:
        return img
    img = await _unsplash_generate(keyword)
    if img:
        return img
    img = await _picsum_generate()
    if img:
        return img
    return _make_colored_image(keyword, color)
