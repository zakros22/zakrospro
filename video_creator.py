import asyncio
import io
import os
import subprocess
import tempfile
import textwrap
from typing import Callable, Awaitable, Optional, List

from PIL import Image as PILImage, ImageDraw, ImageFont, ImageFilter

TARGET_W, TARGET_H = 854, 480
WATERMARK = "@zakros_probot"
FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_REG = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
_FONTS_DIR = os.path.join(os.path.dirname(__file__), "fonts")
FONT_AR_BOLD = os.path.join(_FONTS_DIR, "Amiri-Bold.ttf")
FONT_AR_REG = os.path.join(_FONTS_DIR, "Amiri-Regular.ttf")

_ENC_FACTOR = 0.6
_MIN_ENC_SEC = 20.0

# المدد الزمنية لكل شريحة
INTRO_DURATION = 8.0
SECTION_TITLE_DURATION = 3.0
SUMMARY_DURATION = 8.0

# ألوان احترافية
ACCENT_COLORS = [
    (100, 180, 255), (100, 220, 160), (255, 180, 80),
    (220, 120, 255), (255, 120, 120), (80, 220, 220),
    (255, 200, 100), (160, 255, 160), (255, 150, 200),
]

BG_GRADIENTS = [
    ((10, 20, 50), (5, 40, 70)),
    ((20, 30, 60), (5, 20, 50)),
    ((30, 20, 50), (10, 30, 60)),
    ((15, 25, 55), (5, 35, 65)),
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
            except Exception:
                pass
    path = FONT_BOLD if bold else FONT_REG
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()


def _prepare_text(text: str, is_arabic: bool) -> str:
    """تجهيز النص العربي مع إعادة تشكيل و BiDi"""
    if not is_arabic or not text:
        return text
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
        return get_display(arabic_reshaper.reshape(str(text)))
    except Exception:
        return str(text)


def _draw_text_with_shadow(draw, xy: tuple, text: str, font, fill, shadow_fill=(0, 0, 0, 120)):
    """رسم نص مع ظل"""
    x, y = xy
    draw.text((x + 2, y + 2), text, fill=shadow_fill, font=font)
    draw.text((x, y), text, fill=fill, font=font)


def _draw_text_centered(draw, text: str, y: int, font, color, max_width: int = None):
    """رسم نص في المنتصف مع دعم التفاف النص"""
    if max_width:
        words = text.split()
        lines = []
        current_line = []
        for word in words:
            current_line.append(word)
            test_line = ' '.join(current_line)
            bbox = draw.textbbox((0, 0), test_line, font=font)
            if bbox[2] - bbox[0] > max_width:
                current_line.pop()
                if current_line:
                    lines.append(' '.join(current_line))
                current_line = [word]
        if current_line:
            lines.append(' '.join(current_line))
        text = '\n'.join(lines)

    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    x = max((TARGET_W - tw) // 2, 20)
    _draw_text_with_shadow(draw, (x, y), text, font, color)


def _gradient_bg(color_top=(10, 20, 50), color_bot=(5, 40, 70)) -> PILImage.Image:
    """إنشاء خلفية متدرجة"""
    bg = PILImage.new("RGB", (TARGET_W, TARGET_H), color_top)
    draw = ImageDraw.Draw(bg)
    for y in range(TARGET_H):
        t = y / TARGET_H
        r = int(color_top[0] * (1 - t) + color_bot[0] * t)
        g = int(color_top[1] * (1 - t) + color_bot[1] * t)
        b = int(color_top[2] * (1 - t) + color_bot[2] * t)
        draw.line([(0, y), (TARGET_W, y)], fill=(r, g, b))
    return bg


def _resize_image_for_slide(image_bytes: bytes, target_w: int, target_h: int) -> bytes:
    """تغيير حجم الصورة لتناسب الشريحة مع الحفاظ على النسبة"""
    try:
        img = PILImage.open(io.BytesIO(image_bytes)).convert("RGB")
        iw, ih = img.size

        # حساب النسبة المناسبة
        scale = min(target_w / iw, target_h / ih)
        nw, nh = int(iw * scale), int(ih * scale)

        img = img.resize((nw, nh), PILImage.LANCZOS)

        # إضافة حدود ناعمة
        bordered = PILImage.new("RGB", (target_w, target_h), (20, 25, 40))
        px = (target_w - nw) // 2
        py = (target_h - nh) // 2
        bordered.paste(img, (px, py))

        # إضافة ظل خفيف للصورة
        shadow = PILImage.new("RGBA", (nw + 10, nh + 10), (0, 0, 0, 0))
        shadow_draw = ImageDraw.Draw(shadow)
        shadow_draw.rectangle([(5, 5), (nw + 5, nh + 5)], fill=(0, 0, 0, 100))
        shadow = shadow.filter(ImageFilter.GaussianBlur(radius=8))

        # دمج الظل مع الصورة
        final_img = PILImage.new("RGB", (target_w, target_h), (20, 25, 40))
        shadow_mask = shadow.split()[3] if shadow.mode == 'RGBA' else None
        if shadow_mask:
            final_img.paste(shadow, (px - 5, py - 5), shadow_mask)
        final_img.paste(bordered, (0, 0))

        buf = io.BytesIO()
        final_img.save(buf, "JPEG", quality=92)
        return buf.getvalue()
    except Exception as e:
        print(f"Error resizing image: {e}")
        return image_bytes


def _create_intro_slide(lecture_data: dict, sections: list, is_arabic: bool) -> str:
    """
    شريحة المقدمة:
    - شعار البوت وحقوقه في مربع بالأعلى
    - عنوان المحاضرة
    - خريطة الأقسام (أرقام وعناوين)
    """
    img_fd, img_path = tempfile.mkstemp(prefix="intro_", suffix=".jpg")
    os.close(img_fd)

    bg_grad = BG_GRADIENTS[0]
    bg = _gradient_bg(bg_grad[0], bg_grad[1])
    draw = ImageDraw.Draw(bg)

    # ── مربع الحقوق في الأعلى ────────────────────────────────────────────────
    header_h = 55
    draw.rectangle([(0, 0), (TARGET_W, header_h)], fill=(15, 25, 45))
    draw.rectangle([(0, header_h - 3), (TARGET_W, header_h)], fill=(220, 170, 30))

    # شعار البوت
    logo_font = _get_font(18, bold=True, arabic=False)
    logo_text = "🎓 ZAKROS PRO BOT"
    draw.text((15, 12), logo_text, fill=(255, 220, 100), font=logo_font)

    # حقوق البوت
    rights_font = _get_font(12, arabic=False)
    rights_text = "© جميع الحقوق محفوظة - بوت المحاضرات الذكي"
    if is_arabic:
        rights_text = _prepare_text("© جميع الحقوق محفوظة - بوت المحاضرات الذكي", True)
    bbox = draw.textbbox((0, 0), rights_text, font=rights_font)
    rw = bbox[2] - bbox[0]
    draw.text((TARGET_W - rw - 15, 18), rights_text, fill=(200, 200, 220), font=rights_font)

    # ── عنوان المحاضرة ────────────────────────────────────────────────────────
    title_raw = lecturedata.get("title", "المحاضرة" if is_arabic else "Lecture")
    title_txt = _prepare_text(title_raw, is_arabic)
    title_font = _get_font(28, bold=True, arabic=is_arabic)
    _draw_text_centered(draw, title_txt, header_h + 25, title_font, (255, 220, 80), max_width=TARGET_W - 60)

    # ── نوع المحاضرة ──────────────────────────────────────────────────────────
    lecture_type = lecturedata.get("lecture_type", "other")
    type_labels = {
        "medicine": "🩺 محاضرة طبية" if is_arabic else "Medical Lecture",
        "science": "🔬 محاضرة علمية" if is_arabic else "Science Lecture",
        "math": "📐 رياضيات" if is_arabic else "Mathematics",
        "literature": "📖 أدب ولغة" if is_arabic else "Literature",
        "computer": "💻 علوم الحاسوب" if is_arabic else "Computer Science",
        "history": "🏛️ التاريخ" if is_arabic else "History",
        "business": "💼 إدارة الأعمال" if is_arabic else "Business",
        "other": "📚 محاضرة تعليمية" if is_arabic else "Educational Lecture",
    }
    type_label = type_labels.get(lecture_type, type_labels["other"])
    type_txt = _prepare_text(type_label, is_arabic)
    type_font = _get_font(16, arabic=is_arabic)
    _draw_text_centered(draw, type_txt, header_h + 65, type_font, (180, 200, 240))

    # خط فاصل
    draw.rectangle([(60, header_h + 90), (TARGET_W - 60, header_h + 92)], fill=(220, 170, 30))

    # ── خريطة الأقسام ──────────────────────────────────────────────────────────
    map_y = header_h + 110
    map_title = "📋 خريطة المحاضرة" if is_arabic else "📋 Lecture Map"
    map_title_txt = _prepare_text(map_title, is_arabic)
    map_title_font = _get_font(18, bold=True, arabic=is_arabic)
    _draw_text_centered(draw, map_title_txt, map_y, map_title_font, (255, 255, 255))

    map_y += 35
    max_sections = min(len(sections), 8)
    section_font = _get_font(14, bold=True, arabic=is_arabic)
    num_font = _get_font(16, bold=True)

    for i, section in enumerate(sections[:max_sections]):
        accent = ACCENT_COLORS[i % len(ACCENT_COLORS)]

        # رقم القسم في دائرة
        cx, cy = 50, map_y + i * 32
        draw.ellipse([cx - 12, cy - 12, cx + 12, cy + 12], fill=accent)
        draw.text((cx - 6, cy - 10), str(i + 1), fill=(255, 255, 255), font=num_font)

        # عنوان القسم
        sec_title = section.get("title", f"القسم {i + 1}")[:40]
        sec_txt = _prepare_text(sec_title, is_arabic)
        draw.text((cx + 20, cy - 8), sec_txt, fill=(220, 230, 255), font=section_font)

    # علامة مائية
    wm_font = _get_font(11)
    wm_text = WATERMARK
    bbox = draw.textbbox((0, 0), wm_text, font=wm_font)
    ww = bbox[2] - bbox[0]
    draw.text(((TARGET_W - ww) // 2, TARGET_H - 20), wm_text, fill=(120, 130, 150), font=wm_font)

    bg.save(img_path, "JPEG", quality=90)
    return img_path


def _create_section_title_card(section: dict, idx: int, total: int, is_arabic: bool) -> str:
    """
    بطاقة عنوان القسم:
    "القسم الأول: [عنوان القسم]"
    مع ترقيم واضح
    """
    img_fd, img_path = tempfile.mkstemp(prefix=f"sec_title_{idx}_", suffix=".jpg")
    os.close(img_fd)

    accent = ACCENT_COLORS[idx % len(ACCENT_COLORS)]
    bg_grad = BG_GRADIENTS[idx % len(BG_GRADIENTS)]
    bg = _gradient_bg(bg_grad[0], bg_grad[1])
    draw = ImageDraw.Draw(bg)

    # إطار ذهبي
    draw.rectangle([(8, 8), (TARGET_W - 8, TARGET_H - 8)], outline=(255, 200, 50), width=3)
    draw.rectangle([(12, 12), (TARGET_W - 12, TARGET_H - 12)], outline=accent, width=1)

    # رقم القسم كبير في المنتصف
    center_y = TARGET_H // 2 - 40
    num_str = str(idx + 1)
    num_font = _get_font(80, bold=True)
    bbox = draw.textbbox((0, 0), num_str, font=num_font)
    nw = bbox[2] - bbox[0]
    draw.text(((TARGET_W - nw) // 2, center_y - 30), num_str, fill=accent, font=num_font)

    # "القسم" / "Section"
    section_label = "القسم" if is_arabic else "Section"
    section_label = _prepare_text(section_label, is_arabic)
    label_font = _get_font(20, arabic=is_arabic)
    _draw_text_centered(draw, section_label, center_y + 30, label_font, (200, 210, 240))

    # عنوان القسم
    title_raw = section.get("title", f"Section {idx + 1}")
    title_txt = _prepare_text(title_raw, is_arabic)
    title_font = _get_font(24, bold=True, arabic=is_arabic)
    _draw_text_centered(draw, title_txt, center_y + 65, title_font, (255, 220, 100), max_width=TARGET_W - 80)

    # تقدم الأقسام (X/Y)
    progress = f"{idx + 1} / {total}"
    prog_font = _get_font(14)
    bbox = draw.textbbox((0, 0), progress, font=prog_font)
    pw = bbox[2] - bbox[0]
    draw.text(((TARGET_W - pw) // 2, TARGET_H - 40), progress, fill=(150, 160, 180), font=prog_font)

    # علامة مائية
    wm_font = _get_font(11)
    wm_text = WATERMARK
    bbox = draw.textbbox((0, 0), wm_text, font=wm_font)
    ww = bbox[2] - bbox[0]
    draw.text(((TARGET_W - ww) // 2, TARGET_H - 20), wm_text, fill=(100, 110, 130), font=wm_font)

    bg.save(img_path, "JPEG", quality=90)
    return img_path


def _create_content_slide(
    image_bytes: Optional[bytes],
    keyword: str,
    all_keywords: List[str],
    current_idx: int,
    is_arabic: bool,
    section_title: str = "",
) -> str:
    """
    شريحة المحتوى الرئيسية:
    - صورة كبيرة وواضحة في المنتصف
    - الكلمات المفتاحية أسفل الصورة مع تمييز الحالية
    - عنوان القسم في الأعلى
    """
    img_fd, img_path = tempfile.mkstemp(prefix="content_", suffix=".jpg")
    os.close(img_fd)

    bg_grad = BG_GRADIENTS[current_idx % len(BG_GRADIENTS)]
    bg = _gradient_bg(bg_grad[0], bg_grad[1])
    draw = ImageDraw.Draw(bg)

    # ── شريط عنوان القسم في الأعلى ────────────────────────────────────────────
    header_h = 45
    draw.rectangle([(0, 0), (TARGET_W, header_h)], fill=(15, 25, 45))
    draw.rectangle([(0, header_h - 2), (TARGET_W, header_h)], fill=ACCENT_COLORS[current_idx % len(ACCENT_COLORS)])

    section_display = section_title[:50] if section_title else ""
    section_txt = _prepare_text(section_display, is_arabic)
    section_font = _get_font(16, bold=True, arabic=is_arabic)
    _draw_text_centered(draw, section_txt, 10, section_font, (255, 255, 255))

    # ── منطقة الصورة (كبيرة وواضحة) ────────────────────────────────────────────
    img_area_top = header_h + 10
    img_area_bottom = TARGET_H - 70
    img_area_h = img_area_bottom - img_area_top
    img_area_w = TARGET_W - 40

    if image_bytes:
        try:
            # تجهيز الصورة لتكون كبيرة وواضحة
            img = PILImage.open(io.BytesIO(image_bytes)).convert("RGB")
            iw, ih = img.size

            # حساب الأبعاد المناسبة
            scale = min(img_area_w / iw, img_area_h / ih)
            nw, nh = int(iw * scale), int(ih * scale)

            img = img.resize((nw, nh), PILImage.LANCZOS)

            # إضافة إطار للصورة
            bordered = PILImage.new("RGB", (nw + 8, nh + 8), (30, 35, 50))
            bordered.paste(img, (4, 4))

            # إضافة ظل
            shadow = PILImage.new("RGBA", (nw + 20, nh + 20), (0, 0, 0, 0))
            shadow_draw = ImageDraw.Draw(shadow)
            shadow_draw.rectangle([(10, 10), (nw + 10, nh + 10)], fill=(0, 0, 0, 100))
            shadow = shadow.filter(ImageFilter.GaussianBlur(radius=6))

            # دمج الظل مع الصورة
            final_img = PILImage.new("RGB", (nw + 20, nh + 20), bg_grad[0])
            shadow_mask = shadow.split()[3] if shadow.mode == 'RGBA' else None
            if shadow_mask:
                final_img.paste(shadow, (0, 0), shadow_mask)
            final_img.paste(bordered, (6, 6))

            # وضع الصورة في المنتصف
            px = (TARGET_W - (nw + 20)) // 2
            py = img_area_top + (img_area_h - (nh + 20)) // 2
            bg.paste(final_img, (px, py))

            draw = ImageDraw.Draw(bg)  # إعادة إنشاء draw بعد paste
        except Exception as e:
            print(f"Error loading image: {e}")
            # رسم مربع فارغ مع نص "الصورة غير متوفرة"
            draw.rectangle(
                [(img_area_top, img_area_top), (TARGET_W - 20, img_area_bottom)],
                outline=(100, 100, 120), width=2
            )
            placeholder = "🖼️ الصورة التعليمية" if is_arabic else "Educational Image"
            placeholder = _prepare_text(placeholder, is_arabic)
            place_font = _get_font(18, arabic=is_arabic)
            _draw_text_centered(draw, placeholder, TARGET_H // 2 - 20, place_font, (150, 160, 180))

    # ── الكلمات المفتاحية أسفل الصورة ──────────────────────────────────────────
    kw_y = TARGET_H - 55
    kw_font = _get_font(13, bold=True, arabic=is_arabic)
    small_font = _get_font(11, arabic=is_arabic)

    # عنوان "الكلمات المفتاحية"
    kw_label = "🔑 الكلمات المفتاحية:" if is_arabic else "🔑 Keywords:"
    kw_label = _prepare_text(kw_label, is_arabic)
    draw.text((20, kw_y - 20), kw_label, fill=(200, 200, 220), font=small_font)

    # عرض الكلمات مع تمييز الحالية
    spacing = TARGET_W // max(len(all_keywords), 1)
    for i, kw in enumerate(all_keywords[:6]):  # حد أقصى 6 كلمات
        kw_display = _prepare_text(kw[:20], is_arabic)
        x = 20 + i * (spacing if spacing > 120 else 120)

        if i == current_idx:
            # الكلمة الحالية - مميزة
            bbox = draw.textbbox((0, 0), kw_display, font=kw_font)
            kw_w = bbox[2] - bbox[0]
            # خلفية ملونة للكلمة الحالية
            draw.rectangle(
                [(x - 5, kw_y - 3), (x + kw_w + 10, kw_y + 20)],
                fill=ACCENT_COLORS[current_idx % len(ACCENT_COLORS)]
            )
            draw.text((x + 3, kw_y), kw_display, fill=(255, 255, 255), font=kw_font)
        elif i < current_idx:
            # كلمات تم شرحها
            draw.text((x, kw_y), "✓ " + kw_display, fill=(100, 180, 100), font=small_font)
        else:
            # كلمات قادمة
            draw.text((x, kw_y), "○ " + kw_display, fill=(120, 130, 150), font=small_font)

    # علامة مائية
    wm_font = _get_font(10)
    wm_text = WATERMARK
    bbox = draw.textbbox((0, 0), wm_text, font=wm_font)
    ww = bbox[2] - bbox[0]
    draw.text(((TARGET_W - ww) // 2, TARGET_H - 15), wm_text, fill=(80, 90, 110), font=wm_font)

    bg.save(img_path, "JPEG", quality=92)
    return img_path


def _create_summary_slide(lecture_data: dict, sections: list, is_arabic: bool) -> str:
    """
    شريحة الملخص النهائية:
    - صور مصغرة للأقسام
    - ملخص نصي للمحاضرة
    - النقاط الرئيسية
    """
    img_fd, img_path = tempfile.mkstemp(prefix="summary_", suffix=".jpg")
    os.close(img_fd)

    bg = _gradient_bg((15, 25, 45), (5, 35, 65))
    draw = ImageDraw.Draw(bg)

    # ── عنوان الملخص ──────────────────────────────────────────────────────────
    header_h = 50
    draw.rectangle([(0, 0), (TARGET_W, header_h)], fill=(20, 30, 50))
    draw.rectangle([(0, header_h - 2), (TARGET_W, header_h)], fill=(255, 200, 50))

    summary_title = "📋 ملخص المحاضرة" if is_arabic else "📋 Lecture Summary"
    summary_title = _prepare_text(summary_title, is_arabic)
    title_font = _get_font(22, bold=True, arabic=is_arabic)
    _draw_text_centered(draw, summary_title, 10, title_font, (255, 220, 80))

    # ── صور مصغرة للأقسام ─────────────────────────────────────────────────────
    thumb_y = header_h + 15
    thumb_h = 90
    thumb_w = 120
    spacing = 10
    total_w = len(sections[:4]) * (thumb_w + spacing) - spacing
    start_x = (TARGET_W - total_w) // 2

    for i, section in enumerate(sections[:4]):
        x = start_x + i * (thumb_w + spacing)

        # إطار للصورة المصغرة
        draw.rectangle([(x - 2, thumb_y - 2), (x + thumb_w + 2, thumb_y + thumb_h + 2)],
                       fill=(40, 50, 70))
        draw.rectangle([(x, thumb_y), (x + thumb_w, thumb_y + thumb_h)],
                       fill=(25, 35, 55), outline=ACCENT_COLORS[i % len(ACCENT_COLORS)], width=1)

        # محاولة عرض الصورة إذا كانت موجودة
        img_bytes = section.get("_image_bytes") or (section.get("_keyword_images", [None])[0] if section.get("_keyword_images") else None)
        if img_bytes:
            try:
                thumb = PILImage.open(io.BytesIO(img_bytes)).convert("RGB")
                thumb = thumb.resize((thumb_w - 8, thumb_h - 8), PILImage.LANCZOS)
                bg.paste(thumb, (x + 4, thumb_y + 4))
            except Exception:
                pass

        # رقم القسم
        draw.text((x + 5, thumb_y + thumb_h - 18), str(i + 1), fill=(255, 255, 255),
                  font=_get_font(14, bold=True))

    # ── الملخص النصي ──────────────────────────────────────────────────────────
    text_y = thumb_y + thumb_h + 20

    summary_text = lecturedata.get("summary", "")
    if summary_text:
        summary_txt = _prepare_text(summary_text[:300], is_arabic)
        summary_font = _get_font(13, arabic=is_arabic)

        # تقسيم النص لأسطر
        lines = textwrap.wrap(summary_txt, width=60 if is_arabic else 70)
        for i, line in enumerate(lines[:6]):
            y = text_y + i * 22
            _draw_text_centered(draw, line, y, summary_font, (220, 230, 255))

    # ── النقاط الرئيسية ────────────────────────────────────────────────────────
    key_points = lecturedata.get("key_points", [])[:4]
    if key_points:
        points_y = text_y + min(len(summary_text.split()) * 0.5, 120) + 20
        points_label = "✨ النقاط الرئيسية:" if is_arabic else "✨ Key Points:"
        points_label = _prepare_text(points_label, is_arabic)
        label_font = _get_font(14, bold=True, arabic=is_arabic)
        draw.text((30, points_y), points_label, fill=(255, 200, 100), font=label_font)

        point_font = _get_font(12, arabic=is_arabic)
        for i, point in enumerate(key_points):
            point_txt = _prepare_text(f"• {point[:50]}", is_arabic)
            draw.text((50, points_y + 25 + i * 22), point_txt, fill=(200, 210, 230), font=point_font)

    # علامة مائية
    wm_font = _get_font(11)
    wm_text = WATERMARK
    bbox = draw.textbbox((0, 0), wm_text, font=wm_font)
    ww = bbox[2] - bbox[0]
    draw.text(((TARGET_W - ww) // 2, TARGET_H - 20), wm_text, fill=(100, 110, 130), font=wm_font)

    bg.save(img_path, "JPEG", quality=90)
    return img_path


# ─────────────────────────────────────────────────────────────────────────────
# FFmpeg helpers
# ─────────────────────────────────────────────────────────────────────────────

def _ffmpeg_segment(img_path: str, duration: float, audio_path: Optional[str],
                    audio_start: float, out_path: str,
                    gentle_zoom: bool = True) -> None:
    """تشفير مقطع فيديو من صورة وصوت"""
    dur_str = f"{duration:.3f}"
    fps_main = 15

    def _audio_args():
        if audio_path and os.path.exists(audio_path):
            return ["-ss", f"{audio_start:.3f}", "-t", dur_str, "-i", audio_path]
        return ["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100"]

    if gentle_zoom:
        n_frames = max(int(duration * fps_main), 2)
        zp = f"zoompan=z='min(zoom+0.00015,1.03)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={n_frames}:s={TARGET_W}x{TARGET_H}:fps={fps_main}"
        vf = f"scale=900:506,{zp}"
        aud = _audio_args()
        cmd = [
            "ffmpeg", "-y",
            "-loop", "1", "-t", dur_str, "-i", img_path,
            *aud,
            "-vf", vf,
            "-map", "0:v", "-map", "1:a",
            "-c:v", "libx264", "-preset", "fast",
            "-pix_fmt", "yuv420p", "-r", str(fps_main),
            "-c:a", "aac", "-b:a", "96k", "-ar", "44100", "-ac", "2",
            "-t", dur_str, out_path,
        ]
    else:
        vf = "scale=854:480:force_original_aspect_ratio=decrease,pad=854:480:(ow-iw)/2:(oh-ih)/2"
        aud = _audio_args()
        cmd = [
            "ffmpeg", "-y",
            "-loop", "1", "-t", dur_str, "-i", img_path,
            *aud,
            "-c:v", "libx264", "-preset", "ultrafast", "-tune", "stillimage",
            "-pix_fmt", "yuv420p", "-r", "10", "-vf", vf,
            "-map", "0:v", "-map", "1:a",
            "-c:a", "aac", "-b:a", "96k", "-ar", "44100", "-ac", "2",
            "-t", dur_str, out_path,
        ]

    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg segment failed: {result.stderr[-600:]}")


def _ffmpeg_concat(segment_paths: list[str], output_path: str) -> None:
    """دمج المقاطع"""
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
# بناء قائمة المقاطع
# ─────────────────────────────────────────────────────────────────────────────

def _build_segment_list(
    sections: list,
    audio_results: list,
    lecturedata: dict,
    is_arabic: bool,
) -> tuple[list[dict], list[str], float]:
    """بناء قائمة المقاطع للفيديو"""
    segments: list[dict] = []
    tmp_files: list[str] = []
    total_secs = 0.0
    n_sections = len(sections)

    # ── 1. شريحة المقدمة ──────────────────────────────────────────────────────
    try:
        intro_path = _create_intro_slide(lecture_data, sections, is_arabic)
        tmp_files.append(intro_path)
        segments.append({"img": intro_path, "audio": None, "audio_start": 0.0, "dur": INTRO_DURATION, "gentle_zoom": False})
        total_secs += INTRO_DURATION
    except Exception as e:
        print(f"Intro slide failed: {e}")

    # ── 2. الأقسام ────────────────────────────────────────────────────────────
    for sec_idx, (section, audio_info) in enumerate(zip(sections, audio_results)):
        # 2a. بطاقة عنوان القسم
        try:
            title_path = _create_section_title_card(section, sec_idx, n_sections, is_arabic)
            tmp_files.append(title_path)
            segments.append({"img": title_path, "audio": None, "audio_start": 0.0, "dur": SECTION_TITLE_DURATION, "gentle_zoom": False})
            total_secs += SECTION_TITLE_DURATION
        except Exception as e:
            print(f"Section title card {sec_idx + 1} failed: {e}")

        # 2b. شرائح المحتوى
        keywords = section.get("keywords") or [section.get("title", f"Section {sec_idx + 1}")]
        kw_images = section.get("_keyword_images") or []
        audio_bytes = audio_info.get("audio")
        total_dur = max(float(audio_info.get("duration", section.get("duration_estimate", 8) or 8)), 3.0)
        kw_dur = total_dur / max(len(keywords), 1)

        apath = None
        if audio_bytes:
            afd, apath = tempfile.mkstemp(prefix=f"aud_{sec_idx}_", suffix=".mp3")
            os.close(afd)
            with open(apath, "wb") as f:
                f.write(audio_bytes)
            tmp_files.append(apath)

        sec_title = section.get("title", "")

        for kw_idx, keyword in enumerate(keywords):
            img_bytes = kw_images[kw_idx] if kw_idx < len(kw_images) else section.get("_image_bytes")

            # شريحة المحتوى (صورة كبيرة + كلمات مفتاحية أسفلها)
            content_path = _create_content_slide(
                image_bytes=img_bytes,
                keyword=keyword,
                all_keywords=keywords,
                current_idx=kw_idx,
                is_arabic=is_arabic,
                section_title=sec_title,
            )
            tmp_files.append(content_path)

            segments.append({
                "img": content_path,
                "audio": apath,
                "audio_start": kw_idx * kw_dur,
                "dur": kw_dur,
                "gentle_zoom": True,
            })
            total_secs += kw_dur

    # ── 3. شريحة الملخص ───────────────────────────────────────────────────────
    try:
        summary_path = _create_summary_slide(lecture_data, sections, is_arabic)
        tmp_files.append(summary_path)
        segments.append({"img": summary_path, "audio": None, "audio_start": 0.0, "dur": SUMMARY_DURATION, "gentle_zoom": False})
        total_secs += SUMMARY_DURATION
    except Exception as e:
        print(f"Summary slide failed: {e}")

    return segments, tmp_files, total_secs


def _encode_all_sync(segments: list[dict], output_path: str) -> None:
    """تشفير جميع المقاطع ودمجها"""
    seg_paths: list[str] = []
    try:
        for i, seg in enumerate(segments):
            fd, seg_out = tempfile.mkstemp(prefix=f"seg_{i}_", suffix=".mp4")
            os.close(fd)
            seg_paths.append(seg_out)
            _ffmpeg_segment(
                seg["img"], seg["dur"], seg.get("audio"), seg.get("audio_start", 0.0), seg_out,
                gentle_zoom=seg.get("gentle_zoom", False),
            )
            print(f"  ✅ Segment {i + 1}/{len(segments)} encoded ({seg['dur']:.1f}s)")

        _ffmpeg_concat(seg_paths, output_path)
        print(f"  ✅ Concatenated {len(seg_paths)} segments → {output_path}")
    finally:
        for p in seg_paths:
            try:
                os.remove(p)
            except Exception:
                pass


# ─────────────────────────────────────────────────────────────────────────────
# الوظيفة العامة الرئيسية
# ─────────────────────────────────────────────────────────────────────────────

async def create_video_from_sections(
    sections: list,
    audio_results: list,
    lecturedata: dict,
    output_path: str,
    dialect: str = "msa",
    progress_cb: Callable[[float, float], Awaitable[None]] | None = None,
) -> float:
    """
    إنشاء فيديو المحاضرة الكامل
    """
    is_arabic = dialect not in ("english", "british")
    loop = asyncio.get_event_loop()

    segments, tmp_files, total_video_secs = await loop.run_in_executor(
        None, _build_segment_list, sections, audio_results, lecturedata, is_arabic
    )

    if not segments:
        raise RuntimeError("No valid segments were generated for the video")

    estimated_enc = estimate_encoding_seconds(total_video_secs)

    encode_task = loop.run_in_executor(None, _encode_all_sync, segments, output_path)

    start = loop.time()
    try:
        while not encode_task.done():
            await asyncio.sleep(5)
            if encode_task.done():
                break
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
