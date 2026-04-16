from PIL import Image, ImageDraw, ImageFont
import arabic_reshaper
from bidi.algorithm import get_display
import textwrap
import os
from typing import List, Dict
import random

class ImageGenerator:
    def __init__(self):
        self.width = 1080
        self.height = 1080
        self.colors = [
            ('#1a1a2e', '#16213e'),  # أزرق داكن
            ('#0f3460', '#16213e'),  # أزرق
            ('#2c3e50', '#3498db'),  # أزرق فاتح
            ('#8e44ad', '#9b59b6'),  # بنفسجي
            ('#c0392b', '#e74c3c'),  # أحمر
        ]
        
        # تحميل الخطوط
        self.title_font = self.load_font(48)
        self.body_font = self.load_font(32)
        self.keyword_font = self.load_font(28)
    
    def load_font(self, size: int):
        """تحميل الخط العربي"""
        try:
            # محاولة تحميل خط عربي
            font_paths = [
                '/usr/share/fonts/truetype/amiri/Amiri-Bold.ttf',
                'Amiri-Bold.ttf',
                'arial.ttf'
            ]
            for path in font_paths:
                if os.path.exists(path):
                    return ImageFont.truetype(path, size)
        except:
            pass
        return ImageFont.load_default()
    
    def reshape_arabic(self, text: str) -> str:
        """تشكيل النص العربي للعرض الصحيح"""
        reshaped = arabic_reshaper.reshape(text)
        return get_display(reshaped)
    
    def create_card(self, title: str, content: str, keywords: List[str], 
                    card_number: int, total_cards: int) -> Image.Image:
        """إنشاء كارت واحد"""
        
        # اختيار لون عشوائي
        bg_color, accent_color = random.choice(self.colors)
        
        # إنشاء الصورة
        img = Image.new('RGB', (self.width, self.height), bg_color)
        draw = ImageDraw.Draw(img)
        
        # إضافة تدرج لوني
        for i in range(self.height):
            color = self.interpolate_color(bg_color, accent_color, i / self.height)
            draw.rectangle([(0, i), (self.width, i + 1)], fill=color)
        
        y_position = 50
        
        # رقم الكارت
        card_info = f"{card_number}/{total_cards}"
        draw.text((self.width - 150, y_position), card_info, 
                 fill='white', font=self.body_font)
        
        y_position += 60
        
        # العنوان
        title_arabic = self.reshape_arabic(title)
        title_lines = textwrap.wrap(title_arabic, width=25)
        for line in title_lines:
            bbox = draw.textbbox((0, 0), line, font=self.title_font)
            text_width = bbox[2] - bbox[0]
            x = (self.width - text_width) // 2
            draw.text((x, y_position), line, fill='white', font=self.title_font)
            y_position += 60
        
        y_position += 30
        
        # خط فاصل
        draw.line([(100, y_position), (self.width - 100, y_position)], 
                 fill='white', width=3)
        y_position += 40
        
        # المحتوى
        content_arabic = self.reshape_arabic(content)
        content_lines = textwrap.wrap(content_arabic, width=40)
        for line in content_lines:
            draw.text((100, y_position), line, fill='#e0e0e0', font=self.body_font)
            y_position += 40
        
        y_position += 30
        
        # الكلمات المفتاحية
        if keywords:
            keywords_text = "الكلمات المفتاحية: " + " | ".join(keywords)
            keywords_arabic = self.reshape_arabic(keywords_text)
            keywords_lines = textwrap.wrap(keywords_arabic, width=35)
            for line in keywords_lines:
                draw.text((100, y_position), line, fill='#ffd700', font=self.keyword_font)
                y_position += 35
        
        return img
    
    def interpolate_color(self, color1: str, color2: str, factor: float) -> str:
        """حساب لون متوسط بين لونين"""
        c1 = tuple(int(color1.lstrip('#')[i:i+2], 16) for i in (0, 2, 4))
        c2 = tuple(int(color2.lstrip('#')[i:i+2], 16) for i in (0, 2, 4))
        
        r = int(c1[0] + (c2[0] - c1[0]) * factor)
        g = int(c1[1] + (c2[1] - c1[1]) * factor)
        b = int(c1[2] + (c2[2] - c1[2]) * factor)
        
        return f'#{r:02x}{g:02x}{b:02x}'
    
    async def generate_all_cards(self, analyzed_content: Dict) -> List[str]:
        """توليد جميع الكارتات"""
        cards = []
        
        # كارت العنوان
        title_card = self.create_title_card(
            analyzed_content['title'],
            analyzed_content['type']
        )
        title_path = f"temp/title_card_{random.randint(1000, 9999)}.png"
        title_card.save(title_path)
        cards.append(title_path)
        
        # كارتات الأقسام
        total_sections = len(analyzed_content['sections'])
        for i, section in enumerate(analyzed_content['sections'], 1):
            card = self.create_card(
                section['title'],
                section['explanation'],
                section['keywords'],
                i + 1,  # +1 لأن الكارت الأول هو العنوان
                total_sections + 2  # +2 للعنوان والملخص
            )
            path = f"temp/section_{i}_{random.randint(1000, 9999)}.png"
            card.save(path)
            cards.append(path)
        
        # كارت الملخص
        summary_card = self.create_summary_card(
            analyzed_content['summary'],
            total_sections + 2,
            total_sections + 2
        )
        summary_path = f"temp/summary_{random.randint(1000, 9999)}.png"
        summary_card.save(summary_path)
        cards.append(summary_path)
        
        return cards
    
    def create_title_card(self, title: str, content_type: str) -> Image.Image:
        """إنشاء كارت العنوان"""
        img = Image.new('RGB', (self.width, self.height), '#1a1a2e')
        draw = ImageDraw.Draw(img)
        
        # إضافة تأثيرات
        for i in range(0, self.height, 2):
            color = self.interpolate_color('#1a1a2e', '#0f3460', i / self.height)
            draw.rectangle([(0, i), (self.width, i + 2)], fill=color)
        
        # العنوان الرئيسي
        title_arabic = self.reshape_arabic(title)
        title_lines = textwrap.wrap(title_arabic, width=20)
        
        y_position = self.height // 3
        for line in title_lines:
            bbox = draw.textbbox((0, 0), line, font=self.title_font)
            text_width = bbox[2] - bbox[0]
            x = (self.width - text_width) // 2
            draw.text((x, y_position), line, fill='white', font=self.title_font)
            y_position += 70
        
        # نوع المحتوى
        type_text = f"محاضرة {content_type}"
        type_arabic = self.reshape_arabic(type_text)
        bbox = draw.textbbox((0, 0), type_arabic, font=self.body_font)
        text_width = bbox[2] - bbox[0]
        x = (self.width - text_width) // 2
        draw.text((x, y_position + 50), type_arabic, fill='#e0e0e0', font=self.body_font)
        
        return img
    
    def create_summary_card(self, summary: str, card_number: int, total_cards: int) -> Image.Image:
        """إنشاء كارت الملخص"""
        img = Image.new('RGB', (self.width, self.height), '#16213e')
        draw = ImageDraw.Draw(img)
        
        # رقم الكارت
        card_info = f"{card_number}/{total_cards}"
        draw.text((self.width - 150, 50), card_info, fill='white', font=self.body_font)
        
        # عنوان الملخص
        title = self.reshape_arabic("ملخص المحاضرة")
        bbox = draw.textbbox((0, 0), title, font=self.title_font)
        text_width = bbox[2] - bbox[0]
        x = (self.width - text_width) // 2
        draw.text((x, 120), title, fill='white', font=self.title_font)
        
        # خط فاصل
        draw.line([(100, 190), (self.width - 100, 190)], fill='#ffd700', width=3)
        
        # محتوى الملخص
        summary_arabic = self.reshape_arabic(summary)
        summary_lines = textwrap.wrap(summary_arabic, width=35)
        
        y_position = 250
        for line in summary_lines:
            draw.text((100, y_position), line, fill='white', font=self.body_font)
            y_position += 45
        
        return img
