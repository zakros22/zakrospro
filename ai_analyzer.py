import re
import io
import os
from PIL import Image as PILImage, ImageDraw, ImageFont

def _extract_keywords(text: str, max_words: int = 20) -> list:
    """استخراج الكلمات المفتاحية من النص"""
    stop_words = {'و', 'في', 'من', 'على', 'إلى', 'أن', 'هو', 'هي', 'هذا', 'هذه', 'كان', 
                  'مع', 'ما', 'لا', 'عن', 'إذا', 'لم', 'لن', 'قد', 'ثم', 'أو', 
                  'the', 'a', 'an', 'is', 'are', 'of', 'to', 'in', 'that', 'it',
                  'for', 'on', 'with', 'as', 'at', 'by', 'this', 'and', 'or', 'but'}
    
    words = re.findall(r'[\u0600-\u06FF]{4,}|[a-zA-Z]{4,}', text)
    word_freq = {}
    for w in words:
        w_lower = w.lower()
        if w_lower not in stop_words:
            word_freq[w] = word_freq.get(w, 0) + 1
    
    sorted_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)
    return [w[0] for w in sorted_words[:max_words]]


def _split_text_into_parts(text: str, num_parts: int) -> list:
    """تقسيم النص إلى أجزاء متساوية"""
    words = text.split()
    chunk_size = max(1, len(words) // num_parts)
    parts = []
    for i in range(0, len(words), chunk_size):
        parts.append(' '.join(words[i:i+chunk_size]))
    
    if len(parts) > num_parts:
        parts = parts[:num_parts]
    while len(parts) < num_parts:
        parts.append("")
    
    return parts


async def analyze_lecture(text: str, dialect: str = "msa") -> dict:
    """تحليل بسيط: تقسيم النص + استخراج الكلمات"""
    
    all_keywords = _extract_keywords(text, 30)
    
    word_count = len(text.split())
    if word_count < 300:
        num_sections = 3
    elif word_count < 600:
        num_sections = 4
    else:
        num_sections = 5
    
    text_parts = _split_text_into_parts(text, num_sections)
    
    sections = []
    for i in range(num_sections):
        start_idx = (i * 4) % len(all_keywords)
        keywords = []
        for j in range(4):
            idx = (start_idx + j) % len(all_keywords)
            if all_keywords[idx] not in keywords:
                keywords.append(all_keywords[idx])
        
        sections.append({
            "title": keywords[0] if keywords else f"القسم {i+1}",
            "keywords": keywords if keywords else ["مفهوم", "تعريف", "شرح", "تحليل"],
            "narration": text_parts[i] if i < len(text_parts) else " ".join(keywords),
            "_keyword_images": [None] * 4,
            "_image_bytes": None
        })
    
    return {
        "lecture_type": "other",
        "title": all_keywords[0] if all_keywords else "المحاضرة التعليمية",
        "sections": sections,
        "summary": f"شرحنا: {', '.join(all_keywords[:5])}",
        "all_keywords": all_keywords
    }


async def extract_full_text_from_pdf(pdf_bytes: bytes) -> str:
    import PyPDF2
    reader = PyPDF2.PdfReader(io.BytesIO(pdf_bytes))
    pages = []
    for page in reader.pages:
        page_text = page.extract_text() or ""
        if page_text.strip():
            pages.append(page_text)
    return "\n\n".join(pages)


def _get_font(size: int) -> ImageFont.FreeTypeFont:
    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for p in font_paths:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except:
                pass
    return ImageFont.load_default()


def _make_simple_image(keyword: str, color: tuple) -> bytes:
    """صورة بسيطة ملونة"""
    W, H = 400, 300
    img = PILImage.new("RGB", (W, H), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    
    for y in range(H):
        t = y / H
        r = int(255 * (1 - t) + color[0] * t * 0.2)
        g = int(255 * (1 - t) + color[1] * t * 0.2)
        b = int(255 * (1 - t) + color[2] * t * 0.2)
        draw.line([(0, y), (W, y)], fill=(r, g, b))
    
    draw.rounded_rectangle([(8, 8), (W-8, H-8)], radius=15, outline=color, width=6)
    draw.ellipse([(W//2-50, H//2-50), (W//2+50, H//2+50)], fill=(*color, 30))
    
    font = _get_font(32)
    
    try:
        bbox = font.getbbox(keyword)
        tw = bbox[2] - bbox[0]
    except:
        tw = len(keyword) * 18
    
    x = (W - tw) // 2
    y = H // 2 - 15
    draw.text((x+2, y+2), keyword, fill=(200, 200, 200), font=font)
    draw.text((x, y), keyword, fill=color, font=font)
    
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=90)
    return buf.getvalue()


COLORS = [
    (231, 76, 126),
    (52, 152, 219),
    (46, 204, 113),
    (155, 89, 182),
    (230, 126, 34),
]


async def fetch_image_for_keyword(
    keyword: str,
    section_title: str = "",
    lecture_type: str = "other",
    image_search_en: str = "",
) -> bytes:
    color = COLORS[hash(keyword) % len(COLORS)]
    return _make_simple_image(keyword, color)
