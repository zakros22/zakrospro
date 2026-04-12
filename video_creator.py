# -*- coding: utf-8 -*-
"""
Video Creator Module - النسخة الخرافية الكاملة
=============================================
الميزات:
- مقدمة احترافية مع شعار البوت
- شريحة عنوان المحاضرة
- شريحة خريطة الأقسام مع الكلمات المفتاحية
- شخصية كرتونية تظهر في كل فيديو (وجه + ملابس حسب التخصص)
- صورة واحدة لكل قسم تملأ الشاشة وتحتوي على الكلمات المفتاحية
- كلمات مفتاحية تتراكم مع تقدم الشرح
- مؤقت 5 ثواني للأسئلة التفاعلية (اختياري)
- ملخص نهائي بجميع الكلمات المفتاحية
- دعم كامل للغة العربية
- تنسيق فيديو متوافق مع تيليجرام 100%
"""

import asyncio
import io
import os
import subprocess
import tempfile
from PIL import Image, ImageDraw, ImageFont

# ═══════════════════════════════════════════════════════════════════════════════
# الإعدادات العامة
# ═══════════════════════════════════════════════════════════════════════════════

TARGET_W, TARGET_H = 854, 480
WATERMARK = "@zakros_probot"

# ألوان Osmosis المميزة
COLORS = [
    (231, 76, 126),   # وردي
    (52, 152, 219),   # أزرق
    (46, 204, 113),   # أخضر
    (155, 89, 182),   # بنفسجي
    (230, 126, 34),   # برتقالي
]

# ═══════════════════════════════════════════════════════════════════════════════
# ملابس الشخصية الكرتونية حسب نوع المحاضرة
# ═══════════════════════════════════════════════════════════════════════════════

TEACHER_OUTFITS = {
    # الطب
    "doctor": {
        "color": (255, 255, 255),      # أبيض (معطف الطبيب)
        "accessory": "🩺",              # سماعة
        "hat": "🧢",                    # قبعة طبية
        "bg_color": (200, 230, 255)    # خلفية زرقاء فاتحة
    },
    # الهندسة
    "engineer": {
        "color": (255, 200, 50),       # أصفر (خوذة)
        "accessory": "🔧",              # مفتاح
        "hat": "⛑️",                    # خوذة
        "bg_color": (255, 240, 200)
    },
    # معلم عام
    "teacher": {
        "color": (100, 100, 200),      # أزرق
        "accessory": "📚",              # كتب
        "hat": "🎓",                    # قبعة تخرج
        "bg_color": (220, 220, 255)
    },
    # عالم
    "scientist": {
        "color": (200, 200, 200),      # رمادي (معطف مختبر)
        "accessory": "🔬",              # مجهر
        "hat": "🥽",                    # نظارات واقية
        "bg_color": (240, 240, 250)
    },
    # مؤرخ
    "historian": {
        "color": (139, 90, 43),        # بني
        "accessory": "📜",              # وثيقة
        "hat": "🎩",                    # قبعة
        "bg_color": (250, 240, 220)
    },
    # شيخ (علوم إسلامية)
    "sheikh": {
        "color": (255, 255, 255),      # أبيض
        "accessory": "📿",              # مسبحة
        "hat": "🧕",                    # عمامة
        "bg_color": (230, 245, 230)
    },
    # مبرمج
    "developer": {
        "color": (50, 50, 50),         # أسود
        "accessory": "💻",              # لابتوب
        "hat": "🧢",                    # قبعة
        "bg_color": (220, 220, 230)
    },
    # عالم نفس
    "psychologist": {
        "color": (150, 200, 200),      # أزرق مخضر
        "accessory": "🧠",              # دماغ
        "hat": "👓",                    # نظارات
        "bg_color": (230, 245, 245)
    },
    # قانوني
    "lawyer": {
        "color": (0, 0, 0),            # أسود (روب المحامي)
        "accessory": "⚖️",              # ميزان
        "hat": "👔",                    # ربطة عنق
        "bg_color": (230, 230, 240)
    },
    # اقتصادي
    "business": {
        "color": (0, 0, 100),          # أزرق داكن
        "accessory": "📊",              # رسم بياني
        "hat": "👔",                    # ربطة عنق
        "bg_color": (220, 230, 250)
    },
    # أديب
    "writer": {
        "color": (150, 100, 50),       # بني
        "accessory": "✒️",              # قلم
        "hat": "🧐",                    # نظارة أحادية
        "bg_color": (250, 240, 230)
    },
    # فيلسوف
    "thinker": {
        "color": (100, 100, 100),      # رمادي
        "accessory": "🤔",              # تفكير
        "hat": "👓",                    # نظارات
        "bg_color": (240, 240, 245)
    },
}


def estimate_encoding_seconds(t: float) -> float:
    """تقدير وقت التشفير"""
    return max(20, t * 0.6)


# ═══════════════════════════════════════════════════════════════════════════════
# دوال الخطوط والنصوص العربية
# ═══════════════════════════════════════════════════════════════════════════════

def _get_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """تحميل خط يدعم العربية"""
    paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/app/fonts/Amiri-Bold.ttf",
        "fonts/Amiri-Bold.ttf",
        "/app/fonts/Amiri-Regular.ttf",
        "fonts/Amiri-Regular.ttf"
    ]
    for p in paths:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except:
                pass
    return ImageFont.load_default()


def _arabic(text: str) -> str:
    """تحويل النص العربي لعرض صحيح 100%"""
    if not text:
        return ""
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
        if any('\u0600' <= c <= '\u06FF' for c in text):
            reshaped = arabic_reshaper.reshape(text)
            return get_display(reshaped)
    except Exception as e:
        print(f"[WARN] Arabic reshape failed: {e}")
    return text


def _text_width(text: str, font: ImageFont.FreeTypeFont) -> int:
    """حساب عرض النص بعد معالجته للعربية"""
    text = _arabic(text)
    try:
        bbox = font.getbbox(text)
        return bbox[2] - bbox[0]
    except:
        return len(text) * (font.size // 2)


def _draw_text(draw, x: int, y: int, text: str, font, color, shadow: bool = True):
    """رسم نص مع دعم عربي كامل"""
    text = _arabic(text)
    if shadow:
        draw.text((x + 2, y + 2), text, fill=(200, 200, 200), font=font)
    draw.text((x, y), text, fill=color, font=font)


def _draw_centered_text(draw, y: int, text: str, font, color) -> int:
    """رسم نص في منتصف العرض"""
    text = _arabic(text)
    w = _text_width(text, font)
    x = (TARGET_W - w) // 2
    draw.text((x + 2, y + 2), text, fill=(200, 200, 200), font=font)
    draw.text((x, y), text, fill=color, font=font)
    return y + font.size + 10


def _wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list:
    """تقسيم النص العربي إلى أسطر"""
    text = _arabic(text)
    words = text.split()
    lines = []
    cur = []
    for w in words:
        cur.append(w)
        line = ' '.join(cur)
        if _text_width(line, font) > max_width:
            cur.pop()
            if cur:
                lines.append(' '.join(cur))
            cur = [w]
    if cur:
        lines.append(' '.join(cur))
    return lines if lines else [text]


# ═══════════════════════════════════════════════════════════════════════════════
# رسم الشخصية الكرتونية (الوجه + الملابس)
# ═══════════════════════════════════════════════════════════════════════════════

def _draw_teacher_character(draw, outfit_name: str, teacher_name: str, x_offset: int = 30, y_offset: int = 0):
    """
    رسم الشخصية الكرتونية (وجه + ملابس) في الزاوية اليسرى السفلى
    """
    outfit = TEACHER_OUTFITS.get(outfit_name, TEACHER_OUTFITS["teacher"])
    color = outfit["color"]
    
    # موقع الشخصية (أسفل يسار الشاشة)
    body_x = x_offset + 20
    body_y = TARGET_H - 200 + y_offset
    body_w, body_h = 100, 130
    
    # رسم الجسم (الملابس)
    draw.rounded_rectangle(
        [(body_x, body_y), (body_x + body_w, body_y + body_h)],
        radius=12, fill=color, outline=(50, 50, 50), width=2
    )
    
    # رسم تفاصيل الملابس (ياقة، أزرار...)
    draw.rectangle(
        [(body_x + 30, body_y + 10), (body_x + 70, body_y + 30)],
        fill=(*color, 200), outline=(100, 100, 100), width=1
    )
    
    # الرأس (وجه)
    head_x = body_x + 10
    head_y = body_y - 60
    head_w, head_h = 80, 80
    draw.ellipse(
        [(head_x, head_y), (head_x + head_w, head_y + head_h)],
        fill=(255, 220, 177), outline=(50, 50, 50), width=2
    )
    
    # شعر (حسب النوع)
    if outfit_name in ["sheikh"]:
        # لحية
        draw.ellipse(
            [(head_x + 20, head_y + 50), (head_x + 60, head_y + 85)],
            fill=(100, 100, 100)
        )
    
    # عيون
    eye_y = head_y + 30
    # عين يسار
    draw.ellipse([(head_x + 20, eye_y), (head_x + 32, eye_y + 12)], fill=(255, 255, 255), outline=(0, 0, 0), width=1)
    draw.ellipse([(head_x + 24, eye_y + 3), (head_x + 28, eye_y + 9)], fill=(0, 0, 0))
    # عين يمين
    draw.ellipse([(head_x + 48, eye_y), (head_x + 60, eye_y + 12)], fill=(255, 255, 255), outline=(0, 0, 0), width=1)
    draw.ellipse([(head_x + 52, eye_y + 3), (head_x + 56, eye_y + 9)], fill=(0, 0, 0))
    
    # ابتسامة
    draw.arc(
        [(head_x + 25, head_y + 45), (head_x + 55, head_y + 65)],
        start=0, end=180, fill=(0, 0, 0), width=2
    )
    
    # أحمر خدود
    draw.ellipse([(head_x + 12, head_y + 42), (head_x + 22, head_y + 50)], fill=(255, 180, 180))
    draw.ellipse([(head_x + 58, head_y + 42), (head_x + 68, head_y + 50)], fill=(255, 180, 180))
    
    # القبعة/الزي على الرأس
    hat = outfit["hat"]
    if hat:
        font_hat = _get_font(35)
        draw.text((head_x + 20, head_y - 25), hat, font=font_hat)
    
    # الأكسسوار (سماعة، كتاب...)
    accessory = outfit["accessory"]
    font_acc = _get_font(28)
    draw.text((body_x + 35, body_y + 40), accessory, font=font_acc)
    
    # اسم المعلم تحت الشخصية
    font_name = _get_font(14, bold=True)
    name_w = _text_width(teacher_name, font_name)
    name_x = body_x + (body_w - name_w) // 2
    _draw_text(draw, name_x, body_y + body_h + 5, teacher_name, font_name, (44, 62, 80))


# ═══════════════════════════════════════════════════════════════════════════════
# 1. شريحة المقدمة (Welcome Slide)
# ═══════════════════════════════════════════════════════════════════════════════

def _draw_welcome(teacher_name: str = "", teacher_outfit: str = "teacher") -> str:
    """شريحة المقدمة مع شعار البوت والشخصية الكرتونية"""
    fd, path = tempfile.mkstemp(prefix="welcome_", suffix=".jpg")
    os.close(fd)

    img = Image.new("RGB", (TARGET_W, TARGET_H), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    # شرائط علوية وسفلية
    draw.rectangle([(0, 0), (TARGET_W, 8)], fill=COLORS[0])
    draw.rectangle([(0, TARGET_H - 8), (TARGET_W, TARGET_H)], fill=COLORS[0])

    # إطار كبير للشعار
    frame_x, frame_y = 200, 80
    frame_w, frame_h = 450, 180
    draw.rounded_rectangle(
        [(frame_x, frame_y), (frame_x + frame_w, frame_y + frame_h)],
        radius=25, outline=COLORS[0], width=8
    )
    draw.rounded_rectangle(
        [(frame_x + 10, frame_y + 10), (frame_x + frame_w - 10, frame_y + frame_h - 10)],
        radius=15, outline=COLORS[0], width=2
    )

    # الشعار بخط كبير
    font_logo = _get_font(55, bold=True)
    logo_w = _text_width(WATERMARK, font_logo)
    logo_x = (TARGET_W - logo_w) // 2
    logo_y = frame_y + 50
    _draw_text(draw, logo_x, logo_y, WATERMARK, font_logo, COLORS[0])

    # رسالة الترحيب
    font_welcome = _get_font(32, bold=True)
    welcome_text = "أهلاً ومرحباً بكم"
    welcome_w = _text_width(welcome_text, font_welcome)
    welcome_x = (TARGET_W - welcome_w) // 2
    welcome_y = frame_y + frame_h + 30
    _draw_text(draw, welcome_x, welcome_y, welcome_text, font_welcome, (44, 62, 80))

    # الشخصية الكرتونية (في الأسفل يسار)
    if teacher_name:
        _draw_teacher_character(draw, teacher_outfit, teacher_name, x_offset=30, y_offset=-20)

    # حقوق البوت
    font_wm = _get_font(14, bold=True)
    wm_w = _text_width(WATERMARK, font_wm)
    _draw_text(draw, TARGET_W - wm_w - 25, TARGET_H - 35, WATERMARK, font_wm, COLORS[0])

    img.save(path, "JPEG", quality=90)
    return path


# ═══════════════════════════════════════════════════════════════════════════════
# 2. شريحة عنوان المحاضرة (Title Slide)
# ═══════════════════════════════════════════════════════════════════════════════

def _draw_title(title: str, teacher_name: str = "", teacher_outfit: str = "teacher") -> str:
    """شريحة عرض عنوان المحاضرة"""
    fd, path = tempfile.mkstemp(prefix="title_", suffix=".jpg")
    os.close(fd)

    img = Image.new("RGB", (TARGET_W, TARGET_H), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    draw.rectangle([(0, 0), (TARGET_W, 6)], fill=COLORS[1])

    font_title = _get_font(36, bold=True)
    lines = _wrap_text(title, font_title, TARGET_W - 100)

    y = TARGET_H // 2 - (len(lines) * 45) // 2
    for line in lines:
        w = _text_width(line, font_title)
        x = (TARGET_W - w) // 2
        _draw_text(draw, x, y, line, font_title, (44, 62, 80))
        y += 45

    # الشخصية الكرتونية
    if teacher_name:
        _draw_teacher_character(draw, teacher_outfit, teacher_name, x_offset=30, y_offset=-20)

    # حقوق البوت
    font_wm = _get_font(14, bold=True)
    wm_w = _text_width(WATERMARK, font_wm)
    _draw_text(draw, TARGET_W - wm_w - 25, TARGET_H - 35, WATERMARK, font_wm, COLORS[1])

    img.save(path, "JPEG", quality=90)
    return path


# ═══════════════════════════════════════════════════════════════════════════════
# 3. شريحة خريطة الأقسام (Sections Map)
# ═══════════════════════════════════════════════════════════════════════════════

def _draw_map(titles: list, keywords_list: list, teacher_name: str = "", teacher_outfit: str = "teacher") -> str:
    """شريحة عرض خريطة الأقسام مع الكلمات المفتاحية"""
    fd, path = tempfile.mkstemp(prefix="map_", suffix=".jpg")
    os.close(fd)

    img = Image.new("RGB", (TARGET_W, TARGET_H), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    draw.rectangle([(0, 0), (TARGET_W, 6)], fill=COLORS[2])

    font_title = _get_font(28, bold=True)
    map_title = "📋 خريطة المحاضرة"
    w = _text_width(map_title, font_title)
    x = (TARGET_W - w) // 2
    _draw_text(draw, x, 25, map_title, font_title, COLORS[2])

    y = 80
    font_sec = _get_font(18, bold=True)
    font_kw = _get_font(13)
    font_num = _get_font(14, bold=True)

    for i, (t, kw_list) in enumerate(zip(titles, keywords_list)):
        if i >= 6:  # أقصى حد 6 أقسام في الخريطة
            break
        color = COLORS[i % len(COLORS)]
        
        # رقم القسم
        draw.ellipse([(25, y), (45, y + 20)], fill=color)
        num_str = str(i + 1)
        draw.text((35, y + 3), num_str, fill=(255, 255, 255), font=font_num)
        
        # عنوان القسم
        sec_text = t[:30]
        _draw_text(draw, 60, y - 2, sec_text, font_sec, (44, 62, 80))
        
        # الكلمات المفتاحية
        if kw_list:
            kw_text = " • ".join(kw_list[:3])
            kw_w = _text_width(kw_text, font_kw)
            if kw_w > TARGET_W - 200:
                kw_text = " • ".join(kw_list[:2])
            _draw_text(draw, 75, y + 22, kw_text, font_kw, color)
        
        y += 55

    # الشخصية الكرتونية
    if teacher_name:
        _draw_teacher_character(draw, teacher_outfit, teacher_name, x_offset=30, y_offset=-20)

    # حقوق البوت
    font_wm = _get_font(13, bold=True)
    wm_w = _text_width(WATERMARK, font_wm)
    _draw_text(draw, TARGET_W - wm_w - 25, TARGET_H - 30, WATERMARK, font_wm, COLORS[2])

    img.save(path, "JPEG", quality=90)
    return path


# ═══════════════════════════════════════════════════════════════════════════════
# 4. شريحة عنوان القسم (Section Title Card)
# ═══════════════════════════════════════════════════════════════════════════════

def _draw_section_title(title: str, idx: int, teacher_name: str = "", teacher_outfit: str = "teacher") -> str:
    """شريحة عنوان القسم مع رقم"""
    fd, path = tempfile.mkstemp(prefix=f"sec_title_{idx}_", suffix=".jpg")
    os.close(fd)

    color = COLORS[idx % len(COLORS)]
    img = Image.new("RGB", (TARGET_W, TARGET_H), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    draw.rectangle([(0, 0), (TARGET_W, 6)], fill=color)

    # دائرة الرقم
    cx, cy = TARGET_W // 2, TARGET_H // 2 - 40
    cr = 45
    draw.ellipse([cx - cr, cy - cr, cx + cr, cy + cr], fill=color)

    num_str = str(idx + 1)
    font_num = _get_font(40, bold=True)
    nw = _text_width(num_str, font_num)
    draw.text((cx - nw // 2, cy - 22), num_str, fill=(255, 255, 255), font=font_num)

    # عنوان القسم
    font_title = _get_font(30, bold=True)
    lines = _wrap_text(title, font_title, TARGET_W - 100)
    y = cy + cr + 30
    for line in lines:
        w = _text_width(line, font_title)
        x = (TARGET_W - w) // 2
        _draw_text(draw, x, y, line, font_title, (44, 62, 80))
        y += 40

    # الشخصية الكرتونية
    if teacher_name:
        _draw_teacher_character(draw, teacher_outfit, teacher_name, x_offset=30, y_offset=-20)

    # حقوق البوت
    font_wm = _get_font(13, bold=True)
    wm_w = _text_width(WATERMARK, font_wm)
    _draw_text(draw, TARGET_W - wm_w - 25, TARGET_H - 30, WATERMARK, font_wm, color)

    img.save(path, "JPEG", quality=90)
    return path


# ═══════════════════════════════════════════════════════════════════════════════
# 5. شريحة المحتوى - السبورة المتراكمة مع الشخصية الكرتونية
# ═══════════════════════════════════════════════════════════════════════════════

def _draw_content(
    img_bytes: bytes,
    keywords: list,
    sec_title: str,
    sec_idx: int,
    cur: int,
    total: int,
    teacher_name: str,
    teacher_outfit: str,
    is_arabic: bool = True
) -> str:
    """
    شريحة المحتوى الرئيسية:
    - صورة تملأ المساحة (مع إطار)
    - الشخصية الكرتونية في الزاوية
    - الكلمات المفتاحية تتراكم مع تقدم الشرح
    - مؤشر تقدم (نقاط)
    """
    fd, path = tempfile.mkstemp(prefix="content_", suffix=".jpg")
    os.close(fd)

    color = COLORS[sec_idx % len(COLORS)]
    # خلفية السبورة
    img = Image.new("RGB", (TARGET_W, TARGET_H), (248, 248, 250))
    draw = ImageDraw.Draw(img)

    # شريط علوي
    draw.rectangle([(0, 0), (TARGET_W, 6)], fill=color)

    # عنوان القسم في الأعلى
    font_header = _get_font(18, bold=True)
    hd = sec_title[:40]
    hw = _text_width(hd, font_header)
    hx = (TARGET_W - hw) // 2
    _draw_text(draw, hx, 15, hd, font_header, (44, 62, 80))
    draw.rectangle([(hx, 38), (hx + hw, 40)], fill=color)

    # ═══════════════════════════════════════════════════════════════════════════
    # الصورة الرئيسية (تملأ المساحة)
    # ═══════════════════════════════════════════════════════════════════════════
    img_x, img_y = 200, 55
    img_max_w, img_max_h = 550, 280
    
    if img_bytes:
        try:
            pil = Image.open(io.BytesIO(img_bytes)).convert("RGB")
            iw, ih = pil.size
            s = min(img_max_w / iw, img_max_h / ih)
            nw, nh = int(iw * s), int(ih * s)
            pil = pil.resize((nw, nh), Image.LANCZOS)
            
            px = img_x + (img_max_w - nw) // 2
            py = img_y + (img_max_h - nh) // 2
            
            # إطار للصورة
            draw.rounded_rectangle(
                [(px - 6, py - 6), (px + nw + 6, py + nh + 6)],
                radius=12, outline=color, width=5
            )
            draw.rounded_rectangle(
                [(px - 2, py - 2), (px + nw + 2, py + nh + 2)],
                radius=8, outline=(*color, 100), width=1
            )
            img.paste(pil, (px, py))
        except Exception as e:
            print(f"[WARN] Failed to paste image: {e}")
            # رسم مستطيل فارغ
            draw.rounded_rectangle(
                [(img_x, img_y), (img_x + img_max_w, img_y + img_max_h)],
                radius=12, outline=(200, 200, 200), width=2
            )
    else:
        # رسم مستطيل فارغ
        draw.rounded_rectangle(
            [(img_x, img_y), (img_x + img_max_w, img_y + img_max_h)],
            radius=12, outline=(200, 200, 200), width=2
        )

    # ═══════════════════════════════════════════════════════════════════════════
    # الشخصية الكرتونية (في الزاوية اليسرى السفلى)
    # ═══════════════════════════════════════════════════════════════════════════
    _draw_teacher_character(draw, teacher_outfit, teacher_name, x_offset=15, y_offset=-10)

    # ═══════════════════════════════════════════════════════════════════════════
    # الكلمات المفتاحية (تتراكم مع تقدم الشرح)
    # ═══════════════════════════════════════════════════════════════════════════
    font_kw = _get_font(18, bold=True)
    vis = keywords[:cur + 1]
    
    # موقع الكلمات (يمين الصورة)
    kw_start_x = 200
    kw_start_y = 350
    
    for i, kw in enumerate(vis):
        kcol = COLORS[i % len(COLORS)]
        kw_w = _text_width(kw, font_kw)
        
        col = i % 2
        row = i // 2
        cx = kw_start_x + col * 280
        cy = kw_start_y + row * 35
        
        # خلفية للكلمة
        draw.rounded_rectangle(
            [(cx - 12, cy - 6), (cx + kw_w + 12, cy + 28)],
            radius=10, fill=(*kcol, 25), outline=kcol, width=2
        )
        _draw_text(draw, cx, cy, kw, font_kw, kcol)

    # ═══════════════════════════════════════════════════════════════════════════
    # مؤشر التقدم (نقاط)
    # ═══════════════════════════════════════════════════════════════════════════
    dot_y = TARGET_H - 25
    dot_r = 6
    dot_gap = 25
    total_w = total * dot_gap
    start_x = (TARGET_W - total_w) // 2
    
    for i in range(total):
        dx = start_x + i * dot_gap
        dot_c = color if i <= cur else (200, 200, 200)
        r = dot_r if i <= cur else dot_r - 2
        draw.ellipse([(dx - r, dot_y - r), (dx + r, dot_y + r)], fill=dot_c)

    # ═══════════════════════════════════════════════════════════════════════════
    # حقوق البوت
    # ═══════════════════════════════════════════════════════════════════════════
    font_wm = _get_font(12, bold=True)
    wm_w = _text_width(WATERMARK, font_wm)
    _draw_text(draw, TARGET_W - wm_w - 20, TARGET_H - 22, WATERMARK, font_wm, color)

    img.save(path, "JPEG", quality=92)
    return path


# ═══════════════════════════════════════════════════════════════════════════════
# 6. شريحة السؤال التفاعلي (مؤقت 5 ثواني) - اختياري
# ═══════════════════════════════════════════════════════════════════════════════

def _draw_question_slide(question: str, section_idx: int, teacher_name: str = "", teacher_outfit: str = "teacher") -> str:
    """شريحة سؤال مع مؤقت 5 ثواني"""
    fd, path = tempfile.mkstemp(prefix="question_", suffix=".jpg")
    os.close(fd)
    
    col = COLORS[section_idx % len(COLORS)]
    img = Image.new("RGB", (TARGET_W, TARGET_H), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    draw.rectangle([(0, 0), (TARGET_W, 8)], fill=col)
    draw.rectangle([(0, TARGET_H - 8), (TARGET_W, TARGET_H)], fill=col)

    # أيقونة سؤال
    font_icon = _get_font(50)
    _draw_text(draw, TARGET_W // 2 - 30, 70, "❓", font_icon, col)

    # نص السؤال
    font_q = _get_font(26, bold=True)
    lines = _wrap_text(question, font_q, TARGET_W - 120)
    y = 150
    for line in lines:
        w = _text_width(line, font_q)
        x = (TARGET_W - w) // 2
        _draw_text(draw, x, y, line, font_q, (44, 62, 80))
        y += 45

    # مؤقت 5 ثواني
    font_timer = _get_font(20)
    timer_text = "⏳ فكر في الإجابة... (5 ثوان)"
    w = _text_width(timer_text, font_timer)
    x = (TARGET_W - w) // 2
    _draw_text(draw, x, TARGET_H - 100, timer_text, font_timer, col)

    # الشخصية الكرتونية
    if teacher_name:
        _draw_teacher_character(draw, teacher_outfit, teacher_name, x_offset=30, y_offset=-20)

    img.save(path, "JPEG", quality=90)
    return path


def _draw_answer_slide(question: str, answer: str, section_idx: int, teacher_name: str = "", teacher_outfit: str = "teacher") -> str:
    """شريحة الإجابة"""
    fd, path = tempfile.mkstemp(prefix="answer_", suffix=".jpg")
    os.close(fd)
    
    col = COLORS[section_idx % len(COLORS)]
    img = Image.new("RGB", (TARGET_W, TARGET_H), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    draw.rectangle([(0, 0), (TARGET_W, 8)], fill=col)
    draw.rectangle([(0, TARGET_H - 8), (TARGET_W, TARGET_H)], fill=col)

    # أيقونة إجابة
    font_icon = _get_font(40)
    _draw_text(draw, TARGET_W // 2 - 25, 40, "✅", font_icon, col)

    # السؤال (صغير)
    font_q_small = _get_font(16)
    q_text = question[:60] + "..." if len(question) > 60 else question
    w = _text_width(q_text, font_q_small)
    x = (TARGET_W - w) // 2
    _draw_text(draw, x, 95, q_text, font_q_small, (100, 100, 100))

    # الإجابة
    font_a = _get_font(24, bold=True)
    lines = _wrap_text(answer, font_a, TARGET_W - 100)
    y = 150
    for line in lines:
        w = _text_width(line, font_a)
        x = (TARGET_W - w) // 2
        _draw_text(draw, x, y, line, font_a, col)
        y += 40

    # الشخصية الكرتونية
    if teacher_name:
        _draw_teacher_character(draw, teacher_outfit, teacher_name, x_offset=30, y_offset=-20)

    img.save(path, "JPEG", quality=90)
    return path


# ═══════════════════════════════════════════════════════════════════════════════
# 7. شريحة الملخص النهائي (Final Summary)
# ═══════════════════════════════════════════════════════════════════════════════

def _draw_summary(all_keywords: list, teacher_name: str = "", teacher_outfit: str = "teacher") -> str:
    """شريحة الملخص النهائي مع جميع الكلمات المفتاحية"""
    fd, path = tempfile.mkstemp(prefix="summary_", suffix=".jpg")
    os.close(fd)

    img = Image.new("RGB", (TARGET_W, TARGET_H), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    draw.rectangle([(0, 0), (TARGET_W, 8)], fill=COLORS[0])
    draw.rectangle([(0, TARGET_H - 8), (TARGET_W, TARGET_H)], fill=COLORS[0])

    font_title = _get_font(30, bold=True)
    title_text = "📋 ملخص المحاضرة"
    w = _text_width(title_text, font_title)
    x = (TARGET_W - w) // 2
    _draw_text(draw, x, 35, title_text, font_title, (44, 62, 80))

    y = 90
    font_kw = _get_font(16, bold=True)
    
    for i, kw in enumerate(all_keywords[:12]):
        color = COLORS[i % len(COLORS)]
        kw_w = _text_width(kw, font_kw)
        cx = 50 + (i % 3) * 250
        cy = y + (i // 3) * 45
        
        draw.rounded_rectangle(
            [(cx - 12, cy - 6), (cx + kw_w + 12, cy + 28)],
            radius=10, fill=(*color, 25), outline=color, width=2
        )
        _draw_text(draw, cx, cy, kw, font_kw, color)

    font_thanks = _get_font(26, bold=True)
    thanks_text = "🙏 شكراً لحسن استماعكم"
    w = _text_width(thanks_text, font_thanks)
    x = (TARGET_W - w) // 2
    _draw_text(draw, x, TARGET_H - 60, thanks_text, font_thanks, COLORS[0])

    # الشخصية الكرتونية
    if teacher_name:
        _draw_teacher_character(draw, teacher_outfit, teacher_name, x_offset=30, y_offset=-20)

    # حقوق البوت
    font_wm = _get_font(14, bold=True)
    wm_w = _text_width(WATERMARK, font_wm)
    _draw_text(draw, TARGET_W - wm_w - 25, TARGET_H - 35, WATERMARK, font_wm, COLORS[0])

    img.save(path, "JPEG", quality=90)
    return path


# ═══════════════════════════════════════════════════════════════════════════════
# FFmpeg - تنسيق متوافق مع تيليجرام 100%
# ═══════════════════════════════════════════════════════════════════════════════

def _ffmpeg_seg(img: str, dur: float, aud: str, start: float, out: str):
    """تشفير مقطع فيديو متوافق مع تيليجرام"""
    dstr = f"{dur:.3f}"
    
    if aud and os.path.exists(aud):
        cmd = [
            "ffmpeg", "-y",
            "-loop", "1", "-i", img,
            "-ss", f"{start:.3f}", "-t", dstr, "-i", aud,
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-pix_fmt", "yuv420p",
            "-vf", f"scale={TARGET_W}:{TARGET_H}:force_original_aspect_ratio=decrease,pad={TARGET_W}:{TARGET_H}:(ow-iw)/2:(oh-ih)/2",
            "-r", "15",
            "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "2",
            "-movflags", "+faststart",
            "-shortest", "-t", dstr, out
        ]
    else:
        cmd = [
            "ffmpeg", "-y",
            "-loop", "1", "-i", img,
            "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-pix_fmt", "yuv420p",
            "-vf", f"scale={TARGET_W}:{TARGET_H}:force_original_aspect_ratio=decrease,pad={TARGET_W}:{TARGET_H}:(ow-iw)/2:(oh-ih)/2",
            "-r", "15",
            "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "2",
            "-movflags", "+faststart",
            "-shortest", "-t", dstr, out
        ]
    
    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0:
        print(f"[FFmpeg] Error: {result.stderr.decode()[:500]}")
        raise RuntimeError("FFmpeg encoding failed")


def _ffmpeg_cat(segs: list, out: str):
    """دمج المقاطع"""
    fd, lst = tempfile.mkstemp(suffix=".txt")
    os.close(fd)
    with open(lst, "w") as f:
        for s in segs:
            f.write(f"file '{s}'\n")
    
    cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", out]
    result = subprocess.run(cmd, capture_output=True)
    os.remove(lst)
    
    if result.returncode != 0:
        print(f"[FFmpeg] Concat error: {result.stderr.decode()[:500]}")
        raise RuntimeError("FFmpeg concat failed")


# ═══════════════════════════════════════════════════════════════════════════════
# بناء الفيديو
# ═══════════════════════════════════════════════════════════════════════════════

def _build(sections: list, audio_results: list, lecture_data: dict) -> tuple:
    """
    بناء جميع مقاطع الفيديو
    """
    segs = []
    tmps = []
    total = 0.0
    
    title = lecture_data.get("title", "المحاضرة التعليمية")
    all_keywords = lecture_data.get("all_keywords", [])
    teacher_name = lecture_data.get("teacher_name", "المعلم")
    teacher_outfit = lecture_data.get("teacher_outfit", "teacher")
    is_arabic = not lecture_data.get("is_english", False)
    
    # استخراج الكلمات المفتاحية لكل قسم (للخريطة)
    section_titles = [s.get("title", "") for s in sections]
    section_keywords = [s.get("keywords", []) for s in sections]

    # 1. شريحة المقدمة
    p = _draw_welcome(teacher_name, teacher_outfit)
    tmps.append(p)
    segs.append({"img": p, "audio": None, "audio_start": 0, "dur": 3.5})
    total += 3.5

    # 2. شريحة عنوان المحاضرة
    p = _draw_title(title, teacher_name, teacher_outfit)
    tmps.append(p)
    segs.append({"img": p, "audio": None, "audio_start": 0, "dur": 4.0})
    total += 4.0

    # 3. شريحة خريطة الأقسام
    p = _draw_map(section_titles, section_keywords, teacher_name, teacher_outfit)
    tmps.append(p)
    segs.append({"img": p, "audio": None, "audio_start": 0, "dur": 5.0})
    total += 5.0

    # 4. الأقسام الرئيسية
    for i, (s, a) in enumerate(zip(sections, audio_results)):
        # شريحة عنوان القسم
        p = _draw_section_title(s.get("title", f"القسم {i+1}"), i, teacher_name, teacher_outfit)
        tmps.append(p)
        segs.append({"img": p, "audio": None, "audio_start": 0, "dur": 3.0})
        total += 3.0

        keywords = s.get("keywords", ["مفهوم"])
        img_bytes = s.get("_image_bytes")
        audio_bytes = a.get("audio")
        total_dur = max(a.get("duration", 30), 5.0)
        
        n_kw = len(keywords)
        kw_dur = total_dur / n_kw if n_kw > 0 else total_dur

        apath = None
        if audio_bytes:
            af, apath = tempfile.mkstemp(prefix=f"aud_{i}_", suffix=".mp3")
            os.close(af)
            with open(apath, "wb") as f:
                f.write(audio_bytes)
            tmps.append(apath)

        sec_title = s.get("title", "")
        
        # شرائح المحتوى المتراكم
        for kw_idx in range(n_kw):
            p = _draw_content(
                img_bytes=img_bytes,
                keywords=keywords,
                sec_title=sec_title,
                sec_idx=i,
                cur=kw_idx,
                total=n_kw,
                teacher_name=teacher_name,
                teacher_outfit=teacher_outfit,
                is_arabic=is_arabic
            )
            tmps.append(p)
            segs.append({
                "img": p,
                "audio": apath,
                "audio_start": kw_idx * kw_dur,
                "dur": kw_dur,
            })
            total += kw_dur

        # أسئلة تفاعلية (اختياري - يمكن تعطيلها)
        # if s.get("question"):
        #     p = _draw_question_slide(s["question"], i, teacher_name, teacher_outfit)
        #     tmps.append(p)
        #     segs.append({"img": p, "audio": None, "audio_start": 0, "dur": 5.0})
        #     total += 5.0
        #     
        #     p = _draw_answer_slide(s["question"], s.get("answer", ""), i, teacher_name, teacher_outfit)
        #     tmps.append(p)
        #     segs.append({"img": p, "audio": apath, "audio_start": n_kw * kw_dur, "dur": kw_dur * 0.5})
        #     total += kw_dur * 0.5

    # 5. شريحة الملخص النهائي
    p = _draw_summary(all_keywords, teacher_name, teacher_outfit)
    tmps.append(p)
    segs.append({"img": p, "audio": None, "audio_start": 0, "dur": 6.0})
    total += 6.0

    return segs, tmps, total


def _encode(segs: list, out: str):
    """تشفير جميع المقاطع ودمجها"""
    paths = []
    try:
        for i, s in enumerate(segs):
            fd, p = tempfile.mkstemp(prefix=f"seg_{i}_", suffix=".mp4")
            os.close(fd)
            paths.append(p)
            print(f"[Video] Encoding segment {i+1}/{len(segs)} ({s['dur']:.1f}s)...")
            _ffmpeg_seg(s["img"], s["dur"], s["audio"], s["audio_start"], p)
        
        print(f"[Video] Concatenating {len(paths)} segments...")
        _ffmpeg_cat(paths, out)
        print(f"[Video] Done!")
    finally:
        for p in paths:
            try:
                os.remove(p)
            except:
                pass


# ═══════════════════════════════════════════════════════════════════════════════
# الدالة الرئيسية
# ═══════════════════════════════════════════════════════════════════════════════

async def create_video_from_sections(
    sections: list,
    audio_results: list,
    lecture_data: dict,
    output_path: str,
    dialect: str = "msa",
    progress_cb=None,
) -> float:
    """
    إنشاء فيديو كامل من الأقسام والصوت
    """
    loop = asyncio.get_event_loop()

    # التأكد من وجود جميع البيانات المطلوبة
    for s in sections:
        if "keywords" not in s or not s["keywords"]:
            s["keywords"] = ["مفهوم", "تعريف", "شرح", "تحليل"]
        if "_image_bytes" not in s:
            s["_image_bytes"] = None

    print(f"[Video] Building {len(sections)} sections...")
    segs, tmps, total_secs = await loop.run_in_executor(
        None, _build, sections, audio_results, lecture_data
    )

    print(f"[Video] Encoding video ({total_secs:.1f}s total)...")
    await loop.run_in_executor(None, _encode, segs, output_path)

    # تنظيف الملفات المؤقتة
    for p in tmps:
        try:
            os.remove(p)
        except:
            pass

    return total_secs
