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

# ألوان Osmosis المميزة
OSMOSIS_PINK = (231, 76, 126)      # وردي للأسهم والعناوين
OSMOSIS_BLUE = (52, 152, 219)      # أزرق للتعليقات
OSMOSIS_GREEN = (46, 204, 113)     # أخضر للمفاهيم الإيجابية
OSMOSIS_RED = (231, 76, 60)        # أحمر للتحذيرات/الأمراض
OSMOSIS_PURPLE = (155, 89, 182)    # بنفسجي
OSMOSIS_ORANGE = (230, 126, 34)    # برتقالي
OSMOSIS_DARK = (44, 62, 80)        # أزرق داكن للنصوص
OSMOSIS_GRAY = (127, 140, 141)     # رمادي

# خلفية السبورة
BOARD_BG = (255, 255, 255)          # أبيض ناصع

# ألوان حسب نوع المحاضرة
TYPE_COLORS = {
    'medicine': OSMOSIS_PINK,
    'math': OSMOSIS_BLUE,
    'physics': OSMOSIS_BLUE,
    'chemistry': OSMOSIS_GREEN,
    'history': OSMOSIS_ORANGE,
    'biology': OSMOSIS_GREEN,
    'computer': OSMOSIS_PURPLE,
    'other': OSMOSIS_PINK
}

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
        reshaped = arabic_reshaper.reshape(text)
        return get_display(reshaped)
    except Exception:
        return text


def _draw_osmosis_arrow(draw, x1, y1, x2, y2, color=OSMOSIS_PINK, width=3):
    """رسم سهم بأسلوب Osmosis"""
    import math
    draw.line([(x1, y1), (x2, y2)], fill=color, width=width)
    
    angle = math.atan2(y2 - y1, x2 - x1)
    arrow_len = 12
    arrow_angle = 0.4
    
    x3 = x2 - arrow_len * math.cos(angle - arrow_angle)
    y3 = y2 - arrow_len * math.sin(angle - arrow_angle)
    x4 = x2 - arrow_len * math.cos(angle + arrow_angle)
    y4 = y2 - arrow_len * math.sin(angle + arrow_angle)
    
    draw.polygon([(x2, y2), (x3, y3), (x4, y4)], fill=color)


# ─────────────────────────────────────────────────────────────────────────────
# شريحة المقدمة - Osmosis Style
# ─────────────────────────────────────────────────────────────────────────────

def _draw_intro_slide(lecture_data: dict, sections: list, is_arabic: bool) -> str:
    img_fd, img_path = tempfile.mkstemp(prefix="intro_", suffix=".jpg")
    os.close(img_fd)

    lecture_type = lecture_data.get("lecture_type", "other")
    accent = TYPE_COLORS.get(lecture_type, OSMOSIS_PINK)
    
    img = PILImage.new("RGB", (TARGET_W, TARGET_H), BOARD_BG)
    draw = ImageDraw.Draw(img)

    # شريط علوي
    draw.rectangle([(0, 0), (TARGET_W, 6)], fill=accent)

    # عنوان المحاضرة
    raw_title = lecture_data.get("title", "المحاضرة التعليمية")
    title_txt = _prepare_text(raw_title, is_arabic)
    title_font = _get_font(36, bold=True, arabic=is_arabic)
    
    # تقسيم العنوان
    words = title_txt.split()
    lines = []
    current = []
    for w in words:
        current.append(w)
        line = ' '.join(current)
        try:
            bbox = draw.textbbox((0, 0), line, font=title_font)
            if bbox[2] - bbox[0] > TARGET_W - 100:
                current.pop()
                lines.append(' '.join(current))
                current = [w]
        except Exception:
            pass
    if current:
        lines.append(' '.join(current))
    
    y = TARGET_H // 2 - (len(lines) * 50) // 2
    for line in lines:
        try:
            bbox = draw.textbbox((0, 0), line, font=title_font)
            tw = bbox[2] - bbox[0]
        except Exception:
            tw = len(line) * 20
        x = (TARGET_W - tw) // 2
        # ظل
        draw.text((x + 2, y + 2), line, fill=(220, 220, 220), font=title_font)
        # نص رئيسي
        draw.text((x, y), line, fill=OSMOSIS_DARK, font=title_font)
        y += 50

    # خط تحت العنوان
    draw.rectangle([(TARGET_W//4, y + 10), (TARGET_W*3//4, y + 12)], fill=accent)

    # نوع المحاضرة
    type_names = {
        'medicine': '🩺 محاضرة طبية',
        'math': '📐 محاضرة رياضيات',
        'physics': '⚡ محاضرة فيزياء',
        'chemistry': '🧪 محاضرة كيمياء',
        'history': '📜 محاضرة تاريخية',
        'biology': '🧬 محاضرة أحياء',
        'other': '📚 محاضرة تعليمية'
    }
    type_txt = type_names.get(lecture_type, '📚 محاضرة تعليمية')
    type_disp = _prepare_text(type_txt, is_arabic)
    type_font = _get_font(20, arabic=is_arabic)
    try:
        bbox = draw.textbbox((0, 0), type_disp, font=type_font)
        tw = bbox[2] - bbox[0]
    except Exception:
        tw = len(type_disp) * 12
    x = (TARGET_W - tw) // 2
    draw.text((x, y + 35), type_disp, fill=accent, font=type_font)

    # عدد الأقسام
    n_sec = len(sections)
    info_txt = f"📚 {n_sec} أقسام تعليمية" if is_arabic else f"📚 {n_sec} Sections"
    info_disp = _prepare_text(info_txt, is_arabic)
    info_font = _get_font(16, arabic=is_arabic)
    try:
        bbox = draw.textbbox((0, 0), info_disp, font=info_font)
        tw = bbox[2] - bbox[0]
    except Exception:
        tw = len(info_disp) * 10
    x = (TARGET_W - tw) // 2
    draw.text((x, y + 70), info_disp, fill=OSMOSIS_GRAY, font=info_font)

    # علامة مائية
    wm_font = _get_font(12)
    wm_disp = _prepare_text(WATERMARK, is_arabic)
    try:
        bbox = draw.textbbox((0, 0), wm_disp, font=wm_font)
        ww = bbox[2] - bbox[0]
    except Exception:
        ww = len(wm_disp) * 7
    draw.text(((TARGET_W - ww) // 2, TARGET_H - 30), wm_disp, fill=OSMOSIS_GRAY, font=wm_font)

    img.save(img_path, "JPEG", quality=90)
    return img_path


# ─────────────────────────────────────────────────────────────────────────────
# شريحة عنوان القسم
# ─────────────────────────────────────────────────────────────────────────────

def _draw_section_title_card(section: dict, idx: int, total: int, is_arabic: bool, lecture_type: str) -> str:
    img_fd, img_path = tempfile.mkstemp(prefix=f"sec_title_{idx}_", suffix=".jpg")
    os.close(img_fd)

    colors = [OSMOSIS_PINK, OSMOSIS_BLUE, OSMOSIS_GREEN, OSMOSIS_PURPLE, OSMOSIS_ORANGE]
    accent = colors[idx % len(colors)]
    
    img = PILImage.new("RGB", (TARGET_W, TARGET_H), BOARD_BG)
    draw = ImageDraw.Draw(img)

    # شريط علوي
    draw.rectangle([(0, 0), (TARGET_W, 6)], fill=accent)

    # دائرة مرقمة
    cx, cy, cr = TARGET_W // 2, TARGET_H // 2 - 50, 45
    draw.ellipse([cx - cr, cy - cr, cx + cr, cy + cr], fill=accent)
    num_str = str(idx + 1)
    num_font = _get_font(40, bold=True)
    try:
        bbox = draw.textbbox((0, 0), num_str, font=num_font)
        nw, nh = bbox[2] - bbox[0], bbox[3] - bbox[1]
    except Exception:
        nw, nh = 22, 40
    draw.text((cx - nw // 2, cy - nh // 2), num_str, fill=(255, 255, 255), font=num_font)

    # "القسم X من Y"
    label_raw = f"القسم {idx + 1} من {total}" if is_arabic else f"Section {idx + 1} of {total}"
    label_disp = _prepare_text(label_raw, is_arabic)
    label_font = _get_font(18, arabic=is_arabic)
    try:
        bbox = draw.textbbox((0, 0), label_disp, font=label_font)
        tw = bbox[2] - bbox[0]
    except Exception:
        tw = len(label_disp) * 10
    x = (TARGET_W - tw) // 2
    draw.text((x, cy + cr + 20), label_disp, fill=OSMOSIS_GRAY, font=label_font)

    # عنوان القسم
    raw_title = section.get("title", f"القسم {idx + 1}")
    title_disp = _prepare_text(raw_title, is_arabic)
    title_font = _get_font(32, bold=True, arabic=is_arabic)
    
    words = title_disp.split()
    lines = []
    current = []
    for w in words:
        current.append(w)
        line = ' '.join(current)
        try:
            bbox = draw.textbbox((0, 0), line, font=title_font)
            if bbox[2] - bbox[0] > TARGET_W - 80:
                current.pop()
                lines.append(' '.join(current))
                current = [w]
        except Exception:
            pass
    if current:
        lines.append(' '.join(current))
    
    y = cy + cr + 60
    for line in lines:
        try:
            bbox = draw.textbbox((0, 0), line, font=title_font)
            tw = bbox[2] - bbox[0]
        except Exception:
            tw = len(line) * 18
        x = (TARGET_W - tw) // 2
        draw.text((x, y), line, fill=OSMOSIS_DARK, font=title_font)
        y += 45

    img.save(img_path, "JPEG", quality=90)
    return img_path


# ─────────────────────────────────────────────────────────────────────────────
# شريحة السبورة البيضاء - Osmosis Style (العرض التراكمي مع النصوص العربية)
# ─────────────────────────────────────────────────────────────────────────────

def _draw_osmosis_board_slide(
    keywords: list[str],
    images: list[bytes | None],
    current_kw_idx: int,
    total_kw: int,
    section_title: str,
    section_idx: int,
    is_arabic: bool,
    lecture_type: str,
) -> str:
    """
    سبورة Osmosis تتراكم عليها العناصر تدريجياً مع النصوص العربية
    """
    fd, path = tempfile.mkstemp(prefix="osmosis_", suffix=".jpg")
    os.close(fd)

    colors = [OSMOSIS_PINK, OSMOSIS_BLUE, OSMOSIS_GREEN, OSMOSIS_PURPLE, OSMOSIS_ORANGE]
    accent = colors[section_idx % len(colors)]
    
    img = PILImage.new("RGB", (TARGET_W, TARGET_H), BOARD_BG)
    draw = ImageDraw.Draw(img)

    # إطار بسيط
    draw.rectangle([(4, 4), (TARGET_W-4, TARGET_H-4)], outline=(240, 240, 240), width=1)
    
    # شريط علوي
    draw.rectangle([(0, 0), (TARGET_W, 6)], fill=accent)

    # عنوان القسم في الأعلى
    header_disp = _prepare_text(section_title[:40], is_arabic)
    header_font = _get_font(20, bold=True, arabic=is_arabic)
    try:
        bbox = draw.textbbox((0, 0), header_disp, font=header_font)
        hw = bbox[2] - bbox[0]
    except Exception:
        hw = len(header_disp) * 12
    
    hx = (TARGET_W - hw) // 2
    draw.text((hx, 18), header_disp, fill=OSMOSIS_DARK, font=header_font)
    
    # خط تحت العنوان
    draw.rectangle([(hx, 42), (hx + hw, 44)], fill=accent)

    # ── منطقة المحتوى الرئيسية ─────────────────────────────────────────────
    content_y = 60
    
    n_revealed = current_kw_idx + 1
    
    if n_revealed == 1:
        # عنصر واحد: صورة في المنتصف والكلمة تحتها
        kw = keywords[0] if keywords else ""
        img_bytes = images[0] if images else None
        
        # صورة
        if img_bytes:
            try:
                pil_img = PILImage.open(io.BytesIO(img_bytes)).convert("RGB")
                iw, ih = pil_img.size
                max_w, max_h = 400, 250
                scale = min(max_w / iw, max_h / ih)
                nw, nh = int(iw * scale), int(ih * scale)
                pil_img = pil_img.resize((nw, nh), PILImage.LANCZOS)
                
                px = (TARGET_W - nw) // 2
                py = content_y + 20
                
                # إطار للصورة
                draw.rounded_rectangle(
                    [(px - 5, py - 5), (px + nw + 5, py + nh + 5)],
                    radius=8, outline=accent, width=3
                )
                img.paste(pil_img, (px, py))
                
                content_y = py + nh + 30
            except Exception:
                pass
        
        # الكلمة المفتاحية
        kw_disp = _prepare_text(kw, is_arabic)
        kw_font = _get_font(28, bold=True, arabic=is_arabic)
        try:
            bbox = draw.textbbox((0, 0), kw_disp, font=kw_font)
            kww = bbox[2] - bbox[0]
        except Exception:
            kww = len(kw_disp) * 16
        
        kw_x = (TARGET_W - kww) // 2
        draw.text((kw_x + 2, content_y + 2), kw_disp, fill=(220, 220, 220), font=kw_font)
        draw.text((kw_x, content_y), kw_disp, fill=accent, font=kw_font)
        
    else:
        # عناصر متعددة: شبكة
        cols = 2
        rows = (n_revealed + 1) // 2
        
        cell_w = (TARGET_W - 80) // cols
        cell_h = 180
        
        for i in range(n_revealed):
            col = i % cols
            row = i // cols
            
            cx = 40 + col * (cell_w + 20)
            cy = content_y + row * (cell_h + 20)
            
            kw = keywords[i] if i < len(keywords) else ""
            img_bytes = images[i] if i < len(images) else None
            cell_color = colors[i % len(colors)]
            
            # صورة مصغرة
            img_h = cell_h - 40
            if img_bytes:
                try:
                    pil_img = PILImage.open(io.BytesIO(img_bytes)).convert("RGB")
                    iw, ih = pil_img.size
                    max_w, max_h = cell_w - 10, img_h
                    scale = min(max_w / iw, max_h / ih)
                    nw, nh = int(iw * scale), int(ih * scale)
                    pil_img = pil_img.resize((nw, nh), PILImage.LANCZOS)
                    
                    px = cx + (cell_w - nw) // 2
                    py = cy
                    
                    draw.rounded_rectangle(
                        [(px - 3, py - 3), (px + nw + 3, py + nh + 3)],
                        radius=6, outline=cell_color, width=2
                    )
                    img.paste(pil_img, (px, py))
                except Exception:
                    pass
            
            # الكلمة المفتاحية
            kw_disp = _prepare_text(kw[:20], is_arabic)
            kw_font = _get_font(16, bold=True, arabic=is_arabic)
            try:
                bbox = draw.textbbox((0, 0), kw_disp, font=kw_font)
                kww = bbox[2] - bbox[0]
            except Exception:
                kww = len(kw_disp) * 10
            
            kw_x = cx + (cell_w - kww) // 2
            kw_y = cy + img_h + 8
            draw.text((kw_x, kw_y), kw_disp, fill=cell_color, font=kw_font)
            
            # رقم صغير
            num_str = str(i + 1)
            num_font = _get_font(12, bold=True)
            draw.ellipse([(cx - 5, cy - 5), (cx + 15, cy + 15)], fill=cell_color)
            draw.text((cx + 2, cy - 2), num_str, fill=(255, 255, 255), font=num_font)

    # ── مؤشر التقدم (نقاط) ─────────────────────────────────────────────────
    dot_y = TARGET_H - 30
    dot_r = 5
    dot_gap = 22
    total_w = total_kw * dot_gap
    start_x = (TARGET_W - total_w) // 2
    
    for i in range(total_kw):
        dx = start_x + i * dot_gap
        color = accent if i <= current_kw_idx else (220, 220, 220)
        r = dot_r if i <= current_kw_idx else dot_r - 2
        draw.ellipse([(dx - r, dot_y - r), (dx + r, dot_y + r)], fill=color)

    # علامة مائية
    wm_font = _get_font(11)
    wm_disp = _prepare_text(WATERMARK, is_arabic)
    try:
        bbox = draw.textbbox((0, 0), wm_disp, font=wm_font)
        ww = bbox[2] - bbox[0]
    except Exception:
        ww = len(wm_disp) * 6
    draw.text((TARGET_W - ww - 15, TARGET_H - 18), wm_disp, fill=OSMOSIS_GRAY, font=wm_font)

    img.save(path, "JPEG", quality=92)
    return path


# ─────────────────────────────────────────────────────────────────────────────
# شريحة الملخص النهائي
# ─────────────────────────────────────────────────────────────────────────────

def _draw_final_summary(sections: list, lecture_data: dict, is_arabic: bool) -> str:
    img_fd, img_path = tempfile.mkstemp(prefix="final_summary_", suffix=".jpg")
    os.close(img_fd)

    lecture_type = lecture_data.get("lecture_type", "other")
    accent = TYPE_COLORS.get(lecture_type, OSMOSIS_PINK)
    
    img = PILImage.new("RGB", (TARGET_W, TARGET_H), BOARD_BG)
    draw = ImageDraw.Draw(img)

    draw.rectangle([(0, 0), (TARGET_W, 6)], fill=accent)

    # عنوان
    title_disp = _prepare_text("📋 ملخص المحاضرة", is_arabic)
    title_font = _get_font(30, bold=True, arabic=is_arabic)
    try:
        bbox = draw.textbbox((0, 0), title_disp, font=title_font)
        tw = bbox[2] - bbox[0]
    except Exception:
        tw = len(title_disp) * 17
    tx = (TARGET_W - tw) // 2
    draw.text((tx, 30), title_disp, fill=OSMOSIS_DARK, font=title_font)

    draw.rectangle([(TARGET_W//4, 65), (TARGET_W*3//4, 67)], fill=accent)

    # قائمة الأقسام والكلمات المفتاحية
    y = 90
    colors = [OSMOSIS_PINK, OSMOSIS_BLUE, OSMOSIS_GREEN, OSMOSIS_PURPLE, OSMOSIS_ORANGE]
    
    for i, section in enumerate(sections):
        color = colors[i % len(colors)]
        
        # مربع ملون
        draw.rectangle([(30, y), (48, y + 18)], fill=color)
        
        # عنوان القسم
        sec_title = section.get("title", f"القسم {i+1}")[:35]
        sec_disp = _prepare_text(sec_title, is_arabic)
        sec_font = _get_font(18, bold=True, arabic=is_arabic)
        draw.text((60, y - 2), sec_disp, fill=OSMOSIS_DARK, font=sec_font)
        
        # الكلمات المفتاحية
        keywords = section.get("keywords", [])[:4]
        if keywords:
            kw_text = " • ".join(keywords)
            kw_disp = _prepare_text(kw_text, is_arabic)
            kw_font = _get_font(14, arabic=is_arabic)
            draw.text((75, y + 22), kw_disp, fill=color, font=kw_font)
        
        y += 60

    # ملخص
    summary = lecture_data.get("summary", "")
    if summary:
        summary_disp = _prepare_text(summary[:150], is_arabic)
        summary_font = _get_font(14, arabic=is_arabic)
        
        words = summary_disp.split()
        lines = []
        current = []
        for w in words:
            current.append(w)
            line = ' '.join(current)
            try:
                bbox = draw.textbbox((0, 0), line, font=summary_font)
                if bbox[2] - bbox[0] > TARGET_W - 80:
                    current.pop()
                    lines.append(' '.join(current))
                    current = [w]
            except Exception:
                pass
        if current:
            lines.append(' '.join(current))
        
        for line in lines[:3]:
            try:
                bbox = draw.textbbox((0, 0), line, font=summary_font)
                tw = bbox[2] - bbox[0]
            except Exception:
                tw = len(line) * 8
            x = (TARGET_W - tw) // 2
            draw.text((x, y + 20), line, fill=OSMOSIS_GRAY, font=summary_font)
            y += 22

    # رسالة ختامية
    thanks_disp = _prepare_text("🎓 تم بحمد الله", is_arabic)
    thanks_font = _get_font(24, bold=True, arabic=is_arabic)
    try:
        bbox = draw.textbbox((0, 0), thanks_disp, font=thanks_font)
        tw = bbox[2] - bbox[0]
    except Exception:
        tw = len(thanks_disp) * 14
    tx = (TARGET_W - tw) // 2
    draw.text((tx, TARGET_H - 55), thanks_disp, fill=accent, font=thanks_font)

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
    lecture_type = lecture_data.get("lecture_type", "other")

    # 1. مقدمة (5 ثواني)
    intro_path = _draw_intro_slide(lecture_data, sections, is_arabic)
    tmp_files.append(intro_path)
    segments.append({"img": intro_path, "audio": None, "audio_start": 0.0, "dur": 5.0})
    total_secs += 5.0

    # 2. الأقسام
    for sec_idx, (section, audio_info) in enumerate(zip(sections, audio_results)):
        # عنوان القسم (3 ثواني)
        title_path = _draw_section_title_card(section, sec_idx, n_sections, is_arabic, lecture_type)
        tmp_files.append(title_path)
        segments.append({"img": title_path, "audio": None, "audio_start": 0.0, "dur": 3.0})
        total_secs += 3.0

        keywords = section.get("keywords", ["مفهوم"])
        kw_images = section.get("_keyword_images", [])
        audio_bytes = audio_info.get("audio")
        total_dur = max(float(audio_info.get("duration", 30)), 5.0)
        
        n_kw = len(keywords)
        kw_dur = total_dur / n_kw if n_kw > 0 else total_dur

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
            board_path = _draw_osmosis_board_slide(
                keywords=keywords,
                images=kw_images,
                current_kw_idx=kw_idx,
                total_kw=n_kw,
                section_title=sec_title,
                section_idx=sec_idx,
                is_arabic=is_arabic,
                lecture_type=lecture_type,
            )
            tmp_files.append(board_path)
            
            segments.append({
                "img": board_path,
                "audio": apath,
                "audio_start": kw_idx * kw_dur,
                "dur": kw_dur,
            })
            total_secs += kw_dur

    # 3. ملخص نهائي (6 ثواني)
    final_path = _draw_final_summary(sections, lecture_data, is_arabic)
    tmp_files.append(final_path)
    segments.append({"img": final_path, "audio": None, "audio_start": 0.0, "dur": 6.0})
    total_secs += 6.0

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
