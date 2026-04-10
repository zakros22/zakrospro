import asyncio
import io
import os
import subprocess
import tempfile
import textwrap
import math
from typing import Callable, Awaitable, Optional, List

from PIL import Image as PILImage, ImageDraw, ImageFont, ImageFilter

TARGET_W, TARGET_H = 854, 480
WATERMARK = "@zakros_probot"
FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_REG = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
_FONTS_DIR = os.path.join(os.path.dirname(__file__), "fonts")
FONT_AR_BOLD = os.path.join(_FONTS_DIR, "Amiri-Bold.ttf")
FONT_AR_REG = os.path.join(_FONTS_DIR, "Amiri-Regular.ttf")

_ENC_FACTOR = 0.45
_MIN_ENC_SEC = 15.0

# ألوان كرتونية جذابة
ACCENT_COLORS = [
    (255, 107, 107), (78, 205, 196), (255, 209, 102),
    (170, 120, 255), (255, 140, 200), (100, 200, 255),
    (255, 180, 100), (150, 220, 150), (255, 150, 150),
]

BG_GRADIENTS = [
    ((25, 30, 60), (10, 20, 45)),
    ((30, 25, 55), (15, 15, 40)),
    ((20, 35, 65), (10, 20, 50)),
]

def estimate_encoding_seconds(total_video_seconds: float) -> float:
    return max(_MIN_ENC_SEC, total_video_seconds * _ENC_FACTOR)


def _get_font(size: int, bold: bool = False, arabic: bool = False) -> ImageFont.FreeTypeFont:
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
    
    # ظل
    draw.text((x + 2, y + 2), text, fill=(0, 0, 0, 180), font=font)
    draw.text((x, y), text, fill=color, font=font)


def _gradient_bg(color_top=(25, 30, 60), color_bot=(10, 20, 45)) -> PILImage.Image:
    bg = PILImage.new("RGB", (TARGET_W, TARGET_H), color_top)
    draw = ImageDraw.Draw(bg)
    for y in range(TARGET_H):
        t = y / TARGET_H
        r = int(color_top[0] * (1 - t) + color_bot[0] * t)
        g = int(color_top[1] * (1 - t) + color_bot[1] * t)
        b = int(color_top[2] * (1 - t) + color_bot[2] * t)
        draw.line([(0, y), (TARGET_W, y)], fill=(r, g, b))
    return bg


def _create_cartoon_placeholder(keyword: str, section_title: str, idx: int, is_arabic: bool) -> bytes:
    """إنشاء صورة كرتونية بديلة احترافية"""
    W, H = 800, 500
    bg_color = ACCENT_COLORS[idx % len(ACCENT_COLORS)]
    
    img = PILImage.new("RGB", (W, H), (245, 248, 250))
    draw = ImageDraw.Draw(img)
    
    # خلفية متدرجة ناعمة
    for y in range(H):
        t = y / H
        r = int(255 * (1 - t) + bg_color[0] * 0.3 * t)
        g = int(255 * (1 - t) + bg_color[1] * 0.3 * t)
        b = int(255 * (1 - t) + bg_color[2] * 0.3 * t)
        draw.line([(0, y), (W, y)], fill=(r, g, b))
    
    # إطار كرتوني
    draw.rounded_rectangle([(15, 15), (W-15, H-15)], radius=20, outline=bg_color, width=4)
    draw.rounded_rectangle([(20, 20), (W-20, H-20)], radius=15, outline=(*bg_color, 100), width=2)
    
    # أيقونة تعليمية
    icon = "📚" if is_arabic else "📖"
    icon_font = _get_font(60)
    bbox = draw.textbbox((0, 0), icon, font=icon_font)
    iw = bbox[2] - bbox[0]
    draw.text(((W - iw) // 2, 80), icon, fill=bg_color, font=icon_font)
    
    # الكلمة المفتاحية (كبيرة)
    kw_display = _prepare_text(keyword[:25], is_arabic)
    kw_font = _get_font(36, bold=True, arabic=is_arabic)
    bbox = draw.textbbox((0, 0), kw_display, font=kw_font)
    kw_w = bbox[2] - bbox[0]
    draw.text(((W - kw_w) // 2 + 2, 180), kw_display, fill=(0, 0, 0, 100), font=kw_font)
    draw.text(((W - kw_w) // 2, 178), kw_display, fill=(40, 45, 60), font=kw_font)
    
    # عنوان القسم
    sec_display = _prepare_text(section_title[:40], is_arabic)
    sec_font = _get_font(18, arabic=is_arabic)
    bbox = draw.textbbox((0, 0), sec_display, font=sec_font)
    sw = bbox[2] - bbox[0]
    draw.text(((W - sw) // 2, 260), sec_display, fill=(100, 100, 120), font=sec_font)
    
    # خط زخرفي
    draw.rectangle([(W//4, 300), (W*3//4, 304)], fill=bg_color)
    
    # نص توضيحي
    hint = "🎨 صورة تعليمية" if is_arabic else "🎨 Educational Image"
    hint_display = _prepare_text(hint, is_arabic)
    hint_font = _get_font(16, arabic=is_arabic)
    bbox = draw.textbbox((0, 0), hint_display, font=hint_font)
    hw = bbox[2] - bbox[0]
    draw.text(((W - hw) // 2, 350), hint_display, fill=(150, 150, 170), font=hint_font)
    
    # دوائر زخرفية
    for i in range(3):
        x = 50 + i * 350
        y = 420
        draw.ellipse([x-20, y-20, x+20, y+20], fill=(*bg_color, 50), outline=bg_color, width=2)
    
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=90)
    return buf.getvalue()


def _create_intro_slide(lecture_data: dict, sections: list, is_arabic: bool, total_duration: float) -> str:
    """شريحة المقدمة مع خريطة الأقسام"""
    img_fd, img_path = tempfile.mkstemp(prefix="intro_", suffix=".jpg")
    os.close(img_fd)

    bg = _gradient_bg(BG_GRADIENTS[0][0], BG_GRADIENTS[0][1])
    draw = ImageDraw.Draw(bg)

    # هيدر
    header_h = 60
    draw.rectangle([(0, 0), (TARGET_W, header_h)], fill=(20, 30, 50))
    draw.rectangle([(0, header_h - 3), (TARGET_W, header_h)], fill=(255, 200, 50))

    logo_font = _get_font(18, bold=True)
    draw.text((15, 15), "🎓 ZAKROS PRO", fill=(255, 220, 100), font=logo_font)

    rights = "© جميع الحقوق محفوظة"
    rights = _prepare_text(rights, is_arabic)
    rights_font = _get_font(12)
    bbox = draw.textbbox((0, 0), rights, font=rights_font)
    rw = bbox[2] - bbox[0]
    draw.text((TARGET_W - rw - 15, 20), rights, fill=(200, 200, 220), font=rights_font)

    # عنوان المحاضرة
    title = lecture_data.get("title", "المحاضرة" if is_arabic else "Lecture")
    title_txt = _prepare_text(title, is_arabic)
    title_font = _get_font(26, bold=True, arabic=is_arabic)
    _draw_text_centered(draw, title_txt, header_h + 20, title_font, (255, 220, 80), TARGET_W - 60)

    # نوع المحاضرة
    lt = lecture_data.get("lecture_type", "other")
    types = {
        "medicine": "🩺 طبية" if is_arabic else "Medical",
        "science": "🔬 علمية" if is_arabic else "Science",
        "math": "📐 رياضيات" if is_arabic else "Math",
        "other": "📚 تعليمية" if is_arabic else "Educational",
    }
    type_txt = _prepare_text(types.get(lt, types["other"]), is_arabic)
    type_font = _get_font(16, arabic=is_arabic)
    _draw_text_centered(draw, type_txt, header_h + 60, type_font, (180, 200, 240))

    # مدة الفيديو
    mins = int(total_duration // 60)
    secs = int(total_duration % 60)
    dur_txt = f"⏱️ المدة: {mins}:{secs:02d}" if is_arabic else f"⏱️ Duration: {mins}:{secs:02d}"
    dur_txt = _prepare_text(dur_txt, is_arabic)
    dur_font = _get_font(14)
    _draw_text_centered(draw, dur_txt, header_h + 85, dur_font, (150, 200, 150))

    draw.rectangle([(60, header_h + 110), (TARGET_W - 60, header_h + 112)], fill=(255, 200, 50))

    # خريطة الأقسام
    map_y = header_h + 130
    map_title = "📋 الأقسام:" if is_arabic else "📋 Sections:"
    map_title = _prepare_text(map_title, is_arabic)
    map_font = _get_font(18, bold=True, arabic=is_arabic)
    draw.text((40, map_y), map_title, fill=(255, 255, 255), font=map_font)

    map_y += 35
    sec_font = _get_font(14, arabic=is_arabic)
    num_font = _get_font(15, bold=True)

    for i, s in enumerate(sections[:8]):
        color = ACCENT_COLORS[i % len(ACCENT_COLORS)]
        y = map_y + i * 30
        
        draw.ellipse([35, y-8, 55, y+12], fill=color)
        draw.text((42, y-5), str(i+1), fill=(255, 255, 255), font=num_font)
        
        sec_title = s.get("title", f"القسم {i+1}")[:40]
        sec_txt = _prepare_text(sec_title, is_arabic)
        draw.text((70, y), sec_txt, fill=(220, 230, 255), font=sec_font)

    # علامة مائية
    wm_font = _get_font(11)
    wm = WATERMARK
    bbox = draw.textbbox((0, 0), wm, font=wm_font)
    ww = bbox[2] - bbox[0]
    draw.text(((TARGET_W - ww)//2, TARGET_H - 20), wm, fill=(120, 130, 150), font=wm_font)

    bg.save(img_path, "JPEG", quality=90)
    return img_path


def _create_section_title_card(section: dict, idx: int, total: int, is_arabic: bool) -> str:
    """بطاقة عنوان القسم"""
    img_fd, img_path = tempfile.mkstemp(prefix=f"sec_{idx}_", suffix=".jpg")
    os.close(img_fd)

    color = ACCENT_COLORS[idx % len(ACCENT_COLORS)]
    bg = _gradient_bg(BG_GRADIENTS[idx % len(BG_GRADIENTS)][0], BG_GRADIENTS[idx % len(BG_GRADIENTS)][1])
    draw = ImageDraw.Draw(bg)

    # إطار ذهبي
    draw.rounded_rectangle([(10, 10), (TARGET_W-10, TARGET_H-10)], radius=15, outline=(255, 200, 50), width=3)
    draw.rounded_rectangle([(15, 15), (TARGET_W-15, TARGET_H-15)], radius=12, outline=color, width=1)

    center_y = TARGET_H // 2 - 30
    
    # رقم القسم
    num_str = str(idx + 1)
    num_font = _get_font(70, bold=True)
    bbox = draw.textbbox((0, 0), num_str, font=num_font)
    nw = bbox[2] - bbox[0]
    draw.text(((TARGET_W - nw)//2 + 3, center_y - 33), num_str, fill=(0, 0, 0, 100), font=num_font)
    draw.text(((TARGET_W - nw)//2, center_y - 35), num_str, fill=color, font=num_font)

    # "القسم"
    sec_label = "القسم" if is_arabic else "Section"
    sec_label = _prepare_text(sec_label, is_arabic)
    label_font = _get_font(22, arabic=is_arabic)
    _draw_text_centered(draw, sec_label, center_y + 40, label_font, (220, 220, 240))

    # عنوان القسم
    title = section.get("title", f"Section {idx+1}")
    title_txt = _prepare_text(title, is_arabic)
    title_font = _get_font(22, bold=True, arabic=is_arabic)
    _draw_text_centered(draw, title_txt, center_y + 75, title_font, (255, 220, 100), TARGET_W - 80)

    # التقدم
    prog = f"{idx+1} / {total}"
    prog_font = _get_font(14)
    bbox = draw.textbbox((0, 0), prog, font=prog_font)
    pw = bbox[2] - bbox[0]
    draw.text(((TARGET_W - pw)//2, TARGET_H - 40), prog, fill=(150, 160, 180), font=prog_font)

    wm_font = _get_font(11)
    wm = WATERMARK
    bbox = draw.textbbox((0, 0), wm, font=wm_font)
    ww = bbox[2] - bbox[0]
    draw.text(((TARGET_W - ww)//2, TARGET_H - 20), wm, fill=(100, 110, 130), font=wm_font)

    bg.save(img_path, "JPEG", quality=90)
    return img_path


def _create_content_slide(
    image_bytes: Optional[bytes],
    keyword: str,
    all_keywords: List[str],
    current_idx: int,
    is_arabic: bool,
    section_title: str = "",
    section_idx: int = 0,
) -> str:
    """شريحة المحتوى - صورة كبيرة + كلمات مفتاحية واضحة"""
    img_fd, img_path = tempfile.mkstemp(prefix="content_", suffix=".jpg")
    os.close(img_fd)

    color = ACCENT_COLORS[section_idx % len(ACCENT_COLORS)]
    bg = _gradient_bg((20, 25, 45), (10, 15, 35))
    draw = ImageDraw.Draw(bg)

    # هيدر
    header_h = 45
    draw.rectangle([(0, 0), (TARGET_W, header_h)], fill=(15, 20, 40))
    draw.rectangle([(0, header_h - 2), (TARGET_W, header_h)], fill=color)

    title_display = _prepare_text(section_title[:45], is_arabic)
    title_font = _get_font(16, bold=True, arabic=is_arabic)
    _draw_text_centered(draw, title_display, 10, title_font, (255, 255, 255))

    # منطقة الصورة
    img_top = header_h + 10
    img_bottom = TARGET_H - 80
    img_h = img_bottom - img_top
    img_w = TARGET_W - 40

    if image_bytes:
        try:
            img = PILImage.open(io.BytesIO(image_bytes)).convert("RGB")
            iw, ih = img.size
            
            # تكبير الصورة لتكون واضحة
            scale = min(img_w / iw, img_h / ih)
            nw, nh = int(iw * scale), int(ih * scale)
            img = img.resize((nw, nh), PILImage.LANCZOS)
            
            # إطار أبيض
            framed = PILImage.new("RGB", (nw + 12, nh + 12), (255, 255, 255))
            framed.paste(img, (6, 6))
            
            # ظل
            shadow = PILImage.new("RGBA", (nw + 20, nh + 20), (0, 0, 0, 0))
            s_draw = ImageDraw.Draw(shadow)
            s_draw.rectangle([(8, 8), (nw + 12, nh + 12)], fill=(0, 0, 0, 120))
            shadow = shadow.filter(ImageFilter.GaussianBlur(radius=8))
            
            final = PILImage.new("RGB", (nw + 20, nh + 20), (20, 25, 45))
            if shadow.mode == 'RGBA':
                final.paste(shadow, (0, 0), shadow.split()[3])
            final.paste(framed, (4, 4))
            
            px = (TARGET_W - (nw + 20)) // 2
            py = img_top + (img_h - (nh + 20)) // 2
            bg.paste(final, (px, py))
            draw = ImageDraw.Draw(bg)
        except Exception as e:
            print(f"Image error: {e}")
            # صورة بديلة كرتونية
            placeholder = _create_cartoon_placeholder(keyword, section_title, section_idx, is_arabic)
            img = PILImage.open(io.BytesIO(placeholder)).convert("RGB")
            img = img.resize((img_w, img_h), PILImage.LANCZOS)
            bg.paste(img, (20, img_top))
            draw = ImageDraw.Draw(bg)

    # الكلمات المفتاحية
    kw_y = TARGET_H - 60
    kw_label = "🔑 الكلمات المفتاحية:" if is_arabic else "🔑 Keywords:"
    kw_label = _prepare_text(kw_label, is_arabic)
    label_font = _get_font(12, arabic=is_arabic)
    draw.text((20, kw_y - 20), kw_label, fill=(200, 200, 220), font=label_font)

    # عرض الكلمات مع تمييز الحالية
    spacing = min(130, TARGET_W // max(len(all_keywords), 1))
    for i, kw in enumerate(all_keywords[:6]):
        kw_display = _prepare_text(kw[:18], is_arabic)
        x = 20 + i * spacing
        
        if i == current_idx:
            # الكلمة الحالية - مميزة
            kw_font = _get_font(14, bold=True, arabic=is_arabic)
            bbox = draw.textbbox((0, 0), kw_display, font=kw_font)
            kw_w = bbox[2] - bbox[0]
            draw.rounded_rectangle(
                [(x - 5, kw_y - 3), (x + kw_w + 10, kw_y + 20)],
                radius=5, fill=color
            )
            draw.text((x + 3, kw_y), kw_display, fill=(255, 255, 255), font=kw_font)
        elif i < current_idx:
            # تم شرحها
            kw_font = _get_font(12, arabic=is_arabic)
            draw.text((x, kw_y + 2), "✓ " + kw_display, fill=(100, 200, 100), font=kw_font)
        else:
            # قادمة
            kw_font = _get_font(12, arabic=is_arabic)
            draw.text((x, kw_y + 2), "○ " + kw_display, fill=(140, 150, 170), font=kw_font)

    # علامة مائية
    wm_font = _get_font(10)
    wm = WATERMARK
    bbox = draw.textbbox((0, 0), wm, font=wm_font)
    ww = bbox[2] - bbox[0]
    draw.text(((TARGET_W - ww)//2, TARGET_H - 15), wm, fill=(100, 110, 130), font=wm_font)

    bg.save(img_path, "JPEG", quality=92)
    return img_path


def _create_summary_slide(lecture_data: dict, sections: list, is_arabic: bool) -> str:
    """شريحة الملخص النهائي"""
    img_fd, img_path = tempfile.mkstemp(prefix="summary_", suffix=".jpg")
    os.close(img_fd)

    bg = _gradient_bg((20, 30, 50), (10, 20, 40))
    draw = ImageDraw.Draw(bg)

    # هيدر
    header_h = 50
    draw.rectangle([(0, 0), (TARGET_W, header_h)], fill=(25, 35, 55))
    draw.rectangle([(0, header_h - 2), (TARGET_W, header_h)], fill=(255, 200, 50))

    sum_title = "📋 ملخص المحاضرة" if is_arabic else "📋 Summary"
    sum_title = _prepare_text(sum_title, is_arabic)
    title_font = _get_font(22, bold=True, arabic=is_arabic)
    _draw_text_centered(draw, sum_title, 10, title_font, (255, 220, 80))

    # ملخص نصي
    y = header_h + 20
    summary = lecture_data.get("summary", "")
    if summary:
        sum_txt = _prepare_text(summary[:400], is_arabic)
        sum_font = _get_font(13, arabic=is_arabic)
        lines = textwrap.wrap(sum_txt, width=55)
        for line in lines[:8]:
            draw.text((30, y), line, fill=(220, 230, 255), font=sum_font)
            y += 22

    # النقاط الرئيسية
    y += 15
    points = lecture_data.get("key_points", [])[:5]
    if points:
        pt_label = "✨ النقاط الرئيسية:" if is_arabic else "✨ Key Points:"
        pt_label = _prepare_text(pt_label, is_arabic)
        pt_font = _get_font(14, bold=True, arabic=is_arabic)
        draw.text((30, y), pt_label, fill=(255, 200, 100), font=pt_font)
        y += 25
        
        point_font = _get_font(12, arabic=is_arabic)
        for p in points:
            p_txt = _prepare_text(f"• {p[:50]}", is_arabic)
            draw.text((45, y), p_txt, fill=(200, 210, 230), font=point_font)
            y += 22

    # صور مصغرة للأقسام
    thumb_y = TARGET_H - 100
    thumb_w = 100
    thumb_h = 70
    spacing = 10
    n_thumbs = min(len(sections), 4)
    total_w = n_thumbs * (thumb_w + spacing) - spacing
    start_x = (TARGET_W - total_w) // 2

    for i in range(n_thumbs):
        x = start_x + i * (thumb_w + spacing)
        color = ACCENT_COLORS[i % len(ACCENT_COLORS)]
        draw.rounded_rectangle(
            [(x, thumb_y), (x + thumb_w, thumb_y + thumb_h)],
            radius=8, fill=(30, 40, 60), outline=color, width=2
        )
        draw.text((x + thumb_w//2 - 5, thumb_y + thumb_h//2 - 8), str(i+1), 
                  fill=color, font=_get_font(18, bold=True))

    wm_font = _get_font(10)
    wm = WATERMARK
    bbox = draw.textbbox((0, 0), wm, font=wm_font)
    ww = bbox[2] - bbox[0]
    draw.text(((TARGET_W - ww)//2, TARGET_H - 15), wm, fill=(100, 110, 130), font=wm_font)

    bg.save(img_path, "JPEG", quality=90)
    return img_path


def _ffmpeg_segment(img_path: str, duration: float, audio_path: Optional[str],
                    audio_start: float, out_path: str, gentle_zoom: bool = True) -> None:
    dur_str = f"{duration:.3f}"
    fps = 15

    def audio_args():
        if audio_path and os.path.exists(audio_path):
            return ["-ss", f"{audio_start:.3f}", "-t", dur_str, "-i", audio_path]
        return ["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100"]

    if gentle_zoom:
        n_frames = max(int(duration * fps), 2)
        zp = f"zoompan=z='min(zoom+0.00012,1.025)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={n_frames}:s={TARGET_W}x{TARGET_H}:fps={fps}"
        vf = f"scale=900:506,{zp}"
        aud = audio_args()
        cmd = [
            "ffmpeg", "-y", "-loop", "1", "-t", dur_str, "-i", img_path,
            *aud, "-vf", vf, "-map", "0:v", "-map", "1:a",
            "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p", "-r", str(fps),
            "-c:a", "aac", "-b:a", "96k", "-ar", "44100", "-ac", "2",
            "-t", dur_str, out_path,
        ]
    else:
        vf = "scale=854:480:force_original_aspect_ratio=decrease,pad=854:480:(ow-iw)/2:(oh-ih)/2"
        aud = audio_args()
        cmd = [
            "ffmpeg", "-y", "-loop", "1", "-t", dur_str, "-i", img_path,
            *aud, "-c:v", "libx264", "-preset", "ultrafast", "-tune", "stillimage",
            "-pix_fmt", "yuv420p", "-r", "10", "-vf", vf,
            "-map", "0:v", "-map", "1:a", "-c:a", "aac", "-b:a", "96k",
            "-t", dur_str, out_path,
        ]

    subprocess.run(cmd, capture_output=True, check=True)


def _ffmpeg_concat(segments: list[str], output: str) -> None:
    fd, lst = tempfile.mkstemp(suffix=".txt")
    try:
        os.close(fd)
        with open(lst, "w") as f:
            for s in segments:
                f.write(f"file '{s}'\n")
        subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", output], 
                      capture_output=True, check=True)
    finally:
        try:
            os.remove(lst)
        except:
            pass


def _build_segments(
    sections: list,
    audio_results: list,
    lecture_data: dict,
    is_arabic: bool,
) -> tuple[list[dict], list[str], float]:
    segments = []
    tmp_files = []
    total_secs = 0.0
    n = len(sections)

    # حساب مدة الفيديو الكلية
    total_audio_dur = sum(r.get("duration", 0) for r in audio_results)
    intro_dur = min(INTRO_MAX, max(INTRO_MIN, n * 1.5))
    summary_dur = min(SUMMARY_MAX, max(SUMMARY_MIN, n * 1.0))

    # 1. المقدمة
    try:
        intro = _create_intro_slide(lecture_data, sections, is_arabic, total_audio_dur + intro_dur + summary_dur)
        tmp_files.append(intro)
        segments.append({"img": intro, "audio": None, "audio_start": 0, "dur": intro_dur, "gentle_zoom": False})
        total_secs += intro_dur
    except Exception as e:
        print(f"Intro error: {e}")

    # 2. الأقسام
    for i, (section, audio_info) in enumerate(zip(sections, audio_results)):
        # بطاقة عنوان القسم
        try:
            title_card = _create_section_title_card(section, i, n, is_arabic)
            tmp_files.append(title_card)
            segments.append({"img": title_card, "audio": None, "audio_start": 0, "dur": 2.5, "gentle_zoom": False})
            total_secs += 2.5
        except:
            pass

        # شرائح المحتوى
        keywords = section.get("keywords") or [f"Section {i+1}"]
        kw_images = section.get("_keyword_images") or []
        audio_bytes = audio_info.get("audio")
        total_dur = max(float(audio_info.get("duration", 10)), 4.0)
        kw_dur = total_dur / max(len(keywords), 1)

        apath = None
        if audio_bytes:
            afd, apath = tempfile.mkstemp(prefix=f"aud_{i}_", suffix=".mp3")
            os.close(afd)
            with open(apath, "wb") as f:
                f.write(audio_bytes)
            tmp_files.append(apath)

        for j, kw in enumerate(keywords):
            img_bytes = kw_images[j] if j < len(kw_images) else section.get("_image_bytes")
            
            # إذا ماكو صورة، نصنع صورة كرتونية بديلة
            if not img_bytes:
                img_bytes = _create_cartoon_placeholder(kw, section.get("title", ""), i, is_arabic)

            slide = _create_content_slide(
                img_bytes, kw, keywords, j, is_arabic,
                section.get("title", ""), i
            )
            tmp_files.append(slide)
            segments.append({
                "img": slide, "audio": apath, "audio_start": j * kw_dur,
                "dur": kw_dur, "gentle_zoom": True
            })
            total_secs += kw_dur

    # 3. الملخص
    try:
        summary = _create_summary_slide(lecture_data, sections, is_arabic)
        tmp_files.append(summary)
        segments.append({"img": summary, "audio": None, "audio_start": 0, "dur": summary_dur, "gentle_zoom": False})
        total_secs += summary_dur
    except:
        pass

    return segments, tmp_files, total_secs


def _encode_all(segments: list[dict], output: str) -> None:
    seg_paths = []
    try:
        for i, seg in enumerate(segments):
            fd, out = tempfile.mkstemp(prefix=f"seg_{i}_", suffix=".mp4")
            os.close(fd)
            seg_paths.append(out)
            _ffmpeg_segment(
                seg["img"], seg["dur"], seg.get("audio"),
                seg.get("audio_start", 0), out, seg.get("gentle_zoom", False)
            )
        _ffmpeg_concat(seg_paths, output)
    finally:
        for p in seg_paths:
            try:
                os.remove(p)
            except:
                pass


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

    if not segments:
        raise RuntimeError("No segments generated")

    est = estimate_encoding_seconds(total_secs)
    encode_task = loop.run_in_executor(None, _encode_all, segments, output_path)

    start = loop.time()
    while not encode_task.done():
        await asyncio.sleep(3)
        if progress_cb:
            try:
                await progress_cb(loop.time() - start, est)
            except:
                pass
    await encode_task

    for p in tmp_files:
        try:
            os.remove(p)
        except:
            pass

    return total_secs
