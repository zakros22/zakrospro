"""
ملف منفصل لتوليد الصور التعليمية الاحترافية
يدعم 6 طرق مختلفة + بدائل احترافية
"""

import asyncio
import io
import aiohttp
import random
import base64
import os
from PIL import Image as PILImage, ImageDraw, ImageFont, ImageFilter

# ══════════════════════════════════════════════════════════════════════════════
# استيراد المفاتيح
# ══════════════════════════════════════════════════════════════════════════════
try:
    from config import STABILITY_API_KEYS, REPLICATE_API_TOKEN
except ImportError:
    STABILITY_API_KEYS = []
    REPLICATE_API_TOKEN = ""

# ══════════════════════════════════════════════════════════════════════════════
# 🔑 KEY POOLS & ROTATION
# ══════════════════════════════════════════════════════════════════════════════
_stability_pool = list(STABILITY_API_KEYS) if STABILITY_API_KEYS else []
_stability_idx = 0
_stability_exhausted = set()


# ══════════════════════════════════════════════════════════════════════════════
# 1️⃣ Pollinations.ai - مجاني بالكامل
# ══════════════════════════════════════════════════════════════════════════════
async def generate_pollinations(prompt: str, width: int = 854, height: int = 480) -> bytes | None:
    """توليد صورة باستخدام Pollinations.ai - مجاني"""
    import urllib.parse
    
    clean_prompt = prompt[:380].replace("\n", " ").strip()
    if not clean_prompt:
        clean_prompt = "educational cartoon illustration"
    
    seed = random.randint(1, 99999)
    encoded = urllib.parse.quote(clean_prompt)
    models = ["flux", "flux-anime", "flux-realism", "turbo"]
    
    for model in models:
        try:
            url = f"https://image.pollinations.ai/prompt/{encoded}?width={width}&height={height}&nologo=true&seed={seed}&model={model}"
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                    if resp.status == 200:
                        raw = await resp.read()
                        if len(raw) > 5000:
                            pil_img = PILImage.open(io.BytesIO(raw)).convert("RGB")
                            pil_img = pil_img.resize((width, height), PILImage.LANCZOS)
                            buf = io.BytesIO()
                            pil_img.save(buf, "JPEG", quality=88)
                            print(f"✅ Pollinations success ({model})")
                            return buf.getvalue()
        except Exception as e:
            print(f"⚠️ Pollinations {model} error: {e}")
            continue
    return None


# ══════════════════════════════════════════════════════════════════════════════
# 2️⃣ Stability AI - جودة عالية
# ══════════════════════════════════════════════════════════════════════════════
async def generate_stability(prompt: str, width: int = 896, height: int = 512) -> bytes | None:
    """توليد صورة باستخدام Stability AI"""
    global _stability_idx, _stability_exhausted
    
    if not _stability_pool:
        return None
    
    clean_prompt = f"educational cartoon illustration, clean simple style, professional, {prompt[:300]}"
    
    available_keys = [k for k in _stability_pool if k not in _stability_exhausted]
    if not available_keys:
        return None
    
    for key in available_keys:
        try:
            headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
            payload = {
                "text_prompts": [{"text": clean_prompt}],
                "cfg_scale": 7,
                "height": height,
                "width": width,
                "samples": 1,
                "steps": 30,
            }
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://api.stability.ai/v1/generation/stable-diffusion-xl-1024-v1-0/text-to-image",
                    headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=35)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        b64 = data["artifacts"][0]["base64"]
                        raw = base64.b64decode(b64)
                        pil_img = PILImage.open(io.BytesIO(raw)).convert("RGB")
                        pil_img = pil_img.resize((854, 480), PILImage.LANCZOS)
                        buf = io.BytesIO()
                        pil_img.save(buf, "JPEG", quality=92)
                        print(f"✅ Stability AI success")
                        return buf.getvalue()
                    elif resp.status in (429, 403, 401):
                        _stability_exhausted.add(key)
                        continue
        except Exception as e:
            print(f"⚠️ Stability error: {e}")
            continue
    return None


# ══════════════════════════════════════════════════════════════════════════════
# 3️⃣ Replicate - Flux Schnell (جودة خرافية)
# ══════════════════════════════════════════════════════════════════════════════
async def generate_replicate(prompt: str, width: int = 896, height: int = 512) -> bytes | None:
    """توليد صورة باستخدام Replicate Flux"""
    if not REPLICATE_API_TOKEN:
        return None
    
    clean_prompt = f"educational cartoon illustration, professional clean style, {prompt[:300]}"
    
    try:
        headers = {"Authorization": f"Token {REPLICATE_API_TOKEN}", "Content-Type": "application/json"}
        payload = {
            "version": "black-forest-labs/flux-schnell",
            "input": {
                "prompt": clean_prompt,
                "width": width,
                "height": height,
                "num_outputs": 1,
                "num_inference_steps": 4,
            }
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.replicate.com/v1/predictions",
                headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                if resp.status != 201:
                    return None
                data = await resp.json()
                pred_id = data["id"]
                
                for _ in range(25):
                    await asyncio.sleep(3)
                    async with session.get(
                        f"https://api.replicate.com/v1/predictions/{pred_id}",
                        headers=headers, timeout=aiohttp.ClientTimeout(total=10)
                    ) as check:
                        if check.status != 200:
                            continue
                        result = await check.json()
                        if result.get("status") == "succeeded":
                            output = result.get("output")
                            if output and isinstance(output, list) and output[0]:
                                async with session.get(output[0], timeout=aiohttp.ClientTimeout(total=20)) as img_resp:
                                    if img_resp.status == 200:
                                        raw = await img_resp.read()
                                        pil_img = PILImage.open(io.BytesIO(raw)).convert("RGB")
                                        pil_img = pil_img.resize((854, 480), PILImage.LANCZOS)
                                        buf = io.BytesIO()
                                        pil_img.save(buf, "JPEG", quality=90)
                                        print(f"✅ Replicate Flux success")
                                        return buf.getvalue()
                        elif result.get("status") in ("failed", "canceled"):
                            break
    except Exception as e:
        print(f"⚠️ Replicate error: {e}")
    return None


# ══════════════════════════════════════════════════════════════════════════════
# 4️⃣ HuggingFace Inference - مجاني
# ══════════════════════════════════════════════════════════════════════════════
async def generate_huggingface(prompt: str) -> bytes | None:
    """توليد صورة باستخدام HuggingFace - مجاني"""
    try:
        headers = {"Content-Type": "application/json"}
        payload = {
            "inputs": f"educational cartoon, {prompt[:200]}",
            "parameters": {"width": 512, "height": 288}
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api-inference.huggingface.co/models/black-forest-labs/FLUX.1-dev",
                headers=headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=60),
            ) as resp:
                if resp.status == 200:
                    raw = await resp.read()
                    if len(raw) > 5000:
                        pil_img = PILImage.open(io.BytesIO(raw)).convert("RGB")
                        pil_img = pil_img.resize((854, 480), PILImage.LANCZOS)
                        buf = io.BytesIO()
                        pil_img.save(buf, "JPEG", quality=88)
                        print(f"✅ HuggingFace success")
                        return buf.getvalue()
    except Exception as e:
        print(f"⚠️ HuggingFace error: {e}")
    return None


# ══════════════════════════════════════════════════════════════════════════════
# 5️⃣ Prodia - مجاني (بدون مفتاح)
# ══════════════════════════════════════════════════════════════════════════════
async def generate_prodia(prompt: str) -> bytes | None:
    """توليد صورة باستخدام Prodia - مجاني"""
    try:
        headers = {
            "Content-Type": "application/json",
            "X-Prodia-Key": "free",  # مفتاح مجاني للتجربة
        }
        payload = {
            "prompt": f"educational cartoon, {prompt[:300]}",
            "model": "sd_xl_base_1.0.safetensors",
            "steps": 20,
            "width": 512,
            "height": 288,
        }
        async with aiohttp.ClientSession() as session:
            # إنشاء مهمة
            async with session.post(
                "https://api.prodia.com/v1/job",
                headers=headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                job_id = data.get("job")
                
                if not job_id:
                    return None
                
                # انتظار النتيجة
                for _ in range(20):
                    await asyncio.sleep(2)
                    async with session.get(
                        f"https://api.prodia.com/v1/job/{job_id}",
                        headers=headers,
                        timeout=aiohttp.ClientTimeout(total=10)
                    ) as check:
                        if check.status == 200:
                            result = await check.json()
                            if result.get("status") == "succeeded":
                                img_url = result.get("imageUrl")
                                if img_url:
                                    async with session.get(img_url) as img_resp:
                                        if img_resp.status == 200:
                                            raw = await img_resp.read()
                                            pil_img = PILImage.open(io.BytesIO(raw)).convert("RGB")
                                            pil_img = pil_img.resize((854, 480), PILImage.LANCZOS)
                                            buf = io.BytesIO()
                                            pil_img.save(buf, "JPEG", quality=88)
                                            print(f"✅ Prodia success")
                                            return buf.getvalue()
    except Exception as e:
        print(f"⚠️ Prodia error: {e}")
    return None


# ══════════════════════════════════════════════════════════════════════════════
# 6️⃣ DeepAI - مجاني
# ══════════════════════════════════════════════════════════════════════════════
async def generate_deepai(prompt: str) -> bytes | None:
    """توليد صورة باستخدام DeepAI - مجاني"""
    try:
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        data = {"text": f"educational cartoon illustration, {prompt[:200]}"}
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.deepai.org/api/text2img",
                headers=headers,
                data=data,
                timeout=aiohttp.ClientTimeout(total=40),
            ) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    img_url = result.get("output_url")
                    if img_url:
                        async with session.get(img_url) as img_resp:
                            if img_resp.status == 200:
                                raw = await img_resp.read()
                                pil_img = PILImage.open(io.BytesIO(raw)).convert("RGB")
                                pil_img = pil_img.resize((854, 480), PILImage.LANCZOS)
                                buf = io.BytesIO()
                                pil_img.save(buf, "JPEG", quality=88)
                                print(f"✅ DeepAI success")
                                return buf.getvalue()
    except Exception as e:
        print(f"⚠️ DeepAI error: {e}")
    return None


# ══════════════════════════════════════════════════════════════════════════════
# 7️⃣ صورة احترافية احتياطية (تصميم داخلي)
# ══════════════════════════════════════════════════════════════════════════════
def generate_professional_placeholder(
    keyword: str,
    lecture_type: str = "other",
    section_title: str = "",
    width: int = 854,
    height: int = 480
) -> bytes:
    """إنشاء صورة احترافية جداً كبديل"""
    
    # لوحة ألوان احترافية حسب نوع المحاضرة
    PALETTES = {
        "medicine": {
            "primary": (199, 30, 30),      # أحمر طبي
            "secondary": (20, 78, 140),     # أزرق غامق
            "accent": (255, 200, 0),        # ذهبي
            "bg_gradient": [(245, 248, 255), (230, 240, 255)]
        },
        "science": {
            "primary": (11, 110, 79),       # أخضر علمي
            "secondary": (28, 200, 135),    # أخضر فاتح
            "accent": (255, 220, 50),       # أصفر
            "bg_gradient": [(240, 255, 245), (220, 250, 230)]
        },
        "math": {
            "primary": (58, 12, 163),       # بنفسجي
            "secondary": (100, 60, 220),    # بنفسجي فاتح
            "accent": (255, 180, 0),        # برتقالي
            "bg_gradient": [(250, 245, 255), (240, 235, 255)]
        },
        "computer": {
            "primary": (0, 80, 120),        # أزرق تقني
            "secondary": (0, 160, 200),     # أزرق فاتح
            "accent": (100, 255, 150),      # أخضر نيون
            "bg_gradient": [(245, 250, 255), (235, 245, 255)]
        },
        "other": {
            "primary": (30, 30, 80),        # كحلي
            "secondary": (70, 60, 160),     # بنفسجي
            "accent": (255, 200, 50),       # ذهبي
            "bg_gradient": [(248, 249, 255), (238, 242, 255)]
        }
    }
    
    colors = PALETTES.get(lecture_type, PALETTES["other"])
    primary = colors["primary"]
    secondary = colors["secondary"]
    accent = colors["accent"]
    bg1, bg2 = colors["bg_gradient"]
    
    # إنشاء خلفية متدرجة
    img = PILImage.new("RGB", (width, height), bg1)
    draw = ImageDraw.Draw(img)
    
    # تدرج لوني ناعم
    for y in range(height):
        t = y / height
        r = int(bg1[0] * (1 - t) + bg2[0] * t)
        g = int(bg1[1] * (1 - t) + bg2[1] * t)
        b = int(bg1[2] * (1 - t) + bg2[2] * t)
        draw.line([(0, y), (width, y)], fill=(r, g, b))
    
    # إطار احترافي
    border_width = 6
    draw.rectangle(
        [(border_width, border_width), (width - border_width, height - border_width)],
        outline=primary,
        width=border_width
    )
    
    # إطار داخلي رفيع
    draw.rectangle(
        [(border_width + 8, border_width + 8), (width - border_width - 8, height - border_width - 8)],
        outline=secondary,
        width=2
    )
    
    # دوائر زخرفية في الزوايا
    circle_positions = [
        (30, 30, 80),                          # أعلى يسار
        (width - 80, 30, width - 30),          # أعلى يمين
        (30, height - 80, 80, height - 30),    # أسفل يسار
        (width - 80, height - 80, width - 30, height - 30),  # أسفل يمين
    ]
    for x1, y1, x2, y2 in circle_positions:
        draw.ellipse([x1, y1, x2, y2], fill=primary + (30,))
    
    # أيقونة تعليمية في المنتصف
    icon_size = 100
    icon_x = (width - icon_size) // 2
    icon_y = (height - icon_size) // 2 - 30
    
    # رسم أيقونة كتاب
    draw.rounded_rectangle(
        [icon_x, icon_y, icon_x + icon_size, icon_y + icon_size],
        radius=15,
        fill=secondary + (40,),
        outline=primary,
        width=3
    )
    
    # خطوط داخل الأيقونة (تمثل نص)
    line_y = icon_y + 30
    for i in range(4):
        draw.rounded_rectangle(
            [icon_x + 20, line_y, icon_x + icon_size - 20, line_y + 8],
            radius=4,
            fill=primary + (100,)
        )
        line_y += 18
    
    # تحميل الخط
    try:
        font_path = os.path.join(os.path.dirname(__file__), "fonts", "Amiri-Bold.ttf")
        if os.path.exists(font_path):
            font_bold = ImageFont.truetype(font_path, 36)
            font_regular = ImageFont.truetype(font_path, 20)
        else:
            font_bold = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 36)
            font_regular = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 20)
    except:
        font_bold = ImageFont.load_default()
        font_regular = font_bold
    
    # الكلمة المفتاحية الرئيسية
    display_text = keyword[:30].strip() or "Educational Content"
    
    # تقسيم النص إذا كان طويلاً
    words = display_text.split()
    if len(words) > 5:
        mid = len(words) // 2
        line1 = " ".join(words[:mid])
        line2 = " ".join(words[mid:])
    else:
        line1 = display_text
        line2 = ""
    
    # حساب أبعاد النص
    try:
        bbox = draw.textbbox((0, 0), line1, font=font_bold)
        tw1 = bbox[2] - bbox[0]
        th1 = bbox[3] - bbox[1]
    except:
        tw1 = len(line1) * 18
        th1 = 40
    
    # رسم النص الرئيسي
    text_y = icon_y + icon_size + 30
    text_x = (width - tw1) // 2
    
    # ظل للنص
    draw.text((text_x + 2, text_y + 2), line1, fill=(0, 0, 0, 100), font=font_bold)
    draw.text((text_x, text_y), line1, fill=primary, font=font_bold)
    
    # السطر الثاني
    if line2:
        try:
            bbox2 = draw.textbbox((0, 0), line2, font=font_bold)
            tw2 = bbox2[2] - bbox2[0]
        except:
            tw2 = len(line2) * 18
        text_x2 = (width - tw2) // 2
        draw.text((text_x2 + 2, text_y + th1 + 10), line2, fill=(0, 0, 0, 100), font=font_bold)
        draw.text((text_x2, text_y + th1 + 10), line2, fill=secondary, font=font_bold)
    
    # عنوان القسم (إذا وجد)
    if section_title:
        try:
            section_display = section_title[:40]
            bbox_s = draw.textbbox((0, 0), section_display, font=font_regular)
            tw_s = bbox_s[2] - bbox_s[0]
        except:
            tw_s = len(section_display) * 10
        
        text_x_s = (width - tw_s) // 2
        draw.text((text_x_s, 20), section_display, fill=secondary + (150,), font=font_regular)
    
    # شريط سفلي مع العلامة المائية
    footer_y = height - 35
    draw.rectangle([(0, footer_y), (width, footer_y + 2)], fill=accent)
    
    try:
        small_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 12)
    except:
        small_font = font_regular
    
    watermark = "@zakros_probot"
    try:
        bbox_w = draw.textbbox((0, 0), watermark, font=small_font)
        tw_w = bbox_w[2] - bbox_w[0]
    except:
        tw_w = len(watermark) * 7
    
    draw.text(((width - tw_w) // 2, footer_y + 8), watermark, fill=primary + (100,), font=small_font)
    
    # حفظ الصورة
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=95)
    return buf.getvalue()


# ══════════════════════════════════════════════════════════════════════════════
# 🎨 الدالة الرئيسية - تجربة 6 طرق
# ══════════════════════════════════════════════════════════════════════════════
async def generate_educational_image(
    prompt: str,
    lecture_type: str = "other",
    keyword: str = "",
    section_title: str = "",
) -> bytes:
    """
    الدالة الرئيسية لتوليد الصور التعليمية الاحترافية
    
    تجرب 6 طرق بالترتيب:
    1. Pollinations.ai (مجاني)
    2. Stability AI (مفاتيح)
    3. Replicate Flux (مفتاح)
    4. HuggingFace (مجاني)
    5. Prodia (مجاني)
    6. DeepAI (مجاني)
    7. صورة احترافية داخلية
    """
    clean_prompt = prompt.strip() or keyword or section_title or "educational illustration"
    print(f"🎨 Generating image for: {clean_prompt[:50]}...")
    
    # 1️⃣ Pollinations
    img = await generate_pollinations(clean_prompt)
    if img:
        return img
    
    # 2️⃣ Stability AI
    img = await generate_stability(clean_prompt)
    if img:
        return img
    
    # 3️⃣ Replicate
    img = await generate_replicate(clean_prompt)
    if img:
        return img
    
    # 4️⃣ HuggingFace
    img = await generate_huggingface(clean_prompt)
    if img:
        return img
    
    # 5️⃣ Prodia
    img = await generate_prodia(clean_prompt)
    if img:
        return img
    
    # 6️⃣ DeepAI
    img = await generate_deepai(clean_prompt)
    if img:
        return img
    
    # 7️⃣ صورة احترافية داخلية
    print("🔄 Using professional placeholder")
    return generate_professional_placeholder(keyword, lecture_type, section_title)


# ══════════════════════════════════════════════════════════════════════════════
# دالة متوافقة مع ai_analyzer
# ══════════════════════════════════════════════════════════════════════════════
async def fetch_image_for_keyword(
    keyword: str,
    section_title: str,
    lecture_type: str,
    image_search_en: str = "",
) -> bytes:
    """جلب صورة لكلمة مفتاحية"""
    prompt = image_search_en or keyword
    full_prompt = f"educational cartoon illustration, clean professional style, {prompt}, {lecture_type}"
    
    return await generate_educational_image(
        prompt=full_prompt,
        lecture_type=lecture_type,
        keyword=keyword,
        section_title=section_title,
    )


# ══════════════════════════════════════════════════════════════════════════════
# حالة المفاتيح
# ══════════════════════════════════════════════════════════════════════════════
def get_image_keys_status() -> dict:
    """إرجاع حالة خدمات الصور"""
    return {
        "stability": {
            "total": len(_stability_pool),
            "active": len(_stability_pool) - len(_stability_exhausted),
        },
        "replicate": {"available": bool(REPLICATE_API_TOKEN)},
        "pollinations": {"available": True},
        "huggingface": {"available": True},
        "prodia": {"available": True},
        "deepai": {"available": True},
    }
