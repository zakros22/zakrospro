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
# بيانات الملابس والإكسسوارات حسب التخصص
# ============================================================

# 1. الألوان الرئيسية للزي حسب التخصص
SUBJECT_COLORS = {
    "medicine": (21, 128, 61),      # أخضر طبي
    "surgery": (185, 28, 28),       # أحمر جراحة
    "pediatrics": (255, 159, 67),   # برتقالي أطفال
    "dentistry": (13, 71, 161),     # أزرق أسنان
    "pharmacy": (46, 125, 50),      # أخضر صيدلة
    "engineering": (230, 126, 34),  # برتقالي هندسي
    "civil": (121, 85, 72),         # بني مدني
    "electrical": (255, 193, 7),    # أصفر كهرباء
    "mechanical": (96, 125, 139),   # رمادي ميكانيك
    "aerospace": (33, 33, 33),      # أسود فضاء
    "software": (41, 98, 255),      # أزرق برمجة
    "science": (46, 204, 113),      # أخضر علمي
    "physics": (155, 89, 182),      # بنفسجي فيزياء
    "chemistry": (231, 76, 60),     # أحمر كيمياء
    "biology": (241, 196, 15),      # أصفر أحياء
    "math": (52, 73, 94),           # كحلي رياضيات
    "literature": (192, 57, 43),    # أحمر أدب
    "history": (230, 126, 34),      # برتقالي تاريخ
    "geography": (39, 174, 96),     # أخضر جغرافيا
    "islamic": (21, 101, 192),      # أزرق إسلامي
    "quran": (46, 134, 222),        # أزرق فاتح قرآن
    "hadith": (41, 128, 185),       # أزرق حديث
    "fiqh": (142, 68, 173),         # بنفسجي فقه
    "primary": (255, 107, 107),     # أحمر فاتح ابتدائي
    "middle": (78, 205, 196),       # فيروزي متوسط
    "high": (255, 209, 102),        # أصفر إعدادي
    "default": (100, 116, 139)      # رمادي افتراضي
}

# 2. الإكسسوارات حسب التخصص
ACCESSORIES = {
    "medicine": {"head": "🩺", "glasses": "👓", "chest": "🫀"},
    "surgery": {"head": "⛑️", "glasses": "🥽", "chest": "🔪"},
    "dentistry": {"head": "🦷", "glasses": "👓", "chest": "🪥"},
    "engineering": {"head": "⛑️", "glasses": "👷", "chest": "📐"},
    "civil": {"head": "🏗️", "glasses": "👷", "chest": "🧱"},
    "electrical": {"head": "⚡", "glasses": "👓", "chest": "🔌"},
    "software": {"head": "💻", "glasses": "🤓", "chest": "{ }"},
    "science": {"head": "🔬", "glasses": "🥽", "chest": "🧪"},
    "physics": {"head": "⚛️", "glasses": "👓", "chest": "📊"},
    "chemistry": {"head": "🧪", "glasses": "🥽", "chest": "⚗️"},
    "math": {"head": "📐", "glasses": "🤓", "chest": "📈"},
    "literature": {"head": "📖", "glasses": "👓", "chest": "🖋️"},
    "history": {"head": "🏛️", "glasses": "👓", "chest": "📜"},
    "islamic": {"head": "🕌", "glasses": "👓", "chest": "📿"},
    "quran": {"head": "📖", "glasses": "👓", "chest": "🌟"},
    "primary": {"head": "🎒", "glasses": "👓", "chest": "✏️"},
    "middle": {"head": "📚", "glasses": "👓", "chest": "📝"},
    "high": {"head": "🎓", "glasses": "👓", "chest": "📖"},
    "default": {"head": "👤", "glasses": "👓", "chest": "📚"}
}

# 3. شكل الوجه الأساسي (ثابت لكن نغير لون البشرة أحياناً)
SKIN_TONES = [(255, 219, 172), (241, 194, 125), (224, 172, 105), (198, 134, 66)]

# 4. قصات الشعر حسب النوع (نستخدم شعر افتراضي)
HAIR_STYLES = ["short", "medium", "long", "hijab"]  # hijab للمحاضرات الإسلامية

def _get_font(size):
    try:
        return ImageFont.truetype(FONT_PATH, size)
    except:
        return ImageFont.load_default()

def generate_avatar(subject: str, gender: str = "male", age_group: str = "adult") -> bytes:
    """
    رسم شخصية كرتونية (أفاتار) حسب التخصص.
    """
    # تحديد اللون الرئيسي
    color = SUBJECT_COLORS.get(subject, SUBJECT_COLORS["default"])
    skin = random.choice(SKIN_TONES)
    
    # إنشاء لوحة الرسم
    img = Image.new("RGBA", (AVATAR_W, AVATAR_H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # 1. رسم دائرة الوجه
    face_cx, face_cy = AVATAR_W // 2, AVATAR_H // 2 - 20
    face_r = 120
    draw.ellipse([face_cx - face_r, face_cy - face_r, face_cx + face_r, face_cy + face_r], fill=skin, outline=(0,0,0,50), width=2)
    
    # 2. رسم العيون (بأسلوب كرتوني)
    eye_y = face_cy - 20
    # العين اليسرى
    draw.ellipse([face_cx - 60, eye_y - 15, face_cx - 30, eye_y + 15], fill="white", outline="black", width=2)
    draw.ellipse([face_cx - 50, eye_y - 5, face_cx - 40, eye_y + 5], fill=(46, 134, 222)) # لون العين
    draw.ellipse([face_cx - 47, eye_y - 3, face_cx - 43, eye_y + 1], fill="black") # بؤبؤ
    # العين اليمنى
    draw.ellipse([face_cx + 30, eye_y - 15, face_cx + 60, eye_y + 15], fill="white", outline="black", width=2)
    draw.ellipse([face_cx + 40, eye_y - 5, face_cx + 50, eye_y + 5], fill=(46, 134, 222))
    draw.ellipse([face_cx + 43, eye_y - 3, face_cx + 47, eye_y + 1], fill="black")
    
    # 3. رسم النظارات (إذا كان التخصص يتطلب)
    acc = ACCESSORIES.get(subject, ACCESSORIES["default"])
    if "glasses" in acc:
        # إطار النظارة
        draw.rounded_rectangle([face_cx - 70, eye_y - 20, face_cx - 20, eye_y + 20], radius=10, outline=color, width=4)
        draw.rounded_rectangle([face_cx + 20, eye_y - 20, face_cx + 70, eye_y + 20], radius=10, outline=color, width=4)
        draw.line([face_cx - 20, eye_y, face_cx + 20, eye_y], fill=color, width=4)
    
    # 4. رسم الفم (ابتسامة)
    mouth_y = face_cy + 40
    draw.arc([face_cx - 30, mouth_y - 10, face_cx + 30, mouth_y + 20], start=0, end=180, fill="black", width=3)
    
    # 5. رسم الشعر / الحجاب
    if subject in ["islamic", "quran", "hadith", "fiqh"] or gender == "female":
        # حجاب
        hijab_points = [
            (face_cx - 140, face_cy - 80),
            (face_cx - 80, face_cy - 140),
            (face_cx, face_cy - 150),
            (face_cx + 80, face_cy - 140),
            (face_cx + 140, face_cy - 80),
            (face_cx + 120, face_cy + 20),
            (face_cx + 90, face_cy + 100),
            (face_cx - 90, face_cy + 100),
            (face_cx - 120, face_cy + 20),
        ]
        draw.polygon(hijab_points, fill=color)
    else:
        # شعر عادي
        hair_points = [
            (face_cx - 130, face_cy - 60),
            (face_cx - 60, face_cy - 140),
            (face_cx, face_cy - 150),
            (face_cx + 60, face_cy - 140),
            (face_cx + 130, face_cy - 60),
            (face_cx + 120, face_cy),
            (face_cx - 120, face_cy),
        ]
        draw.polygon(hair_points, fill=(61, 43, 31)) # بني غامق
    
    # 6. رسم الزي (ملابس)
    body_top = face_cy + 100
    body_points = [
        (face_cx - 140, body_top),
        (face_cx + 140, body_top),
        (face_cx + 180, AVATAR_H),
        (face_cx - 180, AVATAR_H),
    ]
    draw.polygon(body_points, fill=color)
    
    # 7. ياقة القميص
    collar_points = [
        (face_cx - 40, body_top),
        (face_cx, body_top + 30),
        (face_cx + 40, body_top),
    ]
    draw.polygon(collar_points, fill="white")
    
    # 8. إضافة شعار التخصص على الصدر
    chest_icon = acc.get("chest", "📚")
    font = _get_font(48)
    draw.text((face_cx - 30, body_top + 50), chest_icon, fill="white", font=font, embedded_color=True)
    
    # 9. إضافة أداة التخصص في اليد
    head_icon = acc.get("head", "📖")
    font_small = _get_font(36)
    draw.text((face_cx - 100, body_top + 80), head_icon, fill="white", font=font_small, embedded_color=True)
    
    # حفظ الصورة
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()
