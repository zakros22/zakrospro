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

# ألوان متناسقة
ACCENT_COLORS = [
    (41, 128, 185),   # أزرق
    (39, 174, 96),    # أخضر
    (230, 126, 34),   # برتقالي
    (155, 89, 182),   # بنفسجي
    (231, 76, 60),    # أحمر
    (52, 152, 219),   # أزرق فاتح
    (241, 196, 15),   # أصفر
    (26, 188, 156),   # فيروزي
]

# ألوان السبورة
BOARD_BG = (255, 255, 255)        # أبيض
BOARD_BORDER = (200, 200, 200)    # رمادي فاتح
TEXT_COLOR = (33, 33, 33)         # أسود تقريباً
TITLE_BG = (240, 240, 245)        # رمادي فاتح جداً


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


# ─────────────────────────────────────────────────────────────────────────────
# 1. شريحة المقدمة
# ─────────────────────────────────────────────────────────────────────────────

def _draw_intro_slide(lecture_data: dict, sections: list, is_arabic: bool) -> str:
    img_fd, img_path = tempfile.mkstemp(prefix="intro_", suffix=".jpg")
    os.close(img_fd)

    # خلفية متدرجة
    img = PILImage.new("RGB", (TARGET_W, TARGET_H), (25, 30, 50))
    draw = ImageDraw.Draw(img)
    
    for y in range(TARGET_H):
        t = y / TARGET_H
        r = int(25 * (1 - t) + 45 * t)
        g = int(30 * (1 - t) + 55 * t)
        b = int(50 * (1 - t) + 80 * t)
        draw.line([(0, y), (TARGET_W, y)], fill=(r, g, b))

    # شريط ذهبي
    draw.rectangle([(0, 0), (TARGET_W, 6)], fill=(255, 200, 50))
    draw.rectangle([(0, TARGET_H - 6), (TARGET_W, TARGET_H)], fill=(255, 200, 50))

    # عنوان المحاضرة
    raw_title = lecture_data.get("title", "المحاضرة التعليمية" if is_arabic else "Educational Lecture")
    title_txt = _prepare_text(raw_title, is_arabic)
    title_font = _get_font(30, bold=True, arabic=is_arabic)
    
    lines = _wrap_text(title_txt, title_font, TARGET_W - 80)
    y_start = TARGET_H // 2 - (len(lines) * 40) // 2
    
    for i, line in enumerate(lines):
        try:
            bbox = draw.textbbox((0, 0), line, font=title_font)
            tw = bbox[2] - bbox[0]
        except Exception:
            tw = len(line) * 18
        x = (TARGET_W - tw) // 2
        y = y_start + i * 45
        draw.text((x + 3, y + 3), line, fill=(0, 0, 0), font=title_font)
        draw.text((x, y), line, fill=(255, 220, 80), font=title_font)

    # معلومات
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
    draw.text(((TARGET_W - ww) // 2, TARGET_H - 25), WATERMARK, fill=(120, 140, 170), font=wm_font)

    img.save(img_path, "JPEG", quality=90)
    return img_path


# ─────────────────────────────────────────────────────────────────────────────
# 2. شريحة عنوان القسم
# ─────────────────────────────────────────────────────────────────────────────

def _draw_section_title_card(section: dict, idx: int, total: int, is_arabic: bool) -> str:
    img_fd, img_path = tempfile.mkstemp(prefix=f"sec_title_{idx}_", suffix=".jpg")
    os.close(img_fd)

    accent = ACCENT_COLORS[idx % len(ACCENT_COLORS)]
    
    img = PILImage.new("RGB", (TARGET_W, TARGET_H), (250, 250, 252))
    draw = ImageDraw.Draw(img)

    # شريط علوي ملون
    draw.rectangle([(0, 0), (TARGET_W, 8)], fill=accent)

    # رقم القسم
    cx, cy, cr = TARGET_W // 2, TARGET_H // 2 - 50, 45
    draw.ellipse([cx - cr, cy - cr, cx + cr, cy + cr], fill=accent)
    num_str = str(idx + 1)
    num_font = _get_font(42, bold=True)
    try:
        bbox = draw.textbbox((0, 0), num_str, font=num_font)
        nw, nh = bbox[2] - bbox[0], bbox[3] - bbox[1]
    except Exception:
        nw, nh = 22, 42
    draw.text((cx - nw // 2, cy - nh // 2), num_str, fill=(255, 255, 255), font=num_font)

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
    draw.text((lx, cy + cr + 15), label_txt, fill=(100, 100, 120), font=label_font)

    # عنوان القسم
    raw_title = section.get("title", f"القسم {idx + 1}")
    title_txt = _prepare_text(raw_title, is_arabic)
    title_font = _get_font(26, bold=True, arabic=is_arabic)
    
    lines = _wrap_text(title_txt, title_font, TARGET_W - 100)
    y_start = cy + cr + 50
    
    for i, line in enumerate(lines):
        try:
            bbox = draw.textbbox((0, 0), line, font=title_font)
            lw = bbox[2] - bbox[0]
        except Exception:
            lw = len(line) * 15
        lx = (TARGET_W - lw) // 2
        draw.text((lx, y_start + i * 40), line, fill=TEXT_COLOR, font=title_font)

    img.save(img_path, "JPEG", quality=90)
    return img_path


# ─────────────────────────────────────────────────────────────────────────────
# 3. شريحة السبورة البيضاء المتراكمة (الرئيسية)
# ─────────────────────────────────────────────────────────────────────────────

def _draw_whiteboard_slide(
    accumulated_images: list[bytes | None],
    accumulated_keywords: list[str],
    section_title: str,
    section_idx: int,
    total_sections: int,
    is_arabic: bool,
    current_kw_idx: int,
    total_kw: int,
) -> str:
    """
    سبورة بيضاء تتراكم عليها الصور والكلمات مع تقدم الشرح.
    accumulated_images: الصور المضافة حتى الآن
    accumulated_keywords: الكلمات المضافة حتى الآن
    """
    fd, path = tempfile.mkstemp(prefix="board_", suffix=".jpg")
    os.close(fd)

    accent = ACCENT_COLORS[section_idx % len(ACCENT_COLORS)]
    
    # خلفية السبورة البيضاء
    img = PILImage.new("RGB", (TARGET_W, TARGET_H), BOARD_BG)
    draw = ImageDraw.Draw(img)

    # إطار خشبي
    frame_w = 12
    draw.rectangle([(0, 0), (TARGET_W, TARGET_H)], outline=(139, 90, 43), width=frame_w)
    draw.rectangle([(frame_w, frame_w), (TARGET_W - frame_w, TARGET_H - frame_w)], 
                   outline=(160, 110, 60), width=2)

    # منطقة المحتوى (داخل الإطار)
    content_x = frame_w + 8
    content_y = frame_w + 8
    content_w = TARGET_W - 2 * (frame_w + 8)
    content_h = TARGET_H - 2 * (frame_w + 8)

    # ── رأس السبورة: عنوان القسم ───────────────────────────────────────────
    header_h = 45
    draw.rectangle([(content_x, content_y), (content_x + content_w, content_y + header_h)], 
                   fill=TITLE_BG, outline=(200, 200, 200), width=1)
    
    # شريط ملون
    draw.rectangle([(content_x, content_y), (content_x + content_w, content_y + 4)], fill=accent)
    
    # عنوان القسم
    header_txt = _prepare_text(section_title[:40], is_arabic)
    header_font = _get_font(16, bold=True, arabic=is_arabic)
    try:
        bbox = draw.textbbox((0, 0), header_txt, font=header_font)
        hw = bbox[2] - bbox[0]
        hh = bbox[3] - bbox[1]
    except Exception:
        hw = len(header_txt) * 9
        hh = 18
    
    hx = content_x + (content_w - hw) // 2
    hy = content_y + (header_h - hh) // 2
    draw.text((hx, hy), header_txt, fill=TEXT_COLOR, font=header_font)
    
    # رقم القسم
    sec_num = f"{section_idx + 1}/{total_sections}"
    num_font = _get_font(11)
    try:
        bbox = draw.textbbox((0, 0), sec_num, font=num_font)
        nw = bbox[2] - bbox[0]
    except Exception:
        nw = len(sec_num) * 6
    nx = content_x + content_w - nw - 8
    draw.text((nx, hy + 2), sec_num, fill=(120, 120, 140), font=num_font)

    # ── منطقة تراكم المحتوى ────────────────────────────────────────────────
    board_content_y = content_y + header_h + 10
    board_content_h = content_h - header_h - 50

    n_items = len(accumulated_keywords)
    
    if n_items == 0:
        # لا يوجد محتوى بعد
        pass
    elif n_items == 1:
        # عنصر واحد: صورة كبيرة في المنتصف والكلمة تحتها
        img_bytes = accumulated_images[0]
        kw = accumulated_keywords[0]
        
        img_area_h = board_content_h - 40
        img_y = board_content_y + 10
        
        if img_bytes:
            try:
                pil_img = PILImage.open(io.BytesIO(img_bytes)).convert("RGB")
                iw, ih = pil_img.size
                
                max_w = content_w - 20
                max_h = img_area_h
                scale = min(max_w / iw, max_h / ih)
                nw, nh = int(iw * scale), int(ih * scale)
                pil_img = pil_img.resize((nw, nh), PILImage.LANCZOS)
                
                px = content_x + (content_w - nw) // 2
                py = img_y + (img_area_h - nh) // 2
                
                # إطار للصورة
                draw.rectangle([(px - 3, py - 3), (px + nw + 3, py + nh + 3)], 
                              outline=accent, width=2)
                img.paste(pil_img, (px, py))
            except Exception:
                pass
        
        # الكلمة المفتاحية
        kw_disp = _prepare_text(kw, is_arabic)
        kw_font = _get_font(20, bold=True, arabic=is_arabic)
        try:
            bbox = draw.textbbox((0, 0), kw_disp, font=kw_font)
            kww = bbox[2] - bbox[0]
        except Exception:
            kww = len(kw_disp) * 12
        
        kw_x = content_x + (content_w - kww) // 2
        kw_y = board_content_y + board_content_h - 30
        draw.text((kw_x, kw_y), kw_disp, fill=accent, font=kw_font)
        
    else:
        # عناصر متعددة: شبكة 2x2
        cols = 2
        rows = (n_items + 1) // 2
        
        cell_w = content_w // cols - 10
        cell_h = (board_content_h // rows) - 10
        
        for i in range(n_items):
            col = i % cols
            row = i // cols
            
            cx = content_x + 5 + col * (cell_w + 10)
            cy = board_content_y + 5 + row * (cell_h + 10)
            
            # صورة مصغرة
            img_bytes = accumulated_images[i] if i < len(accumulated_images) else None
            img_h = cell_h - 35
            
            if img_bytes:
                try:
                    pil_img = PILImage.open(io.BytesIO(img_bytes)).convert("RGB")
                    iw, ih = pil_img.size
                    
                    max_w = cell_w - 6
                    max_h = img_h
                    scale = min(max_w / iw, max_h / ih)
                    nw, nh = max(1, int(iw * scale)), max(1, int(ih * scale))
                    pil_img = pil_img.resize((nw, nh), PILImage.LANCZOS)
                    
                    px = cx + (cell_w - nw) // 2
                    py = cy + (img_h - nh) // 2
                    
                    draw.rectangle([(cx, cy), (cx + cell_w, cy + img_h)], 
                                  outline=(220, 220, 220), width=1)
                    img.paste(pil_img, (px, py))
                except Exception:
                    draw.rectangle([(cx, cy), (cx + cell_w, cy + img_h)], 
                                  outline=(220, 220, 220), width=1)
            
            # الكلمة المفتاحية
            kw = accumulated_keywords[i]
            kw_disp = _prepare_text(kw[:20], is_arabic)
            kw_font = _get_font(12, bold=True, arabic=is_arabic)
            
            try:
                bbox = draw.textbbox((0, 0), kw_disp, font=kw_font)
                kww = bbox[2] - bbox[0]
            except Exception:
                kww = len(kw_disp) * 7
            
            kw_x = cx + (cell_w - kww) // 2
            kw_y = cy + img_h + 3
            draw.text((kw_x, kw_y), kw_disp, fill=TEXT_COLOR, font=kw_font)

    # ── مؤشر التقدم (نقاط) ─────────────────────────────────────────────────
    dot_y = content_y + content_h - 20
    dot_r = 5
    dot_gap = 20
    total_w = total_kw * dot_gap
    start_x = content_x + (content_w - total_w) // 2
    
    for i in range(total_kw):
        dx = start_x + i * dot_gap
        color = accent if i <= current_kw_idx else (200, 200, 200)
        r = dot_r if i <= current_kw_idx else dot_r - 2
        draw.ellipse([(dx - r, dot_y - r), (dx + r, dot_y + r)], fill=color)

    # علامة مائية
    wm_font = _get_font(10)
    try:
        bbox = draw.textbbox((0, 0), WATERMARK, font=wm_font)
        ww = bbox[2] - bbox[0]
    except Exception:
        ww = len(WATERMARK) * 6
    draw.text((TARGET_W - ww - 18, TARGET_H - 18), WATERMARK, fill=(180, 180, 190), font=wm_font)

    img.save(path, "JPEG", quality=92)
    return path


# ─────────────────────────────────────────────────────────────────────────────
# 4. شريحة ملخص القسم
# ─────────────────────────────────────────────────────────────────────────────

def _draw_section_summary(section: dict, idx: int, is_arabic: bool) -> str:
    img_fd, img_path = tempfile.mkstemp(prefix=f"sec_summary_{idx}_", suffix=".jpg")
    os.close(img_fd)

    accent = ACCENT_COLORS[idx % len(ACCENT_COLORS)]
    
    img = PILImage.new("RGB", (TARGET_W, TARGET_H), (250, 250, 252))
    draw = ImageDraw.Draw(img)

    draw.rectangle([(0, 0), (TARGET_W, 6)], fill=accent)

    # عنوان
    title_txt = _prepare_text("✅ تم الانتهاء من القسم", is_arabic)
    title_font = _get_font(22, bold=True, arabic=is_arabic)
    try:
        bbox = draw.textbbox((0, 0), title_txt, font=title_font)
        tw = bbox[2] - bbox[0]
    except Exception:
        tw = len(title_txt) * 13
    tx = (TARGET_W - tw) // 2
    draw.text((tx, 40), title_txt, fill=accent, font=title_font)

    # الكلمات المفتاحية
    keywords = section.get("keywords", [])
    kw_txt = " • ".join(keywords[:4])
    kw_disp = _prepare_text(kw_txt, is_arabic)
    kw_font = _get_font(16, arabic=is_arabic)
    try:
        bbox = draw.textbbox((0, 0), kw_disp, font=kw_font)
        kww = bbox[2] - bbox[0]
    except Exception:
        kww = len(kw_disp) * 9
    kx = (TARGET_W - kww) // 2
    draw.text((kx, 120), kw_disp, fill=TEXT_COLOR, font=kw_font)

    img.save(img_path, "JPEG", quality=90)
    return img_path


# ─────────────────────────────────────────────────────────────────────────────
# 5. شريحة الملخص النهائي
# ─────────────────────────────────────────────────────────────────────────────

def _draw_final_summary(sections: list, lecture_data: dict, is_arabic: bool) -> str:
    img_fd, img_path = tempfile.mkstemp(prefix="final_summary_", suffix=".jpg")
    os.close(img_fd)

    img = PILImage.new("RGB", (TARGET_W, TARGET_H), BOARD_BG)
    draw = ImageDraw.Draw(img)

    frame_w = 12
    draw.rectangle([(0, 0), (TARGET_W, TARGET_H)], outline=(139, 90, 43), width=frame_w)

    # عنوان
    title_txt = _prepare_text("📋 ملخص المحاضرة", is_arabic)
    title_font = _get_font(26, bold=True, arabic=is_arabic)
    try:
        bbox = draw.textbbox((0, 0), title_txt, font=title_font)
        tw = bbox[2] - bbox[0]
    except Exception:
        tw = len(title_txt) * 15
    tx = (TARGET_W - tw) // 2
    draw.text((tx, 35), title_txt, fill=(41, 128, 185), font=title_font)

    draw.rectangle([(TARGET_W // 4, 65), (TARGET_W * 3 // 4, 67)], fill=(41, 128, 185))

    # قائمة الأقسام
    y = 90
    for i, section in enumerate(sections):
        accent = ACCENT_COLORS[i % len(ACCENT_COLORS)]
        
        # مربع ملون
        draw.rectangle([(40, y), (55, y + 15)], fill=accent)
        
        sec_title = section.get("title", f"القسم {i+1}")[:35]
        sec_txt = _prepare_text(f"{i+1}. {sec_title}", is_arabic)
        sec_font = _get_font(14, arabic=is_arabic)
        draw.text((65, y - 2), sec_txt, fill=TEXT_COLOR, font=sec_font)
        
        y += 28

    # ملخص
    summary = lecture_data.get("summary", "")
    if summary:
        summary_txt = _prepare_text(summary[:200], is_arabic)
        summary_font = _get_font(13, arabic=is_arabic)
        lines = _wrap_text(summary_txt, summary_font, TARGET_W - 60)
        y += 20
        for line in lines[:3]:
            draw.text((40, y), line, fill=(80, 80, 100), font=summary_font)
            y += 20

    # رسالة ختامية
    thanks_txt = _prepare_text("🎓 شكراً لمتابعتكم", is_arabic)
    thanks_font = _get_font(20, bold=True, arabic=is_arabic)
    try:
        bbox = draw.textbbox((0, 0), thanks_txt, font=thanks_font)
        tw = bbox[2] - bbox[0]
    except Exception:
        tw = len(thanks_txt) * 12
    tx = (TARGET_W - tw) // 2
    draw.text((tx, TARGET_H - 60), thanks_txt, fill=(41, 128, 185), font=thanks_font)

    img.save(img_path, "JPEG", quality=90)
    return img_path


# ─────────────────────────────────────────────────────────────────────────────
# FFmpeg
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
# بناء المقاطع
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

    # 1. مقدمة (6 ثواني)
    intro_path = _draw_intro_slide(lecture_data, sections, is_arabic)
    tmp_files.append(intro_path)
    segments.append({"img": intro_path, "audio": None, "audio_start": 0.0, "dur": 6.0})
    total_secs += 6.0

    # 2. الأقسام
    for sec_idx, (section, audio_info) in enumerate(zip(sections, audio_results)):
        # عنوان القسم (3 ثواني)
        title_path = _draw_section_title_card(section, sec_idx, n_sections, is_arabic)
        tmp_files.append(title_path)
        segments.append({"img": title_path, "audio": None, "audio_start": 0.0, "dur": 3.0})
        total_secs += 3.0

        keywords = section.get("keywords", ["المفهوم"])
        kw_images = section.get("_keyword_images", [])
        audio_bytes = audio_info.get("audio")
        total_dur = max(float(audio_info.get("duration", 30)), 5.0)
        
        # مدة كل كلمة
        n_kw = len(keywords)
        kw_dur = total_dur / n_kw if n_kw > 0 else total_dur

        # ملف الصوت
        apath = None
        if audio_bytes:
            afd, apath = tempfile.mkstemp(prefix=f"aud_{sec_idx}_", suffix=".mp3")
            os.close(afd)
            with open(apath, "wb") as f:
                f.write(audio_bytes)
            tmp_files.append(apath)

        sec_title = section.get("title", "")
        
        # تراكم الصور والكلمات
        accumulated_imgs = []
        accumulated_kws = []
        
        for kw_idx, keyword in enumerate(keywords):
            # إضافة الصورة والكلمة الحالية
            img_bytes = kw_images[kw_idx] if kw_idx < len(kw_images) else None
            accumulated_imgs.append(img_bytes)
            accumulated_kws.append(keyword)
            
            # رسم السبورة بالمحتوى المتراكم
            board_path = _draw_whiteboard_slide(
                accumulated_images=accumulated_imgs.copy(),
                accumulated_keywords=accumulated_kws.copy(),
                section_title=sec_title,
                section_idx=sec_idx,
                total_sections=n_sections,
                is_arabic=is_arabic,
                current_kw_idx=kw_idx,
                total_kw=n_kw,
            )
            tmp_files.append(board_path)
            
            segments.append({
                "img": board_path,
                "audio": apath,
                "audio_start": kw_idx * kw_dur,
                "dur": kw_dur,
            })
            total_secs += kw_dur

        # ملخص القسم (2 ثانية)
        if n_kw > 0:
            summary_path = _draw_section_summary(section, sec_idx, is_arabic)
            tmp_files.append(summary_path)
            segments.append({"img": summary_path, "audio": None, "audio_start": 0.0, "dur": 2.0})
            total_secs += 2.0

    # 3. ملخص نهائي (8 ثواني)
    final_path = _draw_final_summary(sections, lecture_data, is_arabic)
    tmp_files.append(final_path)
    segments.append({"img": final_path, "audio": None, "audio_start": 0.0, "dur": 8.0})
    total_secs += 8.0

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
        _ffmpeg_concat(seg_paths, output_path)
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
        raise RuntimeError("No valid segments")

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
