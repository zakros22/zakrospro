import json
import re
import io
import asyncio
import aiohttp
import random
from PIL import Image as PILImage, ImageDraw, ImageFont

# ══════════════════════════════════════════════════════════════════════════════
# استيراد المفاتيح من config (إن وجدت)
# ══════════════════════════════════════════════════════════════════════════════
try:
    from config import (
        DEEPSEEK_API_KEYS, GOOGLE_API_KEYS, GROQ_API_KEYS, OPENROUTER_API_KEYS
    )
except ImportError:
    DEEPSEEK_API_KEYS = []
    GOOGLE_API_KEYS = []
    GROQ_API_KEYS = []
    OPENROUTER_API_KEYS = []

# استيراد Google Gemini
try:
    from google import genai
    from google.genai import types as genai_types
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    genai = None
    genai_types = None

# استيراد دوال الصور
try:
    from image_generator import fetch_image_for_keyword, generate_educational_image
except ImportError:
    fetch_image_for_keyword = None
    generate_educational_image = None


# ══════════════════════════════════════════════════════════════════════════════
# 🔑 KEY POOLS
# ══════════════════════════════════════════════════════════════════════════════
_deepseek_pool = list(DEEPSEEK_API_KEYS) if DEEPSEEK_API_KEYS else []
_deepseek_exhausted = set()

_gemini_pool = list(GOOGLE_API_KEYS) if GOOGLE_API_KEYS else []
_gemini_exhausted = set()
_gemini_clients = {}

_groq_pool = list(GROQ_API_KEYS) if GROQ_API_KEYS else []
_groq_exhausted = set()

_or_pool = list(OPENROUTER_API_KEYS) if OPENROUTER_API_KEYS else []
_or_exhausted = set()


class QuotaExhaustedError(Exception):
    pass


# ══════════════════════════════════════════════════════════════════════════════
# 📊 تحليل محلي احترافي (بدون API)
# ══════════════════════════════════════════════════════════════════════════════

# قوالب عناوين حسب نوع المحاضرة
SECTION_TEMPLATES = {
    "medicine": {
        "titles": ["مقدمة", "التشريح", "الفسيولوجيا", "الأمراض", "التشخيص", "العلاج", "الوقاية"],
        "keywords": ["طبي", "تشخيص", "علاج", "أعراض", "وقاية", "جراحة", "أدوية"],
    },
    "science": {
        "titles": ["مقدمة", "المبادئ الأساسية", "النظريات", "التجارب", "النتائج", "التطبيقات", "الاستنتاجات"],
        "keywords": ["علم", "نظرية", "تجربة", "نتيجة", "تحليل", "بحث", "اكتشاف"],
    },
    "math": {
        "titles": ["مقدمة", "التعريفات", "النظريات", "البراهين", "الأمثلة", "التطبيقات", "المسائل"],
        "keywords": ["رياضيات", "معادلة", "دالة", "متغير", "حساب", "هندسة", "جبر"],
    },
    "computer": {
        "titles": ["مقدمة", "المفاهيم", "الخوارزميات", "البرمجة", "قواعد البيانات", "الشبكات", "الأمن"],
        "keywords": ["برمجة", "خوارزمية", "بيانات", "شبكة", "أمن", "تطبيق", "نظام"],
    },
    "other": {
        "titles": ["مقدمة", "المفاهيم الأساسية", "التفاصيل", "الأمثلة", "التطبيقات", "الخلاصة"],
        "keywords": ["مفهوم", "تعريف", "مثال", "تطبيق", "تحليل", "نتيجة"],
    }
}


def _detect_lecture_type(text: str) -> str:
    """تحديد نوع المحاضرة من النص"""
    text_lower = text.lower()
    
    # كلمات مفتاحية لكل نوع
    medical_keywords = ["مرض", "علاج", "طبي", "جراحة", "دواء", "عرض", "تشخيص", "مستشفى", "قلب", "دم", "خلية"]
    science_keywords = ["تجربة", "نظرية", "علم", "فيزياء", "كيمياء", "أحياء", "ذرة", "جزيء", "مختبر"]
    math_keywords = ["معادلة", "رياضيات", "جبر", "هندسة", "حساب", "دالة", "متغير", "تكامل", "تفاضل"]
    computer_keywords = ["برمجة", "حاسوب", "خوارزمية", "بيانات", "شبكة", "برنامج", "كود", "تطبيق"]
    
    if any(kw in text_lower for kw in medical_keywords):
        return "medicine"
    elif any(kw in text_lower for kw in science_keywords):
        return "science"
    elif any(kw in text_lower for kw in math_keywords):
        return "math"
    elif any(kw in text_lower for kw in computer_keywords):
        return "computer"
    else:
        return "other"


def _split_text_into_sections(text: str, num_sections: int) -> list:
    """تقسيم النص إلى أقسام"""
    paragraphs = [p.strip() for p in text.split('\n') if p.strip() and len(p.strip()) > 50]
    
    if not paragraphs:
        # إذا ما في فقرات كافية، نقسم النص بالتساوي
        words = text.split()
        words_per_section = len(words) // num_sections
        sections = []
        for i in range(num_sections):
            start = i * words_per_section
            end = start + words_per_section if i < num_sections - 1 else len(words)
            sections.append(' '.join(words[start:end]))
        return sections
    
    # توزيع الفقرات على الأقسام
    if len(paragraphs) >= num_sections:
        paras_per_section = len(paragraphs) // num_sections
        sections = []
        for i in range(num_sections):
            start = i * paras_per_section
            end = start + paras_per_section if i < num_sections - 1 else len(paragraphs)
            sections.append('\n\n'.join(paragraphs[start:end]))
        return sections
    else:
        # توزيع الفقرات القليلة على الأقسام
        sections = []
        for i in range(num_sections):
            if i < len(paragraphs):
                sections.append(paragraphs[i])
            else:
                sections.append(paragraphs[-1] if paragraphs else "محتوى إضافي")
        return sections


def _extract_keywords_from_text(text: str, max_keywords: int = 4) -> list:
    """استخراج كلمات مفتاحية من النص"""
    # قائمة كلمات شائعة للتجاهل
    stop_words = {
        'في', 'من', 'على', 'إلى', 'عن', 'مع', 'كان', 'هذا', 'هذه', 'الذي', 'التي',
        'و', 'أو', 'ثم', 'حتى', 'كما', 'إذا', 'أن', 'إن', 'لم', 'لن', 'ما', 'لا',
        'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
        'of', 'with', 'by', 'from', 'as', 'is', 'are', 'was', 'were', 'be', 'been'
    }
    
    # استخراج الكلمات الطويلة (أكثر من 3 أحرف)
    words = re.findall(r'\b[\w\u0600-\u06FF]{4,}\b', text)
    
    # عد تكرار الكلمات
    word_count = {}
    for word in words:
        word_lower = word.lower()
        if word_lower not in stop_words:
            word_count[word_lower] = word_count.get(word_lower, 0) + 1
    
    # ترتيب الكلمات حسب التكرار
    sorted_words = sorted(word_count.items(), key=lambda x: x[1], reverse=True)
    
    # إرجاع الكلمات الأصلية (وليس lowercase)
    keywords = []
    for word_lower, _ in sorted_words[:max_keywords * 2]:
        # البحث عن الكلمة الأصلية
        for original in words:
            if original.lower() == word_lower and original not in keywords:
                keywords.append(original)
                break
        if len(keywords) >= max_keywords:
            break
    
    # إذا ما في كلمات كافية
    while len(keywords) < max_keywords:
        keywords.append(f"مصطلح {len(keywords) + 1}")
    
    return keywords[:max_keywords]


def _generate_summary(text: str, max_sentences: int = 5) -> str:
    """توليد ملخص من النص"""
    sentences = re.split(r'(?<=[.!?؟])\s+', text)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 20]
    
    if not sentences:
        return "ملخص المحاضرة"
    
    # اختيار جمل من بداية ووسط ونهاية النص
    summary_sentences = []
    if len(sentences) <= max_sentences:
        summary_sentences = sentences
    else:
        # الجملة الأولى
        summary_sentences.append(sentences[0])
        # جمل من الوسط
        mid = len(sentences) // 2
        for i in range(mid - 1, mid + 2):
            if i < len(sentences):
                summary_sentences.append(sentences[i])
        # الجملة الأخيرة
        if sentences[-1] not in summary_sentences:
            summary_sentences.append(sentences[-1])
    
    return ' '.join(summary_sentences[:max_sentences])


def _local_analyze_lecture(text: str, dialect: str, num_sections: int) -> dict:
    """تحليل محلي كامل للمحاضرة بدون API"""
    
    # تحديد نوع المحاضرة
    lecture_type = _detect_lecture_type(text)
    templates = SECTION_TEMPLATES.get(lecture_type, SECTION_TEMPLATES["other"])
    
    # استخراج العنوان (أول سطر أو أول 50 حرف)
    first_line = text.split('\n')[0].strip()
    title = first_line[:100] if first_line else "محاضرة تعليمية"
    
    # تقسيم النص إلى أقسام
    sections_text = _split_text_into_sections(text, num_sections)
    
    # بناء الأقسام
    sections = []
    for i, section_text in enumerate(sections_text):
        # عنوان القسم
        if i < len(templates["titles"]):
            section_title = f"{templates['titles'][i]}"
        else:
            section_title = f"القسم {i + 1}"
        
        # استخراج كلمات مفتاحية
        keywords = _extract_keywords_from_text(section_text, 4)
        
        # توليد محتوى مبسط
        sentences = re.split(r'(?<=[.!?؟])\s+', section_text)
        content = ' '.join(sentences[:5]) if sentences else section_text[:500]
        
        # نص الشرح (narration)
        narration = section_text[:800] if len(section_text) > 800 else section_text
        
        # صور مقترحة
        keyword_images = [f"educational illustration of {kw}" for kw in keywords]
        
        sections.append({
            "title": section_title,
            "content": content,
            "keywords": keywords,
            "keyword_images": keyword_images,
            "narration": narration,
            "duration_estimate": max(30, len(narration) // 15)
        })
    
    # توليد ملخص
    summary = _generate_summary(text)
    
    # نقاط رئيسية
    key_points = []
    for section in sections[:4]:
        if section["keywords"]:
            key_points.append(f"{section['title']}: {', '.join(section['keywords'][:2])}")
    
    return {
        "lecture_type": lecture_type,
        "title": title,
        "sections": sections,
        "summary": summary,
        "key_points": key_points or ["النقطة الأولى", "النقطة الثانية", "النقطة الثالثة", "النقطة الرابعة"],
        "total_sections": num_sections
    }


# ══════════════════════════════════════════════════════════════════════════════
# دوال API (إن وجدت مفاتيح)
# ══════════════════════════════════════════════════════════════════════════════

async def _generate_with_groq(prompt: str, max_tokens: int = 8192) -> str:
    if not _groq_pool:
        raise QuotaExhaustedError("No Groq keys")
    
    available_keys = [k for k in _groq_pool if k not in _groq_exhausted]
    if not available_keys:
        raise QuotaExhaustedError("All Groq keys exhausted")
    
    for key in available_keys:
        try:
            headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
            payload = {
                "model": "llama-3.3-70b-versatile",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": min(max_tokens, 8192),
                "temperature": 0.3,
            }
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=90)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        print(f"✅ Groq success")
                        return data["choices"][0]["message"]["content"].strip()
                    elif resp.status in (429, 403):
                        _groq_exhausted.add(key)
                        continue
        except Exception as e:
            print(f"⚠️ Groq error: {str(e)[:100]}")
            continue
    
    raise QuotaExhaustedError("All Groq keys exhausted")


async def _generate_with_gemini(prompt: str, max_tokens: int = 8192) -> str:
    if not GEMINI_AVAILABLE or not _gemini_pool:
        raise QuotaExhaustedError("Gemini not available")
    
    available_keys = [k for k in _gemini_pool if k not in _gemini_exhausted]
    if not available_keys:
        raise QuotaExhaustedError("All Gemini keys exhausted")
    
    for key in available_keys:
        if key not in _gemini_clients:
            _gemini_clients[key] = genai.Client(api_key=key)
        client = _gemini_clients[key]
        
        try:
            response = await asyncio.to_thread(
                client.models.generate_content,
                model="gemini-2.0-flash",
                contents=prompt,
                config=genai_types.GenerateContentConfig(
                    temperature=0.3,
                    max_output_tokens=max_tokens
                ),
            )
            print(f"✅ Gemini success")
            return response.text.strip()
        except Exception as e:
            err = str(e)
            if "quota" in err.lower() or "429" in err:
                _gemini_exhausted.add(key)
                continue
    
    raise QuotaExhaustedError("All Gemini keys exhausted")


# ══════════════════════════════════════════════════════════════════════════════
# 🔄 دالة التحليل الرئيسية
# ══════════════════════════════════════════════════════════════════════════════

def _compute_lecture_scale(text: str) -> tuple:
    """تحديد عدد الأقسام بناءً على طول النص"""
    word_count = len(text.split())
    if word_count < 300:
        return 3, "6-8", 3000
    elif word_count < 800:
        return 4, "8-10", 5000
    elif word_count < 1500:
        return 5, "10-12", 6000
    elif word_count < 3000:
        return 6, "12-15", 7000
    else:
        return 7, "15-18", 8192


async def analyze_lecture(text: str, dialect: str = "msa") -> dict:
    """تحليل المحاضرة - يحاول استخدام API أولاً ثم يلجأ للتحليل المحلي"""
    
    num_sections, _, _ = _compute_lecture_scale(text)
    
    # محاولة استخدام Groq أولاً
    if _groq_pool:
        try:
            print("🔄 Trying Groq for analysis...")
            prompt = f"""حلل المحاضرة التالية وأرجع JSON بالتنسيق المطلوب.
            
المحاضرة:
{text[:4000]}

المطلوب: {num_sections} أقسام.
أرجع JSON فقط."""
            
            result_text = await _generate_with_groq(prompt)
            # محاولة استخراج JSON
            json_match = re.search(r'\{[\s\S]*\}', result_text)
            if json_match:
                return json.loads(json_match.group())
        except Exception as e:
            print(f"⚠️ Groq analysis failed: {e}")
    
    # محاولة استخدام Gemini
    if _gemini_pool and GEMINI_AVAILABLE:
        try:
            print("🔄 Trying Gemini for analysis...")
            prompt = f"""Analyze this lecture and return JSON with {num_sections} sections.
            
Lecture text:
{text[:4000]}

Return only JSON."""
            
            result_text = await _generate_with_gemini(prompt)
            json_match = re.search(r'\{[\s\S]*\}', result_text)
            if json_match:
                return json.loads(json_match.group())
        except Exception as e:
            print(f"⚠️ Gemini analysis failed: {e}")
    
    # التحليل المحلي (يعمل دائماً)
    print("📝 Using local analysis...")
    return _local_analyze_lecture(text, dialect, num_sections)


# ══════════════════════════════════════════════════════════════════════════════
# 📄 استخراج النص من PDF
# ══════════════════════════════════════════════════════════════════════════════

async def extract_full_text_from_pdf(pdf_bytes: bytes) -> str:
    """استخراج النص الكامل من PDF"""
    try:
        import PyPDF2
        reader = PyPDF2.PdfReader(io.BytesIO(pdf_bytes))
        pages = []
        for page in reader.pages:
            page_text = page.extract_text() or ""
            if page_text.strip():
                pages.append(page_text)
        result = "\n\n".join(pages)
        if len(result) < 50:
            raise ValueError("النص المستخرج قصير جداً")
        return result
    except ImportError:
        raise ImportError("PyPDF2 غير مثبت. pip install PyPDF2")
    except Exception as e:
        raise ValueError(f"فشل في استخراج النص من PDF: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# 🌐 استخراج النص من رابط URL
# ══════════════════════════════════════════════════════════════════════════════

def _is_safe_url(url: str) -> bool:
    import ipaddress
    from urllib.parse import urlparse

    try:
        parsed = urlparse(url)
        if parsed.scheme not in ('http', 'https'):
            return False

        hostname = parsed.hostname or ''
        if not hostname:
            return False

        blocked_hosts = {'localhost', '127.0.0.1', '0.0.0.0', '::1'}
        if hostname.lower() in blocked_hosts:
            return False

        try:
            ip = ipaddress.ip_address(hostname)
            if ip.is_private or ip.is_loopback:
                return False
        except ValueError:
            pass

        return True
    except Exception:
        return False


async def extract_text_from_url(url: str) -> str:
    """استخراج النص من رابط"""
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        raise ImportError("BeautifulSoup غير مثبت")

    if not _is_safe_url(url):
        raise ValueError("الرابط غير مسموح به")

    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status != 200:
                    raise ValueError(f"HTTP {resp.status}")
                html = await resp.text()

        soup = BeautifulSoup(html, 'html.parser')
        for tag in soup(['script', 'style', 'nav', 'footer', 'header']):
            tag.decompose()

        text = soup.get_text(separator='\n', strip=True)
        lines = [line.strip() for line in text.split('\n') if line.strip() and len(line.strip()) > 20]
        
        if not lines:
            raise ValueError("لم يتم العثور على نص")
        
        result = '\n'.join(lines[:200])
        if len(result) < 100:
            raise ValueError("النص قصير جداً")
        
        return result
        
    except Exception as e:
        raise ValueError(f"خطأ في استخراج النص: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# 🖼️ دالة الصور (متوافقة)
# ══════════════════════════════════════════════════════════════════════════════

async def fetch_image_for_keyword_local(keyword: str, section_title: str, lecture_type: str) -> bytes:
    """توليد صورة محلية احترافية"""
    from PIL import Image as PILImage, ImageDraw, ImageFont
    import os
    
    # ألوان حسب النوع
    colors = {
        "medicine": {"bg": (230, 245, 255), "primary": (25, 118, 210), "accent": (255, 152, 0)},
        "science": {"bg": (232, 245, 233), "primary": (46, 125, 50), "accent": (255, 193, 7)},
        "math": {"bg": (243, 229, 245), "primary": (81, 45, 168), "accent": (255, 87, 34)},
        "computer": {"bg": (227, 242, 253), "primary": (2, 119, 189), "accent": (0, 200, 83)},
        "other": {"bg": (245, 245, 245), "primary": (63, 81, 181), "accent": (255, 64, 129)},
    }
    
    c = colors.get(lecture_type, colors["other"])
    
    img = PILImage.new("RGB", (854, 480), c["bg"])
    draw = ImageDraw.Draw(img)
    
    # إطار
    draw.rectangle([(10, 10), (844, 470)], outline=c["primary"], width=3)
    
    # عنوان القسم
    try:
        font_title = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 24)
        font_kw = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 36)
    except:
        font_title = ImageFont.load_default()
        font_kw = font_title
    
    draw.text((30, 30), section_title[:40], fill=c["primary"], font=font_title)
    
    # الكلمة المفتاحية في المنتصف
    try:
        bbox = draw.textbbox((0, 0), keyword, font=font_kw)
        tw = bbox[2] - bbox[0]
    except:
        tw = len(keyword) * 18
    
    draw.text(((854 - tw) // 2, 200), keyword, fill=c["primary"], font=font_kw)
    
    # خط تحت الكلمة
    draw.rectangle([(200, 260), (654, 265)], fill=c["accent"])
    
    # علامة مائية
    draw.text((700, 440), "@zakros_probot", fill=(150, 150, 150), font=font_title)
    
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=90)
    return buf.getvalue()


# تصدير الدالة المناسبة
if fetch_image_for_keyword is None:
    fetch_image_for_keyword = fetch_image_for_keyword_local
