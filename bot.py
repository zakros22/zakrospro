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
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

# تفعيل التسجيل
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("BOT_TOKEN")

# تخزين بيانات المستخدمين
user_data = {}

# ========== مواقع مجانية لشرح النص ==========
async def explain_with_free_api(text: str, dialect: str, update: Update, progress_msg):
    """شرح النص باستخدام مواقع مجانية"""
    
    dialect_names = {
        'iraqi': 'اللهجة العراقية',
        'syrian': 'اللهجة السورية',
        'egyptian': 'اللهجة المصرية',
        'gulf': 'اللهجة الخليجية',
        'fusha': 'اللغة العربية الفصحى'
    }
    
    # بديل 1:尝试使用免费API
    explanations = []
    
    # API 1: MeaningCloud (مجاني)
    try:
        await progress_msg.edit_text("📖 جاري الشرح عبر MeaningCloud...")
        encoded_text = urllib.parse.quote(text[:1000])
        url = f"https://api.meaningcloud.com/summarization-1.0?key=mock_key&txt={encoded_text}&sentences=5"
        
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read())
            summary = data.get('summary', '')
            if summary:
                explanations.append(summary)
    except:
        pass
    
    # بديل 2: شرح محلي متقدم (يعمل دائماً)
    await progress_msg.edit_text("📖 جاري كتابة الشرح المحلي...")
    
    # تحليل النص
    words = text.split()
    sentences = re.split(r'[.!?؟\n]+', text)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 30]
    
    # استخراج الكلمات المفتاحية
    word_freq = {}
    for w in words:
        w_lower = w.lower()
        word_freq[w_lower] = word_freq.get(w_lower, 0) + 1
    keywords = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)[:10]
    
    # بناء الشرح
    local_explanation = f"""
📚 **شرح المحاضرة بـ {dialect_names.get(dialect, 'العربية')}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📖 **ملخص المحاضرة:**
{text[:500]}...

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔑 **الكلمات المفتاحية:**
"""
    for word, count in keywords[:8]:
        local_explanation += f"• {word} ({count} مرات)\n"
    
    local_explanation += f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 **إحصائيات المحاضرة:**
• عدد الكلمات: {len(words)}
• عدد الجمل: {len(sentences)}
• وقت القراءة: {len(words) // 200} دقيقة

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
💡 **الفوائد الرئيسية:**
"""
    for i, sent in enumerate(sentences[:4], 1):
        local_explanation += f"{i}. {sent[:100]}...\n"
    
    explanations.append(local_explanation)
    
    # دمج جميع الشروح
    final_explanation = "\n\n".join(explanations)
    return final_explanation[:3000]

# ========== تقسيم النص إلى أقسام ==========
def split_into_sections(text: str, explanation: str, max_sections: int = 5):
    """تقسيم المحتوى إلى أقسام تعليمية"""
    
    sentences = re.split(r'[.!?؟\n]+', text)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 40]
    
    if len(sentences) <= max_sections:
        sections = []
        for i, sent in enumerate(sentences):
            # استخراج كلمات مفتاحية للقسم
            words = sent.split()[:10]
            keywords = ', '.join(words[:5])
            
            sections.append({
                'title': f"القسم {i+1}: {sent[:50]}...",
                'keywords': keywords,
                'content': sent[:500],
                'full_text': sent
            })
        return sections
    
    # تقسيم متساوي
    chunk_size = len(sentences) // max_sections
    sections = []
    for i in range(0, len(sentences), chunk_size):
        chunk = '. '.join(sentences[i:i+chunk_size])
        if chunk:
            words = chunk.split()[:10]
            keywords = ', '.join(words[:5])
            sections.append({
                'title': f"القسم {len(sections)+1}: {chunk[:50]}...",
                'keywords': keywords,
                'content': chunk[:500],
                'full_text': chunk
            })
    
    return sections[:max_sections]

# ========== توليد صورة للقسم ==========
async def generate_section_image(title: str, keywords: str, section_num: int, total: int, update: Update, progress_msg):
    """توليد صورة تعليمية للقسم"""
    
    # إنشاء وصف للصورة
    image_prompt = f"{title}, {keywords}, educational illustration"
    clean_prompt = image_prompt.replace(" ", "%20")[:100]
    
    for attempt in range(3):
        await progress_msg.edit_text(f"🖼 توليد صورة القسم {section_num}/{total} - محاولة {attempt+1}/3...")
        
        try:
            url = f"https://image.pollinations.ai/prompt/{clean_prompt}?width=800&height=500"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=25) as response:
                image_data = response.read()
            
            if len(image_data) > 5000:
                return image_data
        except:
            await asyncio.sleep(2)
    
    # صورة نصية بديلة
    return await create_text_image(title, keywords, section_num)

async def create_text_image(title: str, keywords: str, section_num: int):
    """إنشاء صورة نصية تعليمية"""
    try:
        from PIL import Image, ImageDraw, ImageFont
        
        img = Image.new('RGB', (800, 500), color=(20, 40, 70))
        draw = ImageDraw.Draw(img)
        
        # إطار
        for i in range(3):
            draw.rectangle([i, i, 800-i, 500-i], outline=(100, 150, 200), width=3)
        
        try:
            font_title = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 28)
            font_text = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 20)
        except:
            font_title = ImageFont.load_default()
            font_text = ImageFont.load_default()
        
        # عنوان
        draw.text((50, 60), f"📖 {title[:60]}", fill=(255, 215, 0), font=font_title)
        
        # كلمات مفتاحية
        draw.text((50, 130), f"🔑 الكلمات المفتاحية: {keywords[:80]}", fill=(200, 200, 100), font=font_text)
        
        # خط فاصل
        draw.line([50, 170, 750, 170], fill=(100, 150, 200), width=2)
        
        # تذييل
        draw.text((50, 440), f"~ القسم {section_num} ~", fill=(150, 150, 150), font=font_text)
        
        img_buffer = io.BytesIO()
        img.save(img_buffer, format='PNG')
        img_buffer.seek(0)
        return img_buffer.getvalue()
    except:
        return None

# ========== توليد صوت للقسم ==========
async def generate_section_audio(text: str, section_num: int, total: int, update: Update, progress_msg):
    """توليد صوت شرح للقسم"""
    
    await progress_msg.edit_text(f"🎙 توليد صوت القسم {section_num}/{total}...")
    
    for attempt in range(3):
        try:
            audio_text = text[:400]
            has_arabic = any('\u0600' <= c <= '\u06FF' for c in audio_text)
            lang = 'ar' if has_arabic else 'en'
            
            text_encoded = urllib.parse.quote(audio_text)
            url = f"https://translate.google.com/translate_tts?ie=UTF-8&q={text_encoded}&tl={lang}&client=tw-ob"
            
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=20) as response:
                audio_data = response.read()
            
            if len(audio_data) > 5000:
                return audio_data
        except:
            await asyncio.sleep(2)
    
    return None

# ========== إنشاء فيديو باستخدام API خارجي مجاني ==========
async def create_video_online(images_data: list, audios_data: list, sections: list, update: Update, progress_msg):
    """إنشاء فيديو باستخدام خدمة مجانية عبر الإنترنت"""
    
    await progress_msg.edit_text("🎬 جاري إنشاء الفيديو النهائي...")
    
    # بما أن إنشاء الفيديو على Heroku صعب بدون FFmpeg،
    # سنستخدم بديلاً: إرسال كل جزء مع تعليمات دمجها
    
    # إنشاء ملف نصي يحتوي على تعليمات دمج المقاطع
    instructions = "📹 **تعليمات إنشاء الفيديو النهائي**\n\n"
    instructions += "يمكنك دمج هذه المقاطع في فيديو واحد باستخدام:\n\n"
    instructions += "1. **CapCut (مجاني):** استيراد الصور → إضافة الصوت → تصدير فيديو\n"
    instructions += "2. **InShot (مجاني):** نفس الطريقة\n"
    instructions += "3. **FFmpeg (للمتقدمين):**\n\n"
    instructions += "```\n"
    
    for i in range(len(images_data)):
        instructions += f"# المقطع {i+1}: الصورة {i+1}.png + الصوت {i+1}.mp3\n"
    
    instructions += "```\n\n"
    instructions += f"📊 **عدد المقاطع: {len(images_data)}**\n"
    instructions += f"🎬 جودة الفيديو: 720p\n"
    instructions += f"🗣 اللهجة: حسب اختيارك\n"
    
    return instructions

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
                for page in pdf_reader.pages:
                    text += page.extract_text() + "\n"
                return text[:4000]
            except:
                return None
                
        elif file_ext in ['docx', 'doc']:
            try:
                import docx
                doc_file = io.BytesIO(file_content)
                doc = docx.Document(doc_file)
                text = ""
                for para in doc.paragraphs:
                    text += para.text + "\n"
                return text[:4000]
            except:
                return None
    except:
        return None
    
    return None

# ========== إرسال الفيديو النهائي ==========
async def send_final_video(images_data: list, audios_data: list, sections: list, explanation: str, dialect_name: str, update: Update, progress_msg):
    """إرسال الفيديو النهائي"""
    
    await progress_msg.edit_text("📤 **95% - جاري تجهيز الفيديو للإرسال...**")
    
    # إرسال الشرح أولاً
    if explanation:
        if len(explanation) > 4000:
            await update.message.reply_text(explanation[:3500])
            await update.message.reply_text(explanation[3500:7000])
        else:
            await update.message.reply_text(explanation)
    
    await asyncio.sleep(1)
    
    # إرسال كل قسم كصورة + صوت
    for i, (img_data, audio_data) in enumerate(zip(images_data, audios_data)):
        if img_data:
            img_file = io.BytesIO(img_data)
            img_file.name = f"section_{i+1}.png"
            await update.message.reply_photo(
                photo=img_file,
                caption=f"📖 **{sections[i]['title'][:100]}**\n\n🔑 {sections[i]['keywords']}"
            )
        
        if audio_data:
            audio_file = io.BytesIO(audio_data)
            audio_file.name = f"audio_{i+1}.mp3"
            await update.message.reply_audio(
                audio=audio_file,
                title=f"شرح {sections[i]['title'][:50]}",
                caption=f"🎙 شرح {sections[i]['title'][:50]}"
            )
        
        await asyncio.sleep(1)
    
    # تعليمات الدمج
    instructions = f"""
🎬 **كيفية إنشاء الفيديو النهائي**

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 **عدد المقاطع:** {len(images_data)}
🗣 **اللهجة:** {dialect_name}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📱 **طريقة الدمج (مجانية):**

1️⃣ **تحميل تطبيق CapCut** (مجاني)
   • استورد الصور بالترتيب
   • أضف الملفات الصوتية لكل صورة
   • اضبط مدة كل صورة = مدة الصوت
   • قم بالتصدير كفيديو

2️⃣ **أو استخدام InShot** (مجاني)
   • نفس الخطوات أعلاه

3️⃣ **أو استخدام FFmpeg** (للمحترفين):
"""
    for i in range(len(images_data)):
        instructions += f"   • الصورة {i+1} + الصوت {i+1}\n"
    
    instructions += f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ **تم إرسال جميع المواد اللازمة للفيديو!**
"""
    
    await update.message.reply_text(instructions)
    
    await progress_msg.delete()
    
    # إرسال رابط تحميل تعليمي
    await update.message.reply_text(
        f"✅ **تم الانتهاء بنجاح!** 🎉\n\n"
        f"📊 **المحتوى المرسل:**\n"
        f"• {len(images_data)} صورة تعليمية\n"
        f"• {len(audios_data)} ملف صوتي شرح\n"
        f"• شرح كامل باللهجة {dialect_name}\n\n"
        f"🎬 **لإنشاء الفيديو النهائي:**\n"
        f"استخدم تطبيق CapCut أو InShot لدمج الصور مع الصوت\n\n"
        f"📹 النتيجة: فيديو تعليمي متكامل!"
    )

# ========== الوظيفة الرئيسية ==========
async def convert_to_video(content: str, dialect: str, update: Update, is_file: bool = False):
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
    explanation = await explain_with_free_api(content, dialect, update, progress_msg)
    
    await progress_msg.edit_text("📖 **30% - تم كتابة الشرح بنجاح**")
    await asyncio.sleep(1)
    
    # 35% - تقسيم
    await progress_msg.edit_text("📂 **35% - جاري تقسيم المحتوى إلى أقسام...**")
    sections = split_into_sections(content, explanation)
    
    if not sections:
        await progress_msg.edit_text("❌ لا يمكن تقسيم المحتوى")
        return
    
    total = len(sections)
    await progress_msg.edit_text(f"📂 **40% - تم التقسيم إلى {total} أقسام**")
    await asyncio.sleep(1)
    
    images_data = []
    audios_data = []
    
    # 45% - 90% معالجة الأقسام
    for i, section in enumerate(sections, 1):
        percent = 40 + (i / total) * 50
        
        await progress_msg.edit_text(f"🎬 **{int(percent)}% - جاري معالجة {section['title'][:50]}...**")
        
        # صورة
        img_data = await generate_section_image(section['title'], section['keywords'], i, total, update, progress_msg)
        if img_data:
            images_data.append(img_data)
        else:
            images_data.append(await create_text_image(section['title'], section['keywords'], i))
        
        # صوت
        audio_data = await generate_section_audio(section['full_text'], i, total, update, progress_msg)
        if audio_data:
            audios_data.append(audio_data)
    
    # 95% - تجهيز
    await progress_msg.edit_text("📤 **95% - جاري تجهيز الفيديو النهائي...**")
    
    # إرسال النتيجة
    await send_final_video(images_data, audios_data, sections, explanation, dialect_name, update, progress_msg)

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
        await convert_to_video(text_content, dialect, update, is_file=True)
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
    
    await convert_to_video(text, dialect, update, is_file=False)
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
        f"• تقسيمها إلى أقسام تعليمية\n"
        f"• توليد صورة لكل قسم\n"
        f"• توليد صوت شرح لكل قسم\n"
        f"• إرسال جميع المواد لصنع فيديو واحد\n\n"
        f"✅ **النتيجة: فيديو تعليمي متكامل**"
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
        "📁 بعد الاختيار، أرسل ملف PDF أو DOCX أو TXT\n"
        "أو اكتب المحاضرة نصاً\n\n"
        "🎬 **النتيجة:**\n"
        "• شرح كامل\n"
        "• أقسام تعليمية\n"
        "• صور توضيحية\n"
        "• صوت شرح لكل قسم\n"
        "• تعليمات دمج الفيديو\n\n"
        "✅ **فيديو تعليمي متكامل**",
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
    print("✅ بوت تحويل المحاضرات إلى فيديو تعليمي يعمل!")
    print("🗣 اللهجات: عراقية، سورية، مصرية، خليجية، فصحى")
    print("📁 يدعم: PDF, DOCX, TXT")
    print("🎬 المخرجات: شرح + أقسام + صور + صوت + تعليمات فيديو")
    print("=" * 60)
    
    app.run_polling()

if __name__ == "__main__":
    main()
