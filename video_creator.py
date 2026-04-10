import asyncio
import io
import os
import subprocess
import tempfile
from PIL import Image as PILImage, ImageDraw, ImageFont

TARGET_W, TARGET_H = 854, 480
WATERMARK = "@zakros_probot"

# ─────────────────────────────────────────────────────────────────────────────
# البحث عن خط عربي متاح
# ─────────────────────────────────────────────────────────────────────────────

def _find_arabic_font():
    paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/app/fonts/Amiri-Bold.ttf",
        "fonts/Amiri-Bold.ttf",
        "/app/fonts/Amiri-Regular.ttf",
        "fonts/Amiri-Regular.ttf",
    ]
    for p in paths:
        if os.path.exists(p):
            return p
    return None

FONT_PATH = _find_arabic_font()
print(f"📝 Using font: {FONT_PATH}")

_ENC_FACTOR = 0.6
_MIN_ENC_SEC = 20.0

# ألوان
COLORS = [
    (231, 76, 126),   # وردي
    (52, 152, 219),   # أزرق
    (46, 204, 113),   # أخضر
    (155, 89, 182),   # بنفسجي
    (230, 126, 34),   # برتقالي
]

def estimate_encoding_seconds(total_video_seconds: float) -> float:
    return max(_MIN_ENC_SEC, total_video_seconds * _ENC_FACTOR)


def _get_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    if FONT_PATH and os.path.exists(FONT_PATH):
        try:
            return ImageFont.truetype(FONT_PATH, size)
        except Exception:
            pass
    try:
        return ImageFont.load_default()
    except Exception:
        return ImageFont.load_default()


def _prepare_arabic_text(text: str) -> str:
    """تجهيز النص العربي للعرض"""
    if not text:
        return ""
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
        reshaped = arabic_reshaper.reshape(text)
        return get_display(reshaped)
    except Exception:
        return text


def _draw_text_with_shadow(draw, x, y, text, font, color, shadow_color=(200, 200, 200)):
    """رسم نص مع ظل"""
    try:
        draw.text((x + 2, y + 2), text, fill=shadow_color, font=font)
    except:
        pass
    draw.text((x, y), text, fill=color, font=font)


def _get_text_width(text: str, font: ImageFont.FreeTypeFont) -> int:
    try:
        bbox = font.getbbox(text)
        return bbox[2] - bbox[0]
    except:
        return len(text) * (font.size // 2)


def _wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list:
    words = text.split()
    lines = []
    current = []
    for w in words:
        current.append(w)
        line = ' '.join(current)
        if _get_text_width(line, font) > max_width:
            current.pop()
            lines.append(' '.join(current))
            current = [w]
    if current:
        lines.append(' '.join(current))
    return lines if lines else [text]


# ─────────────────────────────────────────────────────────────────────────────
# 1. شريحة المقدمة - شعار كبير في إطار
# ─────────────────────────────────────────────────────────────────────────────

def _draw_welcome_slide() -> str:
    img_fd, img_path = tempfile.mkstemp(prefix="welcome_", suffix=".jpg")
    os.close(img_fd)

    img = PILImage.new("RGB", (TARGET_W, TARGET_H), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    # شريط علوي وسفلي
    draw.rectangle([(0, 0), (TARGET_W, 8)], fill=COLORS[0])
    draw.rectangle([(0, TARGET_H-8), (TARGET_W, TARGET_H)], fill=COLORS[0])

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
    logo_text = WATERMARK
    logo_width = _get_text_width(logo_text, font_logo)
    logo_x = (TARGET_W - logo_width) // 2
    logo_y = frame_y + 60
    
    # ظل ثم النص
    draw.text((logo_x + 4, logo_y + 4), logo_text, fill=(200, 200, 200), font=font_logo)
    draw.text((logo_x, logo_y), logo_text, fill=COLORS[0], font=font_logo)

    # "أهلاً ومرحباً بكم"
    welcome_text = _prepare_arabic_text("أهلاً ومرحباً بكم")
    font_welcome = _get_font(36, bold=True)
    welcome_width = _get_text_width(welcome_text, font_welcome)
    welcome_x = (TARGET_W - welcome_width) // 2
    welcome_y = frame_y + frame_h + 40
    
    draw.text((welcome_x + 3, welcome_y + 3), welcome_text, fill=(200, 200, 200), font=font_welcome)
    draw.text((welcome_x, welcome_y), welcome_text, fill=(44, 62, 80), font=font_welcome)

    img.save(img_path, "JPEG", quality=90)
    return img_path


# ─────────────────────────────────────────────────────────────────────────────
# 2. شريحة عنوان المحاضرة
# ─────────────────────────────────────────────────────────────────────────────

def _draw_title_slide(lecture_data: dict) -> str:
    img_fd, img_path = tempfile.mkstemp(prefix="title_", suffix=".jpg")
    os.close(img_fd)

    img = PILImage.new("RGB", (TARGET_W, TARGET_H), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    draw.rectangle([(0, 0), (TARGET_W, 6)], fill=COLORS[1])

    raw_title = lecture_data.get("title", "المحاضرة التعليمية")
    title_text = _prepare_arabic_text(raw_title)
    font_title = _get_font(38, bold=True)
    
    lines = _wrap_text(title_text, font_title, TARGET_W - 80)
    y = TARGET_H//2 - (len(lines) * 50)//2
    
    for line in lines:
        line_width = _get_text_width(line, font_title)
        x = (TARGET_W - line_width) // 2
        draw.text((x + 3, y + 3), line, fill=(200, 200, 200), font=font_title)
        draw.text((x, y), line, fill=(44, 62, 80), font=font_title)
        y += 50

    # حقوق
    font_wm = _get_font(14, bold=True)
    wm_width = _get_text_width(WATERMARK, font_wm)
    draw.text((TARGET_W - wm_width - 25, TARGET_H - 35), WATERMARK, fill=COLORS[1], font=font_wm)

    img.save(img_path, "JPEG", quality=90)
    return img_path


# ─────────────────────────────────────────────────────────────────────────────
# 3. شريحة خريطة الأقسام
# ─────────────────────────────────────────────────────────────────────────────

def _draw_sections_map(sections: list) -> str:
    img_fd, img_path = tempfile.mkstemp(prefix="map_", suffix=".jpg")
    os.close(img_fd)

    img = PILImage.new("RGB", (TARGET_W, TARGET_H), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    draw.rectangle([(0, 0), (TARGET_W, 6)], fill=COLORS[2])

    # عنوان
    map_title = _prepare_arabic_text("📋 خريطة المحاضرة")
    font_title = _get_font(30, bold=True)
    title_width = _get_text_width(map_title, font_title)
    x = (TARGET_W - title_width) // 2
    draw.text((x, 30), map_title, fill=COLORS[2], font=font_title)

    y = 90
    for i, section in enumerate(sections):
        color = COLORS[i % len(COLORS)]
        
        # رقم القسم
        draw.ellipse([(30, y), (52, y + 22)], fill=color)
        num_str = str(i + 1)
        font_num = _get_font(15, bold=True)
        draw.text((41, y + 3), num_str, fill=(255, 255, 255), font=font_num)
        
        # عنوان القسم
        sec_title = section.get("title", f"القسم {i+1}")[:30]
        sec_text = _prepare_arabic_text(sec_title)
        font_sec = _get_font(20, bold=True)
        draw.text((70, y), sec_text, fill=(44, 62, 80), font=font_sec)
        
        # الكلمات المفتاحية
        keywords = section.get("keywords", [])[:3]
        if keywords:
            kw_text = " • ".join(keywords)
            kw_disp = _prepare_arabic_text(kw_text)
            font_kw = _get_font(14)
            draw.text((85, y + 26), kw_disp, fill=color, font=font_kw)
        
        y += 60

    font_wm = _get_font(13, bold=True)
    wm_width = _get_text_width(WATERMARK, font_wm)
    draw.text((TARGET_W - wm_width - 25, TARGET_H - 30), WATERMARK, fill=COLORS[2], font=font_wm)

    img.save(img_path, "JPEG", quality=90)
    return img_path


# ─────────────────────────────────────────────────────────────────────────────
# 4. شريحة عنوان القسم
# ─────────────────────────────────────────────────────────────────────────────

def _draw_section_title_card(section: dict, idx: int, total: int) -> str:
    img_fd, img_path = tempfile.mkstemp(prefix=f"sec_title_{idx}_", suffix=".jpg")
    os.close(img_fd)

    color = COLORS[idx % len(COLORS)]
    img = PILImage.new("RGB", (TARGET_W, TARGET_H), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    draw.rectangle([(0, 0), (TARGET_W, 6)], fill=color)

    # رقم القسم
    cx, cy, cr = TARGET_W // 2, TARGET_H // 2 - 50, 45
    draw.ellipse([cx - cr, cy - cr, cx + cr, cy + cr], fill=color)
    num_str = str(idx + 1)
    font_num = _get_font(40, bold=True)
    num_width = _get_text_width(num_str, font_num)
    draw.text((cx - num_width//2, cy - 22), num_str, fill=(255, 255, 255), font=font_num)

    # عنوان القسم
    raw_title = section.get("title", f"القسم {idx + 1}")
    title_text = _prepare_arabic_text(raw_title)
    font_title = _get_font(32, bold=True)
    title_width = _get_text_width(title_text, font_title)
    x = (TARGET_W - title_width) // 2
    draw.text((x, cy + cr + 35), title_text, fill=(44, 62, 80), font=font_title)

    font_wm = _get_font(13, bold=True)
    wm_width = _get_text_width(WATERMARK, font_wm)
    draw.text((TARGET_W - wm_width - 25, TARGET_H - 30), WATERMARK, fill=color, font=font_wm)

    img.save(img_path, "JPEG", quality=90)
    return img_path


# ─────────────────────────────────────────────────────────────────────────────
# 5. شريحة السبورة المتراكمة
# ─────────────────────────────────────────────────────────────────────────────

def _draw_accumulating_board(
    accumulated_keywords: list[str],
    current_kw_idx: int,
    total_kw: int,
    section_title: str,
    section_idx: int,
) -> str:
    """
    سبورة تتراكم عليها الكلمات المفتاحية مع صور ملونة تحمل نفس الكلمة
    الصورة دائماً ملائمة لأنها تحمل الكلمة نفسها
    """
    fd, path = tempfile.mkstemp(prefix="board_", suffix=".jpg")
    os.close(fd)

    color = COLORS[section_idx % len(COLORS)]
    img = PILImage.new("RGB", (TARGET_W, TARGET_H), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    draw.rectangle([(0, 0), (TARGET_W, 6)], fill=color)

    # عنوان القسم
    header_text = _prepare_arabic_text(section_title[:40])
    font_header = _get_font(18, bold=True)
    header_width = _get_text_width(header_text, font_header)
    hx = (TARGET_W - header_width) // 2
    draw.text((hx, 15), header_text, fill=(44, 62, 80), font=font_header)
    draw.rectangle([(hx, 38), (hx + header_width, 40)], fill=color)

    n_items = len(accumulated_keywords)
    
    if n_items == 1:
        # عنصر واحد: صورة كبيرة في المنتصف مع الكلمة
        kw = accumulated_keywords[0]
        
        # صورة ملونة تحمل الكلمة
        img_bytes = _make_keyword_image(kw, color)
        try:
            pil_img = PILImage.open(io.BytesIO(img_bytes)).convert("RGB")
            iw, ih = pil_img.size
            max_w, max_h = 500, 250
            scale = min(max_w / iw, max_h / ih)
            nw, nh = int(iw * scale), int(ih * scale)
            pil_img = pil_img.resize((nw, nh), PILImage.LANCZOS)
            
            px = (TARGET_W - nw) // 2
            py = 80
            
            draw.rounded_rectangle(
                [(px - 5, py - 5), (px + nw + 5, py + nh + 5)],
                radius=10, outline=color, width=4
            )
            img.paste(pil_img, (px, py))
        except:
            pass
    else:
        # عناصر متعددة: شبكة
        cols = 2
        rows = (n_items + 1) // 2
        cell_w = (TARGET_W - 100) // cols
        cell_h = 160
        
        for i in range(n_items):
            col = i % cols
            row = i // rows
            
            cx = 50 + col * (cell_w + 20)
            cy = 70 + row * (cell_h + 20)
            
            kw = accumulated_keywords[i]
            cell_color = COLORS[i % len(COLORS)]
            
            # صورة ملونة تحمل الكلمة
            img_bytes = _make_keyword_image(kw, cell_color)
            try:
                pil_img = PILImage.open(io.BytesIO(img_bytes)).convert("RGB")
                iw, ih = pil_img.size
                max_w, max_h = cell_w - 10, cell_h - 40
                scale = min(max_w / iw, max_h / ih)
                nw, nh = int(iw * scale), int(ih * scale)
                pil_img = pil_img.resize((nw, nh), PILImage.LANCZOS)
                
                px = cx + (cell_w - nw) // 2
                py = cy
                
                draw.rounded_rectangle(
                    [(px - 4, py - 4), (px + nw + 4, py + nh + 4)],
                    radius=8, outline=cell_color, width=3
                )
                img.paste(pil_img, (px, py))
            except:
                pass
            
            # رقم
            num_str = str(i + 1)
            font_num = _get_font(12, bold=True)
            draw.ellipse([(cx - 5, cy - 5), (cx + 17, cy + 17)], fill=cell_color)
            draw.text((cx + 3, cy - 2), num_str, fill=(255, 255, 255), font=font_num)

    # مؤشر التقدم
    dot_y = TARGET_H - 30
    dot_r = 6
    dot_gap = 25
    total_w = total_kw * dot_gap
    start_x = (TARGET_W - total_w) // 2
    
    for i in range(total_kw):
        dx = start_x + i * dot_gap
        dot_color = color if i <= current_kw_idx else (220, 220, 220)
        r = dot_r if i <= current_kw_idx else dot_r - 2
        draw.ellipse([(dx - r, dot_y - r), (dx + r, dot_y + r)], fill=dot_color)

    # حقوق
    font_wm = _get_font(12, bold=True)
    wm_width = _get_text_width(WATERMARK, font_wm)
    draw.text((TARGET_W - wm_width - 20, TARGET_H - 25), WATERMARK, fill=color, font=font_wm)

    img.save(path, "JPEG", quality=92)
    return path


def _make_keyword_image(keyword: str, color: tuple) -> bytes:
    """إنشاء صورة ملونة تحمل الكلمة المفتاحية - مضمونة الملاءمة"""
    W, H = 400, 300
    
    img = PILImage.new("RGB", (W, H), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    
    # خلفية متدرجة خفيفة
    for y in range(H):
        t = y / H
        r = int(255 * (1 - t) + color[0] * t * 0.15)
        g = int(255 * (1 - t) + color[1] * t * 0.15)
        b = int(255 * (1 - t) + color[2] * t * 0.15)
        draw.line([(0, y), (W, y)], fill=(r, g, b))
    
    # إطار ملون
    draw.rounded_rectangle([(8, 8), (W-8, H-8)], radius=12, outline=color, width=5)
    
    # دائرة زخرفية
    draw.ellipse([(W//2-55, H//2-55), (W//2+55, H//2+55)], fill=(*color, 25))
    
    # الكلمة المفتاحية بخط كبير
    keyword_disp = _prepare_arabic_text(keyword[:20])
    font_kw = _get_font(32, bold=True)
    
    # تقسيم الكلمة إذا كانت طويلة
    lines = _wrap_text(keyword_disp, font_kw, W - 40)
    
    y = H//2 - (len(lines) * 35)//2
    for line in lines:
        line_width = _get_text_width(line, font_kw)
        x = (W - line_width) // 2
        draw.text((x+2, y+2), line, fill=(200, 200, 200), font=font_kw)
        draw.text((x, y), line, fill=color, font=font_kw)
        y += 40
    
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=90)
    return buf.getvalue()


# ─────────────────────────────────────────────────────────────────────────────
# 6. شريحة الخاتمة - الملخص النهائي
# ─────────────────────────────────────────────────────────────────────────────

def _draw_final_summary(sections: list) -> str:
    img_fd, img_path = tempfile.mkstemp(prefix="summary_", suffix=".jpg")
    os.close(img_fd)

    img = PILImage.new("RGB", (TARGET_W, TARGET_H), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    draw.rectangle([(0, 0), (TARGET_W, 8)], fill=COLORS[0])
    draw.rectangle([(0, TARGET_H-8), (TARGET_W, TARGET_H)], fill=COLORS[0])

    title_text = _prepare_arabic_text("📋 ملخص المحاضرة")
    font_title = _get_font(30, bold=True)
    title_width = _get_text_width(title_text, font_title)
    tx = (TARGET_W - title_width) // 2
    draw.text((tx, 35), title_text, fill=(44, 62, 80), font=font_title)

    y = 90
    for i, section in enumerate(sections):
        color = COLORS[i % len(COLORS)]
        keywords = section.get("keywords", [])
        kw_text = " • ".join(keywords[:4])
        kw_disp = _prepare_arabic_text(kw_text)
        font_kw = _get_font(16, bold=True)
        
        kw_width = _get_text_width(kw_disp, font_kw)
        x = (TARGET_W - kw_width) // 2
        
        # خلفية للكلمات
        draw.rounded_rectangle(
            [(x - 15, y - 8), (x + kw_width + 15, y + 28)],
            radius=8, fill=(*color, 20), outline=color, width=2
        )
        draw.text((x, y), kw_disp, fill=color, font=font_kw)
        y += 50

    thanks_text = _prepare_arabic_text("🙏 شكراً لحسن استماعكم")
    font_thanks = _get_font(26, bold=True)
    thanks_width = _get_text_width(thanks_text, font_thanks)
    tx = (TARGET_W - thanks_width) // 2
    draw.text((tx + 3, TARGET_H - 65), thanks_text, fill=(200, 200, 200), font=font_thanks)
    draw.text((tx, TARGET_H - 68), thanks_text, fill=COLORS[0], font=font_thanks)

    font_wm = _get_font(15, bold=True)
    wm_width = _get_text_width(WATERMARK, font_wm)
    draw.text((TARGET_W - wm_width - 30, TARGET_H - 40), WATERMARK, fill=COLORS[0], font=font_wm)

    img.save(img_path, "JPEG", quality=90)
    return img_path


# ─────────────────────────────────────────────────────────────────────────────
# FFmpeg
# ─────────────────────────────────────────────────────────────────────────────

def _ffmpeg_segment(img_path: str, duration: float, audio_path: str | None,
                    audio_start: float, out_path: str) -> None:
    dur_str = f"{duration:.3f}"
    
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
        "-pix_fmt", "yuv420p", "-r", "15", "-vf", vf,
        "-map", "0:v", "-map", "1:a",
        "-c:a", "aac", "-b:a", "96k", "-ar", "44100", "-ac", "2",
        "-t", dur_str, out_path,
    ]
    subprocess.run(cmd, capture_output=True)


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
        subprocess.run(cmd, capture_output=True)
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
) -> tuple[list[dict], list[str], float]:
    segments: list[dict] = []
    tmp_files: list[str] = []
    total_secs = 0.0
    n_sections = len(sections)

    # 1. المقدمة - شعار كبير
    welcome_path = _draw_welcome_slide()
    tmp_files.append(welcome_path)
    segments.append({"img": welcome_path, "audio": None, "audio_start": 0.0, "dur": 3.5})
    total_secs += 3.5

    # 2. عنوان المحاضرة
    title_path = _draw_title_slide(lecture_data)
    tmp_files.append(title_path)
    segments.append({"img": title_path, "audio": None, "audio_start": 0.0, "dur": 4.0})
    total_secs += 4.0

    # 3. خريطة الأقسام
    map_path = _draw_sections_map(sections)
    tmp_files.append(map_path)
    segments.append({"img": map_path, "audio": None, "audio_start": 0.0, "dur": 5.0})
    total_secs += 5.0

    # 4. الأقسام
    for sec_idx, (section, audio_info) in enumerate(zip(sections, audio_results)):
        # عنوان القسم
        sec_title_path = _draw_section_title_card(section, sec_idx, n_sections)
        tmp_files.append(sec_title_path)
        segments.append({"img": sec_title_path, "audio": None, "audio_start": 0.0, "dur": 3.0})
        total_secs += 3.0

        keywords = section.get("keywords", ["مفهوم"])
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
        
        # تراكم الكلمات
        accum_kw = []
        
        for kw_idx in range(n_kw):
            accum_kw.append(keywords[kw_idx])
            
            board_path = _draw_accumulating_board(
                accumulated_keywords=accum_kw.copy(),
                current_kw_idx=kw_idx,
                total_kw=n_kw,
                section_title=sec_title,
                section_idx=sec_idx,
            )
            tmp_files.append(board_path)
            
            segments.append({
                "img": board_path,
                "audio": apath,
                "audio_start": kw_idx * kw_dur,
                "dur": kw_dur,
            })
            total_secs += kw_dur

    # 5. الخاتمة
    final_path = _draw_final_summary(sections)
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
            _ffmpeg_segment(seg["img"], seg["dur"], seg["audio"], seg["audio_start"], seg_out)
        _ffmpeg_concat(seg_paths, output_path)
    finally:
        for p in seg_paths:
            try:
                os.remove(p)
            except Exception:
                pass


async def create_video_from_sections(
    sections: list,
    audio_results: list,
    lecture_data: dict,
    output_path: str,
    dialect: str = "msa",
    progress_cb=None,
) -> float:
    loop = asyncio.get_event_loop()

    # التأكد من وجود كلمات مفتاحية
    for section in sections:
        if "keywords" not in section or not section["keywords"]:
            section["keywords"] = ["مفهوم", "تعريف", "شرح", "تحليل"]

    segments, tmp_files, total_video_secs = await loop.run_in_executor(
        None, _build_segment_list, sections, audio_results, lecture_data
    )

    if not segments:
        raise RuntimeError("No valid segments")

    encode_task = loop.run_in_executor(None, _encode_all_sync, segments, output_path)

    start = loop.time()
    try:
        while not encode_task.done():
            await asyncio.sleep(3)
            elapsed = loop.time() - start
            if progress_cb:
                try:
                    await progress_cb(elapsed, total_video_secs * 0.6)
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
