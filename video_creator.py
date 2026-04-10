# -*- coding: utf-8 -*-
import asyncio, io, os, subprocess, tempfile
from PIL import Image, ImageDraw, ImageFont

W, H = 854, 480
WATERMARK = "@zakros_probot"
COLORS = [(231,76,126), (52,152,219), (46,204,113), (155,89,182), (230,126,34)]

def estimate_encoding_seconds(t): return max(20, t*0.6)

def _font(sz):
    for p in ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]:
        if os.path.exists(p):
            try: return ImageFont.truetype(p, sz)
            except: pass
    return ImageFont.load_default()

def _arabic(txt):
    if not txt: return ""
    try:
        import arabic_reshaper; from bidi.algorithm import get_display
        if any('\u0600'<=c<='\u06FF' for c in txt): return get_display(arabic_reshaper.reshape(txt))
    except: pass
    return txt

def _tw(txt, f):
    try: return f.getbbox(txt)[2]-f.getbbox(txt)[0]
    except: return len(txt)*(f.size//2)

def _draw(d, x, y, txt, f, col):
    txt = _arabic(txt)
    d.text((x+2,y+2), txt, fill=(200,200,200), font=f)
    d.text((x,y), txt, fill=col, font=f)

def _welcome():
    fd, p = tempfile.mkstemp(suffix=".jpg"); os.close(fd)
    img = Image.new("RGB", (W, H), (255,255,255)); d = ImageDraw.Draw(img)
    d.rectangle([(0,0),(W,8)], fill=COLORS[0]); d.rectangle([(0,H-8),(W,H)], fill=COLORS[0])
    f = _font(60); wm = WATERMARK; ww = _tw(wm, f); x = (W-ww)//2
    _draw(d, x, H//2-40, wm, f, COLORS[0])
    f2 = _font(36); wel = "أهلاً ومرحباً بكم"; w2 = _tw(_arabic(wel), f2); x2 = (W-w2)//2
    _draw(d, x2, H//2+30, wel, f2, (44,62,80))
    img.save(p, "JPEG", quality=90); return p

def _title(txt):
    fd, p = tempfile.mkstemp(suffix=".jpg"); os.close(fd)
    img = Image.new("RGB", (W, H), (255,255,255)); d = ImageDraw.Draw(img)
    d.rectangle([(0,0),(W,6)], fill=COLORS[1])
    f = _font(38); tw = _tw(_arabic(txt), f); x = (W-tw)//2
    _draw(d, x, H//2-20, txt, f, (44,62,80))
    img.save(p, "JPEG", quality=90); return p

def _map(titles):
    fd, p = tempfile.mkstemp(suffix=".jpg"); os.close(fd)
    img = Image.new("RGB", (W, H), (255,255,255)); d = ImageDraw.Draw(img)
    d.rectangle([(0,0),(W,6)], fill=COLORS[2])
    f = _font(30); mt = "📋 خريطة المحاضرة"; w = _tw(_arabic(mt), f); x = (W-w)//2
    _draw(d, x, 30, mt, f, COLORS[2])
    y = 90
    for i, t in enumerate(titles):
        col = COLORS[i%len(COLORS)]
        d.ellipse([(30,y),(52,y+22)], fill=col)
        d.text((41,y+3), str(i+1), fill=(255,255,255), font=_font(15))
        _draw(d, 70, y, t[:35], _font(20), (44,62,80))
        y += 55
    img.save(p, "JPEG", quality=90); return p

def _sec_title(txt, idx):
    fd, p = tempfile.mkstemp(suffix=".jpg"); os.close(fd)
    col = COLORS[idx%len(COLORS)]
    img = Image.new("RGB", (W, H), (255,255,255)); d = ImageDraw.Draw(img)
    d.rectangle([(0,0),(W,6)], fill=col)
    cx, cy = W//2, H//2-40
    d.ellipse([cx-40, cy-40, cx+40, cy+40], fill=col)
    num = str(idx+1); f = _font(40); nw = _tw(num, f)
    d.text((cx-nw//2, cy-22), num, fill=(255,255,255), font=f)
    f2 = _font(30); w2 = _tw(_arabic(txt), f2); x = (W-w2)//2
    _draw(d, x, cy+50, txt, f2, (44,62,80))
    img.save(p, "JPEG", quality=90); return p

def _content(img_bytes, keywords, sec_title, sec_idx, cur, total):
    fd, p = tempfile.mkstemp(suffix=".jpg"); os.close(fd)
    col = COLORS[sec_idx%len(COLORS)]
    img = Image.new("RGB", (W, H), (248,248,250)); d = ImageDraw.Draw(img)
    d.rectangle([(0,0),(W,6)], fill=col)
    fh = _font(18); hd = _arabic(sec_title[:40]); hw = _tw(hd, fh); hx = (W-hw)//2
    _draw(d, hx, 15, sec_title[:40], fh, (44,62,80))
    if img_bytes:
        try:
            pil = Image.open(io.BytesIO(img_bytes)).convert("RGB")
            iw, ih = pil.size; s = min(500/iw, 250/ih); nw, nh = int(iw*s), int(ih*s)
            pil = pil.resize((nw, nh), Image.LANCZOS)
            px, py = (W-nw)//2, 50+(250-nh)//2
            d.rounded_rectangle([(px-5,py-5),(px+nw+5,py+nh+5)], radius=10, outline=col, width=4)
            img.paste(pil, (px, py))
        except: pass
    fk = _font(20); vis = keywords[:cur+1]
    for i, kw in enumerate(vis):
        kcol = COLORS[i%len(COLORS)]; kwt = _arabic(kw); kw_w = _tw(kwt, fk)
        cx, cy = 100+(i%2)*350, 330+(i//2)*40
        d.rounded_rectangle([(cx-10,cy-5),(cx+kw_w+10,cy+30)], radius=8, fill=(*kcol,20), outline=kcol, width=2)
        d.text((cx, cy), kwt, fill=kcol, font=fk)
    dot_y = H-30
    for i in range(total):
        dx = (W-total*25)//2 + i*25
        dot_c = col if i<=cur else (200,200,200); r = 6 if i<=cur else 4
        d.ellipse([(dx-r, dot_y-r), (dx+r, dot_y+r)], fill=dot_c)
    fw = _font(12); wm_w = _tw(WATERMARK, fw)
    d.text((W-wm_w-20, H-25), WATERMARK, fill=col, font=fw)
    img.save(p, "JPEG", quality=92); return p

def _summary(keywords):
    fd, p = tempfile.mkstemp(suffix=".jpg"); os.close(fd)
    img = Image.new("RGB", (W, H), (255,255,255)); d = ImageDraw.Draw(img)
    d.rectangle([(0,0),(W,8)], fill=COLORS[0]); d.rectangle([(0,H-8),(W,H)], fill=COLORS[0])
    f = _font(30); mt = "📋 ملخص المحاضرة"; w = _tw(_arabic(mt), f); x = (W-w)//2
    _draw(d, x, 35, mt, f, (44,62,80))
    y = 90; f2 = _font(18)
    for i, kw in enumerate(keywords[:12]):
        col = COLORS[i%len(COLORS)]; kwt = _arabic(kw); kw_w = _tw(kwt, f2)
        cx, cy = 50+(i%3)*250, y+(i//3)*45
        d.rounded_rectangle([(cx-10,cy-5),(cx+kw_w+10,cy+28)], radius=8, fill=(*col,20), outline=col, width=2)
        d.text((cx, cy), kwt, fill=col, font=f2)
    f3 = _font(26); th = "🙏 شكراً لحسن استماعكم"; w3 = _tw(_arabic(th), f3); x3 = (W-w3)//2
    _draw(d, x3, H-60, th, f3, COLORS[0])
    img.save(p, "JPEG", quality=90); return p

def _ffmpeg_seg(img, dur, aud, start, out):
    dstr = f"{dur:.3f}"
    if aud and os.path.exists(aud):
        cmd = ["ffmpeg", "-y", "-loop", "1", "-i", img, "-ss", f"{start:.3f}", "-t", dstr, "-i", aud, "-c:v", "libx264", "-preset", "fast", "-crf", "23", "-pix_fmt", "yuv420p", "-vf", f"scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2", "-r", "15", "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "2", "-shortest", "-t", dstr, out]
    else:
        cmd = ["ffmpeg", "-y", "-loop", "1", "-i", img, "-f", "lavfi", "-i", "anullsrc", "-c:v", "libx264", "-preset", "fast", "-crf", "23", "-pix_fmt", "yuv420p", "-vf", f"scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2", "-r", "15", "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "2", "-shortest", "-t", dstr, out]
    subprocess.run(cmd, capture_output=True)

def _ffmpeg_cat(segs, out):
    fd, lst = tempfile.mkstemp(suffix=".txt"); os.close(fd)
    with open(lst, "w") as f:
        for s in segs: f.write(f"file '{s}'\n")
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", out], capture_output=True)
    os.remove(lst)

def _build(sections, audios, title, all_kw):
    segs, tmps, total = [], [], 0
    p = _welcome(); tmps.append(p); segs.append({"img":p,"audio":None,"audio_start":0,"dur":3.5}); total+=3.5
    p = _title(title); tmps.append(p); segs.append({"img":p,"audio":None,"audio_start":0,"dur":4}); total+=4
    p = _map([s.get("title","") for s in sections]); tmps.append(p); segs.append({"img":p,"audio":None,"audio_start":0,"dur":5}); total+=5
    for i, (s, a) in enumerate(zip(sections, audios)):
        p = _sec_title(s.get("title",f"قسم {i+1}"), i); tmps.append(p); segs.append({"img":p,"audio":None,"audio_start":0,"dur":3}); total+=3
        kw = s.get("keywords",["مفهوم"]); img = s.get("_image_bytes"); aud = a.get("audio"); dur = max(a.get("duration",30),5); kd = dur/len(kw)
        ap = None
        if aud:
            af, ap = tempfile.mkstemp(suffix=".mp3"); os.close(af)
            with open(ap, "wb") as f: f.write(aud); tmps.append(ap)
        for j in range(len(kw)):
            p = _content(img, kw, s.get("title",""), i, j, len(kw)); tmps.append(p)
            segs.append({"img":p,"audio":ap,"audio_start":j*kd,"dur":kd}); total+=kd
    p = _summary(all_kw); tmps.append(p); segs.append({"img":p,"audio":None,"audio_start":0,"dur":6}); total+=6
    return segs, tmps, total

def _encode(segs, out):
    paths = []
    try:
        for i, s in enumerate(segs):
            fd, p = tempfile.mkstemp(suffix=".mp4"); os.close(fd); paths.append(p)
            _ffmpeg_seg(s["img"], s["dur"], s["audio"], s["audio_start"], p)
        _ffmpeg_cat(paths, out)
    finally:
        for p in paths:
            try: os.remove(p)
            except: pass

async def create_video_from_sections(sections, audio_results, lecture_data, output_path, dialect="msa", progress_cb=None):
    loop = asyncio.get_event_loop()
    title = lecture_data.get("title", "محاضرة")
    all_kw = lecture_data.get("all_keywords", [])
    for s in sections:
        if "keywords" not in s or not s["keywords"]: s["keywords"] = ["مفهوم"]
        if "_image_bytes" not in s: s["_image_bytes"] = None
    segs, tmps, total = await loop.run_in_executor(None, _build, sections, audio_results, title, all_kw)
    await loop.run_in_executor(None, _encode, segs, output_path)
    for p in tmps:
        try: os.remove(p)
        except: pass
    return total
