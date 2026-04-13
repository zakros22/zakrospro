# ai_analyzer.py - تعديل جزء الصور

import requests
from PIL import Image
from io import BytesIO
import uuid

def _fetch_pollinations_image_sync(keyword: str, specialty: str = None) -> Optional[Path]:
    """جلب صورة من Pollinations.ai (متزامن)"""
    try:
        if specialty:
            prompt = f"medical illustration of {keyword} for {specialty} education, clean professional style"
        else:
            prompt = f"medical illustration of {keyword}, educational diagram, clean style"
        
        url = f"https://image.pollinations.ai/prompt/{prompt.replace(' ', '%20')}"
        url += "?width=640&height=480&nologo=true"
        
        response = requests.get(url, timeout=30)
        if response.status_code == 200:
            img = Image.open(BytesIO(response.content))
            file_path = config.IMAGES_TMP / f"pollinations_{uuid.uuid4().hex[:8]}.png"
            img.save(file_path, "PNG")
            logger.info(f"✅ تم جلب صورة من Pollinations: {keyword}")
            return file_path
    except Exception as e:
        logger.debug(f"Pollinations فشل: {e}")
    return None

def _fetch_unsplash_image_sync(keyword: str) -> Optional[Path]:
    """جلب صورة من Unsplash (متزامن)"""
    if not config.UNSPLASH_ACCESS_KEY:
        return None
    try:
        headers = {"Authorization": f"Client-ID {config.UNSPLASH_ACCESS_KEY}"}
        params = {
            "query": f"{keyword} medical",
            "orientation": "landscape",
            "per_page": 1
        }
        response = requests.get("https://api.unsplash.com/search/photos",
                                headers=headers, params=params, timeout=20)
        if response.status_code == 200:
            data = response.json()
            if data["results"]:
                img_url = data["results"][0]["urls"]["regular"]
                img_response = requests.get(img_url, timeout=20)
                img = Image.open(BytesIO(img_response.content))
                img = img.resize((640, 480), Image.Resampling.LANCZOS)
                file_path = config.IMAGES_TMP / f"unsplash_{uuid.uuid4().hex[:8]}.jpg"
                img.save(file_path, "JPEG")
                logger.info(f"✅ تم جلب صورة من Unsplash: {keyword}")
                return file_path
    except Exception as e:
        logger.debug(f"Unsplash فشل: {e}")
    return None

def _fetch_picsum_image_sync() -> Optional[Path]:
    """جلب صورة عشوائية من Lorem Picsum (متزامن)"""
    try:
        response = requests.get("https://picsum.photos/640/480", timeout=15)
        if response.status_code == 200:
            img = Image.open(BytesIO(response.content))
            file_path = config.IMAGES_TMP / f"picsum_{uuid.uuid4().hex[:8]}.jpg"
            img.save(file_path, "JPEG")
            logger.info(f"✅ تم جلب صورة من Picsum")
            return file_path
    except Exception as e:
        logger.debug(f"Picsum فشل: {e}")
    return None

def fetch_image_for_keyword(keyword: str, specialty: str = None) -> Path:
    """
    الدالة الرئيسية لجلب صورة لقسم معين (متزامنة بالكامل).
    تجرب Pollinations -> Unsplash -> Picsum -> صورة مولدة.
    """
    # محاولة Pollinations
    img = _fetch_pollinations_image_sync(keyword, specialty)
    if img:
        return img

    # محاولة Unsplash
    img = _fetch_unsplash_image_sync(keyword)
    if img:
        return img

    # محاولة Picsum
    img = _fetch_picsum_image_sync()
    if img:
        return img

    # الصورة الاحتياطية
    return _make_medical_image(keyword, specialty)
