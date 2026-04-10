import asyncio
import io
import os
import subprocess
import tempfile
from PIL import Image as PILImage, ImageDraw, ImageFont

TARGET_W, TARGET_H = 854, 480
WATERMARK = "@zakros_probot"

# ألوان
COLORS = [
    (231, 76, 126),   # وردي
    (52, 152, 219),   # أزرق
    (46, 204, 113),   # أخضر
    (155, 89, 182),   # بنفسجي
    (230, 126, 34),   # برتقالي
]

def estimate_encoding_seconds(total_video_seconds: float) -> float:
    return max(20.0, total_video_seconds * 0.6)


def _get_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/app/fonts/Amiri-Bold.ttf",
        "fonts/Amiri-Bold.ttf",
    ]
    for p in font_paths:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except:
                pass
    return ImageFont.load_default()


def _prepare_text(text: str) -> str:
    if not text:
        return ""
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
        if any('\u0600' <= c <= '\u06FF' for c in text):
            reshaped = arabic_reshaper.reshape(text)
            return get_display(reshaped)
    except:
        pass
    return text


def _draw_welcome_slide() -> str:
    img_fd, img_path = tempfile.mkstemp(prefix="welcome_", suffix=".jpg")
    os.close(img_fd)

    img = PILImage.new("RGB", (TARGET_W, TARGET_H), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    draw.rectangle([(0, 0), (TARGET_W, 8)], fill=COLORS[0])
    draw.rectangle([(0, TARGET_H-8), (TARGET_W, TARGET_H)], fill=COLORS[0])

    # إطار الشعار
    frame_x, frame_y = 150, 100
    frame_w, frame_h = 550, 200
    draw.rounded_rectangle(
        [(frame_x, frame_y), (frame_x + frame_w, frame_y + frame_h)],
        radius=25, outline=COLORS[0], width=8
    )

    font_logo = _get_font(60, bold=True)
    logo_text = WATERMARK
    try:
        bbox = font_logo.getbbox(logo_text)
        logo_w = bbox[2] - bbox[0]
    except:
        logo_w = len(logo_text) * 35
    logo_x = (TARGET_W - logo_w) // 2
    logo_y = frame_y + 60
    draw.text((logo_x + 4, logo_y + 4), logo_text, fill=(200, 200, 200), font=font_logo)
    draw.text((logo_x, logo_y), logo_text, fill=COLORS[0], font=font_logo)

    welcome_text = _prepare_text("أهلاً ومرحباً بكم")
    font_welcome = _get_font(36, bold=True)
    try:
        bbox = font_welcome.getbbox(welcome_text)
        welcome_w = bbox[2] - bbox[0]
    except:
        welcome_w = len(welcome_text) * 20
    welcome_x = (TARGET_W - welcome_w) // 2
    welcome_y = frame_y + frame_h + 40
    draw.text((welcome_x + 3, welcome_y + 3), welcome_text, fill=(200, 200, 200), font=font_welcome)
    draw.text((welcome_x, welcome_y), welcome_text, fill=(44, 62, 80), font=font_welcome)

    img.save(img_path, "JPEG", quality=90)
    return img_path


def _draw_title_slide(lecture_data: dict) -> str:
    img_fd, img_path = tempfile.mkstemp(prefix="title_", suffix=".jpg")
    os.close(img_fd)

    img = PILImage.new("RGB", (TARGET_W, TARGET_H), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    draw.rectangle([(0, 0), (TARGET_W, 6)], fill=COLORS[1])

    title_text = _prepare_text(lecture_data.get("title", "المحاضرة التعليمية"))
    font_title = _get_font(38, bold=True)
    
    # تقسيم النص
    words = title_text.split()
    lines = []
    current = []
    for w in words:
        current.append(w)
        line = ' '.join(current)
        try:
            bbox = font_title.getbbox(line)
            if bbox[2] - bbox[0] > TARGET_W - 80:
                current.pop()
                lines.append(' '.join(current))
                current = [w]
        except:
            pass
    if current:
        lines.append(' '.join(current))
    
    y = TARGET_H//2 - (len(lines) * 45)//2
    for line in lines:
        try:
            bbox = font_title.getbbox(line)
            tw = bbox[2] - bbox[0]
        except:
            tw = len(line) * 22
        x = (TARGET_W - tw) // 2
        draw.text((x + 3, y + 3), line, fill=(200, 200, 200), font=font_title)
        draw.text((x, y), line, fill=(44, 62, 80), font=font_title)
        y += 45

    img.save(img_path, "JPEG", quality=90)
    return img_path


def _draw_sections_map(sections: list) -> str:
    img_fd, img_path = tempfile.mkstemp(prefix="map_", suffix=".jpg")
    os.close(img_fd)

    img = PILImage.new("RGB", (TARGET_W, TARGET_H), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    draw.rectangle([(0, 0), (TARGET_W, 6)], fill=COLORS[2])

    map_title = _prepare_text("📋 خريطة المحاضرة")
    font_title = _get_font(30, bold=True)
    try:
        bbox = font_title.getbbox(map_title)
        tw = bbox[2] - bbox[0]
    except:
        tw = len(map_title) * 18
    x = (TARGET_W - tw) // 2
    draw.text((x, 30), map_title, fill=COLORS[2], font=font_title)

    y = 90
    for i, section in enumerate(sections):
        color = COLORS[i % len(COLORS)]
        
        draw.ellipse([(30, y), (52, y + 22)], fill=color)
        num_str = str(i + 1)
        font_num = _get_font(15, bold=True)
        draw.text((41, y + 3), num_str, fill=(255, 255, 255), font=font_num)
        
        sec_text = _prepare_text(section.get("title", f"القسم {i+1}")[:30])
        font_sec = _get_font(20, bold=True)
        draw.text((70, y), sec_text, fill=(44, 62, 80), font=font_sec)
        
        keywords = section.get("keywords", [])[:3]
        if keywords:
            kw_text = " • ".join(keywords)
            kw_disp = _prepare_text(kw_text)
            font_kw = _get_font(14)
            draw.text((85, y + 26), kw_disp, fill=color, font=font_kw)
        
        y += 60

    img.save(img_path, "JPEG", quality=90)
    return img_path


def _draw_section_title_card(section: dict, idx: int) -> str:
    img_fd, img_path = tempfile.mkstemp(prefix=f"sec_title_{idx}_", suffix=".jpg")
    os.close(img_fd)

    color = COLORS[idx % len(COLORS)]
    img = PILImage.new("RGB", (TARGET_W, TARGET_H), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    draw.rectangle([(0, 0), (TARGET_W, 6)], fill=color)

    cx, cy, cr = TARGET_W // 2, TARGET_H // 2 - 50, 45
    draw.ellipse([cx - cr, cy - cr, cx + cr, cy + cr], fill=color)
    num_str = str(idx + 1)
    font_num = _get_font(40, bold=True)
    try:
        bbox = font_num.getbbox(num_str)
        nw = bbox[2] - bbox[0]
    except:
        nw = 25
    draw.text((cx - nw//2, cy - 22), num_str, fill=(255, 255, 255), font=font_num)

    title_text = _prepare_text(section.get("title", f"القسم {idx + 1}"))
    font_title = _get_font(32, bold=True)
    try:
        bbox = font_title.getbbox(title_text)
        tw = bbox[2] - bbox[0]
    except:
        tw = len(title_text) * 18
    x = (TARGET_W - tw) // 2
    draw.text((x, cy + cr + 35), title_text, fill=(44, 62, 80), font=font_title)

    img.save(img_path, "JPEG", quality=90)
    return img_path


def _draw_content_slide(
    keywords: list[str],
    terms_en: list[str],
    current_idx: int,
    total_kw: int,
    section_title: str,
    section_idx: int,
) -> str:
    """شريحة محتوى تتراكم فيها الكلمات مع صورها"""
    fd, path = tempfile.mkstemp(prefix="content_", suffix=".jpg")
    os.close(fd)

    color = COLORS[section_idx % len(COLORS)]
    img = PILImage.new("RGB", (TARGET_W, TARGET_H), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    draw.rectangle([(0, 0), (TARGET_W, 6)], fill=color)

    # عنوان القسم
    header_text = _prepare_text(section_title[:40])
    font_header = _get_font(18, bold=True)
    try:
        bbox = font_header.getbbox(header_text)
        hw = bbox[2] - bbox[0]
    except:
        hw = len(header_text) * 10
    hx = (TARGET_W - hw) // 2
    draw.text((hx, 15), header_text, fill=(44, 62, 80), font=font_header)
    draw.rectangle([(hx, 38), (hx + hw, 40)], fill=color)

    n_items = current_idx + 1
    
    if n_items == 1:
        # عنصر واحد
        kw = keywords[0] if keywords else ""
        term_en = terms_en[0] if terms_en else ""
        
        # صورة
        img_bytes = _make_simple_image(kw, color, term_en)
        try:
            pil_img = PILImage.open(io.BytesIO(img_bytes)).convert("RGB")
            iw, ih = pil_img.size
            max_w, max_h = 500, 260
            scale = min(max_w / iw, max_h / ih)
            nw, nh = int(iw * scale), int(ih * scale)
            pil_img = pil_img.resize((nw, nh), PILImage.LANCZOS)
            
            px = (TARGET_W - nw) // 2
            py = 75
            
            draw.rounded_rectangle(
                [(px - 5, py - 5), (px + nw + 5, py + nh + 5)],
                radius=10, outline=color, width=4
            )
            img.paste(pil_img, (px, py))
        except:
            pass
    else:
        # عناصر متعددة
        cols = 2
        rows = (n_items + 1) // 2
        cell_w = (TARGET_W - 100) // cols
        cell_h = 160
        
        for i in range(n_items):
            col = i % cols
            row = i // rows
            
            cx = 50 + col * (cell_w + 20)
            cy = 70 + row * (cell_h + 20)
            
            kw = keywords[i] if i < len(keywords) else ""
            term_en = terms_en[i] if i < len(terms_en) else ""
            cell_color = COLORS[i % len(COLORS)]
            
            img_bytes = _make_simple_image(kw, cell_color, term_en)
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
        dot_color = color if i <= current_idx else (220, 220, 220)
        r = dot_r if i <= current_idx else dot_r - 2
        draw.ellipse([(dx - r, dot_y - r), (dx + r, dot_y + r)], fill=dot_color)

    # حقوق
    font_wm = _get_font(12, bold=True)
    try:
        bbox = font_wm.getbbox(WATERMARK)
        wm_w = bbox[2] - bbox[0]
    except:
        wm_w = len(WATERMARK) * 7
    draw.text((TARGET_W - wm_w - 20, TARGET_H - 25), WATERMARK, fill=color, font=font_wm)

    img.save(path, "JPEG", quality=92)
    return path


def _make_simple_image(keyword: str, color: tuple, term_en: str = "") -> bytes:
    """صورة بسيطة ملونة"""
    W, H = 400, 300
    img = PILImage.new("RGB", (W, H), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    
    for y in range(H):
        t = y / H
        r = int(255 * (1 - t) + color[0] * t * 0.15)
        g = int(255 * (1 - t) + color[1] * t * 0.15)
        b = int(255 * (1 - t) + color[2] * t * 0.15)
        draw.line([(0, y), (W, y)], fill=(r, g, b))
    
    draw.rounded_rectangle([(8, 8), (W-8, H-8)], radius=12, outline=color, width=5)
    draw.ellipse([(W//2-55, H//2-55), (W//2+55, H//2+55)], fill=(*color, 25))
    
    font = _get_font(32, bold=True)
    keyword_disp = _prepare_text(keyword[:20])
    
    words = keyword_disp.split()
    lines = []
    current = []
    for w in words:
        current.append(w)
        line = ' '.join(current)
        try:
            bbox = font.getbbox(line)
            if bbox[2] - bbox[0] > W - 40:
                current.pop()
                lines.append(' '.join(current))
                current = [w]
        except:
            pass
    if current:
        lines.append(' '.join(current))
    
    y = H//2 - (len(lines) * 35)//2 - 10
    for line in lines:
        try:
            bbox = font.getbbox(line)
            tw = bbox[2] - bbox[0]
        except:
            tw = len(line) * 18
        x = (W - tw) // 2
        draw.text((x+2, y+2), line, fill=(200, 200, 200), font=font)
        draw.text((x, y), line, fill=color, font=font)
        y += 40
    
    if term_en:
        font_en = _get_font(18, bold=True)
        term_disp = term_en[:30]
        try:
            bbox = font_en.getbbox(term_disp)
            tw = bbox[2] - bbox[0]
        except:
            tw = len(term_disp) * 10
        x = (W - tw) // 2
        draw.text((x, y + 15), term_disp, fill=(100, 100, 100), font=font_en)
    
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=90)
    return buf.getvalue()


def _draw_final_summary(sections: list) -> str:
    img_fd, img_path = tempfile.mkstemp(prefix="summary_", suffix=".jpg")
    os.close(img_fd)

    img = PILImage.new("RGB", (TARGET_W, TARGET_H), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    draw.rectangle([(0, 0), (TARGET_W, 8)], fill=COLORS[0])
    draw.rectangle([(0, TARGET_H-8), (TARGET_W, TARGET_H)], fill=COLORS[0])

    title_text = _prepare_text("📋 ملخص المحاضرة")
    font_title = _get_font(30, bold=True)
    try:
        bbox = font_title.getbbox(title_text)
        tw = bbox[2] - bbox[0]
    except:
        tw = len(title_text) * 18
    tx = (TARGET_W - tw) // 2
    draw.text((tx, 35), title_text, fill=(44, 62, 80), font=font_title)

    y = 90
    for i, section in enumerate(sections):
        color = COLORS[i % len(COLORS)]
        keywords = section.get("keywords", [])
        kw_text = " • ".join(keywords[:4])
        kw_disp = _prepare_text(kw_text)
        font_kw = _get_font(16, bold=True)
        
        try:
            bbox = font_kw.getbbox(kw_disp)
            kw_w = bbox[2] - bbox[0]
        except:
            kw_w = len(kw_disp) * 9
        
        x = (TARGET_W - kw_w) // 2
        
        draw.rounded_rectangle(
            [(x - 15, y - 8), (x + kw_w + 15, y + 28)],
            radius=8, fill=(*color, 20), outline=color, width=2
        )
        draw.text((x, y), kw_disp, fill=color, font=font_kw)
        y += 50

    thanks_text = _prepare_text("🙏 شكراً لحسن استماعكم")
    font_thanks = _get_font(26, bold=True)
    try:
        bbox = font_thanks.getbbox(thanks_text)
        tw = bbox[2] - bbox[0]
    except:
        tw = len(thanks_text) * 15
    tx = (TARGET_W - tw) // 2
    draw.text((tx + 3, TARGET_H - 65), thanks_text, fill=(200, 200, 200), font=font_thanks)
    draw.text((tx, TARGET_H - 68), thanks_text, fill=COLORS[0], font=font_thanks)

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


def _build_segment_list(
    sections: list,
    audio_results: list,
    lecture_data: dict,
) -> tuple[list[dict], list[str], float]:
    segments: list[dict] = []
    tmp_files: list[str] = []
    total_secs = 0.0

    # 1. مقدمة
    welcome_path = _draw_welcome_slide()
    tmp_files.append(welcome_path)
    segments.append({"img": welcome_path, "audio": None, "audio_start": 0.0, "dur": 3.5})
    total_secs += 3.5

    # 2. عنوان
    title_path = _draw_title_slide(lecture_data)
    tmp_files.append(title_path)
    segments.append({"img": title_path, "audio": None, "audio_start": 0.0, "dur": 4.0})
    total_secs += 4.0

    # 3. خريطة
    map_path = _draw_sections_map(sections)
    tmp_files.append(map_path)
    segments.append({"img": map_path, "audio": None, "audio_start": 0.0, "dur": 5.0})
    total_secs += 5.0

    # 4. أقسام
    for sec_idx, (section, audio_info) in enumerate(zip(sections, audio_results)):
        title_path = _draw_section_title_card(section, sec_idx)
        tmp_files.append(title_path)
        segments.append({"img": title_path, "audio": None, "audio_start": 0.0, "dur": 3.0})
        total_secs += 3.0

        keywords = section.get("keywords", ["مفهوم"])
        terms_en = section.get("terms_en", [])
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
            content_path = _draw_content_slide(
                keywords=keywords,
                terms_en=terms_en,
                current_idx=kw_idx,
                total_kw=n_kw,
                section_title=sec_title,
                section_idx=sec_idx,
            )
            tmp_files.append(content_path)
            
            segments.append({
                "img": content_path,
                "audio": apath,
                "audio_start": kw_idx * kw_dur,
                "dur": kw_dur,
            })
            total_secs += kw_dur

    # 5. خاتمة
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

    for section in sections:
        if "keywords" not in section or not section["keywords"]:
            section["keywords"] = ["مفهوم", "تعريف", "شرح", "تحليل"]
        if "terms_en" not in section:
            section["terms_en"] = []

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
