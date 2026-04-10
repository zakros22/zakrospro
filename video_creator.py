import asyncio
import io
import os
import subprocess
import tempfile
from PIL import Image as PILImage, ImageDraw, ImageFont

TARGET_W, TARGET_H = 854, 480
WATERMARK = "@zakros_probot"
_FONTS_DIR = os.path.join(os.path.dirname(__file__), "fonts")
FONT_AR_BOLD = os.path.join(_FONTS_DIR, "Amiri-Bold.ttf")
FONT_AR_REG = os.path.join(_FONTS_DIR, "Amiri-Regular.ttf")

_ENC_FACTOR = 0.6
_MIN_ENC_SEC = 20.0

# توقيتات محسنة
_INTRO_DURATION = 8.0          # مدة المقدمة
_SECTION_TITLE_DUR = 4.0       # مدة عنوان القسم
_TRANSITION_DUR = 1.5          # مدة فاصل الانتقال
_SUMMARY_DURATION = 10.0       # مدة الملخص النهائي

ACCENT_COLORS = [
    (100, 180, 255), (100, 220, 160), (255, 180, 80),
    (220, 120, 255), (255, 120, 120), (80, 220, 220),
    (255, 200, 100), (160, 255, 160), (255, 140, 200),
]


def estimate_encoding_seconds(total_video_seconds: float) -> float:
    return max(_MIN_ENC_SEC, total_video_seconds * _ENC_FACTOR)


def _get_font(size: int, bold: bool = False, arabic: bool = False) -> ImageFont.FreeTypeFont:
    if arabic:
        path = FONT_AR_BOLD if bold else FONT_AR_REG
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                pass
    try:
        return ImageFont.load_default()
    except Exception:
        return ImageFont.load_default()


def _prepare_text(text: str, is_arabic: bool) -> str:
    if not text or not is_arabic:
        return text or ""
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
        return get_display(arabic_reshaper.reshape(text))
    except Exception:
        return text


def _wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list:
    """تقسيم النص الطويل إلى أسطر"""
    words = text.split()
    lines = []
    current_line = []
    
    for word in words:
        current_line.append(word)
        line_text = ' '.join(current_line)
        try:
            bbox = font.getbbox(line_text)
            line_width = bbox[2] - bbox[0]
        except Exception:
            line_width = len(line_text) * (font.size // 2)
        
        if line_width > max_width:
            if len(current_line) > 1:
                current_line.pop()
                lines.append(' '.join(current_line))
                current_line = [word]
            else:
                lines.append(word)
                current_line = []
    
    if current_line:
        lines.append(' '.join(current_line))
    
    return lines if lines else [text]


def _gradient_bg(color_top=(10, 20, 50), color_bot=(5, 40, 70)) -> PILImage.Image:
    bg = PILImage.new("RGB", (TARGET_W, TARGET_H), color_top)
    draw = ImageDraw.Draw(bg)
    for y in range(TARGET_H):
        t = y / TARGET_H
        r = int(color_top[0] * (1 - t) + color_bot[0] * t)
        g = int(color_top[1] * (1 - t) + color_bot[1] * t)
        b = int(color_top[2] * (1 - t) + color_bot[2] * t)
        draw.line([(0, y), (TARGET_W, y)], fill=(r, g, b))
    return bg


# ─────────────────────────────────────────────────────────────────────────────
# 1. شريحة المقدمة - Introduction Slide
# ─────────────────────────────────────────────────────────────────────────────

def _draw_intro_slide(lecture_data: dict, sections: list, is_arabic: bool) -> str:
    img_fd, img_path = tempfile.mkstemp(prefix="intro_", suffix=".jpg")
    os.close(img_fd)

    bg = _gradient_bg((15, 25, 60), (5, 15, 40))
    draw = ImageDraw.Draw(bg)

    # شريط علوي
    draw.rectangle([(0, 0), (TARGET_W, 8)], fill=(255, 200, 50))
    draw.rectangle([(0, TARGET_H - 8), (TARGET_W, TARGET_H)], fill=(255, 200, 50))

    # عنوان المحاضرة
    raw_title = lecture_data.get("title", "المحاضرة" if is_arabic else "Lecture")
    title_txt = _prepare_text(raw_title, is_arabic)
    title_font = _get_font(32, bold=True, arabic=is_arabic)
    
    lines = _wrap_text(title_txt, title_font, TARGET_W - 80)
    y_start = TARGET_H // 2 - (len(lines) * 35) // 2
    
    for i, line in enumerate(lines):
        try:
            bbox = draw.textbbox((0, 0), line, font=title_font)
            tw = bbox[2] - bbox[0]
        except Exception:
            tw = len(line) * 18
        x = (TARGET_W - tw) // 2
        y = y_start + i * 45
        # ظل
        draw.text((x + 3, y + 3), line, fill=(0, 0, 0), font=title_font)
        draw.text((x, y), line, fill=(255, 220, 80), font=title_font)

    # عدد الأقسام
    n_sec = len(sections)
    info_txt = f"📚 {n_sec} أقسام تعليمية" if is_arabic else f"📚 {n_sec} Sections"
    info_txt = _prepare_text(info_txt, is_arabic)
    info_font = _get_font(18, arabic=is_arabic)
    try:
        bbox = draw.textbbox((0, 0), info_txt, font=info_font)
        iw = bbox[2] - bbox[0]
    except Exception:
        iw = len(info_txt) * 10
    ix = (TARGET_W - iw) // 2
    draw.text((ix, y_start + len(lines) * 45 + 30), info_txt, fill=(180, 200, 230), font=info_font)

    # علامة مائية
    wm_font = _get_font(12)
    try:
        bbox = draw.textbbox((0, 0), WATERMARK, font=wm_font)
        ww = bbox[2] - bbox[0]
    except Exception:
        ww = len(WATERMARK) * 7
    draw.text(((TARGET_W - ww) // 2, TARGET_H - 30), WATERMARK, fill=(100, 120, 150), font=wm_font)

    bg.save(img_path, "JPEG", quality=90)
    return img_path


# ─────────────────────────────────────────────────────────────────────────────
# 2. شريحة عنوان القسم - Section Title Card
# ─────────────────────────────────────────────────────────────────────────────

def _draw_section_title_card(section: dict, idx: int, total: int, is_arabic: bool) -> str:
    img_fd, img_path = tempfile.mkstemp(prefix=f"sec_title_{idx}_", suffix=".jpg")
    os.close(img_fd)

    accent = ACCENT_COLORS[idx % len(ACCENT_COLORS)]
    dark_accent = tuple(max(0, c - 60) for c in accent)
    bg = _gradient_bg((8, 15, 40), dark_accent)
    draw = ImageDraw.Draw(bg)

    # شرائط جانبية
    draw.rectangle([(0, 0), (8, TARGET_H)], fill=accent)
    draw.rectangle([(TARGET_W - 8, 0), (TARGET_W, TARGET_H)], fill=accent)

    # رقم القسم
    cx, cy, cr = TARGET_W // 2, TARGET_H // 2 - 60, 50
    draw.ellipse([cx - cr, cy - cr, cx + cr, cy + cr], fill=accent)
    num_str = str(idx + 1)
    num_font = _get_font(48, bold=True)
    try:
        bbox = draw.textbbox((0, 0), num_str, font=num_font)
        nw, nh = bbox[2] - bbox[0], bbox[3] - bbox[1]
    except Exception:
        nw, nh = 25, 48
    draw.text((cx - nw // 2, cy - nh // 2), num_str, fill=(10, 15, 35), font=num_font)

    # "القسم"
    label_raw = f"القسم {idx + 1} من {total}" if is_arabic else f"Section {idx + 1} of {total}"
    label_txt = _prepare_text(label_raw, is_arabic)
    label_font = _get_font(16, arabic=is_arabic)
    try:
        bbox = draw.textbbox((0, 0), label_txt, font=label_font)
        lw = bbox[2] - bbox[0]
    except Exception:
        lw = len(label_txt) * 9
    lx = (TARGET_W - lw) // 2
    draw.text((lx, cy + cr + 15), label_txt, fill=(200, 220, 255), font=label_font)

    # عنوان القسم
    raw_title = section.get("title", f"Section {idx + 1}")
    title_txt = _prepare_text(raw_title, is_arabic)
    title_font = _get_font(28, bold=True, arabic=is_arabic)
    
    lines = _wrap_text(title_txt, title_font, TARGET_W - 100)
    y_start = cy + cr + 50
    
    for i, line in enumerate(lines):
        try:
            bbox = draw.textbbox((0, 0), line, font=title_font)
            lw = bbox[2] - bbox[0]
        except Exception:
            lw = len(line) * 16
        lx = (TARGET_W - lw) // 2
        draw.text((lx + 2, y_start + i * 40 + 2), line, fill=(0, 0, 0), font=title_font)
        draw.text((lx, y_start + i * 40), line, fill=accent, font=title_font)

    # علامة مائية
    wm_font = _get_font(12)
    try:
        bbox = draw.textbbox((0, 0), WATERMARK, font=wm_font)
        ww = bbox[2] - bbox[0]
    except Exception:
        ww = len(WATERMARK) * 7
    draw.text(((TARGET_W - ww) // 2, TARGET_H - 30), WATERMARK, fill=(120, 140, 170), font=wm_font)

    bg.save(img_path, "JPEG", quality=90)
    return img_path


# ─────────────────────────────────────────────────────────────────────────────
# 3. شريحة المحتوى مع صورة ونص - Content Slide with Image and Text
# ─────────────────────────────────────────────────────────────────────────────

def _draw_content_slide(
    image_bytes: bytes | None,
    keyword: str,
    narration: str,
    is_arabic: bool,
    section_title: str = "",
    section_idx: int = 0,
    total_sections: int = 1,
    kw_idx: int = 0,
    total_kw: int = 4,
) -> str:
    fd, path = tempfile.mkstemp(prefix="content_", suffix=".jpg")
    os.close(fd)

    accent = ACCENT_COLORS[section_idx % len(ACCENT_COLORS)]
    
    # خلفية داكنة أنيقة
    bg = _gradient_bg((18, 25, 45), (8, 15, 35))
    draw = ImageDraw.Draw(bg)

    # شريط علوي
    draw.rectangle([(0, 0), (TARGET_W, 5)], fill=accent)

    # عنوان القسم في الأعلى
    header_txt = _prepare_text(section_title[:40], is_arabic)
    header_font = _get_font(16, bold=True, arabic=is_arabic)
    try:
        bbox = draw.textbbox((0, 0), header_txt, font=header_font)
        hw = bbox[2] - bbox[0]
    except Exception:
        hw = len(header_txt) * 9
    
    hx = (TARGET_W - hw) // 2
    draw.text((hx, 12), header_txt, fill=(220, 220, 240), font=header_font)
    
    # خط تحت العنوان
    draw.rectangle([(TARGET_W // 4, 35), (TARGET_W * 3 // 4, 37)], fill=accent)

    # ── منطقة الصورة (أعلى) ──────────────────────────────────────────────────
    img_area_h = 240
    img_y = 45
    
    if image_bytes:
        try:
            img = PILImage.open(io.BytesIO(image_bytes)).convert("RGB")
            iw, ih = img.size
            
            # تناسب الصورة
            max_w = TARGET_W - 40
            max_h = img_area_h - 10
            scale = min(max_w / iw, max_h / ih)
            nw, nh = int(iw * scale), int(ih * scale)
            img = img.resize((nw, nh), PILImage.LANCZOS)
            
            px = (TARGET_W - nw) // 2
            py = img_y + (img_area_h - nh) // 2
            
            # إطار للصورة
            draw.rectangle(
                [(px - 3, py - 3), (px + nw + 3, py + nh + 3)],
                outline=accent, width=2
            )
            bg.paste(img, (px, py))
        except Exception as e:
            print(f"Image paste error: {e}")
            # رسم مستطيل فارغ
            draw.rectangle(
                [(20, img_y), (TARGET_W - 20, img_y + img_area_h)],
                outline=(100, 100, 120), width=2
            )
            no_img = _prepare_text("🖼️ صورة توضيحية", is_arabic)
            no_font = _get_font(16, arabic=is_arabic)
            try:
                bbox = draw.textbbox((0, 0), no_img, font=no_font)
                nw = bbox[2] - bbox[0]
            except Exception:
                nw = len(no_img) * 9
            nx = (TARGET_W - nw) // 2
            draw.text((nx, img_y + img_area_h // 2 - 10), no_img, fill=(150, 150, 170), font=no_font)
    else:
        draw.rectangle(
            [(20, img_y), (TARGET_W - 20, img_y + img_area_h)],
            outline=(100, 100, 120), width=2
        )

    # ── الكلمة المفتاحية ─────────────────────────────────────────────────────
    kw_y = img_y + img_area_h + 10
    kw_disp = _prepare_text(keyword, is_arabic)
    kw_font = _get_font(22, bold=True, arabic=is_arabic)
    
    # خلفية للكلمة المفتاحية
    try:
        bbox = draw.textbbox((0, 0), kw_disp, font=kw_font)
        kw_w = bbox[2] - bbox[0]
        kw_h = bbox[3] - bbox[1]
    except Exception:
        kw_w = len(kw_disp) * 13
        kw_h = 28
    
    kw_bg_x = (TARGET_W - kw_w) // 2 - 15
    draw.rectangle(
        [(kw_bg_x, kw_y - 5), (kw_bg_x + kw_w + 30, kw_y + kw_h + 5)],
        fill=(*accent, 50) if len(accent) == 3 else accent
    )
    draw.rectangle(
        [(kw_bg_x, kw_y + kw_h + 5), (kw_bg_x + kw_w + 30, kw_y + kw_h + 8)],
        fill=accent
    )
    
    kw_x = (TARGET_W - kw_w) // 2
    draw.text((kw_x + 2, kw_y + 2), kw_disp, fill=(0, 0, 0), font=kw_font)
    draw.text((kw_x, kw_y), kw_disp, fill=(255, 255, 255), font=kw_font)

    # ── نص الشرح ─────────────────────────────────────────────────────────────
    text_y = kw_y + kw_h + 20
    text_font = _get_font(16, arabic=is_arabic)
    
    # تحضير النص (أخذ جملة أو جملتين من narration)
    sentences = narration.split('.')
    short_text = '.'.join(sentences[:2]) + '.' if len(sentences) > 1 else narration[:200]
    display_text = _prepare_text(short_text, is_arabic)
    
    lines = _wrap_text(display_text, text_font, TARGET_W - 60)
    
    for i, line in enumerate(lines[:4]):  # أقصى حد 4 أسطر
        try:
            bbox = draw.textbbox((0, 0), line, font=text_font)
            lw = bbox[2] - bbox[0]
        except Exception:
            lw = len(line) * 9
        lx = (TARGET_W - lw) // 2
        ly = text_y + i * 24
        if ly + 24 < TARGET_H - 40:
            draw.text((lx + 1, ly + 1), line, fill=(0, 0, 0), font=text_font)
            draw.text((lx, ly), line, fill=(230, 230, 245), font=text_font)

    # ── مؤشر التقدم ──────────────────────────────────────────────────────────
    footer_y = TARGET_H - 30
    progress_txt = f"{kw_idx + 1} / {total_kw}"
    prog_font = _get_font(12)
    try:
        bbox = draw.textbbox((0, 0), progress_txt, font=prog_font)
        pw = bbox[2] - bbox[0]
    except Exception:
        pw = len(progress_txt) * 7
    px = (TARGET_W - pw) // 2
    draw.text((px, footer_y), progress_txt, fill=(150, 160, 180), font=prog_font)

    # نقاط التقدم
    dot_r = 5
    dot_gap = 20
    total_w = total_kw * dot_gap
    start_x = (TARGET_W - total_w) // 2
    dot_y = footer_y - 12
    
    for i in range(total_kw):
        dx = start_x + i * dot_gap
        color = accent if i <= kw_idx else (100, 110, 130)
        r = dot_r if i <= kw_idx else dot_r - 1
        draw.ellipse([(dx - r, dot_y - r), (dx + r, dot_y + r)], fill=color)

    # علامة مائية
    wm_font = _get_font(10)
    try:
        bbox = draw.textbbox((0, 0), WATERMARK, font=wm_font)
        ww = bbox[2] - bbox[0]
    except Exception:
        ww = len(WATERMARK) * 6
    draw.text((TARGET_W - ww - 10, TARGET_H - 15), WATERMARK, fill=(100, 110, 130), font=wm_font)

    bg.save(path, "JPEG", quality=92)
    return path


# ─────────────────────────────────────────────────────────────────────────────
# 4. شريحة فاصل انتقالي - Transition Slide
# ─────────────────────────────────────────────────────────────────────────────

def _draw_transition_slide(is_arabic: bool) -> str:
    fd, path = tempfile.mkstemp(prefix="transition_", suffix=".jpg")
    os.close(fd)

    bg = _gradient_bg((25, 30, 50), (15, 20, 40))
    draw = ImageDraw.Draw(bg)

    # دوائر زخرفية
    for i in range(3):
        cx = TARGET_W // 2
        cy = TARGET_H // 2
        r = 30 + i * 20
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(255, 200, 50, 100 - i * 30), width=2)

    transition_txt = _prepare_text("⏸️ يتبع...", is_arabic)
    trans_font = _get_font(24, arabic=is_arabic)
    try:
        bbox = draw.textbbox((0, 0), transition_txt, font=trans_font)
        tw = bbox[2] - bbox[0]
    except Exception:
        tw = len(transition_txt) * 14
    tx = (TARGET_W - tw) // 2
    draw.text((tx, TARGET_H // 2 - 12), transition_txt, fill=(220, 220, 250), font=trans_font)

    bg.save(path, "JPEG", quality=90)
    return path


# ─────────────────────────────────────────────────────────────────────────────
# 5. شريحة الملخص النهائي - Summary Slide
# ─────────────────────────────────────────────────────────────────────────────

def _draw_summary_slide(sections: list, lecture_data: dict, is_arabic: bool) -> str:
    img_fd, img_path = tempfile.mkstemp(prefix="summary_", suffix=".jpg")
    os.close(img_fd)

    bg = _gradient_bg((20, 30, 60), (10, 20, 40))
    draw = ImageDraw.Draw(bg)

    # شريط علوي
    draw.rectangle([(0, 0), (TARGET_W, 6)], fill=(255, 200, 50))

    # عنوان الملخص
    summary_title = "📋 ملخص المحاضرة" if is_arabic else "📋 Lecture Summary"
    title_txt = _prepare_text(summary_title, is_arabic)
    title_font = _get_font(28, bold=True, arabic=is_arabic)
    try:
        bbox = draw.textbbox((0, 0), title_txt, font=title_font)
        tw = bbox[2] - bbox[0]
    except Exception:
        tw = len(title_txt) * 16
    tx = (TARGET_W - tw) // 2
    draw.text((tx + 2, 22), title_txt, fill=(0, 0, 0), font=title_font)
    draw.text((tx, 20), title_txt, fill=(255, 220, 80), font=title_font)

    draw.rectangle([(TARGET_W // 4, 58), (TARGET_W * 3 // 4, 60)], fill=(255, 200, 50))

    # عرض الأقسام
    y_start = 75
    sec_font = _get_font(15, arabic=is_arabic)
    
    for i, section in enumerate(sections[:8]):  # أقصى حد 8 أقسام
        accent = ACCENT_COLORS[i % len(ACCENT_COLORS)]
        
        # رقم القسم
        num_str = f"{i + 1}."
        num_x = 30 if is_arabic else TARGET_W - 50
        draw.text((num_x, y_start + i * 28), num_str, fill=accent, font=sec_font)
        
        # عنوان القسم
        sec_title = section.get("title", f"Section {i+1}")[:35]
        sec_txt = _prepare_text(sec_title, is_arabic)
        title_x = 60 if is_arabic else TARGET_W - 80
        draw.text((title_x, y_start + i * 28), sec_txt, fill=(220, 220, 240), font=sec_font)

    # رسالة ختامية
    thanks_txt = "🎓 شكراً لمتابعتكم" if is_arabic else "🎓 Thank you for watching"
    thanks_txt = _prepare_text(thanks_txt, is_arabic)
    thanks_font = _get_font(20, bold=True, arabic=is_arabic)
    try:
        bbox = draw.textbbox((0, 0), thanks_txt, font=thanks_font)
        tw = bbox[2] - bbox[0]
    except Exception:
        tw = len(thanks_txt) * 12
    tx = (TARGET_W - tw) // 2
    draw.text((tx + 2, TARGET_H - 60), thanks_txt, fill=(0, 0, 0), font=thanks_font)
    draw.text((tx, TARGET_H - 62), thanks_txt, fill=(255, 220, 80), font=thanks_font)

    # علامة مائية
    wm_font = _get_font(12)
    try:
        bbox = draw.textbbox((0, 0), WATERMARK, font=wm_font)
        ww = bbox[2] - bbox[0]
    except Exception:
        ww = len(WATERMARK) * 7
    draw.text(((TARGET_W - ww) // 2, TARGET_H - 25), WATERMARK, fill=(100, 120, 150), font=wm_font)

    bg.save(img_path, "JPEG", quality=90)
    return img_path


# ─────────────────────────────────────────────────────────────────────────────
# FFmpeg Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _ffmpeg_segment(img_path: str, duration: float, audio_path: str | None,
                    audio_start: float, out_path: str) -> None:
    dur_str = f"{duration:.3f}"
    fps_main = 15

    def _audio_args():
        if audio_path and os.path.exists(audio_path):
            return ["-ss", f"{audio_start:.3f}", "-t", dur_str, "-i", audio_path]
        return ["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100"]

    vf = "scale=854:480:force_original_aspect_ratio=decrease,pad=854:480:(ow-iw)/2:(oh-ih)/2"
    aud = _audio_args()
    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-t", dur_str, "-i", img_path,
        *aud,
        "-c:v", "libx264", "-preset", "fast",
        "-pix_fmt", "yuv420p", "-r", str(fps_main), "-vf", vf,
        "-map", "0:v", "-map", "1:a",
        "-c:a", "aac", "-b:a", "96k", "-ar", "44100", "-ac", "2",
        "-t", dur_str, out_path,
    ]

    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg segment failed: {result.stderr[-600:]}")


def _ffmpeg_concat(segment_paths: list[str], output_path: str) -> None:
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
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────────────────────
# بناء قائمة المقاطع
# ─────────────────────────────────────────────────────────────────────────────

def _build_segment_list(
    sections: list,
    audio_results: list,
    lecture_data: dict,
    is_arabic: bool,
) -> tuple[list[dict], list[str], float]:
    segments: list[dict] = []
    tmp_files: list[str] = []
    total_secs = 0.0
    n_sections = len(sections)

    # 1. المقدمة
    try:
        intro_path = _draw_intro_slide(lecture_data, sections, is_arabic)
        tmp_files.append(intro_path)
        segments.append({"img": intro_path, "audio": None, "audio_start": 0.0, "dur": _INTRO_DURATION})
        total_secs += _INTRO_DURATION
    except Exception as e:
        print(f"Intro slide failed: {e}")

    # 2. الأقسام
    for sec_idx, (section, audio_info) in enumerate(zip(sections, audio_results)):
        # عنوان القسم
        try:
            title_path = _draw_section_title_card(section, sec_idx, n_sections, is_arabic)
            tmp_files.append(title_path)
            segments.append({"img": title_path, "audio": None, "audio_start": 0.0, "dur": _SECTION_TITLE_DUR})
            total_secs += _SECTION_TITLE_DUR
        except Exception as e:
            print(f"Section title card failed: {e}")

        keywords = section.get("keywords") or ["المفهوم"]
        kw_images = section.get("_keyword_images") or []
        audio_bytes = audio_info.get("audio")
        narration = section.get("narration", section.get("content", ""))
        total_dur = max(float(audio_info.get("duration", 45)), 3.0)
        kw_dur = total_dur / max(len(keywords), 1)

        # ملف الصوت
        apath = None
        if audio_bytes:
            afd, apath = tempfile.mkstemp(prefix=f"aud_{sec_idx}_", suffix=".mp3")
            os.close(afd)
            with open(apath, "wb") as f:
                f.write(audio_bytes)
            tmp_files.append(apath)

        fallback_img = section.get("_image_bytes")
        sec_title = section.get("title", "")

        # شرائح المحتوى (كل كلمة مفتاحية)
        for kw_idx, keyword in enumerate(keywords):
            img_bytes = kw_images[kw_idx] if kw_idx < len(kw_images) else fallback_img
            
            content_path = _draw_content_slide(
                image_bytes=img_bytes,
                keyword=keyword,
                narration=narration,
                is_arabic=is_arabic,
                section_title=sec_title,
                section_idx=sec_idx,
                total_sections=n_sections,
                kw_idx=kw_idx,
                total_kw=len(keywords),
            )
            tmp_files.append(content_path)
            segments.append({
                "img": content_path,
                "audio": apath,
                "audio_start": kw_idx * kw_dur,
                "dur": kw_dur,
            })
            total_secs += kw_dur

        # فاصل بين الأقسام (إلا القسم الأخير)
        if sec_idx < n_sections - 1:
            try:
                trans_path = _draw_transition_slide(is_arabic)
                tmp_files.append(trans_path)
                segments.append({"img": trans_path, "audio": None, "audio_start": 0.0, "dur": _TRANSITION_DUR})
                total_secs += _TRANSITION_DUR
            except Exception as e:
                print(f"Transition slide failed: {e}")

    # 3. الملخص النهائي
    try:
        summary_path = _draw_summary_slide(sections, lecture_data, is_arabic)
        tmp_files.append(summary_path)
        segments.append({"img": summary_path, "audio": None, "audio_start": 0.0, "dur": _SUMMARY_DURATION})
        total_secs += _SUMMARY_DURATION
    except Exception as e:
        print(f"Summary slide failed: {e}")

    return segments, tmp_files, total_secs


def _encode_all_sync(segments: list[dict], output_path: str) -> None:
    seg_paths: list[str] = []
    try:
        for i, seg in enumerate(segments):
            fd, seg_out = tempfile.mkstemp(prefix=f"seg_{i}_", suffix=".mp4")
            os.close(fd)
            seg_paths.append(seg_out)
            _ffmpeg_segment(
                seg["img"], seg["dur"], seg["audio"], seg["audio_start"], seg_out
            )
            print(f"  ✅ Segment {i+1}/{len(segments)} encoded ({seg['dur']:.1f}s)")

        _ffmpeg_concat(seg_paths, output_path)
        print(f"  ✅ Concatenated {len(seg_paths)} segments → {output_path}")
    finally:
        for p in seg_paths:
            try:
                os.remove(p)
            except Exception:
                pass


# ─────────────────────────────────────────────────────────────────────────────
# الدالة الرئيسية
# ─────────────────────────────────────────────────────────────────────────────

async def create_video_from_sections(
    sections: list,
    audio_results: list,
    lecture_data: dict,
    output_path: str,
    dialect: str = "msa",
    progress_cb=None,
) -> float:
    is_arabic = dialect not in ("english", "british")
    loop = asyncio.get_event_loop()

    segments, tmp_files, total_video_secs = await loop.run_in_executor(
        None, _build_segment_list, sections, audio_results, lecture_data, is_arabic
    )

    if not segments:
        raise RuntimeError("No valid segments were generated for the video")

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
                except Exception:
                    pass
        await encode_task
    finally:
        for path in tmp_files:
            try:
                if os.path.exists(path):
                    os.remove(path)
            except Exception:
                pass

    return total_video_secs
