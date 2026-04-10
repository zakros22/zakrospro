import asyncio
import io
import os
import subprocess
import tempfile
from PIL import Image as PILImage, ImageDraw, ImageFont

TARGET_W, TARGET_H = 854, 480
WATERMARK = "@zakros_probot"

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
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ]
    for p in font_paths:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except:
                pass
    return ImageFont.load_default()


def _draw_welcome_slide() -> str:
    img_fd, img_path = tempfile.mkstemp(prefix="welcome_", suffix=".jpg")
    os.close(img_fd)

    img = PILImage.new("RGB", (TARGET_W, TARGET_H), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    draw.rectangle([(0, 0), (TARGET_W, 8)], fill=COLORS[0])
    draw.rectangle([(0, TARGET_H-8), (TARGET_W, TARGET_H)], fill=COLORS[0])

    frame_x, frame_y = 150, 100
    frame_w, frame_h = 550, 200
    draw.rounded_rectangle(
        [(frame_x, frame_y), (frame_x + frame_w, frame_y + frame_h)],
        radius=25, outline=COLORS[0], width=8
    )

    font_logo = _get_font(60, bold=True)
    try:
        bbox = font_logo.getbbox(WATERMARK)
        logo_w = bbox[2] - bbox[0]
    except:
        logo_w = len(WATERMARK) * 35
    logo_x = (TARGET_W - logo_w) // 2
    logo_y = frame_y + 60
    draw.text((logo_x + 4, logo_y + 4), WATERMARK, fill=(200, 200, 200), font=font_logo)
    draw.text((logo_x, logo_y), WATERMARK, fill=COLORS[0], font=font_logo)

    font_welcome = _get_font(36, bold=True)
    welcome_text = "أهلاً ومرحباً بكم"
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


def _draw_title_slide(title: str) -> str:
    img_fd, img_path = tempfile.mkstemp(prefix="title_", suffix=".jpg")
    os.close(img_fd)

    img = PILImage.new("RGB", (TARGET_W, TARGET_H), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    draw.rectangle([(0, 0), (TARGET_W, 6)], fill=COLORS[1])

    font_title = _get_font(38, bold=True)
    
    words = title.split()
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


def _draw_sections_map(section_titles: list) -> str:
    img_fd, img_path = tempfile.mkstemp(prefix="map_", suffix=".jpg")
    os.close(img_fd)

    img = PILImage.new("RGB", (TARGET_W, TARGET_H), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    draw.rectangle([(0, 0), (TARGET_W, 6)], fill=COLORS[2])

    font_title = _get_font(30, bold=True)
    map_title = "📋 خريطة المحاضرة"
    try:
        bbox = font_title.getbbox(map_title)
        tw = bbox[2] - bbox[0]
    except:
        tw = len(map_title) * 18
    x = (TARGET_W - tw) // 2
    draw.text((x, 30), map_title, fill=COLORS[2], font=font_title)

    y = 90
    for i, sec_title in enumerate(section_titles):
        color = COLORS[i % len(COLORS)]
        
        draw.ellipse([(30, y), (52, y + 22)], fill=color)
        num_str = str(i + 1)
        font_num = _get_font(15, bold=True)
        draw.text((41, y + 3), num_str, fill=(255, 255, 255), font=font_num)
        
        font_sec = _get_font(20, bold=True)
        draw.text((70, y), sec_title[:35], fill=(44, 62, 80), font=font_sec)
        
        y += 55

    img.save(img_path, "JPEG", quality=90)
    return img_path


def _draw_section_title_card(title: str, idx: int) -> str:
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

    font_title = _get_font(32, bold=True)
    try:
        bbox = font_title.getbbox(title)
        tw = bbox[2] - bbox[0]
    except:
        tw = len(title) * 18
    x = (TARGET_W - tw) // 2
    draw.text((x, cy + cr + 35), title, fill=(44, 62, 80), font=font_title)

    img.save(img_path, "JPEG", quality=90)
    return img_path


def _make_keyword_card(keyword: str, color: tuple, idx: int, img_bytes: bytes = None) -> bytes:
    """إنشاء بطاقة للكلمة المفتاحية"""
    W, H = 360, 280
    
    if img_bytes:
        try:
            img = PILImage.open(io.BytesIO(img_bytes)).convert("RGB")
            img = img.resize((W, H), PILImage.LANCZOS)
            draw = ImageDraw.Draw(img)
            draw.rounded_rectangle([(4, 4), (W-4, H-4)], radius=12, outline=color, width=5)
            
            font_num = _get_font(18, bold=True)
            draw.ellipse([(15, 15), (42, 42)], fill=color)
            num_str = str(idx + 1)
            try:
                bbox = font_num.getbbox(num_str)
                nw = bbox[2] - bbox[0]
            except:
                nw = 10
            draw.text((28 - nw//2, 22), num_str, fill=(255, 255, 255), font=font_num)
            
            # كتابة الكلمة على الصورة
            font_kw = _get_font(22, bold=True)
            try:
                bbox = font_kw.getbbox(keyword)
                kw_w = bbox[2] - bbox[0]
            except:
                kw_w = len(keyword) * 13
            kw_x = (W - kw_w) // 2
            draw.text((kw_x+1, H-35), keyword, fill=(0,0,0), font=font_kw)
            draw.text((kw_x, H-36), keyword, fill=(255,255,255), font=font_kw)
            
            buf = io.BytesIO()
            img.save(buf, "JPEG", quality=90)
            return buf.getvalue()
        except:
            pass
    
    # صورة افتراضية
    img = PILImage.new("RGB", (W, H), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    
    for y in range(H):
        t = y / H
        r = int(255 * (1 - t) + color[0] * t * 0.2)
        g = int(255 * (1 - t) + color[1] * t * 0.2)
        b = int(255 * (1 - t) + color[2] * t * 0.2)
        draw.line([(0, y), (W, y)], fill=(r, g, b))
    
    draw.rounded_rectangle([(8, 8), (W-8, H-8)], radius=15, outline=color, width=6)
    draw.ellipse([(W//2-50, H//2-50), (W//2+50, H//2+50)], fill=(*color, 25))
    
    font_num = _get_font(18, bold=True)
    draw.ellipse([(15, 15), (42, 42)], fill=color)
    num_str = str(idx + 1)
    try:
        bbox = font_num.getbbox(num_str)
        nw = bbox[2] - bbox[0]
    except:
        nw = 10
    draw.text((28 - nw//2, 22), num_str, fill=(255, 255, 255), font=font_num)
    
    font_kw = _get_font(26, bold=True)
    words = keyword.split()
    lines = []
    current = []
    for w in words:
        current.append(w)
        line = ' '.join(current)
        try:
            bbox = font_kw.getbbox(line)
            if bbox[2] - bbox[0] > W - 60:
                current.pop()
                lines.append(' '.join(current))
                current = [w]
        except:
            pass
    if current:
        lines.append(' '.join(current))
    
    y = H//2 - (len(lines) * 38)//2
    for line in lines:
        try:
            bbox = font_kw.getbbox(line)
            tw = bbox[2] - bbox[0]
        except:
            tw = len(line) * 15
        x = (W - tw) // 2
        draw.text((x+2, y+2), line, fill=(200, 200, 200), font=font_kw)
        draw.text((x, y), line, fill=color, font=font_kw)
        y += 42
    
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=90)
    return buf.getvalue()


def _draw_accumulating_board(
    accumulated_keywords: list[str],
    accumulated_images: list[bytes | None],
    current_idx: int,
    total_kw: int,
    section_title: str,
    section_idx: int,
) -> str:
    """سبورة تتراكم عليها بطاقات الكلمات مع الصور"""
    fd, path = tempfile.mkstemp(prefix="board_", suffix=".jpg")
    os.close(fd)

    color = COLORS[section_idx % len(COLORS)]
    img = PILImage.new("RGB", (TARGET_W, TARGET_H), (248, 248, 250))
    draw = ImageDraw.Draw(img)

    draw.rectangle([(0, 0), (TARGET_W, 6)], fill=color)

    # عنوان القسم
    font_header = _get_font(18, bold=True)
    try:
        bbox = font_header.getbbox(section_title[:40])
        hw = bbox[2] - bbox[0]
    except:
        hw = len(section_title[:40]) * 10
    hx = (TARGET_W - hw) // 2
    draw.text((hx, 15), section_title[:40], fill=(44, 62, 80), font=font_header)
    draw.rectangle([(hx, 38), (hx + hw, 40)], fill=color)

    n_items = len(accumulated_keywords)
    
    if n_items == 1:
        # عنصر واحد - كبير في المنتصف
        kw = accumulated_keywords[0]
        img_bytes = accumulated_images[0] if accumulated_images else None
        
        card_bytes = _make_keyword_card(kw, color, 0, img_bytes)
        try:
            pil_img = PILImage.open(io.BytesIO(card_bytes)).convert("RGB")
            iw, ih = pil_img.size
            max_w, max_h = 500, 340
            scale = min(max_w / iw, max_h / ih)
            nw, nh = int(iw * scale), int(ih * scale)
            pil_img = pil_img.resize((nw, nh), PILImage.LANCZOS)
            
            px = (TARGET_W - nw) // 2
            py = 70
            
            draw.rounded_rectangle(
                [(px - 5, py - 5), (px + nw + 5, py + nh + 5)],
                radius=12, outline=color, width=4
            )
            img.paste(pil_img, (px, py))
        except:
            pass
    else:
        # عناصر متعددة - شبكة 2x2
        cols = 2
        rows = (n_items + 1) // 2
        cell_w = 380
        cell_h = 290
        start_x = (TARGET_W - (cols * cell_w + (cols - 1) * 15)) // 2
        
        for i in range(n_items):
            col = i % cols
            row = i // rows
            
            cx = start_x + col * (cell_w + 15)
            cy = 65 + row * (cell_h + 10)
            
            kw = accumulated_keywords[i]
            img_bytes = accumulated_images[i] if i < len(accumulated_images) else None
            cell_color = COLORS[i % len(COLORS)]
            
            card_bytes = _make_keyword_card(kw, cell_color, i, img_bytes)
            try:
                pil_img = PILImage.open(io.BytesIO(card_bytes)).convert("RGB")
                iw, ih = pil_img.size
                max_w, max_h = cell_w, cell_h
                scale = min(max_w / iw, max_h / ih)
                nw, nh = int(iw * scale), int(ih * scale)
                pil_img = pil_img.resize((nw, nh), PILImage.LANCZOS)
                
                px = cx + (cell_w - nw) // 2
                py = cy + (cell_h - nh) // 2
                
                img.paste(pil_img, (px, py))
            except:
                pass

    # مؤشر التقدم
    dot_y = TARGET_H - 30
    dot_r = 6
    dot_gap = 25
    total_w = total_kw * dot_gap
    start_x = (TARGET_W - total_w) // 2
    
    for i in range(total_kw):
        dx = start_x + i * dot_gap
        dot_color = color if i <= current_idx else (200, 200, 200)
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


def _draw_final_summary(all_keywords: list) -> str:
    img_fd, img_path = tempfile.mkstemp(prefix="summary_", suffix=".jpg")
    os.close(img_fd)

    img = PILImage.new("RGB", (TARGET_W, TARGET_H), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    draw.rectangle([(0, 0), (TARGET_W, 8)], fill=COLORS[0])
    draw.rectangle([(0, TARGET_H-8), (TARGET_W, TARGET_H)], fill=COLORS[0])

    font_title = _get_font(30, bold=True)
    title_text = "📋 ملخص المحاضرة"
    try:
        bbox = font_title.getbbox(title_text)
        tw = bbox[2] - bbox[0]
    except:
        tw = len(title_text) * 18
    tx = (TARGET_W - tw) // 2
    draw.text((tx, 35), title_text, fill=(44, 62, 80), font=font_title)

    y = 90
    for i, kw in enumerate(all_keywords[:12]):
        color = COLORS[i % len(COLORS)]
        font_kw = _get_font(18, bold=True)
        try:
            bbox = font_kw.getbbox(kw)
            kw_w = bbox[2] - bbox[0]
        except:
            kw_w = len(kw) * 10
        
        col = i % 3
        row = i // 3
        x = 50 + col * 250
        y_pos = y + row * 50
        
        draw.rounded_rectangle(
            [(x - 10, y_pos - 5), (x + kw_w + 10, y_pos + 28)],
            radius=8, fill=(*color, 20), outline=color, width=2
        )
        draw.text((x, y_pos), kw, fill=color, font=font_kw)

    font_thanks = _get_font(26, bold=True)
    thanks_text = "🙏 شكراً لحسن استماعكم"
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
    lecture_title: str,
    all_keywords: list,
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
    title_path = _draw_title_slide(lecture_title)
    tmp_files.append(title_path)
    segments.append({"img": title_path, "audio": None, "audio_start": 0.0, "dur": 4.0})
    total_secs += 4.0

    # 3. خريطة
    section_titles = [s.get("title", f"القسم {i+1}") for i, s in enumerate(sections)]
    map_path = _draw_sections_map(section_titles)
    tmp_files.append(map_path)
    segments.append({"img": map_path, "audio": None, "audio_start": 0.0, "dur": 5.0})
    total_secs += 5.0

    # 4. أقسام
    for sec_idx, (section, audio_info) in enumerate(zip(sections, audio_results)):
        title_path = _draw_section_title_card(section.get("title", f"القسم {sec_idx+1}"), sec_idx)
        tmp_files.append(title_path)
        segments.append({"img": title_path, "audio": None, "audio_start": 0.0, "dur": 3.0})
        total_secs += 3.0

        keywords = section.get("keywords", ["مفهوم"])
        kw_images = section.get("_keyword_images", [])
        audio_bytes = audio_info.get("audio")
        total_dur = max(float(audio_info.get("duration", 45)), 5.0)
        
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
        accum_kw = []
        accum_img = []
        
        for kw_idx in range(n_kw):
            accum_kw.append(keywords[kw_idx])
            img_bytes = kw_images[kw_idx] if kw_idx < len(kw_images) else None
            accum_img.append(img_bytes)
            
            board_path = _draw_accumulating_board(
                accumulated_keywords=accum_kw.copy(),
                accumulated_images=accum_img.copy(),
                current_idx=kw_idx,
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

    # 5. خاتمة
    final_path = _draw_final_summary(all_keywords)
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
    
    lecture_title = lecture_data.get("title", "المحاضرة التعليمية")
    all_keywords = lecture_data.get("all_keywords", [])

    for section in sections:
        if "keywords" not in section or not section["keywords"]:
            section["keywords"] = ["مفهوم", "تعريف", "شرح", "تحليل"]
        if "_keyword_images" not in section:
            section["_keyword_images"] = [None] * len(section.get("keywords", []))

    segments, tmp_files, total_video_secs = await loop.run_in_executor(
        None, _build_segment_list, sections, audio_results, lecture_title, all_keywords
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
