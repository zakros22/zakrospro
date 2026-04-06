import os
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import sqlite3
import tempfile
from datetime import datetime
import time
import re
import requests
from fpdf import FPDF
import arabic_reshaper
from bidi.algorithm import get_display
from deep_translator import GoogleTranslator
import PyPDF2
import docx

BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise Exception("BOT_TOKEN not set")

bot = telebot.TeleBot(BOT_TOKEN)
OWNER_ID = 7021542402

# ========== 1. تحميل الخط ==========
FONT_URL = "https://github.com/googlefonts/noto-fonts/raw/main/hinted/ttf/NotoSans/NotoSans-Regular.ttf"
FONT_PATH = "NotoSans-Regular.ttf"
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

# ========== 2. قاعدة البيانات ==========
conn = sqlite3.connect("lecture.db", check_same_thread=False)
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    points INTEGER DEFAULT 1
)''')
conn.commit()

def get_user(user_id):
    c.execute("SELECT points FROM users WHERE user_id=?", (user_id,))
    row = c.fetchone()
    if not row:
        c.execute("INSERT INTO users (user_id, points) VALUES (?,?)", (user_id, 1))
        conn.commit()
        return 1
    return row[0]

def update_points(user_id, delta):
    c.execute("UPDATE users SET points = points + ? WHERE user_id=?", (delta, user_id))
    conn.commit()

# ========== 3. استخراج النص ==========
def extract_text(file_path):
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
        else:
            return None
    except:
        return None

# ========== 4. تحليل المحاضرة ==========
def analyze_lecture(text):
    # تقسيم النص إلى فقرات
    paragraphs = text.split('\n')
    paragraphs = [p.strip() for p in paragraphs if len(p.strip()) > 30]
    
    if not paragraphs:
        paragraphs = [text[:500]]
    
    result = []
    translator = GoogleTranslator(source='auto', target='ar')
    
    for i, para in enumerate(paragraphs[:15]):  # حد أقصى 15 فقرة
        try:
            translated = translator.translate(para[:1500])
        except:
            translated = para
        
        result.append({
            "num": i + 1,
            "original": para[:400],
            "translated": translated[:400]
        })
    
    return result

# ========== 5. إنشاء PDF ==========
def create_pdf(title, analysis, output_path):
    pdf = FPDF()
    pdf.add_page()
    
    if FONT_PATH and os.path.exists(FONT_PATH):
        pdf.add_font('Noto', '', FONT_PATH, uni=True)
        pdf.set_font('Noto', '', 16)
    else:
        pdf.set_font("Helvetica", "", 16)
    
    # العنوان
    pdf.set_text_color(0, 51, 102)
    pdf.cell(0, 15, f"تحليل المحاضرة: {title}", 0, 1, 'C')
    pdf.ln(5)
    
    # التاريخ
    pdf.set_font_size(10)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(0, 8, f"التاريخ: {datetime.now().strftime('%Y-%m-%d %H:%M')}", 0, 1, 'C')
    pdf.ln(10)
    
    for item in analysis:
        if pdf.get_y() > 250:
            pdf.add_page()
        
        # عنوان القسم
        pdf.set_font_size(12)
        pdf.set_text_color(0, 51, 102)
        pdf.cell(0, 10, f"القسم {item['num']}", 0, 1, 'L')
        
        # النص الأصلي
        pdf.set_font_size(10)
        pdf.set_text_color(0, 0, 150)
        pdf.cell(0, 8, "النص الأصلي:", 0, 1, 'L')
        pdf.set_text_color(0, 0, 0)
        pdf.multi_cell(0, 6, reshape_arabic(item['original']))
        pdf.ln(3)
        
        # الترجمة
        pdf.set_text_color(0, 100, 0)
        pdf.cell(0, 8, "الترجمة:", 0, 1, 'L')
        pdf.set_text_color(0, 0, 0)
        pdf.multi_cell(0, 6, reshape_arabic(item['translated']))
        pdf.ln(8)
        
        # فاصل
        pdf.set_draw_color(200, 200, 200)
        pdf.line(30, pdf.get_y(), 180, pdf.get_y())
        pdf.ln(5)
    
    # حقوق البوت
    pdf.set_y(-20)
    pdf.set_font_size(9)
    pdf.set_text_color(128, 128, 128)
    pdf.cell(0, 8, "@zakros_probot", 0, 0, 'C')
    
    pdf.output(output_path)

# ========== 6. أوامر البوت ==========
@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.chat.id
    points = get_user(user_id)
    
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("📚 تحليل محاضرة", callback_data="analyze"))
    if user_id == OWNER_ID:
        markup.add(InlineKeyboardButton("🔧 لوحة التحكم", callback_data="admin"))
    
    bot.send_message(user_id,
        f"📚 بوت تحليل المحاضرات\n\n"
        f"⭐ رصيدك: {points} نقطة\n"
        f"• كل تحليل يستهلك نقطة واحدة\n\n"
        f"@zakros_probot",
        reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "analyze")
def analyze_start(call):
    user_id = call.message.chat.id
    points = get_user(user_id)
    if points < 1:
        bot.answer_callback_query(call.id, "ليس لديك نقاط كافية!", True)
        return
    
    bot.send_message(user_id, "📌 أرسل عنوان المحاضرة:")
    bot.register_next_step_handler(call.message, get_title)

def get_title(message):
    user_id = message.chat.id
    title = message.text.strip()
    bot.send_message(user_id, f"عنوان: {title}\n\n📚 أرسل المحاضرة (نص أو ملف PDF/Word/TXT):")
    bot.register_next_step_handler(message, get_content, title)

def get_content(message, title):
    user_id = message.chat.id
    content = None
    
    if message.text and not message.text.startswith('/'):
        content = message.text.strip()
    elif message.document:
        file_name = message.document.file_name
        ext = os.path.splitext(file_name)[1].lower()
        if ext not in ['.txt', '.pdf', '.docx']:
            bot.reply_to(message, "نوع الملف غير مدعوم. الأنواع: txt, pdf, docx")
            return
        
        status = bot.reply_to(message, "جاري تحميل الملف...")
        try:
            file_info = bot.get_file(message.document.file_id)
            downloaded = bot.download_file(file_info.file_path)
            with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
                tmp.write(downloaded)
                tmp_path = tmp.name
            content = extract_text(tmp_path)
            os.unlink(tmp_path)
            bot.delete_message(user_id, status.message_id)
        except Exception as e:
            bot.edit_message_text(f"خطأ: {e}", user_id, status.message_id)
            return
    else:
        bot.reply_to(message, "أرسل نصاً أو ملفاً صالحاً")
        return
    
    if not content or len(content) < 50:
        bot.reply_to(message, "النص قصير جداً")
        return
    
    update_points(user_id, -1)
    
    status = bot.reply_to(message, "جاري تحليل المحاضرة...")
    
    try:
        analysis = analyze_lecture(content)
        pdf_path = tempfile.mktemp(suffix='.pdf')
        create_pdf(title, analysis, pdf_path)
        
        new_points = get_user(user_id)
        with open(pdf_path, 'rb') as f:
            bot.send_document(user_id, f, caption=f"✅ تم التحليل\n📚 {title}\n⭐ النقاط المتبقية: {new_points}\n\n@zakros_probot", visible_file_name=f"{title}.pdf")
        
        os.unlink(pdf_path)
        bot.delete_message(user_id, status.message_id)
    except Exception as e:
        bot.edit_message_text(f"❌ فشل: {e}", user_id, status.message_id)
        update_points(user_id, 1)

# ========== 7. لوحة تحكم المالك ==========
@bot.callback_query_handler(func=lambda call: call.data == "admin")
def admin_panel(call):
    if call.message.chat.id != OWNER_ID:
        bot.answer_callback_query(call.id, "غير مصرح", True)
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
    print("✅ البوت يعمل...")
    bot.remove_webhook()
    bot.infinity_polling()
