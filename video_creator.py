# -*- coding: utf-8 -*-
"""
Video Creator Module - Osmosis Style
====================================
الميزات الكاملة:
- مقدمة احترافية مع شعار البوت وترحيب
- شريحة عنوان المحاضرة
- شريحة خريطة الأقسام (جميع الأقسام مع كلماتها المفتاحية)
- شريحة عنوان لكل قسم (مع رقم القسم)
- سبورة بيضاء تتراكم عليها الصور والكلمات المفتاحية مع تقدم الشرح
- شريحة ملخص نهائي (جميع الكلمات المفتاحية + رسالة شكر)
- دعم كامل للغة العربية (arabic_reshaper + bidi)
- حقوق البوت في جميع الشرائح
- فيديو متوافق مع تيليجرام (H.264 + AAC)
"""

import asyncio
import io
import os
import subprocess
import tempfile
from PIL import Image as PILImage, ImageDraw, ImageFont

# ═══════════════════════════════════════════════════════════════════════════════
# الإعدادات العامة
# ═══════════════════════════════════════════════════════════════════════════════

TARGET_W, TARGET_H = 854, 480
WATERMARK = "@zakros_probot"

# ألوان Osmosis المميزة
COLORS = [
    (231, 76, 126),   # وردي
    (52, 152, 219),   # أزرق
    (46, 204, 113),   # أخضر
    (155, 89, 182),   # بنفسجي
    (230, 126, 34),   # برتقالي
]

def estimate_encoding_seconds(total_video_seconds: float) -> float:
    """تقدير وقت التشفير"""
    return max(20.0, total_video_seconds * 0.6)


# ═══════════════════════════════════════════════════════════════════════════════
# دوال الخطوط والنصوص العربية
# ═══════════════════════════════════════════════════════════════════════════════

def _get_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """تحميل خط مناسب مع دعم العربية"""
    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ]
    for path in font_paths:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except:
                pass
    return ImageFont.load_default()


def _prepare_arabic(text: str) -> str:
    """تجهيز النص العربي للعرض بشكل صحيح 100%"""
    if not text:
        return ""
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
        if any('\u0600' <= c <= '\u06FF' for c in text):
            reshaped = arabic_reshaper.reshape(text)
            return get_display(reshaped)
    except Exception as e:
        print(f"[WARN] Arabic reshape failed: {e}")
    return text


def _get_text_width(text: str, font: ImageFont.FreeTypeFont) -> int:
    """حساب عرض النص"""
    try:
        bbox = font.getbbox(text)
        return bbox[2] - bbox[0]
    except:
        return len(text) * (font.size // 2)


def _wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list:
    """تقسيم النص الطويل إلى عدة أسطر"""
    words = text.split()
    lines = []
    current_line = []
    
    for word in words:
        current_line.append(word)
        line_text = ' '.join(current_line)
        if _get_text_width(line_text, font) > max_width:
            current_line.pop()
            if current_line:
                lines.append(' '.join(current_line))
            current_line = [word]
    
    if current_line:
        lines.append(' '.join(current_line))
    
    return lines if lines else [text]


def _draw_text_with_shadow(draw, x: int, y: int, text: str, font, color, shadow=True):
    """رسم نص مع ظل"""
    text = _prepare_arabic(text)
    if shadow:
        draw.text((x + 2, y + 2), text, fill=(200, 200, 200), font=font)
    draw.text((x, y), text, fill=color, font=font)


def _draw_centered_text(draw, y: int, text: str, font, color):
    """رسم نص في منتصف العرض"""
    text = _prepare_arabic(text)
    w = _get_text_width(text, font)
    x = (TARGET_W - w) // 2
    draw.text((x + 2, y + 2), text, fill=(200, 200, 200), font=font)
    draw.text((x, y), text, fill=color, font=font)
    return y + font.size + 10


# ═══════════════════════════════════════════════════════════════════════════════
# 1. شريحة المقدمة (Welcome Slide)
# ═══════════════════════════════════════════════════════════════════════════════

def _draw_welcome_slide() -> str:
    """شريحة المقدمة مع شعار البوت وترحيب"""
    fd, path = tempfile.mkstemp(prefix="welcome_", suffix=".jpg")
    os.close(fd)

    img = PILImage.new("RGB", (TARGET_W, TARGET_H), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    # شرائط علوية وسفلية
    draw.rectangle([(0, 0), (TARGET_W, 8)], fill=COLORS[0])
    draw.rectangle([(0, TARGET_H - 8), (TARGET_W, TARGET_H)], fill=COLORS[0])

    # إطار كبير للشعار
    frame_x, frame_y = 150, 100
    frame_w, frame_h = 550, 200
    draw.rounded_rectangle(
        [(frame_x, frame_y), (frame_x + frame_w, frame_y + frame_h)],
        radius=25, outline=COLORS[0], width=8
    )
    draw.rounded_rectangle(
        [(frame_x + 10, frame_y + 10), (frame_x + frame_w - 10, frame_y + frame_h - 10)],
        radius=15, outline=COLORS[0], width=2
    )

    # الشعار بخط كبير
    font_logo = _get_font(60, bold=True)
    logo_w = _get_text_width(WATERMARK, font_logo)
    logo_x = (TARGET_W - logo_w) // 2
    logo_y = frame_y + 60
    draw.text((logo_x + 4, logo_y + 4), WATERMARK, fill=(200, 200, 200), font=font_logo)
    draw.text((logo_x, logo_y), WATERMARK, fill=COLORS[0], font=font_logo)

    # رسالة الترحيب
    font_welcome = _get_font(36, bold=True)
    welcome_text = _prepare_arabic("أهلاً ومرحباً بكم")
    welcome_w = _get_text_width(welcome_text, font_welcome)
    welcome_x = (TARGET_W - welcome_w) // 2
    welcome_y = frame_y + frame_h + 40
    draw.text((welcome_x + 3, welcome_y + 3), welcome_text, fill=(200, 200, 200), font=font_welcome)
    draw.text((welcome_x, welcome_y), welcome_text, fill=(44, 62, 80), font=font_welcome)

    # حقوق البوت
    font_wm = _get_font(14, bold=True)
    wm_w = _get_text_width(WATERMARK, font_wm)
    draw.text((TARGET_W - wm_w - 25, TARGET_H - 35), WATERMARK, fill=COLORS[0], font=font_wm)

    img.save(path, "JPEG", quality=90)
    return path


# ═══════════════════════════════════════════════════════════════════════════════
# 2. شريحة عنوان المحاضرة (Title Slide)
# ═══════════════════════════════════════════════════════════════════════════════

def _draw_title_slide(title: str) -> str:
    """شريحة عرض عنوان المحاضرة"""
    fd, path = tempfile.mkstemp(prefix="title_", suffix=".jpg")
    os.close(fd)

    img = PILImage.new("RGB", (TARGET_W, TARGET_H), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    draw.rectangle([(0, 0), (TARGET_W, 6)], fill=COLORS[1])

    font_title = _get_font(38, bold=True)
    title_text = _prepare_arabic(title)
    
    lines = _wrap_text(title_text, font_title, TARGET_W - 80)
    y = TARGET_H // 2 - (len(lines) * 45) // 2
    
    for line in lines:
        w = _get_text_width(line, font_title)
        x = (TARGET_W - w) // 2
        draw.text((x + 3, y + 3), line, fill=(200, 200, 200), font=font_title)
        draw.text((x, y), line, fill=(44, 62, 80), font=font_title)
        y += 45

    # حقوق البوت
    font_wm = _get_font(14, bold=True)
    wm_w = _get_text_width(WATERMARK, font_wm)
    draw.text((TARGET_W - wm_w - 25, TARGET_H - 35), WATERMARK, fill=COLORS[1], font=font_wm)

    img.save(path, "JPEG", quality=90)
    return path


# ═══════════════════════════════════════════════════════════════════════════════
# 3. شريحة خريطة الأقسام (Sections Map)
# ═══════════════════════════════════════════════════════════════════════════════

def _draw_sections_map(sections: list) -> str:
    """شريحة عرض خريطة الأقسام مع الكلمات المفتاحية"""
    fd, path = tempfile.mkstemp(prefix="map_", suffix=".jpg")
    os.close(fd)

    img = PILImage.new("RGB", (TARGET_W, TARGET_H), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    draw.rectangle([(0, 0), (TARGET_W, 6)], fill=COLORS[2])

    # عنوان الخريطة
    font_title = _get_font(30, bold=True)
    map_title = _prepare_arabic("📋 خريطة المحاضرة")
    w = _get_text_width(map_title, font_title)
    x = (TARGET_W - w) // 2
    draw.text((x, 30), map_title, fill=COLORS[2], font=font_title)

    y = 90
    font_sec = _get_font(20, bold=True)
    font_kw = _get_font(14)
    font_num = _get_font(15, bold=True)

    for i, section in enumerate(sections):
        color = COLORS[i % len(COLORS)]
        
        # رقم القسم
        draw.ellipse([(30, y), (52, y + 22)], fill=color)
        num_str = str(i + 1)
        draw.text((41, y + 3), num_str, fill=(255, 255, 255), font=font_num)
        
        # عنوان القسم
        sec_title = section.get("title", f"القسم {i+1}")[:35]
        sec_text = _prepare_arabic(sec_title)
        draw.text((70, y), sec_text, fill=(44, 62, 80), font=font_sec)
        
        # الكلمات المفتاحية
        keywords = section.get("keywords", [])[:3]
        if keywords:
            kw_text = " • ".join(keywords)
            kw_disp = _prepare_arabic(kw_text)
            draw.text((85, y + 26), kw_disp, fill=color, font=font_kw)
        
        y += 60

    # حقوق البوت
    font_wm = _get_font(13, bold=True)
    wm_w = _get_text_width(WATERMARK, font_wm)
    draw.text((TARGET_W - wm_w - 25, TARGET_H - 30), WATERMARK, fill=COLORS[2], font=font_wm)

    img.save(path, "JPEG", quality=90)
    return path


# ═══════════════════════════════════════════════════════════════════════════════
# 4. شريحة عنوان القسم (Section Title Card)
# ═══════════════════════════════════════════════════════════════════════════════

def _draw_section_title_card(section: dict, idx: int, total: int) -> str:
    """شريحة عنوان القسم مع رقم"""
    fd, path = tempfile.mkstemp(prefix=f"sec_title_{idx}_", suffix=".jpg")
    os.close(fd)

    color = COLORS[idx % len(COLORS)]
    img = PILImage.new("RGB", (TARGET_W, TARGET_H), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    draw.rectangle([(0, 0), (TARGET_W, 6)], fill=color)

    # دائرة الرقم
    cx, cy, cr = TARGET_W // 2, TARGET_H // 2 - 50, 45
    draw.ellipse([cx - cr, cy - cr, cx + cr, cy + cr], fill=color)
    
    num_str = str(idx + 1)
    font_num = _get_font(40, bold=True)
    nw = _get_text_width(num_str, font_num)
    draw.text((cx - nw // 2, cy - 22), num_str, fill=(255, 255, 255), font=font_num)

    # عنوان القسم
    raw_title = section.get("title", f"القسم {idx + 1}")
    title_text = _prepare_arabic(raw_title)
    font_title = _get_font(32, bold=True)
    tw = _get_text_width(title_text, font_title)
    x = (TARGET_W - tw) // 2
    draw.text((x, cy + cr + 35), title_text, fill=(44, 62, 80), font=font_title)

    # حقوق البوت
    font_wm = _get_font(13, bold=True)
    wm_w = _get_text_width(WATERMARK, font_wm)
    draw.text((TARGET_W - wm_w - 25, TARGET_H - 30), WATERMARK, fill=color, font=font_wm)

    img.save(path, "JPEG", quality=90)
    return path


# ═══════════════════════════════════════════════════════════════════════════════
# 5. شريحة المحتوى - السبورة المتراكمة (Accumulating Whiteboard)
# ═══════════════════════════════════════════════════════════════════════════════

def _draw_content_slide(
    image_bytes: bytes,
    keywords: list,
    section_title: str,
    section_idx: int,
    current_kw: int,
    total_kw: int,
) -> str:
    """
    سبورة بيضاء تتراكم عليها الصور والكلمات المفتاحية مع تقدم الشرح
    """
    fd, path = tempfile.mkstemp(prefix="content_", suffix=".jpg")
    os.close(fd)

    color = COLORS[section_idx % len(COLORS)]
    img = PILImage.new("RGB", (TARGET_W, TARGET_H), (248, 248, 250))
    draw = ImageDraw.Draw(img)

    # شريط علوي
    draw.rectangle([(0, 0), (TARGET_W, 6)], fill=color)

    # عنوان القسم في الأعلى
    font_header = _get_font(18, bold=True)
    header_text = _prepare_arabic(section_title[:40])
    hw = _get_text_width(header_text, font_header)
    hx = (TARGET_W - hw) // 2
    draw.text((hx, 15), header_text, fill=(44, 62, 80), font=font_header)
    draw.rectangle([(hx, 38), (hx + hw, 40)], fill=color)

    # الصورة الرئيسية للقسم
    img_y = 55
    if image_bytes:
        try:
            pil_img = PILImage.open(io.BytesIO(image_bytes)).convert("RGB")
            iw, ih = pil_img.size
            max_w, max_h = 500, 240
            scale = min(max_w / iw, max_h / ih)
            nw, nh = int(iw * scale), int(ih * scale)
            pil_img = pil_img.resize((nw, nh), PILImage.LANCZOS)
            
            px = (TARGET_W - nw) // 2
            py = img_y + (max_h - nh) // 2
            
            draw.rounded_rectangle(
                [(px - 5, py - 5), (px + nw + 5, py + nh + 5)],
                radius=10, outline=color, width=4
            )
            img.paste(pil_img, (px, py))
        except Exception as e:
            print(f"[WARN] Failed to paste image: {e}")

    # الكلمات المفتاحية (تظهر تدريجياً)
    kw_y = 320
    font_kw = _get_font(20, bold=True)
    
    visible_keywords = keywords[:current_kw + 1]
    
    for i, kw in enumerate(visible_keywords):
        kw_color = COLORS[i % len(COLORS)]
        kw_text = _prepare_arabic(kw)
        kw_w = _get_text_width(kw_text, font_kw)
        
        # توزيع الكلمات في سطرين
        col = i % 2
        row = i // 2
        kx = 100 + col * 350
        ky = kw_y + row * 40
        
        # خلفية للكلمة
        draw.rounded_rectangle(
            [(kx - 10, ky - 5), (kx + kw_w + 10, ky + 30)],
            radius=8, fill=(*kw_color, 20), outline=kw_color, width=2
        )
        draw.text((kx, ky), kw_text, fill=kw_color, font=font_kw)

    # مؤشر التقدم (نقاط)
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
    wm_w = _get_text_width(WATERMARK, font_wm)
    draw.text((TARGET_W - wm_w - 20, TARGET_H - 25), WATERMARK, fill=color, font=font_wm)

    img.save(path, "JPEG", quality=92)
    return path


# ═══════════════════════════════════════════════════════════════════════════════
# 6. شريحة الملخص النهائي (Final Summary)
# ═══════════════════════════════════════════════════════════════════════════════

def _draw_final_summary(all_keywords: list) -> str:
    """شريحة الملخص النهائي مع جميع الكلمات المفتاحية"""
    fd, path = tempfile.mkstemp(prefix="summary_", suffix=".jpg")
    os.close(fd)

    img = PILImage.new("RGB", (TARGET_W, TARGET_H), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    draw.rectangle([(0, 0), (TARGET_W, 8)], fill=COLORS[0])
    draw.rectangle([(0, TARGET_H - 8), (TARGET_W, TARGET_H)], fill=COLORS[0])

    # عنوان الملخص
    font_title = _get_font(30, bold=True)
    title_text = _prepare_arabic("📋 ملخص المحاضرة")
    tw = _get_text_width(title_text, font_title)
    tx = (TARGET_W - tw) // 2
    draw.text((tx, 35), title_text, fill=(44, 62, 80), font=font_title)

    # عرض الكلمات المفتاحية في شبكة
    y = 90
    font_kw = _get_font(18, bold=True)
    
    for i, kw in enumerate(all_keywords[:12]):
        color = COLORS[i % len(COLORS)]
        kw_text = _prepare_arabic(kw)
        kw_w = _get_text_width(kw_text, font_kw)
        
        col = i % 3
        row = i // 3
        cx = 50 + col * 250
        cy = y + row * 45
        
        draw.rounded_rectangle(
            [(cx - 10, cy - 5), (cx + kw_w + 10, cy + 28)],
            radius=8, fill=(*color, 20), outline=color, width=2
        )
        draw.text((cx, cy), kw_text, fill=color, font=font_kw)

    # رسالة شكر
    font_thanks = _get_font(26, bold=True)
    thanks_text = _prepare_arabic("🙏 شكراً لحسن استماعكم")
    tw3 = _get_text_width(thanks_text, font_thanks)
    tx3 = (TARGET_W - tw3) // 2
    draw.text((tx3 + 3, TARGET_H - 65), thanks_text, fill=(200, 200, 200), font=font_thanks)
    draw.text((tx3, TARGET_H - 68), thanks_text, fill=COLORS[0], font=font_thanks)

    # حقوق البوت
    font_wm = _get_font(14, bold=True)
    wm_w = _get_text_width(WATERMARK, font_wm)
    draw.text((TARGET_W - wm_w - 25, TARGET_H - 35), WATERMARK, fill=COLORS[0], font=font_wm)

    img.save(path, "JPEG", quality=90)
    return path


# ═══════════════════════════════════════════════════════════════════════════════
# FFmpeg - تشفير الفيديو
# ═══════════════════════════════════════════════════════════════════════════════

def _ffmpeg_segment(img_path: str, duration: float, audio_path: str, audio_start: float, out_path: str):
    """تشفير مقطع واحد - متوافق مع تيليجرام"""
    dur_str = f"{duration:.3f}"
    
    if audio_path and os.path.exists(audio_path):
        cmd = [
            "ffmpeg", "-y",
            "-loop", "1", "-i", img_path,
            "-ss", f"{audio_start:.3f}", "-t", dur_str, "-i", audio_path,
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-pix_fmt", "yuv420p",
            "-vf", f"scale={TARGET_W}:{TARGET_H}:force_original_aspect_ratio=decrease,pad={TARGET_W}:{TARGET_H}:(ow-iw)/2:(oh-ih)/2",
            "-r", "15",
            "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "2",
            "-shortest", "-t", dur_str, out_path
        ]
    else:
        cmd = [
            "ffmpeg", "-y",
            "-loop", "1", "-i", img_path,
            "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-pix_fmt", "yuv420p",
            "-vf", f"scale={TARGET_W}:{TARGET_H}:force_original_aspect_ratio=decrease,pad={TARGET_W}:{TARGET_H}:(ow-iw)/2:(oh-ih)/2",
            "-r", "15",
            "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "2",
            "-shortest", "-t", dur_str, out_path
        ]
    
    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg failed: {result.stderr.decode()[:500]}")


def _ffmpeg_concat(segment_paths: list[str], output_path: str):
    """دمج جميع المقاطع في فيديو واحد"""
    fd, list_path = tempfile.mkstemp(suffix=".txt")
    os.close(fd)
    with open(list_path, "w") as f:
        for p in segment_paths:
            f.write(f"file '{p}'\n")
    
    cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list_path, "-c", "copy", output_path]
    result = subprocess.run(cmd, capture_output=True)
    os.remove(list_path)
    
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg concat failed: {result.stderr.decode()[:500]}")


# ═══════════════════════════════════════════════════════════════════════════════
# بناء الفيديو
# ═══════════════════════════════════════════════════════════════════════════════

def _build_segment_list(
    sections: list,
    audio_results: list,
    lecture_title: str,
    all_keywords: list,
) -> tuple[list[dict], list[str], float]:
    """بناء قائمة بجميع مقاطع الفيديو"""
    segments: list[dict] = []
    tmp_files: list[str] = []
    total_secs = 0.0
    n_sections = len(sections)

    # 1. شريحة المقدمة
    welcome_path = _draw_welcome_slide()
    tmp_files.append(welcome_path)
    segments.append({"img": welcome_path, "audio": None, "audio_start": 0.0, "dur": 3.5})
    total_secs += 3.5

    # 2. شريحة عنوان المحاضرة
    title_path = _draw_title_slide(lecture_title)
    tmp_files.append(title_path)
    segments.append({"img": title_path, "audio": None, "audio_start": 0.0, "dur": 4.0})
    total_secs += 4.0

    # 3. شريحة خريطة الأقسام
    map_path = _draw_sections_map(sections)
    tmp_files.append(map_path)
    segments.append({"img": map_path, "audio": None, "audio_start": 0.0, "dur": 5.0})
    total_secs += 5.0

    # 4. الأقسام الرئيسية
    for sec_idx, (section, audio_info) in enumerate(zip(sections, audio_results)):
        # شريحة عنوان القسم
        sec_title_path = _draw_section_title_card(section, sec_idx, n_sections)
        tmp_files.append(sec_title_path)
        segments.append({"img": sec_title_path, "audio": None, "audio_start": 0.0, "dur": 3.0})
        total_secs += 3.0

        keywords = section.get("keywords", ["مفهوم"])
        section_image = section.get("_image_bytes")
        audio_bytes = audio_info.get("audio")
        total_dur = max(float(audio_info.get("duration", 45)), 5.0)
        
        n_kw = len(keywords)
        kw_dur = total_dur / n_kw if n_kw > 0 else total_dur

        # حفظ ملف الصوت
        apath = None
        if audio_bytes:
            afd, apath = tempfile.mkstemp(prefix=f"aud_{sec_idx}_", suffix=".mp3")
            os.close(afd)
            with open(apath, "wb") as f:
                f.write(audio_bytes)
            tmp_files.append(apath)

        sec_title = section.get("title", "")
        
        # شرائح المحتوى المتراكم
        for kw_idx in range(n_kw):
            content_path = _draw_content_slide(
                image_bytes=section_image,
                keywords=keywords,
                section_title=sec_title,
                section_idx=sec_idx,
                current_kw=kw_idx,
                total_kw=n_kw,
            )
            tmp_files.append(content_path)
            
            segments.append({
                "img": content_path,
                "audio": apath,
                "audio_start": kw_idx * kw_dur,
                "dur": kw_dur,
            })
            total_secs += kw_dur

    # 5. شريحة الخاتمة (الملخص)
    final_path = _draw_final_summary(all_keywords)
    tmp_files.append(final_path)
    segments.append({"img": final_path, "audio": None, "audio_start": 0.0, "dur": 6.0})
    total_secs += 6.0

    return segments, tmp_files, total_secs


def _encode_all_sync(segments: list[dict], output_path: str):
    """تشفير جميع المقاطع ودمجها"""
    seg_paths: list[str] = []
    try:
        for i, seg in enumerate(segments):
            fd, seg_out = tempfile.mkstemp(prefix=f"seg_{i}_", suffix=".mp4")
            os.close(fd)
            seg_paths.append(seg_out)
            _ffmpeg_segment(seg["img"], seg["dur"], seg["audio"], seg["audio_start"], seg_out)
            print(f"  ✅ Segment {i+1}/{len(segments)} encoded ({seg['dur']:.1f}s)")
        
        print(f"  🔗 Concatenating {len(seg_paths)} segments...")
        _ffmpeg_concat(seg_paths, output_path)
        print(f"  ✅ Video saved to {output_path}")
    finally:
        for p in seg_paths:
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
    """إنشاء فيديو كامل من الأقسام والصوت"""
    loop = asyncio.get_event_loop()
    
    lecture_title = lecture_data.get("title", "المحاضرة التعليمية")
    all_keywords = lecture_data.get("all_keywords", [])

    # التأكد من وجود الكلمات المفتاحية والصور
    for section in sections:
        if "keywords" not in section or not section["keywords"]:
            section["keywords"] = ["مفهوم", "تعريف", "شرح", "تحليل"]
        if "_image_bytes" not in section:
            section["_image_bytes"] = None

    print(f"[Video] Building {len(sections)} sections...")
    segments, tmp_files, total_video_secs = await loop.run_in_executor(
        None, _build_segment_list, sections, audio_results, lecture_title, all_keywords
    )

    if not segments:
        raise RuntimeError("No valid segments generated")

    print(f"[Video] Encoding {len(segments)} segments ({total_video_secs:.1f}s total)...")
    estimated_enc = estimate_encoding_seconds(total_video_secs)
    encode_task = loop.run_in_executor(None, _encode_all_sync, segments, output_path)

    start = loop.time()
    try:
        while not encode_task.done():
            await asyncio.sleep(3)
            elapsed = loop.time() - start
            if progress_cb:
                try:
                    await progress_cb(elapsed, estimated_enc)
                except:
                    pass
        await encode_task
    finally:
        # تنظيف الملفات المؤقتة
        for path in tmp_files:
            try:
                if os.path.exists(path):
                    os.remove(path)
            except:
                pass

    print(f"[Video] Done! Duration: {total_video_secs:.1f}s")
    return total_video_secs
