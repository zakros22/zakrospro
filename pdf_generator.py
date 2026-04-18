import os
import io
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from PIL import Image

_FONTS_REGISTERED = False
_FONT_DIR = os.path.join(os.path.dirname(__file__), "fonts")
_ARABIC_REGULAR = os.path.join(_FONT_DIR, "NotoNaskhArabic-Regular.ttf")
_ARABIC_BOLD = os.path.join(_FONT_DIR, "NotoNaskhArabic-Bold.ttf")

def _register_fonts():
    global _FONTS_REGISTERED
    if _FONTS_REGISTERED:
        return
    try:
        if os.path.exists(_ARABIC_REGULAR):
            pdfmetrics.registerFont(TTFont("Arabic", _ARABIC_REGULAR))
        if os.path.exists(_ARABIC_BOLD):
            pdfmetrics.registerFont(TTFont("ArabicBold", _ARABIC_BOLD))
        _FONTS_REGISTERED = True
    except:
        pass

def _ar(text: str) -> str:
    """معالجة النص العربي"""
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
        return get_display(arabic_reshaper.reshape(text))
    except:
        return text

def create_pdf_summary(lecture_data: dict, sections: list, output_path: str) -> str:
    """إنشاء ملخص PDF"""
    _register_fonts()
    
    font_name = "Arabic" if os.path.exists(_ARABIC_REGULAR) else "Helvetica"
    font_bold = "ArabicBold" if os.path.exists(_ARABIC_BOLD) else "Helvetica-Bold"
    
    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        rightMargin=2*cm,
        leftMargin=2*cm,
        topMargin=2*cm,
        bottomMargin=2*cm
    )
    
    styles = getSampleStyleSheet()
    story = []
    
    # عنوان المحاضرة
    title = lecture_data.get("title", "ملخص المحاضرة")
    title_style = ParagraphStyle(
        'Title', parent=styles['Heading1'],
        fontName=font_bold,
        fontSize=22,
        alignment=TA_RIGHT,
        textColor=colors.HexColor('#1a237e'),
        spaceAfter=20
    )
    story.append(Paragraph(_ar(title), title_style))
    
    # الملخص
    summary = lecture_data.get("summary", "")
    if summary:
        summary_style = ParagraphStyle(
            'Summary', parent=styles['Normal'],
            fontName=font_name,
            fontSize=12,
            alignment=TA_RIGHT,
            leading=18,
            spaceAfter=15
        )
        story.append(Paragraph(_ar("📋 الملخص:"), title_style.clone(fontSize=16)))
        story.append(Paragraph(_ar(summary), summary_style))
        story.append(Spacer(1, 10))
    
    # النقاط الرئيسية
    key_points = lecture_data.get("key_points", [])
    if key_points:
        story.append(Paragraph(_ar("✅ النقاط الرئيسية:"), title_style.clone(fontSize=16)))
        bullet_style = ParagraphStyle(
            'Bullet', parent=styles['Normal'],
            fontName=font_name,
            fontSize=11,
            alignment=TA_RIGHT,
            leading=18,
            leftIndent=20
        )
        for point in key_points:
            story.append(Paragraph(_ar(f"• {point}"), bullet_style))
        story.append(Spacer(1, 15))
    
    # الأقسام
    story.append(Paragraph(_ar("📚 الأقسام التفصيلية:"), title_style.clone(fontSize=16)))
    story.append(Spacer(1, 10))
    
    section_title_style = ParagraphStyle(
        'SecTitle', parent=styles['Heading2'],
        fontName=font_bold,
        fontSize=14,
        alignment=TA_RIGHT,
        textColor=colors.HexColor('#283593'),
        spaceAfter=5
    )
    
    section_body_style = ParagraphStyle(
        'SecBody', parent=styles['Normal'],
        fontName=font_name,
        fontSize=11,
        alignment=TA_RIGHT,
        leading=18,
        spaceAfter=15
    )
    
    for i, section in enumerate(sections):
        sec_title = section.get("title", f"القسم {i+1}")
        sec_content = section.get("content", section.get("narration", ""))
        
        story.append(Paragraph(_ar(f"{i+1}. {sec_title}"), section_title_style))
        story.append(Paragraph(_ar(sec_content[:500]), section_body_style))
    
    doc.build(story)
    return output_path
