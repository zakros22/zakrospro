#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
توليد الصور الكرتونية والكروت التعليمية الاحترافية
"""

import io
import os
import random
import tempfile
import asyncio
import aiohttp
from PIL import Image as PILImage, ImageDraw, ImageFont, ImageFilter

# ══════════════════════════════════════════════════════════════════════════════
#  الإعدادات
# ══════════════════════════════════════════════════════════════════════════════
W, H = 854, 480

# ألوان حسب المادة
SUBJECT_COLORS = {
    "medicine": {"primary": (180, 30, 60), "secondary": (220, 50, 80), "accent": (255, 220, 200), "bg": (248, 248, 250)},
    "science": {"primary": (20, 80, 120), "secondary": (40, 140, 200), "accent": (220, 255, 200), "bg": (248, 250, 248)},
    "math": {"primary": (80, 30, 140), "secondary": (130, 60, 200), "accent": (255, 220, 100), "bg": (250, 248, 255)},
    "physics": {"primary": (30, 40, 120), "secondary": (70, 100, 200), "accent": (200, 220, 255), "bg": (248, 250, 255)},
    "chemistry": {"primary": (100, 20, 90), "secondary": (180, 40, 150), "accent": (255, 200, 220), "bg": (255, 248, 250)},
    "engineering": {"primary": (20, 70, 100), "secondary": (60, 130, 180), "accent": (255, 230, 150), "bg": (248, 250, 250)},
    "computer": {"primary": (20, 60, 100), "secondary": (60, 130, 180), "accent": (200, 255, 150), "bg": (248, 250, 248)},
    "history": {"primary": (120, 60, 30), "secondary": (200, 140, 80), "accent": (255, 230, 150), "bg": (255, 250, 245)},
    "literature": {"primary": (60, 30, 80), "secondary": (140, 80, 160), "accent": (255, 200, 220), "bg": (250, 248, 255)},
    "business": {"primary": (20, 80, 60), "secondary": (80, 160, 120), "accent": (255, 220, 100), "bg": (248, 250, 248)},
    "other": {"primary": (40, 40, 120), "secondary": (100, 100, 200), "accent": (255, 200, 100), "bg": (248, 248, 255)},
}


# ══════════════════════════════════════════════════════════════════════════════
#  دوال مساعدة للنص العربي
# ══════════════════════════════════════════════════════════════════════════════
def prepare_arabic(text: str) -> str:
    """تحضير النص العربي للعرض."""
    if not text:
        return text
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
        return get_display(arabic_reshaper.reshape(text))
    except:
        return text


def get_font(size: int, bold: bool = False, arabic: bool = False):
    """تحميل الخط المناسب."""
    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "fonts/Amiri-Bold.ttf" if bold and arabic else "fonts/Amiri-Regular.ttf"
    ]
    
    for path in font_paths:
        try:
            if os.path.exists(path):
                return ImageFont.truetype(path, size)
        except:
            continue
    
    return ImageFont.load_default()


# ══════════════════════════════════════════════════════════════════════════════
#  إنشاء كرت تعليمي احترافي
# ══════════════════════════════════════════════════════════════════════════════
def create_educational_card(
    section_title: str,
    keywords: list,
    subject: str,
    section_num: int,
    total_sections: int,
    is_arabic: bool = True
) -> str:
    """
    إنشاء كرت تعليمي احترافي يشبه الكروت الطبية/التعليمية.
    
    Args:
        section_title: عنوان القسم
        keywords: قائمة الكلمات المفتاحية
        subject: نوع المادة (medicine, math, etc)
        section_num: رقم القسم
        total_sections: إجمالي الأقسام
        is_arabic: هل النص عربي
    
    Returns:
        مسار الصورة المؤقتة
    """
    colors = SUBJECT_COLORS.get(subject, SUBJECT_COLORS["other"])
    primary, secondary, accent, bg_color = colors["primary"], colors["secondary"], colors["accent"], colors["bg"]
    
    # إنشاء الصورة
    img = PILImage.new("RGB", (W, H), bg_color)
    draw = ImageDraw.Draw(img)
    
    # ═════════════════════════════════════════════════════════════════════════
    # شريط علوي
    # ═════════════════════════════════════════════════════════════════════════
    draw.rectangle([(0, 0), (W, 8)], fill=primary)
    
    # ═════════════════════════════════════════════════════════════════════════
    # رأس الكرت - خلفية ملونة
    # ═════════════════════════════════════════════════════════════════════════
    draw.rectangle([(0, 8), (W, 75)], fill=primary)
    
    # رقم القسم
    font_small = get_font(13, bold=True)
    section_label = f"{section_num}/{total_sections}"
    draw.text((18, 16), section_label, fill=(255, 255, 255, 180), font=font_small)
    
    # أيقونة حسب المادة
    icons = {
        "medicine": "🩺", "science": "🔬", "math": "📐", "physics": "⚡",
        "chemistry": "🧪", "engineering": "🏗️", "computer": "💻",
        "history": "📜", "literature": "📖", "business": "💼", "other": "📚"
    }
    icon = icons.get(subject, "📚")
    font_icon = get_font(20)
    draw.text((W - 50, 16), icon, fill=(255, 255, 255, 200), font=font_icon)
    
    # عنوان القسم
    title_display = prepare_arabic(section_title) if is_arabic else section_title
    font_title = get_font(24, bold=True, arabic=is_arabic)
    
    # تقسيم العنوان إذا كان طويلاً
    if len(title_display) > 45:
        words = title_display.split()
        mid = len(words) // 2
        line1 = " ".join(words[:mid])
        line2 = " ".join(words[mid:])
        
        bbox1 = draw.textbbox((0, 0), line1, font=font_title)
        tw1 = bbox1[2] - bbox1[0]
        draw.text(((W - tw1) // 2, 28), line1, fill=(255, 255, 255), font=font_title)
        
        bbox2 = draw.textbbox((0, 0), line2, font=font_title)
        tw2 = bbox2[2] - bbox2[0]
        draw.text(((W - tw2) // 2, 55), line2, fill=(255, 255, 255), font=font_title)
    else:
        bbox = draw.textbbox((0, 0), title_display, font=font_title)
        tw = bbox[2] - bbox[0]
        draw.text(((W - tw) // 2, 30), title_display, fill=(255, 255, 255), font=font_title)
    
    # خط تحت العنوان
    draw.rectangle([(W//4, 72), (W*3//4, 75)], fill=accent)
    
    # ═════════════════════════════════════════════════════════════════════════
    # منطقة المحتوى
    # ═════════════════════════════════════════════════════════════════════════
    # إطار
    draw.rectangle([(20, 90), (W-20, H-20)], fill=(255, 255, 255), outline=secondary, width=2)
    
    # عنوان "مصطلحات رئيسية"
    font_label = get_font(16, bold=True, arabic=is_arabic)
    label = "📌 مصطلحات رئيسية:" if is_arabic else "📌 Key Terms:"
    label_display = prepare_arabic(label) if is_arabic else label
    draw.text((40, 108), label_display, fill=primary, font=font_label)
    
    # ═════════════════════════════════════════════════════════════════════════
    # المصطلحات (في عمودين)
    # ═════════════════════════════════════════════════════════════════════════
    font_kw = get_font(15, arabic=is_arabic)
    y_start = 150
    line_height = 45
    
    # تنظيف المصطلحات
    clean_keywords = []
    for kw in keywords[:8]:
        if kw and len(str(kw)) > 1:
            clean_keywords.append(str(kw))
    
    if not clean_keywords:
        clean_keywords = ["مصطلح 1", "مصطلح 2", "مصطلح 3"] if is_arabic else ["Term 1", "Term 2", "Term 3"]
    
    for i, kw in enumerate(clean_keywords):
        kw_display = prepare_arabic(f"• {kw}") if is_arabic else f"• {kw}"
        
        if i % 2 == 0:
            x = 45
            y = y_start + (i // 2) * line_height
        else:
            x = W//2 + 15
            y = y_start + (i // 2) * line_height
        
        if y < H - 60:
            # مربع ملون صغير
            draw.rectangle([(x-5, y+5), (x-1, y+9)], fill=secondary)
            draw.text((x+5, y), kw_display, fill=(60, 60, 80), font=font_kw)
    
    # ═════════════════════════════════════════════════════════════════════════
    # رسم توضيحي حسب المادة
    # ═════════════════════════════════════════════════════════════════════════
    icon_x = W - 100
    icon_y = H - 110
    
    if subject == "medicine":
        # صليب طبي
        draw.rectangle([(icon_x, icon_y+30), (icon_x+60, icon_y+40)], fill=primary)
        draw.rectangle([(icon_x+25, icon_y+15), (icon_x+35, icon_y+75)], fill=primary)
    elif subject == "math":
        # رموز رياضية
        font_math = get_font(28, bold=True)
        draw.text((icon_x-10, icon_y+20), "∑", fill=primary, font=font_math)
        draw.text((icon_x+30, icon_y+20), "∫", fill=secondary, font=font_math)
    elif subject == "science":
        # دورق
        draw.ellipse([(icon_x+15, icon_y+40), (icon_x+45, icon_y+70)], outline=primary, width=2)
        draw.rectangle([(icon_x+20, icon_y+10), (icon_x+40, icon_y+40)], outline=primary, width=2)
    elif subject == "physics":
        # ذرة
        draw.ellipse([(icon_x+10, icon_y+30), (icon_x+50, icon_y+70)], outline=primary, width=2)
        draw.ellipse([(icon_x+20, icon_y+20), (icon_x+40, icon_y+80)], outline=secondary, width=2)
        draw.ellipse([(icon_x+25, icon_y+40), (icon_x+35, icon_y+50)], fill=accent)
    else:
        # نجمة
        for i in range(5):
            import math
            angle = i * 72 - 90
            x1 = icon_x + 30 + 25 * math.cos(math.radians(angle))
            y1 = icon_y + 45 + 25 * math.sin(math.radians(angle))
            x2 = icon_x + 30 + 12 * math.cos(math.radians(angle+36))
            y2 = icon_y + 45 + 12 * math.sin(math.radians(angle+36))
            draw.line([(x1, y1), (x2, y2)], fill=accent, width=3)
    
    # ═════════════════════════════════════════════════════════════════════════
    # شريط سفلي وعلامة مائية
    # ═════════════════════════════════════════════════════════════════════════
    draw.rectangle([(0, H-6), (W, H)], fill=primary)
    
    font_wm = get_font(11)
    draw.text((W-130, H-22), "@zakros_probot", fill=(150, 150, 170), font=font_wm)
    
    # حفظ الصورة
    fd, path = tempfile.mkstemp(suffix=".jpg", dir="/tmp/telegram_bot")
    os.close(fd)
    img.save(path, "JPEG", quality=92)
    
    return path


# ══════════════════════════════════════════════════════════════════════════════
#  إنشاء صورة الملخص (تجمع كل الصور)
# ══════════════════════════════════════════════════════════════════════════════
def create_summary_card(
    sections: list,
    lecture_title: str,
    subject: str,
    is_arabic: bool = True
) -> str:
    """
    إنشاء كرت الملخص النهائي الذي يجمع كل الأقسام.
    """
    colors = SUBJECT_COLORS.get(subject, SUBJECT_COLORS["other"])
    primary, secondary, accent = colors["primary"], colors["secondary"], colors["accent"]
    
    img = PILImage.new("RGB", (W, H), (248, 248, 250))
    draw = ImageDraw.Draw(img)
    
    # شريط علوي
    draw.rectangle([(0, 0), (W, 8)], fill=primary)
    draw.rectangle([(0, 8), (W, 60)], fill=primary)
    
    # عنوان الملخص
    title = "📋 ملخص المحاضرة" if is_arabic else "📋 Lecture Summary"
    title_display = prepare_arabic(title) if is_arabic else title
    font_title = get_font(24, bold=True, arabic=is_arabic)
    bbox = draw.textbbox((0, 0), title_display, font=font_title)
    tw = bbox[2] - bbox[0]
    draw.text(((W - tw) // 2, 18), title_display, fill=(255, 255, 255), font=font_title)
    
    # إطار المحتوى
    draw.rectangle([(20, 75), (W-20, H-20)], fill=(255, 255, 255), outline=secondary, width=2)
    
    # عرض الأقسام
    font_sec = get_font(14, bold=True, arabic=is_arabic)
    font_kw = get_font(12, arabic=is_arabic)
    
    y = 95
    for i, sec in enumerate(sections[:6]):
        accent_color = list(SUBJECT_COLORS.values())[i % len(SUBJECT_COLORS)]["primary"]
        
        # رقم القسم
        draw.ellipse([(35, y), (55, y+20)], fill=accent_color)
        font_num = get_font(12, bold=True)
        draw.text((42, y+3), str(i+1), fill=(255, 255, 255), font=font_num)
        
        # عنوان القسم
        sec_title = sec.get("title", f"القسم {i+1}")[:35]
        sec_display = prepare_arabic(sec_title) if is_arabic else sec_title
        draw.text((70, y+2), sec_display, fill=(40, 40, 60), font=font_sec)
        
        # كلمات مفتاحية
        keywords = sec.get("keywords", [])[:3]
        kw_text = " • ".join(keywords)
        kw_display = prepare_arabic(kw_text) if is_arabic else kw_text
        draw.text((70, y+22), kw_display, fill=(100, 100, 130), font=font_kw)
        
        y += 55
        
        # خط فاصل
        if i < len(sections) - 1:
            draw.line([(40, y-5), (W-40, y-5)], fill=(200, 200, 210), width=1)
    
    # شريط سفلي
    draw.rectangle([(0, H-6), (W, H)], fill=primary)
    
    # علامة مائية
    font_wm = get_font(11)
    draw.text((W-130, H-22), "@zakros_probot", fill=(150, 150, 170), font=font_wm)
    
    # حفظ
    fd, path = tempfile.mkstemp(suffix=".jpg", dir="/tmp/telegram_bot")
    os.close(fd)
    img.save(path, "JPEG", quality=92)
    
    return path


# ══════════════════════════════════════════════════════════════════════════════
#  توليد صورة باستخدام AI (اختياري)
# ══════════════════════════════════════════════════════════════════════════════
async def generate_ai_image(prompt: str) -> bytes | None:
    """توليد صورة باستخدام Pollinations.ai."""
    import urllib.parse
    
    seed = random.randint(1, 99999)
    encoded = urllib.parse.quote(prompt[:300])
    url = f"https://image.pollinations.ai/prompt/{encoded}?width=854&height=480&seed={seed}&model=flux&nologo=true"
    
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(url, timeout=20) as r:
                if r.status == 200:
                    data = await r.read()
                    if len(data) > 5000:
                        return data
    except:
        pass
    
    return None
