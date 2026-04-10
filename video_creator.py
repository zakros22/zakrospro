# -*- coding: utf-8 -*-
"""
Video Creator Module - Osmosis Style with Full Arabic Support
=============================================================
الحل الجذري للغة العربية:
- استخدام arabic_reshaper لإعادة تشكيل الحروف
- استخدام python-bidi لعكس اتجاه النص (RTL)
- استخدام خط DejaVuSans المضمون على جميع أنظمة Linux
- دالة _arabic() تطبق كل الخطوات بشكل صحيح
"""

import asyncio
import io
import os
import subprocess
import tempfile
from PIL import Image as PILImage, ImageDraw, ImageFont

# ═══════════════════════════════════════════════════════════════════════════════
# الإعدادات
# ═══════════════════════════════════════════════════════════════════════════════

TARGET_W, TARGET_H = 854, 480
WATERMARK = "@zakros_probot"

COLORS = [
    (231, 76, 126),   # وردي
    (52, 152, 219),   # أزرق
    (46, 204, 113),   # أخضر
    (155, 89, 182),   # بنفسجي
    (230, 126, 34),   # برتقالي
]

def estimate_encoding_seconds(t: float) -> float:
    return max(20.0, t * 0.6)


# ═══════════════════════════════════════════════════════════════════════════════
# الحل الجذري للغة العربية
# ═══════════════════════════════════════════════════════════════════════════════

# متغير عام لتخزين الخط بعد تحميله مرة واحدة
_FONT_CACHE = {}

def _get_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """تحميل خط يدعم العربية. يبحث في المسارات القياسية لـ Linux/Heroku."""
    cache_key = f"{size}_{bold}"
    if cache_key in _FONT_CACHE:
        return _FONT_CACHE[cache_key]
    
    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ]
    
    for path in font_paths:
        if os.path.exists(path):
            try:
                font = ImageFont.truetype(path, size)
                _FONT_CACHE[cache_key] = font
                return font
            except:
                pass
    
    # خط افتراضي إذا لم يتم العثور على أي خط
    font = ImageFont.load_default()
    _FONT_CACHE[cache_key] = font
    return font


def _arabic(text: str) -> str:
    """
    الحل الجذري للنصوص العربية.
    يتم استدعاء هذه الدالة على أي نص عربي قبل رسمه.
    """
    if not text:
        return ""
    
    # إذا كان النص لا يحتوي على أحرف عربية، نرجعه كما هو
    if not any('\u0600' <= c <= '\u06FF' for c in text):
        return text
    
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
        
        # الخطوة 1: إعادة تشكيل الحروف العربية
        reshaped = arabic_reshaper.reshape(text)
        
        # الخطوة 2: عكس اتجاه النص (RTL)
        bidi_text = get_display(reshaped)
        
        return bidi_text
    except Exception as e:
        print(f"[WARN] Arabic reshape failed: {e}")
        return text


def _text_width(text: str, font: ImageFont.FreeTypeFont) -> int:
    """حساب عرض النص بعد معالجته للعربية"""
    text = _arabic(text)
    try:
        bbox = font.getbbox(text)
        return bbox[2] - bbox[0]
    except:
        return len(text) * (font.size // 2)


def _draw_text(draw, x: int, y: int, text: str, font, color, shadow: bool = True):
    """
    رسم نص مع دعم كامل للعربية.
    هذه هي الدالة الوحيدة التي يجب استخدامها لرسم أي نص.
    """
    text = _arabic(text)
    if shadow:
        draw.text((x + 2, y + 2), text, fill=(200, 200, 200), font=font)
    draw.text((x, y), text, fill=color, font=font)


def _draw_centered_text(draw, y: int, text: str, font, color):
    """رسم نص في منتصف العرض مع دعم العربية"""
    text = _arabic(text)
    w = _text_width(text, font)
    x = (TARGET_W - w) // 2
    draw.text((x + 2, y + 2), text, fill=(200, 200, 200), font=font)
    draw.text((x, y), text, fill=color, font=font)
    return y + font.size + 10


def _wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list:
    """تقسيم النص العربي إلى أسطر"""
    text = _arabic(text)
    words = text.split()
    lines = []
    current = []
    
    for w in words:
        current.append(w)
        line = ' '.join(current)
        if _text_width(line, font) > max_width:
            current.pop()
            if current:
                lines.append(' '.join(current))
            current = [w]
    
    if current:
        lines.append(' '.join(current))
    
    return lines if lines else [text]


# ═══════════════════════════════════════════════════════════════════════════════
# 1. شريحة المقدمة
# ═══════════════════════════════════════════════════════════════════════════════

def _draw_welcome() -> str:
    fd, path = tempfile.mkstemp(prefix="welcome_", suffix=".jpg")
    os.close(fd)

    img = PILImage.new("RGB", (TARGET_W, TARGET_H), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    # شرائط علوية وسفلية
    draw.rectangle([(0, 0), (TARGET_W, 8)], fill=COLORS[0])
    draw.rectangle([(0, TARGET_H - 8), (TARGET_W, TARGET_H)], fill=COLORS[0])

    # إطار الشعار
    frame_x, frame_y = 150, 100
    frame_w, frame_h = 550, 200
    draw.rounded_rectangle(
        [(frame_x, frame_y), (frame_x + frame_w, frame_y + frame_h)],
        radius=25, outline=COLORS[0], width=8
    )

    # الشعار
    font_logo = _get_font(60, bold=True)
    logo_w = _text_width(WATERMARK, font_logo)
    logo_x = (TARGET_W - logo_w) // 2
    logo_y = frame_y + 60
    _draw_text(draw, logo_x, logo_y, WATERMARK, font_logo, COLORS[0])

    # رسالة الترحيب
    font_welcome = _get_font(36, bold=True)
    welcome_text = "أهلاً ومرحباً بكم"
    welcome_w = _text_width(welcome_text, font_welcome)
    welcome_x = (TARGET_W - welcome_w) // 2
    welcome_y = frame_y + frame_h + 40
    _draw_text(draw, welcome_x, welcome_y, welcome_text, font_welcome, (44, 62, 80))

    # حقوق البوت
    font_wm = _get_font(14, bold=True)
    wm_w = _text_width(WATERMARK, font_wm)
    _draw_text(draw, TARGET_W - wm_w - 25, TARGET_H - 35, WATERMARK, font_wm, COLORS[0])

    img.save(path, "JPEG", quality=90)
    return path


# ═══════════════════════════════════════════════════════════════════════════════
# 2. شريحة عنوان المحاضرة
# ═══════════════════════════════════════════════════════════════════════════════

def _draw_title(title: str) -> str:
    fd, path = tempfile.mkstemp(prefix="title_", suffix=".jpg")
    os.close(fd)

    img = PILImage.new("RGB", (TARGET_W, TARGET_H), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    draw.rectangle([(0, 0), (TARGET_W, 6)], fill=COLORS[1])

    font_title = _get_font(38, bold=True)
    lines = _wrap_text(title, font_title, TARGET_W - 80)
    
    y = TARGET_H // 2 - (len(lines) * 45) // 2
    for line in lines:
        w = _text_width(line, font_title)
        x = (TARGET_W - w) // 2
        _draw_text(draw, x, y, line, font_title, (44, 62, 80))
        y += 45

    # حقوق البوت
    font_wm = _get_font(14, bold=True)
    wm_w = _text_width(WATERMARK, font_wm)
    _draw_text(draw, TARGET_W - wm_w - 25, TARGET_H - 35, WATERMARK, font_wm, COLORS[1])

    img.save(path, "JPEG", quality=90)
    return path


# ═══════════════════════════════════════════════════════════════════════════════
# 3. شريحة خريطة الأقسام
# ═══════════════════════════════════════════════════════════════════════════════

def _draw_map(titles: list) -> str:
    fd, path = tempfile.mkstemp(prefix="map_", suffix=".jpg")
    os.close(fd)

    img = PILImage.new("RGB", (TARGET_W, TARGET_H), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    draw.rectangle([(0, 0), (TARGET_W, 6)], fill=COLORS[2])

    font_title = _get_font(30, bold=True)
    map_title = "📋 خريطة المحاضرة"
    w = _text_width(map_title, font_title)
    x = (TARGET_W - w) // 2
    _draw_text(draw, x, 30, map_title, font_title, COLORS[2])

    y = 90
    font_sec = _get_font(20, bold=True)
    font_num = _get_font(15, bold=True)

    for i, t in enumerate(titles):
        color = COLORS[i % len(COLORS)]
        draw.ellipse([(30, y), (52, y + 22)], fill=color)
        draw.text((41, y + 3), str(i + 1), fill=(255, 255, 255), font=font_num)
        _draw_text(draw, 70, y, t[:35], font_sec, (44, 62, 80))
        y += 55

    # حقوق البوت
    font_wm = _get_font(13, bold=True)
    wm_w = _text_width(WATERMARK, font_wm)
    _draw_text(draw, TARGET_W - wm_w - 25, TARGET_H - 30, WATERMARK, font_wm, COLORS[2])

    img.save(path, "JPEG", quality=90)
    return path


# ═══════════════════════════════════════════════════════════════════════════════
# 4. شريحة عنوان القسم
# ═══════════════════════════════════════════════════════════════════════════════

def _draw_section_title(title: str, idx: int) -> str:
    fd, path = tempfile.mkstemp(prefix="sec_title_", suffix=".jpg")
    os.close(fd)

    color = COLORS[idx % len(COLORS)]
    img = PILImage.new("RGB", (TARGET_W, TARGET_H), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    draw.rectangle([(0, 0), (TARGET_W, 6)], fill=color)

    # دائرة الرقم
    cx, cy, cr = TARGET_W // 2, TARGET_H // 2 - 40, 45
    draw.ellipse([cx - cr, cy - cr, cx + cr, cy + cr], fill=color)
    
    num_str = str(idx + 1)
    font_num = _get_font(40, bold=True)
    nw = _text_width(num_str, font_num)
    draw.text((cx - nw // 2, cy - 22), num_str, fill=(255, 255, 255), font=font_num)

    # عنوان القسم
    font_title = _get_font(32, bold=True)
    tw = _text_width(title, font_title)
    x = (TARGET_W - tw) // 2
    _draw_text(draw, x, cy + cr + 35, title, font_title, (44, 62, 80))

    # حقوق البوت
    font_wm = _get_font(13, bold=True)
    wm_w = _text_width(WATERMARK, font_wm)
    _draw_text(draw, TARGET_W - wm_w - 25, TARGET_H - 30, WATERMARK, font_wm, color)

    img.save(path, "JPEG", quality=90)
    return path


# ═══════════════════════════════════════════════════════════════════════════════
# 5. شريحة المحتوى - السبورة المتراكمة
# ═══════════════════════════════════════════════════════════════════════════════

def _draw_content(
    image_bytes: bytes,
    keywords: list,
    section_title: str,
    section_idx: int,
    current_kw: int,
    total_kw: int,
) -> str:
    fd, path = tempfile.mkstemp(prefix="content_", suffix=".jpg")
    os.close(fd)

    color = COLORS[section_idx % len(COLORS)]
    img = PILImage.new("RGB", (TARGET_W, TARGET_H), (248, 248, 250))
    draw = ImageDraw.Draw(img)

    # شريط علوي
    draw.rectangle([(0, 0), (TARGET_W, 6)], fill=color)

    # عنوان القسم
    font_header = _get_font(18, bold=True)
    hw = _text_width(section_title[:40], font_header)
    hx = (TARGET_W - hw) // 2
    _draw_text(draw, hx, 15, section_title[:40], font_header, (44, 62, 80))
    draw.rectangle([(hx, 38), (hx + hw, 40)], fill=color)

    # الصورة الرئيسية
    if image_bytes:
        try:
            pil = PILImage.open(io.BytesIO(image_bytes)).convert("RGB")
            iw, ih = pil.size
            s = min(500 / iw, 250 / ih)
            nw, nh = int(iw * s), int(ih * s)
            pil = pil.resize((nw, nh), PILImage.LANCZOS)
            
            px = (TARGET_W - nw) // 2
            py = 50 + (250 - nh) // 2
            
            draw.rounded_rectangle(
                [(px - 5, py - 5), (px + nw + 5, py + nh + 5)],
                radius=10, outline=color, width=4
            )
            img.paste(pil, (px, py))
        except:
            pass

    # الكلمات المفتاحية (تظهر تدريجياً)
    font_kw = _get_font(20, bold=True)
    visible = keywords[:current_kw + 1]
    
    for i, kw in enumerate(visible):
        kw_color = COLORS[i % len(COLORS)]
        kw_w = _text_width(kw, font_kw)
        
        col = i % 2
        row = i // 2
        kx = 100 + col * 350
        ky = 330 + row * 40
        
        draw.rounded_rectangle(
            [(kx - 10, ky - 5), (kx + kw_w + 10, ky + 30)],
            radius=8, fill=(*kw_color, 20), outline=kw_color, width=2
        )
        _draw_text(draw, kx, ky, kw, font_kw, kw_color)

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
        draw.ellipse([(dx - r, dot_y - r), (dx + r, dot_y + r)], fill=dot_color)

    # حقوق البوت
    font_wm = _get_font(12, bold=True)
    wm_w = _text_width(WATERMARK, font_wm)
    _draw_text(draw, TARGET_W - wm_w - 20, TARGET_H - 25, WATERMARK, font_wm, color)

    img.save(path, "JPEG", quality=92)
    return path


# ═══════════════════════════════════════════════════════════════════════════════
# 6. شريحة الملخص النهائي
# ═══════════════════════════════════════════════════════════════════════════════

def _draw_summary(keywords: list) -> str:
    fd, path = tempfile.mkstemp(prefix="summary_", suffix=".jpg")
    os.close(fd)

    img = PILImage.new("RGB", (TARGET_W, TARGET_H), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    draw.rectangle([(0, 0), (TARGET_W, 8)], fill=COLORS[0])
    draw.rectangle([(0, TARGET_H - 8), (TARGET_W, TARGET_H)], fill=COLORS[0])

    # عنوان الملخص
    font_title = _get_font(30, bold=True)
    title_text = "📋 ملخص المحاضرة"
    tw = _text_width(title_text, font_title)
    tx = (TARGET_W - tw) // 2
    _draw_text(draw, tx, 35, title_text, font_title, (44, 62, 80))

    # الكلمات المفتاحية
    y = 90
    font_kw = _get_font(18, bold=True)
    
    for i, kw in enumerate(keywords[:12]):
        color = COLORS[i % len(COLORS)]
        kw_w = _text_width(kw, font_kw)
        
        col = i % 3
        row = i // 3
        cx = 50 + col * 250
        cy = y + row * 45
        
        draw.rounded_rectangle(
            [(cx - 10, cy - 5), (cx + kw_w + 10, cy + 28)],
            radius=8, fill=(*color, 20), outline=color, width=2
        )
        _draw_text(draw, cx, cy, kw, font_kw, color)

    # رسالة شكر
    font_thanks = _get_font(26, bold=True)
    thanks_text = "🙏 شكراً لحسن استماعكم"
    tw3 = _text_width(thanks_text, font_thanks)
    tx3 = (TARGET_W - tw3) // 2
    _draw_text(draw, tx3, TARGET_H - 60, thanks_text, font_thanks, COLORS[0])

    # حقوق البوت
    font_wm = _get_font(14, bold=True)
    wm_w = _text_width(WATERMARK, font_wm)
    _draw_text(draw, TARGET_W - wm_w - 25, TARGET_H - 35, WATERMARK, font_wm, COLORS[0])

    img.save(path, "JPEG", quality=90)
    return path


# ═══════════════════════════════════════════════════════════════════════════════
# FFmpeg - تشفير الفيديو
# ═══════════════════════════════════════════════════════════════════════════════

def _ffmpeg_segment(img: str, dur: float, aud: str, start: float, out: str):
    dstr = f"{dur:.3f}"
    if aud and os.path.exists(aud):
        cmd = [
            "ffmpeg", "-y", "-loop", "1", "-i", img,
            "-ss", f"{start:.3f}", "-t", dstr, "-i", aud,
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-pix_fmt", "yuv420p",
            "-vf", f"scale={TARGET_W}:{TARGET_H}:force_original_aspect_ratio=decrease,pad={TARGET_W}:{TARGET_H}:(ow-iw)/2:(oh-ih)/2",
            "-r", "15", "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "2",
            "-shortest", "-t", dstr, out
        ]
    else:
        cmd = [
            "ffmpeg", "-y", "-loop", "1", "-i", img,
            "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-pix_fmt", "yuv420p",
            "-vf", f"scale={TARGET_W}:{TARGET_H}:force_original_aspect_ratio=decrease,pad={TARGET_W}:{TARGET_H}:(ow-iw)/2:(oh-ih)/2",
            "-r", "15", "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "2",
            "-shortest", "-t", dstr, out
        ]
    subprocess.run(cmd, capture_output=True)


def _ffmpeg_concat(segments: list, out: str):
    fd, lst = tempfile.mkstemp(suffix=".txt")
    os.close(fd)
    with open(lst, "w") as f:
        for s in segments:
            f.write(f"file '{s}'\n")
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", out], capture_output=True)
    os.remove(lst)


# ═══════════════════════════════════════════════════════════════════════════════
# بناء الفيديو
# ═══════════════════════════════════════════════════════════════════════════════

def _build(sections: list, audio_results: list, title: str, all_kw: list):
    segs, tmps, total = [], [], 0
    
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
    p = _draw_map([s.get("title", "") for s in sections])
    tmps.append(p)
    segs.append({"img": p, "audio": None, "audio_start": 0, "dur": 5})
    total += 5
    
    # 4. أقسام
    for i, (s, a) in enumerate(zip(sections, audio_results)):
        p = _draw_section_title(s.get("title", f"قسم {i+1}"), i)
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
            p = _draw_content(img, kw, s.get("title", ""), i, j, len(kw))
            tmps.append(p)
            segs.append({"img": p, "audio": ap, "audio_start": j * kd, "dur": kd})
            total += kd
    
    # 5. ملخص
    p = _draw_summary(all_kw)
    tmps.append(p)
    segs.append({"img": p, "audio": None, "audio_start": 0, "dur": 6})
    total += 6
    
    return segs, tmps, total


def _encode(segs: list, out: str):
    paths = []
    try:
        for i, s in enumerate(segs):
            fd, p = tempfile.mkstemp(prefix=f"seg_{i}_", suffix=".mp4")
            os.close(fd)
            paths.append(p)
            _ffmpeg_seg(s["img"], s["dur"], s["audio"], s["audio_start"], p)
        _ffmpeg_concat(paths, out)
    finally:
        for p in paths:
            try:
                os.remove(p)
            except:
                pass


# ═══════════════════════════════════════════════════════════════════════════════
# الدالة الرئيسية
# ═══════════════════════════════════════════════════════════════════════════════

async def create_video_from_sections(
    sections: list,
    audio_results: list,
    lecture_data: dict,
    output_path: str,
    dialect: str = "msa",
    progress_cb=None,
) -> float:
    loop = asyncio.get_event_loop()
    
    title = lecture_data.get("title", "المحاضرة التعليمية")
    all_kw = lecture_data.get("all_keywords", [])
    
    for s in sections:
        if "keywords" not in s or not s["keywords"]:
            s["keywords"] = ["مفهوم", "تعريف", "شرح", "تحليل"]
        if "_image_bytes" not in s:
            s["_image_bytes"] = None
    
    segs, tmps, total = await loop.run_in_executor(
        None, _build, sections, audio_results, title, all_kw
    )
    
    await loop.run_in_executor(None, _encode, segs, output_path)
    
    for p in tmps:
        try:
            os.remove(p)
        except:
            pass
    
    return total
