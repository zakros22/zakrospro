# -*- coding: utf-8 -*-
"""
Video Creator Module - Osmosis Style
Features:
- Whiteboard style slides
- Welcome slide with logo
- Title slide
- Sections map
- Section title cards
- Accumulating content slides (image + keywords)
- Final summary slide
"""

import asyncio
import io
import os
import subprocess
import tempfile
from PIL import Image as PILImage, ImageDraw, ImageFont

# ═══════════════════════════════════════════════════════════════════════════════
# Settings
# ═══════════════════════════════════════════════════════════════════════════════

TARGET_W, TARGET_H = 854, 480
WATERMARK = "@zakros_probot"

# Osmosis Colors
COLORS = [
    (231, 76, 126),   # Pink
    (52, 152, 219),   # Blue
    (46, 204, 113),   # Green
    (155, 89, 182),   # Purple
    (230, 126, 34),   # Orange
]

def estimate_encoding_seconds(total_video_seconds: float) -> float:
    """Estimate encoding time"""
    return max(20.0, total_video_seconds * 0.6)


# ═══════════════════════════════════════════════════════════════════════════════
# Font Loading
# ═══════════════════════════════════════════════════════════════════════════════

def _get_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """Load font with Arabic support"""
    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ]
    for path in font_paths:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except:
                pass
    return ImageFont.load_default()


def _prepare_arabic(text: str) -> str:
    """Prepare Arabic text for display"""
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


def _get_text_width(text: str, font: ImageFont.FreeTypeFont) -> int:
    """Get text width"""
    try:
        bbox = font.getbbox(text)
        return bbox[2] - bbox[0]
    except:
        return len(text) * (font.size // 2)


def _wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list:
    """Wrap text to multiple lines"""
    words = text.split()
    lines = []
    current = []
    for w in words:
        current.append(w)
        line = ' '.join(current)
        if _get_text_width(line, font) > max_width:
            current.pop()
            if current:
                lines.append(' '.join(current))
            current = [w]
    if current:
        lines.append(' '.join(current))
    return lines if lines else [text]


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Welcome Slide
# ═══════════════════════════════════════════════════════════════════════════════

def _draw_welcome() -> str:
    """Welcome slide with logo"""
    fd, path = tempfile.mkstemp(prefix="welcome_", suffix=".jpg")
    os.close(fd)

    img = PILImage.new("RGB", (TARGET_W, TARGET_H), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    # Top and bottom bars
    draw.rectangle([(0, 0), (TARGET_W, 8)], fill=COLORS[0])
    draw.rectangle([(0, TARGET_H-8), (TARGET_W, TARGET_H)], fill=COLORS[0])

    # Logo frame
    frame_x, frame_y = 150, 100
    frame_w, frame_h = 550, 200
    draw.rounded_rectangle(
        [(frame_x, frame_y), (frame_x + frame_w, frame_y + frame_h)],
        radius=25, outline=COLORS[0], width=8
    )

    # Logo text
    font_logo = _get_font(60, bold=True)
    logo_w = _get_text_width(WATERMARK, font_logo)
    logo_x = (TARGET_W - logo_w) // 2
    logo_y = frame_y + 60
    draw.text((logo_x + 4, logo_y + 4), WATERMARK, fill=(200, 200, 200), font=font_logo)
    draw.text((logo_x, logo_y), WATERMARK, fill=COLORS[0], font=font_logo)

    # Welcome text
    font_welcome = _get_font(36, bold=True)
    welcome_text = _prepare_arabic("أهلاً ومرحباً بكم")
    welcome_w = _get_text_width(welcome_text, font_welcome)
    welcome_x = (TARGET_W - welcome_w) // 2
    welcome_y = frame_y + frame_h + 40
    draw.text((welcome_x + 3, welcome_y + 3), welcome_text, fill=(200, 200, 200), font=font_welcome)
    draw.text((welcome_x, welcome_y), welcome_text, fill=(44, 62, 80), font=font_welcome)

    img.save(path, "JPEG", quality=90)
    return path


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Title Slide
# ═══════════════════════════════════════════════════════════════════════════════

def _draw_title(title: str) -> str:
    """Title slide"""
    fd, path = tempfile.mkstemp(prefix="title_", suffix=".jpg")
    os.close(fd)

    img = PILImage.new("RGB", (TARGET_W, TARGET_H), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    draw.rectangle([(0, 0), (TARGET_W, 6)], fill=COLORS[1])

    font_title = _get_font(38, bold=True)
    title_text = _prepare_arabic(title)
    lines = _wrap_text(title_text, font_title, TARGET_W - 80)

    y = TARGET_H//2 - (len(lines) * 45)//2
    for line in lines:
        w = _get_text_width(line, font_title)
        x = (TARGET_W - w) // 2
        draw.text((x + 3, y + 3), line, fill=(200, 200, 200), font=font_title)
        draw.text((x, y), line, fill=(44, 62, 80), font=font_title)
        y += 45

    # Watermark
    font_wm = _get_font(14, bold=True)
    wm_w = _get_text_width(WATERMARK, font_wm)
    draw.text((TARGET_W - wm_w - 25, TARGET_H - 35), WATERMARK, fill=COLORS[1], font=font_wm)

    img.save(path, "JPEG", quality=90)
    return path


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Sections Map
# ═══════════════════════════════════════════════════════════════════════════════

def _draw_map(titles: list) -> str:
    """Sections map slide"""
    fd, path = tempfile.mkstemp(prefix="map_", suffix=".jpg")
    os.close(fd)

    img = PILImage.new("RGB", (TARGET_W, TARGET_H), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    draw.rectangle([(0, 0), (TARGET_W, 6)], fill=COLORS[2])

    font_title = _get_font(30, bold=True)
    map_title = _prepare_arabic("📋 خريطة المحاضرة")
    w = _get_text_width(map_title, font_title)
    x = (TARGET_W - w) // 2
    draw.text((x, 30), map_title, fill=COLORS[2], font=font_title)

    y = 90
    font_sec = _get_font(20, bold=True)
    font_num = _get_font(15, bold=True)

    for i, t in enumerate(titles):
        color = COLORS[i % len(COLORS)]
        draw.ellipse([(30, y), (52, y + 22)], fill=color)
        draw.text((41, y + 3), str(i + 1), fill=(255, 255, 255), font=font_num)
        draw.text((70, y), _prepare_arabic(t[:35]), fill=(44, 62, 80), font=font_sec)
        y += 55

    img.save(path, "JPEG", quality=90)
    return path


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Section Title Card
# ═══════════════════════════════════════════════════════════════════════════════

def _draw_section_title(title: str, idx: int) -> str:
    """Section title card"""
    fd, path = tempfile.mkstemp(prefix="sec_title_", suffix=".jpg")
    os.close(fd)

    color = COLORS[idx % len(COLORS)]
    img = PILImage.new("RGB", (TARGET_W, TARGET_H), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    draw.rectangle([(0, 0), (TARGET_W, 6)], fill=color)

    # Number circle
    cx, cy, cr = TARGET_W // 2, TARGET_H // 2 - 40, 45
    draw.ellipse([cx - cr, cy - cr, cx + cr, cy + cr], fill=color)

    font_num = _get_font(40, bold=True)
    num_str = str(idx + 1)
    nw = _get_text_width(num_str, font_num)
    draw.text((cx - nw//2, cy - 22), num_str, fill=(255, 255, 255), font=font_num)

    # Title
    font_title = _get_font(32, bold=True)
    title_text = _prepare_arabic(title)
    tw = _get_text_width(title_text, font_title)
    x = (TARGET_W - tw) // 2
    draw.text((x, cy + cr + 35), title_text, fill=(44, 62, 80), font=font_title)

    # Watermark
    font_wm = _get_font(13, bold=True)
    wm_w = _get_text_width(WATERMARK, font_wm)
    draw.text((TARGET_W - wm_w - 25, TARGET_H - 30), WATERMARK, fill=color, font=font_wm)

    img.save(path, "JPEG", quality=90)
    return path


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Content Slide (Whiteboard with image and accumulating keywords)
# ═══════════════════════════════════════════════════════════════════════════════

def _draw_content(
    image_bytes: bytes,
    keywords: list,
    section_title: str,
    section_idx: int,
    current_kw: int,
    total_kw: int,
) -> str:
    """Content slide with image and accumulating keywords"""
    fd, path = tempfile.mkstemp(prefix="content_", suffix=".jpg")
    os.close(fd)

    color = COLORS[section_idx % len(COLORS)]
    img = PILImage.new("RGB", (TARGET_W, TARGET_H), (248, 248, 250))
    draw = ImageDraw.Draw(img)

    # Top bar
    draw.rectangle([(0, 0), (TARGET_W, 6)], fill=color)

    # Section title header
    font_header = _get_font(18, bold=True)
    header_text = _prepare_arabic(section_title[:40])
    hw = _get_text_width(header_text, font_header)
    hx = (TARGET_W - hw) // 2
    draw.text((hx, 15), header_text, fill=(44, 62, 80), font=font_header)
    draw.rectangle([(hx, 38), (hx + hw, 40)], fill=color)

    # Main image
    if image_bytes:
        try:
            pil_img = PILImage.open(io.BytesIO(image_bytes)).convert("RGB")
            iw, ih = pil_img.size
            max_w, max_h = 500, 250
            scale = min(max_w / iw, max_h / ih)
            nw, nh = int(iw * scale), int(ih * scale)
            pil_img = pil_img.resize((nw, nh), PILImage.LANCZOS)

            px = (TARGET_W - nw) // 2
            py = 50 + (max_h - nh) // 2

            draw.rounded_rectangle(
                [(px - 5, py - 5), (px + nw + 5, py + nh + 5)],
                radius=10, outline=color, width=4
            )
            img.paste(pil_img, (px, py))
        except:
            pass

    # Keywords (accumulating)
    font_kw = _get_font(20, bold=True)
    visible_kw = keywords[:current_kw + 1]

    for i, kw in enumerate(visible_kw):
        kw_color = COLORS[i % len(COLORS)]
        kw_text = _prepare_arabic(kw)
        kw_w = _get_text_width(kw_text, font_kw)

        col = i % 2
        row = i // 2
        kx = 100 + col * 350
        ky = 330 + row * 40

        draw.rounded_rectangle(
            [(kx - 10, ky - 5), (kx + kw_w + 10, ky + 30)],
            radius=8, fill=(*kw_color, 20), outline=kw_color, width=2
        )
        draw.text((kx, ky), kw_text, fill=kw_color, font=font_kw)

    # Progress dots
    dot_y = TARGET_H - 30
    dot_r = 6
    dot_gap = 25
    total_w = total_kw * dot_gap
    start_x = (TARGET_W - total_w) // 2

    for i in range(total_kw):
        dx = start_x + i * dot_gap
        dot_color = color if i <= current_kw else (200, 200, 200)
        r = dot_r if i <= current_kw else dot_r - 2
        draw.ellipse([(dx - r, dot_y - r), (dx + r, dot_y + r)], fill=dot_color)

    # Watermark
    font_wm = _get_font(12, bold=True)
    wm_w = _get_text_width(WATERMARK, font_wm)
    draw.text((TARGET_W - wm_w - 20, TARGET_H - 25), WATERMARK, fill=color, font=font_wm)

    img.save(path, "JPEG", quality=92)
    return path


# ═══════════════════════════════════════════════════════════════════════════════
# 6. Final Summary Slide
# ═══════════════════════════════════════════════════════════════════════════════

def _draw_summary(all_keywords: list) -> str:
    """Final summary slide"""
    fd, path = tempfile.mkstemp(prefix="summary_", suffix=".jpg")
    os.close(fd)

    img = PILImage.new("RGB", (TARGET_W, TARGET_H), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    draw.rectangle([(0, 0), (TARGET_W, 8)], fill=COLORS[0])
    draw.rectangle([(0, TARGET_H-8), (TARGET_W, TARGET_H)], fill=COLORS[0])

    font_title = _get_font(30, bold=True)
    title_text = _prepare_arabic("📋 ملخص المحاضرة")
    tw = _get_text_width(title_text, font_title)
    tx = (TARGET_W - tw) // 2
    draw.text((tx, 35), title_text, fill=(44, 62, 80), font=font_title)

    y = 90
    font_kw = _get_font(18, bold=True)

    for i, kw in enumerate(all_keywords[:12]):
        color = COLORS[i % len(COLORS)]
        kw_text = _prepare_arabic(kw)
        kw_w = _get_text_width(kw_text, font_kw)

        col = i % 3
        row = i // 3
        cx = 50 + col * 250
        cy = y + row * 45

        draw.rounded_rectangle(
            [(cx - 10, cy - 5), (cx + kw_w + 10, cy + 28)],
            radius=8, fill=(*color, 20), outline=color, width=2
        )
        draw.text((cx, cy), kw_text, fill=color, font=font_kw)

    font_thanks = _get_font(26, bold=True)
    thanks_text = _prepare_arabic("🙏 شكراً لحسن استماعكم")
    tw3 = _get_text_width(thanks_text, font_thanks)
    tx3 = (TARGET_W - tw3) // 2
    draw.text((tx3 + 3, TARGET_H - 65), thanks_text, fill=(200, 200, 200), font=font_thanks)
    draw.text((tx3, TARGET_H - 68), thanks_text, fill=COLORS[0], font=font_thanks)

    img.save(path, "JPEG", quality=90)
    return path


# ═══════════════════════════════════════════════════════════════════════════════
# FFmpeg Helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _ffmpeg_segment(img_path: str, duration: float, audio_path: str, audio_start: float, out_path: str):
    """Encode single segment"""
    dur_str = f"{duration:.3f}"
    audio_args = ["-ss", f"{audio_start:.3f}", "-t", dur_str, "-i", audio_path] if audio_path else ["-f", "lavfi", "-i", "anullsrc"]
    cmd = [
        "ffmpeg", "-y", "-loop", "1", "-t", dur_str, "-i", img_path, *audio_args,
        "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p", "-r", "15",
        "-vf", "scale=854:480:force_original_aspect_ratio=decrease,pad=854:480:(ow-iw)/2:(oh-ih)/2",
        "-map", "0:v", "-map", "1:a", "-c:a", "aac", "-b:a", "96k", "-t", dur_str, out_path
    ]
    subprocess.run(cmd, capture_output=True)


def _ffmpeg_concat(segments: list, output_path: str):
    """Concatenate segments"""
    fd, list_path = tempfile.mkstemp(suffix=".txt")
    os.close(fd)
    with open(list_path, "w") as f:
        for p in segments:
            f.write(f"file '{p}'\n")
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list_path, "-c", "copy", output_path], capture_output=True)
    os.remove(list_path)


# ═══════════════════════════════════════════════════════════════════════════════
# Build Video
# ═══════════════════════════════════════════════════════════════════════════════

def _build_segments(sections: list, audio_results: list, lecture_data: dict):
    """Build all video segments"""
    segments = []
    tmp_files = []
    total_secs = 0.0

    title = lecture_data.get("title", "المحاضرة")
    all_keywords = lecture_data.get("all_keywords", [])

    # 1. Welcome
    p = _draw_welcome()
    tmp_files.append(p)
    segments.append({"img": p, "audio": None, "audio_start": 0, "dur": 3.5})
    total_secs += 3.5

    # 2. Title
    p = _draw_title(title)
    tmp_files.append(p)
    segments.append({"img": p, "audio": None, "audio_start": 0, "dur": 4})
    total_secs += 4

    # 3. Map
    section_titles = [s.get("title", "") for s in sections]
    p = _draw_map(section_titles)
    tmp_files.append(p)
    segments.append({"img": p, "audio": None, "audio_start": 0, "dur": 5})
    total_secs += 5

    # 4. Sections
    for sec_idx, (sec, aud) in enumerate(zip(sections, audio_results)):
        # Section title
        p = _draw_section_title(sec.get("title", f"قسم {sec_idx+1}"), sec_idx)
        tmp_files.append(p)
        segments.append({"img": p, "audio": None, "audio_start": 0, "dur": 3})
        total_secs += 3

        keywords = sec.get("keywords", ["مفهوم"])
        image_bytes = sec.get("_image_bytes")
        audio_bytes = aud.get("audio")
        total_dur = max(aud.get("duration", 30), 5)
        kw_dur = total_dur / len(keywords)

        apath = None
        if audio_bytes:
            afd, apath = tempfile.mkstemp(suffix=".mp3")
            os.close(afd)
            with open(apath, "wb") as f:
                f.write(audio_bytes)
            tmp_files.append(apath)

        # Content slides (accumulating)
        for kw_idx in range(len(keywords)):
            p = _draw_content(
                image_bytes=image_bytes,
                keywords=keywords,
                section_title=sec.get("title", ""),
                section_idx=sec_idx,
                current_kw=kw_idx,
                total_kw=len(keywords),
            )
            tmp_files.append(p)
            segments.append({
                "img": p,
                "audio": apath,
                "audio_start": kw_idx * kw_dur,
                "dur": kw_dur,
            })
            total_secs += kw_dur

    # 5. Summary
    p = _draw_summary(all_keywords)
    tmp_files.append(p)
    segments.append({"img": p, "audio": None, "audio_start": 0, "dur": 6})
    total_secs += 6

    return segments, tmp_files, total_secs


def _encode_all(segments: list, output_path: str):
    """Encode all segments"""
    seg_paths = []
    try:
        for i, seg in enumerate(segments):
            fd, p = tempfile.mkstemp(prefix=f"seg_{i}_", suffix=".mp4")
            os.close(fd)
            seg_paths.append(p)
            _ffmpeg_segment(seg["img"], seg["dur"], seg["audio"], seg["audio_start"], p)
        _ffmpeg_concat(seg_paths, output_path)
    finally:
        for p in seg_paths:
            try:
                os.remove(p)
            except:
                pass


# ═══════════════════════════════════════════════════════════════════════════════
# Main Function
# ═══════════════════════════════════════════════════════════════════════════════

async def create_video_from_sections(
    sections: list,
    audio_results: list,
    lecture_data: dict,
    output_path: str,
    dialect: str = "msa",
    progress_cb=None,
) -> float:
    """Create full video from sections"""
    loop = asyncio.get_event_loop()

    # Ensure keywords exist
    for sec in sections:
        if "keywords" not in sec or not sec["keywords"]:
            sec["keywords"] = ["مفهوم"]
        if "_image_bytes" not in sec:
            sec["_image_bytes"] = None

    segments, tmp_files, total_secs = await loop.run_in_executor(
        None, _build_segments, sections, audio_results, lecture_data
    )

    if not segments:
        raise RuntimeError("No segments generated")

    await loop.run_in_executor(None, _encode_all, segments, output_path)

    # Cleanup temp files
    for p in tmp_files:
        try:
            os.remove(p)
        except:
            pass

    return total_secs
