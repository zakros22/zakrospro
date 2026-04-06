import os
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import sqlite3
import json
import tempfile
import string
import random
from datetime import datetime
import time
import threading
import re
import requests
from fpdf import FPDF
import arabic_reshaper
from bidi.algorithm import get_display
from deep_translator import GoogleTranslator
import PyPDF2
import docx
from pptx import Presentation

BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise Exception("BOT_TOKEN not set")

bot = telebot.TeleBot(BOT_TOKEN)
OWNER_ID = 7021542402

# ========== 1. تحميل خط يدعم اللغة العربية ==========
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
        reshaped = arabic_reshaper.reshape(text)
        return get_display(reshaped)
    return text

# ========== 2. اللهجات ==========
DIALECTS = {
    "iraqi": "اللهجة العراقية",
    "egyptian": "اللهجة المصرية",
    "syrian": "اللهجة السورية",
    "gulf": "اللهجة الخليجية",
    "fusha": "الفصحى"
}

def translate_to_dialect(text, dialect):
    """ترجمة النص إلى اللهجة المطلوبة"""
    if dialect == "fusha":
        return text
    try:
        translator = GoogleTranslator(source='auto', target='ar')
        translated = translator.translate(text)
        return translated
    except:
        return text

# ========== 3. استخراج النص من الملفات ==========
def extract_text_from_file(file_path):
    ext = os.path.splitext(file_path)[1].lower()
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

# ========== 4. تحليل المحاضرة ==========
def analyze_lecture(text):
    """تقسيم المحاضرة إلى أقسام وشرحها"""
    sentences = re.split(r'(?<=[.!?؟])\s+', text)
    sections = []
    current_section = ""
    for sent in sentences:
        if len(current_section) + len(sent) + 2 <= 800:
            current_section += sent + " "
        else:
            if current_section:
                sections.append(current_section.strip())
            current_section = sent + " "
    if current_section:
        sections.append(current_section.strip())
    
    analyzed = []
    for i, section in enumerate(sections):
        # ترجمة القسم إلى العربية
        try:
            translator = GoogleTranslator(source='auto', target='ar')
            translated = translator.translate(section)
        except:
            translated = section
        
        # شرح مبسط
        summary = f"هذا القسم يتحدث عن: {section[:150]}..."
        
        analyzed.append({
            "original": section,
            "translated": translated,
            "summary": summary,
            "part": i + 1
        })
    return analyzed

# ========== 5. إنشاء PDF ==========
def create_lecture_pdf(lecture_title, analyzed, dialect_name, user_id):
    pdf = FPDF()
    pdf.add_page()
    
    if FONT_PATH and os.path.exists(FONT_PATH):
        pdf.add_font('Noto', '', FONT_PATH, uni=True)
        pdf.set_font('Noto', '', 20)
    else:
        pdf.set_font("Helvetica", "", 20)
    
    # العنوان
    pdf.set_text_color(0, 51, 102)
    title_text = reshape_arabic(f"تحليل المحاضرة: {lecture_title}")
    pdf.cell(0, 20, title_text, 0, 1, 'C')
    pdf.ln(5)
    
    # تاريخ
    pdf.set_font_size(10)
    pdf.set_text_color(100, 100, 100)
    date_text = reshape_arabic(f"التاريخ: {datetime.now().strftime('%Y/%m/%d')}")
    pdf.cell(0, 8, date_text, 0, 1, 'C')
    pdf.ln(5)
    
    # اللغة المستخدمة في الشرح
    lang_text = reshape_arabic(f"لغة الشرح: {dialect_name}")
    pdf.cell(0, 8, lang_text, 0, 1, 'C')
    pdf.ln(10)
    
    # خط فاصل
    pdf.set_draw_color(0, 102, 204)
    pdf.line(30, 60, 180, 60)
    pdf.ln(10)
    
    for i, item in enumerate(analyzed):
        # القسم
        pdf.set_font_size(14)
        pdf.set_text_color(0, 51, 102)
        part_text = reshape_arabic(f"القسم {item['part']}")
        pdf.cell(0, 10, part_text, 0, 1, 'L')
        
        # النص الأصلي
        pdf.set_font_size(11)
        pdf.set_text_color(0, 0, 150)
        pdf.cell(0, 8, reshape_arabic("النص الأصلي:"), 0, 1, 'L')
        pdf.set_text_color(0, 0, 0)
        pdf.multi_cell(0, 6, reshape_arabic(item['original'][:500]))
        pdf.ln(3)
        
        # الترجمة
        pdf.set_text_color(0, 100, 0)
        pdf.cell(0, 8, reshape_arabic("الترجمة:"), 0, 1, 'L')
        pdf.set_text_color(0, 0, 0)
        pdf.multi_cell(0, 6, reshape_arabic(item['translated'][:500]))
        pdf.ln(3)
        
        # الشرح
        pdf.set_text_color(150, 100, 0)
        pdf.cell(0, 8, reshape_arabic("الشرح:"), 0, 1, 'L')
        pdf.set_text_color(0, 0, 0)
        pdf.multi_cell(0, 6, reshape_arabic(item['summary']))
        pdf.ln(8)
        
        # فاصل بين الأقسام
        pdf.set_draw_color(200, 200, 200)
        pdf.line(30, pdf.get_y(), 180, pdf.get_y())
        pdf.ln(5)
        
        if pdf.get_y() > 250:
            pdf.add_page()
    
    # حقوق البوت
    pdf.set_y(-25)
    pdf.set_font_size(9)
    pdf.set_text_color(128, 128, 128)
    pdf.cell(0, 8, reshape_arabic("@zakros_probot"), 0, 0, 'C')
    
    path = tempfile.mktemp(suffix='.pdf')
    pdf.output(path)
    return path

# ========== 6. قاعدة البيانات ==========
conn = sqlite3.connect("lecture_bot.db", check_same_thread=False)
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    points INTEGER DEFAULT 1,
    total_shares INTEGER DEFAULT 0
)''')
c.execute('''CREATE TABLE IF NOT EXISTS referrals (
    referrer_id INTEGER,
    referred_id INTEGER,
    date TEXT
)''')
conn.commit()

def get_user(user_id):
    c.execute("SELECT points, total_shares FROM users WHERE user_id=?", (user_id,))
    row = c.fetchone()
    if not row:
        c.execute("INSERT INTO users (user_id, points, total_shares) VALUES (?,?,?)", (user_id, 1, 0))
        conn.commit()
        return {"points": 1, "total_shares": 0}
    return {"points": row[0], "total_shares": row[1]}

def update_points(user_id, delta):
    c.execute("UPDATE users SET points = points + ? WHERE user_id=?", (delta, user_id))
    conn.commit()

def add_share(user_id):
    c.execute("UPDATE users SET total_shares = total_shares + 1 WHERE user_id=?", (user_id,))
    c.execute("SELECT total_shares FROM users WHERE user_id=?", (user_id,))
    shares = c.fetchone()[0]
    if shares % 4 == 0:
        c.execute("UPDATE users SET points = points + 1 WHERE user_id=?", (user_id,))
    conn.commit()

def add_referral(referrer_id, referred_id):
    c.execute("SELECT * FROM referrals WHERE referred_id=?", (referred_id,))
    if c.fetchone():
        return False
    c.execute("INSERT INTO referrals (referrer_id, referred_id, date) VALUES (?,?,?)", 
              (referrer_id, referred_id, datetime.now().isoformat()))
    update_points(referrer_id, 1)
    conn.commit()
    return True

# تخزين مؤقت
temp_data = {}

# ========== 7. أوامر البوت ==========
@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.chat.id
    user = get_user(user_id)
    
    if len(message.text.split()) > 1:
        ref = message.text.split()[1]
        if ref.isdigit() and int(ref) != user_id:
            if add_referral(int(ref), user_id):
                bot.send_message(user_id, "✅ تم تفعيل الإحالة! حصل الداعم على نقطة.")
                bot.send_message(int(ref), "🎉 مستخدم جديد سجل عبر رابطك! +1 نقطة.")
    
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("📚 تحليل محاضرة", callback_data="new_lecture"),
        InlineKeyboardButton("🎁 مشاركة الرابط", callback_data="share_link")
    )
    if user_id == OWNER_ID:
        markup.add(InlineKeyboardButton("🔧 لوحة التحكم", callback_data="admin_panel"))
    
    bot.send_message(user_id,
        f"📚 *بوت تحليل المحاضرات*\n\n"
        f"⭐ رصيدك: {user['points']} نقطة\n"
        f"• كل تحليل محاضرة يستهلك نقطة واحدة.\n"
        f"• يمكنك الحصول على نقاط مجانية عبر مشاركة الرابط (كل 4 مشاركات = نقطة).\n\n"
        f"🔗 رابط إحالتك:\nhttps://t.me/{bot.get_me().username}?start={user_id}\n\n"
        f"📌 @zakros_probot",
        parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "share_link")
def share_link(call):
    user_id = call.message.chat.id
    bot.answer_callback_query(call.id)
    bot.send_message(user_id, f"🎁 رابط إحالتك:\nhttps://t.me/{bot.get_me().username}?start={user_id}\n\nكل 4 مشاركات = نقطة إضافية!")

@bot.callback_query_handler(func=lambda call: call.data == "new_lecture")
def new_lecture(call):
    user_id = call.message.chat.id
    user = get_user(user_id)
    if user["points"] < 1:
        bot.answer_callback_query(call.id, f"⚠️ ليس لديك نقاط كافية! رصيدك: {user['points']} نقطة\nشارك الرابط لتحصل على نقاط!", show_alert=True)
        return
    
    temp_data[user_id] = {"step": "title"}
    bot.edit_message_text("📌 *أرسل عنوان المحاضرة*", user_id, call.message.message_id, parse_mode="Markdown")
    bot.register_next_step_handler(call.message, process_title)

def process_title(message):
    user_id = message.chat.id
    temp_data[user_id]["title"] = message.text.strip()
    temp_data[user_id]["step"] = "content"
    bot.send_message(user_id, "📚 *أرسل المحاضرة (نص أو ملف PDF/Word/PPTX/TXT)*", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.chat.id in temp_data and temp_data.get(m.chat.id, {}).get("step") == "content")
def process_content(message):
    user_id = message.chat.id
    text = None
    
    if message.text and not message.text.startswith('/'):
        text = message.text.strip()
    elif message.document:
        file_name = message.document.file_name
        ext = os.path.splitext(file_name)[1].lower()
        if ext not in ['.txt', '.pdf', '.docx', '.pptx']:
            bot.send_message(user_id, "❌ نوع الملف غير مدعوم. الأنواع المدعومة: txt, pdf, docx, pptx")
            return
        
        status = bot.send_message(user_id, "📥 جاري تحميل الملف...")
        try:
            file_info = bot.get_file(message.document.file_id)
            downloaded = bot.download_file(file_info.file_path)
            with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
                tmp.write(downloaded)
                tmp_path = tmp.name
            text = extract_text_from_file(tmp_path)
            os.unlink(tmp_path)
            bot.delete_message(user_id, status.message_id)
        except Exception as e:
            bot.edit_message_text(f"❌ فشل قراءة الملف: {e}", user_id, status.message_id)
            return
    else:
        bot.send_message(user_id, "❌ أرسل نصاً أو ملفاً صالحاً.")
        return
    
    if not text or len(text.strip()) < 20:
        bot.send_message(user_id, "❌ النص قصير جداً أو لا يمكن قراءته.")
        return
    
    temp_data[user_id]["content"] = text
    temp_data[user_id]["step"] = "dialect"
    
    markup = InlineKeyboardMarkup(row_width=2)
    for key, name in DIALECTS.items():
        markup.add(InlineKeyboardButton(name, callback_data=f"dialect_{key}"))
    bot.send_message(user_id, "🌍 *اختر لهجة الشرح*", parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("dialect_"))
def process_dialect(call):
    user_id = call.message.chat.id
    dialect_key = call.data.split("_")[1]
    dialect_name = DIALECTS[dialect_key]
    
    data = temp_data.get(user_id)
    if not data:
        bot.answer_callback_query(call.id, "انتهت الجلسة، ابدأ من جديد", True)
        return
    
    bot.answer_callback_query(call.id, f"جاري تحليل المحاضرة إلى {dialect_name}...")
    bot.edit_message_reply_markup(user_id, call.message.message_id, reply_markup=None)
    
    status = bot.send_message(user_id, "🔄 جاري تحليل المحاضرة...")
    
    try:
        # استهلاك نقطة
        update_points(user_id, -1)
        
        # تحليل المحاضرة
        analyzed = analyze_lecture(data["content"])
        
        # إنشاء PDF
        pdf_path = create_lecture_pdf(data["title"], analyzed, dialect_name, user_id)
        
        new_user = get_user(user_id)
        bot.delete_message(user_id, status.message_id)
        
        with open(pdf_path, 'rb') as f:
            bot.send_document(user_id, f, caption=f"✅ تم تحليل المحاضرة\n📚 {data['title']}\n🌍 اللهجة: {dialect_name}\n⭐ النقاط المتبقية: {new_user['points']}\n\n@zakros_probot", visible_file_name=f"lecture_{data['title']}.pdf")
        
        os.unlink(pdf_path)
        del temp_data[user_id]
        
    except Exception as e:
        bot.edit_message_text(f"❌ فشل التحليل: {str(e)[:200]}", user_id, status.message_id)

# ========== 8. لوحة تحكم المالك ==========
@bot.callback_query_handler(func=lambda call: call.data == "admin_panel")
def admin_panel(call):
    if call.message.chat.id != OWNER_ID:
        bot.answer_callback_query(call.id, "🔒 غير مصرح", True)
        return
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("➕ إضافة نقاط", callback_data="admin_add_points"),
        InlineKeyboardButton("➖ خصم نقاط", callback_data="admin_remove_points"),
        InlineKeyboardButton("📊 إحصائيات", callback_data="admin_stats"),
        InlineKeyboardButton("📢 إذاعة", callback_data="admin_broadcast")
    )
    bot.send_message(OWNER_ID, "🔧 *لوحة تحكم المالك*", parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "admin_add_points")
def admin_add_points(call):
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
        bot.send_message(OWNER_ID, "❌ صيغة غير صحيحة. أرسل: user_id points")

@bot.callback_query_handler(func=lambda call: call.data == "admin_remove_points")
def admin_remove_points(call):
    if call.message.chat.id != OWNER_ID:
        return
    msg = bot.send_message(OWNER_ID, "أرسل معرف المستخدم وعدد النقاط (مثال: 123456789 3):")
    bot.register_next_step_handler(msg, remove_points_step)

def remove_points_step(message):
    try:
        uid, pts = map(int, message.text.split())
        update_points(uid, -pts)
        bot.send_message(OWNER_ID, f"✅ تم خصم {pts} نقطة من المستخدم {uid}")
    except:
        bot.send_message(OWNER_ID, "❌ صيغة غير صحيحة")

@bot.callback_query_handler(func=lambda call: call.data == "admin_stats")
def admin_stats(call):
    if call.message.chat.id != OWNER_ID:
        return
    c.execute("SELECT COUNT(*) FROM users")
    users = c.fetchone()[0]
    c.execute("SELECT SUM(points) FROM users")
    points = c.fetchone()[0] or 0
    c.execute("SELECT COUNT(*) FROM referrals")
    referrals = c.fetchone()[0]
    bot.send_message(OWNER_ID, f"📊 *إحصائيات البوت*\n\n👥 المستخدمون: {users}\n⭐ مجموع النقاط: {points}\n🔗 عدد الإحالات: {referrals}", parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data == "admin_broadcast")
def admin_broadcast(call):
    if call.message.chat.id != OWNER_ID:
        bot.answer_callback_query(call.id, "🔒 غير مصرح", True)
        return
    msg = bot.send_message(OWNER_ID, "📢 أرسل الرسالة التي تريد إذاعتها:")
    bot.register_next_step_handler(msg, send_broadcast)

def send_broadcast(message):
    broadcast_text = message.text
    c.execute("SELECT user_id FROM users")
    users = c.fetchall()
    success = 0
    for (uid,) in users:
        try:
            bot.send_message(uid, f"📢 إذاعة من المالك:\n\n{broadcast_text}\n\n@zakros_probot")
            success += 1
        except:
            pass
        time.sleep(0.05)
    bot.send_message(OWNER_ID, f"✅ تم إرسال الإذاعة إلى {success} مستخدم.")

if __name__ == "__main__":
    print("✅ بوت تحليل المحاضرات يعمل...")
    bot.remove_webhook()
    bot.infinity_polling()
