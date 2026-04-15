"""
ملف منفصل لتوليد الصور التعليمية
يدعم طرق متعددة مجانية ومدفوعة مع تدوير المفاتيح
"""

import asyncio
import io
import aiohttp
import random
import base64
import os
from PIL import Image as PILImage, ImageDraw, ImageFont
from config import STABILITY_API_KEYS, REPLICATE_API_TOKEN

# ══════════════════════════════════════════════════════════════════════════════
# 🔑 تدوير مفاتيح Stability AI
# ══════════════════════════════════════════════════════════════════════════════
_stability_pool = list(STABILITY_API_KEYS) if STABILITY_API_KEYS else []
_stability_idx = 0
_stability_exhausted = set()


# ══════════════════════════════════════════════════════════════════════════════
# 1️⃣ Pollinations.ai - مجاني بالكامل
# ══════════════════════════════════════════════════════════════════════════════
async def generate_pollinations(prompt: str, width: int = 854, height: int = 480) -> bytes | None:
    import urllib.parse
    
    clean_prompt = prompt[:380].replace("\n", " ").strip()
    if not clean_prompt:
        clean_prompt = "educational illustration"
    
    seed = random.randint(1, 99999)
    encoded = urllib.parse.quote(clean_prompt)
    models = ["flux", "flux-anime", "flux-realism"]
    
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
    global _stability_idx, _stability_exhausted
    
    if not _stability_pool:
        return None
    
    clean_prompt = f"educational cartoon illustration, clean simple style, {prompt[:300]}"
    
    for _ in range(len(_stability_pool)):
        key_idx = _stability_idx % len(_stability_pool)
        key = _stability_pool[key_idx]
        _stability_idx += 1
        
        if key in _stability_exhausted:
            continue
        
        try:
            headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
            payload = {
                "text_prompts": [{"text": clean_prompt}],
                "cfg_scale": 7, "height": height, "width": width,
                "samples": 1, "steps": 30,
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
# 3️⃣ Replicate - Flux Schnell
# ══════════════════════════════════════════════════════════════════════════════
async def generate_replicate(prompt: str, width: int = 896, height: int = 512) -> bytes | None:
    if not REPLICATE_API_TOKEN:
        return None
    
    clean_prompt = f"educational cartoon illustration, clean simple style, {prompt[:300]}"
    
    try:
        headers = {"Authorization": f"Token {REPLICATE_API_TOKEN}", "Content-Type": "application/json"}
        payload = {
            "version": "black-forest-labs/flux-schnell",
            "input": {"prompt": clean_prompt, "width": width, "height": height, "num_outputs": 1}
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
                                        print(f"✅ Replicate success")
                                        return buf.getvalue()
                            break
                        elif result.get("status") in ("failed", "canceled"):
                            break
    except Exception as e:
        print(f"⚠️ Replicate error: {e}")
    return None


# ══════════════════════════════════════════════════════════════════════════════
# 4️⃣ صورة احتياطية
# ══════════════════════════════════════════════════════════════════════════════
def generate_placeholder(keyword: str, lecture_type: str = "other", width: int = 854, height: int = 480) -> bytes:
    PALETTES = {
        "medicine": {"bg1": (20, 78, 140), "bg2": (6, 147, 227), "accent": (255, 200, 0)},
        "science": {"bg1": (11, 110, 79), "bg2": (28, 200, 135), "accent": (255, 220, 50)},
        "math": {"bg1": (58, 12, 163), "bg2": (100, 60, 220), "accent": (255, 180, 0)},
        "literature": {"bg1": (100, 30, 120), "bg2": (180, 60, 200), "accent": (255, 200, 100)},
        "history": {"bg1": (150, 60, 10), "bg2": (220, 110, 40), "accent": (255, 230, 100)},
        "computer": {"bg1": (0, 80, 120), "bg2": (0, 160, 200), "accent": (255, 200, 50)},
        "business": {"bg1": (0, 80, 40), "bg2": (0, 160, 80), "accent": (255, 220, 0)},
        "other": {"bg1": (30, 30, 80), "bg2": (70, 60, 160), "accent": (255, 200, 50)},
    }
    colors = PALETTES.get(lecture_type, PALETTES["other"])
    bg1, bg2, accent = colors["bg1"], colors["bg2"], colors["accent"]
    
    img = PILImage.new("RGB", (width, height), bg1)
    draw = ImageDraw.Draw(img)
    
    for y in range(height):
        t = y / height
        r = int(bg1[0] * (1 - t) + bg2[0] * t)
        g = int(bg1[1] * (1 - t) + bg2[1] * t)
        b = int(bg1[2] * (1 - t) + bg2[2] * t)
        draw.line([(0, y), (width, y)], fill=(r, g, b))
    
    draw.ellipse([-60, -60, 200, 200], fill=accent + (40,))
    draw.ellipse([width - 140, height - 140, width + 60, height + 60], fill=accent + (30,))
    
    try:
        font_path = os.path.join(os.path.dirname(__file__), "fonts", "Amiri-Bold.ttf")
        if os.path.exists(font_path):
            font = ImageFont.truetype(font_path, 42)
        else:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 42)
    except:
        font = ImageFont.load_default()
    
    display_text = keyword[:30].strip() or "Educational Content"
    
    try:
        bbox = draw.textbbox((0, 0), display_text, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    except:
        tw, th = len(display_text) * 20, 50
    
    x, y = (width - tw) // 2, (height - th) // 2
    draw.text((x + 3, y + 3), display_text, fill=(0, 0, 0, 100), font=font)
    draw.text((x, y), display_text, fill=(255, 255, 255), font=font)
    draw.rectangle([width//2 - 100, y + th + 10, width//2 + 100, y + th + 16], fill=accent)
    
    try:
        small_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 12)
        draw.text((width - 130, height - 22), "@zakros_probot", fill=(180, 180, 200), font=small_font)
    except:
        pass
    
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=90)
    return buf.getvalue()


# ══════════════════════════════════════════════════════════════════════════════
# 🎨 الدالة الرئيسية
# ══════════════════════════════════════════════════════════════════════════════
async def generate_educational_image(
    prompt: str,
    lecture_type: str = "other",
    keyword: str = "",
    section_title: str = "",
) -> bytes:
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
    
    # 4️⃣ Placeholder
    print("🔄 Using placeholder image")
    return generate_placeholder(keyword or section_title or prompt[:30], lecture_type)


# ══════════════════════════════════════════════════════════════════════════════
# دالة متوافقة مع ai_analyzer
# ══════════════════════════════════════════════════════════════════════════════
async def fetch_image_for_keyword(
    keyword: str,
    section_title: str,
    lecture_type: str,
    image_search_en: str = "",
) -> bytes:
    prompt = image_search_en or keyword
    full_prompt = f"educational cartoon illustration, simple clean style, {prompt}, {lecture_type}"
    return await generate_educational_image(
        prompt=full_prompt,
        lecture_type=lecture_type,
        keyword=keyword,
        section_title=section_title,
    )


def get_image_keys_status() -> dict:
    return {
        "stability": {
            "total": len(_stability_pool),
            "active": len(_stability_pool) - len(_stability_exhausted),
        },
        "replicate": {"available": bool(REPLICATE_API_TOKEN)},
        "pollinations": {"available": True},
    }
