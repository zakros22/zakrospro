import os
import uuid
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from docx import Document
import asyncio

# إعداد التسجيل للأخطاء
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# توكن البوت - ضع التوكن الخاص بك هنا
TOKEN = 'ضع_التوكن_هنا'

# مجلد لحفظ الملفات المؤقتة
DOWNLOAD_FOLDER = 'downloads'
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

# قاموس لتخزين حالة المستخدم (اللهجة المختارة)
user_dialects = {}

# اللهجات المدعومة
DIALECTS = {
    'fusha': '📖 الفصحى',
    'egyptian': '🇪🇬 مصري',
    'iraqi': '🇮🇶 عراقي',
    'gulf': '🇦🇪 خليجي',
    'syrian': '🇸🇾 شامي'
}

# كلمات اللهجات للتحويل
DIALECT_WORDS = {
    'iraqi': {
        'ماذا': 'شكو', 'كيف': 'شلون', 'لماذا': 'ليش', 'هذا': 'هذاي',
        'جيد': 'زين', 'أريد': 'أريد', 'ذهب': 'راح', 'أكل': 'چال',
        'الان': 'هلگه', 'كبير': 'كبير', 'صغير': 'زغير', 'جميل': 'حلو',
        'قليل': 'شويه', 'كثير': 'هوايه', 'بسرعة': 'بسرعه', 'بطيء': 'بطيء'
    },
    'egyptian': {
        'ماذا': 'إيه', 'كيف': 'إزاي', 'لماذا': 'ليه', 'هذا': 'دا',
        'جيد': 'كويّس', 'أريد': 'عايز', 'ذهب': 'راح', 'أكل': 'أكل',
        'الان': 'دلوقتي', 'كبير': 'كبير', 'صغير': 'صغير', 'جميل': 'جميل',
        'قليل': 'شوية', 'كثير': 'كتير', 'بسرعة': 'بسرعه', 'بطيء': 'بطيء'
    },
    'gulf': {
        'ماذا': 'شو', 'كيف': 'كيف', 'لماذا': 'ليش', 'هذا': 'هذا',
        'جيد': 'زين', 'أريد': 'أبي', 'ذهب': 'راح', 'أكل': 'أكل',
        'الان': 'الحين', 'كبير': 'كبير', 'صغير': 'صغير', 'جميل': 'حلو',
        'قليل': 'شوي', 'كثير': 'وايد', 'بسرعة': 'بسرعه', 'بطيء': 'بطيء'
    },
    'syrian': {
        'ماذا': 'شو', 'كيف': 'كيف', 'لماذا': 'ليش', 'هذا': 'هيدا',
        'جيد': 'منيح', 'أريد': 'بدي', 'ذهب': 'راح', 'أكل': 'أكل',
        'الان': 'هلأ', 'كبير': 'كبير', 'صغير': 'زغير', 'جميل': 'حلو',
        'قليل': 'شوي', 'كثير': 'كتير', 'بسرعة': 'بسرعه', 'بطيء': 'بطيء'
    },
    'fusha': {}
}

def translate_to_dialect(text, dialect):
    """تحويل النص إلى اللهجة المختارة"""
    if dialect == 'fusha' or dialect not in DIALECT_WORDS:
        return text
    
    words = DIALECT_WORDS[dialect]
    result = text
    
    for original, translated in words.items():
        result = result.replace(original, translated)
    
    return result

def process_docx(file_path, dialect):
    """معالجة ملف Word وترجمته"""
    doc = Document(file_path)
    new_doc = Document()
    
    for para in doc.paragraphs:
        translated_text = translate_to_dialect(para.text, dialect)
        new_doc.add_paragraph(translated_text)
    
    output_path = os.path.join(DOWNLOAD_FOLDER, f'translated_{uuid.uuid4().hex}.docx')
    new_doc.save(output_path)
    return output_path

def process_txt(file_path, dialect):
    """معالجة ملف نصي وترجمته"""
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    translated = translate_to_dialect(content, dialect)
    
    output_path = os.path.join(DOWNLOAD_FOLDER, f'translated_{uuid.uuid4().hex}.txt')
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(translated)
    
    return output_path

# ============= أوامر البوت =============

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """رسالة الترحيب"""
    welcome_text = """
🌍 *مرحباً بك في بوت ترجمة اللهجات العربية!*

📌 *الإمكانيات:*
• ترجمة النصوص إلى اللهجات العربية
• ترجمة ملفات (txt, docx)

🗣️ *اللهجات المدعومة:*
• 🇮🇶 عراقي
• 🇪🇬 مصري  
• 🇦🇪 خليجي
• 🇸🇾 شامي
• 📖 فصحى

📝 *كيفية الاستخدام:*
1️⃣ اختر اللهجة من القائمة
2️⃣ أرسل نصاً أو ملفاً
3️⃣ سأعيد لك النص/الملف مترجماً

👉 استخدم /dialect لاختيار اللهجة
👉 استخدم /help للمساعدة
    """
    await update.message.reply_text(welcome_text, parse_mode='Markdown')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """أمر المساعدة"""
    help_text = """
*🔧 أوامر البوت:*

/dialect - اختيار اللهجة
/start - إعادة تشغيل البوت
/help - عرض هذه المساعدة

*📁 الملفات المدعومة:*
• .txt - ملفات نصية
• .docx - مستندات Word

💡 *نصيحة:* اختر اللهجة أولاً ثم أرسل النص أو الملف
    """
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def select_dialect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض قائمة اللهجات للاختيار"""
    keyboard = []
    for key, name in DIALECTS.items():
        keyboard.append([InlineKeyboardButton(name, callback_data=f'dialect_{key}')])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text('🗣️ *اختر اللهجة:*', reply_markup=reply_markup, parse_mode='Markdown')

async def dialect_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة اختيار اللهجة"""
    query = update.callback_query
    await query.answer()
    
    dialect_key = query.data.replace('dialect_', '')
    user_id = query.from_user.id
    
    user_dialects[user_id] = dialect_key
    dialect_name = DIALECTS.get(dialect_key, 'غير معروف')
    
    await query.edit_message_text(f'✅ تم اختيار اللهجة: *{dialect_name}*\n\nالآن أرسل النص أو الملف الذي تريد ترجمته.', parse_mode='Markdown')

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة النصوص المرسلة"""
    user_id = update.message.from_user.id
    text = update.message.text
    
    # التحقق من اختيار اللهجة
    if user_id not in user_dialects:
        await update.message.reply_text('⚠️ يرجى اختيار اللهجة أولاً باستخدام /dialect')
        return
    
    dialect = user_dialects[user_id]
    dialect_name = DIALECTS.get(dialect, 'غير معروف')
    
    # إظهار رسالة انتظار
    waiting_msg = await update.message.reply_text(f'🔄 جاري الترجمة إلى اللهجة {dialect_name}...')
    
    # ترجمة النص
    translated = translate_to_dialect(text, dialect)
    
    # إرسال النتيجة
    await waiting_msg.delete()
    await update.message.reply_text(f'🗣️ *الترجمة إلى {dialect_name}:*\n\n{translated}', parse_mode='Markdown')

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة الملفات المرسلة"""
    user_id = update.message.from_user.id
    document = update.message.document
    file_name = document.file_name
    
    # التحقق من اختيار اللهجة
    if user_id not in user_dialects:
        await update.message.reply_text('⚠️ يرجى اختيار اللهجة أولاً باستخدام /dialect')
        return
    
    dialect = user_dialects[user_id]
    dialect_name = DIALECTS.get(dialect, 'غير معروف')
    
    # التحقق من نوع الملف
    ext = file_name.rsplit('.', 1)[-1].lower()
    if ext not in ['txt', 'docx']:
        await update.message.reply_text('❌ نوع الملف غير مدعوم. يرجى إرسال ملف .txt أو .docx فقط')
        return
    
    # إظهار رسالة انتظار
    waiting_msg = await update.message.reply_text(f'📥 جاري تحميل الملف وترجمته إلى {dialect_name}...')
    
    # تحميل الملف
    file = await document.get_file()
    input_path = os.path.join(DOWNLOAD_FOLDER, f'input_{uuid.uuid4().hex}.{ext}')
    await file.download_to_drive(input_path)
    
    # معالجة الملف حسب نوعه
    if ext == 'txt':
        output_path = process_txt(input_path, dialect)
    else:  # docx
        output_path = process_docx(input_path, dialect)
    
    # حذف الملف الأصلي
    os.remove(input_path)
    
    # إرسال الملف المترجم
    await waiting_msg.delete()
    with open(output_path, 'rb') as f:
        await update.message.reply_document(
            document=f,
            filename=f'translated_{file_name}',
            caption=f'✅ تمت الترجمة إلى اللهجة {dialect_name}'
        )
    
    # حذف الملف المترجم
    os.remove(output_path)

# ============= تشغيل البوت =============

def main():
    """تشغيل البوت"""
    # إنشاء التطبيق
    application = Application.builder().token(TOKEN).build()
    
    # إضافة الأوامر
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("dialect", select_dialect))
    
    # معالجة الضغط على الأزرار
    application.add_handler(CallbackQueryHandler(dialect_callback, pattern='^dialect_'))
    
    # معالجة الرسائل والملفات
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    
    # تشغيل البوت
    print("🤖 البوت يعمل...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
