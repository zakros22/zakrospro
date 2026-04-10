# -*- coding: utf-8 -*-
import json, re, io, asyncio, aiohttp, os, random
from PIL import Image, ImageDraw, ImageFont
from google import genai
from google.genai import types as genai_types

def clean_text(t):
    if not t: return ""
    t = str(t).replace('\x00','').replace('\0','')
    t = re.sub(r'[\x01-\x08\x0b\x0c\x0e-\x1f\x7f]', '', t)
    return re.sub(r'\s+', ' ', t).strip()

# API Keys
_google_keys = [k.strip() for k in os.getenv("GOOGLE_API_KEYS","").split(",") if k.strip()]
_groq_keys = [k.strip() for k in os.getenv("GROQ_API_KEYS","").split(",") if k.strip()]
_curr_g, _exh_g = 0, set()

def _next_google():
    global _curr_g
    if not _google_keys: return None
    for _ in range(len(_google_keys)):
        k = _google_keys[_curr_g % len(_google_keys)]
        if k not in _exh_g: return k
        _curr_g += 1
    return None

async def _ai_gen(prompt, max_t=8192):
    # Google
    for _ in range(len(_google_keys)*2):
        k = _next_google()
        if not k: break
        client = genai.Client(api_key=k)
        for m in ["gemini-2.0-flash", "gemini-2.0-flash-lite"]:
            try:
                r = await asyncio.to_thread(client.models.generate_content, model=m, contents=prompt, config=genai_types.GenerateContentConfig(temperature=0.7, max_output_tokens=max_t))
                return r.text.strip()
            except Exception as e:
                if "429" in str(e) or "quota" in str(e).lower(): _exh_g.add(k); break
    # Groq
    for k in _groq_keys:
        for m in ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"]:
            try:
                headers = {"Authorization": f"Bearer {k}", "Content-Type": "application/json"}
                payload = {"model": m, "messages": [{"role": "user", "content": prompt}], "max_tokens": min(max_t, 8192), "temperature": 0.7}
                async with aiohttp.ClientSession() as s:
                    async with s.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload, timeout=60) as r:
                        if r.status == 200: return (await r.json())["choices"][0]["message"]["content"].strip()
            except: continue
    raise Exception("All AI failed")

def _extract_keywords(t, max_w=30):
    t = clean_text(t)
    stop = {'و','في','من','على','إلى','أن','هو','هي','هذا','هذه','كان','كانت','مع','ما','لا','عن','إذا','لم','لن','قد','ثم','أو','أم','لكن','حتى','بل','كل','بعض','the','a','an','is','are','was','were','of','to','in','that','it','be','for','on','with','as','at','by','this','and','or','but'}
    words = re.findall(r'[\u0600-\u06FF]{4,}|[a-zA-Z]{4,}', t)
    freq = {}
    for w in words:
        wl = w.lower()
        if wl not in stop: freq[w] = freq.get(w, 0) + 1
    return [w[0] for w in sorted(freq.items(), key=lambda x: x[1], reverse=True)[:max_w]]

def _detect_type(t):
    t = clean_text(t).lower()
    med = ['مرض','علاج','طبيب','جراحة','دواء','تشخيص','مريض','قلب','دم','خلية','ورم','سرطان']
    math = ['معادلة','دالة','تفاضل','تكامل','جبر','هندسة','رياضيات']
    phys = ['قوة','طاقة','حركة','سرعة','جاذبية','كهرباء','مغناطيس','فيزياء']
    chem = ['تفاعل','عنصر','مركب','جزيء','ذرة','حمض','قاعدة','كيمياء']
    hist = ['تاريخ','حرب','معركة','حضارة','إمبراطورية','ملك','ثورة']
    bio = ['نبات','حيوان','بيئة','وراثة','تطور','خلية']
    scores = {'medicine': sum(1 for k in med if k in t), 'math': sum(1 for k in math if k in t), 'physics': sum(1 for k in phys if k in t), 'chemistry': sum(1 for k in chem if k in t), 'history': sum(1 for k in hist if k in t), 'biology': sum(1 for k in bio if k in t)}
    best = max(scores, key=scores.get)
    return best if scores[best] > 1 else 'other'

async def analyze_lecture(text, dialect="msa"):
    text = clean_text(text)
    if not text: raise ValueError("Empty")
    keywords = _extract_keywords(text, 40)
    ltype = _detect_type(text)
    wc = len(text.split())
    ns = 3 if wc < 300 else 4 if wc < 600 else 5 if wc < 1000 else 6
    teacher = {'medicine':'طبيب','math':'أستاذ رياضيات','physics':'فيزيائي','chemistry':'كيميائي','history':'مؤرخ','biology':'عالم أحياء','other':'معلم'}.get(ltype,'معلم')
    dial = {"iraq":"بالعراقي","egypt":"بالمصري","syria":"بالشامي","gulf":"بالخليجي","msa":"بالفصحى"}.get(dialect,"بالفصحى")
    prompt = f"""أنت {teacher}. اشرح {dial}. اكتب 15-20 جملة متنوعة لكل قسم. النص: {text[:4000]}. الكلمات: {', '.join(keywords[:15])}. أرجع JSON: {{"title": "عنوان", "sections": [{{"title": "", "keywords": ["","","",""], "narration": ""}}]}}"""
    try:
        content = await _ai_gen(prompt, 8192)
        content = re.sub(r'^```json\s*', '', content.strip())
        content = re.sub(r'\s*```$', '', content)
        res = json.loads(content)
        title = clean_text(res.get("title", keywords[0]))
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
            idx = (i*4) % len(keywords)
            kw = [keywords[(idx+j)%len(keywords)] for j in range(4)]
            st = kw[0] if kw else f"قسم {i+1}"
            nar = f"نتعرف على {', '.join(kw[:3])}. " * 15
        while len(kw) < 4: kw.append("مفهوم")
        sections.append({"title": st, "keywords": kw[:4], "narration": nar, "duration_estimate": max(45, len(nar.split())//3), "_image_bytes": None})
    for s in sections:
        q = " ".join(s["keywords"][:3])
        s["_image_bytes"] = await fetch_image_for_keyword(q, s["title"], ltype)
    return {"lecture_type": ltype, "title": title, "sections": sections, "summary": f"شرحنا: {', '.join(keywords[:8])}", "all_keywords": keywords}

async def extract_full_text_from_pdf(pdf_bytes):
    import PyPDF2
    r = PyPDF2.PdfReader(io.BytesIO(pdf_bytes))
    pages = [p.extract_text() or "" for p in r.pages if p.extract_text()]
    return clean_text("\n\n".join(pages))

# Images
_COLORS = {'medicine': (231,76,126), 'math': (52,152,219), 'physics': (52,152,219), 'chemistry': (46,204,113), 'history': (230,126,34), 'biology': (46,204,113), 'other': (155,89,182)}

def _get_font(sz):
    for p in ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]:
        if os.path.exists(p):
            try: return ImageFont.truetype(p, sz)
            except: pass
    return ImageFont.load_default()

def _make_image(kw, col):
    kw = clean_text(kw) or "مفهوم"
    W, H = 500, 350
    img = Image.new("RGB", (W, H), (255,255,255))
    d = ImageDraw.Draw(img)
    for y in range(H):
        t = y/H
        r, g, b = int(255*(1-t)+col[0]*t*0.2), int(255*(1-t)+col[1]*t*0.2), int(255*(1-t)+col[2]*t*0.2)
        d.line([(0,y), (W,y)], fill=(r,g,b))
    d.rounded_rectangle([(10,10), (W-10,H-10)], radius=20, outline=col, width=8)
    d.ellipse([(W//2-60, H//2-60), (W//2+60, H//2+60)], fill=(*col, 25))
    f = _get_font(32)
    try:
        import arabic_reshaper; from bidi.algorithm import get_display
        kw = get_display(arabic_reshaper.reshape(kw[:30]))
    except: pass
    lines, cur = [], []
    for w in kw.split():
        cur.append(w)
        line = ' '.join(cur)
        try:
            if f.getbbox(line)[2] - f.getbbox(line)[0] > W - 60:
                cur.pop(); lines.append(' '.join(cur)); cur = [w]
        except: pass
    if cur: lines.append(' '.join(cur))
    y = H//2 - (len(lines)*40)//2
    for line in lines:
        try: tw = f.getbbox(line)[2] - f.getbbox(line)[0]
        except: tw = len(line)*18
        x = (W-tw)//2
        d.text((x+3, y+3), line, fill=(200,200,200), font=f)
        d.text((x, y), line, fill=col, font=f)
        y += 45
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=90)
    return buf.getvalue()

async def _pollinations(prompt):
    import urllib.parse
    try:
        async with aiohttp.ClientSession() as s:
            url = f"https://image.pollinations.ai/prompt/{urllib.parse.quote(prompt[:200])}?width=500&height=350&nologo=true"
            async with s.get(url, timeout=15) as r:
                if r.status == 200: return await r.read()
    except: pass
    return None

async def _picsum():
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(f"https://picsum.photos/500/350?random={random.randint(1,1000)}", timeout=10) as r:
                if r.status == 200: return await r.read()
    except: pass
    return None

async def fetch_image_for_keyword(keyword, section_title="", lecture_type="other", image_search_en=""):
    keyword = clean_text(keyword) or "مفهوم"
    col = _COLORS.get(lecture_type, _COLORS['other'])
    img = await _pollinations(f"educational illustration of {keyword}")
    if img: return img
    img = await _picsum()
    if img: return img
    return _make_image(keyword, col)
