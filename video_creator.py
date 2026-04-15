import asyncio
import io
import os
import subprocess
import tempfile
import textwrap
from typing import Callable, Awaitable

from PIL import Image as PILImage, ImageDraw, ImageFont

# ══════════════════════════════════════════════════════════════════════════════
# 📐 الأبعاد والإعدادات
# ══════════════════════════════════════════════════════════════════════════════
TARGET_W, TARGET_H = 854, 480
WATERMARK = "@zakros_probot"

# الخطوط
FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_REG = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
_FONTS_DIR = os.path.join(os.path.dirname(__file__), "fonts")
FONT_AR_BOLD = os.path.join(_FONTS_DIR, "Amiri-Bold.ttf")
FONT_AR_REG = os.path.join(_FONTS_DIR, "Amiri-Regular.ttf")

# إعدادات FFmpeg
_ENC_FACTOR = 0.5
_MIN_ENC_SEC = 15.0

# مدد الشرائح
_INTRO_DUR = 6.0
_SECTION_TITLE_DUR = 2.5
_SUMMARY_DUR = 8.0

# ══════════════════════════════════════════════════════════════════════════════
# 🎨 الألوان حسب نوع المحاضرة
# ══════════════════════════════════════════════════════════════════════════════
THEME_COLORS = {
    "medicine":   {"primary": (199, 30, 30), "secondary": (20, 78, 140), "accent": (255, 200, 0)},
    "science":    {"primary": (11, 110, 79), "secondary": (28, 200, 135), "accent": (255, 220, 50)},
    "math":       {"primary": (58, 12, 163), "secondary": (100, 60, 220), "accent": (255, 180, 0)},
    "literature": {"primary": (100, 30, 120), "secondary": (180, 60, 200), "accent": (255, 200, 100)},
    "history":    {"primary": (150, 60, 10), "secondary": (220, 110, 40), "accent": (255, 230, 100)},
    "computer":   {"primary": (0, 80, 120), "secondary": (0, 160, 200), "accent": (255, 200, 50)},
    "business":   {"primary": (0, 80, 40), "secondary": (0, 160, 80), "accent": (255, 220, 0)},
    "other":      {"primary": (30, 30, 80), "secondary": (70, 60, 160), "accent": (255, 200, 50)},
}

# ألوان الكروت
CARD_BG = (255, 255, 255)
CARD_BORDER = (220, 220, 230)
CARD_SHADOW = (180, 180, 190)
KEYWORD_BG = (245, 245, 250)
KEYWORD_BORDER = (200, 200, 210)
TITLE_BAR_BG = (28, 44, 68)
TITLE_TEXT = (255, 255, 255)
BODY_TEXT = (40, 40, 50)
KEYWORD_TEXT = (60, 80, 120)


def estimate_encoding_seconds(total_video_seconds: float) -> float:
    """تقدير وقت التشفير"""
    return max(_MIN_ENC_SEC, total_video_seconds * _ENC_FACTOR)


def _get_font(size: int, bold: bool = False, arabic: bool = False) -> ImageFont.FreeTypeFont:
    """تحميل الخط المناسب"""
    if arabic:
        path = FONT_AR_BOLD if bold else FONT_AR_REG
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                pass
    path = FONT_BOLD if bold else FONT_REG
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()


def _prepare_text(text: str, is_arabic: bool) -> str:
    """تجهيز النص العربي"""
    if not is_arabic or not text:
        return text
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
        return get_display(arabic_reshaper.reshape(text))
    except Exception:
        return text


def _wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int, draw: ImageDraw.ImageDraw) -> list:
    """تقسيم النص إلى أسطر"""
    words = text.split()
    lines = []
    current_line = []
    
    for word in words:
        test_line = ' '.join(current_line + [word])
        try:
            bbox = draw.textbbox((0, 0), test_line, font=font)
            width = bbox[2] - bbox[0]
        except:
            width = len(test_line) * (font.size // 2)
        
        if width <= max_width:
            current_line.append(word)
        else:
            if current_line:
                lines.append(' '.join(current_line))
            current_line = [word]
    
    if current_line:
        lines.append(' '.join(current_line))
    
    return lines


# ══════════════════════════════════════════════════════════════════════════════
# 1️⃣ شريحة المقدمة — Intro Slide
# ══════════════════════════════════════════════════════════════════════════════

def _draw_intro_slide(lecture_data: dict, sections: list, is_arabic: bool) -> str:
    """شريحة المقدمة مع خريطة المحاضرة"""
    fd, path = tempfile.mkstemp(prefix="intro_", suffix=".jpg")
    os.close(fd)
    
    lecture_type = lecture_data.get("lecture_type", "other")
    theme = THEME_COLORS.get(lecture_type, THEME_COLORS["other"])
    
    # خلفية متدرجة
    img = PILImage.new("RGB", (TARGET_W, TARGET_H), theme["secondary"])
    draw = ImageDraw.Draw(img)
    
    for y in range(TARGET_H):
        t = y / TARGET_H
        r = int(theme["secondary"][0] * (1 - t) + theme["primary"][0] * t)
        g = int(theme["secondary"][1] * (1 - t) + theme["primary"][1] * t)
        b = int(theme["secondary"][2] * (1 - t) + theme["primary"][2] * t)
        draw.line([(0, y), (TARGET_W, y)], fill=(r, g, b))
    
    # شريط علوي
    draw.rectangle([(0, 0), (TARGET_W, 5)], fill=theme["accent"])
    
    # العنوان
    title_raw = lecture_data.get("title", "المحاضرة" if is_arabic else "Lecture")
    title_txt = _prepare_text(title_raw, is_arabic)
    title_font = _get_font(28, bold=True, arabic=is_arabic)
    
    try:
        bbox = draw.textbbox((0, 0), title_txt, font=title_font)
        tw = bbox[2] - bbox[0]
    except:
        tw = len(title_txt) * 15
    draw.text(((TARGET_W - tw) // 2, 20), title_txt, fill=theme["accent"], font=title_font)
    
    # "خريطة المحاضرة"
    map_txt = _prepare_text("خريطة المحاضرة" if is_arabic else "Lecture Map", is_arabic)
    map_font = _get_font(16, arabic=is_arabic)
    draw.text((20, 70), map_txt, fill=(255, 255, 255, 200), font=map_font)
    
    # خط فاصل
    draw.rectangle([(20, 95), (TARGET_W - 20, 97)], fill=theme["accent"])
    
    # قائمة الأقسام
    y_pos = 110
    sections_to_show = sections[:8]
    
    for idx, section in enumerate(sections_to_show):
        # رقم القسم
        num_str = f"{idx + 1}."
        num_font = _get_font(18, bold=True)
        draw.text((30, y_pos), num_str, fill=theme["accent"], font=num_font)
        
        # عنوان القسم
        sec_title = section.get("title", f"Section {idx + 1}")
        sec_txt = _prepare_text(sec_title[:40], is_arabic)
        sec_font = _get_font(16, arabic=is_arabic)
        draw.text((70, y_pos + 2), sec_txt, fill=(255, 255, 255), font=sec_font)
        
        # كلمات مفتاحية
        keywords = section.get("keywords", [])[:3]
        if keywords:
            kw_txt = " • ".join([_prepare_text(k, is_arabic) for k in keywords])
            kw_font = _get_font(12, arabic=is_arabic)
            draw.text((90, y_pos + 25), kw_txt, fill=(200, 200, 220), font=kw_font)
        
        y_pos += 45
    
    # العلامة المائية
    wm_font = _get_font(12)
    draw.text((TARGET_W - 150, TARGET_H - 25), WATERMARK, fill=(150, 160, 180), font=wm_font)
    
    img.save(path, "JPEG", quality=90)
    return path


# ══════════════════════════════════════════════════════════════════════════════
# 2️⃣ كارت القسم — Section Card (التصميم الجديد مثل الصور)
# ══════════════════════════════════════════════════════════════════════════════

def _draw_section_card(
    section: dict,
    idx: int,
    total_sections: int,
    is_arabic: bool,
    image_bytes: bytes | None,
    keywords: list,
    lecture_type: str = "other"
) -> str:
    """
    كارت تعليمي كامل مثل الصور:
    - شريط علوي مع عنوان القسم ورقمه (مثلاً: 25 من 51)
    - صورة في المنتصف
    - كلمات مفتاحية أسفل الصورة في مربعات
    """
    fd, path = tempfile.mkstemp(prefix=f"card_{idx}_", suffix=".jpg")
    os.close(fd)
    
    theme = THEME_COLORS.get(lecture_type, THEME_COLORS["other"])
    
    # خلفية بيضاء مع ظل
    img = PILImage.new("RGB", (TARGET_W, TARGET_H), (245, 245, 250))
    draw = ImageDraw.Draw(img)
    
    # ══════════════════════════════════════════════════════════════════════════
    # الشريط العلوي — عنوان القسم ورقمه
    # ══════════════════════════════════════════════════════════════════════════
    HEADER_H = 50
    draw.rectangle([(0, 0), (TARGET_W, HEADER_H)], fill=TITLE_BAR_BG)
    draw.rectangle([(0, HEADER_H - 3), (TARGET_W, HEADER_H)], fill=theme["primary"])
    
    # عنوان القسم
    sec_title_raw = section.get("title", f"Section {idx + 1}")
    sec_title = _prepare_text(sec_title_raw, is_arabic)
    title_font = _get_font(20, bold=True, arabic=is_arabic)
    
    try:
        bbox = draw.textbbox((0, 0), sec_title, font=title_font)
        tw = bbox[2] - bbox[0]
    except:
        tw = len(sec_title) * 11
    
    # العنوان في الوسط
    title_x = (TARGET_W - tw) // 2
    draw.text((title_x, 12), sec_title, fill=TITLE_TEXT, font=title_font)
    
    # رقم القسم (مثلاً: 25 من 51) — في الزاوية اليمنى
    page_num = f"{idx + 1} من {total_sections}" if is_arabic else f"{idx + 1} of {total_sections}"
    num_font = _get_font(14, arabic=is_arabic)
    try:
        bbox = draw.textbbox((0, 0), page_num, font=num_font)
        nw = bbox[2] - bbox[0]
    except:
        nw = len(page_num) * 8
    
    if is_arabic:
        num_x = 15
    else:
        num_x = TARGET_W - nw - 15
    draw.text((num_x, 16), page_num, fill=(200, 200, 220), font=num_font)
    
    # ══════════════════════════════════════════════════════════════════════════
    # منطقة الصورة
    # ══════════════════════════════════════════════════════════════════════════
    IMG_TOP = HEADER_H + 10
    IMG_BOTTOM = TARGET_H - 90
    IMG_HEIGHT = IMG_BOTTOM - IMG_TOP
    
    # إطار الصورة
    draw.rectangle(
        [(20, IMG_TOP - 2), (TARGET_W - 20, IMG_BOTTOM + 2)],
        outline=CARD_BORDER, width=2
    )
    
    if image_bytes:
        try:
            pil_img = PILImage.open(io.BytesIO(image_bytes)).convert("RGB")
            iw, ih = pil_img.size
            
            # حساب الأبعاد المناسبة
            max_w = TARGET_W - 60
            max_h = IMG_HEIGHT - 10
            scale = min(max_w / iw, max_h / ih)
            nw, nh = int(iw * scale), int(ih * scale)
            
            pil_img = pil_img.resize((nw, nh), PILImage.LANCZOS)
            
            # توسيط الصورة
            px = (TARGET_W - nw) // 2
            py = IMG_TOP + (IMG_HEIGHT - nh) // 2
            
            img.paste(pil_img, (px, py))
        except Exception as e:
            print(f"Image paste error: {e}")
            # رسم مستطيل بديل
            draw.rectangle(
                [(40, IMG_TOP + 20), (TARGET_W - 40, IMG_BOTTOM - 20)],
                fill=(230, 230, 240), outline=(200, 200, 210)
            )
            placeholder = "📷 صورة تعليمية" if is_arabic else "📷 Educational Image"
            ph_font = _get_font(18, arabic=is_arabic)
            try:
                bbox = draw.textbbox((0, 0), placeholder, font=ph_font)
                pw = bbox[2] - bbox[0]
            except:
                pw = len(placeholder) * 10
            draw.text(
                ((TARGET_W - pw) // 2, IMG_TOP + IMG_HEIGHT // 2 - 10),
                placeholder, fill=(150, 150, 160), font=ph_font
            )
    
    # ══════════════════════════════════════════════════════════════════════════
    # الكلمات المفتاحية — في الأسفل
    # ══════════════════════════════════════════════════════════════════════════
    KW_TOP = IMG_BOTTOM + 8
    KW_HEIGHT = 70
    
    # عنوان "مصطلحات رئيسية"
    kw_header = "مصطلحات رئيسية:" if is_arabic else "Key Terms:"
    kw_header_font = _get_font(14, bold=True, arabic=is_arabic)
    draw.text((25, KW_TOP), kw_header, fill=theme["primary"], font=kw_header_font)
    
    # مربعات الكلمات المفتاحية
    kw_font = _get_font(15, bold=True, arabic=is_arabic)
    kw_bg_font = _get_font(13, arabic=is_arabic)
    
    kw_x = 25
    kw_y = KW_TOP + 25
    
    for kw in keywords[:4]:
        kw_disp = _prepare_text(kw, is_arabic)
        
        try:
            bbox = draw.textbbox((0, 0), kw_disp, font=kw_font)
            kw_w = bbox[2] - bbox[0] + 20
        except:
            kw_w = len(kw_disp) * 9 + 20
        
        if kw_x + kw_w > TARGET_W - 25:
            break
        
        # خلفية الكلمة
        draw.rounded_rectangle(
            [(kw_x, kw_y), (kw_x + kw_w, kw_y + 32)],
            radius=6, fill=KEYWORD_BG, outline=KEYWORD_BORDER, width=1
        )
        
        # النص
        draw.text((kw_x + 10, kw_y + 6), kw_disp, fill=KEYWORD_TEXT, font=kw_font)
        
        kw_x += kw_w + 10
    
    # العلامة المائية
    wm_font = _get_font(11)
    draw.text((TARGET_W - 140, TARGET_H - 18), WATERMARK, fill=(170, 170, 190), font=wm_font)
    
    img.save(path, "JPEG", quality=92)
    return path


# ══════════════════════════════════════════════════════════════════════════════
# 3️⃣ شريحة عنوان القسم — Section Title Card
# ══════════════════════════════════════════════════════════════════════════════

def _draw_section_title_card(section: dict, idx: int, total: int, is_arabic: bool, lecture_type: str) -> str:
    """شريحة عنوان القسم"""
    fd, path = tempfile.mkstemp(prefix=f"sec_title_{idx}_", suffix=".jpg")
    os.close(fd)
    
    theme = THEME_COLORS.get(lecture_type, THEME_COLORS["other"])
    
    # خلفية متدرجة
    img = PILImage.new("RGB", (TARGET_W, TARGET_H), theme["secondary"])
    draw = ImageDraw.Draw(img)
    
    for y in range(TARGET_H):
        t = y / TARGET_H
        r = int(theme["secondary"][0] * (1 - t) + theme["primary"][0] * t)
        g = int(theme["secondary"][1] * (1 - t) + theme["primary"][1] * t)
        b = int(theme["secondary"][2] * (1 - t) + theme["primary"][2] * t)
        draw.line([(0, y), (TARGET_W, y)], fill=(r, g, b))
    
    # شريط علوي وسفلي
    draw.rectangle([(0, 0), (TARGET_W, 6)], fill=theme["accent"])
    draw.rectangle([(0, TARGET_H - 6), (TARGET_W, TARGET_H)], fill=theme["accent"])
    
    # رقم القسم كبير
    cx, cy = TARGET_W // 2, TARGET_H // 2 - 40
    draw.ellipse([cx - 50, cy - 50, cx + 50, cy + 50], fill=theme["accent"])
    
    num_str = str(idx + 1)
    num_font = _get_font(48, bold=True)
    try:
        bbox = draw.textbbox((0, 0), num_str, font=num_font)
        nw, nh = bbox[2] - bbox[0], bbox[3] - bbox[1]
    except:
        nw, nh = 30, 50
    draw.text((cx - nw // 2, cy - nh // 2), num_str, fill=theme["primary"], font=num_font)
    
    # "القسم"
    section_label = f"القسم {idx + 1} من {total}" if is_arabic else f"Section {idx + 1} of {total}"
    label_font = _get_font(16, arabic=is_arabic)
    try:
        bbox = draw.textbbox((0, 0), section_label, font=label_font)
        lw = bbox[2] - bbox[0]
    except:
        lw = len(section_label) * 9
    draw.text(((TARGET_W - lw) // 2, cy + 60), section_label, fill=(200, 220, 255), font=label_font)
    
    # عنوان القسم
    title_raw = section.get("title", f"Section {idx + 1}")
    title_txt = _prepare_text(title_raw, is_arabic)
    title_font = _get_font(24, bold=True, arabic=is_arabic)
    
    # تقسيم النص الطويل
    lines = _wrap_text(title_txt, title_font, TARGET_W - 80, draw)
    y_pos = cy + 90
    for line in lines:
        try:
            bbox = draw.textbbox((0, 0), line, font=title_font)
            lw = bbox[2] - bbox[0]
        except:
            lw = len(line) * 13
        draw.text(((TARGET_W - lw) // 2, y_pos), line, fill=theme["accent"], font=title_font)
        y_pos += 35
    
    # العلامة المائية
    wm_font = _get_font(12)
    draw.text((TARGET_W - 150, TARGET_H - 25), WATERMARK, fill=(150, 160, 190), font=wm_font)
    
    img.save(path, "JPEG", quality=90)
    return path


# ══════════════════════════════════════════════════════════════════════════════
# 4️⃣ شريحة الملخص — Summary Slide
# ══════════════════════════════════════════════════════════════════════════════

def _draw_summary_slide(sections: list, lecture_data: dict, is_arabic: bool) -> str:
    """شريحة الملخص النهائي"""
    fd, path = tempfile.mkstemp(prefix="summary_", suffix=".jpg")
    os.close(fd)
    
    lecture_type = lecture_data.get("lecture_type", "other")
    theme = THEME_COLORS.get(lecture_type, THEME_COLORS["other"])
    
    # خلفية
    img = PILImage.new("RGB", (TARGET_W, TARGET_H), (245, 245, 250))
    draw = ImageDraw.Draw(img)
    
    # شريط علوي
    draw.rectangle([(0, 0), (TARGET_W, 60)], fill=TITLE_BAR_BG)
    draw.rectangle([(0, 57), (TARGET_W, 60)], fill=theme["primary"])
    
    # عنوان الملخص
    summary_title = "📋 ملخص المحاضرة" if is_arabic else "📋 Lecture Summary"
    title_font = _get_font(24, bold=True, arabic=is_arabic)
    try:
        bbox = draw.textbbox((0, 0), summary_title, font=title_font)
        tw = bbox[2] - bbox[0]
    except:
        tw = len(summary_title) * 13
    draw.text(((TARGET_W - tw) // 2, 15), summary_title, fill=TITLE_TEXT, font=title_font)
    
    # النقاط الرئيسية
    key_points = lecture_data.get("key_points", [])
    y_pos = 80
    
    point_font = _get_font(16, arabic=is_arabic)
    bullet_font = _get_font(20, bold=True)
    
    for point in key_points[:6]:
        # نجمة/نقطة
        draw.text((30, y_pos), "•", fill=theme["primary"], font=bullet_font)
        
        # النص
        point_txt = _prepare_text(point, is_arabic)
        lines = _wrap_text(point_txt, point_font, TARGET_W - 80, draw)
        for line in lines:
            draw.text((60, y_pos), line, fill=BODY_TEXT, font=point_font)
            y_pos += 28
        y_pos += 10
    
    # الملخص النصي
    summary = lecture_data.get("summary", "")
    if summary:
        y_pos += 10
        draw.rectangle([(30, y_pos), (TARGET_W - 30, y_pos + 2)], fill=theme["accent"])
        y_pos += 15
        
        summary_txt = _prepare_text(summary[:200], is_arabic)
        summary_font = _get_font(15, arabic=is_arabic)
        lines = _wrap_text(summary_txt, summary_font, TARGET_W - 60, draw)
        for line in lines[:4]:
            draw.text((30, y_pos), line, fill=BODY_TEXT, font=summary_font)
            y_pos += 26
    
    # العلامة المائية
    wm_font = _get_font(12)
    draw.text((TARGET_W - 150, TARGET_H - 25), WATERMARK, fill=(170, 170, 190), font=wm_font)
    
    img.save(path, "JPEG", quality=90)
    return path


# ══════════════════════════════════════════════════════════════════════════════
# 🎬 FFmpeg — تشفير الفيديو
# ══════════════════════════════════════════════════════════════════════════════

def _ffmpeg_segment(
    img_path: str, duration: float, audio_path: str | None,
    audio_start: float, out_path: str, gentle_zoom: bool = False
) -> None:
    """تشفير مقطع فيديو واحد"""
    dur_str = f"{duration:.3f}"
    fps = 15
    
    if audio_path and os.path.exists(audio_path):
        audio_args = ["-ss", f"{audio_start:.3f}", "-t", dur_str, "-i", audio_path]
        audio_map = ["-map", "1:a"]
    else:
        audio_args = ["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100"]
        audio_map = ["-map", "1:a"]
    
    if gentle_zoom:
        n_frames = max(int(duration * fps), 2)
        vf = f"scale=900:506,zoompan=z='min(zoom+0.00015,1.03)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={n_frames}:s={TARGET_W}x{TARGET_H}:fps={fps}"
    else:
        vf = f"scale={TARGET_W}:{TARGET_H}:force_original_aspect_ratio=decrease,pad={TARGET_W}:{TARGET_H}:(ow-iw)/2:(oh-ih)/2"
    
    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-t", dur_str, "-i", img_path,
        *audio_args,
        "-vf", vf,
        *audio_map,
        "-map", "0:v",
        "-c:v", "libx264", "-preset", "fast",
        "-pix_fmt", "yuv420p", "-r", str(fps),
        "-c:a", "aac", "-b:a", "96k", "-ar", "44100", "-ac", "2",
        "-t", dur_str, out_path,
    ]
    
    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg failed: {result.stderr[-500:]}")


def _ffmpeg_concat(segment_paths: list[str], output_path: str) -> None:
    """دمج المقاطع"""
    fd, list_path = tempfile.mkstemp(suffix=".txt")
    try:
        os.close(fd)
        with open(list_path, "w") as f:
            for p in segment_paths:
                f.write(f"file '{p}'\n")
        
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0", "-i", list_path,
            "-c", "copy", output_path,
        ]
        result = subprocess.run(cmd, capture_output=True)
        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg concat failed: {result.stderr[-400:]}")
    finally:
        try:
            os.remove(list_path)
        except:
            pass


# ══════════════════════════════════════════════════════════════════════════════
# 🏗️ بناء قائمة المقاطع
# ══════════════════════════════════════════════════════════════════════════════

def _build_segment_list(
    sections: list,
    audio_results: list,
    lecture_data: dict,
    is_arabic: bool,
) -> tuple[list[dict], list[str], float]:
    """بناء قائمة المقاطع للفيديو"""
    segments = []
    tmp_files = []
    total_secs = 0.0
    n_sections = len(sections)
    lecture_type = lecture_data.get("lecture_type", "other")
    
    # 1. المقدمة
    intro_path = _draw_intro_slide(lecture_data, sections, is_arabic)
    tmp_files.append(intro_path)
    segments.append({"img": intro_path, "audio": None, "audio_start": 0.0, "dur": _INTRO_DUR, "gentle_zoom": False})
    total_secs += _INTRO_DUR
    
    # 2. الأقسام
    for sec_idx, (section, audio_info) in enumerate(zip(sections, audio_results)):
        # شريحة عنوان القسم
        title_path = _draw_section_title_card(section, sec_idx, n_sections, is_arabic, lecture_type)
        tmp_files.append(title_path)
        segments.append({"img": title_path, "audio": None, "audio_start": 0.0, "dur": _SECTION_TITLE_DUR, "gentle_zoom": False})
        total_secs += _SECTION_TITLE_DUR
        
        # كارت القسم الرئيسي
        keywords = section.get("keywords", [])[:4]
        image_bytes = section.get("_image_bytes")
        audio_bytes = audio_info.get("audio")
        total_dur = max(float(audio_info.get("duration", section.get("duration_estimate", 30))), 5.0)
        
        apath = None
        if audio_bytes:
            afd, apath = tempfile.mkstemp(prefix=f"aud_{sec_idx}_", suffix=".mp3")
            os.close(afd)
            with open(apath, "wb") as f:
                f.write(audio_bytes)
            tmp_files.append(apath)
        
        # إنشاء الكارت
        card_path = _draw_section_card(
            section, sec_idx, n_sections, is_arabic,
            image_bytes, keywords, lecture_type
        )
        tmp_files.append(card_path)
        
        segments.append({
            "img": card_path,
            "audio": apath,
            "audio_start": 0.0,
            "dur": total_dur,
            "gentle_zoom": True
        })
        total_secs += total_dur
    
    # 3. الملخص
    summary_path = _draw_summary_slide(sections, lecture_data, is_arabic)
    tmp_files.append(summary_path)
    segments.append({"img": summary_path, "audio": None, "audio_start": 0.0, "dur": _SUMMARY_DUR, "gentle_zoom": False})
    total_secs += _SUMMARY_DUR
    
    return segments, tmp_files, total_secs


def _encode_all_sync(segments: list[dict], output_path: str) -> None:
    """تشفير جميع المقاطع ودمجها"""
    seg_paths = []
    try:
        for i, seg in enumerate(segments):
            fd, seg_out = tempfile.mkstemp(prefix=f"seg_{i}_", suffix=".mp4")
            os.close(fd)
            seg_paths.append(seg_out)
            _ffmpeg_segment(
                seg["img"], seg["dur"], seg["audio"], seg["audio_start"], seg_out,
                gentle_zoom=seg.get("gentle_zoom", False)
            )
            print(f"  ✅ Segment {i+1}/{len(segments)} encoded ({seg['dur']:.1f}s)")
        
        _ffmpeg_concat(seg_paths, output_path)
        print(f"  ✅ Concatenated {len(seg_paths)} segments → {output_path}")
    finally:
        for p in seg_paths:
            try:
                os.remove(p)
            except:
                pass


# ══════════════════════════════════════════════════════════════════════════════
# 🎬 دالة إنشاء الفيديو الرئيسية
# ══════════════════════════════════════════════════════════════════════════════

async def create_video_from_sections(
    sections: list,
    audio_results: list,
    lecture_data: dict,
    output_path: str,
    dialect: str = "msa",
    progress_cb: Callable[[float, float], Awaitable[None]] | None = None,
) -> float:
    """
    إنشاء فيديو المحاضرة الكامل
    """
    is_arabic = dialect not in ("english", "british")
    loop = asyncio.get_event_loop()
    
    segments, tmp_files, total_video_secs = await loop.run_in_executor(
        None, _build_segment_list, sections, audio_results, lecture_data, is_arabic
    )
    
    if not segments:
        raise RuntimeError("No valid segments generated")
    
    estimated_enc = estimate_encoding_seconds(total_video_secs)
    
    encode_task = loop.run_in_executor(None, _encode_all_sync, segments, output_path)
    
    start = loop.time()
    try:
        while not encode_task.done():
            await asyncio.sleep(5)
            if encode_task.done():
                break
            elapsed = loop.time() - start
            if progress_cb:
                try:
                    await progress_cb(elapsed, estimated_enc)
                except:
                    pass
        await encode_task
    finally:
        for path in tmp_files:
            try:
                if os.path.exists(path):
                    os.remove(path)
            except:
                pass
    
    return total_video_secs


# دوال متوافقة مع القديم
_draw_slide_bg = _draw_section_card
_draw_slide_overlay = lambda *a, **k: None
_draw_slide = _draw_section_card
