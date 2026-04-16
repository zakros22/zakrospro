#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import asyncio
import logging
import re
import random
import json
import tempfile
import shutil
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
import textwrap

# Telegram
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters, ContextTypes
)
from telegram.constants import ParseMode

# Video
from moviepy.editor import *

# PDF and Docs
import PyPDF2
from docx import Document

# Arabic support
import arabic_reshaper
from bidi.algorithm import get_display

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ============== KeyManager ==============
class KeyManager:
    def __init__(self):
        self.current_key_index = 0
        self.key_usage = {}
        
    def get_analysis_key(self):
        return "free_alternative"
    
    def get_tts_key(self):
        return {'service': 'gtts', 'key': None}

# ============== ContentAnalyzer ==============
class ContentAnalyzer:
    def __init__(self):
        self.key_manager = KeyManager()
        
    async def analyze_content(self, text: str, file_type: str = None) -> Dict:
        cleaned_text = self.clean_text(text)
        content_type = self.detect_content_type(cleaned_text)
        title = self.extract_title(cleaned_text)
        sections = self.extract_sections(cleaned_text)
        
        enriched_sections = []
        for section in sections:
            keywords = self.extract_keywords(section['content'])
            enriched_sections.append({
                'title': section['title'],
                'content': section['content'],
                'keywords': keywords,
                'explanation': self.generate_explanation(section['content'], keywords)
            })
        
        return {
            'type': content_type,
            'title': title,
            'sections': enriched_sections,
            'summary': self.generate_summary(cleaned_text, title)
        }
    
    def clean_text(self, text: str) -> str:
        text = re.sub(r'\n\s*\n', '\n\n', text)
        text = re.sub(r'\s+', ' ', text)
        return text.strip()
    
    def detect_content_type(self, text: str) -> str:
        medical_keywords = ['خلية', 'غشاء', 'مرض', 'علاج', 'جراحة', 'ولادة', 'قيصرية']
        text_lower = text.lower()
        if any(kw in text_lower for kw in medical_keywords):
            return 'medical'
        return 'general'
    
    def extract_title(self, text: str) -> str:
        lines = text.split('\n')
        for line in lines[:5]:
            line = line.strip()
            if line and len(line) < 100:
                return line
        return "محاضرة"
    
    def extract_sections(self, text: str) -> List[Dict]:
        sections = []
        lines = text.split('\n')
        current_section = {'title': 'مقدمة', 'content': []}
        
        section_markers = ['مقدمة', 'تعريف', 'أنواع', 'أسباب', 'أعراض', 'علاج', 'خاتمة', 'نتائج', 'خلاصة']
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            is_header = False
            for marker in section_markers:
                if marker in line and len(line) < 50:
                    if current_section['content']:
                        sections.append({
                            'title': current_section['title'],
                            'content': '\n'.join(current_section['content'])
                        })
                    current_section = {'title': line, 'content': []}
                    is_header = True
                    break
            
            if not is_header:
                current_section['content'].append(line)
        
        if current_section['content']:
            sections.append({
                'title': current_section['title'],
                'content': '\n'.join(current_section['content'])
            })
        
        return sections
    
    def extract_keywords(self, text: str) -> List[str]:
        words = re.findall(r'\b[A-Za-z\u0600-\u06FF]{3,}\b', text)
        stopwords = ['من', 'إلى', 'عن', 'على', 'في', 'مع', 'هذا', 'هذه', 'ذلك']
        keywords = {}
        for word in words:
            if word.lower() not in stopwords:
                keywords[word] = keywords.get(word, 0) + 1
        sorted_keywords = sorted(keywords.items(), key=lambda x: x[1], reverse=True)
        return [kw[0] for kw in sorted_keywords[:5]]
    
    def generate_explanation(self, content: str, keywords: List[str]) -> str:
        sentences = content.split('.')
        summary = '. '.join(sentences[:3]) + '.'
        return summary
    
    def generate_summary(self, text: str, title: str) -> str:
        lines = text.split('\n')[:5]
        return '\n'.join(lines)

# ============== ImageGenerator ==============
class ImageGenerator:
    def __init__(self):
        self.width = 1080
        self.height = 1080
        self.colors = [('#1a1a2e', '#16213e'), ('#0f3460', '#16213e')]
        
    def reshape_arabic(self, text: str) -> str:
        try:
            reshaped = arabic_reshaper.reshape(text)
            return get_display(reshaped)
        except:
            return text
    
    def load_font(self, size: int):
        try:
            return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", size)
        except:
            return ImageFont.load_default()
    
    def create_card(self, title: str, content: str, keywords: List[str], 
                    card_number: int, total_cards: int) -> Image.Image:
        bg_color, accent_color = random.choice(self.colors)
        img = Image.new('RGB', (self.width, self.height), bg_color)
        draw = ImageDraw.Draw(img)
        
        title_font = self.load_font(48)
        body_font = self.load_font(32)
        
        y_position = 50
        card_info = f"{card_number}/{total_cards}"
        draw.text((self.width - 150, y_position), card_info, fill='white', font=body_font)
        
        y_position += 60
        title_arabic = self.reshape_arabic(title)
        title_lines = textwrap.wrap(title_arabic, width=25)
        for line in title_lines:
            bbox = draw.textbbox((0, 0), line, font=title_font)
            text_width = bbox[2] - bbox[0]
            x = (self.width - text_width) // 2
            draw.text((x, y_position), line, fill='white', font=title_font)
            y_position += 60
        
        y_position += 30
        draw.line([(100, y_position), (self.width - 100, y_position)], fill='white', width=3)
        y_position += 40
        
        content_arabic = self.reshape_arabic(content)
        content_lines = textwrap.wrap(content_arabic, width=40)
        for line in content_lines:
            draw.text((100, y_position), line, fill='#e0e0e0', font=body_font)
            y_position += 40
        
        return img
    
    async def generate_all_cards(self, analyzed_content: Dict) -> List[str]:
        cards = []
        os.makedirs("temp", exist_ok=True)
        
        # Title card
        title_card = self.create_title_card(analyzed_content['title'], analyzed_content['type'])
        title_path = f"temp/title_card_{random.randint(1000, 9999)}.png"
        title_card.save(title_path)
        cards.append(title_path)
        
        # Section cards
        total_sections = len(analyzed_content['sections'])
        for i, section in enumerate(analyzed_content['sections'], 1):
            card = self.create_card(
                section['title'],
                section['explanation'],
                section['keywords'],
                i + 1,
                total_sections + 2
            )
            path = f"temp/section_{i}_{random.randint(1000, 9999)}.png"
            card.save(path)
            cards.append(path)
        
        # Summary card
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
        img = Image.new('RGB', (self.width, self.height), '#1a1a2e')
        draw = ImageDraw.Draw(img)
        title_font = self.load_font(60)
        body_font = self.load_font(36)
        
        title_arabic = self.reshape_arabic(title)
        title_lines = textwrap.wrap(title_arabic, width=20)
        
        y_position = self.height // 3
        for line in title_lines:
            bbox = draw.textbbox((0, 0), line, font=title_font)
            text_width = bbox[2] - bbox[0]
            x = (self.width - text_width) // 2
            draw.text((x, y_position), line, fill='white', font=title_font)
            y_position += 70
        
        type_text = f"محاضرة {content_type}"
        type_arabic = self.reshape_arabic(type_text)
        bbox = draw.textbbox((0, 0), type_arabic, font=body_font)
        text_width = bbox[2] - bbox[0]
        x = (self.width - text_width) // 2
        draw.text((x, y_position + 50), type_arabic, fill='#e0e0e0', font=body_font)
        
        return img
    
    def create_summary_card(self, summary: str, card_number: int, total_cards: int) -> Image.Image:
        img = Image.new('RGB', (self.width, self.height), '#16213e')
        draw = ImageDraw.Draw(img)
        title_font = self.load_font(48)
        body_font = self.load_font(32)
        
        card_info = f"{card_number}/{total_cards}"
        draw.text((self.width - 150, 50), card_info, fill='white', font=body_font)
        
        title = self.reshape_arabic("ملخص المحاضرة")
        bbox = draw.textbbox((0, 0), title, font=title_font)
        text_width = bbox[2] - bbox[0]
        x = (self.width - text_width) // 2
        draw.text((x, 120), title, fill='white', font=title_font)
        
        draw.line([(100, 190), (self.width - 100, 190)], fill='#ffd700', width=3)
        
        summary_arabic = self.reshape_arabic(summary)
        summary_lines = textwrap.wrap(summary_arabic, width=35)
        
        y_position = 250
        for line in summary_lines:
            draw.text((100, y_position), line, fill='white', font=body_font)
            y_position += 45
        
        return img

# ============== AudioGenerator ==============
class AudioGenerator:
    def __init__(self):
        self.key_manager = KeyManager()
        os.makedirs("temp_audio", exist_ok=True)
    
    async def generate_audio(self, text: str, section_title: str) -> str:
        try:
            from gtts import gTTS
            filepath = f"temp_audio/audio_{random.randint(1000, 9999)}.mp3"
            
            def generate():
                tts = gTTS(text=text[:500], lang='ar', slow=False)
                tts.save(filepath)
            
            await asyncio.to_thread(generate)
            return filepath
        except Exception as e:
            logger.error(f"Audio generation error: {e}")
            return None
    
    async def generate_all_audio(self, analyzed_content: Dict) -> Dict[str, str]:
        audio_files = {}
        
        intro_text = f"محاضرة: {analyzed_content['title']}"
        audio_files['intro'] = await self.generate_audio(intro_text, "مقدمة")
        
        for i, section in enumerate(analyzed_content['sections']):
            audio_text = f"{section['title']}. {section['explanation'][:300]}"
            audio_files[f'section_{i}'] = await self.generate_audio(audio_text, section['title'])
        
        return audio_files

# ============== VideoMaker ==============
class VideoMaker:
    def __init__(self):
        self.fps = 24
        self.resolution = (1080, 1080)
    
    def create_video(self, image_paths: List[str], audio_files: Dict[str, str], 
                     analyzed_content: Dict) -> str:
        clips = []
        
        # Title clip
        if image_paths and os.path.exists(image_paths[0]):
            duration = 5
            if 'intro' in audio_files and audio_files['intro'] and os.path.exists(audio_files['intro']):
                try:
                    audio_clip = AudioFileClip(audio_files['intro'])
                    duration = audio_clip.duration
                except:
                    pass
            clip = ImageClip(image_paths[0]).set_duration(duration)
            clips.append(clip)
        
        # Section clips
        for i, img_path in enumerate(image_paths[1:-1]):
            if os.path.exists(img_path):
                duration = 5
                audio_key = f'section_{i}'
                if audio_key in audio_files and audio_files[audio_key] and os.path.exists(audio_files[audio_key]):
                    try:
                        audio_clip = AudioFileClip(audio_files[audio_key])
                        duration = audio_clip.duration
                    except:
                        pass
                clip = ImageClip(img_path).set_duration(duration)
                clips.append(clip)
        
        # Summary clip
        if len(image_paths) > 1 and os.path.exists(image_paths[-1]):
            clip = ImageClip(image_paths[-1]).set_duration(5)
            clips.append(clip)
        
        if not clips:
            return None
        
        final_video = concatenate_videoclips(clips, method="compose")
        output_path = f"temp/final_video_{random.randint(1000, 9999)}.mp4"
        
        final_video.write_videofile(
            output_path,
            fps=self.fps,
            codec='libx264',
            audio_codec='aac',
            verbose=False,
            logger=None
        )
        
        return output_path

# ============== Helper Functions ==============
async def download_file(file, filename: str) -> str:
    os.makedirs("temp", exist_ok=True)
    file_path = f"temp/{filename}"
    await file.download_to_drive(file_path)
    return file_path

def cleanup_temp_files():
    for dir_name in ['temp', 'temp_audio']:
        if os.path.exists(dir_name):
            shutil.rmtree(dir_name)
            os.makedirs(dir_name, exist_ok=True)

async def extract_text_from_file(file_path: str) -> str:
    ext = os.path.splitext(file_path)[1].lower()
    
    if ext == '.pdf':
        text = ""
        with open(file_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            for page in pdf_reader.pages:
                text += page.extract_text() + "\n"
        return text
    
    elif ext in ['.docx', '.doc']:
        doc = Document(file_path)
        return "\n".join([p.text for p in doc.paragraphs])
    
    elif ext == '.txt':
        with open(file_path, 'r', encoding='utf-8') as file:
            return file.read()
    
    return ""

# ============== Main Bot ==============
class LectureBot:
    def __init__(self, token: str):
        self.token = token
        self.analyzer = ContentAnalyzer()
        self.image_gen = ImageGenerator()
        self.audio_gen = AudioGenerator()
        self.video_maker = VideoMaker()
        
        os.makedirs("temp", exist_ok=True)
        os.makedirs("temp_audio", exist_ok=True)
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        welcome_message = """
🎓 *مرحباً بك في بوت المحاضرات التعليمية!*

أرسل ملف PDF أو Word أو نص مباشرة لتحويله إلى محاضرة فيديو.

*للبدء:* أرسل ملفاً أو نصاً الآن! 📚
        """
        await update.message.reply_text(welcome_message, parse_mode=ParseMode.MARKDOWN)
    
    async def handle_document(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        status_message = await update.message.reply_text("📥 *جاري معالجة الملف...*", parse_mode=ParseMode.MARKDOWN)
        
        try:
            file = await update.message.document.get_file()
            file_path = await download_file(file, update.message.document.file_name)
            
            await status_message.edit_text("🔍 *جاري استخراج النص...*", parse_mode=ParseMode.MARKDOWN)
            text_content = await extract_text_from_file(file_path)
            
            await self.process_content(update, context, text_content, status_message)
            
        except Exception as e:
            logger.error(f"Error: {e}")
            await status_message.edit_text(f"❌ *خطأ:* {str(e)[:100]}", parse_mode=ParseMode.MARKDOWN)
    
    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        text = update.message.text
        
        if len(text) < 50:
            await update.message.reply_text("📝 *الرجاء إرسال نص أطول* (50 حرف على الأقل)", parse_mode=ParseMode.MARKDOWN)
            return
        
        status_message = await update.message.reply_text("🔍 *جاري تحليل النص...*", parse_mode=ParseMode.MARKDOWN)
        await self.process_content(update, context, text, status_message)
    
    async def process_content(self, update: Update, context: ContextTypes.DEFAULT_TYPE, 
                             text: str, status_message):
        try:
            await status_message.edit_text("🧠 *جاري تحليل المحتوى...*", parse_mode=ParseMode.MARKDOWN)
            analyzed_content = await self.analyzer.analyze_content(text)
            
            await status_message.edit_text("🎨 *جاري إنشاء البطاقات...*", parse_mode=ParseMode.MARKDOWN)
            image_paths = await self.image_gen.generate_all_cards(analyzed_content)
            
            await status_message.edit_text("🎙️ *جاري تحويل النص إلى صوت...*", parse_mode=ParseMode.MARKDOWN)
            audio_files = await self.audio_gen.generate_all_audio(analyzed_content)
            
            await status_message.edit_text("🎬 *جاري تجميع الفيديو...*", parse_mode=ParseMode.MARKDOWN)
            video_path = self.video_maker.create_video(image_paths, audio_files, analyzed_content)
            
            if video_path and os.path.exists(video_path):
                await status_message.edit_text("📤 *جاري إرسال الفيديو...*", parse_mode=ParseMode.MARKDOWN)
                
                info_text = f"📹 *{analyzed_content['title']}*\nعدد الأقسام: {len(analyzed_content['sections'])}"
                
                with open(video_path, 'rb') as video_file:
                    await update.message.reply_video(
                        video=video_file,
                        caption=info_text,
                        parse_mode=ParseMode.MARKDOWN
                    )
                
                await status_message.delete()
            else:
                # إرسال الصور كبديل
                await status_message.edit_text("📸 *جاري إرسال البطاقات...*", parse_mode=ParseMode.MARKDOWN)
                for img_path in image_paths:
                    if os.path.exists(img_path):
                        with open(img_path, 'rb') as img_file:
                            await update.message.reply_photo(photo=img_file)
                await status_message.delete()
            
        except Exception as e:
            logger.error(f"Process error: {e}")
            await status_message.edit_text(f"❌ *خطأ:* {str(e)[:100]}", parse_mode=ParseMode.MARKDOWN)
        
        finally:
            cleanup_temp_files()
    
    def run(self):
        app = Application.builder().token(self.token).build()
        app.add_handler(CommandHandler("start", self.start))
        app.add_handler(MessageHandler(filters.Document.ALL, self.handle_document))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text))
        
        logger.info("Bot started!")
        app.run_polling(allowed_updates=Update.ALL_TYPES)

# ============== Entry Point ==============
if __name__ == "__main__":
    TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    if not TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not set!")
        exit(1)
    
    bot = LectureBot(TOKEN)
    bot.run()
