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
        return get_display(arabic_reshaper.reshape(text))
    except Exception:
        return text


def _draw_intro_slide(lecture_data: dict, sections: list, is_arabic: bool) -> str:
    img_fd, img_path = tempfile.mkstemp(prefix="intro_", suffix=".jpg")
    os.close(img_fd)

    img = PILImage.new("RGB", (TARGET_W, TARGET_H), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    # شريط علوي
    draw.rectangle([(0, 0), (TARGET_W, 6)], fill=COLORS[0])

    # عنوان
    raw_title = lecture_data.get("title", "المحاضرة التعليمية")
    title_txt = _prepare_text(raw_title, is_arabic)
    title_font = _get_font(36, bold=True, arabic=is_arabic)
    
    try:
        bbox = draw.textbbox((0, 0), title_txt, font=title_font)
        tw = bbox[2] - bbox[0]
    except Exception:
        tw = len(title_txt) * 20
    
    x = (TARGET_W - tw) // 2
    draw.text((x + 2, TARGET_H//2 - 30), title_txt, fill=(220, 220, 220), font=title_font)
    draw.text((x, TARGET_H//2 - 32), title_txt, fill=(44, 62, 80), font=title_font)

    # عدد الأقسام
    n_sec = len(sections)
    info_txt = f"📚 {n_sec} أقسام"
    info_disp = _prepare_text(info_txt, is_arabic)
    info_font = _get_font(18, arabic=is_arabic)
    try:
        bbox = draw.textbbox((0, 0), info_disp, font=info_font)
        tw = bbox[2] - bbox[0]
    except Exception:
        tw = len(info_disp) * 10
    x = (TARGET_W - tw) // 2
    draw.text((x, TARGET_H//2 + 30), info_disp, fill=(127, 140, 141), font=info_font)

    img.save(img_path, "JPEG", quality=90)
    return img_path


def _draw_section_title_card(section: dict, idx: int, total: int, is_arabic: bool) -> str:
    img_fd, img_path = tempfile.mkstemp(prefix=f"sec_title_{idx}_", suffix=".jpg")
    os.close(img_fd)

    color = COLORS[idx % len(COLORS)]
    img = PILImage.new("RGB", (TARGET_W, TARGET_H), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    draw.rectangle([(0, 0), (TARGET_W, 6)], fill=color)

    # رقم القسم
    cx, cy, cr = TARGET_W // 2, TARGET_H // 2 - 40, 40
    draw.ellipse([cx - cr, cy - cr, cx + cr, cy + cr], fill=color)
    num_str = str(idx + 1)
    num_font = _get_font(36, bold=True)
    draw.text((cx - 10, cy - 20), num_str, fill=(255, 255, 255), font=num_font)

    # عنوان القسم
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

    img.save(img_path, "JPEG", quality=90)
    return img_path


def _draw_content_slide(
    image_bytes: bytes | None,
    keyword: str,
    kw_idx: int,
    total_kw: int,
    section_title: str,
    section_idx: int,
    is_arabic: bool,
) -> str:
    """شريحة محتوى بسيطة: صورة + كلمة مفتاحية"""
    fd, path = tempfile.mkstemp(prefix="content_", suffix=".jpg")
    os.close(fd)

    color = COLORS[section_idx % len(COLORS)]
    img = PILImage.new("RGB", (TARGET_W, TARGET_H), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    # شريط علوي
    draw.rectangle([(0, 0), (TARGET_W, 5)], fill=color)

    # عنوان القسم
    header_disp = _prepare_text(section_title[:35], is_arabic)
    header_font = _get_font(16, bold=True, arabic=is_arabic)
    try:
        bbox = draw.textbbox((0, 0), header_disp, font=header_font)
        hw = bbox[2] - bbox[0]
    except Exception:
        hw = len(header_disp) * 9
    hx = (TARGET_W - hw) // 2
    draw.text((hx, 15), header_disp, fill=(44, 62, 80), font=header_font)

    # صورة
    img_y = 50
    if image_bytes:
        try:
            pil_img = PILImage.open(io.BytesIO(image_bytes)).convert("RGB")
            iw, ih = pil_img.size
            max_w, max_h = 500, 280
            scale = min(max_w / iw, max_h / ih)
            nw, nh = int(iw * scale), int(ih * scale)
            pil_img = pil_img.resize((nw, nh), PILImage.LANCZOS)
            
            px = (TARGET_W - nw) // 2
            py = img_y + (max_h - nh) // 2
            
            draw.rounded_rectangle(
                [(px - 4, py - 4), (px + nw + 4, py + nh + 4)],
                radius=8, outline=color, width=3
            )
            img.paste(pil_img, (px, py))
        except Exception:
            pass

    # الكلمة المفتاحية
    kw_disp = _prepare_text(keyword, is_arabic)
    kw_font = _get_font(28, bold=True, arabic=is_arabic)
    try:
        bbox = draw.textbbox((0, 0), kw_disp, font=kw_font)
        kww = bbox[2] - bbox[0]
    except Exception:
        kww = len(kw_disp) * 16
    
    kw_x = (TARGET_W - kww) // 2
    kw_y = 360
    draw.text((kw_x + 2, kw_y + 2), kw_disp, fill=(220, 220, 220), font=kw_font)
    draw.text((kw_x, kw_y), kw_disp, fill=color, font=kw_font)

    # مؤشر التقدم
    dot_y = TARGET_H - 30
    dot_r = 5
    dot_gap = 22
    total_w = total_kw * dot_gap
    start_x = (TARGET_W - total_w) // 2
    
    for i in range(total_kw):
        dx = start_x + i * dot_gap
        dot_color = color if i <= kw_idx else (220, 220, 220)
        r = dot_r if i <= kw_idx else dot_r - 2
        draw.ellipse([(dx - r, dot_y - r), (dx + r, dot_y + r)], fill=dot_color)

    # علامة مائية
    wm_font = _get_font(11)
    wm_disp = _prepare_text(WATERMARK, is_arabic)
    try:
        bbox = draw.textbbox((0, 0), wm_disp, font=wm_font)
        ww = bbox[2] - bbox[0]
    except Exception:
        ww = len(wm_disp) * 6
    draw.text((TARGET_W - ww - 15, TARGET_H - 18), wm_disp, fill=(180, 180, 180), font=wm_font)

    img.save(path, "JPEG", quality=92)
    return path


def _draw_final_summary(sections: list, lecture_data: dict, is_arabic: bool) -> str:
    img_fd, img_path = tempfile.mkstemp(prefix="summary_", suffix=".jpg")
    os.close(img_fd)

    img = PILImage.new("RGB", (TARGET_W, TARGET_H), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    draw.rectangle([(0, 0), (TARGET_W, 6)], fill=COLORS[0])

    # عنوان
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

    # رسالة ختامية
    thanks_disp = _prepare_text("🎓 تم بحمد الله", is_arabic)
    thanks_font = _get_font(22, bold=True, arabic=is_arabic)
    try:
        bbox = draw.textbbox((0, 0), thanks_disp, font=thanks_font)
        tw = bbox[2] - bbox[0]
    except Exception:
        tw = len(thanks_disp) * 13
    tx = (TARGET_W - tw) // 2
    draw.text((tx, TARGET_H - 50), thanks_disp, fill=COLORS[0], font=thanks_font)

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

    # مقدمة
    intro_path = _draw_intro_slide(lecture_data, sections, is_arabic)
    tmp_files.append(intro_path)
    segments.append({"img": intro_path, "audio": None, "audio_start": 0.0, "dur": 4.0})
    total_secs += 4.0

    # الأقسام
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
            img_bytes = kw_images[kw_idx] if kw_idx < len(kw_images) else None
            content_path = _draw_content_slide(
                image_bytes=img_bytes,
                keyword=keywords[kw_idx],
                kw_idx=kw_idx,
                total_kw=n_kw,
                section_title=sec_title,
                section_idx=sec_idx,
                is_arabic=is_arabic,
            )
            tmp_files.append(content_path)
            
            segments.append({
                "img": content_path,
                "audio": apath,
                "audio_start": kw_idx * kw_dur,
                "dur": kw_dur,
            })
            total_secs += kw_dur

    # ملخص نهائي
    final_path = _draw_final_summary(sections, lecture_data, is_arabic)
    tmp_files.append(final_path)
    segments.append({"img": final_path, "audio": None, "audio_start": 0.0, "dur": 5.0})
    total_secs += 5.0

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
