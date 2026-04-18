import json
import re
import io
import asyncio
import aiohttp
from PIL import Image as PILImage
from g4f.client import Client

# عميل g4f المجاني
_client = None

def _get_client():
    global _client
    if _client is None:
        _client = Client()
    return _client

def _compute_lecture_scale(text: str) -> tuple:
    """تحديد عدد الأقسام بناءً على طول النص"""
    word_count = len(text.split())
    if word_count < 300:
        return 3, "8-12", 3000
    elif word_count < 800:
        return 5, "12-16", 5000
    else:
        return 7, "15-20", 7000

async def analyze_lecture(text: str, dialect: str = "msa") -> dict:
    """تحليل المحاضرة باستخدام g4f المجاني"""
    
    dialect_instructions = {
        "iraq": "استخدم اللهجة العراقية في الشرح مع كلمات عراقية مثل: هواية، گلت، هسة، شكو، ماكو",
        "egypt": "استخدم اللهجة المصرية في الشرح مع كلمات مصرية مثل: أوي، معلش، كده، يعني، إيه",
        "syria": "استخدم اللهجة الشامية في الشرح مع كلمات شامية مثل: هلق، شو، كتير، منيح، هيك",
        "gulf": "استخدم اللهجة الخليجية في الشرح مع كلمات خليجية مثل: زين، وايد، عاد، هاذي، أبشر",
        "msa": "استخدم العربية الفصحى الواضحة والمبسطة",
        "english": "Use clear, simple English. Explain like a teacher to students."
    }
    
    instruction = dialect_instructions.get(dialect, dialect_instructions["msa"])
    num_sections, sentences_per, _ = _compute_lecture_scale(text)
    text_limit = min(len(text), 4000)
    
    prompt = f"""أنت معلم خبير في تبسيط المحاضرات. حلل هذه المحاضرة وأرجع JSON فقط.

{instruction}

المحاضرة:
---
{text[:text_limit]}
---

أرجع JSON بهذا التنسيق بالضبط (يجب أن يحتوي على {num_sections} أقسام):

{{
  "lecture_type": "نوع المحاضرة (طب/علوم/رياضيات/أدب/تاريخ/تقنية/أعمال/أخرى)",
  "title": "عنوان المحاضرة",
  "sections": [
    {{
      "title": "عنوان القسم",
      "content": "شرح مبسط للقسم ({sentences_per} جمل)",
      "keywords": ["مصطلح1", "مصطلح2", "مصطلح3", "مصطلح4"],
      "narration": "نص الشرح الكامل باللهجة المطلوبة ({sentences_per} جمل)",
      "duration_estimate": 60
    }}
  ],
  "summary": "ملخص المحاضرة (4-5 جمل)",
  "key_points": ["نقطة1", "نقطة2", "نقطة3", "نقطة4"],
  "total_sections": {num_sections}
}}

مهم جداً:
- يجب أن يكون عدد الأقسام {num_sections} بالضبط
- اجعل النصوص باللهجة المطلوبة بالكامل
- أرجع JSON فقط بدون أي نص إضافي"""

    try:
        client = _get_client()
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
        )
        content = response.choices[0].message.content.strip()
        
        # تنظيف الرد
        content = re.sub(r'^```json\s*', '', content)
        content = re.sub(r'\s*```$', '', content)
        content = content.strip()
        
        # محاولة استخراج JSON
        result = json.loads(content)
        return result
        
    except json.JSONDecodeError:
        # محاولة استخراج JSON من النص
        json_match = re.search(r'\{[\s\S]*\}', content)
        if json_match:
            return json.loads(json_match.group())
        raise ValueError("Failed to parse response as JSON")
    except Exception as e:
        # في حالة الفشل - إنشاء تحليل بسيط
        return _fallback_analysis(text, num_sections)

def _fallback_analysis(text: str, num_sections: int) -> dict:
    """تحليل احتياطي بسيط في حالة فشل AI"""
    sentences = [s.strip() for s in text.split('.') if s.strip()]
    section_size = max(1, len(sentences) // num_sections)
    
    sections = []
    for i in range(num_sections):
        start = i * section_size
        end = min(start + section_size, len(sentences))
        section_text = '. '.join(sentences[start:end]) + '.'
        
        sections.append({
            "title": f"القسم {i+1}",
            "content": section_text[:200] + "...",
            "keywords": ["تعليم", "محاضرة", "شرح"],
            "narration": section_text,
            "duration_estimate": 45
        })
    
    return {
        "lecture_type": "other",
        "title": "محاضرة تعليمية",
        "sections": sections,
        "summary": text[:300] + "...",
        "key_points": ["النقطة 1", "النقطة 2", "النقطة 3"],
        "total_sections": num_sections
    }

async def extract_text_from_url(url: str) -> str:
    """استخراج النص من رابط"""
    from bs4 import BeautifulSoup
    
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers, timeout=30) as resp:
            html = await resp.text()
    
    soup = BeautifulSoup(html, 'html.parser')
    for tag in soup(['script', 'style', 'nav', 'footer', 'header']):
        tag.decompose()
    
    text = soup.get_text(separator='\n', strip=True)
    lines = [line.strip() for line in text.split('\n') if len(line.strip()) > 20]
    return '\n'.join(lines[:100])

async def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """استخراج النص من PDF"""
    import PyPDF2
    
    reader = PyPDF2.PdfReader(io.BytesIO(pdf_bytes))
    text = ""
    for page in reader.pages[:10]:  # أول 10 صفحات فقط
        text += page.extract_text() + "\n"
    return text[:10000]

async def generate_educational_image(keyword: str) -> bytes:
    """توليد صورة تعليمية باستخدام Pollinations.ai المجاني"""
    
    prompt = f"Educational illustration of {keyword}, colorful flat design, clean background, professional style, no text"
    
    # استخدام Pollinations.ai (مجاني تماماً)
    url = f"https://image.pollinations.ai/prompt/{prompt.replace(' ', '%20')}"
    url += "?width=1280&height=720&nologo=true"
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=20) as resp:
                if resp.status == 200:
                    raw = await resp.read()
                    # تحويل إلى JPEG
                    img = PILImage.open(io.BytesIO(raw)).convert("RGB")
                    buf = io.BytesIO()
                    img.save(buf, "JPEG", quality=85)
                    return buf.getvalue()
    except Exception as e:
        print(f"Image generation failed: {e}")
    
    # صورة احتياطية
    return _make_placeholder_image(keyword)

def _make_placeholder_image(keyword: str) -> bytes:
    """إنشاء صورة تعليمية احتياطية"""
    from PIL import ImageDraw, ImageFont
    
    W, H = 1280, 720
    bg_color = (41, 128, 185)  # أزرق تعليمي
    img = PILImage.new("RGB", (W, H), bg_color)
    draw = ImageDraw.Draw(img)
    
    # إضافة نص
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 60)
    except:
        font = ImageFont.load_default()
    
    text = keyword[:30]
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    
    draw.text(
        ((W - text_width) // 2, (H - text_height) // 2),
        text,
        fill="white",
        font=font
    )
    
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=90)
    return buf.getvalue()

async def fetch_image_for_keyword(keyword: str, section_title: str = "", lecture_type: str = "") -> bytes:
    """جلب صورة للكلمة المفتاحية"""
    return await generate_educational_image(keyword)
