import asyncio
import io
import os
import subprocess
import tempfile
import textwrap
from typing import Callable, Awaitable, Optional, List

from PIL import Image as PILImage, ImageDraw, ImageFont, ImageFilter

# ============================================================
# الإعدادات الأساسية
# ============================================================
TARGET_W, TARGET_H = 1280, 720
WATERMARK = "@zakros_probot"
FPS = 24

# الخطوط
FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_REG = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
_FONTS_DIR = os.path.join(os.path.dirname(__file__), "fonts")
FONT_AR_BOLD = os.path.join(_FONTS_DIR, "Amiri-Bold.ttf")
FONT_AR_REG = os.path.join(_FONTS_DIR, "Amiri-Regular.ttf")

# المدد الزمنية
INTRO_DURATION = 6.0
SECTION_TITLE_DURATION = 2.5
SUMMARY_DURATION = 6.0
_ENC_FACTOR = 0.5
_MIN_ENC_SEC = 15.0

# الألوان
ACCENT_COLORS = [
    (41, 128, 185), (39, 174, 96), (230, 126, 34),
    (155, 89, 182), (231, 76, 60), (52, 152, 219),
    (241, 196, 15), (142, 68, 173), (26, 188, 156),
]

BG_GRADIENTS = [
    ((20, 30, 60), (10, 20, 45)),
    ((30, 25, 55), (15, 15, 40)),
    ((20, 35, 65), (10, 20, 50)),
]


def estimate_encoding_seconds(total_video_seconds: float) -> float:
    """تقدير وقت التشفير"""
    return max(_MIN_ENC_SEC, total_video_seconds * _ENC_FACTOR)


def _get_font(size: int, bold: bool = False, arabic: bool = False) -> ImageFont.FreeTypeFont:
    """تحميل الخط المناسب"""
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


def _prepare_text(text: str, is_arabic: bool) -> str:
    """تجهيز النص العربي"""
    if not is_arabic or not text:
        return str(text) if text else ""
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
        reshaped = arabic_reshaper.reshape(str(text))
        return get_display(reshaped)
    except:
        return str(text)


def _draw_text_centered(draw, text: str, y: int, font, color, max_width: int = None):
    """رسم نص في المنتصف"""
    if not text:
        return
    
    if max_width:
        words = text.split()
        lines = []
        current = []
        for w in words:
            current.append(w)
            test = ' '.join(current)
            bbox = draw.textbbox((0, 0), test, font=font)
            if bbox[2] - bbox[0] > max_width:
                current.pop()
                if current:
                    lines.append(' '.join(current))
                current = [w]
        if current:
            lines.append(' '.join(current))
        text = '\n'.join(lines)
    
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    x = max((TARGET_W - tw) // 2, 20)
    
    draw.text((x + 2, y + 2), text, fill=(0, 0, 0, 180), font=font)
    draw.text((x, y), text, fill=color, font=font)


def _gradient_bg(color_top=(25, 30, 60), color_bot=(10, 20, 45)) -> PILImage.Image:
    """خلفية متدرجة"""
    bg = PILImage.new("RGB", (TARGET_W, TARGET_H), color_top)
    draw = ImageDraw.Draw(bg)
    for y in range(TARGET_H):
        t = y / TARGET_H
        r = int(color_top[0] * (1 - t) + color_bot[0] * t)
        g = int(color_top[1] * (1 - t) + color_bot[1] * t)
        b = int(color_top[2] * (1 - t) + color_bot[2] * t)
        draw.line([(0, y), (TARGET_W, y)], fill=(r, g, b))
    return bg


def _create_intro_slide(lecture_data: dict, sections: list, is_arabic: bool) -> bytes:
    """شريحة المقدمة"""
    bg = _gradient_bg(BG_GRADIENTS[0][0], BG_GRADIENTS[0][1])
    draw = ImageDraw.Draw(bg)
    
    header_h = 70
    draw.rectangle([(0, 0), (TARGET_W, header_h)], fill=(15, 25, 45))
    draw.rectangle([(0, header_h - 3), (TARGET_W, header_h)], fill=(255, 200, 50))
    
    logo_font = _get_font(20, bold=True)
    draw.text((20, 20), "🎓 ZAKROS PRO BOT", fill=(255, 220, 100), font=logo_font)
    
    rights = "© جميع الحقوق محفوظة - بوت المحاضرات الذكي"
    rights = _prepare_text(rights, is_arabic)
    rights_font = _get_font(14)
    bbox = draw.textbbox((0, 0), rights, font=rights_font)
    rw = bbox[2] - bbox[0]
    draw.text((TARGET_W - rw - 20, 25), rights, fill=(200, 200, 220), font=rights_font)
    
    title = lecture_data.get("title", "المحاضرة" if is_arabic else "Lecture")
    title_txt = _prepare_text(title, is_arabic)
    title_font = _get_font(32, bold=True, arabic=is_arabic)
    _draw_text_centered(draw, title_txt, header_h + 30, title_font, (255, 220, 80), TARGET_W - 80)
    
    lt = lecture_data.get("lecture_type", "other")
    types = {
        "medicine": "🩺 محاضرة طبية" if is_arabic else "Medical Lecture",
        "science": "🔬 محاضرة علمية" if is_arabic else "Science Lecture",
        "math": "📐 رياضيات" if is_arabic else "Mathematics",
        "other": "📚 محاضرة تعليمية" if is_arabic else "Educational Lecture",
    }
    type_txt = _prepare_text(types.get(lt, types["other"]), is_arabic)
    type_font = _get_font(18, arabic=is_arabic)
    _draw_text_centered(draw, type_txt, header_h + 75, type_font, (180, 200, 240))
    
    draw.rectangle([(100, header_h + 110), (TARGET_W - 100, header_h + 112)], fill=(255, 200, 50))
    
    map_y = header_h + 140
    map_title = "📋 خريطة المحاضرة" if is_arabic else "📋 Lecture Map"
    map_title = _prepare_text(map_title, is_arabic)
    map_font = _get_font(20, bold=True, arabic=is_arabic)
    _draw_text_centered(draw, map_title, map_y, map_font, (255, 255, 255))
    
    map_y += 45
    sec_font = _get_font(16, arabic=is_arabic)
    num_font = _get_font(16, bold=True)
    
    for i, s in enumerate(sections[:8]):
        color = ACCENT_COLORS[i % len(ACCENT_COLORS)]
        y = map_y + i * 38
        
        draw.ellipse([40, y-5, 65, y+20], fill=color)
        draw.text((52, y), str(i+1), fill=(255, 255, 255), font=num_font)
        
        sec_title = s.get("title", f"القسم {i+1}")[:40]
        sec_txt = _prepare_text(sec_title, is_arabic)
        draw.text((85, y+2), sec_txt, fill=(220, 230, 255), font=sec_font)
    
    wm_font = _get_font(12)
    wm = WATERMARK
    bbox = draw.textbbox((0, 0), wm, font=wm_font)
    ww = bbox[2] - bbox[0]
    draw.text(((TARGET_W - ww)//2, TARGET_H - 30), wm, fill=(120, 130, 150), font=wm_font)
    
    buf = io.BytesIO()
    bg.save(buf, "JPEG", quality=95)
    return buf.getvalue()


def _create_section_title_card(section: dict, idx: int, total: int, is_arabic: bool) -> bytes:
    """بطاقة عنوان القسم"""
    color = ACCENT_COLORS[idx % len(ACCENT_COLORS)]
    bg = _gradient_bg(BG_GRADIENTS[idx % len(BG_GRADIENTS)][0], BG_GRADIENTS[idx % len(BG_GRADIENTS)][1])
    draw = ImageDraw.Draw(bg)
    
    draw.rounded_rectangle([(15, 15), (TARGET_W-15, TARGET_H-15)], radius=20, outline=(255, 200, 50), width=4)
    draw.rounded_rectangle([(22, 22), (TARGET_W-22, TARGET_H-22)], radius=15, outline=color, width=2)
    
    center_y = TARGET_H // 2 - 40
    
    num_str = str(idx + 1)
    num_font = _get_font(90, bold=True)
    bbox = draw.textbbox((0, 0), num_str, font=num_font)
    nw = bbox[2] - bbox[0]
    draw.text(((TARGET_W - nw)//2 + 3, center_y - 43), num_str, fill=(0, 0, 0, 100), font=num_font)
    draw.text(((TARGET_W - nw)//2, center_y - 45), num_str, fill=color, font=num_font)
    
    sec_label = "القسم" if is_arabic else "Section"
    sec_label = _prepare_text(sec_label, is_arabic)
    label_font = _get_font(24, arabic=is_arabic)
    _draw_text_centered(draw, sec_label, center_y + 50, label_font, (220, 220, 240))
    
    title = section.get("title", f"Section {idx+1}")
    title_txt = _prepare_text(title, is_arabic)
    title_font = _get_font(26, bold=True, arabic=is_arabic)
    _draw_text_centered(draw, title_txt, center_y + 90, title_font, (255, 220, 100), TARGET_W - 100)
    
    prog = f"{idx+1} / {total}"
    prog_font = _get_font(16)
    bbox = draw.textbbox((0, 0), prog, font=prog_font)
    pw = bbox[2] - bbox[0]
    draw.text(((TARGET_W - pw)//2, TARGET_H - 50), prog, fill=(150, 160, 180), font=prog_font)
    
    wm_font = _get_font(12)
    wm = WATERMARK
    bbox = draw.textbbox((0, 0), wm, font=wm_font)
    ww = bbox[2] - bbox[0]
    draw.text(((TARGET_W - ww)//2, TARGET_H - 25), wm, fill=(100, 110, 130), font=wm_font)
    
    buf = io.BytesIO()
    bg.save(buf, "JPEG", quality=95)
    return buf.getvalue()


def _create_content_slide(
    image_bytes: Optional[bytes],
    keyword: str,
    all_keywords: List[str],
    current_idx: int,
    is_arabic: bool,
    section_title: str = "",
    section_idx: int = 0,
) -> bytes:
    """شريحة المحتوى - صورة كبيرة + كلمات مفتاحية"""
    color = ACCENT_COLORS[section_idx % len(ACCENT_COLORS)]
    bg = _gradient_bg((20, 25, 45), (10, 15, 35))
    draw = ImageDraw.Draw(bg)
    
    header_h = 55
    draw.rectangle([(0, 0), (TARGET_W, header_h)], fill=(15, 20, 40))
    draw.rectangle([(0, header_h - 3), (TARGET_W, header_h)], fill=color)
    
    title_display = _prepare_text(section_title[:50], is_arabic)
    title_font = _get_font(18, bold=True, arabic=is_arabic)
    _draw_text_centered(draw, title_display, 14, title_font, (255, 255, 255))
    
    img_top = header_h + 15
    img_bottom = TARGET_H - 100
    img_h = img_bottom - img_top
    img_w = TARGET_W - 60
    
    if image_bytes:
        try:
            img = PILImage.open(io.BytesIO(image_bytes)).convert("RGB")
            iw, ih = img.size
            
            scale = min(img_w / iw, img_h / ih)
            nw, nh = int(iw * scale), int(ih * scale)
            img = img.resize((nw, nh), PILImage.LANCZOS)
            
            framed = PILImage.new("RGB", (nw + 16, nh + 16), (255, 255, 255))
            framed.paste(img, (8, 8))
            
            shadow = PILImage.new("RGBA", (nw + 30, nh + 30), (0, 0, 0, 0))
            s_draw = ImageDraw.Draw(shadow)
            s_draw.rectangle([(12, 12), (nw + 18, nh + 18)], fill=(0, 0, 0, 120))
            shadow = shadow.filter(ImageFilter.GaussianBlur(radius=10))
            
            final = PILImage.new("RGB", (nw + 30, nh + 30), (20, 25, 45))
            if shadow.mode == 'RGBA':
                final.paste(shadow, (0, 0), shadow.split()[3])
            final.paste(framed, (7, 7))
            
            px = (TARGET_W - (nw + 30)) // 2
            py = img_top + (img_h - (nh + 30)) // 2
            bg.paste(final, (px, py))
            draw = ImageDraw.Draw(bg)
        except Exception as e:
            print(f"Image error: {e}")
            draw.rectangle(
                [(40, img_top), (TARGET_W - 40, img_bottom)],
                outline=(100, 100, 120), width=3
            )
            placeholder = "🖼️ الصورة التعليمية" if is_arabic else "🖼️ Educational Image"
            placeholder = _prepare_text(placeholder, is_arabic)
            place_font = _get_font(22, arabic=is_arabic)
            _draw_text_centered(draw, placeholder, TARGET_H // 2, place_font, (150, 160, 180))
    else:
        draw.rectangle(
            [(40, img_top), (TARGET_W - 40, img_bottom)],
            outline=(100, 100, 120), width=3
        )
        placeholder = "🖼️ الصورة التعليمية" if is_arabic else "🖼️ Educational Image"
        placeholder = _prepare_text(placeholder, is_arabic)
        place_font = _get_font(22, arabic=is_arabic)
        _draw_text_centered(draw, placeholder, TARGET_H // 2, place_font, (150, 160, 180))
    
    kw_y = TARGET_H - 75
    kw_label = "🔑 الكلمات المفتاحية:" if is_arabic else "🔑 Keywords:"
    kw_label = _prepare_text(kw_label, is_arabic)
    label_font = _get_font(14, arabic=is_arabic)
    draw.text((30, kw_y - 25), kw_label, fill=(200, 200, 220), font=label_font)
    
    spacing = min(160, TARGET_W // max(len(all_keywords), 1))
    for i, kw in enumerate(all_keywords[:6]):
        kw_display = _prepare_text(kw[:20], is_arabic)
        x = 30 + i * spacing
        
        if i == current_idx:
            kw_font = _get_font(16, bold=True, arabic=is_arabic)
            bbox = draw.textbbox((0, 0), kw_display, font=kw_font)
            kw_w = bbox[2] - bbox[0]
            draw.rounded_rectangle(
                [(x - 8, kw_y - 5), (x + kw_w + 12, kw_y + 25)],
                radius=6, fill=color
            )
            draw.text((x + 4, kw_y), kw_display, fill=(255, 255, 255), font=kw_font)
        elif i < current_idx:
            kw_font = _get_font(14, arabic=is_arabic)
            draw.text((x, kw_y + 2), "✓ " + kw_display, fill=(100, 200, 100), font=kw_font)
        else:
            kw_font = _get_font(14, arabic=is_arabic)
            draw.text((x, kw_y + 2), "○ " + kw_display, fill=(140, 150, 170), font=kw_font)
    
    wm_font = _get_font(11)
    wm = WATERMARK
    bbox = draw.textbbox((0, 0), wm, font=wm_font)
    ww = bbox[2] - bbox[0]
    draw.text(((TARGET_W - ww)//2, TARGET_H - 20), wm, fill=(100, 110, 130), font=wm_font)
    
    buf = io.BytesIO()
    bg.save(buf, "JPEG", quality=95)
    return buf.getvalue()


def _create_summary_slide(lecture_data: dict, sections: list, is_arabic: bool) -> bytes:
    """شريحة الملخص"""
    bg = _gradient_bg((20, 30, 50), (10, 20, 40))
    draw = ImageDraw.Draw(bg)
    
    header_h = 60
    draw.rectangle([(0, 0), (TARGET_W, header_h)], fill=(25, 35, 55))
    draw.rectangle([(0, header_h - 3), (TARGET_W, header_h)], fill=(255, 200, 50))
    
    sum_title = "📋 ملخص المحاضرة" if is_arabic else "📋 Lecture Summary"
    sum_title = _prepare_text(sum_title, is_arabic)
    title_font = _get_font(24, bold=True, arabic=is_arabic)
    _draw_text_centered(draw, sum_title, 15, title_font, (255, 220, 80))
    
    y = header_h + 30
    summary = lecture_data.get("summary", "")
    if summary:
        sum_txt = _prepare_text(summary[:500], is_arabic)
        sum_font = _get_font(16, arabic=is_arabic)
        lines = textwrap.wrap(sum_txt, width=50)
        for line in lines[:8]:
            draw.text((40, y), line, fill=(220, 230, 255), font=sum_font)
            y += 28
    
    y += 20
    points = lecture_data.get("key_points", [])[:5]
    if points:
        pt_label = "✨ النقاط الرئيسية:" if is_arabic else "✨ Key Points:"
        pt_label = _prepare_text(pt_label, is_arabic)
        pt_font = _get_font(16, bold=True, arabic=is_arabic)
        draw.text((40, y), pt_label, fill=(255, 200, 100), font=pt_font)
        y += 30
        
        point_font = _get_font(14, arabic=is_arabic)
        for p in points:
            p_txt = _prepare_text(f"• {p[:60]}", is_arabic)
            draw.text((60, y), p_txt, fill=(200, 210, 230), font=point_font)
            y += 26
    
    thumb_y = TARGET_H - 120
    thumb_w = 140
    thumb_h = 90
    spacing = 15
    n_thumbs = min(len(sections), 4)
    total_w = n_thumbs * (thumb_w + spacing) - spacing
    start_x = (TARGET_W - total_w) // 2
    
    for i in range(n_thumbs):
        x = start_x + i * (thumb_w + spacing)
        color = ACCENT_COLORS[i % len(ACCENT_COLORS)]
        draw.rounded_rectangle(
            [(x, thumb_y), (x + thumb_w, thumb_y + thumb_h)],
            radius=10, fill=(30, 40, 60), outline=color, width=3
        )
        draw.text((x + thumb_w//2 - 8, thumb_y + thumb_h//2 - 10), str(i+1), 
                  fill=color, font=_get_font(22, bold=True))
    
    wm_font = _get_font(11)
    wm = WATERMARK
    bbox = draw.textbbox((0, 0), wm, font=wm_font)
    ww = bbox[2] - bbox[0]
    draw.text(((TARGET_W - ww)//2, TARGET_H - 20), wm, fill=(100, 110, 130), font=wm_font)
    
    buf = io.BytesIO()
    bg.save(buf, "JPEG", quality=95)
    return buf.getvalue()


def _ffmpeg_segment(
    img_bytes: bytes,
    duration: float,
    audio_bytes: Optional[bytes],
    audio_start: float,
    out_path: str,
    gentle_zoom: bool = True
) -> None:
    """تشفير مقطع فيديو"""
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
        f.write(img_bytes)
        img_path = f.name
    
    audio_path = None
    if audio_bytes:
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            f.write(audio_bytes)
            audio_path = f.name
    
    dur_str = f"{duration:.3f}"
    
    if audio_path:
        if gentle_zoom:
            n_frames = max(int(duration * FPS), 2)
            vf = f"scale=1280:720,zoompan=z='min(zoom+0.0001,1.02)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={n_frames}:s=1280x720:fps={FPS}"
            cmd = [
                "ffmpeg", "-y",
                "-loop", "1", "-t", dur_str, "-i", img_path,
                "-ss", f"{audio_start:.3f}", "-t", dur_str, "-i", audio_path,
                "-vf", vf,
                "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p", "-r", str(FPS),
                "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "2",
                "-shortest", out_path
            ]
        else:
            cmd = [
                "ffmpeg", "-y",
                "-loop", "1", "-t", dur_str, "-i", img_path,
                "-ss", f"{audio_start:.3f}", "-t", dur_str, "-i", audio_path,
                "-vf", "scale=1280:720",
                "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "128k",
                "-shortest", out_path
            ]
    else:
        cmd = [
            "ffmpeg", "-y",
            "-loop", "1", "-t", dur_str, "-i", img_path,
            "-vf", "scale=1280:720",
            "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p",
            out_path
        ]
    
    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0:
        error_msg = result.stderr.decode()[-500:] if result.stderr else "Unknown error"
        raise RuntimeError(f"FFmpeg failed: {error_msg}")
    
    os.unlink(img_path)
    if audio_path:
        os.unlink(audio_path)


def _ffmpeg_concat(segment_paths: List[str], output_path: str) -> None:
    """دمج المقاطع"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        for p in segment_paths:
            f.write(f"file '{p}'\n")
        list_path = f.name
    
    cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list_path, "-c", "copy", output_path]
    result = subprocess.run(cmd, capture_output=True)
    
    os.unlink(list_path)
    
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg concat failed: {result.stderr.decode()[-400:]}")


def _build_segments(
    sections: list,
    audio_results: list,
    lecture_data: dict,
    is_arabic: bool,
) -> tuple[List[dict], float]:
    """بناء قائمة المقاطع"""
    segments = []
    total_secs = 0.0
    n_sections = len(sections)
    
    # 1. المقدمة
    intro_bytes = _create_intro_slide(lecture_data, sections, is_arabic)
    segments.append({
        "img": intro_bytes,
        "audio": None,
        "audio_start": 0,
        "dur": INTRO_DURATION,
        "gentle_zoom": False
    })
    total_secs += INTRO_DURATION
    print(f"  ✅ Intro slide created ({INTRO_DURATION}s)")
    
    # 2. الأقسام
    for i, (section, audio_info) in enumerate(zip(sections, audio_results)):
        # بطاقة عنوان القسم
        title_bytes = _create_section_title_card(section, i, n_sections, is_arabic)
        segments.append({
            "img": title_bytes,
            "audio": None,
            "audio_start": 0,
            "dur": SECTION_TITLE_DURATION,
            "gentle_zoom": False
        })
        total_secs += SECTION_TITLE_DURATION
        print(f"  ✅ Section {i+1} title card created ({SECTION_TITLE_DURATION}s)")
        
        # شرائح المحتوى
        keywords = section.get("keywords", [])
        if not keywords:
            keywords = [section.get("title", f"Section {i+1}")]
        
        kw_images = section.get("_keyword_images", [])
        audio_bytes = audio_info.get("audio")
        total_dur = audio_info.get("duration", len(keywords) * 8.0)
        kw_dur = total_dur / max(len(keywords), 1)
        
        for j, kw in enumerate(keywords):
            img_bytes = kw_images[j] if j < len(kw_images) else section.get("_image_bytes")
            
            slide_bytes = _create_content_slide(
                img_bytes, kw, keywords, j, is_arabic,
                section.get("title", ""), i
            )
            
            segments.append({
                "img": slide_bytes,
                "audio": audio_bytes,
                "audio_start": j * kw_dur,
                "dur": kw_dur,
                "gentle_zoom": True
            })
            total_secs += kw_dur
        print(f"  ✅ Section {i+1} content slides created ({len(keywords)} slides, {total_dur:.1f}s)")
    
    # 3. الملخص
    summary_bytes = _create_summary_slide(lecture_data, sections, is_arabic)
    segments.append({
        "img": summary_bytes,
        "audio": None,
        "audio_start": 0,
        "dur": SUMMARY_DURATION,
        "gentle_zoom": False
    })
    total_secs += SUMMARY_DURATION
    print(f"  ✅ Summary slide created ({SUMMARY_DURATION}s)")
    
    return segments, total_secs


def _encode_all(segments: List[dict], output_path: str) -> None:
    """تشفير جميع المقاطع ودمجها"""
    seg_paths = []
    try:
        for i, seg in enumerate(segments):
            with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
                out = f.name
            seg_paths.append(out)
            
            _ffmpeg_segment(
                seg["img"],
                seg["dur"],
                seg.get("audio"),
                seg.get("audio_start", 0),
                out,
                seg.get("gentle_zoom", False)
            )
            print(f"  ✅ Segment {i+1}/{len(segments)} encoded ({seg['dur']:.1f}s)")
        
        _ffmpeg_concat(seg_paths, output_path)
        print(f"  ✅ Video created: {output_path}")
        
    finally:
        for p in seg_paths:
            try:
                os.unlink(p)
            except:
                pass


async def create_video_from_sections(
    sections: list,
    audio_results: list,
    lecture_data: dict,
    output_path: str,
    dialect: str = "msa",
    progress_cb: Optional[Callable[[float, float], Awaitable[None]]] = None,
) -> float:
    """إنشاء الفيديو النهائي"""
    is_arabic = dialect not in ("english", "british")
    loop = asyncio.get_event_loop()
    
    print(f"🎬 Building video segments...")
    segments, total_secs = await loop.run_in_executor(
        None, _build_segments, sections, audio_results, lecture_data, is_arabic
    )
    
    if not segments:
        raise RuntimeError("No segments generated")
    
    print(f"🎬 Encoding {len(segments)} segments (total: {total_secs:.1f}s)...")
    
    encode_task = loop.run_in_executor(None, _encode_all, segments, output_path)
    
    start = loop.time()
    est = estimate_encoding_seconds(total_secs)
    
    while not encode_task.done():
        await asyncio.sleep(3)
        if progress_cb:
            try:
                await progress_cb(loop.time() - start, est)
            except:
                pass
    
    await encode_task
    
    print(f"✅ Video completed: {total_secs:.1f}s")
    return total_secs
