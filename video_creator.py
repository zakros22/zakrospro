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
BOARD_SHADOW = (200, 200, 200)      # ظل خفيف

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


def _draw_osmosis_arrow(draw, x1, y1, x2, y2, color=OSMOSIS_PINK, width=3):
    """رسم سهم بأسلوب Osmosis"""
    import math
    draw.line([(x1, y1), (x2, y2)], fill=color, width=width)
    
    # رأس السهم
    angle = math.atan2(y2 - y1, x2 - x1)
    arrow_len = 12
    arrow_angle = 0.4
    
    x3 = x2 - arrow_len * math.cos(angle - arrow_angle)
    y3 = y2 - arrow_len * math.sin(angle - arrow_angle)
    x4 = x2 - arrow_len * math.cos(angle + arrow_angle)
    y4 = y2 - arrow_len * math.sin(angle + arrow_angle)
    
    draw.polygon([(x2, y2), (x3, y3), (x4, y4)], fill=color)


def _draw_osmosis_bracket(draw, x, y, width, height, color=OSMOSIS_PINK, width_line=3):
    """رسم قوس توضيحي بأسلوب Osmosis"""
    bracket_len = 15
    # خط عمودي يسار
    draw.line([(x, y), (x, y + height)], fill=color, width=width_line)
    # خط أفقي علوي
    draw.line([(x, y), (x + bracket_len, y)], fill=color, width=width_line)
    # خط أفقي سفلي
    draw.line([(x, y + height), (x + bracket_len, y + height)], fill=color, width=width_line)


# ─────────────────────────────────────────────────────────────────────────────
# شريحة المقدمة - Osmosis Style
# ─────────────────────────────────────────────────────────────────────────────

def _draw_intro_slide(lecture_data: dict, sections: list, is_arabic: bool) -> str:
    img_fd, img_path = tempfile.mkstemp(prefix="intro_", suffix=".jpg")
    os.close(img_fd)

    img = PILImage.new("RGB", (TARGET_W, TARGET_H), BOARD_BG)
    draw = ImageDraw.Draw(img)

    # شريط علوي وردي
    draw.rectangle([(0, 0), (TARGET_W, 5)], fill=OSMOSIS_PINK)

    # عنوان المحاضرة
    raw_title = lecture_data.get("title", "المحاضرة التعليمية")
    title_txt = _prepare_text(raw_title, is_arabic)
    title_font = _get_font(32, bold=True, arabic=is_arabic)
    
    # تقسيم العنوان لسطور
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
    
    y = TARGET_H // 2 - (len(lines) * 45) // 2
    for line in lines:
        try:
            bbox = draw.textbbox((0, 0), line, font=title_font)
            tw = bbox[2] - bbox[0]
        except Exception:
            tw = len(line) * 18
        x = (TARGET_W - tw) // 2
        draw.text((x + 2, y + 2), line, fill=(220, 220, 220), font=title_font)
        draw.text((x, y), line, fill=OSMOSIS_DARK, font=title_font)
        y += 45

    # خط تحت العنوان
    draw.rectangle([(TARGET_W//4, y + 10), (TARGET_W*3//4, y + 12)], fill=OSMOSIS_PINK)

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
    draw.text((ix, y + 35), info_txt, fill=OSMOSIS_GRAY, font=info_font)

    # علامة مائية
    wm_font = _get_font(12)
    try:
        bbox = draw.textbbox((0, 0), WATERMARK, font=wm_font)
        ww = bbox[2] - bbox[0]
    except Exception:
        ww = len(WATERMARK) * 7
    draw.text(((TARGET_W - ww) // 2, TARGET_H - 25), WATERMARK, fill=OSMOSIS_GRAY, font=wm_font)

    img.save(img_path, "JPEG", quality=90)
    return img_path


# ─────────────────────────────────────────────────────────────────────────────
# شريحة عنوان القسم
# ─────────────────────────────────────────────────────────────────────────────

def _draw_section_title_card(section: dict, idx: int, total: int, is_arabic: bool) -> str:
    img_fd, img_path = tempfile.mkstemp(prefix=f"sec_title_{idx}_", suffix=".jpg")
    os.close(img_fd)

    colors = [OSMOSIS_PINK, OSMOSIS_BLUE, OSMOSIS_GREEN, OSMOSIS_PURPLE, OSMOSIS_ORANGE]
    accent = colors[idx % len(colors)]
    
    img = PILImage.new("RGB", (TARGET_W, TARGET_H), BOARD_BG)
    draw = ImageDraw.Draw(img)

    # شريط علوي
    draw.rectangle([(0, 0), (TARGET_W, 5)], fill=accent)

    # دائرة مرقمة
    cx, cy, cr = TARGET_W // 2, TARGET_H // 2 - 40, 40
    draw.ellipse([cx - cr, cy - cr, cx + cr, cy + cr], fill=accent)
    num_str = str(idx + 1)
    num_font = _get_font(36, bold=True)
    try:
        bbox = draw.textbbox((0, 0), num_str, font=num_font)
        nw, nh = bbox[2] - bbox[0], bbox[3] - bbox[1]
    except Exception:
        nw, nh = 20, 36
    draw.text((cx - nw // 2, cy - nh // 2), num_str, fill=(255, 255, 255), font=num_font)

    # عنوان القسم
    raw_title = section.get("title", f"القسم {idx + 1}")
    title_txt = _prepare_text(raw_title, is_arabic)
    title_font = _get_font(28, bold=True, arabic=is_arabic)
    
    lines = []
    words = title_txt.split()
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
    
    y = cy + cr + 25
    for line in lines:
        try:
            bbox = draw.textbbox((0, 0), line, font=title_font)
            tw = bbox[2] - bbox[0]
        except Exception:
            tw = len(line) * 16
        x = (TARGET_W - tw) // 2
        draw.text((x, y), line, fill=OSMOSIS_DARK, font=title_font)
        y += 40

    img.save(img_path, "JPEG", quality=90)
    return img_path


# ─────────────────────────────────────────────────────────────────────────────
# شريحة السبورة البيضاء - Osmosis Style (العرض التراكمي)
# ─────────────────────────────────────────────────────────────────────────────

def _draw_osmosis_board_slide(
    accumulated_items: list[dict],  # [{"type": "text", "content": "...", "x": ?, "y": ?}, {"type": "image", ...}]
    current_kw_idx: int,
    total_kw: int,
    section_title: str,
    section_idx: int,
    is_arabic: bool,
) -> str:
    """
    سبورة Osmosis تتراكم عليها العناصر تدريجياً
    """
    fd, path = tempfile.mkstemp(prefix="osmosis_", suffix=".jpg")
    os.close(fd)

    colors = [OSMOSIS_PINK, OSMOSIS_BLUE, OSMOSIS_GREEN, OSMOSIS_PURPLE, OSMOSIS_ORANGE]
    accent = colors[section_idx % len(colors)]
    
    img = PILImage.new("RGB", (TARGET_W, TARGET_H), BOARD_BG)
    draw = ImageDraw.Draw(img)

    # ظل خفيف للإطار
    draw.rectangle([(5, 5), (TARGET_W-5, TARGET_H-5)], outline=(240, 240, 240), width=2)
    
    # شريط علوي ملون
    draw.rectangle([(0, 0), (TARGET_W, 5)], fill=accent)

    # عنوان القسم في الأعلى
    header_txt = _prepare_text(section_title[:35], is_arabic)
    header_font = _get_font(18, bold=True, arabic=is_arabic)
    try:
        bbox = draw.textbbox((0, 0), header_txt, font=header_font)
        hw = bbox[2] - bbox[0]
    except Exception:
        hw = len(header_txt) * 10
    
    hx = (TARGET_W - hw) // 2
    draw.text((hx, 15), header_txt, fill=OSMOSIS_DARK, font=header_font)
    
    # خط تحت العنوان
    draw.rectangle([(hx, 38), (hx + hw, 40)], fill=accent)

    # ── عرض العناصر المتراكمة ─────────────────────────────────────────────
    content_y = 55
    
    for item in accumulated_items:
        if item["type"] == "text":
            text = item["content"]
            font_size = item.get("size", 18)
            bold = item.get("bold", False)
            color_name = item.get("color", "dark")
            
            color_map = {
                "pink": OSMOSIS_PINK,
                "blue": OSMOSIS_BLUE,
                "green": OSMOSIS_GREEN,
                "red": OSMOSIS_RED,
                "purple": OSMOSIS_PURPLE,
                "orange": OSMOSIS_ORANGE,
                "dark": OSMOSIS_DARK,
                "gray": OSMOSIS_GRAY
            }
            color = color_map.get(color_name, OSMOSIS_DARK)
            
            font = _get_font(font_size, bold=bold, arabic=is_arabic)
            text_disp = _prepare_text(text, is_arabic)
            
            x = item.get("x", 30)
            y = item.get("y", content_y)
            
            # رسم نقطة إذا كانت قائمة
            if item.get("bullet", False):
                draw.ellipse([(x - 8, y + 8), (x - 2, y + 14)], fill=color)
                x += 5
            
            draw.text((x, y), text_disp, fill=color, font=font)
            
            # رسم سهم إذا وجد
            if item.get("arrow_to"):
                ax, ay = item["arrow_to"]
                _draw_osmosis_arrow(draw, x + item.get("arrow_from_offset", 50), 
                                   y + 12, ax, ay, color=color)
            
            # رسم قوس توضيحي
            if item.get("bracket"):
                bx, by, bw, bh = item["bracket"]
                _draw_osmosis_bracket(draw, bx, by, bw, bh, color=color)
        
        elif item["type"] == "image":
            img_bytes = item["content"]
            x = item.get("x", 30)
            y = item.get("y", content_y)
            max_w = item.get("max_w", 200)
            max_h = item.get("max_h", 150)
            
            if img_bytes:
                try:
                    pil_img = PILImage.open(io.BytesIO(img_bytes)).convert("RGB")
                    iw, ih = pil_img.size
                    scale = min(max_w / iw, max_h / ih)
                    nw, nh = int(iw * scale), int(ih * scale)
                    pil_img = pil_img.resize((nw, nh), PILImage.LANCZOS)
                    
                    # إطار للصورة
                    draw.rectangle(
                        [(x - 3, y - 3), (x + nw + 3, y + nh + 3)],
                        outline=accent, width=2
                    )
                    img.paste(pil_img, (x, y))
                except Exception:
                    pass
        
        elif item["type"] == "arrow":
            x1, y1 = item["start"]
            x2, y2 = item["end"]
            color_name = item.get("color", "pink")
            color_map = {
                "pink": OSMOSIS_PINK,
                "blue": OSMOSIS_BLUE,
                "green": OSMOSIS_GREEN,
                "red": OSMOSIS_RED
            }
            color = color_map.get(color_name, OSMOSIS_PINK)
            _draw_osmosis_arrow(draw, x1, y1, x2, y2, color=color)
        
        elif item["type"] == "bracket":
            x, y, w, h = item["rect"]
            color_name = item.get("color", "pink")
            color_map = {"pink": OSMOSIS_PINK, "blue": OSMOSIS_BLUE, "green": OSMOSIS_GREEN}
            color = color_map.get(color_name, OSMOSIS_PINK)
            _draw_osmosis_bracket(draw, x, y, w, h, color=color)
        
        elif item["type"] == "box":
            x, y, w, h = item["rect"]
            color_name = item.get("color", "pink")
            color_map = {"pink": OSMOSIS_PINK, "blue": OSMOSIS_BLUE, "green": OSMOSIS_GREEN}
            color = color_map.get(color_name, OSMOSIS_PINK)
            fill = item.get("fill", False)
            if fill:
                draw.rectangle([(x, y), (x + w, y + h)], fill=(*color, 30), outline=color, width=2)
            else:
                draw.rectangle([(x, y), (x + w, y + h)], outline=color, width=2)

    # ── مؤشر التقدم (نقاط) ─────────────────────────────────────────────────
    dot_y = TARGET_H - 25
    dot_r = 5
    dot_gap = 20
    total_w = total_kw * dot_gap
    start_x = (TARGET_W - total_w) // 2
    
    for i in range(total_kw):
        dx = start_x + i * dot_gap
        color = accent if i <= current_kw_idx else (220, 220, 220)
        r = dot_r if i <= current_kw_idx else dot_r - 2
        draw.ellipse([(dx - r, dot_y - r), (dx + r, dot_y + r)], fill=color)

    # علامة مائية
    wm_font = _get_font(10)
    try:
        bbox = draw.textbbox((0, 0), WATERMARK, font=wm_font)
        ww = bbox[2] - bbox[0]
    except Exception:
        ww = len(WATERMARK) * 6
    draw.text((TARGET_W - ww - 15, TARGET_H - 15), WATERMARK, fill=OSMOSIS_GRAY, font=wm_font)

    img.save(path, "JPEG", quality=92)
    return path


# ─────────────────────────────────────────────────────────────────────────────
# بناء عناصر Osmosis من الكلمات المفتاحية
# ─────────────────────────────────────────────────────────────────────────────

def _build_osmosis_items(
    keywords: list[str],
    images: list[bytes | None],
    current_idx: int,
    is_arabic: bool,
) -> list[dict]:
    """
    بناء عناصر السبورة بأسلوب Osmosis التراكمي
    """
    items = []
    
    # تخطيط العناصر
    layout = {
        0: [  # أول عنصر: عنوان رئيسي في المنتصف
            {"type": "text", "content": keywords[0] if keywords else "المفهوم", 
             "x": TARGET_W//2 - 50, "y": 80, "size": 28, "bold": True, "color": "pink"}
        ],
        1: [  # ثاني عنصر: صورة مع شرح
            {"type": "image", "content": images[1] if len(images) > 1 else None,
             "x": 50, "y": 140, "max_w": 200, "max_h": 150},
            {"type": "text", "content": keywords[1] if len(keywords) > 1 else "", 
             "x": 280, "y": 170, "size": 20, "bold": True, "color": "blue"},
            {"type": "arrow", "start": (250, 200), "end": (280, 200), "color": "blue"}
        ],
        2: [  # ثالث عنصر: نص مع سهم للأسفل
            {"type": "text", "content": keywords[2] if len(keywords) > 2 else "", 
             "x": 50, "y": 320, "size": 20, "bold": True, "color": "green"},
            {"type": "arrow", "start": (200, 300), "end": (200, 320), "color": "green"}
        ],
        3: [  # رابع عنصر: صورة ثانية
            {"type": "image", "content": images[3] if len(images) > 3 else None,
             "x": 500, "y": 300, "max_w": 200, "max_h": 150},
            {"type": "text", "content": keywords[3] if len(keywords) > 3 else "", 
             "x": 500, "y": 460, "size": 18, "color": "purple"}
        ]
    }
    
    # إضافة العناصر حسب التراكم
    for i in range(current_idx + 1):
        if i in layout:
            items.extend(layout[i])
    
    return items


# ─────────────────────────────────────────────────────────────────────────────
# شريحة الملخص النهائي
# ─────────────────────────────────────────────────────────────────────────────

def _draw_final_summary(sections: list, lecture_data: dict, is_arabic: bool) -> str:
    img_fd, img_path = tempfile.mkstemp(prefix="final_summary_", suffix=".jpg")
    os.close(img_fd)

    img = PILImage.new("RGB", (TARGET_W, TARGET_H), BOARD_BG)
    draw = ImageDraw.Draw(img)

    draw.rectangle([(0, 0), (TARGET_W, 5)], fill=OSMOSIS_PINK)

    # عنوان
    title_txt = _prepare_text("📋 ملخص المحاضرة", is_arabic)
    title_font = _get_font(28, bold=True, arabic=is_arabic)
    try:
        bbox = draw.textbbox((0, 0), title_txt, font=title_font)
        tw = bbox[2] - bbox[0]
    except Exception:
        tw = len(title_txt) * 16
    tx = (TARGET_W - tw) // 2
    draw.text((tx, 30), title_txt, fill=OSMOSIS_DARK, font=title_font)

    draw.rectangle([(TARGET_W//4, 62), (TARGET_W*3//4, 64)], fill=OSMOSIS_PINK)

    # قائمة الأقسام
    y = 90
    colors = [OSMOSIS_PINK, OSMOSIS_BLUE, OSMOSIS_GREEN, OSMOSIS_PURPLE, OSMOSIS_ORANGE]
    
    for i, section in enumerate(sections):
        color = colors[i % len(colors)]
        
        # مربع ملون
        draw.rectangle([(30, y), (45, y + 15)], fill=color)
        
        sec_title = section.get("title", f"القسم {i+1}")[:40]
        sec_txt = _prepare_text(f"{sec_title}", is_arabic)
        sec_font = _get_font(16, arabic=is_arabic)
        draw.text((55, y - 2), sec_txt, fill=OSMOSIS_DARK, font=sec_font)
        
        # الكلمات المفتاحية
        keywords = section.get("keywords", [])[:3]
        if keywords:
            kw_txt = " • ".join(keywords)
            kw_disp = _prepare_text(kw_txt, is_arabic)
            kw_font = _get_font(12, arabic=is_arabic)
            draw.text((70, y + 18), kw_disp, fill=OSMOSIS_GRAY, font=kw_font)
        
        y += 50

    # رسالة ختامية
    thanks_txt = _prepare_text("🎓 تم بحمد الله", is_arabic)
    thanks_font = _get_font(22, bold=True, arabic=is_arabic)
    try:
        bbox = draw.textbbox((0, 0), thanks_txt, font=thanks_font)
        tw = bbox[2] - bbox[0]
    except Exception:
        tw = len(thanks_txt) * 13
    tx = (TARGET_W - tw) // 2
    draw.text((tx, TARGET_H - 50), thanks_txt, fill=OSMOSIS_PINK, font=thanks_font)

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

    # 1. مقدمة
    intro_path = _draw_intro_slide(lecture_data, sections, is_arabic)
    tmp_files.append(intro_path)
    segments.append({"img": intro_path, "audio": None, "audio_start": 0.0, "dur": 5.0})
    total_secs += 5.0

    # 2. الأقسام
    for sec_idx, (section, audio_info) in enumerate(zip(sections, audio_results)):
        # عنوان القسم
        title_path = _draw_section_title_card(section, sec_idx, n_sections, is_arabic)
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
        
        for kw_idx in range(n_kw):
            # بناء العناصر المتراكمة
            items = _build_osmosis_items(
                keywords=keywords,
                images=kw_images,
                current_idx=kw_idx,
                is_arabic=is_arabic
            )
            
            board_path = _draw_osmosis_board_slide(
                accumulated_items=items,
                current_kw_idx=kw_idx,
                total_kw=n_kw,
                section_title=sec_title,
                section_idx=sec_idx,
                is_arabic=is_arabic,
            )
            tmp_files.append(board_path)
            
            segments.append({
                "img": board_path,
                "audio": apath,
                "audio_start": kw_idx * kw_dur,
                "dur": kw_dur,
            })
            total_secs += kw_dur

    # 3. ملخص نهائي
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
