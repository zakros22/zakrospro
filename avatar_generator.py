import sys
import io
import os
import random
from PIL import Image, ImageDraw, ImageFont

# أبعاد الأفاتار
AVATAR_W, AVATAR_H = 600, 600

# مجلد الخطوط
_FONTS_DIR = os.path.join(os.path.dirname(__file__), "fonts")
FONT_PATH = os.path.join(_FONTS_DIR, "Amiri-Bold.ttf")

# ============================================================
# بيانات الشخصيات حسب التخصص
# ============================================================

# 1. الألوان الرئيسية حسب التخصص
SUBJECT_COLORS = {
    # الطب
    "medicine": (21, 128, 61),
    "surgery": (185, 28, 28),
    "pediatrics": (255, 159, 67),
    "dentistry": (13, 71, 161),
    "pharmacy": (46, 125, 50),
    "cardiology": (220, 20, 60),
    "neurology": (75, 0, 130),
    # الهندسة
    "engineering": (230, 126, 34),
    "civil": (121, 85, 72),
    "electrical": (255, 193, 7),
    "mechanical": (96, 125, 139),
    "aerospace": (33, 33, 33),
    "software": (41, 98, 255),
    "chemical": (0, 150, 136),
    # العلوم
    "science": (46, 204, 113),
    "physics": (155, 89, 182),
    "chemistry": (231, 76, 60),
    "biology": (241, 196, 15),
    "astronomy": (26, 35, 126),
    "mathematics": (52, 73, 94),
    # العلوم الإنسانية
    "literature": (192, 57, 43),
    "history": (230, 126, 34),
    "geography": (39, 174, 96),
    "philosophy": (93, 64, 55),
    "psychology": (156, 39, 176),
    "economics": (0, 150, 136),
    "law": (139, 0, 0),
    # العلوم الإسلامية
    "islamic": (21, 101, 192),
    "quran": (46, 134, 222),
    "hadith": (41, 128, 185),
    "fiqh": (142, 68, 173),
    "aqeedah": (2, 119, 189),
    "tafseer": (26, 83, 92),
    "seerah": (183, 28, 28),
    # المراحل الدراسية
    "primary": (255, 107, 107),
    "middle": (78, 205, 196),
    "high": (255, 209, 102),
    "university": (52, 73, 94),
    # افتراضي
    "other": (100, 116, 139)
}

# 2. الإكسسوارات حسب التخصص
ACCESSORIES = {
    "medicine": {"head": "🩺", "glasses": "👓", "chest": "🫀", "tool": "💊"},
    "surgery": {"head": "⛑️", "glasses": "🥽", "chest": "🔪", "tool": "🏥"},
    "pediatrics": {"head": "🧸", "glasses": "👓", "chest": "🍼", "tool": "👶"},
    "dentistry": {"head": "🦷", "glasses": "👓", "chest": "🪥", "tool": "🔧"},
    "pharmacy": {"head": "💊", "glasses": "👓", "chest": "🧪", "tool": "⚗️"},
    "engineering": {"head": "⛑️", "glasses": "👷", "chest": "📐", "tool": "🔧"},
    "civil": {"head": "🏗️", "glasses": "👷", "chest": "🧱", "tool": "📏"},
    "electrical": {"head": "⚡", "glasses": "👓", "chest": "🔌", "tool": "💡"},
    "mechanical": {"head": "⚙️", "glasses": "👓", "chest": "🔧", "tool": "🏭"},
    "aerospace": {"head": "🚀", "glasses": "🕶️", "chest": "🛸", "tool": "🌍"},
    "software": {"head": "💻", "glasses": "🤓", "chest": "{ }", "tool": "⌨️"},
    "science": {"head": "🔬", "glasses": "🥽", "chest": "🧪", "tool": "🧬"},
    "physics": {"head": "⚛️", "glasses": "👓", "chest": "📊", "tool": "🔭"},
    "chemistry": {"head": "🧪", "glasses": "🥽", "chest": "⚗️", "tool": "🔥"},
    "biology": {"head": "🧬", "glasses": "👓", "chest": "🔬", "tool": "🌿"},
    "math": {"head": "📐", "glasses": "🤓", "chest": "📈", "tool": "🧮"},
    "literature": {"head": "📖", "glasses": "👓", "chest": "🖋️", "tool": "📜"},
    "history": {"head": "🏛️", "glasses": "👓", "chest": "📜", "tool": "🗿"},
    "geography": {"head": "🌍", "glasses": "👓", "chest": "🗺️", "tool": "🧭"},
    "islamic": {"head": "🕌", "glasses": "👓", "chest": "📿", "tool": "📖"},
    "quran": {"head": "📖", "glasses": "👓", "chest": "🌟", "tool": "🕋"},
    "hadith": {"head": "📜", "glasses": "👓", "chest": "🕌", "tool": "📚"},
    "fiqh": {"head": "⚖️", "glasses": "👓", "chest": "📚", "tool": "🕋"},
    "primary": {"head": "🎒", "glasses": "👓", "chest": "✏️", "tool": "📓"},
    "middle": {"head": "📚", "glasses": "👓", "chest": "📝", "tool": "🔬"},
    "high": {"head": "🎓", "glasses": "👓", "chest": "📖", "tool": "💡"},
    "other": {"head": "👤", "glasses": "👓", "chest": "📚", "tool": "📖"}
}

# 3. ألوان البشرة
SKIN_TONES = [
    (255, 219, 172),  # فاتح
    (241, 194, 125),  # قمحي
    (224, 172, 105),  # حنطي
    (198, 134, 66),   # أسمر
]

# 4. قصات الشعر
HAIR_STYLES = {
    "male_short": {"color": (61, 43, 31), "style": "short"},
    "male_medium": {"color": (80, 60, 45), "style": "medium"},
    "female_long": {"color": (51, 34, 24), "style": "long"},
    "hijab": {"color": (21, 101, 192), "style": "hijab"},
    "scholar": {"color": (80, 80, 80), "style": "scholar"},
    "young": {"color": (120, 80, 50), "style": "young"},
}


def _get_font(size):
    try:
        return ImageFont.truetype(FONT_PATH, size)
    except:
        return ImageFont.load_default()


def generate_avatar(subject: str, gender: str = "male", age_group: str = "adult") -> bytes:
    """
    رسم شخصية كرتونية (أفاتار) حسب التخصص والجنس والعمر.
    
    Args:
        subject: نوع المادة (medicine, engineering, etc.)
        gender: الجنس (male, female)
        age_group: الفئة العمرية (child, young, adult, senior)
    
    Returns:
        bytes: صورة PNG للشخصية
    """
    # تحديد اللون الرئيسي
    color = SUBJECT_COLORS.get(subject, SUBJECT_COLORS["other"])
    skin = random.choice(SKIN_TONES)
    
    # تحديد الإكسسوارات
    acc = ACCESSORIES.get(subject, ACCESSORIES["other"])
    
    # تحديد الشعر
    if subject in ["islamic", "quran", "hadith", "fiqh", "aqeedah", "tafseer"]:
        hair = HAIR_STYLES["scholar"] if gender == "male" else HAIR_STYLES["hijab"]
    elif age_group == "child" or subject == "primary":
        hair = HAIR_STYLES["young"]
    elif gender == "female":
        hair = HAIR_STYLES["female_long"]
    else:
        hair = HAIR_STYLES["male_short"]
    
    # إنشاء لوحة الرسم
    img = Image.new("RGBA", (AVATAR_W, AVATAR_H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # ============================================================
    # 1. رسم دائرة الوجه
    # ============================================================
    face_cx, face_cy = AVATAR_W // 2, AVATAR_H // 2 - 20
    face_r = 120
    
    # ظل خفيف للوجه
    draw.ellipse([face_cx - face_r + 3, face_cy - face_r + 3, 
                  face_cx + face_r + 3, face_cy + face_r + 3], 
                 fill=(0, 0, 0, 50))
    # الوجه
    draw.ellipse([face_cx - face_r, face_cy - face_r, 
                  face_cx + face_r, face_cy + face_r], 
                 fill=skin, outline=(0, 0, 0, 80), width=2)
    
    # ============================================================
    # 2. رسم العيون (بأسلوب كرتوني لطيف)
    # ============================================================
    eye_y = face_cy - 20
    
    # العين اليسرى
    draw.ellipse([face_cx - 65, eye_y - 18, face_cx - 25, eye_y + 18], 
                 fill="white", outline=(0, 0, 0, 100), width=2)
    # القزحية
    iris_color = (46, 134, 222) if random.random() > 0.3 else (100, 70, 30)
    draw.ellipse([face_cx - 55, eye_y - 8, face_cx - 35, eye_y + 8], fill=iris_color)
    # البؤبؤ
    draw.ellipse([face_cx - 50, eye_y - 4, face_cx - 40, eye_y + 4], fill="black")
    # لمعان العين
    draw.ellipse([face_cx - 48, eye_y - 6, face_cx - 44, eye_y - 2], fill="white")
    
    # العين اليمنى
    draw.ellipse([face_cx + 25, eye_y - 18, face_cx + 65, eye_y + 18], 
                 fill="white", outline=(0, 0, 0, 100), width=2)
    draw.ellipse([face_cx + 35, eye_y - 8, face_cx + 55, eye_y + 8], fill=iris_color)
    draw.ellipse([face_cx + 40, eye_y - 4, face_cx + 50, eye_y + 4], fill="black")
    draw.ellipse([face_cx + 42, eye_y - 6, face_cx + 46, eye_y - 2], fill="white")
    
    # الحواجب
    eyebrow_y = eye_y - 25
    draw.arc([face_cx - 70, eyebrow_y - 5, face_cx - 20, eyebrow_y + 10], 
             start=0, end=180, fill=(80, 60, 50), width=3)
    draw.arc([face_cx + 20, eyebrow_y - 5, face_cx + 70, eyebrow_y + 10], 
             start=0, end=180, fill=(80, 60, 50), width=3)
    
    # ============================================================
    # 3. رسم النظارات (إذا كان التخصص يتطلب)
    # ============================================================
    if "glasses" in acc:
        # إطار النظارة
        glass_color = (50, 50, 60)
        draw.rounded_rectangle([face_cx - 75, eye_y - 22, face_cx - 15, eye_y + 22], 
                               radius=12, outline=glass_color, width=4)
        draw.rounded_rectangle([face_cx + 15, eye_y - 22, face_cx + 75, eye_y + 22], 
                               radius=12, outline=glass_color, width=4)
        # جسر النظارة
        draw.line([face_cx - 15, eye_y, face_cx + 15, eye_y], fill=glass_color, width=4)
        # أذرع النظارة
        draw.line([face_cx - 75, eye_y - 5, face_cx - 100, eye_y - 20], fill=glass_color, width=3)
        draw.line([face_cx + 75, eye_y - 5, face_cx + 100, eye_y - 20], fill=glass_color, width=3)
    
    # ============================================================
    # 4. رسم الأنف والفم
    # ============================================================
    nose_y = face_cy + 15
    draw.ellipse([face_cx - 8, nose_y - 5, face_cx + 8, nose_y + 10], 
                 fill=(skin[0]-20, skin[1]-20, skin[2]-20, 100), outline=None)
    
    mouth_y = face_cy + 45
    # ابتسامة
    draw.arc([face_cx - 35, mouth_y - 15, face_cx + 35, mouth_y + 25], 
             start=0, end=180, fill=(200, 80, 80), width=4)
    # خدود وردية
    cheek_color = (255, 150, 150, 60)
    draw.ellipse([face_cx - 80, face_cy + 20, face_cx - 40, face_cy + 50], fill=cheek_color)
    draw.ellipse([face_cx + 40, face_cy + 20, face_cx + 80, face_cy + 50], fill=cheek_color)
    
    # ============================================================
    # 5. رسم الشعر / الحجاب
    # ============================================================
    if hair["style"] == "hijab":
        # حجاب إسلامي
        hijab_color = color
        hijab_points = [
            (face_cx - 150, face_cy - 80),
            (face_cx - 90, face_cy - 150),
            (face_cx, face_cy - 160),
            (face_cx + 90, face_cy - 150),
            (face_cx + 150, face_cy - 80),
            (face_cx + 130, face_cy + 20),
            (face_cx + 100, face_cy + 110),
            (face_cx - 100, face_cy + 110),
            (face_cx - 130, face_cy + 20),
        ]
        draw.polygon(hijab_points, fill=hijab_color)
        # تفاصيل الحجاب
        draw.line([(face_cx, face_cy - 150), (face_cx, face_cy + 100)], fill=(0,0,0,30), width=2)
    elif hair["style"] == "scholar":
        # عمامة أو طاقية
        scholar_points = [
            (face_cx - 130, face_cy - 70),
            (face_cx - 70, face_cy - 130),
            (face_cx, face_cy - 140),
            (face_cx + 70, face_cy - 130),
            (face_cx + 130, face_cy - 70),
            (face_cx + 120, face_cy + 10),
            (face_cx - 120, face_cy + 10),
        ]
        draw.polygon(scholar_points, fill=hair["color"])
        # لحية للشخصية العلمائية
        beard_points = [
            (face_cx - 60, face_cy + 60),
            (face_cx - 40, face_cy + 100),
            (face_cx, face_cy + 110),
            (face_cx + 40, face_cy + 100),
            (face_cx + 60, face_cy + 60),
        ]
        draw.polygon(beard_points, fill=(100, 100, 100, 150))
    else:
        # شعر عادي
        hair_points = [
            (face_cx - 140, face_cy - 60),
            (face_cx - 70, face_cy - 150),
            (face_cx, face_cy - 160),
            (face_cx + 70, face_cy - 150),
            (face_cx + 140, face_cy - 60),
            (face_cx + 130, face_cy),
            (face_cx - 130, face_cy),
        ]
        draw.polygon(hair_points, fill=hair["color"])
        
        # خصلات شعر إضافية
        if hair["style"] == "long":
            draw.rectangle([face_cx - 130, face_cy, face_cx - 100, face_cy + 120], fill=hair["color"])
            draw.rectangle([face_cx + 100, face_cy, face_cx + 130, face_cy + 120], fill=hair["color"])
    
    # ============================================================
    # 6. رسم الزي (الملابس)
    # ============================================================
    body_top = face_cy + 100
    body_points = [
        (face_cx - 150, body_top),
        (face_cx + 150, body_top),
        (face_cx + 190, AVATAR_H),
        (face_cx - 190, AVATAR_H),
    ]
    draw.polygon(body_points, fill=color)
    
    # ياقة القميص
    collar_color = (255, 255, 255)
    collar_points = [
        (face_cx - 50, body_top),
        (face_cx, body_top + 40),
        (face_cx + 50, body_top),
    ]
    draw.polygon(collar_points, fill=collar_color)
    
    # ربطة عنق أو شعار
    if subject in ["medicine", "surgery", "pediatrics"]:
        # ربطة عنق طبية
        tie_points = [
            (face_cx - 15, body_top + 10),
            (face_cx, body_top + 60),
            (face_cx + 15, body_top + 10),
        ]
        draw.polygon(tie_points, fill=(185, 28, 28))
    elif subject in ["engineering", "software"]:
        # ربطة عنق هندسية
        tie_points = [
            (face_cx - 15, body_top + 10),
            (face_cx, body_top + 60),
            (face_cx + 15, body_top + 10),
        ]
        draw.polygon(tie_points, fill=(41, 98, 255))
    
    # ============================================================
    # 7. إضافة شعار التخصص على الصدر
    # ============================================================
    chest_icon = acc.get("chest", "📚")
    font = _get_font(48)
    try:
        draw.text((face_cx - 30, body_top + 60), chest_icon, fill="white", font=font, embedded_color=True)
    except:
        draw.text((face_cx - 30, body_top + 60), chest_icon, fill="white", font=font)
    
    # ============================================================
    # 8. إضافة أداة التخصص في اليد
    # ============================================================
    tool_icon = acc.get("tool", "📖")
    font_small = _get_font(36)
    try:
        draw.text((face_cx - 120, body_top + 100), tool_icon, fill="white", font=font_small, embedded_color=True)
    except:
        draw.text((face_cx - 120, body_top + 100), tool_icon, fill="white", font=font_small)
    
    # ============================================================
    # 9. إضافة لمسة نهائية - ظل تحت الشخصية
    # ============================================================
    shadow_ellipse = [
        (face_cx - 100, AVATAR_H - 30),
        (face_cx + 100, AVATAR_H - 10),
    ]
    draw.ellipse(shadow_ellipse, fill=(0, 0, 0, 40))
    
    # ============================================================
    # حفظ الصورة
    # ============================================================
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def get_avatar_for_subject(subject: str) -> bytes:
    """
    دالة مساعدة لتوليد أفاتار حسب التخصص مع اختيارات افتراضية مناسبة.
    """
    # تحديد الجنس والعمر حسب التخصص
    if subject in ["pediatrics", "primary"]:
        gender, age = "female", "young"
    elif subject in ["surgery", "engineering", "aerospace"]:
        gender, age = "male", "adult"
    elif subject in ["islamic", "quran", "hadith", "fiqh"]:
        gender, age = "male", "senior"
    elif subject in ["literature", "psychology"]:
        gender, age = "female", "adult"
    elif subject in ["history", "philosophy"]:
        gender, age = "male", "senior"
    else:
        gender, age = "male", "adult"
    
    return generate_avatar(subject, gender, age)
