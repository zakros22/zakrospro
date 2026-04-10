# -*- coding: utf-8 -*-
import asyncio
import io
import os
import subprocess
import tempfile
from PIL import Image as PILImage, ImageDraw, ImageFont

TARGET_W, TARGET_H = 854, 480
WATERMARK = "@zakros_probot"

COLORS = [(231,76,126), (52,152,219), (46,204,113), (155,89,182), (230,126,34)]

def estimate_encoding_seconds(t):
    return max(20, t * 0.6)

def _get_font(size):
    for p in ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except:
                pass
    return ImageFont.load_default()

def _arabic(text):
    if not text:
        return ""
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
        if any('\u0600' <= c <= '\u06FF' for c in text):
            return get_display(arabic_reshaper.reshape(text))
    except:
        pass
    return text

def _text_width(text, font):
    try:
        bbox = font.getbbox(text)
        return bbox[2] - bbox[0]
    except:
        return len(text) * (font.size // 2)

def _welcome():
    fd, p = tempfile.mkstemp(suffix=".jpg")
    os.close(fd)
    img = PILImage.new("RGB", (TARGET_W, TARGET_H), (255,255,255))
    d = ImageDraw.Draw(img)
    d.rectangle([(0,0), (TARGET_W,8)], fill=COLORS[0])
    d.rectangle([(0,TARGET_H-8), (TARGET_W,TARGET_H)], fill=COLORS[0])
    f = _get_font(60)
    w = _text_width(WATERMARK, f)
    x = (TARGET_W - w) // 2
    d.text((x, TARGET_H//2 - 40), WATERMARK, fill=COLORS[0], font=f)
    f2 = _get_font(36)
    welcome = _arabic("أهلاً ومرحباً بكم")
    w2 = _text_width(welcome, f2)
    x2 = (TARGET_W - w2) // 2
    d.text((x2, TARGET_H//2 + 30), welcome, fill=(44,62,80), font=f2)
    img.save(p, "JPEG", quality=90)
    return p

def _title(title):
    fd, p = tempfile.mkstemp(suffix=".jpg")
    os.close(fd)
    img = PILImage.new("RGB", (TARGET_W, TARGET_H), (255,255,255))
    d = ImageDraw.Draw(img)
    d.rectangle([(0,0), (TARGET_W,6)], fill=COLORS[1])
    f = _get_font(38)
    title = _arabic(title)
    w = _text_width(title, f)
    x = (TARGET_W - w) // 2
    d.text((x, TARGET_H//2 - 20), title, fill=(44,62,80), font=f)
    img.save(p, "JPEG", quality=90)
    return p

def _map(titles):
    fd, p = tempfile.mkstemp(suffix=".jpg")
    os.close(fd)
    img = PILImage.new("RGB", (TARGET_W, TARGET_H), (255,255,255))
    d = ImageDraw.Draw(img)
    d.rectangle([(0,0), (TARGET_W,6)], fill=COLORS[2])
    f = _get_font(30)
    mt = _arabic("📋 خريطة المحاضرة")
    w = _text_width(mt, f)
    x = (TARGET_W - w) // 2
    d.text((x, 30), mt, fill=COLORS[2], font=f)
    y = 90
    for i, t in enumerate(titles):
        col = COLORS[i % len(COLORS)]
        d.ellipse([(30,y), (52,y+22)], fill=col)
        d.text((41,y+3), str(i+1), fill=(255,255,255), font=_get_font(15))
        d.text((70,y), _arabic(t[:35]), fill=(44,62,80), font=_get_font(20))
        y += 55
    img.save(p, "JPEG", quality=90)
    return p

def _sec_title(title, idx):
    fd, p = tempfile.mkstemp(suffix=".jpg")
    os.close(fd)
    col = COLORS[idx % len(COLORS)]
    img = PILImage.new("RGB", (TARGET_W, TARGET_H), (255,255,255))
    d = ImageDraw.Draw(img)
    d.rectangle([(0,0), (TARGET_W,6)], fill=col)
    cx, cy = TARGET_W//2, TARGET_H//2 - 40
    d.ellipse([cx-40, cy-40, cx+40, cy+40], fill=col)
    num = str(idx + 1)
    f = _get_font(40)
    w = _text_width(num, f)
    d.text((cx - w//2, cy - 22), num, fill=(255,255,255), font=f)
    f2 = _get_font(30)
    title = _arabic(title)
    w2 = _text_width(title, f2)
    x = (TARGET_W - w2) // 2
    d.text((x, cy + 50), title, fill=(44,62,80), font=f2)
    img.save(p, "JPEG", quality=90)
    return p

def _content(image_bytes, keywords, sec_title, sec_idx, cur, total):
    fd, p = tempfile.mkstemp(suffix=".jpg")
    os.close(fd)
    col = COLORS[sec_idx % len(COLORS)]
    img = PILImage.new("RGB", (TARGET_W, TARGET_H), (248,248,250))
    d = ImageDraw.Draw(img)
    d.rectangle([(0,0), (TARGET_W,6)], fill=col)
    fh = _get_font(18)
    hd = _arabic(sec_title[:40])
    hw = _text_width(hd, fh)
    hx = (TARGET_W - hw) // 2
    d.text((hx, 15), hd, fill=(44,62,80), font=fh)
    
    if image_bytes:
        try:
            pil = PILImage.open(io.BytesIO(image_bytes)).convert("RGB")
            iw, ih = pil.size
            s = min(500/iw, 250/ih)
            nw, nh = int(iw*s), int(ih*s)
            pil = pil.resize((nw, nh), PILImage.LANCZOS)
            px, py = (TARGET_W - nw)//2, 50 + (250 - nh)//2
            d.rounded_rectangle([(px-5,py-5), (px+nw+5,py+nh+5)], radius=10, outline=col, width=4)
            img.paste(pil, (px, py))
        except:
            pass
    
    fk = _get_font(20)
    vis = keywords[:cur+1]
    for i, kw in enumerate(vis):
        kcol = COLORS[i % len(COLORS)]
        kwt = _arabic(kw)
        kw_w = _text_width(kwt, fk)
        cx, cy = 100 + (i%2)*350, 330 + (i//2)*40
        d.rounded_rectangle([(cx-10,cy-5), (cx+kw_w+10,cy+30)], radius=8, fill=(*kcol,20), outline=kcol, width=2)
        d.text((cx, cy), kwt, fill=kcol, font=fk)
    
    dot_y = TARGET_H - 30
    for i in range(total):
        dx = (TARGET_W - total*25)//2 + i*25
        dot_c = col if i <= cur else (200,200,200)
        r = 6 if i <= cur else 4
        d.ellipse([(dx-r, dot_y-r), (dx+r, dot_y+r)], fill=dot_c)
    
    fw = _get_font(12)
    wm_w = _text_width(WATERMARK, fw)
    d.text((TARGET_W - wm_w - 20, TARGET_H - 25), WATERMARK, fill=col, font=fw)
    img.save(p, "JPEG", quality=92)
    return p

def _summary(keywords):
    fd, p = tempfile.mkstemp(suffix=".jpg")
    os.close(fd)
    img = PILImage.new("RGB", (TARGET_W, TARGET_H), (255,255,255))
    d = ImageDraw.Draw(img)
    d.rectangle([(0,0), (TARGET_W,8)], fill=COLORS[0])
    d.rectangle([(0,TARGET_H-8), (TARGET_W,TARGET_H)], fill=COLORS[0])
    f = _get_font(30)
    mt = _arabic("📋 ملخص المحاضرة")
    w = _text_width(mt, f)
    x = (TARGET_W - w) // 2
    d.text((x, 35), mt, fill=(44,62,80), font=f)
    y = 90
    f2 = _get_font(18)
    for i, kw in enumerate(keywords[:12]):
        col = COLORS[i % len(COLORS)]
        kwt = _arabic(kw)
        kw_w = _text_width(kwt, f2)
        cx, cy = 50 + (i%3)*250, y + (i//3)*45
        d.rounded_rectangle([(cx-10,cy-5), (cx+kw_w+10,cy+28)], radius=8, fill=(*col,20), outline=col, width=2)
        d.text((cx, cy), kwt, fill=col, font=f2)
    f3 = _get_font(26)
    th = _arabic("🙏 شكراً لحسن استماعكم")
    w3 = _text_width(th, f3)
    x3 = (TARGET_W - w3) // 2
    d.text((x3, TARGET_H - 60), th, fill=COLORS[0], font=f3)
    img.save(p, "JPEG", quality=90)
    return p

def _ffmpeg_seg(img, dur, aud, start, out):
    dstr = f"{dur:.3f}"
    a = ["-ss", f"{start:.3f}", "-t", dstr, "-i", aud] if aud else ["-f", "lavfi", "-i", "anullsrc"]
    cmd = ["ffmpeg", "-y", "-loop", "1", "-t", dstr, "-i", img, *a,
           "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p", "-r", "15",
           "-vf", "scale=854:480:force_original_aspect_ratio=decrease,pad=854:480:(ow-iw)/2:(oh-ih)/2",
           "-map", "0:v", "-map", "1:a", "-c:a", "aac", "-b:a", "96k", "-t", dstr, out]
    subprocess.run(cmd, capture_output=True)

def _ffmpeg_cat(segs, out):
    fd, lst = tempfile.mkstemp(suffix=".txt")
    os.close(fd)
    with open(lst, "w") as f:
        for s in segs:
            f.write(f"file '{s}'\n")
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", out], capture_output=True)
    os.remove(lst)

def _build(sections, audio_results, title, all_kw):
    segs, tmps, total = [], [], 0
    
    p = _welcome()
    tmps.append(p)
    segs.append({"img": p, "audio": None, "audio_start": 0, "dur": 3.5})
    total += 3.5
    
    p = _title(title)
    tmps.append(p)
    segs.append({"img": p, "audio": None, "audio_start": 0, "dur": 4})
    total += 4
    
    p = _map([s.get("title", "") for s in sections])
    tmps.append(p)
    segs.append({"img": p, "audio": None, "audio_start": 0, "dur": 5})
    total += 5
    
    for i, (s, a) in enumerate(zip(sections, audio_results)):
        p = _sec_title(s.get("title", f"قسم {i+1}"), i)
        tmps.append(p)
        segs.append({"img": p, "audio": None, "audio_start": 0, "dur": 3})
        total += 3
        
        kw = s.get("keywords", ["مفهوم"])
        img = s.get("_image_bytes")
        aud = a.get("audio")
        dur = max(a.get("duration", 30), 5)
        kd = dur / len(kw)
        
        ap = None
        if aud:
            af, ap = tempfile.mkstemp(suffix=".mp3")
            os.close(af)
            with open(ap, "wb") as f:
                f.write(aud)
            tmps.append(ap)
        
        for j in range(len(kw)):
            p = _content(img, kw, s.get("title", ""), i, j, len(kw))
            tmps.append(p)
            segs.append({"img": p, "audio": ap, "audio_start": j*kd, "dur": kd})
            total += kd
    
    p = _summary(all_kw)
    tmps.append(p)
    segs.append({"img": p, "audio": None, "audio_start": 0, "dur": 6})
    total += 6
    
    return segs, tmps, total

def _encode(segs, out):
    paths = []
    for i, s in enumerate(segs):
        fd, p = tempfile.mkstemp(suffix=".mp4")
        os.close(fd)
        paths.append(p)
        _ffmpeg_seg(s["img"], s["dur"], s["audio"], s["audio_start"], p)
    _ffmpeg_cat(paths, out)
    for p in paths:
        os.remove(p)

async def create_video_from_sections(sections, audio_results, lecture_data, output_path, dialect="msa", progress_cb=None):
    loop = asyncio.get_event_loop()
    title = lecture_data.get("title", "محاضرة")
    all_kw = lecture_data.get("all_keywords", [])
    
    for s in sections:
        if "keywords" not in s or not s["keywords"]:
            s["keywords"] = ["مفهوم"]
        if "_image_bytes" not in s:
            s["_image_bytes"] = None
    
    segs, tmps, total = await loop.run_in_executor(None, _build, sections, audio_results, title, all_kw)
    await loop.run_in_executor(None, _encode, segs, output_path)
    
    for p in tmps:
        try:
            os.remove(p)
        except:
            pass
    
    return total
