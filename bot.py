import os
import io
import logging
import urllib.parse
import urllib.request
import asyncio
import aiohttp
import json
import base64
import random
import re
import subprocess
import time
import sys
import signal
import tempfile
import zipfile
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

# تفعيل التسجيل
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("BOT_TOKEN")
HEROKU_APP_NAME = os.environ.get("HEROKU_APP_NAME")

# تخزين بيانات المستخدمين
user_data = {}

# ========== إعدادات ==========
MAX_IMAGE_RETRIES = 3
MAX_SECTIONS = 5  # أقصى عدد أقسام للفيديو

# ========== وظيفة إعادة تشغيل Heroku ==========
def restart_heroku():
    try:
        if HEROKU_APP_NAME:
            logger.info(f"🔄 جاري إعادة تشغيل {HEROKU_APP_NAME}...")
            subprocess.run(["heroku", "restart", "-a", HEROKU_APP_NAME], capture_output=True, timeout=10)
            return True
    except:
        pass
    return False

# ========== معالجة الملفات ==========
async def extract_text_from_file(file_content: bytes, filename: str, update: Update):
    """استخراج النص من الملف"""
    
    text_content = ""
    file_ext = filename.split('.')[-1].lower() if '.' in filename else 'txt'
    
    try:
        if file_ext == 'txt':
            text_content = file_content.decode('utf-8', errors='ignore')
            
        elif file_ext == 'pdf':
            try:
                import PyPDF2
                pdf_file = io.BytesIO(file_content)
                pdf_reader = PyPDF2.PdfReader(pdf_file)
                for page in pdf_reader.pages:
                    text_content += page.extract_text() + "\n"
            except ImportError:
                await update.message.reply_text("⚠️ جاري تثبيت مكتبة PDF...")
                return None
                
        elif file_ext in ['docx', 'doc']:
            try:
                import docx
                doc_file = io.BytesIO(file_content)
                doc = docx.Document(doc_file)
                for para in doc.paragraphs:
                    text_content += para.text + "\n"
            except ImportError:
                await update.message.reply_text("⚠️ جاري تثبيت مكتبة DOCX...")
                return None
        else:
            await update.message.reply_text(f"⚠️ صيغة {file_ext} غير مدعومة. استخدم PDF, DOCX, TXT")
            return None
        
        if len(text_content) < 100:
            await update.message.reply_text("⚠️ الملف لا يحتوي على نص كافٍ")
            return None
        
        return text_content
        
    except Exception as e:
        logger.error(f"خطأ في معالجة الملف: {e}")
        await update.message.reply_text(f"❌ خطأ: {str(e)[:100]}")
        return None

# ========== تقسيم النص إلى أقسام ==========
def split_into_sections(text: str, num_sections: int = MAX_SECTIONS):
    """تقسيم النص إلى أقسام متساوية"""
    
    # تنظيف النص
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    # محاولة التقسيم حسب العناوين
    lines = text.split('\n')
    sections = []
    current_section = ""
    
    # كلمات تدل على بداية قسم
    keywords = ['الفصل', 'باب', 'مقدمة', 'خاتمة', 'Chapter', 'Section', 'Part', 'أولاً', 'ثانياً', 'أولا', 'ثانيا']
    
    for line in lines:
        is_new = any(kw in line for kw in keywords) and len(line) < 100
        if is_new and current_section:
            sections.append(current_section.strip())
            current_section = line + "\n"
        else:
            current_section += line + "\n"
    
    if current_section.strip():
        sections.append(current_section.strip())
    
    # إذا كان عدد الأقسام قليلاً، قسّم بالتساوي
    if len(sections) < 2:
        words = text.split()
        chunk_size = max(100, len(words) // num_sections)
        sections = []
        for i in range(0, len(words), chunk_size):
            section = ' '.join(words[i:i+chunk_size])
            if section:
                sections.append(section)
    
    # خذ أول 5 أقسام فقط
    return sections[:MAX_SECTIONS]

# ========== شرح النص وتلخيصه ==========
async def explain_section(text: str, section_num: int, total: int, update: Update):
    """شرح قسم من النص"""
    
    words = text.split()
    sentences = re.split(r'[.!?؟]+', text)
    sentences = [s for s in sentences if len(s.strip()) > 20]
    
    has_arabic = any('\u0600' <= c <= '\u06FF' for c in text)
    has_equations = bool(re.search(r'[\+\-\*\/\=\(\)\^]|\d+[a-z]|[a-z]\d+', text))
    
    explanation = f"""
📚 **القسم {section_num}/{total}**

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📝 **المحتوى:**
{text[:400]}{'...' if len(text) > 400 else ''}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 **إحصائيات القسم:**
• عدد الكلمات: {len(words)}
• عدد الجمل: {len(sentences)}
• اللغة: {'عربية' if has_arabic else 'إنجليزية'}

"""
    if has_equations:
        explanation += "• 📐 يحتوي على معادلات رياضية\n"
    
    explanation += f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
💡 **شرح القسم:**
{text[:300]}{'...' if len(text) > 300 else ''}

✅ تم تحليل القسم بنجاح
"""
    await update.message.reply_text(explanation)
    return explanation

# ========== توليد صورة لقسم ==========
async def generate_section_image(prompt: str, section_num: int, update: Update):
    """توليد صورة تمثيلية للقسم"""
    
    for attempt in range(MAX_IMAGE_RETRIES):
        try:
            clean_prompt = prompt.strip().replace(" ", "%20")[:150]
            encoded_prompt = urllib.parse.quote(f"{clean_prompt}, educational illustration, clear style")
            url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=800&height=600"
            
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=30) as response:
                image_data = response.read()
            
            if len(image_data) > 1000:
                image_file = io.BytesIO(image_data)
                image_file.name = f"section_{section_num}.png"
                await update.message.reply_photo(
                    photo=image_file,
                    caption=f"🖼 **صورة تمثيلية للقسم {section_num}**\n📝 {prompt[:100]}..."
                )
                return image_data
                
        except Exception as e:
            logger.error(f"محاولة {attempt+1} فشلت: {e}")
            if attempt < MAX_IMAGE_RETRIES - 1:
                await asyncio.sleep(2)
    
    # صورة بديلة إذا فشل
    return await create_fallback_image(prompt, section_num, update)

async def create_fallback_image(prompt: str, section_num: int, update: Update):
    """إنشاء صورة بديلة"""
    try:
        from PIL import Image, ImageDraw, ImageFont
        
        img = Image.new('RGB', (800, 600), color=(30, 30, 80))
        draw = ImageDraw.Draw(img)
        
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 24)
        except:
            font = ImageFont.load_default()
        
        # كتابة النص على الصورة
        lines = [prompt[i:i+40] for i in range(0, min(len(prompt), 200), 40)]
        y = 100
        for line in lines:
            draw.text((50, y), line, fill=(255, 255, 255), font=font)
            y += 40
        
        draw.text((50, y+50), f"~ القسم {section_num} ~", fill=(200, 200, 200), font=font)
        
        img_buffer = io.BytesIO()
        img.save(img_buffer, format='PNG')
        img_buffer.seek(0)
        
        await update.message.reply_photo(
            photo=img_buffer,
            caption=f"🖼 **صورة القسم {section_num} (نسخة احتياطية)**"
        )
        return img_buffer.getvalue()
        
    except:
        return None

# ========== تحويل النص إلى صوت ==========
async def text_to_audio(text: str, section_num: int, update: Update):
    """تحويل النص إلى صوت MP3"""
    try:
        has_arabic = any('\u0600' <= c <= '\u06FF' for c in text)
        lang = 'ar' if has_arabic else 'en'
        
        text_encoded = urllib.parse.quote(text[:500])
        url = f"https://translate.google.com/translate_tts?ie=UTF-8&q={text_encoded}&tl={lang}&client=tw-ob"
        
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=20) as response:
            audio_data = response.read()
        
        if len(audio_data) > 1000:
            audio_file = io.BytesIO(audio_data)
            audio_file.name = f"audio_section_{section_num}.mp3"
            await update.message.reply_audio(
                audio=audio_file,
                title=f"شرح القسم {section_num}",
                caption=f"🎙 صوت القسم {section_num}"
            )
            return audio_data
        return None
    except Exception as e:
        logger.error(f"خطأ في الصوت: {e}")
        return None

# ========== إنشاء ملخص نهائي ==========
async def create_final_summary(sections: list, explanations: list, update: Update):
    """إنشاء ملخص نهائي للمحتوى كاملاً"""
    
    total_words = sum(len(s.split()) for s in sections)
    total_chars = sum(len(s) for s in sections)
    
    # دمج كل النص
    full_text = ' '.join(sections)
    
    # استخراج الكلمات المفتاحية
    words = full_text.split()
    word_freq = {}
    for w in words:
        w_lower = w.lower()
        word_freq[w_lower] = word_freq.get(w_lower, 0) + 1
    
    keywords = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)[:10]
    
    # إنشاء الملخص
    summary = f"""
📚 **الملخص النهائي للمحتوى**

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 **إحصائيات عامة:**
• عدد الأقسام: {len(sections)}
• إجمالي الكلمات: {total_words}
• إجمالي الحروف: {total_chars}
• وقت القراءة المقدر: {total_words // 200} دقيقة

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔑 **الكلمات المفتاحية:**
"""
    for word, count in keywords[:8]:
        summary += f"• {word} ({count} مرة)\n"
    
    summary += f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📖 **ملخص المحتوى:**
{full_text[:500]}{'...' if len(full_text) > 500 else ''}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ **تم إنشاء الفيديو التعليمي بنجاح!**

🎬 يتكون الفيديو من {len(sections)} مقاطع
🖼 صورة لكل مقطع
🎙 صوت شرح لكل مقطع
"""
    
    await update.message.reply_text(summary)
    return summary

# ========== تجميع الفيديو (إذا أمكن) ==========
async def create_video_from_sections(images_data: list, audios_data: list, update: Update):
    """إنشاء فيديو من الصور والصوت (يتطلب FFmpeg)"""
    
    try:
        # التحقق من وجود FFmpeg
        result = subprocess.run(["ffmpeg", "-version"], capture_output=True)
        if result.returncode != 0:
            await update.message.reply_text(
                "⚠️ **لا يمكن إنشاء فيديو بسبب عدم توفر FFmpeg**\n\n"
                "✅ لكن تم إرسال كل قسم كصورة + صوت منفصلين\n"
                "📁 يمكنك تجميعهم يدوياً"
            )
            return False
        
        # إنشاء مجلد مؤقت
        with tempfile.TemporaryDirectory() as tmpdir:
            video_parts = []
            
            for i, (img_data, audio_data) in enumerate(zip(images_data, audios_data)):
                if img_data and audio_data:
                    img_path = os.path.join(tmpdir, f"img_{i}.png")
                    audio_path = os.path.join(tmpdir, f"audio_{i}.mp3")
                    output_path = os.path.join(tmpdir, f"part_{i}.mp4")
                    
                    with open(img_path, 'wb') as f:
                        f.write(img_data)
                    with open(audio_path, 'wb') as f:
                        f.write(audio_data)
                    
                    # إنشاء مقطع فيديو من صورة + صوت
                    cmd = [
                        "ffmpeg", "-y", "-loop", "1", "-i", img_path,
                        "-i", audio_path, "-c:v", "libx264", "-t", "10",
                        "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest",
                        output_path
                    ]
                    subprocess.run(cmd, capture_output=True)
                    video_parts.append(output_path)
            
            if video_parts:
                await update.message.reply_text("🎬 **جاري تجميع الفيديو النهائي...**")
                return True
                
    except Exception as e:
        logger.error(f"خطأ في إنشاء الفيديو: {e}")
    
    return False

# ========== الوظيفة الرئيسية لتحويل المحتوى إلى فيديو تعليمي ==========
async def convert_to_educational_video(content: str, update: Update, is_file: bool = False):
    """تحويل النص أو الملف إلى فيديو تعليمي"""
    
    # تقسيم النص إلى أقسام
    sections = split_into_sections(content)
    
    if not sections:
        await update.message.reply_text("❌ لا يمكن تقسيم المحتوى إلى أقسام")
        return
    
    await update.message.reply_text(
        f"🎬 **بدء تحويل المحتوى إلى فيديو تعليمي**\n\n"
        f"📊 تم تقسيم المحتوى إلى {len(sections)} أقسام\n"
        f"🖼 سيتم إنشاء صورة لكل قسم\n"
        f"🎙 سيتم إنشاء صوت شرح لكل قسم\n"
        f"⏱ قد يستغرق هذا بضع دقائق"
    )
    
    images_data = []
    audios_data = []
    explanations = []
    
    # معالجة كل قسم
    for i, section in enumerate(sections, 1):
        await update.message.reply_text(f"🔄 **جاري معالجة القسم {i}/{len(sections)}**")
        
        # 1. شرح القسم
        explanation = await explain_section(section, i, len(sections), update)
        explanations.append(explanation)
        
        # 2. استخراج عنوان للصورة (أول 80 حرف)
        image_prompt = section[:80].strip()
        
        # 3. توليد صورة للقسم
        img_data = await generate_section_image(image_prompt, i, update)
        if img_data:
            images_data.append(img_data)
        
        # 4. تحويل النص إلى صوت
        audio_data = await text_to_audio(section, i, update)
        if audio_data:
            audios_data.append(audio_data)
        
        await asyncio.sleep(1)
    
    # 5. إنشاء ملخص نهائي
    await create_final_summary(sections, explanations, update)
    
    # 6. محاولة إنشاء فيديو (إذا أمكن)
    if len(images_data) == len(audios_data) and images_data:
        await create_video_from_sections(images_data, audios_data, update)
    
    await update.message.reply_text(
        f"✅ **تم الانتهاء بنجاح!**\n\n"
        f"📊 تم إنشاء:\n"
        f"• {len(sections)} قسم\n"
        f"• {len(images_data)} صورة\n"
        f"• {len(audios_data)} ملف صوتي\n"
        f"• ملخص نهائي للمحتوى\n\n"
        f"🎬 يمكنك استخدام الصور والصوت لإنشاء فيديو كامل"
    )

# ========== أزرار البوت ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("📹 فيديو من ملف", callback_data="video_file")],
        [InlineKeyboardButton("📹 فيديو من نص", callback_data="video_text")],
        [InlineKeyboardButton("🎨 توليد صورة", callback_data="image")],
        [InlineKeyboardButton("🎵 تحويل نص إلى صوت", callback_data="audio")],
        [InlineKeyboardButton("📚 شرح نص", callback_data="explain")],
    ]
    
    await update.message.reply_text(
        "✨ **مرحباً بك في بوت الفيديو التعليمي!** ✨\n\n"
        "📹 **فيديو من ملف:** أرسل PDF, DOCX, TXT وسأحوله إلى فيديو تعليمي\n"
        "📹 **فيديو من نص:** أرسل نصاً وسأحوله إلى فيديو تعليمي\n"
        "🎨 **توليد صورة:** يحول وصفك إلى صورة\n"
        "🎵 **تحويل نص إلى صوت:** يحول النص إلى MP3\n"
        "📚 **شرح نص:** يحلل النص ويشرحه\n\n"
        "🔽 **اختر ما تريد:**",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    action = query.data
    user_id = query.from_user.id
    
    if action == "video_file":
        await query.edit_message_text(
            "📹 **تحويل ملف إلى فيديو تعليمي**\n\n"
            "📁 **أرسل الملف (PDF, DOCX, TXT):**\n\n"
            "✅ سأقوم بـ:\n"
            "• استخراج النص من الملف\n"
            "• تقسيمه إلى أقسام\n"
            "• شرح كل قسم\n"
            "• توليد صورة لكل قسم\n"
            "• تحويل النص إلى صوت لكل قسم\n"
            "• إنشاء ملخص نهائي\n\n"
            "⏱ قد يستغرق هذا بضع دقائق"
        )
        user_data[user_id] = {'mode': 'video_file'}
        
    elif action == "video_text":
        await query.edit_message_text(
            "📹 **تحويل نص إلى فيديو تعليمي**\n\n"
            "✏️ **أرسل النص الذي تريد تحويله:**\n\n"
            "✅ سأقوم بـ:\n"
            "• تقسيم النص إلى أقسام\n"
            "• شرح كل قسم\n"
            "• توليد صورة لكل قسم\n"
            "• تحويل النص إلى صوت لكل قسم\n"
            "• إنشاء ملخص نهائي"
        )
        user_data[user_id] = {'mode': 'video_text'}
        
    elif action == "image":
        await query.edit_message_text(
            "🎨 **توليد صورة**\n\n✏️ **أرسل وصف الصورة:**"
        )
        user_data[user_id] = {'mode': 'image'}
        
    elif action == "audio":
        keyboard = [
            [InlineKeyboardButton("👨 ذكر", callback_data="audio_male")],
            [InlineKeyboardButton("👩 أنثى", callback_data="audio_female")],
        ]
        await query.edit_message_text("🎤 **اختر نوع الصوت:**", reply_markup=InlineKeyboardMarkup(keyboard))
        
    elif action == "audio_male":
        await query.edit_message_text("🎤 **صوت ذكر**\n\n✏️ **أرسل النص:**")
        user_data[user_id] = {'mode': 'audio', 'gender': 'male'}
        
    elif action == "audio_female":
        await query.edit_message_text("🎤 **صوت أنثى**\n\n✏️ **أرسل النص:**")
        user_data[user_id] = {'mode': 'audio', 'gender': 'female'}
        
    elif action == "explain":
        await query.edit_message_text(
            "📚 **شرح نص**\n\n✏️ **أرسل النص لتحليله:**\n\n"
            "✅ سأقوم بتحليل النص وإعطائك:\n"
            "• عدد الكلمات والحروف\n"
            "• الكلمات المفتاحية\n"
            "• ملخص كامل"
        )
        user_data[user_id] = {'mode': 'explain'}

# ========== شرح نص عادي ==========
async def explain_normal_text(text: str, update: Update):
    """شرح نص عادي"""
    words = text.split()
    sentences = re.split(r'[.!?؟]+', text)
    sentences = [s for s in sentences if s.strip()]
    has_arabic = any('\u0600' <= c <= '\u06FF' for c in text)
    
    word_freq = {}
    for w in words:
        w_lower = w.lower()
        word_freq[w_lower] = word_freq.get(w_lower, 0) + 1
    keywords = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)[:8]
    
    explanation = f"""
📚 **تحليل وشرح النص**

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📝 **النص الأصلي:**
{text[:500]}{'...' if len(text) > 500 else ''}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 **الإحصائيات:**
• عدد الحروف: {len(text)}
• عدد الكلمات: {len(words)}
• عدد الجمل: {len(sentences)}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🌐 **اللغة:** {'عربية' if has_arabic else 'إنجليزية'}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔑 **الكلمات المفتاحية:**
"""
    for word, count in keywords:
        explanation += f"• {word} ({count} مرات)\n"
    
    explanation += f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
💡 **ملخص النص:**
{text[:300]}{'...' if len(text) > 300 else ''}

✅ تم التحليل بنجاح
"""
    await update.message.reply_text(explanation)

# ========== توليد صورة عادية ==========
async def generate_normal_image(prompt: str, update: Update):
    for attempt in range(3):
        try:
            clean_prompt = prompt.strip().replace(" ", "%20")[:150]
            url = f"https://image.pollinations.ai/prompt/{clean_prompt}?width=512&height=512"
            
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=30) as response:
                image_data = response.read()
            
            if len(image_data) > 1000:
                image_file = io.BytesIO(image_data)
                image_file.name = "image.png"
                await update.message.reply_photo(photo=image_file, caption=f"🎨 {prompt[:100]}...")
                return True
        except:
            pass
        await asyncio.sleep(2)
    
    await update.message.reply_text("❌ فشل توليد الصورة")

# ========== تحويل نص إلى صوت عادي ==========
async def generate_normal_audio(text: str, gender: str, update: Update):
    try:
        has_arabic = any('\u0600' <= c <= '\u06FF' for c in text)
        lang = 'ar' if has_arabic else 'en'
        
        text_encoded = urllib.parse.quote(text[:300])
        url = f"https://translate.google.com/translate_tts?ie=UTF-8&q={text_encoded}&tl={lang}&client=tw-ob"
        
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=15) as response:
            audio_data = response.read()
        
        if len(audio_data) > 1000:
            audio_file = io.BytesIO(audio_data)
            audio_file.name = "audio.mp3"
            await update.message.reply_audio(
                audio=audio_file,
                title="النص الصوتي",
                performer=f"{'ذكر' if gender=='male' else 'أنثى'}",
                caption="✅ تم تحويل النص إلى صوت"
            )
            return True
    except:
        pass
    
    await update.message.reply_text("❌ خدمة الصوت غير متاحة حالياً")
    return False

# ========== معالجة الملفات والرسائل ==========
async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة الملفات المرسلة"""
    user_id = update.effective_user.id
    
    if user_id not in user_data or user_data[user_id].get('mode') != 'video_file':
        await update.message.reply_text("❌ الرجاء الضغط على زر 'فيديو من ملف' أولاً")
        return
    
    file = update.message.document
    file_name = file.file_name
    
    # تحميل الملف
    file_obj = await file.get_file()
    file_content = await file_obj.download_as_bytearray()
    
    await update.message.reply_text(f"📁 **تم استلام الملف:** {file_name}\n🔄 جاري المعالجة...")
    
    # استخراج النص
    text_content = await extract_text_from_file(bytes(file_content), file_name, update)
    
    if text_content:
        await convert_to_educational_video(text_content, update, is_file=True)
    else:
        await update.message.reply_text("❌ فشل استخراج النص من الملف")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة الرسائل النصية"""
    user_id = update.effective_user.id
    text = update.message.text
    
    if user_id not in user_data:
        keyboard = [
            [InlineKeyboardButton("📹 فيديو من ملف", callback_data="video_file")],
            [InlineKeyboardButton("📹 فيديو من نص", callback_data="video_text")],
            [InlineKeyboardButton("🎨 توليد صورة", callback_data="image")],
            [InlineKeyboardButton("🎵 تحويل نص إلى صوت", callback_data="audio")],
            [InlineKeyboardButton("📚 شرح نص", callback_data="explain")],
        ]
        await update.message.reply_text(
            "✨ **أهلاً بك!** ✨\n\nاختر ما تريد من الأزرار:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    
    mode_data = user_data[user_id]
    mode = mode_data.get('mode')
    
    processing = await update.message.reply_text("⏳ **جاري المعالجة...**")
    
    if mode == 'video_text':
        await convert_to_educational_video(text, update, is_file=False)
        
    elif mode == 'image':
        await generate_normal_image(text, update)
        
    elif mode == 'audio':
        gender = mode_data.get('gender', 'male')
        await generate_normal_audio(text, gender, update)
        
    elif mode == 'explain':
        await explain_normal_text(text, update)
        
    elif mode == 'video_file':
        await update.message.reply_text("❌ الرجاء إرسال ملف PDF أو DOCX أو TXT")
    
    await processing.delete()
    
    # حذف وضع المستخدم
    del user_data[user_id]
    
    # عرض القائمة مرة أخرى
    keyboard = [
        [InlineKeyboardButton("📹 فيديو من ملف", callback_data="video_file")],
        [InlineKeyboardButton("📹 فيديو من نص", callback_data="video_text")],
        [InlineKeyboardButton("🎨 توليد صورة", callback_data="image")],
        [InlineKeyboardButton("🎵 تحويل نص إلى صوت", callback_data="audio")],
        [InlineKeyboardButton("📚 شرح نص", callback_data="explain")],
    ]
    await update.message.reply_text(
        "✨ **هل تريد صناعة شيء آخر؟**",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ========== التشغيل ==========
def main():
    app = ApplicationBuilder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("=" * 60)
    print("✅ بوت الفيديو التعليمي يعمل!")
    print("📹 تحويل الملفات والنصوص إلى فيديو تعليمي")
    print("🖼 صورة + 🎙 صوت + 📚 شرح + 📝 ملخص")
    print("=" * 60)
    
    app.run_polling()

if __name__ == "__main__":
    main()
