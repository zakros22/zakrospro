import os
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import sqlite3
import json
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
from pptx import Presentation
from langdetect import detect

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
        print("Downloading font...")
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

def detect_language(text):
    """تحديد لغة النص"""
    try:
        lang = detect(text[:500])
        if lang == 'ar':
            return 'arabic', 'العربية'
        else:
            return 'english', 'English'
    except:
        return 'unknown', 'غير معروف'

def translate_text(text, source_lang, target_lang):
    """ترجمة النص"""
    try:
        translator = GoogleTranslator(source=source_lang, target=target_lang)
        return translator.translate(text[:3000])
    except:
        return text

def clean_text(text):
    """تنظيف النص"""
    text = re.sub(r'\n+', '\n', text)
    text = re.sub(r' +', ' ', text)
    return text.strip()

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
    "arabic": "🇸🇦 العربية",
    "english": "🇬🇧 English"
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
                    percent = 10 + int((i + 1) / total_pages * 20)
                    update_progress(user_id, progress_msg_id, "📄 استخراج من PDF", percent)
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
            return text.strip() if text else None
        else:
            return None
    except Exception as e:
        print(f"Extract error: {e}")
        return None

# ========== 4. تحليل المحاضرة ==========
def analyze_lecture(text, target_lang, user_id, progress_msg_id):
    update_progress(user_id, progress_msg_id, "🔍 تحليل المحاضرة", 30)
    
    text = clean_text(text)
    source_lang, source_name = detect_language(text)
    
    update_progress(user_id, progress_msg_id, f"🌍 اللغة المكتشفة: {source_name}", 40)
    
    # تقسيم النص إلى فقرات
    paragraphs = text.split('\n')
    paragraphs = [p for p in paragraphs if len(p.strip()) > 20]
    
    if not paragraphs:
        paragraphs = [text[:500]]
    
    total = len(paragraphs)
    analyzed = []
    
    for i, para in enumerate(paragraphs[:30]):  # حد أقصى 30 فقرة
        percent = 40 + int((i + 1) / total * 50)
        update_progress(user_id, progress_msg_id, f"📝 معالجة الفقرة {i+1}/{total}", percent)
        
        # ترجمة النص
        if target_lang == 'arabic':
            translated = translate_text(para, 'en', 'ar')
        else:
            translated = translate_text(para, 'ar', 'en')
        
        # شرح مبسط
        explanation = f"📌 هذه الفقرة تتحدث عن: {para[:100]}..."
        if target_lang == 'arabic':
            explanation_ar = translate_text(explanation, 'en', 'ar')
        else:
            explanation_ar = translate_text(explanation, 'ar', 'en')
        
        analyzed.append({
            "part": i + 1,
            "original": para,
            "translated": translated,
            "explanation": explanation_ar
        })
    
    update_progress(user_id, progress_msg_id, "📝 كتابة الملخص", 90)
    
    # ملخص
    summary = text[:500] + "..." if len(text) > 500 else text
    if target_lang == 'arabic':
        summary_translated = translate_text(summary, 'en', 'ar')
    else:
        summary_translated = translate_text(summary, 'ar', 'en')
    
    update_progress(user_id, progress_msg_id, "✅ اكتمل التحليل", 95)
    
    return {
        "source_lang": source_name,
        "target_lang": "العربية" if target_lang == 'arabic' else "English",
        "total_paragraphs": len(analyzed),
        "paragraphs": analyzed,
        "summary": summary,
        "summary_translated": summary_translated
    }

# ========== 5. إنشاء PDF ==========
class BilingualPDF(FPDF):
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
            self.cell(0, 10, f"📄 صفحة {self.page_no()}", 0, 0, 'C')
            self.ln(8)
    
    def footer(self):
        self.set_y(-15)
        self.set_font(self.font_name, '', 8)
        self.set_text_color(128, 128, 128)
        self.cell(0, 10, "✨ @zakros_probot ✨", 0, 0, 'C')
    
    def add_section(self, title, original_text, translated_text, explanation):
        self.set_font(self.font_name, '', 14)
        self.set_text_color(0, 51, 102)
        self.cell(0, 10, title, 0, 1, 'L')
        
        self.set_font(self.font_name, '', 11)
        self.set_text_color(0, 0, 150)
        self.cell(0, 8, "📖 النص الأصلي:", 0, 1, 'L')
        self.set_text_color(0, 0, 0)
        self.multi_cell(0, 6, reshape_arabic(original_text))
        self.ln(3)
        
        self.set_text_color(0, 100, 0)
        self.cell(0, 8, "🌍 الترجمة:", 0, 1, 'L')
        self.set_text_color(0, 0, 0)
        self.multi_cell(0, 6, reshape_arabic(translated_text))
        self.ln(3)
        
        self.set_text_color(150, 100, 0)
        self.cell(0, 8, "💡 الشرح:", 0, 1, 'L')
        self.set_text_color(0, 0, 0)
        self.multi_cell(0, 6, reshape_arabic(explanation))
        self.ln(8)
        
        self.set_draw_color(200, 200, 200)
        self.line(30, self.get_y(), 180, self.get_y())
        self.ln(5)

def create_lecture_pdf(title, analysis, user_id, progress_msg_id):
    update_progress(user_id, progress_msg_id, "📄 إنشاء PDF", 97)
    
    pdf = BilingualPDF()
    pdf.add_page()
    
    # العنوان
    pdf.set_font(pdf.font_name, '', 20)
    pdf.set_text_color(0, 51, 102)
    pdf.cell(0, 20, f"📚 تحليل المحاضرة: {title}", 0, 1, 'C')
    
    # المعلومات
    pdf.set_font_size(11)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(0, 10, f"📅 التاريخ: {datetime.now().strftime('%Y/%m/%d - %H:%M')}", 0, 1, 'C')
    pdf.cell(0, 10, f"🌍 اللغة المصدر: {analysis['source_lang']}", 0, 1, 'C')
    pdf.cell(0, 10, f"🎯 اللغة الهدف: {analysis['target_lang']}", 0, 1, 'C')
    pdf.cell(0, 10, f"📊 عدد الفقرات: {analysis['total_paragraphs']}", 0, 1, 'C')
    pdf.ln(10)
    
    pdf.set_draw_color(0, 102, 204)
    pdf.line(30, 100, 180, 100)
    pdf.ln(15)
    
    # الأقسام
    for item in analysis["paragraphs"]:
        if pdf.get_y() > 250:
            pdf.add_page()
        pdf.add_section(f"📖 القسم {item['part']}", item['original'], item['translated'], item['explanation'])
    
    # الملخص
    pdf.add_page()
    pdf.set_font(pdf.font_name, '', 16)
    pdf.set_text_color(0, 51, 102)
    pdf.cell(0, 10, "📝 الملخص النهائي", 0, 1, 'L')
    pdf.ln(5)
    
    pdf.set_font(pdf.font_name, '', 11)
    pdf.set_text_color(0, 0, 150)
    pdf.cell(0, 8, "📖 الملخص الأصلي:", 0, 1, 'L')
    pdf.set_text_color(0, 0, 0)
    pdf.multi_cell(0, 6, reshape_arabic(analysis["summary"]))
    pdf.ln(3)
    
    pdf.set_text_color(0, 100, 0)
    pdf.cell(0, 8, "🌍 الملخص المترجم:", 0, 1, 'L')
    pdf.set_text_color(0, 0, 0)
    pdf.multi_cell(0, 6, reshape_arabic(analysis["summary_translated"]))
    
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
        f"✨📚 بوت تحليل المحاضرات ثنائي اللغة 📚✨\n\n"
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
    temp_data[user_id]["step"] = "target_lang"
    
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("🇸🇦 العربية", callback_data="target_arabic"),
        InlineKeyboardButton("🇬🇧 English", callback_data="target_english")
    )
    bot.send_message(user_id, "🌍 اختر اللغة التي تريد الترجمة إليها:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("target_"))
def process_target_lang(call):
    user_id = call.message.chat.id
    target_lang = call.data.split("_")[1]
    temp_data[user_id]["target_lang"] = target_lang
    temp_data[user_id]["step"] = "content"
    
    bot.edit_message_text("📚 أرسل المحاضرة (نص أو ملف PDF/Word/PPTX/TXT)", user_id, call.message.message_id)
    bot.register_next_step_handler(call.message, process_content)

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
    
    if not content or len(content.strip()) < 50:
        bot.edit_message_text("❌ النص قصير جداً أو لا يمكن قراءته (يحتاج 50 حرفاً على الأقل).", user_id, progress_msg.message_id)
        return
    
    temp_data[user_id]["content"] = content
    temp_data[user_id]["progress_msg_id"] = progress_msg.message_id
    
    try:
        update_points(user_id, -1)
        analysis = analyze_lecture(content, data["target_lang"], user_id, progress_msg.message_id)
        pdf_path = create_lecture_pdf(data["title"], analysis, user_id, progress_msg.message_id)
        new_user = get_user(user_id)
        
        try:
            bot.delete_message(user_id, progress_msg.message_id)
        except:
            pass
        
        with open(pdf_path, 'rb') as f:
            bot.send_document(user_id, f, caption=f"✨✅ تم تحليل المحاضرة بنجاح! ✅✨\n\n📚 العنوان: {data['title']}\n🌍 اللغة المصدر: {analysis['source_lang']}\n🎯 اللغة الهدف: {analysis['target_lang']}\n📊 عدد الفقرات: {analysis['total_paragraphs']}\n⭐ النقاط المتبقية: {new_user['points']}\n\n✨ @zakros_probot ✨", visible_file_name=f"lecture_{data['title'][:30]}.pdf")
        
        os.unlink(pdf_path)
        del temp_data[user_id]
        
    except Exception as e:
        bot.edit_message_text(f"❌ فشل التحليل: {str(e)[:200]}", user_id, progress_msg.message_id)
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
    print("✅ بوت تحليل المحاضرات ثنائي اللغة يعمل...")
    bot.remove_webhook()
    bot.infinity_polling()
