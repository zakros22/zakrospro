#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import asyncio
import io
import os
import subprocess
import tempfile
from typing import Callable, Awaitable
from PIL import Image as PILImage, ImageDraw, ImageFont

# ══════════════════════════════════════════════════════════════════════════════
#  الإعدادات
# ══════════════════════════════════════════════════════════════════════════════
TARGET_W, TARGET_H = 854, 480
WATERMARK = "@zakros_probot"

# الخطوط
FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_REG = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
_FONTS_DIR = os.path.join(os.path.dirname(__file__), "fonts")
FONT_AR_BOLD = os.path.join(_FONTS_DIR, "Amiri-Bold.ttf")
FONT_AR_REG = os.path.join(_FONTS_DIR, "Amiri-Regular.ttf")

# إعدادات التشفير
_ENC_FACTOR = 0.4
_MIN_ENC_SEC = 10.0

# مدد الشرائح
_INTRO_DUR = 6.0
_SECTION_TITLE_DUR = 3.0
_SUMMARY_DUR = 6.0

# ألوان
ACCENT_COLORS = [
    (100, 180, 255), (100, 220, 160), (255, 180, 80),
    (220, 120, 255), (255, 120, 120), (80, 220, 220),
    (255, 200, 100), (160, 255, 160),
]


def estimate_encoding_seconds(total_video_seconds: float) -> float:
    return max(_MIN_ENC_SEC, total_video_seconds * _ENC_FACTOR)


def _prepare_arabic_text(text: str) -> str:
    if not text:
        return text
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
        return get_display(arabic_reshaper.reshape(text))
    except:
        return text


def _get_font(size: int, bold: bool = False, arabic: bool = False):
    if arabic:
        path = FONT_AR_BOLD if bold else FONT_AR_REG
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except:
                pass
    path = FONT_BOLD if bold else FONT_REG
    try:
        return ImageFont.truetype(path, size)
    except:
        return ImageFont.load_default()


def _draw_text_centered(draw, text: str, y: int, font, color, is_arabic: bool = False):
    display = _prepare_arabic_text(text) if is_arabic else text
    try:
        bbox = draw.textbbox((0, 0), display, font=font)
        tw = bbox[2] - bbox[0]
    except:
        tw = len(display) * (font.size // 2)
    x = max((TARGET_W - tw) // 2, 10)
    draw.text((x+2, y+2), display, fill=(0,0,0,140), font=font)
    draw.text((x, y), display, fill=color, font=font)


def _gradient_bg(c1, c2):
    bg = PILImage.new("RGB", (TARGET_W, TARGET_H), c1)
    draw = ImageDraw.Draw(bg)
    for y in range(TARGET_H):
        t = y / TARGET_H
        r = int(c1[0]*(1-t) + c2[0]*t)
        g = int(c1[1]*(1-t) + c2[1]*t)
        b = int(c1[2]*(1-t) + c2[2]*t)
        draw.line([(0,y), (TARGET_W,y)], fill=(r,g,b))
    return bg


# ══════════════════════════════════════════════════════════════════════════════
#  شريحة المقدمة
# ══════════════════════════════════════════════════════════════════════════════

def _draw_intro_slide(lecture_data: dict, sections: list, is_arabic: bool) -> str:
    fd, path = tempfile.mkstemp(prefix="intro_", suffix=".jpg")
    os.close(fd)
    
    bg = _gradient_bg((10, 20, 50), (5, 40, 70))
    draw = ImageDraw.Draw(bg)
    
    draw.rectangle([(0, 0), (TARGET_W, 5)], fill=(220, 170, 30))
    
    title = lecture_data.get("title", "المحاضرة" if is_arabic else "Lecture")
    font = _get_font(26, bold=True, arabic=is_arabic)
    _draw_text_centered(draw, title, 20, font, (255, 220, 80), is_arabic)
    
    subtitle = "خريطة المحاضرة" if is_arabic else "Lecture Map"
    font2 = _get_font(16, arabic=is_arabic)
    _draw_text_centered(draw, subtitle, 65, font2, (180, 200, 230), is_arabic)
    
    draw.rectangle([(40, 85), (TARGET_W-40, 87)], fill=(220, 170, 30))
    
    # عرض الأقسام
    y = 110
    for i, sec in enumerate(sections[:6]):
        accent = ACCENT_COLORS[i % len(ACCENT_COLORS)]
        sec_title = sec.get("title", f"قسم {i+1}")[:40]
        display = _prepare_arabic_text(f"{i+1}. {sec_title}") if is_arabic else f"{i+1}. {sec_title}"
        font3 = _get_font(15, arabic=is_arabic)
        draw.text((50, y), display, fill=accent, font=font3)
        y += 55
    
    # علامة مائية
    wm_font = _get_font(12)
    draw.text((TARGET_W//2 - 50, TARGET_H-25), WATERMARK, fill=(140, 160, 190), font=wm_font)
    
    bg.save(path, "JPEG", quality=85)
    return path


# ══════════════════════════════════════════════════════════════════════════════
#  شريحة عنوان القسم
# ══════════════════════════════════════════════════════════════════════════════

def _draw_section_title_card(section: dict, idx: int, total: int, is_arabic: bool) -> str:
    fd, path = tempfile.mkstemp(prefix=f"sec_title_{idx}_", suffix=".jpg")
    os.close(fd)
    
    accent = ACCENT_COLORS[idx % len(ACCENT_COLORS)]
    bg = _gradient_bg((8, 15, 40), tuple(max(0, c-60) for c in accent))
    draw = ImageDraw.Draw(bg)
    
    draw.rectangle([(0, 0), (TARGET_W, 6)], fill=accent)
    draw.rectangle([(0, TARGET_H-6), (TARGET_W, TARGET_H)], fill=accent)
    
    # رقم القسم
    cx, cy, cr = TARGET_W//2, TARGET_H//2 - 60, 45
    draw.ellipse([cx-cr, cy-cr, cx+cr, cy+cr], fill=accent)
    
    num_font = _get_font(40, bold=True)
    num_str = str(idx + 1)
    bbox = draw.textbbox((0,0), num_str, font=num_font)
    nw, nh = bbox[2]-bbox[0], bbox[3]-bbox[1]
    draw.text((cx-nw//2, cy-nh//2), num_str, fill=(10,15,35), font=num_font)
    
    # "القسم"
    label = f"القسم {idx+1}" if is_arabic else f"Section {idx+1}"
    label_font = _get_font(18, arabic=is_arabic)
    _draw_text_centered(draw, label, cy+cr+10, label_font, (200,220,255), is_arabic)
    
    # عنوان القسم
    title = section.get("title", f"قسم {idx+1}")[:50]
    title_font = _get_font(28, bold=True, arabic=is_arabic)
    _draw_text_centered(draw, title, cy+cr+45, title_font, accent, is_arabic)
    
    # علامة مائية
    wm_font = _get_font(12)
    draw.text((TARGET_W//2 - 50, TARGET_H-25), WATERMARK, fill=(140,160,190), font=wm_font)
    
    bg.save(path, "JPEG", quality=85)
    return path


# ══════════════════════════════════════════════════════════════════════════════
#  شريحة المحتوى - صورة واحدة مع شرح
# ══════════════════════════════════════════════════════════════════════════════

def _draw_content_slide(image_bytes: bytes, section: dict, idx: int, is_arabic: bool) -> str:
    """شريحة المحتوى: صورة واحدة كبيرة تغطي كل القسم."""
    fd, path = tempfile.mkstemp(prefix=f"content_{idx}_", suffix=".jpg")
    os.close(fd)
    
    accent = ACCENT_COLORS[idx % len(ACCENT_COLORS)]
    
    # خلفية الفصل
    canvas = PILImage.new("RGB", (TARGET_W, TARGET_H), (22, 35, 55))
    draw = ImageDraw.Draw(canvas)
    
    # إطار السبورة
    BM, FRAME = 10, 6
    BX1, BY1 = BM+FRAME, BM+FRAME
    BX2, BY2 = TARGET_W-BM-FRAME, TARGET_H-BM-FRAME
    
    # ظل
    draw.rounded_rectangle([(BX1+4, BY1+4), (BX2+4, BY2+4)], radius=6, fill=(40, 30, 20))
    # إطار
    draw.rounded_rectangle([(BX1, BY1), (BX2, BY2)], radius=6, fill=(80, 60, 40))
    # سبورة
    draw.rounded_rectangle([(BX1+3, BY1+3), (BX2-3, BY2-3)], radius=4, fill=(252, 250, 240))
    
    # شريط عنوان القسم
    title = section.get("title", f"قسم {idx+1}")[:40]
    display_title = _prepare_arabic_text(title) if is_arabic else title
    title_font = _get_font(18, bold=True, arabic=is_arabic)
    
    draw.rectangle([(BX1+3, BY1+3), (BX2-3, BY1+35)], fill=accent)
    try:
        tb = draw.textbbox((0,0), display_title, font=title_font)
        tw = tb[2] - tb[0]
    except:
        tw = len(display_title) * 10
    tx = (TARGET_W - tw) // 2
    draw.text((tx, BY1+8), display_title, fill=(255,255,255), font=title_font)
    
    # منطقة الصورة (تأخذ معظم المساحة)
    IMG_TOP = BY1 + 40
    IMG_BOT = BY2 - 15
    IMG_H = IMG_BOT - IMG_TOP
    
    if image_bytes:
        try:
            img = PILImage.open(io.BytesIO(image_bytes)).convert("RGB")
            iw, ih = img.size
            scale = min((BX2-BX1-20)/iw, IMG_H/ih)
            nw, nh = int(iw*scale), int(ih*scale)
            img = img.resize((nw, nh), PILImage.LANCZOS)
            px = BX1 + (BX2-BX1 - nw)//2
            py = IMG_TOP + (IMG_H - nh)//2
            canvas.paste(img, (px, py))
        except:
            pass
    
    # علامة مائية
    draw = ImageDraw.Draw(canvas)
    wm_font = _get_font(10)
    draw.text((TARGET_W//2 - 40, BY2-8), WATERMARK, fill=(170, 175, 185), font=wm_font)
    
    canvas.save(path, "JPEG", quality=92)
    return path


# ══════════════════════════════════════════════════════════════════════════════
#  شريحة الملخص
# ══════════════════════════════════════════════════════════════════════════════

def _draw_summary_slide(sections: list, lecture_data: dict, is_arabic: bool) -> str:
    fd, path = tempfile.mkstemp(prefix="summary_", suffix=".jpg")
    os.close(fd)
    
    canvas = PILImage.new("RGB", (TARGET_W, TARGET_H), (22, 35, 55))
    draw = ImageDraw.Draw(canvas)
    
    BM = 10
    draw.rounded_rectangle([(BM, BM), (TARGET_W-BM, TARGET_H-BM)], radius=8, fill=(252, 250, 240))
    
    # عنوان
    title = "📋 ملخص المحاضرة" if is_arabic else "📋 Summary"
    title_font = _get_font(22, bold=True, arabic=is_arabic)
    _draw_text_centered(draw, title, BM+15, title_font, (28, 44, 68), is_arabic)
    
    draw.rectangle([(BM+10, BM+45), (TARGET_W-BM-10, BM+47)], fill=(220, 175, 40))
    
    # عرض الأقسام
    y = BM + 65
    for i, sec in enumerate(sections[:6]):
        accent = ACCENT_COLORS[i % len(ACCENT_COLORS)]
        sec_title = sec.get("title", f"قسم {i+1}")[:35]
        display = _prepare_arabic_text(f"✓ {sec_title}") if is_arabic else f"✓ {sec_title}"
        font = _get_font(14, arabic=is_arabic)
        draw.text((BM+20, y), display, fill=accent, font=font)
        y += 45
    
    wm_font = _get_font(11)
    draw.text((TARGET_W//2 - 40, TARGET_H-BM-15), WATERMARK, fill=(170, 175, 185), font=wm_font)
    
    canvas.save(path, "JPEG", quality=90)
    return path


# ══════════════════════════════════════════════════════════════════════════════
#  دوال FFmpeg
# ══════════════════════════════════════════════════════════════════════════════

def _ffmpeg_segment(img_path: str, duration: float, audio_path: str | None,
                    audio_start: float, out_path: str) -> None:
    dur = f"{duration:.3f}"
    aud = ["-ss", f"{audio_start:.3f}", "-t", dur, "-i", audio_path] if audio_path and os.path.exists(audio_path) else ["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100"]
    
    cmd = [
        "ffmpeg", "-y", "-loop", "1", "-t", dur, "-i", img_path, *aud,
        "-vf", "scale=854:480:force_original_aspect_ratio=decrease,pad=854:480:(ow-iw)/2:(oh-ih)/2",
        "-map", "0:v", "-map", "1:a",
        "-c:v", "libx264", "-preset", "ultrafast", "-tune", "stillimage",
        "-pix_fmt", "yuv420p", "-r", "10",
        "-c:a", "aac", "-b:a", "96k", "-ar", "44100", "-ac", "2",
        "-t", dur, out_path
    ]
    subprocess.run(cmd, capture_output=True)


def _ffmpeg_concat(seg_paths: list[str], out: str) -> None:
    fd, lst = tempfile.mkstemp(suffix=".txt")
    try:
        os.close(fd)
        with open(lst, "w") as f:
            for p in seg_paths:
                f.write(f"file '{p}'\n")
        subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", out], capture_output=True)
    finally:
        try:
            os.remove(lst)
        except:
            pass


# ══════════════════════════════════════════════════════════════════════════════
#  بناء المقاطع
# ══════════════════════════════════════════════════════════════════════════════

def _build_segments(sections: list, audio_results: list, lecture_data: dict, is_arabic: bool):
    segments, tmp_files = [], []
    total = 0.0
    
    # مقدمة
    intro = _draw_intro_slide(lecture_data, sections, is_arabic)
    tmp_files.append(intro)
    segments.append({"img": intro, "audio": None, "audio_start": 0, "dur": _INTRO_DUR})
    total += _INTRO_DUR
    
    for i, (sec, aud) in enumerate(zip(sections, audio_results)):
        # شريحة عنوان القسم
        title_img = _draw_section_title_card(sec, i, len(sections), is_arabic)
        tmp_files.append(title_img)
        segments.append({"img": title_img, "audio": None, "audio_start": 0, "dur": _SECTION_TITLE_DUR})
        total += _SECTION_TITLE_DUR
        
        # شريحة المحتوى (صورة واحدة للقسم كاملاً)
        img_bytes = sec.get("_image_bytes")
        content_img = _draw_content_slide(img_bytes, sec, i, is_arabic)
        tmp_files.append(content_img)
        
        # تجهيز الصوت
        apath = None
        if aud.get("audio"):
            afd, apath = tempfile.mkstemp(prefix=f"aud_{i}_", suffix=".mp3")
            os.close(afd)
            with open(apath, "wb") as f:
                f.write(aud["audio"])
            tmp_files.append(apath)
        
        dur = max(aud.get("duration", 30), 10)
        segments.append({
            "img": content_img,
            "audio": apath,
            "audio_start": 0,
            "dur": dur,
        })
        total += dur
    
    # ملخص
    summary = _draw_summary_slide(sections, lecture_data, is_arabic)
    tmp_files.append(summary)
    segments.append({"img": summary, "audio": None, "audio_start": 0, "dur": _SUMMARY_DUR})
    total += _SUMMARY_DUR
    
    return segments, tmp_files, total


def _encode_all(segments: list, out: str) -> None:
    seg_paths = []
    try:
        for i, seg in enumerate(segments):
            fd, p = tempfile.mkstemp(prefix=f"seg_{i}_", suffix=".mp4")
            os.close(fd)
            seg_paths.append(p)
            _ffmpeg_segment(seg["img"], seg["dur"], seg["audio"], seg["audio_start"], p)
        _ffmpeg_concat(seg_paths, out)
    finally:
        for p in seg_paths:
            try:
                os.remove(p)
            except:
                pass


# ══════════════════════════════════════════════════════════════════════════════
#  الدالة الرئيسية
# ══════════════════════════════════════════════════════════════════════════════

async def create_video_from_sections(
    sections: list,
    audio_results: list,
    lecture_data: dict,
    output_path: str,
    dialect: str = "msa",
    progress_cb: Callable[[float, float], Awaitable[None]] | None = None,
) -> float:
    is_arabic = dialect not in ("english", "british")
    loop = asyncio.get_event_loop()
    
    segments, tmp_files, total_secs = await loop.run_in_executor(
        None, _build_segments, sections, audio_results, lecture_data, is_arabic
    )
    
    est = estimate_encoding_seconds(total_secs)
    task = loop.run_in_executor(None, _encode_all, segments, output_path)
    
    start = loop.time()
    while not task.done():
        await asyncio.sleep(2)
        if progress_cb:
            try:
                await progress_cb(loop.time() - start, est)
            except:
                pass
    await task
    
    for p in tmp_files:
        try:
            if os.path.exists(p):
                os.remove(p)
        except:
            pass
    
    return total_secs
