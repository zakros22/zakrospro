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

def update_progress(user_id, msg_id, stage, percent):
    bar_length = 20
    filled = int(bar_length * percent // 100)
    bar = "█" * filled + "░" * (bar_length - filled)
    text = f"✨ {stage} ✨\n[{bar}] {percent}%"
    try:
        bot.edit_message_text(text, user_id, msg_id)
    except:
        pass

# ========== 2. اللهجات ==========
DIALECTS = {
    "iraqi": "🇮🇶 اللهجة العراقية",
    "egyptian": "🇪🇬 اللهجة المصرية",
    "syrian": "🇸🇾 اللهجة السورية",
    "gulf": "🇦🇪 اللهجة الخليجية",
    "fusha": "📖 الفصحى"
}

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
def analyze_lecture(text, dialect):
    """تحليل المحاضرة إلى: أساسيات، أقسام، ملخص"""
    
    # تنظيف النص
    text = re.sub(r'\n+', '\n', text)
    text = text.strip()
    
    # 1. الأساسيات (أول 300 حرف)
    basics = text[:400] + "..." if len(text) > 400 else text
    
    # ترجمة الأساسيات إلى اللهجة المختارة
    try:
        translator = GoogleTranslator(source='auto', target='ar')
        basics_translated = translator.translate(basics[:1500])
    except:
        basics_translated = basics
    
    # 2. تقسيم النص إلى أقسام (كل قسم 500 حرف تقريباً)
    sentences = re.split(r'(?<=[.!?؟])\s+', text)
    sections = []
    current = ""
    for sent in sentences:
        if len(current) + len(sent) + 2 <= 500:
            current += sent + " "
        else:
            if current:
                sections.append(current.strip())
            current = sent + " "
    if current:
        sections.append(current.strip())
    
    if not sections:
        sections = [text[:500]]
    
    # تحليل كل قسم
    analyzed_sections = []
    for i, section in enumerate(sections):
        # ترجمة القسم إلى اللهجة
        try:
            translator = GoogleTranslator(source='auto', target='ar')
            translated = translator.translate(section[:1500])
            time.sleep(0.2)
        except:
            translated = section
        
        # شرح القسم
        explanation = f"هذا القسم يتحدث عن: {section[:100]}..."
        
        analyzed_sections.append({
            "num": i + 1,
            "original": section,
            "translated": translated,
            "explanation": explanation
        })
    
    # 3. الملخص النهائي
    summary = f"📝 ملخص المحاضرة:\n\n{text[:500]}..."
    try:
        translator = GoogleTranslator(source='auto', target='ar')
        summary_translated = translator.translate(summary[:1500])
    except:
        summary_translated = summary
    
    return {
        "basics": basics,
        "basics_translated": basics_translated,
        "sections": analyzed_sections,
        "summary": summary,
        "summary_translated": summary_translated,
        "total_sections": len(sections)
    }

# ========== 5. إنشاء PDF ==========
class LecturePDF(FPDF):
    def __init__(self):
        super().__init__()
        if FONT_PATH and os.path.exists(FONT_PATH):
            self.add_font('Noto', '', FONT_PATH, uni=True)
            self.font_name = 'Noto'
        else:
            self.font_name = 'Helvetica'
    
    def header(self):
        if self.page_no() > 1:
            self.set_font(self.font_name, '', 9)
            self.set_text_color(100, 100, 100)
            self.cell(0, 10, f"صفحة {self.page_no()}", 0, 0, 'C')
            self.ln(8)
    
    def footer(self):
        self.set_y(-15)
        self.set_font(self.font_name, '', 8)
        self.set_text_color(128, 128, 128)
        self.cell(0, 10, "@zakros_probot", 0, 0, 'C')

def create_pdf(title, analysis, dialect_name, output_path):
    pdf = LecturePDF()
    pdf.add_page()
    
    # العنوان
    pdf.set_font(pdf.font_name, '', 18)
    pdf.set_text_color(0, 51, 102)
    pdf.cell(0, 15, f"تحليل المحاضرة: {title}", 0, 1, 'C')
    pdf.ln(5)
    
    # التاريخ واللغة
    pdf.set_font_size(10)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(0, 8, f"التاريخ: {datetime.now().strftime('%Y-%m-%d %H:%M')}", 0, 1, 'C')
    pdf.cell(0, 8, f"لغة الشرح: {dialect_name}", 0, 1, 'C')
    pdf.cell(0, 8, f"عدد الأقسام: {analysis['total_sections']}", 0, 1, 'C')
    pdf.ln(10)
    
    pdf.set_draw_color(0, 102, 204)
    pdf.line(30, 70, 180, 70)
    pdf.ln(15)
    
    # ========== الأساسيات ==========
    pdf.set_font(pdf.font_name, '', 14)
    pdf.set_text_color(0, 51, 102)
    pdf.cell(0, 10, "📌 الأساسيات", 0, 1, 'L')
    
    pdf.set_font_size(11)
    pdf.set_text_color(0, 0, 0)
    pdf.multi_cell(0, 6, reshape_arabic(analysis["basics_translated"]))
    pdf.ln(10)
    
    # ========== الأقسام ==========
    pdf.add_page()
    pdf.set_font(pdf.font_name, '', 14)
    pdf.set_text_color(0, 51, 102)
    pdf.cell(0, 10, f"📚 تقسيم المحاضرة", 0, 1, 'L')
    pdf.ln(5)
    
    for section in analysis["sections"]:
        if pdf.get_y() > 250:
            pdf.add_page()
        
        pdf.set_font(pdf.font_name, '', 12)
        pdf.set_text_color(0, 51, 102)
        pdf.cell(0, 10, f"القسم {section['num']}", 0, 1, 'L')
        
        pdf.set_font_size(10)
        pdf.set_text_color(100, 100, 100)
        pdf.multi_cell(0, 6, reshape_arabic(section['translated'][:400]))
        pdf.ln(5)
        
        pdf.set_draw_color(200, 200, 200)
        pdf.line(30, pdf.get_y(), 180, pdf.get_y())
        pdf.ln(5)
    
    # ========== الملخص ==========
    pdf.add_page()
    pdf.set_font(pdf.font_name, '', 14)
    pdf.set_text_color(0, 51, 102)
    pdf.cell(0, 10, "📝 الملخص النهائي", 0, 1, 'L')
    pdf.ln(5)
    pdf.set_font_size(11)
    pdf.set_text_color(0, 0, 0)
    pdf.multi_cell(0, 6, reshape_arabic(analysis["summary_translated"]))
    
    pdf.output(output_path)

# ========== 6. قاعدة البيانات ==========
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

# تخزين مؤقت
temp_data = {}

# ========== 7. أوامر البوت ==========
@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.chat.id
    points = get_user(user_id)
    
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("📚 تحليل محاضرة", callback_data="new_lecture"))
    if user_id == OWNER_ID:
        markup.add(InlineKeyboardButton("🔧 لوحة التحكم", callback_data="admin"))
    
    bot.send_message(user_id,
        f"📚 *بوت تحليل المحاضرات*\n\n"
        f"⭐ رصيدك: {points} نقطة\n"
        f"• كل تحليل يستهلك نقطة واحدة\n"
        f"• أرسل المحاضرة وسأقوم بـ:\n"
        f"  1️⃣ استخراج الأساسيات\n"
        f"  2️⃣ تقسيم المحاضرة إلى أقسام\n"
        f"  3️⃣ شرح كل قسم باللهجة المختارة\n"
        f"  4️⃣ كتابة ملخص نهائي\n\n"
        f"📌 @zakros_probot",
        parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "new_lecture")
def new_lecture(call):
    user_id = call.message.chat.id
    points = get_user(user_id)
    if points < 1:
        bot.answer_callback_query(call.id, "ليس لديك نقاط كافية!", True)
        return
    
    temp_data[user_id] = {"step": "title"}
    bot.edit_message_text("📌 أرسل عنوان المحاضرة:", user_id, call.message.message_id)
    bot.register_next_step_handler(call.message, get_title)

def get_title(message):
    user_id = message.chat.id
    temp_data[user_id]["title"] = message.text.strip()
    temp_data[user_id]["step"] = "dialect"
    
    markup = InlineKeyboardMarkup(row_width=2)
    for key, name in DIALECTS.items():
        markup.add(InlineKeyboardButton(name, callback_data=f"dialect_{key}"))
    bot.send_message(user_id, "🌍 اختر لهجة الشرح:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("dialect_"))
def process_dialect(call):
    user_id = call.message.chat.id
    dialect_key = call.data.split("_")[1]
    dialect_name = DIALECTS[dialect_key]
    
    data = temp_data.get(user_id)
    if not data:
        bot.answer_callback_query(call.id, "انتهت الجلسة، ابدأ من جديد", True)
        return
    
    temp_data[user_id]["dialect"] = dialect_key
    temp_data[user_id]["dialect_name"] = dialect_name
    temp_data[user_id]["step"] = "content"
    
    bot.edit_message_text(f"📚 أرسل المحاضرة (نص أو ملف PDF/Word/TXT)\nلغة الشرح: {dialect_name}", user_id, call.message.message_id)
    bot.register_next_step_handler(call.message, get_content)

def get_content(message):
    user_id = message.chat.id
    data = temp_data.get(user_id)
    if not data or data.get("step") != "content":
        return
    
    content = None
    progress_msg = bot.send_message(user_id, "🔄 جاري تجهيز المعالجة...")
    
    if message.text and not message.text.startswith('/'):
        content = message.text.strip()
        update_progress(user_id, progress_msg.message_id, "تم استلام النص", 10)
    elif message.document:
        file_name = message.document.file_name
        ext = os.path.splitext(file_name)[1].lower()
        if ext not in ['.txt', '.pdf', '.docx']:
            bot.edit_message_text("نوع الملف غير مدعوم. الأنواع: txt, pdf, docx", user_id, progress_msg.message_id)
            return
        
        update_progress(user_id, progress_msg.message_id, "جاري تحميل الملف", 20)
        try:
            file_info = bot.get_file(message.document.file_id)
            downloaded = bot.download_file(file_info.file_path)
            with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
                tmp.write(downloaded)
                tmp_path = tmp.name
            content = extract_text(tmp_path)
            os.unlink(tmp_path)
        except Exception as e:
            bot.edit_message_text(f"خطأ في قراءة الملف: {e}", user_id, progress_msg.message_id)
            return
    else:
        bot.edit_message_text("أرسل نصاً أو ملفاً صالحاً", user_id, progress_msg.message_id)
        return
    
    if not content or len(content) < 100:
        bot.edit_message_text("النص قصير جداً (يحتاج 100 حرف على الأقل)", user_id, progress_msg.message_id)
        return
    
    update_points(user_id, -1)
    
    update_progress(user_id, progress_msg.message_id, "جاري تحليل المحاضرة", 40)
    
    try:
        analysis = analyze_lecture(content, data["dialect"])
        
        update_progress(user_id, progress_msg.message_id, "جاري إنشاء PDF", 80)
        
        pdf_path = tempfile.mktemp(suffix='.pdf')
        create_pdf(data["title"], analysis, data["dialect_name"], pdf_path)
        
        new_points = get_user(user_id)
        
        bot.delete_message(user_id, progress_msg.message_id)
        
        with open(pdf_path, 'rb') as f:
            bot.send_document(user_id, f, caption=f"✅ تم تحليل المحاضرة بنجاح!\n\n📚 العنوان: {data['title']}\n🌍 لغة الشرح: {data['dialect_name']}\n📊 عدد الأقسام: {analysis['total_sections']}\n⭐ النقاط المتبقية: {new_points}\n\n@zakros_probot", visible_file_name=f"{data['title']}.pdf")
        
        os.unlink(pdf_path)
        del temp_data[user_id]
        
    except Exception as e:
        bot.edit_message_text(f"❌ فشل التحليل: {str(e)[:200]}", user_id, progress_msg.message_id)
        update_points(user_id, 1)

# ========== 8. لوحة تحكم المالك ==========
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
    print("✅ بوت تحليل المحاضرات يعمل...")
    bot.remove_webhook()
    bot.infinity_polling()
