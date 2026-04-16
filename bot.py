import os
import asyncio
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, 
    CallbackQueryHandler, filters, ContextTypes
)
from telegram.constants import ParseMode
import tempfile
import shutil

from analyzer import ContentAnalyzer
from image_generator import ImageGenerator
from audio_generator import AudioGenerator
from video_maker import VideoMaker
from utils import download_file, cleanup_temp_files

# إعداد التسجيل
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class LectureBot:
    def __init__(self, token: str):
        self.token = token
        self.analyzer = ContentAnalyzer()
        self.image_gen = ImageGenerator()
        self.audio_gen = AudioGenerator()
        self.video_maker = VideoMaker()
        
        # إنشاء مجلدات مؤقتة
        os.makedirs("temp", exist_ok=True)
        os.makedirs("temp_audio", exist_ok=True)
        
        # قاموس لتخزين حالة المستخدم
        self.user_states = {}
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """أمر /start"""
        welcome_message = """
🎓 *مرحباً بك في بوت المحاضرات التعليمية!*

أنا بوت متخصص في تحويل النصوص والملفات إلى محاضرات فيديو احترافية.

*طريقة الاستخدام:*
1️⃣ أرسل ملف PDF أو Word
2️⃣ أو أرسل نص المحاضرة مباشرة
3️⃣ انتظر قليلاً حتى أقوم بتحليل المحتوى
4️⃣ استلم المحاضرة على شكل فيديو مع شرح صوتي

*الأوامر المتاحة:*
/start - بدء البوت
/help - المساعدة
/about - عن البوت

ابدأ بإرسال ملف أو نص الآن! 📚
        """
        
        keyboard = [
            [InlineKeyboardButton("📖 كيفية الاستخدام", callback_data="help")],
            [InlineKeyboardButton("ℹ️ عن البوت", callback_data="about")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            welcome_message,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup
        )
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """أمر /help"""
        help_text = """
📚 *دليل استخدام البوت*

*أنواع الملفات المدعومة:*
• PDF
• Word (DOCX)
• TXT
• صور تحتوي على نص

*طريقة عمل البوت:*
1. استلام الملف أو النص
2. تحليل المحتوى واستخراج:
   - العنوان الرئيسي
   - الأقسام الفرعية
   - الكلمات المفتاحية
3. إنشاء كارتات تعليمية
4. تحويل الشرح إلى صوت
5. دمج كل شيء في فيديو احترافي

*نصائح:*
• كلما كان النص منظماً أكثر، كانت النتيجة أفضل
• يمكنك إرسال محاضرات طبية، علمية، أدبية، إلخ
• مدة معالجة الملف تعتمد على حجم المحتوى

للمساعدة الإضافية: @support
        """
        await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)
    
    async def about(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """أمر /about"""
        about_text = """
🤖 *عن البوت*

*الإصدار:* 1.0.0
*المطور:* [اسمك]
*التقنيات المستخدمة:*
• Python-Telegram-Bot
• MoviePy
• Pillow
• الذكاء الاصطناعي لتحليل النص

*المميزات:*
✅ دعم اللغة العربية بشكل كامل
✅ تحليل ذكي للمحتوى
✅ إنشاء فيديوهات عالية الجودة
✅ تحويل النص إلى صوت احترافي
✅ دعم ملفات متعددة

تابعني للمزيد من التحديثات! 🚀
        """
        await update.message.reply_text(about_text, parse_mode=ParseMode.MARKDOWN)
    
    async def handle_document(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالجة الملفات المستلمة"""
        user_id = update.effective_user.id
        
        # إرسال رسالة انتظار
        status_message = await update.message.reply_text(
            "📥 *جاري استلام الملف...*",
            parse_mode=ParseMode.MARKDOWN
        )
        
        try:
            # تحميل الملف
            file = await update.message.document.get_file()
            file_path = await download_file(file, update.message.document.file_name)
            
            await status_message.edit_text(
                "🔍 *جاري تحليل المحتوى...*",
                parse_mode=ParseMode.MARKDOWN
            )
            
            # استخراج النص من الملف
            text_content = await self.extract_text_from_file(file_path)
            
            # متابعة المعالجة
            await self.process_content(update, context, text_content, status_message)
            
        except Exception as e:
            logger.error(f"Error handling document: {e}")
            await status_message.edit_text(
                "❌ *حدث خطأ أثناء معالجة الملف*\nالرجاء المحاولة مرة أخرى.",
                parse_mode=ParseMode.MARKDOWN
            )
        finally:
            cleanup_temp_files()
    
    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالجة النصوص المستلمة"""
        text = update.message.text
        
        if len(text) < 50:
            await update.message.reply_text(
                "📝 *الرجاء إرسال نص أطول*\nالحد الأدنى 50 حرفاً لإنشاء محاضرة.",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        status_message = await update.message.reply_text(
            "🔍 *جاري تحليل النص...*",
            parse_mode=ParseMode.MARKDOWN
        )
        
        await self.process_content(update, context, text, status_message)
    
    async def process_content(self, update: Update, context: ContextTypes.DEFAULT_TYPE, 
                             text: str, status_message):
        """معالجة المحتوى وإنشاء الفيديو"""
        
        try:
            # تحليل المحتوى
            await status_message.edit_text(
                "🧠 *جاري تحليل المحتوى واستخراج الأقسام...*",
                parse_mode=ParseMode.MARKDOWN
            )
            
            analyzed_content = await self.analyzer.analyze_content(text)
            
            # إنشاء الصور (الكارتات)
            await status_message.edit_text(
                "🎨 *جاري إنشاء البطاقات التعليمية...*",
                parse_mode=ParseMode.MARKDOWN
            )
            
            image_paths = await self.image_gen.generate_all_cards(analyzed_content)
            
            # إنشاء الصوت
            await status_message.edit_text(
                "🎙️ *جاري تحويل الشرح إلى صوت...*",
                parse_mode=ParseMode.MARKDOWN
            )
            
            audio_files = await self.audio_gen.generate_all_audio(analyzed_content)
            
            # إنشاء الفيديو
            await status_message.edit_text(
                "🎬 *جاري تجميع الفيديو النهائي...*",
                parse_mode=ParseMode.MARKDOWN
            )
            
            video_path = self.video_maker.create_video(
                image_paths, audio_files, analyzed_content
            )
            
            # إرسال الفيديو
            await status_message.edit_text(
                "📤 *جاري إرسال المحاضرة...*",
                parse_mode=ParseMode.MARKDOWN
            )
            
            # إرسال معلومات المحاضرة
            info_text = f"""
📹 *تم إنشاء المحاضرة بنجاح!*

*العنوان:* {analyzed_content['title']}
*النوع:* {analyzed_content['type']}
*عدد الأقسام:* {len(analyzed_content['sections'])}
*المدة:* سيتم عرضها في الفيديو

شكراً لاستخدامك البوت! 🎓
            """
            
            with open(video_path, 'rb') as video_file:
                await update.message.reply_video(
                    video=video_file,
                    caption=info_text,
                    parse_mode=ParseMode.MARKDOWN,
                    supports_streaming=True
                )
            
            await status_message.delete()
            
        except Exception as e:
            logger.error(f"Error processing content: {e}")
            await status_message.edit_text(
                f"❌ *حدث خطأ أثناء المعالجة*\n{str(e)[:100]}",
                parse_mode=ParseMode.MARKDOWN
            )
        
        finally:
            cleanup_temp_files()
    
    async def extract_text_from_file(self, file_path: str) -> str:
        """استخراج النص من الملفات المختلفة"""
        ext = os.path.splitext(file_path)[1].lower()
        
        if ext == '.pdf':
            return await self.extract_from_pdf(file_path)
        elif ext in ['.docx', '.doc']:
            return await self.extract_from_docx(file_path)
        elif ext == '.txt':
            return await self.extract_from_txt(file_path)
        elif ext in ['.jpg', '.jpeg', '.png']:
            return await self.extract_from_image(file_path)
        else:
            raise ValueError(f"نوع الملف غير مدعوم: {ext}")
    
    async def extract_from_pdf(self, file_path: str) -> str:
        """استخراج النص من PDF"""
        import PyPDF2
        
        text = ""
        with open(file_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            for page in pdf_reader.pages:
                text += page.extract_text() + "\n"
        return text
    
    async def extract_from_docx(self, file_path: str) -> str:
        """استخراج النص من Word"""
        from docx import Document
        
        doc = Document(file_path)
        text = "\n".join([paragraph.text for paragraph in doc.paragraphs])
        return text
    
    async def extract_from_txt(self, file_path: str) -> str:
        """استخراج النص من TXT"""
        with open(file_path, 'r', encoding='utf-8') as file:
            return file.read()
    
    async def extract_from_image(self, file_path: str) -> str:
        """استخراج النص من الصور باستخدام OCR"""
        try:
            import pytesseract
            from PIL import Image
            
            image = Image.open(file_path)
            text = pytesseract.image_to_string(image, lang='ara+eng')
            return text
        except:
            return "لم يتم التعرف على نص في الصورة"
    
    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالجة أزرار القائمة"""
        query = update.callback_query
        await query.answer()
        
        if query.data == "help":
            help_text = """
📚 *دليل استخدام البوت*

1. أرسل ملف (PDF, Word, TXT)
2. أو أرسل نصاً مباشرة
3. انتظر معالجة المحتوى
4. استلم الفيديو التعليمي

*للمساعدة:* @support
            """
            await query.edit_message_text(help_text, parse_mode=ParseMode.MARKDOWN)
        
        elif query.data == "about":
            about_text = """
🤖 *بوت المحاضرات التعليمية*
الإصدار 1.0.0

ينشئ فيديوهات تعليمية احترافية من النصوص والملفات.
            """
            await query.edit_message_text(about_text, parse_mode=ParseMode.MARKDOWN)
    
    def run(self):
        """تشغيل البوت"""
        app = Application.builder().token(self.token).build()
        
        # إضافة handlers
        app.add_handler(CommandHandler("start", self.start))
        app.add_handler(CommandHandler("help", self.help_command))
        app.add_handler(CommandHandler("about", self.about))
        app.add_handler(MessageHandler(filters.Document.ALL, self.handle_document))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text))
        app.add_handler(CallbackQueryHandler(self.button_callback))
        
        # تشغيل البوت
        logger.info("Bot started successfully!")
        app.run_polling(allowed_updates=Update.ALL_TYPES)

# نقطة البداية
if __name__ == "__main__":
    TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
    bot = LectureBot(TOKEN)
    bot.run()
