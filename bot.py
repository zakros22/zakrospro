import os
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import sqlite3
import json
import tempfile
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

# ========== 1. تحميل خط عالمي (يدعم العربية واللاتينية) ==========
FONT_URL = "https://github.com/dejavu-fonts/dejavu-fonts/raw/master/ttf/DejaVuSans.ttf"
FONT_PATH = "DejaVuSans.ttf"
if not os.path.exists(FONT_PATH):
    try:
        r = requests.get(FONT_URL, timeout=30)
        with open(FONT_PATH, "wb") as f:
            f.write(r.content)
    except:
        FONT_PATH = None

def reshape_arabic(text):
    """إعادة تشكيل النص العربي فقط"""
    if any('\u0600' <= c <= '\u06FF' for c in text):
        try:
            reshaped = arabic_reshaper.reshape(text)
            return get_display(reshaped)
        except:
            return text
    return text

def update_progress(user_id, msg_id, stage, percent, details=""):
    """تحديث شريط التقدم مع زخرفة"""
    bar_length = 20
    filled = int(bar_length * percent // 100)
    bar = "█" * filled + "░" * (bar_length - filled)
    text = f"✨ {stage} ✨\n[{bar}] {percent}%\n{details}"
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

# ========== 3. استخراج النص من الملفات ==========
def extract_text_from_file(file_path, user_id, progress_msg_id):
    ext = os.path.splitext(file_path)[1].lower()
    update_progress(user_id, progress_msg_id, "📥 استخراج النص", 10)
    try:
        if ext == '.txt':
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
        elif ext == '.pdf':
            text = ""
            with open(file_path, 'rb') as f:
                reader = PyPDF2.PdfReader(f)
                total_pages = len(reader.pages)
                for i, page in enumerate(reader.pages):
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n"
                    percent = 10 + int((i + 1) / total_pages * 10)
                    update_progress(user_id, progress_msg_id, "📄 استخراج من PDF", percent, f"📑 صفحة {i+1}/{total_pages}")
            return text.strip() if text else None
        elif ext == '.docx':
            doc = docx.Document(file_path)
            return "\n".join([para.text for para in doc.paragraphs])
        elif ext == '.pptx':
            text = ""
            prs = Presentation(file_path)
            for i, slide in enumerate(prs.slides):
                for shape in slide.shapes:
                    if hasattr(shape, "text"):
                        text += shape.text + "\n"
                update_progress(user_id, progress_msg_id, "📊 استخراج من PPTX", 10 + int((i + 1) / len(prs.slides) * 10))
            return text.strip() if text else None
        else:
            return None
    except Exception as e:
        print(f"Extract error: {e}")
        return None

# ========== 4. تحليل المحاضرة ==========
def analyze_lecture(text, user_id, progress_msg_id):
    update_progress(user_id, progress_msg_id, "🔍 تحليل المحاضرة", 20)
    
    basics = text[:500] + "..." if len(text) > 500 else text
    
    update_progress(user_id, progress_msg_id, "✂️ تقسيم المحاضرة", 30)
    
    sentences = re.split(r'(?<=[.!?؟])\s+', text)
    sections = []
    current = ""
    for sent in sentences:
        if len(current) + len(sent) + 2 <= 600:
            current += sent + " "
        else:
            if current:
                sections.append(current.strip())
            current = sent + " "
    if current:
        sections.append(current.strip())
    
    if not sections:
        sections = [text[:500]]
    
    total_sections = len(sections)
    analyzed = []
    
    # الكشف عن اللغة
    has_arabic = any('\u0600' <= c <= '\u06FF' for c in text[:500])
    has_latin = any(c.isalpha() and ord(c) < 128 for c in text[:500])
    
    for i, section in enumerate(sections):
        percent = 30 + int((i + 1) / total_sections * 30)
        update_progress(user_id, progress_msg_id, f"📝 معالجة القسم {i+1}/{total_sections}", percent)
        
        # ترجمة إذا كان النص يحتوي على لاتيني
        if has_latin:
            try:
                translator = GoogleTranslator(source='auto', target='ar')
                translated = translator.translate(section[:2000])
                time.sleep(0.3)
            except:
                translated = section
        else:
            translated = section
        
        explanation = f"📌 يتناول هذا القسم: {section[:150]}..."
        
        analyzed.append({
            "part": i + 1,
            "original": section,
            "translated": translated,
            "explanation": explanation
        })
    
    update_progress(user_id, progress_msg_id, "📝 كتابة الملخص", 85)
    summary = f"📚 تحتوي هذه المحاضرة على {total_sections} أقسام. ملخص عام: {text[:400]}..."
    
    update_progress(user_id, progress_msg_id, "✅ اكتمل التحليل", 95)
    
    return {
        "basics": basics,
        "sections": analyzed,
        "summary": summary,
        "total_sections": total_sections,
        "has_latin": has_latin
    }

# ========== 5. إنشاء PDF ==========
class GlobalPDF(FPDF):
    def header(self):
        if self.page_no() > 1:
            self.set_font('DejaVu', '', 9)
            self.set_text_color(100, 100, 100)
            self.cell(0, 10, f"📄 صفحة {self.page_no()}", 0, 0, 'C')
            self.ln(8)
    
    def footer(self):
        self.set_y(-15)
        self.set_font('DejaVu', '', 8)
        self.set_text_color(128, 128, 128)
        self.cell(0, 10, "✨ @zakros_probot ✨", 0, 0, 'C')

def create_lecture_pdf(title, analysis, dialect_name, user_id, progress_msg_id):
    update_progress(user_id, progress_msg_id, "📄 إنشاء PDF", 97)
    
    pdf = GlobalPDF()
    pdf.add_page()
    
    if FONT_PATH and os.path.exists(FONT_PATH):
        pdf.add_font('DejaVu', '', FONT_PATH, uni=True)
        pdf.set_font('DejaVu', '', 20)
    else:
        pdf.set_font("Helvetica", "", 20)
    
    # ========== الصفحة الأولى ==========
    pdf.set_text_color(0, 51, 102)
    pdf.cell(0, 20, f"📚 تحليل المحاضرة: {title}", 0, 1, 'C')
    
    pdf.set_font_size(11)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(0, 10, f"📅 التاريخ: {datetime.now().strftime('%Y/%m/%d - %H:%M')}", 0, 1, 'C')
    pdf.cell(0, 10, f"🌍 لغة الشرح: {dialect_name}", 0, 1, 'C')
    pdf.ln(10)
    
    pdf.set_draw_color(0, 102, 204)
    pdf.line(30, 70, 180, 70)
    pdf.ln(15)
    
    # ========== الأساسيات ==========
    pdf.set_font_size(16)
    pdf.set_text_color(0, 51, 102)
    pdf.cell(0, 10, "📌 الأساسيات", 0, 1, 'L')
    pdf.set_font_size(11)
    pdf.set_text_color(0, 0, 0)
    pdf.multi_cell(0, 7, reshape_arabic(analysis["basics"]))
    pdf.ln(10)
    
    # ========== الأقسام ==========
    pdf.add_page()
    pdf.set_font_size(16)
    pdf.set_text_color(0, 51, 102)
    pdf.cell(0, 10, f"📚 تقسيم المحاضرة ({analysis['total_sections']} أقسام)", 0, 1, 'L')
    pdf.ln(5)
    
    for item in analysis["sections"]:
        if pdf.get_y() > 250:
            pdf.add_page()
        
        # عنوان القسم
        pdf.set_font_size(14)
        pdf.set_text_color(0, 51, 102)
        pdf.cell(0, 10, f"📖 القسم {item['part']}", 0, 1, 'L')
        
        # النص الأصلي
        pdf.set_font_size(11)
        pdf.set_text_color(0, 0, 150)
        pdf.cell(0, 8, "📜 النص الأصلي:", 0, 1, 'L')
        pdf.set_text_color(0, 0, 0)
        pdf.multi_cell(0, 6, reshape_arabic(item['original'][:500]))
        pdf.ln(3)
        
        # الترجمة (إذا كان هناك لاتيني)
        if analysis["has_latin"]:
            if pdf.get_y() > 250:
                pdf.add_page()
            pdf.set_text_color(0, 100, 0)
            pdf.cell(0, 8, "🌍 الترجمة:", 0, 1, 'L')
            pdf.set_text_color(0, 0, 0)
            pdf.multi_cell(0, 6, reshape_arabic(item['translated'][:500]))
            pdf.ln(3)
        
        # الشرح
        if pdf.get_y() > 250:
            pdf.add_page()
        pdf.set_text_color(150, 100, 0)
        pdf.cell(0, 8, "💡 الشرح:", 0, 1, 'L')
        pdf.set_text_color(0, 0, 0)
        pdf.multi_cell(0, 6, reshape_arabic(item['explanation']))
        pdf.ln(8)
        
        # فاصل
        pdf.set_draw_color(200, 200, 200)
        pdf.line(30, pdf.get_y(), 180, pdf.get_y())
        pdf.ln(5)
    
    # ========== الملخص ==========
    pdf.add_page()
    pdf.set_font_size(16)
    pdf.set_text_color(0, 51, 102)
    pdf.cell(0, 10, "📝 الملخص النهائي", 0, 1, 'L')
    pdf.ln(5)
    pdf.set_font_size(12)
    pdf.set_text_color(0, 0, 0)
    pdf.multi_cell(0, 7, reshape_arabic(analysis["summary"]))
    
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
                bot.send_message(user_id, "✅ تم تفعيل الإحالة! +1 نقطة للداعم.")
                bot.send_message(int(ref), "🎉 مستخدم جديد سجل عبر رابطك! +1 نقطة.")
    
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("📚 تحليل محاضرة", callback_data="new_lecture"),
        InlineKeyboardButton("🎁 مشاركة الرابط", callback_data="share_link")
    )
    if user_id == OWNER_ID:
        markup.add(InlineKeyboardButton("🔧 لوحة التحكم", callback_data="admin_panel"))
    
    bot.send_message(user_id,
        f"✨📚 بوت تحليل المحاضرات 📚✨\n\n"
        f"⭐ رصيدك: {user['points']} نقطة\n"
        f"• كل تحليل محاضرة يستهلك نقطة واحدة.\n"
        f"• احصل على نقاط مجانية عبر مشاركة الرابط (كل 4 مشاركات = نقطة).\n\n"
        f"🔗 رابط إحالتك:\nhttps://t.me/{bot.get_me().username}?start={user_id}\n\n"
        f"✨ @zakros_probot ✨",
        reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "share_link")
def share_link(call):
    user_id = call.message.chat.id
    bot.answer_callback_query(call.id)
    bot.send_message(user_id, f"🎁 رابط إحالتك:\nhttps://t.me/{bot.get_me().username}?start={user_id}\n\n✨ كل 4 مشاركات = نقطة إضافية! ✨")

@bot.callback_query_handler(func=lambda call: call.data == "new_lecture")
def new_lecture(call):
    user_id = call.message.chat.id
    user = get_user(user_id)
    if user["points"] < 1:
        bot.answer_callback_query(call.id, f"⚠️ ليس لديك نقاط كافية! رصيدك: {user['points']} نقطة\nشارك الرابط لتحصل على نقاط!", show_alert=True)
        return
    
    temp_data[user_id] = {"step": "title"}
    bot.edit_message_text("📌 أرسل عنوان المحاضرة", user_id, call.message.message_id)
    bot.register_next_step_handler(call.message, process_title)

def process_title(message):
    user_id = message.chat.id
    temp_data[user_id]["title"] = message.text.strip()
    temp_data[user_id]["step"] = "content"
    bot.send_message(user_id, "📚 أرسل المحاضرة (نص أو ملف PDF/Word/PPTX/TXT)")

@bot.message_handler(content_types=['document', 'text'])
def process_content(message):
    user_id = message.chat.id
    data = temp_data.get(user_id)
    if not data or data.get("step") != "content":
        return
    
    content = None
    progress_msg = bot.send_message(user_id, "🔄 جاري تجهيز المعالجة...")
    
    if message.text and not message.text.startswith('/'):
        content = message.text.strip()
        update_progress(user_id, progress_msg.message_id, "✅ تم استلام النص", 5)
    elif message.document:
        file_name = message.document.file_name
        ext = os.path.splitext(file_name)[1].lower()
        
        if ext not in ['.txt', '.pdf', '.docx', '.pptx']:
            bot.edit_message_text("❌ نوع الملف غير مدعوم. الأنواع المدعومة: txt, pdf, docx, pptx", user_id, progress_msg.message_id)
            return
        
        try:
            file_info = bot.get_file(message.document.file_id)
            downloaded = bot.download_file(file_info.file_path)
            with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
                tmp.write(downloaded)
                tmp_path = tmp.name
            content = extract_text_from_file(tmp_path, user_id, progress_msg.message_id)
            os.unlink(tmp_path)
        except Exception as e:
            bot.edit_message_text(f"❌ فشل قراءة الملف: {str(e)[:100]}", user_id, progress_msg.message_id)
            return
    else:
        bot.edit_message_text("❌ أرسل نصاً أو ملفاً صالحاً.", user_id, progress_msg.message_id)
        return
    
    if not content or len(content.strip()) < 20:
        bot.edit_message_text("❌ النص قصير جداً أو لا يمكن قراءته (يحتاج 20 حرفاً على الأقل).", user_id, progress_msg.message_id)
        return
    
    temp_data[user_id]["content"] = content
    temp_data[user_id]["progress_msg_id"] = progress_msg.message_id
    temp_data[user_id]["step"] = "dialect"
    
    markup = InlineKeyboardMarkup(row_width=2)
    for key, name in DIALECTS.items():
        markup.add(InlineKeyboardButton(name, callback_data=f"dialect_{key}"))
    bot.send_message(user_id, "🌍 اختر لهجة الشرح", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("dialect_"))
def process_dialect(call):
    user_id = call.message.chat.id
    dialect_key = call.data.split("_")[1]
    dialect_name = DIALECTS[dialect_key]
    
    data = temp_data.get(user_id)
    if not data:
        bot.answer_callback_query(call.id, "انتهت الجلسة، ابدأ من جديد", True)
        return
    
    bot.answer_callback_query(call.id)
    bot.delete_message(user_id, call.message.message_id)
    
    progress_msg_id = data.get("progress_msg_id")
    
    try:
        update_points(user_id, -1)
        analysis = analyze_lecture(data["content"], user_id, progress_msg_id)
        pdf_path = create_lecture_pdf(data["title"], analysis, dialect_name, user_id, progress_msg_id)
        new_user = get_user(user_id)
        
        try:
            bot.delete_message(user_id, progress_msg_id)
        except:
            pass
        
        with open(pdf_path, 'rb') as f:
            bot.send_document(user_id, f, caption=f"✨✅ تم تحليل المحاضرة بنجاح! ✅✨\n\n📚 العنوان: {data['title']}\n🌍 اللهجة: {dialect_name}\n📊 عدد الأقسام: {analysis['total_sections']}\n⭐ النقاط المتبقية: {new_user['points']}\n\n✨ @zakros_probot ✨", visible_file_name=f"lecture_{data['title'][:30]}.pdf")
        
        os.unlink(pdf_path)
        del temp_data[user_id]
        
    except Exception as e:
        bot.edit_message_text(f"❌ فشل التحليل: {str(e)[:200]}", user_id, progress_msg_id)
        update_points(user_id, 1)

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
    bot.send_message(OWNER_ID, "🔧 لوحة تحكم المالك", reply_markup=markup)

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
    bot.send_message(OWNER_ID, f"📊 إحصائيات البوت\n\n👥 المستخدمون: {users}\n⭐ مجموع النقاط: {points}\n🔗 عدد الإحالات: {referrals}")

@bot.callback_query_handler(func=lambda call: call.data == "admin_broadcast")
def admin_broadcast(call):
    if call.message.chat.id != OWNER_ID:
        bot.answer_callback_query(call.id, "🔒 غير مصرح", True)
        return
    msg = bot.send_message(OWNER_ID, "📢 أرسل الرسالة التي تريد إذاعتها لجميع المستخدمين:")
    bot.register_next_step_handler(msg, send_broadcast)

def send_broadcast(message):
    broadcast_text = message.text
    c.execute("SELECT user_id FROM users")
    users = c.fetchall()
    success = 0
    for (uid,) in users:
        try:
            bot.send_message(uid, f"📢 إذاعة من المالك:\n\n{broadcast_text}\n\n✨ @zakros_probot ✨")
            success += 1
        except:
            pass
        time.sleep(0.05)
    bot.send_message(OWNER_ID, f"✅ تم إرسال الإذاعة إلى {success} مستخدم.")

if __name__ == "__main__":
    print("✅ بوت تحليل المحاضرات يعمل...")
    bot.remove_webhook()
    bot.infinity_polling()
