import os
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import sqlite3
import tempfile
import re
import requests
from PIL import Image, ImageDraw, ImageFont
from moviepy.editor import ImageClip, concatenate_videoclips
import PyPDF2
import docx

BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise Exception("BOT_TOKEN not set")

bot = telebot.TeleBot(BOT_TOKEN)
OWNER_ID = 7021542402

# ========== 1. قاعدة البيانات ==========
conn = sqlite3.connect("video.db", check_same_thread=False)
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    points INTEGER DEFAULT 2
)''')
c.execute('''CREATE TABLE IF NOT EXISTS images (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    keyword TEXT,
    file_id TEXT
)''')
conn.commit()

def get_user(user_id):
    c.execute("SELECT points FROM users WHERE user_id=?", (user_id,))
    row = c.fetchone()
    if not row:
        c.execute("INSERT INTO users (user_id, points) VALUES (?,?)", (user_id, 2))
        conn.commit()
        return 2
    return row[0]

def update_points(user_id, delta):
    c.execute("UPDATE users SET points = points + ? WHERE user_id=?", (delta, user_id))
    conn.commit()

def add_image(keyword, file_id):
    c.execute("INSERT INTO images (keyword, file_id) VALUES (?,?)", (keyword, file_id))
    conn.commit()

def get_image_by_keyword(text):
    words = text.lower().split()
    c.execute("SELECT keyword, file_id FROM images")
    images = c.fetchall()
    for keyword, file_id in images:
        if keyword.lower() in text.lower() or keyword.lower() in words:
            return file_id
    return None

def get_all_images():
    c.execute("SELECT keyword, file_id FROM images")
    return c.fetchall()

# ========== 2. استخراج النص من الملفات ==========
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
                    text += page.extract_text() + "\n"
            return text
        elif ext == '.docx':
            doc = docx.Document(file_path)
            return "\n".join([para.text for para in doc.paragraphs])
        else:
            return None
    except:
        return None

# ========== 3. تحليل المحاضرة ==========
def analyze_lecture(text):
    """تقسيم المحاضرة إلى أقسام"""
    sentences = re.split(r'(?<=[.!?؟])\s+', text)
    parts = []
    current = ""
    for sent in sentences:
        if len(current) + len(sent) + 2 <= 200:
            current += sent + " "
        else:
            if current:
                parts.append(current.strip())
            current = sent + " "
    if current:
        parts.append(current.strip())
    
    if not parts:
        parts = [text[:200]]
    
    return parts

# ========== 4. إنشاء فيديو ==========
def create_video(parts, output_path, duration_per_slide=3):
    try:
        clips = []
        for part in parts:
            # البحث عن صورة مناسبة
            file_id = get_image_by_keyword(part)
            
            if file_id:
                # تحميل الصورة من تلغرام
                file_info = bot.get_file(file_id)
                downloaded = bot.download_file(file_info.file_path)
                img_path = tempfile.mktemp(suffix='.jpg')
                with open(img_path, 'wb') as f:
                    f.write(downloaded)
            else:
                # إنشاء صورة نصية
                img_path = create_text_image(part)
            
            if img_path:
                clip = ImageClip(img_path).set_duration(duration_per_slide).resize(height=720)
                clips.append(clip)
                if os.path.exists(img_path):
                    os.unlink(img_path)
        
        if not clips:
            return False
        
        video = concatenate_videoclips(clips, method="compose")
        video.write_videofile(output_path, fps=24, codec='libx264', threads=2, logger=None)
        video.close()
        return True
    except Exception as e:
        print(f"Video error: {e}")
        return False

def create_text_image(text, width=1280, height=720):
    try:
        img_path = tempfile.mktemp(suffix='.png')
        img = Image.new('RGB', (width, height), color=(30, 40, 80))
        draw = ImageDraw.Draw(img)
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 30)
        except:
            font = ImageFont.load_default()
        
        # تقسيم النص
        lines = []
        words = text.split()
        line = ""
        for w in words:
            if len(line + " " + w) <= 35:
                line += " " + w if line else w
            else:
                lines.append(line)
                line = w
        if line:
            lines.append(line)
        
        y = 250
        for l in lines:
            draw.text((100, y), l, fill=(255, 255, 255), font=font)
            y += 50
        
        img.save(img_path)
        return img_path
    except:
        return None

# ========== 5. تخزين مؤقت ==========
user_data = {}

# ========== 6. أوامر البوت ==========
@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.chat.id
    points = get_user(user_id)
    
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("🎬 تحويل محاضرة", callback_data="convert"),
        InlineKeyboardButton("📸 إضافة صورة", callback_data="add_image"),
        InlineKeyboardButton("🖼️ قائمة الصور", callback_data="list_images")
    )
    if user_id == OWNER_ID:
        markup.add(InlineKeyboardButton("🔧 لوحة التحكم", callback_data="admin"))
    
    bot.send_message(user_id,
        f"🎬 *بوت تحويل المحاضرات إلى فيديو*\n\n"
        f"⭐ رصيدك: {points} نقطة\n"
        f"• كل تحويل = 1 نقطة\n\n"
        f"📸 *كيف يعمل؟*\n"
        f"1. أضف صوراً مع كلمات مفتاحية\n"
        f"2. أرسل محاضرة (نص أو ملف)\n"
        f"3. سأقوم بعرض الصور المناسبة\n"
        f"4. سأرسل الشرح بعد الفيديو\n\n"
        f"@zakros_probot",
        parse_mode="Markdown", reply_markup=markup)

# ========== 7. إضافة الصور (للمالك فقط) ==========
@bot.callback_query_handler(func=lambda call: call.data == "add_image")
def add_image_start(call):
    if call.message.chat.id != OWNER_ID:
        bot.answer_callback_query(call.id, "🔒 فقط المالك يمكنه إضافة صور", True)
        return
    
    user_data[call.message.chat.id] = {"step": "waiting_keyword"}
    bot.edit_message_text("📝 *أرسل الكلمة المفتاحية لهذه الصورة*\nمثال: قلب، شجرة، ولد، سيارة", call.message.chat.id, call.message.message_id, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.chat.id in user_data and user_data.get(m.chat.id, {}).get("step") == "waiting_keyword")
def get_keyword(message):
    user_id = message.chat.id
    keyword = message.text.strip()
    user_data[user_id]["keyword"] = keyword
    user_data[user_id]["step"] = "waiting_image"
    bot.send_message(user_id, "🖼️ *أرسل الصورة الآن*", parse_mode="Markdown")

@bot.message_handler(content_types=['photo'])
def handle_image(message):
    user_id = message.chat.id
    data = user_data.get(user_id)
    
    if not data or data.get("step") != "waiting_image":
        bot.reply_to(message, "❌ ابدأ بـ /start ثم اختر 'إضافة صورة'")
        return
    
    keyword = data["keyword"]
    file_id = message.photo[-1].file_id
    
    add_image(keyword, file_id)
    
    bot.reply_to(message, f"✅ تم حفظ الصورة\n📌 الكلمة المفتاحية: {keyword}")
    del user_data[user_id]

@bot.callback_query_handler(func=lambda call: call.data == "list_images")
def list_images(call):
    if call.message.chat.id != OWNER_ID:
        bot.answer_callback_query(call.id, "🔒 فقط المالك يمكنه رؤية الصور", True)
        return
    
    images = get_all_images()
    if not images:
        bot.send_message(call.message.chat.id, "📭 لا توجد صور مضافة بعد")
        return
    
    text = "🖼️ *قائمة الصور والكلمات المفتاحية:*\n\n"
    for keyword, file_id in images:
        text += f"• {keyword}\n"
    
    bot.send_message(call.message.chat.id, text, parse_mode="Markdown")

# ========== 8. تحويل المحاضرة إلى فيديو ==========
@bot.callback_query_handler(func=lambda call: call.data == "convert")
def convert_start(call):
    user_id = call.message.chat.id
    points = get_user(user_id)
    if points < 1:
        bot.answer_callback_query(call.id, "ليس لديك نقاط كافية!", True)
        return
    
    user_data[user_id] = {"step": "waiting_content"}
    bot.edit_message_text("📝 *أرسل المحاضرة (نص أو ملف txt/pdf/docx)*", user_id, call.message.message_id, parse_mode="Markdown")

@bot.message_handler(content_types=['text', 'document'])
def handle_lecture(message):
    user_id = message.chat.id
    data = user_data.get(user_id)
    
    if not data or data.get("step") != "waiting_content":
        return
    
    content = None
    file_name = None
    
    if message.text and not message.text.startswith('/'):
        content = message.text.strip()
        file_name = "text_lecture.txt"
    elif message.document:
        file_name = message.document.file_name
        ext = os.path.splitext(file_name)[1].lower()
        if ext not in ['.txt', '.pdf', '.docx']:
            bot.reply_to(message, "❌ نوع غير مدعوم. الأنواع: txt, pdf, docx")
            return
        
        try:
            file_info = bot.get_file(message.document.file_id)
            downloaded = bot.download_file(file_info.file_path)
            with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
                tmp.write(downloaded)
                tmp_path = tmp.name
            content = extract_text(tmp_path)
            os.unlink(tmp_path)
        except:
            bot.reply_to(message, "❌ خطأ في قراءة الملف")
            return
    else:
        return
    
    if not content or len(content) < 50:
        bot.reply_to(message, "❌ المحتوى قصير جداً (يحتاج 50 حرفاً)")
        return
    
    # استهلاك نقطة
    update_points(user_id, -1)
    
    status = bot.reply_to(message, "🎬 جاري تحليل المحاضرة...")
    
    try:
        # تحليل المحاضرة
        parts = analyze_lecture(content)
        
        if not parts:
            bot.edit_message_text("❌ لا يوجد محتوى صالح", user_id, status.message_id)
            update_points(user_id, 1)
            return
        
        bot.edit_message_text(f"📊 تم التقسيم إلى {len(parts)} أقسام\n🎬 جاري إنشاء الفيديو...", user_id, status.message_id)
        
        # إنشاء الفيديو
        video_path = tempfile.mktemp(suffix='.mp4')
        
        if create_video(parts, video_path, duration_per_slide=3):
            new_points = get_user(user_id)
            
            # إرسال الفيديو
            with open(video_path, 'rb') as f:
                bot.send_video(user_id, f, caption=f"✅ تم إنشاء الفيديو\n📊 عدد الأقسام: {len(parts)}\n⭐ النقاط المتبقية: {new_points}", supports_streaming=True)
            os.unlink(video_path)
            
            # إرسال الشرح النصي
            explanation = f"📝 *شرح المحاضرة*\n\n"
            for i, part in enumerate(parts):
                explanation += f"{i+1}. {part}\n\n"
            
            bot.send_message(user_id, explanation, parse_mode="Markdown")
        else:
            bot.edit_message_text("❌ فشل إنشاء الفيديو", user_id, status.message_id)
            update_points(user_id, 1)
        
        bot.delete_message(user_id, status.message_id)
        del user_data[user_id]
        
    except Exception as e:
        bot.edit_message_text(f"❌ خطأ: {str(e)[:100]}", user_id, status.message_id)
        update_points(user_id, 1)

# ========== 9. لوحة تحكم المالك ==========
@bot.callback_query_handler(func=lambda call: call.data == "admin")
def admin_panel(call):
    if call.message.chat.id != OWNER_ID:
        bot.answer_callback_query(call.id, "غير مصرح", True)
        return
    
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("➕ إضافة نقاط", callback_data="add_pts"))
    markup.add(InlineKeyboardButton("📊 إحصائيات", callback_data="stats"))
    bot.send_message(OWNER_ID, "🔧 لوحة التحكم", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "add_pts")
def add_points(call):
    if call.message.chat.id != OWNER_ID:
        return
    msg = bot.send_message(OWNER_ID, "أرسل: معرف_المستخدم عدد_النقاط\nمثال: 123456789 5")
    bot.register_next_step_handler(msg, add_points_step)

def add_points_step(message):
    try:
        uid, pts = map(int, message.text.split())
        update_points(uid, pts)
        bot.send_message(OWNER_ID, f"✅ تم إضافة {pts} نقطة")
    except:
        bot.send_message(OWNER_ID, "❌ صيغة غير صحيحة")

@bot.callback_query_handler(func=lambda call: call.data == "stats")
def show_stats(call):
    if call.message.chat.id != OWNER_ID:
        return
    c.execute("SELECT COUNT(*) FROM users")
    users = c.fetchone()[0]
    c.execute("SELECT SUM(points) FROM users")
    points = c.fetchone()[0] or 0
    c.execute("SELECT COUNT(*) FROM images")
    images = c.fetchone()[0]
    bot.send_message(OWNER_ID, f"📊 إحصائيات\n👥 المستخدمون: {users}\n⭐ النقاط: {points}\n🖼️ الصور المحفوظة: {images}")

if __name__ == "__main__":
    print("✅ البوت يعمل...")
    bot.remove_webhook()
    bot.infinity_polling()
