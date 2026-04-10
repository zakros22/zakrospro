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


def _wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list:
    words = text.split()
    lines = []
    current = []
    for w in words:
        current.append(w)
        line = ' '.join(current)
        try:
            bbox = font.getbbox(line)
            if bbox[2] - bbox[0] > max_width:
                current.pop()
                lines.append(' '.join(current))
                current = [w]
        except Exception:
            pass
    if current:
        lines.append(' '.join(current))
    return lines if lines else [text]


# ─────────────────────────────────────────────────────────────────────────────
# 1. شريحة المقدمة - حقوق البوت + أهلاً وسهلاً
# ─────────────────────────────────────────────────────────────────────────────

def _draw_welcome_slide(is_arabic: bool) -> str:
    img_fd, img_path = tempfile.mkstemp(prefix="welcome_", suffix=".jpg")
    os.close(img_fd)

    img = PILImage.new("RGB", (TARGET_W, TARGET_H), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    draw.rectangle([(0, 0), (TARGET_W, 6)], fill=COLORS[0])

    # حقوق البوت
    wm_font = _get_font(24, bold=True)
    try:
        bbox = draw.textbbox((0, 0), WATERMARK, font=wm_font)
        ww = bbox[2] - bbox[0]
    except Exception:
        ww = len(WATERMARK) * 14
    x = (TARGET_W - ww) // 2
    draw.text((x, TARGET_H//2 - 60), WATERMARK, fill=COLORS[0], font=wm_font)

    # أهلاً ومرحباً بكم
    welcome_txt = _prepare_text("أهلاً ومرحباً بكم", is_arabic)
    welcome_font = _get_font(32, bold=True, arabic=is_arabic)
    try:
        bbox = draw.textbbox((0, 0), welcome_txt, font=welcome_font)
        ww = bbox[2] - bbox[0]
    except Exception:
        ww = len(welcome_txt) * 18
    x = (TARGET_W - ww) // 2
    draw.text((x + 2, TARGET_H//2 + 2), welcome_txt, fill=(220, 220, 220), font=welcome_font)
    draw.text((x, TARGET_H//2), welcome_txt, fill=(44, 62, 80), font=welcome_font)

    img.save(img_path, "JPEG", quality=90)
    return img_path


# ─────────────────────────────────────────────────────────────────────────────
# 2. شريحة عنوان المحاضرة
# ─────────────────────────────────────────────────────────────────────────────

def _draw_title_slide(lecture_data: dict, is_arabic: bool) -> str:
    img_fd, img_path = tempfile.mkstemp(prefix="title_", suffix=".jpg")
    os.close(img_fd)

    img = PILImage.new("RGB", (TARGET_W, TARGET_H), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    draw.rectangle([(0, 0), (TARGET_W, 6)], fill=COLORS[1])

    raw_title = lecture_data.get("title", "المحاضرة التعليمية")
    title_txt = _prepare_text(raw_title, is_arabic)
    title_font = _get_font(36, bold=True, arabic=is_arabic)
    
    lines = _wrap_text(title_txt, title_font, TARGET_W - 80)
    y = TARGET_H//2 - (len(lines) * 45)//2
    
    for line in lines:
        try:
            bbox = draw.textbbox((0, 0), line, font=title_font)
            tw = bbox[2] - bbox[0]
        except Exception:
            tw = len(line) * 20
        x = (TARGET_W - tw) // 2
        draw.text((x + 2, y + 2), line, fill=(220, 220, 220), font=title_font)
        draw.text((x, y), line, fill=(44, 62, 80), font=title_font)
        y += 45

    # حقوق
    wm_font = _get_font(12)
    try:
        bbox = draw.textbbox((0, 0), WATERMARK, font=wm_font)
        ww = bbox[2] - bbox[0]
    except Exception:
        ww = len(WATERMARK) * 7
    draw.text((TARGET_W - ww - 20, TARGET_H - 25), WATERMARK, fill=COLORS[1], font=wm_font)

    img.save(img_path, "JPEG", quality=90)
    return img_path


# ─────────────────────────────────────────────────────────────────────────────
# 3. شريحة خريطة الأقسام
# ─────────────────────────────────────────────────────────────────────────────

def _draw_sections_map(sections: list, is_arabic: bool) -> str:
    img_fd, img_path = tempfile.mkstemp(prefix="map_", suffix=".jpg")
    os.close(img_fd)

    img = PILImage.new("RGB", (TARGET_W, TARGET_H), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    draw.rectangle([(0, 0), (TARGET_W, 6)], fill=COLORS[2])

    # عنوان
    map_title = _prepare_text("📋 خريطة المحاضرة", is_arabic)
    title_font = _get_font(28, bold=True, arabic=is_arabic)
    try:
        bbox = draw.textbbox((0, 0), map_title, font=title_font)
        tw = bbox[2] - bbox[0]
    except Exception:
        tw = len(map_title) * 16
    x = (TARGET_W - tw) // 2
    draw.text((x, 30), map_title, fill=COLORS[2], font=title_font)

    # قائمة الأقسام
    y = 90
    for i, section in enumerate(sections):
        color = COLORS[i % len(COLORS)]
        
        # رقم القسم
        draw.ellipse([(30, y), (50, y + 20)], fill=color)
        num_str = str(i + 1)
        num_font = _get_font(14, bold=True)
        draw.text((40, y + 3), num_str, fill=(255, 255, 255), font=num_font)
        
        # عنوان القسم
        sec_title = section.get("title", f"القسم {i+1}")[:30]
        sec_disp = _prepare_text(sec_title, is_arabic)
        sec_font = _get_font(18, arabic=is_arabic)
        draw.text((65, y), sec_disp, fill=(44, 62, 80), font=sec_font)
        
        # الكلمات المفتاحية
        keywords = section.get("keywords", [])[:3]
        if keywords:
            kw_text = " • ".join(keywords)
            kw_disp = _prepare_text(kw_text, is_arabic)
            kw_font = _get_font(13, arabic=is_arabic)
            draw.text((80, y + 22), kw_disp, fill=color, font=kw_font)
        
        y += 55

    # حقوق
    wm_font = _get_font(12)
    try:
        bbox = draw.textbbox((0, 0), WATERMARK, font=wm_font)
        ww = bbox[2] - bbox[0]
    except Exception:
        ww = len(WATERMARK) * 7
    draw.text((TARGET_W - ww - 20, TARGET_H - 25), WATERMARK, fill=COLORS[2], font=wm_font)

    img.save(img_path, "JPEG", quality=90)
    return img_path


# ─────────────────────────────────────────────────────────────────────────────
# 4. شريحة عنوان القسم
# ─────────────────────────────────────────────────────────────────────────────

def _draw_section_title_card(section: dict, idx: int, total: int, is_arabic: bool) -> str:
    img_fd, img_path = tempfile.mkstemp(prefix=f"sec_title_{idx}_", suffix=".jpg")
    os.close(img_fd)

    color = COLORS[idx % len(COLORS)]
    img = PILImage.new("RGB", (TARGET_W, TARGET_H), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    draw.rectangle([(0, 0), (TARGET_W, 6)], fill=color)

    cx, cy, cr = TARGET_W // 2, TARGET_H // 2 - 40, 40
    draw.ellipse([cx - cr, cy - cr, cx + cr, cy + cr], fill=color)
    num_str = str(idx + 1)
    num_font = _get_font(36, bold=True)
    try:
        bbox = draw.textbbox((0, 0), num_str, font=num_font)
        nw = bbox[2] - bbox[0]
    except Exception:
        nw = 20
    draw.text((cx - nw//2, cy - 20), num_str, fill=(255, 255, 255), font=num_font)

    raw_title = section.get("title", f"القسم {idx + 1}")
    title_disp = _prepare_text(raw_title, is_arabic)
    title_font = _get_font(30, bold=True, arabic=is_arabic)
    
    try:
        bbox = draw.textbbox((0, 0), title_disp, font=title_font)
        tw = bbox[2] - bbox[0]
    except Exception:
        tw = len(title_disp) * 17
    
    x = (TARGET_W - tw) // 2
    draw.text((x, cy + cr + 30), title_disp, fill=(44, 62, 80), font=title_font)

    # حقوق
    wm_font = _get_font(12)
    try:
        bbox = draw.textbbox((0, 0), WATERMARK, font=wm_font)
        ww = bbox[2] - bbox[0]
    except Exception:
        ww = len(WATERMARK) * 7
    draw.text((TARGET_W - ww - 20, TARGET_H - 25), WATERMARK, fill=color, font=wm_font)

    img.save(img_path, "JPEG", quality=90)
    return img_path


# ─────────────────────────────────────────────────────────────────────────────
# 5. شريحة السبورة المتراكمة (القلب النابض للفيديو)
# ─────────────────────────────────────────────────────────────────────────────

def _draw_accumulating_board(
    accumulated_keywords: list[str],
    accumulated_images: list[bytes | None],
    current_kw_idx: int,
    total_kw: int,
    section_title: str,
    section_idx: int,
    is_arabic: bool,
) -> str:
    fd, path = tempfile.mkstemp(prefix="board_", suffix=".jpg")
    os.close(fd)

    color = COLORS[section_idx % len(COLORS)]
    img = PILImage.new("RGB", (TARGET_W, TARGET_H), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    draw.rectangle([(0, 0), (TARGET_W, 6)], fill=color)

    # عنوان القسم
    header_disp = _prepare_text(section_title[:40], is_arabic)
    header_font = _get_font(18, bold=True, arabic=is_arabic)
    try:
        bbox = draw.textbbox((0, 0), header_disp, font=header_font)
        hw = bbox[2] - bbox[0]
    except Exception:
        hw = len(header_disp) * 10
    hx = (TARGET_W - hw) // 2
    draw.text((hx, 15), header_disp, fill=(44, 62, 80), font=header_font)
    draw.rectangle([(hx, 38), (hx + hw, 40)], fill=color)

    n_items = len(accumulated_keywords)
    
    if n_items == 1:
        # عنصر واحد: صورة كبيرة في المنتصف
        kw = accumulated_keywords[0]
        img_bytes = accumulated_images[0] if accumulated_images else None
        
        if img_bytes:
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
                    [(px - 4, py - 4), (px + nw + 4, py + nh + 4)],
                    radius=8, outline=color, width=3
                )
                img.paste(pil_img, (px, py))
                
                # الكلمة تحت الصورة
                kw_disp = _prepare_text(kw, is_arabic)
                kw_font = _get_font(24, bold=True, arabic=is_arabic)
                try:
                    bbox = draw.textbbox((0, 0), kw_disp, font=kw_font)
                    kww = bbox[2] - bbox[0]
                except Exception:
                    kww = len(kw_disp) * 14
                kw_x = (TARGET_W - kww) // 2
                draw.text((kw_x, py + nh + 20), kw_disp, fill=color, font=kw_font)
            except Exception:
                pass
    else:
        # عناصر متعددة: شبكة 2x2
        cols = 2
        rows = (n_items + 1) // 2
        cell_w = (TARGET_W - 100) // cols
        cell_h = 160
        
        for i in range(n_items):
            col = i % cols
            row = i // cols
            
            cx = 50 + col * (cell_w + 20)
            cy = 70 + row * (cell_h + 20)
            
            kw = accumulated_keywords[i]
            img_bytes = accumulated_images[i] if i < len(accumulated_images) else None
            cell_color = COLORS[i % len(COLORS)]
            
            # صورة
            if img_bytes:
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
                        [(px - 3, py - 3), (px + nw + 3, py + nh + 3)],
                        radius=6, outline=cell_color, width=2
                    )
                    img.paste(pil_img, (px, py))
                except Exception:
                    pass
            
            # كلمة مفتاحية
            kw_disp = _prepare_text(kw[:15], is_arabic)
            kw_font = _get_font(14, bold=True, arabic=is_arabic)
            try:
                bbox = draw.textbbox((0, 0), kw_disp, font=kw_font)
                kww = bbox[2] - bbox[0]
            except Exception:
                kww = len(kw_disp) * 8
            
            kw_x = cx + (cell_w - kww) // 2
            kw_y = cy + cell_h - 25
            draw.text((kw_x, kw_y), kw_disp, fill=cell_color, font=kw_font)
            
            # رقم
            num_str = str(i + 1)
            num_font = _get_font(10, bold=True)
            draw.ellipse([(cx - 3, cy - 3), (cx + 13, cy + 13)], fill=cell_color)
            draw.text((cx + 3, cy - 2), num_str, fill=(255, 255, 255), font=num_font)

    # مؤشر التقدم
    dot_y = TARGET_H - 25
    dot_r = 5
    dot_gap = 22
    total_w = total_kw * dot_gap
    start_x = (TARGET_W - total_w) // 2
    
    for i in range(total_kw):
        dx = start_x + i * dot_gap
        dot_color = color if i <= current_kw_idx else (220, 220, 220)
        r = dot_r if i <= current_kw_idx else dot_r - 2
        draw.ellipse([(dx - r, dot_y - r), (dx + r, dot_y + r)], fill=dot_color)

    # حقوق
    wm_font = _get_font(11)
    try:
        bbox = draw.textbbox((0, 0), WATERMARK, font=wm_font)
        ww = bbox[2] - bbox[0]
    except Exception:
        ww = len(WATERMARK) * 6
    draw.text((TARGET_W - ww - 15, TARGET_H - 20), WATERMARK, fill=color, font=wm_font)

    img.save(path, "JPEG", quality=92)
    return path


# ─────────────────────────────────────────────────────────────────────────────
# 6. شريحة الخاتمة - الملخص النهائي
# ─────────────────────────────────────────────────────────────────────────────

def _draw_final_summary(sections: list, lecture_data: dict, is_arabic: bool) -> str:
    img_fd, img_path = tempfile.mkstemp(prefix="summary_", suffix=".jpg")
    os.close(img_fd)

    img = PILImage.new("RGB", (TARGET_W, TARGET_H), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    draw.rectangle([(0, 0), (TARGET_W, 6)], fill=COLORS[0])

    title_disp = _prepare_text("📋 ملخص المحاضرة", is_arabic)
    title_font = _get_font(28, bold=True, arabic=is_arabic)
    try:
        bbox = draw.textbbox((0, 0), title_disp, font=title_font)
        tw = bbox[2] - bbox[0]
    except Exception:
        tw = len(title_disp) * 16
    tx = (TARGET_W - tw) // 2
    draw.text((tx, 30), title_disp, fill=(44, 62, 80), font=title_font)

    y = 80
    for i, section in enumerate(sections):
        color = COLORS[i % len(COLORS)]
        keywords = section.get("keywords", [])
        kw_text = " • ".join(keywords[:4])
        kw_disp = _prepare_text(kw_text, is_arabic)
        kw_font = _get_font(16, arabic=is_arabic)
        
        try:
            bbox = draw.textbbox((0, 0), kw_disp, font=kw_font)
            tw = bbox[2] - bbox[0]
        except Exception:
            tw = len(kw_disp) * 9
        
        x = (TARGET_W - tw) // 2
        draw.rectangle([(x - 10, y - 5), (x + tw + 10, y + 25)], fill=(*color, 20))
        draw.text((x, y), kw_disp, fill=color, font=kw_font)
        y += 45

    thanks_disp = _prepare_text("🙏 شكراً لحسن استماعكم", is_arabic)
    thanks_font = _get_font(22, bold=True, arabic=is_arabic)
    try:
        bbox = draw.textbbox((0, 0), thanks_disp, font=thanks_font)
        tw = bbox[2] - bbox[0]
    except Exception:
        tw = len(thanks_disp) * 13
    tx = (TARGET_W - tw) // 2
    draw.text((tx, TARGET_H - 50), thanks_disp, fill=COLORS[0], font=thanks_font)

    # حقوق
    wm_font = _get_font(14, bold=True)
    try:
        bbox = draw.textbbox((0, 0), WATERMARK, font=wm_font)
        ww = bbox[2] - bbox[0]
    except Exception:
        ww = len(WATERMARK) * 8
    draw.text((TARGET_W - ww - 20, TARGET_H - 30), WATERMARK, fill=COLORS[0], font=wm_font)

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
    is_arabic: bool,
) -> tuple[list[dict], list[str], float]:
    segments: list[dict] = []
    tmp_files: list[str] = []
    total_secs = 0.0
    n_sections = len(sections)

    # 1. المقدمة - حقوق + أهلاً وسهلاً
    welcome_path = _draw_welcome_slide(is_arabic)
    tmp_files.append(welcome_path)
    segments.append({"img": welcome_path, "audio": None, "audio_start": 0.0, "dur": 3.0})
    total_secs += 3.0

    # 2. عنوان المحاضرة
    title_path = _draw_title_slide(lecture_data, is_arabic)
    tmp_files.append(title_path)
    segments.append({"img": title_path, "audio": None, "audio_start": 0.0, "dur": 4.0})
    total_secs += 4.0

    # 3. خريطة الأقسام
    map_path = _draw_sections_map(sections, is_arabic)
    tmp_files.append(map_path)
    segments.append({"img": map_path, "audio": None, "audio_start": 0.0, "dur": 5.0})
    total_secs += 5.0

    # 4. الأقسام
    for sec_idx, (section, audio_info) in enumerate(zip(sections, audio_results)):
        # عنوان القسم
        sec_title_path = _draw_section_title_card(section, sec_idx, n_sections, is_arabic)
        tmp_files.append(sec_title_path)
        segments.append({"img": sec_title_path, "audio": None, "audio_start": 0.0, "dur": 3.0})
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
        
        # تراكم الصور والكلمات
        accum_kw = []
        accum_img = []
        
        for kw_idx in range(n_kw):
            accum_kw.append(keywords[kw_idx])
            img_bytes = kw_images[kw_idx] if kw_idx < len(kw_images) else None
            accum_img.append(img_bytes)
            
            board_path = _draw_accumulating_board(
                accumulated_keywords=accum_kw.copy(),
                accumulated_images=accum_img.copy(),
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

    # 5. الخاتمة - الملخص
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
            _ffmpeg_segment(seg["img"], seg["dur"], seg["audio"], seg["audio_start"], seg_out)
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
