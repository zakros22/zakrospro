# video_creator.py
# -*- coding: utf-8 -*-
"""
مصنع الفيديو التعليمي بأسلوب Osmosis (السبورة البيضاء)
مسؤول عن إنشاء فيديو تعليمي احترافي مع شخصية كرتونية طبية
"""

import os
import re
import json
import subprocess
import logging
import uuid
import math
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any, Union
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor, as_completed

# مكتبات الصور والرسوم
try:
    from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps, ImageColor
except ImportError:
    Image = None
    logging.error("Pillow غير مثبتة - مطلوبة لإنشاء الفيديو")

# مكتبات دعم العربية
try:
    import arabic_reshaper
    from bidi.algorithm import get_display
    ARABIC_SUPPORT = True
except ImportError:
    ARABIC_SUPPORT = False
    logging.warning("arabic_reshaper أو python-bidi غير مثبتين. دعم العربية محدود.")

from config import config

logger = logging.getLogger(__name__)

# ==================== الثوابت والألوان ====================

# أبعاد الفيديو (16:9 مصغر)
VIDEO_WIDTH = config.VIDEO_WIDTH
VIDEO_HEIGHT = config.VIDEO_HEIGHT
FPS = config.VIDEO_FPS

# الألوان المستخدمة في التصميم (أسلوب طبي حديث)
COLORS = {
    "primary": "#E84A7A",      # وردي طبي
    "secondary": "#4A90E2",    # أزرق
    "accent1": "#50E3C2",      # أخضر نعناعي
    "accent2": "#9B59B6",      # بنفسجي
    "accent3": "#F5A623",      # برتقالي
    "dark": "#2C3E50",         # أزرق داكن للنصوص
    "light": "#F8F9FA",        # خلفية فاتحة
    "white": "#FFFFFF",
    "black": "#1A1A1A",
    "gray": "#95A5A6",
    "red": "#E74C3C",
    "success": "#27AE60",
}

# ألوان الشخصيات حسب التخصص
TEACHER_OUTFITS = {
    "cardiology": {"coat": "#E74C3C", "accessory": "stethoscope", "hat": "cap", "bg": "#FDEDEC"},
    "pulmonology": {"coat": "#3498DB", "accessory": "stethoscope", "hat": "cap", "bg": "#EBF5FB"},
    "neurology": {"coat": "#9B59B6", "accessory": "hammer", "hat": "cap", "bg": "#F4ECF7"},
    "gastroenterology": {"coat": "#E67E22", "accessory": "stethoscope", "hat": "cap", "bg": "#FDF2E9"},
    "nephrology": {"coat": "#1ABC9C", "accessory": "stethoscope", "hat": "cap", "bg": "#E8F8F5"},
    "endocrinology": {"coat": "#F39C12", "accessory": "stethoscope", "hat": "cap", "bg": "#FEF5E7"},
    "oncology": {"coat": "#8E44AD", "accessory": "ribbon", "hat": "cap", "bg": "#F4ECF7"},
    "general": {"coat": "#5D6D7E", "accessory": "stethoscope", "hat": "cap", "bg": "#EAECEE"},
}

# أسماء المعلمين الافتراضية
TEACHER_NAMES = {
    "cardiology": "د. قلب",
    "pulmonology": "د. رئة",
    "neurology": "د. أعصاب",
    "general": "د. عام",
}

# العلامة المائية
WATERMARK = config.WATERMARK_TEXT

# ==================== تحميل الخطوط ====================

def _get_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """تحميل خط مناسب مع دعم العربية"""
    font_paths = [
        # خطوط تدعم العربية
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/TTF/DejaVuSans.ttf",
        "C:\\Windows\\Fonts\\arial.ttf",
        "C:\\Windows\\Fonts\\tahoma.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
    ]

    if bold:
        font_paths = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
            "C:\\Windows\\Fonts\\arialbd.ttf",
            "C:\\Windows\\Fonts\\tahomabd.ttf",
            "/System/Library/Fonts/Helvetica-Bold.ttf",
        ] + font_paths

    for path in font_paths:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except:
                continue

    # خط احتياطي
    return ImageFont.load_default()


def _arabic(text: str) -> str:
    """تشكيل وعكس النص العربي للعرض الصحيح في PIL"""
    if not text:
        return text
    if ARABIC_SUPPORT:
        try:
            reshaped = arabic_reshaper.reshape(text)
            return get_display(reshaped)
        except:
            pass
    return text


def _draw_text(draw: ImageDraw.Draw, xy: Tuple[int, int], text: str,
               fill: str = COLORS["dark"], font: ImageFont.FreeTypeFont = None,
               anchor: str = None, shadow: bool = True, language: str = "ar",
               max_width: int = None) -> None:
    """
    رسم نص مع دعم العربية وظل خفيف.
    """
    if not text:
        return

    if font is None:
        font = _get_font(24)

    # معالجة النص العربي
    display_text = _arabic(text) if language == "ar" else text

    # رسم الظل
    if shadow:
        shadow_xy = (xy[0] + 1, xy[1] + 1)
        draw.text(shadow_xy, display_text, fill="#888888", font=font, anchor=anchor)

    # رسم النص الأساسي
    if max_width and font:
        # التفاف النص إذا كان أطول من العرض المسموح
        lines = _wrap_text(display_text, font, max_width)
        y = xy[1]
        line_height = font.size + 4
        for line in lines:
            draw.text((xy[0], y), line, fill=fill, font=font, anchor=anchor)
            y += line_height
    else:
        draw.text(xy, display_text, fill=fill, font=font, anchor=anchor)


def _wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> List[str]:
    """تقسيم النص إلى عدة أسطر حسب العرض المحدد"""
    words = text.split()
    lines = []
    current_line = []

    for word in words:
        test_line = ' '.join(current_line + [word])
        try:
            bbox = font.getbbox(test_line)
            width = bbox[2] - bbox[0]
        except:
            width = len(test_line) * font.size * 0.6  # تقدير

        if width <= max_width:
            current_line.append(word)
        else:
            if current_line:
                lines.append(' '.join(current_line))
            current_line = [word]

    if current_line:
        lines.append(' '.join(current_line))

    return lines or [text]


def _draw_rounded_rectangle(draw: ImageDraw.Draw, xy: Tuple[int, int, int, int],
                            radius: int, fill: str = None, outline: str = None, width: int = 1):
    """رسم مستطيل بزوايا دائرية"""
    x1, y1, x2, y2 = xy
    draw.rectangle([x1+radius, y1, x2-radius, y2], fill=fill)
    draw.rectangle([x1, y1+radius, x2, y2-radius], fill=fill)
    draw.pieslice([x1, y1, x1+2*radius, y1+2*radius], 180, 270, fill=fill)
    draw.pieslice([x2-2*radius, y1, x2, y1+2*radius], 270, 360, fill=fill)
    draw.pieslice([x1, y2-2*radius, x1+2*radius, y2], 90, 180, fill=fill)
    draw.pieslice([x2-2*radius, y2-2*radius, x2, y2], 0, 90, fill=fill)
    if outline:
        draw.arc([x1, y1, x1+2*radius, y1+2*radius], 180, 270, fill=outline, width=width)
        draw.arc([x2-2*radius, y1, x2, y1+2*radius], 270, 360, fill=outline, width=width)
        draw.arc([x1, y2-2*radius, x1+2*radius, y2], 90, 180, fill=outline, width=width)
        draw.arc([x2-2*radius, y2-2*radius, x2, y2], 0, 90, fill=outline, width=width)
        draw.line([x1+radius, y1, x2-radius, y1], fill=outline, width=width)
        draw.line([x1+radius, y2, x2-radius, y2], fill=outline, width=width)
        draw.line([x1, y1+radius, x1, y2-radius], fill=outline, width=width)
        draw.line([x2, y1+radius, x2, y2-radius], fill=outline, width=width)


# ==================== رسم الشخصية الكرتونية ====================

def _draw_teacher_character(draw: ImageDraw.Draw, x: int, y: int,
                            specialty: str = "general",
                            name: str = None) -> None:
    """
    رسم شخصية كرتونية (معلم طبي) في الزاوية المحددة.
    """
    outfit = TEACHER_OUTFITS.get(specialty, TEACHER_OUTFITS["general"])
    coat_color = outfit["coat"]
    accessory = outfit.get("accessory", "stethoscope")
    hat = outfit.get("hat", "cap")

    # أبعاد الشخصية
    body_width = 80
    body_height = 100
    head_size = 50

    head_x = x + body_width // 2 - head_size // 2
    head_y = y

    # رسم الجسم (المعطف)
    body_rect = [x, y + head_size - 5, x + body_width, y + head_size + body_height]
    draw.rounded_rectangle(body_rect, radius=10, fill=coat_color, outline=COLORS["dark"], width=2)

    # رسم الوجه (دائرة)
    face_rect = [head_x, head_y, head_x + head_size, head_y + head_size]
    draw.ellipse(face_rect, fill="#FDEBD0", outline=COLORS["dark"], width=2)

    # رسم العيون
    eye_y = head_y + head_size // 3
    left_eye = (head_x + head_size // 3 - 5, eye_y, head_x + head_size // 3 + 5, eye_y + 8)
    right_eye = (head_x + 2*head_size//3 - 5, eye_y, head_x + 2*head_size//3 + 5, eye_y + 8)
    draw.ellipse(left_eye, fill=COLORS["white"], outline=COLORS["dark"], width=1)
    draw.ellipse(right_eye, fill=COLORS["white"], outline=COLORS["dark"], width=1)
    # بؤبؤ العين
    draw.ellipse([left_eye[0]+2, left_eye[1]+2, left_eye[2]-2, left_eye[3]-2], fill=COLORS["dark"])
    draw.ellipse([right_eye[0]+2, right_eye[1]+2, right_eye[2]-2, right_eye[3]-2], fill=COLORS["dark"])

    # رسم الابتسامة
    smile_y = head_y + head_size // 2 + 5
    draw.arc([head_x+15, smile_y-5, head_x+head_size-15, smile_y+10],
             start=0, end=180, fill=COLORS["dark"], width=2)

    # أحمر الخدود
    blush_y = head_y + head_size // 2
    draw.ellipse([head_x+5, blush_y-3, head_x+15, blush_y+7], fill="#FFB6C1", outline=None)
    draw.ellipse([head_x+head_size-15, blush_y-3, head_x+head_size-5, blush_y+7], fill="#FFB6C1", outline=None)

    # رسم القبعة
    if hat == "cap":
        hat_rect = [head_x-5, head_y-5, head_x+head_size+5, head_y+15]
        draw.rounded_rectangle(hat_rect, radius=8, fill=COLORS["secondary"], outline=COLORS["dark"], width=2)
        # شريط القبعة
        draw.rectangle([head_x-5, head_y+5, head_x+head_size+5, head_y+15], fill=COLORS["primary"])

    # رسم الأكسسوار (السماعة الطبية)
    if accessory == "stethoscope":
        steth_y = y + head_size + 20
        draw.arc([x+20, steth_y, x+60, steth_y+30], start=0, end=180, fill=COLORS["gray"], width=3)
        draw.ellipse([x+30, steth_y+25, x+50, steth_y+45], fill=COLORS["gray"], outline=COLORS["dark"], width=2)
        draw.line([x+40, steth_y+45, x+40, y+head_size+body_height-20], fill=COLORS["gray"], width=3)

    # رسم اسم المعلم
    if name is None:
        name = TEACHER_NAMES.get(specialty, "د. طبيب")
    name_font = _get_font(14, bold=True)
    display_name = _arabic(name)
    name_bbox = draw.textbbox((0,0), display_name, font=name_font)
    name_width = name_bbox[2] - name_bbox[0]
    name_x = x + body_width // 2 - name_width // 2
    name_y = y + head_size + body_height + 5
    _draw_text(draw, (name_x, name_y), name, fill=COLORS["dark"], font=name_font, shadow=False)


# ==================== رسم الشرائح الأساسية ====================

def _create_blank_slide(bg_color: str = COLORS["light"]) -> Image.Image:
    """إنشاء شريحة فارغة بالخلفية المحددة"""
    return Image.new("RGB", (VIDEO_WIDTH, VIDEO_HEIGHT), bg_color)


def _draw_welcome_slide(specialty: str = "general", language: str = "ar") -> Image.Image:
    """
    شريحة المقدمة: شعار البوت، رسالة ترحيب، شخصية كرتونية، حقوق.
    المدة: 3.5 ثانية
    """
    img = _create_blank_slide(COLORS["light"])
    draw = ImageDraw.Draw(img)

    # إطار كبير للشعار
    logo_rect = [VIDEO_WIDTH//2 - 150, 50, VIDEO_WIDTH//2 + 150, 200]
    _draw_rounded_rectangle(draw, logo_rect, radius=20, fill=COLORS["white"], outline=COLORS["primary"], width=4)

    # نص الترحيب
    welcome_text = "أهلاً ومرحباً بكم" if language == "ar" else "Welcome"
    welcome_font = _get_font(48, bold=True)
    display_welcome = _arabic(welcome_text) if language == "ar" else welcome_text
    bbox = draw.textbbox((0,0), display_welcome, font=welcome_font)
    w = bbox[2] - bbox[0]
    _draw_text(draw, (VIDEO_WIDTH//2, 130), welcome_text, fill=COLORS["primary"], font=welcome_font, anchor="mm", language=language)

    # اسم البوت
    bot_name_font = _get_font(32, bold=True)
    _draw_text(draw, (VIDEO_WIDTH//2, 180), config.BOT_NAME, fill=COLORS["dark"], font=bot_name_font, anchor="mm", language="ar")

    # شخصية كرتونية
    _draw_teacher_character(draw, 50, VIDEO_HEIGHT-200, specialty=specialty)

    # حقوق البوت
    rights_font = _get_font(16)
    _draw_text(draw, (VIDEO_WIDTH//2, VIDEO_HEIGHT-30), WATERMARK, fill=COLORS["gray"], font=rights_font, anchor="mm", language="ar")

    return img


def _draw_title_slide(title: str, specialty: str = "general", language: str = "ar") -> Image.Image:
    """
    شريحة العنوان: عنوان المحاضرة بخط كبير، شخصية كرتونية.
    المدة: 4 ثواني
    """
    img = _create_blank_slide(COLORS["light"])
    draw = ImageDraw.Draw(img)

    # خلفية مزخرفة خفيفة
    for i in range(3):
        y = 100 + i*100
        draw.ellipse([VIDEO_WIDTH//2-300, y-50, VIDEO_WIDTH//2+300, y+50], fill=COLORS["primary"]+"20", outline=None)

    # عنوان المحاضرة
    title_font = _get_font(40, bold=True)
    lines = _wrap_text(title, title_font, VIDEO_WIDTH-200)
    y_start = 150
    for i, line in enumerate(lines):
        _draw_text(draw, (VIDEO_WIDTH//2, y_start + i*60), line, fill=COLORS["primary"], font=title_font, anchor="mm", language=language)

    # شعار صغير
    _draw_text(draw, (VIDEO_WIDTH//2, y_start + len(lines)*60 + 20), "Medical Lecture", fill=COLORS["gray"], font=_get_font(20), anchor="mm", language="en")

    # شخصية كرتونية
    _draw_teacher_character(draw, 50, VIDEO_HEIGHT-200, specialty=specialty)

    # العلامة المائية
    _draw_text(draw, (VIDEO_WIDTH-20, VIDEO_HEIGHT-20), WATERMARK, fill=COLORS["gray"], font=_get_font(14), anchor="rb", language="ar")

    return img


def _draw_map_slide(sections: List[Dict], language: str = "ar") -> Image.Image:
    """
    شريحة خريطة الأقسام: تعرض جميع الأقسام مع أرقامها وعناوينها وكلماتها المفتاحية.
    المدة: 5 ثواني
    """
    img = _create_blank_slide(COLORS["light"])
    draw = ImageDraw.Draw(img)

    # عنوان "خريطة المحاضرة"
    title_font = _get_font(36, bold=True)
    _draw_text(draw, (VIDEO_WIDTH//2, 40), "خريطة المحاضرة" if language == "ar" else "Lecture Map",
               fill=COLORS["primary"], font=title_font, anchor="mm", language=language)

    # رسم الأقسام كبطاقات
    card_width = 350
    card_height = 60
    start_x = 50
    start_y = 100

    colors_list = [COLORS["primary"], COLORS["secondary"], COLORS["accent1"], COLORS["accent2"], COLORS["accent3"]]

    for i, section in enumerate(sections):
        if i >= 5:  # عرض 5 أقسام كحد أقصى في هذه الشريحة
            break

        col_idx = i % len(colors_list)
        card_color = colors_list[col_idx]

        x = start_x if i < 3 else VIDEO_WIDTH//2 + 30
        y = start_y + (i % 3) * (card_height + 15)

        # خلفية البطاقة
        _draw_rounded_rectangle(draw, [x, y, x+card_width, y+card_height], radius=10, fill=card_color+"30", outline=card_color, width=2)

        # رقم القسم
        num_font = _get_font(28, bold=True)
        _draw_text(draw, (x+30, y+card_height//2), str(i+1), fill=card_color, font=num_font, anchor="lm", language="ar")

        # عنوان القسم
        heading_font = _get_font(18, bold=True)
        heading = section.get('heading', f'القسم {i+1}')
        if len(heading) > 25:
            heading = heading[:25] + "..."
        _draw_text(draw, (x+60, y+20), heading, fill=COLORS["dark"], font=heading_font, anchor="la", language=language)

        # الكلمات المفتاحية (مصغرة)
        keywords = section.get('keywords', [])[:3]
        kw_text = " • ".join(keywords) if keywords else "طبي"
        kw_font = _get_font(12)
        _draw_text(draw, (x+60, y+42), kw_text, fill=COLORS["gray"], font=kw_font, anchor="la", language=language)

    # إذا كان هناك أقسام أكثر
    if len(sections) > 5:
        more_font = _get_font(20)
        _draw_text(draw, (VIDEO_WIDTH//2, VIDEO_HEIGHT-50), f"+ {len(sections)-5} أقسام أخرى",
                   fill=COLORS["gray"], font=more_font, anchor="mm", language="ar")

    # العلامة المائية
    _draw_text(draw, (VIDEO_WIDTH-20, VIDEO_HEIGHT-20), WATERMARK, fill=COLORS["gray"], font=_get_font(14), anchor="rb", language="ar")

    return img


def _draw_section_title_slide(section_num: int, total_sections: int, heading: str,
                              specialty: str = "general", language: str = "ar") -> Image.Image:
    """
    شريحة عنوان القسم: رقم القسم في دائرة، العنوان، الشخصية الكرتونية.
    المدة: 3 ثواني
    """
    img = _create_blank_slide(COLORS["light"])
    draw = ImageDraw.Draw(img)

    color = COLORS["primary"]

    # دائرة رقم القسم
    circle_center = (VIDEO_WIDTH//2, 150)
    circle_r = 70
    draw.ellipse([circle_center[0]-circle_r, circle_center[1]-circle_r,
                  circle_center[0]+circle_r, circle_center[1]+circle_r],
                 fill=color, outline=COLORS["dark"], width=3)

    # نص "قسم" والرقم
    num_font = _get_font(64, bold=True)
    _draw_text(draw, circle_center, str(section_num), fill=COLORS["white"], font=num_font, anchor="mm", shadow=False)

    label_font = _get_font(20)
    label_text = f"قسم {section_num} من {total_sections}" if language == "ar" else f"Section {section_num} of {total_sections}"
    _draw_text(draw, (VIDEO_WIDTH//2, circle_center[1]+circle_r+20), label_text,
               fill=COLORS["gray"], font=label_font, anchor="mm", language=language)

    # عنوان القسم
    heading_font = _get_font(36, bold=True)
    lines = _wrap_text(heading, heading_font, VIDEO_WIDTH-200)
    y_start = 280
    for i, line in enumerate(lines):
        _draw_text(draw, (VIDEO_WIDTH//2, y_start + i*50), line, fill=COLORS["dark"], font=heading_font, anchor="mm", language=language)

    # شخصية كرتونية
    _draw_teacher_character(draw, 50, VIDEO_HEIGHT-200, specialty=specialty)

    # العلامة المائية
    _draw_text(draw, (VIDEO_WIDTH-20, VIDEO_HEIGHT-20), WATERMARK, fill=COLORS["gray"], font=_get_font(14), anchor="rb", language="ar")

    return img

      # ==================== رسم شريحة المحتوى الرئيسية ====================

def _draw_content_slide(section: Dict, section_index: int, total_sections: int,
                        progress: float,  # نسبة التقدم من 0.0 إلى 1.0
                        specialty: str = "general",
                        language: str = "ar",
                        image_path: Path = None) -> Image.Image:
    """
    الشريحة الرئيسية التي تظهر أثناء شرح القسم.
    تحتوي على: عنوان القسم، صورة طبية، شخصية كرتونية،
    كلمات مفتاحية تتراكم مع الوقت، مؤشر تقدم، وحقوق البوت.
    """
    img = _create_blank_slide(COLORS["light"])
    draw = ImageDraw.Draw(img)

    # ----- عنوان القسم (في الأعلى) -----
    heading = section.get('heading', f'القسم {section_index+1}')
    heading_font = _get_font(28, bold=True)
    # خلفية للعنوان
    header_height = 60
    draw.rectangle([0, 0, VIDEO_WIDTH, header_height], fill=COLORS["primary"]+"15")
    _draw_text(draw, (20, header_height//2), heading, fill=COLORS["primary"],
               font=heading_font, anchor="lm", language=language)

    # رقم القسم صغير
    section_label = f"{section_index+1}/{total_sections}"
    _draw_text(draw, (VIDEO_WIDTH-20, header_height//2), section_label,
               fill=COLORS["gray"], font=_get_font(18), anchor="rm", language="ar")

    # ----- الصورة الطبية (في المنتصف مع إطار) -----
    img_area_x = 80
    img_area_y = 80
    img_area_w = 500
    img_area_h = 280

    # إطار خارجي مزدوج
    _draw_rounded_rectangle(draw, [img_area_x-5, img_area_y-5, img_area_x+img_area_w+5, img_area_y+img_area_h+5],
                            radius=15, outline=COLORS["primary"], width=3)
    _draw_rounded_rectangle(draw, [img_area_x-10, img_area_y-10, img_area_x+img_area_w+10, img_area_y+img_area_h+10],
                            radius=18, outline=COLORS["secondary"], width=2)

    # محاولة تحميل الصورة الطبية
    if image_path and Path(image_path).exists():
        try:
            medical_img = Image.open(image_path)
            medical_img = medical_img.resize((img_area_w, img_area_h), Image.Resampling.LANCZOS)
            # اقتصاص إذا لزم الأمر للحفاظ على النسبة
            img.paste(medical_img, (img_area_x, img_area_y))
        except Exception as e:
            logger.warning(f"فشل تحميل الصورة {image_path}: {e}")
            # رسم بديل
            draw.rectangle([img_area_x, img_area_y, img_area_x+img_area_w, img_area_y+img_area_h],
                           fill="#E8F4FD")
            _draw_text(draw, (img_area_x+img_area_w//2, img_area_y+img_area_h//2),
                       "Medical Illustration", fill=COLORS["gray"], font=_get_font(24), anchor="mm")
    else:
        # رسم بديل في حال عدم وجود صورة
        draw.rectangle([img_area_x, img_area_y, img_area_x+img_area_w, img_area_y+img_area_h],
                       fill="#E8F4FD")
        _draw_text(draw, (img_area_x+img_area_w//2, img_area_y+img_area_h//2),
                   "🫀 Medical Image", fill=COLORS["gray"], font=_get_font(28), anchor="mm")

    # ----- الشخصية الكرتونية (في الزاوية اليسرى السفلى) -----
    _draw_teacher_character(draw, 30, VIDEO_HEIGHT-180, specialty=specialty)

    # ----- الكلمات المفتاحية المتراكمة (حسب نسبة التقدم) -----
    keywords = section.get('keywords', [])[:6]  # حتى 6 كلمات
    keywords_to_show = int(len(keywords) * progress)

    if keywords_to_show > 0 and keywords:
        kw_start_x = 620
        kw_start_y = 120
        kw_font = _get_font(22, bold=True)

        for i in range(keywords_to_show):
            kw = keywords[i]
            # لون متدرج
            color_idx = i % len([COLORS["primary"], COLORS["secondary"], COLORS["accent1"],
                                 COLORS["accent2"], COLORS["accent3"]])
            kw_color = [COLORS["primary"], COLORS["secondary"], COLORS["accent1"],
                        COLORS["accent2"], COLORS["accent3"]][color_idx]

            # خلفية دائرية للكلمة
            y_pos = kw_start_y + i * 50
            # رسم مربع صغير مع نقطة
            draw.rectangle([kw_start_x-10, y_pos-5, kw_start_x+180, y_pos+35],
                           fill=kw_color+"20", outline=kw_color, width=2)

            # كتابة الكلمة
            _draw_text(draw, (kw_start_x+10, y_pos+15), kw, fill=kw_color,
                       font=kw_font, anchor="la", language=language)

    # ----- مؤشر التقدم (نقاط في الأسفل) -----
    dot_count = 10
    dot_spacing = 30
    total_width = dot_count * dot_spacing
    start_x = (VIDEO_WIDTH - total_width) // 2 + 15
    dot_y = VIDEO_HEIGHT - 30

    filled_dots = int(dot_count * progress)
    for i in range(dot_count):
        x = start_x + i * dot_spacing
        if i < filled_dots:
            draw.ellipse([x-6, dot_y-6, x+6, dot_y+6], fill=COLORS["primary"])
        else:
            draw.ellipse([x-6, dot_y-6, x+6, dot_y+6], fill=COLORS["gray"], outline=COLORS["gray"])

    # ----- حقوق البوت (علامة مائية) -----
    _draw_text(draw, (VIDEO_WIDTH-20, VIDEO_HEIGHT-20), WATERMARK,
               fill=COLORS["gray"], font=_get_font(14), anchor="rb", language="ar")

    return img


def _draw_summary_slide(sections: List[Dict], title: str,
                        specialty: str = "general", language: str = "ar") -> Image.Image:
    """
    شريحة الملخص النهائي: عنوان "ملخص المحاضرة"، جميع الكلمات المفتاحية
    في شبكة ملونة، رسالة شكر، والشخصية الكرتونية.
    المدة: 6 ثواني
    """
    img = _create_blank_slide(COLORS["light"])
    draw = ImageDraw.Draw(img)

    # عنوان "ملخص المحاضرة"
    summary_font = _get_font(40, bold=True)
    _draw_text(draw, (VIDEO_WIDTH//2, 50), "ملخص المحاضرة" if language == "ar" else "Lecture Summary",
               fill=COLORS["primary"], font=summary_font, anchor="mm", language=language)

    # جمع كل الكلمات المفتاحية من جميع الأقسام
    all_keywords = []
    for section in sections:
        all_keywords.extend(section.get('keywords', [])[:4])
    # إزالة التكرار مع الحفاظ على الترتيب
    seen = set()
    unique_keywords = []
    for kw in all_keywords:
        if kw not in seen:
            seen.add(kw)
            unique_keywords.append(kw)

    # رسم شبكة الكلمات المفتاحية
    cols = 4
    rows = min(5, (len(unique_keywords) + cols - 1) // cols)
    cell_width = 150
    cell_height = 50
    start_x = (VIDEO_WIDTH - (cols * cell_width)) // 2 + cell_width//2
    start_y = 120

    colors_list = [COLORS["primary"], COLORS["secondary"], COLORS["accent1"],
                   COLORS["accent2"], COLORS["accent3"]]

    for idx, kw in enumerate(unique_keywords[:cols*rows]):
        row = idx // cols
        col = idx % cols
        x = start_x + col * cell_width
        y = start_y + row * cell_height

        color = colors_list[idx % len(colors_list)]
        _draw_rounded_rectangle(draw, [x-60, y-5, x+60, y+35], radius=10,
                                fill=color+"20", outline=color, width=2)

        kw_font = _get_font(16, bold=True)
        _draw_text(draw, (x, y+15), kw, fill=color, font=kw_font, anchor="mm", language=language)

    # رسالة شكر
    thanks_font = _get_font(28, bold=True)
    _draw_text(draw, (VIDEO_WIDTH//2, VIDEO_HEIGHT-100),
               "شكراً لحسن استماعكم" if language == "ar" else "Thank you for listening",
               fill=COLORS["dark"], font=thanks_font, anchor="mm", language=language)

    # شخصية كرتونية
    _draw_teacher_character(draw, 50, VIDEO_HEIGHT-200, specialty=specialty)

    # العلامة المائية
    _draw_text(draw, (VIDEO_WIDTH-20, VIDEO_HEIGHT-20), WATERMARK,
               fill=COLORS["gray"], font=_get_font(14), anchor="rb", language="ar")

    return img


# ==================== دوال FFmpeg ====================

def _ffmpeg_seg(input_pattern: str, audio_path: Path, output_path: Path,
                duration: float, fps: int = FPS) -> bool:
    """
    تشفير مقطع فيديو واحد من سلسلة صور (input_pattern) مع مسار صوتي.
    تستخدم ترميز H.264 و AAC مع movflags +faststart.
    """
    cmd = [
        "ffmpeg", "-y", "-framerate", str(fps),
        "-i", input_pattern,
        "-i", str(audio_path) if audio_path and audio_path.exists() else "anullsrc=r=44100:cl=mono",
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", config.AUDIO_BITRATE,
        "-t", str(duration),
        "-movflags", "+faststart",
        "-shortest",
        str(output_path)
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=120)
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"FFmpeg seg error: {e.stderr.decode() if e.stderr else str(e)}")
        return False


def _ffmpeg_cat(segment_paths: List[Path], output_path: Path) -> bool:
    """
    دمج عدة مقاطع فيديو في ملف واحد باستخدام concat demuxer.
    """
    # إنشاء ملف قائمة
    list_path = output_path.with_suffix('.txt')
    with open(list_path, 'w') as f:
        for seg in segment_paths:
            f.write(f"file '{seg.absolute()}'\n")

    cmd = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", str(list_path),
        "-c", "copy",
        "-movflags", "+faststart",
        str(output_path)
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=180)
        list_path.unlink(missing_ok=True)
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"FFmpeg concat error: {e.stderr.decode() if e.stderr else str(e)}")
        return False


# ==================== بناء الفيديو ====================

def _build_frames_for_slide(slide_func, output_dir: Path, slide_name: str,
                            total_frames: int, **kwargs) -> List[Path]:
    """
    توليد إطارات (frames) لشريحة واحدة وحفظها كملفات PNG.
    ترجع قائمة بمسارات الصور المولدة.
    """
    frames = []
    for frame_idx in range(total_frames):
        # يمكن تخصيص معاملات متغيرة مع الوقت (مثل progress)
        if 'progress' in kwargs:
            kwargs['progress'] = (frame_idx + 1) / total_frames

        img = slide_func(**kwargs)
        frame_path = output_dir / f"{slide_name}_{frame_idx:04d}.png"
        img.save(frame_path, "PNG")
        frames.append(frame_path)
    return frames


def _build(video_data: Dict, output_dir: Path) -> Tuple[List[Path], float]:
    """
    بناء جميع مقاطع الفيديو (شرائح) بالترتيب.
    ترجع قائمة بمسارات مقاطع الفيديو المؤقتة والمدة الإجمالية.
    """
    sections = video_data['sections']
    specialty = video_data.get('specialty_code', 'general')
    language = video_data.get('language', 'ar')
    title = video_data.get('title', 'محاضرة طبية')
    dialect = video_data.get('dialect', 'fusha')

    segment_paths = []
    total_duration = 0.0

    # إنشاء مجلد للإطارات المؤقتة
    frames_dir = output_dir / "frames"
    frames_dir.mkdir(exist_ok=True)

    # 1. شريحة المقدمة
    welcome_frames = int(config.WELCOME_DURATION * FPS)
    _build_frames_for_slide(_draw_welcome_slide, frames_dir, "welcome",
                            welcome_frames, specialty=specialty, language=language)
    seg_path = output_dir / "seg_000_welcome.mp4"
    audio_path = config.AUDIO_TMP / "silence_welcome.mp3"
    generate_silence(config.WELCOME_DURATION, audio_path)
    _ffmpeg_seg(str(frames_dir/"welcome_%04d.png"), audio_path, seg_path, config.WELCOME_DURATION)
    segment_paths.append(seg_path)
    total_duration += config.WELCOME_DURATION

    # 2. شريحة العنوان
    title_frames = int(config.TITLE_DURATION * FPS)
    _build_frames_for_slide(_draw_title_slide, frames_dir, "title",
                            title_frames, title=title, specialty=specialty, language=language)
    seg_path = output_dir / "seg_001_title.mp4"
    audio_path = config.AUDIO_TMP / "silence_title.mp3"
    generate_silence(config.TITLE_DURATION, audio_path)
    _ffmpeg_seg(str(frames_dir/"title_%04d.png"), audio_path, seg_path, config.TITLE_DURATION)
    segment_paths.append(seg_path)
    total_duration += config.TITLE_DURATION

    # 3. شريحة الخريطة
    map_frames = int(config.MAP_DURATION * FPS)
    _build_frames_for_slide(_draw_map_slide, frames_dir, "map",
                            map_frames, sections=sections, language=language)
    seg_path = output_dir / "seg_002_map.mp4"
    audio_path = config.AUDIO_TMP / "silence_map.mp3"
    generate_silence(config.MAP_DURATION, audio_path)
    _ffmpeg_seg(str(frames_dir/"map_%04d.png"), audio_path, seg_path, config.MAP_DURATION)
    segment_paths.append(seg_path)
    total_duration += config.MAP_DURATION

    # 4. لكل قسم: شريحة عنوان + شريحة محتوى (بالصوت الفعلي)
    for idx, section in enumerate(sections):
        section_duration = section.get('duration', 10.0)
        section_audio = Path(section.get('audio_path')) if section.get('audio_path') else None

        # شريحة عنوان القسم
        section_title_frames = int(config.SECTION_TITLE_DURATION * FPS)
        _build_frames_for_slide(_draw_section_title_slide, frames_dir, f"sectitle_{idx}",
                                section_title_frames,
                                section_num=idx+1, total_sections=len(sections),
                                heading=section.get('heading', f'قسم {idx+1}'),
                                specialty=specialty, language=language)
        seg_path = output_dir / f"seg_{idx+3:03d}a_title.mp4"
        audio_path = config.AUDIO_TMP / f"silence_sectitle_{idx}.mp3"
        generate_silence(config.SECTION_TITLE_DURATION, audio_path)
        _ffmpeg_seg(str(frames_dir/f"sectitle_{idx}_%04d.png"), audio_path, seg_path, config.SECTION_TITLE_DURATION)
        segment_paths.append(seg_path)
        total_duration += config.SECTION_TITLE_DURATION

        # شريحة المحتوى (مع الصوت الفعلي)
        content_frames = int(section_duration * FPS)
        image_path = Path(section.get('image_path')) if section.get('image_path') else None
        _build_frames_for_slide(_draw_content_slide, frames_dir, f"content_{idx}",
                                content_frames,
                                section=section, section_index=idx, total_sections=len(sections),
                                progress=0.0,  # سيتم تحديثه داخل _build_frames_for_slide
                                specialty=specialty, language=language,
                                image_path=image_path)
        seg_path = output_dir / f"seg_{idx+3:03d}b_content.mp4"
        # استخدام الصوت الفعلي أو صمت
        if section_audio and section_audio.exists():
            _ffmpeg_seg(str(frames_dir/f"content_{idx}_%04d.png"), section_audio, seg_path, section_duration)
        else:
            audio_path = config.AUDIO_TMP / f"silence_content_{idx}.mp3"
            generate_silence(section_duration, audio_path)
            _ffmpeg_seg(str(frames_dir/f"content_{idx}_%04d.png"), audio_path, seg_path, section_duration)
        segment_paths.append(seg_path)
        total_duration += section_duration

    # 5. شريحة الملخص
    summary_frames = int(config.SUMMARY_DURATION * FPS)
    _build_frames_for_slide(_draw_summary_slide, frames_dir, "summary",
                            summary_frames, sections=sections, title=title,
                            specialty=specialty, language=language)
    seg_path = output_dir / "seg_999_summary.mp4"
    audio_path = config.AUDIO_TMP / "silence_summary.mp3"
    generate_silence(config.SUMMARY_DURATION, audio_path)
    _ffmpeg_seg(str(frames_dir/"summary_%04d.png"), audio_path, seg_path, config.SUMMARY_DURATION)
    segment_paths.append(seg_path)
    total_duration += config.SUMMARY_DURATION

    return segment_paths, total_duration


def _encode(segment_paths: List[Path], output_path: Path) -> bool:
    """تجميع المقاطع في فيديو نهائي"""
    return _ffmpeg_cat(segment_paths, output_path)


# ==================== الدالة الرئيسية ====================

def create_video_from_sections(video_data: Dict, output_path: Path = None) -> Tuple[Path, float]:
    """
    الدالة الرئيسية لإنشاء الفيديو التعليمي من بيانات المحاضرة.

    المعاملات:
        video_data: قاموس يحتوي على:
            - sections: قائمة الأقسام (كل قسم به audio_path, duration, image_path, ...)
            - title: عنوان المحاضرة
            - specialty_code: كود التخصص
            - language: اللغة
            - dialect: اللهجة
        output_path: مسار حفظ الفيديو (اختياري)

    ترجع:
        (مسار الفيديو النهائي, المدة الإجمالية بالثواني)
    """
    if not Image:
        raise RuntimeError("مكتبة Pillow غير متوفرة")

    # التحقق من وجود FFmpeg
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
    except:
        raise RuntimeError("FFmpeg غير مثبت أو غير متاح في PATH")

    # إنشاء مجلد مؤقت للفيديو
    job_id = uuid.uuid4().hex[:8]
    work_dir = config.VIDEO_TMP / job_id
    work_dir.mkdir(parents=True, exist_ok=True)

    if output_path is None:
        output_path = work_dir / "final_video.mp4"
    else:
        output_path = Path(output_path)

    logger.info(f"بدء إنشاء الفيديو في {work_dir}")

    try:
        # بناء المقاطع
        segment_paths, total_duration = _build(video_data, work_dir)

        # دمج المقاطع
        success = _encode(segment_paths, output_path)

        if not success or not output_path.exists():
            raise RuntimeError("فشل تشفير الفيديو النهائي")

        # تنظيف الملفات المؤقتة (اختياري)
        # for seg in segment_paths:
        #     seg.unlink(missing_ok=True)
        # shutil.rmtree(work_dir / "frames", ignore_errors=True)

        logger.info(f"✅ تم إنشاء الفيديو بنجاح: {output_path} ({total_duration:.1f} ثانية)")
        return output_path, total_duration

    except Exception as e:
        logger.error(f"❌ فشل إنشاء الفيديو: {e}")
        raise


# للاختبار
if __name__ == "__main__":
    # اختبار بسيط مع بيانات وهمية
    test_data = {
        "title": "أساسيات أمراض القلب",
        "specialty_code": "cardiology",
        "language": "ar",
        "dialect": "fusha",
        "sections": [
            {"heading": "مقدمة", "keywords": ["قلب", "شرايين", "دورة دموية"], "duration": 8.0},
            {"heading": "الأعراض", "keywords": ["ألم صدر", "ضيق تنفس"], "duration": 10.0},
        ]
    }
    # يجب توفير audio_path و image_path فعلياً للتشغيل الحقيقي
    # create_video_from_sections(test_data)
    print("اكتمل تحميل وحدة video_creator")                            
