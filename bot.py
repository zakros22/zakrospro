import os
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import sqlite3
import tempfile
from datetime import datetime
import time
import re
import requests
from deep_translator import GoogleTranslator
import PyPDF2
import docx
from pptx import Presentation
from fpdf import FPDF
import arabic_reshaper
from bidi.algorithm import get_display

BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise Exception("BOT_TOKEN not set")

bot = telebot.TeleBot(BOT_TOKEN)
OWNER_ID = 7021542402

# ========== 1. الخط العربي ==========
FONT_URL = "https://github.com/googlefonts/noto-fonts/raw/main/hinted/ttf/NotoSansArabic/NotoSansArabic-Regular.ttf"
FONT_PATH = "NotoSansArabic-Regular.ttf"
if not os.path.exists(FONT_PATH):
    try:
        r = requests.get(FONT_URL, timeout=30)
        with open(FONT_PATH, "wb") as f:
            f.write(r.content)
    except:
        FONT_PATH = None

def reshape_arabic(text):
    if any('\u0600' <= c <= '\u06FF' for c in text):
        try:
            reshaped = arabic_reshaper.reshape(text)
            return get_display(reshaped)
        except:
            return text
    return text

# ========== 2. اللهجات ==========
DIALECTS = {
    "fusha": "📖 الفصحى",
    "egyptian": "🇪🇬 المصري",
    "iraqi": "🇮🇶 العراقي",
    "syrian": "🇸🇾 السوري",
    "gulf": "🇦🇪 الخليجي",
    "moroccan": "🇲🇦 المغربي",
    "algerian": "🇩🇿 الجزائري",
    "tunisian": "🇹🇳 التونسي",
    "libyan": "🇱🇾 الليبي",
    "jordanian": "🇯🇴 الأردني",
    "palestinian": "🇵🇸 الفلسطيني",
    "lebanese": "🇱🇧 اللبناني",
    "yemeni": "🇾🇪 اليمني",
    "sudanese": "🇸🇩 السوداني",
    "omani": "🇴🇲 العماني"
}

# ========== 3. قاعدة البيانات ==========
conn = sqlite3.connect("translate.db", check_same_thread=False)
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    points INTEGER DEFAULT 3
)''')
conn.commit()

def get_user(user_id):
    c.execute("SELECT points FROM users WHERE user_id=?", (user_id,))
    row = c.fetchone()
    if not row:
        c.execute("INSERT INTO users (user_id, points) VALUES (?,?)", (user_id, 3))
        conn.commit()
        return 3
    return row[0]

def update_points(user_id, delta):
    c.execute("UPDATE users SET points = points + ? WHERE user_id=?", (delta, user_id))
    conn.commit()

# ========== 4. استخراج النص من الملفات ==========
def extract_text_from_file(file_path):
    ext = os.path.splitext(file_path)[1].lower()
    try:
        if ext == '.txt':
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
        elif ext == '.pdf':
            text = ""
            with open(file_path, 'rb') as f:
                reader = PyPDF2.PdfReader(f)
                for page in reader.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n"
            return text.strip()
        elif ext == '.docx':
            doc = docx.Document(file_path)
            return "\n".join([para.text for para in doc.paragraphs])
        elif ext == '.pptx':
            text = ""
            prs = Presentation(file_path)
            for slide in prs.slides:
                for shape in slide.shapes:
                    if hasattr(shape, "text"):
                        text += shape.text + "\n"
            return text.strip()
        else:
            return None
    except Exception as e:
        print(f"Extract error: {e}")
        return None

# ========== 5. إنشاء ملف مترجم ==========
def create_translated_file(original_path, translated_text, output_path):
    ext = os.path.splitext(original_path)[1].lower()
    try:
        if ext == '.txt':
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(translated_text)
        elif ext == '.pdf':
            pdf = FPDF()
            pdf.add_page()
            if FONT_PATH and os.path.exists(FONT_PATH):
                pdf.add_font('Noto', '', FONT_PATH, uni=True)
                pdf.set_font('Noto', '', 12)
            else:
                pdf.set_font("Helvetica", "", 12)
            pdf.multi_cell(0, 6, reshape_arabic(translated_text))
            pdf.output(output_path)
        elif ext == '.docx':
            doc = docx.Document()
            doc.add_paragraph(translated_text)
            doc.save(output_path)
        elif ext == '.pptx':
            from pptx import Presentation as Pres
            prs = Pres()
            slide = prs.slides.add_slide(prs.slide_layouts[1])
            slide.shapes.title.text = "الترجمة"
            slide.placeholders[1].text = translated_text
            prs.save(output_path)
        else:
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(translated_text)
        return True
    except Exception as e:
        print(f"Create file error: {e}")
        return False

# ========== 6. ترجمة النص ==========
def translate_text(text, dialect):
    """ترجمة النص إلى اللهجة المختارة"""
    try:
        translator = GoogleTranslator(source='auto', target='ar')
        translated = translator.translate(text[:3000])
        return translated
    except:
        return text

# ========== 7. تخزين مؤقت ==========
user_data = {}

# ========== 8. أوامر البوت ==========
@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.chat.id
    points = get_user(user_id)
    
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🌍 ترجمة ملف", callback_data="translate_file"))
    
    bot.send_message(user_id,
        f"🌍 *بوت ترجمة الملفات*\n\n"
        f"⭐ رصيدك: {points} نقطة\n"
        f"• كل ترجمة = 1 نقطة\n"
        f"• أرسل أي ملف (txt, pdf, docx, pptx)\n"
        f"• سأقوم بترجمته إلى اللهجة التي تختارها\n\n"
        f"📌 @zakros_probot",
        parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "translate_file")
def translate_file(call):
    user_id = call.message.chat.id
    points = get_user(user_id)
    if points < 1:
        bot.answer_callback_query(call.id, "ليس لديك نقاط كافية!", True)
        return
    
    # عرض اللهجات
    markup = InlineKeyboardMarkup(row_width=3)
    for key, name in DIALECTS.items():
        markup.add(InlineKeyboardButton(name, callback_data=f"dialect_{key}"))
    
    bot.edit_message_text("🌍 *اختر اللهجة التي تريد الترجمة إليها:*", user_id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("dialect_"))
def select_dialect(call):
    user_id = call.message.chat.id
    dialect_key = call.data.split("_")[1]
    dialect_name = DIALECTS[dialect_key]
    
    user_data[user_id] = {"dialect": dialect_key, "dialect_name": dialect_name}
    
    bot.edit_message_text(f"🌍 اللهجة: {dialect_name}\n\n📤 *أرسل الملف الذي تريد ترجمته*\n(يدعم: txt, pdf, docx, pptx)", user_id, call.message.message_id, parse_mode="Markdown")

@bot.message_handler(content_types=['document'])
def handle_file(message):
    user_id = message.chat.id
    data = user_data.get(user_id)
    
    if not data:
        bot.reply_to(message, "❌ ابدأ أولاً بـ /start ثم اختر اللهجة")
        return
    
    file_name = message.document.file_name
    file_ext = os.path.splitext(file_name)[1].lower()
    
    allowed = ['.txt', '.pdf', '.docx', '.pptx']
    if file_ext not in allowed:
        bot.reply_to(message, f"❌ نوع الملف غير مدعوم.\nالأنواع المدعومة: {', '.join(allowed)}")
        return
    
    status = bot.reply_to(message, "🔄 جاري معالجة الملف...")
    
    try:
        # تحميل الملف
        file_info = bot.get_file(message.document.file_id)
        downloaded = bot.download_file(file_info.file_path)
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as tmp_in:
            tmp_in.write(downloaded)
            input_path = tmp_in.name
        
        # استخراج النص
        original_text = extract_text_from_file(input_path)
        
        if not original_text or len(original_text) < 10:
            bot.edit_message_text("❌ لا يمكن قراءة الملف أو النص قصير جداً", user_id, status.message_id)
            os.unlink(input_path)
            return
        
        # ترجمة النص
        translated_text = translate_text(original_text, data["dialect"])
        
        # إنشاء ملف مترجم
        output_path = tempfile.mktemp(suffix=file_ext)
        success = create_translated_file(input_path, translated_text, output_path)
        
        if success:
            # استهلاك نقطة
            update_points(user_id, -1)
            new_points = get_user(user_id)
            
            # إرسال الملف المترجم
            with open(output_path, 'rb') as f:
                new_file_name = f"translated_{file_name}"
                bot.send_document(user_id, f, caption=f"✅ تمت الترجمة بنجاح!\n\n📁 {file_name}\n🌍 اللهجة: {data['dialect_name']}\n⭐ النقاط المتبقية: {new_points}\n\n@zakros_probot", visible_file_name=new_file_name)
        else:
            bot.edit_message_text("❌ فشل إنشاء الملف المترجم", user_id, status.message_id)
        
        # تنظيف الملفات
        os.unlink(input_path)
        if os.path.exists(output_path):
            os.unlink(output_path)
        
        bot.delete_message(user_id, status.message_id)
        del user_data[user_id]
        
    except Exception as e:
        bot.edit_message_text(f"❌ خطأ: {str(e)[:100]}", user_id, status.message_id)

# ========== 9. لوحة تحكم المالك ==========
@bot.message_handler(commands=['admin'])
def admin(message):
    if message.chat.id != OWNER_ID:
        bot.reply_to(message, "غير مصرح")
        return
    
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("➕ إضافة نقاط", callback_data="add_points"))
    markup.add(InlineKeyboardButton("📊 إحصائيات", callback_data="stats"))
    bot.send_message(OWNER_ID, "🔧 لوحة التحكم", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "add_points")
def add_points(call):
    if call.message.chat.id != OWNER_ID:
        return
    msg = bot.send_message(OWNER_ID, "أرسل معرف المستخدم وعدد النقاط (مثال: 123456789 5):")
    bot.register_next_step_handler(msg, add_points_step)

def add_points_step(message):
    try:
        uid, pts = map(int, message.text.split())
        update_points(uid, pts)
        bot.send_message(OWNER_ID, f"✅ تم إضافة {pts} نقطة للمستخدم {uid}")
    except:
        bot.send_message(OWNER_ID, "صيغة غير صحيحة")

@bot.callback_query_handler(func=lambda call: call.data == "stats")
def stats(call):
    if call.message.chat.id != OWNER_ID:
        return
    c.execute("SELECT COUNT(*) FROM users")
    users = c.fetchone()[0]
    c.execute("SELECT SUM(points) FROM users")
    points = c.fetchone()[0] or 0
    bot.send_message(OWNER_ID, f"📊 إحصائيات\n👥 المستخدمون: {users}\n⭐ النقاط: {points}")

if __name__ == "__main__":
    print("✅ بوت ترجمة الملفات يعمل...")
    bot.remove_webhook()
    bot.infinity_polling()
