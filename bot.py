import os
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import sqlite3
import tempfile
from datetime import datetime
import re
import requests
from fpdf import FPDF

BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise Exception("BOT_TOKEN not set")

bot = telebot.TeleBot(BOT_TOKEN)
OWNER_ID = 7021542402

# ========== قاعدة البيانات ==========
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

# ========== اللهجات ==========
DIALECTS = {
    "fusha": "📖 الفصحى",
    "egyptian": "🇪🇬 المصري",
    "iraqi": "🇮🇶 العراقي",
    "syrian": "🇸🇾 السوري",
    "gulf": "🇦🇪 الخليجي"
}

# ========== تحليل المحاضرة ==========
def analyze_lecture(text):
    # تنظيف النص
    text = text.strip()
    if len(text) < 50:
        return None
    
    # الأساسيات (أول 300 حرف)
    basics = text[:300] + "..." if len(text) > 300 else text
    
    # تقسيم إلى أقسام (كل 400 حرف)
    sections = []
    for i in range(0, len(text), 400):
        section = text[i:i+400]
        sections.append({
            "num": len(sections) + 1,
            "text": section
        })
    
    # الملخص (آخر 300 حرف)
    summary = text[-300:] + "..." if len(text) > 300 else text
    
    return {
        "basics": basics,
        "sections": sections,
        "summary": summary,
        "total": len(sections)
    }

# ========== إنشاء PDF ==========
def create_pdf(title, analysis, dialect_name, output_path):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=12)
    
    # العنوان
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, f"تحليل المحاضرة: {title}", 0, 1, 'C')
    pdf.ln(5)
    
    # التاريخ واللغة
    pdf.set_font("Helvetica", size=10)
    pdf.cell(0, 8, f"التاريخ: {datetime.now().strftime('%Y-%m-%d %H:%M')}", 0, 1, 'C')
    pdf.cell(0, 8, f"لغة الشرح: {dialect_name}", 0, 1, 'C')
    pdf.ln(10)
    
    # الأساسيات
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 10, "📌 الأساسيات:", 0, 1, 'L')
    pdf.set_font("Helvetica", size=11)
    pdf.multi_cell(0, 6, analysis["basics"])
    pdf.ln(8)
    
    # الأقسام
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 10, f"📚 تقسيم المحاضرة ({analysis['total']} أقسام):", 0, 1, 'L')
    pdf.ln(3)
    
    for section in analysis["sections"]:
        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(0, 8, f"القسم {section['num']}:", 0, 1, 'L')
        pdf.set_font("Helvetica", size=10)
        pdf.multi_cell(0, 5, section["text"])
        pdf.ln(5)
    
    # الملخص
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 10, "📝 الملخص النهائي:", 0, 1, 'L')
    pdf.set_font("Helvetica", size=11)
    pdf.multi_cell(0, 6, analysis["summary"])
    
    # حقوق البوت
    pdf.set_y(-20)
    pdf.set_font("Helvetica", size=8)
    pdf.cell(0, 8, "@zakros_probot", 0, 0, 'C')
    
    pdf.output(output_path)

# ========== استخراج النص من الملفات ==========
def extract_text(file_path):
    ext = os.path.splitext(file_path)[1].lower()
    try:
        if ext == '.txt':
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
        else:
            return None
    except:
        return None

# ========== أوامر البوت ==========
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
        f"• كل تحليل = 1 نقطة\n\n"
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
    bot.send_message(user_id, f"عنوان: {title}\n\n🌍 اختر لهجة الشرح:", reply_markup=get_dialect_markup())
    bot.register_next_step_handler(message, get_dialect, title)

def get_dialect_markup():
    markup = InlineKeyboardMarkup(row_width=2)
    for key, name in DIALECTS.items():
        markup.add(InlineKeyboardButton(name, callback_data=f"dialect_{key}"))
    return markup

@bot.callback_query_handler(func=lambda call: call.data.startswith("dialect_"))
def get_dialect(call):
    user_id = call.message.chat.id
    dialect_key = call.data.split("_")[1]
    dialect_name = DIALECTS[dialect_key]
    
    bot.edit_message_text(f"🌍 اللهجة: {dialect_name}\n\n📚 أرسل المحاضرة (نص أو ملف .txt):", user_id, call.message.message_id)
    bot.register_next_step_handler(call.message, get_content, dialect_name)

def get_content(message, dialect_name):
    user_id = message.chat.id
    content = None
    
    if message.text and not message.text.startswith('/'):
        content = message.text.strip()
    elif message.document:
        if not message.document.file_name.endswith('.txt'):
            bot.reply_to(message, "أرسل ملف .txt فقط")
            return
        
        try:
            file_info = bot.get_file(message.document.file_id)
            downloaded = bot.download_file(file_info.file_path)
            content = downloaded.decode('utf-8')
        except:
            bot.reply_to(message, "خطأ في قراءة الملف")
            return
    else:
        bot.reply_to(message, "أرسل نصاً أو ملف .txt")
        return
    
    if len(content) < 50:
        bot.reply_to(message, "المحتوى قصير جداً (يحتاج 50 حرفاً)")
        return
    
    # استهلاك نقطة
    update_points(user_id, -1)
    
    status = bot.reply_to(message, "جاري تحليل المحاضرة...")
    
    try:
        analysis = analyze_lecture(content)
        if not analysis:
            bot.edit_message_text("فشل تحليل المحاضرة", user_id, status.message_id)
            update_points(user_id, 1)
            return
        
        pdf_path = tempfile.mktemp(suffix='.pdf')
        create_pdf(message.text if message.text else "المحاضرة", analysis, dialect_name, pdf_path)
        
        new_points = get_user(user_id)
        with open(pdf_path, 'rb') as f:
            bot.send_document(user_id, f, caption=f"✅ تم التحليل\n⭐ النقاط المتبقية: {new_points}\n\n@zakros_probot", visible_file_name="lecture.pdf")
        
        os.unlink(pdf_path)
        bot.delete_message(user_id, status.message_id)
        
    except Exception as e:
        bot.edit_message_text(f"❌ خطأ: {str(e)[:100]}", user_id, status.message_id)
        update_points(user_id, 1)

# ========== لوحة تحكم المالك ==========
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
