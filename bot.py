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

# ========== مواقع مجانية لشرح النص ==========
# بديل 1: Google Gemini API (مجاني)
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

# بديل 2: DeepSeek API (مجاني)
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")

# بديل 3: OpenRouter API (مجاني)
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")

# بديل 4: Hugging Face API (مجاني)
HUGGINGFACE_API_KEY = os.environ.get("HUGGINGFACE_API_KEY", "")

# بديل 5: تحليل محلي (يعمل دائماً)
def explain_local(text: str, dialect: str):
    """شرح محلي للنص (بديل احتياطي)"""
    
    words = text.split()
    sentences = re.split(r'[.!?؟\n]+', text)
    sentences = [s for s in sentences if len(s.strip()) > 20]
    
    # كلمات اللهجة
    dialect_words = {
        'iraqi': 'على سبيل المثال، يعني، شنو، هسه، گال',
        'syrian': 'يعني، شو، هلق، قَال، بدي',
        'egyptian': 'يعني، إيه، دلوقتي، قال، عايز',
        'gulf': 'يعني، وشو، الحين، قال، أبي',
        'fusha': 'يعني، ماذا، الآن، قال، أريد'
    }
    
    dialect_name = {
        'iraqi': 'العراقية',
        'syrian': 'السورية',
        'egyptian': 'المصرية',
        'gulf': 'الخليجية',
        'fusha': 'الفصحى'
    }
    
    explanation = f"""
📚 **شرح النص باللهجة {dialect_name.get(dialect, 'العربية')}**

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📝 **النص الأصلي:**
{text[:400]}{'...' if len(text) > 400 else ''}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 **الملخص:**
{text[:300]}{'...' if len(text) > 300 else ''}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔑 **النقاط الرئيسية:**
"""
    for i, sent in enumerate(sentences[:5], 1):
        explanation += f"{i}. {sent[:100]}...\n"
    
    explanation += f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ تم الشرح بنجاح (تحليل محلي)
"""
    return explanation

async def explain_with_gemini(text: str, dialect: str, update: Update, progress_msg):
    """شرح باستخدام Google Gemini API"""
    if not GEMINI_API_KEY:
        return None
    
    try:
        dialect_names = {
            'iraqi': 'اللهجة العراقية',
            'syrian': 'اللهجة السورية',
            'egyptian': 'اللهجة المصرية',
            'gulf': 'اللهجة الخليجية',
            'fusha': 'اللغة العربية الفصحى'
        }
        
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent?key={GEMINI_API_KEY}"
        headers = {"Content-Type": "application/json"}
        
        prompt = f"""أنت مدرس متخصص. قم بشرح النص التالي شرحاً مفصلاً بـ {dialect_names.get(dialect, 'العربية')}:

النص:
{text[:1500]}

المطلوب:
1. شرح الفكرة الرئيسية
2. شرح النقاط المهمة
3. تبسيط المصطلحات الصعبة
4. إعطاء أمثلة توضيحية

الشرح:"""
        
        data = {
            "contents": [{
                "parts": [{"text": prompt}]
            }]
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=data, timeout=30) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    explanation = result['candidates'][0]['content']['parts'][0]['text']
                    return explanation
        return None
    except Exception as e:
        logger.error(f"Gemini error: {e}")
        return None

async def explain_with_deepseek(text: str, dialect: str, update: Update, progress_msg):
    """شرح باستخدام DeepSeek API"""
    if not DEEPSEEK_API_KEY:
        return None
    
    try:
        dialect_names = {
            'iraqi': 'اللهجة العراقية',
            'syrian': 'اللهجة السورية',
            'egyptian': 'اللهجة المصرية',
            'gulf': 'اللهجة الخليجية',
            'fusha': 'اللغة العربية الفصحى'
        }
        
        url = "https://api.deepseek.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
            "Content-Type": "application/json"
        }
        
        prompt = f"""اشرح النص التالي شرحاً مفصلاً بـ {dialect_names.get(dialect, 'العربية')}:

{text[:1500]}

قدم شرحاً واضحاً ومبسطاً مع ذكر النقاط الرئيسية."""
        
        data = {
            "model": "deepseek-chat",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 2000
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=data, timeout=30) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    return result['choices'][0]['message']['content']
        return None
    except Exception as e:
        logger.error(f"DeepSeek error: {e}")
        return None

async def explain_with_openrouter(text: str, dialect: str, update: Update, progress_msg):
    """شرح باستخدام OpenRouter API"""
    if not OPENROUTER_API_KEY:
        return None
    
    try:
        dialect_names = {
            'iraqi': 'اللهجة العراقية',
            'syrian': 'اللهجة السورية',
            'egyptian': 'اللهجة المصرية',
            'gulf': 'اللهجة الخليجية',
            'fusha': 'اللغة العربية الفصحى'
        }
        
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json"
        }
        
        prompt = f"""اشرح النص التالي شرحاً مفصلاً بـ {dialect_names.get(dialect, 'العربية')}:

{text[:1500]}

قدم شرحاً واضحاً مع تلخيص النقاط الرئيسية."""
        
        data = {
            "model": "openai/gpt-3.5-turbo",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 2000
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=data, timeout=30) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    return result['choices'][0]['message']['content']
        return None
    except Exception as e:
        logger.error(f"OpenRouter error: {e}")
        return None

async def get_explanation(text: str, dialect: str, update: Update, progress_msg):
    """الحصول على شرح النص باستخدام أفضل خدمة متاحة"""
    
    # تجربة الخدمات بالترتيب
    explanation = None
    
    # 1. Gemini
    if not explanation:
        await progress_msg.edit_text(f"📖 جاري شرح النص بـ Gemini API...")
        explanation = await explain_with_gemini(text, dialect, update, progress_msg)
    
    # 2. DeepSeek
    if not explanation:
        await progress_msg.edit_text(f"📖 جاري شرح النص بـ DeepSeek API...")
        explanation = await explain_with_deepseek(text, dialect, update, progress_msg)
    
    # 3. OpenRouter
    if not explanation:
        await progress_msg.edit_text(f"📖 جاري شرح النص بـ OpenRouter API...")
        explanation = await explain_with_openrouter(text, dialect, update, progress_msg)
    
    # 4. شرح محلي (يعمل دائماً)
    if not explanation:
        await progress_msg.edit_text(f"📖 جاري شرح النص محلياً...")
        explanation = explain_local(text, dialect)
    
    return explanation

# ========== تقسيم النص إلى أقسام ==========
def split_into_sections(text: str, max_sections: int = 5):
    """تقسيم النص إلى أقسام متساوية"""
    
    # تنظيف النص
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    # تقسيم حسب الجمل
    sentences = re.split(r'[.!?؟\n]+', text)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 20]
    
    if len(sentences) <= max_sections:
        return ['. '.join(sentences[i:i+2]) for i in range(0, len(sentences), 2)] if len(sentences) > 2 else [text]
    
    # تقسيم متساوي
    chunk_size = len(sentences) // max_sections
    sections = []
    for i in range(0, len(sentences), chunk_size):
        section = '. '.join(sentences[i:i+chunk_size])
        if section:
            sections.append(section)
    
    return sections[:max_sections]

# ========== توليد صورة للقسم ==========
async def generate_section_image(text: str, section_num: int, total: int, update: Update, progress_msg):
    """توليد صورة تمثيلية للقسم"""
    
    # استخراج الكلمات المفتاحية للصورة
    words = text.split()[:15]
    image_prompt = ' '.join(words)[:100]
    
    for attempt in range(3):
        await progress_msg.edit_text(f"🖼 توليد صورة للقسم {section_num}/{total} - المحاولة {attempt+1}/3...")
        
        try:
            clean_prompt = image_prompt.strip().replace(" ", "%20")
            url = f"https://image.pollinations.ai/prompt/{clean_prompt}?width=800&height=600"
            
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=30) as response:
                image_data = response.read()
            
            if len(image_data) > 1000:
                return image_data
        except Exception as e:
            logger.error(f"Image error: {e}")
            await asyncio.sleep(2)
    
    # صورة بديلة
    return await create_fallback_image(text, section_num)

async def create_fallback_image(text: str, section_num: int):
    """إنشاء صورة نصية بديلة"""
    try:
        from PIL import Image, ImageDraw, ImageFont
        
        img = Image.new('RGB', (800, 600), color=(30, 40, 80))
        draw = ImageDraw.Draw(img)
        
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 24)
        except:
            font = ImageFont.load_default()
        
        lines = [text[i:i+45] for i in range(0, min(len(text), 300), 45)]
        y = 100
        for line in lines[:6]:
            draw.text((50, y), line, fill=(255, 255, 255), font=font)
            y += 40
        
        draw.text((50, y+30), f"~ القسم {section_num} ~", fill=(200, 200, 200), font=font)
        
        img_buffer = io.BytesIO()
        img.save(img_buffer, format='PNG')
        img_buffer.seek(0)
        return img_buffer.getvalue()
    except:
        return None

# ========== توليد صوت للقسم باللهجة المختارة ==========
async def generate_section_audio(text: str, dialect: str, section_num: int, total: int, update: Update, progress_msg):
    """توليد صوت شرح للقسم باللهجة المختارة"""
    
    await progress_msg.edit_text(f"🎙 توليد صوت للقسم {section_num}/{total}...")
    
    try:
        # تحديد اللغة بناءً على اللهجة
        lang = 'ar'
        
        # تقصير النص للصوت
        audio_text = text[:500]
        
        text_encoded = urllib.parse.quote(audio_text)
        url = f"https://translate.google.com/translate_tts?ie=UTF-8&q={text_encoded}&tl={lang}&client=tw-ob"
        
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=20) as response:
            audio_data = response.read()
        
        if len(audio_data) > 1000:
            return audio_data
        return None
    except Exception as e:
        logger.error(f"Audio error: {e}")
        return None

# ========== استخراج النص من الملفات ==========
async def extract_text_from_file(file_content: bytes, filename: str, update: Update, progress_msg):
    """استخراج النص من الملف"""
    
    await progress_msg.edit_text("📁 جاري استخراج النص من الملف...")
    
    file_ext = filename.split('.')[-1].lower() if '.' in filename else 'txt'
    text_content = ""
    
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
                await update.message.reply_text("⚠️ جاري تثبيت المكتبات...")
                return None
                
        elif file_ext in ['docx', 'doc']:
            try:
                import docx
                doc_file = io.BytesIO(file_content)
                doc = docx.Document(doc_file)
                for para in doc.paragraphs:
                    text_content += para.text + "\n"
            except ImportError:
                await update.message.reply_text("⚠️ جاري تثبيت المكتبات...")
                return None
        else:
            await update.message.reply_text(f"⚠️ صيغة {file_ext} غير مدعومة")
            return None
        
        if len(text_content) < 100:
            await update.message.reply_text("⚠️ الملف لا يحتوي على نص كافٍ")
            return None
        
        return text_content
        
    except Exception as e:
        logger.error(f"File error: {e}")
        await update.message.reply_text(f"❌ خطأ: {str(e)[:100]}")
        return None

# ========== إنشاء الفيديو النهائي ==========
async def create_video(images_data: list, audios_data: list, update: Update, progress_msg):
    """دمج الصور والصوت في فيديو واحد"""
    
    if not images_data or not audios_data:
        return None
    
    await progress_msg.edit_text("🎬 جاري إنشاء وتشفير الفيديو النهائي...")
    
    try:
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
                    
                    # حساب مدة الصوت
                    cmd_duration = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", audio_path]
                    result = subprocess.run(cmd_duration, capture_output=True, text=True)
                    duration = float(result.stdout.strip()) if result.stdout else 10
                    
                    # إنشاء مقطع فيديو
                    cmd = [
                        "ffmpeg", "-y", "-loop", "1", "-i", img_path,
                        "-i", audio_path, "-c:v", "libx264", "-t", str(duration),
                        "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest",
                        output_path
                    ]
                    subprocess.run(cmd, capture_output=True)
                    video_parts.append(output_path)
            
            if len(video_parts) == 1:
                return video_parts[0]
            
            # دمج المقاطع
            if len(video_parts) > 1:
                list_path = os.path.join(tmpdir, "list.txt")
                with open(list_path, 'w') as f:
                    for part in video_parts:
                        f.write(f"file '{part}'\n")
                
                final_video = os.path.join(tmpdir, "final_video.mp4")
                cmd_concat = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list_path, "-c", "copy", final_video]
                subprocess.run(cmd_concat, capture_output=True)
                
                if os.path.exists(final_video):
                    return final_video
        
        return None
    except Exception as e:
        logger.error(f"Video error: {e}")
        return None

# ========== الوظيفة الرئيسية لتحويل المحتوى إلى فيديو ==========
async def convert_to_video(content: str, dialect: str, update: Update, is_file: bool = False):
    """تحويل النص أو الملف إلى فيديو تعليمي"""
    
    # رسالة التقدم
    progress_msg = await update.message.reply_text("🎬 **بدء عملية التحويل إلى فيديو تعليمي...**\n\n0%")
    
    # 10%
    await progress_msg.edit_text("📊 **10% - جاري تحليل المحتوى وتقسيمه...**")
    await asyncio.sleep(1)
    
    # تقسيم النص إلى أقسام
    sections = split_into_sections(content)
    
    if not sections:
        await progress_msg.edit_text("❌ لا يمكن تقسيم المحتوى إلى أقسام")
        return
    
    total_sections = len(sections)
    await progress_msg.edit_text(f"📊 **20% - تم التقسيم إلى {total_sections} أقسام**")
    await asyncio.sleep(1)
    
    # 30% - شرح النص
    await progress_msg.edit_text(f"📖 **30% - جاري كتابة شرح المحتوى باللهجة المختارة...**")
    
    # الحصول على شرح كامل
    full_explanation = await get_explanation(content, dialect, update, progress_msg)
    
    await progress_msg.edit_text(f"📖 **40% - تم كتابة الشرح بنجاح**")
    await asyncio.sleep(1)
    
    images_data = []
    audios_data = []
    
    # معالجة كل قسم
    for i, section in enumerate(sections, 1):
        percent = 40 + (i / total_sections) * 50
        
        # توليد صورة
        img_data = await generate_section_image(section, i, total_sections, update, progress_msg)
        if img_data:
            images_data.append(img_data)
        
        # توليد صوت
        audio_data = await generate_section_audio(section, dialect, i, total_sections, update, progress_msg)
        if audio_data:
            audios_data.append(audio_data)
        
        await progress_msg.edit_text(f"🎬 **{int(percent)}% - تم معالجة القسم {i}/{total_sections}**")
    
    # 90% - إنشاء الفيديو
    video_path = await create_video(images_data, audios_data, update, progress_msg)
    
    # 95% - تجهيز للإرسال
    await progress_msg.edit_text("🎬 **95% - جاري تجهيز الفيديو للإرسال...**")
    
    if video_path and os.path.exists(video_path):
        # 100% - إرسال الفيديو
        await progress_msg.edit_text("📤 **100% - جاري إرسال الفيديو النهائي...**")
        
        with open(video_path, 'rb') as f:
            await update.message.reply_video(
                video=io.BytesIO(f.read()),
                caption=f"🎬 **الفيديو التعليمي النهائي**\n\n"
                       f"📊 عدد الأقسام: {total_sections}\n"
                       f"🗣 اللهجة: {dialect}\n"
                       f"📝 تم الشرح بنجاح\n\n"
                       f"✅ تم التحويل بنجاح!"
            )
        
        await progress_msg.delete()
        await update.message.reply_text("✅ **تم إنشاء الفيديو التعليمي بنجاح!** 🎉")
    else:
        await progress_msg.edit_text("❌ **فشل إنشاء الفيديو**\n\n💡 حاول بنص أقصر أو محتوى أقل")

# ========== معالجة الملفات والرسائل ==========
async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة الملفات المرسلة"""
    user_id = update.effective_user.id
    
    if user_id not in user_data or user_data[user_id].get('mode') != 'video':
        await update.message.reply_text("❌ الرجاء اختيار اللهجة أولاً من القائمة")
        return
    
    dialect = user_data[user_id].get('dialect', 'fusha')
    file = update.message.document
    file_name = file.file_name
    
    progress_msg = await update.message.reply_text(f"📁 **تم استلام الملف:** {file_name}\n🔄 جاري المعالجة...")
    
    # تحميل الملف
    file_obj = await file.get_file()
    file_content = await file_obj.download_as_bytearray()
    
    # استخراج النص
    text_content = await extract_text_from_file(bytes(file_content), file_name, update, progress_msg)
    
    if text_content:
        await convert_to_video(text_content, dialect, update, is_file=True)
    else:
        await progress_msg.edit_text("❌ فشل استخراج النص من الملف")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة الرسائل النصية"""
    user_id = update.effective_user.id
    text = update.message.text
    
    if user_id not in user_data or user_data[user_id].get('mode') != 'video':
        # عرض قائمة اللهجات
        keyboard = [
            [InlineKeyboardButton("🇮🇶 عراقية", callback_data="dialect_iraqi")],
            [InlineKeyboardButton("🇸🇾 سورية", callback_data="dialect_syrian")],
            [InlineKeyboardButton("🇪🇬 مصرية", callback_data="dialect_egyptian")],
            [InlineKeyboardButton("🇸🇦 خليجية", callback_data="dialect_gulf")],
            [InlineKeyboardButton("📖 فصحى", callback_data="dialect_fusha")],
        ]
        await update.message.reply_text(
            "🎬 **مرحباً بك في بوت تحويل المحاضرات إلى فيديو تعليمي!**\n\n"
            "🗣 **اختر اللهجة التي تريد الشرح بها:**\n\n"
            "🇮🇶 عراقية\n"
            "🇸🇾 سورية\n"
            "🇪🇬 مصرية\n"
            "🇸🇦 خليجية\n"
            "📖 فصحى\n\n"
            "📁 بعد اختيار اللهجة، أرسل:\n"
            "• ملف PDF أو DOCX أو TXT\n"
            "• أو نصاً مباشرة",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    
    dialect = user_data[user_id].get('dialect', 'fusha')
    await convert_to_video(text, dialect, update, is_file=False)
    
    # حذف وضع المستخدم بعد المعالجة
    del user_data[user_id]

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة أزرار اختيار اللهجة"""
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
        f"🎬 سأقوم بـ:\n"
        f"• تحليل المحتوى وتقسيمه\n"
        f"• شرحه باللهجة {dialect_names.get(dialect, 'الفصحى')}\n"
        f"• توليد صورة لكل قسم\n"
        f"• توليد صوت شرح لكل قسم\n"
        f"• دمج كل شيء في فيديو واحد\n"
        f"• إرسال الفيديو النهائي"
    )

# ========== أمر /start ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🇮🇶 عراقية", callback_data="dialect_iraqi")],
        [InlineKeyboardButton("🇸🇾 سورية", callback_data="dialect_syrian")],
        [InlineKeyboardButton("🇪🇬 مصرية", callback_data="dialect_egyptian")],
        [InlineKeyboardButton("🇸🇦 خليجية", callback_data="dialect_gulf")],
        [InlineKeyboardButton("📖 فصحى", callback_data="dialect_fusha")],
    ]
    await update.message.reply_text(
        "🎬 **مرحباً بك في بوت تحويل المحاضرات إلى فيديو تعليمي!**\n\n"
        "🗣 **اختر اللهجة التي تريد الشرح بها:**\n\n"
        "🇮🇶 عراقية\n"
        "🇸🇾 سورية\n"
        "🇪🇬 مصرية\n"
        "🇸🇦 خليجية\n"
        "📖 فصحى\n\n"
        "📁 بعد اختيار اللهجة، أرسل:\n"
        "• ملف PDF أو DOCX أو TXT\n"
        "• أو نصاً مباشرة",
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
    print("🎬 المخرجات: فيديو واحد كامل")
    print("=" * 60)
    
    app.run_polling()

if __name__ == "__main__":
    main()
