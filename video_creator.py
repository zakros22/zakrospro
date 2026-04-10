# -*- coding: utf-8 -*-
import asyncio
import io
import os
import subprocess
import tempfile
from PIL import Image as PILImage, ImageDraw, ImageFont

TARGET_W, TARGET_H = 854, 480
WATERMARK = "@zakros_probot"

COLORS = [
    (231, 76, 126),   # وردي
    (52, 152, 219),   # أزرق
    (46, 204, 113),   # أخضر
    (155, 89, 182),   # بنفسجي
    (230, 126, 34),   # برتقالي
]

def estimate_encoding_seconds(total_video_seconds: float) -> float:
    return max(20.0, total_video_seconds * 0.6)


# ═══════════════════════════════════════════════════════════════════════════════
# تحميل الخط مع دعم عربي
# ═══════════════════════════════════════════════════════════════════════════════

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


def _prepare_arabic(text: str) -> str:
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


# ═══════════════════════════════════════════════════════════════════════════════
# شريحة المقدمة
# ═══════════════════════════════════════════════════════════════════════════════

def _draw_welcome() -> str:
    fd, path = tempfile.mkstemp(suffix=".jpg")
    os.close(fd)
    img = PILImage.new("RGB", (TARGET_W, TARGET_H), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    
    draw.rectangle([(0, 0), (TARGET_W, 8)], fill=COLORS[0])
    draw.rectangle([(0, TARGET_H-8), (TARGET_W, TARGET_H)], fill=COLORS[0])
    
    font = _get_font(60)
    try:
        bbox = font.getbbox(WATERMARK)
        w = bbox[2] - bbox[0]
    except:
        w = len(WATERMARK) * 35
    x = (TARGET_W - w) // 2
    draw.text((x, TARGET_H//2 - 40), WATERMARK, fill=COLORS[0], font=font)
    
    font2 = _get_font(36)
    welcome = _prepare_arabic("أهلاً ومرحباً بكم")
    try:
        bbox = font2.getbbox(welcome)
        w2 = bbox[2] - bbox[0]
    except:
        w2 = len(welcome) * 20
    x2 = (TARGET_W - w2) // 2
    draw.text((x2, TARGET_H//2 + 30), welcome, fill=(44, 62, 80), font=font2)
    
    img.save(path, "JPEG", quality=90)
    return path


# ═══════════════════════════════════════════════════════════════════════════════
# شريحة عنوان المحاضرة
# ═══════════════════════════════════════════════════════════════════════════════

def _draw_title(title: str) -> str:
    fd, path = tempfile.mkstemp(suffix=".jpg")
    os.close(fd)
    img = PILImage.new("RGB", (TARGET_W, TARGET_H), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    
    draw.rectangle([(0, 0), (TARGET_W, 6)], fill=COLORS[1])
    
    font = _get_font(38)
    title = _prepare_arabic(title)
    
    try:
        bbox = font.getbbox(title)
        w = bbox[2] - bbox[0]
    except:
        w = len(title) * 22
    
    x = (TARGET_W - w) // 2
    y = TARGET_H//2 - 20
    draw.text((x+2, y+2), title, fill=(200, 200, 200), font=font)
    draw.text((x, y), title, fill=(44, 62, 80), font=font)
    
    img.save(path, "JPEG", quality=90)
    return path


# ═══════════════════════════════════════════════════════════════════════════════
# شريحة خريطة الأقسام
# ═══════════════════════════════════════════════════════════════════════════════

def _draw_map(titles: list) -> str:
    fd, path = tempfile.mkstemp(suffix=".jpg")
    os.close(fd)
    img = PILImage.new("RGB", (TARGET_W, TARGET_H), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    
    draw.rectangle([(0, 0), (TARGET_W, 6)], fill=COLORS[2])
    
    font = _get_font(30)
    map_title = _prepare_arabic("📋 خريطة المحاضرة")
    try:
        bbox = font.getbbox(map_title)
        w = bbox[2] - bbox[0]
    except:
        w = len(map_title) * 18
    x = (TARGET_W - w) // 2
    draw.text((x, 30), map_title, fill=COLORS[2], font=font)
    
    y = 90
    font2 = _get_font(20)
    for i, t in enumerate(titles):
        color = COLORS[i % len(COLORS)]
        draw.ellipse([(30, y), (52, y+22)], fill=color)
        draw.text((41, y+3), str(i+1), fill=(255, 255, 255), font=_get_font(15))
        draw.text((70, y), _prepare_arabic(t[:35]), fill=(44, 62, 80), font=font2)
        y += 55
    
    img.save(path, "JPEG", quality=90)
    return path


# ═══════════════════════════════════════════════════════════════════════════════
# شريحة عنوان القسم
# ═══════════════════════════════════════════════════════════════════════════════

def _draw_section_title(title: str, idx: int) -> str:
    fd, path = tempfile.mkstemp(suffix=".jpg")
    os.close(fd)
    color = COLORS[idx % len(COLORS)]
    img = PILImage.new("RGB", (TARGET_W, TARGET_H), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    
    draw.rectangle([(0, 0), (TARGET_W, 6)], fill=color)
    
    cx, cy = TARGET_W//2, TARGET_H//2 - 40
    draw.ellipse([cx-40, cy-40, cx+40, cy+40], fill=color)
    
    font = _get_font(36)
    num = str(idx + 1)
    try:
        bbox = font.getbbox(num)
        w = bbox[2] - bbox[0]
    except:
        w = 20
    draw.text((cx - w//2, cy - 20), num, fill=(255, 255, 255), font=font)
    
    font2 = _get_font(30)
    title = _prepare_arabic(title)
    try:
        bbox = font2.getbbox(title)
        w2 = bbox[2] - bbox[0]
    except:
        w2 = len(title) * 17
    x = (TARGET_W - w2) // 2
    draw.text((x, cy + 50), title, fill=(44, 62, 80), font=font2)
    
    img.save(path, "JPEG", quality=90)
    return path


# ═══════════════════════════════════════════════════════════════════════════════
# شريحة المحتوى - صورة واحدة + الكلمات المفتاحية
# ═══════════════════════════════════════════════════════════════════════════════

def _draw_content_slide(
    image_bytes: bytes,
    keywords: list,
    section_title: str,
    section_idx: int,
    current_kw: int,
    total_kw: int,
) -> str:
    """شريحة محتوى: صورة واحدة + الكلمات المفتاحية تظهر تدريجياً"""
    fd, path = tempfile.mkstemp(suffix=".jpg")
    os.close(fd)
    
    color = COLORS[section_idx % len(COLORS)]
    img = PILImage.new("RGB", (TARGET_W, TARGET_H), (248, 248, 250))
    draw = ImageDraw.Draw(img)
    
    # شريط علوي
    draw.rectangle([(0, 0), (TARGET_W, 6)], fill=color)
    
    # عنوان القسم
    font_header = _get_font(18)
    header = _prepare_arabic(section_title[:40])
    try:
        bbox = font_header.getbbox(header)
        w = bbox[2] - bbox[0]
    except:
        w = len(header) * 10
    x = (TARGET_W - w) // 2
    draw.text((x, 15), header, fill=(44, 62, 80), font=font_header)
    
    # الصورة الرئيسية (واحدة للقسم كامل)
    img_y = 50
    if image_bytes:
        try:
            pil = PILImage.open(io.BytesIO(image_bytes)).convert("RGB")
            # تناسب الصورة
            max_w, max_h = 500, 250
            iw, ih = pil.size
            scale = min(max_w/iw, max_h/ih)
            nw, nh = int(iw*scale), int(ih*scale)
            pil = pil.resize((nw, nh), PILImage.LANCZOS)
            
            px = (TARGET_W - nw) // 2
            py = img_y + (max_h - nh) // 2
            
            draw.rounded_rectangle(
                [(px-5, py-5), (px+nw+5, py+nh+5)],
                radius=10, outline=color, width=4
            )
            img.paste(pil, (px, py))
        except:
            pass
    
    # الكلمات المفتاحية (تظهر تدريجياً)
    kw_y = 330
    font_kw = _get_font(20)
    
    # نعرض فقط الكلمات اللي وصلنا لها
    visible_kw = keywords[:current_kw+1]
    
    for i, kw in enumerate(visible_kw):
        kw_color = COLORS[i % len(COLORS)]
        kw_text = _prepare_arabic(kw)
        try:
            bbox = font_kw.getbbox(kw_text)
            kw_w = bbox[2] - bbox[0]
        except:
            kw_w = len(kw_text) * 12
        
        # توزيع الكلمات في سطر أو سطرين
        col = i % 2
        row = i // 2
        kx = 100 + col * 350
        ky = kw_y + row * 40
        
        # خلفية للكلمة
        draw.rounded_rectangle(
            [(kx-10, ky-5), (kx+kw_w+10, ky+30)],
            radius=8, fill=(*kw_color, 20), outline=kw_color, width=2
        )
        draw.text((kx, ky), kw_text, fill=kw_color, font=font_kw)
    
    # مؤشر التقدم
    dot_y = TARGET_H - 30
    dot_r = 6
    dot_gap = 25
    total_w = total_kw * dot_gap
    start_x = (TARGET_W - total_w) // 2
    
    for i in range(total_kw):
        dx = start_x + i * dot_gap
        dot_color = color if i <= current_kw else (200, 200, 200)
        r = dot_r if i <= current_kw else dot_r - 2
        draw.ellipse([(dx-r, dot_y-r), (dx+r, dot_y+r)], fill=dot_color)
    
    # حقوق
    font_wm = _get_font(12)
    try:
        bbox = font_wm.getbbox(WATERMARK)
        wm_w = bbox[2] - bbox[0]
    except:
        wm_w = len(WATERMARK) * 7
    draw.text((TARGET_W - wm_w - 20, TARGET_H - 25), WATERMARK, fill=color, font=font_wm)
    
    img.save(path, "JPEG", quality=92)
    return path


# ═══════════════════════════════════════════════════════════════════════════════
# شريحة الملخص النهائي
# ═══════════════════════════════════════════════════════════════════════════════

def _draw_summary(all_keywords: list, summary_text: str) -> str:
    fd, path = tempfile.mkstemp(suffix=".jpg")
    os.close(fd)
    img = PILImage.new("RGB", (TARGET_W, TARGET_H), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    
    draw.rectangle([(0, 0), (TARGET_W, 8)], fill=COLORS[0])
    draw.rectangle([(0, TARGET_H-8), (TARGET_W, TARGET_H)], fill=COLORS[0])
    
    font = _get_font(30)
    title = _prepare_arabic("📋 ملخص المحاضرة")
    try:
        bbox = font.getbbox(title)
        w = bbox[2] - bbox[0]
    except:
        w = len(title) * 18
    x = (TARGET_W - w) // 2
    draw.text((x, 35), title, fill=(44, 62, 80), font=font)
    
    # الكلمات المفتاحية
    y = 90
    font2 = _get_font(18)
    for i, kw in enumerate(all_keywords[:12]):
        color = COLORS[i % len(COLORS)]
        kw_text = _prepare_arabic(kw)
        try:
            bbox = font2.getbbox(kw_text)
            kw_w = bbox[2] - bbox[0]
        except:
            kw_w = len(kw_text) * 10
        
        col = i % 3
        row = i // 3
        cx = 50 + col * 250
        cy = y + row * 45
        
        draw.rounded_rectangle(
            [(cx-10, cy-5), (cx+kw_w+10, cy+28)],
            radius=8, fill=(*color, 20), outline=color, width=2
        )
        draw.text((cx, cy), kw_text, fill=color, font=font2)
    
    # رسالة شكر
    font3 = _get_font(26)
    thanks = _prepare_arabic("🙏 شكراً لحسن استماعكم")
    try:
        bbox = font3.getbbox(thanks)
        w3 = bbox[2] - bbox[0]
    except:
        w3 = len(thanks) * 15
    x3 = (TARGET_W - w3) // 2
    draw.text((x3, TARGET_H - 60), thanks, fill=COLORS[0], font=font3)
    
    img.save(path, "JPEG", quality=90)
    return path


# ═══════════════════════════════════════════════════════════════════════════════
# FFmpeg
# ═══════════════════════════════════════════════════════════════════════════════

def _ffmpeg_segment(img: str, dur: float, audio: str, start: float, out: str):
    dur_str = f"{dur:.3f}"
    aud = ["-ss", f"{start:.3f}", "-t", dur_str, "-i", audio] if audio else ["-f", "lavfi", "-i", "anullsrc"]
    cmd = [
        "ffmpeg", "-y", "-loop", "1", "-t", dur_str, "-i", img, *aud,
        "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p", "-r", "15",
        "-vf", "scale=854:480:force_original_aspect_ratio=decrease,pad=854:480:(ow-iw)/2:(oh-ih)/2",
        "-map", "0:v", "-map", "1:a", "-c:a", "aac", "-b:a", "96k", "-t", dur_str, out
    ]
    subprocess.run(cmd, capture_output=True)


def _ffmpeg_concat(segs: list, out: str):
    fd, lst = tempfile.mkstemp(suffix=".txt")
    os.close(fd)
    with open(lst, "w") as f:
        for p in segs:
            f.write(f"file '{p}'\n")
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", out], capture_output=True)
    os.remove(lst)


# ═══════════════════════════════════════════════════════════════════════════════
# بناء الفيديو
# ═══════════════════════════════════════════════════════════════════════════════

def _build_segments(sections: list, audio_results: list, lecture_data: dict):
    segs, tmps, total = [], [], 0
    title = lecture_data.get("title", "المحاضرة")
    all_kw = lecture_data.get("all_keywords", [])
    summary_text = lecture_data.get("summary", "")
    
    # 1. مقدمة
    p = _draw_welcome()
    tmps.append(p)
    segs.append({"img": p, "audio": None, "audio_start": 0, "dur": 3.5})
    total += 3.5
    
    # 2. عنوان
    p = _draw_title(title)
    tmps.append(p)
    segs.append({"img": p, "audio": None, "audio_start": 0, "dur": 4})
    total += 4
    
    # 3. خريطة
    section_titles = [s.get("title", "") for s in sections]
    p = _draw_map(section_titles)
    tmps.append(p)
    segs.append({"img": p, "audio": None, "audio_start": 0, "dur": 5})
    total += 5
    
    # 4. الأقسام
    for sec_idx, (sec, aud) in enumerate(zip(sections, audio_results)):
        # عنوان القسم
        p = _draw_section_title(sec.get("title", f"قسم {sec_idx+1}"), sec_idx)
        tmps.append(p)
        segs.append({"img": p, "audio": None, "audio_start": 0, "dur": 3})
        total += 3
        
        keywords = sec.get("keywords", ["مفهوم"])
        section_image = sec.get("_image_bytes")  # صورة واحدة للقسم كامل
        
        audio_bytes = aud.get("audio")
        total_dur = max(aud.get("duration", 30), 5)
        kw_dur = total_dur / len(keywords)
        
        apath = None
        if audio_bytes:
            afd, apath = tempfile.mkstemp(suffix=".mp3")
            os.close(afd)
            with open(apath, "wb") as f:
                f.write(audio_bytes)
            tmps.append(apath)
        
        # شرائح المحتوى - نفس الصورة، الكلمات تظهر تدريجياً
        for kw_idx in range(len(keywords)):
            p = _draw_content_slide(
                image_bytes=section_image,
                keywords=keywords,
                section_title=sec.get("title", ""),
                section_idx=sec_idx,
                current_kw=kw_idx,
                total_kw=len(keywords),
            )
            tmps.append(p)
            segs.append({
                "img": p,
                "audio": apath,
                "audio_start": kw_idx * kw_dur,
                "dur": kw_dur,
            })
            total += kw_dur
    
    # 5. ملخص (مع صوت)
    # نستخدم الصوت الأخير أو ننشئ صوت للملخص
    summary_audio = None
    if audio_results:
        summary_audio = audio_results[-1].get("audio")
    
    p = _draw_summary(all_kw, summary_text)
    tmps.append(p)
    segs.append({"img": p, "audio": summary_audio, "audio_start": 0, "dur": 8})
    total += 8
    
    return segs, tmps, total


def _encode(segs: list, out: str):
    paths = []
    for i, s in enumerate(segs):
        fd, p = tempfile.mkstemp(suffix=".mp4")
        os.close(fd)
        paths.append(p)
        _ffmpeg_segment(s["img"], s["dur"], s["audio"], s["audio_start"], p)
    _ffmpeg_concat(paths, out)
    for p in paths:
        os.remove(p)


async def create_video_from_sections(
    sections: list,
    audio_results: list,
    lecture_data: dict,
    output_path: str,
    dialect: str = "msa",
    progress_cb=None,
) -> float:
    loop = asyncio.get_event_loop()
    
    # التأكد من وجود صورة لكل قسم
    for sec in sections:
        if "_image_bytes" not in sec:
            sec["_image_bytes"] = None
        if "keywords" not in sec or not sec["keywords"]:
            sec["keywords"] = ["مفهوم"]
    
    segs, tmps, total = await loop.run_in_executor(
        None, _build_segments, sections, audio_results, lecture_data
    )
    
    await loop.run_in_executor(None, _encode, segs, output_path)
    
    for p in tmps:
        try:
            os.remove(p)
        except:
            pass
    
    return total
