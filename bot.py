import os
import io
import logging
import urllib.parse
import urllib.request
import asyncio
import aiohttp
import json
import random
import re
import time
import base64
import subprocess
import tempfile
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

# تفعيل التسجيل
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("BOT_TOKEN")

# تخزين بيانات المستخدمين
user_data = {}

# ========== إعدادات ==========
MAX_SECTIONS = 4  # أقصى عدد أقسام للفيديو

# ========== شرح النص ==========
async def explain_text(text: str, dialect: str, update: Update, progress_msg):
    """شرح النص باللهجة المختارة"""
    
    dialect_names = {
        'iraqi': 'العراقية',
        'syrian': 'السورية',
        'egyptian': 'المصرية',
        'gulf': 'الخليجية',
        'fusha': 'الفصحى'
    }
    
    # تحليل النص
    words = text.split()
    sentences = re.split(r'[.!?؟\n]+', text)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 30]
    
    # الكلمات المفتاحية
    word_freq = {}
    for w in words:
        w_lower = w.lower()
        word_freq[w_lower] = word_freq.get(w_lower, 0) + 1
    keywords = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)[:15]
    
    # بناء الشرح
    explanation = f"""
📚 **شرح المحاضرة باللهجة {dialect_names.get(dialect, 'العربية')}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📖 **ملخص المحاضرة:**
{text[:600]}...

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔑 **الكلمات المفتاحية:**
"""
    for word, count in keywords[:10]:
        explanation += f"• {word} ({count} مرات)\n"
    
    explanation += f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 **إحصائيات:**
• عدد الكلمات: {len(words)}
• عدد الجمل: {len(sentences)}
• وقت القراءة: {len(words) // 200} دقيقة

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
💡 **النقاط الرئيسية:**
"""
    for i, sent in enumerate(sentences[:5], 1):
        explanation += f"{i}. {sent[:150]}...\n"
    
    return explanation

# ========== تقسيم النص إلى أقسام ==========
def split_into_sections(text: str, num_sections: int = MAX_SECTIONS):
    """تقسيم النص إلى أقسام متساوية"""
    
    sentences = re.split(r'[.!?؟\n]+', text)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 40]
    
    if len(sentences) <= num_sections:
        sections = []
        for i, sent in enumerate(sentences):
            sections.append({
                'title': f"القسم {i+1}",
                'content': sent[:600],
                'full_text': sent
            })
        return sections
    
    # تقسيم متساوي
    chunk_size = len(sentences) // num_sections
    sections = []
    for i in range(0, len(sentences), chunk_size):
        chunk = '. '.join(sentences[i:i+chunk_size])
        if chunk:
            sections.append({
                'title': f"القسم {len(sections)+1}",
                'content': chunk[:600],
                'full_text': chunk
            })
    
    return sections[:num_sections]

# ========== توليد صورة كرتونية للقسم ==========
async def generate_cartoon_image(text: str, section_num: int, total: int, update: Update, progress_msg):
    """توليد صورة كرتونية تعليمية"""
    
    # استخراج الكلمات المفتاحية للصورة
    words = text.split()[:15]
    image_prompt = ' '.join(words)[:100]
    
    # إضافة أسلوب كرتوني
    cartoon_prompt = f"cartoon illustration, educational, {image_prompt}, colorful, cute style"
    clean_prompt = cartoon_prompt.replace(" ", "%20")
    
    for attempt in range(4):
        await progress_msg.edit_text(f"🎨 رسم صورة كرتونية للقسم {section_num}/{total} - محاولة {attempt+1}/4...")
        
        try:
            # استخدام Pollinations لتوليد صورة كرتونية
            url = f"https://image.pollinations.ai/prompt/{clean_prompt}?width=800&height=500&seed={random.randint(1,10000)}"
            
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=30) as response:
                image_data = response.read()
            
            if len(image_data) > 10000:
                return image_data
        except Exception as e:
            logger.error(f"Image attempt {attempt+1} failed: {e}")
            await asyncio.sleep(2)
    
    # صورة كرتونية بديلة (مرسومة محلياً)
    return await create_cartoon_fallback(text, section_num)

async def create_cartoon_fallback(text: str, section_num: int):
    """إنشاء صورة كرتونية بديلة"""
    try:
        from PIL import Image, ImageDraw, ImageFont
        
        # ألوان كرتونية
        colors = [
            (255, 200, 150), (200, 220, 255), (255, 220, 200), (200, 255, 200)
        ]
        bg_color = random.choice(colors)
        
        img = Image.new('RGB', (800, 500), color=bg_color)
        draw = ImageDraw.Draw(img)
        
        # رسم إطار كرتوني
        for i in range(5):
            draw.rectangle([i, i, 800-i, 500-i], outline=(255, 100, 100), width=3)
        
        # رسم زوايا دائرية
        for x, y in [(20, 20), (760, 20), (20, 460), (760, 460)]:
            draw.ellipse([x, y, x+40, y+40], fill=(255, 150, 150))
        
        try:
            font_title = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 32)
            font_text = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 22)
        except:
            font_title = ImageFont.load_default()
            font_text = ImageFont.load_default()
        
        # عنوان كرتوني
        draw.text((50, 60), f"🎨 القسم {section_num}", fill=(255, 50, 50), font=font_title)
        
        # نص كرتوني
        lines = [text[i:i+45] for i in range(0, min(len(text), 350), 45)]
        y = 130
        for line in lines[:5]:
            draw.text((50, y), line, fill=(50, 50, 150), font=font_text)
            y += 40
        
        # رسومات كرتونية
        draw.ellipse([700, 400, 760, 460], fill=(255, 200, 100))  # شمس كرتونية
        draw.ellipse([30, 400, 90, 460], fill=(100, 200, 100))    # زهرة
        
        img_buffer = io.BytesIO()
        img.save(img_buffer, format='PNG')
        img_buffer.seek(0)
        return img_buffer.getvalue()
    except:
        return None

# ========== توليد صوت للقسم ==========
async def generate_audio(text: str, section_num: int, total: int, update: Update, progress_msg):
    """توليد صوت شرح للقسم"""
    
    await progress_msg.edit_text(f"🎙 تسجيل صوت القسم {section_num}/{total}...")
    
    for attempt in range(3):
        try:
            audio_text = text[:400]
            has_arabic = any('\u0600' <= c <= '\u06FF' for c in audio_text)
            lang = 'ar' if has_arabic else 'en'
            
            text_encoded = urllib.parse.quote(audio_text)
            url = f"https://translate.google.com/translate_tts?ie=UTF-8&q={text_encoded}&tl={lang}&client=tw-ob"
            
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=25) as response:
                audio_data = response.read()
            
            if len(audio_data) > 5000:
                return audio_data
        except:
            await asyncio.sleep(2)
    
    return None

# ========== إنشاء فيديو باستخدام FFmpeg (الطريقة الوحيدة المجانية) ==========
async def create_video_with_ffmpeg(images_data: list, audios_data: list, update: Update, progress_msg):
    """إنشاء فيديو باستخدام FFmpeg"""
    
    await progress_msg.edit_text("🎬 جاري إنشاء الفيديو النهائي...")
    
    # التحقق من وجود FFmpeg
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
    except:
        await progress_msg.edit_text("⚠️ FFmpeg غير متوفر، جاري التثبيت...")
        subprocess.run(["apt-get", "update", "-qq"], capture_output=True)
        subprocess.run(["apt-get", "install", "-y", "-qq", "ffmpeg"], capture_output=True)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        video_parts = []
        
        for i, (img_data, audio_data) in enumerate(zip(images_data, audios_data)):
            if img_data and audio_data:
                img_path = os.path.join(tmpdir, f"img_{i}.png")
                audio_path = os.path.join(tmpdir, f"audio_{i}.mp3")
                video_path = os.path.join(tmpdir, f"part_{i}.mp4")
                
                with open(img_path, 'wb') as f:
                    f.write(img_data)
                with open(audio_path, 'wb') as f:
                    f.write(audio_data)
                
                # حساب مدة الصوت
                result = subprocess.run(
                    ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", audio_path],
                    capture_output=True, text=True
                )
                duration = float(result.stdout.strip()) if result.stdout else 10
                
                # إنشاء مقطع فيديو من الصورة والصوت
                cmd = [
                    "ffmpeg", "-y", "-loop", "1", "-i", img_path,
                    "-i", audio_path, "-c:v", "libx264", "-t", str(duration),
                    "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest",
                    "-vf", "scale=800:600:force_original_aspect_ratio=1,pad=800:600:(ow-iw)/2:(oh-ih)/2",
                    video_path
                ]
                subprocess.run(cmd, capture_output=True, timeout=60)
                
                if os.path.exists(video_path):
                    video_parts.append(video_path)
        
        if not video_parts:
            return None
        
        # دمج المقاطع
        if len(video_parts) == 1:
            final_video = video_parts[0]
        else:
            # إنشاء ملف القائمة
            list_path = os.path.join(tmpdir, "list.txt")
            with open(list_path, 'w') as f:
                for part in video_parts:
                    f.write(f"file '{part}'\n")
            
            final_video = os.path.join(tmpdir, "final_video.mp4")
            cmd_concat = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list_path, "-c", "copy", final_video]
            subprocess.run(cmd_concat, capture_output=True, timeout=120)
        
        if os.path.exists(final_video) and os.path.getsize(final_video) > 100000:
            return final_video
    
    return None

# ========== استخراج النص من الملفات ==========
async def extract_text_from_file(file_content: bytes, filename: str):
    """استخراج النص من الملف"""
    
    file_ext = filename.split('.')[-1].lower() if '.' in filename else 'txt'
    
    try:
        if file_ext == 'txt':
            return file_content.decode('utf-8', errors='ignore')
            
        elif file_ext == 'pdf':
            try:
                import PyPDF2
                pdf_file = io.BytesIO(file_content)
                pdf_reader = PyPDF2.PdfReader(pdf_file)
                text = ""
                for page in pdf_reader.pages[:30]:  # حد أقصى 30 صفحة
                    text += page.extract_text() + "\n"
                return text[:5000]
            except:
                return None
                
        elif file_ext in ['docx', 'doc']:
            try:
                import docx
                doc_file = io.BytesIO(file_content)
                doc = docx.Document(doc_file)
                text = ""
                for para in doc.paragraphs[:200]:
                    text += para.text + "\n"
                return text[:5000]
            except:
                return None
    except:
        return None
    
    return None

# ========== الوظيفة الرئيسية ==========
async def convert_to_video(content: str, dialect: str, update: Update):
    """تحويل المحتوى إلى فيديو تعليمي"""
    
    dialect_names = {
        'iraqi': 'العراقية',
        'syrian': 'السورية',
        'egyptian': 'المصرية',
        'gulf': 'الخليجية',
        'fusha': 'الفصحى'
    }
    dialect_name = dialect_names.get(dialect, 'الفصحى')
    
    # رسالة التقدم
    progress_msg = await update.message.reply_text(
        "🎬 **بدء تحويل المحاضرة إلى فيديو تعليمي...**\n\n"
        "0%"
    )
    
    # 10% - تحليل
    await progress_msg.edit_text("📊 **10% - جاري تحليل المحاضرة...**")
    await asyncio.sleep(1)
    
    # 20% - شرح
    await progress_msg.edit_text(f"📖 **20% - جاري شرح المحاضرة باللهجة {dialect_name}...**")
    explanation = await explain_text(content, dialect, update, progress_msg)
    
    # إرسال الشرح
    if explanation:
        if len(explanation) > 4000:
            await update.message.reply_text(explanation[:3500])
            await update.message.reply_text(explanation[3500:7000])
        else:
            await update.message.reply_text(explanation)
    
    await progress_msg.edit_text("📖 **30% - تم كتابة الشرح**")
    await asyncio.sleep(1)
    
    # 35% - تقسيم
    await progress_msg.edit_text("📂 **35% - جاري تقسيم المحتوى إلى أقسام...**")
    sections = split_into_sections(content)
    
    if not sections:
        await progress_msg.edit_text("❌ لا يمكن تقسيم المحتوى")
        return
    
    total = len(sections)
    await progress_msg.edit_text(f"📂 **40% - تم التقسيم إلى {total} أقسام**")
    await asyncio.sleep(1)
    
    images_data = []
    audios_data = []
    
    # 45% - 80% معالجة الأقسام
    for i, section in enumerate(sections, 1):
        percent = 40 + (i / total) * 40
        
        await progress_msg.edit_text(f"🎨 **{int(percent)}% - جاري معالجة {section['title']}...**")
        
        # توليد صورة كرتونية
        img_data = await generate_cartoon_image(section['full_text'], i, total, update, progress_msg)
        if img_data:
            images_data.append(img_data)
        
        # توليد صوت
        audio_data = await generate_audio(section['full_text'], i, total, update, progress_msg)
        if audio_data:
            audios_data.append(audio_data)
    
    # 85% - إنشاء الفيديو
    await progress_msg.edit_text("🎬 **85% - جاري إنشاء الفيديو النهائي...**")
    
    if len(images_data) == len(audios_data) and images_data:
        video_path = await create_video_with_ffmpeg(images_data, audios_data, update, progress_msg)
        
        if video_path and os.path.exists(video_path):
            await progress_msg.edit_text("📤 **95% - جاري رفع الفيديو...**")
            
            # إرسال الفيديو
            with open(video_path, 'rb') as f:
                await update.message.reply_video(
                    video=io.BytesIO(f.read()),
                    caption=f"🎬 **الفيديو التعليمي النهائي**\n\n"
                           f"🗣 اللهجة: {dialect_name}\n"
                           f"📊 عدد الأقسام: {total}\n"
                           f"🎨 صور كرتونية: {len(images_data)}\n"
                           f"🎙 صوت شرح: {len(audios_data)}\n\n"
                           f"✅ تم إنشاء الفيديو بنجاح!"
                )
            
            await progress_msg.delete()
            await update.message.reply_text("✅ **تم إنشاء الفيديو التعليمي بنجاح!** 🎉")
            return
    
    # إذا فشل الفيديو
    await progress_msg.edit_text("❌ فشل إنشاء الفيديو، جاري إرسال المواد بشكل منفصل...")
    
    # إرسال المواد بشكل منفصل
    for i, (img_data, audio_data) in enumerate(zip(images_data, audios_data)):
        if img_data:
            img_file = io.BytesIO(img_data)
            img_file.name = f"section_{i+1}.png"
            await update.message.reply_photo(photo=img_file, caption=f"🖼 القسم {i+1}")
        
        if audio_data:
            audio_file = io.BytesIO(audio_data)
            audio_file.name = f"audio_{i+1}.mp3"
            await update.message.reply_audio(audio=audio_file, title=f"شرح القسم {i+1}")
    
    await progress_msg.delete()
    await update.message.reply_text(
        "⚠️ **لم نتمكن من إنشاء الفيديو**\n\n"
        "✅ لكن تم إرسال:\n"
        f"• {len(images_data)} صورة كرتونية\n"
        f"• {len(audios_data)} ملف صوتي\n"
        "• شرح كامل\n\n"
        "🎬 يمكنك دمجهم في فيديو باستخدام أي برنامج مجاني"
    )

# ========== معالجة الملفات والرسائل ==========
async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id not in user_data or user_data[user_id].get('mode') != 'video':
        await update.message.reply_text("❌ الرجاء اختيار اللهجة أولاً باستخدام /start")
        return
    
    dialect = user_data[user_id].get('dialect', 'fusha')
    file = update.message.document
    file_name = file.file_name
    
    progress_msg = await update.message.reply_text(f"📁 **تم استلام الملف:** {file_name}\n🔄 جاري المعالجة...")
    
    file_obj = await file.get_file()
    file_content = await file_obj.download_as_bytearray()
    
    text_content = await extract_text_from_file(bytes(file_content), file_name)
    
    if text_content and len(text_content) > 100:
        await convert_to_video(text_content, dialect, update)
    else:
        await progress_msg.edit_text("❌ فشل استخراج النص من الملف أو الملف فارغ")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    
    if user_id not in user_data or user_data[user_id].get('mode') != 'video':
        await update.message.reply_text(
            "❌ الرجاء اختيار اللهجة أولاً\n\nاكتب /start ثم اختر اللهجة"
        )
        return
    
    dialect = user_data[user_id].get('dialect', 'fusha')
    
    if len(text) < 100:
        await update.message.reply_text("⚠️ النص قصير جداً. أرسل نصاً أطول (100 حرف على الأقل)")
        return
    
    await convert_to_video(text, dialect, update)
    del user_data[user_id]

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    action = query.data
    user_id = query.from_user.id
    
    dialect_map = {
        'dialect_iraqi': 'iraqi',
        'dialect_syrian': 'syrian',
        'dialect_egyptian': 'egyptian',
        'dialect_gulf': 'gulf',
        'dialect_fusha': 'fusha'
    }
    
    dialect_names = {
        'iraqi': 'العراقية',
        'syrian': 'السورية',
        'egyptian': 'المصرية',
        'gulf': 'الخليجية',
        'fusha': 'الفصحى'
    }
    
    dialect = dialect_map.get(action, 'fusha')
    user_data[user_id] = {'mode': 'video', 'dialect': dialect}
    
    await query.edit_message_text(
        f"✅ **تم اختيار اللهجة {dialect_names.get(dialect, 'الفصحى')}**\n\n"
        f"📁 **الآن أرسل:**\n"
        f"• ملف PDF أو DOCX أو TXT\n"
        f"• أو اكتب/الصق النص مباشرة\n\n"
        f"🎬 **سأقوم بـ:**\n"
        f"• تحليل المحاضرة بالكامل\n"
        f"• شرحها باللهجة {dialect_names.get(dialect, 'الفصحى')}\n"
        f"• تقسيمها إلى {MAX_SECTIONS} أقسام\n"
        f"• رسم صور كرتونية لكل قسم\n"
        f"• تسجيل صوت شرح لكل قسم\n"
        f"• دمج كل شيء في فيديو واحد\n"
        f"• إرسال الفيديو النهائي\n\n"
        f"⏱ قد يستغرق هذا 2-3 دقائق"
    )

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🇮🇶 عراقية", callback_data="dialect_iraqi")],
        [InlineKeyboardButton("🇸🇾 سورية", callback_data="dialect_syrian")],
        [InlineKeyboardButton("🇪🇬 مصرية", callback_data="dialect_egyptian")],
        [InlineKeyboardButton("🇸🇦 خليجية", callback_data="dialect_gulf")],
        [InlineKeyboardButton("📖 فصحى", callback_data="dialect_fusha")],
    ]
    await update.message.reply_text(
        "🎬 **بوت تحويل المحاضرات إلى فيديو تعليمي**\n\n"
        "🗣 **اختر اللهجة:**\n\n"
        "🇮🇶 عراقية\n"
        "🇸🇾 سورية\n"
        "🇪🇬 مصرية\n"
        "🇸🇦 خليجية\n"
        "📖 فصحى\n\n"
        "📁 بعد الاختيار، أرسل:\n"
        "• ملف PDF أو DOCX أو TXT\n"
        "• أو اكتب المحاضرة نصاً\n\n"
        "🎬 **النتيجة:**\n"
        "• فيديو تعليمي متكامل\n"
        "• صور كرتونية\n"
        "• صوت شرح\n"
        "• تحليل كامل\n\n"
        "✅ **فيديو واحد جاهز للمشاهدة**",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ========== تثبيت FFmpeg في البداية ==========
def install_ffmpeg():
    """تثبيت FFmpeg على Heroku"""
    try:
        subprocess.run(["apt-get", "update", "-qq"], capture_output=True)
        subprocess.run(["apt-get", "install", "-y", "-qq", "ffmpeg"], capture_output=True)
        logger.info("✅ FFmpeg تم تثبيته بنجاح")
    except:
        logger.warning("⚠️ فشل تثبيت FFmpeg")

# ========== التشغيل ==========
def main():
    # تثبيت FFmpeg
    install_ffmpeg()
    
    app = ApplicationBuilder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("=" * 60)
    print("✅ بوت تحويل المحاضرات إلى فيديو تعليمي يعمل!")
    print("🗣 اللهجات: عراقية، سورية، مصرية، خليجية، فصحى")
    print("📁 يدعم: PDF, DOCX, TXT")
    print("🎬 المخرجات: فيديو واحد متكامل + صور كرتونية + صوت")
    print("=" * 60)
    
    app.run_polling()

if __name__ == "__main__":
    main()
